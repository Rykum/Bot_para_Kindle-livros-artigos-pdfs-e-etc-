from app.api import Api
from app.bot_service import BotService


class FakeBot:
    def search_series(self, query, media_type="manga"):
        return [{"title": query, "source": "mangadex", "format_type": "cbz", "url": "http://x"}]

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


def test_clear_cache_sync():
    events = []
    api, service = make_api(events)
    try:
        assert api.clear_cache() == {"removed": 4}
    finally:
        service.stop()
