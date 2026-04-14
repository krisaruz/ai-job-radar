from __future__ import annotations

import json
import logging
import re

from src.models import JobPosting
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SEARCH_URL = "https://jobs.bytedance.com/experienced/position"


class BytedanceScraper(BaseScraper):
    """Bytedance uses SSR with embedded JSON data."""

    @property
    def platform_name(self) -> str:
        return "bytedance"

    def _fetch_jobs(self, keyword: str, city: str) -> list[JobPosting]:
        params = {"keyword": keyword, "limit": 20, "offset": 0}
        headers = {"Referer": "https://jobs.bytedance.com/"}
        resp = self._request_with_retry("GET", SEARCH_URL, params=params, headers=headers)
        html = resp.text

        m = re.search(r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if m:
            try:
                next_data = json.loads(m.group(1))
                return self._parse_next_data(next_data, city)
            except (json.JSONDecodeError, KeyError):
                logger.debug("[bytedance] __NEXT_DATA__ parse failed")

        m2 = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', html, re.DOTALL)
        if m2:
            try:
                state = json.loads(m2.group(1))
                return self._parse_initial_state(state, city)
            except (json.JSONDecodeError, KeyError):
                logger.debug("[bytedance] __INITIAL_STATE__ parse failed")

        return self._parse_html_fallback(html, city)

    def _parse_next_data(self, data: dict, city: str) -> list[JobPosting]:
        jobs = []
        try:
            props = data.get("props", {}).get("pageProps", {})
            job_list = props.get("jobList") or props.get("jobs") or []
            for item in job_list:
                job = self._item_to_posting(item)
                if job and (not city or city in job.location):
                    jobs.append(job)
        except Exception:
            logger.debug("[bytedance] next_data parsing error", exc_info=True)
        return jobs

    def _parse_initial_state(self, state: dict, city: str) -> list[JobPosting]:
        jobs = []
        try:
            job_list = state.get("positionList", {}).get("data", [])
            for item in job_list:
                job = self._item_to_posting(item)
                if job and (not city or city in job.location):
                    jobs.append(job)
        except Exception:
            logger.debug("[bytedance] initial_state parsing error", exc_info=True)
        return jobs

    def _parse_html_fallback(self, html: str, city: str) -> list[JobPosting]:
        jobs = []
        pattern = re.compile(
            r'href="(/experienced/position/[^"]+)"[^>]*>.*?'
            r'class="[^"]*title[^"]*"[^>]*>([^<]+)',
            re.DOTALL,
        )
        for match in pattern.finditer(html):
            path, title = match.group(1), match.group(2).strip()
            if not title:
                continue
            job = JobPosting(
                job_id=path.split("/")[-1].split("?")[0],
                platform="bytedance",
                title=title,
                company="字节跳动",
                url=f"https://jobs.bytedance.com{path}",
            )
            if not city or city in job.location:
                jobs.append(job)

        if not jobs:
            logger.info("[bytedance] no jobs extracted (page structure may have changed)")
        return jobs

    def _item_to_posting(self, item: dict) -> JobPosting | None:
        jid = str(item.get("id", item.get("positionId", "")))
        if not jid:
            return None
        city_info = item.get("city_info") or item.get("city") or {}
        if isinstance(city_info, dict):
            location = city_info.get("name", "")
        elif isinstance(city_info, str):
            location = city_info
        else:
            location = ""

        return JobPosting(
            job_id=jid,
            platform="bytedance",
            title=item.get("title", item.get("name", "")),
            company="字节跳动",
            department=item.get("department", item.get("team", "")),
            location=location,
            experience=item.get("experience", ""),
            education=item.get("education", ""),
            description=item.get("description", item.get("content", "")),
            requirements=item.get("requirement", ""),
            url=f"https://jobs.bytedance.com/experienced/position/{jid}",
        )
