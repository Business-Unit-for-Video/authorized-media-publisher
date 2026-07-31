from pathlib import Path
from unittest.mock import patch

import pytest

from media_publisher.cli import build, read_manifest, validate_rows
from media_publisher.publish import publish


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_manifest_requires_rights_basis(tmp_path: Path) -> None:
    path = write(
        tmp_path / "videos.csv",
        "id,title,video_url,rights_basis,publish_scope\na,t,https://x.test/a.mp4,,public\n",
    )
    rows = read_manifest(path, ("id", "title", "video_url", "rights_basis", "publish_scope"))
    with pytest.raises(ValueError, match="rights_basis"):
        validate_rows(rows, "video")


def test_build_rotates_images_and_writes_report(tmp_path: Path) -> None:
    videos = write(
        tmp_path / "videos.csv",
        "id,title,video_url,rights_basis,publish_scope\n"
        "v1,one,https://x.test/1.mp4,owned,public\n"
        "v2,two,https://x.test/2.mp4,licensed,public\n",
    )
    images = write(
        tmp_path / "images.csv",
        "id,image_url,rights_basis,publish_scope,attribution\n"
        "i1,https://x.test/1.jpg,licensed,public,Artist\n",
    )
    output = tmp_path / "output" / "videos"
    with patch("media_publisher.cli.download") as downloader, patch("media_publisher.cli.run_ffmpeg") as ffmpeg:
        assert build(videos, images, output, 1280, 720) == 2
    assert downloader.call_count == 4
    assert ffmpeg.call_count == 2
    report = (tmp_path / "output" / "build-report.json").read_text(encoding="utf-8")
    assert '"image_rights_basis": "licensed"' in report
    assert '"video_rights_basis": "owned"' in report


def test_private_publish_uses_reprint_source_and_private_flag(tmp_path: Path) -> None:
    report = write(
        tmp_path / "report.json",
        '[{"file":"output/a.mp4","title":"Title","video_source":"https://x.test/v",'
        '"image_source":"https://x.test/i","attribution":"Photo: A"}]',
    )
    with patch("subprocess.run") as run:
        assert publish(report, tmp_path / "cookies.json", "private", 171, "授权素材") == 1
    command = run.call_args.args[0]
    assert command[:4] == ["biliup", "-u", str(tmp_path / "cookies.json"), "upload"]
    assert command[command.index("--copyright") + 1] == "2"
    assert command[command.index("--source") + 1] == "https://x.test/v"
    assert command[command.index("--is-only-self") + 1] == "1"
