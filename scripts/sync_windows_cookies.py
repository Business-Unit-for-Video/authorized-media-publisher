"""Copy the user's two GitHub cookie exports to the local credential directory."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

import requests


ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'youtube-cookies.txt': 'private/youtube_cookies.md',
    'bilibili-cookies.json': 'private/cookies.json',
}


def github_token(authority: Path) -> str:
    for name in ('GH_TOKEN', 'GITHUB_TOKEN'):
        if os.environ.get(name, '').strip():
            return os.environ[name].strip()
    if authority.is_file():
        for line in authority.read_text(encoding='utf-8-sig').splitlines():
            key, separator, value = line.partition('=')
            if separator and key.strip() == 'GITHUB_TOKEN' and value.strip():
                return value.strip().strip('"\'')
    # Reuse configured Git credentials without opening another login prompt.
    result = subprocess.run(
        ['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
        capture_output=True, text=True, cwd=ROOT, timeout=30,
        env={**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never'},
    )
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            key, separator, value = line.partition('=')
            if separator and key == 'password' and value:
                return value
    raise ValueError('没有找到 GitHub 凭据；请使用已配置的 Git 凭据或 authority.md 中的 GITHUB_TOKEN')


def validate_export(name: str, content: bytes) -> None:
    try:
        text = content.decode('utf-8-sig')
        if name == 'youtube-cookies.txt':
            lines = text.splitlines()
            if not lines or not lines[0].lower().startswith(('# netscape http cookie file', '# http cookie file')):
                raise ValueError()
            if not any(len(line.split('\t')) >= 7 for line in lines if not line.startswith('#') or line.startswith('#HttpOnly_')):
                raise ValueError()
        else:
            document = json.loads(text)
            cookies = {item['name']: item['value'] for item in document['cookie_info']['cookies']}
            if not cookies.get('SESSDATA') or not cookies.get('bili_jct'):
                raise ValueError()
    except (UnicodeError, ValueError, KeyError, TypeError, AttributeError):
        raise ValueError(f'{name} 的远端内容格式不正确，本地文件未被替换') from None


def sync_exports(directory: Path, token: str) -> None:
    directory = directory.resolve()
    if directory.is_relative_to(ROOT):
        raise ValueError('Cookie 目录必须位于仓库外')
    exports = {}
    for name, source in SOURCES.items():
        response = requests.get(
            f'https://api.github.com/repos/PeterKZhao/myself/contents/{source}',
            headers={
                'Authorization': f'Bearer {token}',
                'Accept': 'application/vnd.github.raw+json',
                'X-GitHub-Api-Version': '2022-11-28',
            }, timeout=30,
        )
        if response.status_code != 200:
            raise ValueError(f'读取 {source} 失败（HTTP {response.status_code}），本地文件未被替换')
        validate_export(name, response.content)
        # biliup reads JSON as UTF-8, so strip an optional export BOM.
        exports[name] = response.content.decode('utf-8-sig').encode('utf-8')
    # Validate both downloads before changing either local export.
    for name in exports:
        if (directory / name).is_symlink():
            raise ValueError('目标 Cookie 文件是符号链接，请选择普通文件目录')
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in exports.items():
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, prefix='.cookie-', delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(content)
            temporary.replace(directory / name)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        print(f'已同步：{directory / name}', flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cookie-directory', type=Path, required=True)
    parser.add_argument('--authority-file', type=Path, default=ROOT.parent / 'authority.md')
    args = parser.parse_args()
    try:
        sync_exports(args.cookie_directory, github_token(args.authority_file))
    except ValueError as error:
        print(str(error), flush=True)
        return 2
    except Exception as error:
        print(f'Cookie 同步失败：{type(error).__name__}；未输出凭据或原始请求。', flush=True)
        return 1
    print('两份 Cookie 格式验证通过。同步本身不下载视频、不投稿。', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
