# course-navigator 工程分析

调研对象：`F:\Codes\iHateVideos\course-navigator`，来源仓库 `Liu-Bot24/course-navigator`，MIT 许可证，克隆时的提交 `a31708a`（`--depth 1`）。

调研方式：只读阅读后端、前端、桌面启动器与文档，并在本机确认依赖与运行环境要求。没有修改任何文件，没有运行过它的服务。

## 一、它是什么

一个视频课程学习工作台。粘贴视频链接或导入本地视频，取字幕，在视频旁校阅逐字稿，把课程整理成专辑，并用大模型完成字幕翻译、课程分析（导览、大纲、解读、详解）与 ASR 字幕校正（`README.md:9-27`）。

三种使用形态：源码方式（`npm start` 起本地服务，打开 `http://127.0.0.1:15173`）、macOS 安装包与 Homebrew Cask（仅 Apple Silicon）、Windows x64 安装器。产品由三部分组成：FastAPI 后端、React 网页工作台、Tauri 桌面启动器。

## 二、工程构成

| 部分 | 位置 | 内容 |
|---|---|---|
| 后端 | `backend/course_navigator/` | 13 个模块，`app.py`（134KB，全部路由与任务框架）、`ai.py`（132KB，模型调用与提示词）、`ytdlp.py`（51KB，下载与本地识别）、`asr.py`（43KB，校正链路）、`online_asr.py`（22KB，在线识别）、`models.py`、`config.py`、`library.py`、`subtitles.py`、`cookies.py`、`processes.py` |
| 后端测试 | `backend/tests/` | `test_app.py`（154KB）、`test_ai.py`（67KB）、`test_ytdlp.py`（63KB）、`test_asr.py`（16KB）等 7 个文件 |
| 网页工作台 | `frontend/src/` | `App.tsx`（335KB）、`api.ts`、`asrWorkbench.ts`、`subtitleUpload.ts`、`utils.ts`、`types.ts` 与对应测试，React 19 + TypeScript + Vite 7 |
| 桌面启动器 | `launcher/` | Tauri 2，Rust 侧 `runtime.rs`（64KB）、`model_config.rs`、`config.rs`、`workspace.rs`、`asr_cache.rs`、`lib.rs`；界面 `App.tsx` |
| 构建与分发 | `scripts/`、`Casks/` | `prepare-runtime-source.mjs`（打包运行源码与内置工具）、`build-mac-dmg.sh`、`start.sh`、Homebrew Cask |
| 文档 | `README.md`、`README.en.md`、`docs/` | 使用说明、macOS 安装说明、`docs/prompts.zh.md`（内置提示词中文审阅稿） |

Python 依赖（`pyproject.toml`）：`fastapi`、`httpx`、`opencc-python-reimplemented`、`openai-whisper`、`pydantic`、`python-dotenv`、`python-multipart`、`uvicorn[standard]`、`yt-dlp`，要求 Python 3.11 以上；开发组是 `pytest` 与 `pytest-asyncio`。外部程序需要 `ffmpeg` 与 `ffprobe`、`node`（yt-dlp 的 JS 运行时）、`whisper`。

## 三、字幕与语音识别链路

这里有一处容易误判的地方：`asr.py` 里没有识别引擎，它是大模型二次校正模块。本地识别写在 `ytdlp.py` 的 `_run_whisper_asr`，在线识别在 `online_asr.py`，字幕文本解析在 `subtitles.py`。

### 三种字幕来源与回退

字幕来源取值四种（`models.py:12`，`ExtractRequest.subtitle_source` 默认 `subtitles`）：

| 来源 | 行为 |
|---|---|
| 原字幕优先（`subtitles`，默认） | 先让 yt-dlp 取平台字幕，缺失或失败时回退本地 ASR |
| 本地 ASR（`asr`） | 只用本机 whisper |
| 在线 ASR（`online_asr`） | 只用已配置的在线服务 |
| 本地上传（`imported`） | 使用已有的 TXT、MD、SRT、VTT 文本文件 |

回退只在默认模式下发生：在线 ASR 报错或返回空时把错误累积进 `fallback_errors`，继续调用本地 ASR，两条都失败时把两段错误合并成一条消息抛出（`app.py:2290-2395`）。用户显式选择在线 ASR 时失败直接上抛。

### 本地识别

引擎是 `openai-whisper`（PyTorch 实现），以子进程方式调用外部可执行文件：`whisper <音频> --model base --output_format vtt --output_dir <目录>`（`ytdlp.py:1050-1118`）。三点值得注意：

- 模型写死为 `base`，源码里没有 `--device`、`--fp16`、`--beam_size` 等参数，界面与环境变量都不提供切换，即模型不可选
- 唯一可配的是可执行文件来源：环境变量 `COURSE_NAVIGATOR_WHISPER_BINARY`，否则依次在 `PATH`、当前解释器同目录、其上级的 `bin`/`Scripts`、工程 `.venv` 下查找，Windows 额外尝试 `.exe`、`.cmd`、`.bat` 后缀
- 权重下载与缓存交给 openai-whisper 自身的默认行为（首次运行下到用户主目录缓存），工程不干预

音频预处理：本地视频文件用 `ffmpeg -y -i <视频> -vn -ac 1 -ar 16000`，URL 来源交给 yt-dlp 的 `--extract-audio --audio-format wav`；整段交给 whisper，不切块。识别产物是 VTT，读回后用 `subtitles.py` 解析，中文再经 OpenCC 转简体。

### 在线识别

四种服务商（`online_asr.py:371-388`）：

| 服务商 | 端点 | 默认模型 |
|---|---|---|
| `openai` | `https://api.openai.com/v1` + `/audio/transcriptions` | `whisper-1` |
| `groq` | `https://api.groq.com/openai/v1` + `/audio/transcriptions` | `whisper-large-v3-turbo` |
| `xai` | `https://api.x.ai/v1` + `/stt` | `grok-2-voice-1212` |
| `custom` | 用户填写 | 用户填写 |

认证是 `Authorization: Bearer`，密钥从环境变量读取，并支持回落变量（`OPENAI_API_KEY`、`GROQ_API_KEY`、`XAI_API_KEY`）。未显式指定服务商时按 `xai` → `openai` → `groq` → `custom` 选第一个有密钥的，都没有则为 `none`（`config.py:251-283`）。

分块策略（这是最值得参考的一段，`online_asr.py:31-33,178-223`）：音频先转成 64kbps 单声道 16kHz 的 mp3；不超过 20MB 时单块直传，超过时按文件大小估算块数 `min(24, max(2, ceil(大小/20MB)))`，每块时长等于总时长除以块数，首块之后向前、末块之后向后各扩 5 秒作为重叠，用 `ffmpeg -ss/-t` 切成 `part-NNN.mp3` 后**串行**逐块请求，单块超时 300 秒。合并时给每块时间戳加上偏移，再按 `(取整后的起始秒, 文本)` 去掉相邻重复（`online_asr.py:556-576`）。遇到 413 这类体积超限错误没有自动缩小重试的逻辑。

### 字幕文本与时间戳

三种来源的文本都经过同一个解析函数 `subtitles.py` 的 `parse_subtitle_text`。滚动字幕有两步处理（`subtitles.py:69-104`）：起始时间相差不超过 0.2 秒且文本互为前缀的相邻条目只保留更长的一条；再逐条把与前一条重复的词组裁掉，只从词数不少于 3 的重叠开始裁。

在线识别的分段：优先取返回结构里的 `segments`/`results`/`chunks`；没有分段时退到 `words`，按「累计字符数不少于 32」「与上一个词的间隔不少于 0.8 秒」「段跨度不少于 7 秒」三个条件切段，含中日韩字符时直接拼接，否则用空格连接（`online_asr.py:485-549`）。整段纯文本且没有时间戳时直接报错。

持久化结构只有 `{start, end, text}` 三个字段（`models.py:31-34`），与 `transcript_source` 一起写入 `<数据目录>/items/<条目 id>.json`，写入方式先写 `.tmp` 再 `replace`（`library.py:25-33`）。字级时间戳不保存，只在分段计算里用；应用播放用的 WebVTT 是前端从 transcript 现场拼出的字符串，工程里没有导出 SRT 的代码路径。

### 进度、取消与缓存清理

进度是「阶段名 + 百分比 + 文案」三段信息，百分比夹在 1 到 99；阶段包括 `metadata`、`subtitles`、`asr`、`online_asr`、`saving`。本地 whisper 每 2 秒上报一次，进度从 40 升到 88；在线识别按块在 42 到 88 之间上报。

取消有三种机制配合：回调里检查取消标记并抛出 `JobCancelled`；子进程由守护线程每 0.25 秒轮询，先 `terminate()`、5 秒后 `kill()`；`httpx` 请求通过后台线程关闭客户端来中断。线程池三个：学习材料 2 个工作线程，下载与字幕提取各 1 个，应用关闭时 `cancel_futures=True`。

音频与 VTT 保留在 `<数据目录>/subtitles/<条目 id>/` 作为缓存，不在识别结束后删除。缓存超过 500MB 时自动清理，只删音频后缀（`.aac`、`.flac`、`.m4a`、`.mp3`、`.opus`、`.wav`、`.webm`），字幕文本保留；开关持久化在 `.env`，桌面启动器读同一个变量并与后端同步。

## 四、大模型与提示词体系

模型档案库是这套设计里最值得借鉴的部分（`README.md:102-121`、`config.py:191-208`）：

- 每个档案有 `id`、`name`、`provider_type`、`base_url`、`model`、`context_window`、`max_tokens`、`api_key`
- 支持两种接口格式：OpenAI 兼容与 Anthropic
- 四个任务槽位各指向一个档案：字幕模型（字幕与标题翻译）、学习模型（解读与详解）、结构模型（上下文摘要、语义分块、导览、大纲）、ASR 校正模型
- 档案里的 `context_window` 用来决定字幕分片的颗粒度，`temperature` 与 `max_tokens` 是该档案的默认调用参数
- 界面只回显密钥是否已配置与掩码，留空保存时沿用旧值

内置提示词分六类（`docs/prompts.zh.md`）：短字幕整体生成、翻译上下文摘要、字幕分片翻译、学习块生成、层级大纲生成、学习导览生成。几处约定的写法值得照搬：

- 翻译类提示词硬性要求保持字幕段数、顺序与起止时间完全一致，不允许总结、合并、省略
- 学习块提示词约定 `priority` 取 `focus`/`skim`/`skip`/`review`，`high_fidelity_text` 必须保留铺垫、论点、推理链、数字、定义、步骤、转折，并且「宁可细分，也不要过早压缩」
- 大纲提示词要求节点 id 里带上来源学习块的 id，便于校准时间戳
- 全部要求返回严格 JSON，AI 补充的背景知识只允许放在预备知识与复习建议里，不许混进课程事实

模型调用侧：学习块生成最多 3 个并发（`COURSE_NAVIGATOR_LEARNING_BLOCK_WORKERS`），重试默认 3 次（`COURSE_NAVIGATOR_LLM_RETRY_ATTEMPTS`），HTTP 超时按调用类型取 60 到 240 秒。

事实核对：`docs/prompts.zh.md` 里第一节「短字幕整体生成」在 `ai.py` 中没有对应实现，其余五节与代码一致。

## 五、ASR 校正工作台

处理自动识别字幕的专门流程，`asr.py` 与前端 `asrWorkbench.ts` 配合（`README.md:217-237`）：

- 用户可以添加术语、人名、产品名与常见识别错误作为参考信息
- 模型给出定点修改建议，界面并排显示原文与修改后预览，高亮处悬停看理由与证据，按置信度排序，支持一键接受高于阈值的建议与接受后自动保存
- 可选开启搜索校验（Tavily、官方 Firecrawl 或自托管 Firecrawl）为候选项提供外部证据
- 接受后的修改可以保存回工作台作为主字幕

实现上的几个细节：候选提取按批处理（测试用例记录 4300 段字幕产生 12 批候选调用与 1 次审核调用，90 段只做 1 批）；搜索返回的原始片段先归纳成背景卡片再进入审核提示词，原始片段不直接拼进去；模型返回残缺 JSON 时触发一次修复调用；`corrected_text` 是乱码的建议被丢弃；提示词里写明不要展开有效简称，模型仍把简称判为错误时该补丁被丢弃。进度走 6 秒心跳，阶段包括 `candidate`、`search`、`background`、`review`、`model_wait`、`model_parse`。

## 六、下载与视频访问

yt-dlp 作为 Python 依赖安装（不单独维护可执行文件）。视频访问三种模式：普通模式、复用浏览器登录状态（默认 `chrome`，可指定 `chrome:Default`、`chrome:Profile 1`、`safari`、`firefox`、`edge` 等）、Cookies 文件。浏览器登录状态由 yt-dlp 的 `--cookies-from-browser` 承担，浏览器 Cookie 快照用临时目录存放并在结束时清掉。字幕语言与自动字幕可用性取决于 yt-dlp 与平台本身。

下载失败时会删除本次写入的文件；重新抓平台字幕前先清掉目录里已有的 VTT 与 SRT。

## 七、数据存储与目录约定

两类目录分开（`README.md:126-127`、`config.py:169-170`）：

- 课程资料 Workspace（默认 `course-navigator-workspace`，安装版在 `~/Library/Application Support/Course Navigator/Workspace`）：`items/<条目 id>.json`、`library-state.json`、导入与缓存的视频在 `downloads/`
- 本地运行数据目录（默认 `.course-navigator`）：`cookies/`（手工导入的 cookies 写入后尝试 `chmod 600`）、`subtitles/<条目 id>/`

课程包分享用一份 `course-navigator-share` 格式的 JSON，导入导出的内容包括校正字幕、翻译字幕、AI 学习材料、留言、专辑名称与课程顺序。启动时会做一次数据修补（规范化视频路径、回填字段、为本地视频条目补时长）；旧版本把 `items` 与 `downloads` 放在运行数据目录，启动时迁移到 Workspace。

## 八、进程管理与任务框架

`processes.py` 只有三个职责，写法干净：把 `COURSE_NAVIGATOR_RUNTIME_TOOL_PATHS` 与 `/opt/homebrew/bin`、`/usr/local/bin` 前置到子进程 `PATH`；用 `shutil.which` 在该 `PATH` 中查找工具；Windows 下统一加 `CREATE_NO_WINDOW` 与 `STARTUPINFO(SW_HIDE)` 隐藏窗口。yt-dlp、ffmpeg、whisper 全部经这一层启动。

任务框架在内存里：任务状态字典与若干集合（可取消、已取消、结果）由锁保护，状态机取值 `queued`、`running`、`cancelling`、`cancelled`、`succeeded`、`failed`，每步更新都盖时间戳。任务只在提交前建记录再入线程池，取消时排队中的直接置 `cancelled`、运行中的置 `cancelling`，实际终止靠上面三种协作式机制。取消与失败后学习材料回滚到任务开始前的状态，条目已被删除时跳过。

已知缺口：任务状态只在内存，进程重启后全部丢失，没有续跑机制；学习材料任务没有超时限制，只有取消入口；没有独立的残留进程回收器。

## 九、测试体系

`pytest` 与 `pytest-asyncio`，测试目录由 `pyproject.toml` 指定为 `backend/tests`。后端测试文件体量很大（`test_app.py` 154KB、`test_ai.py` 67KB、`test_ytdlp.py` 63KB），覆盖字幕来源回退、ASR 缓存清理、校正任务的取消与结果、whisper 调用与进度、在线识别的压缩分块与两种时间戳解析、提示词的 JSON 修复与乱码丢弃。前端用 vitest 与 `@testing-library/react` 加 jsdom。

发布流程没有 CI，靠手工执行打包脚本。

## 十、桌面壳、运行时与分发

Tauri 启动器的做法有几处值得参考：

- 不要求用户装 Python，改用随包内置的 `uv`：`uv sync` 建虚拟环境，服务命令是 `uv run uvicorn course_navigator.app:app --app-dir backend`
- 内置 Node 与 npm（不在打包时单独装 Python）、`uv`、`ffmpeg` 与 `ffprobe`，打包脚本按平台下载：macOS 从 npm 包取二进制，Windows 用 gyan.dev 的压缩包；工具目录通过环境变量注入后端，后端再前置到子进程 `PATH`
- 依赖状态用标记文件加运行源码的递归摘要比对，决定是否需要重新安装依赖
- 启动前检测端口占用并自动换端口，把结果写回配置与环境文件
- Workspace 迁移分四步：出计划、校验新旧路径不互为上下级、复制、逐项校验，最后才删除旧目录
- 停止服务前核对进程的命令行、工作目录与端口，识别不出就不动，避免误杀其他程序

分发：macOS 用 ad-hoc 签名生成 DMG（明确不公证），Homebrew Cask 只提供 Apple Silicon，首次打开需要用户在系统设置里选择「仍要打开」；Windows 用 NSIS，安装前用 PowerShell 结束正在运行的旧进程；发布产物同时提供 `.sha256`。运行源码整份作为资源随包分发，安装后仍然启动 Vite 开发服务器。

## 十一、隐私与安全做法

写清边界、默认本地：只监听环回地址，没有遥测与产品分析；文档明确列出哪些操作会把字幕文本或搜索查询发给哪个服务；密钥只存在本机环境文件里，接口只回显掩码；cookies 写入后收紧权限；CORS 白名单由配置的网页地址推导；打包时剔除 `.env`、虚拟环境、依赖目录与工作区，运行源码更新时保留用户的 `.env` 与依赖目录；`SECURITY.md` 给出漏洞披露渠道与「怀疑泄露先轮换密钥」的处置建议。

事实陈述的缺口：HTTP 接口没有任何鉴权，安全边界只是绑定环回地址；密钥以明文保存在环境文件；下载的内置工具没有校验和校验；分发产物只有 ad-hoc 签名。

## 十二、与本工程的结合点

把它与 iHateVideos 放在一起看，可以直接参考的部分按价值排序：

1. **在线 ASR 的分块与合并**：20MB 上限、64kbps 单声道压缩、5 秒重叠、块数按体积估算、偏移回填、按起止时间与文本去重。本工程的 `media` 模块已经有分块能力，缺的是这一段策略与合并规则。
2. **三种字幕来源与回退顺序**：原字幕优先、失败回退本地识别、显式选择时不回退。本工程已有 B 站原生字幕优先的思路，对照品是这套更明确的回退语义与错误合并方式。
3. **字幕文本清洗**：滚动字幕的前缀去重与重复词组裁切。本工程目前只处理平台原生字幕，接入 ASR 后一定会遇到这类问题。
4. **ASR 校正工作台**：术语参考、分批候选、搜索证据、置信度排序、批量接受、接收后保存。这是本工程完全没有的一块，也是与「把视频变成可检索文字」这条主线最贴合的一块。
5. **模型档案库与任务槽位**：多档案、两种接口格式、按任务分配、上下文窗口决定分片颗粒度。本工程目前只有一个 `[model]` 段，被 Agent 与 summarize 共用。
6. **提示词约定**：翻译保持段数与时间不变、学习块保留推理链、大纲节点带来源块 id、严格 JSON 与背景知识隔离。本工程 `summarize` 的四个预设可以照这套约定补齐。
7. **任务框架**：任务状态机、阶段化进度、三种协作式取消机制、失败回滚。本工程的 Agent 是同步的，媒体命令也是前台执行，如果要做长任务（识别、批量处理），这套结构是现成的参照。
8. **进程与工具定位**：PATH 注入、Windows 隐藏窗口、进程树终止、可执行文件多级回退。本工程 `media/ffmpeg.py` 已有定位逻辑，可对照补齐可执行文件回退与隐藏窗口。
9. **缓存策略**：过程音频按阈值自动清理、只删音频保留文本、开关持久化并前后端同步。本工程 `temp/` 现在没有容量管理。
10. **测试体系**：pytest 加大量用例、前端 vitest。本工程没有测试目录，`docs/audit/risks.md` 的 R10 记录了这一点。
11. **简体化**：OpenCC 转简体。本工程 `TODO.md` 有语言优先级的待办，这套做法可以直接用。
12. **数据目录分层**：课程资料与运行数据分开，迁移有校验流程。本工程只有 `temp/` 一层。

需要注意的差别：这个工程的重心是「带界面的学习工作台」，本工程的重心是「命令行工具加有监督 Agent」；它的本地识别停在 whisper `base` 且模型不可选，中文长音频的识别质量与可选性都不如 FunASR 方案（见 `funasr.md`）。可借鉴的是流程与工程结构，识别引擎本身另做选型。

## 十三、需要决定的事项

1. 识别引擎选哪条路：这个工程的 openai-whisper 子进程方案（实现简单、模型不可选）与 FunASR 的多模型方案（能力强、依赖更重），或者两者都留成可选
2. 是否引入任务框架：把识别做成带进度与取消的后台任务，还是保持一步一命令的前台执行
3. 字幕来源与回退语义：是否照这套「原字幕优先、失败回退识别、显式选择不回退」的规则，替换或补充本工程现有约定
4. ASR 校正是否纳入范围：纳入的话是做成独立命令，还是接进 Agent 的流程
5. 模型配置形态：是否从单个 `[model]` 扩展成档案库加任务槽位，还是保持单一配置
6. 数据目录是否分层：`temp/` 与课程资料目录分开，还是继续只用 `temp/`
7. 是否引入测试依赖并建立测试目录
