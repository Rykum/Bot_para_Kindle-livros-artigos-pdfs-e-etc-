# 🚀 BRAINSTORM V2 — Melhorias (pesquisado)

> Data: 2026-07-23 · Baseado em teste real da GUI (PR #2) + pesquisa de projetos e padrões de referência.
> Complementa o [BRAINSTORM_MELHORIAS.md](BRAINSTORM_MELHORIAS.md) original.

## 🔎 Referências consultadas e o que ensinam

- **Mihon / Tachiyomi** (leitor de mangá, sucessor do Tachiyomi): sistema de **extensões/fontes**, **atualização automática da biblioteca**, **tracking** (MyAnimeList/AniList/Kitsu), leitor configurável (direção de leitura, filtros de cor, temas), migração de biblioteca. → aponta para *fontes plugáveis, auto-update e favoritos*.
- **FMD2 (Free Manga Downloader 2)**: **fila de downloads**, **favoritos**, **auto-download de novos capítulos**, filtros por gênero/autor/status, **multitarefa/múltiplas conexões**, drag-and-drop. → aponta para *fila visual, concorrência e monitoramento*.
- **API do MangaDex**: limite global ~**5 req/s por IP**; endpoint **at-home 40 req/min**; URLs de página do at-home válidas por **~15 min**; **HTTP 429** quando estoura; "não faça 500 requisições onde 1 resolve". → valida nosso retry por página e exige *rate limiting fiel + backoff 429 + re-resolver URLs expiradas*.
- **Komga / Kavita**: o formato de interoperabilidade é o **`ComicInfo.xml` na raiz do arquivo CBZ** (Series, Volume, Writer, etc.). Ferramentas como ComicTagger/komf gravam esse XML. → aponta para *escrever ComicInfo.xml dentro dos nossos CBZ* (muito mais valioso que só organizar pastas).

---

## A. 💡 Funcionalidades

### A1. `ComicInfo.xml` dentro do CBZ (interop real) — 🔴 ALTA
Hoje o `_download_mangadex_chapter` empacota só as imagens. Gravar um `ComicInfo.xml` na raiz do `.cbz` (Series, Number, Volume, Title, Writer, LanguageISO, Web, Count) faz Komga/Kavita/YACReader lerem título, capítulo, autor e capa **automaticamente**. Alimentar com os dados que o `MetadataEnricher` já busca (Jikan/AniList). É o maior ganho de "produto" com baixo esforço.

### A2. Fila de downloads + histórico + favoritos — 🔴 ALTA
Modelar downloads como uma **fila persistente** (SQLite) com estados (`queued/downloading/done/failed/cancelled`), retomável entre sessões. Adicionar **favoritos/watchlist** por série. Base para monitoramento e para a UI de Downloads virar um gerenciador de verdade (como FMD2).

### A3. Rate limiting fiel à API + 429 — 🔴 ALTA (parcial)
Já demos `fetch_page` com retry + `rate_limiter.wait`. Falta: (a) respeitar **at-home 40 req/min** e **global 5 req/s** com um limiter por-host de token-bucket; (b) ler o header `Retry-After` no **429** e dormir o tempo certo; (c) **re-resolver** as URLs do at-home quando expiram (>15 min) em downloads longos. Ataca diretamente o `RemoteDisconnected` que apareceu no teste.

### A4. Downloads concorrentes com teto — 🟡 MÉDIA
Baixar N páginas/capítulos em paralelo com **semáforo** respeitando os limites acima (async `aiohttp` ou `ThreadPoolExecutor`). Ganho grande de velocidade; risco de 429 se não respeitar o teto (por isso depende de A3).

### A5. Monitoramento de novos capítulos + notificações — 🟡 MÉDIA
Para séries favoritas, checar periodicamente o feed e baixar/avisar novos capítulos. Notificação **desktop nativa** (via pywebview/OS) e opcional Telegram/Discord webhook. Combina com A2.

### A6. Verificação de integridade e de-duplicação — 🟡 MÉDIA
Já calculamos SHA-256. Expor: detectar `.cbz` corrompido (zip inválido/0 páginas), re-baixar automaticamente, e evitar duplicatas por hash. Reparo de biblioteca ("verificar e consertar").

### A7. Leitor/preview embutido — 🟢 BAIXA (esforço alto)
Ver o CBZ na própria janela (viewer de imagens paginado). Diferencial forte, mas é um sub-projeto.

### A8. Mais fontes + fallback entre fontes — 🟢 BAIXA
Além de idioma-fallback (já feito), permitir **fonte-fallback** (ex.: se MangaDex não tem, tenta outra). Depende de um registry de conectores (B1).

---

## B. 🧱 Módulo / Arquitetura

### B1. `ConnectorRegistry` (fontes plugáveis) — 🟡 MÉDIA
Registrar scrapers por capacidade (busca, capítulos, download) e descobrir dinamicamente, como Tachiyomi/HakuNeko. Facilita adicionar fontes sem editar o orquestrador. Já há base modular em `scrapers/`.

### B2. Camada de saída única — 🔴 ALTA
Abstrair `download_url` vs `page_urls` vs `downloadable_files` (o brainstorm original já pedia) **e** centralizar a escrita do CBZ+`ComicInfo.xml` (A1) e a exportação Komga num único "OutputWriter". Reduz o acoplamento espalhado hoje no `media_bot.py`.

### B3. Corrigir o `db_manager` singleton global — 🔴 ALTA (dívida técnica)
A `Session` única global é frágil (o `BotService` serial só contorna o sintoma; o `conftest.py` precisou de `reset_db()`). Migrar para **sessão por operação/escopo** (`sessionmaker` + context manager) elimina a classe inteira de bugs de concorrência e de estado compartilhado nos testes.

### B4. Config central (`settings.json`) + perfis — 🟡 MÉDIA
Externalizar: pastas de download/export, idioma padrão, limites de rate, nº de conexões, TTL de cache. Hoje estão hardcoded. Habilita a aba de Configurações (C7).

### B5. Observabilidade — 🟡 MÉDIA
Logs estruturados (JSON), métricas de sucesso/falha por fonte, `health-check` de fontes (do brainstorm original). Torna falhas diagnosticáveis sem ler o console.

### B6. Testes de contrato entre scrapers — 🟡 MÉDIA
Garantir que todo scraper honra `search/get_series_info/get_all_chapters/get_chapter_url` no mesmo formato (o gap `language` em archive/gutenberg mostrou que falta isso). Um teste parametrizado por scraper.

### B7. Processamento assíncrono real — 🟢 BAIXA
Migrar o núcleo de download para `async` (base para A4). Refactor grande; fazer só quando A4 for prioridade.

---

## C. 🎨 UI / UX

### C1. Aba Downloads como gerenciador de fila — 🔴 ALTA
Mostrar a **fila** (A2): itens com título, capítulo, %, estado, e ações por item (pausar/retomar/cancelar/remover). Hoje é só log+barra. É o passo natural depois do que entregamos.

### C2. Biblioteca rica — 🟡 MÉDIA
Nos cards (já com capa): badge de **atualização disponível**, ordenar/filtrar (por % completo, status, idioma), busca dentro da biblioteca, ação "atualizar todas".

### C3. Busca avançada — 🟡 MÉDIA
Filtros por status/ano/gênero (quando a fonte expõe), ordenação, e **preview** do resultado (capa + sinopse do enricher) antes de baixar.

### C4. Configurações — 🟡 MÉDIA
Aba ligada a B4: idioma padrão, pastas, limites de rate/conexões, tema, TTL de cache, on/off de notificações. Fecha a heurística de Nielsen #7 (flexibilidade).

### C5. Acessibilidade + i18n — 🟡 MÉDIA
Navegação por teclado completa, contraste AA verificado, `aria-*` nos controles, e estrutura para **múltiplos idiomas de interface** (pt-br/en/es) — coerente com a feature de idioma de conteúdo.

### C6. Tema claro/escuro + densidade — 🟢 BAIXA
Alternar tema (hoje só escuro) e densidade da grade de capítulos para telas menores.

### C7. Onboarding e feedback de progresso fino — 🟢 BAIXA
Primeiro uso guiado; e progresso por capítulo/página mais detalhado ("cap 5/118 · página 12/20 · re-tentando…"), reforçando Nielsen #1.

---

## 📊 Priorização (impacto × esforço)

| Prioridade | Item | Impacto | Esforço |
|-----------|------|---------|---------|
| 🔴 | A1 ComicInfo.xml no CBZ | Alto (interop real) | Baixo |
| 🔴 | A3 Rate limit fiel + 429 + re-resolver URLs | Alto (corrige falhas reais) | Baixo/Médio |
| 🔴 | B3 Corrigir singleton do DB | Alto (dívida técnica) | Médio |
| 🔴 | A2 + C1 Fila de downloads (back + UI) | Alto (vira produto) | Médio/Alto |
| 🔴 | B2 Camada de saída única | Alto (manutenção) | Médio |
| 🟡 | A4 Concorrência com teto | Ótimo (velocidade) | Alto |
| 🟡 | A5 Monitoramento + notificações | Bom | Médio |
| 🟡 | B4/C4 Config central + aba | Bom | Médio |
| 🟡 | B1 ConnectorRegistry | Bom (extensível) | Médio |
| 🟡 | C2/C3 Biblioteca/busca ricas | Bom (UX) | Médio |
| 🟢 | A7 Leitor embutido | Diferencial | Alto |
| 🟢 | C6 Tema claro | Nice-to-have | Baixo |

## 🗺️ Sequência sugerida (próximos ciclos)

1. **Ciclo 1 — "produto de verdade":** A1 (ComicInfo.xml) + A3 (rate limit/429) + B2 (OutputWriter). Baixo esforço, alto valor; resolve interop e as falhas de rede que você viu.
2. **Ciclo 2 — gerenciador de downloads:** A2 (fila persistente) + C1 (UI de fila) + B3 (sessão de DB por escopo) como fundação.
3. **Ciclo 3 — automação:** A5 (monitorar/notificar) + B4/C4 (config) + A4 (concorrência).
4. **Ciclo 4 — polimento/escala:** B1 (connectors), C2/C3 (biblioteca/busca), C5 (a11y/i18n), depois A7 (leitor).

---

**Fontes:** Mihon/Tachiyomi (features de biblioteca/extensões), FMD2 (fila/favoritos/auto-update), API do MangaDex (rate limits 5 req/s e at-home 40/min, URLs 15 min, 429), Komga/Kavita wiki (ComicInfo.xml na raiz do CBZ).
