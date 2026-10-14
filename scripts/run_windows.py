"""Check the native Windows environment, or explicitly publish one selected item."""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from media_publisher.cli import find_published_duplicate, load_publish_state, read_video_manifest
from media_publisher.publish import load_cookie_data
from media_publisher.serial import serial_publish
from scripts.check_recent_bilibili_reviews import check_recent


ROOT = Path(__file__).resolve().parents[1]
COLLECTIONS = {
    'JayChou': ('input/videos.csv', '周杰伦'),
    'YuGang': ('input/guodegang-early-successes.csv', '于纲'),
}


class LocalCheckError(RuntimeError):
    """A controlled diagnostic that contains no request URLs or credentials."""


def ineligible_reason(record: dict, state: dict) -> str:
    entry = state['videos'].get(record['id'], {})
    status = entry.get('status')
    if status not in (None, 'reserved', 'uploaded'):
        return f"状态为 {status}，请先核对稿件；不会自动重置历史记录"
    if entry and entry.get('video_url') != record['video_url']:
        return '同一 ID 的来源地址已变化'
    for other_id, other in state['videos'].items():
        if other_id != record['id'] and other.get('video_url') == record['video_url']:
            if other.get('status') in {'submitting', 'uploading', 'uploaded', 'published'}:
                return f"相同来源已有记录 {other_id} ({other['status']})"
    duplicate = find_published_duplicate(record, state)
    if duplicate:
        return f'同内容已发布：{duplicate}'
    return ''


def git(*arguments: str) -> str:
    result = subprocess.run(['git', *arguments], cwd=ROOT, check=True,
                            capture_output=True, text=True, encoding='utf-8')
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collection', choices=COLLECTIONS, default='JayChou')
    parser.add_argument('--video-id')
    parser.add_argument('--cookie-directory', type=Path, required=True)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if args.publish and not args.video_id:
        parser.error('正式发布必须指定 --video-id；每次只处理这一条')

    problems = []
    for executable in ('git', 'ffmpeg', 'ffprobe', 'node'):
        if not shutil.which(executable):
            problems.append(f'缺少程序：{executable}')
    for module in ('yt_dlp', 'aiohttp', 'rsa', 'biliup.plugins.bili_webup'):
        try:
            importlib.import_module(module)
        except ImportError:
            problems.append(f'缺少 Python 模块：{module}，请运行 setup-windows.ps1')
    cookie_directory = args.cookie_directory.resolve()
    if cookie_directory.is_relative_to(ROOT):
        problems.append('Cookie 目录必须放在仓库外')
    youtube_cookie = cookie_directory / 'youtube-cookies.txt'
    bilibili_cookie = cookie_directory / 'bilibili-cookies.json'
    if not youtube_cookie.is_file():
        problems.append(f'缺少 YouTube Cookie：{youtube_cookie}')
    else:
        first = youtube_cookie.read_text(encoding='utf-8-sig').splitlines()
        if not first or not first[0].lower().startswith(('# netscape http cookie file', '# http cookie file')):
            problems.append('YouTube Cookie 需要 Netscape 格式，不能是 GitHub 网页 HTML')
    if not bilibili_cookie.is_file():
        problems.append(f'缺少 Bilibili Cookie：{bilibili_cookie}')
    else:
        try:
            load_cookie_data(bilibili_cookie)
        except OSError:
            problems.append(f'无法读取 Bilibili Cookie，请检查文件权限：{bilibili_cookie}')
        except (ValueError, KeyError, TypeError, AttributeError):
            problems.append(f'Bilibili Cookie 格式不正确：{bilibili_cookie}')
    if problems:
        print('\n'.join(problems), flush=True)
        print('可在当前 PowerShell 重新同步后检查：', flush=True)
        print('powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\run-windows.ps1 -SyncCookies', flush=True)
        return 2

    if args.publish:
        if git('status', '--porcelain'):
            raise LocalCheckError('仓库有未提交改动，请先保存；投稿会提交并推送状态')
        if git('branch', '--show-current') != 'main':
            raise LocalCheckError('本地发布需要位于 main 分支')
        git('pull', '--ff-only', 'origin', 'main')
        # The publisher commits state, so check the identity before rendering.
        if not git('config', 'user.name') or not git('config', 'user.email'):
            raise LocalCheckError('请先设置 Git 提交身份')

    manifest_name, season_title = COLLECTIONS[args.collection]
    manifest = ROOT / manifest_name
    state_path = ROOT / 'state/publish-state.json'
    state = load_publish_state(state_path)
    records = read_video_manifest(manifest)
    selected = next((row for row in records if row['id'] == args.video_id), None)
    print(f'Windows 环境与 Cookie 文件格式检查通过；合集：{season_title}', flush=True)
    print('本检查尚未验证 Cookie 在线有效性或实际分片传输。', flush=True)
    if args.video_id:
        if selected is None:
            raise LocalCheckError('指定的视频 ID 不在该合集清单中')
        reason = ineligible_reason(selected, state)
        if reason:
            raise LocalCheckError(f"{selected['id']}: {reason}")
        print(f"选定：{selected['id']} | {selected['title']}", flush=True)
    else:
        candidates = [row for row in records if not ineligible_reason(row, state)]
        print('可选记录（前五条；正式发布前仍需检查账号）：', flush=True)
        for row in candidates[:5]:
            print(f"  {row['id']} | {row['title']}", flush=True)
    if not args.publish:
        print('检查结束，没有下载、转码或投稿。使用 -VideoId ID -Publish 才会公开发布。', flush=True)
        return 0

    output = ROOT / 'output/windows-local'
    output.mkdir(parents=True, exist_ok=True)
    # A second local process must not race this publisher's state or output.
    lock_path = output / 'publisher.lock'
    with lock_path.open('x', encoding='utf-8') as lock:
        lock.write(datetime.now(timezone.utc).isoformat())
    try:
        if check_recent(bilibili_cookie, state_path, manifest, output / 'recent-review-check.json', 2):
            raise LocalCheckError('最近稿件有审核退回记录，请先处理')
        single_manifest = output / 'selected-video.csv'
        with single_manifest.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(selected))
            writer.writeheader()
            writer.writerow(selected)
        # Both biliup and yt-dlp can rewrite cookie files. Preserve both exports.
        with tempfile.TemporaryDirectory(prefix='publisher-credentials-') as temporary:
            runtime_cookie = Path(temporary) / 'bilibili-cookies.json'
            runtime_youtube = Path(temporary) / 'youtube-cookies.txt'
            shutil.copyfile(bilibili_cookie, runtime_cookie)
            shutil.copyfile(youtube_cookie, runtime_youtube)
            result = serial_publish(
                single_manifest, ROOT / 'input/images.csv', output / 'videos',
                1920, 1080, state_path, 1, runtime_youtube, runtime_cookie,
                'public', 171, '授权素材,音乐', season_title, '',
                'windows-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
            )
        print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        lock_path.unlink()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except LocalCheckError as error:
        print(str(error), flush=True)
        raise SystemExit(2) from None
    except Exception as error:
        # requests exceptions can include Bilibili's csrf-bearing submit URL.
        print(f'本地运行停止：{type(error).__name__}。为保护 Cookie，不输出原始请求或堆栈。', flush=True)
        print('请结合已输出的阶段信息检查；若已开始投稿，先核对账号和 state/publish-state.json。', flush=True)
        raise SystemExit(1) from None
