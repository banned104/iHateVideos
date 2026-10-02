from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

# 照 DownLord video/filename.ts:15-25
ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
TRAILING_DOTS_OR_SPACES = re.compile(r"[. ]+$")
WINDOWS_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$", re.IGNORECASE)


def sanitize_basename(name: str) -> str:
    cleaned = ILLEGAL_CHARS.sub("_", name).strip()
    cleaned = TRAILING_DOTS_OR_SPACES.sub("", cleaned)
    stem = cleaned.split(".")[0]
    if WINDOWS_RESERVED.match(stem):
        cleaned = "_" + cleaned
    return cleaned or "download"


def name_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    return sanitize_basename(urllib.parse.unquote(Path(path).name))


def predict_ext(*, audio_only: bool, acodec: str | None, ext: str | None) -> str:
    """照 DownLord video/filename.ts:50-58。acodec 为空表示还没有选定格式。"""
    if audio_only:
        return "mp3"
    if acodec is None or acodec == "none":
        return "mp4"
    return ext or "mp4"


def video_filename(*, title: str, quality_tag: str | None, ext: str) -> str:
    """照 DownLord tasks/taskManager.ts:1065-1068 的取名：<清洗后的标题> [<短标>].<扩展名>。"""
    base = sanitize_basename(title)
    named = f"{base} [{quality_tag}]" if quality_tag else base
    return f"{named}.{ext}"
