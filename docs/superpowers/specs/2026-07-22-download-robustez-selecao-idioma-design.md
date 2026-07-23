# Download: Cancelamento, Robustez, Seleção de Capítulos e Idioma

**Data:** 2026-07-22
**Status:** Aprovado para implementação
**Base:** decorre do teste real da GUI (PR #2). Constrói sobre a branch `feat/desktop-ui`.

## 1. Objetivo

Resolver problemas encontrados no teste real e ampliar o controle de download:
1. **Cancelar travado** — cancelar um download hoje "prende" porque `should_cancel` só é checado no início de cada capítulo.
2. **Capítulos com erro** — falhas de página derrubam o capítulo e são apenas ignoradas; faltam re-tentativas exaustivas.
3. **Seleção de capítulos** — hoje só é possível baixar "todos os faltantes"; o usuário quer ver a lista e escolher (tudo / intervalo / checkboxes).
4. **Idioma + fallback** — busca/baixa fixo em pt-br; usuário quer escolher idioma (pt-br, en, es) e um idioma secundário de fallback por capítulo.

Não-objetivos: downloads concorrentes; fontes além de MangaDex para este fluxo; tradução de conteúdo.

## 2. Contexto atual (código)

- `media_bot.py::download_complete_series(series, media_type, source_name, skip_existing, progress_callback, should_cancel)` — enumera capítulos disponíveis, calcula faltantes, baixa cada um. `should_cancel()` é checado só no topo do loop de capítulos. Entre capítulos há `time.sleep(2)` fixo. Falhas incrementam `failed_count` e seguem.
- `media_bot.py::_download_mangadex_chapter(...)` — baixa **todas as páginas** de um capítulo em sequência com `scraper.session.get(page_url)` **sem retry por página**; empacota em `.cbz`. Não recebe `should_cancel`.
- `scrapers/mangadex_scraper.py::get_series_info(series_url)` — feed com `translatedLanguage[]: ['pt-br']` **fixo**. `get_chapter_url(series_identifier, chapter_number)` resolve páginas frescas (URLs do at-home server expiram — re-tentar pega URLs novas).
- `app/api.py` — `download_series(series, media_type, source)` baixa todos os faltantes. Não há método para listar capítulos.
- `frontend/app.js` — botão "Baixar" chama `download_series` direto; há botão Cancelar (`cancel_job`), barra de progresso e log ao vivo.

## 3. Design

### 3.1 Correção do cancelamento

**Backend (`media_bot.py`):**
- `_download_mangadex_chapter` recebe `should_cancel: Optional[Callable[[], bool]]` e o checa **entre páginas** (antes de baixar cada página). Ao cancelar: fecha/apaga o `.cbz` parcial e retorna `{'success': False, 'cancelled': True}`.
- Em `download_complete_series`, substituir `time.sleep(2)` por uma espera **interrompível**: laço de `sleep(0.2)` verificando `should_cancel()` a cada iteração; sai imediatamente quando cancelado.
- Manter a checagem de cancel no topo do loop de capítulos.
- `download_complete_series` passa a **retornar** um resumo: `{'total': int, 'downloaded': int, 'failed': int, 'cancelled': bool, 'failed_chapters': [float]}`.

**UI (`frontend/`):**
- Ao clicar **Cancelar**: chamar `cancel_job`, exibir "Cancelando…" e **desabilitar** o botão imediatamente (feedback instantâneo).
- No `job_done` de um download, ler `result.cancelled`: se `true`, status "Download cancelado", barra volta a 0, botão Cancelar some, `currentDownloadJob` limpo. Se `false`, "Download concluído." com resumo (`downloaded/total`, falhas).

### 3.2 Robustez / re-tentativa exaustiva

- **Por página** (`_download_mangadex_chapter`): cada `session.get(page_url)` ganha retry local (3 tentativas, backoff `1.5**n`, respeitando `should_cancel`). Só falha a página após esgotar.
- **Por capítulo** (`download_complete_series`): após a 1ª passada, os capítulos em `failed_chapters` entram em **até 2 rodadas adicionais**, re-chamando `get_chapter_url` (URLs frescas) e re-baixando. Cada rodada respeita `should_cancel` e emite log. Ao final, `failed_chapters` contém só os que realmente não vieram.
- O retry por capítulo usa **sempre o idioma primário** (ver 3.4) — a prioridade é esgotar o idioma escolhido.

### 3.3 Listagem e seleção de capítulos

**Backend (`media_bot.py`):**
- Novo `list_series_chapters(series_title, media_type, source_name, language, fallback_language=None) -> Dict`:
  - `{'title', 'source', 'available': [float], 'downloaded': [float], 'missing': [float], 'by_language': {float: [str]}}`.
  - `available` = união dos números de capítulo disponíveis no idioma primário e (se houver) no fallback; `by_language` mapeia cada número aos idiomas em que existe. `downloaded`/`missing` calculados via `library`.
- `download_complete_series(..., chapters: Optional[List[float]] = None)`: se `chapters` vier, baixa **exatamente** esses (interseção com o disponível); senão, todos os faltantes (comportamento atual).

**Api (`app/api.py`):**
- `list_chapters(series, media_type, source, language, fallback_language)` — assíncrono; emite evento `chapters_list` com o dict acima; retorna `{job_id}`.
- `download_series(series, media_type, source, chapters=None, language='pt-br', fallback_language=None)` — repassa seleção e idiomas.

**UI (`frontend/`):** o botão **Baixar** de um resultado abre um **seletor de capítulos** (nova view/painel):
```
Dandadan — 120 caps (faltam 118)   [idioma: pt-br ▾]  [fallback: nenhum ▾]
[ Baixar tudo (faltantes) ]
Intervalo: de [ 1 ] até [ 50 ]  [Aplicar]     (marca as checkboxes do intervalo)
[x] Cap 1  [x] Cap 2  [ ] Cap 3  ...          (baixados: marcados e desabilitados)
                                   [ Baixar selecionados (N) ]
```
- "Aplicar" do intervalo marca as checkboxes correspondentes (não depende delas para baixar — há também "Baixar intervalo" implícito via seleção).
- "Baixar tudo (faltantes)" e "Baixar selecionados" disparam `download_series` com a lista adequada e trocam para a aba **Downloads**.
- Capítulos já baixados aparecem marcados e travados (não re-baixam).

### 3.4 Idioma primário + fallback

- **Seletores** na UI (no seletor de capítulos e/ou barra de busca): idioma primário `pt-br` (padrão) | `en` | `es`; idioma secundário `nenhum` (padrão) | `pt-br` | `en` | `es`.
- `scrapers/mangadex_scraper.py::get_series_info(series_url, language='pt-br')` e `get_chapter_url(series_identifier, chapter_number, language='pt-br')` passam a aceitar `language` (feed `translatedLanguage[]=[language]`). A assinatura base em `base_scraper.py` ganha `language` opcional (scrapers não-MangaDex ignoram).
- **Prioridade absoluta no primário**: enumeração para o picker e **todas as rodadas de retry** usam o idioma primário. Só depois de esgotar o primário, um capítulo ainda em `failed_chapters` é tentado no **fallback** (resolve `get_chapter_url(..., language=fallback)` e baixa). Isso é uma passada final, por capítulo, apenas se `fallback_language` estiver definido.
- `list_series_chapters` inclui no `available` os capítulos que existem só no fallback (para que sejam selecionáveis), marcados em `by_language`.

## 4. Testes

- `download_complete_series`: cancelamento interrompe entre páginas (mock de scraper com páginas lentas + should_cancel); retorno do resumo (`cancelled`, `downloaded`, `failed_chapters`).
- Retry por capítulo: um capítulo que falha na 1ª e passa na 2ª rodada acaba baixado (mock de `get_chapter_url`/downloader falhando N vezes).
- Retry por página: página falha 2x e passa na 3ª (mock de `session.get`).
- Seleção: `chapters=[1,3]` baixa só 1 e 3; `chapters=None` mantém "todos os faltantes".
- Idioma: `get_series_info(url, language='en')` monta o feed com `translatedLanguage[]=['en']` (mock de `make_request` verifica params); fallback só é acionado após o primário esgotar.
- Api: `list_chapters` emite `chapters_list`; `download_series` repassa `chapters`/`language`/`fallback_language`.
- Frontend: `node --check`; smoke test mantém os tokens da ponte.

## 5. Arquivos tocados

`media_bot.py` (cancel entre páginas, espera interrompível, retorno resumo, retry por capítulo, `list_series_chapters`, `chapters`/idioma no download), `scrapers/mangadex_scraper.py` (idioma no feed, retry por página), `scrapers/base_scraper.py` (assinaturas com `language` opcional), `app/api.py` (`list_chapters`, params novos), `frontend/index.html` + `app.js` + `styles.css` (seletor de capítulos, seletores de idioma, correção do cancelar). Testes em `tests/`.

## 6. Riscos

| Risco | Mitigação |
|-------|-----------|
| Cancel ainda "preso" em espera longa | Espera interrompível + checagem entre páginas |
| Feeds de 2 idiomas dobram chamadas de rede | Cache existente por (série, idioma); fallback só quando há `fallback_language` |
| Lista de 500 checkboxes pesada | Render simples; intervalo reduz necessidade de rolar; sem virtualização em v1 |
| Assinaturas de scraper quebrarem archive/gutenberg | `language` é keyword opcional ignorada por eles |
