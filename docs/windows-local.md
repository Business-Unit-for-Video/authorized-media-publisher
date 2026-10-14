# Windows 本地运行

本地入口使用原生 Windows、PowerShell 和独立的 `.venv`，复用 PATH 上已有的 Python 3.11+、Git、FFmpeg（含 ffprobe）与 Node.js。无需 WSL。GitHub Actions 的 workflow、启用状态和 Secrets 不变。

## 首次安装

在仓库目录打开 PowerShell：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1
```

`ExecutionPolicy Bypass` 只用于这个子进程，不修改系统执行策略。也可通过 `-PythonPath` 指定 Python.exe 的完整路径。所有 Python 依赖都装进仓库 `.venv`，不更改全局环境。

PyPI 的 `biliup==1.2.11` 完整包需要 Rust/C++ 编译，本项目实际只使用其中纯 Python 网页上传模块。安装脚本下载固定版本的官方源码包，校验固定 SHA256，只安装所需的三个 Python 文件与上游 LICENSE，并记录来源及文件哈希；不运行上游编译脚本。安装器不会覆盖未知安装，重复执行会验证已有文件。这个环境不能运行完整 biliup 服务或 Rust CLI。

上传接口使用同一版本的源码。关键依赖固定为成功运行时的 `aiohttp==3.14.4`、`multidict==6.9.1`、`yt-dlp==2026.8.19`。这有助于对照测试，不代表已经证明失败由依赖升级导致。

## Cookie 放置位置

默认目录在仓库之外：`%USERPROFILE%\.authorized-media-publisher\credentials`。例如 `C:\Users\Future\.authorized-media-publisher\credentials`。

此目录取代早期的 `%LOCALAPPDATA%\authorized-media-publisher\credentials`。打包的桌面应用可能把 AppData 访问重定向到自己的 LocalCache，导致应用内看得到 Cookie、普通 PowerShell 却找不到。请在普通 PowerShell 中执行下面的同步命令来建立新的固定目录；旧目录不会自动删除。

| 本地文件 | 内容来源 |
|---|---|
| `youtube-cookies.txt` | `PeterKZhao/myself` 的 `private/youtube_cookies.md` 中原始 Netscape Cookie 文本，不是 GitHub 网页 HTML |
| `bilibili-cookies.json` | 同仓库 `private/cookies.json` 的原始 JSON，含 `cookie_info.cookies` |

不要把 Cookie 或 Token 提交到本仓库。GitHub Secrets 不会自动同步到本地，源 Cookie 更新后需刷新本地副本。运行时会再复制两份 Cookie 到临时目录，避免上传器和 yt-dlp 改写原始导出。可用 `-CookieDirectory` 指定其他仓库外目录。

若提示文件缺失，或源 Cookie 已更新，在实际运行的 Windows PowerShell 中执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-windows.ps1 -SyncCookies
```

它从上述固定的私有仓库路径下载两份 Cookie，全部验证格式后替换本地文件，再运行检查，不会投稿。GitHub 凭据依次取自当前进程的 `GH_TOKEN` / `GITHUB_TOKEN`、仓库父目录 `authority.md` 的 `GITHUB_TOKEN=...`、已配置的 Git credential helper；不会打开新登录窗口，也不打印凭据。两份 Cookie 留在本机，不改 GitHub Secrets。

## 检查与启动

默认仅检查程序、Python 模块、Cookie 文件格式和发布状态，并预览指定数量的候选记录。不会下载、转码、访问账号或投稿。数量默认 1，可用 `-BatchSize` 调整：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-windows.ps1 -BatchSize 2
```

增加 `-Publish` 后，像 Actions 一样自动从所选合集清单取视频，无需输入 ID。发布周杰伦清单中接下来的最多两条：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-windows.ps1 -BatchSize 2 -Publish
```

切换于纲清单及合集使用 `-Collection YuGang`：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-windows.ps1 -Collection YuGang -BatchSize 2 -Publish
```

`-BatchSize` 是本次最多完成的数量：按原清单顺序，一个完成再处理下一个；已上传但待挂合集的记录优先补挂，计入完成数。已发布/跳过的记录、同来源或同标题的重复内容不再上传；源视频明确不可用时记录状态并继续往后取，不占成功数量。清单耗尽则提前结束，其他下载/上传失败仍会停止。此参数不会创建每天定时任务。

仍可用 `-VideoId "实际视频ID" -Publish` 单独处理一条，此时 `-BatchSize` 必须为 1。所有方式都保留原视频 ID，不生成绕过去重的测试 ID。

正式运行前，先确认该视频在账号中未发布，以及 GitHub Actions 没有同时执行发布。Actions 的 concurrency 不能锁住本地进程；本地锁只防止两个本地入口互相抢占。保持电脑联网且不休眠。

正式运行会要求仓库干净且位于 main，先 `git pull --ff-only`，检查最近两条该合集稿件的审核结果，再串行处理清单。与云端共用并提交 `state/publish-state.json`，每条完成后仍由原发布器加入合集、推送 GitHub。文件及报告位于被 Git 忽略的 `output/windows-local/`。

`submitting` / `uploading` 等历史记录不会自动清空。自动模式若清单中的 ID 本身处于此状态，会阻塞整批并提示核对；若是清单外的其他 ID 已经发布或提交了同一来源，自动模式会排除这个来源候选，单 ID 模式则报错停止。需先核对账号，不应删除状态文件或改 ID 重投。更换运行地点不会自动解决历史阻塞。确认创作中心完整稿件列表中不存在对应投稿后，可保留原记录并恢复为 `reserved`，追加核对时间与依据；`retryable` 不会被当前发布队列自动选中。《圣诞星》于 2026-10-14 完成核对并恢复待重试，依据见 `state/reconciliations/IXuhdnB2dAY-20261014.json`。

检查通过仅证明环境和本地文件可用，Cookie 在线有效性、账号状态及实际分片传输仍需单独验证。本地网络也可能失败。浏览器、requests 与 aiohttp 的代理行为不同；当前分片上传不会自动使用 `HTTP_PROXY` / `HTTPS_PROXY`。不要因浏览器能打开视频，就认定上传节点也可连接。

正常失败会释放本地锁。若进程被强制终止，先确认没有本地发布进程、核对账号与状态，再移除 `output/windows-local/publisher.lock`。启动入口不输出未经处理的网络异常堆栈，避免请求 URL 中的凭据进入日志。
