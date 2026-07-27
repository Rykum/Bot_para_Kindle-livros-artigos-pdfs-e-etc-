"""Busca por campo (título / autor / tudo) e ampliação do alcance.

Motivação: buscar só em `title:` no Archive.org descartava a maior parte do
acervo — "O Cortiço" achava 4 itens no campo título contra 226 na busca ampla.
"""

from scrapers.base_scraper import BaseScraper
from scrapers.archive_scraper import ArchiveOrgScraper
from scrapers.gutenberg_scraper import ProjectGutenbergScraper
from scrapers.mangadex_scraper import MangaDexScraper


class FakeResp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def _docs(*identifiers):
    return {"response": {"docs": [
        {"identifier": i, "title": f"Livro {i}", "mediatype": "texts"} for i in identifiers
    ]}}


# --------------------------- normalização ---------------------------

def test_normalize_search_by_defaults_to_titulo():
    assert BaseScraper.normalize_search_by(None) == "titulo"
    assert BaseScraper.normalize_search_by("") == "titulo"
    assert BaseScraper.normalize_search_by("invalido") == "titulo"
    assert BaseScraper.normalize_search_by("  AUTOR ") == "autor"
    assert BaseScraper.normalize_search_by("tudo") == "tudo"


# --------------------------- Archive.org ---------------------------

def test_archive_author_mode_uses_creator_field():
    sc = ArchiveOrgScraper()
    q = sc.build_query("Machado de Assis", "autor")
    assert 'creator:("Machado de Assis"' in q
    assert "title:(" not in q
    assert "mediatype:texts" in q


def test_archive_author_mode_also_tries_the_inverted_name():
    """O Mindhunter está catalogado como "Douglas, John E" — sem a inversão
    a busca por "John Douglas" nunca o encontra."""
    q = ArchiveOrgScraper().build_query("John Douglas", "autor")
    assert '"John Douglas"' in q
    assert '"Douglas, John"' in q
    assert " OR " in q


def test_archive_single_word_author_has_no_inversion():
    q = ArchiveOrgScraper().build_query("Machado", "autor")
    assert q.count('"') == 2, "um nome só não tem ordem para inverter"


def test_archive_queries_are_quoted_as_phrases():
    """Sem aspas o Archive.org trata cada palavra como alternativa e o
    resultado certo se perde no meio do ruído."""
    sc = ArchiveOrgScraper()
    assert 'title:("O Cortiço")' in sc.build_query("O Cortiço", "titulo")
    assert '("O Cortiço")' in sc.build_query("O Cortiço", "tudo")


def test_archive_embedded_quotes_do_not_break_the_query():
    q = ArchiveOrgScraper().build_query('O "Cortiço"', "titulo")
    assert q.count('"') == 2, "aspas do usuário não podem vazar para a consulta"


def test_archive_tudo_mode_has_no_field_restriction():
    sc = ArchiveOrgScraper()
    q = sc.build_query("O Cortiço", "tudo")
    assert "title:(" not in q and "creator:(" not in q
    assert '("O Cortiço")' in q and "mediatype:texts" in q


def test_archive_sorts_by_relevance_not_downloads(monkeypatch):
    """Ordenar por downloads enterrava o item certo sob best-sellers."""
    sc = ArchiveOrgScraper()
    captured = {}

    def fake(url, params=None, retries=0):
        captured.update(params or {})
        return FakeResp(_docs(*[f"i{n}" for n in range(30)]))

    monkeypatch.setattr(sc, "make_request", fake)
    sc.search("Mindhunter", search_by="titulo")
    assert "sort[]" not in captured


def test_archive_language_filter_applies_to_every_mode():
    sc = ArchiveOrgScraper()
    for mode in ("titulo", "autor", "tudo"):
        q = sc.build_query("Dom Casmurro", mode, language="pt")
        assert "portuguese" in q, mode


def test_archive_title_search_is_broadened_when_results_are_few(monkeypatch):
    """Poucos acertos no título -> completa com a busca ampla, sem duplicar."""
    sc = ArchiveOrgScraper()
    queries = []

    def fake(url, params=None, retries=0):
        q = params.get("q")
        queries.append(q)
        if q.startswith("title:"):
            return FakeResp(_docs("a", "b"))
        return FakeResp(_docs("b", "c", "d"))  # "b" repete de propósito

    monkeypatch.setattr(sc, "make_request", fake)
    res = sc.search("O Cortiço", search_by="titulo")

    assert len(queries) == 2, "deveria disparar a consulta ampla de complemento"
    assert queries[0].startswith("title:")
    assert not queries[1].startswith("title:")
    assert [r.metadata["identifier"] for r in res] == ["a", "b", "c", "d"]


def test_archive_title_search_not_broadened_when_results_are_plenty(monkeypatch):
    sc = ArchiveOrgScraper()
    sc.broaden_threshold = 2
    queries = []

    def fake(url, params=None, retries=0):
        queries.append(params.get("q"))
        return FakeResp(_docs("a", "b", "c"))

    monkeypatch.setattr(sc, "make_request", fake)
    sc.search("Dandadan", search_by="titulo")
    assert len(queries) == 1, "com resultados suficientes não precisa ampliar"


def test_archive_author_mode_is_not_broadened(monkeypatch):
    """Ampliar a busca por autor traria ruído — só o modo título amplia."""
    sc = ArchiveOrgScraper()
    queries = []

    def fake(url, params=None, retries=0):
        queries.append(params.get("q"))
        return FakeResp(_docs("a"))

    monkeypatch.setattr(sc, "make_request", fake)
    sc.search("Machado de Assis", search_by="autor")
    assert len(queries) == 1


def test_archive_author_mode_ranks_full_name_matches_first(monkeypatch):
    """Quem bate com o nome inteiro sobe; quem casou só pelo sobrenome desce."""
    sc = ArchiveOrgScraper()

    def fake(url, params=None, retries=0):
        return FakeResp({"response": {"docs": [
            {"identifier": "ruido", "title": "Despatches", "creator": "Haig, Douglas"},
            {"identifier": "certo", "title": "Mindhunter", "creator": "Douglas, John E"},
            {"identifier": "lista", "title": "Outro", "creator": ["Douglas", "John"]},
        ]}})

    monkeypatch.setattr(sc, "make_request", fake)
    res = sc.search("John Douglas", search_by="autor")
    ordem = [r.metadata["identifier"] for r in res]
    assert ordem.index("certo") < ordem.index("ruido")
    assert ordem.index("lista") < ordem.index("ruido"), "creator em lista também conta"


def test_archive_title_mode_keeps_source_order(monkeypatch):
    """Fora do modo autor, a ordem de relevância do Archive.org é preservada."""
    sc = ArchiveOrgScraper()
    sc.broaden_threshold = 0

    def fake(url, params=None, retries=0):
        return FakeResp(_docs("z", "a", "m"))

    monkeypatch.setattr(sc, "make_request", fake)
    res = sc.search("Mindhunter", search_by="titulo")
    assert [r.metadata["identifier"] for r in res] == ["z", "a", "m"]


def test_archive_last_resort_rescues_title_plus_author(monkeypatch):
    """"Sapiens Harari" não existe como frase em título nenhum: sem o último
    recurso a busca devolve zero."""
    sc = ArchiveOrgScraper()
    queries = []

    def fake(url, params=None, retries=0):
        q = params.get("q")
        queries.append(q)
        if " AND " in q.split(") AND mediatype")[0]:      # consulta de termos
            return FakeResp({"response": {"docs": [
                {"identifier": "ok", "title": "Sapiens uma breve história", "mediatype": "texts"},
            ]}})
        return FakeResp({"response": {"docs": []}})

    monkeypatch.setattr(sc, "make_request", fake)
    res = sc.search("Sapiens Harari", search_by="titulo")
    assert len(queries) == 3, "frase no título -> frase em tudo -> termos soltos"
    assert [r.metadata["identifier"] for r in res] == ["ok"]


def test_archive_last_resort_stays_off_when_there_are_results(monkeypatch):
    """A consulta de termos traz muito lixo: só entra se quase nada apareceu."""
    sc = ArchiveOrgScraper()
    sc.broaden_threshold = 0
    queries = []

    def fake(url, params=None, retries=0):
        queries.append(params.get("q"))
        return FakeResp(_docs("a", "b", "c"))

    monkeypatch.setattr(sc, "make_request", fake)
    sc.search("Grande Sertao Veredas", search_by="titulo")
    assert len(queries) == 1


def test_archive_last_resort_needs_more_than_one_term(monkeypatch):
    """Com uma palavra só, a consulta de termos é igual à frase — não repete."""
    sc = ArchiveOrgScraper()
    queries = []

    def fake(url, params=None, retries=0):
        queries.append(params.get("q"))
        return FakeResp({"response": {"docs": []}})

    monkeypatch.setattr(sc, "make_request", fake)
    sc.search("Mindhunter", search_by="titulo")
    assert len(queries) == 2, "só a frase no título e a frase em tudo"


def test_archive_term_coverage_ranking_ignores_accents():
    sc = ArchiveOrgScraper()
    docs = [
        {"identifier": "pouco", "title": "Historia do Brasil"},
        {"identifier": "muito", "title": "Memórias Póstumas de Brás Cubas"},
    ]
    ordenado = sc._rank_by_term_coverage(docs, "Memorias Postumas Bras Cubas")
    assert ordenado[0]["identifier"] == "muito"


def test_archive_asks_for_more_rows_than_before():
    assert ArchiveOrgScraper().rows >= 75


# --------------------------- Gutenberg ---------------------------

def _gutendex(*books):
    return {"results": [
        {"id": i, "title": t, "authors": [{"name": a} for a in authors],
         "formats": {"application/epub+zip": f"https://x/{i}.epub"}}
        for i, (t, authors) in enumerate(books, 1)
    ]}


def test_gutenberg_author_mode_drops_title_only_matches(monkeypatch):
    sc = ProjectGutenbergScraper()

    def fake(url, params=None, retries=0):
        return FakeResp(_gutendex(
            ("Dom Casmurro", ["Machado de Assis"]),
            ("Vida de Machado", ["Outro Autor"]),   # casou pelo título, não pelo autor
        ))

    monkeypatch.setattr(sc, "make_request", fake)
    res = sc.search("Machado de Assis", search_by="autor")
    assert [r.title for r in res] == ["Dom Casmurro"]


def test_gutenberg_title_mode_keeps_everything(monkeypatch):
    sc = ProjectGutenbergScraper()

    def fake(url, params=None, retries=0):
        return FakeResp(_gutendex(
            ("Dom Casmurro", ["Machado de Assis"]),
            ("Vida de Machado", ["Outro Autor"]),
        ))

    monkeypatch.setattr(sc, "make_request", fake)
    assert len(sc.search("Machado", search_by="titulo")) == 2


def test_gutenberg_search_only_uses_desired_formats(monkeypatch):
    """search() precisa continuar respeitando o parâmetro `formats` de quem
    chama — a API tem epub disponível mas só pdf foi pedido, então o pdf tem
    que vencer. A extração de explorar() para _resultados_de() (que ignora
    `formats` e sempre prefere epub) não pode vazar para search()."""
    sc = ProjectGutenbergScraper()

    def fake(url, params=None, retries=0):
        return FakeResp({"results": [{
            "id": 1, "title": "Dom Casmurro",
            "authors": [{"name": "Machado de Assis"}],
            "formats": {
                "application/epub+zip": "https://x/1.epub",
                "application/pdf": "https://x/1.pdf",
            },
        }]})

    monkeypatch.setattr(sc, "make_request", fake)
    res = sc.search("Dom Casmurro", formats=["pdf"], search_by="titulo")
    assert res[0].format_type == "pdf"
    assert res[0].download_url == "https://x/1.pdf"


def test_gutenberg_search_extracts_volume_and_chapter_from_title(monkeypatch):
    """search() precisa continuar preenchendo volume/capítulo quando o
    título traz — comportamento que a extração para _resultados_de() (usado
    só por explorar(), que não chama parse_volume_chapter) não pode apagar."""
    sc = ProjectGutenbergScraper()

    def fake(url, params=None, retries=0):
        return FakeResp(_gutendex(("Coleção Vol. 2 Capítulo 5", ["Autor X"])))

    monkeypatch.setattr(sc, "make_request", fake)
    res = sc.search("Coleção", search_by="titulo")
    assert res[0].volume == 2
    assert res[0].chapter == 5


# --------------------------- MangaDex ---------------------------

def test_mangadex_author_mode_resolves_name_to_ids(monkeypatch):
    """A API do MangaDex só aceita UUID de autor, nunca o nome em texto."""
    sc = MangaDexScraper()
    calls = []

    def fake(url, params=None, retries=0):
        calls.append((url, params))
        if url.endswith("/author"):
            return FakeResp({"data": [{"id": "uuid-1"}, {"id": "uuid-2"}]})
        return FakeResp({"data": []})

    monkeypatch.setattr(sc, "make_request", fake)
    sc.search("Eiichiro Oda", search_by="autor")

    assert calls[0][0].endswith("/author")
    manga_url, manga_params = calls[1]
    assert manga_url.endswith("/manga")
    assert manga_params["authors[]"] == ["uuid-1", "uuid-2"]
    assert "title" not in manga_params


def test_mangadex_author_mode_returns_empty_when_author_unknown(monkeypatch):
    sc = MangaDexScraper()
    calls = []

    def fake(url, params=None, retries=0):
        calls.append(url)
        return FakeResp({"data": []})

    monkeypatch.setattr(sc, "make_request", fake)
    assert sc.search("Autor Inexistente", search_by="autor") == []
    assert len(calls) == 1, "sem autor resolvido, não faz sentido buscar mangás"


def test_mangadex_title_mode_still_uses_title(monkeypatch):
    sc = MangaDexScraper()
    captured = {}

    def fake(url, params=None, retries=0):
        captured.update(params or {})
        return FakeResp({"data": []})

    monkeypatch.setattr(sc, "make_request", fake)
    sc.search("Dandadan", search_by="titulo")
    assert captured["title"] == "Dandadan"
    assert "authors[]" not in captured
