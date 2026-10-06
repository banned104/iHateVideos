from pathlib import Path

import pytest

from ihatevideos.summarize import (
    SummarizeError,
    asset_path,
    asset_reference,
    assets_dir,
    find_placeholder_seconds,
    find_placeholders,
    insert_images,
    list_templates,
    read_template,
    time_label,
)


def test_time_label_pads_minutes_and_seconds():
    assert time_label(12) == "0012s"
    assert time_label(90) == "0130s"
    assert time_label(6030) == "10030s"
    assert time_label(72.75) == "0112s"


def test_asset_path_sits_next_to_markdown():
    md = Path("temp/2026-10-08-函数对象-BV1/en.md").resolve()
    image = asset_path(md, 12)
    assert image == md.parent / "assets" / "en-0012s.jpg"
    assert assets_dir(md) == md.parent / "assets"


def test_asset_reference_uses_forward_slash_and_name_only():
    image = Path("temp/notes/assets/en-0012s.jpg")
    assert asset_reference(image) == "assets/en-0012s.jpg"


def test_find_placeholders_reads_time_and_caption():
    text = "前<!-- FRAME: 12:30 | 结构图 -->后"
    found = find_placeholders(text)
    assert len(found) == 1
    assert found[0].seconds == 750
    assert found[0].caption == "结构图"
    assert found[0].raw == "<!-- FRAME: 12:30 | 结构图 -->"


def test_find_placeholders_accepts_bare_seconds_and_no_caption():
    found = find_placeholders("<!--FRAME:12-->")
    assert len(found) == 1
    assert found[0].seconds == 12
    assert found[0].caption == ""


def test_find_placeholders_ignores_other_comments():
    assert find_placeholders("<!-- 普通注释 -->") == []


def test_find_placeholder_seconds_dedupes_and_keeps_order():
    text = "<!-- FRAME: 90 -->\n<!-- FRAME: 12 -->\n<!-- FRAME: 01:30 -->"
    assert find_placeholder_seconds(text) == [90, 12]


def test_insert_images_replaces_placeholder_when_image_exists(tmp_path):
    md = tmp_path / "函数对象.md"
    md.write_text("正文\n\n<!-- FRAME: 00:12 | 结构图 -->\n", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "函数对象-0012s.jpg").write_bytes(b"jpeg")

    result = insert_images(md)

    assert result["changed"] is True
    assert result["missing"] == []
    assert md.read_text(encoding="utf-8") == "正文\n\n![结构图](assets/函数对象-0012s.jpg)\n"


def test_insert_images_keeps_placeholder_when_image_missing(tmp_path):
    md = tmp_path / "函数对象.md"
    original = "正文\n\n<!-- FRAME: 00:12 | 结构图 -->\n"
    md.write_text(original, encoding="utf-8")

    result = insert_images(md)

    assert result["changed"] is False
    assert len(result["missing"]) == 1
    assert result["missing"][0]["timestamp"] == "00:12"
    assert md.read_text(encoding="utf-8") == original


def test_insert_images_leaves_file_untouched_without_placeholders(tmp_path):
    md = tmp_path / "notes.md"
    md.write_text("没有任何占位符。\n", encoding="utf-8")

    result = insert_images(md)

    assert result["changed"] is False
    assert result["inserted"] == []
    assert result["missing"] == []


def test_insert_images_reports_missing_markdown(tmp_path):
    with pytest.raises(FileNotFoundError):
        insert_images(tmp_path / "nope.md")


def test_list_templates_finds_markdown_files_in_given_root(tmp_path):
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "study-notes.md").write_text(
        "# 教学视频笔记\n\n正文。\n", encoding="utf-8"
    )
    (tmp_path / "templates" / "podcast.md").write_text("# 播客\n", encoding="utf-8")

    items = list_templates(tmp_path)

    assert [item.name for item in items] == ["podcast", "study-notes"]
    assert items[0].title == "播客"
    assert items[1].title == "教学视频笔记"
    assert items[1].body == "正文。\n"


def test_list_templates_returns_empty_when_directory_absent(tmp_path):
    assert list_templates(tmp_path) == []


def test_read_template_accepts_name_without_extension(tmp_path):
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "meeting.md").write_text("# 会议\n\n正文。\n", encoding="utf-8")

    template = read_template("meeting", tmp_path)

    assert template.name == "meeting"
    assert template.title == "会议"


def test_read_template_reports_available_names(tmp_path):
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "meeting.md").write_text("# 会议\n", encoding="utf-8")

    with pytest.raises(SummarizeError) as info:
        read_template("nope", tmp_path)

    assert "meeting" in str(info.value)


def test_read_template_rejects_empty_name(tmp_path):
    with pytest.raises(SummarizeError):
        read_template("   ", tmp_path)
