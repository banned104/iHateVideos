from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from .aria2_args import POLL_INTERVAL_SECONDS
from .aria2_engine import Aria2Engine, error_message_of, map_status, output_path_of
from .aria2_process import Aria2Process
from .binaries import Engines, ffmpeg_location
from .errors import ENGINE_MESSAGES, DownloadError, EngineNotFound, readable
from .filenames import name_from_url, sanitize_basename
from .models import ALLOWED_TRANSITIONS, TERMINAL_STATUSES, Progress, Task, TaskKind, TaskStatus
from .ytdlp_engine import (
    VideoRun,
    YtdlpEngine,
    clean_partials,
    plan_download,
    resolve_video,
)


@dataclass
class DownloadRequest:
    url: str
    kind: TaskKind = TaskKind.DIRECT
    out_dir: Path | None = None
    filename: str | None = None
    limit_kbps: int | None = None
    audio_only: bool = False
    format_id: str | None = None
    height: int | None = None
    subtitles: tuple[str, ...] = ()
    sub_format: str = "srt"
    write_auto_subs: bool = False
    accelerate: bool = True
    cookie_file: str | None = None
    cookie_from_browser: str | None = None


class DownloadService:
    def __init__(
        self,
        *,
        engines: Engines,
        download_dir: Path | str,
        jobs: int = 2,
        global_limit_kbps: int | None = None,
        proxy: str = "",
        on_progress: Callable[[Progress], None] | None = None,
        on_event: Callable[[str], None] | None = None,
    ) -> None:
        self.engines = engines
        self.download_dir = Path(download_dir)
        self.jobs = max(1, jobs)
        self.global_limit_kbps = global_limit_kbps
        self.proxy = proxy
        self.on_progress = on_progress or (lambda item: None)
        self.on_event = on_event or (lambda text: None)

        self.tasks: list[Task] = []
        self._pending: deque[Task] = deque()
        self._started: set[str] = set()
        self._by_gid: dict[str, Task] = {}
        self._last_frame: dict[str, tuple] = {}
        self._process: Aria2Process | None = None
        self._aria2: Aria2Engine | None = None
        self._stopping = False
        self._video_threads: dict[str, threading.Thread] = {}
        self._video_runs: dict[str, VideoRun] = {}
        self._ytdlp: YtdlpEngine | None = None
        self._requests: dict[str, DownloadRequest] = {}
        self._counter = 0

    def submit(self, request: DownloadRequest) -> Task:
        self._counter += 1
        task = Task(
            id=f"t{self._counter}",
            kind=request.kind,
            source=request.url,
            out_dir=Path(request.out_dir) if request.out_dir is not None else self.download_dir,
            filename=request.filename,
            audio_only=request.audio_only,
        )
        self._requests[task.id] = request
        self.tasks.append(task)
        self._pending.append(task)
        return task

    def task(self, task_id: str) -> Task:
        for item in self.tasks:
            if item.id == task_id:
                return item
        raise DownloadError(f"没有这个任务：{task_id}")

    def _transition(self, task: Task, new_status: TaskStatus) -> None:
        if new_status is task.status:
            return
        if new_status not in ALLOWED_TRANSITIONS[task.status]:
            raise DownloadError(f"非法状态流转：{task.status} -> {new_status}（任务 {task.id}）")
        task.status = new_status
        if new_status in TERMINAL_STATUSES:
            task.completed_at = time.time()

    def _fail(self, task: Task, message: str) -> None:
        if task.status in TERMINAL_STATUSES:
            return
        task.error = message
        self._transition(task, TaskStatus.ERROR)

    def stop(self) -> None:
        self._stopping = True
        if self._aria2 is not None:
            for task in self.tasks:
                if (
                    task.kind is TaskKind.DIRECT
                    and task.gid
                    and task.status is TaskStatus.DOWNLOADING
                ):
                    self._aria2.pause(task.gid)
                    self._transition(task, TaskStatus.PAUSED)
        for run in list(self._video_runs.values()):
            if run.process.running:
                run.process.terminate()

    def close(self) -> None:
        for run in list(self._video_runs.values()):
            if run.process.running:
                run.process.terminate()
        self._video_runs.clear()
        if self._process is not None:
            self._process.stop()
            self._process = None
            self._aria2 = None

    def run(self) -> list[Task]:
        while True:
            self._fill()
            self._poll_direct()
            self._poll_video()
            if not self._has_unfinished():
                break
            time.sleep(POLL_INTERVAL_SECONDS)
        self.close()
        return list(self.tasks)

    def _has_unfinished(self) -> bool:
        busy = {
            TaskStatus.RESOLVING,
            TaskStatus.DOWNLOADING,
            TaskStatus.PROCESSING,
        }
        if self._stopping:
            return any(task.status in busy for task in self.tasks)
        return any(task.status not in TERMINAL_STATUSES for task in self.tasks)

    def _active_count(self) -> int:
        return sum(
            1
            for task in self.tasks
            if task.id in self._started and task.status not in TERMINAL_STATUSES
        )

    def _fill(self) -> None:
        if self._stopping:
            return
        while self._pending and self._active_count() < self.jobs:
            task = self._pending.popleft()
            self._started.add(task.id)
            self._start(task)

    def _start(self, task: Task) -> None:
        if task.kind is TaskKind.DIRECT:
            self._start_direct(task)
        else:
            self._start_video(task)

    def _aria2_engine(self) -> Aria2Engine:
        if self._aria2 is not None:
            return self._aria2
        exe = self.engines.aria2c.path
        if exe is None:
            raise EngineNotFound("缺少 aria2c，检查依赖安装或运行 setup-binaries")
        process = Aria2Process(
            exe=exe,
            download_dir=self.download_dir,
            limit_kbps=self.global_limit_kbps,
            all_proxy=self.proxy,
        )
        process.on_restart = self._resubmit_running
        process.start()
        self._process = process
        self._aria2 = Aria2Engine(process)
        return self._aria2

    def _video_engine(self) -> YtdlpEngine:
        if self._ytdlp is None:
            self._ytdlp = YtdlpEngine(
                ffmpeg_location=ffmpeg_location(self.engines.ffmpeg),
                proxy=self.proxy,
                aria2c_path=self.engines.aria2c.path,
            )
        return self._ytdlp

    def _resubmit_running(self) -> None:
        engine = self._aria2
        if engine is None:
            return
        self._by_gid.clear()
        for task in self.tasks:
            if task.kind is not TaskKind.DIRECT or task.status is not TaskStatus.DOWNLOADING:
                continue
            save_dir = task.out_dir or self.download_dir
            task.gid = engine.submit(
                task.source,
                save_dir=save_dir,
                filename=task.filename,
                limit_kbps=self._limit_of(task),
            )
            self._by_gid[task.gid] = task

    def _limit_of(self, task: Task) -> int | None:
        request = self._requests.get(task.id)
        return request.limit_kbps if request is not None else None

    def _start_direct(self, task: Task) -> None:
        engine = self._aria2_engine()
        save_dir = task.out_dir or self.download_dir
        save_dir.mkdir(parents=True, exist_ok=True)
        task.out_dir = save_dir
        if task.filename is None:
            probed = engine.probe_filename(task.source, save_dir=save_dir)
            task.filename = probed or name_from_url(task.source)
        task.save_path = save_dir / task.filename
        task.touch_started()
        task.gid = engine.submit(
            task.source,
            save_dir=save_dir,
            filename=task.filename,
            limit_kbps=self._limit_of(task),
        )
        self._by_gid[task.gid] = task
        self._transition(task, TaskStatus.DOWNLOADING)

    def _start_video(self, task: Task) -> None:
        worker = threading.Thread(
            target=self._resolve_and_start_video,
            args=(task,),
            name=f"video-{task.id}",
            daemon=True,
        )
        self._video_threads[task.id] = worker
        worker.start()

    def _resolve_and_start_video(self, task: Task) -> None:
        request = self._requests[task.id]
        try:
            self._transition(task, TaskStatus.RESOLVING)
            info = resolve_video(
                url=task.source,
                proxy=self.proxy,
                cookie_file=request.cookie_file,
                cookie_from_browser=request.cookie_from_browser,
            )
            plan = plan_download(
                info,
                audio_only=request.audio_only,
                format_id=request.format_id,
                height_cap=request.height,
            )
            if request.filename:
                base = sanitize_basename(request.filename)
                plan = replace(
                    plan, output_base=base, expected_filename=f"{base}.{plan.ext}"
                )
        except DownloadError as exc:
            self._fail(task, str(exc))
            return
        except ValueError as exc:
            self._fail(task, f"bad input: {exc}")
            return

        task.title = info.title
        task.format_id = plan.format_id
        task.quality_tag = plan.quality_tag
        task.filename = plan.expected_filename
        task.fragmented = plan.fragmented
        task.subtitles = list(info.subtitles)
        out_dir = task.out_dir or self.download_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        task.out_dir = out_dir
        task.touch_started()
        accel = request.accelerate and not plan.fragmented
        run = self._video_engine().start(
            task_id=task.id,
            url=task.source,
            out_dir=out_dir,
            plan=plan,
            audio_only=request.audio_only,
            subtitles=request.subtitles,
            sub_format=request.sub_format,
            write_auto_subs=request.write_auto_subs,
            limit_kbps=request.limit_kbps,
            accel_used=accel,
            fallback_tried=False,
            cookie_file=request.cookie_file,
            cookie_from_browser=request.cookie_from_browser,
        )
        task.accel_used = run.accel_used
        self._video_runs[task.id] = run
        self._transition(task, TaskStatus.DOWNLOADING)

    def _poll_direct(self) -> None:
        engine = self._aria2
        if engine is None:
            return
        if self._process is not None:
            self._process.raise_if_broken()
        seen: set[str] = set()
        for raw in engine.active():
            gid = str(raw.get("gid"))
            seen.add(gid)
            task = self._by_gid.get(gid)
            if task is not None:
                self._apply_active(task, raw)
        for gid, task in list(self._by_gid.items()):
            if gid in seen or task.status in TERMINAL_STATUSES:
                continue
            self._apply_status(task, engine.status(gid))

    def _poll_video(self) -> None:
        for task_id, run in list(self._video_runs.items()):
            task = self.task(task_id)
            if task.status in TERMINAL_STATUSES:
                self._video_runs.pop(task_id, None)
                continue
            if run.stage == "processing" and task.status is TaskStatus.DOWNLOADING:
                self._transition(task, TaskStatus.PROCESSING)
            self._emit_video_progress(task, run)
            if run.process.running:
                continue
            code = run.process.wait(0)
            self._finish_video(task, run, code if code is not None else -1)

    def _emit_video_progress(self, task: Task, run: VideoRun) -> None:
        if run.total_bytes <= 0:
            return
        phase = "processing" if run.stage == "processing" else "download"
        frame = (phase, run.downloaded_bytes, round(run.speed, 1))
        if self._last_frame.get(task.id) == frame:
            return
        self._last_frame[task.id] = frame
        task.downloaded_bytes = run.downloaded_bytes
        task.total_bytes = run.total_bytes
        task.speed = run.speed
        self.on_progress(
            Progress(
                task_id=task.id,
                status=task.status,
                phase=phase,
                downloaded_bytes=run.downloaded_bytes,
                total_bytes=run.total_bytes,
                speed=run.speed,
                eta_seconds=(
                    (run.total_bytes - run.downloaded_bytes) / run.speed if run.speed > 0 else None
                ),
            )
        )

    def _finish_video(self, task: Task, run: VideoRun, code: int) -> None:
        if run.process.killed:
            self._video_runs.pop(task.id, None)
            if task.status in (TaskStatus.DOWNLOADING, TaskStatus.PROCESSING):
                self._transition(task, TaskStatus.PAUSED)
            return
        if code == 0:
            self._video_runs.pop(task.id, None)
            if run.destination is None:
                self._fail(task, "yt-dlp 正常结束但没有给出最终路径")
                return
            task.save_path = run.destination
            task.filename = run.destination.name
            if run.selected_formats:
                # 用 yt-dlp 实际选中的格式覆盖预告值，避免记录与实际不一致
                task.format_id = run.selected_formats
            task.speed = 0.0
            for note in run.notes:
                self.on_event(note)
            self._transition(task, TaskStatus.COMPLETED)
            return
        if run.accel_used and not run.fallback_tried:
            # 第二层：改用 yt-dlp 自带下载器重跑一次，期间任务保持下载中
            self._restart_video_without_accel(task, run)
            return
        self._video_runs.pop(task.id, None)
        self._fail(task, f"yt-dlp 退出码 {code}：{run.process.tail_logs(3)}")

    def _restart_video_without_accel(self, task: Task, run: VideoRun) -> None:
        request = self._requests[task.id]
        self.on_event(f"[monitor] {task.id} 经 aria2c 下载失败，改用自带下载器重跑一次")
        clean_partials(run.out_dir, run.plan.output_base)
        new_run = self._video_engine().start(
            task_id=task.id,
            url=task.source,
            out_dir=run.out_dir,
            plan=run.plan,
            audio_only=request.audio_only,
            subtitles=request.subtitles,
            sub_format=request.sub_format,
            write_auto_subs=request.write_auto_subs,
            limit_kbps=request.limit_kbps,
            accel_used=False,
            fallback_tried=True,
            cookie_file=request.cookie_file,
            cookie_from_browser=request.cookie_from_browser,
        )
        self._video_runs[task.id] = new_run
        task.accel_fallback_tried = True

    def _apply_active(self, task: Task, raw: dict) -> None:
        new_status = map_status(str(raw.get("status") or ""))
        if new_status is not task.status:
            self._transition(task, new_status)
        total = int(raw.get("totalLength") or 0)
        if total <= 0:
            # 刚添加时总量还是 0，跳过这一帧，避免上报一次 0% 的假进度
            return
        path = output_path_of(raw)
        if path is not None:
            task.save_path = path
        downloaded = int(raw.get("completedLength") or 0)
        speed = float(raw.get("downloadSpeed") or 0)
        frame = (str(new_status), downloaded, speed, str(task.save_path))
        if self._last_frame.get(task.id) == frame:
            return
        self._last_frame[task.id] = frame
        task.total_bytes = total
        task.downloaded_bytes = downloaded
        task.speed = speed
        self.on_progress(
            Progress(
                task_id=task.id,
                status=task.status,
                phase="download",
                downloaded_bytes=downloaded,
                total_bytes=total,
                speed=speed,
                eta_seconds=(total - downloaded) / speed if speed > 0 else None,
            )
        )

    def _apply_status(self, task: Task, status: dict | None) -> None:
        if status is None:
            task.error = readable(ENGINE_MESSAGES["RPC_TASK_NOT_FOUND"])
            self._transition(task, TaskStatus.ERROR)
            return
        new_status = map_status(str(status.get("status") or ""))
        if new_status is TaskStatus.COMPLETED:
            path = output_path_of(status)
            if path is not None:
                task.save_path = path
                task.filename = path.name
            task.total_bytes = int(status.get("totalLength") or task.total_bytes)
            task.downloaded_bytes = int(status.get("completedLength") or task.downloaded_bytes)
            task.speed = 0.0
            self._transition(task, TaskStatus.COMPLETED)
            return
        if new_status is TaskStatus.ERROR:
            task.error = error_message_of(status)
            self._transition(task, TaskStatus.ERROR)
            return
        if new_status is not task.status:
            self._transition(task, new_status)
        completed = int(status.get("completedLength") or 0)
        if completed > task.downloaded_bytes:
            task.downloaded_bytes = completed
