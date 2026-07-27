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


def test_landing_mentions_genre_exploration():
    """A landing já ficou desatualizada duas vezes: anunciava 3 fontes quando
    havia 9, e depois ignorou a tela Explorar. Funcionalidade que existe no app
    precisa existir no cartão de visita."""
    html = SITE.read_text(encoding="utf-8")
    assert "gênero" in html.lower(), "landing não menciona busca por gênero"
    assert "explorar" in html.lower(), "landing não menciona a tela Explorar"


def test_landing_hq_grid_size_matches_the_code():
    """O número de gêneros de HQ anunciado tem que bater com o que existe.

    A disciplina do projeto é que número escrito sem medir quebra em silêncio —
    e uma landing que promete mais do que entrega é a pior versão disso.
    """
    from scrapers.generos import generos_de
    html = SITE.read_text(encoding="utf-8")
    quantos = len(generos_de("hq"))
    assert quantos == 3, (
        f"a grade de HQ tem {quantos} gêneros; a landing afirma que sobraram "
        f"três. Atualize os dois juntos."
    )
    assert "três" in html.lower() or str(quantos) in html


def test_landing_never_claims_a_stale_closed_list_of_sources():
    """A página se contradizia: 9 fontes na tabela, 3 num card acima."""
    html = SITE.read_text(encoding="utf-8")
    for obsoleta in [
        "Archive.org e Project Gutenberg",
        "MangaDex, Archive.org e Gutenberg",
    ]:
        assert obsoleta not in html, \
            f"lista fechada desatualizada na landing: {obsoleta!r}"
