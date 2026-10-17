import json
import sys

import pytest

from media_publisher import serial as serial_module
from media_publisher.cli import UnavailableVideoError, select_video_batch
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
    sys.argv += ['--batch-size', '2']
    def forbidden(*args, **kwargs):
        raise AssertionError('check-only must not publish or contact external systems')
    for name in ('git', 'serial_publish', 'check_recent'):
        monkeypatch.setattr(runner, name, forbidden)
    assert runner.main() == 0
    assert not (tmp_path / 'output').exists()


def allow_publish(monkeypatch):
    monkeypatch.setattr(runner, 'git', lambda *args: '' if args[0] == 'status' else 'main')
    monkeypatch.setattr(runner, 'check_recent', lambda *args: 0)


def test_publish_without_video_id_passes_batch_size_and_all_candidates(tmp_path, monkeypatch):
    environment(tmp_path, monkeypatch)
    (tmp_path / 'input/videos.csv').write_text(
        'video_id,url,title\n'
        'v1,https://example.com/1,First\n'
        'v2,https://example.com/2,Second\n'
        'v3,https://example.com/3,Third\n', encoding='utf-8',
    )
    sys.argv += ['--batch-size', '2', '--publish']
    allow_publish(monkeypatch)
    calls = []

    def publish(*args):
        calls.append(args)
        # Keep the full queue so an unavailable source can be skipped without
        # consuming one of the requested successful publications.
        records = runner.read_video_manifest(args[0])
        assert [row['id'] for row in records] == ['v1', 'v2', 'v3']
        assert args[6] == 2
        assert args[9] == 'public'
        assert args[12] == '周杰伦'
        return {'built': 2, 'published': 2}

    monkeypatch.setattr(runner, 'serial_publish', publish)
    assert runner.main() == 0
    assert len(calls) == 1


@pytest.mark.parametrize('collection,manifest,season,tags', [
    ('XiaoDaoDaLang', 'xiaodaodalang', '小岛大浪吹', '小岛大浪吹,知识,财经'),
    ('BetterLeaf', 'betterleaf', 'Better Leaf 好葉', 'Better Leaf,好葉,知识,学习'),
])
def test_channel_publish_uses_own_manifest_and_collection(tmp_path, monkeypatch, collection, manifest, season, tags):
    environment(tmp_path, monkeypatch)
    (tmp_path / f'input/{manifest}.csv').write_text(
        'video_id,url,title\n'
        f'{manifest}1,https://example.com/{manifest}1,First channel video\n'
        f'{manifest}2,https://example.com/{manifest}2,Second channel video\n',
        encoding='utf-8',
    )
    sys.argv += ['--collection', collection, '--batch-size', '2', '--publish']
    allow_publish(monkeypatch)
    reviews = []
    monkeypatch.setattr(runner, 'check_recent', lambda *args: reviews.append(args[2]) or 0)
    calls = []

    def publish(*args):
        calls.append(args)
        assert [row['id'] for row in runner.read_video_manifest(args[0])] == [f'{manifest}1', f'{manifest}2']
        assert args[5] == tmp_path / 'state/publish-state.json'
        assert args[6] == 2
        assert args[9:13] == ('public', 171, tags, season)
        return {'built': 2, 'published': 2}

    monkeypatch.setattr(runner, 'serial_publish', publish)
    assert runner.main() == 0
    assert len(calls) == 1
    assert reviews == [tmp_path / f'input/{manifest}.csv']


@pytest.mark.parametrize('arguments', [
    ['--batch-size', '0'],
    ['--batch-size', '-1'],
    ['--batch-size', 'invalid'],
    ['--video-id', 'v1', '--batch-size', '2'],
])
def test_invalid_batch_and_mixed_selection_are_rejected(tmp_path, monkeypatch, arguments):
    environment(tmp_path, monkeypatch)
    sys.argv += [*arguments, '--publish']
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2


def record(video_id, title=None, source=None):
    return {
        'id': video_id, 'title': title or video_id,
        'video_url': source or f'https://example.com/{video_id}',
        'rights_basis': '', 'publish_scope': '',
    }


def test_retryable_video_is_selected_for_republish():
    records = [record('retry')]
    state = {'videos': {'retry': {**records[0], 'status': 'retryable'}}}
    assert select_video_batch(records, state, 1) == records


def test_automatic_queue_prioritizes_pending_attachment_and_filters_duplicates():
    records = [
        record('first'),
        record('same-source', source='https://example.com/first'),
        record('published'),
        record('old-source', source='https://example.com/history'),
        record('old-title', title='周杰倫【牛仔很忙 官方完整MV】'),
        record('pending'),
        record('last'),
        record('skipped'),
    ]
    state = {'videos': {
        'published': {**records[2], 'status': 'published'},
        'history': {'video_url': 'https://example.com/history', 'status': 'published'},
        'cowboy': {'title': '周杰伦 牛仔很忙', 'status': 'published'},
        'pending': {**records[5], 'status': 'uploaded'},
        'skipped': {**records[7], 'status': 'skipped'},
    }}
    before = json.dumps(state, sort_keys=True)
    assert [row['id'] for row in runner.automatic_records(records, state)] == [
        'pending', 'first', 'last',
    ]
    assert json.dumps(state, sort_keys=True) == before


@pytest.mark.parametrize('status', ['submitting', 'uploading'])
def test_automatic_queue_blocks_uncertain_item_in_selected_manifest(status):
    records = [record('new'), record('uncertain')]
    state = {'videos': {'uncertain': {**records[1], 'status': status}}}
    with pytest.raises(runner.LocalCheckError, match='uncertain'):
        runner.automatic_records(records, state)


def test_automatic_queue_ignores_unrelated_uncertain_history():
    records = [record('new')]
    state = {'videos': {'other': {**record('other'), 'status': 'submitting'}}}
    assert runner.automatic_records(records, state) == records


def test_automatic_batch_skips_unavailable_and_stops_after_requested_successes(tmp_path, monkeypatch):
    environment(tmp_path, monkeypatch)
    (tmp_path / 'input/videos.csv').write_text(
        'video_id,url,title\n'
        'v1,https://example.com/1,First\n'
        'v2,https://example.com/2,Second\n'
        'v3,https://example.com/3,Third\n'
        'v4,https://example.com/4,Fourth\n', encoding='utf-8',
    )
    sys.argv += ['--batch-size', '2', '--publish']
    allow_publish(monkeypatch)
    monkeypatch.setattr(serial_module, 'git_commit_state', lambda *args: None)
    events = []

    def builder(*args, **kwargs):
        assert kwargs['batch_size'] == 1
        state = runner.load_publish_state(kwargs['publish_state_path'])
        selected = select_video_batch(runner.read_video_manifest(args[0]), state, 1)[0]
        events.append(('build', selected['id']))
        if selected['id'] == 'v1':
            raise UnavailableVideoError(selected['video_url'], 'Video unavailable')
        output = args[2]
        output.mkdir(parents=True, exist_ok=True)
        (output.parent / 'build-report.json').write_text(
            json.dumps([selected]), encoding='utf-8',
        )
        return 1

    def publisher(*args, **kwargs):
        assert kwargs['max_items'] == 1
        selected = json.loads(args[0].read_text(encoding='utf-8'))[0]
        events.append(('publish', selected['id']))
        state = runner.load_publish_state(args[5])
        state['videos'][selected['id']] = {**selected, 'status': 'published'}
        serial_module.save_state(args[5], state)
        return 1

    def serial_publish(*args):
        result = serial_module.serial_publish(*args, builder=builder, publisher=publisher)
        assert result == {'built': 2, 'published': 2}
        return result

    monkeypatch.setattr(runner, 'serial_publish', serial_publish)
    assert runner.main() == 0
    assert events == [
        ('build', 'v1'), ('build', 'v2'), ('publish', 'v2'),
        ('build', 'v3'), ('publish', 'v3'),
    ]
    saved = runner.load_publish_state(tmp_path / 'state/publish-state.json')
    assert saved['videos']['v1']['status'] == 'unavailable'
    assert 'v4' not in saved['videos']


def test_both_cookie_exports_are_preserved(tmp_path, monkeypatch):
    credentials = environment(tmp_path, monkeypatch)
    original = {p.name: p.read_bytes() for p in credentials.iterdir()}
    sys.argv += ['--video-id', 'v1', '--publish']
    allow_publish(monkeypatch)
    def publish(*args):
        assert args[6] == 1
        # Simulate both upstream tools saving their cookie jars.
        args[7].write_text('yt-dlp updated cookies')
        args[8].write_text('biliup updated cookies')
        return {'built': 1, 'published': 1}
    monkeypatch.setattr(runner, 'serial_publish', publish)
    assert runner.main() == 0
    assert original == {p.name: p.read_bytes() for p in credentials.iterdir()}
    assert not (tmp_path / 'output/windows-local/publisher.lock').exists()
