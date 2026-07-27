# Explorar por gênero e subgênero — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tela nova de descoberta: escolher um gênero e ver o que existe, sem digitar nada — para livro, mangá, manhwa e HQ.

**Architecture:** Taxonomia curada em `scrapers/generos.py` (sem rede), com UUIDs do MangaDex resolvidos em execução. Cada scraper ganha `explorar()`, declarado em `SourceCapabilities`. `MediaBot.explorar_genero` escolhe a ordenação certa por tipo de mídia e reaproveita o fan-out concorrente e a deduplicação já existentes (ver o desvio anotado na Task 6).

**Tech Stack:** Python 3.13, pytest, `requests`, HTML/CSS/JS puro no frontend.

**Spec:** `docs/superpowers/specs/2026-07-26-busca-por-genero-design.md`

**Pré-requisito:** o plano `2026-07-26-design-system-unificado.md` deve estar concluído. A tela Explorar é nova; construí-la no estilo antigo para redesenhar depois é retrabalho.

## Global Constraints

- **Interpretador:** `py -3.13`. Rodar com `PYTHONIOENCODING=utf-8`.
- **Sem CDN** no frontend.
- **Testes de rede na suíte padrão** (decisão do autor: este é um app de rede). Marcar com `@pytest.mark.network`; `-m "not network"` pula quando offline.
- **A mensagem de falha de teste de rede deve distinguir** "a fonte mudou o contrato" de "a fonte está fora do ar". Sem isso, instabilidade de terceiro vira alarme falso de regressão.
- **Cabeçalhos de API:** toda fonte nova chama `self.use_api_headers()` no `__init__`. O padrão do `BaseScraper` se passa por Chrome pedindo `text/html`, e isso já quebrou Zenodo (403) e OAPEN (HTML em vez de JSON).
- **Valores medidos** que o código deve respeitar: `has_fulltext=true` no Open Library; ordenação **relevância** (ausência de `sort`) para livro; `order[followedCount]=desc` no MangaDex.

---

### Task 1: Taxonomia curada

**Files:**
- Create: `scrapers/generos.py`
- Test: `tests/test_generos.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `@dataclass(frozen=True) Genero` com campos `nome: str`, `subgeneros: tuple[str, ...]`, `mangadex_tag: str | None`, `openlibrary: str | None`, `gutendex: str | None`, `archive: str | None`
  - `GENEROS_POR_MIDIA: dict[str, tuple[Genero, ...]]` com chaves `"manga"`, `"manhwa"`, `"livro"`, `"hq"`
  - `generos_de(media_type: str) -> tuple[Genero, ...]`
  - `genero_por_nome(media_type: str, nome: str) -> Genero | None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_generos.py
import pytest
from scrapers.generos import (Genero, GENEROS_POR_MIDIA, generos_de, genero_por_nome)


def test_manga_and_manhwa_share_the_same_taxonomy():
    """Manhwa é mangá coreano: mesma taxonomia, muda só originalLanguage."""
    assert GENEROS_POR_MIDIA["manga"] == GENEROS_POR_MIDIA["manhwa"]


def test_book_and_manga_taxonomies_are_different():
    """'Isekai' não existe em livro; 'Biografia' não existe em mangá."""
    nomes_manga = {g.nome for g in generos_de("manga")}
    nomes_livro = {g.nome for g in generos_de("livro")}
    assert nomes_manga != nomes_livro
    assert "Biografia" in nomes_livro and "Biografia" not in nomes_manga


def test_every_manga_genre_maps_to_a_mangadex_tag():
    for g in generos_de("manga"):
        assert g.mangadex_tag, f"{g.nome} sem tag do MangaDex"


def test_every_book_genre_maps_to_an_english_term():
    """O vocabulário de assunto é inglês: 'ficção científica' dá 14 resultados."""
    for g in generos_de("livro"):
        assert g.openlibrary, f"{g.nome} sem termo do Open Library"
        assert g.openlibrary.isascii(), f"{g.nome}: termo precisa ser em inglês"


def test_hq_grid_is_deliberately_small():
    """Medido: só `superhero` passou; horror trazia Berserk, romance derivava."""
    assert 0 < len(generos_de("hq")) <= 8


def test_lookup_by_name_is_accent_and_case_insensitive():
    assert genero_por_nome("livro", "ficção científica").nome == "Ficção científica"
    assert genero_por_nome("livro", "FICCAO CIENTIFICA").nome == "Ficção científica"
    assert genero_por_nome("livro", "inexistente") is None


def test_unknown_media_type_yields_nothing():
    assert generos_de("artigo") == ()
    assert generos_de("") == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_generos.py -v`
Expected: FAIL — `ModuleNotFoundError: scrapers.generos`.

- [ ] **Step 3: Escrever a taxonomia**

```python
# scrapers/generos.py
"""Taxonomia de gêneros por tipo de mídia.

Curada de propósito: os nomes ficam em português, a hierarquia é estável e o
módulo não faz rede — dá para testar sem API. Os UUIDs das tags do MangaDex
NÃO ficam aqui; são resolvidos em execução (ver mangadex_scraper._tag_ids).

O vocabulário de assunto das fontes de livro é inglês: medido, `science fiction`
devolve 90.804 obras e `ficção científica` devolve 14.
"""

import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class Genero:
    nome: str
    subgeneros: Tuple[str, ...] = ()
    mangadex_tag: Optional[str] = None
    openlibrary: Optional[str] = None
    gutendex: Optional[str] = None
    archive: Optional[str] = None


_MANGA = (
    Genero("Ação", ("Artes marciais", "Samurais", "Militar"), mangadex_tag="Action"),
    Genero("Aventura", ("Sobrevivência", "Viagem no tempo"), mangadex_tag="Adventure"),
    Genero("Comédia", ("Paródia", "Fatia de vida"), mangadex_tag="Comedy"),
    Genero("Drama", ("Tragédia", "Psicológico"), mangadex_tag="Drama"),
    Genero("Fantasia", ("Isekai", "Magia", "Demônios"), mangadex_tag="Fantasy"),
    Genero("Terror", ("Fantasmas", "Monstros", "Psicológico"), mangadex_tag="Horror"),
    Genero("Mistério", ("Detetive", "Crime"), mangadex_tag="Mystery"),
    Genero("Romance", ("Harém", "Escolar"), mangadex_tag="Romance"),
    Genero("Ficção científica", ("Mechas", "Realidade virtual", "Aliens"), mangadex_tag="Sci-Fi"),
    Genero("Esportes", ("Artes marciais",), mangadex_tag="Sports"),
    Genero("Histórico", ("Samurais", "Militar"), mangadex_tag="Historical"),
    Genero("Sobrenatural", ("Demônios", "Fantasmas", "Magia"), mangadex_tag="Supernatural"),
)

_LIVRO = (
    Genero("Ficção científica", ("Distopia", "Space opera", "Cyberpunk"),
           openlibrary="science fiction", gutendex="science fiction"),
    Genero("Terror", ("Gótico", "Sobrenatural"),
           openlibrary="horror", gutendex="horror"),
    Genero("Romance", ("Histórico", "Contemporâneo"),
           openlibrary="romance", gutendex="love stories"),
    Genero("Mistério", ("Policial", "Suspense"),
           openlibrary="detective and mystery stories", gutendex="detective"),
    Genero("Fantasia", ("Épica", "Contos de fadas"),
           openlibrary="fantasy", gutendex="fantasy"),
    Genero("Poesia", ("Épica", "Lírica"),
           openlibrary="poetry", gutendex="poetry"),
    Genero("Filosofia", ("Ética", "Metafísica"),
           openlibrary="philosophy", gutendex="philosophy"),
    Genero("História", ("Brasil", "Antiguidade"),
           openlibrary="history", gutendex="history"),
    Genero("Biografia", ("Memórias",),
           openlibrary="biography", gutendex="biography"),
    Genero("Aventura", ("Viagem", "Náutica"),
           openlibrary="adventure stories", gutendex="adventure"),
)

# Grade pequena de propósito. Medido em collection:comics: `superhero` trouxe
# X-Men e Spider-Man; `horror` trouxe Berserk (mangá) e `romance` derivou.
# Acrescentar gênero aqui EXIGE medir antes — ver §5.3 da spec.
_HQ = (
    Genero("Super-heróis", (), archive="superhero"),
)

GENEROS_POR_MIDIA: Dict[str, Tuple[Genero, ...]] = {
    "manga": _MANGA,
    "manhwa": _MANGA,      # mesma taxonomia; muda só o idioma de origem
    "livro": _LIVRO,
    "hq": _HQ,
}


def _dobra(texto: str) -> str:
    """Minúsculas sem acento, para casar 'FICCAO' com 'Ficção'."""
    plano = unicodedata.normalize("NFKD", str(texto or "").lower())
    return "".join(c for c in plano if not unicodedata.combining(c)).strip()


def generos_de(media_type: str) -> Tuple[Genero, ...]:
    return GENEROS_POR_MIDIA.get((media_type or "").strip().lower(), ())


def genero_por_nome(media_type: str, nome: str) -> Optional[Genero]:
    alvo = _dobra(nome)
    for g in generos_de(media_type):
        if _dobra(g.nome) == alvo:
            return g
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_generos.py -v`
Expected: PASS (7 testes).

- [ ] **Step 5: Commit**

```bash
git add scrapers/generos.py tests/test_generos.py
git commit -m "feat(genero): taxonomia curada por tipo de mídia"
```

---

### Task 2: Resolver tags do MangaDex em execução

**Files:**
- Modify: `scrapers/mangadex_scraper.py`
- Test: `tests/test_mangadex_tags.py`

**Interfaces:**
- Consumes: nada.
- Produces: `MangaDexScraper._tag_ids(nomes: list[str]) -> dict[str, str]` — mapeia nome de tag em inglês para UUID, com cache em memória. Devolve só os que existem.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mangadex_tags.py
from scrapers.mangadex_scraper import MangaDexScraper


class FakeResp:
    def __init__(self, payload): self._p = payload
    def json(self): return self._p


def _tags():
    return {"data": [
        {"id": "uuid-horror", "attributes": {"name": {"en": "Horror"}, "group": "genre"}},
        {"id": "uuid-ghosts", "attributes": {"name": {"en": "Ghosts"}, "group": "theme"}},
    ]}


def test_resolves_names_to_uuids(monkeypatch):
    """A API só aceita UUID; gravar UUID no código quebra quando ele muda."""
    sc = MangaDexScraper()
    monkeypatch.setattr(sc, "make_request", lambda *a, **k: FakeResp(_tags()))
    assert sc._tag_ids(["Horror"]) == {"Horror": "uuid-horror"}


def test_unknown_tag_is_omitted_not_invented(monkeypatch):
    sc = MangaDexScraper()
    monkeypatch.setattr(sc, "make_request", lambda *a, **k: FakeResp(_tags()))
    assert sc._tag_ids(["Horror", "NaoExiste"]) == {"Horror": "uuid-horror"}


def test_tag_table_is_fetched_once(monkeypatch):
    """São 77 tags fixas; buscar a cada exploração é desperdício."""
    sc = MangaDexScraper()
    chamadas = []
    monkeypatch.setattr(sc, "make_request",
                        lambda *a, **k: chamadas.append(1) or FakeResp(_tags()))
    sc._tag_ids(["Horror"])
    sc._tag_ids(["Ghosts"])
    assert len(chamadas) == 1


def test_failure_to_fetch_yields_empty_not_crash(monkeypatch):
    sc = MangaDexScraper()
    monkeypatch.setattr(sc, "make_request", lambda *a, **k: None)
    assert sc._tag_ids(["Horror"]) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_mangadex_tags.py -v`
Expected: FAIL — `AttributeError: '_tag_ids'`.

- [ ] **Step 3: Implementar**

Em `scrapers/mangadex_scraper.py`, acrescentar ao `__init__`:

```python
        self._tabela_tags = None    # cache: nome em inglês -> UUID
```

E o método:

```python
    def _tag_ids(self, nomes):
        """
        Resolve nomes de tag para UUID.

        A API do MangaDex só aceita UUID em `includedTags[]`. Gravar os UUIDs no
        código os transformaria em bomba-relógio: se o MangaDex trocar um, o
        gênero para de funcionar em silêncio. Resolver por nome custa uma chamada
        (as 77 tags mudam raramente) e falha visível.
        """
        if self._tabela_tags is None:
            resposta = self.make_request(f"{self.base_url}/manga/tag")
            if not resposta:
                return {}
            self._tabela_tags = {
                t["attributes"]["name"]["en"]: t["id"]
                for t in resposta.json().get("data", [])
                if t.get("id") and t.get("attributes", {}).get("name", {}).get("en")
            }
        return {n: self._tabela_tags[n] for n in nomes if n in self._tabela_tags}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_mangadex_tags.py -v`
Expected: PASS (4 testes).

- [ ] **Step 5: Commit**

```bash
git add scrapers/mangadex_scraper.py tests/test_mangadex_tags.py
git commit -m "feat(genero): resolve tags do MangaDex por nome, com cache"
```

---

### Task 3: `explorar()` no MangaDex, com capa

**Files:**
- Modify: `scrapers/mangadex_scraper.py`
- Test: `tests/test_explorar_mangadex.py`

**Interfaces:**
- Consumes: `_tag_ids` da Task 2; `Genero` da Task 1.
- Produces: `MangaDexScraper.explorar(genero: Genero, subgenero: str | None = None, ordenacao: str = "popular", idioma_origem: str = "ja") -> list[ScrapedResult]`

O scraper **já pede `includes[]=cover_art` e descarta**. Esta tarefa corrige isso.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_explorar_mangadex.py
from scrapers.generos import genero_por_nome
from scrapers.mangadex_scraper import MangaDexScraper


class FakeResp:
    def __init__(self, payload): self._p = payload
    def json(self): return self._p


TAGS = {"data": [
    {"id": "uuid-horror", "attributes": {"name": {"en": "Horror"}, "group": "genre"}},
    {"id": "uuid-ghosts", "attributes": {"name": {"en": "Ghosts"}, "group": "theme"}},
]}

MANGAS = {"data": [{
    "id": "m-1",
    "attributes": {"title": {"en": "Berserk"}, "status": "ongoing", "year": 1989,
                   "description": {}},
    "relationships": [{"type": "cover_art", "attributes": {"fileName": "capa.jpg"}}],
}]}


def _scraper(monkeypatch):
    sc = MangaDexScraper()
    capturado = {}

    def fake(url, params=None, retries=0):
        if url.endswith("/manga/tag"):
            return FakeResp(TAGS)
        capturado.update(params or {})
        capturado["url"] = url
        return FakeResp(MANGAS)

    monkeypatch.setattr(sc, "make_request", fake)
    return sc, capturado


def test_filters_by_tag_uuid_and_orders_by_followers(monkeypatch):
    sc, cap = _scraper(monkeypatch)
    sc.explorar(genero_por_nome("manga", "Terror"))
    assert cap["includedTags[]"] == ["uuid-horror"]
    assert cap["order[followedCount]"] == "desc"


def test_subgenre_adds_a_second_tag(monkeypatch):
    # "Fantasmas" é o rótulo em português; o MangaDex só conhece "Ghosts".
    # A tradução vive em SUBGENERO_TAG_MANGADEX, em scrapers/generos.py,
    # ao lado da taxonomia — e há teste de sincronia lá.
    sc, cap = _scraper(monkeypatch)
    sc.explorar(genero_por_nome("manga", "Terror"), subgenero="Fantasmas")
    assert set(cap["includedTags[]"]) == {"uuid-horror", "uuid-ghosts"}


def test_manhwa_filters_by_original_language(monkeypatch):
    """Manhwa é mangá coreano: 8.717 obras com originalLanguage=ko."""
    sc, cap = _scraper(monkeypatch)
    sc.explorar(genero_por_nome("manhwa", "Terror"), idioma_origem="ko")
    assert cap["originalLanguage[]"] == ["ko"]


def test_cover_url_is_built_from_the_relationship(monkeypatch):
    """O scraper já pedia cover_art e jogava fora."""
    sc, _ = _scraper(monkeypatch)
    r = sc.explorar(genero_por_nome("manga", "Terror"))[0]
    assert r.metadata["cover_url"] == \
        "https://uploads.mangadex.org/covers/m-1/capa.jpg.256.jpg"


def test_unknown_subgenre_is_ignored_not_fatal(monkeypatch):
    sc, cap = _scraper(monkeypatch)
    sc.explorar(genero_por_nome("manga", "Terror"), subgenero="NaoExiste")
    assert cap["includedTags[]"] == ["uuid-horror"]


def test_unresolvable_genre_returns_empty(monkeypatch):
    """Melhor lista vazia com log que busca sem filtro devolvendo qualquer coisa."""
    sc = MangaDexScraper()
    monkeypatch.setattr(sc, "make_request",
                        lambda url, params=None, retries=0:
                        FakeResp({"data": []}) if url.endswith("/manga/tag") else FakeResp(MANGAS))
    assert sc.explorar(genero_por_nome("manga", "Terror")) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_explorar_mangadex.py -v`
Expected: FAIL — `AttributeError: 'explorar'`.

- [ ] **Step 3: Implementar**

Em `scrapers/mangadex_scraper.py`:

```python
    @staticmethod
    def _cover_url(manga_id, relationships):
        """Monta a URL da capa a partir do relacionamento cover_art."""
        for rel in relationships or []:
            if rel.get("type") == "cover_art":
                arquivo = (rel.get("attributes") or {}).get("fileName")
                if arquivo:
                    return f"https://uploads.mangadex.org/covers/{manga_id}/{arquivo}.256.jpg"
        return None

    def explorar(self, genero, subgenero=None, ordenacao="popular", idioma_origem="ja"):
        """
        Lista obras de um gênero, sem termo de busca.

        A popularidade do MangaDex é medida por obra (seguidores daquele mangá),
        então ela é ao mesmo tempo viva e precisa — diferente de livro, onde a
        popularidade é global e vaza entre gêneros.
        """
        if genero is None:
            return []

        desejadas = [genero.mangadex_tag]
        if subgenero:
            desejadas.append(subgenero)
        ids = self._tag_ids([n for n in desejadas if n])

        tag_principal = ids.get(genero.mangadex_tag)
        if not tag_principal:
            logger.warning(
                f"MangaDex: tag '{genero.mangadex_tag}' não resolvida; "
                f"gênero '{genero.nome}' indisponível")
            return []

        params = {
            "includedTags[]": [i for i in ids.values()],
            "originalLanguage[]": [idioma_origem],
            "order[followedCount]": "desc",
            "includes[]": ["cover_art"],
            "limit": 40,
        }

        resultados = []
        try:
            resposta = self.make_request(f"{self.base_url}/manga", params=params)
            if not resposta:
                return resultados
            for manga in resposta.json().get("data", []):
                atributos = manga.get("attributes", {})
                titulos = atributos.get("title", {})
                titulo = (titulos.get("pt-br") or titulos.get("en")
                          or (list(titulos.values())[0] if titulos else "Sem título"))
                manga_id = manga.get("id")
                resultados.append(ScrapedResult(
                    title=titulo,
                    url=f"https://mangadex.org/title/{manga_id}",
                    source=self.name,
                    format_type="cbz",
                    series_name=titulo,
                    language="pt-br",
                    metadata={
                        "manga_id": manga_id,
                        "identifier": manga_id,
                        "creator": "",
                        "year": atributos.get("year"),
                        "cover_url": self._cover_url(manga_id, manga.get("relationships")),
                        "genero": genero.nome,
                    },
                ))
            logger.info(f"MangaDex: {len(resultados)} obras em '{genero.nome}'")
        except Exception as e:
            logger.error(f"Erro ao explorar no MangaDex: {e}")
        return resultados
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_explorar_mangadex.py -v`
Expected: PASS (6 testes).

- [ ] **Step 5: Commit**

```bash
git add scrapers/mangadex_scraper.py tests/test_explorar_mangadex.py
git commit -m "feat(genero): explorar() no MangaDex, com capa e manhwa"
```

---

### Task 4: `explorar()` no Open Library e no Gutendex

**Files:**
- Modify: `scrapers/openlibrary_scraper.py`, `scrapers/gutenberg_scraper.py`
- Test: `tests/test_explorar_livro.py`

**Interfaces:**
- Consumes: `Genero` da Task 1.
- Produces:
  - `OpenLibraryScraper.explorar(genero, subgenero=None, ordenacao="relevancia") -> list[ScrapedResult]`
  - `ProjectGutenbergScraper.explorar(genero, subgenero=None, ordenacao="relevancia") -> list[ScrapedResult]`
  - `ordenacao` aceita `"relevancia"` (padrão) e `"mais_lidos"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_explorar_livro.py
from scrapers.generos import genero_por_nome
from scrapers.openlibrary_scraper import OpenLibraryScraper
from scrapers.gutenberg_scraper import ProjectGutenbergScraper


class FakeResp:
    def __init__(self, payload): self._p = payload
    def json(self): return self._p


OL = {"docs": [{
    "key": "/works/W1", "title": "Misery", "author_name": ["Stephen King"],
    "first_publish_year": 1987, "ia": ["misery0000king"], "isbn": ["978"],
    "language": ["eng"], "cover_i": 8259296,
}]}


def _ol(monkeypatch):
    sc = OpenLibraryScraper()
    cap = {}
    def fake(url, params=None, retries=0):
        cap.update(params or {})
        return FakeResp(OL)
    monkeypatch.setattr(sc, "make_request", fake)
    return sc, cap


def test_default_ordering_is_relevance_not_popularity(monkeypatch):
    """Medido: por popularidade, Alice no País das Maravilhas aparecia em
    ficção científica E em filosofia. Relevância acerta o gênero."""
    sc, cap = _ol(monkeypatch)
    sc.explorar(genero_por_nome("livro", "Terror"))
    assert cap["subject"] == "horror"
    assert "sort" not in cap, "relevância é a ausência de sort"


def test_most_read_ordering_uses_readinglog(monkeypatch):
    sc, cap = _ol(monkeypatch)
    sc.explorar(genero_por_nome("livro", "Terror"), ordenacao="mais_lidos")
    assert cap["sort"] == "readinglog"


def test_only_downloadable_results(monkeypatch):
    """has_fulltext corta ficção científica de 90.804 para 18.864."""
    sc, cap = _ol(monkeypatch)
    sc.explorar(genero_por_nome("livro", "Terror"))
    assert cap["has_fulltext"] == "true"


def test_subgenre_narrows_the_subject(monkeypatch):
    sc, cap = _ol(monkeypatch)
    sc.explorar(genero_por_nome("livro", "Ficção científica"), subgenero="Distopia")
    assert "science fiction" in cap["subject"].lower()
    assert "distopia" not in cap["subject"].lower(), "subgênero precisa ir em inglês"


def test_every_book_subgenre_resolves():
    """Varre TODOS os subgêneros declarados, não só um caso fácil.

    A primeira versão deste plano testava só "Distopia" — que por acaso não tem
    acento — enquanto metade das chaves do dicionário eram acentuadas e portanto
    inalcançáveis pelo lookup, que passa por `_fold()`.
    """
    from scrapers.generos import generos_de
    sc = OpenLibraryScraper()
    nao_resolvem = [
        (g.nome, s)
        for g in generos_de("livro")
        for s in g.subgeneros
        if sc.SUBGENEROS.get(sc._fold(s)) is None
    ]
    assert not nao_resolvem, f"subgêneros de livro sem tradução: {nao_resolvem}"


def test_cover_url_comes_from_cover_i(monkeypatch):
    sc, _ = _ol(monkeypatch)
    r = sc.explorar(genero_por_nome("livro", "Terror"))[0]
    assert r.metadata["cover_url"] == "https://covers.openlibrary.org/b/id/8259296-M.jpg"


def test_gutendex_uses_topic_and_popular(monkeypatch):
    sc = ProjectGutenbergScraper()
    cap = {}
    monkeypatch.setattr(sc, "make_request",
                        lambda url, params=None, retries=0:
                        cap.update(params or {}) or FakeResp({"results": []}))
    sc.explorar(genero_por_nome("livro", "Terror"))
    assert cap["topic"] == "horror"
    assert cap["sort"] == "popular"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_explorar_livro.py -v`
Expected: FAIL — `AttributeError: 'explorar'`.

- [ ] **Step 3: Implementar no Open Library**

Acrescentar um mapa de subgênero e o método, em `scrapers/openlibrary_scraper.py`:

```python
    #: Subgênero em português -> termo de assunto em inglês.
    #: As chaves são SEM ACENTO de propósito: o lookup passa por `_fold()`, que
    #: remove diacríticos. Chave acentuada aqui é inalcançável — o subgênero
    #: seria ignorado em silêncio, e o usuário veria o gênero inteiro sem aviso.
    SUBGENEROS = {
        "distopia": "dystopias", "space opera": "space opera", "cyberpunk": "cyberpunk",
        "gotico": "gothic fiction", "sobrenatural": "supernatural",
        "historico": "historical fiction", "contemporaneo": "contemporary fiction",
        "policial": "detective and mystery stories", "suspense": "suspense",
        "epica": "epic", "contos de fadas": "fairy tales", "lirica": "lyric poetry",
        "etica": "ethics", "metafisica": "metaphysics",
        "brasil": "brazil", "antiguidade": "antiquities",
        "memorias": "autobiography", "viagem": "voyages and travels",
        "nautica": "seafaring life",
    }

    def explorar(self, genero, subgenero=None, ordenacao="relevancia"):
        """
        Lista obras de um gênero.

        A ordenação padrão é relevância — ausência de `sort`. Medido: ordenar por
        popularidade traz o livro mais reimpresso do acervo inteiro para dentro de
        qualquer gênero, e `Alice no País das Maravilhas` aparecia tanto em ficção
        científica quanto em filosofia.
        """
        if genero is None or not genero.openlibrary:
            return []

        assunto = genero.openlibrary
        if subgenero:
            traduzido = self.SUBGENEROS.get(self._fold(subgenero))
            if traduzido:
                assunto = f"{assunto} {traduzido}"

        params = {
            "subject": assunto,
            "fields": self.FIELDS + ",cover_i",
            "limit": self.rows,
            "has_fulltext": "true",     # só o que dá para baixar
        }
        if ordenacao == "mais_lidos":
            params["sort"] = "readinglog"

        resultados = []
        try:
            resposta = self.make_request(self.search_api, params=params)
            if not resposta:
                return resultados
            for doc in resposta.json().get("docs", []):
                copias = doc.get("ia") or []
                if not copias:
                    continue
                autores = doc.get("author_name") or []
                isbns = doc.get("isbn") or []
                titulo = doc.get("title") or "Sem título"
                capa = doc.get("cover_i")
                resultados.append(ScrapedResult(
                    title=titulo,
                    url=f"https://archive.org/details/{copias[0]}",
                    source=self.name,
                    format_type="pdf",
                    series_name=titulo,
                    language=(doc.get("language") or [None])[0] or "desconhecido",
                    metadata={
                        "identifier": copias[0],
                        "creator": ", ".join(autores),
                        "year": doc.get("first_publish_year"),
                        "isbn": isbns[0] if isbns else None,
                        "openlibrary_key": doc.get("key"),
                        "cover_url": (f"https://covers.openlibrary.org/b/id/{capa}-M.jpg"
                                      if capa else None),
                        "genero": genero.nome,
                    },
                ))
        except Exception as e:
            logger.error(f"Erro ao explorar no Open Library: {e}")
        return resultados
```

- [ ] **Step 4: Implementar no Gutendex**

Em `scrapers/gutenberg_scraper.py`, reaproveitando o laço de resultados que já existe em `search`:

```python
    def explorar(self, genero, subgenero=None, ordenacao="relevancia"):
        """Lista livros de domínio público de um gênero."""
        if genero is None or not genero.gutendex:
            return []
        return self._resultados_de({
            "topic": genero.gutendex,
            "sort": "popular",
        }, rotulo_genero=genero.nome)
```

Isso exige extrair de `search` o laço que monta os resultados, para `explorar` e
`search` compartilharem o mesmo código. O método novo, também em
`scrapers/gutenberg_scraper.py`:

```python
    @staticmethod
    def _cover_url(formats):
        """A capa vem no próprio dicionário de formatos, sob uma chave image/*."""
        for mime, url in (formats or {}).items():
            if mime.startswith('image/'):
                return url
        return None

    def _resultados_de(self, params, rotulo_genero=None):
        """Executa a consulta e monta os ScrapedResult. Usado por search e explorar."""
        resultados = []
        try:
            resposta = self.make_request(self.search_url, params=params)
            if not resposta:
                return resultados
            for livro in resposta.json().get('results', []):
                formatos = livro.get('formats', {}) or {}
                download = (formatos.get('application/epub+zip')
                            or formatos.get('application/pdf'))
                if not download:
                    continue
                autores = ', '.join(a.get('name', '') for a in livro.get('authors', []))
                titulo = livro.get('title', 'Sem título')
                resultados.append(ScrapedResult(
                    title=titulo,
                    url=f"{self.base_url}/ebooks/{livro.get('id')}",
                    source=self.name,
                    format_type='epub' if 'epub' in str(download) else 'pdf',
                    series_name=titulo,
                    language=(livro.get('languages') or ['desconhecido'])[0],
                    download_url=download,
                    metadata={
                        'identifier': str(livro.get('id')),
                        'creator': autores,
                        'cover_url': self._cover_url(formatos),
                        'genero': rotulo_genero,
                    },
                ))
        except Exception as e:
            logger.error(f"Erro no Project Gutenberg: {e}")
        return resultados
```

Depois de extrair, `search` passa a chamar `_resultados_de` com os parâmetros que
já montava, e o filtro de autor do modo `autor` continua aplicado sobre a lista
devolvida — o comportamento dos testes existentes de `search` não pode mudar.

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_explorar_livro.py -v`
Expected: PASS (6 testes).

- [ ] **Step 6: Commit**

```bash
git add scrapers/openlibrary_scraper.py scrapers/gutenberg_scraper.py tests/test_explorar_livro.py
git commit -m "feat(genero): explorar() em livro, com relevância e has_fulltext"
```

---

### Task 5: `explorar()` no Archive.org para HQ, com gêneros validados

**Files:**
- Modify: `scrapers/archive_scraper.py`, `scrapers/generos.py`
- Test: `tests/test_explorar_hq.py`

**Interfaces:**
- Consumes: `Genero` da Task 1.
- Produces: `ArchiveOrgScraper.explorar(genero, subgenero=None, ordenacao="popular") -> list[ScrapedResult]`

**Antes de codar:** medir cada gênero candidato de HQ. A spec (§5.3) exige isso.

- [ ] **Step 1: Medir os candidatos**

```bash
PYTHONIOENCODING=utf-8 py -3.13 - <<'EOF'
import requests
H={'User-Agent':'MediaBot/1.0'}
for g in ['superhero','western','war','crime','funny animal','romance','horror','science fiction']:
    q=f'collection:comics AND subject:("{g}") AND mediatype:texts'
    r=requests.get("https://archive.org/advancedsearch.php",
      params={'q':q,'fl[]':['title'],'sort[]':['downloads desc'],'rows':4,'output':'json'},
      timeout=30,headers=H).json()['response']
    print(f"{g:16}{r['numFound']:>7}  {[str(d.get('title'))[:26] for d in r['docs'][:4]]}")
EOF
```

Registrar o resultado. Um gênero **só entra** em `_HQ` se os 4 primeiros forem HQ de verdade — sem mangá, sem livro. Se só `superhero` passar, a grade fica com um item, e isso é o resultado correto.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_explorar_hq.py
from scrapers.generos import generos_de, genero_por_nome
from scrapers.archive_scraper import ArchiveOrgScraper


class FakeResp:
    def __init__(self, payload): self._p = payload
    def json(self): return self._p


DOCS = {"response": {"docs": [
    {"identifier": "xmen01", "title": "X-Men v1", "mediatype": "texts",
     "creator": "Marvel", "downloads": 900},
]}}


def test_hq_query_is_scoped_to_the_comics_collection(monkeypatch):
    """Sem collection:comics, `superhero` pega qualquer texto do acervo."""
    sc = ArchiveOrgScraper()
    cap = {}
    monkeypatch.setattr(sc, "make_request",
                        lambda url, params=None, retries=0:
                        cap.update(params or {}) or FakeResp(DOCS))
    sc.explorar(genero_por_nome("hq", "Super-heróis"))
    assert "collection:comics" in cap["q"]
    assert 'subject:("superhero")' in cap["q"]


def test_hq_browse_sorts_by_downloads(monkeypatch):
    """Sem termo de busca não há relevância; downloads é o único sinal."""
    sc = ArchiveOrgScraper()
    cap = {}
    monkeypatch.setattr(sc, "make_request",
                        lambda url, params=None, retries=0:
                        cap.update(params or {}) or FakeResp(DOCS))
    sc.explorar(genero_por_nome("hq", "Super-heróis"))
    assert cap["sort[]"] == ["downloads desc"]


def test_hq_cover_is_derived_from_the_identifier(monkeypatch):
    """O Archive.org serve capa por identificador, sem chamada extra."""
    sc = ArchiveOrgScraper()
    monkeypatch.setattr(sc, "make_request", lambda *a, **k: FakeResp(DOCS))
    r = sc.explorar(genero_por_nome("hq", "Super-heróis"))[0]
    assert r.metadata["cover_url"] == "https://archive.org/services/img/xmen01"


def test_every_hq_genre_was_validated():
    """Cada gênero de HQ precisa ter passado pela medição do Step 1."""
    for g in generos_de("hq"):
        assert g.archive, f"{g.nome} sem termo do Archive.org"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_explorar_hq.py -v`
Expected: FAIL — `AttributeError: 'explorar'`.

- [ ] **Step 4: Implementar**

Em `scrapers/archive_scraper.py`:

```python
    def explorar(self, genero, subgenero=None, ordenacao="popular"):
        """
        Lista HQ de um gênero, dentro de collection:comics.

        Aviso de projeto: o acervo de HQ é irregular e o assunto é inconsistente
        — medido, `horror` em collection:comics devolve Berserk, que é mangá. Por
        isso a grade de gêneros de HQ é pequena e cada item foi validado à mão.
        """
        if genero is None or not genero.archive:
            return []

        consulta = (f'collection:comics AND subject:("{genero.archive}") '
                    f'AND mediatype:texts')
        params = {
            "q": consulta,
            "fl[]": ["identifier", "title", "creator", "year", "language",
                     "mediatype", "downloads"],
            "sort[]": ["downloads desc"],   # sem termo de busca não há relevância
            "rows": self.rows,
            "output": "json",
        }

        resultados = []
        try:
            resposta = self.make_request(self.search_api, params=params)
            if not resposta:
                return resultados
            for doc in resposta.json().get("response", {}).get("docs", []):
                identificador = doc.get("identifier")
                titulo = doc.get("title", "")
                if isinstance(titulo, list):
                    titulo = titulo[0] if titulo else "Sem título"
                resultados.append(ScrapedResult(
                    title=titulo,
                    url=f"{self.base_url}/details/{identificador}",
                    source=self.name,
                    format_type=self._detect_archive_format(doc),
                    series_name=titulo,
                    language="desconhecido",
                    metadata={
                        "identifier": identificador,
                        "creator": doc.get("creator", ""),
                        "year": doc.get("year"),
                        "cover_url": f"{self.base_url}/services/img/{identificador}",
                        "genero": genero.nome,
                    },
                ))
        except Exception as e:
            logger.error(f"Erro ao explorar HQ no Archive.org: {e}")
        return resultados
```

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_explorar_hq.py -v`
Expected: PASS (4 testes).

- [ ] **Step 6: Commit**

```bash
git add scrapers/archive_scraper.py scrapers/generos.py tests/test_explorar_hq.py
git commit -m "feat(genero): explorar() de HQ, com gêneros validados por medição"
```

---

### Task 6: Serviço de exploração e capacidades

**Files:**
- Modify: `scrapers/base_scraper.py` (`SourceCapabilities`), `media_bot.py`, `app/api.py`
- Test: `tests/test_servico_explorar.py`

> **Desvio consciente da spec §7.** A spec previa um arquivo `app/explorar.py`.
> Ao detalhar, ficou claro que o serviço precisa do fan-out concorrente, do
> `_dedupe_results` e do `_scraper_applicable` — todos métodos de `MediaBot`.
> Um arquivo separado ou duplicaria essa lógica ou importaria metade do
> `MediaBot`, o que é pior que o método viver ao lado de `search_series`, que
> faz exatamente a mesma dança. Se `media_bot.py` crescer demais, o momento de
> separar é junto com `search_series`, não só com este método.

**Interfaces:**
- Consumes: `explorar()` das Tasks 3, 4 e 5.
- Produces:
  - `SourceCapabilities.explora_genero: bool = False`
  - `MediaBot.explorar_genero(media_type, genero, subgenero=None, ordenacao="relevancia") -> list[dict]`
  - `Api.explorar(media_type, genero, subgenero=None, ordenacao="relevancia") -> {"job_id": str}`, emitindo o evento `explorar_results` com `{"results": [...], "genero": str}`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_servico_explorar.py
from scrapers.base_scraper import SourceCapabilities, BOOK_MEDIA
from media_bot import MediaBot
from scrapers.generos import genero_por_nome


class FonteExplora:
    name = "Explora"
    capabilities = SourceCapabilities(media_types=BOOK_MEDIA, explora_genero=True)
    def explorar(self, genero, subgenero=None, ordenacao="relevancia"):
        return [{"title": f"{genero.nome} 1", "source": self.name,
                 "metadata": {"identifier": "a"}}]


class FonteNaoExplora:
    name = "NaoExplora"
    capabilities = SourceCapabilities(media_types=BOOK_MEDIA)
    def explorar(self, *a, **k):
        raise AssertionError("não deveria ser chamada")


def _bot(fontes):
    bot = MediaBot.__new__(MediaBot)
    bot.scrapers = fontes
    bot.search_timeout = 5
    bot.cache = type("C", (), {"get": lambda *a, **k: None, "set": lambda *a, **k: None})()
    return bot


def test_only_sources_that_declare_it_are_asked():
    """OAPEN, Zenodo, OpenAlex e arXiv não exploram por gênero."""
    bot = _bot([FonteExplora(), FonteNaoExplora()])
    r = bot.explorar_genero("livro", "Terror")
    assert [x["source"] for x in r] == ["Explora"]


def test_unknown_genre_yields_nothing():
    bot = _bot([FonteExplora()])
    assert bot.explorar_genero("livro", "GêneroInexistente") == []


def test_results_are_deduplicated_across_sources():
    bot = _bot([FonteExplora(), FonteExplora()])
    assert len(bot.explorar_genero("livro", "Terror")) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_servico_explorar.py -v`
Expected: FAIL — `SourceCapabilities` não aceita `explora_genero`.

- [ ] **Step 3: Acrescentar a capacidade**

Em `scrapers/base_scraper.py`, dentro de `SourceCapabilities`:

```python
    #: A fonte sabe listar por gênero, sem termo de busca?
    explora_genero: bool = False
```

Marcar `explora_genero=True` em `MangaDexScraper`, `OpenLibraryScraper`,
`ProjectGutenbergScraper` e `ArchiveOrgScraper`.

- [ ] **Step 4: Implementar `explorar_genero` no MediaBot**

Em `media_bot.py`, reaproveitando o fan-out e a deduplicação que já existem:

```python
    def explorar_genero(self, media_type, genero, subgenero=None, ordenacao="relevancia"):
        """
        Lista obras de um gênero, sem termo de busca.

        Manhwa é mangá coreano: mesmo scraper, `originalLanguage` diferente.
        """
        from scrapers.generos import genero_por_nome

        g = genero_por_nome(media_type, genero)
        if g is None:
            print(f"   ❌ Gênero '{genero}' não existe para {media_type}.")
            return []

        idioma_origem = {"manhwa": "ko", "manga": "ja"}.get(
            (media_type or "").strip().lower(), "ja")

        aplicaveis = [s for s in self.scrapers
                      if getattr(s.capabilities, "explora_genero", False)
                      and self._scraper_applicable(s, media_type)]

        def chamar(scraper):
            if isinstance(scraper, MangaDexScraper):
                return scraper.explorar(g, subgenero, ordenacao, idioma_origem)
            return scraper.explorar(g, subgenero, ordenacao)

        respostas = {}
        pool = ThreadPoolExecutor(max_workers=max(len(aplicaveis), 1))
        try:
            futuros = {pool.submit(chamar, s): s for s in aplicaveis}
            try:
                for futuro in as_completed(futuros, timeout=self.search_timeout):
                    fonte = futuros[futuro]
                    try:
                        respostas[fonte.name] = futuro.result()
                    except Exception as e:
                        print(f"   ⚠️ Erro ao explorar em {fonte.name}: {e}")
            except FuturesTimeout:
                lentas = [s.name for f, s in futuros.items() if not f.done()]
                print(f"   ⏱️ {', '.join(lentas)}: demorou demais, seguindo sem ela(s).")
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

        todos = []
        for scraper in aplicaveis:
            for r in (respostas.get(scraper.name) or []):
                todos.append(self._serialize_result(r))
        return self._dedupe_results(todos)
```

- [ ] **Step 5: Expor na ponte JS↔Python**

Em `app/api.py`:

```python
    def explorar(self, media_type: str = "manga", genero: str = "",
                 subgenero: str = None, ordenacao: str = "relevancia") -> Dict[str, str]:
        def fn(bot, emit):
            resultados = bot.explorar_genero(media_type, genero, subgenero or None, ordenacao)
            sugestoes = onde_encontrar(genero, idioma=None) if not resultados else []
            emit("explorar_results", {"results": resultados, "genero": genero,
                                      "onde_encontrar": sugestoes})
            return {"count": len(resultados)}
        return {"job_id": self._service.submit(f"Explorar: {genero}", fn)}

    def generos(self, media_type: str = "manga"):
        """Taxonomia para a interface montar a grade."""
        from scrapers.generos import generos_de
        return [{"nome": g.nome, "subgeneros": list(g.subgeneros)}
                for g in generos_de(media_type)]
```

- [ ] **Step 6: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_servico_explorar.py -v`
Expected: PASS (3 testes).

- [ ] **Step 7: Commit**

```bash
git add scrapers/base_scraper.py media_bot.py app/api.py tests/test_servico_explorar.py
git commit -m "feat(genero): serviço de exploração com capacidade declarativa"
```

---

### Task 7: Tela Explorar

**Files:**
- Modify: `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`
- Test: `tests/test_frontend_explorar.py`

**Interfaces:**
- Consumes: `Api.explorar` e `Api.generos` da Task 6.
- Produces: nada.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_frontend_explorar.py
from pathlib import Path

FRONT = Path(__file__).parent.parent / "frontend"


def test_sidebar_has_the_explore_entry():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert 'data-view="explorar"' in html
    assert 'id="genero-grid"' in html
    assert 'id="subgenero-row"' in html


def test_ordering_selector_exists_for_books():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert 'id="explorar-ordenacao"' in html
    assert "mais_lidos" in html


def test_appjs_wires_explore():
    js = (FRONT / "app.js").read_text(encoding="utf-8")
    assert "explorar_results" in js
    assert "api().explorar(" in js
    assert "api().generos(" in js


def test_covers_degrade_without_breaking():
    """Uma capa do Open Library voltou 502 no teste: sem onerror, ícone quebrado."""
    js = (FRONT / "app.js").read_text(encoding="utf-8")
    assert "onerror" in js


def test_ordering_selector_is_hidden_outside_books():
    """No mangá seria escolha falsa: followedCount já é vivo e preciso."""
    js = (FRONT / "app.js").read_text(encoding="utf-8")
    assert "explorar-ordenacao" in js
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_frontend_explorar.py -v`
Expected: FAIL — `data-view="explorar"` ausente.

- [ ] **Step 3: Acrescentar o item na barra lateral**

Em `frontend/index.html`, depois do item de navegação `busca`:

```html
<button class="nav-item" data-view="explorar">
  <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9.5"/><path d="m15 9-4.5 1.5L9 15l4.5-1.5z"/></svg>
  Explorar
</button>
```

- [ ] **Step 4: Acrescentar a seção**

```html
<section class="view" id="view-explorar">
  <div class="view-head">
    <h1>Explorar</h1>
    <div class="sub">Escolha um gênero e veja o que existe — sem digitar nada.</div>
  </div>

  <div class="panel">
    <div class="search-bar">
      <select id="explorar-midia" title="Tipo de mídia">
        <option value="manga">manga</option>
        <option value="manhwa">manhwa</option>
        <option value="livro">livro</option>
        <option value="hq">hq</option>
      </select>
      <select id="explorar-ordenacao" title="Ordenação">
        <option value="relevancia">Melhores do gênero</option>
        <option value="mais_lidos">Mais lidos agora</option>
      </select>
    </div>
    <div id="genero-grid" class="quick-ranges" style="margin-top:14px"></div>
    <div id="subgenero-row" class="quick-ranges" style="margin-top:10px"></div>
    <div class="hint" id="explorar-aviso" style="margin-top:10px;display:none">
      O acervo de HQ é irregular: o assunto é inconsistente e mangá às vezes aparece
      junto. Por isso a lista de gêneros aqui é curta.
    </div>
  </div>

  <div id="explorar-results" class="card-grid"></div>
</section>
```

- [ ] **Step 5: Ligar no `app.js`**

```javascript
// --- explorar por gênero ---
let generoAtual = null;

function midiaExplorar() { return document.getElementById("explorar-midia").value; }

async function montarGrade() {
  const midia = midiaExplorar();
  const generos = await api().generos(midia);
  const grade = document.getElementById("genero-grid");
  grade.innerHTML = "";
  generoAtual = null;
  document.getElementById("subgenero-row").innerHTML = "";

  // #4 Consistência: só livro tem escolha real de ordenação.
  document.getElementById("explorar-ordenacao").style.display =
    midia === "livro" ? "" : "none";
  document.getElementById("explorar-aviso").style.display =
    midia === "hq" ? "" : "none";

  generos.forEach((g) => {
    const b = document.createElement("button");
    b.className = "range-chip";
    b.textContent = g.nome;
    b.addEventListener("click", () => escolherGenero(g, b));
    grade.appendChild(b);
  });
}

function escolherGenero(g, botao) {
  generoAtual = g;
  document.querySelectorAll("#genero-grid .range-chip")
    .forEach((x) => x.classList.remove("on"));
  botao.classList.add("on");

  const linha = document.getElementById("subgenero-row");
  linha.innerHTML = "";
  g.subgeneros.forEach((s) => {
    const b = document.createElement("button");
    b.className = "range-chip";
    b.textContent = s;
    b.addEventListener("click", () => explorar(s));
    linha.appendChild(b);
  });
  explorar(null);
}

async function explorar(subgenero) {
  if (!generoAtual) return;
  document.getElementById("explorar-results").innerHTML =
    '<p class="muted">Carregando…</p>';
  await api().explorar(midiaExplorar(), generoAtual.nome, subgenero,
                       document.getElementById("explorar-ordenacao").value);
}

document.getElementById("explorar-midia").addEventListener("change", montarGrade);
document.getElementById("explorar-ordenacao").addEventListener("change", () => explorar(null));

on("explorar_results", (p) => {
  const box = document.getElementById("explorar-results");
  if (!p.results.length) {
    if (p.onde_encontrar && p.onde_encontrar.length) renderOndeEncontrar(box, p.onde_encontrar);
    else box.innerHTML = '<p class="muted">Nada encontrado nesse gênero.</p>';
    return;
  }
  box.innerHTML = "";
  p.results.forEach((r) => {
    const div = document.createElement("div");
    div.className = "card";
    const capa = (r.metadata && r.metadata.cover_url) || "";
    // Capa pode voltar 502 (visto no Open Library): esconder sem quebrar a grade.
    const img = capa
      ? `<img class="cover" src="${capa}" alt="" loading="lazy"
             onerror="this.style.display='none'" />`
      : `<div class="cover"></div>`;
    div.innerHTML = `${img}
      <h3>${r.title || "Sem título"}</h3>
      <div class="muted">${(r.metadata && r.metadata.creator) || ""}</div>
      <button class="btn success" style="width:100%;margin-top:10px">Baixar →</button>`;
    div.querySelector("button").addEventListener("click",
      () => openChapters(r.title, r.source, midiaExplorar()));
    box.appendChild(div);
  });
});
```

Chamar `montarGrade()` quando a tela Explorar for aberta, junto do código que já troca de view.

- [ ] **Step 6: Estilo do chip selecionado**

Em `frontend/styles.css`:

```css
.range-chip.on { color:#fff; border-color:var(--blue); background:var(--blue-soft); }
```

- [ ] **Step 7: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest tests/test_frontend_explorar.py -v`
Expected: PASS (5 testes).

- [ ] **Step 8: Abrir o app e usar a tela**

Run: `PYTHONIOENCODING=utf-8 py -3.13 desktop.py`

Conferir, **olhando a janela**:
1. "Explorar" aparece na barra lateral e abre.
2. `manga` → clicar em "Terror" traz Berserk, Chainsaw Man e mostra capas.
3. Aparece a fileira de subgêneros; clicar em "Fantasmas" refina.
4. Trocar para `livro` → o seletor de ordenação aparece; "Terror" traz Misery, O Iluminado.
5. Trocar para `hq` → o seletor some, o aviso aparece.
6. Trocar para `manhwa` → resultados coreanos.

- [ ] **Step 9: Commit**

```bash
git add frontend/ tests/test_frontend_explorar.py
git commit -m "feat(genero): tela Explorar com grade, subgêneros e capas"
```

---

### Task 8: Testes de rede

**Files:**
- Create: `tests/test_explorar_rede.py`
- Modify: `pytest.ini` (criar, se não existir)
- Test: o próprio arquivo.

**Interfaces:**
- Consumes: tudo das Tasks 3 a 6.
- Produces: a marca `network`.

Decisão do autor: **este é um app de rede**, e todos os defeitos da rodada anterior foram de contrato de rede — nenhum apareceu com mock.

- [ ] **Step 1: Registrar a marca**

Criar `pytest.ini` na raiz:

```ini
[pytest]
markers =
    network: chama API externa de verdade. Pule com -m "not network" se estiver offline.
```

- [ ] **Step 2: Escrever os testes de rede**

```python
# tests/test_explorar_rede.py
"""Testes que chamam as APIs de verdade.

Mock não pega contrato: na rodada anterior, o Zenodo respondia 403 a
User-Agent de navegador, o OAPEN devolvia HTML em vez de JSON e o arXiv dava
429 — e todos os testes com dublê passavam.

Pule com: pytest -m "not network"
"""

import pytest

from scrapers.generos import genero_por_nome
from scrapers.mangadex_scraper import MangaDexScraper
from scrapers.openlibrary_scraper import OpenLibraryScraper
from scrapers.archive_scraper import ArchiveOrgScraper

pytestmark = pytest.mark.network


def _exigir(resultados, fonte):
    """Distingue 'a fonte mudou o contrato' de 'a fonte está fora do ar'."""
    if not resultados:
        pytest.fail(
            f"{fonte}: nenhum resultado. Ou o contrato mudou (campo renomeado, "
            f"filtro inválido) ou a fonte está fora do ar. Rode a consulta à mão "
            f"antes de tratar como regressão."
        )


def test_mangadex_horror_returns_real_manga_with_covers():
    r = MangaDexScraper().explorar(genero_por_nome("manga", "Terror"))
    _exigir(r, "MangaDex")
    assert any(x.metadata.get("cover_url") for x in r), "nenhuma capa veio"


def test_mangadex_manhwa_differs_from_manga():
    sc = MangaDexScraper()
    g = genero_por_nome("manhwa", "Romance")
    coreanos = sc.explorar(g, idioma_origem="ko")
    japoneses = sc.explorar(g, idioma_origem="ja")
    _exigir(coreanos, "MangaDex/manhwa")
    _exigir(japoneses, "MangaDex/manga")
    assert {x.title for x in coreanos} != {x.title for x in japoneses}


def test_openlibrary_horror_is_actually_horror():
    """Medido: por relevância vêm Misery, O Iluminado, O Exorcista."""
    r = OpenLibraryScraper().explorar(genero_por_nome("livro", "Terror"))
    _exigir(r, "Open Library")
    titulos = " ".join(x.title.lower() for x in r[:10])
    assert any(t in titulos for t in ["misery", "shining", "exorcist", "horror"]), \
        f"topo do gênero terror não parece terror: {[x.title for x in r[:5]]}"


def test_openlibrary_results_are_downloadable():
    r = OpenLibraryScraper().explorar(genero_por_nome("livro", "Poesia"))
    _exigir(r, "Open Library")
    assert all(x.metadata.get("identifier") for x in r), \
        "has_fulltext deveria garantir exemplar no Archive.org"


def test_archive_hq_returns_downloadable_comics():
    sc = ArchiveOrgScraper()
    r = sc.explorar(genero_por_nome("hq", "Super-heróis"))
    _exigir(r, "Archive.org/HQ")
    info = sc.get_series_info(r[0].url)
    assert info.get("download_url"), f"HQ sem arquivo: {r[0].title}"
```

- [ ] **Step 3: Rodar só os de rede**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest -m network -v`
Expected: PASS. Se falhar, a mensagem já diz como distinguir contrato de indisponibilidade.

- [ ] **Step 4: Rodar a suíte inteira**

Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest -q`
Expected: todos passam, incluindo os de rede.

Confirmar que o modo offline funciona:
Run: `PYTHONIOENCODING=utf-8 py -3.13 -m pytest -q -m "not network"`
Expected: passa, com os de rede marcados como desselecionados.

- [ ] **Step 5: Commit**

```bash
git add pytest.ini tests/test_explorar_rede.py
git commit -m "test(genero): testes de rede na suíte padrão"
```

---

### Task 9: Documentação

**Files:**
- Modify: `README.md`, `docs/AUDITORIA_FONTES.md`
- Test: nenhum.

- [ ] **Step 1: Acrescentar a seção ao README**

Depois da seção de busca:

```markdown
### 🧭 Explorar por gênero
Tela de descoberta: escolha um gênero e veja o que existe, sem digitar nada.

- **Mangá e manhwa** — taxonomia oficial do MangaDex (gênero + tema), ordenados
  por seguidores. Manhwa é o mesmo acervo filtrado por idioma de origem coreano.
- **Livro** — Open Library e Gutendex, ordenados por relevância do gênero, com
  a opção "mais lidos agora". Só entra o que tem exemplar baixável.
- **HQ** — Archive.org. Lista curta de propósito: o acervo é irregular e o
  assunto é inconsistente.
```

- [ ] **Step 2: Atualizar a auditoria**

Em `docs/AUDITORIA_FONTES.md`, na tabela de estado da implementação, acrescentar:

```markdown
| Explorar por gênero | ✅ feita — ver `docs/superpowers/specs/2026-07-26-busca-por-genero-design.md` |
```

- [ ] **Step 3: Rodar a suíte e commitar**

```bash
PYTHONIOENCODING=utf-8 py -3.13 -m pytest -q
git add README.md docs/AUDITORIA_FONTES.md
git commit -m "docs: documenta a exploração por gênero"
```

---

## Notas para quem executar

**Lição da execução: teste que só cobre o caso fácil não cobre nada.** O mesmo
defeito apareceu duas vezes, em tarefas diferentes — subgênero que não resolve e
é ignorado em silêncio — e nas duas o teste do plano exercitava exatamente o
único valor que funcionava (`"Fantasmas"` na Task 3, `"Distopia"` na Task 4).
Quando houver um mapa de rótulo para termo de API, **varra o mapa inteiro**: o
teste tem que iterar sobre a taxonomia declarada, não sobre um exemplo escolhido
à mão.

**Lição da execução: refatoração que "não quebrou nenhum teste" pode ter
quebrado produção.** Extrair `_resultados_de()` do `search()` do Gutendex fez
ele parar de respeitar a ordem de `formats` e de extrair volume/capítulo — e a
suíte passou verde, porque os testes daquele caminho eram fracos. Antes de
extrair código compartilhado, verifique se os testes existentes de fato travam o
comportamento que você está prestes a mover.

**Lição da execução: os rótulos são em português, as APIs falam inglês.** A
primeira versão deste plano prescrevia, na mesma Task 3, um teste passando
`subgenero="Fantasmas"` e uma implementação que só resolvia nomes de tag em
inglês — o código não fazia passar o próprio teste. A tradução
(`SUBGENERO_TAG_MANGADEX`) mora em `scrapers/generos.py`, junto da taxonomia que
ela descreve, com teste travando que todo subgênero listado tenha tag. Sem esse
teste, um subgênero sem tag cai em silêncio para filtro só de gênero: o usuário
clica em "Detetive", vê "Mistério" inteiro, e nada avisa que o refinamento não
aconteceu. O mesmo vale para qualquer par rótulo-em-português / termo-de-API que
aparecer daqui pra frente.

**A Task 5 tem uma medição antes do código, e ela não é opcional.** A grade de HQ nasce do que passar no Step 1. Se só `superhero` sobreviver, a grade tem um item. Isso é o resultado correto: a spec (§5.3) decidiu que seis gêneros que funcionam valem mais que vinte que enganam.

**Não gravar UUID de tag do MangaDex em lugar nenhum.** É por isso que a Task 2 existe.

**Verificação visual é obrigatória na Task 7.** Teste de arquivo confirma que o elemento existe, não que a tela abre nem que a capa carrega.

**Ordem entre os planos.** Este plano pressupõe o design system já migrado. Construir a tela Explorar no estilo antigo e redesenhar depois é retrabalho puro.
