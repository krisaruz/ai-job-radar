from __future__ import annotations

import logging

from src.models import JobPosting

logger = logging.getLogger(__name__)


def filter_by_keywords(jobs: list[JobPosting], keywords: list[str]) -> list[JobPosting]:
    """Keep only jobs matching at least one search keyword in title/description.

    Also populates the keywords_matched field on each job.
    """
    result = []
    for job in jobs:
        matched = job.match_keywords(keywords)
        if matched:
            job.keywords_matched = matched
            result.append(job)

    logger.info(
        "Filter: %d/%d jobs matched keywords",
        len(result), len(jobs),
    )
    return result
