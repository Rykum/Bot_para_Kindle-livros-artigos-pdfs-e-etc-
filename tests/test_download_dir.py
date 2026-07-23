import tempfile
import time
from pathlib import Path

import app.settings_store as ss
from media_bot import MediaBot
from app.api import Api
from app.bot_service import BotService


def make_bot():
    return MediaBot(base_download_dir=str(Path(tempfile.mkdtemp()) / "dl"))


def test_set_download_dir_updates_bot_and_downloader(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "_PATH", tmp_path / "cfg.json")
    bot = make_bot()
    try:
        target = tmp_path / "nova_pasta"
        result = bot.set_download_dir(str(target))
        assert Path(result) == target
        assert bot.base_dir == target
        assert Path(bot.downloader.base_directory) == target
        assert target.exists()
        # persistido
        assert ss.get_setting("download_dir") == str(target)
    finally:
        bot.cleanup()


def test_new_bot_reads_saved_download_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "_PATH", tmp_path / "cfg.json")
    saved = tmp_path / "salva"
    ss.set_setting("download_dir", str(saved))
    bot = MediaBot()  # sem arg → usa a pasta salva
    try:
        assert bot.base_dir == saved
    finally:
        bot.cleanup()


class FakeBot:
    def __init__(self):
        self.base_dir = "/atual/downloads"

    def set_download_dir(self, path):
        self.base_dir = path
        return path

    def cleanup(self):
        pass


def test_api_get_and_set_download_dir():
    events, bot = [], FakeBot()
    service = BotService(bot_factory=lambda: bot, event_sink=lambda n, p: events.append((n, p)))
    api = Api(service)
    service.start()
    try:
        assert api.get_download_dir() == "/atual/downloads"
        r = api.set_download_dir("/nova")
        assert r == {"path": "/nova"}
        assert api.get_download_dir() == "/nova"
    finally:
        service.stop()


def test_api_choose_download_dir_without_window_is_safe():
    events, bot = [], FakeBot()
    service = BotService(bot_factory=lambda: bot, event_sink=lambda n, p: events.append((n, p)))
    api = Api(service)  # sem set_window → self._window is None
    service.start()
    try:
        assert api.choose_download_dir() == {"path": None}
    finally:
        service.stop()
