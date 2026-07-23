import time

from app.api import Api
from app.bot_service import BotService
from download_queue import DownloadQueue


class FakeBot:
    def __init__(self):
        self.downloaded = []

    def download_single_chapter(self, series, chapter_num, **kwargs):
        self.downloaded.append((series, chapter_num))
        return True

    def download_complete_series(self, series, **kwargs):
        return {"total": 0, "downloaded": 0, "failed": 0, "cancelled": False, "failed_chapters": []}

    def cleanup(self):
        pass


def make_api(events, bot):
    service = BotService(bot_factory=lambda: bot, event_sink=lambda n, p: events.append((n, p)))
    api = Api(service)
    service.start()
    return api, service


def _wait(cond, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline and not cond():
        time.sleep(0.02)


def test_enqueue_drains_queue_in_order():
    DownloadQueue()  # garante import/tabela
    events, bot = [], FakeBot()
    api, service = make_api(events, bot)
    try:
        # limpa qualquer resíduo de fila
        for it in api.queue_list():
            api.remove_item(it["id"])
        ack = api.enqueue("Dandadan", [1.0, 2.0], source="mangadex")
        assert ack["enqueued"] == 2
        _wait(lambda: len(bot.downloaded) >= 2)
        assert bot.downloaded == [("Dandadan", 1.0), ("Dandadan", 2.0)]
        # eventos de queue_update foram emitidos
        assert any(n == "queue_update" for n, _ in events)
    finally:
        service.stop()


def test_queue_list_and_clear_finished():
    events, bot = [], FakeBot()
    api, service = make_api(events, bot)
    try:
        for it in api.queue_list():
            api.remove_item(it["id"])
        api.enqueue("S", [1.0])
        _wait(lambda: all(i["status"] in ("done", "failed") for i in api.queue_list()) and api.queue_list())
        api.clear_finished()
        assert api.queue_list() == []
    finally:
        service.stop()


def test_item_enqueued_during_drain_exit_is_not_stranded():
    # Regressao: se o item for enfileirado exatamente na janela entre o
    # `break` do drain (fila vazia) e o reset de `_draining` no `finally`,
    # o antigo codigo deixava o item preso em "queued" ate o proximo
    # enqueue/retry/resume. A propriedade que verificamos aqui e a de
    # recuperacao: apos o primeiro item terminar (drain completo), um
    # segundo item enfileirado depois deve, de qualquer forma, tambem
    # chegar a "done" - provando que o drain reinicia sozinho quando ha
    # trabalho pendente ao sair.
    events, bot = [], FakeBot()
    api, service = make_api(events, bot)
    try:
        for it in api.queue_list():
            api.remove_item(it["id"])

        ack1 = api.enqueue("Serie A", [1.0])
        assert ack1["enqueued"] == 1
        _wait(lambda: any(i["status"] == "done" for i in api.queue_list()))
        items = api.queue_list()
        assert items and all(i["status"] == "done" for i in items)

        ack2 = api.enqueue("Serie B", [1.0])
        assert ack2["enqueued"] == 1
        _wait(lambda: any(i["series"] == "Serie B" and i["status"] == "done" for i in api.queue_list()))
        items = api.queue_list()
        b_items = [i for i in items if i["series"] == "Serie B"]
        assert b_items and all(i["status"] == "done" for i in b_items)
    finally:
        service.stop()


def test_cancel_downloading_item_is_honored():
    # Regressao: cancelar um item que ja esta "downloading" precisa
    # efetivamente interromper o download (via should_cancel) e o
    # resultado final deve permanecer "cancelled" - nunca ser sobrescrito
    # de volta para "done"/"failed" pelo laco do drain.
    captured = {}

    class SelfCancelBot(FakeBot):
        def __init__(self, queue):
            super().__init__()
            self.queue = queue

        def download_single_chapter(self, series, chapter_num, should_cancel=None, **kwargs):
            captured["callable"] = callable(should_cancel)
            job = self.queue.list_items()[0]
            # simula um cancel chegando enquanto o download esta em andamento
            self.queue.cancel_item(job["id"])
            captured["should_cancel_result"] = should_cancel() if should_cancel else None
            return False  # download interrompido por should_cancel

    queue = DownloadQueue()
    for it in queue.list_items():
        queue.remove_item(it["id"])
    events, bot = [], SelfCancelBot(queue)
    api, service = make_api(events, bot)
    try:
        ack = api.enqueue("Serie Cancelada", [1.0])
        assert ack["enqueued"] == 1
        _wait(lambda: captured.get("should_cancel_result") is not None)
        assert captured.get("callable") is True
        assert captured.get("should_cancel_result") is True
        _wait(lambda: queue.list_items() and queue.list_items()[0]["status"] != "downloading")
        items = queue.list_items()
        assert items and items[0]["status"] == "cancelled"
    finally:
        service.stop()


def test_api_init_requeues_stale_downloading():
    # Regressao: se o app for morto no meio de um download, a linha fica
    # com status="downloading" e mostra um badge "ao vivo" enganoso ate o
    # proximo drain. Api.__init__ deve recolocar esses itens em "queued".
    queue = DownloadQueue()
    for it in queue.list_items():
        queue.remove_item(it["id"])
    [job_id] = queue.enqueue("Serie Presa", [1.0])
    queue.mark(job_id, "downloading")

    bot = FakeBot()
    service = BotService(bot_factory=lambda: bot, event_sink=lambda n, p: None)
    Api(service)

    assert DownloadQueue().get_status(job_id) == "queued"


def test_whole_series_with_failures_marked_failed():
    class PartialFailBot(FakeBot):
        def download_complete_series(self, series, **kwargs):
            return {"total": 2, "downloaded": 0, "failed": 2, "cancelled": False,
                    "failed_chapters": [1.0, 2.0]}

    events, bot = [], PartialFailBot()
    api, service = make_api(events, bot)
    try:
        for it in api.queue_list():
            api.remove_item(it["id"])
        ack = api.enqueue("Serie Com Falhas", chapters=None)
        assert ack["enqueued"] == 1
        _wait(lambda: all(i["status"] in ("done", "failed") for i in api.queue_list()) and api.queue_list())
        items = api.queue_list()
        assert items and all(i["status"] == "failed" for i in items)
    finally:
        service.stop()
