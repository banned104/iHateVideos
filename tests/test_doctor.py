import json

import pytest

from ihatevideos.doctor import GROUPS, Check, Report, parse_groups, render_json, render_text
from ihatevideos.doctor.checks import run_checks
from ihatevideos.doctor.models import FAIL, MISSING, OK, SKIP, WARN, one_line


def test_parse_groups_defaults_to_all():
    assert parse_groups(None) == list(GROUPS)


def test_parse_groups_follows_declared_order():
    assert parse_groups("network,python") == ["python", "network"]


def test_parse_groups_drops_duplicates():
    assert parse_groups("python,python") == ["python"]


def test_parse_groups_rejects_unknown_name():
    with pytest.raises(ValueError, match="没有这个分组"):
        parse_groups("nope")


def test_parse_groups_rejects_empty_value():
    with pytest.raises(ValueError, match="没有给出任何分组"):
        parse_groups(" , ")


def test_required_follows_blocks():
    assert not Check("python", "httpx", OK).required
    assert Check("python", "httpx", MISSING, blocks=("ihatevideos-input",)).required


def test_broken_covers_missing_and_fail_only():
    assert Check("a", "b", MISSING).broken
    assert Check("a", "b", FAIL).broken
    assert not Check("a", "b", OK).broken
    assert not Check("a", "b", WARN).broken
    assert not Check("a", "b", SKIP).broken


def test_report_ready_ignores_optional_gap():
    report = Report("C:/x", (Check("python", "httpx", OK), Check("network", "代理", MISSING)))
    assert report.ready
    assert [item.name for item in report.warnings] == ["代理"]


def test_report_blocker_stops_ready():
    report = Report("C:/x", (Check("python", "httpx", MISSING, blocks=("ihatevideos-input",)),))
    assert not report.ready
    assert [item.name for item in report.blockers] == ["httpx"]


def test_report_warn_counts_as_warning_not_blocker():
    report = Report("C:/x", (Check("binary", "ffmpeg 一致性", WARN),))
    assert report.ready
    assert [item.name for item in report.warnings] == ["ffmpeg 一致性"]


def test_report_by_group_uses_declared_order():
    checks = (Check("network", "代理", OK), Check("python", "httpx", OK))
    report = Report("C:/x", checks)
    assert [group for group, _ in report.by_group()] == ["python", "network"]


def test_report_by_group_skips_empty_groups():
    report = Report("C:/x", (Check("python", "httpx", OK),))
    assert [group for group, _ in report.by_group()] == ["python"]


def test_report_json_shape():
    report = Report("C:/x", (Check("python", "httpx", MISSING, blocks=("ihatevideos-input",)),))
    payload = json.loads(render_json(report))
    assert payload["project_root"] == "C:/x"
    assert payload["ready"] is False
    assert payload["blockers"] == ["httpx"]
    assert payload["checks"][0]["blocks"] == ["ihatevideos-input"]
    assert payload["checks"][0]["required"] is True


def test_render_text_lists_group_and_conclusion():
    report = Report("C:/x", (Check("python", "httpx", OK, "网络请求  0.28.1"),))
    text = render_text(report)
    assert "python  Python 依赖" in text
    assert "- ok    httpx" in text
    assert "结论：全部检查通过" in text


def test_render_text_shows_blocks_and_hint_for_broken_required():
    check = Check("python", "httpx", MISSING, blocks=("ihatevideos-input",), hint="uv sync")
    text = render_text(Report("C:/x", (check,)))
    assert "挡住：ihatevideos-input" in text
    assert "补法：uv sync" in text
    assert "结论：先补齐必修项" in text


def test_render_text_hides_blocks_for_optional_gap():
    check = Check("network", "代理", MISSING, hint="配一个代理")
    text = render_text(Report("C:/x", (check,)))
    assert "挡住：" not in text
    assert "补法：配一个代理" in text


def test_one_line_collapses_whitespace():
    assert one_line("命令失败\n  原因  是 x  ") == "命令失败 原因 是 x"


def test_one_line_truncates_to_limit():
    assert len(one_line("x" * 300)) == 200
    assert one_line("x" * 300).endswith("…")


def test_run_checks_only_runs_selected_groups(tmp_path):
    checks = run_checks(root=tmp_path, groups=["python"])
    assert {item.group for item in checks} == {"python"}
