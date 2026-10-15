import json

import pytest

from scripts.check_publish_preflight import main


@pytest.mark.parametrize('header', ['id,title,video_url', 'video_id,title,url'])
@pytest.mark.parametrize('status', ['submitting', 'uploading'])
def test_preflight_blocks_uncertain_record_in_either_manifest_schema(tmp_path, capsys, header, status):
    manifest = tmp_path / 'videos.csv'
    manifest.write_text(header + '\nv1,Original title,https://example.com/1\n', encoding='utf-8-sig')
    state = tmp_path / 'publish-state.json'
    content = json.dumps({'videos': {'v1': {'status': status, 'title': 'Original title'}}})
    state.write_text(content, encoding='utf-8')

    with pytest.raises(SystemExit, match='上传结果不确定'):
        main(['--state', str(state), '--videos', str(manifest)])

    report = json.loads(capsys.readouterr().out)
    assert report['blocked'][0]['id'] == 'v1'
    assert report['blocked'][0]['status'] == status
    assert state.read_text(encoding='utf-8') == content


def test_preflight_does_not_block_skipped_record_or_another_collection(tmp_path, capsys):
    manifest = tmp_path / 'videos.csv'
    manifest.write_text('video_id,url,title\nv1,https://example.com/1,Skipped\n', encoding='utf-8')
    state = tmp_path / 'publish-state.json'
    state.write_text(json.dumps({'videos': {
        'v1': {'status': 'skipped'}, 'other': {'status': 'submitting'},
    }}), encoding='utf-8')

    main(['--state', str(state), '--videos', str(manifest)])

    assert '1 条清单记录' in capsys.readouterr().out


def test_preflight_rejects_missing_id_column_instead_of_silently_passing(tmp_path):
    manifest = tmp_path / 'videos.csv'
    manifest.write_text('url,title\nhttps://example.com/1,Missing ID\n', encoding='utf-8')
    with pytest.raises(SystemExit, match='缺少 id 或 video_id'):
        main(['--state', str(tmp_path / 'state.json'), '--videos', str(manifest)])
