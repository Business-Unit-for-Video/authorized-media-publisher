from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from scripts.check_recent_bilibili_reviews import check_recent, has_rejection_signal


def test_open_bilibili_archive_does_not_block_publishing() -> None:
    signals = [
        {"field": "archive.state", "value": 0},
        {"field": "archive.state_desc", "value": "开放浏览"},
        {"field": "archive.reject_reason", "value": ""},
        {"field": "archive.reject_reason_id", "value": 0},
        {"field": "archive.videos[0].reject_reason", "value": ""},
    ]

    assert not has_rejection_signal(signals)


def test_nonempty_bilibili_rejection_reason_blocks_publishing() -> None:
    assert has_rejection_signal([
        {"field": "archive.reject_reason", "value": "稿件涉嫌违规"},
    ])


def test_explicit_rejected_review_state_blocks_publishing() -> None:
    assert has_rejection_signal([
        {"field": "archive.state_desc", "value": "审核驳回"},
    ])


def test_rejection_reason_id_alone_does_not_block_publishing() -> None:
    assert not has_rejection_signal([
        {"field": "archive.reject_reason_id", "value": 1},
    ])


def test_recent_check_allows_an_open_archive(tmp_path: Path) -> None:
    manifest = tmp_path / "videos.csv"
    manifest.write_text(
        "id,title,video_url,rights_basis,publish_scope\n"
        "v1,one,https://x.test/v1.mp4,owned,public\n",
        encoding="utf-8",
    )
    state = tmp_path / "publish-state.json"
    state.write_text(json.dumps({
        "videos": {"v1": {"status": "published", "aid": 123}},
    }), encoding="utf-8")
    output = tmp_path / "recent-review-check.json"
    inspection = {
        "reports": [{
            "review_signals": [
                {"field": "archive.state", "value": 0},
                {"field": "archive.state_desc", "value": "开放浏览"},
                {"field": "archive.reject_reason", "value": ""},
                {"field": "archive.reject_reason_id", "value": 0},
            ],
        }],
    }

    with patch(
        "scripts.check_recent_bilibili_reviews.inspect_archive",
        return_value=inspection,
    ):
        assert check_recent(tmp_path / "cookies.json", state, manifest, output, 2) == 0

    assert json.loads(output.read_text(encoding="utf-8")) == {
        "checked": 1,
        "blocked": False,
        "reports": [{
            "video_id": "v1",
            "aid": 123,
            "rejected": False,
            "inspection": inspection,
        }],
    }


def test_recent_check_supports_youtube_inventory_schema(tmp_path: Path) -> None:
    manifest = tmp_path / "videos.csv"
    manifest.write_text(
        "video_id,url,title\n"
        "jay1,https://www.youtube.com/watch?v=jay1,Song\n",
        encoding="utf-8",
    )
    state = tmp_path / "publish-state.json"
    state.write_text(json.dumps({
        "videos": {"jay1": {"status": "published", "aid": 456}},
    }), encoding="utf-8")
    output = tmp_path / "recent-review-check.json"
    inspection = {"reports": [{"review_signals": []}]}

    with patch(
        "scripts.check_recent_bilibili_reviews.inspect_archive",
        return_value=inspection,
    ):
        assert check_recent(tmp_path / "cookies.json", state, manifest, output, 2) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["checked"] == 1
    assert report["reports"][0]["video_id"] == "jay1"


def test_skipped_archive_is_not_checked_or_blocking(tmp_path: Path) -> None:
    manifest = tmp_path / "videos.csv"
    manifest.write_text(
        "id,title,video_url,rights_basis,publish_scope\n"
        "v1,one,https://x.test/v1.mp4,owned,public\n",
        encoding="utf-8",
    )
    state = tmp_path / "publish-state.json"
    state.write_text(json.dumps({
        "videos": {
            "v1": {
                "status": "skipped",
                "aid": 123,
                "skip_reason": "稿件不可见，暂不重试",
            },
        },
    }), encoding="utf-8")
    output = tmp_path / "recent-review-check.json"

    with patch("scripts.check_recent_bilibili_reviews.inspect_archive") as inspect:
        assert check_recent(tmp_path / "cookies.json", state, manifest, output, 2) == 0

    inspect.assert_not_called()
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "checked": 0,
        "blocked": False,
        "reports": [],
    }
