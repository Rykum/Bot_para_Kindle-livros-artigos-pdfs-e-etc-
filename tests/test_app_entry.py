"""Smoke test para o entrypoint app.py (janela pywebview não é verificável em CI).

O repositório tem um pacote app/ (app/api.py, app/bot_service.py, ...) e este
projeto também cria um app.py de nível superior como entrypoint da GUI. Isso
faz `import app` resolver para o pacote, não para o arquivo — por isso o
arquivo é carregado aqui via importlib.util.spec_from_file_location, usando
um nome de módulo diferente ("app_entry") para não colidir com o pacote.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

APP_PY = Path(__file__).parent.parent / "app.py"
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


def _load_app_entry():
    spec = importlib.util.spec_from_file_location("app_entry", APP_PY)
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
