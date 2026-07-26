# Auditoria de fontes e spec de expansão da biblioteca

> Objetivo: sair de **3 fontes** (MangaDex, Archive.org, Gutenberg) para uma malha
> ampla de acervos abertos, e — quando a obra não existir legalmente em lugar
> nenhum — **dizer onde ela pode estar** em vez de simplesmente falhar.

Data da auditoria: **26/07/2026** · Autor: *By Munhoz*

> **Revisada em 26/07/2026 após a implementação das Fases 1 a 5.** Três coisas que
> só apareceram ao escrever o código estão corrigidas abaixo e marcadas com
> ⚠️: o **DOAB foi reprovado**, as fontes de API precisaram de **cabeçalhos
> próprios**, e o **arXiv exigiu rate-limit específico**. Ver a seção 10.

---

## 1. Método

Cada candidata foi chamada por **HTTP real**, sem chave, com `User-Agent` próprio
e depois com `User-Agent` de navegador quando houve bloqueio. Registrei código de
status, `content-type` e uma amostra parseada do corpo. Nenhuma fonte entrou nesta
spec por reputação: **só entra o que respondeu**.

Consultas de teste: `Dom Casmurro`, `Machado de Assis`, `brasil`, `casmurro`.

Reprodução: os scripts de sondagem estão descritos na seção 8.

---

## 2. Resultado da auditoria

### 2.1 Aprovadas — funcionam sem chave

| Fonte | HTTP | O que devolveu | Serve para |
|---|---|---|---|
| **Open Library** | 200 | 83 obras p/ "Dom Casmurro"; campo `ia` presente | Metadados, ISBN, ponte p/ Archive.org |
| **Internet Archive** | 200 | *já integrado* | Livros, HQ, artigos |
| **Project Gutenberg** (Gutendex) | 200 | *já integrado* | Livros de domínio público |
| **MangaDex** | 200 | *já integrado* | Mangá, manhwa |
| **Wikisource PT** | 200 | 2.230 páginas p/ "Machado de Assis" | Obras transcritas em português |
| ~~**DOAB**~~ ⚠️ | 200 | 100 itens **ocos** — ver seção 10 | **Reprovado na implementação** |
| **OAPEN** | 200 | 100 itens | Livros acadêmicos de acesso aberto |
| **HathiTrust** (Bib API) | 200 | registro por OCLC | *Só metadados/disponibilidade* |
| **OpenAlex** | 200 | 59.381 obras | Artigos e metadados acadêmicos |
| **arXiv** | 200 | 3 entradas Atom | Artigos (exatas, computação) |
| **Zenodo** | 200 | 193.634 registros | Publicações e dados abertos |
| **Gallica** (BnF) | 200 | 3 registros SRU | Acervo histórico digitalizado |
| **OpenStax** | 200 | 129 livros | Livros didáticos abertos |
| **ManyBooks** | 200 | HTML 163 KB | Domínio público *(exige scraping)* |
| **Comic Book Plus** | 200 | HTML 115 KB | HQ de domínio público *(exige scraping)* |
| **SciELO Livros** | 200 | HTML 78 KB *(OPDS vazio)* | Livros acadêmicos PT *(exige scraping)* |
| **Brasiliana USP** | 200 | HTML 37 KB *(sem REST)* | Acervo histórico BR *(exige scraping)* |

### 2.2 Exigem chave de API

| Fonte | HTTP | Observação |
|---|---|---|
| Google Books | 429 | Funciona sem chave, mas com limite muito baixo |
| Europeana | 400 | Chave gratuita, cadastro simples |
| DPLA | 403 | Chave gratuita por e-mail |
| CORE | timeout | Chave gratuita; agregador enorme de OA |
| Biodiversity Heritage Library | 401 | Chave gratuita |

### 2.3 Reprovadas — bloqueadas ou sem API pública

| Fonte | HTTP | Diagnóstico |
|---|---|---|
| **Domínio Público (MEC)** | 403 | WAF bloqueia inclusive com `User-Agent` de navegador. O formulário existe, a resposta não vem. **Maior perda desta auditoria** — era a fonte com mais acervo em português |
| **BN Digital Brasil** | 403 | Mesmo bloqueio |
| Standard Ebooks | 401 | OPDS passou a exigir autenticação; alternativa é o repositório público |
| DOAJ | 403 | Bloqueia por `User-Agent` |
| Library of Congress | 403 | `fo=json` documentado, mas bloqueado |
| Feedbooks | 403 | Bloqueado |
| LibriVox | 404 | API mudou de endereço |
| Digital Comic Museum | 403 | Bloqueado |

> **Nota:** bibliotecas-sombra (LibGen, Anna's Archive, Z-Library e similares) ficam
> **fora desta spec por decisão de projeto**, coerente com o aviso legal do README.
> Elas não são um item pendente — são um item recusado.

---

## 3. O gargalo real não é a quantidade de fontes

A auditoria confirmou o que os testes de busca já indicavam: **o problema não é
falta de fonte, é obra sob direitos autorais**. Nenhuma das 17 fontes aprovadas
distribui best-seller recente. Adicionar 14 fontes novas amplia muito o acervo de
**domínio público, acadêmico e histórico** — e quase nada o de lançamentos.

Por isso a seção 6 (**"onde encontrar"**) não é um detalhe: é o que responde ao
caso que as fontes não resolvem.

---

## 4. Arquitetura proposta

### 4.1 Problema com o desenho atual

Hoje `MediaBot.__init__` instancia três scrapers numa lista fixa e
`search_series` percorre essa lista **em série**. Com 17 fontes isso significa
17 chamadas sequenciais com rate-limit — busca de dezenas de segundos.

Além disso, `BaseScraper` exige `get_all_chapters` e `get_chapter_url`, que só
fazem sentido para obra seriada. Uma fonte de livro único é forçada a implementar
métodos vazios.

### 4.2 Mudanças

**a) Contrato em camadas.** Separar `BaseScraper` em:

- `SearchableSource` — só `search()` e `get_series_info()`
- `SerialSource(SearchableSource)` — acrescenta `get_all_chapters()` e
  `get_chapter_url()`, para MangaDex e afins

Fontes de livro implementam só a primeira. Elimina o método vazio obrigatório.

**b) Registro com capacidades.** Trocar a lista fixa por um registro declarativo:

```python
@dataclass(frozen=True)
class SourceCapabilities:
    media_types: frozenset[str]     # {"livro", "artigo", "manga"...}
    search_modes: frozenset[str]    # {"titulo", "autor", "tudo"}
    languages: frozenset[str]       # {"pt", "en", "es"} ou vazio = qualquer
    needs_api_key: bool = False
    provides_download: bool = True  # HathiTrust e Open Library = False
    scraping_required: bool = False # HTML, sem API — mais frágil
```

`search_series` passa a filtrar por capacidade em vez de por nome
(`_scraper_applicable` hoje compara `scraper.name` com literais — não escala).

**c) Busca concorrente.** Fan-out com `ThreadPoolExecutor`, timeout por fonte
(sugestão: 12 s) e resultado parcial. Uma fonte lenta ou fora do ar **não pode**
travar a busca inteira. O rate-limit continua por fonte, dentro de cada scraper.

> Atenção: o `bot_service` é um worker **serial** de propósito, para a Session do
> SQLite nunca ser tocada por duas threads. A concorrência fica **dentro** da
> busca, que é só rede — nenhuma thread nova toca o banco.

**d) Deduplicação entre fontes.** Com 17 fontes o mesmo livro volta várias vezes.
Chave de dedupe, em ordem de confiança: `ISBN` → `OpenLibrary ID` → título
normalizado (sem acento, minúsculo) + primeiro sobrenome do autor. Ao fundir,
manter a versão **com download disponível** e maior qualidade de formato
(EPUB > PDF > DJVU).

**e) Fontes ligáveis/desligáveis.** Persistir em `settings_store` quais fontes
estão ativas e as chaves de API. Quem não quer esperar por 17 fontes desliga o que
não usa.

---

## 5. Plano de implementação

Ordenado por **ganho ÷ esforço**, com o que cada fase entrega.

### Fase 1 — Precisão (a base de tudo)
- **Open Library** como camada de resolução: título/autor → ISBN → identificador
  do Archive.org.
- Resolve o problema em aberto dos testes: `Dune` e `1984` sozinhos não acham o
  livro certo. Com desambiguação por ISBN, acham.
- **Não é mais uma fonte de download** — é o que torna as outras precisas.

### Fase 2 — Arquitetura
- Contrato em camadas, registro com capacidades, busca concorrente, dedupe.
- Sem isso, cada fonte nova custa mais que a anterior.

### Fase 3 — Acervo em português
- **Wikisource PT** (API estável, obras transcritas)
- **SciELO Livros** e **Brasiliana USP** (scraping, mais frágeis)
- Maior ganho de literatura brasileira disponível legalmente.

### Fase 4 — Acadêmico e aberto
- **DOAB**, **OAPEN**, **OpenStax**, **Zenodo**
- APIs limpas, sem chave, baixo custo de integração.

### Fase 5 — Artigos
- **OpenAlex**, **arXiv**
- O tipo `artigo` hoje só tem Archive.org; passa a ter cobertura real.

### Fase 6 — Histórico e HQ
- **Gallica**, **Comic Book Plus**, **ManyBooks**
- Scraping em dois dos três: só depois que a arquitetura estiver firme.

### Fase 7 — Com chave (opcional)
- **Google Books**, **CORE**, **Europeana**, **DPLA**, **BHL**
- Exigem cadastro; ficam desligadas por padrão, o usuário liga se quiser.

---

## 6. "Onde encontrar" — quando nada tem para baixar

Comportamento novo, disparado quando a busca acha a obra mas **nenhuma fonte
oferece download**. Em vez de lista vazia, o app mostra um cartão com:

| Destino | O que informa |
|---|---|
| **Open Library / Archive.org** | Se existe para **empréstimo digital** legal |
| **HathiTrust** | Se há visão completa ou só busca interna |
| **Google Books** | Prévia, e se há venda |
| **WorldCat** | **Bibliotecas físicas próximas** que têm o exemplar |
| **Biblioteca pública / universitária** | Link direto ao catálogo, quando aplicável |

Isso reaproveita um padrão que o app **já usa**: capítulo externo do MangaDex hoje
mostra o link para ler em vez de falhar calado. Aqui é a mesma ideia, para livro.

Ganho extra: HathiTrust e Open Library já estão aprovados na auditoria e servem
exatamente para isso, mesmo sem oferecer download.

---

## 7. Riscos

| Risco | Mitigação |
|---|---|
| Scraping de HTML quebra quando o site muda | Marcar `scraping_required=True`; falha de uma fonte não derruba a busca; teste de contrato por fonte |
| Busca fica lenta com 17 fontes | Fan-out concorrente + timeout por fonte + fontes desligáveis |
| Resultado duplicado e confuso | Dedupe por ISBN/OL-ID antes de exibir |
| Fonte bloqueia por excesso de acesso | `RateLimiter` já existe por scraper; respeitar `Retry-After` |
| Chaves de API vazando no repositório | Guardar em `settings_store`, nunca em código; `.gitignore` já cobre |
| Fontes bloqueadas hoje voltarem a funcionar | Re-rodar a auditoria periodicamente; ela é um script, não um documento morto |

---

## 8. Como repetir a auditoria

As sondagens foram feitas com um script de uso único. Recomendação: promovê-lo a
`tests/test_fontes_disponiveis.py`, marcado como teste de rede
(`@pytest.mark.network`), **fora da suíte padrão**, rodado sob demanda:

```bash
py -3.13 -m pytest -m network -q
```

Assim a lista da seção 2 deixa de ser uma foto de 26/07/2026 e passa a ser
verificável a qualquer momento — que é o que impede uma spec de envelhecer calada.

---

## 10. ⚠️ Correções vindas da implementação

Três descobertas que a sondagem não pegou. Todas têm a mesma lição: **medir a
resposta não basta, é preciso usar a resposta**.

### 10.1 DOAB reprovado — contei itens sem olhar dentro

A sondagem original contou **100 itens** e aprovou. Ao escrever o scraper, os
itens se revelaram **ocos**: mesmo no endpoint do item completo,
`dc.title` vem `None` e `bitstreams: 0`. Não há título nem arquivo.

O erro foi de método: `len(resposta)` não é evidência de conteúdo utilizável.
A auditoria agora exige inspecionar **um item inteiro**, não só contar.

### 10.2 Fontes de API precisam de cabeçalho próprio

O `BaseScraper` se identifica como Chrome pedindo `text/html` — sensato para
site, destrutivo para API, de dois jeitos diferentes:

- **Zenodo** responde **403** a User-Agent de navegador
- **OAPEN** (DSpace) honra o `Accept: text/html` e devolve **HTML**, não JSON

As duas ficavam **silenciosamente vazias**: sem erro, sem resultado. Como os
testes usavam mock, passavam todos. Só a busca real expôs.

Solução: `BaseScraper.use_api_headers()`, adotado por Open Library, Wikisource,
OAPEN, Zenodo e OpenAlex. Há teste de regressão que falha se alguma delas voltar
a se passar por navegador. Bônus: a política de User-Agent da Wikimedia **exige**
identificação descritiva — estávamos violando.

### 10.3 arXiv exige rate-limit próprio e HTTPS

Devolvia **429** e zero resultados, por duas causas somadas: o endereço em `http`
redireciona, e cada re-tentativa da cadeia contava como chamada nova; e o delay
padrão de 1 s é mais agressivo que a política do arXiv (~3 s).

### 10.4 Busca por autor: o mesmo defeito, em três fontes

Padrão que se repetiu e vale como regra para fontes futuras — **toda busca por
autor casa palavra a palavra até que se prove o contrário**:

| Fonte | Sintoma | Solução |
|---|---|---|
| Archive.org | `creator:(John Douglas)` → 1331 itens, com Krakatoa no topo | frase entre aspas + as duas ordens do nome |
| OpenAlex | `raw_author_name.search` → 1854 artigos de psiquiatria | resolver em `/authors` e filtrar por `author.id` |
| MangaDex | não aceita nome em texto livre | resolver em `/author` e filtrar por `authors[]` |

### 10.5 Orçamento de tempo da busca

Medido por fonte na mesma consulta: **OAPEN 11,0 s**, Zenodo 3,4 s, Archive.org
1,9 s, OpenAlex 1,7 s, Open Library 1,2 s, Wikisource 0,7 s, Gutenberg 0,4 s,
arXiv 0,3 s.

Com o teto de 20 s, OAPEN e Zenodo eram descartados a cada busca. Baixar o
`rows` do OAPEN para 10 e subir o teto para 30 s recuperou as duas **e reduziu a
busca de ~20 s para 4,5–8,4 s** — porque o tempo antigo era gasto esperando o
timeout expirar, não trabalhando.

> Regra para as próximas fontes: medir o tempo isolado **antes** de registrar.
> Uma fonte de 11 s custa mais que o valor que agrega.

---

## 11. Estado da implementação

| Fase | Situação |
|---|---|
| 1 — Open Library (precisão) | ✅ feita |
| 2 — Arquitetura (capacidades, concorrência, dedupe) | ✅ feita |
| 3 — Português (Wikisource) | ✅ feita · SciELO e Brasiliana **não** (só HTML) |
| 4 — Acadêmico (OAPEN, Zenodo) | ✅ feita · DOAB reprovado |
| 5 — Artigos (OpenAlex, arXiv) | ✅ feita |
| 6 — Histórico e HQ (Gallica, Comic Book Plus, ManyBooks) | ⚠️ **descartada** — ver 11.1 |
| 7 — Com chave (Google Books, CORE, Europeana, DPLA, BHL) | 🔑 **bloqueada no usuário** — encanamento pronto, ver 11.2 |
| "Onde encontrar" (seção 6) | ✅ feita |

Fontes ativas: **MangaDex, Open Library, Wikisource, Archive.org, Gutenberg,
OAPEN, Zenodo, OpenAlex, arXiv**.

Uma nota da Fase 2: a spec propunha separar `BaseScraper` em contrato de duas
camadas. Ao implementar, verificou-se **desnecessário** — só `search` e
`get_series_info` são abstratos, e os métodos de capítulo já têm implementação
padrão. A refatoração foi descartada sem custo.

### 11.1 Fase 6 descartada

As três fontes previstas não pagam a manutenção:

- **Gallica** — acervo da Biblioteca Nacional **da França**, majoritariamente em
  francês. Desalinhado com uma biblioteca em português.
- **Comic Book Plus** e **ManyBooks** — só HTML, sem API. Dois scrapers frágeis,
  que quebram quando o site muda.

Fica registrada como decisão, não como pendência. Se o acervo francês passar a
interessar, o Gallica tem SRU real e é o único dos três que vale reabrir.

### 11.2 Fase 7 bloqueada — e por que não foi escrita às cegas

Todas as cinco exigem cadastro. O **Google Books**, único que teoricamente
funciona sem chave, esgotou a **cota diária por IP** durante a auditoria:

```
429 — Quota exceeded for quota metric 'Queries' and limit 'Queries per day'
```

Escrever os cinco scrapers sem poder chamar a API real repetiria um erro já
cometido cinco vezes: **todas** as fontes implementadas tiveram defeito que só a
chamada real revelou (cabeçalhos, rate-limit, busca por autor). Mock não pega
nenhum desses.

**O que já está pronto**, para a Fase 7 virar configuração em vez de código:

- `settings_store.get_api_key()` / `set_api_key()` / `configured_api_keys()` —
  chaves guardadas no JSON de configurações, que já está no `.gitignore`
- `SourceCapabilities.needs_api_key` — declarativo, por fonte
- `_scraper_applicable` desliga a fonte enquanto não houver chave, para ela não
  entrar na busca só para tomar 401 e gastar o orçamento de tempo das outras

Falta, quando houver chaves: o scraper de cada fonte e um campo na interface.

---

## 9. Resumo

- **30 fontes testadas**, 16 aprovadas sem chave, 5 com chave, 9 reprovadas
  (o DOAB caiu na implementação — seção 10.1).
- A maior perda foi o **Domínio Público do MEC** (403, bloqueio de WAF).
- O gargalo **não é o número de fontes** — é direito autoral. Por isso a
  funcionalidade "onde encontrar" pesa tanto quanto as fontes novas.
- A ordem importa: **Open Library primeiro** (precisão), depois arquitetura,
  depois acervo. Inverter isso faz cada fonte nova custar mais que a anterior.

*Media Bot PT-BR — By Munhoz.*
