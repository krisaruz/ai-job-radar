"""Scraper for zhaopin.com / sou.zhaopin.com (智联招聘).

Rewritten to use Playwright browser automation as primary method
with API fallback. The pure API approach often gets blocked.
"""
from __future__ import annotations

import logging
import re
import time
import random
import urllib.parse

from src.models import JobPosting
from src.scrapers.browser_base import BrowserScraper

logger = logging.getLogger(__name__)


class ZhilianScraper(BrowserScraper):
    """智联招聘 - Playwright browser scraper with API fallback."""

    @property
    def platform_name(self) -> str:
        return "zhilian"

    def scrape(self) -> list[JobPosting]:
        all_jobs: list[JobPosting] = []
        seen_ids: set[str] = set()

        page = None
        try:
            page = self._launch()
        except Exception:
            logger.error("[zhilian] browser launch failed", exc_info=True)
            return all_jobs

        keywords = self.config.get("keywords", [])[:8]
        cities = self.config.get("cities", [])[:3]

        try:
            for kw in keywords:
                for city in cities:
                    try:
                        jobs = self._scrape_search(page, kw, city, seen_ids)
                        all_jobs.extend(jobs)
                        time.sleep(random.uniform(2.0, 5.0))
                    except Exception:
                        logger.warning("[zhilian] %s @ %s failed", kw, city, exc_info=True)
        finally:
            self._save_cookies()

        logger.info("[zhilian] total: %d", len(all_jobs))
        return all_jobs

    def _scrape_search(self, page, keyword: str, city: str,
                       seen_ids: set[str]) -> list[JobPosting]:
        url = f"https://sou.zhaopin.com/?kw={urllib.parse.quote(keyword)}&city={urllib.parse.quote(city)}"
        jobs: list[JobPosting] = []

        api_jobs: list[dict] = []

        def on_resp(response):
            url_str = response.url
            if response.status == 200 and ("sou" in url_str or "search" in url_str):
                ct = response.headers.get("content-type", "")
                if "json" in ct:
                    try:
                        data = response.json()
                        results = data.get("data", {}).get("results", [])
                        if results:
                            api_jobs.extend(results)
                    except Exception:
                        pass

        page.on("response", on_resp)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)
        except Exception:
            logger.warning("[zhilian] page load failed for %s @ %s", keyword, city)
            page.remove_listener("response", on_resp)
            return jobs

        for _ in range(3):
            page.evaluate("window.scrollBy(0, 500)")
            page.wait_for_timeout(600)

        page.remove_listener("response", on_resp)

        if api_jobs:
            for item in api_jobs:
                jid = str(item.get("number", item.get("positionId", "")))
                if not jid or jid in seen_ids:
                    continue
                seen_ids.add(jid)

                company_info = item.get("company", {})
                salary = item.get("salary", "")
                if isinstance(salary, dict):
                    salary = f"{salary.get('low', '')}-{salary.get('high', '')}"

                jobs.append(JobPosting(
                    job_id=jid,
                    platform="zhilian",
                    title=item.get("jobName", item.get("name", "")),
                    company=company_info.get("name", "") if isinstance(company_info, dict) else "",
                    department=company_info.get("type", {}).get("name", "") if isinstance(company_info, dict) and isinstance(company_info.get("type"), dict) else "",
                    location=item.get("city", {}).get("display", "") if isinstance(item.get("city"), dict) else str(item.get("city", city)),
                    experience=item.get("workingExp", {}).get("name", "") if isinstance(item.get("workingExp"), dict) else "",
                    education=item.get("eduLevel", {}).get("name", "") if isinstance(item.get("eduLevel"), dict) else "",
                    salary=str(salary),
                    description=item.get("jobSummary", ""),
                    url=item.get("positionURL", f"https://jobs.zhaopin.com/{jid}.htm"),
                    publish_date=item.get("updateDate", ""),
                ))
            logger.info("[zhilian] %s @ %s: %d from API", keyword, city, len(jobs))
            return jobs

        cards = page.query_selector_all(
            ".joblist-box__item, [class*='job-card'], [class*='JobCard'], "
            "[class*='joblist'], a[href*='jobs.zhaopin.com']"
        )
        logger.info("[zhilian] %s @ %s: %d DOM cards", keyword, city, len(cards))

        for card in cards:
            try:
                text = card.inner_text().strip()
                href = card.get_attribute("href") or ""
                if not href:
                    link = card.query_selector("a[href*='jobs.zhaopin.com']")
                    href = link.get_attribute("href") if link else ""

                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if not lines:
                    continue

                title = lines[0]
                if len(title) < 4 or len(title) > 80:
                    continue

                jid_match = re.search(r'/(\w+)\.htm', href)
                jid = jid_match.group(1) if jid_match else f"zl-{title[:15]}"

                if jid in seen_ids:
                    continue
                seen_ids.add(jid)

                company = ""
                salary = ""
                for line in lines[1:]:
                    if re.search(r'\d+[kK万]', line) or ("-" in line and any(c.isdigit() for c in line)):
                        salary = line
                    elif not company and len(line) > 2:
                        company = line

                jobs.append(JobPosting(
                    job_id=jid,
                    platform="zhilian",
                    title=title,
                    company=company,
                    location=city,
                    salary=salary,
                    url=href if href.startswith("http") else "",
                ))
            except Exception:
                continue

        return jobs

    def _fetch_jobs_browser(self, page, keyword: str, city: str) -> list[JobPosting]:
        return []
