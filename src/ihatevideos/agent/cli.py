import argparse
import sys
from pathlib import Path
from typing import Sequence

from .runner import run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ihatevideos-agent",
        description="iHateVideos supervised agent: checks login, runs tools, asks approval in terminal.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser("run", help="Run one supervised task.")
    group = p_run.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", default="")
    group.add_argument("--task", default="")
    p_run.add_argument("--root", default=None)
    p_run.set_defaults(func=_cmd_run)
    return parser


def _cmd_run(args: argparse.Namespace) -> int:
    task = args.task.strip() if args.task else f"处理这个视频：{args.url.strip()}，取字幕，产物进会话目录"
    root = Path(args.root).expanduser() if args.root else None
    return run(task, root=root)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
