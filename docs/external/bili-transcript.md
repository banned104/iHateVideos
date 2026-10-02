# BiliTranscript 工程分析

调研对象：`F:\Codes\iHateVideos\BiliTranscript`，来源仓库 `W1nge/BiliTranscript`，MIT 许可证，提交 `e085c64`（Release BiliTranscript 1.0.0，2026-09-20）。

调研方式：只读阅读全部 Python 模块、原生 C# 工程、打包脚本、测试与文档，并在本机核对依赖声明与运行要求。没有修改任何文件，没有运行过它的界面与服务。

## 一、它是什么

一个只做 B 站视频文稿提取的 Windows 桌面应用。作者在开头写明了范围边界：没有摘要、笔记、评论分析或知识库归档，粘贴链接就提取全部分P、预览并导出，另外通过局域网 REST 接口被其他软件调用（`README.md:3`）。

技术选择上有两条鲜明的原则：B 站与 API 请求只用 Python 标准库（`requirements.txt` 里只有 `PySide6-Essentials` 与 `shiboken6`，没有任何 HTTP 库），本地语音识别放在独立的 Python 进程里运行（`README.md:193`）。Python 版本要求 3.11 到 3.13。

## 二、工程构成

| 部分 | 位置 | 内容 |
|---|---|---|
| B 站数据层 | `bilibili.py`（15KB） | 编号与链接解析、三条字幕接口、播放地址、音频下载、用 `urllib` 自写的传输层与错误映射 |
| 提取编排 | `extractor.py`（27KB） | 固定降级路线、重试策略、ASR 后备、分P进度与失败隔离 |
| 浏览器桥接 | `browser_bridge.py`（20KB） | 独立浏览器启动、自写 CDP WebSocket 客户端、页面内取字幕轨道 |
| 语音识别 | `asr.py`、`asr_worker.py`、`asr_api.py` | 本地引擎探测与子进程编排、无界面依赖的推理进程、OpenAI 兼容 API 客户端 |
| 界面 | `modern_window.py`（125KB）、`styles.py`、`workers.py`、`settings_model.py` | PySide6 三页式界面、样式表、7 个 QThread 任务类、设置读写 |
| 原生层 | `native/windows_backdrop/`、`bilitranscript_app/native/win-x64/` | .NET 8 的 Acrylic 背景层与随包分发的 DLL |
| 本地 API | `api_server.py`（34KB）、`API.md` | 局域网提取接口，Bearer 鉴权，异步任务 |
| 数据 | `history.py`、`models.py` | SQLite 历史库、分段与导出结构 |
| 打包 | `BiliTranscript.spec`、`installer/`、`build*.bat` | PyInstaller、Inno Setup、三个构建脚本 |
| 测试 | `tests/`（13 个文件）、`tools/` | 标准库 `unittest`，两个端到端脚本 |

## 三、字幕获取的固定降级链

这是整个工程最核心的设计，五个步骤按固定顺序执行，不依赖外部浏览器扩展（`README.md:9-27`、`extractor.py`）：

| 顺序 | 路线 | 接口 |
|---|---|---|
| 1 | 公开字幕 | `/x/player/v2?bvid=&cid=` |
| 2 | 匿名接口 | `/x/player/wbi/v2?bvid=&cid=&aid=` |
| 3 | 专用登录浏览器 | 浏览器页面内请求同一个 `/x/player/wbi/v2` |
| 4 | 本地或 API 语音识别 | 下载音频后转写 |
| 5 | 清理 | 只保留文稿，临时音频任务结束即删除 |

第 2 步存在的原因是公开接口有时只给出 `ai-zh` 的元数据而没有下载地址。每个来源最多尝试 2 次，失败后固定等待 1 秒再试，第二次仍失败才进入下一个来源；重试时会重新探测一次，以便拿到刷新后的字幕地址。字幕正文下载失败或正文为空同样计入这次重试。

结果按固定优先级挑选：人工中文字幕 → B 站中文 AI 字幕 → 其他 B 站字幕 → 本地语音识别。语言排序的实现是两级分组，先按「中文非 AI、中文 AI、非中文非 AI、非中文 AI」分组，组内再按语言标签的权重（`zh-cn`、`zh-hans`、`zh`、`ai-zh`、`zh-hant`、`zh-tw`）。公开英文字幕只暂存为后备，不会挡住后面的匿名或登录浏览器中的中文 AI 字幕。

界面提供五种模式：智能提取、只用公开字幕、只用匿名接口、只用登录浏览器、只用 ASR。手动模式不会降级到其他来源，例如选「只用匿名接口」时不会请求公开字幕、登录浏览器或 ASR。来源诊断功能会真正检测全部分P，分别显示公开、匿名、登录、ASR 四条路线是否可用，给出实际尝试次数、可下载字幕数量和失败原因，检测可随时取消。

## 四、用浏览器承担登录态的做法

这一段的思路值得单独说明：应用**不读取、不解密、不复制任何 Cookie**（`README.md:27`、`browser_bridge.py`）。

它用 Chrome DevTools 协议启动一个独立的浏览器进程：

- 启动参数是 `--remote-debugging-port=39271`、`--user-data-dir=%LOCALAPPDATA%\BiliTranscript\browser-profile`、`--no-first-run`、`--no-default-browser-check`
- 依次探测 Edge、Chrome、Brave 的安装路径，取第一个找到的；浏览器配置目录与用户日常浏览器完全分开
- Python 侧用一个自写的 RFC 6455 WebSocket 客户端（仍在标准库里实现）连接调试端口，只接受 `ws://127.0.0.1`、`localhost`、`::1`
- 真正的请求发生在 B 站页面里：通过 `Runtime.evaluate` 执行 `fetch(..., {credentials:'include'})`，由浏览器自己带上登录态，Python 只接收返回的字幕轨道
- 登录状态通过页面请求 `/x/web-interface/nav` 读 `isLogin` 与用户名判断，打开应用后自动启动浏览器并轮询检查（默认每 3 秒一次，最多 200 次，确认登录后立即停止）
- 批量任务共用同一个浏览器与端口，浏览器路线用模块级锁串行化，公开与匿名路线保持并行

对比常见的 Cookie 文件方案：这边省掉了让用户手工导出 cookies.txt 的步骤，代价是依赖一个特定的桌面浏览器与调试端口，且该浏览器窗口需要保持打开。

## 五、B 站接口层的写法

- 编号与链接解析：BV 号、av 号、完整链接、`b23.tv` 短链（先取重定向再递归解析），主机名白名单只允许 `bilibili.com`、`www.bilibili.com`、`m.bilibili.com`、`b23.tv`
- 元数据只取一次 `/x/web-interface/view`，字段包括标题、UP 主、时长、封面、发布时间、简介与分P列表；分P取 `page`、`cid`、`part`、`duration`
- 音频地址来自 `/x/player/playurl?qn=16&fnval=16&fourk=1`，从 `dash.audio` 里按带宽取最大的一条，没有时退回 `durl`；下载先写 `.part` 临时文件再替换，512KB 分块
- 没有任何 WBI 签名实现（`w_rid`、`wts`、`img_key` 之类都不存在）。需要凭据的请求全部交给专用浏览器，Python 侧只带 UA、Referer、`Accept-Language`
- 媒体地址在下载前做白名单校验：必须是 https，主机名须属于 B 站的几个域名后缀之一
- 超时分三档：取 JSON 30 秒、解析短链 15 秒、下载音频 60 秒
- 传输层自带状态码重试参数，但生产路径一律用 `retries=0`，隐式重试被刻意关掉，重试统一由上层的来源策略负责（0.3.0 的更新记录专门写了这一条）
- 错误映射给出具体原因：HTTP 412 提示「B站拒绝了当前请求，请稍后重试或切换网络」，接口码 `-404` 提示找不到视频，`-101`、`-400`、`-403` 提示暂不允许访问该内容

## 六、语音识别链路

四种后端：`faster-whisper`、`funasr`、`openai-whisper`，以及 OpenAI 兼容的 HTTP 接口（`asr.py`、`asr_worker.py`、`asr_api.py`）。

本地引擎的运行方式：`asr_worker.py` 是一个不依赖 PySide6 的独立脚本，由 `asr.py` 用 `subprocess.Popen` 启动，标准输出逐行输出 JSON 事件，父进程解析事件并读回结果文件。这样设计的直接好处是打包后的界面可以调用机器上任意一个已经装好识别库的 Python（探测顺序是首选解释器、当前解释器、`PATH` 上的 `python`、`python3`，每个都用 `asr_worker.py --probe` 探测，超时 12 秒）。应用自身不携带模型，也不把 torch 之类写进依赖，模型由对应的识别库在首次使用时下载到各自的默认缓存目录。

各后端的默认值与细节：

| 后端 | 默认模型 | 量化与设备 | 备注 |
|---|---|---|---|
| faster-whisper | `small` | `auto` 时 CUDA 用 `float16`、CPU 用 `int8` | 推荐项，能直接读下载的音频，内部用 `vad_filter=True` 处理静音 |
| FunASR | `iic/SenseVoiceSmall` | 同上 | 固定带 `vad_model="fsmn-vad"`，时间戳只能给出整段起止 |
| OpenAI Whisper | `base`（界面默认填 `small`） | 同上 | 需要 `ffmpeg` |
| OpenAI 兼容 API | `mimo-asr` | 不适用 | 默认 `http://127.0.0.1:8765/v1`，密钥 `local`，语言 `zh` |

设备与量化没有界面控件，命令行也不传，实际始终是自动选择（先看 `torch.cuda.is_available()`，再看 `ctranslate2.get_cuda_device_count()`，都不可用则 CPU）。后端与模型是设置项，模型是自由文本输入，按后端分别保存。

音频处理只有一组参数：`ffmpeg -hide_banner -loglevel error -y -i <输入> -ar 16000 -ac 1 <输出 wav>`。FunASR 与 OpenAI Whisper 必定转换；API 接口只对不在允许后缀列表里的文件转换，`.m4s` 会命中；faster-whisper 直接用下载的音频。整段音频一次交给引擎，不做分块与重叠。

进度按阶段映射：音频下载占 0 到 35，识别占 40 到 100，再按分P数量折算成全局百分比。faster-whisper 用当前分段的结束时间除以总时长计算进度，FunASR 与 OpenAI Whisper 只有起点与终点的固定值。取消时子进程先 `terminate()`、等待 3 秒再 `kill()`；ffmpeg 转换只 `terminate()`；API 请求通过关闭套接字中断。所有中间文件（下载的音频、转换出的 WAV、识别结果 JSON）都放在一个临时目录里，任务结束或取消时随目录一起删除。

OpenAI 兼容接口的做法：用 `http.client` 自己拼 multipart，提交字段为 `file`、`model`、`language`、`response_format=verbose_json`，同时兼容只返回 `text` 的服务；因为上游服务一次只处理一个请求，应用内用模块级锁把 API 转录串行化；总超时 1 小时，健康检查 8 秒，连接 15 秒。自动模式下本地引擎不可用时才尝试 API，手动选择 API 时不会启动本地识别。

错误提示的颗粒度值得参考：没有找到任何可用环境时提示安装哪个库；指定后端未安装时把已检测到的后端列表一并给出；缺少 `ffmpeg` 时分两种场景给出不同提示（本地引擎与 API 接口）；连接被拒（`WinError 10061`）时给出上游服务的启动条件与 `/health` 检查命令。

## 七、结果结构与导出

数据模型是三层：`Segment`（起始、结束、文本）、`PartTranscript`（分P的编号、标题、时长、来源、语言、分段与纯文本）、`TranscriptBundle`（视频信息、分P列表、失败清单、创建时间，带 `schema_version`）。

导出四种格式：

- Markdown：头部是标题、来源链接、UP 主、文稿来源与提取时间，多分P时加 `## Pn · 标题`，末尾附未提取分P的清单；时间戳默认关闭，开启时每行前缀 `[mm:ss]`
- 纯文本：只拼接分段文本
- SRT：时间格式 `HH:MM:SS,mmm`，多分P按各分P时长累加偏移
- JSON：分段序列化加上视频与分P元数据

纯文本与 SRT 用 `utf-8-sig` 写出。批量任务只导出 Markdown，文件名为 `{安全标题}__{bvid}.md`，同名时依次追加序号，默认目录是 `文档\Bili文稿`。没有词级时间戳。

## 八、局域网提取 API

默认随软件启动，监听 `0.0.0.0:8766`（关闭软件即停止，可在设置里单独停止或改端口）。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查，免鉴权 |
| GET | `/openapi.json` | OpenAPI 3.1 规范，免鉴权 |
| GET | `/v1/capabilities` | 当前非敏感设置与服务限制 |
| POST | `/v1/extractions` | 提交任务，立即返回 202 与任务 ID |
| GET | `/v1/extractions/{id}` | 查询状态与进度 |
| GET | `/v1/extractions/{id}/result` | 取 `json`、`markdown`、`text` 或 `srt` |
| POST | `/v1/extractions/{id}/cancel` | 取消任务，可重复调用 |

鉴权用 Bearer 令牌，密钥由 `secrets.token_urlsafe(32)` 生成，比较用 `hmac.compare_digest`，长度不足 16 字符或含空白时自动重新生成；401 响应带 `WWW-Authenticate` 头；不设任何 CORS 响应头，文档明确说明这是可信局域网内的 HTTP 服务，没有 HTTPS。

请求约定收得很紧：必须是 `application/json`，必须带 `Content-Length`，请求体上限 16 KiB，只允许 `source` 一个字段且长度上限 2048，任务 ID 必须是 32 位小写十六进制。错误响应统一为 `{"error":{"code","message"}}`，不暴露 Python 堆栈，错误码清单写进了 API 文档。结果格式与响应类型一一对应，JSON 结果在 Bundle 之上追加 `has_issues` 字段表示部分分P失败。

资源限制：最多同时运行 3 个任务、保留 32 个未完成任务、完成结果只在内存中保留 1 小时、重启不恢复。每个任务在提交瞬间固化当时的提取方式、识别后端、模型与上游设置，之后修改界面设置不影响已提交的任务。

这是与桌面界面共用同一套提取逻辑的：任务由界面线程池之外的服务线程池执行，完成回调通过 Qt 信号回到界面线程更新状态，历史库里同时记录界面任务与 API 任务并分组展示。

## 九、界面与 Windows 原生效果

界面用 PySide6（不是 PyQt），Fusion 样式，无边框窗口（`FramelessWindowHint` 加透明背景），初始 1180×760。侧栏 218px 固定宽度，只有首页、历史、设置三个入口，设置以抽屉形式展开六个分类（常规、提取、B站账号、ASR、提取 API、关于）。标题栏自绘，含拖动区与最小化、最大化、关闭三键。首页有闲置、执行中、结果、错误四个状态，结果页含可拖动的时间轴与时间提示。后台任务用 7 个 QThread 类配合信号槽，取消统一走 `threading.Event`。

Acrylic 玻璃效果的实现值得记下来，因为它没有走常见路线：

- 原生层是一个 .NET 8 项目，发布为 AOT 编译的共享库，导出六个可被 C 调用的函数（创建、同步、显示、更新、销毁、取错误）
- 实现方式是在窗口后方放一个不参与交互的视觉窗口（`WS_POPUP` 加透明与不重定向标志），用 Windows Composition 的 host backdrop 笔刷采样窗口后方像素，串接高斯模糊与饱和度效果，再叠一层纯色着色；命中测试返回 `HTTRANSPARENT`，激活消息返回 `MA_NOACTIVATE`，该窗口只承担绘制
- 同时用 `DwmSetWindowAttribute` 关闭系统自带的 backdrop，失败时退回旧版 Accent 策略
- Python 侧用 `ctypes` 加载（不是 pythonnet），加载前按绝对路径预加载 MSVC 运行时与 Win2D 的 DLL，再用 `CreateActCtxW` 加 manifest 完成免注册的 WinRT 激活
- 回退链完整：系统不是 win32、开启高对比度、关闭透明效果、处于节电模式，或 DLL 不存在，任一条件不满足就整体换成全实色样式表
- 窗口移动与缩放期间通过 `nativeEvent` 同步矩形，只负责绘制的那层不参与 Qt 的持续模糊刷新

## 十、数据、打包与分发

历史库是 SQLite，位于 `%LOCALAPPDATA%\BiliTranscript\history.sqlite3`，永久保留，支持按主页调用与 API 调用分组、搜索、分页、按需加载正文、重新导出、再次提取与删除。库里不保存 API 密钥、识别密钥与上游地址。设置走 QSettings，密钥与密钥类字段在快照里脱敏。

打包分两条路：`build.bat` 产出便携 ZIP（PyInstaller，配置里带入 LICENSE 与 NOTICE 作为数据文件），`build-installer.bat` 在此基础上调用 Inno Setup 产出安装程序（先检查 Inno Setup 是否存在，找到后带源码目录参数编译）。安装到当前用户目录无需管理员权限，创建开始菜单入口与可选桌面快捷方式，提供标准卸载，卸载不会删除专用浏览器的登录资料目录。原生层单独用 `build-backdrop.bat` 编译：`dotnet publish -c Release` 后把 DLL、manifest、Win2D 的 DLL 与三个 MSVC 转发 DLL 复制进应用目录。

第三方许可处理得清楚：`NOTICE.md` 逐项列出参考项目（Bili Note，MIT）、Inno Setup 与其中文语言包来源、Win2D 版本、MSVC App-Local DLL 转发包，项目本身 MIT，安装向导会把许可证展示给用户。

## 十一、测试体系

标准库 `unittest`，13 个测试文件、77 个用例，全部用本地假数据，不访问 B 站。覆盖范围包括：提取路线顺序与降级行为（公开中文字幕命中后不再访问后续路线、公开英文字幕让位给匿名中文 AI、每条空来源各试两次后才下降、正文为空时对同一轨道重试、第二次尝试能拿到刷新后的地址）、手动模式不触碰其他来源、批量并行中单视频失败不影响其他、文件名安全化与冲突序号、SRT 时间与分P偏移、序列化往返、B 站客户端拒绝不可信地址与默认不隐式重试、字幕探测与语言优先级、本地引擎不可用时自动转 API。

界面测试的做法是在导入 PySide6 之前把平台设为 `offscreen`，每个用例在临时目录注入 `QSettings(IniFormat)` 与临时历史库，用 `autostart_services=False` 构造窗口再关闭，断言控件可见性、只读状态、时间轴定位、诊断面板文本与历史分页不重复。

除单元测试外还有两个端到端脚本：`tools/api_smoke_test.py` 对运行中的服务走完健康检查、能力查询、提交任务、轮询状态、校验结构与分段、下载 Markdown 六步；`tools/startup_smoke_test.py` 在真实 Qt 事件循环里启动窗口，用测试端口与临时密钥轮询接口是否监听、登录浏览器是否启动、登录检查是否结束。应用自身还内置 `--smoke-test` 与截图参数。

## 十二、事实核对

细读代码后确认的几处与文档或直觉不同的地方：

- 没有 WBI 签名实现，需要凭据的请求全部交给专用浏览器
- 只支持普通视频与分P；番剧、直播、合集、收藏夹、空间投稿列表都没有解析路径，这类链接会在编号解析处被拒绝
- 传输层的 HTTP 状态码重试分支因为默认 `retries=0` 在生产路径不会生效，这是刻意关掉的，测试里有用例断言默认传输层只调用一次
- `CHANGELOG.md` 的 0.6.0 条目写提取接口默认关闭，当前默认值是开启，并有一次性的配置迁移把它改成开启
- 没有日志文件或日志系统，仓库里也不存在日志位置相关的实现
- `--startup` 参数被解析，但没有分支使用它区分启动行为

## 十三、与本工程的结合点

这个工程与 iHateVideos 的重合面很宽：目标都是把 B 站视频变成文字，都用 B 站播放器接口，都要处理登录态。可以借鉴的部分按价值排序：

1. **三条字幕接口与固定降级语义**：公开接口、匿名 `wbi/v2`、登录浏览器三者依次尝试，每来源两次加 1 秒等待，重试时重新探测。本工程目前只用 `bili` 命令行取原生字幕，只有一条路。
2. **浏览器承担登录态**：用 CDP 启动独立配置目录的浏览器，页面内 `fetch` 带凭据，Python 完全不接触 Cookie。本工程现在是让用户从浏览器导出 Netscape 格式文件再导入，两条路可以并存。
3. **语言优先级与 AI 字幕处理**：两级分组排序、公开英文字幕只作后备、公开接口只给 `ai-zh` 元数据时换匿名接口。本工程 `TODO.md` 里有语言优先级的待办，这套规则可以直接用。
4. **本地识别的多引擎探测**：识别放在独立脚本里，由父进程探测机器上装了哪个库的 Python 再调用。本工程如果不想把 torch 写进依赖，这是现成的做法；代价是识别环境要用户自己准备。
5. **识别结果的阶段化进度**：下载 0 到 35、识别 40 到 100、再按分P折算，各引擎至少给出起点与终点两个进度点。本工程的媒体命令是前台执行，没有进度上报。
6. **OpenAI 兼容接口客户端**：自己拼 multipart、`verbose_json` 与纯文本两种响应都兼容、服务端只处理单请求时在应用内串行、连接与健康检查分档超时。这一条与 `docs/cloud-stt.md` 的调研可以直接对照。
7. **局域网提取 API 的完整设计**：Bearer 鉴权与定时比较、异步任务与轮询、四种结果格式、统一错误结构与错误码、提交时固化设置快照、队列与结果有效期上限。本工程的 Agent 现在是同步调用命令行，要做成服务时的参照就在这里。
8. **结果结构与导出**：分段与 Bundle 的分层、SRT 多分P偏移、Markdown 头部字段、`utf-8-sig` 编码。本工程 `export` 模块已有相似职责，可对照字段命名与导出细节。
9. **Windows 原生界面效果**：独立原生背景层加多级回退的完整做法，适合将来要做桌面界面时参考。
10. **打包与分发**：PyInstaller 加 Inno Setup 的当前用户安装、卸载保留登录资料、第三方许可逐项登记。本工程是命令行工具，暂时不需要安装器，但许可登记的做法适用。
11. **测试体系**：77 个用例覆盖降级路线与重试行为，加两个端到端脚本与内置冒烟参数。本工程没有测试目录，`docs/audit/risks.md` 的 R10 记录了这一点。
12. **历史库设计**：SQLite、按调用来源分组、按需加载正文、密钥类字段不入库。

需要留意的差别：它是纯 Windows 桌面应用，界面与原生层占了很大比重；它不做评论、简介、章节的抓取，本工程的 `input` 模块这几项更完整；它对 B 站以外的平台没有支持，本工程还有小宇宙与喜马拉雅。

## 十四、需要决定的事项

1. 字幕获取路线是否补齐：在现有 `bili` 命令行之外，是否增加匿名 `wbi/v2` 与登录浏览器两条路，以及是否照这套「每来源两次、失败降级、手动模式不降级」的语义
2. 登录态方案：保留 Cookie 文件导入，还是补一套专用浏览器方案，或者两者并存
3. 语音识别的接入形态：照这边的子进程探测（识别环境由用户准备），还是把引擎装进工程依赖（对照 `funasr.md` 与 `course-navigator.md` 的取舍）
4. 是否提供局域网服务形态，以及本工程的 Agent 是否改为调用它
5. 结果结构是否对齐：本工程 `export` 现在的输入是外部转录 JSON，接入自产识别结果时沿用现有 schema 还是照这边的分段与 Bundle 分层
6. 是否建立测试目录与端到端冒烟脚本
7. 历史与持久化：是否增加 SQLite 历史库，还是维持 `temp/` 会话目录
