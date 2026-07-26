"""Open Library como camada de precisão.

Buscar "Dune" por texto no Archive.org devolvia "Dune Buggy Rental". O Open
Library conhece a obra e o exemplar correspondente no Archive.org, então a
busca passa a acertar o livro certo.
"""

import pytest

from scrapers.openlibrary_scraper import OpenLibraryScraper


class FakeResp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def _doc(title, autores, ia, **extra):
    d = {"key": f"/works/{title}", "title": title, "author_name": autores,
         "ia": ia, "first_publish_year": 1965, "isbn": ["9780441013593"],
         "language": ["eng"], "edition_count": 3}
    d.update(extra)
    return d


def test_search_by_title_uses_the_title_field(monkeypatch):
    sc = OpenLibraryScraper()
    captured = {}

    def fake(url, params=None, retries=0):
        captured.update(params or {})
        return FakeResp({"docs": []})

    monkeypatch.setattr(sc, "make_request", fake)
    sc.search("Dune", search_by="titulo")
    assert captured["title"] == "Dune"
    assert "author" not in captured and "q" not in captured


def test_search_by_author_uses_the_author_field(monkeypatch):
    sc = OpenLibraryScraper()
    captured = {}

    def fake(url, params=None, retries=0):
        captured.update(params or {})
        return FakeResp({"docs": []})

    monkeypatch.setattr(sc, "make_request", fake)
    sc.search("Frank Herbert", search_by="autor")
    assert captured["author"] == "Frank Herbert"
    assert "title" not in captured


def test_search_tudo_uses_free_query(monkeypatch):
    sc = OpenLibraryScraper()
    captured = {}

    def fake(url, params=None, retries=0):
        captured.update(params or {})
        return FakeResp({"docs": []})

    monkeypatch.setattr(sc, "make_request", fake)
    sc.search("Dune Frank Herbert", search_by="tudo")
    assert captured["q"] == "Dune Frank Herbert"


@pytest.mark.parametrize("entrada,esperado", [
    ("pt", "por"), ("pt-br", "por"), ("en", "eng"), ("es", "spa"),
])
def test_language_is_converted_to_three_letter_code(monkeypatch, entrada, esperado):
    """O Open Library usa ISO 639-2; mandar 'pt' devolveria vazio."""
    sc = OpenLibraryScraper()
    captured = {}

    def fake(url, params=None, retries=0):
        captured.update(params or {})
        return FakeResp({"docs": []})

    monkeypatch.setattr(sc, "make_request", fake)
    sc.search("Dom Casmurro", language=entrada)
    assert captured["language"] == esperado


def test_unknown_language_is_not_sent(monkeypatch):
    sc = OpenLibraryScraper()
    captured = {}

    def fake(url, params=None, retries=0):
        captured.update(params or {})
        return FakeResp({"docs": []})

    monkeypatch.setattr(sc, "make_request", fake)
    sc.search("Dom Casmurro", language="")
    assert "language" not in captured


def test_works_without_archive_copies_are_skipped(monkeypatch):
    """Obra sem exemplar no Archive.org não tem o que baixar."""
    sc = OpenLibraryScraper()

    def fake(url, params=None, retries=0):
        return FakeResp({"docs": [
            _doc("Dune", ["Frank Herbert"], ["dune0000herb"]),
            _doc("Dune sem cópia", ["Frank Herbert"], []),
            _doc("Dune ia nulo", ["Frank Herbert"], None),
        ]})

    monkeypatch.setattr(sc, "make_request", fake)
    res = sc.search("Dune")
    assert [r.title for r in res] == ["Dune"]


def test_result_points_at_the_archive_item(monkeypatch):
    sc = OpenLibraryScraper()

    def fake(url, params=None, retries=0):
        return FakeResp({"docs": [
            _doc("Dune", ["Frank Herbert"], ["dune0000herb", "dune0001herb"]),
        ]})

    monkeypatch.setattr(sc, "make_request", fake)
    r = sc.search("Dune")[0]
    assert r.url == "https://archive.org/details/dune0000herb"
    assert r.source == "Open Library"
    assert r.metadata["creator"] == "Frank Herbert"
    assert r.metadata["isbn"] == "9780441013593"
    assert r.metadata["copies"] == ["dune0000herb", "dune0001herb"]


def test_multiple_authors_are_joined(monkeypatch):
    sc = OpenLibraryScraper()

    def fake(url, params=None, retries=0):
        return FakeResp({"docs": [
            _doc("Mindhunter", ["John E. Douglas", "Mark Olshaker"], ["mh0000doug"]),
        ]})

    monkeypatch.setattr(sc, "make_request", fake)
    assert sc.search("Mindhunter")[0].metadata["creator"] == "John E. Douglas, Mark Olshaker"


def test_empty_query_makes_no_request(monkeypatch):
    sc = OpenLibraryScraper()
    chamadas = []

    monkeypatch.setattr(sc, "make_request",
                        lambda *a, **k: chamadas.append(1) or FakeResp({"docs": []}))
    assert sc.search("   ") == []
    assert not chamadas


def test_get_series_info_delegates_to_archive(monkeypatch):
    """O exemplar é um item do Archive.org — a leitura de arquivos é de lá."""
    sc = OpenLibraryScraper()
    visto = {}

    def fake_archive(series_url, language="pt-br"):
        visto["url"] = series_url
        return {"download_url": "https://archive.org/download/x/livro.pdf", "format": "pdf"}

    monkeypatch.setattr(sc._archive, "get_series_info", fake_archive)
    info = sc.get_series_info("https://archive.org/details/dune0000herb")
    assert visto["url"] == "https://archive.org/details/dune0000herb"
    assert info["format"] == "pdf"


def test_missing_fields_do_not_crash(monkeypatch):
    sc = OpenLibraryScraper()

    def fake(url, params=None, retries=0):
        return FakeResp({"docs": [{"ia": ["x0000y"]}]})   # sem título nem autor

    monkeypatch.setattr(sc, "make_request", fake)
    r = sc.search("qualquer")[0]
    assert r.title == "Sem título"
    assert r.metadata["creator"] == ""
    assert r.metadata["isbn"] is None
