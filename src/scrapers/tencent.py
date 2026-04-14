from __future__ import annotations

import logging

from src.models import JobPosting
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

API_URL = "https://careers.tencent.com/tencentcareer/api/post/Query"


class TencentScraper(BaseScraper):
    @property
    def platform_name(self) -> str:
        return "tencent"

    def _fetch_jobs(self, keyword: str, city: str) -> list[JobPosting]:
        jobs: list[JobPosting] = []
        page = 1
        max_pages = 5

        while page <= max_pages:
            params = {
                "keyword": keyword,
                "pageIndex": page,
                "pageSize": 20,
                "language": "zh-cn",
                "area": f"cn-{city}" if city else "",
                "timestamp": "careers",
            }
            resp = self._request_with_retry("GET", API_URL, params=params)
            data = resp.json()

            if data.get("Code") != 200:
                logger.warning("[tencent] API returned code %s", data.get("Code"))
                break

            posts = data.get("Data", {}).get("Posts", [])
            if not posts:
                break

            for p in posts:
                job = JobPosting(
                    job_id=str(p.get("PostId", "")),
                    platform="tencent",
                    title=p.get("RecruitPostName", ""),
                    company="腾讯",
                    department=p.get("BGName", ""),
                    location=p.get("LocationName", ""),
                    experience=p.get("RequireWorkYearsName", ""),
                    description=p.get("Responsibility", ""),
                    url=p.get("PostURL", f"https://careers.tencent.com/jobdesc.html?postId={p.get('PostId', '')}"),
                    publish_date=p.get("LastUpdateTime", ""),
                    category=p.get("CategoryName", ""),
                )
                jobs.append(job)

            total = data.get("Data", {}).get("Count", 0)
            if page * 20 >= total:
                break
            page += 1

        return jobs
