import asyncio
import hashlib
import json
import logging
import time
import urllib.parse
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from .cookies import bilibili_cookie_string
from .platform import Platform

logger = logging.getLogger(__name__)

BILIBILI_VIDEO_COMMENT_TYPE = 1
DEFAULT_COMMENT_LIMIT = 200
MAX_PAGE_SIZE = 20
BILIBILI_WBI_WEB_LOCATION = 1315875
BILIBILI_MIXIN_KEY_ENC_TAB = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5,
    49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24,
    55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6,
    63, 57, 62, 11, 36, 20, 34, 44, 52,
)
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class PlatformComment:
    rpid: int | str
    author: str
    author_uid: int | str
    message: str
    like: int
    ctime: str
    ctime_timestamp: int
    is_up_reply: bool = False
    replies: tuple["PlatformComment", ...] = ()


@dataclass(frozen=True)
class PlatformCommentBundle:
    bvid: str
    fetched_count: int
    requested_limit: int | None
    total_count: int
    sort: str
    comments: tuple[PlatformComment, ...] = field(default_factory=tuple)
    aid: int = 0
    platform: str = Platform.BILIBILI.value
    source: str = "api"


BilibiliComment = PlatformComment
BilibiliCommentBundle = PlatformCommentBundle


def count_comment_replies(bundle: PlatformCommentBundle) -> int:
    return sum(len(comment.replies) for comment in bundle.comments)


def count_up_replies(bundle: PlatformCommentBundle) -> int:
    return sum(
        int(comment.is_up_reply)
        + sum(int(reply.is_up_reply) for reply in comment.replies)
        for comment in bundle.comments
    )


def _headers(cookie: str = "") -> dict[str, str]:
    headers = {
        "User-Agent": _USER_AGENT,
        "Referer": "https://www.bilibili.com",
        "Origin": "https://www.bilibili.com",
    }
    if cookie.strip():
        headers["Cookie"] = cookie.strip()
    return headers


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _format_ctime(timestamp: int) -> str:
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def _parse_comment(raw: dict[str, Any], *, up_uid: int) -> PlatformComment:
    member = raw.get("member")
    if not isinstance(member, dict):
        member = {}
    content = raw.get("content")
    if not isinstance(content, dict):
        content = {}

    author_uid = _to_int(member.get("mid"))
    ctime_timestamp = _to_int(raw.get("ctime"))
    return PlatformComment(
        rpid=_to_int(raw.get("rpid")),
        author=str(member.get("uname") or ""),
        author_uid=author_uid,
        message=str(content.get("message") or "").strip(),
        like=_to_int(raw.get("like")),
        ctime=_format_ctime(ctime_timestamp),
        ctime_timestamp=ctime_timestamp,
        is_up_reply=up_uid > 0 and author_uid == up_uid,
    )


def _sort_value(sort: str) -> int:
    normalized = sort.strip().lower()
    if normalized in {"time", "latest", "new"}:
        return 0
    return 1


def _wbi_sort_mode(sort: str) -> int:
    normalized = sort.strip().lower()
    if normalized in {"time", "latest", "new"}:
        return 2
    return 3


def _wbi_mixin_key(img_key: str, sub_key: str) -> str:
    original = f"{img_key}{sub_key}"
    if len(original) < 64:
        raise RuntimeError("Bilibili WBI key is incomplete")
    return "".join(original[index] for index in BILIBILI_MIXIN_KEY_ENC_TAB)[:32]


def _extract_wbi_key(url: Any) -> str:
    filename = str(url or "").rsplit("/", 1)[-1]
    return filename.split(".", 1)[0]


async def _fetch_wbi_mixin_key(client: httpx.AsyncClient) -> str:
    response = await client.get("https://api.bilibili.com/x/web-interface/nav")
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("Bilibili WBI nav data is missing")
    wbi_img = data.get("wbi_img")
    if not isinstance(wbi_img, dict):
        raise RuntimeError("Bilibili WBI image keys are missing")
    return _wbi_mixin_key(
        _extract_wbi_key(wbi_img.get("img_url")),
        _extract_wbi_key(wbi_img.get("sub_url")),
    )


def _sign_wbi_params(params: dict[str, Any], mixin_key: str) -> dict[str, Any]:
    signed = dict(params)
    signed["wts"] = int(time.time())
    sanitized = {
        key: "".join(char for char in str(value) if char not in "!'()*")
        for key, value in signed.items()
    }
    query = urllib.parse.urlencode(sorted(sanitized.items()))
    sanitized["w_rid"] = hashlib.md5(f"{query}{mixin_key}".encode()).hexdigest()
    return sanitized


async def _fetch_main_comment_page(
    client: httpx.AsyncClient,
    *,
    aid: int,
    mode: int,
    offset: str,
    mixin_key: str,
) -> dict[str, Any]:
    response = await client.get(
        "https://api.bilibili.com/x/v2/reply/wbi/main",
        params=_sign_wbi_params(
            {
                "oid": aid,
                "type": BILIBILI_VIDEO_COMMENT_TYPE,
                "mode": mode,
                "pagination_str": json.dumps({"offset": offset}, separators=(",", ":")),
                "plat": 1,
                "seek_rpid": "",
                "web_location": BILIBILI_WBI_WEB_LOCATION,
            },
            mixin_key,
        ),
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(payload.get("message") or "Bilibili WBI comment API error")
    data = payload.get("data")
    if not isinstance(data, dict):
        return {}
    return data


async def _fetch_reply_page(
    client: httpx.AsyncClient,
    *,
    aid: int,
    root_rpid: int,
    page: int,
) -> list[dict[str, Any]]:
    response = await client.get(
        "https://api.bilibili.com/x/v2/reply/reply",
        params={
            "type": BILIBILI_VIDEO_COMMENT_TYPE,
            "oid": aid,
            "root": root_rpid,
            "ps": MAX_PAGE_SIZE,
            "pn": page,
        },
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(payload.get("message") or "Bilibili reply API error")
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    replies = data.get("replies")
    return replies if isinstance(replies, list) else []


async def _fetch_all_replies(
    client: httpx.AsyncClient,
    *,
    aid: int,
    root_rpid: int,
    reply_count: int,
    up_uid: int,
    reply_limit: int | None = None,
) -> tuple[PlatformComment, ...]:
    if reply_count <= 0:
        return ()
    if reply_limit is not None:
        reply_count = min(reply_count, reply_limit)

    replies: list[PlatformComment] = []
    page = 1
    while True:
        try:
            raw_replies = await _fetch_reply_page(
                client,
                aid=aid,
                root_rpid=root_rpid,
                page=page,
            )
        except Exception as exc:
            logger.warning(
                "Failed to fetch Bilibili child replies for root %s page %s: %s",
                root_rpid,
                page,
                exc,
            )
            break
        if not raw_replies:
            break
        replies.extend(_parse_comment(item, up_uid=up_uid) for item in raw_replies)
        if len(raw_replies) < MAX_PAGE_SIZE or len(replies) >= reply_count:
            break
        page += 1

    return tuple(replies[:reply_count])


async def fetch_bilibili_comments_async(
    *,
    aid: int,
    bvid: str,
    up_uid: int,
    limit: int | None = DEFAULT_COMMENT_LIMIT,
    sort: str = "hot",
    cookie: str = "",
    reply_limit: int | None = None,
) -> PlatformCommentBundle:
    if aid <= 0:
        raise ValueError("Bilibili aid is required to fetch comments")
    if limit is not None and limit <= 0:
        raise ValueError("comment limit must be positive or None")

    try:
        return await _fetch_bilibili_comments_wbi(
            aid=aid,
            bvid=bvid,
            up_uid=up_uid,
            limit=limit,
            sort=sort,
            reply_limit=reply_limit,
        )
    except Exception as exc:
        logger.warning("Bilibili WBI comment API failed, falling back: %s", exc)

    return await _fetch_bilibili_comments_legacy(
        aid=aid,
        bvid=bvid,
        up_uid=up_uid,
        limit=limit,
        sort=sort,
        cookie=cookie,
        reply_limit=reply_limit,
    )


async def _fetch_bilibili_comments_wbi(
    *,
    aid: int,
    bvid: str,
    up_uid: int,
    limit: int | None,
    sort: str,
    reply_limit: int | None = None,
) -> PlatformCommentBundle:
    total_count = 0
    comments: list[PlatformComment] = []
    seen_rpids: set[int | str] = set()
    offset = ""
    mode = _wbi_sort_mode(sort)
    stopped_early = False

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=30.0,
        headers=_headers(),
    ) as client:
        mixin_key = await _fetch_wbi_mixin_key(client)
        while limit is None or len(comments) < limit:
            try:
                data = await _fetch_main_comment_page(
                    client,
                    aid=aid,
                    mode=mode,
                    offset=offset,
                    mixin_key=mixin_key,
                )
            except Exception:
                if comments:
                    logger.warning(
                        "Bilibili WBI comment pagination stopped after %s comments; returning partial results",
                        len(comments),
                    )
                    stopped_early = True
                    break
                raise
            cursor = data.get("cursor")
            if isinstance(cursor, dict):
                total_count = max(
                    total_count,
                    _to_int(cursor.get("all_count")),
                    _to_int(cursor.get("total")),
                )
            raw_comments = data.get("replies")
            if not isinstance(raw_comments, list) or not raw_comments:
                break

            for raw_comment in raw_comments:
                if not isinstance(raw_comment, dict):
                    continue
                comment = _parse_comment(raw_comment, up_uid=up_uid)
                if comment.rpid in seen_rpids:
                    continue
                seen_rpids.add(comment.rpid)
                reply_count = _to_int(
                    raw_comment.get("rcount"), _to_int(raw_comment.get("count"))
                )
                replies = await _fetch_all_replies(
                    client,
                    aid=aid,
                    root_rpid=comment.rpid,
                    reply_count=reply_count,
                    up_uid=up_uid,
                    reply_limit=reply_limit,
                )
                comments.append(
                    PlatformComment(
                        rpid=comment.rpid,
                        author=comment.author,
                        author_uid=comment.author_uid,
                        message=comment.message,
                        like=comment.like,
                        ctime=comment.ctime,
                        ctime_timestamp=comment.ctime_timestamp,
                        is_up_reply=comment.is_up_reply,
                        replies=replies,
                    )
                )
                if limit is not None and len(comments) >= limit:
                    break

            if not isinstance(cursor, dict) or cursor.get("is_end"):
                break
            pagination_reply = cursor.get("pagination_reply")
            next_offset = (
                pagination_reply.get("next_offset")
                if isinstance(pagination_reply, dict)
                else ""
            )
            if not next_offset or next_offset == offset:
                break
            offset = str(next_offset)

    return PlatformCommentBundle(
        bvid=bvid,
        fetched_count=len(comments),
        requested_limit=limit,
        total_count=max(total_count, len(comments)),
        sort=sort,
        comments=tuple(comments),
        aid=aid,
        platform=Platform.BILIBILI.value,
        source="wbi_api_partial" if stopped_early else "wbi_api",
    )


async def _fetch_bilibili_comments_legacy(
    *,
    aid: int,
    bvid: str,
    up_uid: int,
    limit: int | None,
    sort: str,
    cookie: str,
    reply_limit: int | None = None,
) -> PlatformCommentBundle:
    page = 1
    total_count = 0
    comments: list[PlatformComment] = []

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=30.0,
        headers=_headers(cookie),
    ) as client:
        while limit is None or len(comments) < limit:
            remaining = MAX_PAGE_SIZE if limit is None else limit - len(comments)
            page_size = min(MAX_PAGE_SIZE, max(1, remaining))
            response = await client.get(
                "https://api.bilibili.com/x/v2/reply",
                params={
                    "type": BILIBILI_VIDEO_COMMENT_TYPE,
                    "oid": aid,
                    "sort": _sort_value(sort),
                    "ps": page_size,
                    "pn": page,
                    "nohot": 1,
                },
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != 0:
                raise RuntimeError(
                    payload.get("message") or "Bilibili comment API error"
                )

            data = payload.get("data")
            if not isinstance(data, dict):
                break
            page_info = data.get("page")
            if isinstance(page_info, dict):
                total_count = _to_int(page_info.get("count"), total_count)
            raw_comments = data.get("replies")
            if not isinstance(raw_comments, list) or not raw_comments:
                break

            for raw_comment in raw_comments:
                if not isinstance(raw_comment, dict):
                    continue
                comment = _parse_comment(raw_comment, up_uid=up_uid)
                reply_count = _to_int(
                    raw_comment.get("rcount"), _to_int(raw_comment.get("count"))
                )
                replies = await _fetch_all_replies(
                    client,
                    aid=aid,
                    root_rpid=comment.rpid,
                    reply_count=reply_count,
                    up_uid=up_uid,
                    reply_limit=reply_limit,
                )
                comments.append(
                    PlatformComment(
                        rpid=comment.rpid,
                        author=comment.author,
                        author_uid=comment.author_uid,
                        message=comment.message,
                        like=comment.like,
                        ctime=comment.ctime,
                        ctime_timestamp=comment.ctime_timestamp,
                        is_up_reply=comment.is_up_reply,
                        replies=replies,
                    )
                )
                if limit is not None and len(comments) >= limit:
                    break

            if len(raw_comments) < page_size:
                break
            page += 1

    return PlatformCommentBundle(
        bvid=bvid,
        fetched_count=len(comments),
        requested_limit=limit,
        total_count=total_count,
        sort=sort,
        comments=tuple(comments),
        aid=aid,
        platform=Platform.BILIBILI.value,
        source="api",
    )


def fetch_bilibili_comments(
    *,
    aid: int,
    bvid: str,
    up_uid: int,
    limit: int | None = DEFAULT_COMMENT_LIMIT,
    sort: str = "hot",
    cookie: str = "",
    reply_limit: int | None = None,
) -> PlatformCommentBundle:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "An event loop is already running; use fetch_bilibili_comments_async instead."
        )

    return asyncio.run(
        fetch_bilibili_comments_async(
            aid=aid,
            bvid=bvid,
            up_uid=up_uid,
            limit=limit,
            sort=sort,
            cookie=cookie,
            reply_limit=reply_limit,
        )
    )


def fetch_comments_with_login(
    *,
    aid: int,
    bvid: str,
    up_uid: int,
    limit: int | None = DEFAULT_COMMENT_LIMIT,
    sort: str = "hot",
    reply_limit: int | None = None,
) -> PlatformCommentBundle:
    # Cookie 自动取导入好的登录态，没有就匿名，结果照常返回
    return fetch_bilibili_comments(
        aid=aid,
        bvid=bvid,
        up_uid=up_uid,
        limit=limit,
        sort=sort,
        cookie=bilibili_cookie_string(),
        reply_limit=reply_limit,
    )


def write_comments_json(bundle: PlatformCommentBundle, path: Path) -> Path:
    path.write_text(
        json.dumps(asdict(bundle), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def comments_to_markdown(bundle: PlatformCommentBundle) -> str:
    lines = [
        "# Bilibili 精选评论",
        "",
        f"- 资源: {bundle.bvid}",
        f"- 排序: {bundle.sort}",
        f"- 已抓取主评论: {bundle.fetched_count}",
        f"- 已抓取子评论: {count_comment_replies(bundle)}",
        f"- 评论区总数: {bundle.total_count}",
        f"- 来源: {bundle.source}",
        "",
    ]
    if bundle.aid:
        lines.insert(3, f"- AID: {bundle.aid}")
    if not bundle.comments:
        lines.append("暂无可用评论。")
        return "\n".join(lines).rstrip() + "\n"

    for index, comment in enumerate(bundle.comments, start=1):
        prefix = "**UP主回复** " if comment.is_up_reply else ""
        lines.append(f"## {index}. {prefix}{comment.author}")
        lines.append(f"- 点赞: {comment.like}")
        if comment.ctime:
            lines.append(f"- 时间: {comment.ctime}")
        lines.append("")
        message = f"**{comment.message}**" if comment.is_up_reply else comment.message
        lines.append(message or "(空评论)")
        lines.append("")
        if comment.replies:
            lines.append("子评论：")
            for reply in comment.replies:
                reply_prefix = "**UP主回复** " if reply.is_up_reply else ""
                reply_message = (
                    f"**{reply.message}**" if reply.is_up_reply else reply.message
                )
                lines.append(
                    f"- {reply_prefix}{reply.author}（点赞 {reply.like}）：{reply_message or '(空评论)'}"
                )
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_comments_markdown(bundle: PlatformCommentBundle, path: Path) -> Path:
    path.write_text(comments_to_markdown(bundle), encoding="utf-8")
    return path


__all__ = [
    "DEFAULT_COMMENT_LIMIT",
    "BilibiliComment",
    "BilibiliCommentBundle",
    "PlatformComment",
    "PlatformCommentBundle",
    "comments_to_markdown",
    "count_comment_replies",
    "count_up_replies",
    "fetch_bilibili_comments",
    "fetch_bilibili_comments_async",
    "fetch_comments_with_login",
    "write_comments_json",
    "write_comments_markdown",
]
