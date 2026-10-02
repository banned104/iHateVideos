from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path

import httpx

from .binaries import FFMPEG_NAME, FFPROBE_NAME, bin_dir
from .errors import BinaryInstallError

SOURCE_URL = (
    "https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip"
)
RECORD_NAME = "SOURCES.json"
ARCHIVE_NAME = "ffmpeg-download.zip"
CHUNK_BYTES = 1 << 20
TIMEOUT_SECONDS = 600.0
DOWNLOAD_ATTEMPTS = 8
WANTED = (FFMPEG_NAME, FFPROBE_NAME)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_record(record_path: Path) -> dict:
    if not record_path.is_file():
        return {}
    return json.loads(record_path.read_text(encoding="utf-8"))


def _write_record(record_path: Path, payload: dict) -> None:
    temp_path = record_path.with_name(record_path.name + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp_path, record_path)


def _record_is_current(record: dict, target_dir: Path) -> bool:
    files = record.get("files")
    if not isinstance(files, list) or len(files) != len(WANTED):
        return False
    for entry in files:
        target = target_dir / str(entry.get("name"))
        if not target.is_file():
            return False
        if _sha256(target) != entry.get("sha256"):
            return False
    return True


def _expected_total(response: httpx.Response, resume_offset: int) -> int | None:
    content_range = response.headers.get("content-range")
    if content_range and "/" in content_range:
        return int(content_range.rsplit("/", 1)[1])
    length = response.headers.get("content-length")
    if length is None:
        return None
    return int(length) + resume_offset


def _fetch_once(url: str, target: Path) -> dict:
    offset = target.stat().st_size if target.is_file() else 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    with httpx.stream(
        "GET", url, headers=headers, follow_redirects=True, timeout=TIMEOUT_SECONDS
    ) as response:
        response.raise_for_status()
        # 服务器不支持续传时会回 200 全量，此时必须从头写，否则会与残留拼接出坏文件
        resume = offset > 0 and response.status_code == httpx.codes.PARTIAL_CONTENT
        expected = _expected_total(response, offset if resume else 0)
        result = {
            "final_url": str(response.url),
            "etag": response.headers.get("etag"),
            "expected_bytes": expected,
        }
        with target.open("ab" if resume else "wb") as stream:
            for block in response.iter_bytes(CHUNK_BYTES):
                stream.write(block)
    result["received_bytes"] = target.stat().st_size
    return result


def _download(url: str, target: Path) -> dict:
    """来源会中途断流，用 Range 续传重试；每次拿到完整字节数才算成功。"""
    last_error: Exception | None = None
    for _ in range(DOWNLOAD_ATTEMPTS):
        try:
            result = _fetch_once(url, target)
        except httpx.HTTPError as exc:
            last_error = exc
            continue
        expected = result["expected_bytes"]
        if expected is None or result["received_bytes"] == expected:
            return result
        last_error = BinaryInstallError(
            f"下载不完整：收到 {result['received_bytes']} 字节，应为 {expected} 字节"
        )
    raise BinaryInstallError(f"下载失败，已续传尝试 {DOWNLOAD_ATTEMPTS} 次") from last_error


def _extract(archive_path: Path, target_dir: Path) -> list[dict]:
    with zipfile.ZipFile(archive_path) as archive:
        broken = archive.testzip()
        if broken is not None:
            raise BinaryInstallError(f"下载的压缩包损坏：{broken}")
        members: dict[str, zipfile.ZipInfo] = {}
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename).name
            if name in WANTED and name not in members:
                members[name] = info
        missing = [name for name in WANTED if name not in members]
        if missing:
            raise BinaryInstallError(f"压缩包里没有 {missing}，来源的目录结构可能变了")
        files = []
        for name in WANTED:
            target = target_dir / name
            with archive.open(members[name]) as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink)
            files.append({"name": name, "bytes": target.stat().st_size, "sha256": _sha256(target)})
    return files


def setup_binaries(*, root: Path | None = None, force: bool = False) -> dict:
    target_dir = bin_dir(root)
    target_dir.mkdir(parents=True, exist_ok=True)
    record_path = target_dir / RECORD_NAME
    record = _read_record(record_path)

    if not force and _record_is_current(record, target_dir):
        return {
            "bin_dir": str(target_dir),
            "source_url": record.get("source_url") or SOURCE_URL,
            "etag": record.get("etag"),
            "downloaded": False,
            "skipped": True,
            "files": record["files"],
        }

    archive_path = target_dir / ARCHIVE_NAME
    try:
        transfer = _download(SOURCE_URL, archive_path)
        archive_sha256 = _sha256(archive_path)
        files = _extract(archive_path, target_dir)
    finally:
        archive_path.unlink(missing_ok=True)

    _write_record(
        record_path,
        {
            "source_url": SOURCE_URL,
            "final_url": transfer["final_url"],
            "etag": transfer["etag"],
            "bytes": transfer["received_bytes"],
            "sha256": archive_sha256,
            "downloaded_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "files": files,
        },
    )
    return {
        "bin_dir": str(target_dir),
        "source_url": SOURCE_URL,
        "etag": transfer["etag"],
        "downloaded": True,
        "skipped": False,
        "files": files,
    }
