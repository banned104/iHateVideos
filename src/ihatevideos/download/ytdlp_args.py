from __future__ import annotations

from pathlib import Path
from typing import Sequence

# 照 DownLord video/ytdlpArgs.ts:19-20 的进度模板
PROGRESS_TEMPLATE = (
    "dlp:%(progress.status)s|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|"
    "%(progress.total_bytes_estimate)s|%(progress.speed)s"
)
FINAL_PATH_TEMPLATE = "after_move:%(filepath)j"
SOCKET_TIMEOUT_SECONDS = "30"
RESOLVE_TIMEOUT_SECONDS = 90.0
AUDIO_FORMAT = "mp3"
AUDIO_QUALITY = "0"
CONCURRENT_FRAGMENTS = 4
FRAGMENTED_PROTOCOLS = ("m3u8", "m3u8_native", "http_dash_segments", "dash")
# 照 DownLord video/ytdlpDownloader.ts:44
ARIA2_DOWNLOADER_ARGS = (
    "-x 16 -s 16 -k 1M --connect-timeout=10 --auto-save-interval=1 --allow-overwrite=true"
)


def is_fragmented_protocol(protocol: str | None) -> bool:
    """照 DownLord video/formatAccel.ts:14-30：分片协议不交给 aria2c。"""
    if not protocol:
        return False
    return any(name in protocol for name in FRAGMENTED_PROTOCOLS)


def proxy_args(proxy: str) -> list[str]:
    # 照 DownLord proxy/proxyArgs.ts:79-81：直连档传空串显式关闭代理，而不是省略参数
    return ["--proxy", proxy]


def cookie_args(*, cookie_file: str | None = None, cookie_from_browser: str | None = None) -> list[str]:
    if cookie_from_browser:
        return ["--cookies-from-browser", cookie_from_browser]
    if cookie_file:
        return ["--cookies", cookie_file]
    return []


def build_resolve_args(
    *,
    url: str,
    proxy: str,
    cookie_file: str | None = None,
    cookie_from_browser: str | None = None,
) -> list[str]:
    """照 DownLord video/ytdlpArgs.ts:39-64。"""
    args = [
        "-J",
        "--flat-playlist",
        "--no-warnings",
        "--ignore-config",
        "--no-color",
        "--socket-timeout",
        SOCKET_TIMEOUT_SECONDS,
    ]
    args += proxy_args(proxy)
    args += cookie_args(cookie_file=cookie_file, cookie_from_browser=cookie_from_browser)
    args.append(url)
    return args


def build_selector(
    *,
    audio_only: bool,
    format_id: str | None,
    acodec: str | None,
    height_cap: int | None,
) -> tuple[str, str | None]:
    """照 DownLord video/ytdlpFormat.ts:21-48，返回（格式选择表达式，合流格式）。"""
    if audio_only:
        return "bestaudio/best", None
    if format_id:
        if acodec == "none":
            return f"{format_id}+bestaudio/{format_id}", "mp4"
        return format_id, None
    if height_cap is not None:
        return (
            f"bestvideo[height<={height_cap}]+bestaudio/best[height<={height_cap}]/best",
            "mp4",
        )
    return "best", None


def normalize_langs(langs: Sequence[str]) -> tuple[str, ...]:
    """照 DownLord video/ytdlpSubtitle.ts:66-78：去空白、去重、保持顺序。"""
    ordered: list[str] = []
    for item in langs:
        text = item.strip()
        if text and text not in ordered:
            ordered.append(text)
    return tuple(ordered)


def build_subtitle_args(
    *, langs: Sequence[str], sub_format: str, include_auto: bool
) -> list[str]:
    """照 DownLord video/ytdlpSubtitle.ts:51-60。"""
    normalized = normalize_langs(langs)
    if not normalized:
        return []
    args = ["--write-subs"]
    if include_auto:
        args.append("--write-auto-subs")
    args += [
        "--sub-langs",
        ",".join(normalized),
        "--sub-format",
        f"{sub_format}/best",
        "--convert-subs",
        sub_format,
    ]
    return args


def downloader_args(*, accel_path: str | None, limit_kbps: int | None, proxy: str) -> list[str]:
    """照 DownLord video/ytdlpDownloader.ts:28-51。

    经 aria2c 下载时限速与代理都要传给 aria2c 自己，因为 yt-dlp 的 --limit-rate
    对外部下载器不生效，而 aria2c 不读系统代理。
    """
    limited = limit_kbps is not None and limit_kbps > 0
    if accel_path:
        limit_segment = f" --max-download-limit={limit_kbps}K" if limited else ""
        return [
            "--downloader",
            accel_path,
            "--downloader-args",
            f"aria2c:{ARIA2_DOWNLOADER_ARGS}{limit_segment} --all-proxy={proxy}",
        ]
    args = ["--concurrent-fragments", str(CONCURRENT_FRAGMENTS)]
    if limited:
        args += ["--limit-rate", f"{limit_kbps}K"]
    return args


def build_download_args(
    *,
    url: str,
    out_dir: Path | str,
    output_base: str,
    selector: str,
    merge_format: str | None,
    ffmpeg_location: str,
    proxy: str,
    audio_only: bool,
    subtitle_args: Sequence[str],
    accel_path: str | None,
    limit_kbps: int | None,
    cookie_file: str | None = None,
    cookie_from_browser: str | None = None,
) -> list[str]:
    """照 DownLord video/ytdlpArgs.ts:121-190 的参数顺序。"""
    output = str(Path(out_dir) / f"{output_base}.%(ext)s")
    args = [
        "-f",
        selector,
        "-o",
        output,
        "--no-playlist",
        "--newline",
        "--progress",
        "--progress-template",
        PROGRESS_TEMPLATE,
        "--ffmpeg-location",
        ffmpeg_location,
    ]
    if audio_only:
        args += ["-x", "--audio-format", AUDIO_FORMAT, "--audio-quality", AUDIO_QUALITY]
    if merge_format:
        args += ["--merge-output-format", merge_format]
    args += [
        "--windows-filenames",
        "--no-color",
        "--no-warnings",
        "--ignore-config",
        # --print 会隐含静默模式，加 --no-quiet 才能保留 [info] 行与实际格式、拿不到的格式提示
        "--no-quiet",
        "--socket-timeout",
        SOCKET_TIMEOUT_SECONDS,
    ]
    args += proxy_args(proxy)
    args += cookie_args(cookie_file=cookie_file, cookie_from_browser=cookie_from_browser)
    args += list(subtitle_args)
    if subtitle_args:
        args.append("-i")
    args += downloader_args(accel_path=accel_path, limit_kbps=limit_kbps, proxy=proxy)
    args += ["--print", FINAL_PATH_TEMPLATE, url]
    return args
