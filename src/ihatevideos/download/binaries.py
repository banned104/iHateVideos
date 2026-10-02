from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import aria2c
import imageio_ffmpeg

from ihatevideos.agent.config import find_project_root

from .errors import EngineStartError

PROBE_TIMEOUT_SECONDS = 60
BIN_SUBDIR = ("temp", "bin")
SOURCES = {
    "aria2c": "package:aria2",
    "ffmpeg": "package:imageio-ffmpeg",
    "ffprobe": None,
    "yt_dlp": "module:yt-dlp",
}


def executable_name(base: str) -> str:
    return f"{base}.exe" if os.name == "nt" else base


ARIA2C_NAME = executable_name("aria2c")
FFMPEG_NAME = executable_name("ffmpeg")
FFPROBE_NAME = executable_name("ffprobe")


@dataclass(frozen=True)
class Engine:
    name: str
    path: str | None
    version: str | None
    source: str

    @property
    def available(self) -> bool:
        return self.path is not None

    def to_json(self) -> dict:
        return {
            "path": self.path,
            "version": self.version,
            "source": self.source,
            "available": self.available,
        }


@dataclass(frozen=True)
class Engines:
    aria2c: Engine
    ffmpeg: Engine
    ffprobe: Engine
    yt_dlp: Engine

    @property
    def ready(self) -> bool:
        return self.aria2c.available and self.ffmpeg.available and self.yt_dlp.available

    def missing(self) -> list[str]:
        return [item.name for item in (self.aria2c, self.ffmpeg, self.yt_dlp) if not item.available]

    def to_json(self) -> dict:
        return {
            "aria2c": self.aria2c.to_json(),
            "ffmpeg": self.ffmpeg.to_json(),
            "ffprobe": self.ffprobe.to_json(),
            "yt_dlp": self.yt_dlp.to_json(),
            "ready": self.ready,
        }


def bin_dir(root: Path | None = None) -> Path:
    return (root or find_project_root()) / Path(*BIN_SUBDIR)


def ffmpeg_location(engine: Engine) -> str:
    """yt-dlp 的 --ffmpeg-location：temp/bin 时给目录（ffprobe 在同目录），否则给可执行文件本身。"""
    if engine.path is None:
        raise EngineStartError("缺少 ffmpeg，无法向 yt-dlp 传递 --ffmpeg-location")
    if Path(engine.path).parent == bin_dir():
        return str(Path(engine.path).parent)
    return engine.path


def _pick_from_bin(name: str, project_bin: Path) -> str | None:
    candidate = project_bin / name
    return str(candidate) if candidate.is_file() else None


def _fallback_path(base: str) -> str | None:
    if base == "aria2c":
        candidate = Path(aria2c.ARIA2C)
        return str(candidate) if candidate.is_file() else None
    if base == "ffmpeg":
        return imageio_ffmpeg.get_ffmpeg_exe()
    return None


def _probe_first_line_version(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=PROBE_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()
        raise EngineStartError(
            f"{command[0]} 无法启动（退出码 {completed.returncode}）：{tail[-1] if tail else ''}"
        )
    return completed.stdout or ""


def _version_of(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) >= 3 and parts[1] == "version":
            return parts[2]
        return stripped
    raise EngineStartError("版本探测没有任何输出")


def _probe_executable(path: str) -> str:
    return _version_of(_probe_first_line_version([path, "--version"]))


def _probe_ffmpeg_tool(path: str) -> str:
    return _version_of(_probe_first_line_version([path, "-version"]))


def _probe_yt_dlp() -> str:
    completed = subprocess.run(
        [sys.executable, "-m", "yt_dlp", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=PROBE_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        raise EngineStartError(f"python -m yt_dlp 无法启动（退出码 {completed.returncode}）")
    return (completed.stdout or "").strip()


def resolve_engines(*, root: Path | None = None, probe: bool = True) -> Engines:
    project_bin = bin_dir(root)

    aria2c_path = _pick_from_bin(ARIA2C_NAME, project_bin) or _fallback_path("aria2c")
    ffmpeg_path = _pick_from_bin(FFMPEG_NAME, project_bin) or _fallback_path("ffmpeg")
    ffprobe_path = _pick_from_bin(FFPROBE_NAME, project_bin)

    def source_of(path: str | None, base: str) -> str:
        if path is None:
            return "missing"
        return "temp/bin" if Path(path).parent == project_bin else str(SOURCES[base])

    aria2c_engine = Engine(
        name="aria2c",
        path=aria2c_path,
        version=_probe_executable(aria2c_path) if probe and aria2c_path else None,
        source=source_of(aria2c_path, "aria2c"),
    )
    ffmpeg_engine = Engine(
        name="ffmpeg",
        path=ffmpeg_path,
        version=_probe_ffmpeg_tool(ffmpeg_path) if probe and ffmpeg_path else None,
        source=source_of(ffmpeg_path, "ffmpeg"),
    )
    ffprobe_engine = Engine(
        name="ffprobe",
        path=ffprobe_path,
        version=_probe_ffmpeg_tool(ffprobe_path) if probe and ffprobe_path else None,
        source=source_of(ffprobe_path, "ffprobe"),
    )
    yt_dlp_engine = Engine(
        name="yt_dlp",
        path=sys.executable,
        version=_probe_yt_dlp() if probe else None,
        source=str(SOURCES["yt_dlp"]),
    )
    return Engines(
        aria2c=aria2c_engine,
        ffmpeg=ffmpeg_engine,
        ffprobe=ffprobe_engine,
        yt_dlp=yt_dlp_engine,
    )
