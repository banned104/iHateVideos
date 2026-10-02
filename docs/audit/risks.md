# iHateVideos 工程风险清单

分析对象：`f:\Codes\iHateVideos\iHateVideos`，提交 `f2934653a763af1704c19c5bc387d1b524b042a2`。

判定标记：`确认` 表示有代码路径或实验输出作为依据；`待确认` 表示依据代码推断出可能性，需要实际运行对应场景才能定论。分析 skill 要求把可疑之处标为启发式结论，没有经过实际场景复现的条目都不作为已经确认的问题。

## R1 中文输出编码与 Agent 解码方式不匹配

判定：确认（有实验输出）

现象：`input`、`export`、`summarize`、`agent` 四个命令行没有把输出流编码固定为 UTF-8，`media` 一个模块固定了。当前 Windows 代码页是 cp936，这四个命令输出的中文按 GBK 编码写入管道，而 `agent/tools.py` 的 `run_cli` 用 `encoding="utf-8"` 解码子进程输出。

证据：

- `src/ihatevideos/media/cli.py:299-303` 有 `stream.reconfigure(encoding="utf-8")`，其余四个 `main` 函数（`input/cli.py:335`、`export/cli.py:122`、`summarize/cli.py:136`、`agent/cli.py:30`）没有。
- `src/ihatevideos/agent/tools.py:43` 使用 `encoding="utf-8"`。
- 实验：用 UTF-8 解码运行 `ihatevideos-input ids "【科技补全120】测试"`，输出里的中文变成不可读的替换字符序列；对照运行 `ihatevideos-media probe` 并传入含中文的路径，UTF-8 解码正常。

影响：Agent 拿到的 `session_dir`、标题、产物路径在含中文时出现乱码，后续 `read_file`、`write_file`、下游命令都会失败。这条链路恰好是 Agent 的主要用法（B 站标题几乎都含中文）。`temp/` 下的历史会话目录名称为中文，说明这条路径实际会被走到。

## R2 temp 外写入的审批通过后仍然被拒绝

判定：确认（代码路径）

现象：`harness.py` 对写入 `temp/` 之外的 `write_file` 调用挂审批，用户输入 `y` 表示批准；`tools.py` 的 `write_file` 对 `temp/` 之外的路径直接抛出 `ValueError`。

证据：

- `src/ihatevideos/agent/harness.py:22-27` 与 `:42-50`：`when=lambda request: writes_outside_temp(...)` 决定是否中断。
- `src/ihatevideos/agent/tools.py:80-81`：`if not target.is_relative_to(resolved_temp): raise ValueError(...)`。
- `.venv/Lib/site-packages/langchain/agents/middleware/human_in_the_loop.py:425` 确认 `when` 返回真值时进入中断流程。

影响：批准之后工具仍然报错，模型只能改到 `temp/` 内重试。README 第 11 行写"写 temp 外暂停审批"，`skills/ihatevideos-agent/SKILL.md` 第 43 至 44 行写"y approves"，`runner.py` 的拒绝提示写"换 temp 目录内的路径重做"，三处文字都让读者以为批准可以写外部路径。

## R3 模板文件的注释指错配置位置

判定：确认

现象：`config.example.toml` 第一行写"复制成 `temp/config/config.toml` 再填真实值（temp/ 不提交）"，实际读取位置是工程根目录的 `config.toml`。

证据：`src/ihatevideos/agent/config.py:37` 的 `config_file=resolved / "config.toml"`；`README.md` 第 31 行与 `skills/ihatevideos-agent/SKILL.md` 第 22 至 25 行都写根目录 `config.toml`。`config_dir` 只用于存放用户粘贴的 cookies.txt。

影响：按模板注释操作的读者会把配置放到 `temp/config/`，两个命令都会以退出码 2 停止并提示找不到 `config.toml`。

## R4 summarize 模块没有接入 Agent 白名单

判定：待确认（需要确认设计意图）

现象：`ihatevideos-summarize` 有完整的命令行与 Skill 文档，`agent/tools.py` 的 `ALLOWED_COMMANDS` 只包含 `ihatevideos-input`、`ihatevideos-export`、`ihatevideos-media`。

证据：`src/ihatevideos/agent/tools.py:7-14`；`README.md` 第 11 行写 Agent"按流程调用上面两个模块"；`CHANGELOG.md` 0.3.0 只记录新增 media 四个子命令。

影响：Agent 会话无法完成到总结这一步，用户需要离开会话手工执行。若这是有意安排，README 与 `skills/ihatevideos-agent/SKILL.md` 的流程描述可以写清边界。

## R5 未使用导入与无调用点的公开接口

判定：确认（静态检查）

现象：`ruff check src` 报 2 处未使用导入，另有若干公开函数在整个工程内没有任何调用点。

证据：

- `src/ihatevideos/agent/cli.py:2` 导入 `sys` 未使用；`src/ihatevideos/summarize/cli.py:9` 导入 `CUSTOM_PRESET` 未使用。
- `TIMELINE_SCHEMA_VERSION`（`export/json_to_md.py:9`）只出现在 `export/__init__.py` 的导出列表。
- `build_transcription_artifact_name`（`input/platform.py:78`）只出现在 `input/__init__.py` 导出列表与 `skills/ihatevideos-input/SKILL.md`。
- `fetch_xiaoyuzhou_metadata`（`input/xiaoyuzhou.py:351`）只出现在 `input/__init__.py` 导出列表。
- `batch_format_markdown`（`export/markdown_fmt.py:54`）只出现在 `export/__init__.py` 导出列表。
- `extract_bilibili_page_from_target_id`（`input/bilibili_ids.py:58`）既没有调用点，也没有进入任何导出列表。

影响：阅读时需要区分对外接口与移植时的残留。`skills/ihatevideos-input/SKILL.md` 第 97 行把 `build_transcription_artifact_name` 列为可用辅助函数，实际没有任何代码路径使用它。

## R6 markdownlint 调用在 Windows 下的 shell 写法

判定：待确认

现象：`export/markdown_fmt.py:41-48` 用 `shell=True` 执行 `markdownlint-cli2 --fix "<路径>" || true`。Windows 下 `shell=True` 走 `cmd.exe`，`||` 右侧的 `true` 不是系统命令。

证据：`src/ihatevideos/export/markdown_fmt.py:41-48`；本机 `Get-Command markdownlint-cli2` 没有结果。

影响：本机因为 `markdownlint-cli2` 未安装，这段代码不会执行，暂时看不到后果。安装该工具后格式化大体仍会生效，`true` 不存在带来的错误输出会被 `capture_output=True` 吞掉，只影响失败分支的语义。

## R7 小宇宙时长字段的直接整数转换

判定：待确认

现象：`input/xiaoyuzhou.py:230` 是 `duration = int(episode.get("duration", 0) or 0)`。页面 `__NEXT_DATA__` 里该字段若是形如 `"1234"` 的字符串可以正常转换，若是 `"1:23"` 这类文本会抛出 `ValueError` 并中断整次解析。

证据：`src/ihatevideos/input/xiaoyuzhou.py:230`。同一函数里其余字段都经过 `_clean_text`、`_first_non_empty` 之类的容错处理，只有时长做了直接转换。

影响：页面结构变化时会以异常形式中断，符合工程的就地崩溃约定，需要实际抓取一次页面才能确认字段类型。

## R8 重复出现的条目

判定：确认（影响很小）

- `.gitignore` 第 58 行与第 61 行都写了 `.agents`。
- `src/ihatevideos/agent/runner.py:13` 的 `BILIBILI_HINTS` 里 `"bilibili"` 出现两次。

## R9 宽泛异常捕获与就地崩溃约定的张力

判定：确认（属于已有设计取舍）

现象：多处用宽泛捕获把失败转成降级路径。

证据：`input/resolver.py:104-105`（元数据失败只记警告）、`input/subtitle.py:87-89`（字幕失败按缓存未命中处理）、`input/comments.py:262-269`、`:304-315`、`:349-357`（评论接口失败改用旧接口或返回部分结果）、`input/cli.py:157-158`（元数据失败后用 BV 号当标题）。

影响：字幕与评论的降级在 Skill 文档里写明是正常结果，属于有意安排。`input/cli.py` 的元数据降级会让会话目录名丢掉发布日期，退回当天日期，这一点文档没有提到。

## R10 自动化测试只覆盖下载模块

判定：部分确认

现象：`tests/` 目录与 `pytest` 依赖是随 `download` 模块引入的，覆盖下载模块的参数组装、格式选择表达式、文件名清洗、状态流转与 yt-dlp 的行解析与信息树解析，共 39 个用例。`input`、`export`、`summarize`、`media` 仍然没有测试，质量验证依靠手工运行命令与各 Skill 的 `evals.json`。

证据：`tests/` 目录与 `pyproject.toml` 的 `[dependency-groups] dev`；`uv run pytest tests -q` 得 39 passed。

影响：`media` 模块的参数摘要、时间解析、表格提取这些纯函数逻辑仍没有回归保护；`ihatevideos-media` 与 `ihatevideos-download` 没有 `evals.json`，其余四个 Skill 有。

## 已知待办

`TODO.md` 记录两项：YouTube 字幕接入 `input` 模块（验收要求 `ytsub` 命令对公开视频产出会话目录双文件、无字幕返回退出码 3）、语言优先级确认（写明中简、中繁、英的选用顺序）。

## 工程缺口

工程内没有语音识别实现。`ihatevideos-export` 的 `json2md` 只接受外部已经产出的转录 JSON（`export/json_to_md.py` 兼容 Qwen、Groq、火山三种结构），`docs/cloud-stt.md` 是选型调研与适配器设想，没有对应代码。转录这一步当前由工程之外的流程完成。



