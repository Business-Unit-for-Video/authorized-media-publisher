import json
import sys

import pytest

from scripts import run_windows as runner


@pytest.mark.parametrize('status', ['submitting', 'uploading', 'uploaded', 'published'])
def test_local_run_blocks_same_source_under_another_id(status):
    record = {'id': 'new', 'video_url': 'https://example.com/video', 'title': 'Example'}
    state = {'videos': {'old': {'video_url': record['video_url'], 'status': status}}}
    assert '相同来源' in runner.ineligible_reason(record, state)


def environment(tmp_path, monkeypatch):
    (tmp_path / 'input').mkdir()
    (tmp_path / 'state').mkdir()
    (tmp_path / 'input/videos.csv').write_text(
        'video_id,url,title\nv1,https://example.com/video,Example\n', encoding='utf-8'
    )
    (tmp_path / 'state/publish-state.json').write_text(json.dumps({
        'version': 1, 'images': {'cycle': 1, 'used_image_ids': []}, 'videos': {},
    }), encoding='utf-8')
    credentials = tmp_path.parent / (tmp_path.name + '-credentials')
    credentials.mkdir()
    (credentials / 'youtube-cookies.txt').write_text('# Netscape HTTP Cookie File\n', encoding='utf-8')
    (credentials / 'bilibili-cookies.json').write_text(json.dumps({'cookie_info': {'cookies': [
        {'name': 'SESSDATA', 'value': 'dummy'}, {'name': 'bili_jct', 'value': 'dummy'},
    ]}}), encoding='utf-8')
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    monkeypatch.setattr(runner.shutil, 'which', lambda _: 'present')
    monkeypatch.setattr(runner.importlib, 'import_module', lambda _: object())
    monkeypatch.setattr(sys, 'argv', ['run_windows', '--cookie-directory', str(credentials)])
    return credentials


def test_default_check_never_calls_git_network_or_publisher(tmp_path, monkeypatch):
    environment(tmp_path, monkeypatch)
    def forbidden(*args, **kwargs):
        raise AssertionError('check-only must not publish or contact external systems')
    for name in ('git', 'serial_publish', 'check_recent'):
        monkeypatch.setattr(runner, name, forbidden)
    assert runner.main() == 0
    assert not (tmp_path / 'output').exists()


def test_publish_requires_explicit_video_id(tmp_path, monkeypatch):
    environment(tmp_path, monkeypatch)
    sys.argv.append('--publish')
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2


def test_both_cookie_exports_are_preserved(tmp_path, monkeypatch):
    credentials = environment(tmp_path, monkeypatch)
    original = {p.name: p.read_bytes() for p in credentials.iterdir()}
    sys.argv += ['--video-id', 'v1', '--publish']
    monkeypatch.setattr(runner, 'git', lambda *args: '' if args[0] == 'status' else 'main')
    monkeypatch.setattr(runner, 'check_recent', lambda *args: 0)
    def publish(*args):
        # Simulate both upstream tools saving their cookie jars.
        args[7].write_text('yt-dlp updated cookies')
        args[8].write_text('biliup updated cookies')
        return {'built': 1, 'published': 1}
    monkeypatch.setattr(runner, 'serial_publish', publish)
    assert runner.main() == 0
    assert original == {p.name: p.read_bytes() for p in credentials.iterdir()}
    assert not (tmp_path / 'output/windows-local/publisher.lock').exists()
