# Ciclo 2 — Refactor DB + Fila persistente + UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fim do singleton global de sessão do DB (via `session_scope()` + sessão própria), uma fila de downloads persistente (`download_jobs`), e a aba Downloads virando um gerenciador de fila por item.

**Architecture:** DB primeiro (fundação), depois o `DownloadQueue` (CRUD via `session_scope`), depois o `MediaBot` ganha download de 1 capítulo, o `Api` ganha um "drain job" que o worker serial roda para esvaziar a fila, e por fim a UI de fila.

**Tech Stack:** Python 3.13, SQLAlchemy/SQLite, pywebview, pytest, node (`node --check`).

## Global Constraints

- **Interpretador:** o `python` do PATH está quebrado. Use SEMPRE `py -3.13` (ex.: `py -3.13 -m pytest`).
- **Entrypoint da GUI:** `desktop.py` (não `app.py`).
- **Núcleo estável:** só adicionar parâmetros keyword opcionais; não quebrar CLI/`tests/test_core.py` nem os testes de download já existentes. Rodar a suíte completa antes de cada commit.
- **Concorrência:** todo acesso ao bot/DB continua via worker serial do `BotService`. O código novo (fila) usa `db_manager.session_scope()` por operação.
- **Não migrar** o `LibraryManager` para session-per-operation agora (evitar objetos ORM detached); ele só passa a ter **sessão própria por instância**.
- **Idioma da copy:** pt-br.

---

### Task 1: DB — `session_scope()`, sessão própria, `DownloadJob`

**Files:**
- Modify: `database.py`
- Modify: `media_bot.py` (`cleanup`)
- Test: `tests/test_db_session.py`

**Interfaces:**
- Produces:
  - `db_manager.get_session()` retorna uma **nova** `Session` (SessionLocal), não uma global.
  - `db_manager.session_scope()` — context manager: commit no sucesso, rollback na exceção, close no fim.
  - `db_manager.SessionLocal` = `sessionmaker(bind=engine, expire_on_commit=False)`.
  - `class DownloadJob(Base)` na tabela `download_jobs`.
  - `MediaBot.cleanup()` fecha só a sessão do `LibraryManager` (sem `db_manager.close()`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_db_session.py`:

```python
import pytest

from database import db_manager, DownloadJob, Series


def test_session_scope_commits_and_isolates():
    with db_manager.session_scope() as s:
        s.add(Series(title="ScopeSerie", source_name="x"))
    with db_manager.session_scope() as s2:
        found = s2.query(Series).filter(Series.title == "ScopeSerie").first()
        assert found is not None


def test_session_scope_rolls_back_on_error():
    try:
        with db_manager.session_scope() as s:
            s.add(Series(title="RollbackSerie", source_name="x"))
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    with db_manager.session_scope() as s2:
        assert s2.query(Series).filter(Series.title == "RollbackSerie").first() is None


def test_get_session_returns_independent_sessions():
    a = db_manager.get_session()
    b = db_manager.get_session()
    assert a is not b
    a.close()
    b.close()


def test_download_job_model_exists():
    with db_manager.session_scope() as s:
        job = DownloadJob(series="S", chapter_number=1.0, status="queued")
        s.add(job)
        s.flush()
        assert job.id is not None
        assert job.status == "queued"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_db_session.py -v`
Expected: FAIL (`session_scope` inexistente; `DownloadJob` inexistente).

- [ ] **Step 3: Refactor `DatabaseManager` + add `DownloadJob`**

In `database.py`, add the import at the top:

```python
from contextlib import contextmanager
```

Add the `DownloadJob` model (after `MediaFile`):

```python
class DownloadJob(Base):
    """Item da fila de downloads (persistente)."""
    __tablename__ = 'download_jobs'

    id = Column(Integer, primary_key=True)
    series = Column(String, nullable=False)
    source = Column(String, default='mangadex')
    media_type = Column(String, default='manga')
    chapter_number = Column(Float, nullable=True)  # None = série inteira (faltantes)
    language = Column(String, default='pt-br')
    fallback_language = Column(String, nullable=True)
    status = Column(String, default='queued')  # queued/downloading/done/failed/cancelled
    error = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<DownloadJob(series='{self.series}', chapter={self.chapter_number}, status='{self.status}')>"
```

Replace the `DatabaseManager` class with:

Add the imports at the top of `database.py` (near the SQLAlchemy imports):

```python
from sqlalchemy import event
```

```python
class DatabaseManager:
    """Gerenciador de engine e sessões. Sem sessão global compartilhada."""

    def __init__(self, db_path: str = str(DB_PATH)):
        # check_same_thread=False: a fila é mutada pela thread do JS-API enquanto o
        # worker serial drena — cada session_scope abre sua própria conexão.
        self.engine = create_engine(
            f'sqlite:///{db_path}', echo=False,
            connect_args={"check_same_thread": False},
        )

        # WAL + busy_timeout reduzem "database is locked" sob acesso concorrente.
        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def get_session(self):
        """Retorna uma NOVA sessão (o chamador é responsável por fechá-la)."""
        return self.SessionLocal()

    @contextmanager
    def session_scope(self):
        """Sessão com commit/rollback/close automáticos."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def reset_db(self):
        """CUIDADO: Apaga todo o banco."""
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)


db_manager = DatabaseManager()
```

- [ ] **Step 4: Update `MediaBot.cleanup`**

In `media_bot.py`, change `cleanup`:

```python
    def cleanup(self):
        """Limpeza final."""
        self.library.cleanup()
```

(Remove the `db_manager.close()` line. If `db_manager` is now unused in `media_bot.py`, keep the import — `Series`/other names may still be used; leave the import line as-is.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.13 -m pytest tests/test_db_session.py tests/test_core.py tests/test_download_cancel.py -v`
Expected: passam, sem regressão. (`tests/conftest.py`'s `reset_db()` continua funcionando.)

- [ ] **Step 6: Commit**

```bash
git add database.py media_bot.py tests/test_db_session.py
git commit -m "feat: session_scope e sessão própria no DB; modelo DownloadJob"
```

---

### Task 2: `DownloadQueue` (CRUD da fila)

**Files:**
- Create: `download_queue.py`
- Test: `tests/test_download_queue.py`

**Interfaces:**
- Consumes: `db_manager.session_scope()`, `DownloadJob` (Task 1).
- Produces:
  - `class DownloadQueue`
  - `enqueue(series, chapters, source="mangadex", media_type="manga", language="pt-br", fallback_language=None) -> List[int]`
  - `list_items(limit=500) -> List[dict]`; `next_queued() -> Optional[dict]`; `mark(job_id, status, error=None)`; `cancel_item(job_id)`; `retry_item(job_id)`; `remove_item(job_id)`; `clear_finished()`; `requeue_stale()`.
  - dict de item: `{id, series, source, media_type, chapter_number, language, fallback_language, status, error}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_download_queue.py`:

```python
from download_queue import DownloadQueue


def test_enqueue_creates_one_row_per_chapter():
    q = DownloadQueue()
    ids = q.enqueue("Dandadan", [1.0, 2.0, 3.0], source="mangadex", language="pt-br")
    assert len(ids) == 3
    items = q.list_items()
    chapters = sorted(i["chapter_number"] for i in items if i["series"] == "Dandadan")
    assert chapters == [1.0, 2.0, 3.0]
    assert all(i["status"] == "queued" for i in items)


def test_enqueue_none_creates_single_series_row():
    q = DownloadQueue()
    ids = q.enqueue("One Piece", None)
    assert len(ids) == 1
    item = [i for i in q.list_items() if i["id"] == ids[0]][0]
    assert item["chapter_number"] is None


def test_next_queued_is_fifo_and_mark_advances():
    q = DownloadQueue()
    a, b = q.enqueue("S", [1.0, 2.0])
    nxt = q.next_queued()
    assert nxt["id"] == a
    q.mark(a, "done")
    assert q.next_queued()["id"] == b


def test_cancel_retry_remove_clear():
    q = DownloadQueue()
    a, b = q.enqueue("S", [1.0, 2.0])
    q.cancel_item(a)
    assert [i for i in q.list_items() if i["id"] == a][0]["status"] == "cancelled"
    q.retry_item(a)
    assert [i for i in q.list_items() if i["id"] == a][0]["status"] == "queued"
    q.mark(b, "done")
    q.clear_finished()
    remaining = {i["id"] for i in q.list_items()}
    assert b not in remaining and a in remaining
    q.remove_item(a)
    assert not q.list_items()


def test_requeue_stale_resets_downloading():
    q = DownloadQueue()
    (a,) = q.enqueue("S", [1.0])
    q.mark(a, "downloading")
    q.requeue_stale()
    assert q.next_queued()["id"] == a
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_download_queue.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'download_queue'`).

- [ ] **Step 3: Implement `DownloadQueue`**

Create `download_queue.py`:

```python
"""Fila de downloads persistente (SQLite via DownloadJob)."""

from __future__ import annotations

from typing import List, Optional

from database import DownloadJob, db_manager

_FIELDS = ("id", "series", "source", "media_type", "chapter_number",
           "language", "fallback_language", "status", "error")


def _to_dict(job: DownloadJob) -> dict:
    return {field: getattr(job, field) for field in _FIELDS}


class DownloadQueue:
    def enqueue(self, series: str, chapters, source: str = "mangadex",
                media_type: str = "manga", language: str = "pt-br",
                fallback_language: Optional[str] = None) -> List[int]:
        targets = list(chapters) if chapters else [None]
        ids: List[int] = []
        with db_manager.session_scope() as s:
            for ch in targets:
                job = DownloadJob(
                    series=series, source=source, media_type=media_type,
                    chapter_number=(float(ch) if ch is not None else None),
                    language=language, fallback_language=fallback_language,
                    status="queued",
                )
                s.add(job)
                s.flush()
                ids.append(job.id)
        return ids

    def list_items(self, limit: int = 500) -> List[dict]:
        with db_manager.session_scope() as s:
            rows = s.query(DownloadJob).order_by(DownloadJob.id).limit(limit).all()
            return [_to_dict(j) for j in rows]

    def next_queued(self) -> Optional[dict]:
        with db_manager.session_scope() as s:
            job = (s.query(DownloadJob)
                   .filter(DownloadJob.status == "queued")
                   .order_by(DownloadJob.id).first())
            return _to_dict(job) if job else None

    def mark(self, job_id: int, status: str, error: Optional[str] = None) -> None:
        with db_manager.session_scope() as s:
            job = s.get(DownloadJob, job_id)
            if job:
                job.status = status
                job.error = error

    def cancel_item(self, job_id: int) -> None:
        self.mark(job_id, "cancelled")

    def retry_item(self, job_id: int) -> None:
        self.mark(job_id, "queued", None)

    def remove_item(self, job_id: int) -> None:
        with db_manager.session_scope() as s:
            job = s.get(DownloadJob, job_id)
            if job:
                s.delete(job)

    def clear_finished(self) -> int:
        with db_manager.session_scope() as s:
            return (s.query(DownloadJob)
                    .filter(DownloadJob.status.in_(["done", "cancelled"]))
                    .delete(synchronize_session=False))

    def requeue_stale(self) -> int:
        with db_manager.session_scope() as s:
            return (s.query(DownloadJob)
                    .filter(DownloadJob.status == "downloading")
                    .update({"status": "queued"}, synchronize_session=False))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.13 -m pytest tests/test_download_queue.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add download_queue.py tests/test_download_queue.py
git commit -m "feat: DownloadQueue persistente (CRUD via session_scope)"
```

---

### Task 3: `MediaBot` — download de 1 capítulo com retry/fallback

**Files:**
- Modify: `media_bot.py`
- Test: `tests/test_download_single.py`

**Interfaces:**
- Consumes: `_attempt_chapter` (existente, tri-state `"ok"/"fail"/"cancelled"`), `_build_series_meta`, `_resolve_scraper`, `_resolve_series_reference`.
- Produces:
  - `MediaBot._download_one_chapter_with_retries(scraper, series, series_reference, series_title, chapter_num, source_name, language, fallback_language, series_meta, progress_callback, should_cancel) -> str` (`"ok"/"fail"/"cancelled"`): até 3 tentativas no idioma primário, depois 1 no fallback.
  - `MediaBot.download_single_chapter(series_title, chapter_num, source_name="mangadex", media_type="manga", language="pt-br", fallback_language=None, progress_callback=None, should_cancel=None) -> bool` — resolve scraper/reference/series_meta e chama o helper; retorna `True` em sucesso.
  - `download_complete_series` passa a usar `_download_one_chapter_with_retries` por capítulo (mantendo o resumo/semântica de cancelado).

- [ ] **Step 1: Write the failing test**

Create `tests/test_download_single.py`:

```python
import tempfile
from pathlib import Path

from media_bot import MediaBot


def make_bot():
    return MediaBot(base_download_dir=str(Path(tempfile.mkdtemp()) / "dl"))


def test_download_single_chapter_success(monkeypatch):
    bot = make_bot()
    try:
        monkeypatch.setattr(bot, "_resolve_series_reference", lambda *a, **k: "ref")
        monkeypatch.setattr(bot, "_build_series_meta", lambda *a, **k: {"series": "S"})
        scraper = bot._resolve_scraper("mangadex")
        monkeypatch.setattr(scraper, "get_chapter_url",
                            lambda ref, num, language="pt-br": {"download_url": "http://x/f.cbz", "format": "cbz"})
        monkeypatch.setattr(bot.downloader, "download",
                            lambda **kw: {"success": True, "file_path": "f", "metadata": {"format": "cbz", "size": 1, "sha256": "h"}})
        ok = bot.download_single_chapter("S", 5.0, source_name="mangadex")
        assert ok is True
    finally:
        bot.cleanup()


def test_download_single_chapter_fails_after_retries(monkeypatch):
    bot = make_bot()
    try:
        monkeypatch.setattr(bot, "_resolve_series_reference", lambda *a, **k: "ref")
        monkeypatch.setattr(bot, "_build_series_meta", lambda *a, **k: {"series": "S"})
        scraper = bot._resolve_scraper("mangadex")
        monkeypatch.setattr(scraper, "get_chapter_url", lambda ref, num, language="pt-br": None)
        ok = bot.download_single_chapter("S", 5.0, source_name="mangadex")
        assert ok is False
    finally:
        bot.cleanup()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_download_single.py -v`
Expected: FAIL (`download_single_chapter` inexistente).

- [ ] **Step 3: Extract the per-chapter retry helper + add `download_single_chapter`**

In `media_bot.py`, add `_download_one_chapter_with_retries`. Match `_attempt_chapter`'s ACTUAL argument order in your call (read the current definition first; it returns `"ok"/"fail"/"cancelled"` and takes `series_meta`):

```python
    def _download_one_chapter_with_retries(self, scraper, series, series_reference, series_title,
                                           chapter_num, source_name, language, fallback_language,
                                           series_meta, progress_callback, should_cancel):
        for _ in range(3):
            if should_cancel is not None and should_cancel():
                return "cancelled"
            status = self._attempt_chapter(scraper, series, series_reference, series_title,
                                           chapter_num, source_name, language,
                                           progress_callback, should_cancel, series_meta)
            if status in ("ok", "cancelled"):
                return status
        if fallback_language:
            if should_cancel is not None and should_cancel():
                return "cancelled"
            status = self._attempt_chapter(scraper, series, series_reference, series_title,
                                           chapter_num, source_name, fallback_language,
                                           progress_callback, should_cancel, series_meta)
            if status in ("ok", "cancelled"):
                return status
        return "fail"

    def download_single_chapter(self, series_title, chapter_num, source_name="mangadex",
                                media_type="manga", language="pt-br", fallback_language=None,
                                progress_callback=None, should_cancel=None) -> bool:
        scraper = self._resolve_scraper(source_name)
        if not scraper:
            return False
        series = self.library.get_or_create_series(series_title, source_name)
        series_reference = self._resolve_series_reference(scraper, series_title, media_type)
        series_meta = self._build_series_meta(series_title, source_name, media_type, series_reference)
        status = self._download_one_chapter_with_retries(
            scraper, series, series_reference, series_title, chapter_num, source_name,
            language, fallback_language, series_meta, progress_callback, should_cancel)
        return status == "ok"
```

Then refactor `download_complete_series`'s per-chapter loop to call `_download_one_chapter_with_retries` for each chapter in `missing_chapters` (instead of the inline round/fallback loops), accumulating `downloaded_count`/`failed_chapters` and breaking on `"cancelled"` (set `cancelled=True`). Keep the summary return `{total, downloaded, failed, cancelled, failed_chapters}` unchanged. **The existing tests in `tests/test_download_retry_select.py` and `tests/test_download_cancel.py` MUST still pass** — run them.

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.13 -m pytest tests/test_download_single.py tests/test_download_retry_select.py tests/test_download_cancel.py tests/test_core.py -v`
Expected: passam, sem regressão.

- [ ] **Step 5: Commit**

```bash
git add media_bot.py tests/test_download_single.py
git commit -m "feat: download de 1 capítulo com retry/fallback reaproveitável pela fila"
```

---

### Task 4: `Api` — runner da fila + endpoints + eventos

**Files:**
- Modify: `app/api.py`
- Test: `tests/test_api_queue.py`

**Interfaces:**
- Consumes: `BotService`, `DownloadQueue`, `MediaBot.download_single_chapter`/`download_complete_series`.
- Produces (na classe `Api`):
  - `enqueue(series, chapters=None, source="mangadex", media_type="manga", language="pt-br", fallback_language=None) -> {enqueued: int}` — grava na fila, emite `queue_update`, e inicia o drain se não houver um ativo.
  - `queue_list() -> List[dict]` (sync via `run_sync`).
  - `cancel_item(id)`, `retry_item(id)` (re-inicia o drain), `remove_item(id)`, `clear_finished()`, `pause_queue()`, `resume_queue()` (re-inicia o drain) — todos síncronos, retornam `{ok: True}` (e emitem `queue_update`).
  - Evento `queue_update` (payload `{items: [...], paused: bool}`) empurrado a cada mudança.

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_queue.py`:

```python
import time

from app.api import Api
from app.bot_service import BotService
from download_queue import DownloadQueue


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


def make_api(events, bot):
    service = BotService(bot_factory=lambda: bot, event_sink=lambda n, p: events.append((n, p)))
    api = Api(service)
    service.start()
    return api, service


def _wait(cond, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline and not cond():
        time.sleep(0.02)


def test_enqueue_drains_queue_in_order():
    DownloadQueue()  # garante import/tabela
    events, bot = [], FakeBot()
    api, service = make_api(events, bot)
    try:
        # limpa qualquer resíduo de fila
        for it in api.queue_list():
            api.remove_item(it["id"])
        ack = api.enqueue("Dandadan", [1.0, 2.0], source="mangadex")
        assert ack["enqueued"] == 2
        _wait(lambda: len(bot.downloaded) >= 2)
        assert bot.downloaded == [("Dandadan", 1.0), ("Dandadan", 2.0)]
        # eventos de queue_update foram emitidos
        assert any(n == "queue_update" for n, _ in events)
    finally:
        service.stop()


def test_queue_list_and_clear_finished():
    events, bot = [], FakeBot()
    api, service = make_api(events, bot)
    try:
        for it in api.queue_list():
            api.remove_item(it["id"])
        api.enqueue("S", [1.0])
        _wait(lambda: all(i["status"] in ("done", "failed") for i in api.queue_list()) and api.queue_list())
        api.clear_finished()
        assert api.queue_list() == []
    finally:
        service.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_api_queue.py -v`
Expected: FAIL (`enqueue` inexistente).

- [ ] **Step 3: Implement the queue runner + endpoints in `Api`**

In `app/api.py`, add to `__init__`: `self._queue = DownloadQueue()`, `self._paused = False`, `self._draining = False` (import `from download_queue import DownloadQueue`). Add:

```python
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
                    self.emit_event("queue_update", {"items": self._queue.list_items(), "paused": self._paused})

                    def progress(label, current, total):
                        emit("progress", {"label": label, "current": current, "total": total})

                    try:
                        if item["chapter_number"] is None:
                            summary = bot.download_complete_series(
                                item["series"], media_type=item["media_type"], source_name=item["source"],
                                progress_callback=progress, language=item["language"],
                                fallback_language=item["fallback_language"])
                            ok = bool(summary and summary.get("downloaded", 0) >= 0 and not summary.get("cancelled"))
                        else:
                            ok = bot.download_single_chapter(
                                item["series"], item["chapter_number"], source_name=item["source"],
                                media_type=item["media_type"], language=item["language"],
                                fallback_language=item["fallback_language"], progress_callback=progress)
                        self._queue.mark(job_id, "done" if ok else "failed",
                                         None if ok else "download não concluído")
                    except Exception as exc:  # noqa: BLE001
                        self._queue.mark(job_id, "failed", str(exc))
                    self.emit_event("queue_update", {"items": self._queue.list_items(), "paused": self._paused})
            finally:
                self._draining = False
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
```

Note: `queue_list`/`cancel_item`/etc. read/write the DB via `DownloadQueue` (its own `session_scope`), so they are safe to run directly (each opens+closes its own session) — but to keep ALL DB access on the worker thread, route `queue_list` through `run_sync` (as above) and keep the mutations (cancel/retry/remove/clear/pause/resume) via `DownloadQueue`'s scoped sessions, which are short and self-contained. (If the reviewer flags cross-thread DB access, wrap the mutations in `run_sync` too.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.13 -m pytest tests/test_api_queue.py tests/test_api.py tests/test_api_chapters.py -v`
Expected: passam.

- [ ] **Step 5: Commit**

```bash
git add app/api.py tests/test_api_queue.py
git commit -m "feat: runner da fila e endpoints de fila na Api"
```

---

### Task 5: Frontend — aba Downloads como gerenciador de fila

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`
- Test: `tests/test_frontend_queue.py`

**Interfaces:** consome `Api.enqueue`, `queue_list`, `cancel_item`, `retry_item`, `remove_item`, `clear_finished`, `pause_queue`, `resume_queue`, e o evento `queue_update`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_frontend_queue.py`:

```python
from pathlib import Path

FRONT = Path(__file__).parent.parent / "frontend"


def test_index_has_queue_controls():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert 'id="queue-list"' in html
    assert 'id="btn-queue-pause"' in html
    assert 'id="btn-queue-clear"' in html


def test_appjs_wires_queue():
    js = (FRONT / "app.js").read_text(encoding="utf-8")
    assert "queue_update" in js
    assert "enqueue" in js
    assert "cancel_item" in js and "retry_item" in js
    assert "window.pushEvent" in js and "window.pywebview.api" in js
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_frontend_queue.py -v`
Expected: FAIL.

- [ ] **Step 3: Add queue markup to `index.html`**

In `frontend/index.html`, inside `#view-downloads` (after the progress area, before/around the log), add:

```html
        <div class="form-row">
          <button id="btn-queue-pause" class="btn">Pausar fila</button>
          <button id="btn-queue-clear" class="btn">Limpar concluídos</button>
          <span id="queue-counts" class="muted">—</span>
        </div>
        <div id="queue-list" class="queue-list"></div>
```

- [ ] **Step 4: Add queue styles to `styles.css`**

Append to `frontend/styles.css`:

```css
.queue-list { display: flex; flex-direction: column; gap: 6px; margin: 10px 0; max-height: 40vh; overflow-y: auto; }
.queue-item { display: flex; align-items: center; gap: 10px; background: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 8px 12px; }
.queue-item .title { flex: 1; font-size: 13px; }
.queue-badge { font-size: 11px; padding: 2px 8px; border-radius: 999px; }
.queue-badge.queued { background: #1f2937; color: #cbd5e1; }
.queue-badge.downloading { background: #1d4ed8; color: #fff; }
.queue-badge.done { background: #0f766e; color: #fff; }
.queue-badge.failed { background: #7f1d1d; color: #fff; }
.queue-badge.cancelled { background: #92400e; color: #fff; }
.queue-item button { padding: 4px 8px; font-size: 12px; }
```

- [ ] **Step 5: Wire the queue in `app.js`**

In `frontend/app.js`:

(a) Make the chapter-picker download buttons ENQUEUE instead of a single download. Replace the body of `startDownload(chapters)` so it calls `api().enqueue(...)` and goes to Downloads:

```javascript
function startDownload(chapters) {
  api().enqueue(chaptersState.series, chapters, chaptersState.source, chaptersState.media,
                langPrimary(), langFallback());
  goTo("downloads");
  loadQueue();
}
```

(b) Add queue rendering + controls:

```javascript
async function loadQueue() {
  const items = await api().queue_list();
  renderQueue(items || []);
}
on("queue_update", (p) => renderQueue((p && p.items) || []));

function renderQueue(items) {
  const box = document.getElementById("queue-list");
  if (!box) return;
  const counts = items.reduce((a, i) => { a[i.status] = (a[i.status] || 0) + 1; return a; }, {});
  const cEl = document.getElementById("queue-counts");
  if (cEl) cEl.textContent =
    `${counts.queued || 0} na fila · ${counts.downloading || 0} baixando · ${counts.done || 0} ok · ${counts.failed || 0} falhou`;
  box.innerHTML = "";
  items.forEach((i) => {
    const chap = i.chapter_number == null ? "série completa" : "cap " + i.chapter_number;
    const div = document.createElement("div");
    div.className = "queue-item";
    div.innerHTML = `<span class="queue-badge ${i.status}">${i.status}</span>
      <span class="title">${i.series} · ${chap}</span>`;
    if (i.status === "failed") {
      const r = document.createElement("button");
      r.className = "btn"; r.textContent = "Re-tentar";
      r.addEventListener("click", () => api().retry_item(i.id).then(loadQueue));
      div.appendChild(r);
    }
    if (i.status === "queued" || i.status === "downloading") {
      const c = document.createElement("button");
      c.className = "btn warn"; c.textContent = "Cancelar";
      c.addEventListener("click", () => api().cancel_item(i.id).then(loadQueue));
      div.appendChild(c);
    }
    const rm = document.createElement("button");
    rm.className = "btn"; rm.textContent = "×";
    rm.addEventListener("click", () => api().remove_item(i.id).then(loadQueue));
    div.appendChild(rm);
    box.appendChild(div);
  });
}

let queuePaused = false;
document.getElementById("btn-queue-pause").addEventListener("click", async () => {
  queuePaused = !queuePaused;
  await (queuePaused ? api().pause_queue() : api().resume_queue());
  document.getElementById("btn-queue-pause").textContent = queuePaused ? "Retomar fila" : "Pausar fila";
  loadQueue();
});
document.getElementById("btn-queue-clear").addEventListener("click", () =>
  api().clear_finished().then(loadQueue));
```

(c) Call `loadQueue()` when navigating to Downloads (in the nav handler, add `if (btn.dataset.view === "downloads") loadQueue();`) and once inside the `pywebviewready` handler.

- [ ] **Step 6: Verify + run tests**

Run: `node --check frontend/app.js`
Expected: válido.
Run: `py -3.13 -m pytest tests/test_frontend_queue.py tests/test_frontend_chapters.py tests/test_app_entry.py -v`
Expected: passam.

- [ ] **Step 7: Commit**

```bash
git add frontend/index.html frontend/app.js frontend/styles.css tests/test_frontend_queue.py
git commit -m "feat: aba Downloads como gerenciador de fila (estado por item + ações)"
```

---

## Verificação final (após todas as tasks)

- [ ] `py -3.13 -m pytest -q` — suíte inteira verde.
- [ ] `node --check frontend/app.js` — válido.
- [ ] Verificação manual (humano) em `py -3.13 desktop.py`: buscar → seletor → "Baixar" enfileira; a aba Downloads mostra a fila drenando item a item, com estado por item; pausar/retomar; cancelar/re-tentar/remover um item; fechar e reabrir o app e ver a fila persistida.
