import pytest

from database import db_manager, DownloadJob, Series


def test_session_scope_commits_and_isolates():
    with db_manager.session_scope() as s:
        s.add(Series(title="ScopeSerie", source_name="x"))
    with db_manager.session_scope() as s2:
        found = s2.query(Series).filter(Series.title == "ScopeSerie").first()
        assert found is not None


def test_session_scope_rolls_back_on_error():
    try:
        with db_manager.session_scope() as s:
            s.add(Series(title="RollbackSerie", source_name="x"))
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    with db_manager.session_scope() as s2:
        assert s2.query(Series).filter(Series.title == "RollbackSerie").first() is None


def test_get_session_returns_independent_sessions():
    a = db_manager.get_session()
    b = db_manager.get_session()
    assert a is not b
    a.close()
    b.close()


def test_download_job_model_exists():
    with db_manager.session_scope() as s:
        job = DownloadJob(series="S", chapter_number=1.0, status="queued")
        s.add(job)
        s.flush()
        assert job.id is not None
        assert job.status == "queued"
