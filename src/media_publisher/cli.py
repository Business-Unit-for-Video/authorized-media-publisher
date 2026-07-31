from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

VIDEO_FIELDS = ("id", "title", "video_url", "rights_basis", "publish_scope")
YOUTUBE_FIELDS = ("video_id", "url", "title")
IMAGE_FIELDS = ("id", "image_url", "rights_basis", "publish_scope", "attribution")
IMAGE_INVENTORY_FIELDS = ("id", "image_url", "source_page_url", "rights_status")


def read_manifest(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    missing = set(fields) - set(rows[0]) if rows else set(fields)
    if missing:
        raise ValueError(f"{path}: missing columns: {', '.join(sorted(missing))}")
    return rows


def read_video_manifest(
    path: Path,
    rights_basis: str = "",
    publish_scope: str = "",
) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        rows = list(reader)
    if set(VIDEO_FIELDS).issubset(fieldnames):
        return rows
    missing = set(YOUTUBE_FIELDS) - fieldnames
    if missing:
        raise ValueError(f"{path}: unsupported video schema; missing columns: {', '.join(sorted(missing))}")
    return [{
        "id": row["video_id"],
        "title": row["title"],
        "video_url": row["url"],
        "rights_basis": rights_basis,
        "publish_scope": publish_scope,
    } for row in rows]


def read_image_manifest(
    path: Path,
    rights_basis: str = "",
    publish_scope: str = "",
) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        rows = list(reader)
    if set(IMAGE_FIELDS).issubset(fieldnames):
        return rows
    missing = set(IMAGE_INVENTORY_FIELDS) - fieldnames
    if missing:
        raise ValueError(f"{path}: unsupported image schema; missing columns: {', '.join(sorted(missing))}")
    return [{
        "id": row["id"],
        "image_url": row["image_url"],
        "rights_basis": rights_basis,
        "publish_scope": publish_scope,
        "attribution": row.get("credit") or row.get("artist") or row.get("source_page_url") or "",
        "source_page_url": row.get("source_page_url") or "",
        "inventory_rights_status": row.get("rights_status") or "",
    } for row in rows]


def load_image_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"cycle": 1, "used_image_ids": []}
    state = json.loads(path.read_text(encoding="utf-8"))
    used = state.get("used_image_ids", [])
    cycle = state.get("cycle", 1)
    if not isinstance(used, list) or not all(isinstance(item, str) for item in used):
        raise ValueError(f"{path}: used_image_ids must be a list of strings")
    if not isinstance(cycle, int) or cycle < 1:
        raise ValueError(f"{path}: cycle must be a positive integer")
    return {"cycle": cycle, "used_image_ids": used}


def select_images(
    images: list[dict[str, str]],
    count: int,
    state: dict[str, object],
) -> tuple[list[dict[str, str]], dict[str, object]]:
    if not images:
        raise ValueError("image: manifest is empty")
    used = set(state["used_image_ids"])
    cycle = int(state["cycle"])
    selected: list[dict[str, str]] = []
    while len(selected) < count:
        available = [row for row in images if row["id"] not in used]
        if not available:
            used.clear()
            cycle += 1
            available = list(images)
        take = min(count - len(selected), len(available))
        chosen = available[:take]
        selected.extend(chosen)
        used.update(row["id"] for row in chosen)
    return selected, {"cycle": cycle, "used_image_ids": sorted(used)}


def write_image_state(path: Path, state: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


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


def download_video(url: str, target: Path) -> None:
    host = (urlparse(url).hostname or "").lower()
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        subprocess.run([
            sys.executable, "-m", "yt_dlp", "--no-playlist",
            "-f", "bv*+ba/b", "--merge-output-format", "mp4",
            "-o", str(target), url,
        ], check=True)
        return
    download(url, target)


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


def build(
    video_manifest: Path,
    image_manifest: Path,
    output_dir: Path,
    width: int,
    height: int,
    video_rights_basis: str = "",
    video_publish_scope: str = "",
    image_rights_basis: str = "",
    image_publish_scope: str = "",
    image_state_path: Path = Path("state/image-usage.json"),
) -> int:
    videos = read_video_manifest(video_manifest, video_rights_basis, video_publish_scope)
    images = read_image_manifest(image_manifest, image_rights_basis, image_publish_scope)
    validate_rows(videos, "video")
    validate_rows(images, "image")
    image_state = load_image_state(image_state_path)
    selected_images, next_image_state = select_images(images, len(videos), image_state)
    output_dir.mkdir(parents=True, exist_ok=True)
    report: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="media-publisher-") as temp:
        temp_dir = Path(temp)
        for index, video_row in enumerate(videos):
            image_row = selected_images[index]
            video_path = temp_dir / f"{video_row['id']}.source"
            image_path = temp_dir / f"{image_row['id']}.image"
            output_path = output_dir / f"{index + 1:04d}-{video_row['id']}.mp4"
            download_video(video_row["video_url"], video_path)
            download(image_row["image_url"], image_path)
            run_ffmpeg(video_path, image_path, output_path, width, height)
            report.append({
                "file": str(output_path),
                "title": video_row["title"],
                "video_source": video_row["video_url"],
                "video_rights_basis": video_row["rights_basis"],
                "image_source": image_row["image_url"],
                "image_rights_basis": image_row["rights_basis"],
                "image_id": image_row["id"],
                "image_usage_cycle": str(next_image_state["cycle"]),
                "attribution": image_row["attribution"],
            })
    (output_dir.parent / "build-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_image_state(image_state_path, next_image_state)
    return len(videos)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--videos", type=Path, default=Path("input/videos.csv"))
    parser.add_argument("--images", type=Path, default=Path("input/images.csv"))
    parser.add_argument("--output", type=Path, default=Path("output/videos"))
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--video-rights-basis", default="")
    parser.add_argument("--video-publish-scope", default="")
    parser.add_argument("--image-rights-basis", default="")
    parser.add_argument("--image-publish-scope", default="")
    parser.add_argument("--image-state", type=Path, default=Path("state/image-usage.json"))
    args = parser.parse_args()
    count = build(
        args.videos, args.images, args.output, args.width, args.height,
        args.video_rights_basis, args.video_publish_scope,
        args.image_rights_basis, args.image_publish_scope, args.image_state,
    )
    print(json.dumps({"built": count, "width": args.width, "height": args.height}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
