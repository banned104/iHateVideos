from __future__ import annotations

import importlib.util
from pathlib import Path

from ..media.audio import extract_audio
from ..media.clip import cut_media
from ..media.ffmpeg import (
    FfmpegError,
    MediaToolNotFound,
    base_arguments,
    resolve_ffmpeg,
    run_tool,
)
from ..media.frames import capture_frames
from ..media.probe import probe_media
from ..stt.engine import DEFAULT_LANGUAGE, load_asr_model
from .models import (
    FAIL,
    FFMPEG_HINT,
    MEDIA_BLOCKS,
    MODEL_HINT,
    OK,
    SKIP,
    STT_BLOCKS,
    Check,
    one_line,
)

SAMPLE_SECONDS = 1.0
SAMPLE_WIDTH = 320
SAMPLE_HEIGHT = 240
SAMPLE_FPS = 10
TONE_HZ = 440
SMOKE_TIMEOUT_SECONDS = 120
WORK_SUBDIR = ("temp", "doctor")
FRAME_SECONDS = 0.5
CLIP_SECONDS = 0.5
CUDA_MATRIX_SIZE = 256
SILENCE_SECONDS = 1
FFMPEG_STEPS = ("合成样片", "读流", "截 jpg", "截 png", "抽 wav", "剪一段")


def work_dir(root: Path | str) -> Path:
    return Path(root).joinpath(*WORK_SUBDIR)


def _size_text(path: Path) -> str:
    size = path.stat().st_size
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} 字节"


def _ffmpeg_fail(name: str, detail: str) -> Check:
    return Check("ffmpeg", name, FAIL, detail, MEDIA_BLOCKS, FFMPEG_HINT)


def _make_sample(target: Path, *, timeout: int) -> str | None:
    # 用 lavfi 现造一段带画面与声音的样片，不依赖任何外部素材
    try:
        ffmpeg = resolve_ffmpeg()
        run_tool(
            ffmpeg,
            [
                *base_arguments(),
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"testsrc=size={SAMPLE_WIDTH}x{SAMPLE_HEIGHT}:rate={SAMPLE_FPS}:duration={SAMPLE_SECONDS}",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={TONE_HZ}:duration={SAMPLE_SECONDS}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(target),
            ],
            timeout=timeout,
        )
    except (MediaToolNotFound, FfmpegError) as exc:
        return one_line(str(exc))
    if not target.is_file() or target.stat().st_size == 0:
        return f"没有生成样片：{target}"
    return None


def _probe_step(sample: Path) -> Check:
    try:
        media = probe_media(sample)
    except (FfmpegError, MediaToolNotFound, FileNotFoundError) as exc:
        return _ffmpeg_fail("读流", one_line(str(exc)))
    if not media.has_video or not media.has_audio:
        return _ffmpeg_fail("读流", f"样片只读到画面 {media.has_video}、声音 {media.has_audio}")
    return Check(
        "ffmpeg",
        "读流",
        OK,
        f"时长 {media.duration_seconds:.3f} 秒，{media.video.codec} + {media.audio.codec}",
    )


def _frame_step(sample: Path, target: Path, *, fmt: str, timeout: int) -> Check:
    name = f"截 {fmt}"
    try:
        capture_frames(sample, [(FRAME_SECONDS, target)], fmt=fmt, timeout=timeout)
    except (FfmpegError, MediaToolNotFound) as exc:
        return _ffmpeg_fail(name, one_line(str(exc)))
    if not target.is_file() or target.stat().st_size == 0:
        return _ffmpeg_fail(name, f"没有生成可用的画面文件：{target}")
    return Check("ffmpeg", name, OK, _size_text(target))


def _audio_step(sample: Path, target: Path, *, timeout: int) -> Check:
    try:
        result = extract_audio(sample, fmt="wav", output=target, timeout=timeout)
    except (FfmpegError, MediaToolNotFound, ValueError) as exc:
        return _ffmpeg_fail("抽 wav", one_line(str(exc)))
    return Check(
        "ffmpeg",
        "抽 wav",
        OK,
        f"{result.sample_rate} Hz {result.channels} 声道，{_size_text(result.path)}",
    )


def _clip_step(sample: Path, target: Path, *, timeout: int) -> Check:
    try:
        result = cut_media(
            sample, start=0.0, duration=CLIP_SECONDS, mode="copy", output=target, timeout=timeout
        )
    except (FfmpegError, MediaToolNotFound, ValueError) as exc:
        return _ffmpeg_fail("剪一段", one_line(str(exc)))
    return Check("ffmpeg", "剪一段", OK, _size_text(result.path))


def run_ffmpeg_smoke(work: Path, *, timeout: int = SMOKE_TIMEOUT_SECONDS) -> list[Check]:
    """跑一遍取帧、抽音频、剪切的真实路径，判定看产物而不看 ffmpeg 的提示文本。"""
    work.mkdir(parents=True, exist_ok=True)
    sample = work / "sample.mp4"
    error = _make_sample(sample, timeout=timeout)
    if error is not None:
        checks = [_ffmpeg_fail("合成样片", error)]
        checks += [Check("ffmpeg", name, SKIP, "样片没造出来") for name in FFMPEG_STEPS[1:]]
        return checks
    return [
        Check("ffmpeg", "合成样片", OK, _size_text(sample)),
        _probe_step(sample),
        _frame_step(sample, work / "shot.jpg", fmt="jpg", timeout=timeout),
        _frame_step(sample, work / "shot.png", fmt="png", timeout=timeout),
        _audio_step(sample, work / "sound.wav", timeout=timeout),
        _clip_step(sample, work / "part.mp4", timeout=timeout),
    ]


def _cuda_step(index: int) -> Check:
    import torch

    name = f"CUDA 计算 cuda:{index}"
    try:
        device = torch.device(f"cuda:{index}")
        # 全 1 矩阵乘的结果是精确整数，能同时验出「分配得了」与「算得对」
        left = torch.full(
            (CUDA_MATRIX_SIZE, CUDA_MATRIX_SIZE), 1.0, dtype=torch.float32, device=device
        )
        product = (left @ left).to("cpu")
    except RuntimeError as exc:
        return Check("gpu", name, FAIL, one_line(str(exc)), STT_BLOCKS, FFMPEG_HINT)
    if not bool(torch.all(product == float(CUDA_MATRIX_SIZE))):
        return Check("gpu", name, FAIL, f"矩阵乘结果不是 {CUDA_MATRIX_SIZE}", STT_BLOCKS, FFMPEG_HINT)
    return Check("gpu", name, OK, torch.cuda.get_device_name(index))


def run_cuda_smoke() -> list[Check]:
    if importlib.util.find_spec("torch") is None:
        return [Check("gpu", "CUDA 计算", SKIP, "没有装 torch")]
    import torch

    if not torch.cuda.is_available():
        return [Check("gpu", "CUDA 计算", SKIP, "torch 报告 CUDA 不可用")]
    return [_cuda_step(index) for index in range(torch.cuda.device_count())]


def run_model_smoke(work: Path) -> list[Check]:
    """真正加载两份权重并用一段静音跑一次识别，这是最慢的一项检查。"""
    work.mkdir(parents=True, exist_ok=True)
    silence = work / "silence.wav"
    try:
        run_tool(
            resolve_ffmpeg(),
            [
                *base_arguments(),
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=16000:cl=mono",
                "-t",
                str(SILENCE_SECONDS),
                str(silence),
            ],
            timeout=SMOKE_TIMEOUT_SECONDS,
        )
    except (MediaToolNotFound, FfmpegError) as exc:
        return [Check("stt", "模型加载", SKIP, f"造不出静音样本：{one_line(str(exc))}")]
    try:
        model, _, _ = load_asr_model(with_timestamps=True)
        # 静音样本识别出空内容是正常的，这里只看加载与推理有没有抛异常
        model.transcribe(audio=str(silence), language=DEFAULT_LANGUAGE, return_time_stamps=True)
    except Exception as exc:  # noqa: BLE001 — 模型加载的失败形态很多，统一报成一条
        detail = one_line(f"{type(exc).__name__}: {exc}")
        return [Check("stt", "模型加载", FAIL, detail, STT_BLOCKS, MODEL_HINT)]
    return [Check("stt", "模型加载", OK, "识别模型与对齐器都加载成功，并跑通一次识别")]
