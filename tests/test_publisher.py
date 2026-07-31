import json
from pathlib import Path
from unittest.mock import patch

import pytest

from media_publisher.cli import (
    build,
    download_video,
    read_image_manifest,
    read_manifest,
    read_video_manifest,
    select_images,
    select_video_batch,
    validate_rows,
)
from media_publisher.publish import publish


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def initial_state() -> dict[str, object]:
    return {
        "version": 1,
        "images": {"cycle": 1, "used_image_ids": []},
        "videos": {},
        "season": {},
    }


def test_manifest_requires_rights_basis(tmp_path: Path) -> None:
    path = write(
        tmp_path / "videos.csv",
        "id,title,video_url,rights_basis,publish_scope\na,t,https://x.test/a.mp4,,public\n",
    )
    rows = read_manifest(path, ("id", "title", "video_url", "rights_basis", "publish_scope"))
    with pytest.raises(ValueError, match="rights_basis"):
        validate_rows(rows, "video")


def test_youtube_inventory_schema_is_normalized(tmp_path: Path) -> None:
    path = write(
        tmp_path / "videos.csv",
        "video_id,url,title,channel,channel_id,duration,upload_date,availability,live_status,view_count,matched_queries,discovered_at\n"
        "abc,https://www.youtube.com/watch?v=abc,Song,Artist,c,212,20200101,public,not_live,1,q,now\n",
    )
    assert read_video_manifest(path, "licensed", "private") == [{
        "id": "abc", "title": "Song",
        "video_url": "https://www.youtube.com/watch?v=abc",
        "rights_basis": "licensed", "publish_scope": "private",
    }]


def test_youtube_download_uses_yt_dlp(tmp_path: Path) -> None:
    with patch("subprocess.run") as run:
        download_video("https://www.youtube.com/watch?v=abc", tmp_path / "video.source")
    command = run.call_args.args[0]
    assert command[1:3] == ["-m", "yt_dlp"]
    assert "--no-playlist" in command


def test_inventory_image_schema_is_normalized(tmp_path: Path) -> None:
    path = write(
        tmp_path / "images.csv",
        "id,person_query,title,source_page_url,image_url,thumbnail_url,mime,width,height,license_short_name,license_url,artist,credit,usage_terms,source,rights_status,collected_at\n"
        "i1,q,t,https://x.test/page,https://x.test/i.jpg,https://x.test/t.jpg,image/jpeg,100,100,UNKNOWN,,,,,Bing Images,review-required,now\n",
    )
    rows = read_image_manifest(path, "licensed", "private")
    assert rows[0]["image_url"] == "https://x.test/i.jpg"
    assert rows[0]["attribution"] == "https://x.test/page"


def test_image_rotation_resets_after_exhaustion() -> None:
    images = [{"id": "i1"}, {"id": "i2"}, {"id": "i3"}]
    first, state = select_images(images, 2, {"cycle": 1, "used_image_ids": []})
    second, state = select_images(images, 1, state)
    third, state = select_images(images, 1, state)
    assert [row["id"] for row in first + second + third] == ["i1", "i2", "i3", "i1"]
    assert state["cycle"] == 2


def test_batch_skips_reserved_and_published() -> None:
    videos = [{"id": "v1"}, {"id": "v2"}, {"id": "v3"}]
    state = initial_state()
    state["videos"] = {"v1": {"status": "published"}, "v2": {"status": "uploading"}}
    assert [row["id"] for row in select_video_batch(videos, state, 2)] == ["v2", "v3"]
    with pytest.raises(ValueError, match="positive"):
        select_video_batch(videos, state, 0)


def build_manifests(tmp_path: Path) -> tuple[Path, Path]:
    videos = write(
        tmp_path / "videos.csv",
        "id,title,video_url,rights_basis,publish_scope\n"
        "v1,one,https://x.test/1.mp4,owned,private\n"
        "v2,two,https://x.test/2.mp4,licensed,private\n",
    )
    images = write(
        tmp_path / "images.csv",
        "id,image_url,rights_basis,publish_scope,attribution\n"
        "i1,https://x.test/1.jpg,licensed,private,Artist\n"
        "i2,https://x.test/2.jpg,licensed,private,Artist\n",
    )
    return videos, images


def test_build_limits_batch_and_does_not_advance_state(tmp_path: Path) -> None:
    videos, images = build_manifests(tmp_path)
    output = tmp_path / "output" / "videos"
    state = tmp_path / "state" / "publish-state.json"
    with patch("media_publisher.cli.download_video"), patch("media_publisher.cli.download"), patch(
        "media_publisher.cli.run_ffmpeg"
    ):
        assert build(videos, images, output, 1280, 720, publish_state_path=state, batch_size=1) == 1
    assert not state.exists()
    report = json.loads((tmp_path / "output" / "build-report.json").read_text())
    assert report[0]["video_id"] == "v1"
    assert report[0]["image_id"] == "i1"


def test_failed_build_does_not_advance_state(tmp_path: Path) -> None:
    videos, images = build_manifests(tmp_path)
    state = tmp_path / "state" / "publish-state.json"
    with patch("media_publisher.cli.download_video"), patch("media_publisher.cli.download"), patch(
        "media_publisher.cli.run_ffmpeg", side_effect=RuntimeError("ffmpeg failed")
    ):
        with pytest.raises(RuntimeError, match="ffmpeg failed"):
            build(videos, images, tmp_path / "output" / "videos", 1280, 720, publish_state_path=state)
    assert not state.exists()


class FakeSeason:
    def __init__(self, fail_attach: bool = False):
        self.fail_attach = fail_attach
        self.attached: list[int] = []

    def resolve_or_create(self, title: str, description: str) -> tuple[int, int]:
        assert len(title) <= 20
        return 10, 20

    def attach(self, aid: int, title: str, section_id: int) -> None:
        if self.fail_attach:
            raise RuntimeError("season failed")
        self.attached.append(aid)


def report_file(tmp_path: Path) -> Path:
    return write(tmp_path / "report.json", json.dumps([{
        "video_id": "v1", "file": "output/a.mp4", "title": "Title",
        "video_source": "https://x.test/v", "image_source": "https://x.test/i",
        "image_id": "i1", "image_usage_cycle": "1", "attribution": "Photo: A",
    }]))


def test_publish_persists_reservation_upload_and_season(tmp_path: Path) -> None:
    state = tmp_path / "state" / "publish-state.json"
    commits: list[str] = []
    season = FakeSeason()
    count = publish(
        report_file(tmp_path), tmp_path / "cookies.json", "private", 171, "tag",
        state, "测试合集名称超过二十个字符时应截断", "desc", "run-1",
        persist=lambda path, message: commits.append(message),
        uploader=lambda *args: {"aid": 123, "bvid": "BV1"},
        season_factory=lambda path: season,
    )
    saved = json.loads(state.read_text())
    assert count == 1
    assert saved["videos"]["v1"]["status"] == "published"
    assert saved["videos"]["v1"]["aid"] == 123
    assert saved["images"]["used_image_ids"] == ["i1"]
    assert season.attached == [123]
    assert len(commits) == 3


def test_uploaded_video_retries_only_season_attachment(tmp_path: Path) -> None:
    state = tmp_path / "state" / "publish-state.json"
    uploader_calls = 0

    def uploader(*args):
        nonlocal uploader_calls
        uploader_calls += 1
        return {"aid": 123, "bvid": "BV1"}

    with pytest.raises(RuntimeError, match="season failed"):
        publish(
            report_file(tmp_path), tmp_path / "cookies.json", "private", 171, "tag",
            state, "合集", "", persist=lambda *args: None, uploader=uploader,
            season_factory=lambda path: FakeSeason(fail_attach=True),
        )
    assert json.loads(state.read_text())["videos"]["v1"]["status"] == "uploaded"
    empty = write(tmp_path / "empty.json", "[]")
    season = FakeSeason()
    assert publish(
        empty, tmp_path / "cookies.json", "private", 171, "tag", state, "合集", "",
        persist=lambda *args: None, uploader=uploader, season_factory=lambda path: season,
    ) == 1
    assert uploader_calls == 1
    assert season.attached == [123]
