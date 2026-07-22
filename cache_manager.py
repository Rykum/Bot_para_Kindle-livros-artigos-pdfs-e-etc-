#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cache local simples para resultados de busca e metadados.
Armazena JSON em disco com TTL configurável.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional


class CacheManager:
    def __init__(self, cache_dir: str = "./cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key_to_path(self, key: str) -> Path:
        cache_key = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{cache_key}.json"

    def get(self, key: str, max_age_seconds: int = 86400) -> Optional[Any]:
        cache_file = self._key_to_path(key)
        if not cache_file.exists():
            return None

        age = time.time() - cache_file.stat().st_mtime
        if age > max_age_seconds:
            return None

        try:
            with cache_file.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return None

    def set(self, key: str, value: Any) -> None:
        cache_file = self._key_to_path(key)
        with cache_file.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)

    def clear(self) -> int:
        removed = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
                removed += 1
            except Exception:
                continue
        return removed