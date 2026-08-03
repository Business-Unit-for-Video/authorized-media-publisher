from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote, urlparse, urlsplit, urlunsplit
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
        return [{**row, "thumbnail_url": row.get("thumbnail_url") or ""} for row in rows]
    missing = set(IMAGE_INVENTORY_FIELDS) - fieldnames
    if missing:
        raise ValueError(f"{path}: unsupported image schema; missing columns: {', '.join(sorted(missing))}")
    return [{
        "id": row["id"],
        "image_url": row["image_url"],
        "thumbnail_url": row.get("thumbnail_url") or "",
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


def load_publish_state(path: Path, legacy_image_state_path: Path | None = None) -> dict[str, object]:
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
    else:
        images = load_image_state(legacy_image_state_path) if legacy_image_state_path else {
            "cycle": 1, "used_image_ids": []
        }
        state = {"version": 1, "images": images, "videos": {}, "season": {}}
    if state.get("version") != 1 or not isinstance(state.get("videos"), dict):
        raise ValueError(f"{path}: unsupported publish state")
    images = state.get("images")
    if not isinstance(images, dict):
        raise ValueError(f"{path}: images must be an object")
    load_image_state_from_value(images, path)
    if not isinstance(state.get("season", {}), dict):
        raise ValueError(f"{path}: season must be an object")
    return state


def load_image_state_from_value(state: dict[str, object], path: Path) -> dict[str, object]:
    used = state.get("used_image_ids", [])
    cycle = state.get("cycle", 1)
    if not isinstance(used, list) or not all(isinstance(item, str) for item in used):
        raise ValueError(f"{path}: used_image_ids must be a list of strings")
    if not isinstance(cycle, int) or cycle < 1:
        raise ValueError(f"{path}: cycle must be a positive integer")
    return {"cycle": cycle, "used_image_ids": used}


def select_video_batch(
    videos: list[dict[str, str]], state: dict[str, object], batch_size: int,
) -> list[dict[str, str]]:
    if batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    known = state["videos"]
    selected = [
        row for row in videos
        if row["id"] not in known or known[row["id"]].get("status") == "reserved"
    ]
    return selected[:batch_size]


def select_images_with_cycles(
    images: list[dict[str, str]], count: int, state: dict[str, object],
) -> tuple[list[tuple[dict[str, str], int]], dict[str, object]]:
    if not images:
        raise ValueError("image: manifest is empty")
    used = set(state["used_image_ids"])
    cycle = int(state["cycle"])
    selected: list[tuple[dict[str, str], int]] = []
    while len(selected) < count:
        available = [row for row in images if row["id"] not in used]
        if not available:
            used.clear()
            cycle += 1
            available = list(images)
        take = min(count - len(selected), len(available))
        for row in available[:take]:
            selected.append((row, cycle))
            used.add(row["id"])
    return selected, {"cycle": cycle, "used_image_ids": sorted(used)}


def validate_rows(rows: list[dict[str, str]], label: str) -> None:
    if not rows:
        raise ValueError(f"{label}: manifest is empty")
    seen: set[str] = set()
    for row in rows:
        item_id = row["id"].strip()
        if not item_id or item_id in seen:
            raise ValueError(f"{label}: duplicate or empty id: {item_id!r}")
        seen.add(item_id)
        parsed = urlparse(row["video_url"] if label == "video" else row["image_url"])
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"{label} {item_id}: URL must be http(s)")


def download(url: str, target: Path) -> None:
    parts = urlsplit(url)
    request_url = urlunsplit((
        parts.scheme,
        parts.netloc,
        quote(parts.path, safe="/%:@"),
        parts.query,
        parts.fragment,
    ))
    request = Request(request_url, headers={"User-Agent": "authorized-media-publisher/0.1"})
    with urlopen(request) as response, target.open("wb") as handle:
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)


def validate_image(path: Path) -> None:
    result = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", str(path),
            "-frames:v", "1", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "unable to decode an image frame"
        raise ValueError(f"downloaded file is not a valid image: {detail}")


def download_image(row: dict[str, str], target: Path) -> str:
    urls = [row["image_url"]]
    thumbnail_url = row.get("thumbnail_url", "").strip()
    if thumbnail_url and thumbnail_url not in urls:
        urls.append(thumbnail_url)
    failures: list[str] = []
    for url in urls:
        for attempt in range(2):
            try:
                target.unlink(missing_ok=True)
                download(url, target)
                validate_image(target)
                return url
            except Exception as exc:
                failures.append(f"{url} attempt {attempt + 1}: {exc}")
    target.unlink(missing_ok=True)
    raise RuntimeError(
        f"image {row['id']}: primary and fallback downloads were invalid; "
        + "; ".join(failures)
    )


def download_video(url: str, target: Path, cookie_path: Path | None = None) -> Path:
    host = (urlparse(url).hostname or "").lower()
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        command = [
            sys.executable, "-m", "yt_dlp", "--no-playlist",
            "--js-runtimes", "node", "--remote-components", "ejs:github",
            "-f", "bv*+ba/b", "--merge-output-format", "mp4",
            "--print", "after_move:filepath",
        ]
        if cookie_path:
            command.extend(["--cookies", str(cookie_path)])
        command.extend(["-o", f"{target}.%(ext)s", url])
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        paths = [Path(line) for line in result.stdout.splitlines() if line.strip()]
        if not paths or not paths[-1].is_file():
            raise RuntimeError("yt-dlp did not report a downloaded media file")
        return paths[-1]
    download(url, target)
    return target


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
    publish_state_path: Path = Path("state/publish-state.json"),
    batch_size: int = 1,
    youtube_cookies: Path | None = None,
) -> int:
    videos = read_video_manifest(video_manifest, video_rights_basis, video_publish_scope)
    images = read_image_manifest(image_manifest, image_rights_basis, image_publish_scope)
    validate_rows(videos, "video")
    validate_rows(images, "image")
    publish_state = load_publish_state(
        publish_state_path, publish_state_path.with_name("image-usage.json")
    )
    selected_videos = select_video_batch(videos, publish_state, batch_size)
    selected_images: list[tuple[dict[str, str], int]] = []
    working_image_state = dict(publish_state["images"])
    image_by_id = {row["id"]: row for row in images}
    for video_row in selected_videos:
        existing = publish_state["videos"].get(video_row["id"], {})
        if existing.get("status") == "reserved":
            image_id = str(existing["image_id"])
            if image_id not in image_by_id:
                raise ValueError(f"reserved image {image_id} is no longer in the manifest")
            selected_images.append((image_by_id[image_id], int(existing["image_cycle"])))
        else:
            chosen, working_image_state = select_images_with_cycles(
                images, 1, working_image_state
            )
            selected_images.extend(chosen)
    output_dir.mkdir(parents=True, exist_ok=True)
    report: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="media-publisher-") as temp:
        temp_dir = Path(temp)
        downloaded_images: list[tuple[Path, str]] = []
        # Validate all selected images before expensive video downloads and transcodes.
        for index, (image_row, _) in enumerate(selected_images):
            image_path = temp_dir / f"{index:04d}-{image_row['id']}.image"
            actual_image_url = download_image(image_row, image_path)
            downloaded_images.append((image_path, actual_image_url))
        for index, video_row in enumerate(selected_videos):
            image_row, image_cycle = selected_images[index]
            video_path = download_video(video_row["video_url"], temp_dir / video_row["id"], youtube_cookies)
            image_path, actual_image_url = downloaded_images[index]
            output_path = output_dir / f"{index + 1:04d}-{video_row['id']}.mp4"
            run_ffmpeg(video_path, image_path, output_path, width, height)
            report.append({
                "video_id": video_row["id"],
                "file": str(output_path),
                "title": video_row["title"],
                "video_source": video_row["video_url"],
                "video_rights_basis": video_row["rights_basis"],
                "image_source": actual_image_url,
                "image_rights_basis": image_row["rights_basis"],
                "image_id": image_row["id"],
                "image_usage_cycle": str(image_cycle),
                "attribution": image_row["attribution"],
            })
    (output_dir.parent / "build-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return len(selected_videos)


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
    parser.add_argument("--publish-state", type=Path, default=Path("state/publish-state.json"))
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--youtube-cookies", type=Path)
    args = parser.parse_args()
    count = build(
        args.videos, args.images, args.output, args.width, args.height,
        args.video_rights_basis, args.video_publish_scope,
        args.image_rights_basis, args.image_publish_scope,
        args.publish_state, args.batch_size, args.youtube_cookies,
    )
    print(json.dumps({"built": count, "width": args.width, "height": args.height}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
