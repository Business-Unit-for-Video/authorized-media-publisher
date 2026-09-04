from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from media_publisher.cli import load_publish_state, write_image_state


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_state(path: Path, state: dict[str, object]) -> None:
    write_image_state(path, state)


def git_commit_state(path: Path, message: str) -> None:
    subprocess.run(["git", "add", str(path)], check=True)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if staged.returncode == 0:
        return
    if staged.returncode != 1:
        raise RuntimeError("unable to inspect staged publish state")
    subprocess.run(["git", "commit", "-m", message], check=True)
    subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)


def reserve_record(
    state: dict[str, object], record: dict[str, str], run_id: str,
) -> None:
    video_id = record["video_id"]
    videos = state["videos"]
    if video_id in videos:
        existing = videos[video_id]
        if existing.get("video_url") != record["video_source"]:
            raise ValueError(f"video {video_id}: source URL changed")
        if existing.get("status") == "reserved":
            if existing.get("image_id") != record["image_id"]:
                raise ValueError(f"video {video_id}: reserved image changed")
            existing.update({"workflow_run_id": run_id, "reserved_at": now_iso()})
            return
        if existing.get("status") == "submitting":
            raise RuntimeError(
                f"video {video_id}: upload may have completed; inspect Bilibili before retrying"
            )
        raise ValueError(f"video {video_id}: already uploaded or published")
    images = state["images"]
    image_cycle = int(record["image_usage_cycle"])
    if image_cycle > int(images["cycle"]):
        images["cycle"] = image_cycle
        images["used_image_ids"] = []
    used = set(images["used_image_ids"])
    used.add(record["image_id"])
    images["used_image_ids"] = sorted(used)
    videos[video_id] = {
        "status": "reserved",
        "video_url": record["video_source"],
        "title": record["title"],
        "image_id": record["image_id"],
        "image_cycle": image_cycle,
        "workflow_run_id": run_id,
        "reserved_at": now_iso(),
    }


def mark_submitting(state: dict[str, object], video_id: str) -> None:
    entry = state["videos"][video_id]
    entry.update({"status": "submitting", "submitting_at": now_iso()})


def mark_uploaded(state: dict[str, object], video_id: str, result: dict[str, object]) -> None:
    entry = state["videos"][video_id]
    entry.update({
        "status": "uploaded",
        "aid": int(result["aid"]),
        "bvid": str(result.get("bvid") or ""),
        "uploaded_at": now_iso(),
    })


def mark_published(
    state: dict[str, object], video_id: str, season_id: int, section_id: int,
) -> None:
    entry = state["videos"][video_id]
    entry.update({
        "status": "published",
        "season_id": season_id,
        "section_id": section_id,
        "season_attached": True,
        "published_at": now_iso(),
    })


def mark_unavailable(
    state: dict[str, object], record: dict[str, str], reason: str,
) -> None:
    """Record a source video that the platform explicitly reports unavailable."""
    video_id = record["id"]
    videos = state["videos"]
    entry = videos.get(video_id)
    if entry is None:
        entry = {
            "video_url": record["video_url"],
            "title": record["title"],
        }
        videos[video_id] = entry
    entry.update({
        "status": "unavailable",
        "video_url": record["video_url"],
        "title": record["title"],
        "unavailable_reason": reason[:500],
        "unavailable_at": now_iso(),
    })


def mark_duplicate(
    state: dict[str, object], record: dict[str, str], duplicate_of: str,
) -> None:
    """Record a different source ID for content that is already published."""
    video_id = record["id"]
    entry = state["videos"].get(video_id) or {}
    state["videos"][video_id] = entry
    entry.update({
        "status": "duplicate",
        "video_url": record["video_url"],
        "title": record["title"],
        "duplicate_of": duplicate_of,
        "duplicate_reason": "normalized title matches already published content",
        "duplicate_at": now_iso(),
    })


def load_cookie_data(path: Path) -> tuple[dict[str, str], str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cookies = {
        item["name"]: item["value"]
        for item in data.get("cookie_info", {}).get("cookies", [])
    }
    csrf = cookies.get("bili_jct", "")
    if not cookies.get("SESSDATA") or not csrf:
        raise ValueError("Bilibili cookies require SESSDATA and bili_jct")
    return cookies, csrf


def upload_video(
    record: dict[str, str], cookie_path: Path, visibility: str, tid: int, tags: str,
) -> dict[str, object]:
    from biliup.plugins.bili_webup import BiliBili, Data

    if visibility != "public":
        raise ValueError("Bilibili publishing is public-only")

    @dataclass
    class PublishData(Data):
        is_only_self: int = 0

    video = PublishData(is_only_self=0)
    video.title = record["title"][:80]
    video.desc = (
        f"Video source: {record['video_source']}\n"
        f"Image source: {record['image_source']}\n{record['attribution']}"
    )
    video.copyright = 2
    video.source = record["video_source"]
    video.tid = tid
    video.set_tag([item.strip() for item in tags.split(",") if item.strip()])
    with BiliBili(video) as bili:
        bili.login(str(cookie_path), str(cookie_path))
        part = bili.upload_file(record["file"], "AUTO", 3)
        part["title"] = Path(record["file"]).stem[:80]
        video.append(part)
        result = bili.submit("web")
    if result.get("code") != 0:
        raise RuntimeError(f"Bilibili upload failed: {result.get('code')} {result.get('message')}")
    payload = result.get("data") or {}
    aid = payload.get("aid") or result.get("aid")
    bvid = payload.get("bvid") or result.get("bvid") or ""
    if not aid:
        raise RuntimeError("Bilibili upload succeeded without an aid")
    return {"aid": int(aid), "bvid": str(bvid)}


class SeasonClient:
    def __init__(self, cookie_path: Path):
        import requests

        cookies, self.csrf = load_cookie_data(cookie_path)
        self.session = requests.Session()
        self.session.cookies.update(cookies)
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Origin": "https://member.bilibili.com",
            "Referer": "https://member.bilibili.com/",
        })

    def request(self, method: str, url: str, **kwargs) -> object:
        response = self.session.request(method, url, timeout=30, **kwargs)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"Bilibili API failed: {payload.get('code')} {payload.get('message')}")
        return payload.get("data")

    def seasons(self) -> list[dict[str, object]]:
        data = self.request(
            "GET", "https://member.bilibili.com/x2/creative/web/seasons",
            params={"pn": 1, "ps": 50, "order": "desc", "sort": "mtime", "filter": 1},
        )
        return (data or {}).get("seasons", [])

    def resolve_or_create(self, title: str, description: str) -> tuple[int, int]:
        for item in self.seasons():
            season = item.get("season", {})
            if season.get("title") == title:
                sections = item.get("sections", {}).get("sections", [])
                if not sections:
                    raise RuntimeError("Bilibili season has no section")
                return int(season["id"]), int(sections[0]["id"])
        data = self.request(
            "POST",
            "https://member.bilibili.com/x2/creative/web/season/add",
            params={"csrf": self.csrf},
            json={
                "title": title[:20],
                "cover": "https://s1.hdslb.com/bfs/templar/york-static/viedeo_material_default.png",
                "desc": description,
            },
        )
        season_id = int(data.get("season_id") if isinstance(data, dict) else data)
        for item in self.seasons():
            season = item.get("season", {})
            if int(season.get("id", 0)) == season_id:
                sections = item.get("sections", {}).get("sections", [])
                return season_id, int(sections[0]["id"])
        raise RuntimeError("created Bilibili season was not returned by season list")

    def attach(self, aid: int, title: str, section_id: int) -> None:
        section = self.request(
            "GET", "https://member.bilibili.com/x2/creative/web/season/section",
            params={"id": section_id},
        ) or {}
        episodes = section.get("episodes") or []
        if any(int(item.get("aid", 0)) == aid for item in episodes):
            return
        verify = self.request(
            "GET",
            "https://member.bilibili.com/x2/creative/web/season/section/episode/verify/batch",
            params={"aids": str(aid)},
        ) or {}
        audit = (verify.get("ep_audits") or {}).get(str(aid), {})
        if int(audit.get("code", 0)) != 0:
            raise RuntimeError(f"video {aid} cannot join season: {audit.get('msg', '')}")
        cid = audit.get("cid")
        if not cid:
            info = self.request(
                "GET", "https://member.bilibili.com/x/client/archive/view",
                params={"aid": aid},
            ) or {}
            cid = (info.get("videos") or [{}])[0].get("cid")
        if not cid:
            raise RuntimeError(f"video {aid}: no cid available")
        self.request(
            "POST",
            "https://member.bilibili.com/x2/creative/web/season/section/episodes/add",
            params={"csrf": self.csrf},
            json={
                "sectionId": section_id,
                "episodes": [{
                    "title": title,
                    "aid": aid,
                    "cid": int(cid),
                    "charging_pay": 0,
                    "member_first": 0,
                }],
                "csrf": self.csrf,
            },
        )
        refreshed = self.request(
            "GET", "https://member.bilibili.com/x2/creative/web/season/section",
            params={"id": section_id},
        ) or {}
        refreshed_episodes = refreshed.get("episodes") or []
        if not any(int(item.get("aid", 0)) == aid for item in refreshed_episodes):
            raise RuntimeError(f"video {aid} was not present after season attachment")


def publish(
    report_path: Path,
    cookie_path: Path,
    visibility: str,
    tid: int,
    tags: str,
    state_path: Path,
    season_title: str,
    season_description: str,
    run_id: str = "local",
    persist: Callable[[Path, str], None] = git_commit_state,
    uploader: Callable[..., dict[str, object]] = upload_video,
    season_factory: Callable[[Path], SeasonClient] = SeasonClient,
    max_items: int | None = None,
    eligible_video_ids: set[str] | None = None,
) -> int:
    if visibility != "public":
        raise ValueError("Bilibili publishing is public-only")
    records = json.loads(report_path.read_text(encoding="utf-8"))
    state = load_publish_state(state_path, state_path.with_name("image-usage.json"))
    pending_uploaded = [
        (video_id, entry)
        for video_id, entry in state["videos"].items()
        if entry.get("status") == "uploaded"
        and (eligible_video_ids is None or video_id in eligible_video_ids)
    ]
    if not records and not pending_uploaded:
        return 0
    season_client = season_factory(cookie_path)
    normalized_title = season_title[:20]
    season_id, section_id = season_client.resolve_or_create(normalized_title, season_description)
    state["season"] = {
        "title": normalized_title,
        "season_id": season_id,
        "section_id": section_id,
    }
    completed = 0
    for video_id, entry in pending_uploaded:
        if max_items is not None and completed >= max_items:
            return completed
        season_client.attach(int(entry["aid"]), str(entry["title"]), section_id)
        mark_published(state, video_id, season_id, section_id)
        save_state(state_path, state)
        persist(state_path, f"chore: attach Bilibili season {video_id}")
        completed += 1
    for record in records:
        if max_items is not None and completed >= max_items:
            return completed
        reserve_record(state, record, run_id)
        save_state(state_path, state)
        persist(state_path, f"chore: reserve Bilibili video {record['video_id']}")
        mark_submitting(state, record["video_id"])
        save_state(state_path, state)
        persist(state_path, f"chore: mark Bilibili submission {record['video_id']}")
        result = uploader(record, cookie_path, visibility, tid, tags)
        mark_uploaded(state, record["video_id"], result)
        save_state(state_path, state)
        persist(state_path, f"chore: record Bilibili upload {record['video_id']}")
        season_client.attach(int(result["aid"]), record["title"], section_id)
        mark_published(state, record["video_id"], season_id, section_id)
        save_state(state_path, state)
        persist(state_path, f"chore: attach Bilibili season {record['video_id']}")
        completed += 1
    return completed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=Path("output/build-report.json"))
    parser.add_argument("--cookies", type=Path, required=True)
    parser.add_argument("--visibility", choices=("public",), default="public")
    parser.add_argument("--tid", type=int, default=171)
    parser.add_argument("--tags", default="授权素材,音乐")
    parser.add_argument("--state", type=Path, default=Path("state/publish-state.json"))
    parser.add_argument("--season-title", required=True)
    parser.add_argument("--season-description", default="")
    parser.add_argument("--run-id", default="local")
    args = parser.parse_args()
    count = publish(
        args.report, args.cookies, args.visibility, args.tid, args.tags,
        args.state, args.season_title, args.season_description, args.run_id,
    )
    print(json.dumps({"published": count, "visibility": args.visibility}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
