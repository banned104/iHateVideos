from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class TaskKind(StrEnum):
    DIRECT = "direct"
    VIDEO = "video"


class TaskStatus(StrEnum):
    RESOLVING = "resolving"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


# 合法流转表，照 DownLord tasks/stateMachine.ts 去掉 awaiting_selection
ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.QUEUED: frozenset(
        {TaskStatus.RESOLVING, TaskStatus.DOWNLOADING, TaskStatus.ERROR}
    ),
    TaskStatus.RESOLVING: frozenset(
        {TaskStatus.QUEUED, TaskStatus.DOWNLOADING, TaskStatus.ERROR}
    ),
    TaskStatus.DOWNLOADING: frozenset(
        {TaskStatus.PROCESSING, TaskStatus.COMPLETED, TaskStatus.PAUSED, TaskStatus.ERROR}
    ),
    TaskStatus.PAUSED: frozenset({TaskStatus.DOWNLOADING, TaskStatus.ERROR}),
    TaskStatus.PROCESSING: frozenset(
        {TaskStatus.COMPLETED, TaskStatus.PAUSED, TaskStatus.ERROR}
    ),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.ERROR: frozenset(),
}

TERMINAL_STATUSES = frozenset({TaskStatus.COMPLETED, TaskStatus.ERROR})


@dataclass
class SubtitleTrack:
    lang: str
    name: str
    auto: bool
    formats: list[str]

    def to_json(self) -> dict:
        return {
            "lang": self.lang,
            "name": self.name,
            "auto": self.auto,
            "formats": list(self.formats),
        }


@dataclass
class FormatInfo:
    format_id: str
    ext: str | None
    height: int | None
    fps: float | None
    vcodec: str | None
    acodec: str | None
    filesize: int | None
    tbr: float | None
    note: str | None
    protocol: str | None
    quality_tag: str | None = None

    def to_json(self) -> dict:
        return {
            "format_id": self.format_id,
            "ext": self.ext,
            "height": self.height,
            "fps": self.fps,
            "vcodec": self.vcodec,
            "acodec": self.acodec,
            "filesize": self.filesize,
            "tbr": self.tbr,
            "note": self.note,
            "protocol": self.protocol,
            "quality_tag": self.quality_tag,
        }


@dataclass
class VideoInfo:
    video_id: str
    title: str
    duration_seconds: float | None
    uploader: str | None
    extractor: str | None
    webpage_url: str | None
    thumbnail: str | None
    formats: list[FormatInfo] = field(default_factory=list)
    subtitles: list[SubtitleTrack] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "id": self.video_id,
            "title": self.title,
            "duration_seconds": self.duration_seconds,
            "uploader": self.uploader,
            "extractor": self.extractor,
            "webpage_url": self.webpage_url,
            "thumbnail": self.thumbnail,
            "formats": [item.to_json() for item in self.formats],
            "subtitles": [item.to_json() for item in self.subtitles],
        }


@dataclass(frozen=True)
class Progress:
    task_id: str
    status: TaskStatus
    phase: str
    downloaded_bytes: int
    total_bytes: int
    speed: float
    eta_seconds: float | None

    def to_json(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": str(self.status),
            "phase": self.phase,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "speed": self.speed,
            "eta_seconds": self.eta_seconds,
        }


@dataclass
class Task:
    id: str
    kind: TaskKind
    source: str
    status: TaskStatus = TaskStatus.QUEUED
    title: str | None = None
    filename: str | None = None
    out_dir: Path | None = None
    save_path: Path | None = None
    selector: str | None = None
    format_id: str | None = None
    quality_tag: str | None = None
    total_bytes: int = 0
    downloaded_bytes: int = 0
    speed: float = 0.0
    subtitles: list[SubtitleTrack] = field(default_factory=list)
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None

    # 只在内存里存在的运行时字段，不写进任何持久化结构
    gid: str | None = None
    accel_used: bool = False
    accel_fallback_tried: bool = False
    fragmented: bool = False
    audio_only: bool = False

    def touch_started(self) -> None:
        if self.started_at is None:
            self.started_at = time.time()

    def size_bytes(self) -> int | None:
        if self.save_path is None or not self.save_path.is_file():
            return None
        return self.save_path.stat().st_size

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "url": self.source,
            "kind": str(self.kind),
            "status": str(self.status),
            "title": self.title,
            "format_id": self.format_id,
            "quality_tag": self.quality_tag,
            "filename": self.filename,
            "save_path": str(self.save_path) if self.save_path is not None else None,
            "size_bytes": self.size_bytes(),
            "subtitles": [item.to_json() for item in self.subtitles],
            "error": self.error,
        }
