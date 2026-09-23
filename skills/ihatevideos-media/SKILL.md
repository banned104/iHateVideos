---
name: ihatevideos-media
description: 用 ffmpeg 处理本地音视频的工程 Skill：读流信息与时长、按时间点取画面、按时间段剪切视频或音频、提取音轨、把音轨切成等长片段。当需要从视频里取出某一秒的画面、把一段视频或音频剪出来、把音轨单独导出或分块时使用本 Skill。不要自己拼 ffmpeg 命令行，一律通过 ihatevideos-media 命令或 ihatevideos.media 模块调用。
---

# iHateVideos Media（本地音视频处理）

你是这个工程里负责音视频处理的一步。输入是一个本地文件路径，产出是画面图片、
剪切片段或音频文件。不联网、不识别平台、不做语音识别与总结。

## 何时使用

- 先知道时长与流信息 → `probe`
- 要某一时间点的画面 → `frames`
- 要一段时间的内容，视频或音频都行 → `clip`
- 只要音轨，或要把音轨按时长切块交给语音识别 → `audio`

## 模块位置

- 代码：`src/ihatevideos/media/`（`ffmpeg.py`、`probe.py`、`frames.py`、
  `clip.py`、`audio.py`、`paths.py`、`timestamps.py`、`cli.py`）
- 在项目根目录用 `uv run ihatevideos-media ...` 调用
- 依赖系统 `ffmpeg` 与 `ffprobe`，可用环境变量 `FFMPEG_PATH` / `FFPROBE_PATH` 指定位置

## 命令

四个子命令，标准输出一行 JSON，日志与 ffmpeg 的错误信息走标准错误。

```bash
uv run ihatevideos-media probe <input> [--streams] [--timeout 60]
uv run ihatevideos-media frames <input> (--at "12,1:30" | --every 30 | --count 12) \
    [--range "10-120"] [--out-dir DIR] [--format jpg|png] [--width 1280] \
    [--quality 2] [--max-frames 64] [--jobs 4] [--timeout 600] [--reuse]
uv run ihatevideos-media clip <input> [--start "0"] [--end "1:10" | --duration 30] \
    [--mode reencode|copy] [--audio-only] [--out FILE | --out-dir DIR] [--timeout 600] [--reuse]
uv run ihatevideos-media audio <input> [--format wav|m4a|mp3] [--sample-rate 16000] \
    [--channels 1] [--bitrate 192k] [--range "10-600"] [--chunk-seconds 600] \
    [--out FILE | --out-dir DIR] [--timeout 600] [--reuse]
```

## 时间写法

`90`、`90.5`、`1:30`、`01:30.5`、`1:02:03` 都接受，转录文本里的 `MM:SS` 可以直接粘进
`--at`、`--start`、`--end`、`--duration`、`--range`。`--at` 用逗号分隔多个时间点，
`--range` 写成 `起点-终点`，终点留空表示到结尾。

## 产物位置

默认输出目录是 `temp/media/<源文件主干名>`，`--out-dir` 可以换成会话目录。

```
frames/frame-001_12.000s_<参数摘要>.jpg  序号按时间顺序，文件名含时间点
audio/<主干名>_<参数摘要>.wav            提取的完整音轨
audio/chunks-600s-<参数摘要>/audio-001.wav
clips/<主干名>_01m00s-01m10s_<参数摘要>.mp4
```

默认覆盖同名产物，`--reuse` 时保留已有文件并在 JSON 里写 `"reused": true`，产物名里带有
参数摘要，只有参数完全相同的调用才会复用同一个文件。

- `frames --quality` 只对 jpg 生效，png 会忽略它。
- `clip` 不给 `--end` 也不给 `--duration` 时剪到文件结尾。
- `audio --chunk-seconds` 不能和 `--format`、`--out` 同时用，分块固定输出 wav。

## Agent 判断

| 情况 | 动作 |
|---|---|
| `probe` 返回 `has_video: false` | 不要跑 `frames`，改用 `audio` 或停下 |
| `frames` 退出码 `3` | 输入没有视频流，属正常跳过，换 `audio` 或停下 |
| `audio` 退出码 `3` | 输入没有音轨，属正常跳过，换 `frames` 或停下 |
| `clip --mode copy` | 起点会停在前一个关键帧的位置，产出的时长比请求多几十毫秒；要准确起点就用默认的 `reencode` |
| 时间点超出媒体时长 | 退出码 `2`，按 `probe` 给出的时长改时间点，不要重发同一条命令 |
| `frames` 时间点超过 `--max-frames` | 退出码 `2`，改用更大的 `--every` 或更小的 `--count` |
| `frames --count` | 在给定区间内均匀取中点，第一帧不贴区间起点 |
| 抽帧给视觉模型看 | 用 `--width 1280` 控制图片大小，`--at` 指定要看的秒数 |
| 切块交给语音识别 | 用 `audio --chunk-seconds 600`，块的起止秒数写在 JSON 的 `chunks` 里，回填时间戳时加上 `start_seconds` |

退出码：`0` 产出成功 · `2` 输入不合法（文件不存在、参数冲突、超出时长或上限）·
`3` 缺少需要的流，正常跳过 · `1` 运行失败（找不到 ffmpeg、命令非零退出、超时）。

## 回给上层

- `probe`：`duration_seconds`、`has_video`、`has_audio`、`video`、`audio`
- `frames`：`frames[].path` 与 `frames[].seconds`，失败的记在 `skipped` 里
- `clip`：`path`、`start_seconds`、`end_seconds`
- `audio`：`path`，分块时是 `chunks[].path` 与每块的 `start_seconds`、`end_seconds`

只使用命令打印出来的路径，不要自己拼。

## 依赖

系统 `ffmpeg` 与 `ffprobe`，Python 侧只用标准库。找不到可执行文件时立即报错并提示
安装位置，不做兜底。

## Test prompts for this skill

1. "这个视频有多少秒？有没有音轨？路径是 `temp/media/<某个 mp4>`。"
2. "从 `temp/media/<某个 mp4>` 的 `1:00` 到 `1:10` 剪一段出来，同时把第 10 秒的画面取出来给我看。"
3. "把这个 mp3 的音轨按 600 秒切块，告诉我每一块的起止秒数和文件路径。"
