"""Install the verified pure-Python biliup web uploader into this virtualenv.

biliup's normal source installation also builds a Rust extension which this
project never imports. We preserve only the upstream Python web uploader and
its license, without executing the source archive's build scripts.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import sysconfig
import tarfile
import tempfile
import urllib.request


VERSION = "1.2.11"
SOURCE_URL = (
    "https://files.pythonhosted.org/packages/e9/92/"
    "d1c40c9aba014fd9ded6eb1819a78163159516866254ef3752ec47ed2ebf/"
    "biliup-1.2.11.tar.gz"
)
SOURCE_SHA256 = "c47f2857119cee848edc382467ef7791def7ffb43fe90bbe87d2d29ed795b767"
OWNER = "authorized-media-publisher/windows-webup-bootstrap/v1"
MARKER = "windows-webup-source.json"
SOURCE_FILES = {
    f"biliup-{VERSION}/biliup/__init__.py": "__init__.py",
    f"biliup-{VERSION}/biliup/plugins/__init__.py": "plugins/__init__.py",
    f"biliup-{VERSION}/biliup/plugins/bili_webup.py": "plugins/bili_webup.py",
    f"biliup-{VERSION}/LICENSE": "LICENSE",
}
MAX_DOWNLOAD = 20 * 1024 * 1024
MAX_SOURCE_FILE = 2 * 1024 * 1024


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_source_files(
    archive: bytes, expected_sha256: str = SOURCE_SHA256
) -> dict[str, bytes]:
    """Read exact, regular-file members; never extract archive paths to disk."""
    if sha256(archive) != expected_sha256:
        raise ValueError("biliup archive SHA256 mismatch; nothing was installed")
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as source:
        for member in source:
            relative = SOURCE_FILES.get(member.name)
            if relative is None:
                continue
            if relative in files or not member.isfile():
                raise ValueError(f"Unexpected duplicate or non-file member: {member.name}")
            if member.size > MAX_SOURCE_FILE:
                raise ValueError(f"Oversized source member: {member.name}")
            stream = source.extractfile(member)
            if stream is None:
                raise ValueError(f"Missing source bytes: {member.name}")
            files[relative] = stream.read(MAX_SOURCE_FILE + 1)
    missing = set(SOURCE_FILES.values()) - files.keys()
    if missing:
        raise ValueError(f"Required source files missing: {', '.join(sorted(missing))}")
    return files


def verified_existing_install(target: Path) -> bool:
    if not target.exists() and not target.is_symlink():
        return False
    if target.is_symlink() or not target.is_dir():
        raise RuntimeError(f"Refusing to replace existing biliup path: {target}")
    marker = target / MARKER
    try:
        metadata = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f"Existing biliup has no valid bootstrap marker; refusing to overwrite {target}"
        ) from exc
    if not isinstance(metadata, dict) or (
        metadata.get("owner") != OWNER
        or metadata.get("version") != VERSION
        or metadata.get("source_url") != SOURCE_URL
        or metadata.get("source_sha256") != SOURCE_SHA256
    ):
        raise RuntimeError(f"Unrecognized biliup bootstrap marker: {target}")
    hashes = metadata.get("files", {})
    if not isinstance(hashes, dict) or set(hashes) != set(SOURCE_FILES.values()):
        raise RuntimeError(f"Incomplete biliup bootstrap marker: {target}")
    for relative, expected in hashes.items():
        path = target / relative
        if path.is_symlink() or not path.is_file() or sha256(path.read_bytes()) != expected:
            raise RuntimeError(f"Existing biliup file was modified: {relative}")
    return True


def install_archive(
    archive: bytes,
    site_packages: Path,
    *,
    expected_sha256: str = SOURCE_SHA256,
) -> bool:
    """Install into a fresh package directory, or leave a verified install alone."""
    target = site_packages / "biliup"
    if verified_existing_install(target):
        return False
    files = read_source_files(archive, expected_sha256)
    metadata = {
        "owner": OWNER,
        "version": VERSION,
        "source_url": SOURCE_URL,
        "source_sha256": expected_sha256,
        "scope": "Pure-Python web uploader only; upstream Rust CLI is not installed",
        "files": {relative: sha256(data) for relative, data in files.items()},
    }
    site_packages.mkdir(parents=True, exist_ok=True)
    # The temporary directory is on the same filesystem for an atomic rename.
    with tempfile.TemporaryDirectory(prefix=".biliup-webup-", dir=site_packages) as stage:
        package = Path(stage) / "biliup"
        package.mkdir()
        for relative, data in files.items():
            destination = package / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        (package / MARKER).write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        package.rename(target)
    return True


def download_archive() -> bytes:
    request = urllib.request.Request(
        SOURCE_URL, headers={"User-Agent": "authorized-media-publisher/windows-setup"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        archive = response.read(MAX_DOWNLOAD + 1)
    if len(archive) > MAX_DOWNLOAD:
        raise ValueError("biliup source archive exceeded the download limit")
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    if sys.prefix == sys.base_prefix:
        raise SystemExit("Use the project virtualenv; global Python installation is forbidden")
    site_packages = Path(sysconfig.get_path("purelib")).resolve()
    try:
        site_packages.relative_to(Path(sys.prefix).resolve())
    except ValueError as exc:
        raise SystemExit("site-packages must be inside the active virtualenv") from exc
    if verified_existing_install(site_packages / "biliup"):
        print(f"Verified existing biliup {VERSION} pure-Python web uploader")
        return
    install_archive(download_archive(), site_packages)
    print(f"Installed verified biliup {VERSION} pure-Python web uploader")


if __name__ == "__main__":
    main()
