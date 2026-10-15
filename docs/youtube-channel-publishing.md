# YouTube 频道转写与 Bilibili 发布

两个频道各有独立的公开转写仓库；本仓库保存对应的视频发布清单，负责按清单下载原视频、制作图片叠加画面并公开投稿。转写文档用于检索和阅读，不会在这里重新配音或生成文字视频。

## 频道与入口

| 频道 | 转写文档目录 | 发布清单 | GitHub Actions 发布入口 | Bilibili 合集 | Windows 参数 |
|---|---|---|---|---|---|
| [小岛大浪吹-非正经政经频道](https://www.youtube.com/@xiaodaodalang) | [文档索引](https://github.com/Business-Unit-for-Video/xiaodaodalang-video2text/blob/main/docs/video-index.md) | [input/xiaodaodalang.csv](../input/xiaodaodalang.csv) | [发布小岛大浪吹视频到 Bilibili](https://github.com/Business-Unit-for-Video/authorized-media-publisher/actions/workflows/publish-xiaodaodalang.yml) | 小岛大浪吹 | `-Collection XiaoDaoDaLang` |
| [Better Leaf 好葉](https://www.youtube.com/@betterleaf) | [文档索引](https://github.com/Business-Unit-for-Video/betterleaf-video2text/blob/main/docs/video-index.md) | [input/betterleaf.csv](../input/betterleaf.csv) | [发布Better Leaf 好葉视频到 Bilibili](https://github.com/Business-Unit-for-Video/authorized-media-publisher/actions/workflows/publish-betterleaf.yml) | Better Leaf 好葉 | `-Collection BetterLeaf` |

转写文件分别保存在上游仓库的 `youtube_channels/xiaodaodalang/` 和 `youtube_channels/betterleaf/`，索引会标明文档是否已经生成。清单中存在视频不等于该视频已经转写或已经发布。

## 更新清单

在 Actions 中运行「同步 YouTube 频道发布清单」，从两个公开转写仓库的 `docs/video-catalog.json` 更新本仓库清单。新视频发现、字幕和转写在对应转写仓库完成；本仓库使用它们的视频 ID、原始标题及 YouTube 链接，不把 Markdown 文件当作视频来源。

只纳入公开来源，不纳入会员限定内容；不套用其他课程项目的时长门槛。发现清单本身不能保证视频在所有地区都可下载，发布时仍会核实来源。原视频 ID 会保留用于去重。

## 在 GitHub Actions 发布

1. 进入上表中对应频道的 Actions 页面，选择 `Run workflow`。
2. 设置 `batch_size`，默认最多完成 2 条；宽、高默认 1920 × 1080。
3. 执行后按清单顺序逐个处理，结果和报告在该次运行中查看。

两个入口固定使用自己的清单和合集，全部为公开投稿。它们与周杰伦、于纲共用 `authorized-media-publisher` 并发组和 `state/publish-state.json`，因此云端发布会排队，历史状态持续用于去重。这里没有新增每天定时发布。

凭据复用本仓库现有的 `YOUTUBE_SOURCE_COOKIE_FILE_AUTHORIZED_PUBLISHER` 和 `BILIBILI_PUBLISH_COOKIE_JSON`，运行环境为 `bilibili-publish`，无须为这两个发布入口重复配置另一套 Cookie。公开仓库只存清单和代码，Cookie 只从 Secrets 写入临时文件。

## 在原生 Windows 发布

环境安装与 Cookie 同步见 [Windows 本地运行](windows-local.md)。在本仓库目录执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-windows.ps1 -Collection XiaoDaoDaLang -BatchSize 2 -Publish
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-windows.ps1 -Collection BetterLeaf -BatchSize 2 -Publish
```

上面两条分别对应两个频道，按需要选择执行；去掉 `-Publish` 就只做本地检查和候选预览。`-BatchSize` 是单次完成数量。运行时不要同时启动云端发布，本地锁与 GitHub Actions 的并发控制相互独立。

## 制作、审核与状态

复用现有视频处理：保留原视频音频，将原画面强模糊并变暗，再以 `input/images.csv` 选出的图片作为主要画面。该流程与文字转配音、文字转视频生成分开维护。新频道使用频道名和知识相关标签，分区参数为 `171`，不沿用周杰伦的音乐标签。

已发布、已跳过或重复的视频不会重复上传；来源明确不可用时记录原因并继续取下一条，不占成功数量。已上传但未加合集的条目优先补挂，计入完成数量。未知下载或上传错误仍会停止。

每次发布前检查该清单最近两条稿件；审核退回会阻塞，人工决定跳过时保留原因与历史记录。`submitting` / `uploading` 表示远端结果尚未确认，需要先核对账号，不能为了继续队列直接清空记录。详细操作见 [审核阻塞说明](bilibili-review-gate.md)。
