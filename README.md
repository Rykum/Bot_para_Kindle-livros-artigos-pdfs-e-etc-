# 📚 Media Bot PT-BR

Aplicativo **desktop** para **buscar, baixar e organizar** mangás, livros, HQs, manhwas e artigos — centralizando o download numa biblioteca sua, com metadados prontos para servidores como **Komga/Kavita**.

> Interface moderna (pywebview), fila de downloads persistente, e o núcleo que respeita as fontes (rate-limiting, retry). Desenvolvido *By Munhoz*.

---

## 🚀 Início rápido

```bash
py -3.13 -m pip install -r requirements.txt
py -3.13 desktop.py
```

> Neste ambiente use o launcher **`py -3.13`** (o `python` do PATH pode estar quebrado).

Ou gere o **executável clicável** e rode com duplo-clique:

```bash
py -3.13 build.py      # gera dist/MediaBot.exe
```

---

## ✨ Funcionalidades

### 🔎 Busca em 9 fontes, por título ou autor
- **Buscar por**: **Título** (padrão), **Autor** ou **Qualquer campo** — a preferência fica salva entre sessões.
- **Seletor de idioma na busca** (Qualquer / Português / Inglês / Espanhol) — filtra livros/artigos por idioma; cada resultado mostra o idioma real.
- As fontes são consultadas **em paralelo**, com deduplicação entre elas (por ISBN, identificador ou título+autor) e timeout: fonte lenta ou fora do ar não trava a busca.
- Resultados em cards com capa, fonte e formato.

> Buscar por autor exigiu caminho próprio em cada fonte: o Archive.org cataloga
> invertido (*"Douglas, John E"*), e MangaDex e OpenAlex não aceitam nome em texto
> livre — é preciso resolver o autor antes. Detalhes em `docs/AUDITORIA_FONTES.md`.

### 🧭 "Onde encontrar" — quando nenhuma fonte tem o arquivo
Acervo aberto não distribui obra sob direitos autorais. Em vez de devolver lista
vazia, o app mostra onde a obra pode estar legalmente: **empréstimo digital**
(Open Library, Internet Archive), **leitura online** (HathiTrust, Google Livros),
**bibliotecas físicas próximas** (WorldCat) e **sebos** (Estante Virtual, só em
buscas em português).

### 🧭 Explorar por gênero
Tela de descoberta: escolha um gênero e veja o que existe, sem digitar nada.

- **Mangá e manhwa** — taxonomia oficial do MangaDex (gênero + tema), ordenados
  por seguidores. Manhwa é o mesmo acervo filtrado por idioma de origem coreano.
- **Livro** — Open Library (ordenada por relevância do gênero, com a opção
  "mais lidos agora") e Gutendex (sempre por popularidade de download; não
  tem relevância nem subgênero — refinar por subgênero é só a Open Library),
  concatenadas. Só entra o que tem exemplar baixável.
- **HQ** — Archive.org. Lista curta de propósito: o acervo é irregular e o
  assunto é inconsistente.

### 🎯 Seleção de capítulos (não trava em nada)
- Ao abrir uma série, o app **analisa a quantidade real** e mostra: *"Capítulos 1–200 · N disponíveis · X baixados · faltam Y"*.
- **Baixar tudo (faltantes)**, **intervalo** (de/até, com os limites reais da série), **checkboxes** por capítulo e **faixas rápidas** geradas pela quantidade real (1–50, 51–100, …).
- Botão de **ajuda "?"** explicando o intervalo.

### 🌐 Idioma primário + fallback (mangá)
- Escolha o idioma principal (pt-br/en/es). Se um capítulo não vier nele **após esgotar as re-tentativas**, tenta o **idioma secundário** (opcional).
- Capítulos que só existem em **versão oficial/externa** (fora do MangaDex) não falham calados: o log mostra **o link para ler**.

### ⬇️ Fila de downloads persistente (gerenciador)
- Enfileirar uma série vira **1 item por capítulo**; a fila **sobrevive entre sessões** e **retoma sozinha** ao abrir o app.
- Estado por item (fila / baixando / concluído / falhou / cancelado), com **cancelar / re-tentar / remover**, **pausar/retomar** a fila e **limpar concluídos**.
- Robustez: **retry por página e por capítulo**, **cancelamento que para na hora** (checado entre páginas), rate-limiting fiel às fontes (evita 429/`RemoteDisconnected`) e re-resolução de URLs expiradas.

### 🏷️ Metadados prontos para Komga/Kavita
- Cada **CBZ** novo já sai com **`ComicInfo.xml`** na raiz (Série, Capítulo, Volume, Autor, Idioma…), preenchido com dados do **Jikan/AniList**. Komga/Kavita/YACReader leem tudo automaticamente.
- **Exportação Komga/Kavita** com um clique (organiza em `Série/Chapter NNN/…`).

### 📁 Onde os arquivos ficam
- **Pasta de downloads configurável** (Ferramentas → *Escolher pasta*), com a escolha **salva** entre sessões.
- Botões **"Abrir pasta"** (downloads e export) para achar os arquivos no Explorer.
- Formatos: **CBZ** (mangá/imagens), **PDF/EPUB/DJVU/…** (livros — extensão detectada da fonte).

### 🖥️ Biblioteca e visão geral
- **Biblioteca** em cards com **capa** (Jikan/AniList), progresso e status; ações de **Status** e **Exportar** por série.
- **Dashboard** com totais (séries, itens baixados, coleções completas, faltantes).

### 🎨 UI/UX
- Visual **minimalista**, tema escuro, **ícones SVG** (sem CDN), aplicando as **10 heurísticas de Nielsen** (visibilidade de estado, prevenção/recuperação de erro, confirmações, atalhos, persistência de preferências…).

---

## 🗂️ Tipos de mídia e fontes

| Tipo | Fonte(s) | Formato típico |
|------|----------|----------------|
| `manga`, `manhwa`, `hq` | MangaDex, Archive.org | CBZ |
| `livro` | **Open Library**, **Wikisource**, Archive.org, Project Gutenberg, **OAPEN**, **Zenodo** | PDF / EPUB |
| `artigo` | **OpenAlex**, **arXiv**, Archive.org, Open Library, OAPEN, Zenodo | PDF |

**O que cada fonte acrescenta:**

| Fonte | Papel |
|-------|-------|
| **Open Library** | Camada de **precisão**: resolve título/autor para a obra certa via ISBN e aponta o exemplar no Archive.org. É o que faz `Dune` achar Frank Herbert em vez de *"Dune Buggy Rental"*. |
| **Wikisource** | Literatura em **EPUB de texto transcrito** (pt/en/es), não scan em PDF — o melhor formato para Kindle. |
| **OAPEN** · **Zenodo** | Livros acadêmicos de acesso aberto; o Zenodo tem muita coisa em português que não existe nas outras. |
| **OpenAlex** · **arXiv** | Artigos com PDF aberto. O OpenAlex traz bastante SciELO. |
| **Archive.org** · **Gutenberg** · **MangaDex** | Base original do app. |

> Auditei **30 fontes** por HTTP real antes de escolher estas. O que foi reprovado
> — e por quê — está em **[`docs/AUDITORIA_FONTES.md`](docs/AUDITORIA_FONTES.md)**,
> junto com o plano das fases que faltam.

---

## 💻 CLI (opcional)

Além da interface gráfica, há uma CLI simples:

```bash
py -3.13 media_bot.py search "Dandadan" --media-type manga
py -3.13 media_bot.py search "Machado de Assis" --media-type livro --search-by autor
py -3.13 media_bot.py search "Dom Casmurro" --media-type livro --language pt
py -3.13 media_bot.py download "Dandadan" --media-type manga --source mangadex
py -3.13 media_bot.py status "Dandadan"
py -3.13 media_bot.py library
py -3.13 media_bot.py cache-clear
py -3.13 media_bot.py graph-status
```

---

## 🧱 Arquitetura (visão geral)

- **`desktop.py`** — entrypoint da GUI (pywebview) · **`frontend/`** — SPA local (sem CDN).
- **`app/`** — ponte e serviços:
  - `bot_service.py` — **worker serial** que executa todas as operações do bot (a Session SQLite nunca é tocada por duas threads).
  - `api.py` — ponte JS↔Python + **runner da fila**.
  - `output_writer.py` (CBZ + ComicInfo), `komga_exporter.py`, `metadata_enricher.py` (Jikan/AniList), `settings_store.py`.
- **`media_bot.py`** — orquestra scrapers, download, retry/fallback e biblioteca.
- **`download_queue.py`** — fila persistente (SQLite) · **`database.py`** — modelos + `session_scope`.
- **`scrapers/`** — 9 fontes sob o contrato comum de `base_scraper`. Cada uma declara
  um `SourceCapabilities` (tipos de mídia que atende, modos de busca, se oferece
  download, se exige chave), e o roteamento consulta isso — acrescentar fonte não
  exige editar `if` em lugar nenhum.
- **`app/where_to_find.py`** — destinos legais quando nenhuma fonte tem o arquivo.
- **`library_manager.py`** — biblioteca, itens faltantes, exportação.

Executável via **`build.py`** (PyInstaller `--onefile --windowed`). A GUI antiga em Tkinter fica em `legacy/gui_app.py`.

---

## 🧪 Testes

```bash
py -3.13 -m pytest -q                      # 290 testes (6 exigem rede)
py -3.13 -m pytest -q -m "not network"     # offline
```

---

## ⚠️ Notas

- **Interpretador:** use `py -3.13`.
- **Aviso legal:** ferramenta de organização/pesquisa. Baixe apenas conteúdo disponível legalmente e respeite os direitos autorais e os termos de uso das fontes.
- Fontes de mangá com API aberta e estável são escassas — o app usa o **MangaDex** (a mais confiável). Capítulos apenas "oficiais/externos" não são baixáveis de forma estável em lugar nenhum; nesses casos o app informa o link.

---

*Media Bot PT-BR — By Munhoz.*
