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


def test_gutendex_warns_when_subgenre_is_discarded(monkeypatch, caplog):
    """Gutendex não tem vocabulário para subgênero: silêncio faria o usuário
    pensar que 'Distopia' filtrou quando na verdade veio ficção científica
    inteira (mesmo bug que motivou o aviso da Open Library e do MangaDex)."""
    import logging
    sc = ProjectGutenbergScraper()
    monkeypatch.setattr(sc, "make_request",
                        lambda url, params=None, retries=0: FakeResp({"results": []}))
    with caplog.at_level(logging.WARNING):
        sc.explorar(genero_por_nome("livro", "Ficção científica"), subgenero="Distopia")
    assert any("Distopia" in r.message for r in caplog.records), \
        "subgênero descartado pela Gutendex precisa avisar"


# ============ idioma real do exemplar ============

def _ol_com_idiomas(monkeypatch, docs, idiomas):
    """Open Library devolvendo `docs`; Archive.org devolvendo `idiomas`."""
    sc = OpenLibraryScraper()

    def fake_ol(url, params=None, retries=0):
        return FakeResp({"docs": docs})

    def fake_archive(url, params=None, retries=0):
        return FakeResp({"response": {"docs": [
            {"identifier": i, "language": lg} for i, lg in idiomas.items()]}})

    monkeypatch.setattr(sc, "make_request", fake_ol)
    monkeypatch.setattr(sc._archive, "make_request", fake_archive)
    return sc


def _doc(titulo, copias):
    return {"key": f"/works/{titulo}", "title": titulo, "author_name": ["X"],
            "ia": copias, "isbn": ["978"], "language": ["eng"], "cover_i": 1}


def test_language_shown_is_the_file_not_the_work(monkeypatch):
    """O campo `language` do Open Library lista TODOS os idiomas em que a obra
    existe — Misery traz 15. O que importa é o idioma do exemplar que será
    baixado: medido, o de Misery estava em chinês."""
    sc = _ol_com_idiomas(monkeypatch,
                         [_doc("Misery", ["misery_chines"])],
                         {"misery_chines": "chi"})
    r = sc.explorar(genero_por_nome("livro", "Terror"))[0]
    assert r.language == "chi", "mostrou o idioma da obra, não o do arquivo"


def test_portuguese_copy_is_chosen_when_it_exists(monkeypatch):
    """Entre os exemplares da mesma obra, o em português ganha."""
    sc = _ol_com_idiomas(monkeypatch,
                         [_doc("Thinner", ["thinner_eng", "maldicao_pt"])],
                         {"thinner_eng": "eng", "maldicao_pt": "por"})
    r = sc.explorar(genero_por_nome("livro", "Terror"))[0]
    assert r.metadata["identifier"] == "maldicao_pt"
    assert r.language == "por"


def test_portuguese_results_come_first(monkeypatch):
    """Priorizar em vez de filtrar: filtrar deixaria 0,3% a 2,7% do acervo."""
    sc = _ol_com_idiomas(
        monkeypatch,
        [_doc("Em ingles", ["a_eng"]), _doc("Em portugues", ["b_pt"]),
         _doc("Em alemao", ["c_ger"])],
        {"a_eng": "eng", "b_pt": "por", "c_ger": "ger"})
    titulos = [r.title for r in sc.explorar(genero_por_nome("livro", "Terror"))]
    assert titulos[0] == "Em portugues"


def test_language_resolution_is_batched(monkeypatch):
    """Uma chamada resolve a página inteira; uma por exemplar seria inviável
    com o rate-limit de 1,5s por domínio do Archive.org."""
    sc = OpenLibraryScraper()
    chamadas = []
    monkeypatch.setattr(sc, "make_request", lambda *a, **k: FakeResp(
        {"docs": [_doc(f"L{n}", [f"id{n}"]) for n in range(10)]}))

    def conta(url, params=None, retries=0):
        chamadas.append(params.get("q"))
        return FakeResp({"response": {"docs": []}})

    monkeypatch.setattr(sc._archive, "make_request", conta)
    sc.explorar(genero_por_nome("livro", "Terror"))
    assert len(chamadas) == 1, f"esperava 1 chamada em lote, houve {len(chamadas)}"
    assert chamadas[0].count("identifier:") == 10


def test_unknown_language_keeps_the_first_copy(monkeypatch):
    """Sem informação, mantém o comportamento anterior e não inventa idioma."""
    sc = _ol_com_idiomas(monkeypatch, [_doc("Sem dados", ["x", "y"])], {})
    r = sc.explorar(genero_por_nome("livro", "Terror"))[0]
    assert r.metadata["identifier"] == "x"
    assert r.language == "desconhecido"
