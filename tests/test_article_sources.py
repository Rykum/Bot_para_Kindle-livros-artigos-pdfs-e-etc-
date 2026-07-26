"""Fase 5: OpenAlex e arXiv — artigos.

Antes destes, o tipo `artigo` só tinha o Archive.org. Ambos exigiram um caminho
de dois passos ou ajuste de rate-limit descoberto só com chamada real.
"""

from scrapers.base_scraper import ARTICLE_MEDIA
from scrapers.openalex_scraper import OpenAlexScraper
from scrapers.arxiv_scraper import ArxivScraper


class FakeResp:
    def __init__(self, payload=None, text=""):
        self._p = payload
        self.text = text

    def json(self):
        return self._p


# =========================== OpenAlex ===========================

def _work(titulo="Estudo", autores=("Ana Silva",), pdf="https://x/a.pdf"):
    return {
        "id": "https://openalex.org/W123",
        "title": titulo,
        "publication_year": 2021,
        "language": "pt",
        "authorships": [{"author": {"display_name": n}} for n in autores],
        "best_oa_location": {"pdf_url": pdf} if pdf else {},
    }


def test_openalex_only_serves_articles():
    assert OpenAlexScraper.capabilities.media_types == ARTICLE_MEDIA
    assert not OpenAlexScraper.capabilities.handles("livro")


def test_openalex_skips_works_without_pdf(monkeypatch):
    """'Acesso aberto' pode significar só página de destino, sem arquivo."""
    sc = OpenAlexScraper()
    monkeypatch.setattr(sc, "make_request", lambda *a, **k: FakeResp(
        {"results": [_work("Com PDF"), _work("Sem PDF", pdf=None)]}))
    assert [r.title for r in sc.search("x")] == ["Com PDF"]


def test_openalex_title_mode_filters_by_title(monkeypatch):
    sc = OpenAlexScraper()
    captured = {}
    monkeypatch.setattr(sc, "make_request",
                        lambda url, params=None, retries=0: captured.update(params or {}) or FakeResp({"results": []}))
    sc.search("literatura brasileira", search_by="titulo")
    assert "title.search:literatura brasileira" in captured["filter"]
    assert "open_access.is_oa:true" in captured["filter"]


def test_openalex_author_mode_resolves_ids_first(monkeypatch):
    """
    `raw_author_name.search` casava palavra a palavra e devolvia 1854 trabalhos
    de psiquiatria para "Machado de Assis". Resolver o autor antes corrige.
    """
    sc = OpenAlexScraper()
    chamadas = []

    def fake(url, params=None, retries=0):
        chamadas.append((url, params))
        if url.endswith('/authors'):
            return FakeResp({"results": [
                {"id": "https://openalex.org/A1", "display_name": "Yann LeCun"},
                {"id": "https://openalex.org/A2", "display_name": "Outra Pessoa"},
            ]})
        return FakeResp({"results": []})

    monkeypatch.setattr(sc, "make_request", fake)
    sc.search("Yann LeCun", search_by="autor")

    assert chamadas[0][0].endswith('/authors')
    # "Outra Pessoa" não bate com o nome buscado e é descartada.
    assert "author.id:A1" in chamadas[1][1]["filter"]
    assert "A2" not in chamadas[1][1]["filter"]


def test_openalex_author_matching_ignores_accents(monkeypatch):
    """'Antonio Candido' precisa casar com 'Antônio Cândido'."""
    sc = OpenAlexScraper()
    chamadas = []

    def fake(url, params=None, retries=0):
        chamadas.append((url, params))
        if url.endswith('/authors'):
            return FakeResp({"results": [
                {"id": "https://openalex.org/A9", "display_name": "Antônio Cândido"}]})
        return FakeResp({"results": []})

    monkeypatch.setattr(sc, "make_request", fake)
    sc.search("Antonio Candido", search_by="autor")
    assert "author.id:A9" in chamadas[1][1]["filter"]


def test_openalex_unknown_author_returns_empty(monkeypatch):
    sc = OpenAlexScraper()
    chamadas = []

    def fake(url, params=None, retries=0):
        chamadas.append(url)
        return FakeResp({"results": []})

    monkeypatch.setattr(sc, "make_request", fake)
    assert sc.search("Autor Inexistente", search_by="autor") == []
    assert len(chamadas) == 1, "sem autor resolvido, não busca trabalhos"


# =========================== arXiv ===========================

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1609.04846v1</id>
    <title>A Tutorial about
      Random Neural Networks</title>
    <published>2016-09-15T00:00:00Z</published>
    <author><name>Sebastian Basterrech</name></author>
    <author><name>Gerardo Rubino</name></author>
    <link title="pdf" href="https://arxiv.org/pdf/1609.04846v1"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/0000.0000v1</id>
    <title>Sem PDF</title>
    <author><name>Alguem</name></author>
    <link title="doi" href="https://doi.org/x"/>
  </entry>
</feed>"""


def test_arxiv_only_serves_articles():
    assert ArxivScraper.capabilities.media_types == ARTICLE_MEDIA


def test_arxiv_parses_atom_and_joins_wrapped_titles(monkeypatch):
    """O arXiv quebra o título em várias linhas no Atom."""
    sc = ArxivScraper()
    monkeypatch.setattr(sc, "make_request", lambda *a, **k: FakeResp(text=ATOM))
    res = sc.search("neural")
    assert [r.title for r in res] == ["A Tutorial about Random Neural Networks"]
    r = res[0]
    assert r.metadata["creator"] == "Sebastian Basterrech, Gerardo Rubino"
    assert r.metadata["year"] == "2016"
    assert r.download_url == "https://arxiv.org/pdf/1609.04846v1"


def test_arxiv_entries_without_pdf_are_skipped(monkeypatch):
    sc = ArxivScraper()
    monkeypatch.setattr(sc, "make_request", lambda *a, **k: FakeResp(text=ATOM))
    assert all(r.title != "Sem PDF" for r in sc.search("x"))


def test_arxiv_uses_its_own_query_language(monkeypatch):
    sc = ArxivScraper()
    captured = {}
    monkeypatch.setattr(sc, "make_request",
                        lambda url, params=None, retries=0: captured.update(params or {}) or FakeResp(text=ATOM))
    sc.search("Yann LeCun", search_by="autor")
    assert captured["search_query"] == 'au:"Yann LeCun"'
    sc.search("neural", search_by="titulo")
    assert captured["search_query"] == 'ti:"neural"'
    sc.search("neural", search_by="tudo")
    assert captured["search_query"] == 'all:"neural"'


def test_arxiv_malformed_xml_does_not_crash(monkeypatch):
    sc = ArxivScraper()
    monkeypatch.setattr(sc, "make_request", lambda *a, **k: FakeResp(text="<isso nao fecha"))
    assert sc.search("x") == []


def test_arxiv_respects_its_rate_limit_policy():
    """Com o padrão de 1 s o arXiv devolvia 429; a política dele pede ~3 s."""
    sc = ArxivScraper()
    assert sc.rate_limiter.delays.get('export.arxiv.org') >= 3.0
    assert sc.search_api.startswith("https://"), "em http o redirecionamento gerava 429"
