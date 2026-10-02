---
name: ihatevideos-download
description: 用 aria2c 与 yt-dlp 把网络上的直链与视频取到本地的工程 Skill：查引擎、装 ffprobe、列格式与字幕、下载直链、下载视频（可只取音频）。只写项目内的 temp 与目标目录，不改系统任何位置。
---

# iHateVideos Download（下载直链与视频）

## 何时使用

- 需要把一条**直链**文件（iso、zip、mp4 等）下载到本地，要求分段、断点续传或限速。
- 需要把一条**视频页**（B 站以外的站点，或需要 yt-dlp 能力时）的某一档清晰度、或只把音频取下来。
- 需要先看某个视频页有哪些格式与字幕语言，再决定下哪一档。

## 模块位置

`src/ihatevideos/download/`，命令行入口 `src/ihatevideos/download/cli.py`。命令行名字是 `ihatevideos-download`。

## 命令

```bash
# 看三个引擎的位置与版本
uv run ihatevideos-download engines

# 取回 uv 装不进来的 ffprobe（写进项目内的 temp/bin/）
uv run ihatevideos-download setup-binaries [--force]

# 列出一个视频页的格式与字幕语言
uv run ihatevideos-download formats "<视频页链接>"

# 下载直链（可给多条）
uv run ihatevideos-download file <直链> [<直链> ...] [--out-dir DIR] [--filename NAME] \
    [--limit KBPS] [--global-limit KBPS] [--jobs N] [--no-proxy]

# 下载视频
uv run ihatevideos-download video <视频页> [<视频页> ...] [--format 编号] [--height 720] \
    [--audio-only] [--subs zh-Hans,en] [--sub-format srt] [--write-auto-subs] \
    [--no-accel] [--out-dir DIR] [--filename NAME] [--limit KBPS] [--jobs N] \
    [--cookie FILE] [--cookie-from-browser edge] [--no-proxy]
```

- `--format` 与 `--height` 互斥。都不给时按最高清晰度自动选择。
- `--limit` 是单个任务的限速，`--global-limit` 是本次运行的总体限速，单位都是 KiB/s。
- `--filename` 只在给一条链接时可用。
- 默认输出目录是项目内的 `temp/download`。

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 全部任务完成 |
| 1 | 运行失败（有任务没有完成、引擎启动失败、被中断） |
| 2 | 输入不合法（参数冲突、格式编号不在清单里） |
| 3 | 正常跳过（站点不被 yt-dlp 支持、这个地址没有可用格式） |

## 产物位置

- 下载结果写在 `--out-dir`，默认 `temp/download`。
- 中断时目录里会留下断点：直链留下 `<文件名>.aria2` 控制文件，视频留下 `.part`。再跑同一条命令即从断点继续。
- `setup-binaries` 只写 `temp/bin/`，并在其中留一份 `SOURCES.json`（来源 URL、ETag、字节数、SHA256）。
- 命令只往目标目录与项目内的 `temp/` 写入，不改 PATH、不写注册表、不写系统目录、不写用户配置目录。
- 标准输出是一行 JSON，进度写在标准错误。

## Agent 判断

- 目标站点是 B 站、小宇宙、喜马拉雅时，走 `ihatevideos-input`，不要用本命令。
- 只要音频转文字时用 `video --audio-only`，产物是 mp3。
- `formats` 返回的 `subtitles` 为空说明这个页面没有可下载的字幕（B 站字幕需要登录态，走 `ihatevideos-input subtitle`）。
- 退出码 3 表示正常跳过，不要当成失败重试。
- 中断与继续都靠文件断点，不需要保存任务编号。

## 回给上层

命令的实际输出 JSON。`tasks[].save_path` 是最终路径，`size_bytes` 是磁盘上的字节数，`error` 为 `null` 表示该任务成功。`tasks[].format_id` 是 yt-dlp 实际选中的格式（可能是两条，例如 `100026+30280` 表示视频与音频分开下载后合流）。不要编造路径。

标准错误里还会原样打印 yt-dlp 关于「哪些格式拿不到」的提示，例如 4K 与 1080P 高码率需要大会员。看到这类提示时如实转告，不要当成失败。

## 依赖

`pyproject.toml` 里的 `aria2`（aria2c 本体）、`aria2p`（RPC 客户端）、`imageio-ffmpeg`（ffmpeg 本体）、`yt-dlp`。ffprobe 不在 PyPI，由 `setup-binaries` 取回项目内的 `temp/bin/`。下载子进程跟随系统代理，需要直连时加 `--no-proxy`。

## Test prompts for this skill

- 看看下载引擎都在哪，版本是多少。
- 这条视频页有哪些清晰度可以下？字幕有哪几种语言？
- 把这个视频的 720p 下到 temp/download 里。
- 只把这个视频的音频下下来。
- 下载这个直链文件，限制每秒 512 KiB。
- 下载到一半我按了 Ctrl+C，再跑一次它会接着下吗？
