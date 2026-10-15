"""Sync two public transcript catalogs into separate video-publishing queues."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, parse_qs

import requests

ROOT = Path(__file__).resolve().parents[1]
ORG = 'Business-Unit-for-Video'
CHANNELS = {'xiaodaodalang': '小岛大浪吹', 'betterleaf': 'Better Leaf 好葉'}
FIELDS = ('video_id', 'url', 'title', 'channel', 'duration', 'tab', 'availability',
          'transcript_status', 'plain_url', 'timestamps_url')


def validate_catalog(handle: str, document: dict) -> list[dict]:
    if document.get('destination') != handle or document.get('channel_url') != f'https://www.youtube.com/@{handle}':
        raise ValueError(f'{handle}: 目录频道不匹配，原清单未替换')
    items = document.get('items')
    if not isinstance(items, list) or not items:
        raise ValueError(f'{handle}: 目录为空或格式错误，原清单未替换')
    rows, seen = [], set()
    for item in items:
        vid = item.get('id', '')
        title = item.get('title', '')
        url = item.get('url', '')
        parts = urlsplit(url)
        if (not re.fullmatch(r'[A-Za-z0-9_-]{11}', vid) or vid in seen or not title.strip()
                or parts.scheme != 'https' or parts.netloc != 'www.youtube.com'
                or parts.path != '/watch' or parse_qs(parts.query).get('v') != [vid]):
            raise ValueError(f'{handle}: 视频标识、标题或来源地址不合法')
        seen.add(vid)
        if item.get('availability') not in (None, '', 'public'):
            continue
        if item.get('live_status') in ('is_live', 'is_upcoming', 'post_live'):
            continue
        links = {}
        for key in ('plain_url', 'timestamps_url'):
            link = item.get(key) or ''
            if link and not link.startswith(f'https://github.com/{ORG}/{handle}-video2text/blob/main/youtube_channels/{handle}/'):
                raise ValueError(f'{handle}: 转写链接不属于预期仓库')
            links[key] = link
        rows.append({'video_id': vid, 'url': url, 'title': title, 'channel': CHANNELS[handle],
                     'duration': item.get('duration') if item.get('duration') is not None else '',
                     'tab': item.get('tab') or '', 'availability': item.get('availability') or '',
                     'transcript_status': item.get('transcript_status') or 'pending', **links})
    if not rows:
        raise ValueError(f'{handle}: 没有公开候选视频，原清单未替换')
    return rows


def merge_order(path: Path, rows: list[dict]) -> list[dict]:
    """Keep established queue order; append newly discovered IDs once."""
    by_id = {row['video_id']: row for row in rows}
    ordered = []
    if path.exists():
        with path.open(encoding='utf-8-sig', newline='') as stream:
            old = list(csv.DictReader(stream))
        for row in old:
            if row.get('video_id') in by_id:
                ordered.append(by_id.pop(row['video_id']))
    ordered.extend(by_id.values())
    return ordered


def build_csv(rows):
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def sync(handles: list[str], catalog_root: Path | None = None):
    pending = {}
    for handle in handles:
        if catalog_root:
            document = json.loads((catalog_root / f'{handle}-video2text/docs/video-catalog.json').read_text(encoding='utf-8'))
        else:
            response = requests.get(
                f'https://raw.githubusercontent.com/{ORG}/{handle}-video2text/main/docs/video-catalog.json', timeout=60)
            response.raise_for_status()
            document = response.json()
        path = ROOT / 'input' / f'{handle}.csv'
        pending[handle] = (path, merge_order(path, validate_catalog(handle, document)))
    # Validate both sources before replacing any queue. Publish state is never modified.
    for handle, (path, rows) in pending.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.csv.tmp')
        temporary.write_text(build_csv(rows), encoding='utf-8')
        temporary.replace(path)
        print(f'{CHANNELS[handle]}: {len(rows)} 条清单记录', flush=True)
    lines = ['# 频道视频与转写文档目录', '',
             '视频标题、来源和转写进度来自两个公开转写仓库。CSV 是原视频发布队列，转写文本不作为视频素材。', '',
             '| 频道 | 视频发布清单 | 转写文档目录 |', '|---|---|---|']
    for handle, name in CHANNELS.items():
        lines.append(f'| {name} | [CSV](../input/{handle}.csv) | [文档与进度](https://github.com/{ORG}/{handle}-video2text/blob/main/docs/video-index.md) |')
    lines += ['', 'GitHub Actions 中手动运行 **同步 YouTube 频道发布清单** 可刷新。每天也会自动同步一次；同步不会投稿。',
              '已存在的视频顺序保持不变，新发现的视频追加到末尾。暂时不再公开的视频会从候选清单移除，历史发布状态继续保留。',
              '文档链接仅在转写文件实际生成后填写。尚未转写的视频同样可以按原视频发布流程处理。',
              '', '发布方式见 [频道发布说明](youtube-channel-publishing.md)。', '']
    (ROOT / 'docs/channel-document-lists.md').write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channel', choices=CHANNELS, action='append')
    parser.add_argument('--catalog-root', type=Path, help='首次初始化时读取本地同级转写仓库')
    args = parser.parse_args()
    sync(args.channel or list(CHANNELS), args.catalog_root)
