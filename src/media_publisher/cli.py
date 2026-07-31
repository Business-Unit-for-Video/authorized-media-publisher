from __future__ import annotations

import argparse
import csv
import json
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

VIDEO_FIELDS = ("id", "title", "video_url", "rights_basis", "publish_scope")
IMAGE_FIELDS = ("id", "image_url", "rights_basis", "publish_scope", "attribution")


def read_manifest(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    missing = set(fields) - set(rows[0]) if rows else set(fields)
    if missing:
        raise ValueError(f"{path}: missing columns: {', '.join(sorted(missing))}")
    return rows


def validate_rows(rows: list[dict[str, str]], label: str) -> None:
    if not rows:
        raise ValueError(f"{label}: manifest is empty")
    seen: set[str] = set()
    for row in rows:
        item_id = row["id"].strip()
        if not item_id or item_id in seen:
            raise ValueError(f"{label}: duplicate or empty id: {item_id!r}")
        seen.add(item_id)
        if not row["rights_basis"].strip():
            raise ValueError(f"{label} {item_id}: rights_basis is required")
        if not row["publish_scope"].strip():
            raise ValueError(f"{label} {item_id}: publish_scope is required")
        parsed = urlparse(row["video_url"] if label == "video" else row["image_url"])
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"{label} {item_id}: URL must be http(s)")


def download(url: str, target: Path) -> None:
    request = Request(url, headers={"User-Agent": "authorized-media-publisher/0.1"})
    with urlopen(request) as response, target.open("wb") as handle:
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)


def run_ffmpeg(video: Path, image: Path, output: Path, width: int, height: int) -> None:
    filtergraph = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    )
    command = [
        "ffmpeg", "-y", "-i", str(video), "-loop", "1", "-i", str(image),
        "-filter_complex", f"[1:v]{filtergraph}[cover]",
        "-map", "0:a?", "-map", "[cover]", "-c:v", "mpeg4", "-b:v", "2M", "-pix_fmt", "yuv420p", "-shortest", "-movflags", "+faststart", str(output),
    ]
    subprocess.run(command, check=True)


def build(video_manifest: Path, image_manifest: Path, output_dir: Path, width: int, height: int) -> int:
    videos = read_manifest(video_manifest, VIDEO_FIELDS)
    images = read_manifest(image_manifest, IMAGE_FIELDS)
    validate_rows(videos, "video")
    validate_rows(images, "image")
    output_dir.mkdir(parents=True, exist_ok=True)
    report: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="media-publisher-") as temp:
        temp_dir = Path(temp)
        for index, video_row in enumerate(videos):
            image_row = images[index % len(images)]
            video_path = temp_dir / f"{video_row['id']}.source"
            image_path = temp_dir / f"{image_row['id']}.image"
            output_path = output_dir / f"{index + 1:04d}-{video_row['id']}.mp4"
            download(video_row["video_url"], video_path)
            download(image_row["image_url"], image_path)
            run_ffmpeg(video_path, image_path, output_path, width, height)
            report.append({
                "file": str(output_path),
                "title": video_row["title"],
                "video_source": video_row["video_url"],
                "video_rights_basis": video_row["rights_basis"],
                "image_source": image_row["image_url"],
                "image_rights_basis": image_row["rights_basis"],
                "attribution": image_row["attribution"],
            })
    (output_dir.parent / "build-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return len(videos)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--videos", type=Path, default=Path("input/videos.csv"))
    parser.add_argument("--images", type=Path, default=Path("input/images.csv"))
    parser.add_argument("--output", type=Path, default=Path("output/videos"))
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    args = parser.parse_args()
    count = build(args.videos, args.images, args.output, args.width, args.height)
    print(json.dumps({"built": count, "width": args.width, "height": args.height}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
