# Authorized Media Publisher

This repository contains only the processing and publishing logic. It does not search for, bundle, or endorse any third-party video or image source.

## Inputs

`input/videos.csv` uses the exact `youtube-music-video-search/output/videos.csv` schema:

```text
video_id,url,title,channel,channel_id,duration,upload_date,availability,live_status,view_count,matched_queries,discovered_at
```

The publisher maps `video_id` to its internal ID and `url` to the source URL. The discovery CSV does not establish reuse permission, so the manual workflow separately requires `video_rights_basis` and `video_publish_scope`. YouTube watch URLs are downloaded with `yt-dlp`; the legacy native manifest schema remains supported for authorized direct media URLs.

`input/images.csv` accepts the exact 17-column output from `adult-performer-image-inventory/output/images.csv`:

```text
id,person_query,title,source_page_url,image_url,thumbnail_url,mime,width,height,license_short_name,license_url,artist,credit,usage_terms,source,rights_status,collected_at
```

The publisher maps `image_url` directly and uses `credit` or `artist` as attribution. The discovery `rights_status` remains auditable metadata; the workflow separately requires `image_rights_basis` and `image_publish_scope`.

Image rotation is persisted in `state/image-usage.json`. A successful build records each selected image ID. Later builds continue with unused IDs; after all inventory IDs have been used, the state starts the next cycle and permits reuse. The state is committed only after the build succeeds.

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
