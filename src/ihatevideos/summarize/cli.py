from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from ..media.ffmpeg import DEFAULT_TIMEOUT_SECONDS, FfmpegError, MediaToolNotFound
from ..media.frames import DEFAULT_JOBS, DEFAULT_QUALITY, SUPPORTED_FORMATS
from ..media.timestamps import parse_seconds_list
from .capture import capture_for_markdown
from .errors import SummarizeError
from .insert import find_placeholder_seconds, insert_images, read_markdown
from .paths import DEFAULT_FRAME_FORMAT, assets_dir, templates_dir
from .templates import list_templates, read_template


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _fail(message: str, code: int) -> int:
    print(f"error: {message}", file=sys.stderr)
    return code


def _cmd_templates(args: argparse.Namespace) -> int:
    items = list_templates()
    _emit(
        {
            "command": "templates",
            "dir": str(templates_dir()),
            "templates": [
                {"name": item.name, "title": item.title, "path": str(item.path)}
                for item in items
            ],
        }
    )
    return 0


def _cmd_template(args: argparse.Namespace) -> int:
    try:
        template = read_template(args.name)
    except SummarizeError as exc:
        return _fail(str(exc), 2)
    _emit(
        {
            "command": "template",
            "name": template.name,
            "title": template.title,
            "path": str(template.path),
            "body": template.body,
        }
    )
    return 0


def _collect_timestamps(markdown_text: str, extra: str | None) -> list[float]:
    timestamps = find_placeholder_seconds(markdown_text)
    if extra:
        for seconds in parse_seconds_list(extra):
            if seconds not in timestamps:
                timestamps.append(seconds)
    return timestamps


def _cmd_frames(args: argparse.Namespace) -> int:
    try:
        _, text = read_markdown(args.markdown)
    except FileNotFoundError as exc:
        return _fail(str(exc), 2)
    try:
        timestamps = _collect_timestamps(text, args.at)
    except ValueError as exc:
        return _fail(str(exc), 2)
    if not timestamps:
        return _fail(f"{args.markdown} 里没有 <!-- FRAME: 时间 --> 占位符，也没有给出 --at", 2)
    try:
        frames, skipped = capture_for_markdown(
            args.video,
            args.markdown,
            timestamps,
            fmt=args.format,
            width=args.width,
            quality=args.quality,
            jobs=args.jobs,
            timeout=args.timeout,
            reuse=args.reuse,
        )
    except FileNotFoundError as exc:
        return _fail(str(exc), 2)
    except ValueError as exc:
        return _fail(str(exc), 2)
    except (FfmpegError, MediaToolNotFound) as exc:
        return _fail(str(exc), 1)
    _emit(
        {
            "command": "frames",
            "video": str(args.video),
            "markdown": str(args.markdown),
            "assets_dir": str(assets_dir(args.markdown)),
            "requested": len(timestamps),
            "frames": [item.to_json() for item in frames],
            "skipped": skipped,
        }
    )
    return 3 if skipped else 0


def _cmd_insert(args: argparse.Namespace) -> int:
    try:
        result = insert_images(args.markdown, fmt=args.format)
    except FileNotFoundError as exc:
        return _fail(str(exc), 2)
    _emit({"command": "insert", **result})
    return 3 if result["missing"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ihatevideos-summarize",
        description=(
            "iHateVideos 图文笔记工具：列出写作模板、把视频画面取到 Markdown 同级的 assets/、"
            "再把正文里的占位符换成图片引用。"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("templates", help="列出 templates/ 里可用的模板。")
    p_list.set_defaults(func=_cmd_templates)

    p_show = sub.add_parser("template", help="打印一个模板的正文，照着它写笔记。")
    p_show.add_argument("name", help="模板名，就是 templates/ 里的文件名（不含 .md）。")
    p_show.set_defaults(func=_cmd_template)

    p_frames = sub.add_parser("frames", help="把视频画面取到 Markdown 同级的 assets/。")
    p_frames.add_argument("video", help="视频文件路径。")
    p_frames.add_argument(
        "--md",
        dest="markdown",
        required=True,
        help="Markdown 文件路径；它的位置决定 assets/ 放在哪里，它的文件名决定图片名。",
    )
    p_frames.add_argument(
        "--at",
        default=None,
        help="额外的时间点，逗号分隔，例如 \"12,1:30\"；与正文里的占位符合并。",
    )
    p_frames.add_argument(
        "--format",
        default=DEFAULT_FRAME_FORMAT,
        choices=SUPPORTED_FORMATS,
        help="图片格式。",
    )
    p_frames.add_argument("--width", type=int, default=None, help="缩放宽度，默认保持原尺寸。")
    p_frames.add_argument("--quality", type=int, default=DEFAULT_QUALITY, help="jpg 画质 1-31，数字越小越清晰。")
    p_frames.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help="并发取帧数量。")
    p_frames.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="单帧超时秒数。")
    p_frames.add_argument("--reuse", action="store_true", help="已有同名图片时直接沿用。")
    p_frames.set_defaults(func=_cmd_frames)

    p_insert = sub.add_parser("insert", help="把正文里的 <!-- FRAME: 时间 | 图注 --> 换成图片引用。")
    p_insert.add_argument("markdown", help="要改写的 Markdown 文件路径。")
    p_insert.add_argument(
        "--format",
        default=DEFAULT_FRAME_FORMAT,
        choices=SUPPORTED_FORMATS,
        help="图片格式，要与取帧时用的一致。",
    )
    p_insert.set_defaults(func=_cmd_insert)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
