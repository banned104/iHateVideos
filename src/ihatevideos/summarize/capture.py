from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from ..media.ffmpeg import DEFAULT_TIMEOUT_SECONDS
from ..media.frames import DEFAULT_JOBS, DEFAULT_QUALITY, FrameResult, capture_frames
from .paths import DEFAULT_FRAME_FORMAT, asset_path


def capture_for_markdown(
    video: Path | str,
    markdown_path: Path | str,
    timestamps: Sequence[float],
    *,
    fmt: str = DEFAULT_FRAME_FORMAT,
    width: int | None = None,
    quality: int = DEFAULT_QUALITY,
    jobs: int = DEFAULT_JOBS,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    reuse: bool = False,
) -> tuple[list[FrameResult], list[dict[str, Any]]]:
    """把视频在给定时间点的画面取到 Markdown 同级的 assets/ 目录

    目标文件名由 Markdown 文件名与时间点决定，整个目录可以直接搬走。
    """
    if not timestamps:
        raise ValueError("没有给出任何时间点")
    md = Path(markdown_path)
    targets = [(float(seconds), asset_path(md, float(seconds), fmt)) for seconds in timestamps]
    return capture_frames(
        video,
        targets,
        fmt=fmt,
        width=width,
        quality=quality,
        jobs=jobs,
        timeout=timeout,
        reuse=reuse,
    )
