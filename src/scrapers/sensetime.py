"""Scraper for 商汤科技 (hr-jobs.sensetime.com).

Uses the Feishu Recruitment SaaS shared module (sensetime self-hosts the Feishu
recruitment frontend at hr-jobs.sensetime.com). Detail page URL uses /exp/position/
prefix instead of the default /index/position/.
"""
from __future__ import annotations

from src.models import JobPosting
from src.scrapers.feishu_common import scrape_feishu_jobs

HOST = "hr-jobs.sensetime.com"
PLATFORM = "sensetime"
COMPANY = "商汤"
URL_PATH_TEMPLATE = "/exp/position/{jid}/detail"


def scrape_sensetime() -> list[JobPosting]:
    return scrape_feishu_jobs(
        host=HOST,
        platform=PLATFORM,
        company=COMPANY,
        url_path_template=URL_PATH_TEMPLATE,
    )
