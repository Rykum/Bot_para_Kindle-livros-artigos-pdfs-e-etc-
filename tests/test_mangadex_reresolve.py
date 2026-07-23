import tempfile
from pathlib import Path

import requests

from media_bot import MediaBot


def make_bot():
    return MediaBot(base_download_dir=str(Path(tempfile.mkdtemp()) / "dl"))


def test_reresolve_on_expired_url_completes_chapter():
    bot = make_bot()
    try:
        state = {"reresolved": False}

        class FakeScraper:
            def fetch_page(self, url, should_cancel=None, max_attempts=3):
                if url.startswith("old/") and "2" in url:
                    resp = requests.Response()
                    resp.status_code = 410
                    err = requests.exceptions.HTTPError("expired")
                    err.response = resp
                    raise err
                return b"img"

            def reresolve_pages(self, chapter_id):
                state["reresolved"] = True
                return ["new/1.jpg", "new/2.jpg"]

        chapter_data = {"page_urls": ["old/1.jpg", "old/2.jpg"],
                        "download_type": "mangadex_cbz", "chapter_id": "abc"}
        result = bot._download_mangadex_chapter(FakeScraper(), chapter_data, "S", 1.0)
        assert state["reresolved"] is True
        assert result["success"] is True
    finally:
        bot.cleanup()
