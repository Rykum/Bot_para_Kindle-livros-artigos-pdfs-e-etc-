import time

from app.api import Api
from app.bot_service import BotService


class FakeBot:
    def __init__(self):
        self.download_kwargs = None

    def list_series_chapters(self, series, media_type="manga", source_name="mangadex",
                             language="pt-br", fallback_language=None):
        return {"title": series, "available": [1.0, 2.0], "downloaded": [],
                "missing": [1.0, 2.0], "by_language": {1.0: [language]}, "source": source_name}

    def download_complete_series(self, series, **kwargs):
        self.download_kwargs = kwargs
        return {"total": 0, "downloaded": 0, "failed": 0, "cancelled": False, "failed_chapters": []}

    def cleanup(self):
        pass


def make_api(events, bot):
    service = BotService(bot_factory=lambda: bot, event_sink=lambda n, p: events.append((n, p)))
    api = Api(service)
    service.start()
    return api, service


def test_list_chapters_emits_event():
    events, bot = [], FakeBot()
    api, service = make_api(events, bot)
    try:
        ack = api.list_chapters("Dandadan", language="en", fallback_language="pt-br")
        assert "job_id" in ack
        deadline = time.time() + 5
        while time.time() < deadline and not any(n == "chapters_list" for n, _ in events):
            time.sleep(0.01)
        payload = [p for n, p in events if n == "chapters_list"]
        assert payload and payload[0]["available"] == [1.0, 2.0]
    finally:
        service.stop()


def test_download_series_forwards_selection_and_language():
    events, bot = [], FakeBot()
    api, service = make_api(events, bot)
    try:
        api.download_series("Dandadan", chapters=[1.0], language="en", fallback_language="es")
        deadline = time.time() + 5
        while time.time() < deadline and bot.download_kwargs is None:
            time.sleep(0.01)
        assert bot.download_kwargs["chapters"] == [1.0]
        assert bot.download_kwargs["language"] == "en"
        assert bot.download_kwargs["fallback_language"] == "es"
    finally:
        service.stop()
