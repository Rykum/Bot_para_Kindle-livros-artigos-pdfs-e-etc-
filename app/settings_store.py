"""Armazenamento simples de configurações do usuário (JSON em disco).

Usado para persistir preferências entre sessões (ex.: pasta de downloads).
O caminho é um módulo-level var para facilitar isolamento em testes.
"""

from __future__ import annotations

import json
from pathlib import Path

# Arquivo na raiz do projeto (ao lado de media_bot.py).
_PATH = Path(__file__).resolve().parent.parent / "media_bot_settings.json"


def _load() -> dict:
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_setting(key: str, default=None):
    return _load().get(key, default)


def set_setting(key: str, value) -> None:
    data = _load()
    data[key] = value
    try:
        _PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
