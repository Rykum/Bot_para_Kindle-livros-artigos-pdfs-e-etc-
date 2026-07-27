# -*- coding: utf-8 -*-
from scrapers.base_scraper import SourceCapabilities, BOOK_MEDIA
from media_bot import MediaBot
from scrapers.generos import genero_por_nome


class FonteExplora:
    name = "Explora"
    capabilities = SourceCapabilities(media_types=BOOK_MEDIA, explora_genero=True)
    def explorar(self, genero, subgenero=None, ordenacao="relevancia"):
        return [{"title": f"{genero.nome} 1", "source": self.name,
                 "metadata": {"identifier": "a"}}]


class FonteNaoExplora:
    name = "NaoExplora"
    capabilities = SourceCapabilities(media_types=BOOK_MEDIA)
    def explorar(self, *a, **k):
        raise AssertionError("não deveria ser chamada")


def _bot(fontes):
    bot = MediaBot.__new__(MediaBot)
    bot.scrapers = fontes
    bot.search_timeout = 5
    bot.cache = type("C", (), {"get": lambda *a, **k: None, "set": lambda *a, **k: None})()
    return bot


def test_only_sources_that_declare_it_are_asked():
    """OAPEN, Zenodo, OpenAlex e arXiv não exploram por gênero."""
    bot = _bot([FonteExplora(), FonteNaoExplora()])
    r = bot.explorar_genero("livro", "Terror")
    assert [x["source"] for x in r] == ["Explora"]


def test_unknown_genre_yields_nothing():
    bot = _bot([FonteExplora()])
    assert bot.explorar_genero("livro", "GêneroInexistente") == []


def test_results_are_deduplicated_across_sources():
    bot = _bot([FonteExplora(), FonteExplora()])
    assert len(bot.explorar_genero("livro", "Terror")) == 1
