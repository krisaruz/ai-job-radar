"""Common base scraper for Feishu Recruitment (jobs.feishu.cn / hr-jobs.<host>) SaaS portals.

Many mid-size Chinese tech companies (智谱, 莉莉丝, MiniMax, 叠纸, 商汤) outsource
their career site to Feishu's recruitment SaaS. They share the same API:

    POST /api/v1/csrf/token              -> get CSRF token
    POST /api/v1/search/job/posts        -> search positions
        body: {keyword, limit, offset, portal_type, ...}
        header: x-csrf-token: <token>

This module exposes `scrape_feishu_jobs()` which takes a host + company name
and returns a list of JobPosting.

Identifying social recruitment: response field `recruit_type.parent.name == "社招"`.
"""
from __future__ import annotations

import logging
import time
import random
from typing import Optional

from curl_cffi import requests as curl_requests
from fake_useragent import UserAgent

from src.models import JobPosting

logger = logging.getLogger(__name__)

_ua = UserAgent(browsers=["chrome", "edge"], os=["windows", "macos"])

PAGE_LIMIT = 30  # feishu API max per page
MAX_PAGES = 30   # hard cap; 30*30=900 jobs ceiling


def _build_job(item: dict, host: str, platform: str, company: str,
               url_path_template: str = "/index/position/{jid}/detail") -> Optional[JobPosting]:
    """Convert one Feishu job_post_list item to JobPosting. Return None if invalid."""
    jid = str(item.get("id", ""))
    title = item.get("title", "") or ""
    if not jid or not title:
        return None

    city_list = item.get("city_list") or []
    if isinstance(city_list, list) and city_list:
        loc = ", ".join(str(c.get("name", "")) for c in city_list if isinstance(c, dict) and c.get("name"))
    else:
        ci = item.get("city_info")
        loc = ci.get("name", "") if isinstance(ci, dict) else ""

    recruit_type = item.get("recruit_type", {}) or {}
    recruit_parent = recruit_type.get("parent", {}) or {}
    recruit_kind = recruit_parent.get("name", "")  # "社招" / "校招" / "实习"

    job_category = item.get("job_category", {}) or {}
    department = job_category.get("name", "")

    url_path = url_path_template.format(jid=jid)
    if url_path.startswith("http://") or url_path.startswith("https://"):
        detail_url = url_path
    else:
        detail_url = f"https://{host}{url_path}"

    return JobPosting(
        job_id=jid,
        platform=platform,
        title=title,
        company=company,
        department=department,
        location=loc,
        description=item.get("description", "") or "",
        requirements=item.get("requirement", "") or "",
        url=detail_url,
        publish_date=item.get("publish_time", "") or "",
        category=recruit_kind,
    )


def scrape_feishu_jobs(
    host: str,
    platform: str,
    company: str,
    keywords: list[str] | None = None,
    social_only: bool = True,
    url_path_template: str = "/index/position/{jid}/detail",
) -> list[JobPosting]:
    """Scrape a Feishu Recruitment SaaS portal.

    Args:
        host: e.g. "zhipu-ai.jobs.feishu.cn" or "hr-jobs.sensetime.com"
        platform: scraper platform id used in JobPosting.platform
        company: company display name used in JobPosting.company
        keywords: optional list of search keywords; if None or empty, lists all jobs
        social_only: if True, filter to recruit_type.parent.name == "社招"
        url_path_template: detail page URL path template with {jid} placeholder.
            Default "/index/position/{jid}/detail" works for most feishu.cn portals.
            Sensetime uses "/exp/position/{jid}/detail".
            Papergames uses "https://career.papegames.com/social/position/{jid}/detail"
            (full URL with different host).
    """
    session = curl_requests.Session(
        timeout=30,
        impersonate="chrome",
        headers={
            "User-Agent": _ua.random,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Origin": f"https://{host}",
            "Referer": f"https://{host}/index",
        },
    )

    # Phase 1: get CSRF token
    try:
        csrf_resp = session.post(f"https://{host}/api/v1/csrf/token", json={})
        csrf_resp.raise_for_status()
        token = csrf_resp.json().get("data", {}).get("token", "")
        if not token:
            logger.warning("[%s] empty csrf token", platform)
            return []
    except Exception as e:
        logger.warning("[%s] csrf fetch failed: %s", platform, e)
        return []

    logger.info("[%s] csrf token acquired", platform)

    # Phase 2: search jobs (paginated)
    all_items: dict[str, dict] = {}
    search_keywords = keywords or [""]
    seen_offsets: set[int] = set()

    for kw in search_keywords:
        offset = 0
        consecutive_empty = 0
        while offset < PAGE_LIMIT * MAX_PAGES:
            body = {
                "keyword": kw,
                "limit": PAGE_LIMIT,
                "offset": offset,
                "job_category_id_list": [],
                "tag_id_list": [],
                "location_code_list": [],
                "subject_id_list": [],
                "recruitment_id_list": [],
                "portal_type": 6,
                "job_function_id_list": [],
                "storefront_id_list": [],
                "portal_entrance": 1,
            }
            try:
                resp = session.post(
                    f"https://{host}/api/v1/search/job/posts?portal_type=6",
                    json=body,
                    headers={"x-csrf-token": token, "Referer": f"https://{host}/index"},
                )
                resp.raise_for_status()
                data = resp.json().get("data", {}) or {}
            except Exception as e:
                logger.warning("[%s] search failed at offset=%d: %s", platform, offset, e)
                break

            posts = data.get("job_post_list", []) or []
            total_count = data.get("count") or 0

            if not posts:
                break

            new_in_page = 0
            for it in posts:
                jid = str(it.get("id", ""))
                if jid and jid not in all_items:
                    all_items[jid] = it
                    new_in_page += 1

            if new_in_page == 0:
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    break
            else:
                consecutive_empty = 0

            offset += PAGE_LIMIT
            seen_offsets.add(offset)

            if total_count and offset >= total_count:
                break

            time.sleep(random.uniform(0.4, 0.9))

        logger.info("[%s] keyword=%r collected=%d", platform, kw or "(empty)", len(all_items))

    # Phase 3: build JobPosting list
    jobs: list[JobPosting] = []
    for item in all_items.values():
        j = _build_job(item, host, platform, company, url_path_template=url_path_template)
        if not j:
            continue
        if social_only:
            recruit_kind = (item.get("recruit_type", {}) or {}).get("parent", {}).get("name", "")
            if recruit_kind and recruit_kind != "社招":
                continue
        jobs.append(j)

    session.close()
    logger.info("[%s] total jobs: %d (social_only=%s)", platform, len(jobs), social_only)
    return jobs
