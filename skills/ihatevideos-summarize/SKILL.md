---
name: ihatevideos-summarize
description: 把视频或音频变成图文并茂的 Markdown 笔记。给一个已经转写好的视频，套工程里的模板写出正文，再按正文里留下的画面占位符把对应时间点的画面取到笔记同级的 assets/ 目录，最后把占位符换成图片引用。只要需要给视频写学习笔记、播客笔记、会议记录，需要把视频画面插进 Markdown，需要一套能直接拖进 Obsidian 的笔记文件夹，或者要列出和自定义写作模板，都用本 Skill。本 Skill 不加载任何模型、不调用在线接口，文字部分由你自己写，画面部分交给命令。
---

# iHateVideos Summarize（图文笔记）

你是这个工程里负责写笔记的一步。输入是一份转写结果和一个视频文件，产出是一个可以直接搬走的
笔记文件夹：一份 Markdown 加一个同级的 `assets/`。

文字由你写，画面由命令取。本 Skill 不做转写，转写交给 `ihatevideos-stt`。

## 何时使用

- 要把一集教学视频写成可复盘的笔记 → `template study-notes`
- 要把一期播客写成带观点、带时间线的笔记 → `template podcast`
- 要把一次会议的录屏写成带决议和行动项的记录 → `template meeting`
- 要把视频里的图表、代码、幻灯片放进笔记 → 在正文里留占位符，然后 `frames` 加 `insert`
- 不知道自己手上有哪些模板 → `templates`
- 想加一套自己的写作格式 → 往工程根目录 `templates/` 里加 `.md`

## 模块位置

- 代码：`src/ihatevideos/summarize/`（`templates.py` 读模板、`capture.py` 取画面、
  `insert.py` 找占位符与替换引用、`paths.py` 路径与图片命名、`cli.py` 命令行）
- 模板：工程根目录 `templates/`，随仓库提交，三套：`study-notes`、`podcast`、`meeting`
- 在项目根目录用 `uv run ihatevideos-summarize ...` 调用
- 取画面复用 `ihatevideos-media` 的 ffmpeg 封装，不重复实现

## 命令

```bash
uv run ihatevideos-summarize templates

uv run ihatevideos-summarize template <名字>

uv run ihatevideos-summarize frames <视频> --md <笔记> [--at "12,1:30"] \
    [--width N] [--quality 2] [--jobs 4] [--timeout 600] [--reuse] [--format jpg|png]

uv run ihatevideos-summarize insert <笔记> [--format jpg|png]
```

`--format` 写在子命令之后。取帧与插入两边要写成一样，否则 `insert` 会找不到图片。

`frames` 的时间点有两个来源，合并去重：

1. 正文里的画面占位符，这是主要来源，不用手写时间点；
2. `--at` 额外指定的时间点，很少用。

`--md` 决定 `assets/` 放在哪里，也决定图片文件名，必写。

## 占位符

在正文里想插图的位置写：

```
<!-- FRAME: 12:30 | 图注 -->
```

- 时间用 `MM:SS` 或 `HH:MM:SS`，也可以只写秒数。写 5999 秒这种超过一小时的数会被显示成 `01:39:59`。
- 竖直线上是图注，会原样变成图片的替代文字，可省略。
- 同一个时间点出现多次时只取一张图，每个占位符都会各自被替换。
- 一集视频留多少张由你判断。挑真正承载信息的画面，不要把换页、头像、闲聊留下来。

## 产物

`frames` 把画面取到 Markdown 同级的 `assets/`，图片名是 `<笔记文件名>-<MMSS>s.<格式>`：

```
temp/2026-10-08-函数对象-BV1SLaZ6FEeL/
  函数对象.md
  assets/
    函数对象-0012s.jpg
    函数对象-0130s.jpg
```

整个文件夹可以直接拖进 Obsidian，图片引用是相对路径加正斜杠，换电脑、换目录都不会断。

`insert` 原地改写 Markdown（覆盖写），把占位符换成 `![图注](assets/xxx.jpg)`，**不可重复执行**：
第二次跑时已经没有占位符，什么都不会发生。

## 输出格式

### `templates`

```json
{
  "command": "templates",
  "dir": "工程根目录\\templates",
  "templates": [
    {"name": "meeting", "title": "会议", "path": "…\\templates\\meeting.md"}
  ]
}
```

### `template`

```json
{
  "command": "template",
  "name": "study-notes",
  "title": "教学视频笔记",
  "path": "…\\templates\\study-notes.md",
  "body": "去掉首行标题之后的模板正文，含正文结构与占位符用法"
}
```

### `frames`

```json
{
  "command": "frames",
  "video": "视频绝对路径",
  "markdown": "笔记路径",
  "assets_dir": "…\\assets",
  "requested": 4,
  "frames": [
    {"index": 1, "seconds": 72.0, "timestamp": "01:12",
     "path": "…\\assets\\函数对象-0112s.jpg", "reused": false}
  ],
  "skipped": [
    {"seconds": 5940.0, "timestamp": "01:39:00", "reason": "ffmpeg 的报错原文"}
  ]
}
```

`frames` 里的顺序与传入时间点一致，`index` 是顺序号，`reused` 为 `true` 表示沿用了已有图片。

### `insert`

```json
{
  "command": "insert",
  "markdown": "笔记路径",
  "changed": true,
  "inserted": [
    {"timestamp": "01:12", "seconds": 72.0, "image": "…\\assets\\函数对象-0112s.jpg", "caption": "结构图"}
  ],
  "missing": [
    {"timestamp": "01:39:00", "seconds": 5940.0, "image": "…", "caption": "…"}
  ]
}
```

`missing` 里的占位符在正文里原样保留，说明那一帧没取到。原因通常是时间点超出视频长度。

## 完整流程

1. `uv run ihatevideos-summarize templates`，看有哪些模板。
2. `uv run ihatevideos-summarize template study-notes`，拿到模板正文，照它的结构写。
3. 读转写结果（`temp/stt/<主干名>/export.md` 或 `transcription.json`），写笔记，存成
   `temp/<日期>-<标题>-<BV号>/<标题>.md`，在关键位置留下 `<!-- FRAME: 时间 | 图注 -->`。
4. `uv run ihatevideos-summarize frames "<视频路径>" --md "<笔记路径>"`。
5. `uv run ihatevideos-summarize insert "<笔记路径>"`。
6. 读 `insert` 的输出：`inserted` 是成功的，`missing` 非空就按时间点调整正文里的占位符后重跑第 4、5 步。

## Agent 判断

| 情况 | 动作 |
|---|---|
| 还没写正文 | 先 `templates` 加 `template`，拿到模板再动笔，不要凭印象自己造结构 |
| 不知道这集讲了什么内容 | 先要转写结果；本 Skill 不读视频内容，只看你写好的正文里的时间点 |
| 判断不了哪一帧值得留 | 用一个能说出内容的时间点，图注写清楚这一帧在讲什么；不要留整分钟采样的帧 |
| 一集 30 分钟的教学视频 | 3 到 8 张合适 |
| 一次两小时的会议 | 5 到 12 张，集中在分享屏幕的段落 |
| 纯音频播客 | 不写任何占位符，跳过 `frames` 和 `insert` |
| `insert` 的 `missing` 非空 | 看 `timestamp`，多半超出视频长度；改成视频内的准确时间点，重跑 `frames` 与 `insert` |
| 正文被 `insert` 改过，想再改文字 | 直接改 Markdown 里的 `![](...)`，没有占位符可用了 |
| 已经跑过一次 `insert` | 不要再跑，什么都不会发生 |
| 想换一套写作结构 | 往工程根目录 `templates/` 加 `.md`，首行 `# 标题` 会被当成模板名 |

退出码：`0` 成功 · `2` 输入不合法（文件不存在、模板不存在、时间点写错、正文里没有占位符）·
`3` 部分画面没取到（`frames` 的 `skipped` 非空，或 `insert` 的 `missing` 非空）·
`1` 运行失败（找不到 ffmpeg）。

`templates` 恒返回 `0`；`template` 找不到模板时返回 `2`。

## 回给上层

- `templates`：`templates[].name`、`templates[].title`
- `template`：`body`，照着它写
- `frames`：`assets_dir`、`frames[].path`、`skipped`
- `insert`：`changed`、`inserted`、`missing`

只使用命令打印出来的路径，不要自己拼。

## 依赖

- 取画面用 `ffmpeg`，定位顺序与环境变量 `FFMPEG_PATH`、`IHATEVIDEOS_FFMPEG` 无关的部分
  由 `ihatevideos-media` 负责；拿不到 ffmpeg 时 `frames` 返回 `1`。
- 不加载任何模型，不需要显卡，不联网。
- `templates/` 随仓库提交；存在工程外时 `templates` 返回空列表。

## Test prompts for this skill

1. "把 `temp/stt/函数对象_ev/export.md` 写成学习笔记，只留 3 张图，存到 `temp/` 下。"
2. "我有一期播客的转写，想整理成能直接拖进 Obsidian 的笔记，该怎么做？"
3. "笔记里的图没插进去，`missing` 里列了一条，原因是什么？"
