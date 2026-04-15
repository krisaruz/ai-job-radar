"""Scraper for zhaopin.kuaishou.cn (快手招聘).

Uses Playwright: navigate to social recruitment page, use search input,
intercept API responses for structured data, DOM fallback.
"""
from __future__ import annotations

import logging
import re
import time
import random

from src.models import JobPosting

logger = logging.getLogger(__name__)

KEYWORDS = ["测试", "AI", "Agent", "评测", "大模型", "质量", "LLM"]
BASE_URL = "https://zhaopin.kuaishou.cn/recruit/e/#/official/social/"


def scrape_kuaishou() -> list[JobPosting]:
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

        def on_resp(response):
            url = response.url
            if response.status == 200:
                ct = response.headers.get("content-type", "")
                if "json" in ct and any(s in url for s in ("position", "job", "search", "list", "social")):
                    try:
                        data = response.json()
                        _extract_items(data, all_items)
                    except Exception:
                        pass

        page.on("response", on_resp)

        try:
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(4000)
        except Exception:
            logger.warning("[kuaishou] initial page load failed")

        for kw in KEYWORDS:
            try:
                search_input = page.query_selector(
                    "input[placeholder*='搜索'], input[placeholder*='职位'], "
                    "input[type='search'], input[class*='search'], input[class*='Search']"
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

                for _ in range(3):
                    page.evaluate("window.scrollBy(0, 600)")
                    page.wait_for_timeout(800)

            except Exception:
                logger.warning("[kuaishou] search failed for %s", kw)

            _scrape_dom(page, all_items)
            logger.info("[kuaishou] keyword=%s cumulative=%d", kw, len(all_items))
            time.sleep(random.uniform(1.0, 2.0))

        page.remove_listener("response", on_resp)

        jobs: list[JobPosting] = []
        for pid, item in all_items.items():
            loc = item.get("cityName", item.get("city", item.get("location", "")))
            if isinstance(loc, list):
                loc = ", ".join(str(v) for v in loc if v)

            jobs.append(JobPosting(
                job_id=pid, platform="kuaishou", company="快手",
                title=item.get("positionName", item.get("name", item.get("jobName", ""))),
                department=item.get("deptName", item.get("department", "")),
                location=str(loc),
                description=item.get("positionDesc", item.get("description", "")),
                requirements=item.get("positionReq", item.get("requirement", "")),
                url=f"https://zhaopin.kuaishou.cn/recruit/e/#/official/social/detail/{pid}",
            ))

        logger.info("[kuaishou] total: %d", len(jobs))
        browser.close()

    return jobs


def _extract_items(data, all_items: dict) -> None:
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                has_title = any(k in item for k in ("positionName", "name", "jobName"))
                has_id = any(k in item for k in ("positionId", "id", "jobId"))
                if has_title and has_id:
                    pid = str(item.get("positionId", item.get("id", item.get("jobId", ""))))
                    if pid and pid not in all_items:
                        all_items[pid] = item
                else:
                    _extract_items(item, all_items)
        return
    if not isinstance(data, dict):
        return
    for key in ("data", "list", "result", "records", "items", "content", "positionList"):
        val = data.get(key)
        if val is not None:
            _extract_items(val, all_items)


def _scrape_dom(page, all_items: dict) -> None:
    try:
        cards = page.query_selector_all(
            "a[href*='detail'], [class*='job-card'], [class*='position-item'], "
            "[class*='job-item'], [class*='list-item']"
        )
        for card in cards:
            try:
                text = card.inner_text().strip()
                href = card.get_attribute("href") or ""
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if not lines or len(lines[0]) < 4:
                    continue
                jid_match = re.search(r'detail/(\w+)', href) or re.search(r'/(\d+)', href)
                pid = jid_match.group(1) if jid_match else None
                if not pid or pid in all_items:
                    continue
                all_items[pid] = {
                    "positionId": pid, "positionName": lines[0],
                    "deptName": lines[1] if len(lines) > 1 else "",
                    "cityName": lines[2] if len(lines) > 2 else "",
                }
            except Exception:
                continue
    except Exception:
        pass
