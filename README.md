# Authorized Media Publisher

This repository contains only the processing and publishing logic. It does not search for, bundle, or endorse any third-party video or image source.

## Inputs

`input/videos.csv` is intentionally shaped like the one-link-per-song output from `youtube-music-video-search`, but this repository does not download that repository's URLs automatically. Replace the example with videos you own or are licensed to reuse.

`input/images.csv` contains photo URLs. Each row must include:

- `rights_basis`: ownership, license, model/photographer consent, or another documented legal basis;
- `publish_scope`: for example `private` or `public` and the target platform;
- `attribution`: required credit text.

Do not add a real person's photo URL unless you have the necessary image rights and consent for the declared Bilibili use. The workflow does not search for adult-performer photos and does not infer permission from a public URL.

## Local run

```bash
python -m pip install -e .
# Requires ffmpeg on PATH.
media-publisher --videos input/videos.csv --images input/images.csv
```

Each source video is downloaded, the selected image is scaled with aspect ratio preserved, padded to the requested fixed canvas (default `1920x1080`), and combined with the source audio. `output/build-report.json` records both sources and rights metadata.

## GitHub Actions

`.github/workflows/publish.yml` is manual only. `publish_mode=build` creates an artifact and does not upload to Bilibili. `private` uploads as a private draft; `public` is an explicit public upload choice. Configure the repository environment `bilibili-publish` with an Actions secret named `BILIBILI_COOKIE_JSON`. The secret value must be the Biliup cookie JSON, and is written only to the ephemeral runner filesystem.

The workflow uses the Biliup CLI and currently pins `biliup==1.2.2`. Review Bilibili rules, copyright status, image rights, and the generated artifact before public submission.

## Image inventory

The discovery list is maintained separately in [`Business-Unit-for-Video/adult-performer-image-inventory`](https://github.com/Business-Unit-for-Video/adult-performer-image-inventory). Its committed `output/` contains exactly 1000 deduplicated candidate image links with source pages and query provenance.

Do not feed that discovery output directly into a public upload. Review selected rows for identity, copyright, consent, publicity rights, attribution, and Bilibili use, then copy only approved rows into `input/images.csv` with a documented `rights_basis` and `publish_scope`.
