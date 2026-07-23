"""Enriquecimento de metadados via Jikan (MyAnimeList) com fallback AniList.

Não requer API key. Degrada graciosamente a None em qualquer erro de rede.
Resultados são cacheados por 7 dias via CacheManager.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import requests

from cache_manager import CacheManager

_JIKAN_URL = "https://api.jikan.moe/v4/manga"
_ANILIST_URL = "https://graphql.anilist.co"
_TTL_SECONDS = 7 * 24 * 3600
_TIMEOUT = 10

_ANILIST_QUERY = """
query ($search: String) {
  Media(search: $search, type: MANGA) {
    title { romaji english native }
    status
    chapters
    volumes
    averageScore
    description(asHtml: false)
    coverImage { large }
  }
}
"""


class MetadataEnricher:
    def __init__(self, cache: Optional[CacheManager] = None, session=None):
        self.cache = cache or CacheManager()
        self.session = session or requests.Session()

    def enrich(self, title: str) -> Optional[Dict[str, Any]]:
        key = f"enrich::{title.strip().lower()}"
        cached = self.cache.get(key, max_age_seconds=_TTL_SECONDS)
        if cached is not None:
            return cached

        result = self._from_jikan(title) or self._from_anilist(title)
        if result is not None:
            self.cache.set(key, result)
        return result

    def _from_jikan(self, title: str) -> Optional[Dict[str, Any]]:
        try:
            response = self.session.get(_JIKAN_URL, params={"q": title, "limit": 1}, timeout=_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return None

        data = payload.get("data") or []
        if not data:
            return None
        manga = data[0]
        return {
            "title": manga.get("title"),
            "alternative_titles": [t.get("title") for t in manga.get("titles", []) if t.get("title")],
            "status": manga.get("status"),
            "chapters": manga.get("chapters"),
            "volumes": manga.get("volumes"),
            "score": manga.get("score"),
            "synopsis": manga.get("synopsis"),
            "cover_image": (manga.get("images", {}).get("jpg", {}) or {}).get("large_image_url"),
            "authors": [a.get("name") for a in manga.get("authors", []) if a.get("name")],
        }

    def _from_anilist(self, title: str) -> Optional[Dict[str, Any]]:
        try:
            response = self.session.post(
                _ANILIST_URL,
                json={"query": _ANILIST_QUERY, "variables": {"search": title}},
                timeout=_TIMEOUT,
            )
            response.raise_for_status()
            media = (response.json().get("data") or {}).get("Media")
        except Exception:
            return None

        if not media:
            return None
        titles = media.get("title", {}) or {}
        return {
            "title": titles.get("romaji") or titles.get("english") or title,
            "alternative_titles": [v for v in (titles.get("english"), titles.get("native")) if v],
            "status": media.get("status"),
            "chapters": media.get("chapters"),
            "volumes": media.get("volumes"),
            "score": media.get("averageScore"),
            "synopsis": media.get("description"),
            "cover_image": (media.get("coverImage", {}) or {}).get("large"),
            "authors": [],
        }
