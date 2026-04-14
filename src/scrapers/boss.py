from __future__ import annotations

import logging
import urllib.parse

from src.models import JobPosting
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"

CITY_CODES = {
    "北京": "101010100",
    "上海": "101020100",
    "杭州": "101210100",
    "深圳": "101280600",
    "广州": "101280100",
    "成都": "101270100",
    "武汉": "101200100",
}


class BossScraper(BaseScraper):
    """Boss直聘 - 通过 Web API 搜索岗位。

    Boss直聘反爬较强，此爬虫可能需要有效的 cookie 才能正常工作。
    如果 API 返回需要登录，会优雅地跳过。
    """

    @property
    def platform_name(self) -> str:
        return "boss"

    def _fetch_jobs(self, keyword: str, city: str) -> list[JobPosting]:
        city_code = CITY_CODES.get(city, "100010000")
        jobs: list[JobPosting] = []
        page = 1
        max_pages = 3

        while page <= max_pages:
            params = {
                "query": keyword,
                "city": city_code,
                "page": page,
                "pageSize": 30,
            }
            headers = {
                "Referer": f"https://www.zhipin.com/web/geek/job?query={urllib.parse.quote(keyword)}&city={city_code}",
                "Origin": "https://www.zhipin.com",
            }

            try:
                resp = self._request_with_retry("GET", SEARCH_URL, params=params, headers=headers)
                data = resp.json()
            except Exception:
                logger.warning("[boss] request failed for %s @ %s", keyword, city)
                break

            code = data.get("code")
            if code != 0:
                logger.info("[boss] API code=%s (may need login), skipping", code)
                break

            zp_data = data.get("zpData", {})
            job_list = zp_data.get("jobList", [])
            if not job_list:
                break

            for item in job_list:
                brand = item.get("brandName", "")
                salary = item.get("salaryDesc", "")
                job = JobPosting(
                    job_id=str(item.get("encryptJobId", item.get("jobId", ""))),
                    platform="boss",
                    title=item.get("jobName", ""),
                    company=brand,
                    department=item.get("brandIndustry", ""),
                    location=item.get("cityName", ""),
                    experience=item.get("jobExperience", ""),
                    education=item.get("jobDegree", ""),
                    salary=salary,
                    description="; ".join(item.get("skills", [])),
                    url=f"https://www.zhipin.com/job_detail/{item.get('encryptJobId', '')}.html",
                )
                jobs.append(job)

            if len(job_list) < 30:
                break
            page += 1

        return jobs
