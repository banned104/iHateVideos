from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

from .errors import ModelNotReady
from .models import AlignUnit
from .paths import default_aligner_dir, default_model_dir

DEFAULT_LANGUAGE = "Chinese"
DEFAULT_MAX_NEW_TOKENS = 8192
DEFAULT_BATCH_SIZE = 16
DEFAULT_DEVICE = "cuda:0"
_MODEL_MARKERS = ("config.json", "preprocessor_config.json")


def configure_gpu(gpu: int | None) -> None:
    # CUDA_VISIBLE_DEVICES 要在 import torch 之前写进环境，之后设置不会再生效
    if gpu is None:
        return
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)


def describe_device(device: str) -> str:
    # 设了 CUDA_VISIBLE_DEVICES 之后索引会重新编号，光看 cuda:0 分不清是哪块卡
    import torch
    if not torch.cuda.is_available():
        return "cpu"
    index = 0
    if ":" in device:
        index = int(device.rsplit(":", 1)[1])
    return torch.cuda.get_device_name(index)


def _has_weights(directory: Path) -> bool:
    if any(directory.glob("*.safetensors")):
        return True
    return (directory / "pytorch_model.bin").is_file()


def describe_model_dir(path: Path | str) -> dict[str, Any]:
    # doctor 用：只报告现状，不抛异常
    directory = Path(path).expanduser()
    if not directory.is_dir():
        return {"path": str(directory), "exists": False, "missing": [], "has_weights": False}
    missing = [name for name in _MODEL_MARKERS if not (directory / name).is_file()]
    return {
        "path": str(directory),
        "exists": True,
        "missing": missing,
        "has_weights": _has_weights(directory),
    }


def require_model_dir(path: Path | str, label: str) -> Path:
    directory = Path(path).expanduser()
    if not directory.is_dir():
        raise ModelNotReady(
            f"{label}目录不存在：{directory}。把权重下载到工程根目录的 models/ 下再试。"
        )
    missing = [name for name in _MODEL_MARKERS if not (directory / name).is_file()]
    if missing:
        raise ModelNotReady(f"{label}目录不完整：{directory} 缺少 {', '.join(missing)}")
    if not _has_weights(directory):
        raise ModelNotReady(f"{label}目录没有权重文件：{directory}")
    return directory


def load_asr_model(
    *,
    model_dir: Path | str | None = None,
    aligner_dir: Path | str | None = None,
    with_timestamps: bool = True,
    device: str = DEFAULT_DEVICE,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
) -> tuple[Any, Path, Path | None]:
    import torch
    from qwen_asr import Qwen3ASRModel

    resolved_model = require_model_dir(model_dir or default_model_dir(), "识别模型")
    resolved_aligner: Path | None = None
    if with_timestamps:
        resolved_aligner = require_model_dir(
            aligner_dir or default_aligner_dir(), "时间戳模型"
        )

    kwargs: dict[str, Any] = {
        "dtype": torch.bfloat16,
        "device_map": device,
        "max_inference_batch_size": batch_size,
        "max_new_tokens": max_new_tokens,
    }
    if resolved_aligner is not None:
        kwargs["forced_aligner"] = str(resolved_aligner)
        kwargs["forced_aligner_kwargs"] = {"dtype": torch.bfloat16, "device_map": device}

    model = Qwen3ASRModel.from_pretrained(str(resolved_model), **kwargs)
    return model, resolved_model, resolved_aligner


def run_transcription(
    model: Any,
    audio_path: Path | str,
    *,
    language: str | None = DEFAULT_LANGUAGE,
    with_timestamps: bool = True,
) -> tuple[str, str, list[AlignUnit]]:
    results = model.transcribe(
        audio=str(audio_path),
        language=language,
        return_time_stamps=with_timestamps,
    )
    if not results:
        raise RuntimeError("识别模型没有返回任何结果")
    item = results[0]
    units = [
        AlignUnit(
            text=str(unit.text),
            start_seconds=float(unit.start_time),
            end_seconds=float(unit.end_time),
        )
        for unit in (getattr(item, "time_stamps", None) or [])
    ]
    detected = str(getattr(item, "language", "") or language or "")
    return detected, str(item.text or ""), units


def probe_runtime() -> dict[str, Any]:
    # doctor 用：只报告环境现状，缺什么就地说明，不做兜底
    report: dict[str, Any] = {
        "torch": None,
        "cuda_available": False,
        "device_count": 0,
        "devices": [],
        "qwen_asr": importlib.util.find_spec("qwen_asr") is not None,
    }
    if importlib.util.find_spec("torch") is None:
        return report
    import torch

    report["torch"] = torch.__version__
    report["cuda_available"] = torch.cuda.is_available()
    if report["cuda_available"]:
        report["device_count"] = torch.cuda.device_count()
        report["devices"] = [
            {"index": index, "name": torch.cuda.get_device_name(index)}
            for index in range(report["device_count"])
        ]
    return report
