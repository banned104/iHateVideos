from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..media.timestamps import format_timestamp, parse_seconds
from .paths import DEFAULT_FRAME_FORMAT, asset_path, asset_reference

PLACEHOLDER_RE = re.compile(
    r"<!--\s*FRAME:\s*(?P<time>\d+(?::\d+)*(?:\.\d+)?)"
    r"\s*(?:\|\s*(?P<caption>[^>]*?))?\s*-->"
)


@dataclass(frozen=True)
class Placeholder:
    start: int
    end: int
    raw: str
    seconds: float
    caption: str


def find_placeholders(text: str) -> list[Placeholder]:
    found: list[Placeholder] = []
    for match in PLACEHOLDER_RE.finditer(text):
        found.append(
            Placeholder(
                start=match.start(),
                end=match.end(),
                raw=match.group(0),
                seconds=parse_seconds(match.group("time")),
                caption=(match.group("caption") or "").strip(),
            )
        )
    return found


def find_placeholder_seconds(text: str) -> list[float]:
    # 同一时间点重复出现时只保留一次，保持出现顺序
    seen: dict[float, None] = {}
    for item in find_placeholders(text):
        seen.setdefault(item.seconds, None)
    return list(seen)


def read_markdown(markdown_path: Path | str) -> tuple[Path, str]:
    md = Path(markdown_path)
    if not md.is_file():
        raise FileNotFoundError(f"找不到 Markdown 文件：{md}")
    return md, md.read_text(encoding="utf-8")


def render_reference(caption: str, image_path: Path | str) -> str:
    return f"![{caption}]({asset_reference(image_path)})"


def insert_images(
    markdown_path: Path | str, *, fmt: str = DEFAULT_FRAME_FORMAT
) -> dict[str, Any]:
    """把正文里的占位符换成图片引用

    图片不存在时保留占位符原样，并把这一处记进 missing。
    """
    md, text = read_markdown(markdown_path)
    pieces: list[str] = []
    cursor = 0
    inserted: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for item in find_placeholders(text):
        pieces.append(text[cursor : item.start])
        image = asset_path(md, item.seconds, fmt)
        record = {
            "timestamp": format_timestamp(item.seconds),
            "seconds": item.seconds,
            "image": str(image),
            "caption": item.caption,
        }
        if image.is_file():
            inserted.append(record)
            pieces.append(render_reference(item.caption, image))
        else:
            missing.append(record)
            pieces.append(item.raw)
        cursor = item.end
    pieces.append(text[cursor:])
    updated = "".join(pieces)

    changed = updated != text
    if changed:
        md.write_text(updated, encoding="utf-8")
    return {
        "markdown": str(md),
        "changed": changed,
        "inserted": inserted,
        "missing": missing,
    }
