from __future__ import annotations

import glob
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .errors import DownloadError, YtdlpError, YtdlpUnsupported
from .filenames import predict_ext, sanitize_basename, video_filename
from .models import FormatInfo, SubtitleTrack, VideoInfo
from .ytdlp_args import (
    RESOLVE_TIMEOUT_SECONDS,
    build_download_args,
    build_resolve_args,
    build_selector,
    build_subtitle_args,
    is_fragmented_protocol,
)
from .ytdlp_json import parse_info_tree, quality_tag, resolved_top_height
from .ytdlp_progress import parse_output_line
from .ytdlp_process import YtdlpProcess

UNSUPPORTED_MARKERS = ("Unsupported URL", "is not a valid URL")
PARTIAL_SUFFIXES = (".part", ".aria2", ".ytdl")
# yt-dlp 在成功解析时会说明哪些格式拿不到（例如需要大会员）
NOTE_MARKERS = ("are missing;", "Requested format is not available")


@dataclass(frozen=True)
class VideoPlan:
    output_base: str
    expected_filename: str
    selector: str
    merge_format: str | None
    ext: str
    quality_tag: str | None
    format_id: str | None
    fragmented: bool


@dataclass
class VideoRun:
    task_id: str
    plan: VideoPlan
    out_dir: Path
    process: YtdlpProcess
    accel_used: bool
    fallback_tried: bool = False
    stage: str = "downloading"
    destination: Path | None = None
    selected_formats: str | None = None
    notes: list[str] = field(default_factory=list)
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed: float = 0.0
    subtitles: list[SubtitleTrack] = field(default_factory=list)


def is_note_line(line: str) -> bool:
    """yt-dlp 说明「哪些格式拿不到」的行，例如需要大会员。只在选择格式时打印。"""
    return any(marker in line for marker in NOTE_MARKERS)


def resolve_video(
    *,
    url: str,
    proxy: str,
    cookie_file: str | None = None,
    cookie_from_browser: str | None = None,
) -> VideoInfo:
    """解析阶段：取信息树并解析成本工程的数据结构。"""
    process = YtdlpProcess()
    args = build_resolve_args(
        url=url, proxy=proxy, cookie_file=cookie_file, cookie_from_browser=cookie_from_browser
    )
    try:
        output = process.run_capture(args, timeout=RESOLVE_TIMEOUT_SECONDS)
    except YtdlpError as exc:
        raise _map_resolve_error(exc) from exc
    return parse_info_tree(_load_info_tree(output))


def _load_info_tree(output: str) -> dict:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise YtdlpError(f"yt-dlp 的信息树不是合法 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise YtdlpError("yt-dlp 的信息树顶层不是对象")
    return payload


def _map_resolve_error(exc: YtdlpError) -> DownloadError:
    text = str(exc)
    for marker in UNSUPPORTED_MARKERS:
        if marker in text:
            return YtdlpUnsupported(text)
    return exc


def find_format(info: VideoInfo, format_id: str) -> FormatInfo:
    for item in info.formats:
        if item.format_id == format_id:
            return item
    raise ValueError(f"格式编号 {format_id} 不在清单里")


def top_format(formats: Sequence[FormatInfo], height_cap: int | None) -> FormatInfo | None:
    """照 DownLord video/qualityLabel.ts:50-58：取不超过上限的实际最高清晰度那条。"""
    height = resolved_top_height(formats, height_cap)
    if height is None:
        return None
    for item in formats:
        if item.height == height:
            return item
    return None


def plan_download(
    info: VideoInfo,
    *,
    audio_only: bool,
    format_id: str | None,
    height_cap: int | None,
) -> VideoPlan:
    explicit = find_format(info, format_id) if format_id else None
    if audio_only:
        naming = None
        tag = quality_tag(audio_only=True, format_height=None, height_cap=None)
    elif explicit is not None:
        naming = explicit
        tag = quality_tag(audio_only=False, format_height=explicit.height, height_cap=None)
    elif height_cap is not None:
        naming = top_format(info.formats, height_cap)
        tag = quality_tag(audio_only=False, format_height=None, height_cap=height_cap)
    else:
        naming = top_format(info.formats, None)
        if naming is None:
            raise YtdlpUnsupported("这个视频没有可用的视频格式")
        tag = quality_tag(audio_only=False, format_height=naming.height, height_cap=None)

    if audio_only:
        selector, merge_format = build_selector(
            audio_only=True, format_id=None, acodec=None, height_cap=None
        )
    elif explicit is not None:
        selector, merge_format = build_selector(
            audio_only=False, format_id=explicit.format_id, acodec=explicit.acodec, height_cap=None
        )
    elif height_cap is not None:
        selector, merge_format = build_selector(
            audio_only=False, format_id=None, acodec=None, height_cap=height_cap
        )
    else:
        selector, merge_format = build_selector(
            audio_only=False, format_id=naming.format_id, acodec=naming.acodec, height_cap=None
        )
    ext = predict_ext(
        audio_only=audio_only,
        acodec=naming.acodec if naming is not None else None,
        ext=naming.ext if naming is not None else None,
    )
    filename = video_filename(title=info.title, quality_tag=tag, ext=ext)
    base = sanitize_basename(info.title)
    output_base = f"{base} [{tag}]" if tag else base
    return VideoPlan(
        output_base=output_base,
        expected_filename=filename,
        selector=selector,
        merge_format=merge_format,
        ext=ext,
        quality_tag=tag,
        format_id=naming.format_id if naming is not None else None,
        fragmented=is_fragmented_protocol(naming.protocol) if naming is not None else False,
    )


def clean_partials(out_dir: Path, output_base: str) -> None:
    """照 DownLord video/videoEngine.ts:177-203：换下载器时清掉残留分片，同一下载器继续时保留。"""
    for path in out_dir.glob(f"{glob.escape(output_base)}.*"):
        name = path.name
        if name.endswith(PARTIAL_SUFFIXES) or ".part-Frag" in name:
            path.unlink()


class YtdlpEngine:
    def __init__(self, *, ffmpeg_location: str, proxy: str, aria2c_path: str | None) -> None:
        self.ffmpeg_location = ffmpeg_location
        self.proxy = proxy
        self.aria2c_path = aria2c_path

    def accel_path(self, plan: VideoPlan, *, enabled: bool) -> str | None:
        """照 DownLord video/formatAccel.ts：分片协议与二进制缺失都不交给 aria2c。"""
        if not enabled or plan.fragmented or self.aria2c_path is None:
            return None
        return self.aria2c_path

    def start(
        self,
        *,
        task_id: str,
        url: str,
        out_dir: Path,
        plan: VideoPlan,
        audio_only: bool,
        subtitles: Sequence[str],
        sub_format: str,
        write_auto_subs: bool,
        limit_kbps: int | None,
        accel_used: bool,
        fallback_tried: bool,
        cookie_file: str | None = None,
        cookie_from_browser: str | None = None,
    ) -> VideoRun:
        accel = self.accel_path(plan, enabled=accel_used)
        subtitle_args = build_subtitle_args(
            langs=subtitles, sub_format=sub_format, include_auto=write_auto_subs
        )
        args = build_download_args(
            url=url,
            out_dir=out_dir,
            output_base=plan.output_base,
            selector=plan.selector,
            merge_format=plan.merge_format,
            ffmpeg_location=self.ffmpeg_location,
            proxy=self.proxy,
            audio_only=audio_only,
            subtitle_args=subtitle_args,
            accel_path=accel,
            limit_kbps=limit_kbps,
            cookie_file=cookie_file,
            cookie_from_browser=cookie_from_browser,
        )
        run = VideoRun(
            task_id=task_id,
            plan=plan,
            out_dir=out_dir,
            process=YtdlpProcess(),
            accel_used=accel is not None,
            fallback_tried=fallback_tried,
        )
        run.process.start(args, on_line=lambda line: absorb_line(run, line))
        return run


def absorb_line(run: VideoRun, line: str) -> None:
    if is_note_line(line):
        run.notes.append(line)
        return
    parsed = parse_output_line(line)
    if parsed is None:
        return
    if parsed.kind == "progress" and parsed.progress is not None:
        run.downloaded_bytes = parsed.progress.downloaded_bytes
        run.total_bytes = parsed.progress.total_bytes
        run.speed = parsed.progress.speed
        return
    if parsed.kind == "postprocess":
        run.stage = "processing"
        return
    if parsed.kind == "formats" and parsed.formats:
        run.selected_formats = parsed.formats
        return
    if parsed.kind == "destination" and parsed.filepath:
        run.destination = Path(parsed.filepath)
        return
