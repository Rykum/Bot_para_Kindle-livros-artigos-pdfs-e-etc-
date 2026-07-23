import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from media_bot import MediaBot


def make_bot():
    return MediaBot(base_download_dir=str(Path(tempfile.mkdtemp()) / "dl"))


def test_mangadex_chapter_writes_comicinfo():
    bot = make_bot()
    try:
        class FakeScraper:
            def fetch_page(self, url, should_cancel=None, max_attempts=3):
                return b"img"

        chapter_data = {"page_urls": ["u1", "u2"], "download_type": "mangadex_cbz",
                        "title": "O Início", "volume": 1}
        series_meta = {"series": "Dandadan", "summary": "sinopse", "writer": "Autor X", "count": 120}
        result = bot._download_mangadex_chapter(
            FakeScraper(), chapter_data, "Dandadan", 15.0,
            series_meta=series_meta, language="pt-br",
        )
        assert result["success"] is True
        with zipfile.ZipFile(result["file_path"]) as zf:
            assert "ComicInfo.xml" in zf.namelist()
            root = ET.fromstring(zf.read("ComicInfo.xml"))
            got = {c.tag: c.text for c in root}
            assert got["Series"] == "Dandadan"
            assert got["Number"] == "15.0" or got["Number"] == "15"
            assert got["Writer"] == "Autor X"
            assert got["LanguageISO"] == "pt"
    finally:
        bot.cleanup()
