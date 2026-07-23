"""Regressão: capítulos com múltiplas versões (externa vazia + real baixável).

Bug real (Dandadan cap 1): a 1ª versão era externa (externalUrl, 0 páginas) e o
código desistia. A correção tenta as versões baixáveis até uma render páginas.
"""

from scrapers.mangadex_scraper import MangaDexScraper


def test_get_chapter_url_skips_external_and_picks_downloadable(monkeypatch):
    scraper = MangaDexScraper()
    info = {
        "available_chapters": [
            {"chapter": 1.0, "chapter_id": "ext", "external": True, "pages": 0,
             "volume": 1.0, "title": "oficial"},
            {"chapter": 1.0, "chapter_id": "real", "external": False, "pages": 68,
             "volume": 1.0, "title": "scan"},
        ]
    }
    monkeypatch.setattr(scraper, "get_series_info", lambda ref, language="pt-br": info)

    def fake_athome(cid):
        if cid == "real":
            return {"base_url": "http://h", "hash": "abc", "pages": ["1.jpg", "2.jpg"]}
        return {"base_url": "http://h", "hash": "", "pages": []}  # externa: sem páginas

    monkeypatch.setattr(scraper, "get_chapter_download_url", fake_athome)

    result = scraper.get_chapter_url("ref", 1.0, language="pt-br")
    assert result is not None
    assert result["chapter_id"] == "real"      # escolheu a versão baixável
    assert result["page_count"] == 2


def test_get_chapter_url_none_when_only_external(monkeypatch):
    scraper = MangaDexScraper()
    info = {"available_chapters": [
        {"chapter": 1.0, "chapter_id": "ext", "external": True, "pages": 0, "volume": 1.0},
    ]}
    monkeypatch.setattr(scraper, "get_series_info", lambda ref, language="pt-br": info)
    monkeypatch.setattr(scraper, "get_chapter_download_url",
                        lambda cid: {"base_url": "h", "hash": "", "pages": []})
    assert scraper.get_chapter_url("ref", 1.0, language="pt-br") is None


def test_get_chapter_url_reports_external_only_with_url(monkeypatch):
    """Capítulo só oficial/externo -> retorna marcador com o link (clareza)."""
    scraper = MangaDexScraper()
    info = {"available_chapters": [
        {"chapter": 1.0, "chapter_id": "ext", "external": True, "pages": 0,
         "external_url": "https://oficial.example/dandadan/1", "volume": 1.0},
    ]}
    monkeypatch.setattr(scraper, "get_series_info", lambda ref, language="pt-br": info)
    result = scraper.get_chapter_url("ref", 1.0, language="pt-br")
    assert result is not None
    assert result["download_type"] == "external_only"
    assert result["external_url"] == "https://oficial.example/dandadan/1"
