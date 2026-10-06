from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# 状态取值：missing 是找不到，fail 是找到了但跑不通，两者补法不同，不能合并
OK = "ok"
WARN = "warn"
MISSING = "missing"
FAIL = "fail"
SKIP = "skip"

GROUPS: tuple[str, ...] = ("python", "binary", "ffmpeg", "gpu", "stt", "bilibili", "network")

GROUP_TITLES = {
    "python": "Python 依赖",
    "binary": "外部程序",
    "ffmpeg": "ffmpeg 烟测",
    "gpu": "GPU",
    "stt": "语音识别",
    "bilibili": "B 站",
    "network": "网络",
}

FFMPEG_HINT = "安装 FFmpeg 并加入 PATH，或用 FFMPEG_PATH / FFPROBE_PATH 指定位置"
MODEL_HINT = "把权重放进工程根目录的 models/ 下"

# 挡住某条命令的检查项算必修；没有 blocks 的算选修，缺了只记进 warnings
INPUT_BLOCKS = ("ihatevideos-input",)
DOWNLOAD_BLOCKS = ("ihatevideos-download",)
MEDIA_BLOCKS = ("ihatevideos-media", "ihatevideos-summarize", "ihatevideos-stt")
STT_BLOCKS = ("ihatevideos-stt",)


def one_line(text: str, limit: int = 200) -> str:
    """把多行错误压成一行，方便塞进报告的一行里。"""
    joined = " ".join(text.split())
    return joined if len(joined) <= limit else joined[: limit - 1] + "…"


def parse_groups(raw: str | None) -> list[str]:
    """把 --only 的取值解析成分组名，顺序按 GROUPS 声明的顺序。"""
    if raw is None:
        return list(GROUPS)
    picked: list[str] = []
    for item in raw.split(","):
        name = item.strip()
        if not name:
            continue
        if name not in GROUPS:
            raise ValueError(f"没有这个分组：{name}；可用的是：{', '.join(GROUPS)}")
        if name not in picked:
            picked.append(name)
    if not picked:
        raise ValueError("--only 没有给出任何分组")
    return [group for group in GROUPS if group in picked]


@dataclass(frozen=True)
class Check:
    group: str
    name: str
    state: str
    detail: str = ""
    blocks: tuple[str, ...] = ()
    hint: str = ""

    @property
    def required(self) -> bool:
        # 挡住某条命令的算必修，其余算选修：选修缺了不该判死整个环境
        return bool(self.blocks)

    @property
    def broken(self) -> bool:
        return self.state in (MISSING, FAIL)

    def to_json(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "name": self.name,
            "state": self.state,
            "detail": self.detail,
            "blocks": list(self.blocks),
            "hint": self.hint,
            "required": self.required,
        }


@dataclass(frozen=True)
class Report:
    project_root: str
    checks: tuple[Check, ...]

    @property
    def blockers(self) -> tuple[Check, ...]:
        return tuple(item for item in self.checks if item.required and item.broken)

    @property
    def warnings(self) -> tuple[Check, ...]:
        return tuple(
            item for item in self.checks if item.state == WARN or (not item.required and item.broken)
        )

    @property
    def ready(self) -> bool:
        return not self.blockers

    def by_group(self) -> list[tuple[str, list[Check]]]:
        grouped: list[tuple[str, list[Check]]] = []
        for group in GROUPS:
            items = [item for item in self.checks if item.group == group]
            if items:
                grouped.append((group, items))
        return grouped

    def to_json(self) -> dict[str, Any]:
        return {
            "project_root": self.project_root,
            "ready": self.ready,
            "blockers": [item.name for item in self.blockers],
            "warnings": [item.name for item in self.warnings],
            "checks": [item.to_json() for item in self.checks],
        }
