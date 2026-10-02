# CHANGELOG

## 0.4.0 — 2026-10-02

- 下载模块（`src/ihatevideos/download/`）与命令行 `ihatevideos-download`：aria2c 直链下载（多线程分段、断点续传、限速、崩溃退避重启），yt-dlp 视频下载（信息树解析、格式与字幕清单、清晰度短标、合流、抽音频、经 aria2c 加速与失败回退）。任务记录里的 `format_id` 是 yt-dlp 实际选中的格式，yt-dlp 关于「哪些格式拿不到」（例如需要大会员）的提示原样透出。
- 依赖一条命令装齐 aria2c、ffmpeg、yt-dlp；`setup-binaries` 把 uv 取不到的 ffprobe 取回项目内的 `temp/bin/`，只写项目目录，不改系统任何位置。
- 下载子进程跟随系统代理，`--no-proxy` 可显式直连。
- Agent 的命令白名单增加 `ihatevideos-download` 的五个子命令。

## 0.3.0 — 2026-09-21

- LLM 总结模块（`ihatevideos-summarize`）：转录 Markdown 转总结，评论 Markdown 的观点追加到总结末尾，内置金融时间线、通用总结、学习笔记、投资播客四个预设。
- 媒体处理工具（`ihatevideos-media`）：读流信息与时长、按时间点取画面、按时间段剪切视频与音频、提取音轨与按时长分块。
- Agent 的命令白名单增加 `ihatevideos-media` 的四个子命令。

## 0.2.0 — 2026-09-21

- 有监督 Agent：终端启动，登录态预检，写 temp 外当场审批（`ihatevideos-agent`）。
- 模型配置：根目录 `config.toml`（`config.example.toml` 为模板，真实值不提交）。

## 0.1.3 — 2026-09-21

- 评论默认 10 条主评论、每条子评论最多 10 条（`--reply-limit` 可调）。

## 0.1.2 — 2026-09-21

- 字幕中间产物进会话目录：`temp/<日期>-<标题>-<BV号>/`，`subtitle` 默认写 temp，已存在加序号不覆盖。

## 0.1.1 — 2026-09-21

- B 站登录态：浏览器 Cookie 导入与状态检查（`cookies --file/--check`），只走 Cookie，不做扫码登录。
- 字幕落文件：`subtitle` 命令直出文本与时间轴 JSON，`input` Skill 给出三步端到端流程。
- 修复 GBK 控制台下 `bili` 输出宽字符崩死导致字幕误判缺失。

## 0.1.0 — 2026-09-20

- 多平台输入：B 站（含原生字幕优先）/小宇宙/喜马拉雅/本地文件统一接入（`ihatevideos-input`）。
- 内容导出：转录 JSON 转原文 Markdown、总结表格、 B 站时间线（`ihatevideos-export`）。
- 首批随工程 Skill：`ihatevideos-input`、`ihatevideos-export`（通用工具 Skill 留本地 `.agents/`，不进仓库）。
