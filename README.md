# Authorized Media Publisher

This repository contains only the processing and publishing logic. It does not search for, bundle, or endorse any third-party video or image source.

## Inputs

`input/videos.csv` uses the exact `youtube-music-video-search/output/videos.csv` schema:

```text
video_id,url,title,channel,channel_id,duration,upload_date,availability,live_status,view_count,matched_queries,discovered_at
```

The publisher maps `video_id` to its internal ID and `url` to the source URL. The CSV is the operator-selected input: this repository does not classify videos, inspect course length, or filter rows by duration. Rights and publish-scope fields are optional audit metadata rather than runtime gates. YouTube watch URLs are downloaded with `yt-dlp`; the legacy native manifest schema remains supported for direct media URLs. An optional `remove_segments` column accepts semicolon-separated ranges such as `00:10:27-00:10:39`; those ranges are removed from both the video and audio before the image overlay is rendered.

`input/images.csv` accepts the exact 17-column output from `adult-performer-image-inventory/output/images.csv`:

```text
id,person_query,title,source_page_url,image_url,thumbnail_url,mime,width,height,license_short_name,license_url,artist,credit,usage_terms,source,rights_status,collected_at
```

Images removed by the operator are deleted from this manifest and are never selected for new builds. Historical `state/publish-state.json` entries may still retain their image ID for auditability; that does not make the retired image eligible for a future publication.

The publisher maps `image_url` directly and uses `credit` or `artist` as attribution. The discovery `rights_status`, optional rights metadata, and attribution remain available in the generated audit report.

Image rotation and video publishing are persisted together in `state/publish-state.json`. The build selects only the next video IDs that are not complete and does not advance state. Every Bilibili submission is public: the publisher reserves the video and image before upload, records the returned Bilibili `aid`/`bvid`, and then attaches the video to the selected Bilibili Season collection. Later runs skip completed video IDs. Before building, the serial runner also compares a conservative normalized content-title key against already published records so the same content from a different YouTube ID is saved as `duplicate` rather than uploaded twice. Videos marked `skipped`, `unavailable`, or `duplicate` are treated as complete and excluded from the review gate. Explicit YouTube unavailability is recorded with `unavailable_reason`; transient or unknown download errors still fail the run for investigation. If collection attachment fails after upload, the next run retries only the attachment rather than uploading a duplicate. Once all image IDs have been used, the image cycle increments and reuse starts from the beginning. The legacy `state/image-usage.json` is imported when the unified state is first created.

Do not add a real person's photo URL unless you have the necessary image rights and consent for the declared Bilibili use. The workflow does not search for adult-performer photos and does not infer permission from a public URL.

## Local run

Windows 原生安装、检查与按数量批量发布见[Windows 本地运行说明](docs/windows-local.md)。GitHub Actions 保持独立可用。

```bash
python -m pip install -e .
# Requires ffmpeg on PATH.
media-publisher --videos input/videos.csv --images input/images.csv
```

Selected images are downloaded and validated before expensive video downloads begin. A transient invalid image response is retried, then `thumbnail_url` is used when the inventory provides one. Each source video is downloaded, heavily blurred and darkened into a background layer, and keeps its original audio. The selected image is fitted as the central main visual on roughly 84% of the output canvas. `output/build-report.json` records the actual image URL used, both sources, and rights metadata.

## GitHub Actions

四个独立入口固定使用各自清单和 Bilibili 合集，均为手动触发、公开投稿，默认每次最多完成两条：

| Actions 文件 | 输入清单 | Bilibili 合集 |
|---|---|---|
| [publish-jay-chou.yml](.github/workflows/publish-jay-chou.yml) | `input/videos.csv` | 周杰伦 |
| [publish-yu-gang.yml](.github/workflows/publish-yu-gang.yml) | `input/guodegang-early-successes.csv` | 于纲 |
| [publish-xiaodaodalang.yml](.github/workflows/publish-xiaodaodalang.yml) | `input/xiaodaodalang.csv` | 小岛大浪吹 |
| [publish-betterleaf.yml](.github/workflows/publish-betterleaf.yml) | `input/betterleaf.csv` | Better Leaf 好葉 |

小岛大浪吹、Better Leaf 好葉的公开转写仓库、文档索引、清单更新和 Windows 命令见 [YouTube 频道转写与发布](docs/youtube-channel-publishing.md)。本仓库处理清单中的原视频与图片，不把转写文档重新生成视频。

两频道的文档目录汇总见 [频道视频与转写文档目录](docs/channel-document-lists.md)。于纲、周杰伦的账号审核结果和剩余队列见 [2026-10-15 发布现状](docs/publishing-status-2026-10-15.md)。

这些入口共用并发组和状态文件，同一时间只有一个云端发布任务运行，已完成内容按来源 ID 和内容标题去重。发布器不增加课程类型或时长过滤。`batch_size` 是本次实际发布或补挂合集的数量上限，`unavailable` 和 `duplicate` 不占数量。每条依次制作、投稿、记录状态再继续，其他失败会停止并保留此前的成功记录。

提交前状态会从 `reserved` 改为 `submitting`；如果远端结果不确定，后续同清单任务会停止，需先核对 Bilibili 账号。环境 `bilibili-publish` 使用仓库已有的 `BILIBILI_PUBLISH_COOKIE_JSON` 和 `YOUTUBE_SOURCE_COOKIE_FILE_AUTHORIZED_PUBLISHER`，Secret 只写入临时文件。上传模块当前固定 `biliup==1.2.11`。

审核阻塞的状态位置、人工核对步骤和更新方式见[中文操作说明](docs/bilibili-review-gate.md)。

## Image inventory

The discovery list is maintained separately in [`Business-Unit-for-Video/adult-performer-image-inventory`](https://github.com/Business-Unit-for-Video/adult-performer-image-inventory). Its committed `output/` contains exactly 1000 deduplicated candidate image links with source pages and query provenance.

Do not feed that discovery output directly into a public upload. Review selected rows for identity, copyright, consent, publicity rights, attribution, and Bilibili use, then copy only approved rows into `input/images.csv` with a documented `rights_basis` and `publish_scope`.
