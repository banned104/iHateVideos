from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .ffmpeg import DEFAULT_TIMEOUT_SECONDS, FfmpegError, base_arguments, run_ffmpeg
from .paths import ensure_dir, frame_path, frames_dir, parameter_signature
from .timestamps import format_timestamp

SUPPORTED_FORMATS = ("jpg", "png")
DEFAULT_MAX_FRAMES = 64
DEFAULT_JOBS = 4
DEFAULT_QUALITY = 2


@dataclass(frozen=True)
class FrameResult:
    index: int
    seconds: float
    path: Path
    reused: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "seconds": round(self.seconds, 3),
            "timestamp": format_timestamp(self.seconds),
            "path": str(self.path),
            "reused": self.reused,
        }


def build_timestamps(
    *,
    duration_seconds: float,
    at: Sequence[float] = (),
    every: float | None = None,
    count: int | None = None,
    start: float = 0.0,
    end: float | None = None,
    max_frames: int = DEFAULT_MAX_FRAMES,
) -> list[float]:
    if max_frames <= 0:
        raise ValueError("--max-frames 必须大于 0")
    if duration_seconds <= 0:
        raise ValueError("媒体时长不合法，无法计算时间点")
    limit = duration_seconds if end is None else min(float(end), duration_seconds)
    if start < 0:
        raise ValueError("起始时间不能为负数")
    if limit <= start:
        raise ValueError(f"时间段不成立：{start} 到 {limit}")
    selected = [bool(at), every is not None, count is not None]
    if sum(selected) != 1:
        raise ValueError("时间点来源必须且只能选一种：--at / --every / --count")
    points: list[float] = []
    if at:
        for value in sorted(float(item) for item in at):
            if value < start or value >= limit:
                raise ValueError(f"时间点 {value} 不在 {start} 到 {limit} 之间")
            points.append(value)
    elif every is not None:
        step = float(every)
        if step <= 0:
            raise ValueError("--every 必须大于 0")
        current = start
        while current < limit:
            points.append(current)
            if len(points) > max_frames:
                raise ValueError(f"按 {step} 秒间隔取帧超过上限 {max_frames}，请改用更大的间隔或 --count")
            current += step
    else:
        number = int(count or 0)
        if number <= 0:
            raise ValueError("--count 必须大于 0")
        if number > max_frames:
            raise ValueError(f"--count（{number}）超过上限 {max_frames}")
        span = limit - start
        points = [start + (index + 0.5) * span / number for index in range(number)]
    if not points:
        raise ValueError("没有算出任何时间点")
    return points


def extract_frames(
    source: Path | str,
    timestamps: Sequence[float],
    *,
    out_dir: Path | str,
    fmt: str = "jpg",
    width: int | None = None,
    quality: int = DEFAULT_QUALITY,
    jobs: int = DEFAULT_JOBS,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    reuse: bool = False,
) -> tuple[list[FrameResult], list[dict[str, Any]]]:
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"画面格式只能是 {' 或 '.join(SUPPORTED_FORMATS)}：{fmt}")
    if fmt == "jpg" and not 1 <= quality <= 31:
        raise ValueError(f"--quality 必须落在 1 到 31 之间：{quality}")
    if width is not None and width <= 0:
        raise ValueError(f"--width 必须大于 0：{width}")
    if jobs <= 0:
        raise ValueError(f"--jobs 必须大于 0：{jobs}")
    if not timestamps:
        raise ValueError("没有给出任何时间点")
    media_path = Path(source).expanduser()
    if not media_path.is_file():
        raise FileNotFoundError(f"找不到输入文件：{media_path}")
    signature = parameter_signature(fmt=fmt, width=width or 0, quality=quality if fmt == "jpg" else 0)
    ensure_dir(frames_dir(out_dir))
    results: dict[int, FrameResult] = {}
    pending: list[tuple[int, float, Path]] = []
    for order, seconds in enumerate(timestamps, start=1):
        target = frame_path(out_dir, order, float(seconds), fmt, signature)
        if reuse and target.is_file() and target.stat().st_size > 0:
            results[order] = FrameResult(index=order, seconds=float(seconds), path=target, reused=True)
            continue
        pending.append((order, float(seconds), target))

    def _capture(item: tuple[int, float, Path]) -> tuple[int, float, Path]:
        order, seconds, target = item
        args = [
            *base_arguments(),
            "-y",
            "-ss",
            f"{seconds:.3f}",
            "-i",
            str(media_path),
            "-frames:v",
            "1",
            "-an",
            "-sn",
        ]
        if width is not None:
            args += ["-vf", f"scale={int(width)}:-2"]
        if fmt == "jpg":
            args += ["-q:v", str(quality)]
        args.append(str(target))
        run_ffmpeg(args, timeout=timeout)
        if not target.is_file() or target.stat().st_size == 0:
            raise FfmpegError(f"没有生成可用的画面文件：{target}")
        return order, seconds, target

    skipped: list[dict[str, Any]] = []
    if pending:
        with ThreadPoolExecutor(max_workers=int(jobs)) as pool:
            futures = {pool.submit(_capture, item): item for item in pending}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    order, seconds, target = future.result()
                except FfmpegError as exc:
                    skipped.append(
                        {
                            "seconds": round(float(item[1]), 3),
                            "timestamp": format_timestamp(float(item[1])),
                            "reason": str(exc),
                        }
                    )
                    continue
                results[order] = FrameResult(index=order, seconds=seconds, path=target, reused=False)
    ordered = [results[key] for key in sorted(results)]
    if not ordered:
        raise FfmpegError(f"全部 {len(timestamps)} 个时间点都没有取出画面")
    return ordered, skipped
