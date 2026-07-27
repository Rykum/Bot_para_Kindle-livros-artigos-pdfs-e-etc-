# Explorar por gênero e subgênero

Data: **26/07/2026** · Autor: *By Munhoz*

Tela nova de descoberta: escolher um gênero e ver o que existe, sem digitar nada.
Cobre os quatro tipos principais — **livro, mangá, manhwa e HQ**.

---

## 1. Problema

A busca atual exige saber o que se procura. Não há caminho para "quero ler algo
de terror" nem para descobrir obra desconhecida.

---

## 2. O achado que define o desenho

Medi o suporte a gênero em cada fonte, por HTTP real. As naturezas são opostas:

| fonte | vocabulário | ordenação que funciona |
|---|---|---|
| **MangaDex** | **Fechado**: 25 gêneros + 38 temas, filtro por UUID | `followedCount` — vivo **e** preciso |
| **Open Library** | Texto livre, em inglês | **relevância** (padrão) |
| **Gutendex** | Texto livre, estilo biblioteca | `popular` |
| **Archive.org** | Texto livre, inconsistente | ruim para gênero — **fora** |

### 2.1 Popularidade funciona em mangá e falha em livro

Com `has_fulltext=true` (só baixáveis), no Open Library:

| ordenação | ficção científica | terror | filosofia |
|---|---|---|---|
| **relevância** | Invisible Man, Caves of Steel | Misery, Shining, Exorcist | Nietzsche, Meditações, Tao Te Ching |
| rating | Hitchhiker's, Watchmen | ⚠️ Maus, O Hobbit | ⚠️ O Pequeno Príncipe |
| readinglog | ⚠️ Harry Potter | ⚠️ Crepúsculo | 48 Leis do Poder |

**Causa:** o MangaDex mede popularidade *dentro da obra* (seguidores daquele
mangá). O Open Library mede no acervo inteiro, então o livro mais lido vaza para
dentro de qualquer gênero. Ordenar por edições era pior ainda: *Alice no País das
Maravilhas* aparecia tanto em ficção científica quanto em filosofia.

**Decisão:** ordenação **por fonte**, não global. Livro ganha um seletor que
mangá não tem.

### 2.2 O idioma da taxonomia

`subject=science fiction` → 90.804 obras. `subject=ficção científica` → **14**.
O vocabulário de assunto é inglês. Toda tradução PT→EN é responsabilidade do app.

---

## 3. Decisões

| # | Decisão |
|---|---|
| 1 | **Modo descoberta**, sem termo de texto |
| 2 | Cobre **livro, mangá, manhwa e HQ** |
| 3 | **Taxonomia por tipo de mídia** — "Isekai" não existe em livro, "Biografia" não existe em mangá |
| 4 | **Tela "Explorar" própria** na barra lateral, com grade clicável |
| 5 | Ordenação **por fonte**; só livro expõe seletor |
| 6 | **Capa** nos resultados, degradando sem quebrar |

---

## 4. Taxonomia — curada com resolução viva

Combina estabilidade e atualidade:

**Curado (em código):** hierarquia, nomes em português e tradução por fonte.
Testável sem rede, revisável, traduzível.

**Vivo (em execução):** os **UUIDs** das tags do MangaDex **não** ficam gravados.
São resolvidos por nome, com cache de 24 h. Se o MangaDex trocar um UUID, nada
quebra; se criar tag nova, o log registra que falta tradução.

```python
GENEROS_MANGA = [
    Genero("Terror", subgeneros=["Demônios", "Fantasmas", "Psicológico"],
           mangadex_tag="Horror"),          # UUID resolvido ao vivo
]

GENEROS_LIVRO = [
    Genero("Ficção científica", subgeneros=["Distopia", "Space opera", "Cyberpunk"],
           openlibrary="science fiction", gutendex="science fiction"),
]
```

---

## 5. Comportamento por tipo de mídia

### 5.1 Mangá, manhwa e manhua — mesmo código

Um parâmetro os separa: `originalLanguage[]`.

| tipo | idioma de origem | acervo medido |
|---|---|---|
| mangá | `ja` | 74.987 |
| manhwa | `ko` | 8.717 |
| manhua | `zh` | 6.049 |

Grade de gêneros → segunda fileira de temas (subgênero) → resultados ordenados por
`followedCount`. Filtro exato por UUID, sem falso positivo.

Verificado: Horror → Berserk, Chainsaw Man, Mieruko-chan.

### 5.2 Livro — duas fontes, ordenação dupla

Fontes: **Open Library** (principal — tem capa e filtro de baixável) e
**Gutendex** (complementa com domínio público).

Seletor de ordenação, exclusivo deste tipo:

- **"Melhores do gênero"** (padrão) → relevância do Open Library
- **"Mais lidos agora"** → `readinglog`, sinal vivo, com a ressalva de que derrapa

Sempre `has_fulltext=true`: ficção científica cai de 90.804 para 18.864, e o que
sobra é baixável.

### 5.3 HQ — o mais fraco, e a spec assume isso

Fonte: Archive.org `collection:comics` (80.482 itens; **3 de 4** com CBR/PDF —
verificados Tintin, Astérix, Invincible).

O problema: o assunto é inconsistente e **mangá vaza**. Buscar `horror` em
`collection:comics` devolve *Berserk*. Só `superhero` ficou limpo (X-Men,
Spider-Man).

**Decisão:** grade de HQ **menor e conservadora**, só com os gêneros medidos como
utilizáveis, e aviso na tela de que o acervo é irregular. Seis gêneros que
funcionam valem mais que vinte que enganam.

---

## 6. Capas

| fonte | origem | observação |
|---|---|---|
| MangaDex | `cover_art` | **já é pedido hoje e descartado** |
| Open Library | `cover_i` → `covers.openlibrary.org` | uma voltou **502** no teste |
| Archive.org | `services/img/{identificador}` | derivável, sem chamada extra |
| Gutendex | vem no `formats` | |
| Wikisource, OAPEN, Zenodo | não têm | espaço reservado |

Toda imagem precisa de `onerror` que esconde e mostra o espaço reservado. Sem
isso, ícone quebrado no meio da grade.

---

## 7. Arquitetura

**Arquivos novos**

- `scrapers/generos.py` — taxonomia. Estrutura pura, sem rede.
- `app/explorar.py` — serviço. Sabe qual ordenação cada tipo usa. Reaproveita o
  fan-out concorrente e a deduplicação existentes.
- `frontend/` — item na barra lateral, grade, segunda fileira, seletor.

**Nos scrapers existentes**

Método `explorar(genero, subgenero, ordenacao)`, declarado em
`SourceCapabilities`. Fonte que não sabe explorar simplesmente não aparece — a
mesma mecânica de capacidades já usada no roteamento por tipo de mídia. OAPEN,
Zenodo, OpenAlex e arXiv ficam de fora sem `if` em lugar nenhum.

---

## 8. Erros e degradação

| situação | comportamento |
|---|---|
| UUID de tag não resolve | gênero desabilitado na grade + log; nunca busca vazia silenciosa |
| Capa 502 ou timeout | `onerror` esconde; espaço reservado |
| Fonte estoura o tempo | herda o atual: segue sem ela |
| Gênero sem resultado | reaproveita o "onde encontrar" |

---

## 9. Testes — rede por padrão

**Este é um app de rede.** Todos os defeitos desta sessão foram de contrato de
rede, e **nenhum** apareceu com mock:

| defeito | como se manifestou |
|---|---|
| Zenodo 403 | User-Agent de navegador rejeitado |
| OAPEN devolvia HTML | content-negotiation pelo `Accept` |
| arXiv 429 | redirecionamento http→https + rate-limit curto |
| Busca por autor | casava palavra a palavra em 3 fontes |
| DOAB | itens sem título e sem arquivo |

Portanto os testes de rede entram na **suíte padrão**. `-m "not network"` fica
disponível para quem estiver offline.

**Custo assumido:** a suíte fica mais lenta e pode falhar por causa alheia —
durante esta sessão o Jikan deu 504 e o Gutendex expirou. A mitigação é a
mensagem de falha distinguir **"a fonte mudou o contrato"** de **"a fonte está
fora do ar"**, para não confundir regressão com instabilidade de terceiro.

**Sem rede:** taxonomia, tradução por fonte, escolha de ordenação, construção de
URL de capa.

**Com rede, um por fonte:** a busca por gênero devolve resultado plausível, com
capa e com arquivo.

---

## 10. Fora do escopo

Registrado para depois, deliberadamente separado:

**Acabamento de manhwa** — AniList (GraphQL, sem chave) e Kitsu dão títulos
melhores: "Solo Leveling" em vez de "Na Honjaman Level-Up". Nenhum dos dois
hospeda arquivo; seriam camada de metadados, como o Open Library é para livro.
Melhoria de acabamento, não de capacidade.

**Ampliação de repertório** — trilha separada, porque não são fontes de gênero:

| fonte | o que agrega |
|---|---|
| **OpenStax** | 129 livros didáticos com `pdf_url` direto |
| **Europe PMC** | 204.065 artigos de acesso aberto com PDF, forte no Brasil |
| **Unpaywall** | **Não é fonte** — resolve DOI → PDF aberto. Resgataria os trabalhos que o OpenAlex descarta hoje por não terem `pdf_url` |

**Reprovadas na auditoria desta rodada:** Wikibooks (o ws-export só serve o
Wikisource, 404), Semantic Scholar (429), Comick (conexão), GlobalComix,
Webtoons, Tapas (400), MangaPlus (404), Metron e Comic Vine (exigem chave).

Para HQ e manhwa **não há fonte nova**: manhwa está bem servido pelo MangaDex, e
HQ segue dependendo do Archive.org com acervo irregular.

---

*Media Bot PT-BR — By Munhoz.*
