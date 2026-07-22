# Media Bot Desktop — Interface Web Local (pywebview) + Executável

**Data:** 2026-07-22
**Status:** Aprovado para implementação
**Autor:** Rykum + Claude

## 1. Objetivo

Substituir a GUI Tkinter demonstrativa (`gui_app.py`) por uma **interface desktop moderna** baseada em web (HTML/CSS/JS) rodando em uma janela nativa via **pywebview**, com o núcleo `MediaBot` como backend. Entregar um **executável clicável** (`dist/MediaBot.exe`) para uso sem terminal por usuário não técnico.

Não-objetivos (v1): interface web servida remotamente, autenticação, multiusuário, notificações Telegram/Discord, comparador de qualidade de scans, monitoramento automático de novos capítulos. Esses ficam no roadmap.

## 2. Contexto do código atual

- Núcleo `MediaBot` (`media_bot.py`): fluxo `Search → Filter → DB Check → Download → Register`. Métodos: `search_series`, `download_complete_series(progress_callback)`, `check_collection_status`, `list_library`, `clear_cache`, `print_graph_status`, `get_complete_series_chapters`.
- `LibraryManager`: `list_all_series()`, `get_series_progress(series)` (retorna dict com `completion_percentage`, `chapters_downloaded`, `total_chapters_registered`, `missing_chapters`, `is_complete`, `status`, `title`).
- `CacheManager`: `get(key, max_age_seconds)`, `set(key, value)`, `clear()`.
- Banco: SQLite + SQLAlchemy. `database.db_manager` é **singleton global com uma única Session**.

### Restrição arquitetural crítica

`db_manager` expõe **uma Session compartilhada**. Sessions do SQLAlchemy/SQLite **não são thread-safe**. A GUI Tkinter atual cria um `MediaBot()` novo por ação em threads separadas e chama `cleanup()` (que fecha a Session global) — padrão frágil e sujeito a corrida. O novo design **não** repete isso.

## 3. Arquitetura

```
Janela pywebview (WebView2 no Windows)
  frontend/  (HTML + CSS + JS, SPA sem build, sem CDN)
        │  window.pywebview.api.*   (ponte JS↔Python)
        ▼
  app/api.py        → classe Api exposta ao JS (métodos finos)
  app/bot_service.py → 1 MediaBot vivo + 1 worker-thread serial (fila de jobs)
        ▼
  MediaBot / LibraryManager / scrapers (núcleo intacto)
  + app/metadata_enricher.py (novo)
  + app/komga_exporter.py    (novo)
```

### 3.1 Modelo de concorrência (decisão-chave)

Um **único worker serial** (`threading.Thread` + `queue.Queue`) dentro de `BotService` processa **todas** as operações do bot, uma de cada vez. Consequências:

- Uma única instância `MediaBot` viva durante toda a sessão (criada no worker, usada só por ele). A Session global nunca é acessada de duas threads.
- Métodos da `Api` **não bloqueiam**: enfileiram um job, retornam `{job_id, accepted: true}` imediatamente.
- Progresso, log e mudança de etapa do pipeline são **eventos empurrados** para o JS via `webview.windows[0].evaluate_js("window.pushEvent(...)")`, não valores de retorno.
- Cancelamento: `cancel_job(job_id)` seta um flag cooperativo lido entre capítulos no loop de download.

Alternativa descartada: `MediaBot` por request. Reabriria/fecharia a Session global repetidamente e permitiria corrida entre requests concorrentes.

### 3.2 Serialização de dados

`stdout` do bot (muitos `print`) é capturado via `contextlib.redirect_stdout` no worker e reemitido como eventos de log — preservando o feedback rico existente sem reescrever os `print`. Retornos estruturados (listas de resultados, dicts de progresso) são convertidos para JSON serializável antes de cruzar a ponte.

## 4. Camada de ponte — `app/api.py`

Classe `Api` registrada em `webview.create_window(..., js_api=api)`. Métodos (todos retornam dict serializável):

| Método | Ação |
|--------|------|
| `search(query, media_type)` | enfileira busca; resultados chegam por evento `search_results` |
| `download_series(series, media_type, source)` | enfileira download completo |
| `series_status(series)` | progresso de uma coleção |
| `library()` | lista de séries + progresso (para cards) |
| `dashboard_stats()` | agregados para o Dashboard |
| `enrich_metadata(title, media_type)` | Jikan/AniList → sinopse/capa/status |
| `export_komga(series)` | organiza arquivos no layout Komga/Kavita |
| `clear_cache()` | limpa cache local |
| `graph_status()` | resumo do grafo graphify |
| `cancel_job(job_id)` | cancela job em andamento |

Eventos empurrados ao JS: `log`, `progress` (`{label, current, total}`), `pipeline_stage`, `job_done`, `job_error`, `search_results`, `metrics`.

## 5. Frontend — `frontend/`

SPA sem etapa de build e **sem CDN** (tudo local, requisito de empacotamento offline). Arquivos: `index.html`, `styles.css`, `app.js`, `assets/` (ícone, placeholder de capa embutido como data-URI ou arquivo local).

Design system: tema escuro, paleta slate/blue herdada e modernizada da GUI atual (`#0f172a`/`#111827`/`#2563eb`). Tipografia Segoe UI (nativa Windows). Componentes: sidebar de navegação, cards, tabela/grid, barra de progresso, console de log, badges de etapa do pipeline.

Navegação por abas (estado no `app.js`, sem router externo):

| Aba | Conteúdo |
|-----|----------|
| **Dashboard** | Cards: nº de séries, itens baixados, coleções completas, itens faltantes; distribuição por fonte e por formato |
| **Buscar** | Form (query / tipo de mídia / fonte) → grid de resultados com capa, fonte, formato, botão "baixar série" |
| **Biblioteca** | Cards visuais por série: capa (via enricher), barra de progresso, %, status, ações (ver status, exportar Komga) |
| **Downloads** | Fila e progresso em tempo real + console de log ao vivo |
| **Ferramentas** | Limpar cache, status do grafo graphify, enriquecer metadados |

Acessibilidade mínima: foco visível, contraste AA no tema escuro, navegação por teclado nos botões principais.

## 6. Features novas (v1)

### 6.1 `app/metadata_enricher.py` — `MetadataEnricher`
- Fonte primária: **Jikan** (`https://api.jikan.moe/v4/manga?q=<title>`), sem API key.
- Fallback: **AniList** GraphQL quando Jikan não retorna.
- Retorna: `title`, `alternative_titles`, `status`, `chapters`, `volumes`, `score`, `synopsis`, `cover_image`.
- Resultado cacheado via `CacheManager` (chave `enrich::<title>`, TTL 7 dias).
- Timeouts curtos e degradação graciosa (retorna `None` sem quebrar a UI).

### 6.2 `app/komga_exporter.py` — `KomgaExporter`
- Lê arquivos baixados registrados no DB para a série (`MediaFile.file_path`).
- Organiza em `exports/komga/<série sanitizada>/<Volume NNN | Chapter NNN>/arquivo`.
- Copia (não move) para preservar o original. Idempotente (pula o que já existe).
- Retorna resumo: caminho base, nº de arquivos exportados.

### 6.3 Dashboard
Agrega `library.list_all_series()` + `get_series_progress()`; conta formatos/fontes lendo `MediaFile`/`Series`.

## 7. Empacotamento — `build.py`

- `pyinstaller --onefile --windowed --name MediaBot --add-data "frontend;frontend" --icon assets/icon.ico app.py`.
- `app.py` resolve o caminho de `frontend/` tanto em dev quanto dentro do bundle (`sys._MEIPASS`).
- Saída: `dist/MediaBot.exe`. WebView2 já presente no Windows 11.
- `build.py` documenta o comando e executa o PyInstaller de forma reproduzível.

## 8. Migração de arquivos

```
app/
  __init__.py
  api.py
  bot_service.py
  metadata_enricher.py
  komga_exporter.py
app.py                (novo entrypoint: cria a janela pywebview)
build.py              (gera o .exe)
frontend/
  index.html
  styles.css
  app.js
  assets/
legacy/
  gui_app.py          (Tkinter movido para cá, preservado e funcional)
```

`requirements.txt`: adicionar `pywebview>=5.0` e `pyinstaller>=6.0` (este último só para build). `README.md`: atualizar seção de interface para a nova GUI web + instruções de build do `.exe`.

## 9. Testes

Adicionar em `tests/`:
- `test_metadata_enricher.py`: Jikan/AniList com `requests` mockado; fallback; cache; degradação a `None`.
- `test_komga_exporter.py`: layout de diretórios em `tmp_path`; idempotência; sanitização de nomes.
- `test_bot_service.py`: fila serial processa jobs em ordem; nunca há duas operações simultâneas (assert de exclusão); eventos emitidos.
- `test_api_contract.py`: cada método da `Api` retorna estrutura JSON-serializável esperada (com `BotService` fake/mock).

## 10. Riscos e mitigações

| Risco | Mitigação |
|-------|-----------|
| Session SQLite compartilhada / corrida | Worker serial único (§3.1) |
| pywebview não instalado no ambiente atual | Adicionar a `requirements.txt`; `app.py` dá mensagem clara se ausente |
| APIs externas (Jikan/AniList) fora do ar | Timeout curto + fallback + degradação graciosa |
| Empacotar `frontend/` no bundle | `--add-data` + resolução via `sys._MEIPASS` em `app.py` |
| Downloads longos travando a UI | Operações no worker; UI só recebe eventos |

## 11. Ordem de implementação sugerida

1. `BotService` (worker serial) + testes.
2. `Api` fina sobre o `BotService` + contrato.
3. `app.py` (janela pywebview) + `frontend/` esqueleto (abas + ponte + log/progresso ao vivo).
4. Dashboard + Biblioteca visual.
5. `MetadataEnricher` + capas + testes.
6. `KomgaExporter` + botão de exportação + testes.
7. Mover Tkinter para `legacy/`, atualizar `README.md`/`requirements.txt`.
8. `build.py` + gerar `dist/MediaBot.exe`.
