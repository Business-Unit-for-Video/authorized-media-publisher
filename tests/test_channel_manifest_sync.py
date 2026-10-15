import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('channel_sync', Path(__file__).parents[1] / 'scripts/sync_channel_manifests.py')
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


def catalog(*items):
    return {'destination': 'betterleaf', 'channel_url': 'https://www.youtube.com/@betterleaf', 'items': list(items)}


def video(vid='abcdefghijk', **extra):
    return {'id': vid, 'title': '真实视频名称', 'url': f'https://www.youtube.com/watch?v={vid}', **extra}


def test_catalog_rejects_wrong_channel_and_duplicate_ids():
    with pytest.raises(ValueError):
        sync.validate_catalog('xiaodaodalang', catalog(video()))
    with pytest.raises(ValueError):
        sync.validate_catalog('betterleaf', catalog(video(), video()))


def test_restricted_sources_are_excluded_and_text_links_stay_empty():
    rows = sync.validate_catalog('betterleaf', catalog(video(), video('12345678901', availability='subscriber_only')))
    assert len(rows) == 1 and rows[0]['title'] == '真实视频名称'
    assert rows[0]['plain_url'] == '' and rows[0]['transcript_status'] == 'pending'


def test_queue_order_is_stable_when_new_video_appears_first(tmp_path):
    path = tmp_path / 'channel.csv'
    original = sync.validate_catalog('betterleaf', catalog(video()))
    path.write_text(sync.build_csv(original), encoding='utf-8')
    latest = sync.validate_catalog('betterleaf', catalog(video('12345678901'), video()))
    assert [r['video_id'] for r in sync.merge_order(path, latest)] == ['abcdefghijk', '12345678901']


def test_bad_transcript_link_cannot_enter_publishing_catalog():
    with pytest.raises(ValueError):
        sync.validate_catalog('betterleaf', catalog(video(plain_url='https://example.com/unrelated')))
