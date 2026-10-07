from __future__ import annotations

import argparse
import shutil
import sys
from typing import Sequence

from ..paths import find_project_root
from .checks import run_checks
from .models import GROUPS, Report, parse_groups
from .report import render_json, render_text
from .smoke import run_dir, work_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ihatevideos-doctor",
        description=(
            "iHateVideos 运行环境检查：Python 依赖、外部程序、ffmpeg 实际出活能力、"
            "GPU 计算、模型权重、B 站 cookies 与登录态、系统代理。"
        ),
    )
    parser.add_argument(
        "--only",
        default=None,
        help=f"只跑指定分组，逗号分隔；可选 {', '.join(GROUPS)}。",
    )
    parser.add_argument("--no-smoke", action="store_true", help="不跑烟测，只做位置与版本解析。")
    parser.add_argument("--deep", action="store_true", help="额外加载两份语音识别权重并跑一次识别。")
    parser.add_argument("--json", action="store_true", help="输出 JSON，供上层 Agent 读取。")
    parser.add_argument("--keep", action="store_true", help="保留本次运行的 temp/doctor/<时间>/ 产物。")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        groups = parse_groups(args.only)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    root = find_project_root()
    work = run_dir(root)
    checks = run_checks(
        root=root,
        groups=groups,
        smoke=not args.no_smoke,
        deep=args.deep,
        work=work,
    )
    report = Report(project_root=str(root), checks=tuple(checks))
    print(render_json(report) if args.json else render_text(report))
    if args.keep:
        print(f"烟测产物留在：{work}", file=sys.stderr)
    else:
        shutil.rmtree(work, ignore_errors=True)
        parent = work_dir(root)
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
    return 0 if report.ready else 3


if __name__ == "__main__":
    raise SystemExit(main())
