from __future__ import annotations

MESSAGE_MAX = 200


class DownloadError(RuntimeError):
    pass


class EngineNotFound(DownloadError):
    pass


class EngineStartError(DownloadError):
    pass


class RpcCallError(DownloadError):
    pass


class YtdlpError(DownloadError):
    pass


class YtdlpUnsupported(YtdlpError):
    pass


class BinaryInstallError(DownloadError):
    pass


# aria2 下载状态码到中文，照 DownLord errors/mapError.ts:136-157
ARIA2_DOWNLOAD_ERRORS: dict[str, str] = {
    "1": "下载失败(引擎未知错误),请重试",
    "2": "连接超时,请检查网络或代理后重试",
    "3": "资源不存在(链接可能已失效)",
    "4": "资源不存在(多次 404,链接可能已失效)",
    "5": "下载被中止(速度过慢)",
    "6": "网络错误,请检查网络或代理",
    "7": "下载未完成",
    "9": "磁盘空间不足",
    "11": "相同文件已在下载中(请勿重复添加)",
    "12": "相同内容的种子已在下载中,请勿重复添加",
    "13": "目标文件已存在",
    "16": "无法创建或写入目标文件",
    "17": "文件读写错误",
    "18": "无法创建下载目录",
    "19": "域名解析失败,请检查网络或代理",
    "24": "HTTP 认证失败",
    "26": "种子文件损坏或缺少元信息",
    "27": "磁力链接格式错误",
    "29": "服务器繁忙(过载),请稍后重试",
    "32": "文件校验失败(内容不完整)",
}

# 照 DownLord errors/mapError.ts:177-180；码 24 的出路按本工程改写，因为本工程没有浏览器扩展
ARIA2_ERROR_NEXT_STEPS: dict[str, str] = {
    "22": "链接可能已失效。若这次下载是从浏览器点过来的,回浏览器重新点一次下载即可拿到新链接。",
    "24": "该链接需要登录凭据,而直链下载不携带登录态。若它来自某个视频页,请改用 video 子命令下载该页面。",
}

# 引擎与 RPC 的文案，照 DownLord errors/errorCatalog.ts:53-76
ENGINE_MESSAGES: dict[str, str] = {
    "ENGINE_NOT_READY": "下载引擎未就绪或已退出",
    "ENGINE_TIMEOUT": "下载引擎响应超时，请重试",
    "RPC_PARAM": "下载引擎参数错误",
    "RPC_INTERNAL": "下载引擎内部错误",
    "RPC_RESOURCE": "下载引擎资源不足",
    "RPC_DUPLICATE": "下载引擎重复操作",
    "RPC_INVALID_REQUEST": "下载引擎收到无效请求",
    "RPC_METHOD_NOT_FOUND": "下载引擎方法不存在",
    "RPC_INVALID_PARAMS": "下载引擎参数无效",
    "RPC_INTERNAL_STD": "下载引擎内部错误",
    "RPC_UNAUTHORIZED": "下载引擎鉴权失败（secret 不匹配）",
    "RPC_TASK_NOT_FOUND": "下载任务不存在",
}


def readable(message: str, next_step: str | None = None) -> str:
    return f"{message}。下一步:{next_step}" if next_step else message


def tidy_aria2_message(message: str) -> str:
    flat = " ".join(message.split()).strip()
    flat = flat.removesuffix(": Error: 操作成功完成。 (0)")
    return flat[:MESSAGE_MAX] + "…" if len(flat) > MESSAGE_MAX else flat


def map_aria2_error(error_code: str, error_message: str | None = None) -> str:
    trimmed = (error_code or "").strip()
    if not trimmed.isdigit():
        return error_code
    known = ARIA2_DOWNLOAD_ERRORS.get(trimmed)
    detail = tidy_aria2_message(error_message) if error_message else ""
    base = known if known is not None else f"下载失败(引擎代码 {trimmed})"
    if detail and (trimmed == "1" or known is None):
        base = f"下载失败(引擎代码 {trimmed}):{detail}"
    return readable(base, ARIA2_ERROR_NEXT_STEPS.get(trimmed))
