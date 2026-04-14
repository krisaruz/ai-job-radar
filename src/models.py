from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class JobPosting:
    job_id: str
    platform: str
    title: str
    company: str
    department: str = ""
    location: str = ""
    experience: str = ""
    education: str = ""
    salary: str = ""
    description: str = ""
    requirements: str = ""
    url: str = ""
    publish_date: str = ""
    scraped_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    keywords_matched: list[str] = field(default_factory=list)
    category: str = ""

    @property
    def unique_key(self) -> str:
        return f"{self.platform}:{self.job_id}"

    @property
    def content_hash(self) -> str:
        raw = f"{self.title}|{self.company}|{self.department}|{self.location}|{self.description}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> JobPosting:
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in valid_fields}
        return cls(**filtered)

    def match_keywords(self, keywords: list[str]) -> list[str]:
        text = f"{self.title} {self.department} {self.description} {self.requirements}".lower()
        return [kw for kw in keywords if kw.lower() in text]

    def classify(self, categories: dict) -> str:
        text = f"{self.title} {self.department} {self.description}".lower()
        for cat_id, cat_cfg in categories.items():
            cat_keywords = cat_cfg.get("keywords", [])
            if any(kw.lower() in text for kw in cat_keywords):
                return cat_id
        return "other"


def load_jobs_from_json(path: str) -> list[JobPosting]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [JobPosting.from_dict(d) for d in data]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_jobs_to_json(jobs: list[JobPosting], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([j.to_dict() for j in jobs], f, ensure_ascii=False, indent=2)
