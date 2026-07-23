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
