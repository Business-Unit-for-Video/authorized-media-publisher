"""Validate a YouTube Netscape cookie export without printing cookie values."""

from __future__ import annotations

import sys
import time
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_youtube_cookies.py PATH", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.exists() or path.stat().st_size == 0:
        print("YouTube cookie file is missing or empty", file=sys.stderr)
        return 1
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    first = next((line.strip().lower() for line in lines if line.strip()), "")
    if not (first.startswith("# netscape http cookie file") or first.startswith("# http cookie file")):
        print("YouTube cookie file is not a Netscape export", file=sys.stderr)
        return 1
    rows = []
    usable = []
    now = int(time.time())
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) < 7:
            continue
        rows.append(line)
        domain = fields[0].replace("#HttpOnly_", "", 1).lower()
        if "youtube.com" not in domain and "youtu.be" not in domain:
            continue
        try:
            expiry = int(float(fields[4] or "0"))
        except ValueError:
            expiry = -1
        if expiry == 0 or expiry > now:
            usable.append(line)
    if not rows or not usable:
        print("YouTube cookie file contains no usable YouTube cookie rows", file=sys.stderr)
        return 1
    print(f"YouTube cookie validated ({len(rows)} rows, {len(usable)} non-expired/session rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
