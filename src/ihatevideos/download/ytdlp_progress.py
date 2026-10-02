from __future__ import annotations

import json
import re
from dataclasses import dataclass

# 常量与规则照 DownLord video/ytdlpProgress.ts，含义逐条保持一致
PROGRESS_PREFIX = "dlp:"
RE_POSTPROCESS_TAG = re.compile(r"^\[(Merger|ExtractAudio|VideoConvertor|Fixup\w*|Metadata)\]")
RE_DELETING_ORIGINAL = re.compile(r"Deleting original file")
RE_ABS_PATH = re.compile(r"^([A-Za-z]:[\\/]|\\\\|/)")
RE_ALREADY_DOWNLOADED = re.compile(r"^\[download\]\s+(.+?)\s+has already been downloaded$")
# yt-dlp 实际选中的格式，例如 [info] BV1xx: Downloading 1 format(s): 30016+30216
RE_DOWNLOADING_FORMATS = re.compile(r"^\[info\]\s+.*Downloading \d+ format\(s\):\s*(.+)$")


@dataclass(frozen=True)
class ProgressFrame:
    downloaded_bytes: int
    total_bytes: int
    speed: float
    stream_done: bool


@dataclass(frozen=True)
class ParsedLine:
    kind: str  # "progress" | "postprocess" | "destination" | "formats"
    progress: ProgressFrame | None = None
    filepath: str | None = None
    formats: str | None = None


# 模板里取不到的字段会输出字面量 NA，这里显式把 NA 与空串当作空值
def _blank_to_none(raw: str) -> str | None:
    text = raw.strip()
    return None if text == "" or text == "NA" else text


def _to_int(raw: str) -> int | None:
    text = _blank_to_none(raw)
    return None if text is None else int(text)


def _to_float(raw: str) -> float | None:
    text = _blank_to_none(raw)
    return None if text is None else float(text)


def _first_int(*values: int | None) -> int:
    for value in values:
        if value is not None:
            return value
    return 0


def _parse_progress(payload: str) -> ParsedLine | None:
    parts = payload.split("|")
    if len(parts) != 5:
        return None
    status = parts[0].strip()
    if status not in ("downloading", "finished"):
        return None
    downloaded = _to_int(parts[1])
    total = _to_int(parts[2])
    estimate = _to_int(parts[3])
    speed = _to_float(parts[4])
    total_bytes = _first_int(total, estimate)
    if status == "downloading":
        frame = ProgressFrame(
            downloaded_bytes=downloaded if downloaded is not None else 0,
            total_bytes=total_bytes,
            speed=speed if speed is not None else 0.0,
            stream_done=False,
        )
    else:
        frame = ProgressFrame(
            downloaded_bytes=downloaded if downloaded is not None else total_bytes,
            total_bytes=total_bytes,
            speed=0.0,
            stream_done=True,
        )
    return ParsedLine(kind="progress", progress=frame)


def parse_output_line(line: str) -> ParsedLine | None:
    text = line.strip()
    if not text:
        return None
    if text.startswith(PROGRESS_PREFIX):
        return _parse_progress(text[len(PROGRESS_PREFIX):])
    if RE_POSTPROCESS_TAG.match(text) or RE_DELETING_ORIGINAL.search(text):
        return ParsedLine(kind="postprocess")
    selected = RE_DOWNLOADING_FORMATS.match(text)
    if selected is not None:
        return ParsedLine(kind="formats", formats=selected.group(1).strip())
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        parsed = json.loads(text)
        if isinstance(parsed, str) and RE_ABS_PATH.match(parsed):
            return ParsedLine(kind="destination", filepath=parsed)
        return None
    if RE_ABS_PATH.match(text):
        return ParsedLine(kind="destination", filepath=text)
    already = RE_ALREADY_DOWNLOADED.match(text)
    if already is not None:
        return ParsedLine(kind="destination", filepath=already.group(1))
    return None
