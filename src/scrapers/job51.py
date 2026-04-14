from __future__ import annotations

import logging

from src.models import JobPosting
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SEARCH_URL = "https://we.51job.com/api/job/search-pc"

AREA_CODES = {
    "北京": "010000",
    "上海": "020000",
    "杭州": "080200",
    "深圳": "040000",
    "广州": "030200",
    "成都": "090200",
    "武汉": "170200",
}


class Job51Scraper(BaseScraper):
    """前程无忧 - 通过 PC 搜索 API 获取岗位。"""

    @property
    def platform_name(self) -> str:
        return "job51"

    def _fetch_jobs(self, keyword: str, city: str) -> list[JobPosting]:
        area_code = AREA_CODES.get(city, "")
        jobs: list[JobPosting] = []

        params = {
            "api_key": "51job",
            "keyword": keyword,
            "searchType": "2",
            "function": "",
            "industry": "",
            "jobArea": area_code,
            "jobArea2": "",
            "landmark": "",
            "metro": "",
            "salary": "",
            "workYear": "",
            "degree": "",
            "companyType": "",
            "companySize": "",
            "jobType": "",
            "issueDate": "",
            "sortType": "0",
            "pageNum": "1",
            "requestId": "",
            "pageSize": "50",
            "source": "1",
            "accountId": "",
        }
        headers = {
            "Referer": "https://we.51job.com/",
            "Origin": "https://we.51job.com",
        }

        try:
            resp = self._request_with_retry("GET", SEARCH_URL, params=params, headers=headers)
            data = resp.json()
        except Exception:
            logger.warning("[job51] request failed for %s @ %s", keyword, city)
            return jobs

        status = data.get("status")
        if status != "1":
            logger.info("[job51] API status=%s msg=%s", status, data.get("msg", ""))
            return jobs

        engine_list = data.get("resultbody", {}).get("job", {}).get("items", [])

        for item in engine_list:
            tags = item.get("tags", [])
            tag_str = ", ".join(tags) if isinstance(tags, list) else str(tags)

            job = JobPosting(
                job_id=str(item.get("jobId", item.get("encryptId", ""))),
                platform="job51",
                title=item.get("jobName", ""),
                company=item.get("fullCompanyName", item.get("companyName", "")),
                department=item.get("companyInd", ""),
                location=item.get("jobAreaString", ""),
                experience=item.get("workYearString", ""),
                education=item.get("degreeString", ""),
                salary=item.get("provideSalaryString", ""),
                description=tag_str,
                url=item.get("jobHref", ""),
                publish_date=item.get("issueDateString", item.get("updateDate", "")),
            )
            jobs.append(job)

        return jobs
