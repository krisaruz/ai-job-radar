"""Scraper for job.xiaohongshu.com (小红书招聘).

Uses Playwright for DOM extraction + API interception for detail pages.
"""
from __future__ import annotations

import logging
import re

from src.models import JobPosting

logger = logging.getLogger(__name__)

KEYWORDS = ["测试", "AI", "Agent", "评测", "质量", "算法", "大模型", "AIGC", "LLM"]


def scrape_xiaohongshu() -> list[JobPosting]:
    from playwright.sync_api import sync_playwright
    try:
        from playwright_stealth import Stealth
        stealth = Stealth()
    except ImportError:
        stealth = None

    all_jobs: list[JobPosting] = []
    seen_ids: set[str] = set()

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

        for kw in KEYWORDS:
            try:
                page.goto(
                    f"https://job.xiaohongshu.com/social/position?positionName={kw}",
                    wait_until="domcontentloaded",
                    timeout=15000,
                )
                page.wait_for_timeout(4000)

                for _ in range(5):
                    page.evaluate("window.scrollBy(0, 600)")
                    page.wait_for_timeout(1000)

                links = page.query_selector_all("a[href*='/social/position/']")
                new_count = 0
                for link in links:
                    href = link.get_attribute("href") or ""
                    m = re.search(r"/social/position/(\d+)", href)
                    if not m:
                        continue
                    pid = m.group(1)
                    if pid in seen_ids:
                        continue
                    seen_ids.add(pid)
                    text = link.inner_text().strip()
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    if len(lines) >= 2:
                        title = lines[0]
                        dept = lines[1] if len(lines) > 1 else ""
                        loc = lines[2] if len(lines) > 2 else ""
                        all_jobs.append(JobPosting(
                            job_id=pid,
                            platform="xiaohongshu",
                            company="小红书",
                            title=title,
                            department=dept,
                            location=loc,
                            url=f"https://job.xiaohongshu.com/social/position/{pid}",
                        ))
                        new_count += 1
                logger.info("[xiaohongshu] keyword=%s new=%d total=%d", kw, new_count, len(all_jobs))
            except Exception:
                logger.warning("[xiaohongshu] keyword=%s failed", kw, exc_info=True)

        relevant_kw = ["测试", "评测", "质量", "QA", "Agent", "AI", "大模型"]
        relevant = [j for j in all_jobs if any(k in j.title for k in relevant_kw)]
        logger.info("[xiaohongshu] fetching details for %d relevant jobs", len(relevant))

        for j in relevant[:25]:
            try:
                detail_data: dict = {}

                def handler(resp):
                    ct = resp.headers.get("content-type", "")
                    if resp.status == 200 and "json" in ct and "position" in resp.url:
                        try:
                            data = resp.json()
                            if isinstance(data, dict) and "data" in data:
                                detail_data.update(data.get("data", {}))
                        except Exception:
                            pass

                page.on("response", handler)
                page.goto(j.url, wait_until="domcontentloaded", timeout=10000)
                page.wait_for_timeout(2000)
                page.remove_listener("response", handler)

                if detail_data:
                    j.description = detail_data.get("positionDesc", detail_data.get("description", ""))
                    j.requirements = detail_data.get("positionReq", detail_data.get("requirement", ""))
                    j.experience = detail_data.get("workYear", "")
                    j.education = detail_data.get("education", "")
            except Exception:
                pass

        logger.info("[xiaohongshu] total: %d", len(all_jobs))
        browser.close()

    return all_jobs
