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


def test_every_manga_subgenre_maps_to_a_mangadex_tag():
    """Subgênero sem tag cai para filtro só de gênero, sem avisar o usuário."""
    from scrapers.generos import SUBGENERO_TAG_MANGADEX, generos_de
    faltando = [
        (g.nome, s)
        for g in generos_de("manga")
        for s in g.subgeneros
        if s not in SUBGENERO_TAG_MANGADEX
    ]
    assert not faltando, f"subgêneros sem tag do MangaDex: {faltando}"
