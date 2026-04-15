"""Scraper for zhaopin.meituan.com (美团招聘).

Uses Playwright: navigate to page, use search input for keywords,
intercept getJobList API responses for structured data.
"""
from __future__ import annotations

import logging
import time
import random

from src.models import JobPosting

logger = logging.getLogger(__name__)

KEYWORDS = ["测试", "AI", "评测", "Agent", "大模型", "质量", "LLM"]
BASE_URL = "https://zhaopin.meituan.com/social-recruitment"


def scrape_meituan() -> list[JobPosting]:
    from playwright.sync_api import sync_playwright
    try:
        from playwright_stealth import Stealth
        stealth = Stealth()
    except ImportError:
        stealth = None

    all_items: dict[str, dict] = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        page = context.new_page()
        if stealth:
            stealth.apply_stealth_sync(page)

        def on_job_list(resp):
            if "getJobList" in resp.url and resp.status == 200:
                try:
                    data = resp.json()
                    items = (data.get("data", {}) or {}).get("list", [])
                    for it in items:
                        jid = it.get("jobUnionId", "")
                        if jid and jid not in all_items:
                            all_items[jid] = it
                except Exception:
                    pass

        page.on("response", on_job_list)

        try:
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)
        except Exception:
            logger.warning("[meituan] initial page load failed")

        for kw in KEYWORDS:
            try:
                search_input = page.query_selector(
                    "input[placeholder*='搜索'], input[placeholder*='职位'], "
                    "input[type='search'], input[class*='search']"
                )
                if search_input:
                    search_input.click()
                    search_input.fill("")
                    search_input.fill(kw)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(3000)
                else:
                    page.goto(f"{BASE_URL}?keyword={kw}", wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(3000)
            except Exception:
                logger.warning("[meituan] search failed for %s", kw)

            logger.info("[meituan] keyword=%s cumulative=%d", kw, len(all_items))
            time.sleep(random.uniform(1.0, 2.0))

        page.remove_listener("response", on_job_list)

        relevant_kw = ["测试", "评测", "质量", "QA", "Agent", "AI", "大模型", "算法", "LLM", "AIGC"]
        relevant_ids = [
            jid for jid, it in all_items.items()
            if any(k in it.get("name", "") for k in relevant_kw)
        ]
        logger.info("[meituan] fetching details for %d/%d relevant jobs", len(relevant_ids), len(all_items))

        for jid in relevant_ids[:25]:
            detail: dict = {}

            def detail_handler(resp):
                if "getJobDetail" in resp.url and resp.status == 200:
                    try:
                        data = resp.json()
                        d = data.get("data", {})
                        if d:
                            detail.update(d)
                    except Exception:
                        pass

            page.on("response", detail_handler)
            try:
                page.goto(f"{BASE_URL}/{jid}", wait_until="domcontentloaded", timeout=10000)
                page.wait_for_timeout(2000)
            except Exception:
                pass
            page.remove_listener("response", detail_handler)
            if detail:
                all_items[jid].update(detail)

        jobs: list[JobPosting] = []
        for jid, it in all_items.items():
            jobs.append(JobPosting(
                job_id=jid, platform="meituan", company="美团",
                title=it.get("name", ""),
                department=it.get("jobCategory", it.get("bgName", "")),
                location=it.get("city", ""),
                experience=it.get("workYearName", ""),
                education=it.get("educationName", ""),
                description=it.get("describe", ""),
                requirements=it.get("requirement", ""),
                url=f"https://zhaopin.meituan.com/social-recruitment/{jid}",
            ))

        logger.info("[meituan] total: %d", len(jobs))
        browser.close()

    return jobs
