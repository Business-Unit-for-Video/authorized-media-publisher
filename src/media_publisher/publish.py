from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def publish(report_path: Path, cookie_path: Path, visibility: str, tid: int, tags: str) -> int:
    records = json.loads(report_path.read_text(encoding="utf-8"))
    for record in records:
        command = [
            "biliup", "-u", str(cookie_path), "upload", record["file"],
            "--copyright", "2", "--source", record["video_source"],
            "--tid", str(tid), "--title", record["title"][:80],
            "--desc", (
                f"Video source: {record['video_source']}\n"
                f"Image source: {record['image_source']}\n{record['attribution']}"
            ),
            "--tag", tags,
        ]
        if visibility == "private":
            command.extend(["--is-only-self", "1"])
        subprocess.run(command, check=True)
    return len(records)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=Path("output/build-report.json"))
    parser.add_argument("--cookies", type=Path, required=True)
    parser.add_argument("--visibility", choices=("private", "public"), default="private")
    parser.add_argument("--tid", type=int, default=171)
    parser.add_argument("--tags", default="授权素材,音乐")
    args = parser.parse_args()
    count = publish(args.report, args.cookies, args.visibility, args.tid, args.tags)
    print(json.dumps({"published": count, "visibility": args.visibility}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
