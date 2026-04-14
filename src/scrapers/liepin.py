from __future__ import annotations

import json
import logging

from src.models import JobPosting
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api-c.liepin.com/api/com.liepin.searchfront4c.pc-search-job"

CITY_CODES = {
    "北京": "010",
    "上海": "020",
    "杭州": "070",
    "深圳": "050",
    "广州": "060",
    "成都": "280",
    "武汉": "190",
}


class LiepinScraper(BaseScraper):
    """猎聘 - 通过搜索 API 获取岗位。"""

    @property
    def platform_name(self) -> str:
        return "liepin"

    def _fetch_jobs(self, keyword: str, city: str) -> list[JobPosting]:
        city_code = CITY_CODES.get(city, "")
        jobs: list[JobPosting] = []

        payload = {
            "data": {
                "mainSearchPcConditionForm": {
                    "city": city_code,
                    "dq": city_code,
                    "currentPage": 0,
                    "pageSize": 40,
                    "key": keyword,
                },
                "passThroughForm": {"scene": "pcSearchNew"},
            },
        }
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Referer": "https://www.liepin.com/zhaopin/",
            "Origin": "https://www.liepin.com",
            "X-Requested-With": "XMLHttpRequest",
        }

        try:
            resp = self._request_with_retry("POST", SEARCH_URL, json=payload, headers=headers)
            data = resp.json()
        except Exception:
            logger.warning("[liepin] request failed for %s @ %s", keyword, city)
            return jobs

        code = data.get("code")
        if code != 0:
            logger.info("[liepin] API code=%s msg=%s", code, data.get("msg", ""))
            return jobs

        job_card_list = (
            data.get("data", {})
            .get("data", {})
            .get("jobCardList", [])
        )

        for item in job_card_list:
            job_info = item.get("job", {})
            comp_info = item.get("comp", {})

            job = JobPosting(
                job_id=str(job_info.get("jobId", "")),
                platform="liepin",
                title=job_info.get("title", ""),
                company=comp_info.get("compName", ""),
                department=comp_info.get("compIndustry", ""),
                location=job_info.get("dq", ""),
                experience=job_info.get("requireWorkYears", ""),
                education=job_info.get("requireEduLevel", ""),
                salary=job_info.get("salary", ""),
                description=job_info.get("labels", ""),
                url=f"https://www.liepin.com/job/{job_info.get('jobId', '')}.shtml",
                publish_date=job_info.get("refreshTime", ""),
            )
            jobs.append(job)

        return jobs
