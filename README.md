# Authorized Media Publisher

This repository contains only the processing and publishing logic. It does not search for, bundle, or endorse any third-party video or image source.

## Inputs

`input/videos.csv` uses the exact `youtube-music-video-search/output/videos.csv` schema:

```text
video_id,url,title,channel,channel_id,duration,upload_date,availability,live_status,view_count,matched_queries,discovered_at
```

The publisher maps `video_id` to its internal ID and `url` to the source URL. Rights and publish-scope fields are optional audit metadata rather than runtime gates. YouTube watch URLs are downloaded with `yt-dlp`; the legacy native manifest schema remains supported for direct media URLs.

`input/images.csv` accepts the exact 17-column output from `adult-performer-image-inventory/output/images.csv`:

```text
id,person_query,title,source_page_url,image_url,thumbnail_url,mime,width,height,license_short_name,license_url,artist,credit,usage_terms,source,rights_status,collected_at
```

The publisher maps `image_url` directly and uses `credit` or `artist` as attribution. The discovery `rights_status`, optional rights metadata, and attribution remain available in the generated audit report.

Image rotation and video publishing are persisted together in `state/publish-state.json`. The build selects only the next `batch_size` video IDs that are not complete and does not advance state. Every Bilibili submission is public: the publisher reserves the video and image before upload, records the returned Bilibili `aid`/`bvid`, and then attaches the video to the selected Bilibili Season collection. Later runs skip completed video IDs. If collection attachment fails after upload, the next run retries only the attachment rather than uploading a duplicate. Once all image IDs have been used, the image cycle increments and reuse starts from the beginning. The legacy `state/image-usage.json` is imported when the unified state is first created.

Do not add a real person's photo URL unless you have the necessary image rights and consent for the declared Bilibili use. The workflow does not search for adult-performer photos and does not infer permission from a public URL.

## Local run

```bash
python -m pip install -e .
# Requires ffmpeg on PATH.
media-publisher --videos input/videos.csv --images input/images.csv
```

Selected images are downloaded and validated before expensive video downloads begin. A transient invalid image response is retried, then `thumbnail_url` is used when the inventory provides one. Each source video is downloaded, heavily blurred and darkened into a background layer, and keeps its original audio. The selected image is fitted as the central main visual on roughly 84% of the output canvas. `output/build-report.json` records the actual image URL used, both sources, and rights metadata.

## GitHub Actions

`.github/workflows/publish.yml` is manual only and public-only. Every run builds and uploads media in the same job. `batch_size` is the maximum number of state items processed in the run. Execution is strictly serial: finish one pending collection attachment when present, otherwise build one video, publish it, persist its state, and only then continue. A failure therefore preserves earlier completed uploads. Before remote submission, state changes from `reserved` to `submitting`; if the runner stops while the remote result is unknown, later runs halt instead of automatically creating a duplicate, so the Bilibili account and state must be reconciled manually. Configure the repository environment `bilibili-publish` with an Actions secret named `BILIBILI_COOKIE_JSON`. The secret value must be the Biliup cookie JSON, and is written only to the ephemeral runner filesystem.

The workflow uses the Biliup CLI and currently pins `biliup==1.2.2`. Review Bilibili rules, copyright status, and image rights before submission.

## Image inventory

The discovery list is maintained separately in [`Business-Unit-for-Video/adult-performer-image-inventory`](https://github.com/Business-Unit-for-Video/adult-performer-image-inventory). Its committed `output/` contains exactly 1000 deduplicated candidate image links with source pages and query provenance.

Do not feed that discovery output directly into a public upload. Review selected rows for identity, copyright, consent, publicity rights, attribution, and Bilibili use, then copy only approved rows into `input/images.csv` with a documented `rights_basis` and `publish_scope`.
