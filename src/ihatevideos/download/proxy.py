from __future__ import annotations

import urllib.request

# 代理自动配置（PAC）脚本不能直接当作代理地址使用
PAC_SUFFIXES = (".pac", ".js")


def system_proxy() -> str | None:
    """读系统代理。Windows 上标准库会读注册表的 Internet Settings，其他平台读环境变量。"""
    proxies = urllib.request.getproxies()
    for key in ("https", "http"):
        value = proxies.get(key)
        if value and not value.lower().endswith(PAC_SUFFIXES):
            return value
    return None


def resolve_proxy(*, disabled: bool) -> str:
    """返回要下发的代理值：空字符串表示显式直连，与 DownLord 的直连档一致。"""
    if disabled:
        return ""
    return system_proxy() or ""
