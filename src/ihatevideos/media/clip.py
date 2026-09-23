from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ffmpeg import DEFAULT_TIMEOUT_SECONDS, FfmpegError, base_arguments, run_ffmpeg
from .paths import clip_path, ensure_dir, parameter_signature
from .probe import MediaInfo, probe_media

SUPPORTED_MODES = ("reencode", "copy")
VIDEO_CONTAINERS = {"mp4", "mov", "m4v", "mkv", "webm"}
AUDIO_CONTAINERS = {"wav", "mp3", "m4a"}
DEFAULT_VIDEO_SUFFIX = "mp4"
DEFAULT_AUDIO_SUFFIX = "m4a"


@dataclass(frozen=True)
class ClipResult:
    source: Path
    path: Path
    start_seconds: float
    end_seconds: float
    mode: str
    audio_only: bool
    reused: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "input": str(self.source),
            "path": str(self.path),
            "start_seconds": round(self.start_seconds, 3),
            "end_seconds": round(self.end_seconds, 3),
            "duration_seconds": round(self.end_seconds - self.start_seconds, 3),
            "mode": self.mode,
            "audio_only": self.audio_only,
            "reused": self.reused,
        }


def _output_suffix(source: Path, *, media: MediaInfo, audio_only: bool) -> str:
    # 输出后缀决定编码器与容器，两者不匹配 ffmpeg 会直接失败，所以只保留支持的组合
    suffix = source.suffix.lower().lstrip(".")
    if audio_only or not media.has_video:
        return suffix if suffix in AUDIO_CONTAINERS else DEFAULT_AUDIO_SUFFIX
    if suffix in VIDEO_CONTAINERS or suffix in AUDIO_CONTAINERS:
        return suffix
    return DEFAULT_VIDEO_SUFFIX


def _audio_codec_args(suffix: str) -> list[str]:
    if suffix == "wav":
        return ["-c:a", "pcm_s16le"]
    if suffix == "mp3":
        return ["-c:a", "libmp3lame", "-b:a", "192k"]
    if suffix == "webm":
        return ["-c:a", "libopus", "-b:a", "128k"]
    return ["-c:a", "aac", "-b:a", "192k"]


def _video_codec_args(suffix: str) -> list[str]:
    if suffix == "webm":
        return ["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


def cut_media(
    source: Path | str,
    *,
    start: float = 0.0,
    end: float | None = None,
    duration: float | None = None,
    mode: str = "reencode",
    audio_only: bool = False,
    output: Path | str | None = None,
    out_dir: Path | str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    reuse: bool = False,
) -> ClipResult:
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"--mode 只能是 {' 或 '.join(SUPPORTED_MODES)}：{mode}")
    if end is not None and duration is not None:
        raise ValueError("--end 与 --duration 只能给出一个")
    media_path = Path(source).expanduser()
    media = probe_media(media_path, timeout=min(timeout, 60))
    total = media.duration_seconds
    if start < 0:
        raise ValueError("--start 不能为负数")
    if start >= total:
        raise ValueError(f"--start（{start} 秒）超过媒体时长（{total:.3f} 秒）")
    if end is not None:
        stop = float(end)
        if stop <= start:
            raise ValueError(f"--end（{stop} 秒）必须大于 --start（{start} 秒）")
        if stop > total:
            raise ValueError(f"--end（{stop} 秒）超过媒体时长（{total:.3f} 秒）")
    elif duration is not None:
        if duration <= 0:
            raise ValueError("--duration 必须大于 0")
        stop = min(start + float(duration), total)
    else:
        stop = total
    if audio_only and not media.has_audio:
        raise ValueError(f"输入没有音轨，无法只取音频：{media_path}")
    signature = parameter_signature(
        mode=mode,
        audio_only=audio_only,
        start=round(start, 3),
        end=round(stop, 3),
    )
    if output is not None:
        target = Path(output).expanduser()
    else:
        base = Path(out_dir) if out_dir is not None else Path("temp") / "media"
        suffix = _output_suffix(media_path, media=media, audio_only=audio_only)
        target = clip_path(base, media_path, start, stop, suffix, signature)
    if reuse and target.is_file() and target.stat().st_size > 0:
        return ClipResult(
            source=media_path,
            path=target,
            start_seconds=start,
            end_seconds=stop,
            mode=mode,
            audio_only=audio_only,
            reused=True,
        )
    ensure_dir(target.parent)
    length = f"{stop - start:.3f}"
    if mode == "copy":
        # copy 模式把裁剪参数放在输入之后，seek 前置与流复制一起用会得到过长的片段
        args = [*base_arguments(), "-y", "-i", str(media_path), "-ss", f"{start:.3f}", "-t", length]
        if audio_only or not media.has_video:
            args += ["-vn"]
        args += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
    else:
        args = [*base_arguments(), "-y", "-ss", f"{start:.3f}", "-i", str(media_path), "-t", length]
        suffix = target.suffix.lower().lstrip(".")
        if audio_only or not media.has_video:
            args += ["-vn", *_audio_codec_args(suffix)]
        else:
            args += [*_video_codec_args(suffix), *_audio_codec_args(suffix)]
            if suffix == "mp4":
                args += ["-movflags", "+faststart"]
    args.append(str(target))
    run_ffmpeg(args, timeout=timeout)
    if not target.is_file() or target.stat().st_size == 0:
        raise FfmpegError(f"没有生成可用的剪切结果：{target}")
    return ClipResult(
        source=media_path,
        path=target,
        start_seconds=start,
        end_seconds=stop,
        mode=mode,
        audio_only=audio_only,
        reused=False,
    )
