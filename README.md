# iHateVideos

Python 工具集合：把视频变成可检索的文字。Python 版本使用 uv 管理（`pyproject.toml`）。

## 目录组成

- `src/ihatevideos/input/`：多平台输入。B 站（含原生字幕优先）/小宇宙/喜马拉雅/本地文件，统一输出音频路径、元数据、资源编号。
- `src/ihatevideos/export/`：内容导出。转录 JSON 转原文 Markdown，总结转干净表格与 B 站时间线。
- `src/ihatevideos/media/`：本地音视频处理。ffprobe 读流信息与时长，ffmpeg 取画面、剪切视频与音频、提取音轨与分块（`ihatevideos-media`）。
- `src/ihatevideos/download/`：下载。aria2c 直链（多线程分段、断点续传、限速），yt-dlp 视频（格式与字幕清单、合流、抽音频、经 aria2c 加速与失败回退），`setup-binaries` 取回 uv 装不进来的 ffprobe（`ihatevideos-download`）。
- `src/ihatevideos/stt/`：本地语音转写。Qwen3-ASR-1.7B 出文字，Qwen3-ForcedAligner-0.6B 出字级时间戳，句级结果直接交给 `ihatevideos-export`（`ihatevideos-stt`）。权重放工程根目录 `models/`，不进版本库。
- `src/ihatevideos/summarize/`：图文笔记。给视频配画面：列模板、把画面取到 Markdown 同级的 `assets/`、把正文里的占位符换成图片引用（`ihatevideos-summarize`）。模板放工程根目录 `templates/`，可以自己加。
- `src/ihatevideos/doctor/`：运行环境检查。一次查完 Python 依赖、外部程序、ffmpeg 实际出活能力、GPU 计算、语音识别权重、B 站 cookies 与登录态、系统代理（`ihatevideos-doctor`）。
- `skills/`：随仓库提交的工程 Skills（`ihatevideos-input`、`ihatevideos-export`、`ihatevideos-media`、`ihatevideos-download`、`ihatevideos-stt`、`ihatevideos-summarize`、`ihatevideos-doctor`）。
- `.agents/skills/`：通用工具 Skills，只存本地，不提交。
- `temp/`：中间结果、Cookie 文件，只存本地，不提交。

## 快速开始

```bash
uv sync
uv run ihatevideos-input detect "BV1xx411c7mD"
uv run ihatevideos-export --help
uv run ihatevideos-media probe "temp/media/<某个视频文件>"
uv run ihatevideos-stt doctor
uv run ihatevideos-stt transcribe "temp/media/<某个视频文件>" --gpu 0
uv run ihatevideos-download engines
uv run ihatevideos-download formats "https://www.bilibili.com/video/BV1xx411c7mD"
uv run ihatevideos-download file "https://example.com/big.iso" --out-dir temp/download
uv run ihatevideos-summarize templates
uv run ihatevideos-summarize template study-notes
uv run ihatevideos-doctor
```

## 语音转写权重

`ihatevideos-stt` 需要两份模型权重，体积大，不进版本库，首次使用前自己下载到工程根目录 `models/`：

```bash
uv run huggingface-cli download Qwen/Qwen3-ASR-1.7B --local-dir models/Qwen3-ASR-1.7B
uv run huggingface-cli download Qwen/Qwen3-ForcedAligner-0.6B --local-dir models/Qwen3-ForcedAligner-0.6B
```

国内网络慢可以把 `huggingface-cli download` 换成 `modelscope download --model <模型名> --local_dir <目录>`。
下完跑 `uv run ihatevideos-stt doctor`，`ready` 为 `true` 就能用。详细说明见 `skills/ihatevideos-stt/SKILL.md`。

## B 站登录态

B 站字幕接口只对登录态返回：

1. 在浏览器登录 B 站，用 Cookie 导出扩展（例如 Get cookies.txt LOCALLY）导出 Netscape 格式。
2. 把导出的文件复制到 `temp/config/`，文件名随意，程序自己会找（多份时取最近修改的那份）。
3. 运行 `uv run ihatevideos-input cookies`，`login` 为 `true` 表示可用。

文件只放在工程内，不写用户主目录，删除工程即可清除。cookies 失效时重新导出一份覆盖进去即可。

`cookies` 会用这份文件调一次 B 站登录接口：`login: true` 表示服务端仍认；`false` 时 `detail` 给出原因（没有文件、目录里没有可用的 cookies、B 站返回的错误码、或这份 cookies 已失效）。不要把 SESSDATA 的值贴到聊天里，密钥只留在本地文件。


## 图文笔记

`ihatevideos-summarize` 负责把视频画面放进 Markdown 笔记。四个子命令：`templates` 列出 `templates/` 里有哪些模板，`template <名字>` 打印某个模板的正文，`frames <视频> --md <笔记>` 按正文里的占位符取帧到笔记同级的 `assets/`，`insert <笔记>` 把占位符换成图片引用。

占位符写成 `<!-- FRAME: 12:30 | 图注 -->`，时间用 `MM:SS` 或 `HH:MM:SS`，竖直线上是图注。取不到画面的占位符原样保留，`insert` 会把它列在输出的 `missing` 里。

笔记与图片在同一个文件夹里，整个文件夹可以直接搬进 Obsidian：

    temp/2026-10-08-函数对象-BV1SLaZ6FEeL/
      函数对象.md
      assets/
        函数对象-0012s.jpg

模板放工程根目录 `templates/`，现有三套：`study-notes`（教学视频笔记）、`podcast`（播客）、`meeting`（会议）。往这个目录里加 `.md` 就多一套模板。

## 运行环境检查

`ihatevideos-doctor` 一次把运行环境查一遍：Python 依赖、外部程序、ffmpeg 实际出活能力、GPU 计算、语音识别权重、B 站 cookies 与登录态、系统代理。默认跑烟测——用 `lavfi` 现造 1 秒样片，真的走一遍读流、截 jpg、截 png、抽 wav、剪一段，每步检查产物而不看 ffmpeg 的提示文本；CUDA 用一次矩阵乘确认每块卡真的能算。

```bash
uv run ihatevideos-doctor
uv run ihatevideos-doctor --only ffmpeg,gpu     # 只看指定分组
uv run ihatevideos-doctor --no-smoke            # 只做位置与版本解析
uv run ihatevideos-doctor --deep                # 额外加载两份权重跑一次识别
uv run ihatevideos-doctor --json                # 给上层 Agent 读的结构化结果
```

检查项有五种状态：`ok`、`warn`（能用但有隐患）、`missing`（找不到）、`fail`（找到了但跑不通）、`skip`（这次没测）。挡住某条命令的算必修，其余算选修；选修缺了退出码仍为 `0`，只记进 `warnings`。退出码 `0` 必修齐备、`3` 有必修未就绪、`2` 参数写错。

## Skills

各 Skill 目录下的 `SKILL.md` 是调用手册，写明命令、退出码、判断表与测试提示词。按流程串起来：输入接入、下载、媒体处理、转录、导出。

## 提交规则

见 `AGENTS.md`。改了 CLI 参数、退出码、输出格式，同步修改对应 Skill 文档。
