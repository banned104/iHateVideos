import logging
from http.cookiejar import MozillaCookieJar
from pathlib import Path

import httpx

from ..paths import find_project_root
from .platform import Platform

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126 Safari/537.36"
)
# 旧名字保留：subtitle.py 与 doctor 都按这个引用
BILIBILI_USER_AGENT = BROWSER_USER_AGENT
CONFIG_SUBDIR = ("temp", "config")
LOGIN_CHECK_TIMEOUT_SECONDS = 30.0
# 目录里可能混进别的大文件，超过这个大小就不当 cookies 试解析
MAX_COOKIES_FILE_BYTES = 1024 * 1024
# 提示用户用什么导出 cookies；CLI 各处的提示都引用这一句
COOKIES_EXPORT_HINT = "用 Chrome 插件「Get cookies.txt LOCALLY」导出一份 cookies.txt"

# 每个平台认哪些域名、留哪些字段、缺了哪个字段就不算可用
COOKIE_DOMAINS: dict[Platform, tuple[str, ...]] = {
    Platform.BILIBILI: ("bilibili.com",),
    Platform.YOUTUBE: ("youtube.com",),
}
WANTED_COOKIES: dict[Platform, tuple[str, ...]] = {
    Platform.BILIBILI: ("SESSDATA", "bili_jct", "DedeUserID", "buvid3", "buvid4"),
    Platform.YOUTUBE: (
        "LOGIN_INFO",
        "SID",
        "HSID",
        "SSID",
        "APISID",
        "SAPISID",
        "__Secure-1PSID",
        "__Secure-3PSID",
    ),
}
REQUIRED_COOKIES: dict[Platform, str] = {
    Platform.BILIBILI: "SESSDATA",
    Platform.YOUTUBE: "LOGIN_INFO",
}
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
YOUTUBE_ACCOUNT_URL = "https://www.youtube.com/account"
GOOGLE_LOGIN_HOST = "accounts.google.com"


def config_dir() -> Path:
    """放 cookies 文件的目录：工程根下的 temp/config。"""
    return find_project_root().joinpath(*CONFIG_SUBDIR)


def _domain_matches(domain: str, suffixes: tuple[str, ...]) -> bool:
    return any(domain == suffix or domain.endswith(f".{suffix}") for suffix in suffixes)


def load_cookies(cookies_file: Path | str, platform: Platform = Platform.BILIBILI) -> dict[str, str]:
    """用标准库解析 Netscape cookies.txt，取出该平台需要的字段。"""
    path = Path(cookies_file)
    if not path.is_file():
        raise FileNotFoundError(f"Cookie 文件不存在：{path}")
    jar = MozillaCookieJar(str(path))
    jar.load(ignore_discard=True, ignore_expires=True)
    wanted = WANTED_COOKIES[platform]
    found: dict[str, str] = {}
    for cookie in jar:
        if not _domain_matches(cookie.domain.lower(), COOKIE_DOMAINS[platform]):
            continue
        if cookie.name in wanted and cookie.value:
            found.setdefault(cookie.name, cookie.value)
    return found


def load_bilibili_cookies(cookies_file: Path | str) -> dict[str, str]:
    """B 站专用入口，内部走 load_cookies。"""
    return load_cookies(cookies_file, Platform.BILIBILI)


def find_cookies_file(platform: Platform = Platform.BILIBILI) -> Path | None:
    """在配置目录里找一份该平台可用的 cookies 文件，取最近修改的那份。"""
    directory = config_dir()
    if not directory.is_dir():
        return None
    required = REQUIRED_COOKIES[platform]
    candidates = [
        item
        for item in directory.iterdir()
        if item.is_file() and item.stat().st_size <= MAX_COOKIES_FILE_BYTES
    ]
    for path in sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            values = load_cookies(path, platform)
        except (OSError, ValueError) as exc:
            logger.debug("跳过不是 Netscape cookies 的文件 %s：%s", path.name, exc)
            continue
        if values.get(required):
            return path
    return None


def credential_data(platform: Platform = Platform.BILIBILI) -> dict[str, str]:
    """读当前生效的 cookies 字段；没有可用文件时返回空字典。"""
    path = find_cookies_file(platform)
    if path is None:
        return {}
    return load_cookies(path, platform)


def credential_status(platform: Platform = Platform.BILIBILI) -> dict:
    # 只返回状态与长度，不返回密钥内容
    directory = config_dir()
    path = find_cookies_file(platform)
    if path is None:
        if not directory.is_dir():
            return {"state": "missing", "dir": str(directory)}
        names = sorted(item.name for item in directory.iterdir() if item.is_file())
        if not names:
            return {"state": "missing", "dir": str(directory)}
        return {
            "state": "empty",
            "dir": str(directory),
            "files": names,
            "cookie_name": REQUIRED_COOKIES[platform],
        }
    required = REQUIRED_COOKIES[platform]
    values = load_cookies(path, platform)
    return {
        "state": "ok",
        "path": str(path),
        "cookie_name": required,
        "cookie_len": len(values.get(required, "")),
    }


def cookie_header(data: dict[str, str], platform: Platform = Platform.BILIBILI) -> str:
    return "; ".join(
        f"{name}={data[name]}" for name in WANTED_COOKIES[platform] if data.get(name)
    )


def bilibili_cookie_string() -> str:
    # 给评论接口用的 Cookie 头：有登录态就带上，没有就匿名，调用方不中断
    data = credential_data(Platform.BILIBILI)
    parts = []
    if data.get("SESSDATA"):
        parts.append(f"SESSDATA={data['SESSDATA']}")
    if data.get("bili_jct"):
        parts.append(f"bili_jct={data['bili_jct']}")
    return "; ".join(parts)


def verify_bilibili_login(timeout_seconds: float = LOGIN_CHECK_TIMEOUT_SECONDS) -> tuple[bool, str]:
    """用当前 cookies 调一次 B站 nav 接口，确认登录态在服务端是否仍然有效。"""
    data = credential_data(Platform.BILIBILI)
    required = REQUIRED_COOKIES[Platform.BILIBILI]
    if not data.get(required):
        return False, f"没有可用的 cookies 文件，{COOKIES_EXPORT_HINT} 复制到 {config_dir()}"
    headers = {
        "User-Agent": BILIBILI_USER_AGENT,
        "Referer": "https://www.bilibili.com/",
        "Cookie": cookie_header(data, Platform.BILIBILI),
    }
    try:
        response = httpx.get(NAV_URL, headers=headers, timeout=timeout_seconds)
        payload = response.json()
    except httpx.HTTPError as exc:
        return False, f"检查登录态时网络请求失败：{exc}"
    except ValueError as exc:
        return False, f"B站返回了无法解析的数据：{exc}"
    if payload.get("code") != 0:
        return False, f"B站返回错误 {payload.get('code')}：{payload.get('message', '')}"
    body = payload.get("data") or {}
    if not body.get("isLogin"):
        return False, f"这份 cookies 在 B站已经失效，{COOKIES_EXPORT_HINT} 重新导出一份"
    return True, str(body.get("uname") or "已登录")


def verify_youtube_login(timeout_seconds: float = LOGIN_CHECK_TIMEOUT_SECONDS) -> tuple[bool, str]:
    """带 cookies 请求 YouTube 账号页；被送到 Google 登录页说明这份 cookies 已经不管用。"""
    data = credential_data(Platform.YOUTUBE)
    required = REQUIRED_COOKIES[Platform.YOUTUBE]
    if not data.get(required):
        return False, f"没有可用的 cookies 文件，{COOKIES_EXPORT_HINT} 复制到 {config_dir()}"
    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Cookie": cookie_header(data, Platform.YOUTUBE),
    }
    try:
        response = httpx.get(
            YOUTUBE_ACCOUNT_URL,
            headers=headers,
            timeout=timeout_seconds,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        return False, f"检查登录态时网络请求失败：{exc}"
    host = (response.url.host or "").lower()
    if host == GOOGLE_LOGIN_HOST or host.endswith(f".{GOOGLE_LOGIN_HOST}"):
        return False, f"这份 cookies 在 YouTube 已经失效，{COOKIES_EXPORT_HINT} 重新导出一份"
    if response.status_code >= 400:
        return False, f"YouTube 返回状态码 {response.status_code}，无法确认登录态"
    return True, "已登录"


def verify_login(
    platform: Platform = Platform.BILIBILI,
    *,
    timeout_seconds: float = LOGIN_CHECK_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    if platform == Platform.YOUTUBE:
        return verify_youtube_login(timeout_seconds=timeout_seconds)
    if platform == Platform.BILIBILI:
        return verify_bilibili_login(timeout_seconds=timeout_seconds)
    raise ValueError(f"没有为 {platform.value} 实现登录态检查")
