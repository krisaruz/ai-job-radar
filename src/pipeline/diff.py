from __future__ import annotations

import logging
from dataclasses import dataclass

from src.models import JobPosting

logger = logging.getLogger(__name__)


@dataclass
class DiffResult:
    new_jobs: list[JobPosting]
    removed_jobs: list[JobPosting]
    unchanged_jobs: list[JobPosting]

    @property
    def has_changes(self) -> bool:
        return bool(self.new_jobs or self.removed_jobs)

    def summary(self) -> str:
        return (
            f"新增 {len(self.new_jobs)} | "
            f"下线 {len(self.removed_jobs)} | "
            f"不变 {len(self.unchanged_jobs)}"
        )


def compute_diff(current: list[JobPosting], previous: list[JobPosting]) -> DiffResult:
    """Compare current scrape results against previous data."""
    prev_keys = {j.unique_key: j for j in previous}
    curr_keys = {j.unique_key: j for j in current}

    new_jobs = [curr_keys[k] for k in curr_keys if k not in prev_keys]
    removed_jobs = [prev_keys[k] for k in prev_keys if k not in curr_keys]
    unchanged_jobs = [curr_keys[k] for k in curr_keys if k in prev_keys]

    result = DiffResult(
        new_jobs=new_jobs,
        removed_jobs=removed_jobs,
        unchanged_jobs=unchanged_jobs,
    )
    logger.info("Diff: %s", result.summary())
    return result
