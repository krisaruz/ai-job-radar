from __future__ import annotations

import os
from pathlib import Path

import yaml


def load_config(config_path: str | None = None) -> dict:
    if config_path is None:
        config_path = str(Path(__file__).parent.parent / "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg


def get_project_root() -> Path:
    return Path(__file__).parent.parent


def get_data_dir() -> Path:
    d = get_project_root() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_feishu_webhook_url() -> str | None:
    return os.environ.get("FEISHU_WEBHOOK_URL")
