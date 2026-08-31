# 发布器的职责边界

`authorized-media-publisher` 只负责把人工选定的 CSV 视频制作并公开投稿到 Bilibili，并按状态加入指定合集。

本仓库不检查视频是否为大课、不按时长筛选，也不生成文字转视频内容。视频时长、课程类型、片段排除和 15–20 分钟延后保存等规则，应由上游发现或转写仓库负责；通过筛选后的记录再交给本发布器即可。

清单中的 `duration`、`duration_seconds` 或 `content_type` 可以保留为审计字段，但不会改变发布器的选择结果。发布器仍会跳过状态文件中已经完成或明确跳过的同一视频，避免重复投稿。

GitHub Actions 提供两个固定入口：`发布周杰伦视频到 Bilibili` 固定读取 `input/videos.csv` 并加入“周杰伦”合集；`发布于纲视频到 Bilibili` 固定读取 `input/guodegang-early-successes.csv` 并加入“于纲”合集。两个入口不再要求人工填写清单路径或合集名称。
