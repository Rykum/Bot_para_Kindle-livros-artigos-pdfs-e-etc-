"""Fase 4: OAPEN e Zenodo — livros acadêmicos de acesso aberto.

Ambos guardam muita coisa além de livro (licença, capa, planilha, código), então
o filtro de arquivos é o que separa um resultado útil de lixo.
"""

from scrapers.oapen_scraper import OapenScraper
from scrapers.zenodo_scraper import ZenodoScraper


class FakeResp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


# =========================== OAPEN ===========================

def _item(nome="Livro Aberto", autor="Silva, Ana", bitstreams=None):
    return {
        "uuid": "u-1", "name": nome, "handle": "20.500/123",
        "metadata": [
            {"key": "dc.contributor.author", "value": autor},
            {"key": "dc.date.issued", "value": "2021"},
            {"key": "dc.language", "value": "por"},
        ],
        "bitstreams": bitstreams if bitstreams is not None else [
            {"name": "livro.pdf", "mimeType": "application/pdf",
             "retrieveLink": "/rest/bitstreams/abc/retrieve", "sizeBytes": 100},
        ],
    }


def test_oapen_keeps_only_book_files(monkeypatch):
    """Licença e capa não podem virar resultado de download."""
    sc = OapenScraper()

    def fake(url, params=None, retries=0):
        return FakeResp([_item(bitstreams=[
            {"name": "license.txt", "mimeType": "text/plain", "retrieveLink": "/a"},
            {"name": "capa.png", "mimeType": "image/png", "retrieveLink": "/b"},
            {"name": "livro.pdf", "mimeType": "application/pdf", "retrieveLink": "/c"},
        ])])

    monkeypatch.setattr(sc, "make_request", fake)
    r = sc.search("brasil")[0]
    assert [f["format"] for f in r.metadata["files"]] == ["pdf"]


def test_oapen_prefers_pdf_over_epub(monkeypatch):
    sc = OapenScraper()

    def fake(url, params=None, retries=0):
        return FakeResp([_item(bitstreams=[
            {"name": "l.epub", "mimeType": "application/epub+zip", "retrieveLink": "/e"},
            {"name": "l.pdf", "mimeType": "application/pdf", "retrieveLink": "/p"},
        ])])

    monkeypatch.setattr(sc, "make_request", fake)
    r = sc.search("brasil")[0]
    assert r.format_type == "pdf"
    assert r.download_url.endswith("/p")


def test_oapen_makes_the_retrieve_link_absolute(monkeypatch):
    """O DSpace devolve caminho relativo; baixar assim falharia."""
    sc = OapenScraper()
    monkeypatch.setattr(sc, "make_request",
                        lambda *a, **k: FakeResp([_item()]))
    r = sc.search("brasil")[0]
    assert r.download_url == "https://library.oapen.org/rest/bitstreams/abc/retrieve"


def test_oapen_items_without_files_are_skipped(monkeypatch):
    sc = OapenScraper()
    monkeypatch.setattr(sc, "make_request",
                        lambda *a, **k: FakeResp([_item(bitstreams=[])]))
    assert sc.search("brasil") == []


def test_oapen_author_mode_filters_by_author(monkeypatch):
    sc = OapenScraper()

    def fake(url, params=None, retries=0):
        return FakeResp([
            _item(nome="Do autor certo", autor="Machado de Assis"),
            _item(nome="De outro", autor="Outro Nome"),
        ])

    monkeypatch.setattr(sc, "make_request", fake)
    assert [r.title for r in sc.search("Machado de Assis", search_by="autor")] == ["Do autor certo"]


def test_oapen_empty_query_makes_no_request(monkeypatch):
    sc = OapenScraper()
    chamadas = []
    monkeypatch.setattr(sc, "make_request",
                        lambda *a, **k: chamadas.append(1) or FakeResp([]))
    assert sc.search("") == []
    assert not chamadas


# =========================== Zenodo ===========================

def _record(titulo="Estudo", autores=("Ana Silva",), arquivos=None):
    return {
        "id": 123,
        "metadata": {
            "title": titulo,
            "creators": [{"name": n} for n in autores],
            "publication_date": "2021-05-01",
            "doi": "10.5281/zenodo.123",
        },
        "files": arquivos if arquivos is not None else [
            {"key": "Livro.pdf", "size": 500,
             "links": {"self": "https://zenodo.org/api/records/123/files/Livro.pdf"}},
        ],
    }


def _hits(*records):
    return {"hits": {"hits": list(records), "total": len(records)}}


def test_zenodo_title_mode_uses_the_title_field(monkeypatch):
    sc = ZenodoScraper()
    captured = {}

    def fake(url, params=None, retries=0):
        captured.update(params or {})
        return FakeResp(_hits())

    monkeypatch.setattr(sc, "make_request", fake)
    sc.search("Dom Casmurro", search_by="titulo")
    assert captured["q"] == 'title:"Dom Casmurro"'


def test_zenodo_author_mode_uses_the_creators_field(monkeypatch):
    sc = ZenodoScraper()
    captured = {}

    def fake(url, params=None, retries=0):
        captured.update(params or {})
        return FakeResp(_hits())

    monkeypatch.setattr(sc, "make_request", fake)
    sc.search("Machado de Assis", search_by="autor")
    assert captured["q"] == 'creators.name:"Machado de Assis"'


def test_zenodo_tudo_mode_is_a_free_query(monkeypatch):
    sc = ZenodoScraper()
    captured = {}
    monkeypatch.setattr(sc, "make_request",
                        lambda url, params=None, retries=0: captured.update(params or {}) or FakeResp(_hits()))
    sc.search("literatura brasileira", search_by="tudo")
    assert captured["q"] == "literatura brasileira"


def test_zenodo_ignores_non_book_files(monkeypatch):
    """Zenodo guarda dado bruto e código junto com a publicação."""
    sc = ZenodoScraper()

    def fake(url, params=None, retries=0):
        return FakeResp(_hits(_record(arquivos=[
            {"key": "dados.csv", "links": {"self": "u1"}},
            {"key": "codigo.zip", "links": {"self": "u2"}},
            {"key": "Livro.pdf", "links": {"self": "u3"}},
        ])))

    monkeypatch.setattr(sc, "make_request", fake)
    r = sc.search("x")[0]
    assert [f["format"] for f in r.metadata["files"]] == ["pdf"]
    assert r.download_url == "u3"


def test_zenodo_records_without_book_files_are_skipped(monkeypatch):
    sc = ZenodoScraper()

    def fake(url, params=None, retries=0):
        return FakeResp(_hits(_record(arquivos=[{"key": "dados.csv", "links": {"self": "u"}}])))

    monkeypatch.setattr(sc, "make_request", fake)
    assert sc.search("x") == []


def test_zenodo_joins_authors_and_extracts_year(monkeypatch):
    sc = ZenodoScraper()

    def fake(url, params=None, retries=0):
        return FakeResp(_hits(_record(autores=("Ana Silva", "João Souza"))))

    monkeypatch.setattr(sc, "make_request", fake)
    r = sc.search("x")[0]
    assert r.metadata["creator"] == "Ana Silva, João Souza"
    assert r.metadata["year"] == "2021"


def test_zenodo_get_series_info_reads_the_record(monkeypatch):
    sc = ZenodoScraper()
    visto = {}

    def fake(url, params=None, retries=0):
        visto["url"] = url
        return FakeResp(_record())

    monkeypatch.setattr(sc, "make_request", fake)
    info = sc.get_series_info("https://zenodo.org/records/123")
    assert visto["url"].endswith("/123")
    assert info["format"] == "pdf"
    assert info["total_files"] == 1
    assert info["available_chapters"][0]["download_url"] == info["download_url"]


# ============ regressão: cabeçalhos de API ============

def test_api_sources_do_not_pretend_to_be_a_browser():
    """
    O padrão do BaseScraper se passa por Chrome pedindo text/html. O Zenodo
    responde 403 a isso e o DSpace do OAPEN devolve HTML em vez de JSON — as
    duas fontes ficavam silenciosamente vazias na busca real.
    """
    from scrapers.openlibrary_scraper import OpenLibraryScraper
    from scrapers.wikisource_scraper import WikisourceScraper

    for cls in (ZenodoScraper, OapenScraper, OpenLibraryScraper, WikisourceScraper):
        headers = cls().session.headers
        assert 'Mozilla' not in headers['User-Agent'], cls.__name__
        assert headers['User-Agent'].startswith('MediaBot/'), cls.__name__
        assert headers['Accept'] == 'application/json', cls.__name__
