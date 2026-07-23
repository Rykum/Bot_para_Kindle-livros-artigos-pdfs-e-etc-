"""Regressão: títulos com acento/pontuação criavam SÉRIES DUPLICADAS
(o ilike do SQLite não é insensível a acento), e o export caía numa
duplicata vazia -> pasta vazia."""

import tempfile
from pathlib import Path

from media_bot import MediaBot
from database import Series


def make_bot():
    return MediaBot(base_download_dir=str(Path(tempfile.mkdtemp()) / "dl"))


def test_no_duplicate_for_accented_title():
    bot = make_bot()
    try:
        lib = bot.library
        s1 = lib.get_or_create_series("Drácula - Bram Stoker (1897)", "archive")
        s2 = lib.get_or_create_series("Drácula - Bram Stoker (1897)", "archive")
        s3 = lib.get_or_create_series("dracula - bram stoker (1897)", "archive")  # sem acento
        assert s1.id == s2.id == s3.id
        assert lib.session.query(Series).count() == 1
    finally:
        bot.cleanup()


def test_dedupe_removes_empty_duplicates():
    bot = make_bot()
    try:
        lib = bot.library
        for _ in range(3):
            lib.session.add(Series(title="Titulo X", source_name="x",
                                   language="pt-br", status="unknown"))
        lib.session.commit()
        assert lib.session.query(Series).count() == 3
        removed = lib.dedupe_series()
        assert removed == 2
        assert lib.session.query(Series).count() == 1
    finally:
        bot.cleanup()
