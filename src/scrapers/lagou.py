from __future__ import annotations

import logging
import urllib.parse

from src.models import JobPosting
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.lagou.com/jobs/v2/positionAjax.json"
LIST_PAGE = "https://www.lagou.com/zhaopin/"

CITY_MAP = {
    "北京": "北京",
    "上海": "上海",
    "杭州": "杭州",
    "深圳": "深圳",
    "广州": "广州",
    "成都": "成都",
    "武汉": "武汉",
}


class LagouScraper(BaseScraper):
    """拉勾 - 通过 POST 搜索 API 获取岗位。

    拉勾反爬非常严格，需要先访问列表页获取 cookie，
    然后带着 cookie + CSRF token 请求搜索 API。
    失败概率较高，作为尽力而为的数据源。
    """

    @property
    def platform_name(self) -> str:
        return "lagou"

    def _init_cookies(self, city: str) -> None:
        """Visit list page to initialize session cookies."""
        url = f"{LIST_PAGE}?city={urllib.parse.quote(city)}"
        try:
            self._request_with_retry("GET", url)
        except Exception:
            logger.debug("[lagou] failed to init cookies")

    def _fetch_jobs(self, keyword: str, city: str) -> list[JobPosting]:
        mapped_city = CITY_MAP.get(city, city)
        self._init_cookies(mapped_city)

        jobs: list[JobPosting] = []

        form_data = {
            "first": "true",
            "pn": "1",
            "kd": keyword,
            "city": mapped_city,
        }
        headers = {
            "Referer": f"https://www.lagou.com/jobs/list_{urllib.parse.quote(keyword)}",
            "Origin": "https://www.lagou.com",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "X-Anit-Forge-Code": "0",
            "X-Anit-Forge-Token": "None",
        }

        try:
            resp = self._request_with_retry("POST", SEARCH_URL, data=form_data, headers=headers)
            data = resp.json()
        except Exception:
            logger.warning("[lagou] request failed for %s @ %s", keyword, city)
            return jobs

        if not data.get("success"):
            logger.info("[lagou] API failed: %s", data.get("msg", "unknown"))
            return jobs

        position_result = data.get("content", {}).get("positionResult", {})
        result_list = position_result.get("result", [])

        for item in result_list:
            salary = item.get("salary", "")
            skills = item.get("skillLables", item.get("positionLables", []))

            job = JobPosting(
                job_id=str(item.get("positionId", "")),
                platform="lagou",
                title=item.get("positionName", ""),
                company=item.get("companyFullName", item.get("companyShortName", "")),
                department=item.get("industryField", ""),
                location=item.get("city", ""),
                experience=item.get("workYear", ""),
                education=item.get("education", ""),
                salary=salary,
                description=", ".join(skills) if isinstance(skills, list) else str(skills),
                url=f"https://www.lagou.com/jobs/{item.get('positionId', '')}.html",
                publish_date=item.get("createTime", item.get("formatCreateTime", "")),
            )
            jobs.append(job)

        return jobs
