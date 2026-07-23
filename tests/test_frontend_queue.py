from pathlib import Path

FRONT = Path(__file__).parent.parent / "frontend"


def test_index_has_queue_controls():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert 'id="queue-list"' in html
    assert 'id="btn-queue-pause"' in html
    assert 'id="btn-queue-clear"' in html
    assert 'id="btn-cancel"' not in html


def test_appjs_wires_queue():
    js = (FRONT / "app.js").read_text(encoding="utf-8")
    assert "queue_update" in js
    assert "enqueue" in js
    assert "cancel_item" in js and "retry_item" in js
    assert "window.pushEvent" in js and "window.pywebview.api" in js
    assert "currentDownloadJob" not in js
