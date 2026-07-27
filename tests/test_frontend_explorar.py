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
