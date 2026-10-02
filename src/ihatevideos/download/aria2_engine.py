from __future__ import annotations

import time
from pathlib import Path

import aria2p

from .aria2_args import (
    ARIA2_ACTIVE_STATUSES,
    ARIA2_DONE_STATUSES,
    ARIA2_FAILED_STATUSES,
    ARIA2_PAUSED_STATUSES,
    DRY_RUN_OPTIONS,
    DRY_RUN_POLL_SECONDS,
    DRY_RUN_TIMEOUT_SECONDS,
    PROGRESS_KEYS,
    build_task_options,
    format_limit,
)
from .aria2_process import CLIENT_ERRORS, Aria2Process
from .errors import DownloadError, RpcCallError, map_aria2_error
from .models import TaskStatus

GID_NOT_FOUND_CODE = 1


def map_status(raw_status: str) -> TaskStatus:
    if raw_status in ARIA2_ACTIVE_STATUSES:
        return TaskStatus.DOWNLOADING
    if raw_status in ARIA2_PAUSED_STATUSES:
        return TaskStatus.PAUSED
    if raw_status in ARIA2_DONE_STATUSES:
        return TaskStatus.COMPLETED
    if raw_status in ARIA2_FAILED_STATUSES:
        return TaskStatus.ERROR
    raise DownloadError(f"aria2 返回了未知状态：{raw_status}")


def error_message_of(status: dict) -> str:
    return map_aria2_error(
        str(status.get("errorCode") or ""), str(status.get("errorMessage") or "")
    )


def output_path_of(status: dict) -> Path | None:
    files = status.get("files") or []
    if not files:
        return None
    path = files[0].get("path")
    return Path(str(path)) if path else None


class Aria2Engine:
    def __init__(self, process: Aria2Process) -> None:
        self.process = process

    @property
    def api(self) -> aria2p.API:
        api = self.process.api
        if api is None:
            raise RpcCallError("aria2 引擎没有运行")
        return api

    def submit(
        self,
        url: str,
        *,
        save_dir: Path | str,
        filename: str | None = None,
        limit_kbps: int | None = None,
    ) -> str:
        options = build_task_options(
            save_dir=save_dir, filename=filename, limit_kbps=limit_kbps
        )
        try:
            return str(self.api.client.add_uri([url], options=options))
        except CLIENT_ERRORS as exc:
            raise RpcCallError(f"添加下载任务失败：{exc}") from exc

    def probe_filename(self, url: str, *, save_dir: Path | str) -> str | None:
        """照 DownLord engine/downloadEngine.ts 的 resolveHttpFilename：试运行取回真实文件名。"""
        options = dict(DRY_RUN_OPTIONS)
        options["dir"] = str(save_dir)
        try:
            gid = str(self.api.client.add_uri([url], options=options))
        except CLIENT_ERRORS as exc:
            raise RpcCallError(f"文件名预探失败：{exc}") from exc
        try:
            deadline = time.monotonic() + DRY_RUN_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                status = self.status(gid)
                if status is None:
                    return None
                raw = str(status.get("status") or "")
                if raw in ARIA2_DONE_STATUSES:
                    path = output_path_of(status)
                    return path.name if path is not None else None
                if raw in ARIA2_FAILED_STATUSES:
                    return None
                time.sleep(DRY_RUN_POLL_SECONDS)
            return None
        finally:
            self._forget(gid)

    def active(self) -> list[dict]:
        try:
            return list(self.api.client.tell_active(keys=list(PROGRESS_KEYS)))
        except CLIENT_ERRORS as exc:
            raise RpcCallError(f"读取下载进度失败：{exc}") from exc

    def status(self, gid: str) -> dict | None:
        try:
            return dict(self.api.client.tell_status(gid, keys=list(PROGRESS_KEYS)))
        except aria2p.ClientException as exc:
            if exc.code == GID_NOT_FOUND_CODE:
                return None
            raise RpcCallError(str(exc.message)) from exc
        except CLIENT_ERRORS as exc:
            raise RpcCallError(f"读取任务状态失败：{exc}") from exc

    def pause(self, gid: str) -> None:
        self._call("暂停", lambda: self.api.client.force_pause(gid))

    def resume(self, gid: str) -> None:
        self._call("继续", lambda: self.api.client.unpause(gid))

    def remove(self, gid: str) -> None:
        self._call("移除", lambda: self.api.client.force_remove(gid))
        self._forget(gid)

    def set_global_limit(self, limit_kbps: int | None) -> None:
        value = format_limit(limit_kbps)
        self._call(
            "设置全局限速", lambda: self.api.client.change_global_option({"max-download-limit": value})
        )

    def _call(self, action: str, func) -> None:
        try:
            func()
        except CLIENT_ERRORS as exc:
            raise RpcCallError(f"{action}失败：{exc}") from exc

    def _forget(self, gid: str) -> None:
        # 去掉任务与结果记录是清理动作，引擎已经丢掉它时不用报错
        for func in (self.api.client.force_remove, self.api.client.remove_download_result):
            try:
                func(gid)
            except CLIENT_ERRORS:
                continue
