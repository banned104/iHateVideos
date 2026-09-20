"""Command-line interface for the ``ihatevideos.export`` module.

Independent entry point (no Agent needed)::

    ihatevideos-export json2md <transcription.json> [--min-length N] [-o OUT]
    ihatevideos-export table <summary.md> [--keep-time]
    ihatevideos-export timeline <summary.md>

Exit codes (for Agent judgement):
    0 = produced a file (path in JSON stdout)
    3 = skipped normally: no table in file, or no parseable video times
        (NOT a failure — continue the workflow without that artifact)
    2 = bad input (missing file, bad args)
    1 = unexpected failure
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .json_to_md import convert_json_to_md
from .tables import export_table_markdown


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _cmd_json2md(args: argparse.Namespace) -> int:
    src = Path(args.json)
    if not src.is_file():
        print(f"error: input file not found: {src}", file=sys.stderr)
        return 2
    try:
        out = convert_json_to_md(src, args.output, min_length=args.min_length)
    except (ValueError, OSError) as exc:
        print(f"error: conversion failed: {exc}", file=sys.stderr)
        return 1
    _print_json({"command": "json2md", "input": str(src), "path": str(out), "skipped": None})
    return 0


def _cmd_table(args: argparse.Namespace) -> int:
    src = Path(args.summary)
    if not src.is_file():
        print(f"error: input file not found: {src}", file=sys.stderr)
        return 2
    try:
        out = export_table_markdown(src, which="last", keep_time_column=args.keep_time)
    except (ValueError, OSError) as exc:
        print(f"error: table export failed: {exc}", file=sys.stderr)
        return 1
    if out is None:
        _print_json(
            {
                "command": "table",
                "input": str(src),
                "path": None,
                "skipped": "no markdown table found in file",
            }
        )
        return 3
    _print_json({"command": "table", "input": str(src), "path": str(out), "skipped": None})
    return 0


def _cmd_timeline(args: argparse.Namespace) -> int:
    from .timeline import export_summary_timeline_text

    src = Path(args.summary)
    if not src.is_file():
        print(f"error: input file not found: {src}", file=sys.stderr)
        return 2
    try:
        out = export_summary_timeline_text(src)
    except (ValueError, OSError) as exc:
        print(f"error: timeline export failed: {exc}", file=sys.stderr)
        return 1
    if out is None:
        _print_json(
            {
                "command": "timeline",
                "input": str(src),
                "path": None,
                "skipped": "no table with parseable 视频时间 found in file",
            }
        )
        return 3
    _print_json({"command": "timeline", "input": str(src), "path": str(out), "skipped": None})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ihatevideos-export",
        description="iHateVideos layer-1 exports: transcription.json -> md, summary.md -> table/timeline.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_j = sub.add_parser("json2md", help="Convert transcription JSON to 原文 Markdown.")
    p_j.add_argument("json")
    p_j.add_argument("-o", "--output", default=None)
    p_j.add_argument("--min-length", type=int, default=60)
    p_j.set_defaults(func=_cmd_json2md)

    p_t = sub.add_parser("table", help="Export last table of a summary (default: drop 视频时间 column).")
    p_t.add_argument("summary")
    p_t.add_argument("--keep-time", action="store_true")
    p_t.set_defaults(func=_cmd_table)

    p_l = sub.add_parser("timeline", help="Export Bilibili-comment timeline from last summary table.")
    p_l.add_argument("summary")
    p_l.set_defaults(func=_cmd_timeline)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except ValueError as exc:
        print(f"error: bad input: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
