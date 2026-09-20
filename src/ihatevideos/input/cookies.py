import json
import os
import time
from http.cookiejar import MozillaCookieJar
from pathlib import Path

from bili_cli.auth import CREDENTIAL_FILE, save_credential
from bilibili_api.utils.network import Credential

BILIBILI_COOKIES_FILE_ENV = "BILIBILI_COOKIES_FILE"
CREDENTIAL_TTL_DAYS = 7
WANTED_COOKIES = ("SESSDATA", "bili_jct", "DedeUserID", "buvid3", "buvid4")


def credential_status() -> dict:
    # 只返回状态与长度，不返回密钥内容
    if not CREDENTIAL_FILE.exists():
        return {"state": "missing", "path": str(CREDENTIAL_FILE)}
    try:
        data = json.loads(CREDENTIAL_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {"state": "broken", "path": str(CREDENTIAL_FILE)}
    if not data.get("sessdata"):
        return {"state": "empty", "path": str(CREDENTIAL_FILE)}
    age_days = (time.time() - data.get("saved_at", 0)) / 86400
    state = "stale" if age_days > CREDENTIAL_TTL_DAYS else "ok"
    return {
        "state": state,
        "path": str(CREDENTIAL_FILE),
        "age_days": round(age_days, 1),
        "sessdata_len": len(data.get("sessdata", "")),
    }


def load_bilibili_cookies(cookies_file: Path | str) -> dict[str, str]:
    # 用标准库解析 Netscape cookies.txt，不手写解析
    path = Path(cookies_file).expanduser()
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


def import_bilibili_cookies(cookies_file: Path | str | None = None) -> Path:
    # 与 video-knowledge-agent 同约定：默认读 BILIBILI_COOKIES_FILE
    if cookies_file is None:
        configured = os.environ.get(BILIBILI_COOKIES_FILE_ENV, "").strip()
        if not configured:
            raise ValueError("没有指定 Cookie 文件：传文件路径或设置 BILIBILI_COOKIES_FILE")
        cookies_file = configured
    values = load_bilibili_cookies(cookies_file)
    if not values.get("SESSDATA"):
        raise ValueError(f"{cookies_file} 里没有 SESSDATA，先在浏览器登录 B 站再导出")
    save_credential(
        Credential(
            sessdata=values["SESSDATA"],
            bili_jct=values.get("bili_jct", ""),
            dedeuserid=values.get("DedeUserID", ""),
            buvid3=values.get("buvid3", ""),
        )
    )
    return CREDENTIAL_FILE
