import logging
from pathlib import Path

from ..download.binaries import ffmpeg_location, resolve_engines
from ..download.errors import DownloadError
from ..download.models import VideoInfo
from ..download.proxy import resolve_proxy
from ..download.ytdlp_engine import YtdlpEngine, plan_download, resolve_video
from .cookies import find_cookies_file
from .platform import Platform, PlatformDownloader, PlatformMetadata

logger = logging.getLogger(__name__)

DEFAULT_HEIGHT_CAP = 1080
MEDIA_TIMEOUT_SECONDS = 3600.0
SUPPORTED_MEDIA = ("audio", "video")


def metadata_from_info(info: VideoInfo) -> PlatformMetadata:
    """把 yt-dlp 的信息树结果转成平台元数据。"""
    return PlatformMetadata(
        platform=Platform.YOUTUBE,
        platform_id=info.video_id,
        title=info.title,
        author=info.uploader or "",
        pubdate=info.upload_date or "",
        duration_seconds=int(info.duration_seconds or 0),
        extra={
            "webpage_url": info.webpage_url or "",
            "thumbnail": info.thumbnail or "",
            "extractor": info.extractor or "",
        },
    )


def default_cookie_file() -> str | None:
    """temp/config 里那份 YouTube cookies；没有就返回 None，让 yt-dlp 匿名访问。"""
    path = find_cookies_file(Platform.YOUTUBE)
    return str(path) if path is not None else None


class YoutubeDownloader(PlatformDownloader):
    """YouTube 的媒体下载：信息树走 yt-dlp，产物交给 download 模块的引擎。"""

    def __init__(
        self,
        *,
        media: str = "audio",
        height_cap: int = DEFAULT_HEIGHT_CAP,
        cookie_file: str | None = None,
        proxy: str | None = None,
    ) -> None:
        if media not in SUPPORTED_MEDIA:
            raise ValueError(f"media 只能是 audio 或 video，收到 {media}")
        self.media = media
        self.height_cap = height_cap
        self.cookie_file = default_cookie_file() if cookie_file is None else cookie_file
        self.proxy = resolve_proxy(disabled=False) if proxy is None else proxy

    def resolve_info(self, url: str) -> VideoInfo:
        """取一次信息树；同一份信息后面还要用来挑字幕。"""
        return resolve_video(url=url, proxy=self.proxy, cookie_file=self.cookie_file)

    def download_media(self, info: VideoInfo, url: str, output_dir: Path) -> Path:
        audio_only = self.media == "audio"
        plan = plan_download(
            info,
            audio_only=audio_only,
            format_id=None,
            height_cap=None if audio_only else self.height_cap,
        )
        engines = resolve_engines(probe=False)
        engine = YtdlpEngine(
            ffmpeg_location=ffmpeg_location(engines.ffmpeg),
            proxy=self.proxy,
            aria2c_path=None,
        )
        run = engine.start(
            task_id="youtube",
            url=url,
            out_dir=output_dir,
            plan=plan,
            audio_only=audio_only,
            subtitles=(),
            sub_format="vtt",
            write_auto_subs=False,
            limit_kbps=None,
            accel_used=False,
            fallback_tried=False,
            cookie_file=self.cookie_file,
        )
        code = run.process.wait(timeout=MEDIA_TIMEOUT_SECONDS)
        if code is None:
            run.process.terminate()
            raise DownloadError(f"下载超过 {MEDIA_TIMEOUT_SECONDS:.0f} 秒没有结束")
        if code != 0:
            raise DownloadError(f"yt-dlp 退出码 {code}：{run.process.tail_logs(3)}")
        if run.destination is None:
            raise DownloadError("yt-dlp 正常结束但没有给出最终路径")
        return run.destination

    def download_audio(self, url: str, output_dir: Path) -> tuple[Path, PlatformMetadata]:
        """按 PlatformDownloader 的约定：下媒体文件并返回（路径，元数据）。"""
        output_dir.mkdir(parents=True, exist_ok=True)
        info = self.resolve_info(url)
        metadata = metadata_from_info(info)
        return self.download_media(info, url, output_dir), metadata
