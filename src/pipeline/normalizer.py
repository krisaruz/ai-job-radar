from __future__ import annotations

import re

from src.models import JobPosting


def normalize_job(job: JobPosting, categories: dict) -> JobPosting:
    """Clean and standardize fields on a single JobPosting."""
    job.title = _clean_text(job.title)
    job.description = _clean_text(job.description)
    job.requirements = _clean_text(job.requirements)
    job.location = _normalize_location(job.location)

    if not job.category or job.category == "other":
        job.category = job.classify(categories)

    return job


def normalize_jobs(jobs: list[JobPosting], categories: dict) -> list[JobPosting]:
    return [normalize_job(j, categories) for j in jobs]


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_location(loc: str) -> str:
    if not loc:
        return ""
    loc = loc.replace("，", ",").replace("、", ",")
    for suffix in ["市", "区"]:
        loc = loc.replace(suffix, "")
    return loc.strip()
