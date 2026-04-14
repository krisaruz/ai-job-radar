from __future__ import annotations

import logging

from src.models import JobPosting

logger = logging.getLogger(__name__)


def deduplicate(jobs: list[JobPosting]) -> list[JobPosting]:
    """Remove duplicates based on platform + job_id (unique_key).

    If duplicates exist, keep the one with the most data (longer description).
    """
    seen: dict[str, JobPosting] = {}
    for job in jobs:
        key = job.unique_key
        if key in seen:
            existing = seen[key]
            if len(job.description) > len(existing.description):
                seen[key] = job
        else:
            seen[key] = job

    removed = len(jobs) - len(seen)
    if removed:
        logger.info("Dedup: removed %d duplicates, %d unique jobs", removed, len(seen))
    return list(seen.values())
