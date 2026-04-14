from __future__ import annotations

import logging

from src.models import JobPosting
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SEARCH_URL = "https://fe-api.zhaopin.com/c/i/sou"

CITY_CODES = {
    "北京": "530",
    "上海": "538",
    "杭州": "653",
    "深圳": "765",
    "广州": "763",
    "成都": "801",
    "武汉": "736",
}


class ZhilianScraper(BaseScraper):
    """智联招聘 - 通过前端搜索 API 获取岗位。"""

    @property
    def platform_name(self) -> str:
        return "zhilian"

    def _fetch_jobs(self, keyword: str, city: str) -> list[JobPosting]:
        city_code = CITY_CODES.get(city, "")
        jobs: list[JobPosting] = []
        start = 0
        page_size = 60
        max_pages = 2

        for page_idx in range(max_pages):
            params = {
                "pageSize": page_size,
                "cityId": city_code,
                "kw": keyword,
                "start": start,
                "kt": "3",
            }
            headers = {
                "Referer": "https://sou.zhaopin.com/",
                "Origin": "https://sou.zhaopin.com",
            }

            try:
                resp = self._request_with_retry("GET", SEARCH_URL, params=params, headers=headers)
                data = resp.json()
            except Exception:
                logger.warning("[zhilian] request failed for %s @ %s page %d", keyword, city, page_idx)
                break

            code = data.get("code")
            if code != 200:
                logger.info("[zhilian] API code=%s", code)
                break

            results = data.get("data", {}).get("results", [])
            if not results:
                break

            for item in results:
                company_info = item.get("company", {})
                salary = item.get("salary", "")
                if isinstance(salary, dict):
                    salary = f"{salary.get('low', '')}-{salary.get('high', '')}"

                job = JobPosting(
                    job_id=str(item.get("number", item.get("positionId", ""))),
                    platform="zhilian",
                    title=item.get("jobName", item.get("name", "")),
                    company=company_info.get("name", ""),
                    department=company_info.get("type", {}).get("name", "") if isinstance(company_info.get("type"), dict) else "",
                    location=item.get("city", {}).get("display", "") if isinstance(item.get("city"), dict) else str(item.get("city", "")),
                    experience=item.get("workingExp", {}).get("name", "") if isinstance(item.get("workingExp"), dict) else "",
                    education=item.get("eduLevel", {}).get("name", "") if isinstance(item.get("eduLevel"), dict) else "",
                    salary=str(salary),
                    description=item.get("jobSummary", ""),
                    url=item.get("positionURL", f"https://jobs.zhaopin.com/{item.get('number', '')}.htm"),
                    publish_date=item.get("updateDate", ""),
                )
                jobs.append(job)

            num_found = data.get("data", {}).get("numFound", 0)
            start += page_size
            if start >= num_found:
                break

        return jobs
