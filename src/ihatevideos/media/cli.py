from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .audio import (
    DEFAULT_WAV_CHANNELS,
    DEFAULT_WAV_SAMPLE_RATE,
    SUPPORTED_FORMATS as AUDIO_FORMATS,
    chunk_audio,
    extract_audio,
)
from .clip import SUPPORTED_MODES, cut_media
from .ffmpeg import DEFAULT_TIMEOUT_SECONDS, FFPROBE_TIMEOUT_SECONDS, FfmpegError, MediaToolNotFound
from .frames import (
    DEFAULT_JOBS,
    DEFAULT_MAX_FRAMES,
    DEFAULT_QUALITY,
    SUPPORTED_FORMATS as FRAME_FORMATS,
    build_timestamps,
    extract_frames,
)
from .paths import default_output_dir
from .probe import probe_media
from .timestamps import parse_seconds, parse_seconds_list


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _require_file(raw: str) -> Path | None:
    source = Path(raw).expanduser()
    if not source.is_file():
        print(f"error: input file not found: {source}", file=sys.stderr)
        return None
    return source


def _resolve_out_dir(raw: str | None, source: Path) -> Path:
    return Path(raw).expanduser() if raw else default_output_dir(source)


def _parse_range(value: str, total: float) -> tuple[float, float | None]:
    text = value.strip()
    if "-" not in text:
        raise ValueError(f"--range 需要写成 起点-终点，例如 10-120 或 10-：{value}")
    head, _, tail = text.partition("-")
    start = parse_seconds(head) if head.strip() else 0.0
    stop = parse_seconds(tail) if tail.strip() else None
    if stop is not None and stop <= start:
        raise ValueError(f"--range 的终点必须大于起点：{value}")
    if start >= total:
        raise ValueError(f"--range 的起点（{start} 秒）超过媒体时长（{total:.3f} 秒）")
    if stop is not None and stop > total:
        raise ValueError(f"--range 的终点（{stop} 秒）超过媒体时长（{total:.3f} 秒）")
    return start, stop


def _cmd_probe(args: argparse.Namespace) -> int:
    source = _require_file(args.input)
    if source is None:
        return 2
    info = probe_media(source, timeout=args.timeout)
    _print_json({"command": "probe", **info.to_json(include_streams=args.streams)})
    return 0


def _cmd_frames(args: argparse.Namespace) -> int:
    source = _require_file(args.input)
    if source is None:
        return 2
    info = probe_media(source, timeout=args.timeout)
    if not info.has_video:
        _print_json(
            {
                "command": "frames",
                "input": str(source),
                "duration_seconds": round(info.duration_seconds, 3),
                "count": 0,
                "out_dir": None,
                "frames": [],
                "skipped": [],
                "reason": "input has no video stream",
            }
        )
        return 3
    start = 0.0
    stop: float | None = None
    if args.range_spec:
        start, stop = _parse_range(args.range_spec, info.duration_seconds)
    at = parse_seconds_list(args.at) if args.at else ()
    every = parse_seconds(args.every) if args.every else None
    timestamps = build_timestamps(
        duration_seconds=info.duration_seconds,
        at=at,
        every=every,
        count=args.count,
        start=start,
        end=stop,
        max_frames=args.max_frames,
    )
    out_dir = _resolve_out_dir(args.out_dir, source)
    frames, skipped = extract_frames(
        source,
        timestamps,
        out_dir=out_dir,
        fmt=args.format,
        width=args.width,
        quality=args.quality,
        jobs=args.jobs,
        timeout=args.timeout,
        reuse=args.reuse,
    )
    _print_json(
        {
            "command": "frames",
            "input": str(source),
            "duration_seconds": round(info.duration_seconds, 3),
            "count": len(frames),
            "out_dir": str(out_dir),
            "frames": [frame.to_json() for frame in frames],
            "skipped": skipped,
        }
    )
    return 0


def _cmd_clip(args: argparse.Namespace) -> int:
    source = _require_file(args.input)
    if source is None:
        return 2
    info = probe_media(source, timeout=args.timeout)
    if args.audio_only and not info.has_audio:
        _print_json(
            {
                "command": "clip",
                "input": str(source),
                "path": None,
                "reason": "input has no audio stream",
            }
        )
        return 3
    start = parse_seconds(args.start) if args.start is not None else 0.0
    end = parse_seconds(args.end) if args.end is not None else None
    duration = parse_seconds(args.duration) if args.duration is not None else None
    result = cut_media(
        source,
        start=start,
        end=end,
        duration=duration,
        mode=args.mode,
        audio_only=args.audio_only,
        output=args.out,
        out_dir=_resolve_out_dir(args.out_dir, source),
        timeout=args.timeout,
        reuse=args.reuse,
    )
    _print_json({"command": "clip", **result.to_json()})
    return 0


def _cmd_audio(args: argparse.Namespace) -> int:
    source = _require_file(args.input)
    if source is None:
        return 2
    info = probe_media(source, timeout=args.timeout)
    if not info.has_audio:
        _print_json(
            {
                "command": "audio",
                "input": str(source),
                "path": None,
                "chunks": [],
                "reason": "input has no audio stream",
            }
        )
        return 3
    start = 0.0
    end: float | None = None
    if args.range_spec:
        start, end = _parse_range(args.range_spec, info.duration_seconds)
    out_dir = _resolve_out_dir(args.out_dir, source)
    if args.chunk_seconds is not None:
        if args.format != "wav":
            raise ValueError("--chunk-seconds 只与 wav 分块配套，请不要同时指定 --format")
        if args.out is not None:
            raise ValueError("--chunk-seconds 会产出多个文件，请改用 --out-dir 指定目录")
        sample_rate = args.sample_rate if args.sample_rate is not None else DEFAULT_WAV_SAMPLE_RATE
        channels = args.channels if args.channels is not None else DEFAULT_WAV_CHANNELS
        chunks = chunk_audio(
            source,
            chunk_seconds=args.chunk_seconds,
            out_dir=out_dir,
            sample_rate=sample_rate,
            channels=channels,
            start=start,
            end=end,
            timeout=args.timeout,
            reuse=args.reuse,
        )
        span = (end if end is not None else info.duration_seconds) - start
        _print_json(
            {
                "command": "audio",
                "input": str(source),
                "path": None,
                "format": "wav",
                "sample_rate": sample_rate,
                "channels": channels,
                "duration_seconds": round(span, 3),
                "chunk_seconds": args.chunk_seconds,
                "out_dir": str(out_dir),
                "chunks": [chunk.to_json() for chunk in chunks],
            }
        )
        return 0
    result = extract_audio(
        source,
        fmt=args.format,
        sample_rate=args.sample_rate,
        channels=args.channels,
        bitrate=args.bitrate,
        start=start,
        end=end,
        output=args.out,
        out_dir=out_dir,
        timeout=args.timeout,
        reuse=args.reuse,
    )
    _print_json({"command": "audio", **result.to_json(), "chunks": []})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ihatevideos-media",
        description="iHateVideos media tool: ffprobe/ffmpeg for probe, frames, clip and audio.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_probe = sub.add_parser("probe", help="Read container, stream and duration info.")
    p_probe.add_argument("input")
    p_probe.add_argument("--streams", action="store_true", help="Include every stream of the container.")
    p_probe.add_argument("--timeout", type=int, default=FFPROBE_TIMEOUT_SECONDS)
    p_probe.set_defaults(func=_cmd_probe)

    p_frames = sub.add_parser("frames", help="Extract still images at given times.")
    p_frames.add_argument("input")
    source_group = p_frames.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--at", default=None, help="Comma separated times: 12,1:30,2:05.5")
    source_group.add_argument("--every", default=None, help="Evenly spaced step in seconds, e.g. 30")
    source_group.add_argument("--count", type=int, default=None, help="Evenly spaced number of frames")
    p_frames.add_argument("--range", dest="range_spec", default=None, help="Limit to 起点-终点, e.g. 10-120")
    p_frames.add_argument("--out-dir", default=None)
    p_frames.add_argument("--format", choices=list(FRAME_FORMATS), default="jpg")
    p_frames.add_argument("--width", type=int, default=None, help="Scale to this width, keep aspect ratio")
    p_frames.add_argument("--quality", type=int, default=DEFAULT_QUALITY, help="JPEG quality, 1 (best) to 31; ignored for png")
    p_frames.add_argument("--max-frames", type=int, default=DEFAULT_MAX_FRAMES)
    p_frames.add_argument("--jobs", type=int, default=DEFAULT_JOBS)
    p_frames.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    p_frames.add_argument("--reuse", action="store_true", help="Keep existing images instead of overwriting")
    p_frames.set_defaults(func=_cmd_frames)

    p_clip = sub.add_parser("clip", help="Cut a time range out of a video or audio file.")
    p_clip.add_argument("input")
    p_clip.add_argument("--start", default="0", help="Start time: 90 / 1:30 / 01:02:03")
    clip_group = p_clip.add_mutually_exclusive_group()
    clip_group.add_argument("--end", default=None, help="End time, same syntax as --start")
    clip_group.add_argument("--duration", default=None, help="Length in seconds or time syntax")
    p_clip.add_argument("--mode", choices=list(SUPPORTED_MODES), default="reencode")
    p_clip.add_argument("--audio-only", action="store_true")
    p_clip.add_argument("--out", default=None)
    p_clip.add_argument("--out-dir", default=None)
    p_clip.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    p_clip.add_argument("--reuse", action="store_true")
    p_clip.set_defaults(func=_cmd_clip)

    p_audio = sub.add_parser("audio", help="Extract the audio track, optionally split into WAV chunks.")
    p_audio.add_argument("input")
    p_audio.add_argument("--format", choices=list(AUDIO_FORMATS), default="wav")
    p_audio.add_argument("--sample-rate", type=int, default=None)
    p_audio.add_argument("--channels", type=int, default=None)
    p_audio.add_argument("--bitrate", default=None, help="Bitrate for m4a/mp3, e.g. 192k")
    p_audio.add_argument("--range", dest="range_spec", default=None, help="Limit to 起点-终点, e.g. 10-600")
    p_audio.add_argument("--chunk-seconds", type=float, default=None, help="Split into equal WAV chunks")
    p_audio.add_argument("--out", default=None)
    p_audio.add_argument("--out-dir", default=None)
    p_audio.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    p_audio.add_argument("--reuse", action="store_true")
    p_audio.set_defaults(func=_cmd_audio)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    # 中文路径要按 UTF-8 写出，Agent 侧按 UTF-8 读取命令行输出
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: bad input: {exc}", file=sys.stderr)
        return 2
    except MediaToolNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FfmpegError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
