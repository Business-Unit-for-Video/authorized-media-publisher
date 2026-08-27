from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Callable

from media_publisher.cli import build, load_publish_state
from media_publisher.publish import publish


def serial_publish(
    video_manifest: Path,
    image_manifest: Path,
    output_dir: Path,
    width: int,
    height: int,
    publish_state_path: Path,
    batch_size: int,
    youtube_cookies: Path | None,
    bilibili_cookies: Path,
    visibility: str,
    tid: int,
    tags: str,
    season_title: str,
    season_description: str,
    run_id: str,
    builder: Callable[..., int] = build,
    publisher: Callable[..., int] = publish,
    content_policy: str = "all",
    min_duration_seconds: int = 1800,
) -> dict[str, int]:
    if batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    if visibility != "public":
        raise ValueError("Bilibili publishing is public-only")

    built = 0
    published = 0
    report_path = output_dir.parent / "build-report.json"
    for item_number in range(1, batch_size + 1):
        state = load_publish_state(
            publish_state_path, publish_state_path.with_name("image-usage.json")
        )
        uncertain = [
            video_id for video_id, entry in state["videos"].items()
            if entry.get("status") in {"submitting", "uploading"}
        ]
        if uncertain:
            raise RuntimeError(
                "upload outcome is uncertain for video(s) "
                + ", ".join(uncertain)
                + "; inspect Bilibili and reconcile state before continuing"
            )
        pending_uploaded = any(
            entry.get("status") == "uploaded" for entry in state["videos"].values()
        )
        if pending_uploaded:
            output_dir.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text("[]\n", encoding="utf-8")
            published += publisher(
                report_path,
                bilibili_cookies,
                visibility,
                tid,
                tags,
                publish_state_path,
                season_title,
                season_description,
                f"{run_id}-{item_number}",
                max_items=1,
            )
            continue

        # Each iteration exposes only one newly built file to the publisher.
        shutil.rmtree(output_dir, ignore_errors=True)
        report_path.unlink(missing_ok=True)
        item_built = builder(
            video_manifest,
            image_manifest,
            output_dir,
            width,
            height,
            publish_state_path=publish_state_path,
            batch_size=1,
            youtube_cookies=youtube_cookies,
            content_policy=content_policy,
            min_duration_seconds=min_duration_seconds,
        )
        item_published = publisher(
            report_path,
            bilibili_cookies,
            visibility,
            tid,
            tags,
            publish_state_path,
            season_title,
            season_description,
            f"{run_id}-{item_number}",
            max_items=1,
        )
        published += item_published
        if item_built == 0:
            break
        built += item_built

    return {"built": built, "published": published}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--videos", type=Path, default=Path("input/videos.csv"))
    parser.add_argument("--images", type=Path, default=Path("input/images.csv"))
    parser.add_argument("--output", type=Path, default=Path("output/videos"))
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--state", type=Path, default=Path("state/publish-state.json"))
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--youtube-cookies", type=Path)
    parser.add_argument("--bilibili-cookies", type=Path, required=True)
    parser.add_argument("--visibility", choices=("public",), default="public")
    parser.add_argument("--tid", type=int, default=171)
    parser.add_argument("--tags", default="授权素材,音乐")
    parser.add_argument("--season-title", required=True)
    parser.add_argument("--season-description", default="")
    parser.add_argument("--run-id", default="local")
    parser.add_argument("--content-policy", choices=("all", "long_form"), default="all")
    parser.add_argument("--min-duration-seconds", type=int, default=1800)
    args = parser.parse_args()

    result = serial_publish(
        args.videos,
        args.images,
        args.output,
        args.width,
        args.height,
        args.state,
        args.batch_size,
        args.youtube_cookies,
        args.bilibili_cookies,
        args.visibility,
        args.tid,
        args.tags,
        args.season_title,
        args.season_description,
        args.run_id,
        content_policy=args.content_policy,
        min_duration_seconds=args.min_duration_seconds,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
