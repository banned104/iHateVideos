---
name: ihatevideos-stt
description: 用 Qwen3-ASR-1.7B 把本地音视频转成带字级时间戳的中文文字，产出的 JSON 能被 ihatevideos-export 直接转成 Markdown。只要需要把一个视频或音频里的说话内容变成文字、要给总结阶段准备带时间的转录、要知道每句话在音频里的准确位置，或者转写结果里出现专有名词识别错误想换参数重跑，都用本 Skill。不要自己写 torch 或 transformers 代码去调用模型，一律通过 ihatevideos-stt 命令或 ihatevideos.stt 模块调用。
---

# iHateVideos STT（本地语音转写）

你是这个工程里负责语音识别的一步。输入是一个本地音视频文件，产出是带时间戳的转录文件。
不联网、不下载权重、不做总结、不做画面处理。

## 何时使用

- 要一段音视频里的文字 → `transcribe`
- 要每句话在音频里的起止时间 → `transcribe`，默认就带
- 要每个字在音频里的位置 → 读 `transcription.json` 的 `units`
- 不确定显卡和权重能不能用 → 先 `doctor`
- 只要整段文本、不要时间戳，想跑快一点 → `transcribe --no-timestamps`

## 模块位置

- 代码：`src/ihatevideos/stt/`（`engine.py` 模型加载与推理、`audio.py` 音频准备、
  `sentences.py` 字级时间戳聚成句子、`models.py` 数据类、`paths.py` 产物路径、
  `service.py` 一站式编排、`cli.py` 命令行）
- 在项目根目录用 `uv run ihatevideos-stt ...` 调用
- 权重放在工程根目录的 `models/` 下，被 `.gitignore` 忽略，不进版本库：

| 目录 | 作用 | 体积 |
|---|---|---|
| `models/Qwen3-ASR-1.7B` | 识别模型 | 4.5 GB |
| `models/Qwen3-ForcedAligner-0.6B` | 时间戳模型 | 1.8 GB |

## 命令

```bash
uv run ihatevideos-stt doctor [--model-dir DIR] [--aligner-dir DIR]

uv run ihatevideos-stt transcribe <input> [--language Chinese] [--gpu N] [--device cuda:0] \
    [--model-dir DIR] [--aligner-dir DIR] [--no-timestamps] [--batch-size 16] \
    [--max-new-tokens 8192] [--out-dir DIR] [--timeout 600] [--reuse] [--full]
```

输入可以是视频（`mp4`、`mkv`）或音频（`mp3`、`m4a`、`wav`），程序自己抽成 16 kHz 单声道 wav，
不需要先跑 `ihatevideos-media audio`。已经抽好的 wav 也一样能直接喂进来。

`--gpu N` 用来限定只使用第 N 块显卡，机器上有多块卡、别的任务正在占用其中一块时必须写。
设了之后 CUDA 设备索引会重新编号，输出里的 `device` 会是 `cuda:0`，真实是哪块卡看 `device_name`。
`--reuse` 复用已经抽好的 `audio.wav`，重跑时省掉抽音频的时间。

## 产物

默认输出目录是 `temp/stt/<源文件主干名>`，`--out-dir` 可以换成会话目录。三个文件：

| 文件 | 内容 | 给谁用 |
|---|---|---|
| `audio.wav` | 16 kHz 单声道音轨 | 排查问题、复跑 |
| `transcription.json` | 完整结果，含句级与字级时间戳 | 需要字级位置的步骤 |
| `export.json` | 只有句级时间戳的载荷 | `ihatevideos-export json2md` |

标准输出是一行 JSON。默认只给概要与整段文本，`--full` 会带上完整的 `sentences` 与 `units`。

## 输出格式

### 标准输出与 `transcription.json`

```json
{
  "command": "transcribe",
  "input": "源文件绝对路径",
  "audio": "抽出来的 wav 路径",
  "model_dir": "识别模型目录",
  "aligner_dir": "时间戳模型目录，--no-timestamps 时为 null",
  "language": "Chinese",
  "device": "cuda:0",
  "device_name": "NVIDIA GeForce RTX 4070 Ti SUPER",
  "duration_seconds": 1211.15,
  "audio_seconds": 0.812,
  "load_seconds": 41.782,
  "transcribe_seconds": 443.172,
  "realtime_factor": 0.3659,
  "chars": 5247,
  "text": "整段文本，没有换行",
  "sentences": [
    {"begin_time": 1000, "end_time": 15000, "text": "大家好，欢迎继续收看。"}
  ],
  "units": [
    {"text": "大", "start_time": 1.0, "end_time": 1.16}
  ],
  "out": "transcription.json 的路径"
}
```

时间单位有两套，混用会算错位置，务必分清：

- `sentences[].begin_time` 与 `end_time` 是**毫秒**，与 `ihatevideos-export` 认的
  `transcripts[].sentences[].begin_time` 一致。
- `units[].start_time` 与 `end_time` 是**秒**，带三位小数，来自时间戳模型。
- 顶层 `duration_seconds`、`*_seconds` 都是秒。

`realtime_factor` 是转写耗时除以音频时长。小于 1 表示比实时快。

### `export.json`

已经转成 `ihatevideos-export` 认的结构，不要再自己拼：

```json
{
  "source": "源文件绝对路径",
  "language": "Chinese",
  "text": "整段文本",
  "transcripts": [
    {"id": "0", "text": "整段文本", "sentences": [{"begin_time": 1000, "end_time": 15000, "text": "…"}]}
  ]
}
```

下一步直接跑：

```bash
uv run ihatevideos-export json2md temp/stt/<主干名>/export.json
```

### `doctor` 的输出

```json
{
  "command": "doctor",
  "project_root": "工程根目录",
  "runtime": {"torch": "2.14.1+cu130", "cuda_available": true, "device_count": 2,
              "devices": [{"index": 0, "name": "…"}, {"index": 1, "name": "…"}], "qwen_asr": true},
  "model": {"path": "…", "exists": true, "missing": [], "has_weights": true},
  "aligner": {"path": "…", "exists": true, "missing": [], "has_weights": true},
  "ready": true
}
```

## Agent 判断

| 情况 | 动作 |
|---|---|
| 还没跑过转写 | 先跑 `doctor`，`ready` 为 `false` 就停下，把缺的东西报给用户 |
| `doctor` 退出码 `3` | 环境或权重不齐，不要接着跑 `transcribe` |
| 机器上有别的任务占着显卡 | 用 `--gpu N` 指定空闲的那块，不要让它自己选 |
| 视频超过 20 分钟 | 直接跑，程序内部按 20 分钟分块；开时间戳时按 3 分钟分块并自动累加时间偏移，不用你切 |
| 想重跑同一个文件 | 加 `--reuse`，抽音频那一步会跳过 |
| 只要文本不要时间戳 | `--no-timestamps`，不加载时间戳模型，快一些 |
| 转写耗时 | 实测 20.2 分钟中文视频约 443 秒（`realtime_factor` 0.37）。长视频按这个比例估时间 |
| 专有名词识别错误 | 模型没有热词表。识别错的人名、术语、英文缩写，只能靠下游总结阶段纠正，不要指望重跑变对 |
| 需要逐字位置 | 读 `transcription.json` 的 `units`，不要用 `sentences` 的毫秒值去反推 |
| 输入没有音轨 | 退出码 `3`，换文件或停下 |
| 输出被截断 | 标准输出默认不含 `units` 和 `sentences`；要完整内容读 `transcription.json` |

退出码：`0` 成功 · `2` 输入不合法（文件不存在、参数写错）· `3` 环境或权重不齐 ·
`1` 运行失败（找不到 ffmpeg、显存不足、模型报错）。

## 回给上层

- `doctor`：`ready`、`runtime.devices`、`model`、`aligner`
- `transcribe`：`out`（完整结果）、`export`（给导出模块）、`language`、`chars`、
  `sentence_count`、`duration_seconds`、`realtime_factor`

只使用命令打印出来的路径，不要自己拼。

## 环境与依赖

- Python 侧：`torch`（CUDA 版）、`qwen-asr`、`transformers`，都由 `uv sync` 装好。
- 抽音频用 `ffmpeg`，定位顺序是环境变量 `FFMPEG_PATH` 或 `IHATEVIDEOS_FFMPEG`，其次 `PATH`。
- Windows 上装不了 vLLM，也装不了 flash-attn，只能走 transformers 后端：
  能批量、能出时间戳，**不能流式**。
- 显存：1.7B 加时间戳模型实测峰值约 5.75 GB，16 GB 的卡够用。

## Test prompts for this skill

1. "把 `temp/media/某个视频.mp4` 转成文字，要每句话的时间，用第 1 块显卡。"
2. "转写好的结果在哪？下一步怎么变成 Markdown？"
3. "我想确认这台机器能不能跑语音识别，先检查一下环境。"
