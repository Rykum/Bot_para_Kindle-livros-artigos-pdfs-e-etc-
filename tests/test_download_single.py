import tempfile
from pathlib import Path

from media_bot import MediaBot


def make_bot():
    return MediaBot(base_download_dir=str(Path(tempfile.mkdtemp()) / "dl"))


def test_download_single_chapter_success(monkeypatch):
    bot = make_bot()
    try:
        monkeypatch.setattr(bot, "_resolve_series_reference", lambda *a, **k: "ref")
        monkeypatch.setattr(bot, "_build_series_meta", lambda *a, **k: {"series": "S"})
        scraper = bot._resolve_scraper("mangadex")
        monkeypatch.setattr(scraper, "get_chapter_url",
                            lambda ref, num, language="pt-br": {"download_url": "http://x/f.cbz", "format": "cbz"})
        monkeypatch.setattr(bot.downloader, "download",
                            lambda **kw: {"success": True, "file_path": "f", "metadata": {"format": "cbz", "size": 1, "sha256": "h"}})
        ok = bot.download_single_chapter("S", 5.0, source_name="mangadex")
        assert ok is True
    finally:
        bot.cleanup()


def test_download_single_chapter_fails_after_retries(monkeypatch):
    bot = make_bot()
    try:
        monkeypatch.setattr(bot, "_resolve_series_reference", lambda *a, **k: "ref")
        monkeypatch.setattr(bot, "_build_series_meta", lambda *a, **k: {"series": "S"})
        scraper = bot._resolve_scraper("mangadex")
        monkeypatch.setattr(scraper, "get_chapter_url", lambda ref, num, language="pt-br": None)
        ok = bot.download_single_chapter("S", 5.0, source_name="mangadex")
        assert ok is False
    finally:
        bot.cleanup()
