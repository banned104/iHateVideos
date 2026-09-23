import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ffmpeg import DEFAULT_TIMEOUT_SECONDS, FfmpegError, base_arguments, run_ffmpeg
from .paths import audio_path, chunk_dir, chunk_path, ensure_dir, parameter_signature
from .probe import probe_media

SUPPORTED_FORMATS = ("wav", "m4a", "mp3")
DEFAULT_WAV_SAMPLE_RATE = 16000
DEFAULT_WAV_CHANNELS = 1
DEFAULT_BITRATE = "192k"
_BYTES_PER_SAMPLE = 2
_MIN_CHUNK_SECONDS = 0.05


@dataclass(frozen=True)
class AudioResult:
    source: Path
    path: Path
    fmt: str
    sample_rate: int
    channels: int
    duration_seconds: float
    reused: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "input": str(self.source),
            "path": str(self.path),
            "format": self.fmt,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "duration_seconds": round(self.duration_seconds, 3),
            "reused": self.reused,
        }


@dataclass(frozen=True)
class AudioChunk:
    index: int
    path: Path
    start_seconds: float
    end_seconds: float
    size_bytes: int

    def to_json(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "path": str(self.path),
            "start_seconds": round(self.start_seconds, 3),
            "end_seconds": round(self.end_seconds, 3),
            "size_bytes": self.size_bytes,
        }


def _codec_args(fmt: str, bitrate: str | None) -> list[str]:
    if fmt == "wav":
        return ["-c:a", "pcm_s16le"]
    if fmt == "mp3":
        return ["-c:a", "libmp3lame", "-b:a", bitrate or DEFAULT_BITRATE]
    return ["-c:a", "aac", "-b:a", bitrate or DEFAULT_BITRATE]


def _min_chunk_bytes(sample_rate: int, channels: int) -> int:
    # 不足 50 毫秒的块视为音频已经结束
    return max(1, int(sample_rate * channels * _BYTES_PER_SAMPLE * _MIN_CHUNK_SECONDS))


def extract_audio(
    source: Path | str,
    *,
    fmt: str = "wav",
    sample_rate: int | None = None,
    channels: int | None = None,
    bitrate: str | None = None,
    start: float | None = None,
    end: float | None = None,
    output: Path | str | None = None,
    out_dir: Path | str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    reuse: bool = False,
) -> AudioResult:
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"--format 只能是 {' 或 '.join(SUPPORTED_FORMATS)}：{fmt}")
    if sample_rate is not None and sample_rate <= 0:
        raise ValueError(f"--sample-rate 必须大于 0：{sample_rate}")
    if channels is not None and channels <= 0:
        raise ValueError(f"--channels 必须大于 0：{channels}")
    media_path = Path(source).expanduser()
    media = probe_media(media_path, timeout=min(timeout, 60))
    if not media.has_audio:
        raise ValueError(f"输入没有音轨：{media_path}")
    total = media.duration_seconds
    range_start = 0.0 if start is None else float(start)
    range_end = total if end is None else float(end)
    if range_start < 0:
        raise ValueError("--range 的起点不能为负数")
    if range_end <= range_start:
        raise ValueError(f"音频时间段不成立：{range_start} 到 {range_end}")
    if range_end > total:
        raise ValueError(f"--range 的终点（{range_end} 秒）超过媒体时长（{total:.3f} 秒）")
    resolved_rate = sample_rate
    resolved_channels = channels
    if fmt == "wav":
        resolved_rate = sample_rate if sample_rate is not None else DEFAULT_WAV_SAMPLE_RATE
        resolved_channels = channels if channels is not None else DEFAULT_WAV_CHANNELS
    if output is not None:
        target = Path(output).expanduser()
    else:
        base = Path(out_dir) if out_dir is not None else Path("temp") / "media"
        signature = parameter_signature(
            fmt=fmt,
            sample_rate=resolved_rate or 0,
            channels=resolved_channels or 0,
            bitrate=bitrate or "",
            start=round(range_start, 3),
            end=round(range_end, 3),
        )
        target = audio_path(base, media_path, fmt, signature)
    if reuse and target.is_file() and target.stat().st_size > 0:
        return AudioResult(
            source=media_path,
            path=target,
            fmt=fmt,
            sample_rate=resolved_rate or media.audio.sample_rate,
            channels=resolved_channels or media.audio.channels,
            duration_seconds=range_end - range_start,
            reused=True,
        )
    ensure_dir(target.parent)
    args = [
        *base_arguments(),
        "-y",
        "-ss",
        f"{range_start:.3f}",
        "-i",
        str(media_path),
        "-t",
        f"{range_end - range_start:.3f}",
        "-vn",
    ]
    if resolved_channels is not None:
        args += ["-ac", str(resolved_channels)]
    if resolved_rate is not None:
        args += ["-ar", str(resolved_rate)]
    args += [*_codec_args(fmt, bitrate), str(target)]
    run_ffmpeg(args, timeout=timeout)
    if not target.is_file() or target.stat().st_size == 0:
        raise FfmpegError(f"没有生成可用的音频文件：{target}")
    return AudioResult(
        source=media_path,
        path=target,
        fmt=fmt,
        sample_rate=resolved_rate or media.audio.sample_rate,
        channels=resolved_channels or media.audio.channels,
        duration_seconds=range_end - range_start,
        reused=False,
    )


def chunk_audio(
    source: Path | str,
    *,
    chunk_seconds: float,
    out_dir: Path | str | None = None,
    sample_rate: int = DEFAULT_WAV_SAMPLE_RATE,
    channels: int = DEFAULT_WAV_CHANNELS,
    start: float = 0.0,
    end: float | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    reuse: bool = False,
) -> list[AudioChunk]:
    # 切成等长 WAV，供语音识别分块提交
    if chunk_seconds <= 0:
        raise ValueError(f"--chunk-seconds 必须大于 0：{chunk_seconds}")
    if sample_rate <= 0:
        raise ValueError(f"--sample-rate 必须大于 0：{sample_rate}")
    if channels <= 0:
        raise ValueError(f"--channels 必须大于 0：{channels}")
    media_path = Path(source).expanduser()
    media = probe_media(media_path, timeout=min(timeout, 60))
    if not media.has_audio:
        raise ValueError(f"输入没有音轨：{media_path}")
    total = media.duration_seconds
    range_start = float(start)
    range_end = total if end is None else min(float(end), total)
    if range_start < 0:
        raise ValueError("起始时间不能为负数")
    if range_end <= range_start:
        raise ValueError(f"音频时间段不成立：{range_start} 到 {range_end}")
    min_bytes = _min_chunk_bytes(sample_rate, channels)
    bytes_per_second = sample_rate * channels * _BYTES_PER_SAMPLE
    if chunk_seconds * bytes_per_second < min_bytes:
        raise ValueError(f"--chunk-seconds 太小，每块不足 {_MIN_CHUNK_SECONDS} 秒：{chunk_seconds}")
    span = range_end - range_start
    if span < _MIN_CHUNK_SECONDS:
        raise ValueError(f"音频时间段不足 {_MIN_CHUNK_SECONDS} 秒：{span:.3f}")
    count = max(1, math.ceil(round(span, 3) / chunk_seconds))
    base = Path(out_dir) if out_dir is not None else Path("temp") / "media"
    signature = parameter_signature(
        sample_rate=sample_rate,
        channels=channels,
        chunk_seconds=round(chunk_seconds, 3),
        start=round(range_start, 3),
        end=round(range_end, 3),
    )
    ensure_dir(chunk_dir(base, chunk_seconds, signature))
    chunks: list[AudioChunk] = []
    for index in range(1, count + 1):
        chunk_start = range_start + (index - 1) * chunk_seconds
        chunk_length = min(chunk_seconds, range_end - chunk_start)
        if chunk_length <= 0:
            break
        target = chunk_path(base, chunk_seconds, index, signature)
        if reuse and target.is_file() and target.stat().st_size > min_bytes:
            chunks.append(
                AudioChunk(
                    index=index,
                    path=target,
                    start_seconds=chunk_start,
                    end_seconds=chunk_start + chunk_length,
                    size_bytes=target.stat().st_size,
                )
            )
            continue
        args = [
            *base_arguments(),
            "-y",
            "-ss",
            f"{chunk_start:.3f}",
            "-i",
            str(media_path),
            "-t",
            f"{chunk_length:.3f}",
            "-vn",
            "-ac",
            str(channels),
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(target),
        ]
        run_ffmpeg(args, timeout=timeout)
        if not target.is_file() or target.stat().st_size <= min_bytes:
            # 音频已经结束，去掉这个空块
            if target.is_file():
                target.unlink()
            break
        chunks.append(
            AudioChunk(
                index=index,
                path=target,
                start_seconds=chunk_start,
                end_seconds=chunk_start + chunk_length,
                size_bytes=target.stat().st_size,
            )
        )
    if not chunks:
        raise FfmpegError(f"没有切出任何音频分块：{media_path}")
    return chunks
