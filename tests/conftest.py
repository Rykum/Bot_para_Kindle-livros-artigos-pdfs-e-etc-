import pytest

from database import db_manager


@pytest.fixture(autouse=True)
def _isolated_db():
    """Garante uma base de dados limpa para cada teste.

    `db_manager` é um singleton de processo (ver database.py) compartilhado
    por todas as instâncias de MediaBot/LibraryManager criadas nos testes.
    Sem este reset, testes que usam o mesmo título de série (ex.: "Serie")
    poluiriam o estado uns dos outros dentro da mesma sessão de pytest.
    """
    db_manager.reset_db()
    yield
