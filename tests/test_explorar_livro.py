from scrapers.generos import genero_por_nome
from scrapers.openlibrary_scraper import OpenLibraryScraper
from scrapers.gutenberg_scraper import ProjectGutenbergScraper


class FakeResp:
    def __init__(self, payload): self._p = payload
    def json(self): return self._p


OL = {"docs": [{
    "key": "/works/W1", "title": "Misery", "author_name": ["Stephen King"],
    "first_publish_year": 1987, "ia": ["misery0000king"], "isbn": ["978"],
    "language": ["eng"], "cover_i": 8259296,
}]}


def _ol(monkeypatch):
    sc = OpenLibraryScraper()
    cap = {}
    def fake(url, params=None, retries=0):
        cap.update(params or {})
        return FakeResp(OL)
    monkeypatch.setattr(sc, "make_request", fake)
    return sc, cap


def test_default_ordering_is_relevance_not_popularity(monkeypatch):
    """Medido: por popularidade, Alice no País das Maravilhas aparecia em
    ficção científica E em filosofia. Relevância acerta o gênero."""
    sc, cap = _ol(monkeypatch)
    sc.explorar(genero_por_nome("livro", "Terror"))
    assert cap["subject"] == "horror"
    assert "sort" not in cap, "relevância é a ausência de sort"


def test_most_read_ordering_uses_readinglog(monkeypatch):
    sc, cap = _ol(monkeypatch)
    sc.explorar(genero_por_nome("livro", "Terror"), ordenacao="mais_lidos")
    assert cap["sort"] == "readinglog"


def test_only_downloadable_results(monkeypatch):
    """has_fulltext corta ficção científica de 90.804 para 18.864."""
    sc, cap = _ol(monkeypatch)
    sc.explorar(genero_por_nome("livro", "Terror"))
    assert cap["has_fulltext"] == "true"


def test_subgenre_narrows_the_subject(monkeypatch):
    sc, cap = _ol(monkeypatch)
    sc.explorar(genero_por_nome("livro", "Ficção científica"), subgenero="Distopia")
    assert "science fiction" in cap["subject"].lower()
    assert "distopia" not in cap["subject"].lower(), "subgênero precisa ir em inglês"


def test_cover_url_comes_from_cover_i(monkeypatch):
    sc, _ = _ol(monkeypatch)
    r = sc.explorar(genero_por_nome("livro", "Terror"))[0]
    assert r.metadata["cover_url"] == "https://covers.openlibrary.org/b/id/8259296-M.jpg"


def test_every_book_subgenre_resolves():
    """Subgênero que não resolve é ignorado em silêncio, e o usuário vê o
    gênero inteiro sem nada avisar."""
    from scrapers.generos import generos_de
    sc = OpenLibraryScraper()
    nao_resolvem = []
    for g in generos_de("livro"):
        for s in g.subgeneros:
            if sc.SUBGENEROS.get(sc._fold(s)) is None:
                nao_resolvem.append((g.nome, s))
    assert not nao_resolvem, f"subgêneros de livro sem tradução: {nao_resolvem}"


def test_unresolved_subgenre_warns(monkeypatch, caplog):
    """Sem aviso, o filtro cai em silêncio para o gênero inteiro."""
    import logging
    sc, _ = _ol(monkeypatch)
    with caplog.at_level(logging.WARNING):
        sc.explorar(genero_por_nome("livro", "Terror"), subgenero="NaoExiste")
    assert any("NaoExiste" in r.message for r in caplog.records), \
        "subgênero não resolvido precisa avisar"


def test_gutendex_uses_topic_and_popular(monkeypatch):
    sc = ProjectGutenbergScraper()
    cap = {}
    monkeypatch.setattr(sc, "make_request",
                        lambda url, params=None, retries=0:
                        cap.update(params or {}) or FakeResp({"results": []}))
    sc.explorar(genero_por_nome("livro", "Terror"))
    assert cap["topic"] == "horror"
    assert cap["sort"] == "popular"
