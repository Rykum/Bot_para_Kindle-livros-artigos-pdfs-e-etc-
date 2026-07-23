"""Ponte JS↔Python exposta ao frontend via pywebview (js_api).

Operações longas (search/download) são assíncronas e empurram eventos ao JS.
Leituras rápidas (library/dashboard/status/...) rodam de forma síncrona no
worker do BotService e retornam o resultado direto ao JS.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from app.bot_service import BotService
from app.komga_exporter import KomgaExporter
from app.metadata_enricher import MetadataEnricher


class Api:
    def __init__(self, service: BotService):
        self._service = service
        self._window = None

    def set_window(self, window) -> None:
        self._window = window

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
    def search(self, query: str, media_type: str = "manga") -> Dict[str, str]:
        def fn(bot, emit):
            results = bot.search_series(query, media_type=media_type)
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
