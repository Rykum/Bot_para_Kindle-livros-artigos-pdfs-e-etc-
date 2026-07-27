# tests/test_landing_content.py
from pathlib import Path

SITE = Path(__file__).parent.parent / "site" / "index.html"


def test_landing_lists_every_active_source():
    """A landing é o cartão de visita: não pode anunciar 3 fontes quando há 9."""
    html = SITE.read_text(encoding="utf-8")
    for fonte in ["MangaDex", "Open Library", "Wikisource", "Archive.org",
                  "Project Gutenberg", "OAPEN", "Zenodo", "OpenAlex", "arXiv"]:
        assert fonte in html, f"landing não menciona {fonte}"


def test_landing_mentions_author_search_and_where_to_find():
    html = SITE.read_text(encoding="utf-8")
    assert "por autor" in html.lower()
    assert "onde encontrar" in html.lower()
