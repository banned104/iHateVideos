from __future__ import annotations

import json

from .models import FAIL, GROUP_TITLES, MISSING, OK, SKIP, WARN, Report

STATE_TITLES = {
    OK: "ok",
    WARN: "warn",
    MISSING: "MISS",
    FAIL: "FAIL",
    SKIP: "skip",
}
_STATE_WIDTH = 4
_INDENT = " " * 8


def _check_line(item) -> list[str]:
    title = STATE_TITLES.get(item.state, item.state)
    line = f"- {title:<{_STATE_WIDTH}}  {item.name}"
    if item.detail:
        line += f"    {item.detail}"
    lines = [line]
    if item.blocks and item.broken:
        lines.append(f"{_INDENT}挡住：{', '.join(item.blocks)}")
    if item.hint and item.broken:
        lines.append(f"{_INDENT}补法：{item.hint}")
    return lines


def _summary(report: Report) -> str:
    blockers = report.blockers
    warnings = report.warnings
    if not blockers and not warnings:
        return "结论：全部检查通过"
    lines = ["结论：可以开始使用" if not blockers else "结论：先补齐必修项"]
    if blockers:
        lines.append(f"必修未就绪 {len(blockers)} 项：{', '.join(item.name for item in blockers)}")
    if warnings:
        lines.append(f"隐患 {len(warnings)} 项：{', '.join(item.name for item in warnings)}")
    return "\n".join(lines)


def render_text(report: Report) -> str:
    lines = [
        "iHateVideos 运行环境检查",
        f"工程根目录  {report.project_root}",
        "",
    ]
    for group, checks in report.by_group():
        lines.append(f"{group}  {GROUP_TITLES[group]}")
        for item in checks:
            lines += _check_line(item)
        lines.append("")
    lines.append(_summary(report))
    return "\n".join(lines)


def render_json(report: Report) -> str:
    return json.dumps(report.to_json(), ensure_ascii=False, indent=2)
