from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from media_publisher.publish import SeasonClient


def episodes(client: SeasonClient, section_id: int) -> list[dict[str, Any]]:
    data = cast(dict[str, Any], client.request(
        "GET",
        "https://member.bilibili.com/x2/creative/web/season/section",
        params={"id": section_id},
    ) or {})
    return cast(list[dict[str, Any]], data.get("episodes") or [])


def by_aid(items: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for item in items:
        aid = int(item.get("aid") or 0)
        if not aid:
            continue
        if aid in result:
            raise RuntimeError(f"duplicate aid {aid} in one Bilibili section")
        result[aid] = item
    return result


def move(
    cookie_path: Path,
    source_section_id: int,
    target_section_id: int,
    aids: list[int],
) -> dict[str, object]:
    if source_section_id == target_section_id:
        raise ValueError("source and target sections must differ")
    client = SeasonClient(cookie_path)
    requested = set(aids)
    source_before = by_aid(episodes(client, source_section_id))
    target_before = by_aid(episodes(client, target_section_id))
    if not requested:
        requested = set(source_before)
    absent = sorted(requested - set(source_before) - set(target_before))
    if absent:
        raise RuntimeError(f"aids absent from both source and target: {absent}")

    moved: list[int] = []
    already_moved: list[int] = []
    for aid in sorted(requested):
        source = by_aid(episodes(client, source_section_id))
        target = by_aid(episodes(client, target_section_id))
        source_episode = source.get(aid)
        if source_episode is None:
            if aid in target:
                already_moved.append(aid)
                continue
            raise RuntimeError(f"aid {aid} disappeared from both sections")

        if aid not in target:
            client.attach(aid, str(source_episode.get("title") or aid), target_section_id)
        target_verified = by_aid(episodes(client, target_section_id))
        if aid not in target_verified:
            raise RuntimeError(f"aid {aid} was not verified in target; source retained")

        episode_id = int(source_episode.get("id") or 0)
        if not episode_id:
            raise RuntimeError(f"aid {aid}: source episode has no episode id")
        client.request(
            "POST",
            "https://member.bilibili.com/x2/creative/web/season/section/episode/del",
            data={"id": episode_id, "csrf": client.csrf},
        )
        source_after = by_aid(episodes(client, source_section_id))
        target_after = by_aid(episodes(client, target_section_id))
        if aid in source_after or aid not in target_after:
            raise RuntimeError(f"aid {aid}: final section verification failed")
        moved.append(aid)

    source_final = by_aid(episodes(client, source_section_id))
    target_final = by_aid(episodes(client, target_section_id))
    return {
        "requested": len(requested),
        "moved": moved,
        "already_moved": already_moved,
        "source_remaining": len(source_final),
        "target_total": len(target_final),
        "verified": all(aid not in source_final and aid in target_final for aid in requested),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Move owned Bilibili videos between creator-center season sections"
    )
    parser.add_argument("--cookies", type=Path, required=True)
    parser.add_argument("--source-section-id", type=int, required=True)
    parser.add_argument("--target-section-id", type=int, required=True)
    parser.add_argument("--aid", type=int, action="append", default=[])
    args = parser.parse_args()
    result = move(
        args.cookies,
        args.source_section_id,
        args.target_section_id,
        args.aid,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
