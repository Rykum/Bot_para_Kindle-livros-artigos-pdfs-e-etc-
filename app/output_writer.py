"""Camada única de saída: cria o .cbz com ComicInfo.xml na raiz (interop Komga/Kavita)."""

from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple
from xml.sax.saxutils import escape

_LANG_MAP = {"pt-br": "pt", "pt": "pt", "en": "en", "es": "es"}
_INT_FIELDS = {"Number", "Volume", "Count", "PageCount"}
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class OutputWriter:
    def build_comicinfo_xml(self, meta: dict) -> str:
        parts: List[str] = []

        def add(tag: str, value) -> None:
            if value is not None and value != "":
                if tag in _INT_FIELDS and isinstance(value, (int, float)) and not isinstance(value, bool):
                    if float(value).is_integer():
                        value = int(value)
                text = _CONTROL_CHARS_RE.sub("", str(value))
                parts.append(f"  <{tag}>{escape(text)}</{tag}>")

        add("Series", meta.get("series"))
        add("Number", meta.get("number"))
        add("Volume", meta.get("volume"))
        add("Title", meta.get("title"))
        add("Summary", meta.get("summary"))
        add("Writer", meta.get("writer"))
        add("Count", meta.get("count"))
        add("PageCount", meta.get("page_count"))
        add("Web", meta.get("web"))
        language = meta.get("language")
        if language:
            add("LanguageISO", _LANG_MAP.get(str(language).lower(), str(language).lower()))
        add("Manga", "YesAndRightToLeft")

        body = "\n".join(parts)
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n'
            f"{body}\n</ComicInfo>\n"
        )

    def write_cbz(self, pages: List[Tuple[str, bytes]], comicinfo: dict, dest_path) -> dict:
        dest_path = Path(dest_path)
        with zipfile.ZipFile(dest_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("ComicInfo.xml", self.build_comicinfo_xml(comicinfo))
            for name, data in pages:
                archive.writestr(name, data)

        raw = dest_path.read_bytes()
        return {
            "filepath": str(dest_path),
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "page_count": len(pages),
        }
