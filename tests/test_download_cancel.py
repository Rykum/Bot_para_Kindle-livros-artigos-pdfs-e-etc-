import tempfile
from pathlib import Path

from media_bot import MediaBot


def make_bot():
    return MediaBot(base_download_dir=str(Path(tempfile.mkdtemp()) / "dl"))


def test_download_returns_summary_and_stops_on_cancel(monkeypatch):
    bot = make_bot()
    try:
        monkeypatch.setattr(bot, "_resolve_series_reference", lambda *a, **k: "ref")
        monkeypatch.setattr(bot, "get_complete_series_chapters", lambda *a, **k: [1.0, 2.0, 3.0])
        # Evita chamada HTTP real ao enricher (Jikan/AniList) durante o teste.
        monkeypatch.setattr(bot, "_build_series_meta", lambda *a, **k: {"series": "Serie"})
        summary = bot.download_complete_series("Serie", source_name="mangadex", should_cancel=lambda: True)
        assert summary["cancelled"] is True
        assert summary["downloaded"] == 0
        assert summary["total"] == 3
    finally:
        bot.cleanup()


def test_mangadex_chapter_cancel_between_pages(monkeypatch):
    bot = make_bot()
    try:
        calls = {"pages": 0}

        class FakeScraper:
            def fetch_page(self, url, should_cancel=None, max_attempts=3):
                calls["pages"] += 1
                if should_cancel and should_cancel():
                    raise RuntimeError("cancelled")
                return b"img"

        chapter_data = {"page_urls": ["u1", "u2", "u3"], "download_type": "mangadex_cbz"}
        result = bot._download_mangadex_chapter(
            FakeScraper(), chapter_data, "Serie", 1.0,
            should_cancel=lambda: calls["pages"] >= 1,  # cancela após a 1ª página
        )
        assert result["success"] is False
        assert result.get("cancelled") is True
        assert calls["pages"] <= 2  # não baixou todas as páginas
    finally:
        bot.cleanup()
