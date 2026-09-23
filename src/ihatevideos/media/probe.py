from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ffmpeg import FfmpegError, FFPROBE_TIMEOUT_SECONDS, run_ffprobe_json


@dataclass(frozen=True)
class VideoStreamInfo:
    index: int
    codec: str
    width: int
    height: int
    fps: float
    pixel_format: str
    bitrate: int
    frames: int

    def to_json(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "codec": self.codec,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "pixel_format": self.pixel_format,
            "bitrate": self.bitrate,
            "frames": self.frames,
        }


@dataclass(frozen=True)
class AudioStreamInfo:
    index: int
    codec: str
    sample_rate: int
    channels: int
    bitrate: int

    def to_json(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "codec": self.codec,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "bitrate": self.bitrate,
        }


@dataclass(frozen=True)
class StreamSummary:
    index: int
    codec_type: str
    codec: str
    duration_seconds: float
    width: int
    height: int
    sample_rate: int
    channels: int

    def to_json(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "codec_type": self.codec_type,
            "codec": self.codec,
            "duration_seconds": round(self.duration_seconds, 3),
            "width": self.width,
            "height": self.height,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
        }


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    format_name: str
    size_bytes: int
    duration_seconds: float
    video: VideoStreamInfo | None
    audio: AudioStreamInfo | None
    streams: tuple[StreamSummary, ...] = field(default=())

    @property
    def has_video(self) -> bool:
        return self.video is not None

    @property
    def has_audio(self) -> bool:
        return self.audio is not None

    def to_json(self, *, include_streams: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "input": str(self.path),
            "format": self.format_name,
            "size_bytes": self.size_bytes,
            "duration_seconds": self.duration_seconds,
            "has_video": self.has_video,
            "has_audio": self.has_audio,
            "video": self.video.to_json() if self.video else None,
            "audio": self.audio.to_json() if self.audio else None,
        }
        if include_streams:
            payload["streams"] = [stream.to_json() for stream in self.streams]
        return payload


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_fraction(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    if "/" in text:
        numerator, _, denominator = text.partition("/")
        divisor = _as_float(denominator)
        return _as_float(numerator) / divisor if divisor else 0.0
    return _as_float(text)


def probe_media(path: Path | str, *, timeout: int = FFPROBE_TIMEOUT_SECONDS) -> MediaInfo:
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"找不到输入文件：{source}")
    payload = run_ffprobe_json(
        ["-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(source)],
        timeout=timeout,
    )
    streams = payload.get("streams") or []
    if not isinstance(streams, list):
        raise FfmpegError(f"ffprobe 没有返回流信息：{source}")
    format_section = payload.get("format") or {}
    duration = _as_float(format_section.get("duration"), 0.0)
    video: VideoStreamInfo | None = None
    audio: AudioStreamInfo | None = None
    summaries: list[StreamSummary] = []
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        codec_type = str(stream.get("codec_type") or "")
        stream_duration = _as_float(stream.get("duration"), 0.0)
        duration = max(duration, stream_duration)
        summaries.append(
            StreamSummary(
                index=_as_int(stream.get("index"), -1),
                codec_type=codec_type,
                codec=str(stream.get("codec_name") or ""),
                duration_seconds=stream_duration,
                width=_as_int(stream.get("width")),
                height=_as_int(stream.get("height")),
                sample_rate=_as_int(stream.get("sample_rate")),
                channels=_as_int(stream.get("channels")),
            )
        )
        if codec_type == "video" and video is None:
            video = VideoStreamInfo(
                index=_as_int(stream.get("index"), -1),
                codec=str(stream.get("codec_name") or ""),
                width=_as_int(stream.get("width")),
                height=_as_int(stream.get("height")),
                fps=_parse_fraction(stream.get("avg_frame_rate") or stream.get("r_frame_rate")),
                pixel_format=str(stream.get("pix_fmt") or ""),
                bitrate=_as_int(stream.get("bit_rate")),
                frames=_as_int(stream.get("nb_frames")),
            )
        elif codec_type == "audio" and audio is None:
            audio = AudioStreamInfo(
                index=_as_int(stream.get("index"), -1),
                codec=str(stream.get("codec_name") or ""),
                sample_rate=_as_int(stream.get("sample_rate")),
                channels=_as_int(stream.get("channels")),
                bitrate=_as_int(stream.get("bit_rate")),
            )
    # 图片之类的输入没有时长，probe 仍然返回流信息，时长交给各子命令校验
    return MediaInfo(
        path=source,
        format_name=str(format_section.get("format_name") or ""),
        size_bytes=_as_int(format_section.get("size")) or source.stat().st_size,
        duration_seconds=duration,
        video=video,
        audio=audio,
        streams=tuple(summaries),
    )
