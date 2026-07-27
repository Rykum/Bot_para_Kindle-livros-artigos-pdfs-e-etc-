from scrapers.mangadex_scraper import MangaDexScraper


class FakeResp:
    def __init__(self, payload): self._p = payload
    def json(self): return self._p


def _tags():
    return {"data": [
        {"id": "uuid-horror", "attributes": {"name": {"en": "Horror"}, "group": "genre"}},
        {"id": "uuid-ghosts", "attributes": {"name": {"en": "Ghosts"}, "group": "theme"}},
    ]}


def test_resolves_names_to_uuids(monkeypatch):
    """A API só aceita UUID; gravar UUID no código quebra quando ele muda."""
    sc = MangaDexScraper()
    monkeypatch.setattr(sc, "make_request", lambda *a, **k: FakeResp(_tags()))
    assert sc._tag_ids(["Horror"]) == {"Horror": "uuid-horror"}


def test_unknown_tag_is_omitted_not_invented(monkeypatch):
    sc = MangaDexScraper()
    monkeypatch.setattr(sc, "make_request", lambda *a, **k: FakeResp(_tags()))
    assert sc._tag_ids(["Horror", "NaoExiste"]) == {"Horror": "uuid-horror"}


def test_tag_table_is_fetched_once(monkeypatch):
    """São 77 tags fixas; buscar a cada exploração é desperdício."""
    sc = MangaDexScraper()
    chamadas = []
    monkeypatch.setattr(sc, "make_request",
                        lambda *a, **k: chamadas.append(1) or FakeResp(_tags()))
    sc._tag_ids(["Horror"])
    sc._tag_ids(["Ghosts"])
    assert len(chamadas) == 1


def test_failure_to_fetch_yields_empty_not_crash(monkeypatch):
    sc = MangaDexScraper()
    monkeypatch.setattr(sc, "make_request", lambda *a, **k: None)
    assert sc._tag_ids(["Horror"]) == {}


def test_failure_does_not_poison_the_cache(monkeypatch):
    """Uma queda de rede momentânea não pode deixar o app sem tags até reiniciar."""
    sc = MangaDexScraper()
    respostas = [None, FakeResp(_tags())]   # 1ª falha, 2ª funciona
    chamadas = []

    def fake(url, params=None, retries=0):
        chamadas.append(url)
        return respostas.pop(0)

    monkeypatch.setattr(sc, "make_request", fake)

    assert sc._tag_ids(["Horror"]) == {}          # falhou
    assert sc._tag_ids(["Horror"]) == {"Horror": "uuid-horror"}   # tentou de novo
    assert len(chamadas) == 2, "a falha não pode ter ficado guardada no cache"
