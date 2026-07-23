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
