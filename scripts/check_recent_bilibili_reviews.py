"""Stop publishing when recent target-manifest submissions show rejection signals."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from media_publisher.publish import load_cookie_data
from scripts.inspect_bilibili_archive import inspect_archive


REJECTION_WORDS = re.compile(
    r"拒|驳|驳回|违规|违禁|封禁|封号|下架|不通过|失败|reject|rejected|denied|blocked|fail",
    re.IGNORECASE,
)


def has_rejection_signal(signals: list[dict[str, Any]]) -> bool:
    for signal in signals:
        field = str(signal.get("field", "")).lower()
        value = signal.get("value")
        if value in (None, "", [], {}):
            continue
        text = json.dumps(value, ensure_ascii=False)
        if "reject" in field or "reject" in text.lower():
            return True
        if any(key in field for key in ("audit_status", "review_status", "state", "status")):
            if REJECTION_WORDS.search(text):
                return True
        if "reason" in field and REJECTION_WORDS.search(text):
            return True
    return False


def check_recent(
    cookies: Path, state_path: Path, video_manifest: Path, output: Path, limit: int,
) -> int:
    manifest_ids = {
        row["id"] for row in __import__("csv").DictReader(
            video_manifest.open(encoding="utf-8-sig", newline="")
        )
    }
    state = json.loads(state_path.read_text(encoding="utf-8"))
    candidates: list[tuple[str, dict[str, Any]]] = []
    for video_id, entry in state.get("videos", {}).items():
        if video_id not in manifest_ids or not entry.get("aid"):
            continue
        if entry.get("status") == "rejected":
            candidates.append((video_id, entry))
            continue
        if entry.get("status") in {"published", "uploaded"}:
            candidates.append((video_id, entry))
    candidates.sort(
        key=lambda item: item[1].get("published_at")
        or item[1].get("uploaded_at")
        or item[1].get("submitting_at")
        or "",
        reverse=True,
    )
    reports: list[dict[str, Any]] = []
    blocked = False
    for video_id, entry in candidates[:limit]:
        if entry.get("status") == "rejected":
            reports.append({"video_id": video_id, "aid": entry["aid"], "rejected": True, "source": "state"})
            blocked = True
            continue
        report = inspect_archive(cookies, int(entry["aid"]))
        rejected = any(
            has_rejection_signal(item.get("review_signals", []))
            for item in report["reports"]
        )
        reports.append({"video_id": video_id, "aid": entry["aid"], "rejected": rejected, "inspection": report})
        blocked = blocked or rejected
    result = {"checked": len(reports), "blocked": blocked, "reports": reports}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"checked": len(reports), "blocked": blocked}, ensure_ascii=False))
    return 2 if blocked else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cookies", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--videos", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=2)
    args = parser.parse_args()
    return check_recent(args.cookies, args.state, args.videos, args.output, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
