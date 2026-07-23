# Ciclo 1 — ComicInfo.xml + Rate-limit fiel + OutputWriter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CBZ novos passam a conter `ComicInfo.xml` (interop Komga/Kavita) via uma camada `OutputWriter`, com metadados por série do enricher; e o acesso ao MangaDex ganha rate-limiting fiel, tratamento de 429 e re-resolução de URLs expiradas.

**Architecture:** Um novo `OutputWriter` isola a criação do CBZ + ComicInfo. `media_bot.py` busca metadados da série 1x e delega o empacotamento. O `RateLimiter` do `base_scraper` vira token-bucket por host com relógio injetável; `make_request`/`fetch_page` respeitam `Retry-After` no 429; o download de capítulo re-resolve URLs do at-home quando expiram.

**Tech Stack:** Python 3.13, requests, zipfile, xml, pytest.

## Global Constraints

- **Interpretador:** o `python` do PATH está quebrado. Use SEMPRE `py -3.13` (ex.: `py -3.13 -m pytest`).
- **Entrypoint da GUI:** `desktop.py` (não `app.py`).
- **Núcleo estável:** só adicionar parâmetros keyword opcionais; não quebrar CLI/`tests/test_core.py` nem os scrapers archive/gutenberg. Rodar a suíte completa antes de cada commit.
- **Escopo:** ComicInfo.xml só em **novos downloads** (sem backfill).
- **Limites reais do MangaDex (da pesquisa):** `api.mangadex.org` ~5 req/s; host at-home (`*.mangadex.network`) ~40 req/min; URLs de página válidas ~15 min; 429 traz `Retry-After`.
- **Testabilidade de tempo:** o `RateLimiter` e o tratamento de 429 devem aceitar relógio/sleep injetáveis para testes rápidos e determinísticos.
- **Idioma da copy:** pt-br.

---

### Task 1: `OutputWriter` (CBZ + ComicInfo.xml)

**Files:**
- Create: `app/output_writer.py`
- Test: `tests/test_output_writer.py`

**Interfaces:**
- Produces:
  - `class OutputWriter`
  - `OutputWriter.build_comicinfo_xml(meta: dict) -> str` — XML válido; omite campos ausentes; escapa entidades. Chaves de `meta`: `series, number, volume, title, summary, writer, count, page_count, web, language`.
  - `OutputWriter.write_cbz(pages: List[Tuple[str, bytes]], comicinfo: dict, dest_path) -> dict` — escreve `ComicInfo.xml` na raiz + páginas; retorna `{filepath, size, sha256, page_count}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_output_writer.py`:

```python
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from app.output_writer import OutputWriter


def test_build_comicinfo_has_fields_and_escapes():
    xml = OutputWriter().build_comicinfo_xml({
        "series": "Tom & Jerry <manga>", "number": 15, "volume": 2,
        "title": "Cap", "summary": "abc", "writer": "Autor A",
        "count": 120, "page_count": 3, "web": "http://x", "language": "pt-br",
    })
    root = ET.fromstring(xml)  # parse valida o XML e o escaping
    assert root.tag == "ComicInfo"
    got = {child.tag: child.text for child in root}
    assert got["Series"] == "Tom & Jerry <manga>"
    assert got["Number"] == "15"
    assert got["LanguageISO"] == "pt"
    assert got["Manga"] == "YesAndRightToLeft"
    assert got["PageCount"] == "3"


def test_build_comicinfo_omits_missing():
    xml = OutputWriter().build_comicinfo_xml({"series": "S", "number": 1})
    root = ET.fromstring(xml)
    tags = {c.tag for c in root}
    assert "Summary" not in tags
    assert "Writer" not in tags
    assert "Series" in tags


def test_write_cbz_contains_comicinfo_and_pages(tmp_path):
    dest = tmp_path / "cap.cbz"
    result = OutputWriter().write_cbz(
        pages=[("001.jpg", b"aaa"), ("002.jpg", b"bbb")],
        comicinfo={"series": "S", "number": 1, "page_count": 2},
        dest_path=dest,
    )
    assert dest.exists()
    assert result["page_count"] == 2
    assert result["size"] == dest.stat().st_size
    assert len(result["sha256"]) == 64
    with zipfile.ZipFile(dest) as zf:
        names = zf.namelist()
        assert "ComicInfo.xml" in names
        assert "001.jpg" in names and "002.jpg" in names
        ET.fromstring(zf.read("ComicInfo.xml"))  # ComicInfo é XML válido
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_output_writer.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.output_writer'`).

- [ ] **Step 3: Implement `OutputWriter`**

Create `app/output_writer.py`:

```python
"""Camada única de saída: cria o .cbz com ComicInfo.xml na raiz (interop Komga/Kavita)."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple
from xml.sax.saxutils import escape

_LANG_MAP = {"pt-br": "pt", "pt": "pt", "en": "en", "es": "es"}


class OutputWriter:
    def build_comicinfo_xml(self, meta: dict) -> str:
        parts: List[str] = []

        def add(tag: str, value) -> None:
            if value is not None and value != "":
                parts.append(f"  <{tag}>{escape(str(value))}</{tag}>")

        add("Series", meta.get("series"))
        add("Number", meta.get("number"))
        add("Volume", meta.get("volume"))
        add("Title", meta.get("title"))
        add("Summary", meta.get("summary"))
        add("Writer", meta.get("writer"))
        add("Count", meta.get("count"))
        add("PageCount", meta.get("page_count"))
        add("Web", meta.get("web"))
        language = meta.get("language")
        if language:
            add("LanguageISO", _LANG_MAP.get(str(language).lower(), str(language).lower()))
        add("Manga", "YesAndRightToLeft")

        body = "\n".join(parts)
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n'
            f"{body}\n</ComicInfo>\n"
        )

    def write_cbz(self, pages: List[Tuple[str, bytes]], comicinfo: dict, dest_path) -> dict:
        dest_path = Path(dest_path)
        with zipfile.ZipFile(dest_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("ComicInfo.xml", self.build_comicinfo_xml(comicinfo))
            for name, data in pages:
                archive.writestr(name, data)

        raw = dest_path.read_bytes()
        return {
            "filepath": str(dest_path),
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "page_count": len(pages),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.13 -m pytest tests/test_output_writer.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/output_writer.py tests/test_output_writer.py
git commit -m "feat: OutputWriter escreve CBZ com ComicInfo.xml"
```

---

### Task 2: Enricher com autores + integração do OutputWriter no download

**Files:**
- Modify: `app/metadata_enricher.py` (extrair `authors`)
- Modify: `media_bot.py` (buscar `series_meta` 1x; `_download_mangadex_chapter` delega ao OutputWriter)
- Test: `tests/test_comicinfo_integration.py`

**Interfaces:**
- Consumes: `OutputWriter` (Task 1), `MetadataEnricher`.
- Produces:
  - `MetadataEnricher.enrich(...)` retorna também `authors: List[str]`.
  - `MediaBot._download_mangadex_chapter(scraper, chapter_data, series_title, chapter_num, progress_callback=None, should_cancel=None, series_meta=None, language="pt-br")` — usa `OutputWriter.write_cbz` e injeta `ComicInfo.xml`.
  - `MediaBot.download_complete_series` monta `series_meta` 1x via enricher e o repassa (+ `language`) para cada capítulo mangadex.

- [ ] **Step 1: Write the failing test**

Create `tests/test_comicinfo_integration.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_comicinfo_integration.py -v`
Expected: FAIL (`_download_mangadex_chapter` não aceita `series_meta`; cbz sem ComicInfo).

- [ ] **Step 3: Extract authors in the enricher**

In `app/metadata_enricher.py`, in `_from_jikan`, add `authors` to the returned dict:

```python
            "authors": [a.get("name") for a in manga.get("authors", []) if a.get("name")],
```

And in `_from_anilist`'s returned dict add:

```python
            "authors": [],
```

(AniList staff extraction is out of scope; return an empty list so the key always exists.)

- [ ] **Step 4: Delegate to OutputWriter in `_download_mangadex_chapter`**

In `media_bot.py`, add the import near the top:

```python
from app.output_writer import OutputWriter
```

Replace `_download_mangadex_chapter` so it collects pages then delegates:

```python
    def _download_mangadex_chapter(self, scraper, chapter_data, series_title, chapter_num,
                                   progress_callback=None, should_cancel=None,
                                   series_meta=None, language="pt-br"):
        page_urls = chapter_data.get('page_urls') or []
        if not page_urls:
            return {'success': False, 'error': 'MangaDex chapter has no page URLs'}

        chapter_label = self._format_chapter_label(chapter_num)
        filename = f"{self._sanitize_filename(series_title)}_cap_{chapter_label}.cbz"
        output_path = self.base_dir / filename

        pages = []
        try:
            for index, page_url in enumerate(page_urls, 1):
                if should_cancel is not None and should_cancel():
                    raise RuntimeError("cancelled")
                content = scraper.fetch_page(page_url, should_cancel=should_cancel)
                suffix = Path(urlparse(page_url).path).suffix or '.jpg'
                pages.append((f"{index:03d}{suffix}", content))
                if progress_callback:
                    progress_callback(f"{series_title} cap. {chapter_label}", index, len(page_urls))

            comicinfo = dict(series_meta or {})
            comicinfo.setdefault('series', series_title)
            comicinfo.update({
                'number': chapter_num,
                'volume': chapter_data.get('volume'),
                'title': chapter_data.get('title'),
                'page_count': len(pages),
                'language': language,
            })
            result = OutputWriter().write_cbz(pages, comicinfo, output_path)
            return {
                'success': True,
                'filepath': result['filepath'],
                'file_path': result['filepath'],
                'size': result['size'],
                'hash': result['sha256'],
                'error': None,
                'metadata': {'format': 'cbz', 'size': result['size'], 'sha256': result['sha256']},
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

- [ ] **Step 5: Build `series_meta` once in `download_complete_series`**

In `media_bot.py`, near the top of `download_complete_series` (after `series_reference` is resolved and before the download rounds), add:

```python
        # Metadados da série para o ComicInfo.xml (1x por download; degrada a vazio)
        series_meta = {'series': series_title}
        try:
            from app.metadata_enricher import MetadataEnricher
            enriched = MetadataEnricher(cache=self.cache).enrich(series_title) or {}
            authors = enriched.get('authors') or []
            series_meta.update({
                'summary': enriched.get('synopsis'),
                'writer': ", ".join(authors) if authors else None,
                'count': enriched.get('chapters'),
                'web': series_reference if str(series_reference).startswith('http') else None,
            })
        except Exception:
            pass
```

Then in `_attempt_chapter` (which calls `_download_mangadex_chapter`), pass `series_meta=series_meta, language=language` through. Update `_attempt_chapter`'s signature to accept `series_meta=None` and thread it, and update the call site in the round/fallback loops to pass `series_meta`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `py -3.13 -m pytest tests/test_comicinfo_integration.py tests/test_download_cancel.py tests/test_download_retry_select.py tests/test_metadata_enricher.py tests/test_core.py -v`
Expected: passam, sem regressão (o teste de cancelamento entre páginas continua válido).

- [ ] **Step 7: Commit**

```bash
git add app/metadata_enricher.py media_bot.py tests/test_comicinfo_integration.py
git commit -m "feat: ComicInfo.xml nos CBZ novos com metadados da série"
```

---

### Task 3: `RateLimiter` token-bucket + 429 (base scraper)

**Files:**
- Modify: `scrapers/base_scraper.py`
- Test: `tests/test_rate_limiter.py`

**Interfaces:**
- Produces:
  - `RateLimiter(time_fn=time.time, sleep_fn=time.sleep)` — mantém `wait(url)` e adiciona token-bucket por host: `api.mangadex.org` → (5, 1.0s); host que termina em `mangadex.network` → (40, 60.0s).
  - `BaseScraper.make_request(...)` — no HTTP 429, lê `Retry-After` e aguarda antes de re-tentar (sem estourar `max_retries`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_rate_limiter.py`:

```python
from scrapers.base_scraper import RateLimiter


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds  # o sono avança o relógio


def test_token_bucket_throttles_after_cap():
    clock = FakeClock()
    rl = RateLimiter(time_fn=clock.time, sleep_fn=clock.sleep)
    # zera o delay fixo para isolar o token-bucket
    rl.delays = {"default": 0.0}
    url = "https://api.mangadex.org/manga"
    # 5 req/s: a 6ª deve forçar um sleep
    for _ in range(5):
        rl.wait(url)
    rl.wait(url)
    assert clock.slept, "a 6ª requisição no mesmo segundo deveria aguardar"


def test_different_hosts_have_independent_budgets():
    clock = FakeClock()
    rl = RateLimiter(time_fn=clock.time, sleep_fn=clock.sleep)
    rl.delays = {"default": 0.0}
    for _ in range(5):
        rl.wait("https://api.mangadex.org/manga")
    # outro host não deve ter sido afetado (nenhum sleep ainda p/ 1ª dele)
    before = len(clock.slept)
    rl.wait("https://cmdxd98.mangadex.network/data/abc/1.jpg")
    assert len(clock.slept) == before
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_rate_limiter.py -v`
Expected: FAIL (`RateLimiter()` não aceita `time_fn`; sem token-bucket).

- [ ] **Step 3: Implement token-bucket in `RateLimiter`**

In `scrapers/base_scraper.py`, replace the `RateLimiter` class with:

```python
class RateLimiter:
    """Rate limiter por domínio: delay mínimo + token-bucket por janela."""

    def __init__(self, time_fn=time.time, sleep_fn=time.sleep):
        self._time = time_fn
        self._sleep = sleep_fn
        self.domains = {}  # domain -> last_request_time
        self.delays = {
            'default': 1.0,
            'mangadex.org': 2.0,
            'archive.org': 1.5,
            'gutenberg.org': 2.0,
            'nyaa.si': 3.0,
        }
        self._hits = {}  # host -> list[timestamp]

    def _window_for(self, host: str):
        if host == 'api.mangadex.org':
            return (5, 1.0)
        if host.endswith('mangadex.network'):
            return (40, 60.0)
        return None

    def wait(self, url: str):
        domain = urlparse(url).netloc

        # 1) delay mínimo fixo por domínio (comportamento existente)
        delay = self.delays.get(domain, self.delays['default'])
        if domain in self.domains:
            elapsed = self._time() - self.domains[domain]
            if elapsed < delay:
                self._sleep(delay - elapsed)
        self.domains[domain] = self._time()

        # 2) token-bucket por janela para hosts com limite conhecido
        window = self._window_for(domain)
        if window:
            max_req, seconds = window
            hits = self._hits.setdefault(domain, [])
            now = self._time()
            hits[:] = [t for t in hits if now - t < seconds]
            if len(hits) >= max_req:
                sleep_for = seconds - (now - hits[0])
                if sleep_for > 0:
                    self._sleep(sleep_for)
                now = self._time()
                hits[:] = [t for t in hits if now - t < seconds]
            hits.append(self._time())
```

(Keep the existing module-level `import time`; the class now routes time through `self._time`/`self._sleep`.)

- [ ] **Step 4: Handle 429 in `make_request`**

In `scrapers/base_scraper.py`, update `make_request` to check for 429 before `raise_for_status`:

```python
    def make_request(self, url: str, params: Dict = None, retries: int = 0) -> Optional[requests.Response]:
        try:
            self.rate_limiter.wait(url)
            response = self.session.get(url, params=params, timeout=self.timeout)

            if response.status_code == 429 and retries < self.max_retries:
                retry_after = response.headers.get('Retry-After')
                try:
                    wait_time = float(retry_after) if retry_after is not None else self.retry_backoff ** retries
                except (TypeError, ValueError):
                    wait_time = self.retry_backoff ** retries
                logger.warning(f"429 recebido para {url}. Aguardando {wait_time}s (Retry-After)")
                time.sleep(wait_time)
                return self.make_request(url, params, retries + 1)

            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            if retries < self.max_retries:
                wait_time = self.retry_backoff ** retries
                logger.warning(f"Tentativa {retries + 1} falhou para {url}: {e}. Aguardando {wait_time}s")
                time.sleep(wait_time)
                return self.make_request(url, params, retries + 1)
            logger.error(f"Falha após {self.max_retries} tentativas para {url}: {e}")
            return None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.13 -m pytest tests/test_rate_limiter.py tests/test_mangadex_language.py tests/test_core.py -v`
Expected: passam, sem regressão.

- [ ] **Step 6: Commit**

```bash
git add scrapers/base_scraper.py tests/test_rate_limiter.py
git commit -m "feat: rate limiter token-bucket por host e Retry-After no 429"
```

---

### Task 4: `fetch_page` 429 + re-resolução de URLs expiradas (MangaDex)

**Files:**
- Modify: `scrapers/mangadex_scraper.py`
- Modify: `media_bot.py` (re-resolução no `_download_mangadex_chapter`)
- Test: `tests/test_mangadex_reresolve.py`

**Interfaces:**
- Produces:
  - `MangaDexScraper.fetch_page(...)` — respeita `Retry-After` no 429; ao esgotar, levanta a última exceção (com `response` quando HTTPError).
  - `MangaDexScraper.reresolve_pages(chapter_id: str) -> List[str]` — re-chama `get_chapter_download_url` + `build_page_urls`, retornando novas URLs (lista vazia em falha).
  - `MediaBot._download_mangadex_chapter` — se uma página falha com 403/404/410 (URL expirada), re-resolve **uma vez** via `chapter_data['chapter_id']` e continua nas páginas restantes.

- [ ] **Step 1: Write the failing test**

Create `tests/test_mangadex_reresolve.py`:

```python
import tempfile
from pathlib import Path

import requests

from media_bot import MediaBot


def make_bot():
    return MediaBot(base_download_dir=str(Path(tempfile.mkdtemp()) / "dl"))


def test_reresolve_on_expired_url_completes_chapter():
    bot = make_bot()
    try:
        state = {"reresolved": False}

        class FakeScraper:
            def fetch_page(self, url, should_cancel=None, max_attempts=3):
                if url.startswith("old/") and "2" in url:
                    resp = requests.Response()
                    resp.status_code = 410
                    err = requests.exceptions.HTTPError("expired")
                    err.response = resp
                    raise err
                return b"img"

            def reresolve_pages(self, chapter_id):
                state["reresolved"] = True
                return ["new/1.jpg", "new/2.jpg"]

        chapter_data = {"page_urls": ["old/1.jpg", "old/2.jpg"],
                        "download_type": "mangadex_cbz", "chapter_id": "abc"}
        result = bot._download_mangadex_chapter(FakeScraper(), chapter_data, "S", 1.0)
        assert state["reresolved"] is True
        assert result["success"] is True
    finally:
        bot.cleanup()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m pytest tests/test_mangadex_reresolve.py -v`
Expected: FAIL (sem `reresolve_pages`; sem re-resolução no download).

- [ ] **Step 3: Add 429 handling + `reresolve_pages` to the scraper**

In `scrapers/mangadex_scraper.py`, update `fetch_page` to honor `Retry-After` on 429, and add `reresolve_pages`:

```python
    def fetch_page(self, page_url, should_cancel=None, max_attempts=3):
        import time
        last_error = None
        for attempt in range(max_attempts):
            if should_cancel is not None and should_cancel():
                raise RuntimeError("cancelled")
            try:
                self.rate_limiter.wait(page_url)
                response = self.session.get(page_url, timeout=60)
                if response.status_code == 429:
                    retry_after = response.headers.get('Retry-After')
                    try:
                        wait_time = float(retry_after) if retry_after is not None else 1.5 ** attempt
                    except (TypeError, ValueError):
                        wait_time = 1.5 ** attempt
                    time.sleep(wait_time)
                    continue
                response.raise_for_status()
                return response.content
            except requests.exceptions.HTTPError as exc:
                last_error = exc
                # URLs expiradas não adiantam re-tentar: propaga para re-resolução
                status = getattr(exc.response, 'status_code', None)
                if status in (403, 404, 410):
                    raise
                time.sleep(1.5 ** attempt)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(1.5 ** attempt)
        raise last_error if last_error else RuntimeError("falha ao baixar página")

    def reresolve_pages(self, chapter_id: str):
        try:
            info = self.get_chapter_download_url(chapter_id)
            return self.build_page_urls(info) if info else []
        except Exception:
            return []
```

(Ensure `import requests` is present at the top of `mangadex_scraper.py` — add it if missing.)

- [ ] **Step 4: Re-resolve in `_download_mangadex_chapter`**

In `media_bot.py`, change the page loop in `_download_mangadex_chapter` to support a one-time re-resolution. Replace the `for index, page_url in enumerate(...)` loop body with an index-based loop:

```python
            urls = list(page_urls)
            reresolved = False
            index = 0
            while index < len(urls):
                if should_cancel is not None and should_cancel():
                    raise RuntimeError("cancelled")
                page_url = urls[index]
                try:
                    content = scraper.fetch_page(page_url, should_cancel=should_cancel)
                except Exception as exc:
                    status = getattr(getattr(exc, 'response', None), 'status_code', None)
                    chapter_id = chapter_data.get('chapter_id')
                    if (status in (403, 404, 410) and not reresolved
                            and chapter_id and hasattr(scraper, 'reresolve_pages')):
                        print("      🔄 URLs expiradas, re-resolvendo…")
                        new_urls = scraper.reresolve_pages(chapter_id)
                        if new_urls and len(new_urls) == len(urls):
                            urls = new_urls
                            reresolved = True
                            continue  # re-tenta o mesmo índice com a URL nova
                    raise
                suffix = Path(urlparse(page_url).path).suffix or '.jpg'
                pages.append((f"{index + 1:03d}{suffix}", content))
                if progress_callback:
                    progress_callback(f"{series_title} cap. {chapter_label}", index + 1, len(urls))
                index += 1
```

(Keep the `comicinfo`/`OutputWriter.write_cbz` block and the `except Exception` cleanup from Task 2. The `pages` list, `output_path`, and labels are unchanged.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.13 -m pytest tests/test_mangadex_reresolve.py tests/test_comicinfo_integration.py tests/test_download_cancel.py tests/test_core.py -v`
Expected: passam, sem regressão (cancelamento entre páginas continua válido — o `should_cancel` é checado no topo do while).

- [ ] **Step 6: Commit**

```bash
git add scrapers/mangadex_scraper.py media_bot.py tests/test_mangadex_reresolve.py
git commit -m "feat: Retry-After e re-resolução de URLs expiradas no download MangaDex"
```

---

## Verificação final (após todas as tasks)

- [ ] `py -3.13 -m pytest -q` — suíte inteira verde.
- [ ] Verificação manual (humano) em `py -3.13 desktop.py`: baixar um capítulo → abrir o `.cbz` gerado em `downloads/` e confirmar que contém `ComicInfo.xml` com Series/Number/LanguageISO; importar no Komga/Kavita e ver os metadados corretos.
