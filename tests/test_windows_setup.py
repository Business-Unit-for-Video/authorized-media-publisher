from __future__ import annotations

import io
import json
from pathlib import Path
import tarfile

import pytest

from scripts import setup_windows as setup


def source_archive(*, omit: str = "", symlink: str = "", duplicate: str = "") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name in [*setup.SOURCE_FILES, "../../outside.py"]:
            if name == omit:
                continue
            info = tarfile.TarInfo(name)
            data = f"contents of {name}".encode()
            info.size = len(data)
            if name == symlink:
                info.type = tarfile.SYMTYPE
                info.linkname = "../../outside.py"
                info.size = 0
            archive.addfile(info, io.BytesIO(data))
            if name == duplicate:
                archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def test_archive_hash_is_checked_before_installing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        setup.install_archive(source_archive(), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_only_whitelisted_files_and_provenance_are_installed(tmp_path: Path) -> None:
    archive = source_archive()
    digest = setup.sha256(archive)
    assert setup.install_archive(archive, tmp_path, expected_sha256=digest)
    target = tmp_path / "biliup"
    actual = {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()}
    assert actual == {*setup.SOURCE_FILES.values(), setup.MARKER}
    assert not (tmp_path.parent / "outside.py").exists()
    metadata = json.loads((target / setup.MARKER).read_text())
    assert metadata["source_url"] == setup.SOURCE_URL
    assert metadata["source_sha256"] == digest
    assert metadata["version"] == "1.2.11"
    assert all(
        setup.sha256((target / relative).read_bytes()) == expected
        for relative, expected in metadata["files"].items()
    )


@pytest.mark.parametrize("fault", ["omit", "symlink", "duplicate"])
def test_invalid_required_members_are_rejected(tmp_path: Path, fault: str) -> None:
    archive = source_archive(**{fault: next(iter(setup.SOURCE_FILES))})
    with pytest.raises(ValueError):
        setup.install_archive(archive, tmp_path, expected_sha256=setup.sha256(archive))
    assert list(tmp_path.iterdir()) == []


def test_existing_unmarked_package_is_preserved(tmp_path: Path) -> None:
    target = tmp_path / "biliup"
    target.mkdir()
    (target / "__init__.py").write_text("original installation")
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        setup.install_archive(source_archive(), tmp_path)
    assert (target / "__init__.py").read_text() == "original installation"


def test_repeated_install_is_verified_and_unchanged(tmp_path: Path, monkeypatch) -> None:
    archive = source_archive()
    digest = setup.sha256(archive)
    monkeypatch.setattr(setup, "SOURCE_SHA256", digest)
    assert setup.install_archive(archive, tmp_path, expected_sha256=digest)
    target = tmp_path / "biliup"
    before = (target / setup.MARKER).stat().st_mtime_ns
    assert not setup.install_archive(archive, tmp_path, expected_sha256=digest)
    assert (target / setup.MARKER).stat().st_mtime_ns == before
    (target / "plugins" / "bili_webup.py").write_text("locally modified")
    with pytest.raises(RuntimeError, match="was modified"):
        setup.install_archive(archive, tmp_path, expected_sha256=digest)


def test_main_refuses_global_python(monkeypatch) -> None:
    monkeypatch.setattr(setup.sys, "argv", ["setup_windows.py"])
    monkeypatch.setattr(setup.sys, "prefix", setup.sys.base_prefix)
    with pytest.raises(SystemExit, match="global Python installation is forbidden"):
        setup.main()
