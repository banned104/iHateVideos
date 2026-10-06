---
name: ihatevideos-doctor
description: 检查这台机器能不能跑 iHateVideos：Python 依赖、外部程序（ffmpeg / ffprobe / aria2c / yt-dlp）、ffmpeg 实际出活能力、GPU 计算、语音识别权重、B 站 cookies 与登录态、系统代理。只要在动手做转写、取帧、下载之前需要确认环境，或者某条命令失败想知道是不是环境问题，或者要把「缺什么、怎么补」报给用户，都用本 Skill。不要自己写脚本去试探 ffmpeg 或 CUDA，一律通过 ihatevideos-doctor 命令或 ihatevideos.doctor 模块。
---

# iHateVideos Doctor（运行环境检查）

你是这个工程里负责「动手之前先看一眼环境」的一步。输入是当前这台机器，产出是一份分组报告。
不改配置、不装东西、不下载权重，只报告现状。

## 何时使用

- 用户第一次在这台机器上用这个工程 → 先跑一遍
- 某条命令报错，先分清楚是环境问题还是输入问题 → 跑一遍
- 要转写之前确认显卡和权重 → `--only gpu,stt`
- 要下载之前确认 aria2c 与 ffmpeg → `--only binary`
- 要把「缺什么」报给用户 → 读 JSON 的 `blockers` 与 `warnings`

## 模块位置

- 代码：`src/ihatevideos/doctor/`（`models.py` 数据类与状态、`checks.py` 七组检查项、
  `smoke.py` 需要真跑的检查、`report.py` 文本与 JSON 输出、`cli.py` 命令行）
- 在项目根目录用 `uv run ihatevideos-doctor ...` 调用
- 它从 `input`、`download`、`media`、`stt` 四个模块取现成的解析函数，不重复实现

## 命令

```bash
uv run ihatevideos-doctor [--only GROUP[,GROUP...]] [--no-smoke] [--deep] [--json] [--keep]
```

| 参数 | 作用 |
|---|---|
| `--only` | 只跑指定分组，逗号分隔 |
| `--no-smoke` | 不跑烟测，只做位置与版本解析 |
| `--deep` | 额外真正加载两份权重并跑一次识别（慢，几分钟） |
| `--json` | 输出 JSON，供上层 Agent 读取 |
| `--keep` | 保留 `temp/doctor/` 里的烟测产物 |

## 分组与检查项

| 分组 | 查什么 |
|---|---|
| `python` | 十个第三方包是否装齐，逐个报版本 |
| `binary` | `ffmpeg`/`ffprobe`（media 侧）、`ffmpeg`/`ffprobe`/`aria2c`/`yt-dlp`（download 侧），以及两份 ffmpeg 是否同一个文件 |
| `ffmpeg` | 烟测：合成样片、读流、截 jpg、截 png、抽 wav、剪一段 |
| `gpu` | torch 与 CUDA、每块卡的矩阵乘、每块卡的显存 |
| `stt` | 识别模型权重、对齐器权重，`--deep` 时真正加载并识别 |
| `bilibili` | cookies 文件、B 站可达、登录态 |
| `network` | 系统代理 |

烟测的做法是用 `lavfi` 现造 1 秒样片，真的走一遍取帧、抽音频、剪切。判定看**产物**（文件存在、字节大于 0、能被读回），不看 ffmpeg 打印的提示文本——提示文本里有警告但产物正常是常见情况。

CUDA 烟测在每块卡上做一次全 1 矩阵乘并比对结果。`torch.cuda.is_available()` 只回答「有没有卡」，回答不了「这块卡能不能真算」。

## 状态取值

| 状态 | 含义 | 怎么处理 |
|---|---|---|
| `ok` | 齐备 | 不用管 |
| `warn` | 能用但有隐患 | 报给用户，不挡事 |
| `missing` | 找不到 | 必修项要停下；补法看 `hint` |
| `fail` | 找到了但跑不通 | 必修项要停下；`detail` 里是原始错误 |
| `skip` | 这次没测 | 带 `--no-smoke` 或没加 `--deep` 时出现，不是问题 |

`missing` 与 `fail` 必须分开看：「ffmpeg 没装」和「ffmpeg 装了但截不出帧」是两回事。

挡住某条命令的检查项算**必修**，其余算**选修**。选修缺了退出码仍是 `0`，只进 `warnings`。

## 输出

默认是分组文本：

```
iHateVideos 运行环境检查
工程根目录  F:\Codes\iHateVideos\iHateVideos

binary  外部程序
- ok    ffmpeg (media)    F:\Softwares\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.EXE  N-126404-g818e5d965b-20260904
- ok    ffmpeg (download) F:\Codes\iHateVideos\iHateVideos\temp\bin\ffmpeg.exe  9.0.2-essentials_build-www.gyan.dev  [temp/bin]
- warn  ffmpeg 一致性      media 用 …，download 用 …
- MISS  aria2c            没找到
        挡住：ihatevideos-download
        补法：ihatevideos-download binaries 会把 aria2c 与 ffmpeg 装到 temp/bin/
```

`--json` 给出同构数据：

```json
{
  "project_root": "工程根目录",
  "ready": false,
  "blockers": ["aria2c"],
  "warnings": ["ffmpeg 一致性", "登录态"],
  "checks": [
    {
      "group": "binary",
      "name": "aria2c",
      "state": "missing",
      "detail": "没找到",
      "blocks": ["ihatevideos-download"],
      "hint": "ihatevideos-download binaries 会把 aria2c 与 ffmpeg 装到 temp/bin/",
      "required": true
    }
  ]
}
```

## Agent 判断

| 情况 | 动作 |
|---|---|
| `ready` 为 `true` | 环境可以用了，继续原本要做的事 |
| 有 `blockers` | 停下，把每项的 `name`、`detail`、`hint` 报给用户，等用户处理 |
| 有 `warnings` | 继续做，但在回答里提一句 |
| `ffmpeg 一致性` 是 `warn` | 说明取帧与下载用的是两份 ffmpeg。本机正常情况下就是两份，不必强求统一；只在出现取帧或合并异常时才当作线索 |
| `登录态` 是 `warn` | cookies 过期了，`ihatevideos-input` 的字幕与评论会拿不到。让用户重新导出一份覆盖 `temp/config/` |
| `B 站可达` 是 `fail` | 网络或代理不通。先看 `network` 组的代理，再让用户检查网络 |
| `python` 组有 `missing` | 让用户跑 `uv sync`，不要自己装包 |
| `stt` 组权重 `missing` | 让用户按 `skills/ihatevideos-stt/SKILL.md` 下载权重，doctor 不下载 |
| 想快一点 | `--no-smoke`，跳过全部需要真跑的检查 |
| 要确认模型真能加载 | 加 `--deep`，会加载两份权重并用 1 秒静音跑一次识别 |
| 想看烟测产物 | 加 `--keep`，产物留在 `temp/doctor/` |

## 退出码

- `0` 必修项齐备（选修缺也返回 `0`）
- `3` 有必修项 `missing` 或 `fail`
- `2` 参数写错（`--only` 给了不存在的分组）
- `1` doctor 自身抛出未预期异常

## 回给上层

- 文本输出直接给人看
- `--json` 给 Agent 读：先看 `ready`，再看 `blockers` 与 `warnings`，需要细节时从 `checks` 里按 `name` 取
- 不要自己拼路径去试探环境，报告里的路径就是各模块实际会用的路径

## 与其它检查命令的关系

`ihatevideos-stt doctor`、`ihatevideos-download engines`、`ihatevideos-input cookies` 三个命令都保留，各自覆盖本模块的细节。`ihatevideos-doctor` 做跨模块汇总，并补上它们没覆盖的部分：ffmpeg 真的能不能出活、CUDA 真的能不能算、两份 ffmpeg 是不是同一个文件。

## 不做的事

- 不自动安装或修复任何东西
- 不下载模型权重
- 不检查代码风格、测试套件、工程目录之外的系统环境
- 不提问、不等待输入。要问用户什么，由调用它的 Agent 决定

## Test prompts for this skill

1. "我想在这台机器上跑语音转写，先帮我看看环境行不行。"
2. "`ihatevideos-media frames` 报错了，是不是 ffmpeg 的问题？"
3. "把这个工程需要的运行环境整体检查一遍，缺什么列给我。"
