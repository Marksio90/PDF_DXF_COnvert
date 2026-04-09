"""
Garbage Collector — background task that periodically removes files and
database records older than GC_MAX_AGE_HOURS.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger("gc")


async def run_gc_loop():
    """Async task loop — awaited once on startup and runs forever."""
    while True:
        try:
            await asyncio.to_thread(_gc_cycle)
        except Exception as exc:
            logger.error("GC cycle failed: %s", exc)
        await asyncio.sleep(settings.GC_INTERVAL_SECONDS)


def _gc_cycle():
    from app.db.database import SessionLocal
    from app.db.models import Job

    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.GC_MAX_AGE_HOURS)

    db = SessionLocal()
    try:
        old_jobs = db.query(Job).filter(Job.created_at < cutoff).all()
        if not old_jobs:
            return

        for job in old_jobs:
            _delete_file(job.pdf_path)
            _delete_file(job.dxf_path)
            _delete_file(job.preview_path)
            db.delete(job)
            logger.info("GC: removed job %s (created %s)", job.id, job.created_at)

        db.commit()
    finally:
        db.close()


def _delete_file(path: str | None):
    if not path:
        return
    p = Path(path)
    try:
        if p.exists():
            p.unlink()
    except Exception as exc:
        logger.warning("GC: could not delete %s: %s", path, exc)
