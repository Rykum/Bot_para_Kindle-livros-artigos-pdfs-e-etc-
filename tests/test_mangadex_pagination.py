from scrapers.mangadex_scraper import MangaDexScraper


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _chapters(start, end):
    return [{"id": f"c{i}", "attributes": {"chapter": str(i), "volume": "1"}} for i in range(start, end + 1)]


def test_get_series_info_paginates_beyond_500(monkeypatch):
    scraper = MangaDexScraper()
    calls = {"feed": 0}

    def fake_make_request(url, params=None, retries=0):
        if "/feed" in url:
            calls["feed"] += 1
            offset = params.get("offset", 0)
            if offset == 0:
                return FakeResponse({"data": _chapters(1, 500), "total": 620})   # página cheia
            return FakeResponse({"data": _chapters(501, 620), "total": 620})       # última, parcial
        return FakeResponse({"data": {"attributes": {"title": {"en": "X"}}}})

    monkeypatch.setattr(scraper, "make_request", fake_make_request)
    info = scraper.get_series_info("https://mangadex.org/title/abc")

    assert calls["feed"] == 2                      # paginou
    assert info["total_chapters"] == 620           # pegou todos, não só 500
    assert len(info["available_chapters"]) == 620


def test_get_series_info_single_page_stops(monkeypatch):
    scraper = MangaDexScraper()
    calls = {"feed": 0}

    def fake_make_request(url, params=None, retries=0):
        if "/feed" in url:
            calls["feed"] += 1
            return FakeResponse({"data": _chapters(1, 30), "total": 30})  # parcial → para
        return FakeResponse({"data": {"attributes": {"title": {"en": "X"}}}})

    monkeypatch.setattr(scraper, "make_request", fake_make_request)
    info = scraper.get_series_info("https://mangadex.org/title/abc")
    assert calls["feed"] == 1
    assert info["total_chapters"] == 30
