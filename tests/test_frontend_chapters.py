from pathlib import Path

FRONT = Path(__file__).parent.parent / "frontend"


def test_index_has_chapter_picker_and_language_selectors():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert 'id="view-chapters"' in html
    assert 'id="lang-primary"' in html
    assert 'id="lang-fallback"' in html
    assert 'id="btn-download-all"' in html
    assert 'id="btn-download-selected"' in html


def test_appjs_wires_chapters_and_cancel_reset():
    js = (FRONT / "app.js").read_text(encoding="utf-8")
    assert "list_chapters" in js
    assert "chapters_list" in js
    # cancelar dá feedback e reseta estado
    assert "Cancelando" in js
    assert "result.cancelled" in js or "p.result" in js
    # validação de erro-prevenção: baixar selecionados desabilitado sem seleção
    assert "btn-download-selected" in js
    # bridge intacta
    assert "window.pushEvent" in js
    assert "window.pywebview.api" in js


def test_styles_has_chapter_grid():
    css = (FRONT / "styles.css").read_text(encoding="utf-8")
    assert "chapter" in css.lower()
