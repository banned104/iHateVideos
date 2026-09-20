---
name: ihatevideos-export
description: Export layer-1 content artifacts for the iHateVideos project (transcription JSON to Markdown, summary table Markdown, Bilibili-comment timeline text). Use this skill whenever the agent has just produced a transcription JSON or a summary Markdown and needs the human-readable or paste-ready files — even if the request only says "export it" or "make the timeline". Do NOT reimplement table parsing or timestamp extraction; always call ihatevideos.export or the ihatevideos-export CLI instead.
---

# iHateVideos Export (small skill for content导出)

You are the **export step** of a larger video workflow. Upstream hands you a
`transcription.json` and/or a `summary.md`. Your only job: produce the
layer-1 artifacts. You never transcribe, summarize, or render PDF/PNG
(those are layer 2, a different skill).

## When to use

- You hold a `transcription.json` → run `json2md` (always).
- You hold a `summary.md` → try `table` and `timeline` (both may skip).
- Never for STT, LLM summarization, comments, or PDF/PNG/HTML rendering.

## Module location

Belongs to the `iHateVideos` uv project:

- Code: `F:\Codes\iHateVideos\iHateVideos\src\ihatevideos\export\`
- Run from `F:\Codes\iHateVideos\iHateVideos` with `uv run`.

## API and CLI (same thing, pick one)

Python:

```python
from ihatevideos.export import (
    convert_json_to_md,                        # json -> 原文.md (always returns Path)
    export_summary_table_without_video_time,   # summary -> *_table.md | None
    export_summary_timeline_text,              # summary -> *_timeline.txt | None
)
```

CLI (preferred for Agent shell steps — machine-readable JSON on stdout):

```bash
uv run ihatevideos-export json2md <transcription.json> [-o OUT] [--min-length 60]
uv run ihatevideos-export table <summary.md> [--keep-time]
uv run ihatevideos-export timeline <summary.md>
```

## Agent judgement (how to decide)

Follow this decision table exactly. `skipped` is a **normal** outcome,
not a failure — never retry a skipped export, never ask the user about it.

| Situation | Action | Reason |
|---|---|---|
| Have `transcription.json` | MUST run `json2md` | Downstream (summary, review) reads the `Speaker MM:SS` Markdown, never raw JSON |
| Have `summary.md` | TRY `table`, then TRY `timeline` | Each decides for itself; one may produce while the other skips |
| `table` exit `0` | Pass `*_table.md` on as "clean table for humans" (no 视频时间 column) | Default drops the time column; use `--keep-time` only if the next step explicitly needs timestamps in the table |
| `table` exit `3` (`no markdown table found`) | Continue WITHOUT the table file | Some presets/summaries legitimately contain no table |
| `timeline` exit `0` | Pass `*_timeline.txt` on as "paste-ready for Bilibili comments" (`MM:SS 名称（代码）`, sorted, deduped, `<br>` split) | Only file meant for comment pasting |
| `timeline` exit `3` (`no parseable 视频时间`) | Continue WITHOUT the timeline file | No time column or no parseable `MM:SS` is a valid summary shape |
| `json2md` fails / file missing (exit `2`/`1`) | STOP and report — do not fabricate Markdown | The 原文 Markdown is load-bearing; everything downstream depends on it |
| Which table? | Always the LAST table in the file | Summaries append tables at the end; earlier tables (if any) are drafts |
| Timestamps look estimated? | Export anyway, flag it | The extractor only copies `MM:SS` text; timestamp honesty is the summarizer's duty, not yours |

Exit codes: `0` produced · `3` skipped-normally · `2` bad input · `1` unexpected failure.

## Output back to the orchestrator

```python
{
    "原文_md": str | None,      # from json2md, None only if it failed (then you already stopped)
    "table_md": str | None,     # None when skipped (exit 3) — normal
    "timeline_txt": str | None, # None when skipped (exit 3) — normal
}
```

Never invent a path that the command did not print.

## Dependencies

None beyond the Python standard library. `markdownlint-cli2` is used
opportunistically for formatting and silently skipped when absent.

## Test prompts for this skill

1. "把这份转录 JSON 转成原文 Markdown：`<path>/demo_transcription.json`，告诉我 Speaker 时间行是否正确。"
2. "这份总结 `<path>/demo_summary.md` 有表格，同时导出干净表格和B站时间线，并说明两个文件的用途区别。"
3. "这份总结 `<path>/plain_summary.md` 没有表格，跑 table 和 timeline，确认返回的是正常跳过（exit 3）而不是失败。"
