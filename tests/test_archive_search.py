"""Regressão: a busca de livros no Archive.org estava retornando 0 (forçava
idioma português e não filtrava mediatype:texts)."""

from scrapers.archive_scraper import ArchiveOrgScraper


class FakeResp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def test_search_query_uses_title_and_texts_without_language(monkeypatch):
    sc = ArchiveOrgScraper()
    queries = []

    def fake_make_request(url, params=None, retries=0):
        queries.append(params.get("q"))
        return FakeResp({"response": {"docs": [
            {"identifier": "sw1", "title": "Star Wars Insider", "mediatype": "texts"},
            {"identifier": "sw2", "title": ["Star Wars: Darth Vader"], "mediatype": "texts"},
        ]}})

    monkeypatch.setattr(sc, "make_request", fake_make_request)
    res = sc.search("Star Wars", formats=["pdf"])

    # A primeira consulta continua sendo a estrita, por título. Como ela rendeu
    # pouco, vem a consulta ampla de complemento (ver test_search_by.py).
    assert 'title:("Star Wars")' in queries[0]
    assert all("mediatype:texts" in q for q in queries)
    assert all("language:" not in q for q in queries)   # não força português
    assert len(res) == 2                                # sem duplicar identifiers
    assert res[0].title == "Star Wars Insider"
    assert res[1].title == "Star Wars: Darth Vader"     # title em lista -> 1º elemento


def test_search_with_language_adds_filter(monkeypatch):
    sc = ArchiveOrgScraper()
    captured = {}

    def fake(url, params=None, retries=0):
        captured["q"] = params.get("q")
        return FakeResp({"response": {"docs": []}})

    monkeypatch.setattr(sc, "make_request", fake)
    sc.search("Dom Casmurro", language="pt")
    assert "language:" in captured["q"]
    assert "portuguese" in captured["q"]
    # inglês
    sc.search("Dracula", language="en")
    assert "english" in captured["q"]


def test_get_series_info_filters_only_book_files_and_prefers_pdf(monkeypatch):
    sc = ArchiveOrgScraper()

    def fake_make_request(url, params=None, retries=0):
        return FakeResp({
            "metadata": {"title": "Dom Casmurro"},
            "files": [
                {"name": "__ia_thumb.jpg", "source": "original"},
                {"name": "meta.xml", "source": "original"},
                {"name": "livro.epub", "source": "derivative"},
                {"name": "livro.pdf", "source": "original"},
            ],
        })

    monkeypatch.setattr(sc, "make_request", fake_make_request)
    info = sc.get_series_info("https://archive.org/details/domcasmurro")
    files = info["downloadable_files"]
    exts = [f["format"] for f in files]
    assert "jpg" not in exts and "xml" not in exts     # lixo filtrado
    assert exts[0] == "pdf"                             # PDF preferido
    assert info["download_url"].endswith("livro.pdf")
    assert info["format"] == "pdf"
