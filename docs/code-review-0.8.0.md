# iHateVideos 代码审查报告（0.8.0）

审查日期：2026-10-08

审查范围：`src/ihatevideos/` 全部七个模块（`download`、`export`、`input`、`media`、`stt`、`summarize`、`doctor`）、`tests/`、`pyproject.toml` 与八个命令入口、`skills/`、`templates/`、`README.md` 与 `docs/` 的描述一致性。

审查方式：六个只读审查任务按模块分工阅读，主代理按每条结论给出的 `file:line` 回到源码核对，能用命令确认的用命令确认（时间标签格式、命令退出码、模块导入范围）。下列条目全部经过核对。

## 缺陷

### 严重级别 高

**1. `src/ihatevideos/input/bilibili_audio.py:183-200` — 本次下载没有产出新文件时，回退成目录里任意一份音频文件**

下载前记下输出目录里已有的音频（183 行），下载后取新增文件（192-196 行）。新增集合为空时（197-198 行）直接扫描整个输出目录，把上一次运行留下的文件当作这一次的结果返回。`resolver.py` 随后用这个文件名提取 BV 号，会把不相干的 BV 号写进 `ResolvedInput.bvid`。

后果：B 站音频下载失败时返回错误音频与错误标识，退出码仍然为 0，调用方分辨不出来。

建议修法：新增文件集合为空时抛出异常，附带 yutto 的退出码与输出目录。

**2. `src/ihatevideos/export/markdown_fmt.py:38-51` — 把路径拼进 shell 命令字符串**

`subprocess.run(f'markdownlint-cli2 --fix "{md_path}" || true', shell=True, ...)`。路径里带双引号时命令结构被改变，`-o` 参数可以带出额外命令；`|| true` 依赖 POSIX shell，PowerShell 作为解释器时 `markdownlint-cli2` 直接报语法错误，格式化静默失效，50 行的宽捕获再把异常降级成 debug 日志。

建议修法：改成参数列表传入并去掉 `shell=True`，失败状态用返回码判断。

### 严重级别 中

**3. `src/ihatevideos/summarize/insert.py:75-87` — 图片扩展名与实际产物不一致时，全部占位符被判成缺失**

`asset_path(md, item.seconds, fmt)` 只按 `--format` 拼路径，82 行只认 `image.is_file()`。`frames --format png` 生成图片后执行 `insert`（默认 `jpg`），正文里的占位符全部原地保留，`missing` 全量非空，退出码 3，而图片都在 `assets/` 里。

建议修法：`--format` 之外再按支持的扩展名查找已有图片，找不到时在 `missing` 的提示里写出实际查找过的路径。

**4. `src/ihatevideos/download/service.py:234-237` 与 `aria2_engine.py:80` — 服务器给出的文件名不经过清洗**

`probe_filename` 的返回值直接写进 `task.filename`，再进 `save_dir / task.filename` 与 aria2c 的 `out` 选项（`aria2_args.py:104-105`）。`sanitize_basename` 只在用户给 `--filename` 的分支（`service.py:275`）与 `name_from_url`（`filenames.py:24`）里调用。服务器返回带路径分隔符的文件名时会写到目标目录之外。

建议修法：`task.filename = sanitize_basename(probed or name_from_url(task.source))`。

**5. `src/ihatevideos/download/aria2_args.py:103` — 任务级 `max-download-limit` 覆盖全局限速**

`build_task_options` 无条件写入 `max-download-limit`，不限速时取值 `"0"`（`format_limit`，`aria2_args.py:63-64`）。aria2c 的任务级选项优先于启动参数里的 `--max-download-limit`，于是用户只给 `--global-limit` 不给 `--limit` 时限速静默失效。`aria2_engine.py:131` 的 `set_global_limit` 没有任何调用点。

建议修法：不限速时任务级选项里不写 `max-download-limit`，或者让 `set_global_limit` 在进程启动后调用一次。

**6. `src/ihatevideos/download/ytdlp_progress.py:96-97` — 首尾带引号的输出行直接进 `json.loads`**

解析没有保护，遇到非 JSON 内容抛出 `JSONDecodeError`。这条路径在 yt-dlp 的读取线程里执行（`ytdlp_process.py` 的 `_drain`），主循环看不到异常，任务最终被判定成「正常结束但没有给出最终路径」。

建议修法：解析失败时当作普通输出行返回 `None`。

**7. `src/ihatevideos/stt/engine.py:15` 与 `stt/cli.py:105-106` — 默认设备是 `cuda:0`**

`--gpu` 默认 `None`，`configure_gpu(None)` 直接返回，不写 `CUDA_VISIBLE_DEVICES`，权重落到物理第 0 块卡。这与「STT 用 GPU 1」的要求不符，机器上第 0 块卡被占用时整次转写失败。

建议修法：`--gpu` 的默认值改成 `1`，`--device` 保持 `cuda:0`（写入 `CUDA_VISIBLE_DEVICES` 之后索引重新编号）。

**8. `src/ihatevideos/stt/sentences.py:24-42` 与 `76-86` — 字符与时间戳单元的对应关系建立失败时，句子时间戳取到邻近单元甚至整句为 0**

`_clean_to_unit_index` 只在两侧字符相等时同时推进 `left` 与 `right`（34-38 行），不相等时只推进 `left`（39-41 行）。识别文本里有时间戳模型没有的字符时（例如 `C++` 的加号），`right` 停住，后续字符被逐个跳过；时间戳模型多输出字符时，匹配位置会串到别的单元。`_time_range_ms` 在句子起点之后找不到任何对应单元时返回 `(0, 0)`（81-82 行），典型情形是文本末尾出现这类字符。

后果：句子时间轴失真，导出的笔记里时间点不可信。

建议修法：两侧文本不一致时按字符位置在已匹配区间之间插值取时间，并在输出里标出没有时间的句子。

**9. `src/ihatevideos/media/timestamps.py:61-70` — 时间标签四舍五入到 0.1 秒，两个不同区间共用一个标签**

`format_clip_label(59.96)` 与 `format_clip_label(60)` 都返回 `01m00s`（已用命令确认）。该标签是剪切产物文件名的组成部分，`clip` 的 `--reuse` 按文件名与字节数判断复用，两个不同区间因此共用同一份产物。

建议修法：标签保留到毫秒，或者把区间的原始数值一并写进文件名。

**10. `src/ihatevideos/doctor/checks.py:286-287` — 权重缺失时 `--deep` 会产生两条阻塞项**

`check_stt` 在 `deep` 为真时无条件调用 `run_model_smoke`，`run_model_smoke` 又捕获全部异常报成「模型加载 FAIL」（`smoke.py:214-220`）。权重缺失这一件事于是同时产生「识别模型权重 MISSING」与「模型加载 FAIL」两条阻塞记录。

建议修法：权重未就绪时把「模型加载」记成 `SKIP`，只保留权重那一条。

**11. `pyproject.toml:8` — `requires-python = ">=3.11"` 与实际运行版本不一致**

虚拟环境是 CPython 3.12.13，`uv sync` 在 3.11 解释器上同样会解析成功。建议改成 `>=3.12`，或者写清真实的版本下限。

### 严重级别 低

**12. `src/ihatevideos/doctor/cli.py:56-57` — `--keep` 的产物不跨次保留**

不带 `--keep` 时删除整个 `temp/doctor`，上一次用 `--keep` 留下的产物一并被清掉。`--only` 不含 `ffmpeg`、`stt` 时即使带 `--keep` 也不会产生这个目录。

**13. `src/ihatevideos/doctor/checks.py:57` — `find_spec` 没有保护**

`_missing_of` 直接调用 `importlib.util.find_spec(name)`，父包损坏时会抛出 `ModuleNotFoundError`。「环境残缺时仍能出报告」在这条路径上不成立。建议套一层捕获，只把抛出的情况当作缺失。

**14. `src/ihatevideos/doctor/smoke.py:192-221` — 模型加载没有超时**

`run_model_smoke` 不接收 `timeout` 形参，内部只对造静音样本的 ffmpeg 调用设了超时，`load_asr_model` 卡住时只能人工终止。

**15. `src/ihatevideos/summarize/insert.py:93-94` — 换行符被整篇改写**

`write_text` 在 Windows 上把 `\n` 写成 `\r\n`，一份 LF 换行的笔记只要被 `insert` 改动一次，全篇换行都会变样。建议显式指定 `newline="\n"` 或按原文的换行写回。

**16. `src/ihatevideos/export/timeline.py:60-66` — 单元格数量不足的行被原样保留**

`time_index` 不在该行范围内时不删除任何单元格（63-64 行），重新拼接后各行剩下的列数不同，Markdown 表格渲染错位。同一文件的 `extract_timeline_entries` 对这种行是跳过的，两处行为不一致。

**17. `src/ihatevideos/input/cli.py:162-165` — 元数据获取失败被宽捕获**

`except Exception` 后 `metadata` 置空，会话目录改用当天日期，`meta.json` 不写，stdout 里没有任何字段说明原因，退出码仍为 0。建议把失败原因写进 stdout 的 JSON。

**18. `src/ihatevideos/export/cli.py:1-15` 与 `export/__init__.py:1-10` — 模块文件开头是 docstring**

与「Python 文件最前面不允许 docstring」的约定不符。

**19. `pyproject.toml:4` — `description` 还是脚手架默认值** `Add your description here`，会进包元数据。

## 测试缺口

`tests/` 现有 7 个文件：`test_doctor.py`、`test_summarize.py`、`test_stt_sentences.py`、`test_input_subtitle.py`、`test_download_args.py`、`test_download_json.py`、`test_download_progress.py`。

- `media` 模块九个源文件零测试。`parse_seconds`、`format_clip_label`、`probe_media` 的字段解析、`build_timestamps`、`capture_frames`、`chunk_audio`、`cut_media` 全部没有用例。
- `export` 模块六个源文件零测试。`json_to_md.py`、`tables.py`、`timeline.py`、`markdown_fmt.py`、`cli.py` 全部没有用例，缺陷 2 与 16 都在这里。
- `stt` 只有 `sentences.py` 的 `group_sentences` 有测试。`engine.py`、`audio.py`、`paths.py`、`models.py`、`service.py`、`cli.py` 零测试，缺陷 8 的两种触发条件都没有用例。
- `doctor` 只有 `models.py` 与 `report.py` 的数据逻辑有测试。七个 `check_*` 函数、四个烟测函数、`cli.main` 的退出码映射零测试。
- `download` 的 `service.py`（任务调度、状态流转、回退重跑）、`aria2_process.py`（进程启动与收尾）、`binaries.py`、`install_binaries.py`、`proxy.py` 零测试。
- `input` 的 `resolver.py`、`url_detect.py`、`bilibili_ids.py`、`artifacts.py`、`comments.py`、`metadata.py`、`xiaoyuzhou.py`、`ximalaya.py`、`bilibili_audio.py` 零测试，缺陷 1 就在 `bilibili_audio.py`。
- `summarize` 的 `capture.py` 与 `cli.py` 零测试，`insert` 的「部分命中」分支没有用例。
- 工程里没有 `pytest` 配置（无 `[tool.pytest.ini_options]`、无 `testpaths`、无 `conftest.py`），测试隔离靠各用例自己写 `tmp_path`。

## 文档与实现不一致

- `skills/ihatevideos-stt/SKILL.md:143` 写「超过 20 分钟程序内部按 20 分钟分块；开时间戳时按 3 分钟分块并自动累加时间偏移」。`src/ihatevideos/stt/` 里没有任何分块代码，`service.py` 是一次性抽音频加一次转写。
- `skills/ihatevideos-stt/SKILL.md:149` 写「输入没有音轨 → 退出码 `3`」。`media/audio.py` 抛 `ValueError`，`stt/cli.py:132-134` 映射成退出码 `2`。
- `skills/ihatevideos-media/SKILL.md:93-94` 写「不做兜底」。`media/probe.py:108-119` 的 `_as_int` 与 `_as_float` 在解析失败时返回 0 与 0.0，继续构造 `MediaInfo`。
- `skills/ihatevideos-doctor/SKILL.md:52` 与 `CHANGELOG.md` 写烟测判定「能被读回」。`doctor/smoke.py:91`、`:117` 的取帧与抽音两步只查文件存在与字节数。
- `skills/ihatevideos-doctor/SKILL.md:31`、`:123` 写 `--keep` 保留 `temp/doctor/`，与缺陷 12 描述的跨次行为不一致。
- `README.md:87` 的退出码列表缺 `1`（doctor 自身未预期异常）。
- `docs/audit/summary.md`、`docs/audit/risks.md`、`docs/external/funasr.md`、`docs/cloud-stt.md:82` 描述的是 `agent` 模块还在、工程内没有语音识别的时期，多处指向 `src/ihatevideos/agent/`、`config.example.toml` 与「转录由工程之外的流程完成」。这几个目录此前约定保持原样，是否更新由你决定。

## 建议的修复顺序

1. 缺陷 1、3、8：这三条会让产物本身出错，调用方还看不出来。
2. 缺陷 2、4、6：路径与输出解析上的失败会直接中断任务，且报错方向指向别处。
3. 缺陷 5、7、11：参数与声明和实际行为不符，属于配置语义问题。
4. 缺陷 10、12、13、14：doctor 的报告准确性与自保护。
5. 缺陷 9、15、16、17、18、19：命名、写回与约定层面的整理。
6. 测试缺口按模块补，`media` 与 `export` 优先，这两块当前完全没有用例。
