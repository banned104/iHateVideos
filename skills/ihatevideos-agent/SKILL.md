---
name: ihatevideos-agent
description: Run the supervised iHateVideos video agent (LangChain) for end-to-end Bilibili intake in a terminal session. Use this skill when the user wants the agent itself to handle a video URL — login check, subtitle fetch, approval prompts — instead of running each CLI by hand. The agent only calls project CLIs and reads/writes files; writes outside temp/ pause for terminal y/n approval.
---

# iHateVideos Agent (supervised runner)

You start one supervised session. The agent checks login state, tells the
user what to do when something is missing, runs project CLIs, and asks y/n
before writing outside `temp/`.

## When to use

- User gives a video URL and wants the agent to drive the whole intake.
- User wants approvals handled interactively in the terminal.
- Never for transcription, summarization, or rendering (later modules).

## Module location

- Code: `src/ihatevideos/agent/` (`config.py`, `tools.py`, `harness.py`,
  `runner.py`, `cli.py`), LangChain `create_agent` plus three tools.
- Config: `config.toml` at the project root, `[model]` with `api_base`,
  `api_key`, `model` (OpenAI compatible, never committed). Copy the
  tracked `config.example.toml` there and fill real values. Missing file
  stops with instructions.
- Run from the project root with `uv run`.

## API (three calls cover everything)

```bash
uv run ihatevideos-agent run --url "<B站链接>"
uv run ihatevideos-agent run --task "<自由任务描述>"
```

Session flow, in order:

1. Bilibili tasks run a login preflight. State not ok stops the session
   and prints 3 steps: export browser cookies to `temp/config/`, press
   Enter, auto import plus recheck. Key never enters chat.
2. Agent loop: `run_cli` (project CLI whitelist), `read_file` (project,
   temp, external readable), `write_file` (`temp/` direct).
3. Writes outside `temp/` pause with a terminal y/n prompt. `y` approves,
   anything else rejects with a retry hint.
4. Session ends printing one JSON: `session_dir`, `artifacts`, `status`,
   `note`. Downstream steps take `session_dir` verbatim.

## Rules

1. One session handles one task. New task means a new run.
2. Cookie problems never reach the model loop: preflight resolves them
   first, or the session exits with code 2.
3. Approval prompts only appear for outside-`temp/` writes. Everything
   else runs without pausing.
4. Never invent artifact paths. Only paths printed by CLI output or the
   final JSON exist.
5. No QR login path exists in this project. Cookie import is the only
   login method.

## Test prompts for this skill

1. "跑这个视频：`https://www.bilibili.com/video/BV1Kxeb6mE8o/`，字幕进会话目录。"
2. "登录态失效时停下，按三步提示我操作，不要自己猜密钥。"
3. "让 Agent 写仓库源码外的路径，必须先弹 y/n 审批。"
