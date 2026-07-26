"""Fase 2: capacidades declaradas, busca concorrente e deduplicação.

Antes, decidir se uma fonte servia para um tipo de mídia era uma cadeia de `if`
comparando `scraper.name` com literais, e a busca percorria as fontes em série.
"""

import time

import pytest

from scrapers.base_scraper import SourceCapabilities, SERIAL_MEDIA, BOOK_MEDIA
from scrapers.mangadex_scraper import MangaDexScraper
from scrapers.archive_scraper import ArchiveOrgScraper
from scrapers.gutenberg_scraper import ProjectGutenbergScraper
from scrapers.openlibrary_scraper import OpenLibraryScraper
from media_bot import MediaBot


# --------------------------- capacidades ---------------------------

def test_capabilities_handles_is_case_insensitive():
    cap = SourceCapabilities(media_types=BOOK_MEDIA)
    assert cap.handles("livro") and cap.handles("  LIVRO ")
    assert not cap.handles("manga")


def test_each_source_declares_its_media_types():
    assert MangaDexScraper.capabilities.media_types == SERIAL_MEDIA
    assert ProjectGutenbergScraper.capabilities.media_types == BOOK_MEDIA
    assert OpenLibraryScraper.capabilities.media_types == BOOK_MEDIA
    # Archive.org é a única que atende os dois mundos.
    assert ArchiveOrgScraper.capabilities.handles("manga")
    assert ArchiveOrgScraper.capabilities.handles("livro")


@pytest.mark.parametrize("media_type,esperadas", [
    ("manga", {"MangaDex", "Archive.org"}),
    ("livro", {"Open Library", "Archive.org", "Project Gutenberg"}),
    ("artigo", {"Open Library", "Archive.org", "Project Gutenberg"}),
])
def test_routing_matches_the_previous_behaviour(media_type, esperadas):
    """A troca da cadeia de `if` por capacidades não pode mudar o roteamento."""
    bot = MediaBot.__new__(MediaBot)          # sem tocar disco nem rede
    bot.scrapers = [MangaDexScraper(), OpenLibraryScraper(),
                    ArchiveOrgScraper(), ProjectGutenbergScraper()]
    aplicaveis = {s.name for s in bot.scrapers
                  if bot._scraper_applicable(s, media_type)}
    assert aplicaveis == esperadas


def test_source_without_capabilities_is_allowed():
    """Fonte de terceiro que não declarou nada não pode sumir da busca."""
    class Solta:
        name = "Solta"
    bot = MediaBot.__new__(MediaBot)
    assert bot._scraper_applicable(Solta(), "livro")


# --------------------------- deduplicação ---------------------------

def test_dedupe_prefers_isbn_over_title():
    bot = MediaBot.__new__(MediaBot)
    a = {"title": "Dune", "metadata": {"isbn": "978", "creator": "Herbert"}}
    b = {"title": "DUNE (edição diferente)", "metadata": {"isbn": "978", "creator": "F. Herbert"}}
    assert bot._dedupe_key(a) == bot._dedupe_key(b)


def test_dedupe_falls_back_to_title_and_author_ignoring_accents():
    bot = MediaBot.__new__(MediaBot)
    a = {"title": "O Cortiço", "metadata": {"creator": "Aluísio Azevedo"}}
    b = {"title": "o cortico", "metadata": {"creator": "aluisio azevedo"}}
    assert bot._dedupe_key(a) == bot._dedupe_key(b)


def test_dedupe_keeps_different_books_apart():
    bot = MediaBot.__new__(MediaBot)
    a = {"title": "Dune", "metadata": {"creator": "Frank Herbert"}}
    b = {"title": "Dune Messiah", "metadata": {"creator": "Frank Herbert"}}
    assert bot._dedupe_key(a) != bot._dedupe_key(b)


def test_dedupe_keeps_the_first_occurrence():
    """As fontes precisas vêm primeiro — a versão delas é a que fica."""
    bot = MediaBot.__new__(MediaBot)
    entrada = [
        {"title": "Dune", "source": "Open Library", "metadata": {"isbn": "978"}},
        {"title": "Dune", "source": "Archive.org", "metadata": {"isbn": "978"}},
        {"title": "Outro", "source": "Archive.org", "metadata": {}},
    ]
    saida = bot._dedupe_results(entrada)
    assert [r["source"] for r in saida] == ["Open Library", "Archive.org"]
    assert saida[0]["title"] == "Dune"


def test_dedupe_handles_creator_as_list():
    bot = MediaBot.__new__(MediaBot)
    a = {"title": "Mindhunter", "metadata": {"creator": ["Douglas", "Olshaker"]}}
    assert "mindhunter" in bot._dedupe_key(a)


# --------------------------- busca concorrente ---------------------------

class FonteFake:
    def __init__(self, name, resultados, demora=0.0, explode=False):
        self.name = name
        self.capabilities = SourceCapabilities(media_types=BOOK_MEDIA)
        self._resultados = resultados
        self._demora = demora
        self._explode = explode

    def search(self, query, formats=None, language=None, search_by="titulo"):
        time.sleep(self._demora)
        if self._explode:
            raise RuntimeError("fonte caiu")
        return self._resultados


def _bot_com(fontes, timeout=5):
    bot = MediaBot.__new__(MediaBot)
    bot.scrapers = fontes
    bot.search_timeout = timeout
    bot.cache = type("C", (), {"get": lambda *a, **k: None,
                               "set": lambda *a, **k: None})()
    return bot


def _res(titulo, ident):
    return {"title": titulo, "source": "x", "metadata": {"identifier": ident}}


def test_search_runs_sources_concurrently():
    """Três fontes de 0,4 s em série levariam 1,2 s; juntas, bem menos."""
    fontes = [FonteFake(f"F{i}", [_res(f"L{i}", f"id{i}")], demora=0.4) for i in range(3)]
    bot = _bot_com(fontes)
    inicio = time.time()
    res = bot.search_series("x", media_type="livro")
    duracao = time.time() - inicio
    assert len(res) == 3
    assert duracao < 0.9, f"levou {duracao:.2f}s — parece estar rodando em série"


def test_search_preserves_source_order_not_completion_order():
    """A fonte mais precisa vem primeiro mesmo respondendo por último."""
    fontes = [
        FonteFake("Lenta mas precisa", [_res("primeiro", "a")], demora=0.3),
        FonteFake("Rápida", [_res("segundo", "b")], demora=0.0),
    ]
    res = _bot_com(fontes).search_series("x", media_type="livro")
    assert [r["title"] for r in res] == ["primeiro", "segundo"]


def test_one_broken_source_does_not_sink_the_search():
    fontes = [
        FonteFake("Quebrada", [], explode=True),
        FonteFake("Boa", [_res("achou", "a")]),
    ]
    res = _bot_com(fontes).search_series("x", media_type="livro")
    assert [r["title"] for r in res] == ["achou"]


def test_slow_source_is_dropped_without_blocking(capsys):
    fontes = [
        FonteFake("Travada", [_res("nunca", "z")], demora=2.0),
        FonteFake("Boa", [_res("achou", "a")]),
    ]
    res = _bot_com(fontes, timeout=0.3).search_series("x", media_type="livro")
    assert [r["title"] for r in res] == ["achou"]
    assert "demorou demais" in capsys.readouterr().out


def test_search_deduplicates_across_sources():
    fontes = [
        FonteFake("A", [_res("Dune", "mesmo")]),
        FonteFake("B", [_res("Dune", "mesmo")]),
    ]
    assert len(_bot_com(fontes).search_series("x", media_type="livro")) == 1
