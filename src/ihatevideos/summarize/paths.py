from __future__ import annotations

from pathlib import Path

from ..paths import find_project_root

ASSETS_DIR_NAME = "assets"
TEMPLATES_DIR_NAME = "templates"
DEFAULT_FRAME_FORMAT = "jpg"


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


def asset_path(
    markdown_path: Path | str, seconds: float, fmt: str = DEFAULT_FRAME_FORMAT
) -> Path:
    md = Path(markdown_path)
    return assets_dir(md) / f"{md.stem}-{time_label(seconds)}.{fmt}"


def asset_reference(image_path: Path | str) -> str:
    # Markdown 与 Obsidian 都要求正斜杠，路径相对 Markdown 文件所在目录
    return f"{ASSETS_DIR_NAME}/{Path(image_path).name}"
