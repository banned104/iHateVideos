from __future__ import annotations

import json
import time
from pathlib import Path

from ..media.ffmpeg import DEFAULT_TIMEOUT_SECONDS
from .audio import prepare_audio
from .engine import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_DEVICE,
    DEFAULT_LANGUAGE,
    DEFAULT_MAX_NEW_TOKENS,
    describe_device,
    load_asr_model,
    run_transcription,
)
from .models import TranscriptionResult
from .paths import default_output_dir, export_path, transcript_path
from .sentences import group_sentences


def transcribe(
    source: Path | str,
    *,
    out_dir: Path | str | None = None,
    model_dir: Path | str | None = None,
    aligner_dir: Path | str | None = None,
    with_timestamps: bool = True,
    language: str | None = DEFAULT_LANGUAGE,
    device: str = DEFAULT_DEVICE,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
    reuse: bool = False,
    audio_timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> TranscriptionResult:
    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"输入文件不存在：{source_path}")

    target_dir = Path(out_dir).expanduser() if out_dir else default_output_dir(source_path)
    target_dir.mkdir(parents=True, exist_ok=True)

    audio_started = time.monotonic()
    audio = prepare_audio(source_path, target_dir, reuse=reuse, timeout=audio_timeout)
    audio_seconds = time.monotonic() - audio_started

    load_started = time.monotonic()
    model, resolved_model, resolved_aligner = load_asr_model(
        model_dir=model_dir,
        aligner_dir=aligner_dir,
        with_timestamps=with_timestamps,
        device=device,
        batch_size=batch_size,
        max_new_tokens=max_new_tokens,
    )
    load_seconds = time.monotonic() - load_started

    transcribe_started = time.monotonic()
    detected_language, text, units = run_transcription(
        model, audio.path, language=language, with_timestamps=with_timestamps
    )
    transcribe_seconds = time.monotonic() - transcribe_started

    out_file = transcript_path(target_dir)
    result = TranscriptionResult(
        input_path=source_path,
        audio_path=audio.path,
        model_dir=resolved_model,
        aligner_dir=resolved_aligner,
        language=detected_language,
        device=device,
        device_name=describe_device(device),
        duration_seconds=audio.duration_seconds,
        audio_seconds=audio_seconds,
        load_seconds=load_seconds,
        transcribe_seconds=transcribe_seconds,
        text=text,
        sentences=group_sentences(text, units),
        units=units,
        out_path=out_file,
    )
    out_file.write_text(
        json.dumps(result.to_json(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    export_path(target_dir).write_text(
        json.dumps(result.to_export_payload(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result
