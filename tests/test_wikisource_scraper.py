"""Wikisource: texto transcrito em EPUB, não scan em PDF.

O ganho é de qualidade, não só de acervo — o EPUB gerado é texto pesquisável.
"""

import pytest

from scrapers.wikisource_scraper import WikisourceScraper


class FakeResp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def _hits(*titulos):
    return {"query": {"search": [{"title": t, "wordcount": 1000} for t in titulos]}}


def test_chapter_subpages_are_filtered_out(monkeypatch):
    """Sem o filtro, "Dom Casmurro" viraria 139 resultados do mesmo livro."""
    sc = WikisourceScraper()

    def fake(url, params=None, retries=0):
        return FakeResp(_hits("Dom Casmurro", "Dom Casmurro/I",
                              "Dom Casmurro/CXIX", "O Cortiço"))

    monkeypatch.setattr(sc, "make_request", fake)
    assert [r.title for r in sc.search("Dom Casmurro")] == ["Dom Casmurro", "O Cortiço"]


def test_search_asks_only_for_the_main_namespace(monkeypatch):
    sc = WikisourceScraper()
    captured = {}

    def fake(url, params=None, retries=0):
        captured.update(params or {})
        captured["url"] = url
        return FakeResp(_hits())

    monkeypatch.setattr(sc, "make_request", fake)
    sc.search("Machado de Assis")
    assert captured["srnamespace"] == 0
    assert captured["srsearch"] == "Machado de Assis"
    assert "pt.wikisource.org" in captured["url"]


@pytest.mark.parametrize("idioma,host", [
    (None, "pt.wikisource.org"), ("pt", "pt.wikisource.org"),
    ("pt-br", "pt.wikisource.org"), ("en", "en.wikisource.org"),
    ("es", "es.wikisource.org"), ("xx", "pt.wikisource.org"),
])
def test_language_picks_the_right_wiki(monkeypatch, idioma, host):
    """Cada idioma do Wikisource é um site separado."""
    sc = WikisourceScraper()
    captured = {}

    def fake(url, params=None, retries=0):
        captured["url"] = url
        return FakeResp(_hits())

    monkeypatch.setattr(sc, "make_request", fake)
    sc.search("Moby Dick", language=idioma)
    assert host in captured["url"]


def test_result_carries_a_ready_epub_link(monkeypatch):
    sc = WikisourceScraper()

    def fake(url, params=None, retries=0):
        return FakeResp(_hits("Dom Casmurro"))

    monkeypatch.setattr(sc, "make_request", fake)
    r = sc.search("Dom Casmurro")[0]
    assert r.format_type == "epub"
    assert "ws-export.wmcloud.org" in r.download_url
    assert "format=epub" in r.download_url
    assert "lang=pt" in r.download_url
    assert "Dom%20Casmurro" in r.download_url


def test_titles_with_spaces_and_accents_are_encoded(monkeypatch):
    sc = WikisourceScraper()

    def fake(url, params=None, retries=0):
        return FakeResp(_hits("O Cortiço"))

    monkeypatch.setattr(sc, "make_request", fake)
    r = sc.search("O Cortiço")[0]
    assert " " not in r.url and " " not in r.download_url
    assert "O_Corti" in r.url


def test_get_series_info_rebuilds_the_export_link():
    sc = WikisourceScraper()
    info = sc.get_series_info("https://pt.wikisource.org/wiki/Dom_Casmurro")
    assert info["format"] == "epub"
    assert info["title"] == "Dom Casmurro"
    assert "page=Dom%20Casmurro" in info["download_url"]
    assert info["available_chapters"][0]["download_url"] == info["download_url"]
    assert info["total_files"] == 1


def test_get_series_info_handles_percent_encoded_titles():
    sc = WikisourceScraper()
    info = sc.get_series_info("https://pt.wikisource.org/wiki/O_Corti%C3%A7o")
    assert info["title"] == "O Cortiço"


def test_get_series_info_uses_the_language_of_the_url():
    sc = WikisourceScraper()
    info = sc.get_series_info("https://en.wikisource.org/wiki/Moby-Dick")
    assert "lang=en" in info["download_url"]
    assert info["language"] == "en"


def test_empty_query_makes_no_request(monkeypatch):
    sc = WikisourceScraper()
    chamadas = []
    monkeypatch.setattr(sc, "make_request",
                        lambda *a, **k: chamadas.append(1) or FakeResp(_hits()))
    assert sc.search("  ") == []
    assert not chamadas
