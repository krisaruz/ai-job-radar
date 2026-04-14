from __future__ import annotations

import logging
import re
import urllib.parse

from src.models import JobPosting
from src.scrapers.browser_base import BrowserScraper

logger = logging.getLogger(__name__)

SEARCH_URL = "https://maimai.cn/web/search_center?type=job&query={keyword}&city={city}"


class MaimaiScraper(BrowserScraper):
    """脉脉 - 通过 Playwright 浏览器搜索岗位。

    脉脉需要登录才能查看完整信息。此爬虫依赖持久化的 cookie 登录态。
    首次使用需要手动登录并保存 cookie（设置 MAIMAI_COOKIE 环境变量或
    先在本地通过交互式浏览器登录一次以生成 cookie 文件）。
    """

    @property
    def platform_name(self) -> str:
        return "maimai"

    def _fetch_jobs_browser(self, page, keyword: str, city: str) -> list[JobPosting]:
        url = SEARCH_URL.format(
            keyword=urllib.parse.quote(keyword),
            city=urllib.parse.quote(city),
        )
        jobs: list[JobPosting] = []

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
        except Exception:
            logger.warning("[maimai] page load failed for %s @ %s", keyword, city)
            return jobs

        # Check if login is required
        if "login" in page.url.lower() or page.query_selector("input[type='password']"):
            logger.warning("[maimai] login required, skipping (no valid cookie)")
            return jobs

        for _ in range(3):
            page.evaluate("window.scrollBy(0, 600)")
            page.wait_for_timeout(800)

        cards = page.query_selector_all(
            "div.job-card, div[class*='JobCard'], li[class*='job-item']"
        )

        for card in cards:
            try:
                title_el = card.query_selector(
                    "span[class*='title'], div[class*='job-name'], a[class*='title']"
                )
                company_el = card.query_selector(
                    "span[class*='company'], div[class*='company-name']"
                )
                salary_el = card.query_selector(
                    "span[class*='salary'], div[class*='salary']"
                )
                location_el = card.query_selector(
                    "span[class*='city'], span[class*='location']"
                )
                link_el = card.query_selector("a[href*='job']")

                title = title_el.inner_text().strip() if title_el else ""
                company = company_el.inner_text().strip() if company_el else ""
                salary = salary_el.inner_text().strip() if salary_el else ""
                location = location_el.inner_text().strip() if location_el else ""
                href = link_el.get_attribute("href") if link_el else ""

                if not title:
                    continue

                job_id_match = re.search(r'/job[/_]?(\w+)', href or "")
                job_id = job_id_match.group(1) if job_id_match else title[:20]

                full_url = href if href.startswith("http") else f"https://maimai.cn{href}" if href else ""

                job = JobPosting(
                    job_id=job_id,
                    platform="maimai",
                    title=title,
                    company=company,
                    location=location,
                    salary=salary,
                    url=full_url,
                )
                jobs.append(job)
            except Exception:
                continue

        return jobs
