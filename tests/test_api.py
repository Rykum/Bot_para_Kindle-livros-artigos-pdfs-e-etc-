from app.api import Api
from app.bot_service import BotService


class FakeBot:
    def __init__(self):
        self.last_search = None
        self.last_explorar = None

    def search_series(self, query, media_type="manga", language=None, search_by="titulo"):
        self.last_search = {"query": query, "media_type": media_type,
                            "language": language, "search_by": search_by}
        return [{"title": query, "source": "mangadex", "format_type": "cbz", "url": "http://x"}]

    def explorar_genero(self, media_type, genero, subgenero=None, ordenacao="relevancia"):
        self.last_explorar = {"media_type": media_type, "genero": genero,
                              "subgenero": subgenero, "ordenacao": ordenacao}
        if genero == "SemResultado":
            return []
        return [{"title": genero, "source": "mangadex", "metadata": {"identifier": "a"}}]

    def get_library_data(self):
        return [{"title": "Dandadan", "completion_percentage": 50.0, "is_complete": False}]

    def dashboard_stats(self):
        return {"total_series": 1, "total_downloaded": 3, "complete_collections": 0,
                "missing_total": 2, "by_format": {"cbz": 3}, "by_source": {"mangadex": 1}}

    def clear_cache(self):
        return 4

    def cleanup(self):
        pass


def make_api(events):
    service = BotService(bot_factory=FakeBot, event_sink=lambda n, p: events.append((n, p)))
    api = Api(service)
    service.start()
    return api, service


def test_library_returns_data_sync():
    events = []
    api, service = make_api(events)
    try:
        data = api.library()
        assert data[0]["title"] == "Dandadan"
    finally:
        service.stop()


def test_dashboard_stats_sync():
    events = []
    api, service = make_api(events)
    try:
        stats = api.dashboard_stats()
        assert stats["total_series"] == 1
        assert stats["by_format"] == {"cbz": 3}
    finally:
        service.stop()


def test_search_is_async_and_emits_results():
    import time
    events = []
    api, service = make_api(events)
    try:
        ack = api.search("Dandadan", "manga")
        assert "job_id" in ack
        deadline = time.time() + 5
        while time.time() < deadline:
            if any(n == "search_results" for n, _ in events):
                break
            time.sleep(0.01)
        payloads = [p for n, p in events if n == "search_results"]
        assert payloads and payloads[0]["results"][0]["title"] == "Dandadan"
    finally:
        service.stop()


def test_search_forwards_search_by_to_the_bot():
    """O modo de busca escolhido na interface precisa chegar ao scraper."""
    import time
    events = []
    service = BotService(bot_factory=FakeBot, event_sink=lambda n, p: events.append((n, p)))
    api = Api(service)
    service.start()
    try:
        api.search("Machado de Assis", "livro", "pt", "autor")
        deadline = time.time() + 5
        while time.time() < deadline:
            if any(n == "search_results" for n, _ in events):
                break
            time.sleep(0.01)
        assert service._bot.last_search == {
            "query": "Machado de Assis", "media_type": "livro",
            "language": "pt", "search_by": "autor",
        }
    finally:
        service.stop()


def test_explorar_emits_results_payload_without_onde_encontrar():
    """Payload de explorar_results tem as 3 chaves certas; com resultado, sem sugestão."""
    import time
    events = []
    api, service = make_api(events)
    try:
        ack = api.explorar("manga", "Terror")
        assert "job_id" in ack
        deadline = time.time() + 5
        while time.time() < deadline:
            if any(n == "explorar_results" for n, _ in events):
                break
            time.sleep(0.01)
        payloads = [p for n, p in events if n == "explorar_results"]
        assert payloads
        payload = payloads[0]
        assert set(["results", "genero", "onde_encontrar"]).issubset(payload.keys())
        assert payload["genero"] == "Terror"
        assert payload["results"][0]["title"] == "Terror"
        assert payload["onde_encontrar"] == []
    finally:
        service.stop()


def test_explorar_suggests_onde_encontrar_when_no_results():
    """Sem resultado, cai no mesmo cartão de 'onde encontrar' da busca por texto."""
    import time
    events = []
    api, service = make_api(events)
    try:
        api.explorar("livro", "SemResultado")
        deadline = time.time() + 5
        while time.time() < deadline:
            if any(n == "explorar_results" for n, _ in events):
                break
            time.sleep(0.01)
        payloads = [p for n, p in events if n == "explorar_results"]
        assert payloads
        assert payloads[0]["results"] == []
        assert payloads[0]["onde_encontrar"]  # não vazio
    finally:
        service.stop()


def test_generos_returns_taxonomy_for_media_type():
    events = []
    api, service = make_api(events)
    try:
        generos = api.generos("livro")
        assert any(g["nome"] == "Terror" for g in generos)
        terror = next(g for g in generos if g["nome"] == "Terror")
        assert "Gótico" in terror["subgeneros"]
    finally:
        service.stop()


def test_clear_cache_sync():
    events = []
    api, service = make_api(events)
    try:
        assert api.clear_cache() == {"removed": 4}
    finally:
        service.stop()


class FakeWindow:
    def __init__(self):
        self.calls = []

    def evaluate_js(self, script):
        self.calls.append(script)


def test_emit_event_pushes_to_window():
    events = []
    api, service = make_api(events)
    try:
        fake_window = FakeWindow()
        api.set_window(fake_window)
        api.emit_event("log", {"line": "oi"})
        assert len(fake_window.calls) == 1
        call = fake_window.calls[0]
        assert "window.pushEvent(" in call
        assert '"log"' in call
        assert '"oi"' in call
    finally:
        service.stop()


def test_emit_event_noop_without_window():
    events = []
    api, service = make_api(events)
    try:
        api.emit_event("log", {"line": "x"})  # não deve levantar exceção
    finally:
        service.stop()


class CancelableFakeBot:
    """Bot que expõe should_cancel() para fora via holder, permitindo ao teste
    disparar cancel_job() enquanto o download 'em andamento' aguarda."""

    def __init__(self, holder, proceed):
        self._holder = holder
        self._proceed = proceed

    def download_complete_series(self, series, media_type, source_name,
                                  progress_callback, should_cancel,
                                  chapters=None, language="pt-br", fallback_language=None):
        self._holder["should_cancel"] = should_cancel
        self._proceed.wait(timeout=2)
        self._holder["result"] = should_cancel()

    def cleanup(self):
        pass


def test_download_series_should_cancel_reflects_cancel_job():
    import threading
    import time

    events = []
    holder = {"should_cancel": None, "result": None}
    proceed = threading.Event()
    service = BotService(
        bot_factory=lambda: CancelableFakeBot(holder, proceed),
        event_sink=lambda n, p: events.append((n, p)),
    )
    api = Api(service)
    service.start()
    try:
        ack = api.download_series("X")

        deadline = time.time() + 2
        while time.time() < deadline and holder["should_cancel"] is None:
            time.sleep(0.01)
        assert holder["should_cancel"] is not None

        api.cancel_job(ack["job_id"])
        proceed.set()

        deadline = time.time() + 3
        while time.time() < deadline:
            if holder["result"] is not None or any(
                n in ("job_done", "job_error") for n, _ in events
            ):
                break
            time.sleep(0.01)

        assert holder["result"] is True
    finally:
        service.stop()
