"""Command-line interface for the ``ihatevideos.input`` module.

Independent entry point (no Agent needed)::

    ihatevideos-input detect <url>
    ihatevideos-input normalize <input>
    ihatevideos-input ids <input>
    ihatevideos-input ximalaya <url>
    ihatevideos-input resolve (--url URL | --audio-path PATH) [options]

``resolve`` is the same contract the Skill uses: exactly one input in,
``ResolvedInput`` out, printed as JSON on stdout. Anything that downloads
audio or hits the network happens only in ``resolve`` (and Bilibili subtitle
probe inside it); the other subcommands are pure offline parsing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .bilibili_ids import (
    extract_bilibili_page,
    extract_bilibili_target_id,
    extract_bvid,
    normalize_bilibili_target,
)
from .resolver import resolve_input
from .url_detect import detect_platform
from .ximalaya import resolve_ximalaya_sound_url


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _cmd_detect(args: argparse.Namespace) -> int:
    platform = detect_platform(args.url)
    _print_json({"url": args.url, "platform": platform.value if platform else None})
    return 0


def _cmd_normalize(args: argparse.Namespace) -> int:
    print(normalize_bilibili_target(args.input))
    return 0


def _cmd_ids(args: argparse.Namespace) -> int:
    _print_json(
        {
            "input": args.input,
            "bvid": extract_bvid(args.input),
            "page": extract_bilibili_page(args.input),
            "target_id": extract_bilibili_target_id(args.input),
            "normalized": normalize_bilibili_target(args.input),
        }
    )
    return 0


def _cmd_ximalaya(args: argparse.Namespace) -> int:
    canonical, track_id = resolve_ximalaya_sound_url(args.url)
    _print_json({"url": args.url, "canonical_url": canonical, "track_id": track_id})
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    if bool(args.url) == bool(args.audio_path):
        print("error: exactly one of --url / --audio-path is required", file=sys.stderr)
        return 2
    try:
        result = resolve_input(
            url=args.url or "",
            audio_path=args.audio_path,
            input_bvid=args.input_bvid,
            prefer_bilibili_subtitle=not args.no_prefer_subtitle,
            download_dir=args.download_dir,
            audio_quality=args.audio_quality,
            fetch_metadata=not args.no_metadata,
            subtitle_timeout_seconds=args.subtitle_timeout,
        )
    except FileNotFoundError as exc:
        print(f"error: file not found: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: bad input: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"error: platform request failed: {exc}", file=sys.stderr)
        return 1
    _print_json(
        {
            "audio_path": str(result.audio_file) if result.audio_file else None,
            "has_native_subtitle": result.subtitle is not None,
            "subtitle_chars": len(result.subtitle.text) if result.subtitle else 0,
            "resource_id": result.transcription_id,
            "bvid": result.bvid,
            "platform": result.platform.value if result.platform else None,
            "use_local_audio": result.use_local_audio,
            "title": result.metadata.title if result.metadata else None,
            "author": result.metadata.author if result.metadata else None,
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ihatevideos-input",
        description="iHateVideos multi-platform input: URL/file -> audio + metadata (+native subtitle).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_detect = sub.add_parser("detect", help="Detect platform of a URL (offline).")
    p_detect.add_argument("url")
    p_detect.set_defaults(func=_cmd_detect)

    p_norm = sub.add_parser("normalize", help="Normalize a Bilibili input (offline).")
    p_norm.add_argument("input")
    p_norm.set_defaults(func=_cmd_normalize)

    p_ids = sub.add_parser("ids", help="Show BV/page/target-id/normalized (offline).")
    p_ids.add_argument("input")
    p_ids.set_defaults(func=_cmd_ids)

    p_xima = sub.add_parser(
        "ximalaya", help="Resolve a Ximalaya URL to canonical sound URL (offline for direct links)."
    )
    p_xima.add_argument("url")
    p_xima.set_defaults(func=_cmd_ximalaya)

    p_resolve = sub.add_parser(
        "resolve", help="Resolve one input (may download / hit network)."
    )
    group = p_resolve.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", default="")
    group.add_argument("--audio-path", default=None)
    p_resolve.add_argument("--input-bvid", default=None)
    p_resolve.add_argument("--download-dir", default=".")
    p_resolve.add_argument("--audio-quality", default="30216")
    p_resolve.add_argument("--no-prefer-subtitle", action="store_true")
    p_resolve.add_argument("--no-metadata", action="store_true")
    p_resolve.add_argument("--subtitle-timeout", type=int, default=60)
    p_resolve.set_defaults(func=_cmd_resolve)

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
