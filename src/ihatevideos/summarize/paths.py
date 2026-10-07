from __future__ import annotations

import re
from pathlib import Path

from ..paths import find_project_root

ASSETS_DIR_NAME = "assets"
TEMPLATES_DIR_NAME = "templates"
DEFAULT_FRAME_FORMAT = "jpg"
# 笔记名里的空白换成短横线：Markdown 链接的目标遇到空格就断了，Obsidian 与其他阅读器都会看不到图
WHITESPACE_RE = re.compile(r"\s+")
# 链接目标里有特殊含义的字符，百分号必须排在第一个，否则会把自己刚写进去的转义再转一遍
REFERENCE_ESCAPES = (("%", "%25"), (" ", "%20"), ("#", "%23"), ("?", "%3F"))


def project_root(start: Path | None = None) -> Path:
    return find_project_root(Path(start) if start is not None else None)


def templates_dir(root: Path | None = None) -> Path:
    return (root or project_root()) / TEMPLATES_DIR_NAME


def assets_dir(markdown_path: Path | str) -> Path:
    return Path(markdown_path).parent / ASSETS_DIR_NAME


def time_label(seconds: float) -> str:
    # 图片文件名里的时间标签：00:12 -> 0012s，01:30 -> 0130s，100:30 -> 10030s
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    return f"{minutes:02d}{secs:02d}s"


def asset_stem(markdown_path: Path | str) -> str:
    # 图片名沿用笔记名，但不带空白
    return WHITESPACE_RE.sub("-", Path(markdown_path).stem)


def asset_path(
    markdown_path: Path | str, seconds: float, fmt: str = DEFAULT_FRAME_FORMAT
) -> Path:
    md = Path(markdown_path)
    return assets_dir(md) / f"{asset_stem(md)}-{time_label(seconds)}.{fmt}"


def asset_reference(image_path: Path | str) -> str:
    # Markdown 与 Obsidian 都要求正斜杠，路径相对 Markdown 文件所在目录
    name = Path(image_path).name
    for raw, escaped in REFERENCE_ESCAPES:
        name = name.replace(raw, escaped)
    return f"{ASSETS_DIR_NAME}/{name}"
