"""Scraper for talent.antgroup.com (蚂蚁集团招聘).

Uses Playwright with API interception. talent.antgroup.com is similar to
talent.alibaba.com (same tech stack) but for Ant Group specifically.
"""
from __future__ import annotations

import json
import logging
import re

from src.models import JobPosting

logger = logging.getLogger(__name__)

KEYWORDS = ["测试", "AI", "Agent", "评测", "大模型", "质量", "AIGC", "LLM", "算法测试"]

BASE_URL = "https://talent.antgroup.com/off-campus"


def scrape_antgroup() -> list[JobPosting]:
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

        target_page = [1]

        def intercept(route, request):
            if request.method == "POST":
                try:
                    body = json.loads(request.post_data)
                    body["pageIndex"] = target_page[0]
                    body["pageSize"] = 50
                    if "keyword" not in body:
                        body["keyword"] = ""
                    route.continue_(post_data=json.dumps(body))
                    return
                except Exception:
                    pass
            route.continue_()

        page.route("**/position/search**", intercept)
        page.route("**/position/list**", intercept)

        current_batch: list[dict] = []
        total_count = 0

        def on_resp(response):
            nonlocal total_count
            url = response.url
            if response.status == 200 and ("position" in url):
                ct = response.headers.get("content-type", "")
                if "json" in ct:
                    try:
                        data = response.json()
                        if data.get("success") or data.get("code") in (200, 0, None):
                            content = data.get("content", data.get("data", {}))
                            if isinstance(content, dict):
                                total_count = content.get("totalCount", content.get("total", 0))
                                items = content.get("datas", content.get("list", content.get("records", [])))
                                if isinstance(items, list):
                                    current_batch.clear()
                                    current_batch.extend(items)
                    except Exception:
                        pass

        page.on("response", on_resp)

        for pi in range(1, 15):
            target_page[0] = pi
            current_batch.clear()

            try:
                page.goto(
                    f"{BASE_URL}?lang=zh",
                    wait_until="domcontentloaded",
                    timeout=15000,
                )
                page.wait_for_timeout(3000)
            except Exception:
                logger.warning("[antgroup] page %d load failed", pi)
                break

            if not current_batch:
                if pi == 1:
                    _try_keyword_search(page, all_items)
                break

            new_count = 0
            for item in current_batch:
                pid = str(item.get("id", item.get("positionId", "")))
                if pid and pid not in all_items:
                    all_items[pid] = item
                    new_count += 1

            logger.info("[antgroup] page %d: total=%d returned=%d new=%d cumulative=%d",
                        pi, total_count, len(current_batch), new_count, len(all_items))

            if len(current_batch) < 50:
                break

        page.remove_listener("response", on_resp)

        jobs: list[JobPosting] = []
        for pid, item in all_items.items():
            locations = item.get("workLocations", item.get("workLocation", ""))
            if isinstance(locations, list):
                loc = ", ".join(str(v) for v in locations if v)
            else:
                loc = str(locations) if locations else ""

            dept = item.get("department", "") or item.get("departmentName", "") or item.get("buName", "")

            jobs.append(JobPosting(
                job_id=pid,
                platform="antgroup",
                title=item.get("name", item.get("positionName", "")),
                company="蚂蚁集团",
                department=str(dept),
                location=loc,
                experience=_format_experience(item.get("experience")),
                education=_format_degree(item.get("degree")),
                description=item.get("description", ""),
                requirements=item.get("requirement", ""),
                url=f"https://talent.antgroup.com/off-campus/position-detail?positionId={pid}",
            ))

        logger.info("[antgroup] total: %d", len(jobs))
        browser.close()

    return jobs


def _try_keyword_search(page, all_items: dict) -> None:
    """If pagination interception didn't work, try keyword-based DOM extraction."""
    for kw in KEYWORDS:
        try:
            page.goto(
                f"{BASE_URL}?keyword={kw}&lang=zh",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            page.wait_for_timeout(3000)

            for _ in range(3):
                page.evaluate("window.scrollBy(0, 600)")
                page.wait_for_timeout(800)

            cards = page.query_selector_all(
                "a[href*='positionId'], a[href*='position-detail'], "
                "[class*='position'], [class*='Position']"
            )
            new_count = 0
            for card in cards:
                try:
                    text = card.inner_text().strip()
                    href = card.get_attribute("href") or ""
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    if not lines or len(lines[0]) < 4:
                        continue

                    jid_match = re.search(r'positionId=(\w+)', href)
                    pid = jid_match.group(1) if jid_match else f"ant-{lines[0][:15]}"
                    if pid not in all_items:
                        all_items[pid] = {
                            "id": pid, "name": lines[0],
                            "department": lines[1] if len(lines) > 1 else "",
                            "workLocations": lines[2] if len(lines) > 2 else "",
                        }
                        new_count += 1
                except Exception:
                    continue
            logger.info("[antgroup] keyword=%s DOM new=%d", kw, new_count)
        except Exception:
            logger.warning("[antgroup] keyword=%s failed", kw)


def _format_experience(exp) -> str:
    if not exp:
        return ""
    if isinstance(exp, str):
        return exp
    if isinstance(exp, dict):
        fr = exp.get("from")
        to = exp.get("to")
        if fr and to:
            return f"{fr}-{to}年"
        if fr:
            return f"{fr}年以上"
    return ""


def _format_degree(deg) -> str:
    DEGREE_MAP = {
        "bachelor": "本科", "master": "硕士", "doctor": "博士",
        "phd": "博士", "college": "大专",
    }
    if not deg:
        return ""
    if isinstance(deg, str):
        return DEGREE_MAP.get(deg.lower(), deg)
    return str(deg)
