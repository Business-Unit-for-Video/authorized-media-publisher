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

不要将 `submitting` 直接改为 `published`，除非已在 Bilibili 创作中心核对该稿件确实存在并且 `aid`、`bvid` 与状态文件一致。这样可避免重复投稿。
