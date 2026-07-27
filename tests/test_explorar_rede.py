# -*- coding: utf-8 -*-
"""Testes que chamam as APIs de verdade.

Mock não pega contrato: na rodada anterior, o Zenodo respondia 403 a
User-Agent de navegador, o OAPEN devolvia HTML em vez de JSON e o arXiv dava
429 — e todos os testes com dublê passavam.

Pule com: pytest -m "not network"
"""

import pytest

from scrapers.generos import genero_por_nome, generos_de, SUBGENERO_TAG_MANGADEX
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


def test_subgenero_tag_mangadex_values_exist_in_real_api():
    """Task 3 travou só as CHAVES de SUBGENERO_TAG_MANGADEX (ver
    tests/test_generos.py). Um erro de digitação no VALOR — "Ghots" em vez de
    "Ghosts" — passaria verde ali e só se manifestaria em produção, como
    filtro que silenciosamente não filtra nada. scrapers/generos.py é sem
    rede de propósito, então a validação contra a API real fica aqui.
    """
    sc = MangaDexScraper()
    resposta = sc.make_request(f"{sc.base_url}/manga/tag")
    _exigir([resposta] if resposta else [], "MangaDex/tag")

    nomes_em_ingles = {
        t["attributes"]["name"]["en"]
        for t in resposta.json().get("data", [])
        if t.get("attributes", {}).get("name", {}).get("en")
    }
    _exigir(nomes_em_ingles, "MangaDex/tag")

    for subgenero, tag in SUBGENERO_TAG_MANGADEX.items():
        assert tag in nomes_em_ingles, (
            f"SUBGENERO_TAG_MANGADEX[{subgenero!r}] = {tag!r} não existe mais "
            f"entre as tags do MangaDex. Corrija o valor em scrapers/generos.py."
        )

    for g in generos_de("manga"):
        assert g.mangadex_tag in nomes_em_ingles, (
            f"Genero {g.nome!r}.mangadex_tag = {g.mangadex_tag!r} não existe "
            f"mais entre as tags do MangaDex. Corrija o valor em "
            f"scrapers/generos.py."
        )
