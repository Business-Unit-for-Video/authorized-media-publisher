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
    manifest.write_text("id\nv1\n", encoding="utf-8")
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
