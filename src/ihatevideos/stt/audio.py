from __future__ import annotations

from pathlib import Path

from ..media.audio import DEFAULT_WAV_CHANNELS, DEFAULT_WAV_SAMPLE_RATE, AudioResult, extract_audio
from ..media.ffmpeg import DEFAULT_TIMEOUT_SECONDS
from .paths import audio_path


def prepare_audio(
    source: Path | str,
    out_dir: Path | str,
    *,
    reuse: bool = False,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> AudioResult:
    # 识别模型只认 16 kHz 单声道 wav，统一在这里转好，后续步骤不用再关心输入格式
    return extract_audio(
        source,
        fmt="wav",
        sample_rate=DEFAULT_WAV_SAMPLE_RATE,
        channels=DEFAULT_WAV_CHANNELS,
        output=audio_path(out_dir),
        timeout=timeout,
        reuse=reuse,
    )
