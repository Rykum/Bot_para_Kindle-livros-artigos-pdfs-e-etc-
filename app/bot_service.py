"""Worker serial que executa todas as operações do MediaBot em uma única thread.

Garante que a Session SQLite global (db_manager) nunca seja acessada por duas
threads ao mesmo tempo. Operações longas usam submit() (assíncrono, via eventos);
leituras rápidas usam run_sync() (bloqueante, retorna o resultado).
"""

from __future__ import annotations

import contextlib
import io
import queue
import threading
import uuid
from typing import Any, Callable, Optional

EventSink = Callable[[str, dict], None]
Job = Callable[[Any, Callable[[str, dict], None]], Any]

_SENTINEL = object()


class _EmittingStream(io.TextIOBase):
    """Reemite cada linha de stdout como evento 'log' em tempo real."""

    def __init__(self, emit: Callable[[str, dict], None]):
        self._emit = emit
        self._buffer = ""

    def write(self, text: str) -> int:
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._emit("log", {"line": line})
        return len(text)

    def flush(self) -> None:
        if self._buffer:
            self._emit("log", {"line": self._buffer})
            self._buffer = ""


class BotService:
    def __init__(self, bot_factory: Callable[[], Any], event_sink: EventSink):
        self._bot_factory = bot_factory
        self._event_sink = event_sink
        self._queue: "queue.Queue" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._bot: Any = None
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()

    # --- ciclo de vida ---
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._queue.put(_SENTINEL)
        if self._thread:
            self._thread.join(timeout=5)

    # --- submissão ---
    def submit(self, label: str, fn: Job) -> str:
        job_id = uuid.uuid4().hex
        self._queue.put((job_id, label, fn, None))
        return job_id

    def run_sync(self, label: str, fn: Job, timeout: float = 120) -> Any:
        job_id = uuid.uuid4().hex
        box: dict = {"event": threading.Event(), "result": None, "error": None}
        self._queue.put((job_id, label, fn, box))
        if not box["event"].wait(timeout):
            raise TimeoutError(f"Operação '{label}' excedeu {timeout}s")
        if box["error"] is not None:
            raise box["error"]
        return box["result"]

    # --- cancelamento cooperativo ---
    def cancel(self, job_id: str) -> None:
        with self._lock:
            self._cancelled.add(job_id)

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._cancelled

    # --- loop do worker ---
    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                break
            job_id, label, fn, box = item
            if self._bot is None:
                self._bot = self._bot_factory()

            def emit(name: str, payload: dict) -> None:
                self._event_sink(name, {**payload, "job_id": job_id})

            self._event_sink("job_started", {"job_id": job_id, "label": label})
            stream = _EmittingStream(emit)
            try:
                with contextlib.redirect_stdout(stream):
                    result = fn(self._bot, emit)
                stream.flush()
                if box is not None:
                    box["result"] = result
                self._event_sink("job_done", {"job_id": job_id, "label": label, "result": result})
            except Exception as exc:  # noqa: BLE001 — a UI precisa do erro
                stream.flush()
                if box is not None:
                    box["error"] = exc
                self._event_sink("job_error", {"job_id": job_id, "label": label, "error": str(exc)})
            finally:
                if box is not None:
                    box["event"].set()

        if self._bot is not None and hasattr(self._bot, "cleanup"):
            with contextlib.suppress(Exception):
                self._bot.cleanup()
