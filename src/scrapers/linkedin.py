from __future__ import annotations

import logging
import re
import urllib.parse

from src.models import JobPosting
from src.scrapers.browser_base import BrowserScraper

logger = logging.getLogger(__name__)

SEARCH_TEMPLATE = (
    "https://www.linkedin.com/jobs/search/"
    "?keywords={keyword}&location={city}%2C%20China&f_TPR=r86400"
)


class LinkedInScraper(BrowserScraper):
    """LinkedIn Jobs - 通过 Playwright 访问公开搜索页。

    LinkedIn 的职位搜索页不需要登录即可看到基础列表（前 25 条）。
    使用 Playwright 加载页面后，从 DOM 中提取职位卡片信息。
    """

    @property
    def platform_name(self) -> str:
        return "linkedin"

    def _fetch_jobs_browser(self, page, keyword: str, city: str) -> list[JobPosting]:
        url = SEARCH_TEMPLATE.format(
            keyword=urllib.parse.quote(keyword),
            city=urllib.parse.quote(city),
        )
        jobs: list[JobPosting] = []

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
        except Exception:
            logger.warning("[linkedin] page load failed for %s @ %s", keyword, city)
            return jobs

        # Scroll down to load more cards
        for _ in range(3):
            page.evaluate("window.scrollBy(0, 800)")
            page.wait_for_timeout(1000)

        cards = page.query_selector_all(
            "div.base-card, li.jobs-search-results__list-item, div.job-search-card"
        )

        for card in cards:
            try:
                title_el = card.query_selector(
                    "h3.base-search-card__title, "
                    "span.sr-only, "
                    "h3.job-search-card__title"
                )
                company_el = card.query_selector(
                    "h4.base-search-card__subtitle, "
                    "a.job-search-card__subtitle-link"
                )
                location_el = card.query_selector(
                    "span.job-search-card__location"
                )
                link_el = card.query_selector("a.base-card__full-link, a[href*='/jobs/view/']")

                title = title_el.inner_text().strip() if title_el else ""
                company = company_el.inner_text().strip() if company_el else ""
                location = location_el.inner_text().strip() if location_el else ""
                href = link_el.get_attribute("href") if link_el else ""

                if not title:
                    continue

                job_id_match = re.search(r'/jobs/view/(\d+)', href or "")
                job_id = job_id_match.group(1) if job_id_match else title[:20]

                job = JobPosting(
                    job_id=job_id,
                    platform="linkedin",
                    title=title,
                    company=company,
                    location=location,
                    url=href.split("?")[0] if href else "",
                )
                jobs.append(job)
            except Exception:
                continue

        return jobs
