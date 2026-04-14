from __future__ import annotations

import logging
import os
import random
import time
from abc import ABC, abstractmethod

from curl_cffi import requests as curl_requests
from fake_useragent import UserAgent

from src.models import JobPosting

logger = logging.getLogger(__name__)

_ua = UserAgent(browsers=["chrome", "edge"], os=["windows", "macos"])


class BaseScraper(ABC):
    """Base class for API-based scrapers (Tier 1 & Tier 2)."""

    MAX_RETRIES = 3
    RETRY_BACKOFF = 2.0

    def __init__(self, config: dict):
        self.config = config
        proxy = os.environ.get("PROXY_URL")
        self.session = curl_requests.Session(
            timeout=30,
            headers=self._default_headers(),
            impersonate="chrome",
            proxies={"https": proxy, "http": proxy} if proxy else None,
        )

    def _default_headers(self) -> dict:
        return {
            "User-Agent": _ua.random,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def _rotate_ua(self) -> None:
        self.session.headers["User-Agent"] = _ua.random

    @property
    @abstractmethod
    def platform_name(self) -> str: ...

    @abstractmethod
    def _fetch_jobs(self, keyword: str, city: str) -> list[JobPosting]: ...

    def _request_with_retry(self, method: str, url: str, **kwargs) -> curl_requests.Response:
        last_exc = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                self._rotate_ua()
                resp = self.session.request(method, url, **kwargs)
                resp.raise_for_status()
                return resp
            except Exception as e:
                last_exc = e
                wait = self.RETRY_BACKOFF ** attempt + random.uniform(0, 1)
                logger.warning(
                    "[%s] attempt %d/%d failed: %s, retrying in %.1fs",
                    self.platform_name, attempt, self.MAX_RETRIES, e, wait,
                )
                time.sleep(wait)
        raise last_exc  # type: ignore[misc]

    def scrape(self) -> list[JobPosting]:
        all_jobs: list[JobPosting] = []
        keywords = self.config.get("keywords", [])
        cities = self.config.get("cities", [])

        for kw in keywords:
            for city in cities:
                try:
                    logger.info("[%s] searching: %s @ %s", self.platform_name, kw, city)
                    jobs = self._fetch_jobs(kw, city)
                    all_jobs.extend(jobs)
                    time.sleep(random.uniform(2.0, 5.0))
                except Exception:
                    logger.warning(
                        "[%s] %s @ %s failed",
                        self.platform_name, kw, city,
                        exc_info=True,
                    )

        logger.info("[%s] total raw results: %d", self.platform_name, len(all_jobs))
        return all_jobs

    def close(self) -> None:
        self.session.close()
