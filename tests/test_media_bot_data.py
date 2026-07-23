import tempfile
from pathlib import Path

from media_bot import MediaBot


def make_bot():
    return MediaBot(base_download_dir=str(Path(tempfile.mkdtemp()) / "dl"))


def test_get_library_data_returns_list_of_dicts():
    bot = make_bot()
    try:
        data = bot.get_library_data()
        assert isinstance(data, list)
        for item in data:
            assert "title" in item
            assert "completion_percentage" in item
            assert "is_complete" in item
    finally:
        bot.cleanup()


def test_dashboard_stats_has_expected_keys():
    bot = make_bot()
    try:
        stats = bot.dashboard_stats()
        for key in ["total_series", "total_downloaded", "complete_collections",
                    "missing_total", "by_format", "by_source"]:
            assert key in stats
        assert isinstance(stats["by_format"], dict)
        assert isinstance(stats["by_source"], dict)
    finally:
        bot.cleanup()


def test_get_series_status_data_returns_progress_dict():
    bot = make_bot()
    try:
        status = bot.get_series_status_data("Serie Inexistente XYZ")
        assert "completion_percentage" in status
        assert "title" in status
    finally:
        bot.cleanup()


def test_download_stops_when_should_cancel_true(monkeypatch):
    bot = make_bot()
    try:
        # Força uma lista de capítulos disponíveis sem tocar a rede.
        monkeypatch.setattr(bot, "get_complete_series_chapters", lambda *a, **k: [1.0, 2.0, 3.0])
        monkeypatch.setattr(bot, "_resolve_series_reference", lambda *a, **k: "ref")
        calls = {"n": 0}

        def fake_get_chapter_url(ref, num):
            calls["n"] += 1
            return {"download_url": "http://x/f.cbz", "format": "cbz"}

        scraper = bot._resolve_scraper("mangadex")
        monkeypatch.setattr(scraper, "get_chapter_url", fake_get_chapter_url)
        bot.download_complete_series("Serie", source_name="mangadex",
                                     should_cancel=lambda: True)
        assert calls["n"] == 0  # cancelado antes do primeiro capítulo
    finally:
        bot.cleanup()
