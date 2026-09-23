import math

_MAX_TIME_PARTS = 3


def _reject(value: object, seconds: float) -> float:
    if not math.isfinite(seconds):
        raise ValueError(f"无法解析时间：{value}")
    if seconds < 0:
        raise ValueError(f"时间不能为负数：{value}")
    return seconds


def parse_seconds(value: str | int | float) -> float:
    # 接受 90 / 90.5 / 1:30 / 01:30.5 / 1:02:03.250
    if isinstance(value, bool):
        raise ValueError(f"无法解析时间：{value}")
    if isinstance(value, (int, float)):
        return _reject(value, float(value))
    text = str(value).strip()
    if not text:
        raise ValueError("时间参数是空的")
    parts = text.split(":")
    if len(parts) > _MAX_TIME_PARTS:
        raise ValueError(f"无法解析时间：{value}")
    total = 0.0
    for part in parts:
        if not part.strip():
            raise ValueError(f"无法解析时间：{value}")
        try:
            piece = float(part)
        except ValueError as exc:
            raise ValueError(f"无法解析时间：{value}") from exc
        total = total * 60 + _reject(value, piece)
    return _reject(value, total)


def parse_seconds_list(value: str) -> list[float]:
    items = [item for item in (piece.strip() for piece in value.split(",")) if item]
    if not items:
        raise ValueError("时间点列表是空的")
    return [parse_seconds(item) for item in items]


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_seconds_label(seconds: float) -> str:
    # 目录名与文件名里不能出现小数点，整数直接写，小数用 p 代替
    if float(seconds).is_integer():
        return f"{int(seconds)}s"
    return f"{seconds:g}".replace(".", "p") + "s"


def format_clip_label(seconds: float) -> str:
    # 剪切产物文件名里的时间标签：00m30s / 01h02m03s，不足一秒的部分保留一位小数
    total = round(float(seconds), 1)
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    secs = round(total % 60, 1)
    secs_text = f"{int(secs):02d}" if float(secs).is_integer() else f"{secs:04.1f}"
    if hours:
        return f"{hours:02d}h{minutes:02d}m{secs_text}s"
    return f"{minutes:02d}m{secs_text}s"
