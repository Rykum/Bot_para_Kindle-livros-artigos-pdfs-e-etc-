# Download: Cancelamento, Robustez, Seleção e Idioma — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cancelamento que realmente para, re-tentativa exaustiva de capítulos, seleção de capítulos (tudo/intervalo/checkboxes), idioma primário + fallback no MangaDex, e UI/UX alinhada às 10 heurísticas de Nielsen.

**Architecture:** Backend-first e testável. O núcleo (`media_bot.py`, `mangadex_scraper.py`) ganha idioma, retry e cancelamento granular; a `Api` expõe `list_chapters` e novos parâmetros; o frontend adiciona o seletor de capítulos + idiomas e corrige o cancelar. Cada camada é validada por testes antes da UI.

**Tech Stack:** Python 3.13, pywebview, requests, SQLAlchemy, pytest, node (só `node --check`).

## Global Constraints

- **Interpretador:** o `python` do PATH está quebrado. Use SEMPRE `py -3.13` (ex.: `py -3.13 -m pytest`).
- **Entrypoint:** a GUI é `desktop.py` (NÃO `app.py`; existe o pacote `app/`). Nunca criar `app.py`.
- **Frontend sem CDN:** todo CSS/JS/asset local e inline.
- **Núcleo estável:** só adicionar parâmetros keyword opcionais; não quebrar assinaturas usadas por CLI/`tests/test_core.py`. Rodar a suíte completa antes de cada commit.
- **Concorrência:** todo acesso ao bot/DB continua via worker serial do `BotService`.
- **Idioma primário tem prioridade absoluta:** enumeração e TODAS as rodadas de retry usam o primário; o fallback é uma passada final, por capítulo, só se `fallback_language` estiver definido.
- **Idiomas suportados:** `pt-br`, `en`, `es`. Primário padrão `pt-br`; fallback padrão `nenhum` (None).
- **Idioma da copy:** pt-br.

---

### Task 1: MangaDex — idioma no feed + retry por página

**Files:**
- Modify: `scrapers/mangadex_scraper.py`
- Modify: `scrapers/base_scraper.py` (assinaturas com `language` opcional)
- Test: `tests/test_mangadex_language.py`

**Interfaces:**
- Consumes: `BaseScraper.make_request` (existente).
- Produces:
  - `MangaDexScraper.get_series_info(series_url, language: str = "pt-br") -> Dict` (feed usa `translatedLanguage[]=[language]`)
  - `MangaDexScraper.get_chapter_url(series_identifier, chapter_number, language: str = "pt-br") -> Optional[Dict]`
  - `BaseScraper.get_series_info(series_url, language: str = "pt-br")` e `BaseScraper.get_all_chapters(series_identifier, language="pt-br")` e `BaseScraper.get_chapter_url(series_identifier, chapter_number, language="pt-br")` — `language` keyword opcional (ignorado por scrapers não-MangaDex).

- [ ] **Step 1: Write the failing test**

Create `tests/test_mangadex_language.py`:

```python
from scrapers.mangadex_scraper import MangaDexScraper


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_get_series_info_uses_selected_language(monkeypatch):
    scraper = MangaDexScraper()
    captured = {}

    def fake_make_request(url, params=None, retries=0):
        captured.setdefault("langs", [])
        if "/feed" in url:
            captured["langs"].append(params.get("translatedLanguage[]"))
            return FakeResponse({"data": [
                {"id": "c1", "attributes": {"chapter": "1", "volume": "1", "title": "A"}},
            ]})
        return FakeResponse({"data": {"attributes": {"title": {"en": "X"}}}})

    monkeypatch.setattr(scraper, "make_request", fake_make_request)
    info = scraper.get_series_info("https://mangadex.org/title/abc", language="en")

    assert captured["langs"] == [["en"]]
    assert info["available_chapters"][0]["chapter"] == 1.0


def test_get_series_info_defaults_to_pt_br(monkeypatch):
    scraper = MangaDexScraper()
    captured = {}

    def fake_make_request(url, params=None, retries=0):
        if "/feed" in url:
            captured["lang"] = params.get("translatedLanguage[]")
            return FakeResponse({"data": []})
        return FakeResponse({"data": {"attributes": {"title": {"en": "X"}}}})

    monkeypatch.setattr(scraper, "make_request", fake_make_request)
    scraper.get_series_info("https://mangadex.org/title/abc")
    assert captured["lang"] == ["pt-br"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_mangadex_language.py -v`
Expected: FAIL (`get_series_info() got an unexpected keyword argument 'language'`).

- [ ] **Step 3: Add `language` to base scraper signatures**

In `scrapers/base_scraper.py`, change the abstract/base method signatures to accept an optional `language`:

- `def get_series_info(self, series_url: str, language: str = "pt-br") -> Dict:` (abstractmethod signature)
- `def get_all_chapters(self, series_identifier: str, language: str = "pt-br") -> List[float]:` — and inside it call `self.get_series_info(series_identifier, language=language)`.
- `def get_chapter_url(self, series_identifier: str, chapter_number: float, language: str = "pt-br") -> Optional[Dict[str, Any]]:` — and inside it call `self.get_series_info(series_identifier, language=language)`.

(Only add the parameter and thread it into the internal `get_series_info` calls; keep the rest of each method's body unchanged.)

- [ ] **Step 4: Thread `language` through MangaDex**

In `scrapers/mangadex_scraper.py`:

Change `get_series_info` signature to `def get_series_info(self, series_url: str, language: str = "pt-br") -> Dict:` and in its `params` for the feed replace `'translatedLanguage[]': ['pt-br']` with `'translatedLanguage[]': [language]`. Also set the returned `'language': language`.

Change `get_chapter_url` to `def get_chapter_url(self, series_identifier: str, chapter_number: float, language: str = "pt-br") -> Optional[Dict]:` and call `self.get_series_info(series_identifier, language=language)` at its top.

- [ ] **Step 5: Add per-page retry helper**

In `scrapers/mangadex_scraper.py`, add a method used to fetch a single page with retry (will be consumed by `media_bot.py` in Task 2):

```python
    def fetch_page(self, page_url: str, should_cancel=None, max_attempts: int = 3):
        """Baixa uma página com retry local. Retorna bytes ou levanta a última exceção."""
        import time
        last_error = None
        for attempt in range(max_attempts):
            if should_cancel is not None and should_cancel():
                raise RuntimeError("cancelled")
            try:
                response = self.session.get(page_url, timeout=60)
                response.raise_for_status()
                return response.content
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(1.5 ** attempt)
        raise last_error if last_error else RuntimeError("falha ao baixar página")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `py -3.13 -m pytest tests/test_mangadex_language.py tests/test_core.py -v`
Expected: novos passam; `test_core` sem regressão.

- [ ] **Step 7: Commit**

```bash
git add scrapers/mangadex_scraper.py scrapers/base_scraper.py tests/test_mangadex_language.py
git commit -m "feat: idioma no feed do MangaDex e retry por página"
```

---

### Task 2: Cancelamento granular + retorno de resumo no download

**Files:**
- Modify: `media_bot.py`
- Test: `tests/test_download_cancel.py`

**Interfaces:**
- Consumes: `MangaDexScraper.fetch_page` (Task 1).
- Produces:
  - `MediaBot._download_mangadex_chapter(scraper, chapter_data, series_title, chapter_num, progress_callback=None, should_cancel=None)` — checa `should_cancel` entre páginas; usa `scraper.fetch_page`; ao cancelar apaga o `.cbz` parcial e retorna `{'success': False, 'cancelled': True}`.
  - `MediaBot.download_complete_series(...)` retorna `{'total': int, 'downloaded': int, 'failed': int, 'cancelled': bool, 'failed_chapters': List[float]}`; espera entre capítulos é interrompível.

- [ ] **Step 1: Write the failing test**

Create `tests/test_download_cancel.py`:

```python
import tempfile
from pathlib import Path

from media_bot import MediaBot


def make_bot():
    return MediaBot(base_download_dir=str(Path(tempfile.mkdtemp()) / "dl"))


def test_download_returns_summary_and_stops_on_cancel(monkeypatch):
    bot = make_bot()
    try:
        monkeypatch.setattr(bot, "_resolve_series_reference", lambda *a, **k: "ref")
        monkeypatch.setattr(bot, "get_complete_series_chapters", lambda *a, **k: [1.0, 2.0, 3.0])
        summary = bot.download_complete_series("Serie", source_name="mangadex", should_cancel=lambda: True)
        assert summary["cancelled"] is True
        assert summary["downloaded"] == 0
        assert summary["total"] == 3
    finally:
        bot.cleanup()


def test_mangadex_chapter_cancel_between_pages(monkeypatch):
    bot = make_bot()
    try:
        calls = {"pages": 0}

        class FakeScraper:
            def fetch_page(self, url, should_cancel=None, max_attempts=3):
                calls["pages"] += 1
                if should_cancel and should_cancel():
                    raise RuntimeError("cancelled")
                return b"img"

        chapter_data = {"page_urls": ["u1", "u2", "u3"], "download_type": "mangadex_cbz"}
        result = bot._download_mangadex_chapter(
            FakeScraper(), chapter_data, "Serie", 1.0,
            should_cancel=lambda: calls["pages"] >= 1,  # cancela após a 1ª página
        )
        assert result["success"] is False
        assert result.get("cancelled") is True
        assert calls["pages"] <= 2  # não baixou todas as páginas
    finally:
        bot.cleanup()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_download_cancel.py -v`
Expected: FAIL (retorno atual é `None`; `_download_mangadex_chapter` ainda não aceita `should_cancel`).

- [ ] **Step 3: Update `_download_mangadex_chapter`**

In `media_bot.py`, change the signature to add `should_cancel=None` and rewrite the page loop to check cancel and use `fetch_page`:

```python
    def _download_mangadex_chapter(self, scraper, chapter_data, series_title, chapter_num,
                                   progress_callback=None, should_cancel=None):
        page_urls = chapter_data.get('page_urls') or []
        if not page_urls:
            return {'success': False, 'error': 'MangaDex chapter has no page URLs'}

        chapter_label = self._format_chapter_label(chapter_num)
        filename = f"{self._sanitize_filename(series_title)}_cap_{chapter_label}.cbz"
        output_path = self.base_dir / filename

        try:
            with zipfile.ZipFile(output_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for index, page_url in enumerate(page_urls, 1):
                    if should_cancel is not None and should_cancel():
                        raise RuntimeError("cancelled")
                    content = scraper.fetch_page(page_url, should_cancel=should_cancel)
                    suffix = Path(urlparse(page_url).path).suffix or '.jpg'
                    archive.writestr(f"{index:03d}{suffix}", content)
                    if progress_callback:
                        progress_callback(f"{series_title} cap. {chapter_label}", index, len(page_urls))

            file_hash = self.downloader.calculate_hash(str(output_path))
            file_size = output_path.stat().st_size
            return {
                'success': True,
                'filepath': str(output_path),
                'file_path': str(output_path),
                'size': file_size,
                'hash': file_hash,
                'error': None,
                'metadata': {'format': 'cbz', 'size': file_size, 'sha256': file_hash},
            }
        except Exception as exc:
            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass
            cancelled = str(exc) == "cancelled"
            return {'success': False, 'error': str(exc), 'cancelled': cancelled}
```

- [ ] **Step 4: Update `download_complete_series` — cancel-aware wait + summary return**

In `media_bot.py`, inside `download_complete_series`:

- Where the mangadex branch calls `self._download_mangadex_chapter(...)`, pass `should_cancel=should_cancel`.
- Replace the `time.sleep(2)` at the end of the loop with an interruptible wait:

```python
                # Rate limiting interrompível entre capítulos
                waited = 0.0
                while waited < 2.0:
                    if should_cancel is not None and should_cancel():
                        break
                    time.sleep(0.2)
                    waited += 0.2
```

- Track a `cancelled` flag (set it when `should_cancel()` triggers the break at the top of the loop or when a chapter result has `cancelled`), and at the end `return` the summary:

```python
        return {
            'total': len(missing_chapters),
            'downloaded': downloaded_count,
            'failed': failed_count,
            'cancelled': cancelled,
            'failed_chapters': failed_chapters,
        }
```

Add `cancelled = False` and `failed_chapters = []` before the loop; append `chapter_num` to `failed_chapters` on failure; set `cancelled = True` when the cancel check breaks the loop. Keep all existing prints. (When `available_chapters` is empty or all present, return a summary with zeros too instead of bare `return`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.13 -m pytest tests/test_download_cancel.py tests/test_media_bot_data.py tests/test_core.py -v`
Expected: passam, sem regressão.

- [ ] **Step 6: Commit**

```bash
git add media_bot.py tests/test_download_cancel.py
git commit -m "feat: cancelamento granular entre páginas e resumo de download"
```

---

### Task 3: Re-tentativa exaustiva por capítulo + seleção + fallback de idioma

**Files:**
- Modify: `media_bot.py`
- Test: `tests/test_download_retry_select.py`

**Interfaces:**
- Consumes: o resumo/loop da Task 2.
- Produces:
  - `MediaBot.download_complete_series(series_title, media_type="manga", source_name="mangadex", skip_existing=True, progress_callback=None, should_cancel=None, chapters: Optional[List[float]] = None, language: str = "pt-br", fallback_language: Optional[str] = None)` — baixa subconjunto se `chapters` vier; após a 1ª passada re-tenta `failed_chapters` em até 2 rodadas (idioma primário); depois, se `fallback_language`, uma passada final por capítulo ainda faltante usando o fallback.
  - `MediaBot.list_series_chapters(series_title, media_type, source_name, language="pt-br", fallback_language=None) -> Dict` — `{title, source, available, downloaded, missing, by_language}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_download_retry_select.py`:

```python
import tempfile
from pathlib import Path

from media_bot import MediaBot


def make_bot():
    return MediaBot(base_download_dir=str(Path(tempfile.mkdtemp()) / "dl"))


def _stub_common(bot, monkeypatch, available):
    monkeypatch.setattr(bot, "_resolve_series_reference", lambda *a, **k: "ref")
    monkeypatch.setattr(bot, "get_complete_series_chapters", lambda *a, **k: list(available))


def test_only_selected_chapters_are_downloaded(monkeypatch):
    bot = make_bot()
    try:
        _stub_common(bot, monkeypatch, [1.0, 2.0, 3.0])
        requested = []
        scraper = bot._resolve_scraper("mangadex")

        def fake_get_chapter_url(ref, num, language="pt-br"):
            requested.append(num)
            return {"download_url": "http://x/f.cbz", "format": "cbz"}

        monkeypatch.setattr(scraper, "get_chapter_url", fake_get_chapter_url)
        monkeypatch.setattr(bot.downloader, "download",
                            lambda **kw: {"success": True, "file_path": "f", "metadata": {"format": "cbz", "size": 1, "sha256": "h"}})
        bot.download_complete_series("Serie", source_name="mangadex", chapters=[1.0, 3.0])
        assert sorted(requested) == [1.0, 3.0]
    finally:
        bot.cleanup()


def test_failed_chapter_is_retried_and_succeeds(monkeypatch):
    bot = make_bot()
    try:
        _stub_common(bot, monkeypatch, [1.0])
        scraper = bot._resolve_scraper("mangadex")
        monkeypatch.setattr(scraper, "get_chapter_url",
                            lambda ref, num, language="pt-br": {"download_url": "http://x/f.cbz", "format": "cbz"})
        attempts = {"n": 0}

        def flaky_download(**kw):
            attempts["n"] += 1
            if attempts["n"] < 2:
                return {"success": False, "error": "boom"}
            return {"success": True, "file_path": "f", "metadata": {"format": "cbz", "size": 1, "sha256": "h"}}

        monkeypatch.setattr(bot.downloader, "download", flaky_download)
        summary = bot.download_complete_series("Serie", source_name="mangadex")
        assert summary["downloaded"] == 1
        assert summary["failed_chapters"] == []
        assert attempts["n"] >= 2  # re-tentou
    finally:
        bot.cleanup()


def test_fallback_language_used_after_primary_exhausted(monkeypatch):
    bot = make_bot()
    try:
        _stub_common(bot, monkeypatch, [1.0])
        scraper = bot._resolve_scraper("mangadex")
        langs = []

        def fake_get_chapter_url(ref, num, language="pt-br"):
            langs.append(language)
            if language == "pt-br":
                return None  # indisponível no primário
            return {"download_url": "http://x/f.cbz", "format": "cbz"}

        monkeypatch.setattr(scraper, "get_chapter_url", fake_get_chapter_url)
        monkeypatch.setattr(bot.downloader, "download",
                            lambda **kw: {"success": True, "file_path": "f", "metadata": {"format": "cbz", "size": 1, "sha256": "h"}})
        summary = bot.download_complete_series("Serie", source_name="mangadex",
                                               language="pt-br", fallback_language="en")
        assert "en" in langs                # fallback foi acionado
        assert langs.index("en") > 0        # só depois de tentar o primário
        assert summary["downloaded"] == 1
    finally:
        bot.cleanup()


def test_list_series_chapters_shape(monkeypatch):
    bot = make_bot()
    try:
        monkeypatch.setattr(bot, "_resolve_series_reference", lambda *a, **k: "ref")
        monkeypatch.setattr(bot, "get_complete_series_chapters", lambda *a, **k: [1.0, 2.0])
        data = bot.list_series_chapters("Serie", "manga", "mangadex")
        for key in ["title", "available", "downloaded", "missing", "by_language"]:
            assert key in data
        assert data["available"] == [1.0, 2.0]
    finally:
        bot.cleanup()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_download_retry_select.py -v`
Expected: FAIL (`chapters`/`language`/`fallback_language` inexistentes; `list_series_chapters` inexistente).

- [ ] **Step 3: Add the new signature + selection + retry rounds + fallback**

In `media_bot.py`, update `download_complete_series` signature:

```python
    def download_complete_series(self, series_title, media_type="manga", source_name="mangadex",
                                 skip_existing=True, progress_callback=None, should_cancel=None,
                                 chapters=None, language="pt-br", fallback_language=None):
```

Thread `language` into `get_complete_series_chapters`/`_resolve_series_reference`/`get_chapter_url` calls. Compute the target set:

```python
        if chapters:
            requested = sorted(set(float(c) for c in chapters) & set(available_chapters))
            missing_chapters = self.library.find_missing_chapters(series, requested) if skip_existing else requested
        else:
            missing_chapters = self.library.find_missing_chapters(series, available_chapters)
```

Extract the per-chapter download into a helper `self._attempt_chapter(scraper, series, series_reference, series_title, chapter_num, source_name, language, progress_callback, should_cancel)` that returns `True/False` (encapsulates the existing get_chapter_url → download/mangadex → register logic, using the given `language`). Then:

```python
        pending = list(missing_chapters)
        failed_chapters = []
        cancelled = False
        for round_index in range(3):  # 1 principal + 2 re-tentativas
            still_failed = []
            for chapter_num in pending:
                if should_cancel is not None and should_cancel():
                    cancelled = True
                    break
                ok = self._attempt_chapter(scraper, series, series_reference, series_title,
                                           chapter_num, source_name, language,
                                           progress_callback, should_cancel)
                if ok:
                    downloaded_count += 1
                else:
                    still_failed.append(chapter_num)
            if cancelled or not still_failed:
                pending = still_failed
                break
            print(f"   🔁 Re-tentando {len(still_failed)} capítulo(s) (rodada {round_index + 2})...")
            pending = still_failed

        # Fallback de idioma, por capítulo, só após esgotar o primário
        if pending and fallback_language and not cancelled:
            print(f"   🌐 Tentando fallback de idioma ({fallback_language}) em {len(pending)} capítulo(s)...")
            still_failed = []
            for chapter_num in pending:
                if should_cancel is not None and should_cancel():
                    cancelled = True
                    break
                ok = self._attempt_chapter(scraper, series, series_reference, series_title,
                                           chapter_num, source_name, fallback_language,
                                           progress_callback, should_cancel)
                if ok:
                    downloaded_count += 1
                else:
                    still_failed.append(chapter_num)
            pending = still_failed

        failed_chapters = pending
        failed_count = len(failed_chapters)
        return {'total': len(missing_chapters), 'downloaded': downloaded_count,
                'failed': failed_count, 'cancelled': cancelled, 'failed_chapters': failed_chapters}
```

Implement `_attempt_chapter` by moving the existing body of the per-chapter loop (resolve `get_chapter_url(series_reference, chapter_num, language=language)`, mangadex vs direct download, register on success) into it, returning `True` on successful register and `False` otherwise. It must pass `should_cancel` to `_download_mangadex_chapter`.

- [ ] **Step 4: Add `list_series_chapters`**

In `media_bot.py`, add:

```python
    def list_series_chapters(self, series_title, media_type="manga", source_name="mangadex",
                             language="pt-br", fallback_language=None):
        series = self.library.get_or_create_series(series_title, source_name)
        primary = self.get_complete_series_chapters(series_title, source_name, media_type)  # usa cache/idioma primário
        by_language = {c: [language] for c in primary}
        available = set(primary)
        if fallback_language:
            try:
                scraper = self._resolve_scraper(source_name)
                ref = self._resolve_series_reference(scraper, series_title, media_type)
                fb = sorted(set(scraper.get_all_chapters(ref, language=fallback_language)))
            except Exception:
                fb = []
            for c in fb:
                available.add(c)
                by_language.setdefault(c, [])
                if fallback_language not in by_language[c]:
                    by_language[c].append(fallback_language)
        available = sorted(available)
        progress = self.library.get_series_progress(series)
        downloaded = sorted(set(available) - set(self.library.find_missing_chapters(series, available)))
        missing = sorted(set(available) - set(downloaded))
        return {'title': series.title, 'source': source_name, 'available': available,
                'downloaded': downloaded, 'missing': missing, 'by_language': by_language}
```

(`get_complete_series_chapters` deve repassar `language` ao scraper; ajuste sua assinatura para `get_complete_series_chapters(self, series_title, source_name="mangadex", media_type="manga", language="pt-br")` e passe `language` ao `scraper.get_all_chapters(series_reference, language=language)`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.13 -m pytest tests/test_download_retry_select.py tests/test_download_cancel.py tests/test_core.py -v`
Expected: passam, sem regressão.

- [ ] **Step 6: Commit**

```bash
git add media_bot.py tests/test_download_retry_select.py
git commit -m "feat: re-tentativa por capítulo, seleção de capítulos e fallback de idioma"
```

---

### Task 4: Api — `list_chapters` + parâmetros de seleção/idioma

**Files:**
- Modify: `app/api.py`
- Test: `tests/test_api_chapters.py`

**Interfaces:**
- Consumes: `MediaBot.list_series_chapters`, `download_complete_series` (Task 3).
- Produces:
  - `Api.list_chapters(series, media_type="manga", source="mangadex", language="pt-br", fallback_language=None) -> {'job_id'}` (assíncrono; emite evento `chapters_list` com o dict).
  - `Api.download_series(series, media_type="manga", source="mangadex", chapters=None, language="pt-br", fallback_language=None) -> {'job_id'}` (repassa tudo ao download).

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_chapters.py`:

```python
import time

from app.api import Api
from app.bot_service import BotService


class FakeBot:
    def __init__(self):
        self.download_kwargs = None

    def list_series_chapters(self, series, media_type="manga", source_name="mangadex",
                             language="pt-br", fallback_language=None):
        return {"title": series, "available": [1.0, 2.0], "downloaded": [],
                "missing": [1.0, 2.0], "by_language": {1.0: [language]}, "source": source_name}

    def download_complete_series(self, series, **kwargs):
        self.download_kwargs = kwargs
        return {"total": 0, "downloaded": 0, "failed": 0, "cancelled": False, "failed_chapters": []}

    def cleanup(self):
        pass


def make_api(events, bot):
    service = BotService(bot_factory=lambda: bot, event_sink=lambda n, p: events.append((n, p)))
    api = Api(service)
    service.start()
    return api, service


def test_list_chapters_emits_event():
    events, bot = [], FakeBot()
    api, service = make_api(events, bot)
    try:
        ack = api.list_chapters("Dandadan", language="en", fallback_language="pt-br")
        assert "job_id" in ack
        deadline = time.time() + 5
        while time.time() < deadline and not any(n == "chapters_list" for n, _ in events):
            time.sleep(0.01)
        payload = [p for n, p in events if n == "chapters_list"]
        assert payload and payload[0]["available"] == [1.0, 2.0]
    finally:
        service.stop()


def test_download_series_forwards_selection_and_language():
    events, bot = [], FakeBot()
    api, service = make_api(events, bot)
    try:
        api.download_series("Dandadan", chapters=[1.0], language="en", fallback_language="es")
        deadline = time.time() + 5
        while time.time() < deadline and bot.download_kwargs is None:
            time.sleep(0.01)
        assert bot.download_kwargs["chapters"] == [1.0]
        assert bot.download_kwargs["language"] == "en"
        assert bot.download_kwargs["fallback_language"] == "es"
    finally:
        service.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_api_chapters.py -v`
Expected: FAIL (`list_chapters` inexistente; `download_series` não repassa `chapters`).

- [ ] **Step 3: Update `Api`**

In `app/api.py`, replace `download_series` and add `list_chapters`:

```python
    def download_series(self, series, media_type="manga", source="mangadex",
                        chapters=None, language="pt-br", fallback_language=None):
        job_holder = {"id": None}

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

    def list_chapters(self, series, media_type="manga", source="mangadex",
                      language="pt-br", fallback_language=None):
        def fn(bot, emit):
            data = bot.list_series_chapters(series, media_type=media_type, source_name=source,
                                            language=language, fallback_language=fallback_language)
            emit("chapters_list", data)
            return {"count": len(data.get("available", []))}
        return {"job_id": self._service.submit(f"Capítulos: {series}", fn)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.13 -m pytest tests/test_api_chapters.py tests/test_api.py -v`
Expected: passam.

- [ ] **Step 5: Commit**

```bash
git add app/api.py tests/test_api_chapters.py
git commit -m "feat: Api list_chapters e parâmetros de seleção/idioma no download"
```

---

### Task 5: Frontend — seletor de capítulos, idiomas e correção do cancelar (com heurísticas de Nielsen)

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`
- Test: `tests/test_frontend_chapters.py` (asserções estáticas sobre o conteúdo dos arquivos)

**Interfaces:** consome `Api.list_chapters`, `Api.download_series(chapters, language, fallback_language)`, `Api.cancel_job`, e o evento `chapters_list` e o `result` do `job_done`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_frontend_chapters.py`:

```python
from pathlib import Path

FRONT = Path(__file__).parent.parent / "frontend"


def test_index_has_chapter_picker_and_language_selectors():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert 'id="view-chapters"' in html
    assert 'id="lang-primary"' in html
    assert 'id="lang-fallback"' in html
    assert 'id="btn-download-all"' in html
    assert 'id="btn-download-selected"' in html


def test_appjs_wires_chapters_and_cancel_reset():
    js = (FRONT / "app.js").read_text(encoding="utf-8")
    assert "list_chapters" in js
    assert "chapters_list" in js
    # cancelar dá feedback e reseta estado
    assert "Cancelando" in js
    assert "result.cancelled" in js or "p.result" in js
    # validação de erro-prevenção: baixar selecionados desabilitado sem seleção
    assert "btn-download-selected" in js
    # bridge intacta
    assert "window.pushEvent" in js
    assert "window.pywebview.api" in js


def test_styles_has_chapter_grid():
    css = (FRONT / "styles.css").read_text(encoding="utf-8")
    assert "chapter" in css.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_frontend_chapters.py -v`
Expected: FAIL (elementos ainda não existem).

- [ ] **Step 3: Add the chapter-picker view + language selectors to `index.html`**

In `frontend/index.html`, add a nav entry is NOT needed (the picker is reached from a search result). Add a new hidden view after `view-search`:

```html
      <section id="view-chapters" class="view">
        <div class="row-between">
          <h1 id="chapters-title">Capítulos</h1>
          <button id="btn-chapters-back" class="btn">← Voltar</button>
        </div>
        <div class="form-row">
          <label title="Idioma principal da busca/download">Idioma
            <select id="lang-primary"><option value="pt-br">pt-br</option><option value="en">en</option><option value="es">es</option></select>
          </label>
          <label title="Idioma usado só se o capítulo não vier no principal, após esgotar as re-tentativas">Fallback
            <select id="lang-fallback"><option value="">nenhum</option><option value="pt-br">pt-br</option><option value="en">en</option><option value="es">es</option></select>
          </label>
        </div>
        <p id="chapters-summary" class="muted">—</p>
        <div class="form-row">
          <button id="btn-download-all" class="btn success">Baixar tudo (faltantes)</button>
          <span class="muted">Intervalo:</span>
          <input id="range-from" type="number" min="0" style="max-width:90px" placeholder="de" />
          <input id="range-to" type="number" min="0" style="max-width:90px" placeholder="até" />
          <button id="btn-range-apply" class="btn">Aplicar</button>
          <button id="btn-download-selected" class="btn accent" disabled>Baixar selecionados (0)</button>
        </div>
        <div id="chapter-grid" class="chapter-grid"></div>
      </section>
```

- [ ] **Step 4: Add chapter-grid styles to `styles.css`**

Append to `frontend/styles.css`:

```css
.row-between { display: flex; justify-content: space-between; align-items: center; }
.chapter-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 6px; max-height: 52vh; overflow-y: auto; padding: 6px; background: #0b1220; border-radius: 10px; }
.chapter-chip { display: flex; align-items: center; gap: 6px; padding: 6px 8px; border-radius: 6px; background: #111827; font-size: 13px; cursor: pointer; }
.chapter-chip input { cursor: pointer; }
.chapter-chip.done { opacity: .55; cursor: not-allowed; }
.chapter-chip .lang { color: #64748b; font-size: 11px; margin-left: auto; }
label select { margin-left: 6px; }
```

- [ ] **Step 5: Wire the picker, selection, language and cancel-reset in `app.js`**

In `frontend/app.js`:

(a) Change the search-result "Baixar" handler so that, instead of calling `download_series` directly, it opens the chapter picker:

```javascript
    div.querySelector("button").addEventListener("click", () => openChapters(r.title || r.series_name, r.source || "mangadex"));
```

(b) Add the picker logic (module-level state + functions):

```javascript
let chaptersState = { series: null, source: "mangadex", available: [], downloaded: [], byLang: {} };

function langPrimary() { return document.getElementById("lang-primary").value; }
function langFallback() { return document.getElementById("lang-fallback").value || null; }

async function openChapters(series, source) {
  chaptersState.series = series; chaptersState.source = source;
  document.getElementById("chapters-title").textContent = series;
  document.getElementById("chapters-summary").textContent = "Carregando capítulos…";
  document.getElementById("chapter-grid").innerHTML = "";
  goTo("chapters");
  await api().list_chapters(series, "manga", source, langPrimary(), langFallback());
}
on("chapters_list", (d) => {
  chaptersState.available = d.available || [];
  chaptersState.downloaded = d.downloaded || [];
  chaptersState.byLang = d.by_language || {};
  const missing = (d.missing || []).length;
  document.getElementById("chapters-summary").textContent =
    `${d.available.length} caps · ${d.downloaded.length} baixados · faltam ${missing}`;
  renderChapterGrid();
});

function renderChapterGrid() {
  const grid = document.getElementById("chapter-grid");
  grid.innerHTML = "";
  const done = new Set(chaptersState.downloaded);
  chaptersState.available.forEach((num) => {
    const isDone = done.has(num);
    const langs = (chaptersState.byLang[num] || []).join(", ");
    const chip = document.createElement("label");
    chip.className = "chapter-chip" + (isDone ? " done" : "");
    chip.innerHTML = `<input type="checkbox" ${isDone ? "checked disabled" : ""} data-num="${num}"><span>Cap ${num}</span><span class="lang">${langs}</span>`;
    if (!isDone) chip.querySelector("input").addEventListener("change", updateSelectedCount);
    grid.appendChild(chip);
  });
  updateSelectedCount();
}

function selectedChapters() {
  return Array.from(document.querySelectorAll("#chapter-grid input:checked:not([disabled])"))
    .map((el) => parseFloat(el.dataset.num));
}
function updateSelectedCount() {
  const n = selectedChapters().length;
  const btn = document.getElementById("btn-download-selected");
  btn.textContent = `Baixar selecionados (${n})`;
  btn.disabled = n === 0;  // Nielsen #5: prevenção de erro
}

document.getElementById("btn-range-apply").addEventListener("click", () => {
  let from = parseFloat(document.getElementById("range-from").value);
  let to = parseFloat(document.getElementById("range-to").value);
  if (isNaN(from) || isNaN(to)) return;
  if (from > to) { const t = from; from = to; to = t; }  // corrige de>até
  document.querySelectorAll("#chapter-grid input:not([disabled])").forEach((el) => {
    const num = parseFloat(el.dataset.num);
    el.checked = num >= from && num <= to;
  });
  updateSelectedCount();
});

function startDownload(chapters) {
  api().download_series(chaptersState.series, "manga", chaptersState.source, chapters, langPrimary(), langFallback());
  goTo("downloads");
}
document.getElementById("btn-download-all").addEventListener("click", () => startDownload(null));
document.getElementById("btn-download-selected").addEventListener("click", () => {
  const sel = selectedChapters();
  if (sel.length) startDownload(sel);
});
document.getElementById("btn-chapters-back").addEventListener("click", () => goTo("search"));
```

(c) Fix the cancel button feedback + reset. Add a cancel button handler that gives instant feedback, and update the `job_done` handler to read the result:

```javascript
const cancelBtn = () => document.getElementById("btn-cancel");
if (cancelBtn()) {
  cancelBtn().addEventListener("click", () => {
    if (!currentDownloadJob) return;
    api().cancel_job(currentDownloadJob);
    document.getElementById("progress-text").textContent = "Cancelando…";
    cancelBtn().disabled = true;  // feedback imediato
  });
}
```

Replace the existing `on("job_done", ...)` handler with one that reads the summary and resets on cancel:

```javascript
on("job_done", (p) => {
  logEl().textContent += `✅ ${p.label} concluído.\n`;
  logEl().scrollTop = logEl().scrollHeight;
  if (p.job_id === currentDownloadJob) {
    const r = p.result || {};
    if (r.cancelled) {
      document.getElementById("progress-text").textContent = "Download cancelado.";
      document.getElementById("progress-bar").style.width = "0%";
    } else if (r.total !== undefined) {
      const failed = (r.failed_chapters || []).length;
      document.getElementById("progress-text").textContent =
        `Download concluído: ${r.downloaded}/${r.total}` + (failed ? ` · ${failed} não vieram: ${r.failed_chapters.join(", ")}` : "");
    }
    currentDownloadJob = null;
    if (cancelBtn()) cancelBtn().disabled = false;
  }
});
```

Ensure `currentDownloadJob` is set from the awaited `download_series` return inside `startDownload`:

```javascript
function startDownload(chapters) {
  document.getElementById("progress-bar").style.width = "0%";
  document.getElementById("progress-text").textContent = "Iniciando…";
  if (cancelBtn()) cancelBtn().disabled = false;
  api().download_series(chaptersState.series, "manga", chaptersState.source, chapters, langPrimary(), langFallback())
    .then((ack) => { currentDownloadJob = ack && ack.job_id; });
  goTo("downloads");
}
```

(Remove any earlier duplicate `job_done` handler and the old direct-download `startDownload`/`currentDownloadJob` wiring so there is exactly one of each.)

- [ ] **Step 6: Verify JS validity + run tests**

Run: `node --check frontend/app.js`
Expected: sem saída (válido).
Run: `py -3.13 -m pytest tests/test_frontend_chapters.py tests/test_app_entry.py -v`
Expected: passam (inclui o smoke test dos tokens da ponte).

- [ ] **Step 7: Commit**

```bash
git add frontend/index.html frontend/app.js frontend/styles.css tests/test_frontend_chapters.py
git commit -m "feat: seletor de capítulos, idiomas e correção do cancelar (heurísticas de Nielsen)"
```

---

### Task 6: Nielsen — prevenção de erros e recuperação transversais

Fecha os itens ➕ das heurísticas que ainda não foram cobertos pelas tasks anteriores: confirmação em Limpar cache, validação de busca vazia, mensagens de erro humanas com ação de recuperação, persistência de idioma/fonte, estados vazios.

**Files:**
- Modify: `frontend/app.js`
- Modify: `frontend/index.html` (estados vazios / textos de ajuda, se necessário)
- Test: extend `tests/test_frontend_chapters.py`

**Interfaces:** usa `Api.clear_cache`, `Api.enrich_metadata`, eventos `job_error`.

- [ ] **Step 1: Add assertions (TDD) to the frontend test**

Append to `tests/test_frontend_chapters.py`:

```python
def test_appjs_has_nielsen_safeguards():
    js = (FRONT / "app.js").read_text(encoding="utf-8")
    # #5 prevenção: confirmação ao limpar cache
    assert "confirm(" in js
    # #6 reconhecer: persiste idioma/fonte
    assert "localStorage" in js
    # #9 recuperação: handler de job_error mostra mensagem amigável
    assert 'on("job_error"' in js
    # #7 eficiência: Enter dispara busca
    assert '"Enter"' in js or "keydown" in js
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_frontend_chapters.py::test_appjs_has_nielsen_safeguards -v`
Expected: FAIL.

- [ ] **Step 3: Implement the safeguards in `app.js`**

Add near the relevant handlers:

```javascript
// #5 Prevenção de erro: confirmar limpar cache
// (substituir o handler existente de #btn-cache)
document.getElementById("btn-cache").addEventListener("click", async () => {
  if (!confirm("Limpar todo o cache local de buscas e capítulos?")) return;
  const r = await api().clear_cache();
  alert(`Cache removido: ${r.removed} arquivo(s)`);
});

// #7 Eficiência: Enter no campo de busca dispara a busca
document.getElementById("q").addEventListener("keydown", (e) => {
  if (e.key === "Enter") document.getElementById("btn-search").click();
});

// #6 Reconhecer em vez de lembrar: persistir idioma/fonte/tipo
function persistPrefs() {
  localStorage.setItem("mb_prefs", JSON.stringify({
    lang: langPrimary(), fb: document.getElementById("lang-fallback").value,
    media: document.getElementById("media-type").value,
  }));
}
function restorePrefs() {
  try {
    const p = JSON.parse(localStorage.getItem("mb_prefs") || "{}");
    if (p.lang) document.getElementById("lang-primary").value = p.lang;
    if (p.fb !== undefined) document.getElementById("lang-fallback").value = p.fb;
    if (p.media) document.getElementById("media-type").value = p.media;
  } catch (_) {}
}
["lang-primary", "lang-fallback", "media-type"].forEach((id) => {
  const el = document.getElementById(id);
  if (el) el.addEventListener("change", persistPrefs);
});

// #9 Recuperação: erro amigável
on("job_error", (p) => {
  logEl().textContent += `⚠️ ${p.label}: ${p.error}\n`;
  logEl().scrollTop = logEl().scrollHeight;
  if (p.job_id === currentDownloadJob) {
    document.getElementById("progress-text").textContent = "Falhou — tente novamente.";
    currentDownloadJob = null;
    if (cancelBtn()) cancelBtn().disabled = false;
  }
});
```

Call `restorePrefs()` inside the `pywebviewready` handler (after the elements exist). If an `on("job_error", ...)` handler already exists from a prior task, replace it with this one (keep exactly one).

- [ ] **Step 4: Verify + run tests**

Run: `node --check frontend/app.js`
Expected: válido.
Run: `py -3.13 -m pytest tests/test_frontend_chapters.py tests/test_app_entry.py -v`
Expected: passam.

- [ ] **Step 5: Commit**

```bash
git add frontend/app.js frontend/index.html tests/test_frontend_chapters.py
git commit -m "feat: salvaguardas de Nielsen (confirmação, prefs, recuperação de erro, Enter)"
```

---

## Verificação final (após todas as tasks)

- [ ] `py -3.13 -m pytest -q` — suíte inteira verde.
- [ ] `node --check frontend/app.js` — válido.
- [ ] Verificação manual (humano) em `py -3.13 desktop.py`: buscar → abrir capítulos → idioma/fallback → intervalo marca checkboxes → "Baixar selecionados" desabilitado sem seleção → baixar → **Cancelar para na hora** e reseta → capítulo que falha re-tenta → confirmação ao limpar cache.
