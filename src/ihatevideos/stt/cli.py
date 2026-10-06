from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from ..media.ffmpeg import FfmpegError, MediaToolNotFound
from .engine import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_DEVICE,
    DEFAULT_LANGUAGE,
    DEFAULT_MAX_NEW_TOKENS,
    configure_gpu,
    describe_model_dir,
    probe_runtime,
)
from .errors import ModelNotReady, SttError
from .models import TranscriptionResult
from .paths import default_aligner_dir, default_model_dir, export_path, project_root
from .service import transcribe


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _dir_ready(report: dict) -> bool:
    return bool(report["exists"]) and not report["missing"] and bool(report["has_weights"])


def _summary_payload(result: TranscriptionResult) -> dict:
    # 字级时间戳动辄几千条，标准输出只给概要与整段文本，完整内容写在文件里
    payload = result.to_json()
    payload.pop("units")
    payload.pop("sentences")
    payload["sentence_count"] = len(result.sentences)
    payload["export"] = str(export_path(result.out_path.parent)) if result.out_path else None
    return payload


def _cmd_doctor(args: argparse.Namespace) -> int:
    runtime = probe_runtime()
    model = describe_model_dir(args.model_dir or default_model_dir())
    aligner = describe_model_dir(args.aligner_dir or default_aligner_dir())
    ready = (
        bool(runtime["qwen_asr"])
        and bool(runtime["cuda_available"])
        and _dir_ready(model)
        and _dir_ready(aligner)
    )
    _print_json(
        {
            "command": "doctor",
            "project_root": str(project_root()),
            "runtime": runtime,
            "model": model,
            "aligner": aligner,
            "ready": ready,
        }
    )
    return 0 if ready else 3


def _cmd_transcribe(args: argparse.Namespace) -> int:
    source = Path(args.input).expanduser()
    if not source.is_file():
        print(f"error: 输入文件不存在：{source}", file=sys.stderr)
        return 2
    configure_gpu(args.gpu)
    result = transcribe(
        source,
        out_dir=args.out_dir,
        model_dir=args.model_dir,
        aligner_dir=args.aligner_dir,
        with_timestamps=not args.no_timestamps,
        language=args.language,
        device=args.device,
        batch_size=args.batch_size,
        max_new_tokens=args.max_new_tokens,
        reuse=args.reuse,
        audio_timeout=args.timeout,
    )
    payload = result.to_json() if args.full else _summary_payload(result)
    _print_json({"command": "transcribe", **payload})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ihatevideos-stt",
        description="用 Qwen3-ASR 把本地音视频转成带时间戳的文字",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="检查运行环境与模型权重")
    doctor.add_argument("--model-dir", default=None)
    doctor.add_argument("--aligner-dir", default=None)
    doctor.set_defaults(func=_cmd_doctor)

    transcribe_parser = subparsers.add_parser("transcribe", help="转写一个音视频文件")
    transcribe_parser.add_argument("input", help="本地音视频路径，视频会先抽成 16 kHz 单声道 wav")
    transcribe_parser.add_argument("--language", default=DEFAULT_LANGUAGE, help="语言提示，默认 Chinese")
    transcribe_parser.add_argument("--gpu", type=int, default=None, help="只使用第 N 块 GPU")
    transcribe_parser.add_argument("--device", default=DEFAULT_DEVICE, help="torch 设备名，默认 cuda:0")
    transcribe_parser.add_argument("--model-dir", default=None, help="识别模型目录，默认 models/Qwen3-ASR-1.7B")
    transcribe_parser.add_argument("--aligner-dir", default=None, help="时间戳模型目录")
    transcribe_parser.add_argument("--no-timestamps", action="store_true", help="不加载时间戳模型，只出整段文本")
    transcribe_parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    transcribe_parser.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    transcribe_parser.add_argument("--out-dir", default=None)
    transcribe_parser.add_argument("--timeout", type=int, default=600, help="抽音频的超时秒数")
    transcribe_parser.add_argument("--reuse", action="store_true", help="复用已有的音频与结果")
    transcribe_parser.add_argument("--full", action="store_true", help="标准输出里带上完整的句子与字级时间戳")
    transcribe_parser.set_defaults(func=_cmd_transcribe)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    # 中文路径要按 UTF-8 写出，Agent 侧按 UTF-8 读取命令行输出
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: bad input: {exc}", file=sys.stderr)
        return 2
    except ModelNotReady as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except SttError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except MediaToolNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FfmpegError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
