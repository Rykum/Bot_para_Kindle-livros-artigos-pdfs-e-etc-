from scrapers.generos import generos_de, genero_por_nome
from scrapers.archive_scraper import ArchiveOrgScraper


class FakeResp:
    def __init__(self, payload): self._p = payload
    def json(self): return self._p


DOCS = {"response": {"docs": [
    {"identifier": "xmen01", "title": "X-Men v1", "mediatype": "texts",
     "creator": "Marvel", "downloads": 900},
]}}


def test_hq_query_is_scoped_to_the_comics_collection(monkeypatch):
    """Sem collection:comics, `superhero` pega qualquer texto do acervo."""
    sc = ArchiveOrgScraper()
    cap = {}
    monkeypatch.setattr(sc, "make_request",
                        lambda url, params=None, retries=0:
                        cap.update(params or {}) or FakeResp(DOCS))
    sc.explorar(genero_por_nome("hq", "Super-heróis"))
    assert "collection:comics" in cap["q"]
    assert 'subject:("superhero")' in cap["q"]


def test_hq_browse_sorts_by_downloads(monkeypatch):
    """Sem termo de busca não há relevância; downloads é o único sinal."""
    sc = ArchiveOrgScraper()
    cap = {}
    monkeypatch.setattr(sc, "make_request",
                        lambda url, params=None, retries=0:
                        cap.update(params or {}) or FakeResp(DOCS))
    sc.explorar(genero_por_nome("hq", "Super-heróis"))
    assert cap["sort[]"] == ["downloads desc"]


def test_hq_cover_is_derived_from_the_identifier(monkeypatch):
    """O Archive.org serve capa por identificador, sem chamada extra."""
    sc = ArchiveOrgScraper()
    monkeypatch.setattr(sc, "make_request", lambda *a, **k: FakeResp(DOCS))
    r = sc.explorar(genero_por_nome("hq", "Super-heróis"))[0]
    assert r.metadata["cover_url"] == "https://archive.org/services/img/xmen01"


def test_every_hq_genre_was_validated():
    """Cada gênero de HQ precisa ter passado pela medição do Step 1."""
    for g in generos_de("hq"):
        assert g.archive, f"{g.nome} sem termo do Archive.org"
