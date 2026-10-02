from __future__ import annotations

import argparse
import json
import signal
import sys
from pathlib import Path
from typing import Callable, Sequence

from ihatevideos.agent.config import find_project_root

from .binaries import resolve_engines
from .errors import DownloadError, YtdlpUnsupported
from .install_binaries import setup_binaries
from .models import Progress, Task, TaskKind, TaskStatus
from .proxy import resolve_proxy
from .service import DownloadRequest, DownloadService
from .ytdlp_engine import resolve_video

DEFAULT_DOWNLOAD_SUBDIR = ("temp", "download")


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GiB"


def _default_dir(raw: str | None) -> Path:
    if raw:
        return Path(raw).expanduser()
    return find_project_root() / Path(*DEFAULT_DOWNLOAD_SUBDIR)


def _progress_printer() -> Callable[[Progress], None]:
    def printer(progress: Progress) -> None:
        label = progress.task_id
        if progress.phase == "processing":
            label = f"{label} 后处理"
        if progress.total_bytes <= 0:
            print(f"[{label}] 已下载 {_format_bytes(progress.downloaded_bytes)}", file=sys.stderr)
            return
        percent = progress.downloaded_bytes / progress.total_bytes * 100
        speed = f"{_format_bytes(int(progress.speed))}/s" if progress.speed > 0 else "-"
        line = (
            f"[{label}] {percent:5.1f}%  {speed}  "
            f"{_format_bytes(progress.downloaded_bytes)} / {_format_bytes(progress.total_bytes)}"
        )
        if progress.eta_seconds is not None:
            seconds = int(progress.eta_seconds)
            line += f"  {seconds // 60:02d}:{seconds % 60:02d} 剩余"
        print(line, file=sys.stderr)

    return printer


def _event_printer() -> Callable[[str], None]:
    def printer(text: str) -> None:
        print(text, file=sys.stderr)

    return printer


def _install_signal_handler(service: DownloadService) -> None:
    def handler(signum, _frame) -> None:
        print(f"\n收到信号 {signum}，正在停止并保留断点……", file=sys.stderr)
        service.stop()

    signal.signal(signal.SIGINT, handler)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, handler)


def _summarize(command: str, tasks: list[Task]) -> int:
    _print_json({"command": command, "tasks": [task.to_json() for task in tasks]})
    return 0 if all(task.status is TaskStatus.COMPLETED for task in tasks) else 1


def _cmd_engines(args: argparse.Namespace) -> int:
    engines = resolve_engines()
    _print_json({"command": "engines", **engines.to_json()})
    missing = engines.missing()
    if missing:
        print(f"error: 缺少引擎 {missing}，运行 setup-binaries 或检查依赖安装", file=sys.stderr)
        return 1
    return 0


def _cmd_setup_binaries(args: argparse.Namespace) -> int:
    result = setup_binaries(force=args.force)
    _print_json({"command": "setup-binaries", **result})
    return 0


def _cmd_formats(args: argparse.Namespace) -> int:
    info = resolve_video(
        url=args.url,
        proxy=resolve_proxy(disabled=args.no_proxy),
        cookie_file=args.cookie,
        cookie_from_browser=args.cookie_from_browser,
    )
    _print_json({"command": "formats", "url": args.url, **info.to_json()})
    if not info.formats:
        print("error: 这个地址没有可用的格式", file=sys.stderr)
        return 3
    return 0


def _cmd_file(args: argparse.Namespace) -> int:
    if args.filename and len(args.url) > 1:
        raise ValueError("给了多条链接时不能同时指定 --filename")
    out_dir = _default_dir(args.out_dir)
    engines = resolve_engines()
    service = DownloadService(
        engines=engines,
        download_dir=out_dir,
        jobs=args.jobs,
        global_limit_kbps=args.global_limit,
        proxy=resolve_proxy(disabled=args.no_proxy),
        on_progress=_progress_printer(),
        on_event=_event_printer(),
    )
    _install_signal_handler(service)
    for url in args.url:
        service.submit(
            DownloadRequest(
                url=url,
                out_dir=out_dir,
                filename=args.filename,
                limit_kbps=args.limit,
            )
        )
    tasks = service.run()
    return _summarize("file", tasks)


def _cmd_video(args: argparse.Namespace) -> int:
    if args.filename and len(args.url) > 1:
        raise ValueError("给了多条链接时不能同时指定 --filename")
    if args.format_id and args.height:
        raise ValueError("--format 与 --height 不能同时使用")
    out_dir = _default_dir(args.out_dir)
    engines = resolve_engines()
    service = DownloadService(
        engines=engines,
        download_dir=out_dir,
        jobs=args.jobs,
        global_limit_kbps=args.global_limit,
        proxy=resolve_proxy(disabled=args.no_proxy),
        on_progress=_progress_printer(),
        on_event=_event_printer(),
    )
    _install_signal_handler(service)
    subtitles = tuple(item for item in (args.subs or "").split(",") if item.strip())
    for url in args.url:
        service.submit(
            DownloadRequest(
                url=url,
                kind=TaskKind.VIDEO,
                out_dir=out_dir,
                filename=args.filename,
                limit_kbps=args.limit,
                audio_only=args.audio_only,
                format_id=args.format_id,
                height=args.height,
                subtitles=subtitles,
                sub_format=args.sub_format,
                write_auto_subs=args.write_auto_subs,
                accelerate=not args.no_accel,
                cookie_file=args.cookie,
                cookie_from_browser=args.cookie_from_browser,
            )
        )
    tasks = service.run()
    return _summarize("video", tasks)


def _add_common_network_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cookie", default=None, help="Netscape 格式的 cookies.txt 文件")
    parser.add_argument("--cookie-from-browser", default=None, help="从浏览器读取登录态，例如 edge")
    parser.add_argument("--no-proxy", action="store_true", help="忽略系统代理，直连")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ihatevideos-download",
        description="iHateVideos download tool: aria2c direct links and yt-dlp videos.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_engines = sub.add_parser(
        "engines", help="Locate aria2c, ffmpeg, ffprobe and yt-dlp, print versions."
    )
    p_engines.set_defaults(func=_cmd_engines)

    p_bins = sub.add_parser(
        "setup-binaries",
        help="Fetch the binaries uv cannot provide (ffprobe) into the project temp/bin directory.",
    )
    p_bins.add_argument("--force", action="store_true", help="Download again even if the record matches")
    p_bins.set_defaults(func=_cmd_setup_binaries)

    p_formats = sub.add_parser("formats", help="Resolve a video page and list formats and subtitles.")
    p_formats.add_argument("url")
    _add_common_network_arguments(p_formats)
    p_formats.set_defaults(func=_cmd_formats)

    p_file = sub.add_parser("file", help="Download direct links with aria2c.")
    p_file.add_argument("url", nargs="+")
    p_file.add_argument("--out-dir", default=None, help="Target directory, defaults to temp/download")
    p_file.add_argument("--filename", default=None, help="Only valid with a single URL")
    p_file.add_argument("--limit", type=int, default=None, help="Per-task limit in KiB/s")
    p_file.add_argument("--global-limit", type=int, default=None, help="Engine-wide limit in KiB/s")
    p_file.add_argument("--jobs", type=int, default=2, help="How many tasks run at once")
    p_file.add_argument("--no-proxy", action="store_true", help="Ignore the system proxy and connect directly")
    p_file.set_defaults(func=_cmd_file)

    p_video = sub.add_parser("video", help="Download videos with yt-dlp.")
    p_video.add_argument("url", nargs="+")
    p_video.add_argument("--format", dest="format_id", default=None, help="格式编号，见 formats 子命令")
    p_video.add_argument("--height", type=int, default=None, help="清晰度上限，例如 720")
    p_video.add_argument("--audio-only", action="store_true", help="只取音频并转成 mp3")
    p_video.add_argument("--subs", default=None, help="字幕语言，逗号分隔")
    p_video.add_argument("--sub-format", default="srt", help="字幕格式，默认 srt")
    p_video.add_argument("--write-auto-subs", action="store_true", help="同时写自动生成的字幕")
    p_video.add_argument("--no-accel", action="store_true", help="不用 aria2c 加速，使用自带下载器")
    p_video.add_argument("--out-dir", default=None, help="Target directory, defaults to temp/download")
    p_video.add_argument("--filename", default=None, help="Only valid with a single URL")
    p_video.add_argument("--limit", type=int, default=None, help="Per-task limit in KiB/s")
    p_video.add_argument("--global-limit", type=int, default=None, help="Engine-wide limit in KiB/s")
    p_video.add_argument("--jobs", type=int, default=2, help="How many tasks run at once")
    _add_common_network_arguments(p_video)
    p_video.set_defaults(func=_cmd_video)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    # 中文路径要按 UTF-8 写出，Agent 侧按 UTF-8 读取命令行输出
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except YtdlpUnsupported as exc:
        print(f"error: 不支持这个地址：{exc}", file=sys.stderr)
        return 3
    except DownloadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: bad input: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
