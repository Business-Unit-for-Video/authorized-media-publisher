# Adult Performer Image Inventory

This repository only scans approved public image sources and writes an auditable image-link inventory. It does not process videos, download media binaries, publish to Bilibili, or infer permission from a public URL.

## Inputs and output

- `config/image-searches.txt`: one performer or search query per line.
- `output/images.csv`: tabular image links and metadata.
- `output/images.jsonl`: machine-readable records.
- `output/licensed-image-urls.txt`: convenience list for records with license metadata.
- `output/manifest.json`: counts, source failures, and scope notes.

The scanner defaults to Wikimedia Commons because it exposes source and license metadata through an API. It does not crawl adult sites, bypass access controls, or use anti-bot evasion.

```bash
python -m pip install -e '.[test]'
media-image-inventory --queries config/image-searches.txt --limit 20 --output output
pytest -q
```

Each record preserves the source page, original image URL, thumbnail URL, dimensions, creator/credit fields, license metadata, query, source, and collection time. `license-metadata-present` only means that license metadata was returned by the source. It is not approval to use a real person's likeness on Bilibili; identity, copyright, consent, publicity rights, platform terms, and attribution still require review.

## GitHub Actions

`.github/workflows/image-inventory.yml` is the only workflow. It runs weekly or by manual dispatch, uploads `output/` as an Artifact, and commits refreshed inventory data to `main` when it changes. HTTP 403/429 failures are recorded in `output/manifest.json`; if all queries fail, the workflow exits non-zero instead of claiming a successful empty library.
