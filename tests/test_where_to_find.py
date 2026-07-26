"""'Onde encontrar': quando nenhuma fonte tem o arquivo, apontar onde a obra está.

Conclusão da auditoria: o gargalo da biblioteca é direito autoral, não falta de
fonte. Devolver lista vazia esconde essa informação do usuário.
"""

from app.api import Api
from app.bot_service import BotService
from app.where_to_find import onde_encontrar


def test_suggestions_include_the_search_term_encoded():
    destinos = onde_encontrar("Dom Casmurro")
    assert destinos
    for d in destinos:
        assert "Dom+Casmurro" in d["url"], d["nome"]
        assert d["url"].startswith("https://")
        assert d["nome"] and d["descricao"] and d["tipo"]


def test_author_is_added_to_disambiguate():
    d = onde_encontrar("Dune", autor="Frank Herbert")[0]
    assert "Dune+Frank+Herbert" in d["url"]


def test_accents_and_symbols_are_escaped():
    d = onde_encontrar("O Cortiço & cia")[0]
    assert " " not in d["url"] and "&+" not in d["url"]
    assert "Corti%C3%A7o" in d["url"]


def test_empty_search_yields_nothing():
    assert onde_encontrar("") == []
    assert onde_encontrar("   ") == []
    assert onde_encontrar(None) == []


def test_brazilian_destination_only_for_portuguese():
    nomes = lambda idioma: {d["nome"] for d in onde_encontrar("Dom Casmurro", idioma=idioma)}
    assert "Estante Virtual" in nomes(None)
    assert "Estante Virtual" in nomes("pt")
    assert "Estante Virtual" in nomes("pt-br")
    assert "Estante Virtual" not in nomes("en")


def test_covers_borrowing_reading_library_and_buying():
    tipos = {d["tipo"] for d in onde_encontrar("Dune")}
    assert {"emprestimo", "leitura", "catalogo", "compra"} <= tipos


# --------------------------- integração com a busca ---------------------------

class BotSemResultado:
    def search_series(self, query, media_type="manga", language=None, search_by="titulo"):
        return []

    def cleanup(self):
        pass


class BotComResultado(BotSemResultado):
    def search_series(self, query, media_type="manga", language=None, search_by="titulo"):
        return [{"title": query, "source": "Archive.org"}]


def _busca(bot_factory, **kwargs):
    import time
    eventos = []
    service = BotService(bot_factory=bot_factory,
                         event_sink=lambda n, p: eventos.append((n, p)))
    api = Api(service)
    service.start()
    try:
        api.search("Torto Arado", "livro", **kwargs)
        limite = time.time() + 5
        while time.time() < limite:
            if any(n == "search_results" for n, _ in eventos):
                break
            time.sleep(0.01)
        return [p for n, p in eventos if n == "search_results"][0]
    finally:
        service.stop()


def test_empty_search_emits_where_to_find():
    payload = _busca(BotSemResultado)
    assert payload["results"] == []
    assert payload["onde_encontrar"], "busca vazia deveria sugerir onde procurar"
    assert "Torto+Arado" in payload["onde_encontrar"][0]["url"]


def test_successful_search_does_not_suggest_anything():
    payload = _busca(BotComResultado)
    assert payload["results"]
    assert payload["onde_encontrar"] == []


# --------------------------- abrir no navegador ---------------------------

def test_open_external_rejects_non_http_urls():
    """A URL vem do JS; `webbrowser` abriria file:// alegremente."""
    api = Api(BotService(bot_factory=BotSemResultado, event_sink=lambda *a: None))
    for ruim in ["file:///C:/Windows/System32", "javascript:alert(1)", "", None, 123]:
        assert api.open_external(ruim) == {"ok": False}


def test_open_external_accepts_https(monkeypatch):
    api = Api(BotService(bot_factory=BotSemResultado, event_sink=lambda *a: None))
    import webbrowser
    abertos = []
    monkeypatch.setattr(webbrowser, "open", lambda u: abertos.append(u) or True)
    assert api.open_external("https://openlibrary.org/search?q=x") == {"ok": True}
    assert abertos == ["https://openlibrary.org/search?q=x"]
