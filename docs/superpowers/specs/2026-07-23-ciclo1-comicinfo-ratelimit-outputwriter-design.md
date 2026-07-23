# Ciclo 1 — ComicInfo.xml + Rate-limit fiel + OutputWriter

**Data:** 2026-07-23
**Status:** Aprovado para implementação
**Base:** branch `feat/desktop-ui` (PR #2). Decorre do [BRAINSTORM_MELHORIAS_V2.md](../../../BRAINSTORM_MELHORIAS_V2.md).
**Escopo confirmado:** ComicInfo.xml **apenas em novos downloads** (backfill fica para depois).

## 1. Objetivo

Três melhorias coesas no caminho de download/saída, de alto valor e baixo/médio esforço:
1. **`OutputWriter`** — camada única que cria o `.cbz` (empacota páginas + escreve `ComicInfo.xml` na raiz). `_download_mangadex_chapter` delega a ela.
2. **`ComicInfo.xml`** dentro de cada CBZ novo, preenchido com metadados da série (Jikan/AniList via `MetadataEnricher`, buscados 1x por série por download). Faz Komga/Kavita/YACReader lerem título/autor/capa automaticamente.
3. **Rate-limit fiel + 429 + URLs expiradas** — honrar os limites reais do MangaDex, respeitar `Retry-After` no 429, e re-resolver URLs do at-home quando expiram. Ataca o `RemoteDisconnected` visto no teste real.

Não-objetivos: backfill de CBZ existentes; ComicInfo em PDF/EPUB (formato é só para CBZ/comics); downloads concorrentes (Ciclo 3).

## 2. Contexto (código atual)

- `media_bot.py::_download_mangadex_chapter` monta o `.cbz` inline (loop de `fetch_page` → `archive.writestr`), sem metadados.
- `scrapers/mangadex_scraper.py`: `get_chapter_download_url(chapter_id)` retorna `{base_url, hash, pages, force_port_443}` (válido ~15 min); `build_page_urls` monta as URLs; `fetch_page(page_url, should_cancel, max_attempts)` já tem retry + `rate_limiter.wait` (Ciclo 0).
- `scrapers/base_scraper.py::RateLimiter` — delay fixo por domínio (`wait(url)`), sem token-bucket nem tratamento de 429. `make_request` tem retry mas não lê `Retry-After`.
- `app/metadata_enricher.py::MetadataEnricher.enrich(title)` → `{title, alternative_titles, status, chapters, volumes, score, synopsis, cover_image}` (cacheado).

## 3. Design

### 3.1 `app/output_writer.py` — `OutputWriter`

```python
class OutputWriter:
    def build_comicinfo_xml(self, meta: dict) -> str: ...
    def write_cbz(self, pages: list[tuple[str, bytes]], comicinfo: dict, dest_path: Path) -> dict: ...
```

- `pages`: lista de `(nome_arquivo, bytes)` já baixados (o download em si continua no chamador, que passa cancel/rate para o scraper).
- `write_cbz` cria o zip com as páginas **e** `ComicInfo.xml` na raiz; retorna `{filepath, size, sha256, page_count}`.
- `build_comicinfo_xml(meta)` gera XML válido (escapando entidades) com os campos abaixo, omitindo os ausentes.

**Campos do ComicInfo.xml** (a partir de `meta`):
`Series` (título da série), `Number` (capítulo), `Volume`, `Title` (título do capítulo), `Summary` (sinopse do enricher), `Writer` (autor, se houver), `LanguageISO` (idioma: pt-br→`pt`, en→`en`, es→`es`), `Count` (total de capítulos do enricher), `Manga` = `YesAndRightToLeft`, `PageCount`, `Web` (URL da série). Namespace/estrutura padrão do Anansi Project (raiz `<ComicInfo>`).

### 3.2 Integração no download (`media_bot.py`)

- No início de `download_complete_series`, buscar **uma vez** os metadados da série via `MetadataEnricher.enrich(series_title)` (degradação a `None` sem quebrar) e guardar num dict base (`series_meta`).
- `_download_mangadex_chapter` passa a: baixar as páginas (como hoje, com `fetch_page`/cancel) para uma lista `(nome, bytes)`, montar o `comicinfo` combinando `series_meta` + dados do capítulo (`Number`, `Volume`, `Title`, `PageCount`, `LanguageISO`), e chamar `OutputWriter.write_cbz(...)`. Cancelamento entre páginas permanece.
- Assinatura ganha `series_meta: Optional[dict] = None` e `language: str = "pt-br"` (para `LanguageISO`).

### 3.3 Rate-limit fiel + 429 + re-resolução (`scrapers/base_scraper.py` + `mangadex_scraper.py`)

- **Token-bucket por host** no `RateLimiter`: além do delay atual, um limite de **taxa por janela** por host — `api.mangadex.org`: ~5 req/s; host do at-home (`*.mangadex.network`/o `base_url` retornado): ~40 req/min. `wait(url)` bloqueia até haver "orçamento". Implementação simples: fila de timestamps por host, aparando os fora da janela.
- **429 handling**: em `make_request` e `fetch_page`, ao receber `status_code == 429`, ler o header `Retry-After` (segundos) e dormir esse tempo (fallback: backoff atual) antes de re-tentar. Não contar 429 como tentativa "gasta" além do razoável.
- **URLs expiradas (at-home)**: `_download_mangadex_chapter` recebe também o `chapter_id`. Se uma página falhar com **403/404/410** (URL expirada) após as re-tentativas, re-resolver **uma vez** via `scraper.get_chapter_download_url(chapter_id)` → novo `base_url`/`hash` → reconstruir as URLs das páginas **restantes** e continuar. Loga "URLs expiradas, re-resolvendo…".

## 4. Testes

- `OutputWriter.build_comicinfo_xml`: campos presentes/omitidos corretamente; XML válido (parse com `xml.etree`), entidades escapadas (título com `&`/`<`).
- `OutputWriter.write_cbz`: o `.cbz` contém `ComicInfo.xml` na raiz + as páginas; retorna hash/size/page_count corretos (ler o zip de volta em `tmp_path`).
- Integração: `_download_mangadex_chapter` (com FakeScraper) produz um cbz que contém `ComicInfo.xml` com `Number` = capítulo e `Series` do `series_meta`.
- `RateLimiter`: token-bucket limita a taxa (simular N chamadas e checar espaçamento mínimo por host com um relógio injetável).
- 429: `make_request`/`fetch_page` com resposta 429 + `Retry-After: 2` dorme ~2s (relógio/sleep mockado) e re-tenta.
- Re-resolução: uma página que retorna 410 dispara `get_chapter_download_url` de novo e completa com as URLs novas (mock).

## 5. Arquivos tocados

`app/output_writer.py` (novo), `media_bot.py` (enricher por série + delegar ao OutputWriter + chapter_id/idioma), `scrapers/base_scraper.py` (token-bucket + 429), `scrapers/mangadex_scraper.py` (429 em fetch_page + re-resolução), testes em `tests/`.

## 6. Riscos

| Risco | Mitigação |
|-------|-----------|
| Enricher lento/offline atrasa o download | Buscar 1x por série, timeout curto, degradar a `None` (ComicInfo sem autor/sinopse ainda é válido) |
| Token-bucket com relógio real deixa testes lentos/frágeis | Injetar um `time_fn`/`sleep_fn` no RateLimiter para testar sem esperar |
| Re-resolução em loop | Re-resolver no máximo 1x por capítulo; se falhar de novo, contar falha (entra no retry por capítulo já existente) |
| ComicInfo com caracteres inválidos | Escapar entidades XML; validar com parse nos testes |
