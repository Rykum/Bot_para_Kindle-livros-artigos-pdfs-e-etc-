# Sistema de design unificado — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Levar o sistema de design da landing (`site/index.html`) para o app desktop, e atualizar a landing com as funcionalidades que ela ainda não menciona.

**Architecture:** Troca de tokens em `frontend/styles.css` — superfícies near-black, bordas em alpha, tipografia Instrument Serif + Inter autohospedada. A landing recebe conteúdo novo sem mudar seu design, que já é a referência.

**Tech Stack:** CSS puro, HTML, fontes WOFF2 autohospedadas, pytest para asserções sobre os arquivos do frontend.

## Global Constraints

- **Sem CDN.** O app é desktop e roda offline. Toda fonte e todo asset ficam em disco. Este é princípio do projeto, não preferência.
- **Interpretador:** `py -3.13`. O `python` do PATH pode estar quebrado.
- **Encoding:** rodar Python com `PYTHONIOENCODING=utf-8`; `media_bot.py` imprime emoji e quebra em cp1252.
- **Testes de frontend** neste projeto afirmam sobre o conteúdo dos arquivos (ver `tests/test_frontend_queue.py`). Seguir esse padrão.
- **Paleta de destino**, copiada da landing, valores exatos:
  `--ink-950:#08090c` · `--ink-900:#0b0d12` · `--ink-850:#0e1117` · `--ink-800:#11151d`
  `--line:rgba(255,255,255,.065)` · `--line-2:rgba(255,255,255,.11)` · `--line-3:rgba(255,255,255,.18)`
  `--tx:#eceef3` · `--tx-2:#98a1b2` · `--tx-3:#616a7b`
  `--blue:#7ea6ff` · `--blue-2:#a8c3ff` · `--blue-soft:rgba(126,166,255,.10)` · `--cream:#e8d5b0`
  `--ok:#5ec9a0` · `--warn:#d7a355` · `--ease:cubic-bezier(.22,.61,.36,1)`

---

### Task 1: Fontes autohospedadas no app

**Files:**
- Create: `frontend/fonts/inter-var-latin.woff2` (cópia de `site/fonts/`)
- Create: `frontend/fonts/instrumentserif-latin.woff2` (cópia de `site/fonts/`)
- Create: `frontend/fonts/instrumentserif-italic-latin.woff2` (cópia de `site/fonts/`)
- Modify: `frontend/styles.css` (topo do arquivo)
- Test: `tests/test_frontend_design.py`

**Interfaces:**
- Consumes: nada.
- Produces: as famílias CSS `'Inter'` e `'Instrument Serif'` disponíveis para as tarefas seguintes.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_frontend_design.py
from pathlib import Path

FRONT = Path(__file__).parent.parent / "frontend"


def test_fonts_are_self_hosted():
    """O app roda offline: nenhuma fonte pode vir de CDN."""
    fontes = FRONT / "fonts"
    assert (fontes / "inter-var-latin.woff2").exists()
    assert (fontes / "instrumentserif-latin.woff2").exists()
    assert (fontes / "instrumentserif-italic-latin.woff2").exists()


def test_css_declares_both_families_locally():
    css = (FRONT / "styles.css").read_text(encoding="utf-8")
    assert "@font-face" in css
    assert "url(fonts/inter-var-latin.woff2)" in css
    assert "url(fonts/instrumentserif-latin.woff2)" in css
    assert "fonts.googleapis.com" not in css
    assert "https://" not in css.split("/* ---------------- Sidebar")[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_frontend_design.py -v`
Expected: FAIL — `frontend/fonts/inter-var-latin.woff2` não existe.

- [ ] **Step 3: Copiar as fontes e declarar as famílias**

```bash
mkdir -p frontend/fonts
cp site/fonts/*.woff2 frontend/fonts/
```

No topo de `frontend/styles.css`, antes do `:root`:

```css
@font-face{
  font-family:'Inter'; font-style:normal; font-weight:100 900; font-display:swap;
  src:url(fonts/inter-var-latin.woff2) format('woff2');
}
@font-face{
  font-family:'Instrument Serif'; font-style:normal; font-weight:400; font-display:swap;
  src:url(fonts/instrumentserif-latin.woff2) format('woff2');
}
@font-face{
  font-family:'Instrument Serif'; font-style:italic; font-weight:400; font-display:swap;
  src:url(fonts/instrumentserif-italic-latin.woff2) format('woff2');
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_frontend_design.py -v`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
git add frontend/fonts frontend/styles.css tests/test_frontend_design.py
git commit -m "feat(ui): fontes Inter e Instrument Serif autohospedadas no app"
```

---

### Task 2: Trocar os tokens de cor e forma

**Files:**
- Modify: `frontend/styles.css:6-41` (bloco `:root`)
- Test: `tests/test_frontend_design.py`

**Interfaces:**
- Consumes: famílias de fonte da Task 1.
- Produces: as variáveis `--ink-950`, `--line`, `--tx`, `--blue`, `--cream` etc., consumidas pelas Tasks 3 e 4. Os nomes antigos (`--bg`, `--surface`, `--text`, `--muted`, `--accent`) permanecem como **apelidos** apontando para os novos, para que nenhuma regra existente quebre nesta tarefa.

- [ ] **Step 1: Write the failing test**

Acrescentar a `tests/test_frontend_design.py`:

```python
def test_tokens_match_the_landing_palette():
    """A paleta do app tem que ser a mesma da landing, valor por valor."""
    css = (FRONT / "styles.css").read_text(encoding="utf-8")
    for token, valor in [
        ("--ink-950", "#08090c"), ("--ink-900", "#0b0d12"),
        ("--ink-850", "#0e1117"), ("--ink-800", "#11151d"),
        ("--tx", "#eceef3"), ("--tx-2", "#98a1b2"), ("--tx-3", "#616a7b"),
        ("--blue", "#7ea6ff"), ("--cream", "#e8d5b0"),
    ]:
        assert f"{token}:{valor}" in css.replace(" ", ""), token


def test_borders_are_alpha_hairlines_not_solid():
    """Bordas sólidas criam 'caixinhas'; a landing usa hairlines em alpha."""
    css = (FRONT / "styles.css").read_text(encoding="utf-8")
    assert "rgba(255,255,255,.065)" in css.replace(" ", "")
    assert "#212c3d" not in css, "cor de borda sólida antiga ainda presente"


def test_old_token_names_still_resolve():
    """Apelidos evitam quebrar as regras existentes nesta etapa."""
    css = (FRONT / "styles.css").read_text(encoding="utf-8").replace(" ", "")
    assert "--bg:var(--ink-950)" in css
    assert "--accent:var(--blue)" in css
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_frontend_design.py -v`
Expected: FAIL — `--ink-950` não existe.

- [ ] **Step 3: Substituir o bloco `:root`**

Trocar o `:root` inteiro de `frontend/styles.css` por:

```css
:root {
  /* superfícies — near-black frio (mesma paleta da landing) */
  --ink-950:#08090c;
  --ink-900:#0b0d12;
  --ink-850:#0e1117;
  --ink-800:#11151d;
  --ink-750:#151a23;

  /* linhas em alpha: hairlines que respiram, nunca "caixinhas" */
  --line:rgba(255,255,255,.065);
  --line-2:rgba(255,255,255,.11);
  --line-3:rgba(255,255,255,.18);

  /* texto — 3 níveis, sem mais */
  --tx:#eceef3;
  --tx-2:#98a1b2;
  --tx-3:#616a7b;

  /* acentos: azul funcional + creme editorial */
  --blue:#7ea6ff;
  --blue-2:#a8c3ff;
  --blue-soft:rgba(126,166,255,.10);
  --cream:#e8d5b0;

  --ok:#5ec9a0;
  --ok-soft:rgba(94,201,160,.12);
  --warn:#d7a355;
  --warn-soft:rgba(215,163,85,.10);
  --danger:#e06666;
  --danger-soft:rgba(224,102,102,.12);

  /* apelidos: mantêm as regras existentes funcionando */
  --bg:var(--ink-950);
  --surface:var(--ink-900);
  --surface-2:var(--ink-850);
  --surface-3:var(--ink-800);
  --border:var(--line);
  --border-soft:var(--line);
  --text:var(--tx);
  --muted:var(--tx-2);
  --faint:var(--tx-3);
  --accent:var(--blue);
  --accent-hover:var(--blue-2);
  --accent-soft:var(--blue-soft);
  --success:var(--ok);
  --success-soft:var(--ok-soft);

  --r-sm:8px; --r-md:12px; --r-lg:18px;
  --shadow:none; --shadow-sm:none;
  --ring:0 0 0 3px var(--blue-soft);
  --ease:cubic-bezier(.22,.61,.36,1);

  --s-1:4px; --s-2:8px; --s-3:12px; --s-4:16px; --s-5:20px; --s-6:24px; --s-8:32px;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_frontend_design.py -v`
Expected: PASS (5 testes).

- [ ] **Step 5: Ver o app com a paleta nova**

Run: `PYTHONIOENCODING=utf-8 py -3.13 desktop.py`
Esperado: o app abre em near-black, sem borda sólida visível. **Olhe a janela.** Tela em branco significa erro de CSS, não sucesso.

- [ ] **Step 6: Commit**

```bash
git add frontend/styles.css tests/test_frontend_design.py
git commit -m "feat(ui): paleta near-black e hairlines em alpha, iguais à landing"
```

---

### Task 3: Tipografia — corpo em Inter, títulos em serifa

**Files:**
- Modify: `frontend/styles.css` (regra `body`, `h1`, `.panel-title`, `.brand`, `.signature`)
- Test: `tests/test_frontend_design.py`

**Interfaces:**
- Consumes: famílias da Task 1, tokens da Task 2.
- Produces: nada que outras tarefas consumam.

- [ ] **Step 1: Write the failing test**

```python
def test_body_uses_inter_and_headings_use_serif():
    css = (FRONT / "styles.css").read_text(encoding="utf-8")
    corpo = css.split("body {")[1].split("}")[0]
    assert "'Inter'" in corpo
    assert "Segoe UI" in corpo, "manter como fallback"
    h1 = css.split("h1 {")[1].split("}")[0]
    assert "'Instrument Serif'" in h1


def test_signature_keeps_the_editorial_italic():
    """'By Munhoz' é assinatura: serifa itálica creme, como na landing."""
    css = (FRONT / "styles.css").read_text(encoding="utf-8")
    assinatura = css.split(".signature b")[1].split("}")[0]
    assert "var(--cream)" in assinatura
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_frontend_design.py::test_body_uses_inter_and_headings_use_serif -v`
Expected: FAIL — `'Inter'` não está na regra `body`.

- [ ] **Step 3: Aplicar a tipografia**

Em `frontend/styles.css`, na regra `body`, trocar a linha `font-family`:

```css
  font-family:'Inter',"Segoe UI",system-ui,-apple-system,sans-serif;
  font-feature-settings:"cv05" 1,"cv11" 1,"ss01" 1;
```

Trocar a regra `h1`:

```css
h1 {
  font-family:'Instrument Serif',Georgia,serif;
  font-weight:400;
  font-size:30px;
  line-height:1.1;
  letter-spacing:-.015em;
  margin:0;
  color:#f6f7fa;
}
```

Trocar a assinatura:

```css
.signature b {
  font-family:'Instrument Serif',Georgia,serif;
  font-style:italic;
  font-weight:400;
  font-size:16px;
  color:var(--cream);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_frontend_design.py -v`
Expected: PASS (7 testes).

- [ ] **Step 5: Rodar a suíte inteira**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest -q`
Expected: todos passam. Nenhum teste de frontend existente deve quebrar — os apelidos da Task 2 garantem isso.

- [ ] **Step 6: Commit**

```bash
git add frontend/styles.css tests/test_frontend_design.py
git commit -m "feat(ui): Inter no corpo, Instrument Serif nos títulos e na assinatura"
```

---

### Task 4: Textura de fundo

**Files:**
- Modify: `frontend/styles.css` (acrescentar regras `body::before` e `body::after`)
- Test: `tests/test_frontend_design.py`

**Interfaces:**
- Consumes: tokens da Task 2.
- Produces: nada.

- [ ] **Step 1: Write the failing test**

```python
def test_background_has_grain_and_glow_like_the_landing():
    css = (FRONT / "styles.css").read_text(encoding="utf-8")
    assert "feTurbulence" in css, "grão ausente"
    assert "radial-gradient" in css, "brilho radial ausente"
    assert "pointer-events:none" in css.replace(" ", ""), \
        "a textura não pode capturar clique"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_frontend_design.py::test_background_has_grain_and_glow_like_the_landing -v`
Expected: FAIL — "grão ausente".

- [ ] **Step 3: Acrescentar a textura**

Depois da regra `body` em `frontend/styles.css`:

```css
/* textura: brilho radial baixo + grão fino, iguais à landing */
body::before{
  content:"";position:fixed;inset:0;z-index:0;pointer-events:none;
  background:
    radial-gradient(820px 480px at 12% -6%, rgba(126,166,255,.09), transparent 62%),
    radial-gradient(680px 420px at 94% 4%, rgba(232,213,176,.04), transparent 60%);
}
body::after{
  content:"";position:fixed;inset:-50%;z-index:0;pointer-events:none;
  opacity:.03;mix-blend-mode:overlay;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='220'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.82' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='220' height='220' filter='url(%23n)'/%3E%3C/svg%3E");
}
#app{position:relative;z-index:1;}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_frontend_design.py -v`
Expected: PASS (8 testes).

- [ ] **Step 5: Ver o app e confirmar que continua clicável**

Run: `PYTHONIOENCODING=utf-8 py -3.13 desktop.py`
Esperado: fundo com grão sutil; **clicar num item da barra lateral ainda troca de tela**. Se não trocar, o `pointer-events:none` ou o `z-index` está errado.

- [ ] **Step 6: Commit**

```bash
git add frontend/styles.css tests/test_frontend_design.py
git commit -m "feat(ui): grão e brilho radial de fundo, iguais à landing"
```

---

### Task 5: Atualizar o conteúdo da landing

**Files:**
- Modify: `site/index.html` (seção `#fontes`, seção `#recursos`, `<meta name="description">`)
- Test: `tests/test_landing_content.py`

**Interfaces:**
- Consumes: nada.
- Produces: nada.

A landing menciona **3 fontes** e desconhece busca por autor, "onde encontrar" e as 6 fontes acrescentadas.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_landing_content.py
from pathlib import Path

SITE = Path(__file__).parent.parent / "site" / "index.html"


def test_landing_lists_every_active_source():
    """A landing é o cartão de visita: não pode anunciar 3 fontes quando há 9."""
    html = SITE.read_text(encoding="utf-8")
    for fonte in ["MangaDex", "Open Library", "Wikisource", "Archive.org",
                  "Project Gutenberg", "OAPEN", "Zenodo", "OpenAlex", "arXiv"]:
        assert fonte in html, f"landing não menciona {fonte}"


def test_landing_mentions_author_search_and_where_to_find():
    html = SITE.read_text(encoding="utf-8")
    assert "por autor" in html.lower()
    assert "onde encontrar" in html.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_landing_content.py -v`
Expected: FAIL — "landing não menciona Open Library".

- [ ] **Step 3: Atualizar a tabela de fontes**

Em `site/index.html`, trocar o `<tbody>` da seção `#fontes`:

```html
<tbody>
  <tr><td>Mangá · Manhwa · HQ</td><td>MangaDex · Archive.org</td><td class="mono">CBZ + ComicInfo.xml</td></tr>
  <tr><td>Livro</td><td>Open Library · Wikisource · Archive.org · Project Gutenberg · OAPEN · Zenodo</td><td class="mono">PDF / EPUB / DJVU</td></tr>
  <tr><td>Artigo</td><td>OpenAlex · arXiv · Archive.org · OAPEN · Zenodo</td><td class="mono">PDF</td></tr>
</tbody>
```

- [ ] **Step 4: Acrescentar dois cards de recurso**

Dentro da `<div class="grid">` da seção `#recursos`, antes do card "Seleção de capítulos honesta":

```html
<div class="card" data-reveal>
  <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
  <h3>Busca por título, autor ou qualquer campo</h3>
  <p>Cada fonte exigiu um caminho próprio: o Archive.org cataloga invertido (<i>"Douglas, John E"</i>), e MangaDex e OpenAlex não aceitam nome em texto livre — é preciso resolver o autor antes.</p>
</div>

<div class="card" data-reveal>
  <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9.5"/><path d="m15 9-4.5 1.5L9 15l4.5-1.5z"/></svg>
  <h3>Onde encontrar, quando ninguém tem</h3>
  <p>Acervo aberto não distribui obra sob direitos autorais. Em vez de lista vazia, o app aponta empréstimo digital, leitura online, bibliotecas físicas próximas e sebos.</p>
</div>
```

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_landing_content.py -v`
Expected: PASS (2 testes).

- [ ] **Step 6: Ver a landing localmente**

```bash
cd site && PYTHONIOENCODING=utf-8 py -3.13 -m http.server 8080 --bind 127.0.0.1
```
Abrir `http://localhost:8080`. **Olhe a página.** Conferir que a tabela não estourou a largura no celular (ela vive dentro de `.table-scroll`).

- [ ] **Step 7: Commit**

```bash
git add site/index.html tests/test_landing_content.py
git commit -m "docs(site): landing atualizada com as 9 fontes, busca por autor e onde encontrar"
```

---

### Task 6: Publicar a landing

**Files:**
- Nenhum arquivo alterado.

**Interfaces:**
- Consumes: Task 5.
- Produces: nada.

- [ ] **Step 1: Rodar a suíte inteira**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest -q`
Expected: todos passam.

- [ ] **Step 2: Publicar**

```bash
npx --yes vercel@latest deploy --prod --yes
```

- [ ] **Step 3: Verificar o que está no ar**

```bash
curl -s https://media-bot-ptbr.vercel.app | grep -c "Open Library"
```
Expected: `1` ou mais. Zero significa que o deploy subiu a versão antiga.

- [ ] **Step 4: Commit**

Nada a commitar; o deploy não gera arquivo. Se o `.vercel/` tiver mudado, ele já está no `.gitignore`.

---

## Notas para quem executar

**Por que os apelidos na Task 2.** `frontend/styles.css` tem ~316 linhas e dezenas de regras usando `--bg`, `--surface`, `--accent`. Trocar tudo de uma vez seria uma tarefa impossível de revisar. Os apelidos deixam a paleta mudar numa tarefa e as regras migrarem depois, se alguém quiser. Não é dívida: é uma camada de compatibilidade que funciona.

**O que NÃO fazer.** Não redesenhar componente por componente nesta rodada. A troca de tokens já muda o app inteiro, porque tudo já consome variáveis. Redesenho de componente é outro trabalho, e não foi pedido.

**Verificação visual é obrigatória** nas Tasks 2, 4 e 5. CSS não tem tipo: teste de arquivo confirma que a regra existe, não que ela está bonita nem que a tela abre. Abra o app e olhe.
