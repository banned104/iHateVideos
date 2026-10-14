import json
from pathlib import Path
from typing import Any, Sequence

import webvtt

from ..download.errors import DownloadError
from ..download.models import SubtitleTrack
from ..download.ytdlp_engine import download_subtitles
from .subtitle import Subtitle, SubtitleItem, SubtitleResult, language_priority


def track_sort_key(track: SubtitleTrack) -> tuple[int, int, str]:
    """人工字幕排在自动字幕前面，同类型内按中简 → 中繁 → 英 → 其它。"""
    return (1 if track.auto else 0, language_priority(track.lang), track.lang)


def pick_subtitle_track(tracks: Sequence[SubtitleTrack]) -> SubtitleTrack | None:
    """从清单里挑一条要下的字幕；没有可下的轨道时返回 None。"""
    candidates = [track for track in tracks if track.formats]
    if not candidates:
        return None
    return min(candidates, key=track_sort_key)


def _timestamp_ms(moment: Any) -> int:
    """把 webvtt-py 的时间戳拆成毫秒。"""
    return (
        int(moment.hours) * 3_600_000
        + int(moment.minutes) * 60_000
        + int(moment.seconds) * 1000
        + int(moment.milliseconds)
    )


def _json3_text(segs: Any) -> str:
    if not isinstance(segs, list):
        return ""
    joined = "".join(
        str(segment.get("utf8", "")) for segment in segs if isinstance(segment, dict)
    )
    return joined.strip()


def parse_json3(text: str) -> tuple[SubtitleItem, ...]:
    """解析 YouTube 的 json3 字幕：每个 event 是一段。"""
    payload = json.loads(text)
    events = payload.get("events")
    if not isinstance(events, list):
        raise ValueError("json3 字幕里没有 events")
    items: list[SubtitleItem] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        start_ms = event.get("tStartMs")
        if not isinstance(start_ms, int):
            continue
        content = _json3_text(event.get("segs"))
        if not content:
            continue
        duration = event.get("dDurationMs")
        end_ms = start_ms + duration if isinstance(duration, int) else start_ms
        items.append(
            SubtitleItem(start_ms=start_ms, end_ms=max(start_ms, end_ms), text=content)
        )
    if not items:
        raise ValueError("json3 字幕里没有可用的分段")
    return tuple(items)


def parse_vtt(path: Path) -> tuple[SubtitleItem, ...]:
    """解析 vtt 字幕；同一段的多行合并成一行。"""
    items: list[SubtitleItem] = []
    for caption in webvtt.read(str(path)):
        content = " ".join(line.strip() for line in caption.lines if line.strip())
        if not content:
            continue
        start_ms = _timestamp_ms(caption.start_time)
        end_ms = _timestamp_ms(caption.end_time)
        items.append(
            SubtitleItem(start_ms=start_ms, end_ms=max(start_ms, end_ms), text=content)
        )
    if not items:
        raise ValueError("vtt 字幕里没有可用的分段")
    return tuple(items)


def parse_subtitle_file(path: Path) -> tuple[SubtitleItem, ...]:
    """按扩展名分派：json3 走标准库 json，vtt 交给 webvtt-py。"""
    suffix = path.suffix.lower()
    if suffix == ".json3":
        return parse_json3(path.read_text(encoding="utf-8"))
    if suffix == ".vtt":
        return parse_vtt(path)
    raise ValueError(f"不认识的字幕格式：{path.suffix}")


def fetch_youtube_subtitle(
    url: str,
    *,
    tracks: Sequence[SubtitleTrack],
    out_dir: Path,
    output_base: str,
    proxy: str,
    cookie_file: str | None = None,
) -> SubtitleResult:
    """挑一条字幕下下来并解析；失败时在 reason 里说明原因。"""
    track = pick_subtitle_track(tracks)
    if track is None:
        return SubtitleResult(None, "这个视频没有可下载的字幕轨道")
    try:
        path = download_subtitles(
            url=url,
            out_dir=out_dir,
            output_base=output_base,
            lang=track.lang,
            auto=track.auto,
            proxy=proxy,
            cookie_file=cookie_file,
        )
        items = parse_subtitle_file(path)
    except (DownloadError, ValueError, OSError) as exc:
        return SubtitleResult(None, f"取 {track.lang} 字幕失败：{exc}")
    text = "\n".join(item.text for item in items)
    return SubtitleResult(
        Subtitle(text=text, items=items),
        "",
        lang=track.lang,
        source="auto" if track.auto else "manual",
    )
