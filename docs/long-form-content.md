# 大课/长视频清单规则

这个发布仓库默认只处理完整的大课、讲座或课程，不把大量短片段混入投稿队列。

## 清单标注

视频清单可以在现有字段之外增加以下可选字段：

```csv
content_type,duration_seconds
long_form,3600
```

`content_type` 明确标为 `long_form`、`lecture`、`course`、`full` 或“大课”时可进入队列。标为 `clip`、`short`、`fragment`、“片段”或“小段”的条目会被排除。

没有 `content_type` 的条目，只有在提供 `duration` 或 `duration_seconds` 且达到最低时长时才会进入队列。工作流默认最低时长为 1,800 秒（30 分钟）；无法确认类型或时长的条目会被跳过，不会下载、构建或投稿。

## Actions 设置

`Publish authorized media` 工作流的 `content_policy` 默认是 `long_form`，`min_duration_seconds` 默认是 `1800`。只有在人工确认整份清单确实不含片段时，才应选择 `all`。

旧的清单如果没有这些字段，不会被自动推断为大课。请先复制一份清单，补充 `content_type=long_form` 或有效时长，再在 Actions 中使用它。已记录为 `published` 或 `skipped` 的视频仍然按状态去重，不会重复投稿。
