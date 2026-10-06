from __future__ import annotations

from pathlib import Path

from ..media.paths import sanitize_stem
from ..paths import find_project_root

MODEL_NAME = "Qwen3-ASR-1.7B"
ALIGNER_NAME = "Qwen3-ForcedAligner-0.6B"
MODELS_SUBDIR = "models"
DEFAULT_OUTPUT_ROOT = Path("temp") / "stt"
AUDIO_FILENAME = "audio.wav"
TRANSCRIPT_FILENAME = "transcription.json"
EXPORT_FILENAME = "export.json"


def project_root(start: Path | str | None = None) -> Path:
    return find_project_root(Path(start) if start is not None else None)


def models_root(root: Path | str | None = None) -> Path:
    base = Path(root) if root is not None else project_root()
    return base / MODELS_SUBDIR


def default_model_dir(root: Path | str | None = None) -> Path:
    return models_root(root) / MODEL_NAME


def default_aligner_dir(root: Path | str | None = None) -> Path:
    return models_root(root) / ALIGNER_NAME


def default_output_dir(source: Path | str, *, root: Path | str | None = None) -> Path:
    base = Path(root) if root is not None else DEFAULT_OUTPUT_ROOT
    return base / sanitize_stem(Path(source).stem)


def audio_path(out_dir: Path | str) -> Path:
    return Path(out_dir) / AUDIO_FILENAME


def transcript_path(out_dir: Path | str) -> Path:
    return Path(out_dir) / TRANSCRIPT_FILENAME


def export_path(out_dir: Path | str) -> Path:
    return Path(out_dir) / EXPORT_FILENAME
