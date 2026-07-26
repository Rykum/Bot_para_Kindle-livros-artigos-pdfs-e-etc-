"""Fase 7 (destravamento): chaves de API e fontes que dependem de cadastro.

As fontes da Fase 7 (Google Books, CORE, Europeana, DPLA, BHL) exigem chave.
Enquanto o usuário não configura, elas precisam ficar **fora** da busca — não
entrar para falhar com 401 e consumir o orçamento de tempo das outras.
"""

import json

import pytest

from scrapers.base_scraper import SourceCapabilities, BOOK_MEDIA
from media_bot import MediaBot
from app import settings_store


@pytest.fixture
def settings_isolado(tmp_path, monkeypatch):
    """O settings_store escreve num JSON fixo; isola para não sujar o do usuário."""
    monkeypatch.setattr(settings_store, "_PATH", tmp_path / "settings.json")
    return tmp_path / "settings.json"


# --------------------------- armazenamento ---------------------------

def test_key_roundtrip(settings_isolado):
    assert settings_store.get_api_key("Google Books") is None
    settings_store.set_api_key("Google Books", "abc123")
    assert settings_store.get_api_key("Google Books") == "abc123"


def test_key_lookup_is_case_insensitive(settings_isolado):
    settings_store.set_api_key("Google Books", "k")
    assert settings_store.get_api_key("google books") == "k"
    assert settings_store.get_api_key("  GOOGLE BOOKS  ") == "k"


def test_blank_key_is_treated_as_absent(settings_isolado):
    settings_store.set_api_key("CORE", "   ")
    assert settings_store.get_api_key("CORE") is None


def test_key_can_be_removed(settings_isolado):
    settings_store.set_api_key("DPLA", "k")
    settings_store.set_api_key("DPLA", "")
    assert settings_store.get_api_key("DPLA") is None
    assert "dpla" not in settings_store.configured_api_keys()


def test_keys_do_not_clobber_other_settings(settings_isolado):
    settings_store.set_setting("download_dir", "D:/livros")
    settings_store.set_api_key("Europeana", "k")
    assert settings_store.get_setting("download_dir") == "D:/livros"
    assert settings_store.get_api_key("Europeana") == "k"


def test_configured_list_reports_what_is_set(settings_isolado):
    settings_store.set_api_key("Google Books", "a")
    settings_store.set_api_key("CORE", "b")
    assert settings_store.configured_api_keys() == ["core", "google books"]


# --------------------------- roteamento ---------------------------

class FonteComChave:
    name = "Google Books"
    capabilities = SourceCapabilities(media_types=BOOK_MEDIA, needs_api_key=True)


class FonteSemChave:
    name = "Wikisource"
    capabilities = SourceCapabilities(media_types=BOOK_MEDIA)


def test_keyed_source_is_off_until_configured(settings_isolado):
    bot = MediaBot.__new__(MediaBot)
    assert not bot._scraper_applicable(FonteComChave(), "livro")


def test_keyed_source_turns_on_once_configured(settings_isolado):
    settings_store.set_api_key("Google Books", "abc123")
    bot = MediaBot.__new__(MediaBot)
    assert bot._scraper_applicable(FonteComChave(), "livro")


def test_keyless_source_is_unaffected(settings_isolado):
    bot = MediaBot.__new__(MediaBot)
    assert bot._scraper_applicable(FonteSemChave(), "livro")


def test_key_does_not_override_media_type(settings_isolado):
    """Ter chave não faz uma fonte de livro aparecer em busca de mangá."""
    settings_store.set_api_key("Google Books", "abc123")
    bot = MediaBot.__new__(MediaBot)
    assert not bot._scraper_applicable(FonteComChave(), "manga")


def test_keys_are_not_stored_in_source_code():
    """As chaves vivem no settings JSON, que está no .gitignore."""
    from pathlib import Path
    gitignore = Path(__file__).resolve().parent.parent / ".gitignore"
    assert "media_bot_settings.json" in gitignore.read_text(encoding="utf-8")
