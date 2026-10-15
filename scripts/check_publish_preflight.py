"""Check uncertain submissions before installing third-party dependencies."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--videos', type=Path, required=True)
    args = parser.parse_args(argv)
    state = json.loads(args.state.read_text(encoding='utf-8')) if args.state.exists() else {'videos': {}}
    with args.videos.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        # Both accepted manifest formats must participate in the early guard.
        if 'id' in fields:
            id_field = 'id'
        elif 'video_id' in fields:
            id_field = 'video_id'
        else:
            raise SystemExit('发布前检查失败：清单缺少 id 或 video_id 列')
        ids = {(row.get(id_field) or '').strip() for row in reader}
    ids.discard('')
    blocked = []
    for video_id in sorted(ids):
        entry = (state.get('videos') or {}).get(video_id) or {}
        if entry.get('status') in {'submitting', 'uploading'}:
            blocked.append({
                'id': video_id,
                'status': entry.get('status'),
                'title': entry.get('title', ''),
                'workflow_run_id': entry.get('workflow_run_id', ''),
            })
    if blocked:
        print(json.dumps({'blocked': blocked}, ensure_ascii=False, indent=2))
        raise SystemExit('发布前检查失败：清单包含上传结果不确定的记录，请先核对 Bilibili 后再继续')
    print(f'发布前检查通过：{len(ids)} 条清单记录没有 submitting/uploading 阻塞状态')


if __name__ == '__main__':
    main()
