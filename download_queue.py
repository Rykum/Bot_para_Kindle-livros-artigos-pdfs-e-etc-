"""Fila de downloads persistente (SQLite via DownloadJob)."""

from __future__ import annotations

from typing import List, Optional

from database import DownloadJob, db_manager

_FIELDS = ("id", "series", "source", "media_type", "chapter_number",
           "language", "fallback_language", "status", "error")


def _to_dict(job: DownloadJob) -> dict:
    return {field: getattr(job, field) for field in _FIELDS}


class DownloadQueue:
    def enqueue(self, series: str, chapters, source: str = "mangadex",
                media_type: str = "manga", language: str = "pt-br",
                fallback_language: Optional[str] = None) -> List[int]:
        targets = list(chapters) if chapters else [None]
        ids: List[int] = []
        with db_manager.session_scope() as s:
            for ch in targets:
                job = DownloadJob(
                    series=series, source=source, media_type=media_type,
                    chapter_number=(float(ch) if ch is not None else None),
                    language=language, fallback_language=fallback_language,
                    status="queued",
                )
                s.add(job)
                s.flush()
                ids.append(job.id)
        return ids

    def list_items(self, limit: int = 500) -> List[dict]:
        with db_manager.session_scope() as s:
            rows = s.query(DownloadJob).order_by(DownloadJob.id).limit(limit).all()
            return [_to_dict(j) for j in rows]

    def next_queued(self) -> Optional[dict]:
        with db_manager.session_scope() as s:
            job = (s.query(DownloadJob)
                   .filter(DownloadJob.status == "queued")
                   .order_by(DownloadJob.id).first())
            return _to_dict(job) if job else None

    def mark(self, job_id: int, status: str, error: Optional[str] = None) -> None:
        with db_manager.session_scope() as s:
            job = s.get(DownloadJob, job_id)
            if job:
                job.status = status
                job.error = error

    def cancel_item(self, job_id: int) -> None:
        self.mark(job_id, "cancelled")

    def retry_item(self, job_id: int) -> None:
        self.mark(job_id, "queued", None)

    def remove_item(self, job_id: int) -> None:
        with db_manager.session_scope() as s:
            job = s.get(DownloadJob, job_id)
            if job:
                s.delete(job)

    def clear_finished(self) -> int:
        with db_manager.session_scope() as s:
            return (s.query(DownloadJob)
                    .filter(DownloadJob.status.in_(["done", "cancelled"]))
                    .delete(synchronize_session=False))

    def requeue_stale(self) -> int:
        with db_manager.session_scope() as s:
            return (s.query(DownloadJob)
                    .filter(DownloadJob.status == "downloading")
                    .update({"status": "queued"}, synchronize_session=False))
