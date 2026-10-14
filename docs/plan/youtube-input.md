# YouTube 下载与总结接入方案

对应 `TODO.md` 的 TODO-001（YouTube 字幕接入 input 模块，验收：`ytsub` 命令对公开视频输出会话目录双文件，无字幕返回 exit 3）与 TODO-002（语言优先级确认，验收：Skill 写明中简、中繁、英的选用顺序）。

用户已导出的登录态文件：`C:\Users\Banned\Downloads\www.youtube.com_cookies.txt`（25 条，域名 `.youtube.com`，含 `SID`、`LOGIN_INFO`、`__Secure-1PSID` 等）。

## 一、现状

### download 模块已经具备的能力

- yt-dlp 以子进程调起：`[sys.executable, "-m", "yt_dlp", *args]`（`ytdlp_process.py:44-45`），解析用 `subprocess.run`，下载用 `Popen` 逐行回调。
- 参数拼装齐备：`proxy_args`（`ytdlp_args.py:31`）、`cookie_args`（`:36`，支持 `--cookies` 与 `--cookies-from-browser`）、`build_resolve_args`（`:44`，`-J --flat-playlist`）、`build_selector`（`:67`，音频、指定格式、高度上限三条路）、`build_subtitle_args`（`:99`，`--write-subs/--write-auto-subs/--sub-langs/--sub-format/--convert-subs`）、`build_download_args`（`:141`，`-o`、`--no-playlist`、进度模板、`-x --audio-format mp3`）。
- 元数据走 `-J`：`resolve_video()`（`ytdlp_engine.py:65`）→ `parse_info_tree`（`ytdlp_json.py:114`）→ `VideoInfo`（`models.py:92`，含 `video_id/title/duration_seconds/uploader/extractor/webpage_url/thumbnail/formats/subtitles`）。`SubtitleTrack`（`models.py:46`）有 `lang/name/auto/formats`，人工与自动字幕都在 `subtitles` 里用 `auto` 区分。
- CLI 五个子命令（`download/cli.py:191-242`）：`engines`、`setup-binaries`、`formats`、`file`、`video`；公共参数 `--cookie`、`--cookie-from-browser`、`--no-proxy`；退出码 0/1/2/3。
- yt-dlp 来自 pip 包（`pyproject.toml:18`），`binaries.py:189-194` 直接给 `sys.executable`。

结论：YouTube 的下载能力不需要新写，缺的是「把 yt-dlp 接进 input 的约定」与三处具体缺口。

### 三处缺口

1. **cookies 只认 B 站。** `input/cookies.py:46 find_cookies_file()` 扫 `temp/config/*.txt`，只挑「含 SESSDATA」的文件（`:62`）。YouTube 那份没有 SESSDATA，现有逻辑永远找不到它。
2. **字幕结构只服务 B 站。** `subtitle.py:49-75` 的 `BilibiliSubtitle` / `BilibiliSubtitleItem` / `SubtitleResult` 与 `ResolvedInput.subtitle`（`resolver.py:33`）的类型标注都只写 B 站。
3. **字幕文件路径无处回收。** `VideoRun` 只跟一个 `destination`（`ytdlp_engine.py:51`），`absorb_line`（`:247-267`）只认主文件路径；`--write-subs` 下出来的字幕文件不在任何返回值里，`--print after_move:%(filepath)j`（`ytdlp_args.py:11`）也不包含它。

另外 `input` 侧没有 YouTube 平台：`Platform` 只有三值（`platform.py:108-111`），`detect_platform`（`url_detect.py:57-80`）与 `extract_platform_id`（`:83-124`）都不认 YouTube 域名。

## 二、分工与数据流

`input` 负责「链接 → 媒体文件 + 元数据 + 字幕」，YouTube 与 B 站并列；`download` 负责「链接 → 视频文件」，取帧时用；`summarize` 只认本地视频与 Markdown，不改。

一次 YouTube 视频从链接到带图笔记：

1. `ihatevideos-input resolve --url <链接>`：拿元数据、拿字幕；命中字幕就不下音频，未命中就按 `--media` 下音频或视频。
2. 要插图时 `ihatevideos-input resolve --url <链接> --media video`：产物是 1080p 以内的 mp4（含音轨），同时拿到字幕。
3. 写笔记：`ihatevideos-summarize template study-notes` 拿模板，正文里写 `<!-- FRAME: MM:SS | 图注 -->` 占位符。
4. `ihatevideos-summarize frames <mp4> --md <笔记.md>`：把画面取到笔记同级的 `assets/`。
5. `ihatevideos-summarize insert <笔记.md>`：占位符换成图片引用。

没有字幕时：`resolve` 产出 mp3（`--media audio`，默认），交给 `ihatevideos-stt` 转写，转写文本按同样方式写笔记。

## 三、cookies 按平台选择

改 `input/cookies.py`：

- 新增按平台的域名与必需字段表：
  - `Platform.BILIBILI`：域名 `.bilibili.com`，必需 `SESSDATA`
  - `Platform.YOUTUBE`：域名 `.youtube.com`，必需 `LOGIN_INFO`
- `load_bilibili_cookies` 改成通用的 `load_cookies(path, platform)`（保留旧名字作包装，避免破坏现有调用点与 `__init__.py:99` 的导出）。
- `find_cookies_file(platform=Platform.BILIBILI)`：扫 `temp/config/*.txt`，按该平台域名收集 cookie，缺必需字段就跳过，取最新修改的一份。默认参数保持 B 站，现有调用点行为不变。
- `credential_status(platform=Platform.BILIBILI)` 同步扩展，返回的 `state` 取值不变（`ok`/`empty`/`missing`）。
- 登录态校验分成两条：
  - B 站：现有 `verify_login`（`:116`，调 `x/web-interface/nav`）。
  - YouTube：新增 `verify_youtube_login`，用 httpx 带 cookie 请求 `https://www.youtube.com/account`，看最终 URL 的主机是否变成 `accounts.google.com`；被重定向就是未登录。实现前先用真实 cookies 跑一次确认响应形态。
- CLI：`input cookies` 加 `--platform {bilibili,youtube}`，默认 `bilibili`；退出码约定不变（`0` 已登录、`3` 未登录或没有可用文件）。

用户在 `temp/config/` 放两份文件（`www.bilibili.com_cookies.txt` 与 `www.youtube.com_cookies.txt`），文件名不参与判定，域名与必需字段决定归属。

## 四、字幕获取与解析

### 获取流程

1. `resolve_video(url, proxy, cookie_file=...)` 拿 `VideoInfo`，从中取 `subtitles` 清单（`auto` 区分人工与自动）。
2. 按语言优先级排序，选中一条。
3. 只下这一条：`--skip-download --sub-langs <lang> --sub-format json3/vtt/best`，选中自动字幕时加 `--write-auto-subs`，人工字幕加 `--write-subs`。
4. 产物用「调用前后目录快照对比」找出（与 `bilibili_audio.py:180-205` 同一个套路），得到 `<output_base>.<lang>.json3` 或 `.vtt`。
5. 解析成 `SubtitleItem` 序列。

只下一次调用、只下一条语言，产物唯一，也不必改动 `VideoRun` 的单路径模型。

### 解析

- `.json3`：标准库 `json` 读取，取 `events[].tStartMs` / `dDurationMs` / `segs[].utf8` 拼出文本。JSON 不算需要手写的格式解析。
- `.vtt`：用 `webvtt-py` 解析，不自己写 WebVTT 解析。
- 两种都产出 `(start_ms, end_ms, text)`，跳过空文本与纯样式行（`align:start position:0%` 这类），合并相邻重复行（自动字幕会滚动重复）。

### 语言优先级（TODO-002）

统一成一张表，人工字幕整体排在自动字幕之前，组内按语言：

| 顺序 | 人工字幕 | 自动字幕 |
|---|---|---|
| 1 | `zh-Hans`、`zh-CN`、`zh-SG` | `zh-Hans`、`zh-CN`、`zh-SG` |
| 2 | `zh-Hant`、`zh-TW`、`zh-HK` | `zh-Hant`、`zh-TW`、`zh-HK` |
| 3 | `en`、`en-US`、`en-GB` | `en`、`en-US`、`en-GB` |
| 4 | 其它语言 | 其它语言 |

B 站侧现有 `LANGUAGE_PRIORITIES`（`subtitle.py:31-39`）已经做到「中文优先于英文」（先按 `rank_subtitles:95` 的中文分组，再看语言权重），本次把它与 YouTube 的映射统一到一张表上，`zh`、`ai-zh` 这类 B 站专用代码保留原有取值。

Skill 文档里把这张顺序写出来（TODO-002 的验收）。

## 五、命令与产物

### 新命令 `ytsub`（TODO-001）

```
uv run ihatevideos-input ytsub <url> [--out-dir temp] [--timeout 60]
```

- 只取字幕，不碰视频与音频。
- 产物写进会话目录（`artifacts.py:23 prepare_session_dir`，目录名 `<日期>-<标题>-youtube_<video_id>`）：
  - `<stem>_sub.txt`：纯文本，段与段之间换行
  - `<stem>_sub_items.json`：`[{"start_ms":…,"end_ms":…,"text":…}]`
  - `<stem>_meta.json`：标题、作者、发布时间、时长、平台、视频 ID、字幕来源（`manual` / `auto`）、语言代码
- `stem` = `youtube_<video_id>`，与 `metadata.py:59` 的 `f"{pm.platform.value}_{pm.platform_id}"` 一致。
- 退出码：`0` 成功；`3` 没有可用字幕（与 B 站 `subtitle` 命令一致）；`2` URL 非法或参数错；`1` 网络或下载失败。

### `resolve` 的 YouTube 分支

```
uv run ihatevideos-input resolve --url <链接> [--media audio|video] [--download-dir temp] [--subtitle-timeout 60]
```

- 先取字幕。命中字幕时 `audio_file` 为 `null`（与 B 站分支一致，省一次下载）。
- 未命中字幕时按 `--media` 下媒体文件：
  - `audio`（默认）：`-x --audio-format mp3 --audio-quality 0`（`ytdlp_args.py:172-173` 已有），产物给 `ihatevideos-stt` 转写。
  - `video`：`bestvideo[height<=1080]+bestaudio/best`，合流 mp4，取帧与转写都用它（转写时用 `media` 模块抽音轨）。
- 输出 JSON 字段沿用现有 `cli.py:80-93`：`audio_path`、`has_native_subtitle`、`subtitle_chars`、`subtitle_reason`、`resource_id`、`bvid`、`platform`（`"youtube"`）、`use_local_audio`、`title`、`author`，另加 `subtitle_lang` 与 `subtitle_source`（`manual`/`auto`）。
- 退出码沿用：`0`、`2`、`1`。

## 六、需要改动的文件

### input 模块

| 文件 | 改动 |
|---|---|
| `platform.py:108-111` | 加 `YOUTUBE = "youtube"`；`PlatformMetadata` 不改，`extra` 放 `channel`、`uploader_id`、`webpage_url`、`thumbnail` |
| `url_detect.py:18-21` | 加 `YOUTUBE_HOSTS`（`youtube.com`、`www.youtube.com`、`m.youtube.com`、`music.youtube.com`、`youtu.be`、`www.youtube-nocookie.com`）与视频 ID 正则（`/watch?v=<id>`、`/shorts/<id>`、`/live/<id>`、`/embed/<id>`、`/v/<id>`、`youtu.be/<id>`，ID 为 `[A-Za-z0-9_-]{11}`） |
| `url_detect.py:57-80` | `detect_platform` 加 YouTube 分支；播放列表链接（带 `list=`）仍判为 YouTube，由下游按单视频处理并说明 |
| `url_detect.py:83-124` | `extract_platform_id` 加 YouTube 分支返回视频 ID |
| `cookies.py` | 按平台挑文件与校验登录态（第三节） |
| 新建 `youtube.py` | `YoutubeDownloader(PlatformDownloader)`：`download_audio(url, output_dir, *, media="audio")` 复用 `download` 模块的 `resolve_video` + `YtdlpProcess` + `ytdlp_args`；`fetch_subtitle(url)` 返回 `SubtitleResult` |
| 新建 `youtube_subtitle.py` | 语言优先级排序、选语言、`--skip-download` 下字幕、json3 与 vtt 解析成 `SubtitleItem` |
| `subtitle.py:49-75` | `BilibiliSubtitle` → `Subtitle`、`BilibiliSubtitleItem` → `SubtitleItem`（保留旧名字作别名）；`SubtitleResult.subtitle` 类型改成 `Subtitle \| None` |
| `resolver.py:22` | 加 import |
| `resolver.py:167` 之后 | 加 YouTube 分支，返回 `ResolvedInput`（`bvid` = `input_bvid or metadata.bvid`，`platform=Platform.YOUTUBE`，`subtitle_reason` 写明无字幕或未登录） |
| `resolver.py:33` | `subtitle` 字段类型改成 `Subtitle \| None` |
| `cli.py:256-320` | 加 `ytsub` 子命令；`resolve` 加 `--media`；`cookies` 加 `--platform` |
| `__init__.py:50-103` | 导出新增的公开名字 |

`artifacts.py` 不改：`session_dir_name`、`subtitle_artifact_paths`、`write_meta_json` 都与平台无关（子代理核对过，`write_meta_json` 的 `aid`/`tid` 用 `getattr` 取默认值）。

### download 模块

只加一个函数，不改现有结构：`ytdlp_engine.py` 里加 `download_subtitles(*, url, out_dir, output_base, lang, auto, proxy, cookie_file, cookie_from_browser, ffmpeg_location) -> Path`，拼 `--skip-download --write-subs/--write-auto-subs --sub-langs <lang> --sub-format json3/vtt/best`，用目录前后对比找出新文件并返回。

`service.py`、`models.py`、`cli.py` 不动（`video` 子命令现有行为保持）。

### doctor 模块

- `checks.py:38-49` 的依赖表：`yt_dlp` 的「缺了挡住谁」加上 `ihatevideos-input`（YouTube 接入后 yt-dlp 成为 input 的依赖）；`webvtt-py` 加进表。
- `checks.py:336 check_bilibili` 旁边加 `check_youtube`：cookies 文件（按 `find_cookies_file(Platform.YOUTUBE)`）、登录态（`verify_youtube_login`）、站点可达（请求 `https://www.youtube.com/robots.txt` 或 `https://www.youtube.com`）。没有 cookies 记 `MISSING`（挡住 input 的 YouTube 字幕与需要登录的视频），登录态失效记 `WARN`，与 B 站那组的轻重一致。
- `skills/ihatevideos-doctor/SKILL.md` 的报告说明表加一行 YouTube。

### 文档

- `skills/ihatevideos-input/SKILL.md`：支持的域名列表（`:14-17`）、`platform` 取值与 `subtitle` 字段说明（`:86-89`）、`ytsub` 命令、语言优先级（TODO-002）、退出码。
- `skills/ihatevideos-download/SKILL.md:65`：「B 站、小宇宙、喜马拉雅走 `ihatevideos-input`」改成含 YouTube 的分工说明（取字幕与音频走 input，取整段视频走 download）。
- `README.md`：命令表加 `ytsub`，cookies 一节写明两份文件按域名区分。
- `CHANGELOG.md` 加 0.9.0 条目，`VERSION`、`pyproject.toml`、`uv.lock` 同步。

## 七、依赖变化

新增 `webvtt-py`（解析 YouTube 的 vtt 字幕）。`yt-dlp`、`httpx` 已有。

## 八、测试

| 文件 | 覆盖 |
|---|---|
| `tests/test_input_url_detect.py`（新建） | YouTube 链接形态判定与 ID 提取：`watch?v=`、`shorts/`、`live/`、`embed/`、`youtu.be/`、带 `&t=` 与 `&list=` 参数、`music.youtube.com`、非法 ID 长度、非 YouTube 域名 |
| `tests/test_input_youtube_subtitle.py`（新建） | json3 与 vtt 样本转 `SubtitleItem`：样本放 `tests/data/`，覆盖空段、滚动重复行、毫秒换算、`<c>` 标签与 `align` 行剔除 |
| `tests/test_input_cookies.py`（新建） | 按平台挑文件：两份文件各归其主、缺必需字段时跳过、目录不存在、同名多份取最新 |
| `tests/test_input_subtitle.py`（已有） | 语言优先级表：中简 > 中繁 > 英 > 其它，人工优先于自动 |
| `tests/test_doctor.py`（已有） | 新增的 YouTube 检查组在缺依赖时记 `SKIP` |

`resolver` 的 YouTube 分支与真实下载不做单元测试（会依赖网络与真实 cookies），靠真机验收。

## 九、真机验收

1. `uv run ihatevideos-input ytsub <一个公开且有中文字幕的视频>` → 会话目录里出现 `_sub.txt`、`_sub_items.json`、`_meta.json`，退出 0。
2. 同一个链接换成没有字幕的视频 → 退出 3，`reason` 写明原因。
3. `uv run ihatevideos-input resolve --url <链接>` → JSON 里 `platform` 为 `youtube`、`subtitle_chars` 大于 0、`subtitle_lang` 与 `subtitle_source` 有值。
4. 找一个同时有中简与英文人工字幕的视频 → 选中中简。
5. `uv run ihatevideos-input resolve --url <链接> --media video` → 得到 mp4，`ffprobe` 能读到音轨与视频轨。
6. `uv run ihatevideos-input cookies --platform youtube` → `login: true`，退出 0。
7. 端到端：YouTube 链接 → `resolve --media video` → 写一篇笔记（`study-notes` 模板）→ `summarize frames` → `summarize insert` → 打开笔记确认图片与正文都在。
8. `uv run ihatevideos-doctor --only youtube`（或并入现有分组）→ cookies 与登录态两项状态正确。
9. `uv run pytest tests -q` 全通过。

## 十、实施顺序

每一步都以「能跑通并有验证」为完成条件。

1. `url_detect.py` 加 YouTube 判定与 ID 提取 + 单元测试。此时 `input detect <YouTube 链接>` 就能报出 `youtube`。
2. `cookies.py` 按平台挑文件与校验登录态 + 单元测试 + `input cookies --platform youtube` 真机验证。
3. `subtitle.py` 的字幕结构改名（保留别名）+ 语言优先级统一 + 既有测试通过。
4. 新建 `youtube_subtitle.py`（选语言、下字幕、解析）+ 单元测试。
5. `download/ytdlp_engine.py` 加 `download_subtitles`，第 4 步接上它。
6. 新建 `youtube.py` 的 `YoutubeDownloader`，`resolver.py` 加分支，`cli.py` 加 `ytsub` 与 `resolve --media`。
7. doctor 的依赖表与 YouTube 检查组，`skills/` 两份文档、`README.md`、`CHANGELOG.md`、`VERSION` 同步。
8. 真机跑第九节全部条目，`TODO.md` 勾掉 TODO-001 与 TODO-002。

版本按 0.9.0（新增平台与命令），提交按 `feat:` 一条，或按上面第 1 至 3 步（input 侧平台与 cookies）、第 4 至 6 步（字幕与下载）、第 7 步（doctor 与文档）分三条。
