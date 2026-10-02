# DownLord 下载内核移植到 iHateVideos 的实施计划

调研对象：`F:\Codes\iHateVideos\DownLord`（Electron + TypeScript 桌面下载器，版本 1.0.0，383 个 ts、54 个 tsx，含浏览器扩展）。
目标工程：`F:\Codes\iHateVideos\iHateVideos`（Python 0.3.0，uv 管理）。

## 一、目标与边界

把 DownLord 主进程里与下载有关的业务能力用 Python 重新实现，成为 iHateVideos 的一个独立模块 `src/ihatevideos/download/`，配独立命令行 `ihatevideos-download`。

### 纳入移植的部分

| 能力 | DownLord 出处 | 内容 |
|---|---|---|
| 引擎进程管理 | `src/main/engine/aria2Process.ts`、`port.ts`、`secret.ts` | aria2c 子进程启动、空闲端口选择、RPC secret 生成、崩溃检测与指数退避重启、崩溃风暴上限 |
| 引擎参数 | `src/main/engine/aria2Args.ts`、`aria2Headers.ts`、`aria2Limit.ts`、`btOptions.ts` | 启动参数、任务级选项、限速选项、BT 选项、做种选项、文件选择索引压缩 |
| 引擎 RPC | `src/main/engine/rpcClient.ts`、`rpcCodec.ts` | JSON-RPC 调用封装、请求组装、响应解析、错误码归一、进度字段映射 |
| 引擎主逻辑 | `src/main/engine/downloadEngine.ts`（1154 行） | 内存 id 与 gid 映射、进度轮询与节流去重、终态检测、BT 元数据向真实下载的 gid 转移、崩溃后重提、HTTP 文件名预探、全局限速与任务限速、tracker 热应用 |
| 双执行器路由 | `src/main/engine/compositeEngine.ts` | 直链与 BT 走 aria2，视频走 yt-dlp，按下发入口分流并按 id 回查 |
| 视频解析 | `src/main/video/videoResolver.ts`、`ytdlpJson.ts`、`ytdlpSubtitle.ts`、`qualityLabel.ts`、`ytdlpFormat.ts` | yt-dlp 信息树解析、格式清单、字幕清单、清晰度标签、格式选择器推导 |
| 视频下载 | `src/main/video/videoEngine.ts`（607 行）、`ytdlpArgs.ts`、`ytdlpProcess.ts`、`ytdlpProgress.ts`、`ytdlpDownloader.ts`、`ytdlpEnv.ts`、`ytdlpHeaders.ts`、`ytdlpCookie.ts`、`formatAccel.ts` | 每任务一进程、进度行解析、后处理阶段识别、最终路径捕获、暂停即杀进程树、挂 aria2c 加速与分片协议判定 |
| 任务管理 | `src/main/tasks/taskManager.ts`（2165 行）、`stateMachine.ts`、`concurrency.ts`、`recovery.ts`、`duplicateDetect.ts` | 八态状态机、并发出队、重启恢复计划、提交前查重与重命名序号 |
| 持久化 | `src/main/db/schema.ts`、`taskDao.ts`、`categoryDao.ts`、`connection.ts`、`migration.ts` | SQLite 三张表、DAO、WAL、启动自检、损坏备份重建、迁移 |
| 类别与路径 | `src/main/category/categorize.ts`、`categoryModel.ts`、`src/main/video/filename.ts` | 扩展名清单、类别判定、目录路由、文件名清洗、扩展名预测 |
| 配置 | `src/main/config/jsonConfigStore.ts`、`src/main/settings/settingsService.ts`、`validateSettings.ts` | JSON 原子写、损坏回退、字段校验与取值范围限制 |
| 代理 | `src/main/proxy/proxyArgs.ts`、`proxyService.ts`、`systemProxy.ts`、`systemProxyReader.ts`、`proxyStore.ts` | 三档代理、系统代理读取、引擎参数注入、显式关闭 |
| 引擎定位 | `src/main/binaries/locator.ts`、`probeVersion.ts`、`selfCheck.ts`、`engineVersions.ts` | 三引擎定位、版本探测、启动自检 |
| BT 附加 | `src/main/bt/trackerText.ts`、`btTrackerStore.ts`、`btTrackerService.ts`、`torrentPaths.ts` | tracker 表解析与更新、种子托管副本路径 |
| 错误文案 | `src/main/errors/errorCatalog.ts`、`mapError.ts` | 错误码目录、可读中文映射、下一步提示 |
| yt-dlp 热更新 | `src/main/update/ytdlpUpdater.ts`、`updateHttp.ts`、`paths.ts` | 下载新版本、校验、原子替换、失败保留旧版 |

### 不纳入移植的部分

- Electron 渲染层全部内容：`src/renderer/`、`src/preload/`、Fluent UI 主题、窗口与托盘。
- 浏览器扩展与本地通道：`extension/`、`src/main/extensionChannel/`、`src/main/takeover/`、`src/shared/sniffMedia.ts`。这些依赖浏览器环境，Python 侧没有对应载体；第四档「从扩展获取 Cookie」随之取消，登录态走浏览器 cookies.txt 或 yt-dlp 的 `--cookies-from-browser`。
- 剪贴板监控：`src/main/clipboard/`。与视频转文字的工作内容无关。
- 应用本体自动更新：`src/main/update/appUpdater.ts`、`electron-updater`、`dev-app-update.yml`。
- 工程与发布流程：`.github/`、`scripts/release*`、`scripts/gate.mjs`、`electron-builder.yml`、许可证材料与 `THIRD-PARTY-NOTICES.md` 的流程部分。
- IPC 类型定义：`src/shared/ipc.ts`（1461 行）。它是主进程与渲染层的通道约定，Python 侧只保留其中的数据模型部分，通道定义不移植。

## 二、模块结构

新模块位于 `src/ihatevideos/download/`，与 `input`、`export`、`media`、`summarize` 并列。

| Python 文件 | 来源 | 职责 |
|---|---|---|
| `__init__.py` | — | 导出 `DownloadService`、数据模型、`resolve_engines` 等对外接口 |
| `models.py` | `src/shared/ipc.ts` 的数据模型部分 | `TaskKind`、`TaskStatus`、`Task`、`Progress`、`FormatInfo`、`TorrentMeta`、`TorrentFile`、`Settings` 等数据类与枚举 |
| `binaries.py` | `binaries/locator.ts`、`probeVersion.ts`、`selfCheck.ts`、`engineVersions.ts` | 三引擎定位（环境变量、PATH、项目 `resources/bin`）、版本探测、启动自检 |
| `aria2_args.py` | `engine/aria2Args.ts`、`aria2Headers.ts`、`aria2Limit.ts`、`btOptions.ts` | 启动参数、任务选项、限速选项、BT 选项、种子文件选择索引压缩 |
| `aria2_process.py` | `engine/aria2Process.ts`、`port.ts`、`secret.ts` | 子进程启动与就绪等待、崩溃检测与退避、优雅停止 |
| `aria2_engine.py` | `engine/downloadEngine.ts`、`rpcCodec.ts` | RPC 调用（经 aria2p）、进度轮询与节流、终态检测、BT 元数据 gid 转移、崩溃重提、文件名预探、限速下发 |
| `ytdlp_args.py` | `video/ytdlpArgs.ts`、`ytdlpDownloader.ts`、`ytdlpCookie.ts`、`ytdlpHeaders.ts`、`ytdlpFormat.ts`、`formatAccel.ts` | 解析与下载参数组装、格式选择器推导、加速与限速参数 |
| `ytdlp_process.py` | `video/ytdlpProcess.ts`、`ytdlpEnv.ts` | yt-dlp 子进程封装、进程树终止、环境变量净化 |
| `ytdlp_engine.py` | `video/videoEngine.ts` | 视频解析与下载后端、进度行解析（`ytdlpProgress.ts`）、后处理阶段与终路径捕获、暂停与继续 |
| `ytdlp_json.py` | `video/ytdlpJson.ts`、`ytdlpSubtitle.ts`、`qualityLabel.ts` | 信息树解析、字幕清单、清晰度标签 |
| `task_manager.py` | `tasks/taskManager.ts` | 任务增删改查、状态流转、并发控制、查重、重启恢复、关键节点写库 |
| `state_machine.py` | `tasks/stateMachine.ts`、`concurrency.ts`、`recovery.ts` | 合法流转表、出队计算、恢复计划 |
| `duplicate.py` | `tasks/duplicateDetect.ts` | 冲突检测、命名序号 |
| `db.py` | `db/schema.ts`、`connection.ts`、`migration.ts` | 连接、建表、WAL、自检、备份重建、迁移 |
| `dao.py` | `db/taskDao.ts`、`categoryDao.ts` | 任务与类别的读写与检索、历史统计 |
| `categories.py` | `category/categorize.ts`、`categoryModel.ts` | 扩展名与类别清单、类别判定、目录路由 |
| `filenames.py` | `video/filename.ts`、`tasks/taskManager.ts` 的取名部分 | 文件名清洗、URL 末段取名、扩展名预测 |
| `config_store.py` | `config/jsonConfigStore.ts` | JSON 原子写、损坏回退 |
| `settings.py` | `settings/settingsService.ts`、`validateSettings.ts` | 设置读取与合并校验、取值范围限制、变更联动 |
| `proxy.py` | `proxy/proxyArgs.ts`、`proxyService.ts`、`systemProxy*.ts` | 三档代理、系统代理读取、参数注入 |
| `trackers.py` | `bt/trackerText.ts`、`btTrackerStore.ts`、`btTrackerService.ts`、`bt/torrentPaths.ts` | tracker 表解析与更新、种子副本路径 |
| `errors.py` | `errors/errorCatalog.ts`、`mapError.ts` | 错误目录、可读中文映射 |
| `ytdlp_update.py` | `update/ytdlpUpdater.ts`、`updateHttp.ts`、`update/paths.ts` | yt-dlp 下载、校验、原子替换 |
| `cli.py` | 新增 | `ihatevideos-download` 命令行 |

模块内的数据流与 DownLord 相同：命令行走 `cli.py`，Python 调用方走 `DownloadService`；两者都经过 `task_manager.py`，由它协调 `aria2_engine.py` 与 `ytdlp_engine.py`，状态改动经 `dao.py` 写入 `db.py`，保存位置由 `categories.py` 与 `filenames.py` 算出。

与现有模块的复用点：ffmpeg 定位直接用 `src/ihatevideos/media/ffmpeg.py` 的 `resolve_ffmpeg()`，媒体信息读取用 `media/probe.py`，不再新建一套。

## 三、Python 侧的技术选择

| 能力 | DownLord 的做法 | Python 侧的选择 | 依据 |
|---|---|---|---|
| aria2 控制 | 自写 JSON-RPC 客户端 + fetch | `aria2p` 库的 `Client` 与 `API` | `aria2p` 是对 aria2 JSON-RPC 的完整封装，`Client` 已实现 `add_uri`、`add_torrent`、`change_option`、`change_global_option`、`force_pause`、`force_remove`、`pause`、`unpause`、`remove`、`remove_download_result`、`tell_status`、`tell_active`、`tell_waiting`、`tell_stopped`、`get_global_stat`、`listen_to_notifications`、`shutdown`、`force_shutdown`；`API` 层提供 `add_uris`、`add_torrent`、`get_downloads`、`set_options`、`set_global_options`、`listen_to_notifications` 等高层方法 |
| yt-dlp 调用 | `yt-dlp.exe` 子进程 + `-J` JSON + `--progress-template` | 子进程调用 `python -m yt_dlp`，参数与行解析规则沿用 DownLord | 已验证本机 yt-dlp 2026.08.19 支持 `python -m yt_dlp`；保留 DownLord 已通过真机验证的参数组合（`--print after_move:%(filepath)j` 的 JSON 转义解决了中文路径乱码）与进度行解析规则，暂停语义仍是杀进程树 |
| yt-dlp 的 Python 接口 | 未使用 | 仅在需要读取信息树与格式清单的场景可直接 `import yt_dlp` 调用 `YoutubeDL`；`progress_hooks` 与 `postprocessor_hooks` 的字段在 yt-dlp 源码 docstring 中有明确定义（`status`、`filename`、`downloaded_bytes`、`total_bytes`、`total_bytes_estimate`、`speed`、`eta`、`fragment_index`、`fragment_count`），与 `ytdlpProgress.ts` 解析的字段一致 | 两种调用方式并存时以子进程为主，避免线程内无法安全终止 |
| ffmpeg | `--ffmpeg-location` 指向内置 ffmpeg | 复用 `media/ffmpeg.py` 的 `resolve_ffmpeg()`，同样以 `--ffmpeg-location` 传给 yt-dlp | 工程已有一套定位与错误处理，不重复实现 |
| SQLite | Electron 内置 `node:sqlite` | 标准库 `sqlite3` | 无需新增依赖；WAL、`quick_check`、备份重建、迁移都能直接实现 |
| 子进程 | `child_process.spawn` + `taskkill /T /F` | `subprocess.Popen` + `taskkill /T /F`（Windows），POSIX 下 `os.killpg` | 与 DownLord 的进程树终止策略相同 |
| 并发 | Node 事件循环 + `setInterval` 轮询 | 后台线程轮询（`threading.Thread` + `Event`），任务命令经队列串行执行 | 轮询与状态变更都要有单一执行者，避免共享状态竞争 |
| 配置读写 | 手写 JSON 原子写 | `json` + 临时文件 + `os.replace` | 与 DownLord 的原子写语义相同 |
| 配置读取（模型） | 已有 `config.toml` | 继续用 `tomllib` | 工程的模型配置已有约定 |
| 系统代理读取 | 读 Windows 注册表 | `urllib.request.getproxies()` 与注册表读取（`winreg`） | 系统代理在 Windows 上写在注册表 `Internet Settings` |
| 浏览器 Cookie | 扩展第四档 + 浏览器数据库读取 | yt-dlp 的 `--cookies-from-browser` 与 `--cookies <文件>` | yt-dlp 原生支持，Python 侧不需要自行读取浏览器数据库 |

需要加入 `pyproject.toml` 的依赖：`aria2p`、`yt-dlp`。已有的 `httpx` 用于 tracker 表更新与 yt-dlp 热更新下载。外部程序：`aria2c`（本机已有 1.37.0，与 DownLord 内置版本一致）、`ffmpeg`、`ffprobe`（本机已有）。

## 四、数据模型

SQLite 三张表照搬 DownLord（`src/main/db/schema.ts`）：

```sql
CREATE TABLE tasks (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,                -- 'http' | 'video' | 'torrent'
  source TEXT NOT NULL,              -- 原始 URL / magnet / .torrent 路径
  status TEXT NOT NULL,              -- 八态之一
  filename TEXT NOT NULL,
  savePath TEXT NOT NULL,
  category TEXT,
  totalBytes INTEGER DEFAULT 0,
  downloadedBytes INTEGER DEFAULT 0,
  videoMeta TEXT,                    -- JSON
  error TEXT,
  createdAt INTEGER NOT NULL,
  startedAt INTEGER,
  completedAt INTEGER,
  torrentMeta TEXT,                  -- JSON
  CHECK(kind IN ('http','video','torrent')),
  CHECK(status IN ('resolving','awaiting_selection','queued','downloading','paused','processing','completed','error'))
);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_category ON tasks(category);
CREATE INDEX idx_tasks_createdAt ON tasks(createdAt DESC);

CREATE TABLE categories (
  key TEXT PRIMARY KEY,
  displayName TEXT NOT NULL,
  extensions TEXT NOT NULL,          -- JSON 数组
  savePath TEXT NOT NULL
);

CREATE TABLE schema_version (
  version INTEGER PRIMARY KEY,
  appliedAt INTEGER NOT NULL
);
```

写库时机照搬 DownLord 的进度分层：状态流转与 `startedAt`、`completedAt`、`error`、首次已知的 `totalBytes` 写入数据库；瞬时速度与已下载字节只留内存，供调用方读取。

只在内存里保存的运行时状态：`gid`、限速覆盖值、做种状态、上行速度、节点数、连接数。`gid` 在 DownLord 里明确不写入数据库，移植后保持这条约定。

类别清单照搬 `categoryModel.ts` 的六类（video、audio、archive、document、program、other）与各自扩展名；目录路由规则照搬 `resolveCategoryDir`：类别自定义目录优先，否则默认目录加子目录，other 保存到默认目录本身。

## 五、对外接口

### Python 接口

```python
from ihatevideos.download import DownloadService, TaskKind, TaskStatus

service = DownloadService.open(root=..., data_dir=..., default_dir=...)
task = service.add(url="https://.../file.zip")                    # 直链
task = service.add(url="https://.../watch?v=...", kind=TaskKind.VIDEO)  # 视频解析
task = service.add(url="magnet:?xt=...")                          # 磁力
service.resolve_formats(task.id)                                  # 视频格式清单
service.submit_choice(task.id, format_id="137", audio_only=False, subtitles=(...))
service.pause(task.id) / service.resume(task.id) / service.remove(task.id)
service.retry(task.id)
service.set_limit(task.id, kb_per_second=None)                    # None = 跟随全局
service.select_torrent_files(task.id, indices=[1, 3, 4])
service.stop_seeding(task.id)
progress = service.progress(task.id)                              # 运行时快照
rows = service.history(status=..., category=..., text=..., limit=...)
stats = service.history_stats()
service.close()
```

要点：新增任务时若命名与历史或磁盘冲突，返回冲突信息并等待决策（沿用 `duplicateDetect.ts` 的三种冲突类型 completed / diskOnly / active 与四种处理方式），调用方可以显式选择改名、覆盖、跳过或重新提交。状态流转全部经 `state_machine.py` 校验，非法流转记录日志并拒绝，不改变任务当前状态。

### 命令行

```
ihatevideos-download engines                      # 三引擎定位与版本，启动自检
ihatevideos-download add <url> [--kind] [--dir] [--filename] [--category]
ihatevideos-download formats <task-id>            # 解析视频并输出格式与字幕清单
ihatevideos-download select <task-id> --format 137 [--audio-only] [--subs zh-Hans,srt]
ihatevideos-download list [--status] [--category] [--text] [--limit]
ihatevideos-download pause|resume|remove|retry <task-id>
ihatevideos-download limit <task-id> [--kb 512|--global]
ihatevideos-download torrent-files <task-id>      # 列出种子内文件与选中状态
ihatevideos-download torrent-select <task-id> --index 1,3-5
ihatevideos-download seed-stop <task-id>
ihatevideos-download history [--status] [--category] [--text] [--limit]
ihatevideos-download stats
ihatevideos-download categories [--set key=dir]
ihatevideos-download config [--set key=value]
ihatevideos-download ytdlp-update [--check]
ihatevideos-download serve                        # 前台守着任务队列直到全部结束
```

输出约定沿用工程现有做法：标准输出一行 JSON（`ensure_ascii=False`），日志与引擎报错走标准错误。退出码沿用现有约定：`0` 成功，`2` 输入不合法，`1` 运行失败，`3` 正常跳过（解析不支持该站点、种子没有可选文件等）。

新增的 CLI 需要按工程约定把三个输出流编码固定为 UTF-8（`stream.reconfigure(encoding="utf-8")`）。这条正是 `docs/audit/risks.md` 里 R1 记录的问题：`ihatevideos-input`、`ihatevideos-export`、`ihatevideos-summarize` 目前没有这一步，Agent 的 `run_cli` 以 UTF-8 解码子进程输出，含中文时会乱码。新命令从一开始就带上，同一个问题在既有三个命令上的处理另行安排。

### 与现有模块的连接

1. `ihatevideos-input` 的 `resolver.py` 增加一条通用视频路径：平台判定为 B 站、小宇宙、喜马拉雅之外的链接，且 `detect_platform` 返回 `None` 时，交给 download 模块的解析与下载，只取音频（`audio_only`）供转录使用。B 站、小宇宙、喜马拉雅的现有下载路径不改动（B 站继续用 yutto，小宇宙与喜马拉雅继续用各自下载器）。
2. `ihatevideos-agent` 的命令白名单增加 `ihatevideos-download` 及其子命令；`skills/` 增加一个 `ihatevideos-download/SKILL.md`，写明命令、退出码、判断表与测试提示词。
3. `temp/` 下新增 `download/` 作为任务数据与配置的存放位置，与现有 `temp/media/` 的约定一致（`temp/` 已在 `.gitignore` 中）。

## 六、交付单元与验收

六个交付单元按依赖关系排列，每一个都能独立运行并当场验证。命令全部在工程根目录执行。

### 单元 1 引擎定位与 aria2 控制通路

内容：`binaries.py`、`aria2_args.py`、`aria2_process.py`、`aria2_engine.py` 的启动与停止部分、`errors.py` 的引擎条目。
来源：`binaries/*`、`engine/aria2Args.ts`、`engine/aria2Process.ts`、`engine/downloadEngine.ts`（启动部分）、`errors/errorCatalog.ts` 的引擎条目。
验收：

```bash
uv run ihatevideos-download engines
```

期望输出三个引擎的路径与版本（aria2c 1.37.0、yt-dlp、ffmpeg），随后启动 aria2c 并读取其版本，停止时子进程真正退出（无残留进程）。

### 单元 2 直链下载、任务状态与并发

内容：`models.py`、`state_machine.py`、`aria2_engine.py` 的完整实现、`task_manager.py` 的内存部分、`filenames.py`。
来源：`engine/downloadEngine.ts`、`rpcCodec.ts`、`tasks/stateMachine.ts`、`tasks/concurrency.ts`、`video/filename.ts`。

内容要点：多线程分段参数（`--split=16`、`--min-split-size=1M`、`--max-connection-per-server=16`）、断点续传（`--continue=true`、`--auto-save-interval=1`）、暂停用 `forcePause`、删除用 `forceRemove`、进度轮询与字段无变化时不重复上报、崩溃检测与指数退避重启、崩溃风暴上限。验收：下载一个公开许可的直链文件（例如 Blender 基金会的《Big Buck Bunny》，与 DownLord 演示素材同源），中途暂停再继续，比较最终文件与预期大小；检查同目录留下过 `.aria2` 控制文件。

### 单元 3 持久化、类别、查重与恢复

内容：`db.py`、`dao.py`、`categories.py`、`duplicate.py`、`task_manager.py` 的写库与恢复部分、`config_store.py`、`settings.py`。
来源：`db/*`、`category/*`、`tasks/duplicateDetect.ts`、`tasks/recovery.ts`、`config/jsonConfigStore.ts`、`settings/*`。
验收：连续添加同名任务时能报出冲突并给出改名选项；进程结束后重新打开，未完成任务按恢复计划重新提交（下载中的续传、解析中的重新解析、暂停的保持暂停）；`stats` 的合计与类别分组与库中记录一致；把库文件故意写坏一个字节后启动，能看到「备份旧库再新建」的行为，旧库仍在。

### 单元 4 视频解析与下载

内容：`ytdlp_args.py`、`ytdlp_process.py`、`ytdlp_json.py`、`ytdlp_engine.py`。
来源：`video/ytdlpArgs.ts`、`ytdlpProcess.ts`、`ytdlpJson.ts`、`ytdlpSubtitle.ts`、`ytdlpProgress.ts`、`videoEngine.ts`、`ytdlpDownloader.ts`、`formatAccel.ts`、`qualityLabel.ts`。
验收：解析一个公开站点视频并列出格式与字幕语言；按选定格式下载并合并；`--audio-only` 时产出 mp3；进度在解析与下载期间持续上报，后处理阶段状态变为 `processing`，完成后 `savePath` 与磁盘文件一致；HLS 或 DASH 分片格式不挂 aria2c，改用并发分片抓取；挂 aria2c 的普通格式在失败时按 DownLord 的三层回退改用自带下载器。

### 单元 5 BT 与磁力

内容：`aria2_args.py` 的 BT 部分、`trackers.py`、`aria2_engine.py` 的元数据 gid 转移与种子信息上报、`task_manager.py` 的种子选择与做种部分。
来源：`engine/btOptions.ts`、`engine/downloadEngine.ts` 的 BT 分支、`bt/*`。
验收：用公开测试种子完成元数据获取、文件清单展示、文件选择、下载完成；磁力链接能完成从元数据到真实下载的 gid 转移且进度连续；做种默认关闭，开启后按分享率或时长停止；tracker 表能更新并在启动参数中生效。

### 单元 6 代理、限速、yt-dlp 热更新与技能文档

内容：`proxy.py`、限速三态、`ytdlp_update.py`、`skills/ihatevideos-download/SKILL.md`、Agent 白名单、`README` 与 `CHANGELOG` 更新。
验收：三档代理都能实际生效（直连、手动地址、跟随系统），直连档显式关闭代理而不是省略参数；全局限速与任务级限速（跟随全局 / 不限 / 指定值）都能在运行中观察到速度变化；yt-dlp 热更新能下载新版、校验、替换并保留旧版回退；Skill 文档里的每条命令都能按文档描述运行。

## 七、验证方式

1. 纯函数部分写单元测试：状态流转表、出队计算、恢复计划、查重判定、文件名清洗（含 Windows 保留设备名与尾部点）、类别判定与目录路由、进度行解析、aria2 参数与 BT 选项、种子文件选择索引压缩。这些函数在 DownLord 里都有对应测试文件，测试用例可以直接转成 Python 用例（例如 `aria2Args.test.ts` 用参数列表相等断言，`btOptions.test.ts` 用 `[7,3,4,1,5,3]` → `"1,3-5,7"` 这类具体输入输出）。
2. 涉及网络的验收按上面的交付单元逐个真跑，保留命令输出作为证据。
3. 不使用任何替代实现、假数据或只为通过测试的临时处理。需要网络时用公开许可的素材与公开测试种子。
4. 工程目前没有测试目录，需要新建 `tests/`（`pyproject.toml` 增加开发依赖 `pytest`，或使用标准库 `unittest`）。这是第六节里需要一并定下的一件小事，见下方决策点。

## 八、需要拍板的三项决策

1. 数据目录位置。计划采用 `temp/download/`（数据库、配置、种子副本都在其中），与现有 `temp/media/` 的约定一致。另一种做法是在根目录 `config.toml` 里增加 `[download]` 段来指定数据目录与默认下载目录。前者改动最小，后者与模型配置集中在一处。
2. BT 与磁力是否纳入本次范围。计划把它作为单元 5 纳入，理由是 aria2 原生支持 BT，Python 侧只增加选项构造、元数据 gid 转移与种子信息上报；去掉它可以让单元 5 整体消失，代码量减少约两个文件的规模。
3. 测试框架选 `pytest` 还是标准库 `unittest`。工程目前的验证方式是手工运行命令加各 Skill 的 `evals.json`，没有测试依赖。

## 九、前提与已知限制

- 本次移植只覆盖 DownLord 主进程的下载业务。界面、浏览器扩展、下载接管、网页嗅探、扩展取 Cookie 在 Python 侧没有载体，不做。
- DownLord 里大量「与改动前逐字节等价」的约定靠 TypeScript 的快照测试与 `deepEqual` 断言维持。移植时这些约定转换成参数列表相等断言与固定输入输出用例，含义不变。
- B 站下载在 iHateVideos 里由 yutto 负责，DownLord 用 yt-dlp，两者能力有重叠。本次不改动 `input` 的 B 站路径，避免影响已通过验证的现有链路。
- 需要登录的站点在 Python 侧走 yt-dlp 的 `--cookies-from-browser` 或浏览器导出的 cookies.txt，`input` 模块已有的 `cookies` 命令导入的 SESSDATA 是给 B 站字幕接口用的，两者不通用。
- DownLord 的 tracker 静态表会随时间失效，`bt/trackerText.ts` 与 `btTrackerService.ts` 里的更新逻辑要一并移植，否则磁力在无 tracker 的网络下取不到元数据。

## 十、调研期间对环境做的改动

- 为确认 yt-dlp 的 Python 入口可用，把 `yt-dlp 2026.08.19` 安装到了 `temp/probe-ytdlp/`（`temp/` 已在 `.gitignore` 中），只用读取与验证，没有改动 `pyproject.toml` 与 `uv.lock`。正式实施时用 `uv add yt-dlp` 加入依赖，这个临时副本可以删除。
- 确认本机已有 `aria2c 1.37.0`（与 DownLord 内置版本相同）、`ffmpeg`、`ffprobe`。
- 没有修改 DownLord 仓库的任何文件，也没有修改 iHateVideos 的源码；本文件在 `docs/external/`，同一批调研的分析产物在 `docs/audit/`。





