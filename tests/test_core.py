import tempfile
import unittest
from pathlib import Path
import tkinter as tk

from cache_manager import CacheManager
from media_bot import MediaBot, build_cli_parser
from gui_app import MediaBotGUI
from normalizer import ContentNormalizer, ParsedMetadata


class NormalizerTests(unittest.TestCase):
    def test_parse_filename_extracts_volume_chapter_and_format(self):
        metadata = ContentNormalizer.parse_filename("Dandadan Volume 1 Capítulo 15.cbz")

        self.assertEqual(metadata.volume_number, 1.0)
        self.assertEqual(metadata.chapter_number, 15.0)
        self.assertEqual(metadata.format_detected, "cbz")

    def test_missing_sequence_detects_simple_gap(self):
        missing = ContentNormalizer.find_missing_sequence([1.0, 2.0, 4.0])

        self.assertEqual(missing, [3.0])


class CacheTests(unittest.TestCase):
    def test_cache_roundtrip_and_clear(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = CacheManager(temp_dir)

            payload = {"title": "Dandadan", "chapter": 15}
            cache.set("search::dandadan", payload)

            self.assertEqual(cache.get("search::dandadan"), payload)
            self.assertEqual(cache.clear(), 1)
            self.assertIsNone(cache.get("search::dandadan"))


class CliAndBotTests(unittest.TestCase):
    def test_cli_parser_exposes_expected_commands(self):
        parser = build_cli_parser()
        parsed = parser.parse_args(["search", "Dandadan", "--media-type", "manga"])

        self.assertEqual(parsed.command, "search")
        self.assertEqual(parsed.query, "Dandadan")
        self.assertEqual(parsed.media_type, "manga")

    def test_media_bot_helpers_are_stable(self):
        bot = MediaBot(base_download_dir=str(Path(tempfile.gettempdir()) / "media-bot-tests"))
        try:
            self.assertEqual(bot._formats_for_media_type("manga"), ["cbz", "cbr"])
            self.assertEqual(bot._formats_for_media_type("livro"), ["pdf", "epub"])
            self.assertIsNotNone(bot._resolve_scraper("mangadex"))
        finally:
            bot.cleanup()


class GuiSmokeTests(unittest.TestCase):
    def test_gui_builds_without_error(self):
        root = tk.Tk()
        root.withdraw()
        try:
            gui = MediaBotGUI(root)
            self.assertIn("series", gui.metric_vars)
            self.assertTrue(gui.pipeline_labels)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()