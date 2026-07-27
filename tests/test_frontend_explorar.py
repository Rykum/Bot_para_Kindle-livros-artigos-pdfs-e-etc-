# tests/test_frontend_explorar.py
import re
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
    """No mangá seria escolha falsa: followedCount já é vivo e preciso.

    Antes este teste só checava a substring 'explorar-ordenacao', que aparece
    4x no arquivo por outros motivos (id do elemento, listener de 'change',
    leitura do .value) — apagar o bloco que esconde o seletor fora de 'livro'
    deixava o teste verde. O regex abaixo ancora na lógica de fato: a
    atribuição de .style.display condicionada a midia === "livro".
    """
    js = (FRONT / "app.js").read_text(encoding="utf-8")
    padrao = re.compile(
        r'getElementById\("explorar-ordenacao"\)\.style\.display\s*=\s*'
        r'\r?\n?\s*midia\s*===\s*"livro"\s*\?\s*""\s*:\s*"none"'
    )
    assert padrao.search(js), (
        "seletor de ordenação precisa ficar escondido fora de 'livro' "
        "(midia === \"livro\" ? \"\" : \"none\")"
    )
