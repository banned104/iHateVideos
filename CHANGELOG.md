# CHANGELOG



## 0.9.0 — 2026-10-14

- `input` 支持 YouTube：链接判定认 `watch?v=`、`shorts`、`live`、`embed`、`v` 与 `youtu.be` 短链，`Platform` 加 `YOUTUBE` 取值；频道页、首页、纯播放列表页没有视频 ID，仍按不支持的 URL 处理。
- 新增 `ihatevideos-input ytsub <url>`：只取一条字幕，按人工优先、中简 → 中繁 → 英 → 其它的顺序挑轨道，写进会话目录的 `_sub.txt`、`_sub_items.json`、`_meta.json`；没有可下载的字幕轨道时退出码 `3`。
- `resolve` 加 `--media audio|video` 与 `--height`：默认的 `audio` 命中字幕就不下媒体；`video` 是明确要视频文件（取帧用），命中字幕也照下，清晰度用 `--height` 限定（默认 1080）。输出加 `subtitle_lang` 与 `subtitle_source` 两个字段。
- `cookies` 改成按平台挑文件与校验登录态：B 站看 `SESSDATA`，YouTube 看 `LOGIN_INFO`，两份文件放同一个 `temp/config/` 目录；命令加 `--platform`，登录态检查分平台实现。
- `download` 支持只下一条语言的字幕：`--skip-download` 配 `--write-subs` 或 `--write-auto-subs`，json3 优先、vtt 兜底；字幕文件不出现在 `after_move` 输出里，用调用前后目录对比找出。
- 字幕结构改成平台无关：`BilibiliSubtitle` 与 `BilibiliSubtitleItem` 改名为 `Subtitle` 与 `SubtitleItem`，旧名字保留为别名；语言优先顺序统一成一张表。
- 依赖加 `webvtt-py`，用来解析 YouTube 的 vtt 字幕；`VideoInfo` 加 `upload_date`。
- `doctor` 加 `youtube` 分组：cookies 文件、登录态、站点可达三项，轻重与 B 站那组一致；依赖表加 `webvtt-py`，`yt-dlp` 的阻挡范围加上 `ihatevideos-input`。
- 修 `stt`：`--gpu` 默认改成第 0 块卡（RTX 4080 SUPER），第 1 块卡常被别的任务占用。
- 补测试：`tests/test_input_url_detect.py`、`tests/test_input_cookies.py`、`tests/test_input_youtube_subtitle.py` 与两个字幕样本，测试总数由 128 增至 195。
## 0.8.1 — 2026-10-08

- 修 `input`：B 站音频这次没有产出新文件时，不再拿目录里任意一份旧音频充当结果，只有标题对得上的那份会被复用。
- 修 `download`：服务器 `Content-Disposition` 给的文件名先清洗再使用；不限速时任务级选项不再写 `max-download-limit`，`--global-limit` 恢复生效；yt-dlp 输出行解析失败不再让读取线程抛出异常。
- 修 `media`：剪切产物文件名的时间标签保留到毫秒，`00m59.960s` 与 `01m00s` 不再共用一个名字。
- 修 `stt`：`--gpu` 默认用第 1 块卡，只有一块卡时写 `--gpu 0`；没有可用 CUDA 设备时给出明确提示；字符与时间戳单元对不上时按左右两侧已知单元插值，句首句尾不再出现 0。
- 修 `summarize`：`insert` 按支持的扩展名查找已有图片，取帧用了 png 也能插入；写回时保持原文换行。
- 修 `export`：`markdownlint-cli2` 改用参数列表调用，不再拼接 shell 命令；表格删列时各行补齐到同一列数。
- 修 `doctor`：权重没就绪时 `--deep` 只报一条必修；`--keep` 保留本次运行的 `temp/doctor/<时间>/`，下一次运行不再清掉它；模型加载有独立超时；`find_spec` 抛出异常时按未安装处理。
- `export` 与 `input` 两个命令补上标准输出的 UTF-8 设置，中文不再按 GBK 写出。
- 按工程约定去掉 `input`、`export` 两个模块文件开头的 docstring，出处信息改成注释。
- `requires-python` 改成 `>=3.12`，与虚拟环境一致；补上工程描述。
- 补测试：`media` 与 `export` 两个模块此前没有用例，现在有 `tests/test_media_timestamps.py` 与 `tests/test_export_timeline.py`；`stt`、`summarize`、`doctor`、`download` 各补了针对本次修复的用例，测试总数由 107 增至 128。

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
