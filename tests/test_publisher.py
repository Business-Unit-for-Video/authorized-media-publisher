import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from media_publisher.cli import (
    build,
    download,
    download_image,
    download_video,
    read_image_manifest,
    read_manifest,
    read_video_manifest,
    run_ffmpeg,
    select_images,
    select_video_batch,
    validate_image,
    validate_rows,
)
from media_publisher.publish import SeasonClient, publish
from media_publisher.serial import serial_publish


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


def test_workflow_is_public_only() -> None:
    workflow = (Path(__file__).parents[1] / ".github/workflows/publish.yml").read_text(
        encoding="utf-8"
    )
    assert "          - build\n" not in workflow
    assert "  build:\n" not in workflow
    assert "  publish:\n" in workflow
    assert "publish_mode:" not in workflow
    assert "--visibility public" in workflow


def test_publish_rejects_non_public_visibility(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="public-only"):
        publish(
            tmp_path / "missing-report.json",
            tmp_path / "cookies.json",
            "private",
            171,
            "tag",
            tmp_path / "state.json",
            "season",
            "",
        )


def test_manifest_allows_empty_rights_metadata(tmp_path: Path) -> None:
    path = write(
        tmp_path / "videos.csv",
        "id,title,video_url,rights_basis,publish_scope\na,t,https://x.test/a.mp4,,\n",
    )
    rows = read_manifest(path, ("id", "title", "video_url", "rights_basis", "publish_scope"))
    validate_rows(rows, "video")


def test_youtube_inventory_schema_is_normalized(tmp_path: Path) -> None:
    path = write(
        tmp_path / "videos.csv",
        "video_id,url,title,channel,channel_id,duration,upload_date,availability,live_status,view_count,matched_queries,discovered_at\n"
        "abc,https://www.youtube.com/watch?v=abc,Song,Artist,c,212,20200101,public,not_live,1,q,now\n",
    )
    assert read_video_manifest(path, "licensed", "public") == [{
        "id": "abc", "title": "Song",
        "video_url": "https://www.youtube.com/watch?v=abc",
        "rights_basis": "licensed", "publish_scope": "public",
    }]


def test_youtube_download_uses_yt_dlp(tmp_path: Path) -> None:
    cookies = tmp_path / "youtube-cookies.txt"
    cookies.write_text("cookie", encoding="utf-8")
    with patch("subprocess.run") as run:
        result = run.return_value
        result.stdout = str(tmp_path / "video.source.mp4") + "\n"
        (tmp_path / "video.source.mp4").write_bytes(b"video")
        actual = download_video(
            "https://www.youtube.com/watch?v=abc", tmp_path / "video.source", cookies
        )
    command = run.call_args.args[0]
    assert actual.name == "video.source.mp4"
    assert command[1:3] == ["-m", "yt_dlp"]
    assert "--no-playlist" in command
    assert command[command.index("--js-runtimes") + 1] == "node"
    assert command[command.index("--remote-components") + 1] == "ejs:github"
    assert command[command.index("--cookies") + 1] == str(cookies)


def test_inventory_image_schema_is_normalized(tmp_path: Path) -> None:
    path = write(
        tmp_path / "images.csv",
        "id,person_query,title,source_page_url,image_url,thumbnail_url,mime,width,height,license_short_name,license_url,artist,credit,usage_terms,source,rights_status,collected_at\n"
        "i1,q,t,https://x.test/page,https://x.test/i.jpg,https://x.test/t.jpg,image/jpeg,100,100,UNKNOWN,,,,,Bing Images,review-required,now\n",
    )
    rows = read_image_manifest(path, "licensed", "public")
    assert rows[0]["image_url"] == "https://x.test/i.jpg"
    assert rows[0]["thumbnail_url"] == "https://x.test/t.jpg"
    assert rows[0]["attribution"] == "https://x.test/page"


def test_image_validation_decodes_a_frame(tmp_path: Path) -> None:
    path = tmp_path / "image"
    path.write_bytes(b"not an image")
    with pytest.raises(ValueError, match="not a valid image"):
        validate_image(path)


def test_download_percent_encodes_non_ascii_url_path(tmp_path: Path) -> None:
    response = MagicMock()
    response.__enter__.return_value.read.side_effect = [b"image", b""]
    with patch("media_publisher.cli.urlopen", return_value=response) as mocked:
        download("https://laoshi.ink/assets/img/celebrities/jav/いち花.jpg", tmp_path / "image")
    assert "%E3%81%84%E3%81%A1%E8%8A%B1.jpg" in mocked.call_args.args[0].full_url
    assert (tmp_path / "image").read_bytes() == b"image"


def test_image_download_retries_then_uses_thumbnail(tmp_path: Path) -> None:
    row = {
        "id": "i1",
        "image_url": "https://x.test/full.jpg",
        "thumbnail_url": "https://x.test/thumb.jpg",
    }
    attempts: list[str] = []

    def fake_download(url: str, target: Path) -> None:
        attempts.append(url)
        target.write_bytes(b"response")

    def fake_validate(path: Path) -> None:
        if len(attempts) < 3:
            raise ValueError("invalid image")

    with patch("media_publisher.cli.download", side_effect=fake_download), patch(
        "media_publisher.cli.validate_image", side_effect=fake_validate
    ):
        actual = download_image(row, tmp_path / "image")
    assert actual == row["thumbnail_url"]
    assert attempts == [row["image_url"], row["image_url"], row["thumbnail_url"]]


def test_ffmpeg_overlays_transparent_image_over_video(tmp_path: Path) -> None:
    with patch("media_publisher.cli.subprocess.run") as run:
        run_ffmpeg(tmp_path / "video.mp4", tmp_path / "image.jpg", tmp_path / "output.mp4", 1920, 1080)
    command = run.call_args.args[0]
    filtergraph = command[command.index("-filter_complex") + 1]
    assert "[0:v]" in filtergraph
    assert "[base][watermark]overlay=W-w-32:32" in filtergraph
    assert "colorchannelmixer=aa=0.35" in filtergraph
    assert command[command.index("-map") + 1] == "[composite]"
    assert "0:a?" in command


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
    state["videos"] = {"v1": {"status": "published"}, "v2": {"status": "reserved"}}
    assert [row["id"] for row in select_video_batch(videos, state, 2)] == ["v2", "v3"]
    with pytest.raises(ValueError, match="positive"):
        select_video_batch(videos, state, 0)


def build_manifests(tmp_path: Path) -> tuple[Path, Path]:
    videos = write(
        tmp_path / "videos.csv",
        "id,title,video_url,rights_basis,publish_scope\n"
        "v1,one,https://x.test/1.mp4,owned,public\n"
        "v2,two,https://x.test/2.mp4,licensed,public\n",
    )
    images = write(
        tmp_path / "images.csv",
        "id,image_url,rights_basis,publish_scope,attribution\n"
        "i1,https://x.test/1.jpg,licensed,public,Artist\n"
        "i2,https://x.test/2.jpg,licensed,public,Artist\n",
    )
    return videos, images


def test_build_limits_batch_and_does_not_advance_state(tmp_path: Path) -> None:
    videos, images = build_manifests(tmp_path)
    output = tmp_path / "output" / "videos"
    state = tmp_path / "state" / "publish-state.json"
    with patch("media_publisher.cli.download_video"), patch(
        "media_publisher.cli.download_image", side_effect=lambda row, path: row["image_url"]
    ), patch(
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
    with patch("media_publisher.cli.download_video"), patch(
        "media_publisher.cli.download_image", side_effect=lambda row, path: row["image_url"]
    ), patch(
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


def test_season_attach_accepts_null_episode_lists() -> None:
    client = object.__new__(SeasonClient)
    responses = iter([
        {"episodes": None},
        {"ep_audits": {"123": {"code": 0, "cid": 456}}},
        None,
        {"episodes": [{"aid": 123}]},
    ])
    requests: list[tuple[str, str]] = []

    def request(method: str, url: str, **kwargs):
        requests.append((method, url))
        return next(responses)

    client.request = request
    client.csrf = "csrf"
    client.attach(123, "title", 20)
    assert len(requests) == 4


def report_file(tmp_path: Path) -> Path:
    return write(tmp_path / "report.json", json.dumps([{
        "video_id": "v1", "file": "output/a.mp4", "title": "Title",
        "video_source": "https://x.test/v", "image_source": "https://x.test/i",
        "image_id": "i1", "image_usage_cycle": "1", "attribution": "Photo: A",
    }]))


def test_serial_publish_builds_and_publishes_one_at_a_time(tmp_path: Path) -> None:
    events: list[tuple[str, int]] = []
    next_item = 0

    def builder(*args, **kwargs) -> int:
        nonlocal next_item
        assert kwargs["batch_size"] == 1
        next_item += 1
        output_dir = args[2]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{next_item}.mp4").write_bytes(b"video")
        (output_dir.parent / "build-report.json").write_text(
            json.dumps([{"video_id": f"v{next_item}"}]), encoding="utf-8"
        )
        events.append(("build", next_item))
        return 1

    def publisher(*args, **kwargs) -> int:
        report = json.loads(args[0].read_text(encoding="utf-8"))
        item = int(report[0]["video_id"][1:])
        events.append(("publish", item))
        return 1

    result = serial_publish(
        tmp_path / "videos.csv",
        tmp_path / "images.csv",
        tmp_path / "output" / "videos",
        1280,
        720,
        tmp_path / "state.json",
        3,
        None,
        tmp_path / "cookies.json",
        "public",
        171,
        "tag",
        "season",
        "",
        "run",
        builder=builder,
        publisher=publisher,
    )
    assert result == {"built": 3, "published": 3}
    assert events == [
        ("build", 1), ("publish", 1),
        ("build", 2), ("publish", 2),
        ("build", 3), ("publish", 3),
    ]


def test_serial_publish_stops_when_no_new_video(tmp_path: Path) -> None:
    builds = 0
    publishes = 0

    def builder(*args, **kwargs) -> int:
        nonlocal builds
        builds += 1
        output_dir = args[2]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir.parent / "build-report.json").write_text("[]", encoding="utf-8")
        return 0

    def publisher(*args, **kwargs) -> int:
        nonlocal publishes
        publishes += 1
        return 0

    result = serial_publish(
        tmp_path / "videos.csv", tmp_path / "images.csv",
        tmp_path / "output" / "videos", 1280, 720,
        tmp_path / "state.json", 10, None, tmp_path / "cookies.json",
        "public", 171, "tag", "season", "", "run",
        builder=builder, publisher=publisher,
    )
    assert result == {"built": 0, "published": 0}
    assert builds == 1
    assert publishes == 1


def test_serial_publish_stops_after_publish_failure(tmp_path: Path) -> None:
    events: list[str] = []

    def builder(*args, **kwargs) -> int:
        output_dir = args[2]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir.parent / "build-report.json").write_text("[]", encoding="utf-8")
        events.append("build")
        return 1

    def publisher(*args, **kwargs) -> int:
        events.append("publish")
        raise RuntimeError("upload failed")

    with pytest.raises(RuntimeError, match="upload failed"):
        serial_publish(
            tmp_path / "videos.csv", tmp_path / "images.csv",
            tmp_path / "output" / "videos", 1280, 720,
            tmp_path / "state.json", 10, None, tmp_path / "cookies.json",
            "public", 171, "tag", "season", "", "run",
            builder=builder, publisher=publisher,
        )
    assert events == ["build", "publish"]


def test_serial_publish_blocks_uncertain_upload_state(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = initial_state()
    state["videos"] = {"v1": {"status": "submitting"}}
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(RuntimeError, match="outcome is uncertain"):
        serial_publish(
            tmp_path / "videos.csv", tmp_path / "images.csv",
            tmp_path / "output" / "videos", 1280, 720,
            state_path, 10, None, tmp_path / "cookies.json",
            "public", 171, "tag", "season", "", "run",
        )


def test_serial_publish_finishes_one_pending_attachment_before_build(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state = initial_state()
    state["videos"] = {"v1": {"status": "uploaded", "aid": 1, "title": "one"}}
    state_path.write_text(json.dumps(state), encoding="utf-8")
    events: list[str] = []

    def publisher(*args, **kwargs) -> int:
        assert kwargs["max_items"] == 1
        events.append("publish")
        return 1

    def builder(*args, **kwargs) -> int:
        events.append("build")
        return 1

    result = serial_publish(
        tmp_path / "videos.csv", tmp_path / "images.csv",
        tmp_path / "output" / "videos", 1280, 720,
        state_path, 1, None, tmp_path / "cookies.json",
        "public", 171, "tag", "season", "", "run",
        builder=builder, publisher=publisher,
    )
    assert result == {"built": 0, "published": 1}
    assert events == ["publish"]


def test_publish_persists_reservation_upload_and_season(tmp_path: Path) -> None:
    state = tmp_path / "state" / "publish-state.json"
    commits: list[str] = []
    season = FakeSeason()
    count = publish(
        report_file(tmp_path), tmp_path / "cookies.json", "public", 171, "tag",
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
    assert len(commits) == 4


def test_publish_max_items_limits_multi_record_report(tmp_path: Path) -> None:
    state = tmp_path / "state" / "publish-state.json"
    report = write(tmp_path / "report.json", json.dumps([
        {
            "video_id": "v1", "title": "one", "video_source": "https://example.com/1",
            "image_id": "i1", "image_source": "https://example.com/i1",
            "image_usage_cycle": 0, "output": str(tmp_path / "1.mp4"),
        },
        {
            "video_id": "v2", "title": "two", "video_source": "https://example.com/2",
            "image_id": "i2", "image_source": "https://example.com/i2",
            "image_usage_cycle": 0, "output": str(tmp_path / "2.mp4"),
        },
    ]))
    (tmp_path / "1.mp4").write_bytes(b"video")
    (tmp_path / "2.mp4").write_bytes(b"video")
    uploaded: list[str] = []

    class FakeSeason:
        def __init__(self, _: Path):
            pass

        def resolve_or_create(self, title: str, description: str) -> tuple[int, int]:
            return 10, 20

        def attach(self, aid: int, title: str, section_id: int) -> None:
            pass

    count = publish(
        report, tmp_path / "cookies.json", "public", 171, "tag", state,
        "season", "description", max_items=1,
        persist=lambda *_: None,
        uploader=lambda record, *_: uploaded.append(record["video_id"]) or {"aid": 1, "bvid": "BV1"},
        season_factory=FakeSeason,
    )
    assert count == 1
    assert uploaded == ["v1"]
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert set(saved["videos"]) == {"v1"}


def test_uploaded_video_retries_only_season_attachment(tmp_path: Path) -> None:
    state = tmp_path / "state" / "publish-state.json"
    uploader_calls = 0

    def uploader(*args):
        nonlocal uploader_calls
        uploader_calls += 1
        return {"aid": 123, "bvid": "BV1"}

    with pytest.raises(RuntimeError, match="season failed"):
        publish(
            report_file(tmp_path), tmp_path / "cookies.json", "public", 171, "tag",
            state, "合集", "", persist=lambda *args: None, uploader=uploader,
            season_factory=lambda path: FakeSeason(fail_attach=True),
        )
    assert json.loads(state.read_text())["videos"]["v1"]["status"] == "uploaded"
    empty = write(tmp_path / "empty.json", "[]")
    season = FakeSeason()
    assert publish(
        empty, tmp_path / "cookies.json", "public", 171, "tag", state, "合集", "",
        persist=lambda *args: None, uploader=uploader, season_factory=lambda path: season,
    ) == 1
    assert uploader_calls == 1
    assert season.attached == [123]
