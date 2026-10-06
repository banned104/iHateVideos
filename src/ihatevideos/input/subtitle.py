import asyncio
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from bilibili_api import video
from bilibili_api.exceptions import (
    CredentialNoSessdataException,
    NetworkException,
    ResponseCodeException,
)
from bilibili_api.utils import network as bili_network
from bilibili_api.utils.network import Credential

from .bilibili_ids import extract_bilibili_page, extract_bvid
from .cookies import BILIBILI_USER_AGENT, config_dir, credential_data

logger = logging.getLogger(__name__)

ALLOWED_MEDIA_SUFFIXES = (
    ".bilibili.com",
    ".hdslb.com",
    ".bilivideo.com",
    ".bilivideo.cn",
    ".biliapi.net",
    ".akamaized.net",
)
# 语言权重照 B 站播放器字幕轨的 lan 取值排列，未列出的排在最后
LANGUAGE_PRIORITIES = {
    "zh-cn": 0,
    "zh-hans": 1,
    "zh": 2,
    "ai-zh": 3,
    "zh-hant": 4,
    "zh-tw": 5,
    "en": 0,
}
UNLISTED_LANGUAGE_PRIORITY = 20
BODY_DOWNLOAD_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class BilibiliSubtitleItem:
    """One timestamped Bilibili subtitle item."""

    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class BilibiliSubtitle:
    """Subtitle text and timeline items returned by Bilibili."""

    text: str
    items: tuple[BilibiliSubtitleItem, ...] = ()


@dataclass(frozen=True)
class SubtitleResult:
    """字幕获取结果；subtitle 为 None 时 reason 说明原因，调用方要把它显示出来。"""

    subtitle: BilibiliSubtitle | None
    reason: str = ""

    @property
    def available(self) -> bool:
        return self.subtitle is not None


def track_language(track: dict[str, Any]) -> str:
    return str(track.get("lan") or track.get("id_str") or "unknown")


def track_url(track: dict[str, Any]) -> str:
    return str(track.get("subtitle_url") or track.get("subtitle_url_v2") or "")


def is_chinese_track(track: dict[str, Any]) -> bool:
    language = track_language(track).lower().replace("_", "-")
    return language.startswith("zh") or language in {"ai-zh", "zho", "chi"}


def is_ai_track(track: dict[str, Any]) -> bool:
    language = track_language(track).lower().replace("_", "-")
    try:
        type_value = int(track.get("type") or 0)
    except (TypeError, ValueError):
        type_value = 0
    return bool(track.get("ai_status")) or language.startswith("ai-") or type_value == 1


def rank_subtitles(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按「中文非 AI → 中文 AI → 非中文非 AI → 非中文 AI」排序，组内再按语言权重。"""

    def score(track: dict[str, Any]) -> tuple[int, int, str]:
        language = track_language(track).lower().replace("_", "-")
        if is_chinese_track(track):
            group = 1 if is_ai_track(track) else 0
        else:
            group = 3 if is_ai_track(track) else 2
        label = str(track.get("lan_doc") or language)
        return group, LANGUAGE_PRIORITIES.get(language, UNLISTED_LANGUAGE_PRIORITY), label

    return sorted([track for track in tracks if track_url(track)], key=score)


def validated_media_url(url: str) -> str:
    """补全协议并校验域名，只接受 B 站自己的媒体域名。"""
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not any(
        host.endswith(suffix) for suffix in ALLOWED_MEDIA_SUFFIXES
    ):
        raise ValueError(f"地址不属于可信的 B站域名：{url}")
    return url


def select_part_cid(pages: list[dict[str, Any]], page: int) -> int:
    """按分P序号取 cid；序号越界或字段缺失时抛出带原因的错误。"""
    if not pages:
        raise ValueError("视频没有分P信息")
    if page < 1 or page > len(pages):
        raise ValueError(f"分P {page} 不存在，该视频共 {len(pages)} 个分P")
    cid = pages[page - 1].get("cid")
    if not cid:
        raise ValueError(f"分P {page} 没有 cid")
    return int(cid)


def parse_subtitle_body(payload: Any) -> tuple[BilibiliSubtitleItem, ...]:
    """把字幕正文 JSON 转成分段；空正文按失败处理。"""
    if not isinstance(payload, dict) or not isinstance(payload.get("body"), list):
        raise ValueError("字幕正文格式不受支持")
    items: list[BilibiliSubtitleItem] = []
    for raw in payload["body"]:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("content") or "").strip()
        if not text:
            continue
        try:
            start_ms = max(0, round(float(raw.get("from") or 0) * 1000))
            end_ms = max(start_ms, round(float(raw.get("to") or 0) * 1000))
        except (TypeError, ValueError):
            continue
        items.append(BilibiliSubtitleItem(start_ms=start_ms, end_ms=end_ms, text=text))
    if not items:
        raise ValueError("字幕正文为空")
    return tuple(items)


def build_credential() -> Credential:
    data = credential_data()
    return Credential(
        sessdata=data.get("SESSDATA", ""),
        bili_jct=data.get("bili_jct", ""),
        buvid3=data.get("buvid3", ""),
        buvid4=data.get("buvid4", ""),
        dedeuserid=data.get("DedeUserID", ""),
    )


def describe_api_error(exc: ResponseCodeException) -> str:
    code = exc.code
    message = exc.msg or ""
    if code == -404:
        return "没有找到这个视频，可能已删除或不可见"
    if code in {-101, -400, -403}:
        return f"B站不允许访问该内容（{message}）"
    return f"B站接口返回错误 {code}：{message}"


async def _download_body(url: str, *, bvid: str) -> tuple[BilibiliSubtitleItem, ...]:
    media_url = validated_media_url(url)
    headers = {
        "User-Agent": BILIBILI_USER_AGENT,
        "Referer": f"https://www.bilibili.com/video/{bvid}/",
    }
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=BODY_DOWNLOAD_TIMEOUT_SECONDS
    ) as client:
        response = await client.get(media_url, headers=headers)
        response.raise_for_status()
        payload = response.json()
    return parse_subtitle_body(payload)


async def _fetch_subtitle_async(target: str) -> SubtitleResult:
    bvid = extract_bvid(target)
    if bvid is None:
        return SubtitleResult(None, "无法从输入提取 BV 号")
    page = extract_bilibili_page(target) or 1
    credential = build_credential()
    if not credential.sessdata:
        return SubtitleResult(
            None,
            f"没有可用的 cookies 文件，把导出的 cookies.txt 复制到 {config_dir()}",
        )

    client = video.Video(bvid=bvid, credential=credential)
    pages = await client.get_pages()
    try:
        cid = select_part_cid(pages, page)
    except ValueError as exc:
        return SubtitleResult(None, str(exc))

    info = await client.get_player_info(cid=cid)
    if not isinstance(info, dict):
        return SubtitleResult(None, "B站播放器接口没有返回数据")
    subtitle_block = info.get("subtitle")
    tracks: list[dict[str, Any]] = []
    if isinstance(subtitle_block, dict):
        raw_tracks = subtitle_block.get("subtitles")
        if isinstance(raw_tracks, list):
            tracks = [track for track in raw_tracks if isinstance(track, dict)]
    if not tracks:
        if info.get("need_login_subtitle"):
            return SubtitleResult(None, "该分P的字幕需要登录后才能读取，当前凭据不可用")
        return SubtitleResult(None, f"该分P（第 {page} P）没有字幕轨道")

    ranked = rank_subtitles(tracks)
    if not ranked:
        return SubtitleResult(None, "字幕轨道只有元数据，没有下载地址")

    failures: list[str] = []
    for track in ranked:
        language = track_language(track)
        try:
            items = await _download_body(track_url(track), bvid=bvid)
        except ValueError as exc:
            failures.append(f"{language}：{exc}")
            continue
        except httpx.HTTPError as exc:
            failures.append(f"{language}：字幕正文下载失败（{exc}）")
            continue
        text = "\n".join(item.text for item in items)
        logger.info("B站字幕命中：%s，%d 段", language, len(items))
        return SubtitleResult(BilibiliSubtitle(text=text, items=items), "")

    return SubtitleResult(None, "；".join(failures) or "没有可下载的字幕正文")


async def release_bilibili_client() -> None:
    """在事件循环内关掉 bilibili_api 的请求客户端。

    它的 atexit 清理会在 asyncio.run 已经关闭的循环上再关一次，
    进程退出时踩到已关闭的循环，Windows 上表现为 0xC0000005。
    """
    pool = bili_network.session_pool.get(bili_network.selected_client)
    if not pool:
        return
    client = pool.pop(asyncio.get_running_loop(), None)
    if client is None:
        return
    try:
        await client.close()
    except Exception as exc:  # noqa: BLE001
        logger.debug("关闭 B站请求客户端失败：%s", exc)


def fetch_bilibili_subtitle(target: str, *, timeout_seconds: int = 60) -> SubtitleResult:
    """按分P的 cid 取 B站原生字幕，失败时在 reason 里给出可读原因。"""
    cleaned_target = target.strip()
    if not cleaned_target:
        return SubtitleResult(None, "输入为空")
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "An event loop is already running; fetch_bilibili_subtitle is synchronous."
        )

    async def run() -> SubtitleResult:
        try:
            return await asyncio.wait_for(
                _fetch_subtitle_async(cleaned_target), timeout=float(timeout_seconds)
            )
        finally:
            await release_bilibili_client()

    try:
        return asyncio.run(run())
    except asyncio.TimeoutError:
        return SubtitleResult(None, f"获取 B站字幕超时（{timeout_seconds} 秒）")
    except CredentialNoSessdataException:
        return SubtitleResult(
            None, f"B站 cookies 缺少 sessdata，重新从浏览器导出一份放到 {config_dir()}"
        )
    except ResponseCodeException as exc:
        return SubtitleResult(None, describe_api_error(exc))
    except NetworkException as exc:
        return SubtitleResult(None, f"B站网络请求失败：{exc}")
