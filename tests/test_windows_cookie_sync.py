import json
from types import SimpleNamespace

import pytest

from scripts import sync_windows_cookies as sync


YOUTUBE = b'# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tdummy\n'
BILIBILI = json.dumps({'cookie_info': {'cookies': [
    {'name': 'SESSDATA', 'value': 'dummy-session'},
    {'name': 'bili_jct', 'value': 'dummy-csrf'},
]}}).encode()


@pytest.mark.parametrize('prefix', [b'', b'\xef\xbb\xbf'])
def test_sync_downloads_valid_exports_without_printing_values(tmp_path, monkeypatch, capsys, prefix):
    monkeypatch.setattr(sync.requests, 'get', lambda url, **kw: SimpleNamespace(
        status_code=200, content=prefix + (YOUTUBE if url.endswith('.md') else BILIBILI),
    ))
    sync.sync_exports(tmp_path, 'test-token')
    assert (tmp_path / 'youtube-cookies.txt').read_bytes() == YOUTUBE
    assert (tmp_path / 'bilibili-cookies.json').read_bytes() == BILIBILI
    assert 'dummy' not in capsys.readouterr().out


def test_bad_second_download_preserves_both_existing_files(tmp_path, monkeypatch):
    for name in sync.SOURCES:
        (tmp_path / name).write_bytes(b'existing-export')
    monkeypatch.setattr(sync.requests, 'get', lambda url, **kw: SimpleNamespace(
        status_code=200, content=YOUTUBE if url.endswith('.md') else b'{"message":"not a cookie export"}',
    ))
    with pytest.raises(ValueError, match='格式不正确'):
        sync.sync_exports(tmp_path, 'test-token')
    assert all((tmp_path / name).read_bytes() == b'existing-export' for name in sync.SOURCES)


def test_authority_token_is_reused_without_git_login(tmp_path, monkeypatch):
    monkeypatch.delenv('GH_TOKEN', raising=False)
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)
    authority = tmp_path / 'authority.md'
    authority.write_text('GITHUB_TOKEN=test-token\nUNRELATED=value\n', encoding='utf-8')
    monkeypatch.setattr(sync.subprocess, 'run', lambda *a, **k: pytest.fail('must not prompt for login'))
    assert sync.github_token(authority) == 'test-token'


def test_github_download_error_preserves_existing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(sync.requests, 'get', lambda *a, **kw: SimpleNamespace(status_code=404))
    with pytest.raises(ValueError, match='HTTP 404'):
        sync.sync_exports(tmp_path, 'test-token')
    assert list(tmp_path.iterdir()) == []
