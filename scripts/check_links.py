"""Link health check: verify every job URL in data/jobs.json still works.

Runs headless Playwright per unique URL (new page each time — reusing one page
breaks hash-router SPAs that don't reload on same-path navigation). Writes a
markdown report to data/link-health.md and exits non-zero when more than
LINK_FAILURE_THRESHOLD% of links are dead, so CI can alert.

Usage:
    python -m scripts.check_links              # full check
    python -m scripts.check_links --sample 3   # 3 links per company
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent
JOBS_FILE = PROJECT_ROOT / "data" / "jobs.json"
REPORT_FILE = PROJECT_ROOT / "data" / "link-health.md"

# Exit code 1 when this share of links is dead.
LINK_FAILURE_THRESHOLD = 0.10

COOKIE_LABELS = ["接受 Cookie", "Accept Cookies", "接受所有Cookie", "同意"]

DEAD_KEYWORDS = [
    "该职位已下线",
    "没有找到页面",
    "页面不存在",
    "您搜索的页面不存在",
    "没有您浏览的职位",
    "Not Found",
    "职位已关闭",
    "职位已下架",
    "job has been closed",
]

# Domains that block headless Playwright entirely; verified via SSR instead.
SSR_CHECK_DOMAINS = {"talent.baidu.com"}


def keywords_from(title: str) -> list[str]:
    import re
    words = []
    for m in re.findall(r"(?:MJ\d{4,8}|J\d{5,7}|A\d{5,7}|R10\d{4}|JR\d{9}[A-Z]?|\d{6,})", title):
        words.append(m)
    for w in re.findall(r"[\u4e00-\u9fff]{2,}", title):
        if w not in ("方向",) or len(w) > 3:
            words.append(w)
    for w in re.findall(r"[A-Za-z]{3,}", title):
        words.append(w)
    return words


def check_ssr(url: str, title: str) -> str:
    """talent.baidu.com: fetch page, parse __INITIAL_DATA__ postInfo."""
    import re as _re
    from curl_cffi import requests as curl_requests

    try:
        session = curl_requests.Session(impersonate="chrome", timeout=25)
        resp = session.get(url)
        m = _re.search(r"window\.__INITIAL_DATA__\s*=\s*(\{.*?\})\s*(?:;|</script>)", resp.text, _re.DOTALL)
        if not m:
            return "OFFLINE"
        raw = m.group(1).replace(":undefined", ":null").replace(",undefined", ",null")
        data = json.loads(raw)
        name = data.get("detailData", {}).get("postInfo", {}).get("name", "")
        return "OK" if name else "OFFLINE"
    except Exception:
        return "ERROR"


def check_browser(page, url: str, title: str) -> str:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(5000)
        for label in COOKIE_LABELS:
            loc = page.get_by_text(label, exact=False)
            if loc.count() > 0:
                try:
                    loc.first.click(timeout=2000)
                except Exception:
                    pass
                break
        page.wait_for_timeout(3000)
        page.mouse.wheel(0, 600)
        page.wait_for_timeout(2500)
        body = page.inner_text("body")

        if len(body) < 300:
            page.wait_for_timeout(8000)
            body = page.inner_text("body")

        if any(kw in body for kw in DEAD_KEYWORDS) and len(body) < 2500:
            return "OFFLINE"
        words = keywords_from(title)
        if not words:
            return "UNKNOWN"
        import re as _re
        codes = [w for w in words if _re.match(r"^(?:MJ|J\d|A\d|R10|JR)", w)]
        code_hit = any(c in body for c in codes)
        kw_hit = sum(1 for w in words if w in body)
        if code_hit or kw_hit >= max(1, len(words) // 3):
            return "OK"
        if len(body) < 120:
            return "EMPTY"
        return "MISMATCH"
    except Exception:
        return "ERROR"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=0, help="N links per company (0 = all)")
    args = parser.parse_args()

    if not JOBS_FILE.exists():
        print("data/jobs.json not found")
        return 1
    jobs = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    if not jobs:
        print("no jobs to check")
        return 0

    by_company: dict[str, list[dict]] = defaultdict(list)
    for j in jobs:
        if j.get("url"):
            by_company[j.get("company") or j["platform"]].append(j)

    cases: list[dict] = []
    for company, items in by_company.items():
        take = items if not args.sample else items[: args.sample]
        for j in take:
            cases.append({"company": company, "title": j["title"], "url": j["url"]})

    print(f"checking {len(cases)} links across {len(by_company)} companies")

    results: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for i, case in enumerate(cases):
            domain = case["url"].split("/")[2]
            if domain in SSR_CHECK_DOMAINS:
                status = check_ssr(case["url"], case["title"])
            else:
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                status = check_browser(page, case["url"], case["title"])
                page.close()
            results.append({**case, "status": status})
            if (i + 1) % 10 == 0:
                print(f"  {i + 1}/{len(cases)} done")
        browser.close()

    stats = Counter(r["status"] for r in results)
    total = len(results)
    dead = total - stats.get("OK", 0)
    dead_ratio = dead / total if total else 0

    # Report
    lines = [
        "# 链接健康报告",
        "",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 检查 {total} 个链接",
        "",
        f"| 状态 | 数量 | 占比 |",
        f"| --- | --- | --- |",
    ]
    for status, n in stats.most_common():
        lines.append(f"| {status} | {n} | {n / total:.1%} |")
    lines.append("")

    problems = [r for r in results if r["status"] != "OK"]
    if problems:
        lines.append("## 问题链接")
        lines.append("")
        for r in problems[:50]:
            lines.append(f"- [{r['status']}] {r['company']} | {r['title'][:40]} | {r['url']}")
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"report written to {REPORT_FILE}")
    print(f"stats: {dict(stats)} | dead ratio {dead_ratio:.1%}")

    return 1 if dead_ratio > LINK_FAILURE_THRESHOLD else 0


if __name__ == "__main__":
    sys.exit(main())
