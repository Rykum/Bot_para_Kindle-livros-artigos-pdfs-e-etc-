#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera o executável MediaBot.exe com PyInstaller.

Uso: py -3.13 build.py
Saída: dist/MediaBot.exe
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def main() -> int:
    # Evita UnicodeEncodeError ao imprimir emojis em consoles Windows (cp1252).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    # No Windows, --add-data usa ';' como separador (origem;destino).
    sep = ";" if sys.platform.startswith("win") else ":"
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile", "--windowed",
        "--name", "MediaBot",
        f"--add-data", f"frontend{sep}frontend",
        "--collect-all", "webview",
    ]
    icon = ROOT / "assets" / "icon.ico"
    if icon.exists():
        args += ["--icon", str(icon)]
    args.append("desktop.py")

    print("Executando:", " ".join(args))
    result = subprocess.run(args, cwd=str(ROOT))
    if result.returncode == 0:
        print("\n✅ Build concluído: dist/MediaBot.exe")
    else:
        print("\n❌ Build falhou.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
