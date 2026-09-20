"""Mult-platform input module (belongs to the iHateVideos project).

One import surface for the Agent:

    from ihatevideos.input import resolve_input, detect_platform, Platform
"""

from .artifacts import (
    comment_artifact_paths,
    prepare_session_dir,
    session_dir_name,
    subtitle_artifact_paths,
    write_meta_json,
)
from .bilibili_ids import (
    extract_bilibili_page,
    extract_bilibili_target_id,
    extract_bvid,
    normalize_bilibili_target,
)
from .comments import (
    DEFAULT_COMMENT_LIMIT,
    BilibiliComment,
    BilibiliCommentBundle,
    PlatformComment,
    PlatformCommentBundle,
    comments_to_markdown,
    count_comment_replies,
    count_up_replies,
    fetch_bilibili_comments,
    fetch_bilibili_comments_async,
    fetch_comments_with_login,
    write_comments_json,
    write_comments_markdown,
)
from .cookies import (
    BILIBILI_COOKIES_FILE_ENV,
    bilibili_cookie_string,
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
    "BilibiliComment",
    "BilibiliCommentBundle",
    "BilibiliSubtitle",
    "DEFAULT_COMMENT_LIMIT",
    "Platform",
    "PlatformComment",
    "PlatformCommentBundle",
    "PlatformDownloader",
    "PlatformMetadata",
    "ResolvedInput",
    "VideoMetadata",
    "XiaoyuzhouDownloader",
    "XimalayaDownloader",
    "bilibili_cookie_string",
    "comment_artifact_paths",
    "comments_to_markdown",
    "count_comment_replies",
    "count_up_replies",
    "credential_status",
    "detect_platform",
    "extract_bilibili_page",
    "extract_bilibili_target_id",
    "extract_bvid",
    "extract_platform_id",
    "fetch_bilibili_comments",
    "fetch_bilibili_comments_async",
    "fetch_bilibili_subtitle",
    "fetch_comments_with_login",
    "fetch_xiaoyuzhou_metadata",
    "get_video_metadata",
    "get_video_metadata_async",
    "import_bilibili_cookies",
    "load_bilibili_cookies",
    "normalize_bilibili_target",
    "prepare_session_dir",
    "resolve_input",
    "resolve_ximalaya_sound_url",
    "build_transcription_artifact_name",
    "sanitize_filename_component",
    "session_dir_name",
    "subtitle_artifact_paths",
    "write_comments_json",
    "write_comments_markdown",
    "write_meta_json",
]
