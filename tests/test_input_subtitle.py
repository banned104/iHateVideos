import os
from pathlib import Path

import pytest

from ihatevideos.input.cookies import (
    config_dir,
    credential_status,
    find_cookies_file,
    load_bilibili_cookies,
)
from ihatevideos.input.subtitle import (
    BilibiliSubtitleItem,
    is_ai_track,
    is_chinese_track,
    parse_subtitle_body,
    rank_subtitles,
    select_part_cid,
    track_language,
    validated_media_url,
)


def test_rank_subtitles_prefers_manual_chinese():
    tracks = [
        {"lan": "en", "subtitle_url": "//a.hdslb.com/en.json"},
        {"lan": "ai-zh", "subtitle_url": "//a.hdslb.com/ai.json"},
        {"lan": "zh-CN", "subtitle_url": "//a.hdslb.com/cn.json"},
    ]
    assert [track["lan"] for track in rank_subtitles(tracks)] == ["zh-CN", "ai-zh", "en"]


def test_rank_subtitles_orders_by_weight_inside_group():
    tracks = [
        {"lan": "zh-tw", "subtitle_url": "//a.hdslb.com/tw.json"},
        {"lan": "zh-cn", "subtitle_url": "//a.hdslb.com/cn.json"},
        {"lan": "zh-hans", "subtitle_url": "//a.hdslb.com/hans.json"},
    ]
    assert [track["lan"] for track in rank_subtitles(tracks)] == ["zh-cn", "zh-hans", "zh-tw"]


def test_rank_subtitles_drops_tracks_without_url():
    tracks = [
        {"lan": "zh-CN", "subtitle_url": ""},
        {"lan": "en", "subtitle_url": "//a.hdslb.com/en.json"},
    ]
    ranked = rank_subtitles(tracks)
    assert [track["lan"] for track in ranked] == ["en"]


def test_rank_subtitles_accepts_v2_url_field():
    tracks = [{"lan": "zh-CN", "subtitle_url_v2": "//a.hdslb.com/cn.json"}]
    assert len(rank_subtitles(tracks)) == 1


def test_track_language_falls_back_to_id_str():
    assert track_language({"id_str": "zh-CN"}) == "zh-CN"
    assert track_language({}) == "unknown"


def test_chinese_track_detection():
    assert is_chinese_track({"lan": "zh-CN"})
    assert is_chinese_track({"lan": "ai-zh"})
    assert is_chinese_track({"lan": "zho"})
    assert not is_chinese_track({"lan": "en"})


def test_ai_track_detection():
    assert is_ai_track({"lan": "ai-zh"})
    assert is_ai_track({"lan": "zh-CN", "ai_status": 1})
    assert is_ai_track({"lan": "zh-CN", "type": 1})
    assert not is_ai_track({"lan": "zh-CN"})


def test_validated_media_url_adds_scheme():
    assert (
        validated_media_url("//aisubtitle.hdslb.com/bfs/subtitle/x.json")
        == "https://aisubtitle.hdslb.com/bfs/subtitle/x.json"
    )


def test_validated_media_url_rejects_foreign_host():
    with pytest.raises(ValueError, match="不属于可信的 B站域名"):
        validated_media_url("https://example.com/x.json")


def test_validated_media_url_rejects_plain_http():
    with pytest.raises(ValueError, match="不属于可信的 B站域名"):
        validated_media_url("http://aisubtitle.hdslb.com/x.json")


def test_select_part_cid_picks_requested_page():
    pages = [{"page": 1, "cid": 111}, {"page": 2, "cid": 222}]
    assert select_part_cid(pages, 2) == 222


def test_select_part_cid_reports_missing_page():
    pages = [{"page": 1, "cid": 111}]
    with pytest.raises(ValueError, match="分P 5 不存在，该视频共 1 个分P"):
        select_part_cid(pages, 5)


def test_select_part_cid_rejects_empty_pages():
    with pytest.raises(ValueError, match="没有分P信息"):
        select_part_cid([], 1)


def test_select_part_cid_rejects_page_without_cid():
    with pytest.raises(ValueError, match="分P 1 没有 cid"):
        select_part_cid([{"page": 1}], 1)


def test_parse_subtitle_body_converts_seconds_to_milliseconds():
    items = parse_subtitle_body({"body": [{"from": 1.5, "to": 2.25, "content": " 你好 "}]})
    assert items == (BilibiliSubtitleItem(start_ms=1500, end_ms=2250, text="你好"),)


def test_parse_subtitle_body_skips_blank_content():
    items = parse_subtitle_body(
        {"body": [{"from": 0, "to": 1, "content": "   "}, {"from": 1, "to": 2, "content": "正文"}]}
    )
    assert len(items) == 1
    assert items[0].text == "正文"


def test_parse_subtitle_body_rejects_bad_shape():
    with pytest.raises(ValueError, match="格式不受支持"):
        parse_subtitle_body({"body": "not-a-list"})


def test_parse_subtitle_body_rejects_empty_body():
    with pytest.raises(ValueError, match="字幕正文为空"):
        parse_subtitle_body({"body": []})


NETSCAPE_HEADER = "# Netscape HTTP Cookie File\n"


def write_cookies(path: Path, sessdata: str) -> None:
    path.write_text(
        NETSCAPE_HEADER
        + f".bilibili.com\tTRUE\t/\tFALSE\t0\tSESSDATA\t{sessdata}\n"
        + ".bilibili.com\tTRUE\t/\tFALSE\t0\tbili_jct\tjct-value\n",
        encoding="utf-8",
    )


def make_project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    directory = tmp_path / "temp" / "config"
    directory.mkdir(parents=True)
    return directory


def test_load_bilibili_cookies_keeps_only_bilibili_domain(tmp_path):
    path = tmp_path / "cookies.txt"
    path.write_text(
        NETSCAPE_HEADER
        + ".bilibili.com\tTRUE\t/\tFALSE\t0\tSESSDATA\tbili-value\n"
        + ".example.com\tTRUE\t/\tFALSE\t0\tSESSDATA\tother-value\n",
        encoding="utf-8",
    )
    assert load_bilibili_cookies(path)["SESSDATA"] == "bili-value"


def test_find_cookies_file_picks_newest(tmp_path, monkeypatch):
    directory = make_project(tmp_path)
    older = directory / "old_cookies.txt"
    write_cookies(older, "old-value")
    newer = directory / "new_cookies.txt"
    write_cookies(newer, "new-value")
    os.utime(older, (1_000_000, 1_000_000))
    os.utime(newer, (2_000_000, 2_000_000))
    monkeypatch.chdir(tmp_path)
    assert find_cookies_file() == newer


def test_find_cookies_file_skips_files_without_sessdata(tmp_path, monkeypatch):
    directory = make_project(tmp_path)
    (directory / "notes.txt").write_text("这里不是 cookies\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert find_cookies_file() is None
    status = credential_status()
    assert status["state"] == "empty"
    assert status["files"] == ["notes.txt"]


def test_credential_status_missing_without_config_dir(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    status = credential_status()
    assert status["state"] == "missing"
    assert status["dir"] == str(config_dir())


def test_credential_status_ok_reports_sessdata_length(tmp_path, monkeypatch):
    directory = make_project(tmp_path)
    write_cookies(directory / "cookies.txt", "abcdef")
    monkeypatch.chdir(tmp_path)
    status = credential_status()
    assert status["state"] == "ok"
    assert status["sessdata_len"] == len("abcdef")


def test_config_dir_sits_under_project_root(tmp_path, monkeypatch):
    make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert config_dir() == tmp_path / "temp" / "config"
