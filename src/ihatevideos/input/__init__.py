"""Mult-platform input module (belongs to the iHateVideos project).

One import surface for the Agent:

    from ihatevideos.input import resolve_input, detect_platform, Platform
"""

from .bilibili_ids import (
    extract_bilibili_page,
    extract_bilibili_target_id,
    extract_bvid,
    normalize_bilibili_target,
)
from .cookies import (
    BILIBILI_COOKIES_FILE_ENV,
    credential_status,
    import_bilibili_cookies,
    load_bilibili_cookies,
)
from .metadata import VideoMetadata, get_video_metadata, get_video_metadata_async
from .platform import (
    Platform,
    PlatformDownloader,
    PlatformMetadata,
    build_transcription_artifact_name,
    sanitize_filename_component,
)
from .resolver import ResolvedInput, resolve_input
from .subtitle import BilibiliSubtitle, fetch_bilibili_subtitle
from .url_detect import detect_platform, extract_platform_id
from .xiaoyuzhou import XiaoyuzhouDownloader, fetch_xiaoyuzhou_metadata
from .ximalaya import XimalayaDownloader, resolve_ximalaya_sound_url

__all__ = [
    "BILIBILI_COOKIES_FILE_ENV",
    "BilibiliSubtitle",
    "Platform",
    "PlatformDownloader",
    "PlatformMetadata",
    "ResolvedInput",
    "VideoMetadata",
    "XiaoyuzhouDownloader",
    "XimalayaDownloader",
    "credential_status",
    "detect_platform",
    "extract_bilibili_page",
    "extract_bilibili_target_id",
    "extract_bvid",
    "extract_platform_id",
    "fetch_bilibili_subtitle",
    "fetch_xiaoyuzhou_metadata",
    "get_video_metadata",
    "get_video_metadata_async",
    "import_bilibili_cookies",
    "load_bilibili_cookies",
    "normalize_bilibili_target",
    "resolve_input",
    "resolve_ximalaya_sound_url",
    "build_transcription_artifact_name",
    "sanitize_filename_component",
]
