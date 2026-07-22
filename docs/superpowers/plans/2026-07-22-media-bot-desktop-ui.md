# Media Bot Desktop UI (pywebview) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir a GUI Tkinter por uma interface desktop web (pywebview) moderna sobre o núcleo `MediaBot`, com dashboard, biblioteca visual, enriquecimento de metadados e exportação Komga, entregue como `dist/MediaBot.exe`.

**Architecture:** Uma janela pywebview carrega um SPA local (HTML/CSS/JS, sem CDN). A ponte JS↔Python é uma classe `Api`. Todas as operações do bot passam por um `BotService` com **um único worker serial** (fila), garantindo que a Session SQLite global nunca seja acessada por duas threads. Operações longas (busca/download) são assíncronas e empurram eventos ao JS; leituras rápidas (biblioteca/dashboard/status) rodam de forma síncrona no worker e retornam direto ao JS.

**Tech Stack:** Python 3.13, pywebview, SQLAlchemy/SQLite (existente), requests (existente), pytest, PyInstaller.

## Global Constraints

- **Interpretador:** o `python` no PATH está quebrado (trampoline uv). Use SEMPRE `py -3.13` para rodar Python/pytest. Ex.: `py -3.13 -m pytest`.
- **Frontend sem CDN:** todo CSS/JS/asset é local (requisito de empacotamento offline). Nada de `<script src="https://...">` ou fontes remotas.
- **Núcleo estável:** não quebrar a API pública de `MediaBot` já usada pela CLI e por `tests/test_core.py`. Adições são permitidas; mudanças de assinatura existentes não.
- **Concorrência:** nenhum acesso ao `db_manager`/`LibraryManager` fora do worker do `BotService`.
- **Dependências novas:** `pywebview>=5.0` (runtime) e `pyinstaller>=6.0` (build) em `requirements.txt`.
- **Idioma:** toda copy visível ao usuário em pt-br.
- **Paleta:** tema escuro slate/blue — base `#0f172a`, superfícies `#111827`/`#1f2937`, acento `#2563eb`, texto `#e5e7eb`.

---

### Task 1: Scaffolding + `BotService` (worker serial)

**Files:**
- Create: `app/__init__.py`
- Create: `conftest.py` (raiz — ancora o rootdir do pytest para importar o pacote `app`)
- Create: `app/bot_service.py`
- Test: `tests/test_bot_service.py`

**Interfaces:**
- Consumes: nada (base do projeto).
- Produces:
  - `class BotService(bot_factory: Callable[[], Any], event_sink: Callable[[str, dict], None])`
  - `BotService.start() -> None` (inicia a thread worker)
  - `BotService.stop() -> None` (encerra o worker; fecha o bot se tiver `.cleanup()`)
  - `BotService.submit(label: str, fn: Callable[[Any, Callable[[str, dict], None]], Any]) -> str` (assíncrono; `fn(bot, emit)`; retorna `job_id`)
  - `BotService.run_sync(label: str, fn: Callable[[Any, Callable[[str, dict], None]], Any], timeout: float = 120) -> Any` (roda no worker e retorna o resultado; propaga exceção)
  - `BotService.cancel(job_id: str) -> None`
  - `BotService.is_cancelled(job_id: str) -> bool`
  - Eventos emitidos via `event_sink(name, payload)`: `job_started`, `log`, `progress`, `job_done`, `job_error` (todos com `job_id`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_bot_service.py`:

```python
import threading
import time

from app.bot_service import BotService


class FakeBot:
    def __init__(self):
        self.cleaned_up = False

    def cleanup(self):
        self.cleaned_up = True


def make_service(events):
    return BotService(bot_factory=FakeBot, event_sink=lambda name, payload: events.append((name, payload)))


def test_run_sync_returns_result_and_uses_bot():
    events = []
    service = make_service(events)
    service.start()
    try:
        result = service.run_sync("read", lambda bot, emit: isinstance(bot, FakeBot))
        assert result is True
    finally:
        service.stop()


def test_jobs_never_overlap():
    events = []
    service = make_service(events)
    service.start()
    active = {"count": 0, "max": 0}
    lock = threading.Lock()

    def slow(bot, emit):
        with lock:
            active["count"] += 1
            active["max"] = max(active["max"], active["count"])
        time.sleep(0.02)
        with lock:
            active["count"] -= 1
        return "ok"

    try:
        ids = [service.submit(f"job{i}", slow) for i in range(5)]
        deadline = time.time() + 5
        done = set()
        while len(done) < 5 and time.time() < deadline:
            for name, payload in list(events):
                if name == "job_done":
                    done.add(payload["job_id"])
            time.sleep(0.01)
        assert done == set(ids)
        assert active["max"] == 1  # nunca dois jobs simultâneos
    finally:
        service.stop()


def test_error_emits_job_error():
    events = []
    service = make_service(events)
    service.start()

    def boom(bot, emit):
        raise ValueError("falhou")

    try:
        service.submit("bad", boom)
        deadline = time.time() + 5
        while time.time() < deadline:
            if any(n == "job_error" for n, _ in events):
                break
            time.sleep(0.01)
        errors = [p for n, p in events if n == "job_error"]
        assert errors and "falhou" in errors[0]["error"]
    finally:
        service.stop()


def test_cancel_marks_job():
    events = []
    service = make_service(events)
    service.start()
    try:
        job_id = service.submit("long", lambda bot, emit: time.sleep(0.05))
        service.cancel(job_id)
        assert service.is_cancelled(job_id) is True
    finally:
        service.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_bot_service.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.bot_service'`.

- [ ] **Step 3: Create the package and rootdir anchor**

Create `app/__init__.py`:

```python
"""Camada de aplicação da GUI desktop do Media Bot."""
```

Create `conftest.py` (raiz do repositório):

```python
import sys
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

- [ ] **Step 4: Implement `BotService`**

Create `app/bot_service.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.13 -m pytest tests/test_bot_service.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add app/__init__.py app/bot_service.py conftest.py tests/test_bot_service.py
git commit -m "feat: BotService com worker serial para operações do bot"
```

---

### Task 2: Métodos de dados no `MediaBot` + cancelamento cooperativo

Adiciona métodos que retornam **dados estruturados** (a UI precisa de JSON, não de `print`) e um `should_cancel` opcional no download.

**Files:**
- Modify: `media_bot.py` (adicionar métodos e um parâmetro; não alterar assinaturas existentes)
- Test: `tests/test_media_bot_data.py`

**Interfaces:**
- Consumes: `LibraryManager`, `CacheManager` (existentes).
- Produces:
  - `MediaBot.get_library_data() -> List[Dict]` — cada item: `{title, status, completion_percentage, chapters_downloaded, total_chapters_registered, is_complete}`
  - `MediaBot.get_series_status_data(title: str) -> Dict` — mesmo dict de `get_series_progress`.
  - `MediaBot.dashboard_stats() -> Dict` — `{total_series, total_downloaded, complete_collections, missing_total, by_format: dict, by_source: dict}`
  - `MediaBot.download_complete_series(..., should_cancel: Optional[Callable[[], bool]] = None)` — verifica antes de cada capítulo e interrompe se `True`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_media_bot_data.py`:

```python
import tempfile
from pathlib import Path

from media_bot import MediaBot


def make_bot():
    return MediaBot(base_download_dir=str(Path(tempfile.mkdtemp()) / "dl"))


def test_get_library_data_returns_list_of_dicts():
    bot = make_bot()
    try:
        data = bot.get_library_data()
        assert isinstance(data, list)
        for item in data:
            assert "title" in item
            assert "completion_percentage" in item
            assert "is_complete" in item
    finally:
        bot.cleanup()


def test_dashboard_stats_has_expected_keys():
    bot = make_bot()
    try:
        stats = bot.dashboard_stats()
        for key in ["total_series", "total_downloaded", "complete_collections",
                    "missing_total", "by_format", "by_source"]:
            assert key in stats
        assert isinstance(stats["by_format"], dict)
        assert isinstance(stats["by_source"], dict)
    finally:
        bot.cleanup()


def test_get_series_status_data_returns_progress_dict():
    bot = make_bot()
    try:
        status = bot.get_series_status_data("Serie Inexistente XYZ")
        assert "completion_percentage" in status
        assert "title" in status
    finally:
        bot.cleanup()


def test_download_stops_when_should_cancel_true(monkeypatch):
    bot = make_bot()
    try:
        # Força uma lista de capítulos disponíveis sem tocar a rede.
        monkeypatch.setattr(bot, "get_complete_series_chapters", lambda *a, **k: [1.0, 2.0, 3.0])
        monkeypatch.setattr(bot, "_resolve_series_reference", lambda *a, **k: "ref")
        calls = {"n": 0}

        def fake_get_chapter_url(ref, num):
            calls["n"] += 1
            return {"download_url": "http://x/f.cbz", "format": "cbz"}

        scraper = bot._resolve_scraper("mangadex")
        monkeypatch.setattr(scraper, "get_chapter_url", fake_get_chapter_url)
        bot.download_complete_series("Serie", source_name="mangadex",
                                     should_cancel=lambda: True)
        assert calls["n"] == 0  # cancelado antes do primeiro capítulo
    finally:
        bot.cleanup()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_media_bot_data.py -v`
Expected: FAIL com `AttributeError: 'MediaBot' object has no attribute 'get_library_data'`.

- [ ] **Step 3: Implement the data methods**

In `media_bot.py`, add these methods to the `MediaBot` class (após `list_library`, antes de `cleanup`):

```python
    def get_library_data(self) -> List[Dict[str, Any]]:
        """Retorna dados estruturados de todas as séries (para a UI)."""
        data = []
        for series in self.library.list_all_series():
            progress = self.library.get_series_progress(series)
            data.append({
                'title': progress['title'],
                'status': progress['status'],
                'completion_percentage': progress['completion_percentage'],
                'chapters_downloaded': progress['chapters_downloaded'],
                'total_chapters_registered': progress['total_chapters_registered'],
                'is_complete': progress['is_complete'],
                'source_name': series.source_name,
            })
        return data

    def get_series_status_data(self, series_title: str) -> Dict[str, Any]:
        """Retorna o progresso de uma coleção como dict (para a UI)."""
        series = self.library.get_or_create_series(series_title)
        return self.library.get_series_progress(series)

    def dashboard_stats(self) -> Dict[str, Any]:
        """Agrega estatísticas da biblioteca para o dashboard."""
        from collections import defaultdict
        from database import MediaFile

        series_list = self.library.list_all_series()
        total_downloaded = 0
        complete = 0
        missing_total = 0
        by_source: Dict[str, int] = defaultdict(int)

        for series in series_list:
            progress = self.library.get_series_progress(series)
            total_downloaded += progress['chapters_downloaded']
            missing_total += len(progress['missing_chapters'])
            if progress['is_complete']:
                complete += 1
            by_source[series.source_name or 'desconhecido'] += 1

        by_format: Dict[str, int] = defaultdict(int)
        session = self.library.session
        for media_file in session.query(MediaFile).all():
            by_format[media_file.file_format or 'desconhecido'] += 1

        return {
            'total_series': len(series_list),
            'total_downloaded': total_downloaded,
            'complete_collections': complete,
            'missing_total': missing_total,
            'by_format': dict(by_format),
            'by_source': dict(by_source),
        }
```

- [ ] **Step 4: Add the `should_cancel` parameter**

In `media_bot.py`, change the signature of `download_complete_series`:

```python
    def download_complete_series(self, series_title: str, media_type: str = "manga",
                                 source_name: str = "mangadex", skip_existing: bool = True,
                                 progress_callback: Optional[Any] = None,
                                 should_cancel: Optional[Any] = None):
```

Then, inside the `for chapter_num in missing_chapters:` loop, add the check as the **first** statement of the loop body (immediately after the `for` line, before `chapter_label = ...`):

```python
                if should_cancel is not None and should_cancel():
                    print("   ⏹️  Download cancelado pelo usuário.")
                    break
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.13 -m pytest tests/test_media_bot_data.py tests/test_core.py -v`
Expected: todos passam (inclui regressão do `test_core.py`).

- [ ] **Step 6: Commit**

```bash
git add media_bot.py tests/test_media_bot_data.py
git commit -m "feat: métodos de dados no MediaBot e cancelamento cooperativo"
```

---

### Task 3: `MetadataEnricher` (Jikan + fallback AniList)

**Files:**
- Create: `app/metadata_enricher.py`
- Test: `tests/test_metadata_enricher.py`

**Interfaces:**
- Consumes: `CacheManager` (de `cache_manager.py`), `requests`.
- Produces:
  - `class MetadataEnricher(cache: Optional[CacheManager] = None, session=None)`
  - `MetadataEnricher.enrich(title: str) -> Optional[Dict]` — retorna `{title, alternative_titles, status, chapters, volumes, score, synopsis, cover_image}` ou `None`. Usa cache (TTL 7 dias) e degrada a `None` em qualquer erro de rede.

- [ ] **Step 1: Write the failing test**

Create `tests/test_metadata_enricher.py`:

```python
import tempfile

from cache_manager import CacheManager
from app.metadata_enricher import MetadataEnricher


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, get_map=None, post_result=None):
        self.get_map = get_map or {}
        self.post_result = post_result
        self.get_calls = []
        self.post_calls = []

    def get(self, url, params=None, timeout=None):
        self.get_calls.append((url, params))
        return self.get_map.get("default", FakeResponse({"data": []}))

    def post(self, url, json=None, timeout=None):
        self.post_calls.append((url, json))
        return self.post_result


JIKAN_OK = {
    "data": [{
        "title": "Dandadan",
        "titles": [{"title": "ダンダダン"}],
        "status": "Publishing",
        "chapters": 120,
        "volumes": 12,
        "score": 8.6,
        "synopsis": "Uma história sobre fantasmas e aliens.",
        "images": {"jpg": {"large_image_url": "http://img/dandadan.jpg"}},
    }]
}


def test_enrich_uses_jikan_first():
    session = FakeSession(get_map={"default": FakeResponse(JIKAN_OK)})
    with tempfile.TemporaryDirectory() as tmp:
        enricher = MetadataEnricher(cache=CacheManager(tmp), session=session)
        result = enricher.enrich("Dandadan")
    assert result is not None
    assert result["title"] == "Dandadan"
    assert result["chapters"] == 120
    assert result["cover_image"] == "http://img/dandadan.jpg"


def test_enrich_caches_result():
    session = FakeSession(get_map={"default": FakeResponse(JIKAN_OK)})
    with tempfile.TemporaryDirectory() as tmp:
        cache = CacheManager(tmp)
        enricher = MetadataEnricher(cache=cache, session=session)
        enricher.enrich("Dandadan")
        first_calls = len(session.get_calls)
        enricher.enrich("Dandadan")  # deve vir do cache
        assert len(session.get_calls) == first_calls


def test_enrich_returns_none_on_network_error():
    class BrokenSession:
        def get(self, *a, **k):
            raise ConnectionError("sem rede")

        def post(self, *a, **k):
            raise ConnectionError("sem rede")

    with tempfile.TemporaryDirectory() as tmp:
        enricher = MetadataEnricher(cache=CacheManager(tmp), session=BrokenSession())
        assert enricher.enrich("Qualquer") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_metadata_enricher.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.metadata_enricher'`.

- [ ] **Step 3: Implement `MetadataEnricher`**

Create `app/metadata_enricher.py`:

```python
"""Enriquecimento de metadados via Jikan (MyAnimeList) com fallback AniList.

Não requer API key. Degrada graciosamente a None em qualquer erro de rede.
Resultados são cacheados por 7 dias via CacheManager.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import requests

from cache_manager import CacheManager

_JIKAN_URL = "https://api.jikan.moe/v4/manga"
_ANILIST_URL = "https://graphql.anilist.co"
_TTL_SECONDS = 7 * 24 * 3600
_TIMEOUT = 10

_ANILIST_QUERY = """
query ($search: String) {
  Media(search: $search, type: MANGA) {
    title { romaji english native }
    status
    chapters
    volumes
    averageScore
    description(asHtml: false)
    coverImage { large }
  }
}
"""


class MetadataEnricher:
    def __init__(self, cache: Optional[CacheManager] = None, session=None):
        self.cache = cache or CacheManager()
        self.session = session or requests.Session()

    def enrich(self, title: str) -> Optional[Dict[str, Any]]:
        key = f"enrich::{title.strip().lower()}"
        cached = self.cache.get(key, max_age_seconds=_TTL_SECONDS)
        if cached is not None:
            return cached

        result = self._from_jikan(title) or self._from_anilist(title)
        if result is not None:
            self.cache.set(key, result)
        return result

    def _from_jikan(self, title: str) -> Optional[Dict[str, Any]]:
        try:
            response = self.session.get(_JIKAN_URL, params={"q": title, "limit": 1}, timeout=_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return None

        data = payload.get("data") or []
        if not data:
            return None
        manga = data[0]
        return {
            "title": manga.get("title"),
            "alternative_titles": [t.get("title") for t in manga.get("titles", []) if t.get("title")],
            "status": manga.get("status"),
            "chapters": manga.get("chapters"),
            "volumes": manga.get("volumes"),
            "score": manga.get("score"),
            "synopsis": manga.get("synopsis"),
            "cover_image": (manga.get("images", {}).get("jpg", {}) or {}).get("large_image_url"),
        }

    def _from_anilist(self, title: str) -> Optional[Dict[str, Any]]:
        try:
            response = self.session.post(
                _ANILIST_URL,
                json={"query": _ANILIST_QUERY, "variables": {"search": title}},
                timeout=_TIMEOUT,
            )
            response.raise_for_status()
            media = (response.json().get("data") or {}).get("Media")
        except Exception:
            return None

        if not media:
            return None
        titles = media.get("title", {}) or {}
        return {
            "title": titles.get("romaji") or titles.get("english") or title,
            "alternative_titles": [v for v in (titles.get("english"), titles.get("native")) if v],
            "status": media.get("status"),
            "chapters": media.get("chapters"),
            "volumes": media.get("volumes"),
            "score": media.get("averageScore"),
            "synopsis": media.get("description"),
            "cover_image": (media.get("coverImage", {}) or {}).get("large"),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.13 -m pytest tests/test_metadata_enricher.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/metadata_enricher.py tests/test_metadata_enricher.py
git commit -m "feat: MetadataEnricher com Jikan e fallback AniList"
```

---

### Task 4: `KomgaExporter`

**Files:**
- Create: `app/komga_exporter.py`
- Test: `tests/test_komga_exporter.py`

**Interfaces:**
- Consumes: `LibraryManager` (para achar arquivos da série via DB) e `shutil`/`pathlib`.
- Produces:
  - `class KomgaExporter(library: LibraryManager, export_root: str = "./exports/komga")`
  - `KomgaExporter.export_series(title: str) -> Dict` — retorna `{base_path, exported, skipped}`. Cria `export_root/<série sanitizada>/<Volume NNN | Chapter NNN>/<arquivo>`. Copia (não move). Idempotente.
  - `KomgaExporter.sanitize(name: str) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_komga_exporter.py`:

```python
from pathlib import Path

from app.komga_exporter import KomgaExporter


class FakeFile:
    def __init__(self, file_path, file_format="cbz"):
        self.file_path = file_path
        self.file_format = file_format
        self.download_status = "completed"


class FakeChapter:
    def __init__(self, chapter_number, files, volume_number=1.0):
        self.chapter_number = chapter_number
        self.files = files
        self.volume_number = volume_number


class FakeLibrary:
    """Simula o mínimo que o exporter consome."""
    def __init__(self, chapters):
        self._chapters = chapters

    def get_or_create_series(self, title, *a, **k):
        return type("S", (), {"title": title})()

    def iter_downloaded_files(self, series):
        # (volume_number, chapter_number, file_path, file_format)
        for chap in self._chapters:
            for f in chap.files:
                yield (chap.volume_number, chap.chapter_number, f.file_path, f.file_format)


def make_source_file(tmp_path, name):
    p = tmp_path / name
    p.write_bytes(b"conteudo")
    return str(p)


def test_export_creates_komga_layout(tmp_path):
    src = make_source_file(tmp_path, "cap1.cbz")
    library = FakeLibrary([FakeChapter(1.0, [FakeFile(src)])])
    exporter = KomgaExporter(library=library, export_root=str(tmp_path / "out"))

    result = exporter.export_series("Dandadan")

    exported = Path(result["base_path"]) / "Chapter 001" / "cap1.cbz"
    assert exported.exists()
    assert result["exported"] == 1


def test_export_is_idempotent(tmp_path):
    src = make_source_file(tmp_path, "cap1.cbz")
    library = FakeLibrary([FakeChapter(1.0, [FakeFile(src)])])
    exporter = KomgaExporter(library=library, export_root=str(tmp_path / "out"))

    exporter.export_series("Dandadan")
    result = exporter.export_series("Dandadan")  # segunda vez pula
    assert result["skipped"] == 1
    assert result["exported"] == 0


def test_sanitize_removes_invalid_chars(tmp_path):
    exporter = KomgaExporter(library=FakeLibrary([]), export_root=str(tmp_path))
    assert exporter.sanitize('a/b:c*?"<>|') == "a_b_c"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_komga_exporter.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.komga_exporter'`.

- [ ] **Step 3: Add `iter_downloaded_files` to `LibraryManager`**

In `library_manager.py`, add this method to the `LibraryManager` class (after `list_all_series`):

```python
    def iter_downloaded_files(self, series):
        """Itera (volume_number, chapter_number, file_path, file_format) dos arquivos baixados."""
        volumes = self.session.query(Volume).filter(Volume.series_id == series.id).all()
        for vol in volumes:
            chapters = self.session.query(Chapter).filter(Chapter.volume_id == vol.id).all()
            for chap in chapters:
                files = self.session.query(MediaFile).filter(
                    MediaFile.chapter_id == chap.id,
                    MediaFile.download_status == 'completed'
                ).all()
                for media_file in files:
                    yield (vol.volume_number, chap.chapter_number,
                           media_file.file_path, media_file.file_format)
```

- [ ] **Step 4: Implement `KomgaExporter`**

Create `app/komga_exporter.py`:

```python
"""Exporta a coleção baixada para o layout esperado por Komga/Kavita.

Estrutura: <export_root>/<série>/<Chapter NNN>/<arquivo>. Copia (não move) e
é idempotente — arquivos já presentes no destino são pulados.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Dict


class KomgaExporter:
    def __init__(self, library: Any, export_root: str = "./exports/komga"):
        self.library = library
        self.export_root = Path(export_root)

    @staticmethod
    def sanitize(name: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*]+', "_", name)
        return cleaned.strip().strip(".")

    def export_series(self, title: str) -> Dict[str, Any]:
        series = self.library.get_or_create_series(title)
        base_path = self.export_root / self.sanitize(series.title)
        base_path.mkdir(parents=True, exist_ok=True)

        exported = 0
        skipped = 0
        for volume_number, chapter_number, file_path, _fmt in self.library.iter_downloaded_files(series):
            source = Path(file_path)
            if not source.exists():
                skipped += 1
                continue

            if chapter_number is not None:
                folder = f"Chapter {int(chapter_number):03d}"
            elif volume_number is not None:
                folder = f"Volume {int(volume_number):03d}"
            else:
                folder = "Outros"

            target_dir = base_path / folder
            target_dir.mkdir(parents=True, exist_ok=True)
            destination = target_dir / source.name

            if destination.exists():
                skipped += 1
                continue

            shutil.copy(source, destination)
            exported += 1

        return {"base_path": str(base_path), "exported": exported, "skipped": skipped}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.13 -m pytest tests/test_komga_exporter.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add app/komga_exporter.py library_manager.py tests/test_komga_exporter.py
git commit -m "feat: KomgaExporter e iteração de arquivos baixados"
```

---

### Task 5: `Api` (fachada da ponte JS↔Python)

**Files:**
- Create: `app/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `BotService`, `MediaBot`, `MetadataEnricher`, `KomgaExporter`.
- Produces:
  - `class Api(service: BotService)`
  - `Api.set_window(window) -> None` (guarda a janela pywebview para empurrar eventos)
  - Métodos assíncronos (retornam `{'job_id': str}`): `search(query, media_type)`, `download_series(series, media_type, source)`
  - Métodos síncronos (retornam dados): `library()`, `dashboard_stats()`, `series_status(series)`, `graph_status()`, `clear_cache()`, `enrich_metadata(title)`, `export_komga(series)`
  - `Api.cancel_job(job_id)` → `{'cancelled': True}`
  - `Api.emit_event(name, payload)` — usado como `event_sink` do `BotService`; empurra ao JS via `window.evaluate_js` quando há janela.

- [ ] **Step 1: Write the failing test**

Create `tests/test_api.py`:

```python
from app.api import Api
from app.bot_service import BotService


class FakeBot:
    def search_series(self, query, media_type="manga"):
        return [{"title": query, "source": "mangadex", "format_type": "cbz", "url": "http://x"}]

    def get_library_data(self):
        return [{"title": "Dandadan", "completion_percentage": 50.0, "is_complete": False}]

    def dashboard_stats(self):
        return {"total_series": 1, "total_downloaded": 3, "complete_collections": 0,
                "missing_total": 2, "by_format": {"cbz": 3}, "by_source": {"mangadex": 1}}

    def clear_cache(self):
        return 4

    def cleanup(self):
        pass


def make_api(events):
    service = BotService(bot_factory=FakeBot, event_sink=lambda n, p: events.append((n, p)))
    api = Api(service)
    service.start()
    return api, service


def test_library_returns_data_sync():
    events = []
    api, service = make_api(events)
    try:
        data = api.library()
        assert data[0]["title"] == "Dandadan"
    finally:
        service.stop()


def test_dashboard_stats_sync():
    events = []
    api, service = make_api(events)
    try:
        stats = api.dashboard_stats()
        assert stats["total_series"] == 1
        assert stats["by_format"] == {"cbz": 3}
    finally:
        service.stop()


def test_search_is_async_and_emits_results():
    import time
    events = []
    api, service = make_api(events)
    try:
        ack = api.search("Dandadan", "manga")
        assert "job_id" in ack
        deadline = time.time() + 5
        while time.time() < deadline:
            if any(n == "search_results" for n, _ in events):
                break
            time.sleep(0.01)
        payloads = [p for n, p in events if n == "search_results"]
        assert payloads and payloads[0]["results"][0]["title"] == "Dandadan"
    finally:
        service.stop()


def test_clear_cache_sync():
    events = []
    api, service = make_api(events)
    try:
        assert api.clear_cache() == {"removed": 4}
    finally:
        service.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_api.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.api'`.

- [ ] **Step 3: Implement `Api`**

Create `app/api.py`:

```python
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
                        source: str = "mangadex") -> Dict[str, str]:
        job_holder: Dict[str, Optional[str]] = {"id": None}

        def fn(bot, emit):
            def progress(label, current, total):
                emit("progress", {"label": label, "current": current, "total": total})
            bot.download_complete_series(
                series, media_type=media_type, source_name=source,
                progress_callback=progress,
                should_cancel=lambda: self._service.is_cancelled(job_holder["id"]),
            )
            return {"done": True}

        job_id = self._service.submit(f"Download: {series}", fn)
        job_holder["id"] = job_id
        return {"job_id": job_id}

    # --- síncronos ---
    def library(self) -> Any:
        return self._service.run_sync("library", lambda bot, emit: bot.get_library_data())

    def dashboard_stats(self) -> Any:
        return self._service.run_sync("dashboard", lambda bot, emit: bot.dashboard_stats())

    def series_status(self, series: str) -> Any:
        return self._service.run_sync("status", lambda bot, emit: bot.get_series_status_data(series))

    def graph_status(self) -> Any:
        def fn(bot, emit):
            bot.print_graph_status()  # log vai por evento
            return {"ok": True}
        return {"job_id": self._service.submit("Status do grafo", fn)}

    def clear_cache(self) -> Dict[str, int]:
        removed = self._service.run_sync("cache-clear", lambda bot, emit: bot.clear_cache())
        return {"removed": removed}

    def enrich_metadata(self, title: str) -> Any:
        def fn(bot, emit):
            enricher = MetadataEnricher(cache=bot.cache)
            return enricher.enrich(title)
        return self._service.run_sync("enrich", fn)

    def export_komga(self, series: str) -> Any:
        def fn(bot, emit):
            exporter = KomgaExporter(library=bot.library)
            return exporter.export_series(series)
        return self._service.run_sync("export", fn)

    def cancel_job(self, job_id: str) -> Dict[str, bool]:
        self._service.cancel(job_id)
        return {"cancelled": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.13 -m pytest tests/test_api.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/api.py tests/test_api.py
git commit -m "feat: fachada Api da ponte JS-Python"
```

---

### Task 6: Entrypoint `app.py` + esqueleto do frontend (janela + ponte + log/progresso ao vivo)

Instala pywebview, cria a janela e um frontend mínimo que já prova a ponte: uma aba de log recebendo eventos ao vivo e o botão de busca funcionando. Verificação é manual (GUI).

**Files:**
- Create: `app.py`
- Create: `frontend/index.html`
- Create: `frontend/styles.css`
- Create: `frontend/app.js`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: `Api`, `BotService`, `MediaBot`.
- Produces: janela pywebview funcional; `window.pushEvent(name, payload)` no JS; `window.pywebview.api.*` acessível.

- [ ] **Step 1: Install pywebview**

Run: `py -3.13 -m pip install "pywebview>=5.0"`
Expected: `Successfully installed pywebview-...`

- [ ] **Step 2: Add dependency to requirements**

In `requirements.txt`, after the `tqdm>=4.66.0` block, add:

```
# Interface desktop (GUI web local)
pywebview>=5.0

# Build do executável (somente para gerar o .exe)
pyinstaller>=6.0
```

- [ ] **Step 3: Create `app.py`**

Create `app.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entrypoint da interface desktop do Media Bot (pywebview)."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import webview
except ImportError:  # pragma: no cover
    print("pywebview não está instalado. Rode: py -3.13 -m pip install pywebview")
    raise SystemExit(1)

from app.api import Api
from app.bot_service import BotService
from media_bot import MediaBot


def frontend_dir() -> Path:
    """Resolve a pasta frontend/ em dev e dentro do bundle PyInstaller."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "frontend"
    return Path(__file__).parent / "frontend"


def main() -> None:
    service = BotService(bot_factory=MediaBot, event_sink=lambda n, p: api.emit_event(n, p))
    api = Api(service)
    service.start()

    index = frontend_dir() / "index.html"
    window = webview.create_window(
        "Media Bot PT-BR",
        url=str(index),
        js_api=api,
        width=1240,
        height=820,
        min_size=(1000, 680),
        background_color="#0f172a",
    )
    api.set_window(window)

    try:
        webview.start()
    finally:
        service.stop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create `frontend/index.html`**

Create `frontend/index.html`:

```html
<!DOCTYPE html>
<html lang="pt-br">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Media Bot PT-BR</title>
  <link rel="stylesheet" href="styles.css" />
</head>
<body>
  <div id="app">
    <aside class="sidebar">
      <div class="brand">📚 Media Bot</div>
      <nav>
        <button class="nav-item active" data-view="dashboard">Dashboard</button>
        <button class="nav-item" data-view="search">Buscar</button>
        <button class="nav-item" data-view="library">Biblioteca</button>
        <button class="nav-item" data-view="downloads">Downloads</button>
        <button class="nav-item" data-view="tools">Ferramentas</button>
      </nav>
      <div class="sidebar-foot" id="conn-state">Conectando…</div>
    </aside>
    <main class="content">
      <section id="view-dashboard" class="view active"><h1>Dashboard</h1><div id="dash-cards" class="card-grid"></div></section>
      <section id="view-search" class="view">
        <h1>Buscar</h1>
        <div class="form-row">
          <input id="q" placeholder="Título da série" value="Dandadan" />
          <select id="media-type"><option>manga</option><option>livro</option><option>hq</option><option>manhwa</option><option>artigo</option></select>
          <button id="btn-search" class="btn accent">Buscar</button>
        </div>
        <div id="search-results" class="card-grid"></div>
      </section>
      <section id="view-library" class="view"><h1>Biblioteca</h1><div id="library-cards" class="card-grid"></div></section>
      <section id="view-downloads" class="view">
        <h1>Downloads</h1>
        <div class="progress"><div id="progress-bar" class="progress-bar"></div></div>
        <div id="progress-text" class="muted">Sem download em andamento.</div>
        <pre id="log" class="log"></pre>
      </section>
      <section id="view-tools" class="view">
        <h1>Ferramentas</h1>
        <div class="form-row">
          <button id="btn-cache" class="btn warn">Limpar cache</button>
          <button id="btn-graph" class="btn">Status do grafo</button>
        </div>
      </section>
    </main>
  </div>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 5: Create `frontend/styles.css`**

Create `frontend/styles.css`:

```css
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body { font-family: "Segoe UI", system-ui, sans-serif; background: #0f172a; color: #e5e7eb; }
#app { display: flex; height: 100vh; }
.sidebar { width: 220px; background: #111827; display: flex; flex-direction: column; padding: 16px 12px; gap: 6px; }
.brand { font-size: 18px; font-weight: 700; color: #f8fafc; padding: 8px 10px 16px; }
.nav-item { text-align: left; background: transparent; border: 0; color: #cbd5e1; padding: 10px 12px; border-radius: 8px; cursor: pointer; font-size: 14px; }
.nav-item:hover { background: #1f2937; }
.nav-item.active { background: #1d4ed8; color: #fff; }
.sidebar-foot { margin-top: auto; font-size: 12px; color: #64748b; padding: 8px 10px; }
.content { flex: 1; overflow-y: auto; padding: 28px 32px; }
h1 { font-size: 22px; margin: 0 0 20px; color: #f8fafc; }
.view { display: none; }
.view.active { display: block; }
.form-row { display: flex; gap: 10px; margin-bottom: 20px; align-items: center; flex-wrap: wrap; }
input, select { background: #0b1220; border: 1px solid #1f2937; color: #e5e7eb; padding: 10px 12px; border-radius: 8px; font-size: 14px; }
input { flex: 1; min-width: 220px; }
.btn { background: #1f2937; border: 0; color: #e5e7eb; padding: 10px 16px; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 14px; }
.btn:hover { filter: brightness(1.15); }
.btn.accent { background: #2563eb; color: #fff; }
.btn.warn { background: #92400e; color: #fff; }
.btn.success { background: #0f766e; color: #fff; }
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 16px; }
.card { background: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 16px; }
.card h3 { margin: 0 0 6px; font-size: 15px; color: #f8fafc; }
.card .muted { font-size: 13px; color: #94a3b8; }
.card .cover { width: 100%; height: 150px; object-fit: cover; border-radius: 8px; background: #0b1220; margin-bottom: 10px; }
.stat { font-size: 28px; font-weight: 700; color: #60a5fa; }
.progress { background: #0b1220; border-radius: 999px; height: 12px; overflow: hidden; margin-bottom: 8px; }
.progress-bar { height: 100%; width: 0; background: #2563eb; transition: width .2s; }
.log { background: #0b1220; border-radius: 10px; padding: 14px; height: 320px; overflow-y: auto; font-family: Consolas, monospace; font-size: 12.5px; white-space: pre-wrap; color: #cbd5e1; }
.muted { color: #94a3b8; font-size: 13px; }
```

- [ ] **Step 6: Create `frontend/app.js`**

Create `frontend/app.js`:

```javascript
"use strict";

// --- ponte de eventos empurrados pelo Python ---
window.pushEvent = function (name, payload) {
  const handlers = window._handlers[name] || [];
  handlers.forEach((h) => h(payload));
};
window._handlers = {};
function on(name, fn) {
  (window._handlers[name] = window._handlers[name] || []).push(fn);
}

function api() {
  return window.pywebview && window.pywebview.api;
}

// --- navegação ---
document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("view-" + btn.dataset.view).classList.add("active");
    if (btn.dataset.view === "library") loadLibrary();
    if (btn.dataset.view === "dashboard") loadDashboard();
  });
});

// --- log ao vivo ---
const logEl = () => document.getElementById("log");
on("log", (p) => {
  const el = logEl();
  el.textContent += p.line + "\n";
  el.scrollTop = el.scrollHeight;
});
on("job_started", (p) => { logEl().textContent += `\n=== ${p.label} ===\n`; });
on("job_error", (p) => { logEl().textContent += `❌ Erro: ${p.error}\n`; });

// --- progresso ---
on("progress", (p) => {
  const pct = p.total ? Math.round((p.current / p.total) * 100) : 0;
  document.getElementById("progress-bar").style.width = pct + "%";
  document.getElementById("progress-text").textContent = `${p.label}: ${p.current}/${p.total} (${pct}%)`;
});

// --- busca ---
document.getElementById("btn-search").addEventListener("click", async () => {
  const q = document.getElementById("q").value.trim();
  const mt = document.getElementById("media-type").value;
  if (!q) return;
  document.getElementById("search-results").innerHTML = '<p class="muted">Buscando…</p>';
  await api().search(q, mt);
});
on("search_results", (p) => {
  const box = document.getElementById("search-results");
  if (!p.results.length) { box.innerHTML = '<p class="muted">Nenhum resultado.</p>'; return; }
  box.innerHTML = "";
  p.results.forEach((r) => {
    const div = document.createElement("div");
    div.className = "card";
    div.innerHTML = `<h3>${r.title || r.series_name || "Sem título"}</h3>
      <p class="muted">${r.source || "?"} · ${r.format_type || r.format || "?"}</p>
      <button class="btn success">Baixar série</button>`;
    div.querySelector("button").addEventListener("click", () => {
      api().download_series(r.title || r.series_name, mtOf(), r.source || "mangadex");
      goTo("downloads");
    });
    box.appendChild(div);
  });
});
function mtOf() { return document.getElementById("media-type").value; }
function goTo(view) { document.querySelector(`.nav-item[data-view="${view}"]`).click(); }

// --- biblioteca ---
async function loadLibrary() {
  const box = document.getElementById("library-cards");
  box.innerHTML = '<p class="muted">Carregando…</p>';
  const data = await api().library();
  if (!data.length) { box.innerHTML = '<p class="muted">Biblioteca vazia.</p>'; return; }
  box.innerHTML = "";
  data.forEach((s) => {
    const pct = Math.round(s.completion_percentage || 0);
    const div = document.createElement("div");
    div.className = "card";
    div.innerHTML = `<h3>${s.title}</h3>
      <p class="muted">${s.is_complete ? "✅ Completa" : "⏳ " + pct + "%"}</p>
      <div class="progress"><div class="progress-bar" style="width:${pct}%"></div></div>
      <p class="muted">${s.chapters_downloaded}/${s.total_chapters_registered} caps</p>`;
    box.appendChild(div);
  });
}

// --- dashboard ---
async function loadDashboard() {
  const box = document.getElementById("dash-cards");
  box.innerHTML = '<p class="muted">Carregando…</p>';
  const s = await api().dashboard_stats();
  box.innerHTML = "";
  const cards = [
    ["Séries", s.total_series], ["Itens baixados", s.total_downloaded],
    ["Coleções completas", s.complete_collections], ["Itens faltantes", s.missing_total],
  ];
  cards.forEach(([label, value]) => {
    const div = document.createElement("div");
    div.className = "card";
    div.innerHTML = `<div class="stat">${value}</div><p class="muted">${label}</p>`;
    box.appendChild(div);
  });
}

// --- ferramentas ---
document.getElementById("btn-cache").addEventListener("click", async () => {
  const r = await api().clear_cache();
  alert(`Cache removido: ${r.removed} arquivo(s)`);
});
document.getElementById("btn-graph").addEventListener("click", () => { api().graph_status(); goTo("downloads"); });

// --- init ---
window.addEventListener("pywebviewready", () => {
  document.getElementById("conn-state").textContent = "Pronto";
  loadDashboard();
});
```

- [ ] **Step 7: Manual verification — a janela abre e a ponte funciona**

Run: `py -3.13 app.py`
Expected:
- A janela "Media Bot PT-BR" abre com a sidebar e o Dashboard mostrando 4 cards (valores podem ser 0).
- Clicar em **Buscar** → botão "Buscar" → a aba de resultados mostra cards ou "Nenhum resultado"; a aba **Downloads** mostra log ao vivo com as mensagens do bot.
- Clicar em **Ferramentas → Limpar cache** mostra um alerta com a contagem.
Feche a janela para encerrar.

- [ ] **Step 8: Commit**

```bash
git add app.py frontend/ requirements.txt
git commit -m "feat: entrypoint pywebview e frontend com ponte, log e progresso ao vivo"
```

---

### Task 7: Biblioteca visual com capas + status/export por série + enriquecimento

Liga capas (via `enrich_metadata`) e ações por série (ver status, exportar Komga). Verificação manual.

**Files:**
- Modify: `frontend/app.js`
- Modify: `frontend/index.html` (placeholder de capa via data-URI)

**Interfaces:**
- Consumes: `Api.enrich_metadata`, `Api.export_komga`, `Api.series_status`.

- [ ] **Step 1: Add cover placeholder constant to `app.js`**

At the top of `frontend/app.js` (após `"use strict";`), add:

```javascript
const COVER_PLACEHOLDER =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="230" height="150"><rect width="100%" height="100%" fill="#0b1220"/><text x="50%" y="50%" fill="#334155" font-family="sans-serif" font-size="14" text-anchor="middle" dominant-baseline="middle">sem capa</text></svg>'
  );
```

- [ ] **Step 2: Replace `loadLibrary` with the cover-enabled version**

In `frontend/app.js`, replace the entire `loadLibrary` function with:

```javascript
async function loadLibrary() {
  const box = document.getElementById("library-cards");
  box.innerHTML = '<p class="muted">Carregando…</p>';
  const data = await api().library();
  if (!data.length) { box.innerHTML = '<p class="muted">Biblioteca vazia.</p>'; return; }
  box.innerHTML = "";
  data.forEach((s) => {
    const pct = Math.round(s.completion_percentage || 0);
    const div = document.createElement("div");
    div.className = "card";
    div.innerHTML = `
      <img class="cover" src="${COVER_PLACEHOLDER}" alt="capa" />
      <h3>${s.title}</h3>
      <p class="muted">${s.is_complete ? "✅ Completa" : "⏳ " + pct + "%"}</p>
      <div class="progress"><div class="progress-bar" style="width:${pct}%"></div></div>
      <p class="muted">${s.chapters_downloaded}/${s.total_chapters_registered} caps</p>
      <div class="form-row" style="margin-top:10px">
        <button class="btn">Status</button>
        <button class="btn success">Exportar</button>
      </div>`;
    const [statusBtn, exportBtn] = div.querySelectorAll("button");
    statusBtn.addEventListener("click", async () => {
      const st = await api().series_status(s.title);
      alert(`${st.title}\nConclusão: ${Math.round(st.completion_percentage)}%\n` +
            `Baixados: ${st.chapters_downloaded}/${st.total_chapters_registered}\n` +
            `Faltando: ${st.missing_chapters.join(", ") || "nada"}`);
    });
    exportBtn.addEventListener("click", async () => {
      const r = await api().export_komga(s.title);
      alert(`Exportado para:\n${r.base_path}\nArquivos: ${r.exported} (pulados: ${r.skipped})`);
    });
    // Enriquecimento assíncrono da capa (não bloqueia o render)
    api().enrich_metadata(s.title).then((meta) => {
      if (meta && meta.cover_image) div.querySelector(".cover").src = meta.cover_image;
    });
    box.appendChild(div);
  });
}
```

- [ ] **Step 3: Manual verification**

Run: `py -3.13 app.py`
Expected:
- Aba **Biblioteca**: cada série aparece como card com capa (placeholder "sem capa" e, se a série tiver correspondência no Jikan/AniList e houver rede, a capa real substitui em seguida).
- Botão **Status** abre alerta com o progresso da coleção.
- Botão **Exportar** cria `exports/komga/<série>/...` e mostra o resumo.

*(Nota: se a biblioteca estiver vazia, use a CLI para popular — ex.: `py -3.13 media_bot.py download "Dandadan" --source mangadex` — ou verifique apenas o estado "Biblioteca vazia".)*

- [ ] **Step 4: Commit**

```bash
git add frontend/app.js frontend/index.html
git commit -m "feat: biblioteca visual com capas, status e exportação por série"
```

---

### Task 8: Arquivar Tkinter, atualizar testes, requirements e README

**Files:**
- Create: `legacy/gui_app.py` (mover)
- Delete: `gui_app.py` (após mover)
- Modify: `tests/test_core.py` (o import de `gui_app` e o smoke test da GUI Tkinter)
- Modify: `README.md`

**Interfaces:** nenhuma nova.

- [ ] **Step 1: Move the Tkinter GUI to `legacy/`**

```bash
mkdir -p legacy
git mv gui_app.py legacy/gui_app.py
```

- [ ] **Step 2: Update `tests/test_core.py` to reflect the move**

In `tests/test_core.py`, change the import line:

```python
from gui_app import MediaBotGUI
```

to:

```python
from legacy.gui_app import MediaBotGUI
```

Add `legacy/__init__.py` so the import resolves:

Create `legacy/__init__.py`:

```python
"""GUIs legadas preservadas (Tkinter)."""
```

- [ ] **Step 3: Run the full test suite**

Run: `py -3.13 -m pytest -v`
Expected: todos os testes passam (test_core, test_bot_service, test_media_bot_data, test_metadata_enricher, test_komga_exporter, test_api).

- [ ] **Step 4: Update the README interface section**

In `README.md`, replace the "## Interface Gráfica" section (linhas que começam em `## Interface Gráfica` até antes de `## CLI`) with:

```markdown
## Interface Gráfica (Desktop)

A interface oficial agora é uma janela desktop moderna (pywebview):

```bash
py -3.13 -m pip install -r requirements.txt
py -3.13 app.py
```

Abas disponíveis:
- **Dashboard** — totais da biblioteca (séries, itens, completas, faltantes)
- **Buscar** — pesquisa em todas as fontes com resultados em cards
- **Biblioteca** — cards visuais por série com capa, progresso, status e exportação Komga/Kavita
- **Downloads** — progresso e log em tempo real
- **Ferramentas** — limpar cache e status do grafo

Para gerar o executável clicável (`dist/MediaBot.exe`):

```bash
py -3.13 build.py
```

> A GUI antiga em Tkinter foi preservada em `legacy/gui_app.py`.
```

- [ ] **Step 5: Commit**

```bash
git add legacy/ README.md tests/test_core.py
git rm --cached gui_app.py 2>/dev/null || true
git commit -m "refactor: arquivar GUI Tkinter em legacy e atualizar docs/testes"
```

---

### Task 9: `build.py` + gerar `dist/MediaBot.exe`

**Files:**
- Create: `build.py`
- Create: `assets/icon.ico` (ícone gerado programaticamente)

**Interfaces:** nenhuma (script de build).

- [ ] **Step 1: Install PyInstaller**

Run: `py -3.13 -m pip install "pyinstaller>=6.0"`
Expected: `Successfully installed pyinstaller-...`

- [ ] **Step 2: Generate an app icon**

Run:
```bash
py -3.13 -c "from pathlib import Path; from PIL import Image; Path('assets').mkdir(exist_ok=True); img=Image.new('RGBA',(256,256),(37,99,235,255)); img.save('assets/icon.ico',sizes=[(256,256),(64,64),(32,32),(16,16)])" 2>&1 || echo "PIL_MISSING"
```
If output contains `PIL_MISSING`, run `py -3.13 -m pip install pillow` and retry the command above.
Expected: `assets/icon.ico` criado.

- [ ] **Step 3: Create `build.py`**

Create `build.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera o executável MediaBot.exe com PyInstaller.

Uso: py -3.13 build.py
Saída: dist/MediaBot.exe
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def main() -> int:
    # No Windows, --add-data usa ';' como separador (origem;destino).
    sep = ";" if sys.platform.startswith("win") else ":"
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile", "--windowed",
        "--name", "MediaBot",
        f"--add-data", f"frontend{sep}frontend",
        "--collect-all", "webview",
    ]
    icon = ROOT / "assets" / "icon.ico"
    if icon.exists():
        args += ["--icon", str(icon)]
    args.append("app.py")

    print("Executando:", " ".join(args))
    result = subprocess.run(args, cwd=str(ROOT))
    if result.returncode == 0:
        print("\n✅ Build concluído: dist/MediaBot.exe")
    else:
        print("\n❌ Build falhou.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Build the executable**

Run: `py -3.13 build.py`
Expected: termina com `✅ Build concluído: dist/MediaBot.exe` e o arquivo `dist/MediaBot.exe` existe.

- [ ] **Step 5: Manual verification — o .exe abre**

Run: `./dist/MediaBot.exe` (ou duplo-clique no Explorer)
Expected: a janela "Media Bot PT-BR" abre igual ao `py -3.13 app.py`, com Dashboard, Buscar, Biblioteca, Downloads e Ferramentas funcionando. Feche a janela.

- [ ] **Step 6: Ignore build artifacts and commit the build tooling**

In `.gitignore`, add (se ainda não presentes):

```
build/
dist/
*.spec
```

```bash
git add build.py assets/icon.ico .gitignore
git commit -m "build: script PyInstaller e ícone para gerar MediaBot.exe"
```

---

## Verificação final (após todas as tasks)

- [ ] `py -3.13 -m pytest -v` — suíte inteira verde.
- [ ] `py -3.13 app.py` — todas as 5 abas funcionam.
- [ ] `dist/MediaBot.exe` — abre por duplo-clique e replica a GUI.
- [ ] `git status` limpo (sem `build/`, `dist/`, `*.spec` rastreados).
