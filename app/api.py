"""Ponte JS↔Python exposta ao frontend via pywebview (js_api).

Operações longas (search/download) são assíncronas e empurram eventos ao JS.
Leituras rápidas (library/dashboard/status/...) rodam de forma síncrona no
worker do BotService e retornam o resultado direto ao JS.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Dict, Optional

from app.bot_service import BotService
from app.komga_exporter import KomgaExporter
from app.metadata_enricher import MetadataEnricher
from download_queue import DownloadQueue


class Api:
    def __init__(self, service: BotService):
        self._service = service
        self._window = None
        self._queue = DownloadQueue()
        try:
            self._queue.requeue_stale()
        except Exception:
            pass
        self._paused = False
        self._draining = False
        self._drain_lock = threading.Lock()

    def set_window(self, window) -> None:
        self._window = window
        # Retoma a fila persistente assim que a GUI está pronta: itens que
        # ficaram "queued" de uma sessão anterior voltam a ser processados.
        try:
            self._start_drain()
        except Exception:
            pass

    # event_sink do BotService
    def emit_event(self, name: str, payload: dict) -> None:
        if self._window is None:
            return
        data = json.dumps(payload, ensure_ascii=False, default=str)
        try:
            self._window.evaluate_js(f"window.pushEvent({json.dumps(name)}, {data})")
        except Exception:
            pass

    # --- assíncronos ---
    def search(self, query: str, media_type: str = "manga", language: str = None) -> Dict[str, str]:
        def fn(bot, emit):
            results = bot.search_series(query, media_type=media_type, language=language or None)
            emit("search_results", {"results": results})
            return {"count": len(results)}
        return {"job_id": self._service.submit(f"Busca: {query}", fn)}

    def download_series(self, series: str, media_type: str = "manga",
                        source: str = "mangadex", chapters=None,
                        language: str = "pt-br", fallback_language: Optional[str] = None) -> Dict[str, str]:
        job_holder: Dict[str, Optional[str]] = {"id": None}

        def fn(bot, emit):
            def progress(label, current, total):
                emit("progress", {"label": label, "current": current, "total": total})
            return bot.download_complete_series(
                series, media_type=media_type, source_name=source,
                progress_callback=progress,
                should_cancel=lambda: self._service.is_cancelled(job_holder["id"]),
                chapters=chapters, language=language, fallback_language=fallback_language,
            )

        job_id = self._service.submit(f"Download: {series}", fn)
        job_holder["id"] = job_id
        return {"job_id": job_id}

    def list_chapters(self, series: str, media_type: str = "manga", source: str = "mangadex",
                      language: str = "pt-br", fallback_language: Optional[str] = None) -> Dict[str, str]:
        def fn(bot, emit):
            data = bot.list_series_chapters(series, media_type=media_type, source_name=source,
                                            language=language, fallback_language=fallback_language)
            emit("chapters_list", data)
            return {"count": len(data.get("available", []))}
        return {"job_id": self._service.submit(f"Capítulos: {series}", fn)}

    # --- síncronos ---
    def library(self) -> Any:
        return self._service.run_sync("library", lambda bot, emit: bot.get_library_data(), quiet=True)

    def dashboard_stats(self) -> Any:
        return self._service.run_sync("dashboard", lambda bot, emit: bot.dashboard_stats(), quiet=True)

    def series_status(self, series: str) -> Any:
        return self._service.run_sync("status", lambda bot, emit: bot.get_series_status_data(series), quiet=True)

    def graph_status(self) -> Any:
        def fn(bot, emit):
            bot.print_graph_status()  # log vai por evento
            return {"ok": True}
        return {"job_id": self._service.submit("Status do grafo", fn)}

    def clear_cache(self) -> Dict[str, int]:
        removed = self._service.run_sync("cache-clear", lambda bot, emit: bot.clear_cache(), quiet=True)
        return {"removed": removed}

    def get_download_dir(self) -> str:
        return self._service.run_sync("get-dir", lambda bot, emit: str(bot.base_dir), quiet=True)

    def set_download_dir(self, path: str) -> Dict[str, Any]:
        new = self._service.run_sync("set-dir", lambda bot, emit: bot.set_download_dir(path), quiet=True)
        return {"path": new}

    def _open_in_explorer(self, path) -> bool:
        import os
        import sys
        import subprocess
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
            return True
        except Exception:
            return False

    def open_download_dir(self) -> Dict[str, Any]:
        from pathlib import Path
        path = self._service.run_sync("get-dir", lambda bot, emit: str(bot.base_dir), quiet=True)
        Path(path).mkdir(parents=True, exist_ok=True)
        return {"ok": self._open_in_explorer(path)}

    def open_path(self, path: str) -> Dict[str, Any]:
        return {"ok": self._open_in_explorer(path)}

    def choose_download_dir(self) -> Dict[str, Any]:
        """Abre o seletor de pasta nativo e aplica a escolha (persistida)."""
        if self._window is None:
            return {"path": None}
        try:
            import webview
            result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        except Exception:
            return {"path": None}
        if not result:
            return {"path": None}
        chosen = result[0] if isinstance(result, (list, tuple)) else result
        return self.set_download_dir(chosen)

    def enrich_metadata(self, title: str) -> Any:
        def fn(bot, emit):
            enricher = MetadataEnricher(cache=bot.cache)
            return enricher.enrich(title)
        return self._service.run_sync("enrich", fn, quiet=True)

    def export_komga(self, series: str) -> Any:
        def fn(bot, emit):
            exporter = KomgaExporter(library=bot.library)
            return exporter.export_series(series)
        return self._service.run_sync("export", fn, quiet=True)

    def cancel_job(self, job_id: str) -> Dict[str, bool]:
        self._service.cancel(job_id)
        return {"cancelled": True}

    # --- fila de downloads ---
    def _emit_queue(self):
        self.emit_event("queue_update", {"items": self._queue.list_items(), "paused": self._paused})

    def enqueue(self, series, chapters=None, source="mangadex", media_type="manga",
                language="pt-br", fallback_language=None):
        ids = self._queue.enqueue(series, chapters, source=source, media_type=media_type,
                                  language=language, fallback_language=fallback_language)
        self._emit_queue()
        self._start_drain()
        return {"enqueued": len(ids)}

    def _start_drain(self):
        with self._drain_lock:
            if self._draining or self._paused:
                return
            self._draining = True

        def drain(bot, emit):
            self._queue.requeue_stale()
            try:
                while not self._paused:
                    item = self._queue.next_queued()
                    if not item:
                        break
                    job_id = item["id"]
                    self._queue.mark(job_id, "downloading")
                    emit("queue_update", {"items": self._queue.list_items(), "paused": self._paused})

                    def progress(label, current, total):
                        emit("progress", {"label": label, "current": current, "total": total})

                    should_cancel = lambda: self._queue.get_status(job_id) == "cancelled"
                    try:
                        if item["chapter_number"] is None:
                            summary = bot.download_complete_series(
                                item["series"], media_type=item["media_type"], source_name=item["source"],
                                progress_callback=progress, should_cancel=should_cancel,
                                language=item["language"],
                                fallback_language=item["fallback_language"])
                            ok = bool(summary) and not summary.get("cancelled") and not summary.get("failed_chapters")
                        else:
                            ok = bot.download_single_chapter(
                                item["series"], item["chapter_number"], source_name=item["source"],
                                media_type=item["media_type"], language=item["language"],
                                fallback_language=item["fallback_language"], progress_callback=progress,
                                should_cancel=should_cancel)
                        if self._queue.get_status(job_id) != "cancelled":
                            self._queue.mark(job_id, "done" if ok else "failed",
                                             None if ok else "download não concluído")
                    except Exception as exc:  # noqa: BLE001
                        if self._queue.get_status(job_id) != "cancelled":
                            self._queue.mark(job_id, "failed", str(exc))
                    emit("queue_update", {"items": self._queue.list_items(), "paused": self._paused})
            finally:
                with self._drain_lock:
                    self._draining = False
            if not self._paused and self._queue.next_queued():
                self._start_drain()
            return {"drained": True}

        self._service.submit("Fila de downloads", drain)

    def queue_list(self):
        return self._service.run_sync("queue_list", lambda bot, emit: self._queue.list_items(), quiet=True)

    def cancel_item(self, job_id):
        self._queue.cancel_item(job_id)
        self._emit_queue()
        return {"ok": True}

    def retry_item(self, job_id):
        self._queue.retry_item(job_id)
        self._emit_queue()
        self._start_drain()
        return {"ok": True}

    def remove_item(self, job_id):
        self._queue.remove_item(job_id)
        self._emit_queue()
        return {"ok": True}

    def clear_finished(self):
        self._queue.clear_finished()
        self._emit_queue()
        return {"ok": True}

    def pause_queue(self):
        self._paused = True
        self._emit_queue()
        return {"ok": True}

    def resume_queue(self):
        self._paused = False
        self._emit_queue()
        self._start_drain()
        return {"ok": True}
