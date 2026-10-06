# CHANGELOG


## 0.8.0 — 2026-10-08

- 新增运行环境检查模块（`src/ihatevideos/doctor/`）与命令行 `ihatevideos-doctor`，一次把 Python 依赖、外部程序、ffmpeg 实际出活能力、GPU 计算、语音识别权重、B 站 cookies 与登录态、系统代理查一遍。
- 烟测不看程序的提示文本，只看产物：用 `lavfi` 现造 1 秒样片，依次跑 ffprobe 读流、截 jpg、截 png、抽 wav、剪一段，每步检查文件存在且能被读回；CUDA 烟测在每块卡上做一次全 1 矩阵乘并比对结果；`--deep` 真正加载两份权重并跑一次识别。
- 检查项分 `ok`、`warn`、`missing`、`fail`、`skip` 五种状态，`missing`（找不到）与 `fail`（找到了但跑不通）分开报告。挡住某条命令的算必修，其余算选修；选修缺了退出码仍为 `0`，只记进 `warnings`。
- 新增 `ffmpeg 一致性` 检查：`media` 走环境变量与 PATH，`download` 走 `temp/bin/`，两处解析结果不同时给出 `warn`。
- 输出默认是分组文本，`--json` 给出同构数据供上层 Agent 读取。`stt doctor`、`download engines`、`input cookies` 三个原有检查命令保留，`doctor` 做跨模块汇总并补上它们没覆盖的部分。

## 0.7.0 — 2026-10-08

- 重建图文笔记模块（`src/ihatevideos/summarize/`）与命令行 `ihatevideos-summarize`：`templates` 列出写作模板，`template` 打印模板正文，`frames` 按 Markdown 里的画面占位符取帧到笔记同级的 `assets/`，`insert` 把占位符换成图片引用。
- 占位符写成 `<!-- FRAME: MM:SS | 图注 -->`，时间点直接从正文里读，不用另外手写；同一个时间点重复出现只取一张图。取不到画面的占位符原样保留并记进 `missing`，部分失败时退出码为 `3`。
- 图片名是 `<笔记文件名>-<MMSS>s.jpg`，引用用相对路径加正斜杠，整个笔记文件夹可以直接搬进 Obsidian。
- 模板放工程根目录 `templates/`，随仓库提交三套：教学视频笔记、播客、会议；往该目录加 `.md` 就多一套。
- `media/frames.py` 抽出 `capture_frames(source, targets, ...)`，目标路径由调用方决定，`extract_frames` 改为调它。笔记模块复用它与 `media` 的 ffmpeg 封装。
- 本模块不加载任何模型、不联网，正文由调用它的 Agent 写。
## 0.6.0 — 2026-10-07

- 移除有监督 Agent（`ihatevideos-agent`）与对应 Skill。它做的事手动敲命令都能做到，模块没有测试，且需要工程根目录的 `config.toml`，开箱状态下启动即退出码 2。
- 一并去掉 `langchain`、`langchain-openai` 两个依赖，`langgraph`、`pydantic` 作为它们的传递依赖同时移出环境。
- `config.example.toml` 失去使用者，一并删除。
- `download` 的两处 `find_project_root` 导入改从 `ihatevideos.paths` 取，不再经过 agent 模块。

## 0.5.0 — 2026-10-07

- 移除 LLM 总结模块（`ihatevideos-summarize`）与对应 Skill，为重新设计让位。它与其它模块没有代码耦合，`langchain`、`langchain-openai` 依赖与 `agent/config.py` 模型配置保留，Agent 仍在使用。
- 语音转写的句级聚合改用识别文本的标点断句，时间从字级时间戳取：标点不再丢失，句子边界不再落在词语中间。同一个 30.7 分钟视频的句数由 113 增至 210。
- `.gitignore` 忽略本地分析产物目录 `analysis_outputs/`。

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
