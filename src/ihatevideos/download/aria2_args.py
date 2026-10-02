from __future__ import annotations

from pathlib import Path

# 照 DownLord engine/aria2Args.ts、port.ts、secret.ts、downloadEngine.ts 的取值
MAX_CONCURRENT_DOWNLOADS = 10
SPLIT = 16
MIN_SPLIT_SIZE = "1M"
MAX_CONNECTION_PER_SERVER = 16
CONNECT_TIMEOUT_SECONDS = 10
AUTO_SAVE_INTERVAL_SECONDS = 1
LOG_LINES = 100

READY_POLL_SECONDS = 0.2
READY_TIMEOUT_SECONDS = 5.0
PORT_ATTEMPTS = 3
SHUTDOWN_GRACE_SECONDS = 10.0
RPC_TIMEOUT_SECONDS = 10.0

POLL_INTERVAL_SECONDS = 1.0
CRASH_WINDOW_SECONDS = 60.0
MAX_CRASHES_PER_WINDOW = 5
CRASH_BACKOFF_BASE_SECONDS = 0.5
CRASH_BACKOFF_EXPONENT_CAP = 10

DRY_RUN_TIMEOUT_SECONDS = 5.0
DRY_RUN_POLL_SECONDS = 0.1

PROXY_ENV_NAMES = frozenset({"http_proxy", "https_proxy", "all_proxy", "ftp_proxy", "no_proxy"})

# 照 DownLord engine/downloadEngine.ts 的 PROGRESS_KEYS
PROGRESS_KEYS = (
    "gid",
    "status",
    "totalLength",
    "completedLength",
    "downloadSpeed",
    "connections",
    "errorCode",
    "errorMessage",
    "files",
)

# 照 DownLord engine/downloadEngine.ts 的 resolveHttpFilename
DRY_RUN_OPTIONS = {
    "dry-run": "true",
    "continue": "false",
    "auto-file-renaming": "true",
    "allow-overwrite": "false",
    "connect-timeout": "3",
    "timeout": "5",
    "max-tries": "1",
    "retry-wait": "0",
}

# aria2 状态到本模块七个状态的映射
ARIA2_ACTIVE_STATUSES = frozenset({"active", "waiting"})
ARIA2_PAUSED_STATUSES = frozenset({"paused"})
ARIA2_DONE_STATUSES = frozenset({"complete"})
ARIA2_FAILED_STATUSES = frozenset({"error", "removed"})


def format_limit(limit_kbps: int | None) -> str:
    return f"{limit_kbps}K" if limit_kbps and limit_kbps > 0 else "0"


def build_start_args(
    *,
    exe: str,
    port: int,
    secret: str,
    download_dir: Path | str,
    pid: int,
    limit_kbps: int | None = None,
    all_proxy: str = "",
) -> list[str]:
    args = [
        exe,
        "--enable-rpc",
        f"--rpc-listen-port={port}",
        "--rpc-listen-all=false",
        f"--rpc-secret={secret}",
        "--continue=true",
        f"--max-connection-per-server={MAX_CONNECTION_PER_SERVER}",
        f"--split={SPLIT}",
        f"--min-split-size={MIN_SPLIT_SIZE}",
        "--file-allocation=none",
        f"--connect-timeout={CONNECT_TIMEOUT_SECONDS}",
        f"--dir={download_dir}",
        f"--stop-with-process={pid}",
        f"--auto-save-interval={AUTO_SAVE_INTERVAL_SECONDS}",
        f"--max-concurrent-downloads={MAX_CONCURRENT_DOWNLOADS}",
        f"--all-proxy={all_proxy}",
    ]
    if limit_kbps and limit_kbps > 0:
        args.append(f"--max-download-limit={limit_kbps}K")
    return args


def build_task_options(
    *, save_dir: Path | str, filename: str | None = None, limit_kbps: int | None = None
) -> dict[str, str]:
    options = {"dir": str(save_dir), "max-download-limit": format_limit(limit_kbps)}
    if filename:
        options["out"] = filename
    return options
