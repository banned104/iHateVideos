import logging
from http.cookiejar import MozillaCookieJar
from pathlib import Path

import httpx

from ..paths import find_project_root

logger = logging.getLogger(__name__)

BILIBILI_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126 Safari/537.36"
)
CONFIG_SUBDIR = ("temp", "config")
WANTED_COOKIES = ("SESSDATA", "bili_jct", "DedeUserID", "buvid3", "buvid4")
REQUIRED_COOKIE = "SESSDATA"
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
LOGIN_CHECK_TIMEOUT_SECONDS = 30.0
# 目录里可能混进别的大文件，超过这个大小就不当 cookies 试解析
MAX_COOKIES_FILE_BYTES = 1024 * 1024


def config_dir() -> Path:
    """放 cookies 文件的目录：工程根下的 temp/config。"""
    return find_project_root().joinpath(*CONFIG_SUBDIR)


def load_bilibili_cookies(cookies_file: Path | str) -> dict[str, str]:
    """用标准库解析 Netscape cookies.txt，取出 B 站需要的字段。"""
    path = Path(cookies_file)
    if not path.is_file():
        raise FileNotFoundError(f"Cookie 文件不存在：{path}")
    jar = MozillaCookieJar(str(path))
    jar.load(ignore_discard=True, ignore_expires=True)
    found: dict[str, str] = {}
    for cookie in jar:
        domain = cookie.domain.lower()
        if domain != "bilibili.com" and not domain.endswith(".bilibili.com"):
            continue
        if cookie.name in WANTED_COOKIES and cookie.value:
            found.setdefault(cookie.name, cookie.value)
    return found


def find_cookies_file() -> Path | None:
    """在配置目录里找一份含 SESSDATA 的 cookies 文件，取最近修改的那份。"""
    directory = config_dir()
    if not directory.is_dir():
        return None
    candidates = [
        item
        for item in directory.iterdir()
        if item.is_file() and item.stat().st_size <= MAX_COOKIES_FILE_BYTES
    ]
    for path in sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            values = load_bilibili_cookies(path)
        except (OSError, ValueError) as exc:
            logger.debug("跳过不是 Netscape cookies 的文件 %s：%s", path.name, exc)
            continue
        if values.get(REQUIRED_COOKIE):
            return path
    return None


def credential_data() -> dict[str, str]:
    """读当前生效的 cookies 字段；没有可用文件时返回空字典。"""
    path = find_cookies_file()
    if path is None:
        return {}
    return load_bilibili_cookies(path)


def credential_status() -> dict:
    # 只返回状态与长度，不返回密钥内容
    directory = config_dir()
    path = find_cookies_file()
    if path is None:
        if not directory.is_dir():
            return {"state": "missing", "dir": str(directory)}
        names = sorted(item.name for item in directory.iterdir() if item.is_file())
        if not names:
            return {"state": "missing", "dir": str(directory)}
        return {"state": "empty", "dir": str(directory), "files": names}
    values = load_bilibili_cookies(path)
    return {
        "state": "ok",
        "path": str(path),
        "sessdata_len": len(values.get(REQUIRED_COOKIE, "")),
    }


def cookie_header(data: dict[str, str]) -> str:
    pairs = (
        ("SESSDATA", data.get("SESSDATA")),
        ("bili_jct", data.get("bili_jct")),
        ("DedeUserID", data.get("DedeUserID")),
        ("buvid3", data.get("buvid3")),
        ("buvid4", data.get("buvid4")),
    )
    return "; ".join(f"{name}={value}" for name, value in pairs if value)


def bilibili_cookie_string() -> str:
    # 给评论接口用的 Cookie 头：有登录态就带上，没有就匿名，调用方不中断
    data = credential_data()
    parts = []
    if data.get("SESSDATA"):
        parts.append(f"SESSDATA={data['SESSDATA']}")
    if data.get("bili_jct"):
        parts.append(f"bili_jct={data['bili_jct']}")
    return "; ".join(parts)


def verify_login(timeout_seconds: float = LOGIN_CHECK_TIMEOUT_SECONDS) -> tuple[bool, str]:
    """用当前 cookies 调一次 B站 nav 接口，确认登录态在服务端是否仍然有效。"""
    data = credential_data()
    if not data.get(REQUIRED_COOKIE):
        return False, f"没有可用的 cookies 文件，把导出的 cookies.txt 复制到 {config_dir()}"
    headers = {
        "User-Agent": BILIBILI_USER_AGENT,
        "Referer": "https://www.bilibili.com/",
        "Cookie": cookie_header(data),
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
        return False, "这份 cookies 在 B站已经失效，重新从浏览器导出一份"
    return True, str(body.get("uname") or "已登录")
