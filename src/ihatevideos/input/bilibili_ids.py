"""Bilibili BV ID extraction and target normalization.

Extracted from bilibili2text ``b2t/download/yutto_cli.py`` (pure helpers only).
The legacy subprocess-based ``download_audio`` is NOT ported; audio download
lives in ``bilibili_audio.py`` (yutto Python API).
"""

import logging
import re
from urllib.parse import parse_qs, urlsplit

import requests

logger = logging.getLogger(__name__)

_BVID_PATTERN = re.compile(r"(BV[0-9A-Za-z]{10})", re.IGNORECASE)
_TARGET_ID_PAGE_PATTERN = re.compile(
    r"BV[0-9A-Za-z]{10}_p([1-9][0-9]*)(?:[-_/]|$)", re.IGNORECASE
)
_B23_SHORT_URL_PATTERN = re.compile(r"b23\.tv/", re.IGNORECASE)
_HTTP_URL_PATTERN = re.compile(r"https?://\S+")


def extract_bvid(raw: str) -> str | None:
    """Extract a BV ID from input, returns None on failure."""
    match = _BVID_PATTERN.search(raw.strip())
    if match is None:
        return None
    bvid = match.group(1)
    return "BV" + bvid[2:]


def extract_bilibili_page(raw: str) -> int | None:
    """Extract a positive Bilibili multipart page number from a URL."""
    url_match = _HTTP_URL_PATTERN.search(raw.strip())
    target = url_match.group(0) if url_match else raw.strip()
    try:
        values = parse_qs(urlsplit(target).query).get("p", [])
    except ValueError:
        return None
    if not values or not values[0].isdigit():
        return None
    page = int(values[0])
    return page if page > 0 else None


def extract_bilibili_target_id(raw: str) -> str | None:
    """Build the storage identity for a video, separating multipart pages."""
    bvid = extract_bvid(raw)
    if bvid is None:
        return None
    page = extract_bilibili_page(raw)
    if page is None or page == 1:
        return bvid
    return f"{bvid}_p{page}"


def extract_bilibili_page_from_target_id(raw: str) -> int | None:
    """Extract a multipart page from an internal transcription or run ID."""
    match = _TARGET_ID_PAGE_PATTERN.search(raw.strip())
    return int(match.group(1)) if match else None


def _resolve_b23_short_url(url: str, timeout: float = 5.0) -> str:
    """Resolve b23.tv short URL, follow redirects and return the real URL."""
    try:
        resp = requests.head(url, allow_redirects=True, timeout=timeout)
        final = resp.url
        logger.debug("b23.tv 解析: %s -> %s", url, final)
        return final
    except Exception as exc:
        logger.warning("解析 b23.tv 短链接失败: %s，继续使用原始 URL", exc)
        return url


def normalize_bilibili_target(raw: str) -> str:
    """Normalize input to a target string that yutto can process directly.

    Supported input formats:
    - Full Bilibili URL (with query params)
    - Plain BV ID
    - b23.tv short URL (auto-follows redirects to resolve)
    - Bilibili default share text (e.g. "title-Bilibili" https://b23.tv/xxx)
    """
    target = raw.strip()
    if not target:
        raise ValueError("URL 不能为空")

    # Extract URL from share text (handles "title-Bilibili" https://... format)
    url_match = _HTTP_URL_PATTERN.search(target)
    if url_match:
        target = url_match.group(0)

    # Resolve b23.tv short URL
    if _B23_SHORT_URL_PATTERN.search(target):
        target = _resolve_b23_short_url(target)

    bvid = extract_bvid(target)
    if bvid is None:
        return target

    normalized = f"https://www.bilibili.com/video/{bvid}"
    page = extract_bilibili_page(target)
    if page is not None:
        return f"{normalized}?p={page}"
    return normalized
