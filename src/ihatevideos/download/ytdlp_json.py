from __future__ import annotations

from typing import Sequence

from .errors import YtdlpUnsupported
from .models import FormatInfo, SubtitleTrack, VideoInfo

# 规则照 DownLord video/ytdlpJson.ts、ytdlpSubtitle.ts、qualityLabel.ts
HIGHEST_TAG = "最高"


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_number(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if text == "" or text == "NA":
            return None
        return float(text)
    return None


def _as_int(value: object) -> int | None:
    number = _as_number(value)
    return None if number is None else int(number)


def _entries(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def quality_tag(
    *, audio_only: bool, format_height: int | None, height_cap: int | None
) -> str | None:
    if audio_only:
        return None
    if format_height is not None:
        return f"{format_height}p"
    if height_cap is not None:
        return HIGHEST_TAG if height_cap >= 2160 else f"{height_cap}p"
    return HIGHEST_TAG


def quality_label(
    *, audio_only: bool, format_height: int | None, height_cap: int | None
) -> str:
    if audio_only:
        return "仅音频 MP3"
    if format_height is not None:
        return f"{format_height}P"
    if height_cap is not None:
        return HIGHEST_TAG if height_cap >= 2160 else f"≤{height_cap}P"
    return HIGHEST_TAG


def resolved_top_height(formats: Sequence[FormatInfo], height_cap: int | None) -> int | None:
    heights = [
        item.height
        for item in formats
        if item.height is not None and (height_cap is None or item.height <= height_cap)
    ]
    return max(heights) if heights else None


def _format_from_entry(entry: dict) -> FormatInfo:
    height = _as_int(entry.get("height"))
    filesize = _as_int(entry.get("filesize"))
    if filesize is None:
        filesize = _as_int(entry.get("filesize_approx"))
    return FormatInfo(
        format_id=_as_str(entry.get("format_id")) or "",
        ext=_as_str(entry.get("ext")),
        height=height,
        fps=_as_number(entry.get("fps")),
        vcodec=_as_str(entry.get("vcodec")),
        acodec=_as_str(entry.get("acodec")),
        filesize=filesize,
        tbr=_as_number(entry.get("tbr")),
        note=_as_str(entry.get("format_note")),
        protocol=_as_str(entry.get("protocol")),
        quality_tag=quality_tag(audio_only=height is None, format_height=height, height_cap=None),
    )


def _tracks_from(block: object, *, auto: bool) -> list[SubtitleTrack]:
    if not isinstance(block, dict):
        return []
    tracks: list[SubtitleTrack] = []
    for lang, entries in block.items():
        if not isinstance(entries, list):
            continue
        name = ""
        formats: list[str] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            ext = _as_str(item.get("ext"))
            if ext is not None:
                formats.append(ext)
            if name == "":
                candidate = item.get("name")
                if isinstance(candidate, str):
                    name = candidate
        tracks.append(SubtitleTrack(lang, name, auto, formats))
    return tracks


def parse_info_tree(payload: dict) -> VideoInfo:
    if payload.get("_type") == "playlist":
        raise YtdlpUnsupported("这是播放列表或合集，本命令只处理单个视频")
    video_id = _as_str(payload.get("id")) or ""
    raw_title = _as_str(payload.get("title"))
    extractor = _as_str(payload.get("extractor"))
    if extractor is None:
        extractor = _as_str(payload.get("extractor_key"))
    webpage_url = _as_str(payload.get("webpage_url"))
    if webpage_url is None:
        webpage_url = _as_str(payload.get("original_url"))
    subtitles = _tracks_from(payload.get("subtitles"), auto=False)
    subtitles.extend(_tracks_from(payload.get("automatic_captions"), auto=True))
    return VideoInfo(
        video_id=video_id,
        title=raw_title if raw_title is not None else video_id,
        duration_seconds=_as_number(payload.get("duration")),
        uploader=_as_str(payload.get("uploader")),
        extractor=extractor,
        webpage_url=webpage_url,
        thumbnail=_as_str(payload.get("thumbnail")),
        formats=[_format_from_entry(entry) for entry in _entries(payload.get("formats"))],
        subtitles=subtitles,
    )
