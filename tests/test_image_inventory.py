import csv
import json
from pathlib import Path

from media_publisher.image_inventory import clean, load_queries, write_outputs


def test_clean_strips_html_and_decodes_entities() -> None:
    assert clean({"value": "<b>Jane &amp; Studio</b>"}) == "Jane & Studio"


def test_load_queries_ignores_comments_and_blanks(tmp_path: Path) -> None:
    path = tmp_path / "queries.txt"
    path.write_text("# comment\n\nName One\nName Two\n", encoding="utf-8")
    assert load_queries(path) == ["Name One", "Name Two"]


def test_write_outputs_separates_review_required(tmp_path: Path) -> None:
    base = {
        "id": "1", "person_query": "Name", "title": "File:A.jpg",
        "source_page_url": "https://commons.test/A", "image_url": "https://img.test/A.jpg",
        "thumbnail_url": "https://img.test/A-thumb.jpg", "mime": "image/jpeg",
        "width": 100, "height": 200, "license_short_name": "CC BY-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/", "artist": "A",
        "credit": "A", "usage_terms": "CC BY-SA 4.0", "source": "Wikimedia Commons",
        "rights_status": "license-metadata-present", "collected_at": "now",
    }
    second = {**base, "id": "2", "image_url": "https://img.test/B.jpg", "rights_status": "review-required"}
    write_outputs([base, second], tmp_path)
    rows = list(csv.DictReader((tmp_path / "images.csv").open(encoding="utf-8")))
    assert len(rows) == 2
    assert (tmp_path / "licensed-image-urls.txt").read_text().splitlines() == ["https://img.test/A.jpg"]
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["license_metadata_present_count"] == 1
    assert manifest["review_required_count"] == 1
