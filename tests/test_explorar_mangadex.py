# tests/test_explorar_mangadex.py
from scrapers.generos import genero_por_nome
from scrapers.mangadex_scraper import MangaDexScraper


class FakeResp:
    def __init__(self, payload): self._p = payload
    def json(self): return self._p


TAGS = {"data": [
    {"id": "uuid-horror", "attributes": {"name": {"en": "Horror"}, "group": "genre"}},
    {"id": "uuid-ghosts", "attributes": {"name": {"en": "Ghosts"}, "group": "theme"}},
]}

MANGAS = {"data": [{
    "id": "m-1",
    "attributes": {"title": {"en": "Berserk"}, "status": "ongoing", "year": 1989,
                   "description": {}},
    "relationships": [{"type": "cover_art", "attributes": {"fileName": "capa.jpg"}}],
}]}


def _scraper(monkeypatch):
    sc = MangaDexScraper()
    capturado = {}

    def fake(url, params=None, retries=0):
        if url.endswith("/manga/tag"):
            return FakeResp(TAGS)
        capturado.update(params or {})
        capturado["url"] = url
        return FakeResp(MANGAS)

    monkeypatch.setattr(sc, "make_request", fake)
    return sc, capturado


def test_filters_by_tag_uuid_and_orders_by_followers(monkeypatch):
    sc, cap = _scraper(monkeypatch)
    sc.explorar(genero_por_nome("manga", "Terror"))
    assert cap["includedTags[]"] == ["uuid-horror"]
    assert cap["order[followedCount]"] == "desc"


def test_subgenre_adds_a_second_tag(monkeypatch):
    sc, cap = _scraper(monkeypatch)
    sc.explorar(genero_por_nome("manga", "Terror"), subgenero="Fantasmas")
    assert set(cap["includedTags[]"]) == {"uuid-horror", "uuid-ghosts"}


def test_manhwa_filters_by_original_language(monkeypatch):
    """Manhwa é mangá coreano: 8.717 obras com originalLanguage=ko."""
    sc, cap = _scraper(monkeypatch)
    sc.explorar(genero_por_nome("manhwa", "Terror"), idioma_origem="ko")
    assert cap["originalLanguage[]"] == ["ko"]


def test_cover_url_is_built_from_the_relationship(monkeypatch):
    """O scraper já pedia cover_art e jogava fora."""
    sc, _ = _scraper(monkeypatch)
    r = sc.explorar(genero_por_nome("manga", "Terror"))[0]
    assert r.metadata["cover_url"] == \
        "https://uploads.mangadex.org/covers/m-1/capa.jpg.256.jpg"


def test_unknown_subgenre_is_ignored_not_fatal(monkeypatch):
    sc, cap = _scraper(monkeypatch)
    sc.explorar(genero_por_nome("manga", "Terror"), subgenero="NaoExiste")
    assert cap["includedTags[]"] == ["uuid-horror"]


def test_unresolvable_genre_returns_empty(monkeypatch):
    """Melhor lista vazia com log que busca sem filtro devolvendo qualquer coisa."""
    sc = MangaDexScraper()
    monkeypatch.setattr(sc, "make_request",
                        lambda url, params=None, retries=0:
                        FakeResp({"data": []}) if url.endswith("/manga/tag") else FakeResp(MANGAS))
    assert sc.explorar(genero_por_nome("manga", "Terror")) == []


def test_unresolved_subgenre_warns(monkeypatch, caplog):
    """Sem aviso, o filtro cai em silêncio para o gênero inteiro."""
    import logging
    sc, _ = _scraper(monkeypatch)
    with caplog.at_level(logging.WARNING):
        sc.explorar(genero_por_nome("manga", "Terror"), subgenero="NaoExiste")
    assert any("NaoExiste" in r.message for r in caplog.records), \
        "subgênero não resolvido precisa avisar"


def test_exploring_hq_makes_no_network_call(monkeypatch):
    """HQ está em SERIAL_MEDIA (capabilities do MangaDex inclui 'hq'), mas o
    MangaDex não é fonte de HQ: Genero('Super-heróis', archive='superhero')
    não tem mangadex_tag. Sem a guarda `not genero.mangadex_tag`, isso gastava
    uma chamada de rede e logava 'gênero indisponível' — mensagem errada,
    já que o problema não é disponibilidade, é a fonte não cobrir o tipo."""
    sc = MangaDexScraper()

    def fail(*a, **k):
        raise AssertionError("MangaDex não deveria ser chamado para HQ")

    monkeypatch.setattr(sc, "make_request", fail)
    assert sc.explorar(genero_por_nome("hq", "Super-heróis")) == []
