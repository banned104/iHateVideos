# iHateVideos

Python 工具集合：把视频变成可检索的文字。Python 版本使用 uv 管理（`pyproject.toml`）。

## 目录组成

- `src/ihatevideos/input/`：多平台输入。B 站（含原生字幕优先）/小宇宙/喜马拉雅/本地文件，统一输出音频路径、元数据、资源编号。
- `src/ihatevideos/export/`：内容导出。转录 JSON 转原文 Markdown，总结转干净表格与 B 站时间线。
- `src/ihatevideos/media/`：本地音视频处理。ffprobe 读流信息与时长，ffmpeg 取画面、剪切视频与音频、提取音轨与分块（`ihatevideos-media`）。
- `src/ihatevideos/download/`：下载。aria2c 直链（多线程分段、断点续传、限速），yt-dlp 视频（格式与字幕清单、合流、抽音频、经 aria2c 加速与失败回退），`setup-binaries` 取回 uv 装不进来的 ffprobe（`ihatevideos-download`）。
- `src/ihatevideos/stt/`：本地语音转写。Qwen3-ASR-1.7B 出文字，Qwen3-ForcedAligner-0.6B 出字级时间戳，句级结果直接交给 `ihatevideos-export`（`ihatevideos-stt`）。权重放工程根目录 `models/`，不进版本库。
- `src/ihatevideos/agent/`：有监督 Agent（LangChain）。终端启动，按流程调用上面两个模块，写 temp 外暂停审批。
- `skills/`：随仓库提交的工程 Skills（`ihatevideos-input`、`ihatevideos-export`、`ihatevideos-agent`、`ihatevideos-media`、`ihatevideos-download`、`ihatevideos-stt`）。
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
```

## 语音转写权重

`ihatevideos-stt` 需要两份模型权重，体积大，不进版本库，首次使用前自己下载到工程根目录 `models/`：

```bash
uv run huggingface-cli download Qwen/Qwen3-ASR-1.7B --local-dir models/Qwen3-ASR-1.7B
uv run huggingface-cli download Qwen/Qwen3-ForcedAligner-0.6B --local-dir models/Qwen3-ForcedAligner-0.6B
```

国内网络慢可以把 `huggingface-cli download` 换成 `modelscope download --model <模型名> --local_dir <目录>`。
下完跑 `uv run ihatevideos-stt doctor`，`ready` 为 `true` 就能用。详细说明见 `skills/ihatevideos-stt/SKILL.md`。

## Agent

```bash
uv run ihatevideos-agent run --url "<B站链接>"
```

启动有监督会话：先检查登录态（缺失就在终端提示用户粘 Cookie），执行中写 temp 外当场 y/n 审批，结束打印 JSON（含 `session_dir`）。模型配置：复制 `config.example.toml` 到根目录 `config.toml` 再填真实值（`[model]` 下 `api_base`、`api_key`、`model`，OpenAI 兼容接口，不提交）。调用手册见 `skills/ihatevideos-agent/SKILL.md`。

## B 站登录态

B 站字幕接口只对登录态返回：

1. 在浏览器登录 B 站，用 Cookie 导出扩展（例如 Get cookies.txt LOCALLY）导出 Netscape 格式。
2. 把导出的文件复制到 `temp/config/`，文件名随意，程序自己会找（多份时取最近修改的那份）。
3. 运行 `uv run ihatevideos-input cookies`，`login` 为 `true` 表示可用。

文件只放在工程内，不写用户主目录，删除工程即可清除。cookies 失效时重新导出一份覆盖进去即可。

`cookies` 会用这份文件调一次 B 站登录接口：`login: true` 表示服务端仍认；`false` 时 `detail` 给出原因（没有文件、目录里没有可用的 cookies、B 站返回的错误码、或这份 cookies 已失效）。不要把 SESSDATA 的值贴到聊天里，密钥只留在本地文件。

## Skills

Agent 开发看各 Skill 目录下的 `SKILL.md`。大 Skill 按流程调用小 Skill：输入接入、下载、媒体处理、转录、导出。

## 提交规则

见 `AGENTS.md`。改了 CLI 参数、退出码、输出格式，同步修改对应 Skill 文档。
