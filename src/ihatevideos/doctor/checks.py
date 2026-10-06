from __future__ import annotations

import importlib.util
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Sequence

from ..media.ffmpeg import MediaToolNotFound, resolve_ffmpeg, resolve_ffprobe
from ..stt.engine import describe_model_dir, probe_runtime
from ..stt.paths import default_aligner_dir, default_model_dir
from .models import (
    DOWNLOAD_BLOCKS,
    FAIL,
    FFMPEG_HINT,
    INPUT_BLOCKS,
    MEDIA_BLOCKS,
    MISSING,
    MODEL_HINT,
    OK,
    SKIP,
    STT_BLOCKS,
    WARN,
    Check,
    one_line,
)
from .smoke import FFMPEG_STEPS, run_cuda_smoke, run_ffmpeg_smoke, run_model_smoke, work_dir

PROBE_TIMEOUT_SECONDS = 60
LOGIN_TIMEOUT_SECONDS = 30.0
COOKIES_HINT = "从浏览器导出一份 cookies.txt 放进 temp/config/"
# ihatevideos.download 与 ihatevideos.input 的 __init__ 会在导入期拉起全部子模块，
# 先把它们需要的第三方包查清楚，缺了就不导入，doctor 才能在环境残缺时照常给出报告
DOWNLOAD_REQUIREMENTS = ("aria2c", "imageio_ffmpeg", "aria2p", "requests", "httpx")
INPUT_REQUIREMENTS = ("httpx", "bilibili_api", "requests")

# (导入名, 发行包名, 用处, 缺了挡住谁)
PYTHON_PACKAGES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("httpx", "httpx", "网络请求", ("ihatevideos-input", "ihatevideos-download")),
    ("requests", "requests", "网络请求", ("ihatevideos-input", "ihatevideos-download")),
    ("aria2p", "aria2p", "aria2c 进程控制", DOWNLOAD_BLOCKS),
    ("aria2c", "aria2", "aria2c 可执行文件", DOWNLOAD_BLOCKS),
    ("bilibili_api", "bilibili-api-python", "B 站接口", INPUT_BLOCKS),
    ("yt_dlp", "yt-dlp", "视频下载", DOWNLOAD_BLOCKS),
    ("imageio_ffmpeg", "imageio-ffmpeg", "ffmpeg 可执行文件", DOWNLOAD_BLOCKS),
    ("yutto", "yutto", "B 站音频下载", INPUT_BLOCKS),
    ("torch", "torch", "GPU 计算", STT_BLOCKS),
    ("qwen_asr", "qwen-asr", "语音识别", STT_BLOCKS),
)


def _can_import(*names: str) -> bool:
    return all(importlib.util.find_spec(name) is not None for name in names)


def _missing_of(names: Sequence[str]) -> list[str]:
    return [name for name in names if importlib.util.find_spec(name) is None]


def _distribution_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _probe_version(path: str, flag: str) -> str | None:
    # 取版本行的做法与 download/binaries.py 一致，保证两份报告里的版本号可对照
    try:
        completed = subprocess.run(
            [path, flag],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    for line in (completed.stdout or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) >= 3 and parts[1] == "version":
            return parts[2]
        return stripped
    return None


def check_python() -> list[Check]:
    checks: list[Check] = []
    for module_name, dist_name, purpose, blocks in PYTHON_PACKAGES:
        version = _distribution_version(dist_name)
        if importlib.util.find_spec(module_name) is None:
            checks.append(
                Check(
                    "python",
                    module_name,
                    MISSING,
                    f"{purpose}：没有安装",
                    blocks,
                    "uv sync 会把依赖装齐",
                )
            )
            continue
        checks.append(Check("python", module_name, OK, f"{purpose}  {version or '版本未知'}"))
    return checks


def _media_binary(name: str, resolver) -> tuple[Check, str | None]:
    label = f"{name} (media)"
    try:
        path = resolver()
    except MediaToolNotFound as exc:
        return Check("binary", label, MISSING, one_line(str(exc)), MEDIA_BLOCKS, FFMPEG_HINT), None
    version = _probe_version(path, "-version")
    if version is None:
        return Check("binary", label, FAIL, f"{path} 无法执行 -version", MEDIA_BLOCKS, FFMPEG_HINT), path
    return Check("binary", label, OK, f"{path}  {version}"), path


def _ffmpeg_consistency(media_path: str | None, download_path: str | None) -> Check | None:
    if not media_path or not download_path:
        return None
    if Path(media_path).resolve() == Path(download_path).resolve():
        return Check("binary", "ffmpeg 一致性", OK, "两处解析到同一个可执行文件")
    return Check(
        "binary",
        "ffmpeg 一致性",
        WARN,
        f"media 用 {media_path}，download 用 {download_path}",
        (),
        "取帧与抽音频走一份 ffmpeg、下载合并走另一份，行为可能不一致",
    )


def check_binaries() -> list[Check]:
    checks: list[Check] = []
    ffmpeg_check, media_ffmpeg = _media_binary("ffmpeg", resolve_ffmpeg)
    ffprobe_check, _ = _media_binary("ffprobe", resolve_ffprobe)
    checks += [ffmpeg_check, ffprobe_check]

    if not _can_import(*DOWNLOAD_REQUIREMENTS):
        missing = ", ".join(_missing_of(DOWNLOAD_REQUIREMENTS))
        checks.append(
            Check(
                "binary",
                "download 侧可执行文件",
                SKIP,
                f"缺少 {missing}，无法解析 download 用的那一份",
                DOWNLOAD_BLOCKS,
            )
        )
        return checks

    from ..download.binaries import resolve_engines
    from ..download.errors import EngineStartError

    try:
        engines = resolve_engines()
    except (EngineStartError, OSError) as exc:
        checks.append(
            Check("binary", "download 侧可执行文件", FAIL, one_line(str(exc)), DOWNLOAD_BLOCKS)
        )
        return checks

    download_ffmpeg: str | None = None
    pairs = (
        (engines.aria2c, "aria2c"),
        (engines.ffmpeg, "ffmpeg (download)"),
        (engines.ffprobe, "ffprobe (download)"),
        (engines.yt_dlp, "yt-dlp"),
    )
    for engine, label in pairs:
        if not engine.available:
            checks.append(
                Check(
                    "binary",
                    label,
                    MISSING,
                    "没找到",
                    DOWNLOAD_BLOCKS,
                    "ihatevideos-download binaries 会把 aria2c 与 ffmpeg 装到 temp/bin/",
                )
            )
            continue
        if label == "yt-dlp":
            # yt-dlp 是当模块跑的，engine.path 给的是解释器
            location = f"{engine.path} -m yt_dlp"
        else:
            location = str(engine.path)
        detail = f"{location}  {engine.version}" if engine.version else location
        checks.append(Check("binary", label, OK, f"{detail}  [{engine.source}]"))
        if label == "ffmpeg (download)":
            download_ffmpeg = engine.path

    consistency = _ffmpeg_consistency(media_ffmpeg, download_ffmpeg)
    if consistency is not None:
        checks.append(consistency)
    return checks


def check_ffmpeg(work: Path, *, smoke: bool) -> list[Check]:
    if not smoke:
        return [Check("ffmpeg", name, SKIP, "带了 --no-smoke") for name in FFMPEG_STEPS]
    return run_ffmpeg_smoke(work)


def _memory_checks(runtime: dict) -> list[Check]:
    if not runtime["cuda_available"]:
        return [Check("gpu", "显存", SKIP, "CUDA 不可用")]
    import torch

    checks: list[Check] = []
    for index in range(runtime["device_count"]):
        free, total = torch.cuda.mem_get_info(index)
        checks.append(
            Check(
                "gpu",
                f"显存 cuda:{index}",
                OK,
                f"空闲 {free / 1024**3:.1f} GB / 共 {total / 1024**3:.1f} GB",
            )
        )
    return checks


def check_gpu(*, smoke: bool) -> list[Check]:
    runtime = probe_runtime()
    checks: list[Check] = []
    if runtime["torch"] is None:
        checks.append(
            Check("gpu", "torch CUDA", MISSING, "没有装 torch", STT_BLOCKS, "uv sync 会把依赖装齐")
        )
    elif not runtime["cuda_available"]:
        checks.append(
            Check(
                "gpu",
                "torch CUDA",
                FAIL,
                f"torch {runtime['torch']} 报告 CUDA 不可用",
                STT_BLOCKS,
                "确认装的是 CUDA 版 torch，并检查显卡驱动",
            )
        )
    else:
        checks.append(
            Check("gpu", "torch CUDA", OK, f"torch {runtime['torch']}，{runtime['device_count']} 块卡")
        )
    if smoke:
        checks += run_cuda_smoke()
    else:
        checks.append(Check("gpu", "CUDA 计算", SKIP, "带了 --no-smoke"))
    checks += _memory_checks(runtime)
    return checks


def check_stt(work: Path, *, deep: bool) -> list[Check]:
    checks: list[Check] = []
    for label, directory in (("识别模型", default_model_dir()), ("对齐器", default_aligner_dir())):
        name = f"{label}权重"
        report = describe_model_dir(directory)
        if not report["exists"]:
            checks.append(Check("stt", name, MISSING, f"目录不存在：{report['path']}", STT_BLOCKS, MODEL_HINT))
        elif report["missing"]:
            checks.append(
                Check(
                    "stt",
                    name,
                    MISSING,
                    f"{report['path']} 缺少 {', '.join(report['missing'])}",
                    STT_BLOCKS,
                    MODEL_HINT,
                )
            )
        elif not report["has_weights"]:
            checks.append(
                Check("stt", name, MISSING, f"{report['path']} 没有权重文件", STT_BLOCKS, MODEL_HINT)
            )
        else:
            checks.append(Check("stt", name, OK, report["path"]))
    if deep:
        checks += run_model_smoke(work)
    else:
        checks.append(Check("stt", "模型加载", SKIP, "没有加 --deep"))
    return checks


def _reachable_check(url: str, *, timeout: float) -> Check:
    import httpx

    from ..input.cookies import BILIBILI_USER_AGENT

    # 不带浏览器请求头会被 B 站当成脚本挡掉，返回的就不是 JSON
    headers = {
        "User-Agent": BILIBILI_USER_AGENT,
        "Referer": "https://www.bilibili.com/",
    }
    try:
        response = httpx.get(url, headers=headers, timeout=timeout)
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return Check("bilibili", "B 站可达", FAIL, one_line(str(exc)), INPUT_BLOCKS, "检查网络与代理设置")
    if not isinstance(payload, dict) or "code" not in payload:
        return Check("bilibili", "B 站可达", FAIL, "返回的内容不是预期的 JSON 结构", INPUT_BLOCKS)
    if payload.get("code") != 0:
        # 业务码非 0 说明服务器已经正常应答，只是这次没带登录态，能通就算可达
        return Check(
            "bilibili",
            "B 站可达",
            OK,
            f"应答正常，业务码 {payload.get('code')}：{payload.get('message', '')}",
        )
    return Check("bilibili", "B 站可达", OK, "nav 接口正常应答")


def check_bilibili(*, timeout: float = LOGIN_TIMEOUT_SECONDS) -> list[Check]:
    if not _can_import(*INPUT_REQUIREMENTS):
        missing = ", ".join(_missing_of(INPUT_REQUIREMENTS))
        return [
            Check("bilibili", "cookies 文件", SKIP, f"缺少 {missing}，无法读取 cookies"),
            Check("bilibili", "登录态", SKIP, f"缺少 {missing}"),
            Check("bilibili", "B 站可达", SKIP, f"缺少 {missing}"),
        ]

    from ..input.cookies import NAV_URL, credential_status, verify_login

    checks: list[Check] = []
    status = credential_status()
    state = status["state"]
    if state == "missing":
        checks.append(
            Check(
                "bilibili",
                "cookies 文件",
                MISSING,
                f"{status['dir']} 里没有 cookies 文件",
                INPUT_BLOCKS,
                COOKIES_HINT,
            )
        )
    elif state == "empty":
        checks.append(
            Check(
                "bilibili",
                "cookies 文件",
                MISSING,
                f"{status['dir']} 里的文件都不含 SESSDATA：{', '.join(status['files'])}",
                INPUT_BLOCKS,
                COOKIES_HINT,
            )
        )
    else:
        checks.append(
            Check("bilibili", "cookies 文件", OK, f"{status['path']}，SESSDATA {status['sessdata_len']} 字符")
        )
    checks.append(_reachable_check(NAV_URL, timeout=timeout))
    if state != "ok":
        checks.append(Check("bilibili", "登录态", SKIP, "没有可用的 cookies 文件"))
    else:
        ok, message = verify_login(timeout_seconds=timeout)
        # cookies 过期会挡住字幕与评论，但不影响下载与本地处理，所以记成隐患而不是必修
        checks.append(Check("bilibili", "登录态", OK if ok else WARN, message, (), COOKIES_HINT))
    return checks


def check_network() -> list[Check]:
    if not _can_import(*DOWNLOAD_REQUIREMENTS):
        missing = ", ".join(_missing_of(DOWNLOAD_REQUIREMENTS))
        return [Check("network", "代理", SKIP, f"缺少 {missing}，无法读取系统代理")]

    from ..download.proxy import system_proxy

    proxy = system_proxy()
    if proxy:
        return [Check("network", "代理", OK, proxy)]
    return [Check("network", "代理", WARN, "没有读到系统代理", (), "访问 B 站之外的站点可能需要代理")]


def run_checks(
    *,
    root: Path,
    groups: Sequence[str],
    smoke: bool = True,
    deep: bool = False,
) -> list[Check]:
    work = work_dir(root)
    checks: list[Check] = []
    if "python" in groups:
        checks += check_python()
    if "binary" in groups:
        checks += check_binaries()
    if "ffmpeg" in groups:
        checks += check_ffmpeg(work, smoke=smoke)
    if "gpu" in groups:
        checks += check_gpu(smoke=smoke)
    if "stt" in groups:
        checks += check_stt(work, deep=deep)
    if "bilibili" in groups:
        checks += check_bilibili()
    if "network" in groups:
        checks += check_network()
    return checks
