from ihatevideos.export.markdown_fmt import format_markdown_with_markdownlint
from ihatevideos.export.timeline import extract_timeline_entries, remove_video_time_column


def test_remove_video_time_column_keeps_every_row_width():
    table = (
        "| 视频时间 | 主题 | 说明 |\n"
        "| --- | --- | --- |\n"
        "| 00:12 | 开场 | 介绍 |\n"
        "| 01:30 | 收尾 |\n"
    )

    rendered = remove_video_time_column(table)

    assert rendered.splitlines() == [
        "| 主题 | 说明 |",
        "| --- | --- |",
        "| 开场 | 介绍 |",
        "| 收尾 |  |",
    ]


def test_remove_video_time_column_returns_input_without_time_column():
    table = "| 主题 | 说明 |\n| --- | --- |\n| 开场 | 介绍 |\n"
    assert remove_video_time_column(table) == table


def test_extract_timeline_entries_reads_time_and_topic():
    table = (
        "| 视频时间 | 主题 |\n"
        "| --- | --- |\n"
        "| 00:12 | 开场 |\n"
        "| 01:30 | 收尾 |\n"
        "| 01:30 | 收尾 |\n"
    )

    entries = extract_timeline_entries(table)

    assert [(item.timestamp, item.stock_name) for item in entries] == [
        ("00:12", "开场"),
        ("01:30", "收尾"),
    ]


def test_format_markdown_ignores_missing_file(tmp_path):
    format_markdown_with_markdownlint(tmp_path / "nope.md")
