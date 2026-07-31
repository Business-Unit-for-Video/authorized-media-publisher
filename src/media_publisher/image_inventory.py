from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import time
from urllib.error import HTTPError
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://commons.wikimedia.org/w/api.php"
FIELDS = (
    "id", "person_query", "title", "source_page_url", "image_url", "thumbnail_url",
    "mime", "width", "height", "license_short_name", "license_url", "artist",
    "credit", "usage_terms", "source", "rights_status", "collected_at",
)


def clean(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("value", "")
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))).strip()


def request_json(params: dict[str, object]) -> dict:
    url = f"{API}?{urlencode(params)}"
    for attempt in range(4):
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "authorized-media-inventory/0.1 (contact: repository-maintainer)",
            },
        )
        try:
            with urlopen(request) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in {403, 429} or attempt == 3:
                raise
            retry_after = error.headers.get("Retry-After")
            delay = int(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
            time.sleep(delay)
    raise RuntimeError("image source request exhausted retries")


def scan_query(query: str, limit: int) -> list[dict[str, object]]:
    payload = request_json({
        "action": "query", "generator": "search", "gsrsearch": query,
        "gsrnamespace": 6, "gsrlimit": limit, "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata", "iiurlwidth": 1280,
        "format": "json", "formatversion": 2,
    })
    records: list[dict[str, object]] = []
    now = datetime.now(timezone.utc).isoformat()
    for page in payload.get("query", {}).get("pages", []):
        info = (page.get("imageinfo") or [{}])[0]
        metadata = info.get("extmetadata") or {}
        image_url = info.get("url", "")
        if not image_url:
            continue
        license_name = clean(metadata.get("LicenseShortName"))
        usage_terms = clean(metadata.get("UsageTerms"))
        license_url = clean(metadata.get("LicenseUrl"))
        rights_status = "license-metadata-present" if license_name and (license_url or usage_terms) else "review-required"
        records.append({
            "id": hashlib.sha256(image_url.encode()).hexdigest()[:20],
            "person_query": query,
            "title": page.get("title", ""),
            "source_page_url": info.get("descriptionurl", ""),
            "image_url": image_url,
            "thumbnail_url": info.get("thumburl", ""),
            "mime": info.get("mime", ""),
            "width": info.get("width", ""),
            "height": info.get("height", ""),
            "license_short_name": license_name,
            "license_url": license_url,
            "artist": clean(metadata.get("Artist")),
            "credit": clean(metadata.get("Credit")),
            "usage_terms": usage_terms,
            "source": "Wikimedia Commons",
            "rights_status": rights_status,
            "collected_at": now,
        })
    return records


def load_queries(path: Path) -> list[str]:
    queries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            queries.append(line)
    if not queries:
        raise ValueError("query file is empty")
    return queries


def write_outputs(
    records: list[dict[str, object]],
    output: Path,
    failures: list[dict[str, str]] | None = None,
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    records = sorted(records, key=lambda row: (str(row["person_query"]), str(row["title"])))
    with (output / "images.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)
    with (output / "images.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    approved = [record for record in records if record["rights_status"] == "license-metadata-present"]
    with (output / "licensed-image-urls.txt").open("w", encoding="utf-8") as handle:
        for record in approved:
            handle.write(str(record["image_url"]) + "\n")
    manifest = {
        "record_count": len(records),
        "license_metadata_present_count": len(approved),
        "review_required_count": len(records) - len(approved),
        "scope_note": "Public search results with source metadata; identity, consent, and downstream reuse remain subject to review.",
        "failures": failures or [],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", type=Path, default=Path("config/image-searches.txt"))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("image-library"))
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 500:
        parser.error("--limit must be between 1 and 500")
    records: dict[str, dict[str, object]] = {}
    failures: list[dict[str, str]] = []
    for query in load_queries(args.queries):
        try:
            query_records = scan_query(query, args.limit)
        except HTTPError as error:
            failures.append({"query": query, "error": f"HTTP {error.code}: {error.reason}"})
            continue
        for record in query_records:
            existing = records.get(str(record["id"]))
            if existing:
                terms = set(str(existing["person_query"]).split(" | "))
                terms.add(query)
                existing["person_query"] = " | ".join(sorted(terms))
            else:
                records[str(record["id"])] = record
        time.sleep(1)
    write_outputs(list(records.values()), args.output, failures)
    print(json.dumps({"queries": len(load_queries(args.queries)), "records": len(records), "failures": len(failures)}, ensure_ascii=False))
    return 1 if failures and not records else 0


if __name__ == "__main__":
    raise SystemExit(main())
