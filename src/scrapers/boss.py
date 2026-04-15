"""Scraper for zhipin.com (Boss直聘).

Rewritten to use Playwright browser automation.
The API approach fails due to aggressive anti-bot detection requiring login.
Playwright with stealth can browse the public search pages.
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

CITY_CODES = {
    "北京": "101010100",
    "上海": "101020100",
    "杭州": "101210100",
    "深圳": "101280600",
    "广州": "101280100",
}


class BossScraper(BrowserScraper):
    """Boss直聘 - Playwright browser scraper.

    Uses browser automation to bypass anti-bot measures.
    Extracts job cards from DOM or intercepts API responses.
    """

    @property
    def platform_name(self) -> str:
        return "boss"

    def scrape(self) -> list[JobPosting]:
        all_jobs: list[JobPosting] = []
        seen_ids: set[str] = set()

        page = None
        try:
            page = self._launch()
        except Exception:
            logger.error("[boss] browser launch failed", exc_info=True)
            return all_jobs

        keywords = self.config.get("keywords", [])[:6]
        cities = self.config.get("cities", [])[:3]

        try:
            for kw in keywords:
                for city in cities:
                    city_code = CITY_CODES.get(city, "101010100")
                    try:
                        jobs = self._scrape_search(page, kw, city, city_code, seen_ids)
                        all_jobs.extend(jobs)
                        time.sleep(random.uniform(3.0, 6.0))
                    except Exception:
                        logger.warning("[boss] %s @ %s failed", kw, city, exc_info=True)
        finally:
            self._save_cookies()

        logger.info("[boss] total: %d", len(all_jobs))
        return all_jobs

    def _scrape_search(self, page, keyword: str, city: str, city_code: str,
                       seen_ids: set[str]) -> list[JobPosting]:
        url = f"https://www.zhipin.com/web/geek/job?query={urllib.parse.quote(keyword)}&city={city_code}"
        jobs: list[JobPosting] = []

        api_jobs: list[dict] = []

        def on_resp(response):
            if "joblist" in response.url and response.status == 200:
                try:
                    data = response.json()
                    if data.get("code") == 0:
                        for item in data.get("zpData", {}).get("jobList", []):
                            api_jobs.append(item)
                except Exception:
                    pass

        page.on("response", on_resp)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(4000)
        except Exception:
            logger.warning("[boss] page load failed for %s @ %s", keyword, city)
            page.remove_listener("response", on_resp)
            return jobs

        captcha = page.query_selector("[class*='verify'], [class*='captcha'], .dialog-confirm")
        if captcha:
            logger.warning("[boss] captcha detected, skipping %s @ %s", keyword, city)
            page.remove_listener("response", on_resp)
            return jobs

        page.remove_listener("response", on_resp)

        if api_jobs:
            for item in api_jobs:
                jid = str(item.get("encryptJobId", item.get("jobId", "")))
                if jid in seen_ids:
                    continue
                seen_ids.add(jid)
                jobs.append(JobPosting(
                    job_id=jid,
                    platform="boss",
                    title=item.get("jobName", ""),
                    company=item.get("brandName", ""),
                    department=item.get("brandIndustry", ""),
                    location=item.get("cityName", city),
                    experience=item.get("jobExperience", ""),
                    education=item.get("jobDegree", ""),
                    salary=item.get("salaryDesc", ""),
                    description="; ".join(item.get("skills", [])),
                    url=f"https://www.zhipin.com/job_detail/{jid}.html",
                ))
            logger.info("[boss] %s @ %s: %d from API", keyword, city, len(jobs))
            return jobs

        for _ in range(3):
            page.evaluate("window.scrollBy(0, 500)")
            page.wait_for_timeout(600)

        cards = page.query_selector_all(
            ".job-card-wrapper, [class*='job-card'], "
            ".search-job-result li, [class*='jobCard']"
        )
        logger.info("[boss] %s @ %s: %d DOM cards", keyword, city, len(cards))

        for card in cards:
            try:
                text = card.inner_text().strip()
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if not lines:
                    continue

                title = lines[0]
                if len(title) < 4 or len(title) > 60:
                    continue

                link_el = card.query_selector("a")
                href = link_el.get_attribute("href") if link_el else ""
                full_url = f"https://www.zhipin.com{href}" if href and not href.startswith("http") else href

                jid_match = re.search(r'/job_detail/([^./?]+)', href or "")
                jid = jid_match.group(1) if jid_match else f"boss-{title[:15]}"

                if jid in seen_ids:
                    continue
                seen_ids.add(jid)

                company = ""
                salary = ""
                for line in lines[1:]:
                    if re.search(r'\d+[kK万]', line) or ("·" in line and any(c.isdigit() for c in line)):
                        salary = line
                    elif not company and len(line) > 2 and not line.startswith("距离"):
                        company = line

                jobs.append(JobPosting(
                    job_id=jid,
                    platform="boss",
                    title=title,
                    company=company,
                    location=city,
                    salary=salary,
                    url=full_url,
                ))
            except Exception:
                continue

        return jobs

    def _fetch_jobs_browser(self, page, keyword: str, city: str) -> list[JobPosting]:
        return []
