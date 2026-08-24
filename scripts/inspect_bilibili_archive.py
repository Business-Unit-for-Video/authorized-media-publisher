"""Write a non-sensitive Bilibili archive status report for one submission."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import requests

from media_publisher.publish import load_cookie_data


SIGNAL_WORDS = ("audit", "reason", "reject", "state", "message", "warning", "notice")
IDENTITY_FIELDS = ("aid", "bvid", "title", "cid", "tid", "ctime", "pubtime")


def collect_review_signals(value: Any, path: str = "") -> list[dict[str, Any]]:
    """Keep only fields that can explain an archive's review state."""
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}" if path else key
            if any(word in key.lower() for word in SIGNAL_WORDS):
                found.append({"field": item_path, "value": item})
            found.extend(collect_review_signals(item, item_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(collect_review_signals(item, f"{path}[{index}]"))
    return found


def summarize(payload: dict[str, Any], endpoint: str) -> dict[str, Any]:
    data = payload.get("data") or {}
    archive = data.get("archive", data) if isinstance(data, dict) else {}
    identity = {
        key: archive[key]
        for key in IDENTITY_FIELDS
        if isinstance(archive, dict) and key in archive
    }
    return {
        "endpoint": endpoint,
        "code": payload.get("code"),
        "message": payload.get("message"),
        "archive": identity,
        "review_signals": collect_review_signals(data),
    }


def inspect_archive(cookie_path: Path, aid: int) -> dict[str, Any]:
    cookies, _ = load_cookie_data(cookie_path)
    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Origin": "https://member.bilibili.com",
        "Referer": "https://member.bilibili.com/",
    })
    reports: list[dict[str, Any]] = []
    for endpoint in (
        "https://member.bilibili.com/x/client/archive/view",
        "https://member.bilibili.com/x/vupre/web/archive/view",
    ):
        response = session.get(endpoint, params={"aid": aid}, timeout=30)
        response.raise_for_status()
        reports.append(summarize(response.json(), endpoint))
    return {"aid": aid, "reports": reports}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cookies", type=Path, required=True)
    parser.add_argument("--aid", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = inspect_archive(args.cookies, args.aid)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for item in report["reports"]:
        print(f"{item['endpoint']}: {item['code']} {item['message']}")
        for signal in item["review_signals"]:
            print(f"{signal['field']}: {signal['value']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
