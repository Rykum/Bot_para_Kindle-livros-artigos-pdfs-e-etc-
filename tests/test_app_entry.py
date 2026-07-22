"""Smoke test para o entrypoint desktop.py (janela pywebview não é verificável em CI).

O entrypoint da GUI é desktop.py (nomeado assim para não colidir com o pacote
app/). O arquivo é carregado aqui via importlib.util.spec_from_file_location
para exercitar seu código de nível superior (imports e frontend_dir) sem
disparar a janela pywebview.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

DESKTOP_PY = Path(__file__).parent.parent / "desktop.py"
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


def _load_app_entry():
    spec = importlib.util.spec_from_file_location("desktop_entry", DESKTOP_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frontend_dir_points_at_existing_index():
    module = _load_app_entry()
    index = module.frontend_dir() / "index.html"
    assert index.exists()


def test_app_js_has_bridge_contract():
    app_js = (FRONTEND_DIR / "app.js").read_text(encoding="utf-8")
    assert "window.pushEvent" in app_js
    assert "window.pywebview.api" in app_js or "window.pywebview && window.pywebview.api" in app_js
