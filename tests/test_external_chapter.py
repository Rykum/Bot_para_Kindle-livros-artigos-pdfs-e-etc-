import tempfile
from pathlib import Path

from media_bot import MediaBot


def make_bot():
    return MediaBot(base_download_dir=str(Path(tempfile.mkdtemp()) / "dl"))


def _stub(bot, monkeypatch, chapters):
    monkeypatch.setattr(bot, "_resolve_series_reference", lambda *a, **k: "ref")
    monkeypatch.setattr(bot, "_build_series_meta", lambda *a, **k: {"series": "S"})
    monkeypatch.setattr(bot, "get_complete_series_chapters", lambda *a, **k: list(chapters))


def test_external_chapter_uses_language_fallback(monkeypatch):
    bot = make_bot()
    try:
        _stub(bot, monkeypatch, [1.0])
        scraper = bot._resolve_scraper("mangadex")
        langs = []

        def fake_get_chapter_url(ref, num, language="pt-br"):
            langs.append(language)
            if language == "pt-br":
                return {"download_type": "external_only", "external_url": "http://x/1"}
            return {"download_url": "http://x/f.cbz", "format": "cbz"}

        monkeypatch.setattr(scraper, "get_chapter_url", fake_get_chapter_url)
        monkeypatch.setattr(bot.downloader, "download",
                            lambda **kw: {"success": True, "file_path": "f",
                                          "metadata": {"format": "cbz", "size": 1, "sha256": "h"}})
        summary = bot.download_complete_series("S", source_name="mangadex",
                                               language="pt-br", fallback_language="en")
        assert langs.count("pt-br") == 1      # externo NÃO é re-tentado 3x
        assert "en" in langs                  # foi pro fallback
        assert summary["downloaded"] == 1


    finally:
        bot.cleanup()


def test_external_only_without_fallback_is_failed_not_retried(monkeypatch):
    bot = make_bot()
    try:
        _stub(bot, monkeypatch, [1.0])
        scraper = bot._resolve_scraper("mangadex")
        calls = {"n": 0}

        def fake(ref, num, language="pt-br"):
            calls["n"] += 1
            return {"download_type": "external_only", "external_url": "http://x/1"}

        monkeypatch.setattr(scraper, "get_chapter_url", fake)
        summary = bot.download_complete_series("S", source_name="mangadex", language="pt-br")
        assert summary["failed_chapters"] == [1.0]
        assert calls["n"] == 1                # externo não é martelado 3x
    finally:
        bot.cleanup()
