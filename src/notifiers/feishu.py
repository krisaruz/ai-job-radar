from __future__ import annotations

import hashlib
import hmac
import base64
import logging
import os
import time

import httpx

from src.models import JobPosting
from src.pipeline.diff import DiffResult

logger = logging.getLogger(__name__)

PLATFORM_NAMES = {
    "tencent": "腾讯",
    "alibaba": "阿里巴巴",
    "bytedance": "字节跳动",
    "baidu": "百度",
    "boss": "Boss直聘",
    "liepin": "猎聘",
    "zhilian": "智联招聘",
    "job51": "前程无忧",
    "lagou": "拉勾",
    "linkedin": "LinkedIn",
    "maimai": "脉脉",
    "meituan": "美团",
    "kuaishou": "快手",
    "xiaohongshu": "小红书",
    "netease": "网易",
    "huawei": "华为",
}


def send_feishu_notification(
    webhook_url: str,
    diff: DiffResult,
    total_active: int,
    secret: str | None = None,
) -> bool:
    if not webhook_url:
        logger.warning("Feishu webhook URL not configured, skipping notification")
        return False

    if not diff.has_changes:
        logger.info("No changes to report, skipping Feishu notification")
        return True

    if secret is None:
        secret = os.environ.get("FEISHU_SECRET")

    card = _build_card(diff, total_active)
    payload: dict = {"msg_type": "interactive", "card": card}

    if secret:
        timestamp = str(int(time.time()))
        sign = _gen_sign(timestamp, secret)
        payload["timestamp"] = timestamp
        payload["sign"] = sign

    try:
        resp = httpx.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 0 or result.get("StatusCode") == 0:
            logger.info("Feishu notification sent successfully")
            return True
        logger.warning("Feishu API error: %s", result)
        return False
    except Exception:
        logger.error("Failed to send Feishu notification", exc_info=True)
        return False


def _build_card(diff: DiffResult, total_active: int) -> dict:
    new_count = len(diff.new_jobs)
    removed_count = len(diff.removed_jobs)

    elements = []

    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": (
                f"**当前活跃岗位**: {total_active} 个 | "
                f"**新增**: {new_count} | "
                f"**下线**: {removed_count}"
            ),
        },
    })

    elements.append({"tag": "hr"})

    if diff.new_jobs:
        by_company: dict[str, list[JobPosting]] = {}
        for j in diff.new_jobs:
            company = PLATFORM_NAMES.get(j.platform, j.company)
            by_company.setdefault(company, []).append(j)

        for company, jobs in by_company.items():
            lines = [f"**{company}** ({len(jobs)} 个新增)"]
            for j in jobs[:10]:
                loc = f" | {j.location}" if j.location else ""
                link = f"[{j.title}]({j.url})" if j.url else j.title
                lines.append(f"  - {link}{loc}")
            if len(jobs) > 10:
                lines.append(f"  - ...等共 {len(jobs)} 个岗位")

            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": "\n".join(lines)},
            })

    if diff.removed_jobs:
        elements.append({"tag": "hr"})
        removed_titles = ", ".join(j.title for j in diff.removed_jobs[:5])
        more = f" 等共 {removed_count} 个" if removed_count > 5 else ""
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**下线岗位**: {removed_titles}{more}",
            },
        })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "content": f"AI 岗位雷达 - 今日新增 {new_count} 个岗位",
                "tag": "plain_text",
            },
            "template": "blue" if new_count > 0 else "grey",
        },
        "elements": elements,
    }


def _gen_sign(timestamp: str, secret: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")
