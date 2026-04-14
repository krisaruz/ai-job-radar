from __future__ import annotations

import logging

from src.models import JobPosting
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SEARCH_URL = "https://talent.alibaba.com/position/search"
PAGE_URL = "https://talent.alibaba.com/off-campus/position-list"


class AlibabaScraper(BaseScraper):
    @property
    def platform_name(self) -> str:
        return "alibaba"

    def _init_session(self) -> str:
        resp = self._request_with_retry("GET", PAGE_URL)
        cookies = dict(self.session.cookies) if hasattr(self.session.cookies, 'items') else {}
        csrf = cookies.get("XSRF-TOKEN", "")
        if not csrf:
            logger.warning("[alibaba] XSRF-TOKEN not found in cookies")
        return csrf

    def _fetch_jobs(self, keyword: str, city: str) -> list[JobPosting]:
        csrf = self._init_session()
        jobs: list[JobPosting] = []
        page = 1
        max_pages = 3

        while page <= max_pages:
            payload = {"keyword": keyword, "pageNo": page, "pageSize": 20}
            headers = {
                "Content-Type": "application/json",
                "Referer": PAGE_URL,
                "Origin": "https://talent.alibaba.com",
                "x-xsrf-token": csrf,
            }
            resp = self._request_with_retry("POST", SEARCH_URL, json=payload, headers=headers)
            data = resp.json()

            if not data.get("success"):
                logger.warning("[alibaba] API error: %s", data.get("errorMsg"))
                break

            content = data.get("content", {})
            total = content.get("totalCount", 0)
            datas = content.get("datas") or []

            if not datas:
                break

            for d in datas:
                location_list = d.get("workLocationList") or []
                location_str = ", ".join(
                    loc.get("cityName", "") for loc in location_list
                ) if location_list else ""

                if city and city not in location_str:
                    continue

                job = JobPosting(
                    job_id=str(d.get("id", d.get("positionId", ""))),
                    platform="alibaba",
                    title=d.get("name", ""),
                    company="阿里巴巴",
                    department=d.get("departmentName", ""),
                    location=location_str,
                    experience=d.get("workExperience", ""),
                    education=d.get("degreeString", ""),
                    description=d.get("description", ""),
                    requirements=d.get("requirement", ""),
                    url=f"https://talent.alibaba.com/off-campus/position-detail?positionId={d.get('id', '')}",
                    publish_date=d.get("gmtModified", ""),
                )
                jobs.append(job)

            if page * 20 >= total:
                break
            page += 1

        return jobs
