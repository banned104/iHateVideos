import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

DEFAULT_TIMEOUT_SECONDS = 600
FFPROBE_TIMEOUT_SECONDS = 60
_STDERR_TAIL_LINES = 10


class MediaToolNotFound(RuntimeError):
    pass


class FfmpegError(RuntimeError):
    pass


def _executable_name(base: str) -> str:
    return f"{base}.exe" if os.name == "nt" else base


def _resolve_tool(env_names: Sequence[str], base: str) -> str:
    # 环境变量优先，其次 PATH；两处都找不到就地报错
    for name in env_names:
        raw = os.environ.get(name, "").strip()
        if not raw:
            continue
        candidate = Path(raw).expanduser()
        if candidate.is_dir():
            candidate = candidate / _executable_name(base)
        if not candidate.is_file():
            raise MediaToolNotFound(f"{name} 指向的位置没有可执行文件：{candidate}")
        return str(candidate)
    found = shutil.which(base)
    if not found:
        raise MediaToolNotFound(
            f"找不到 {base}，请安装 FFmpeg 并加入 PATH，或用 FFMPEG_PATH / FFPROBE_PATH 指定位置"
        )
    return found


def resolve_ffmpeg() -> str:
    return _resolve_tool(("FFMPEG_PATH", "IHATEVIDEOS_FFMPEG"), "ffmpeg")


def resolve_ffprobe() -> str:
    return _resolve_tool(("FFPROBE_PATH", "IHATEVIDEOS_FFPROBE"), "ffprobe")


def base_arguments() -> list[str]:
    # -nostdin 防止 ffmpeg 抢占终端输入
    return ["-hide_banner", "-loglevel", "error", "-nostdin"]


def _failure_message(command: Sequence[str], completed: subprocess.CompletedProcess) -> str:
    tail = "\n".join(
        line for line in (completed.stderr or "").splitlines()[-_STDERR_TAIL_LINES:] if line.strip()
    )
    text = f"命令失败（退出码 {completed.returncode}）：{' '.join(command)}"
    return f"{text}\n{tail}" if tail else text


def run_tool(
    exe: str,
    args: Sequence[str],
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    cwd: Path | str | None = None,
) -> subprocess.CompletedProcess:
    command = [exe, *args]
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise MediaToolNotFound(f"无法启动 {exe}：{exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise FfmpegError(f"命令超过 {timeout} 秒没有结束：{' '.join(command)}") from exc
    if completed.returncode != 0:
        raise FfmpegError(_failure_message(command, completed))
    return completed


def run_ffmpeg(
    args: Sequence[str], *, timeout: int = DEFAULT_TIMEOUT_SECONDS, cwd: Path | str | None = None
) -> subprocess.CompletedProcess:
    return run_tool(resolve_ffmpeg(), args, timeout=timeout, cwd=cwd)


def run_ffprobe_json(
    args: Sequence[str], *, timeout: int = FFPROBE_TIMEOUT_SECONDS
) -> dict[str, Any]:
    completed = run_tool(resolve_ffprobe(), args, timeout=timeout)
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise FfmpegError(f"ffprobe 的输出不是合法 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise FfmpegError("ffprobe 输出的 JSON 顶层不是对象")
    return payload
