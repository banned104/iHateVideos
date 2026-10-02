from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from collections import deque
from typing import Callable, Sequence

from .aria2_args import LOG_LINES, PROXY_ENV_NAMES
from .errors import YtdlpError

CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def child_environment() -> dict[str, str]:
    """照 DownLord video/ytdlpEnv.ts 与 childEnv.ts：去掉代理变量，固定输出编码。"""
    env = {
        key: value for key, value in os.environ.items() if key.lower() not in PROXY_ENV_NAMES
    }
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def kill_process_tree(pid: int) -> None:
    """照 DownLord video/ytdlpProcess.ts:152-167：先终止整棵树，再终止父进程。"""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/pid", str(pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATIONFLAGS,
        )
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except ProcessLookupError:
        return


def _command(args: Sequence[str]) -> list[str]:
    return [sys.executable, "-m", "yt_dlp", *args]


class YtdlpProcess:
    def __init__(self, *, log_lines: int = LOG_LINES) -> None:
        self.logs: deque[str] = deque(maxlen=log_lines)
        self._proc: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._killed = False

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc is not None else None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def killed(self) -> bool:
        return self._killed

    def tail_logs(self, lines: int = 5) -> str:
        return " | ".join(list(self.logs)[-lines:])

    def run_capture(self, args: Sequence[str], *, timeout: float) -> str:
        """一次性执行并取回完整输出，用于解析阶段的信息树。"""
        command = _command(args)
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=timeout,
                env=child_environment(),
                creationflags=CREATIONFLAGS,
            )
        except subprocess.TimeoutExpired as exc:
            raise YtdlpError(f"yt-dlp 超过 {timeout:.0f} 秒没有结束") from exc
        # 解析成功时 stderr 里带着「哪些格式拿不到」这类提示，保留下来供调用方查看
        if completed.stderr:
            self._remember(completed.stderr)
        if completed.returncode != 0:
            self._remember(completed.stdout)
            raise YtdlpError(
                f"yt-dlp 退出码 {completed.returncode}：{self.tail_logs(3)}"
            )
        return completed.stdout or ""

    def start(self, args: Sequence[str], *, on_line: Callable[[str], None]) -> None:
        command = _command(args)
        self._killed = False
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=child_environment(),
            creationflags=CREATIONFLAGS,
        )
        self._proc = proc
        self._reader = threading.Thread(
            target=self._drain, args=(proc, on_line), name="ytdlp-reader", daemon=True
        )
        self._reader.start()

    def _drain(self, proc: subprocess.Popen[str], on_line: Callable[[str], None]) -> None:
        stream = proc.stdout
        if stream is None:
            return
        for raw in stream:
            text = raw.rstrip("\r\n")
            self.logs.append(text)
            on_line(text)

    def _remember(self, *streams: str | None) -> None:
        for stream in streams:
            for line in (stream or "").splitlines():
                if line.strip():
                    self.logs.append(line.rstrip())

    def wait(self, timeout: float | None = None) -> int | None:
        proc = self._proc
        if proc is None:
            raise YtdlpError("yt-dlp 进程还没有启动")
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def terminate(self) -> int:
        """终止进程树，返回退出码。"""
        proc = self._proc
        if proc is None:
            raise YtdlpError("yt-dlp 进程还没有启动")
        self._killed = True
        kill_process_tree(proc.pid)
        proc.kill()
        code = proc.wait(timeout=30)
        if self._reader is not None:
            self._reader.join(timeout=10)
        return code
