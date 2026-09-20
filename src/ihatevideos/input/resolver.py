"""Unified multi-platform input resolver.

This is the single entry point the Agent (and any future pipeline) calls.
It merges the branching logic of bilibili2text
``b2t/pipeline.py::_resolve_pipeline_input`` but stays decoupled from
``AppConfig``/storage: callers pass a plain ``download_dir`` and get back a
plain dataclass.

Contract:
    input: URL (bilibili/xiaoyuzhou/ximalaya) OR local audio file
    output: ResolvedInput(audio_file | None, metadata | None, bvid,
            transcription_id, subtitle | None, use_local_audio, platform)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .bilibili_audio import download_audio as download_bilibili_audio
from .bilibili_ids import (
    extract_bilibili_target_id,
    extract_bvid,
    normalize_bilibili_target,
)
from .metadata import VideoMetadata, get_video_metadata
from .platform import Platform
from .subtitle import BilibiliSubtitle, fetch_bilibili_subtitle
from .url_detect import detect_platform
from .xiaoyuzhou import XiaoyuzhouDownloader
from .ximalaya import XimalayaDownloader

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedInput:
    audio_file: Path | None
    metadata: VideoMetadata | None
    bvid: str
    transcription_id: str
    subtitle: BilibiliSubtitle | None
    use_local_audio: bool
    platform: Platform | None


def resolve_input(
    *,
    url: str = "",
    audio_path: Path | str | None = None,
    input_bvid: str | None = None,
    prefer_bilibili_subtitle: bool = True,
    download_dir: Path | str = ".",
    audio_quality: str = "30216",
    fetch_metadata: bool = True,
    subtitle_timeout_seconds: int = 60,
) -> ResolvedInput:
    """Resolve one video/audio input to (audio, metadata, subtitle).

    - Local file: must exist; bvid comes from ``input_bvid`` or the
      ``BV号`` inside the filename. No download, no subtitle fetch.
    - Bilibili URL: optionally reuse the native subtitle (no audio download
      in that case), otherwise download audio via yutto.
    - Xiaoyuzhou / Ximalaya URL: download audio via the platform downloader.
    """
    normalized_audio_path = (
        Path(audio_path).expanduser().resolve() if audio_path is not None else None
    )
    if normalized_audio_path is not None:
        if not normalized_audio_path.is_file():
            raise FileNotFoundError(f"上传音频文件不存在: {normalized_audio_path}")
        bvid = input_bvid or extract_bvid(normalized_audio_path.name)
        if bvid is None:
            raise ValueError(
                "无法提取资源 ID。请上传形如 `BV号_视频标题.xxx` 的音频文件。"
            )
        return ResolvedInput(
            audio_file=normalized_audio_path,
            metadata=None,
            bvid=bvid,
            transcription_id=bvid,
            subtitle=None,
            use_local_audio=True,
            platform=None,
        )

    if not url.strip():
        raise ValueError("URL 不能为空")
    platform = detect_platform(url)
    if platform is None and extract_bvid(url) is not None:
        platform = Platform.BILIBILI
    if platform is None:
        raise ValueError("不支持的 URL，请使用 Bilibili、小宇宙或喜马拉雅链接")

    if platform == Platform.BILIBILI:
        normalized_url = normalize_bilibili_target(url)
        bvid = input_bvid or extract_bvid(normalized_url)
        transcription_id = extract_bilibili_target_id(normalized_url) or bvid
        metadata = None
        if bvid and fetch_metadata:
            try:
                metadata = get_video_metadata(bvid)
            except Exception as exc:
                logger.warning("Failed to fetch video metadata: %s", exc)

        subtitle = None
        if prefer_bilibili_subtitle:
            logger.info("=== 获取 B 站字幕 ===")
            subtitle = fetch_bilibili_subtitle(
                normalized_url, timeout_seconds=subtitle_timeout_seconds
            )
        if subtitle is not None:
            audio_file = None
        else:
            logger.info("=== 下载音频 ===")
            audio_file, downloaded_metadata = download_bilibili_audio(
                normalized_url,
                Path(download_dir),
                audio_quality,
                fetch_metadata=metadata is None and fetch_metadata,
            )
            if metadata is None:
                metadata = downloaded_metadata
            bvid = bvid or extract_bvid(audio_file.name)
        if bvid is None:
            raise ValueError("无法从 URL 提取有效的资源 ID")
        return ResolvedInput(
            audio_file=audio_file,
            metadata=metadata,
            bvid=bvid,
            transcription_id=transcription_id or bvid,
            subtitle=subtitle,
            use_local_audio=False,
            platform=platform,
        )

    if platform == Platform.XIAOYUZHOU:
        logger.info("=== 下载小宇宙音频 ===")
        audio_file, platform_metadata = XiaoyuzhouDownloader().download_audio(
            url, Path(download_dir)
        )
        metadata = VideoMetadata.from_platform_metadata(platform_metadata)
        bvid = input_bvid or metadata.bvid
        return ResolvedInput(
            audio_file=audio_file,
            metadata=metadata,
            bvid=bvid,
            transcription_id=bvid,
            subtitle=None,
            use_local_audio=False,
            platform=platform,
        )

    if platform == Platform.XIMALAYA:
        logger.info("=== 下载喜马拉雅音频 ===")
        audio_file, platform_metadata = XimalayaDownloader().download_audio(
            url, Path(download_dir)
        )
        metadata = VideoMetadata.from_platform_metadata(platform_metadata)
        bvid = input_bvid or metadata.bvid
        return ResolvedInput(
            audio_file=audio_file,
            metadata=metadata,
            bvid=bvid,
            transcription_id=bvid,
            subtitle=None,
            use_local_audio=False,
            platform=platform,
        )

    raise ValueError(f"不支持的平台: {platform}")
