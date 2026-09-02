from __future__ import annotations

import json
import logging
import re

from src.models import JobPosting
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SOCIAL_LIST_URL = "https://talent.baidu.com/jobs/social-list"


class BaiduScraper(BaseScraper):
    """Baidu talent site uses SSR."""

    @property
    def platform_name(self) -> str:
        return "baidu"

    def _fetch_jobs(self, keyword: str, city: str) -> list[JobPosting]:
        params = {"search": keyword}
        resp = self._request_with_retry("GET", SOCIAL_LIST_URL, params=params)
        html = resp.text

        jobs = self._parse_nuxt_data(html, city)
        if jobs:
            return jobs
        return self._parse_html(html, keyword, city)

    def _parse_nuxt_data(self, html: str, city: str) -> list[JobPosting]:
        jobs = []

        # Try __NEXT_DATA__ (Next.js SSR)
        m = re.search(r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                props = data.get("props", {}).get("pageProps", {})
                post_list = props.get("postList", props.get("jobs", []))
                for p in post_list:
                    job = self._dict_to_posting(p)
                    if job and (not city or city in job.location):
                        jobs.append(job)
                if jobs:
                    return jobs
            except (json.JSONDecodeError, KeyError):
                pass

        # Try __INITIAL_DATA__ (Baidu's custom SSR — actual list data lives in listData.listDetailData)
        m_init = re.search(r'window\.__INITIAL_DATA__\s*=\s*(\{.*?\})\s*(?:;|</script>)', html, re.DOTALL)
        if m_init:
            try:
                # Baidu's SSR contains JS `undefined` literals that aren't valid JSON
                raw = m_init.group(1).replace(':undefined', ':null').replace(',undefined', ',null')
                data = json.loads(raw)
                list_detail = data.get("listData", {}).get("listDetailData", []) or []
                for p in list_detail:
                    job = self._dict_to_posting(p)
                    if job and (not city or city in job.location):
                        jobs.append(job)
                if jobs:
                    return jobs
            except (json.JSONDecodeError, KeyError, ValueError):
                pass

        # Try __NUXT__ (legacy Nuxt.js)
        m2 = re.search(r'window\.__NUXT__\s*=\s*(\{.*?\});?\s*</script>', html, re.DOTALL)
        if m2:
            try:
                data = json.loads(m2.group(1))
                walked = self._walk_nuxt_for_posts(data, city)
                if walked:
                    return walked
            except (json.JSONDecodeError, ValueError):
                pass

        return jobs

    def _walk_nuxt_for_posts(self, data: dict, city: str) -> list[JobPosting]:
        jobs = []
        if isinstance(data, dict):
            for key, val in data.items():
                if key in ("postList", "jobList", "list") and isinstance(val, list):
                    for item in val:
                        if isinstance(item, dict):
                            job = self._dict_to_posting(item)
                            if job and (not city or city in job.location):
                                jobs.append(job)
                elif isinstance(val, dict):
                    jobs.extend(self._walk_nuxt_for_posts(val, city))
        return jobs

    def _parse_html(self, html: str, keyword: str, city: str) -> list[JobPosting]:
        jobs = []

        ssr_pattern = re.compile(
            r'window\.__INITIAL_DATA__\s*=\s*(\{.*?\})\s*(?:;|<)',
            re.DOTALL,
        )
        # Detail route verified against SPA source (list chunk onClick):
        # window.open("/jobs" + "/detail/" + recruitType + "/" + postId)
        # recruitType must be the enum value "SOCIAL" (uppercase); lowercase
        # "social" renders an empty shell page (no SSR detailData).
        for m_ssr in ssr_pattern.finditer(html):
            try:
                data = json.loads(m_ssr.group(1))
                post_info = data.get("detailData", {}).get("postInfo", {})
                if post_info and post_info.get("name"):
                    name = post_info["name"]
                    jid_match = re.search(r'（([A-Z]\d+)）', name)
                    post_id = post_info.get("postId", "")
                    job_id = jid_match.group(1) if jid_match else (post_id or name[:15])
                    detail_url = f"https://talent.baidu.com/jobs/detail/SOCIAL/{post_id}" if post_id else ""
                    job = JobPosting(
                        job_id=job_id,
                        platform="baidu",
                        title=name,
                        company="百度",
                        department=post_info.get("businessGroup", ""),
                        location=post_info.get("workPlace", ""),
                        education=post_info.get("education", ""),
                        description=post_info.get("description", ""),
                        requirements=post_info.get("serviceCondition", ""),
                        url=detail_url,
                    )
                    if not city or city in (job.location or html):
                        jobs.append(job)
            except (json.JSONDecodeError, KeyError):
                continue

        if jobs:
            return jobs

        simple_pattern = re.compile(r'(?:^|>)([^<>]{4,60}?)（([A-Z]\d+)）')
        for m in simple_pattern.finditer(html):
            raw_title = m.group(1).strip()
            raw_title = re.sub(r'^(?:script|span|div|a|li|h\d)>', '', raw_title)
            if not raw_title or raw_title.startswith("window.") or len(raw_title) < 3:
                continue
            title = raw_title + f"（{m.group(2)}）"
            # Fallback path: only J-code available, no postId. Use search URL
            # so users can reach the job by searching the J-code on the page.
            from urllib.parse import quote
            job = JobPosting(
                job_id=m.group(2),
                platform="baidu",
                title=title,
                company="百度",
                url=f"https://talent.baidu.com/jobs/social-list?search={quote(m.group(2))}",
            )
            if not city or city in html:
                jobs.append(job)
        return jobs

    def _dict_to_posting(self, d: dict) -> JobPosting | None:
        # Baidu SSR uses postId (UUID) for the SPA detail route. jobId is also UUID
        # but the URL pattern requires postId.
        post_id = str(d.get("postId", d.get("id", "")))
        job_id = str(d.get("jobId", d.get("id", post_id)))
        if not post_id:
            return None
        # J-codes (e.g. J98291) in the title are display-only IDs and do NOT
        # work as URL path segments — the route needs the postId UUID.
        name = d.get("name", d.get("title", "")) or ""
        jcode_match = re.search(r'（([A-Z]\d+)）', name)
        display_jid = jcode_match.group(1) if jcode_match else post_id
        return JobPosting(
            job_id=display_jid,
            platform="baidu",
            title=name,
            company="百度",
            department=d.get("department", d.get("businessGroup", d.get("postType", ""))),
            location=d.get("city", d.get("location", d.get("workPlace", ""))),
            experience=d.get("workYear", d.get("workYears", "")),
            education=d.get("education", ""),
            description=d.get("description", d.get("responsibility", d.get("workContent", ""))),
            url=f"https://talent.baidu.com/jobs/detail/SOCIAL/{post_id}",
            publish_date=d.get("publishDate", d.get("updateDate", "")),
        )
