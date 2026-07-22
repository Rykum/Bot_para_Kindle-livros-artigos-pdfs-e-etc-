#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entrypoint da interface desktop do Media Bot (pywebview)."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import webview
except ImportError:  # pragma: no cover
    print("pywebview não está instalado. Rode: py -3.13 -m pip install pywebview")
    raise SystemExit(1)

from app.api import Api
from app.bot_service import BotService
from media_bot import MediaBot


def frontend_dir() -> Path:
    """Resolve a pasta frontend/ em dev e dentro do bundle PyInstaller."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "frontend"
    return Path(__file__).parent / "frontend"


def main() -> None:
    service = BotService(bot_factory=MediaBot, event_sink=lambda n, p: api.emit_event(n, p))
    api = Api(service)
    service.start()

    index = frontend_dir() / "index.html"
    window = webview.create_window(
        "Media Bot PT-BR",
        url=str(index),
        js_api=api,
        width=1240,
        height=820,
        min_size=(1000, 680),
        background_color="#0f172a",
    )
    api.set_window(window)

    try:
        webview.start()
    finally:
        service.stop()


if __name__ == "__main__":
    main()
