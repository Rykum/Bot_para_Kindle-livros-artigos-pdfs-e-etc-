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


# --------------------------------------------------------------------------
# Chaves de API das fontes que exigem cadastro (Google Books, CORE, Europeana,
# DPLA, BHL). Ficam aqui, nunca no código — este arquivo já está no .gitignore.
# --------------------------------------------------------------------------

_API_KEYS = "api_keys"


def get_api_key(source_name: str) -> str | None:
    """Chave da fonte, ou None se o usuário ainda não configurou."""
    chaves = _load().get(_API_KEYS) or {}
    valor = chaves.get((source_name or "").strip().lower())
    return valor.strip() if isinstance(valor, str) and valor.strip() else None


def set_api_key(source_name: str, key: str | None) -> None:
    """Guarda (ou apaga, com valor vazio) a chave de uma fonte."""
    data = _load()
    chaves = dict(data.get(_API_KEYS) or {})
    nome = (source_name or "").strip().lower()
    if key and key.strip():
        chaves[nome] = key.strip()
    else:
        chaves.pop(nome, None)
    data[_API_KEYS] = chaves
    try:
        _PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def configured_api_keys() -> list[str]:
    """Nomes das fontes que já têm chave — para a interface mostrar o estado."""
    return sorted((_load().get(_API_KEYS) or {}).keys())
