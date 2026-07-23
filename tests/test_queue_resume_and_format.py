import tempfile
import time
from pathlib import Path

from media_bot import MediaBot
from app.api import Api
from app.bot_service import BotService
from download_queue import DownloadQueue


def _wait(cond, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline and not cond():
        time.sleep(0.02)


class FakeBot:
    def __init__(self):
        self.downloaded = []

    def download_single_chapter(self, series, chapter_num, **kwargs):
        self.downloaded.append((series, chapter_num))
        return True

    def download_complete_series(self, series, **kwargs):
        return {"total": 0, "downloaded": 0, "failed": 0, "cancelled": False, "failed_chapters": []}

    def cleanup(self):
        pass


def test_set_window_resumes_persisted_queued_items():
    """Bug: itens 'queued' de sessão anterior não eram retomados ao abrir o app."""
    events, bot = [], FakeBot()
    service = BotService(bot_factory=lambda: bot, event_sink=lambda n, p: events.append((n, p)))
    api = Api(service)
    service.start()
    try:
        # Simula uma sessão anterior: um item já está na fila, mas nada o drenou.
        DownloadQueue().enqueue("SeriePrevia", [1.0])
        assert bot.downloaded == []
        # set_window (GUI pronta) deve retomar a fila.
        api.set_window(object())
        _wait(lambda: ("SeriePrevia", 1.0) in bot.downloaded)
        assert ("SeriePrevia", 1.0) in bot.downloaded
    finally:
        service.stop()


# --- extensão de arquivo para downloads diretos ---
def _bot():
    return MediaBot(base_download_dir=str(Path(tempfile.mkdtemp()) / "dl"))


def test_extension_from_explicit_format():
    bot = _bot()
    try:
        assert bot._resolve_file_extension({"format": "pdf", "download_url": "http://x/a.bin"}) == "pdf"
        assert bot._resolve_file_extension({"format": "epub", "download_url": "http://x/a"}) == "epub"
    finally:
        bot.cleanup()


def test_extension_derived_from_url_when_format_missing():
    bot = _bot()
    try:
        assert bot._resolve_file_extension({"download_url": "http://x/livro.pdf"}) == "pdf"
        assert bot._resolve_file_extension({"format": "unknown", "download_url": "http://x/book.epub"}) == "epub"
        assert bot._resolve_file_extension({"download_url": "http://x/hq.cbr"}) == "cbr"
    finally:
        bot.cleanup()


def test_extension_falls_back_when_unknown():
    bot = _bot()
    try:
        assert bot._resolve_file_extension({"download_url": "http://x/arquivo"}) == "bin"
    finally:
        bot.cleanup()
