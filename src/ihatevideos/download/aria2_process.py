from __future__ import annotations

import os
import secrets
import socket
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

import aria2p
import requests

from .aria2_args import (
    CRASH_BACKOFF_BASE_SECONDS,
    CRASH_BACKOFF_EXPONENT_CAP,
    CRASH_WINDOW_SECONDS,
    LOG_LINES,
    MAX_CRASHES_PER_WINDOW,
    PORT_ATTEMPTS,
    PROXY_ENV_NAMES,
    READY_POLL_SECONDS,
    READY_TIMEOUT_SECONDS,
    RPC_TIMEOUT_SECONDS,
    SHUTDOWN_GRACE_SECONDS,
    build_start_args,
)
from .errors import EngineStartError

HOST = "http://localhost"
CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
# 就绪探测与 RPC 期间还能遇到的两种异常：客户端异常与连接层异常
CLIENT_ERRORS = (aria2p.ClientException, requests.exceptions.RequestException)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def child_environment() -> dict[str, str]:
    return {
        key: value for key, value in os.environ.items() if key.lower() not in PROXY_ENV_NAMES
    }


class Aria2Process:
    def __init__(
        self,
        *,
        exe: str,
        download_dir: Path | str,
        limit_kbps: int | None = None,
        all_proxy: str = "",
    ) -> None:
        self.exe = exe
        self.download_dir = Path(download_dir)
        self.limit_kbps = limit_kbps
        self.all_proxy = all_proxy
        self.logs: deque[str] = deque(maxlen=LOG_LINES)
        self.api: aria2p.API | None = None
        self.on_restart: Callable[[], None] | None = None
        self.restarts = 0

        self._proc: subprocess.Popen[str] | None = None
        self._readers: list[threading.Thread] = []
        self._stopping = threading.Event()
        self._monitor: threading.Thread | None = None
        self._failure: Exception | None = None
        self._crash_times: list[float] = []
        self._lock = threading.Lock()

    def start(self) -> None:
        self._spawn_with_attempts()
        self._monitor = threading.Thread(target=self._watch, name="aria2-monitor", daemon=True)
        self._monitor.start()

    def raise_if_broken(self) -> None:
        if self._failure is not None:
            raise self._failure

    def tail_logs(self, lines: int = 3) -> str:
        return " | ".join(list(self.logs)[-lines:])

    def _spawn_with_attempts(self) -> None:
        last: Exception | None = None
        for _ in range(PORT_ATTEMPTS):
            self._stopping.clear()
            port = free_port()
            secret = secrets.token_hex(32)
            args = build_start_args(
                exe=self.exe,
                port=port,
                secret=secret,
                download_dir=self.download_dir,
                pid=os.getpid(),
                limit_kbps=self.limit_kbps,
                all_proxy=self.all_proxy,
            )
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=child_environment(),
                creationflags=CREATIONFLAGS,
            )
            client = aria2p.Client(
                host=HOST, port=port, secret=secret, timeout=RPC_TIMEOUT_SECONDS
            )
            try:
                self._wait_ready(proc, client)
            except EngineStartError as exc:
                last = exc
                self._kill(proc)
                continue
            self._proc = proc
            self.api = aria2p.API(client)
            self._start_readers(proc)
            return
        raise EngineStartError(f"aria2c 启动失败：{last}")

    def _wait_ready(self, proc: subprocess.Popen[str], client: aria2p.Client) -> None:
        deadline = time.monotonic() + READY_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise EngineStartError(
                    f"aria2c 启动后立即退出（退出码 {proc.returncode}）"
                )
            try:
                client.get_version()
                return
            except CLIENT_ERRORS:
                time.sleep(READY_POLL_SECONDS)
        raise EngineStartError(f"aria2c 在 {READY_TIMEOUT_SECONDS} 秒内没有就绪")

    def _start_readers(self, proc: subprocess.Popen[str]) -> None:
        for stream_name, stream in (("out", proc.stdout), ("err", proc.stderr)):
            if stream is None:
                continue
            thread = threading.Thread(
                target=self._drain, args=(stream_name, stream), daemon=True
            )
            thread.start()
            self._readers.append(thread)

    def _drain(self, stream_name: str, stream) -> None:
        for line in stream:
            text = line.rstrip()
            if text:
                self.logs.append(f"[{stream_name}] {text}")

    def _kill(self, proc: subprocess.Popen[str]) -> None:
        proc.kill()
        proc.wait(timeout=SHUTDOWN_GRACE_SECONDS)

    def _watch(self) -> None:
        while True:
            proc = self._proc
            if proc is None:
                return
            proc.wait()
            if self._stopping.is_set():
                return
            now = time.monotonic()
            with self._lock:
                self._crash_times = [
                    item for item in self._crash_times if now - item < CRASH_WINDOW_SECONDS
                ]
                self._crash_times.append(now)
                count = len(self._crash_times)
                if count > MAX_CRASHES_PER_WINDOW:
                    self._failure = EngineStartError(
                        f"aria2c 在 {int(CRASH_WINDOW_SECONDS)} 秒内崩溃 {count} 次，停止重启。"
                        f"引擎输出：{self.tail_logs()}"
                    )
                    return
                exponent = min(count, CRASH_BACKOFF_EXPONENT_CAP) - 1
                delay = CRASH_BACKOFF_BASE_SECONDS * (2**exponent)
            self.logs.append(f"[monitor] aria2c 退出（退出码 {proc.returncode}），{delay:.1f} 秒后重启")
            time.sleep(delay)
            try:
                self._spawn_with_attempts()
            except EngineStartError as exc:
                self._failure = exc
                return
            self.restarts += 1
            if self.on_restart is not None:
                self.on_restart()

    def stop(self) -> None:
        self._stopping.set()
        api = self.api
        if api is not None:
            self._shutdown_rpc(api, force=False)
            if not self._wait_exit(SHUTDOWN_GRACE_SECONDS / 2):
                self._shutdown_rpc(api, force=True)
        if not self._wait_exit(SHUTDOWN_GRACE_SECONDS / 2):
            proc = self._proc
            if proc is not None and proc.poll() is None:
                self._kill(proc)
        if self._monitor is not None:
            self._monitor.join(timeout=SHUTDOWN_GRACE_SECONDS)
        self.api = None

    def _shutdown_rpc(self, api: aria2p.API, *, force: bool) -> None:
        # 引擎可能已经自己退出，这里的关闭调用是尽力而为
        try:
            if force:
                api.client.force_shutdown()
            else:
                api.client.shutdown()
        except CLIENT_ERRORS:
            pass

    def _wait_exit(self, timeout: float) -> bool:
        proc = self._proc
        if proc is None:
            return True
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return True
            time.sleep(0.05)
        return proc.poll() is not None
