from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AlignUnit:
    text: str
    start_seconds: float
    end_seconds: float

    def to_json(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "start_time": round(self.start_seconds, 3),
            "end_time": round(self.end_seconds, 3),
        }


@dataclass(frozen=True)
class Sentence:
    begin_time_ms: int
    end_time_ms: int
    text: str

    def to_json(self) -> dict[str, Any]:
        # begin_time 用毫秒，字段名与 export 模块认的 transcripts[].sentences[] 一致
        return {
            "begin_time": self.begin_time_ms,
            "end_time": self.end_time_ms,
            "text": self.text,
        }


@dataclass(frozen=True)
class TranscriptionResult:
    input_path: Path
    audio_path: Path
    model_dir: Path
    aligner_dir: Path | None
    language: str
    device: str
    device_name: str
    duration_seconds: float
    audio_seconds: float
    load_seconds: float
    transcribe_seconds: float
    text: str
    sentences: list[Sentence]
    units: list[AlignUnit] = field(default_factory=list)
    out_path: Path | None = None

    @property
    def realtime_factor(self) -> float:
        if self.duration_seconds <= 0:
            return 0.0
        return self.transcribe_seconds / self.duration_seconds

    def to_json(self) -> dict[str, Any]:
        return {
            "input": str(self.input_path),
            "audio": str(self.audio_path),
            "model_dir": str(self.model_dir),
            "aligner_dir": str(self.aligner_dir) if self.aligner_dir else None,
            "language": self.language,
            "device": self.device,
            "device_name": self.device_name,
            "duration_seconds": round(self.duration_seconds, 3),
            "audio_seconds": round(self.audio_seconds, 3),
            "load_seconds": round(self.load_seconds, 3),
            "transcribe_seconds": round(self.transcribe_seconds, 3),
            "realtime_factor": round(self.realtime_factor, 4),
            "chars": len(self.text),
            "text": self.text,
            "sentences": [item.to_json() for item in self.sentences],
            "units": [item.to_json() for item in self.units],
            "out": str(self.out_path) if self.out_path else None,
        }

    def to_export_payload(self) -> dict[str, Any]:
        # export 模块的 json_to_md 认这个结构，直接写出去就能转 Markdown
        return {
            "source": str(self.input_path),
            "language": self.language,
            "text": self.text,
            "transcripts": [
                {
                    "id": "0",
                    "text": self.text,
                    "sentences": [item.to_json() for item in self.sentences],
                }
            ],
        }
