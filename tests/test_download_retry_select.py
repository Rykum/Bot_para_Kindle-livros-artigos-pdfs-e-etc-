import tempfile
from pathlib import Path

from media_bot import MediaBot


def make_bot():
    return MediaBot(base_download_dir=str(Path(tempfile.mkdtemp()) / "dl"))


def _stub_common(bot, monkeypatch, available):
    monkeypatch.setattr(bot, "_resolve_series_reference", lambda *a, **k: "ref")
    monkeypatch.setattr(bot, "get_complete_series_chapters", lambda *a, **k: list(available))


def test_only_selected_chapters_are_downloaded(monkeypatch):
    bot = make_bot()
    try:
        _stub_common(bot, monkeypatch, [1.0, 2.0, 3.0])
        requested = []
        scraper = bot._resolve_scraper("mangadex")

        def fake_get_chapter_url(ref, num, language="pt-br"):
            requested.append(num)
            return {"download_url": "http://x/f.cbz", "format": "cbz"}

        monkeypatch.setattr(scraper, "get_chapter_url", fake_get_chapter_url)
        monkeypatch.setattr(bot.downloader, "download",
                            lambda **kw: {"success": True, "file_path": "f", "metadata": {"format": "cbz", "size": 1, "sha256": "h"}})
        bot.download_complete_series("Serie", source_name="mangadex", chapters=[1.0, 3.0])
        assert sorted(requested) == [1.0, 3.0]
    finally:
        bot.cleanup()


def test_failed_chapter_is_retried_and_succeeds(monkeypatch):
    bot = make_bot()
    try:
        _stub_common(bot, monkeypatch, [1.0])
        scraper = bot._resolve_scraper("mangadex")
        monkeypatch.setattr(scraper, "get_chapter_url",
                            lambda ref, num, language="pt-br": {"download_url": "http://x/f.cbz", "format": "cbz"})
        attempts = {"n": 0}

        def flaky_download(**kw):
            attempts["n"] += 1
            if attempts["n"] < 2:
                return {"success": False, "error": "boom"}
            return {"success": True, "file_path": "f", "metadata": {"format": "cbz", "size": 1, "sha256": "h"}}

        monkeypatch.setattr(bot.downloader, "download", flaky_download)
        summary = bot.download_complete_series("Serie", source_name="mangadex")
        assert summary["downloaded"] == 1
        assert summary["failed_chapters"] == []
        assert attempts["n"] >= 2  # re-tentou
    finally:
        bot.cleanup()


def test_fallback_language_used_after_primary_exhausted(monkeypatch):
    bot = make_bot()
    try:
        _stub_common(bot, monkeypatch, [1.0])
        scraper = bot._resolve_scraper("mangadex")
        langs = []

        def fake_get_chapter_url(ref, num, language="pt-br"):
            langs.append(language)
            if language == "pt-br":
                return None  # indisponível no primário
            return {"download_url": "http://x/f.cbz", "format": "cbz"}

        monkeypatch.setattr(scraper, "get_chapter_url", fake_get_chapter_url)
        monkeypatch.setattr(bot.downloader, "download",
                            lambda **kw: {"success": True, "file_path": "f", "metadata": {"format": "cbz", "size": 1, "sha256": "h"}})
        summary = bot.download_complete_series("Serie", source_name="mangadex",
                                               language="pt-br", fallback_language="en")
        assert "en" in langs                # fallback foi acionado
        assert langs.index("en") > 0        # só depois de tentar o primário
        assert summary["downloaded"] == 1
    finally:
        bot.cleanup()


def test_list_series_chapters_shape(monkeypatch):
    bot = make_bot()
    try:
        monkeypatch.setattr(bot, "_resolve_series_reference", lambda *a, **k: "ref")
        monkeypatch.setattr(bot, "get_complete_series_chapters", lambda *a, **k: [1.0, 2.0])
        data = bot.list_series_chapters("Serie", "manga", "mangadex")
        for key in ["title", "available", "downloaded", "missing", "by_language"]:
            assert key in data
        assert data["available"] == [1.0, 2.0]
    finally:
        bot.cleanup()


def test_cancelled_chapter_not_in_failed_chapters(monkeypatch):
    bot = make_bot()
    try:
        _stub_common(bot, monkeypatch, [1.0, 2.0])
        scraper = bot._resolve_scraper("mangadex")
        monkeypatch.setattr(
            scraper, "get_chapter_url",
            lambda ref, num, language="pt-br": {"download_type": "mangadex_cbz", "page_urls": ["u1"]},
        )

        def fake_mangadex_download(scraper_arg, chapter_data, series_title, chapter_num,
                                    progress_callback=None, should_cancel=None):
            # Simula cancelamento no meio do download (ex.: entre páginas).
            return {"success": False, "cancelled": True, "error": "cancelled"}

        monkeypatch.setattr(bot, "_download_mangadex_chapter", fake_mangadex_download)
        summary = bot.download_complete_series("Serie", source_name="mangadex")
        assert summary["cancelled"] is True
        assert summary["failed_chapters"] == []
    finally:
        bot.cleanup()
