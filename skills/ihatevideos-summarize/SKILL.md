---
name: ihatevideos-summarize
description: Summarize video transcripts and comment viewpoints for the iHateVideos project with an LLM. Use this skill when a transcript Markdown or text file exists and a summary Markdown is needed, or when a comments Markdown exists and audience viewpoints must be appended. Model config comes from the project root config.toml (shared with ihatevideos-agent). Never invent timestamps or table rows.
---

# iHateVideos Summarize (small skill for LLM总结)

You turn transcript text into summary Markdown. Two commands, both print
JSON and write files beside the source (session dir when the source lives
in one).

## When to use

- A transcript file (`*_sub.txt`, `*.md`) exists and `*_summary.md` is needed.
- A comments Markdown exists and `## 精选评论观点` must be appended.
- Never for transcription, download, rendering, or table export (use the
  export skill for tables and timelines).

## Module location

- Code: `src/ihatevideos/summarize/` (`presets.py`, `client.py`,
  `summarize.py`, `cli.py`). LLM via LangChain OpenAI compatible client.
- Model config: project root `config.toml`, `[model]` shared with the agent.
  Missing config stops with instructions, exit 2.
- Run from the project root with `uv run`.

## API (three calls cover everything)

```bash
uv run ihatevideos-summarize presets
# offline: timeline_merge (default) / summary / study_notes / investment_podcast
uv run ihatevideos-summarize summary <transcript> [--preset NAME] [--template "..."] [--meta <meta.json>]
# exit 0 -> summary_path ready. exit 2 -> bad input or missing config. exit 1 -> LLM failure.
uv run ihatevideos-summarize viewpoints <summary.md> --comments <comments.md>
# appends ## 精选评论观点 plus stats block. appended:false on empty comments is a normal skip.
```

## Rules

1. One transcript per call. Long transcripts are the caller's problem to
   split; this skill sends the whole file in one request.
2. Preset default is `timeline_merge`. Custom templates must contain the
   `{content}` placeholder or the call is rejected before any billing.
3. Timestamps come only from `Speaker MM:SS` lines in the source. A summary
   that invents times is a failure — the presets already forbid it, and a
   missing time must stay `-`.
4. `--meta` selects the summary header (title/author/published). Without it
   the title is inferred from the filename. Never invent metadata.
5. Viewpoints failures (exit 1) must not delete or truncate the summary.
   The summary stands alone; viewpoints only append.
6. After a summary with a table exists, hand `summary_path` to the export
   skill for table and timeline files.

## Test prompts for this skill

1. "用通用总结处理这份转录，元数据用同目录的 meta 文件。"
2. "把这份评论文件的观点追加到总结末尾，空评论文件要正常跳过。"
3. "列出可用 preset，再试一个不存在的 preset 名称，必须报错而不是调用模型。"
