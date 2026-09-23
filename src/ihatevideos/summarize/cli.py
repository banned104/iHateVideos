import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from ihatevideos.agent.config import load_model_config, resolve_paths

from .presets import CUSTOM_PRESET, list_presets
from .summarize import append_viewpoints, summarize_markdown


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _model_config() -> object:
    paths = resolve_paths()
    try:
        return load_model_config(paths)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def _read_meta(meta_arg: str | None, md_path: Path) -> dict | None:
    if meta_arg:
        meta_path = Path(meta_arg)
    else:
        meta_path = md_path.parent / f"{md_path.stem.split('_sub')[0]}_meta.json"
    if not meta_path.is_file():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _cmd_summary(args: argparse.Namespace) -> int:
    md_path = Path(args.md)
    if not md_path.is_file():
        print(f"error: input file not found: {md_path}", file=sys.stderr)
        return 2
    model_config = _model_config()
    try:
        summary_path = summarize_markdown(
            md_path,
            model_config,
            preset=args.preset,
            template=args.template,
            metadata=_read_meta(args.meta, md_path),
            timeout=args.timeout,
        )
    except ValueError as exc:
        print(f"error: bad input: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"error: summarize failed: {exc}", file=sys.stderr)
        return 1
    _print_json(
        {
            "command": "summary",
            "input": str(md_path),
            "summary_path": str(summary_path),
            "preset": args.preset or "timeline_merge",
            "skipped": None,
        }
    )
    return 0


def _cmd_viewpoints(args: argparse.Namespace) -> int:
    summary_path = Path(args.summary)
    comments_path = Path(args.comments)
    if not summary_path.is_file():
        print(f"error: input file not found: {summary_path}", file=sys.stderr)
        return 2
    if not comments_path.is_file():
        print(f"error: input file not found: {comments_path}", file=sys.stderr)
        return 2
    model_config = _model_config()
    try:
        appended = append_viewpoints(
            summary_path, comments_path, model_config, timeout=args.timeout
        )
    except ValueError as exc:
        print(f"error: bad input: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"error: viewpoints failed: {exc}", file=sys.stderr)
        return 1
    _print_json(
        {
            "command": "viewpoints",
            "summary_path": str(summary_path),
            "appended": appended,
            "skipped": None if appended else "empty comments file",
        }
    )
    return 0


def _cmd_presets(args: argparse.Namespace) -> int:
    _print_json({"command": "presets", "presets": list_presets()})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ihatevideos-summarize",
        description="iHateVideos LLM summarize: transcript -> summary, comments -> viewpoints.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_sum = sub.add_parser("summary", help="Summarize a transcript file.")
    p_sum.add_argument("md")
    p_sum.add_argument("--preset", default="timeline_merge")
    p_sum.add_argument("--template", default=None)
    p_sum.add_argument("--meta", default=None)
    p_sum.add_argument("--timeout", type=int, default=300)
    p_sum.set_defaults(func=_cmd_summary)

    p_view = sub.add_parser("viewpoints", help="Append comment viewpoints to a summary.")
    p_view.add_argument("summary")
    p_view.add_argument("--comments", required=True)
    p_view.add_argument("--timeout", type=int, default=300)
    p_view.set_defaults(func=_cmd_viewpoints)

    p_list = sub.add_parser("presets", help="List available presets (offline).")
    p_list.set_defaults(func=_cmd_presets)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else 1
    except ValueError as exc:
        print(f"error: bad input: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
