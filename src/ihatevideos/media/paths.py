import hashlib
import re
from pathlib import Path

from .timestamps import format_clip_label, format_seconds_label

DEFAULT_OUTPUT_ROOT = Path("temp") / "media"
_ILLEGAL_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_stem(value: str, *, max_length: int = 60) -> str:
    cleaned = _ILLEGAL_NAME_CHARS.sub("_", value).strip().strip(".")
    if not cleaned:
        cleaned = "media"
    return cleaned[:max_length]


def source_stem(source: Path | str) -> str:
    return sanitize_stem(Path(source).stem)


def parameter_signature(**parts: object) -> str:
    # 影响产出的参数摘要写进文件名，--reuse 才不会复用到别的参数产出的文件
    payload = "|".join(f"{key}={value}" for key, value in sorted(parts.items()))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]


def default_output_dir(source: Path | str, *, root: Path | str | None = None) -> Path:
    base = Path(root).expanduser() if root is not None else DEFAULT_OUTPUT_ROOT
    return base / source_stem(source)


def ensure_dir(path: Path | str) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def frames_dir(out_dir: Path | str) -> Path:
    return Path(out_dir) / "frames"


def audio_dir(out_dir: Path | str) -> Path:
    return Path(out_dir) / "audio"


def chunk_dir(out_dir: Path | str, chunk_seconds: float, signature: str) -> Path:
    # 目录名带上块时长与参数摘要，换参数后不会误用旧产物
    return audio_dir(out_dir) / f"chunks-{format_seconds_label(chunk_seconds)}-{signature}"


def clips_dir(out_dir: Path | str) -> Path:
    return Path(out_dir) / "clips"


def frame_path(
    out_dir: Path | str, index: int, seconds: float, fmt: str, signature: str
) -> Path:
    return frames_dir(out_dir) / f"frame-{index:03d}_{seconds:.3f}s_{signature}.{fmt}"


def audio_path(out_dir: Path | str, source: Path | str, fmt: str, signature: str) -> Path:
    return audio_dir(out_dir) / f"{source_stem(source)}_{signature}.{fmt}"


def chunk_path(
    out_dir: Path | str,
    chunk_seconds: float,
    index: int,
    signature: str,
    fmt: str = "wav",
) -> Path:
    return chunk_dir(out_dir, chunk_seconds, signature) / f"audio-{index:03d}.{fmt}"


def clip_path(
    out_dir: Path | str,
    source: Path | str,
    start: float,
    end: float,
    suffix: str,
    signature: str,
) -> Path:
    label = f"{format_clip_label(start)}-{format_clip_label(end)}"
    return clips_dir(out_dir) / f"{source_stem(source)}_{label}_{signature}.{suffix}"
