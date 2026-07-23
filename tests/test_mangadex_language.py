from scrapers.mangadex_scraper import MangaDexScraper


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_get_series_info_uses_selected_language(monkeypatch):
    scraper = MangaDexScraper()
    captured = {}

    def fake_make_request(url, params=None, retries=0):
        captured.setdefault("langs", [])
        if "/feed" in url:
            captured["langs"].append(params.get("translatedLanguage[]"))
            return FakeResponse({"data": [
                {"id": "c1", "attributes": {"chapter": "1", "volume": "1", "title": "A"}},
            ]})
        return FakeResponse({"data": {"attributes": {"title": {"en": "X"}}}})

    monkeypatch.setattr(scraper, "make_request", fake_make_request)
    info = scraper.get_series_info("https://mangadex.org/title/abc", language="en")

    assert captured["langs"] == [["en"]]
    assert info["available_chapters"][0]["chapter"] == 1.0


def test_get_series_info_defaults_to_pt_br(monkeypatch):
    scraper = MangaDexScraper()
    captured = {}

    def fake_make_request(url, params=None, retries=0):
        if "/feed" in url:
            captured["lang"] = params.get("translatedLanguage[]")
            return FakeResponse({"data": []})
        return FakeResponse({"data": {"attributes": {"title": {"en": "X"}}}})

    monkeypatch.setattr(scraper, "make_request", fake_make_request)
    scraper.get_series_info("https://mangadex.org/title/abc")
    assert captured["lang"] == ["pt-br"]
