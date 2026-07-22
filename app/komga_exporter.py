"""Exporta a coleção baixada para o layout esperado por Komga/Kavita.

Estrutura: <export_root>/<série>/<Chapter NNN>/<arquivo>. Copia (não move) e
é idempotente — arquivos já presentes no destino são pulados.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Dict


class KomgaExporter:
    def __init__(self, library: Any, export_root: str = "./exports/komga"):
        self.library = library
        self.export_root = Path(export_root)

    @staticmethod
    def sanitize(name: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*]+', "_", name)
        return cleaned.strip().strip("_.")

    def export_series(self, title: str) -> Dict[str, Any]:
        series = self.library.get_or_create_series(title)
        base_path = self.export_root / self.sanitize(series.title)
        base_path.mkdir(parents=True, exist_ok=True)

        exported = 0
        skipped = 0
        for volume_number, chapter_number, file_path, _fmt in self.library.iter_downloaded_files(series):
            source = Path(file_path)
            if not source.exists():
                skipped += 1
                continue

            if chapter_number is not None:
                folder = f"Chapter {int(chapter_number):03d}"
            elif volume_number is not None:
                folder = f"Volume {int(volume_number):03d}"
            else:
                folder = "Outros"

            target_dir = base_path / folder
            target_dir.mkdir(parents=True, exist_ok=True)
            destination = target_dir / source.name

            if destination.exists():
                skipped += 1
                continue

            shutil.copy(source, destination)
            exported += 1

        return {"base_path": str(base_path), "exported": exported, "skipped": skipped}
