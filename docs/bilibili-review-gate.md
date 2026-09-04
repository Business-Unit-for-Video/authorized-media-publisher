# Bilibili 审核阻塞的手动处理

发布工作流会在投稿前检查目标清单中最近两条已上传或已发布稿件。检查结果写入运行产物 `output/recent-review-check.json`；该文件每次运行都会重新生成，不能通过修改它解除阻塞。

真正持续保存的状态在 `state/publish-state.json` 的 `videos` 对象中。每个视频按 YouTube `video_id` 记录其 `status`、`aid` 和 `bvid`。

## 已在 Bilibili 正常公开

当 Bilibili 显示稿件为“开放浏览”，请保留或更新该视频为：

```json
{
  "status": "published",
  "aid": 123456,
  "bvid": "BV1...",
  "published_at": "2026-08-25T00:00:00+00:00"
}
```

提交 `state/publish-state.json` 后，下一次运行会再次向 Bilibili 查询最近两条稿件。空的 `reject_reason`、`reject_reason_id: 0` 和“开放浏览”不会阻塞发布。

## Bilibili 确认驳回

将该条目的 `status` 改为 `rejected`，保留 `aid`、`bvid` 和审核原因。下一次发布会继续阻塞，避免在问题未处理时自动投稿。处理完成后，由人工确认 Bilibili 中的最终状态，再更新为 `published`。

## 特殊稿件暂不重试

如果稿件已经投稿，但 Bilibili 显示“稿件不可见”且原因无法明确定位，可以将该条目标记为 `skipped`，让后续视频继续处理：

```json
{
  "status": "skipped",
  "aid": 117155869756824,
  "bvid": "BV1juhG6CEJH",
  "skipped_at": "2026-08-26T00:00:00+00:00",
  "skip_reason": "稿件不可见（Bilibili 公开接口返回 62002），暂不重试"
}
```

`skipped` 会被构建器视为已处理项目，也不会进入最近审核检查，因此不会阻塞其他视频。它不会删除 Bilibili 原稿，也不会自动申诉或重新投稿。以后若要重试，应先人工确认原因，再使用新的清单 ID 和修改后的素材重新提交。

如果 YouTube 下载器明确返回“Video unavailable”“Private video”“has been removed”或地区不可用等源平台错误，串行发布器会把该条记录为 `unavailable`，保存 `unavailable_reason` 和 `unavailable_at`，然后继续处理同一批次的下一条。它不会进入 Bilibili，也不会被当作待审核稿件；网络错误、Cookie 错误或其他无法明确归类的下载错误仍会使 workflow 失败，避免把临时故障误标记为不可用。

当前清单中的 `eOc6cG1l9JM` 已按此规则记录为 `skipped`（Bilibili `aid=117155869756824`，`bvid=BV1juhG6CEJH`，原因码 `62002`）。后续运行会保留这条记录并跳过它，不会再次投稿，也不会阻塞其他条目。

不要将 `submitting` 直接改为 `published`，除非已在 Bilibili 创作中心核对该稿件确实存在并且 `aid`、`bvid` 与状态文件一致。这样可避免重复投稿。
