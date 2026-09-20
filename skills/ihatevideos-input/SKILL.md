---
name: ihatevideos-input
description: Ingest one video/audio input for the iHateVideos project (Bilibili, Xiaoyuzhou, Ximalaya, or a local audio file) into unified audio + metadata + optional native subtitle. Use this skill whenever the agent needs to accept a video URL or uploaded file before splitting, transcribing, or summarizing — even if the request only says "handle this link" or "process this file". Do NOT reimplement URL detection, BV ID parsing, or per-platform downloaders; always call ihatevideos.input instead.
---

# iHateVideos Input (small skill for video拆分)

You are the **input step** of a larger video-splitting workflow. A big skill
orchestrates you plus other small skills (transcribe, split, summarize). Your
only job: turn **one raw input** into a standard `ResolvedInput`.

## When to use

- User or orchestrator gives you a video URL (`bilibili.com`, `b23.tv`,
  `xiaoyuzhoufm.com/episode/...`, `ximalaya.com/sound/...`, `xima.tv/...`)
  or a bare `BV号`.
- User or orchestrator gives you a local audio file path.
- Never for transcription, frame extraction, or summarization itself.

## Module location

This skill belongs to the `iHateVideos` uv project (sibling of
`bilibili2text`, not a standalone project):

- Code: `F:\Codes\iHateVideos\iHateVideos\src\ihatevideos\input\`
- Project: `F:\Codes\iHateVideos\iHateVideos\pyproject.toml`
- Run everything with `uv run` from `F:\Codes\iHateVideos\iHateVideos`.

## API (use exactly this)

End-to-end Bilibili subtitle flow. Three CLI calls, zero Python needed:

```bash
uv run ihatevideos-input cookies --check
# state: ok -> go to step 3. otherwise -> step 2.
uv run ihatevideos-input cookies --file <pasted-file>
uv run ihatevideos-input subtitle <bilibili-url> --out-dir temp
# exit 0 -> session_dir + text_path + items_path ready. exit 3 -> no native subtitle, go to ASR.
uv run ihatevideos-input comments <bilibili-url> --limit 10 --reply-limit 10 --session-dir <session_dir>
# optional step, Bilibili only. exit 0 -> comments_json + comments_markdown ready.
# exit 1 -> continue without comments, never block the workflow.
```

## Output paths (intermediate artifacts)

`subtitle` never drops loose files. `--out-dir` defaults to the project
`temp/` (git-ignored). Each call creates one session dir per video:

```
temp/2026-09-19-<标题50字>-<BV号>/BV号_sub.txt
temp/2026-09-19-<标题50字>-<BV号>/BV号_sub_items.json
temp/2026-09-19-<标题50字>-<BV号>/BV号_meta.json
temp/2026-09-19-<标题50字>-<BV号>/BV号_comments.json
temp/2026-09-19-<标题50字>-<BV号>/BV号_comments.md
```

Rules: date is the video publish date, fetch date when unavailable;
title is filename-sanitized; BV号 suffix stays for traceability; an
existing dir gets `_<n>` instead of being overwritten. Downstream steps
(transcribe, split, summarize) receive `session_dir` and read/write inside
it. JSON field `session_dir` is the handoff handle — pass it on verbatim.

Python (only when the orchestrator needs objects instead of files):

```python
from ihatevideos.input import resolve_input

result = resolve_input(
    url="https://www.bilibili.com/video/BV1xx411c7mD?p=2",
    download_dir="./work",      # audio lands here (B站/yutto, 小宇宙, 喜马拉雅)
    audio_quality="30216",      # B站 only, yutto quality code
    prefer_bilibili_subtitle=True,  # B站 only: try native subtitle first
)
# OR for an uploaded file:
result = resolve_input(audio_path="uploads/BV1xx411c7mD_title.m4a")
```

`ResolvedInput` fields:

| field | meaning |
|---|---|
| `audio_file` | `Path \| None` — downloaded/copied audio; `None` when B站原生字幕命中 (no download happened) |
| `metadata` | `VideoMetadata \| None` — `bvid/title/author/pubdate/description/...`; `None` only for local files |
| `bvid` | stable resource id (`BV...`, `BV..._pN` for 分P, `xiaoyuzhou_<eid>`, `ximalaya_<trackId>`) |
| `transcription_id` | storage identity (分P kept separate: `BV..._p2`) |
| `subtitle` | `BilibiliSubtitle(text, items) \| None` — B站 only, with ms timeline; `None` means "go to ASR" |
| `use_local_audio` | `True` only for uploaded files |
| `platform` | `Platform.BILIBILI/XIAOYUZHOU/XIMALAYA`, `None` for local files |

Helpers (only when the orchestrator asks for inspection, not downloading):

- `detect_platform(url) -> Platform | None`
- `extract_bvid(s)`, `extract_bilibili_target_id(s)`,
  `normalize_bilibili_target(s)`
- `resolve_ximalaya_sound_url(url) -> (canonical_url, track_id)`
- `fetch_bilibili_subtitle(target) -> BilibiliSubtitle | None`
- `build_transcription_artifact_name(name, resource_id)`
- `import_bilibili_cookies(path | None) -> Path` — read SESSDATA from a
  browser-exported Netscape `cookies.txt` (or `BILIBILI_COOKIES_FILE` env)
  into the credential file `bili` reads; call it when subtitle fetch fails
  with empty sessdata instead of asking the user to QR-scan

## Rules (why they exist)

1. **One input per call.** Batch URLs by calling repeatedly; the module keeps
   no global state and each call creates its own download dir entry.
2. **B站字幕优先但可降级。** `subtitle is not None` means skip ASR and use
   `subtitle.text/items` directly. `None` (no subtitles, `bili` CLI missing,
   timeout) is a normal cache-miss — fall through to `audio_file` + ASR,
   never fail the whole task for it.
3. **分P是不同资源。** `?p=2` becomes `BV..._p2` in `transcription_id`;
   never merge parts.
4. **喜马拉雅只收单集。** `album/` links raise `ValueError` — ask the
   orchestrator for a concrete `sound` link instead of guessing track order.
5. **本地文件不碰网络。** `audio_path` must exist and its filename must
   contain a `BV号` unless `input_bvid` is given. The original file is never
   deleted or moved.
6. **Errors are typed:** `ValueError` = bad/unsupported input (ask user for a
   new link); `FileNotFoundError` = missing local file or zero downloads;
   `RuntimeError` = platform API failure (retry once, then report).
7. **Bilibili login state first.** Before any Bilibili subtitle fetch, run
   `uv run ihatevideos-input cookies --check`. `state: ok` means proceed.
   `missing / empty / stale / broken` means stop and prompt the user with
   the exact 3 steps from the project README (paste the browser-exported
   file into `temp/` under any name and tell you the filename, run
   `cookies --file` on it, re-run `--check`). Never ask
   the user to paste the SESSDATA value into chat; secrets stay in local
   files. After a successful import, retry the subtitle fetch once.
8. **Comments are optional and Bilibili-only.** Fetch them only when the
   orchestrator needs audience viewpoints (`comments --limit 10
   --reply-limit 10`: 10 hot top-level comments, each with up to 10 child
   replies, UP author marked). Large pulls (`--limit N`, `--all`) need an
   explicit orchestrator demand — never default to them. Non-BV targets
   exit 2 (skip, not an error); fetch failure exits 1 (continue without
   comments, never block transcription or summary). `meta.json`
   (title/author/pubdate/description) lands beside the subtitle files
   whenever metadata succeeds.

## Output back to the orchestrator

Always return these three, nothing more:

```python
{
    "audio_path": str(result.audio_file) if result.audio_file else None,
    "has_native_subtitle": result.subtitle is not None,
    "resource_id": result.transcription_id,
}
```

Pass `metadata` through only if the next step (split/transcribe) needs
title/author. Never invent titles when `metadata is None`.

## Quick self-check (offline, no network)

```bash
uv run ihatevideos-input detect "BV1xx411c7mD"
```

## CLI (same module, no Agent needed)

```bash
uv run ihatevideos-input detect <url>          # offline: bilibili/xiaoyuzhou/ximalaya?
uv run ihatevideos-input ids <bilibili-input>  # offline: bvid/page/target_id/normalized
uv run ihatevideos-input ximalaya <url>        # offline for direct sound links
uv run ihatevideos-input resolve --url <url> --download-dir ./work        # may download
uv run ihatevideos-input resolve --audio-path uploads/BV1xx411c7mD_x.m4a  # local, offline
uv run ihatevideos-input cookies --file cookies.txt  # import login state, no QR needed
uv run ihatevideos-input cookies --check  # ok / missing / empty / stale / broken
uv run ihatevideos-input subtitle <bilibili-url> --out-dir <dir>  # write text + items files
```

`resolve` prints the Skill contract as JSON
(`audio_path/has_native_subtitle/resource_id/...`). Exit codes: `0` ok,
`2` bad input, `1` missing file / platform failure.

## Test prompts for this skill

1. "B站字幕端到端：先 `--check`，坏了就导入用户粘的文件，再 `subtitle` 落文件，报三条路径。"
2. "把这个 B站链接接进来：`https://www.bilibili.com/video/BV1xx411c7mD?p=2`，告诉我有没有原生字幕、音频在哪、resource_id 是什么。"
3. "用户传了一个文件 `uploads/BV1xx411c7mD_访谈.m4a`，按本地输入走，不要联网。"
4. "这个能接吗：`https://www.ximalaya.com/album/12345`？不能的话说明原因并索要单集链接。"
