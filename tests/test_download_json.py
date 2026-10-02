from __future__ import annotations

import pytest

from ihatevideos.download.errors import YtdlpUnsupported
from ihatevideos.download.models import FormatInfo
from ihatevideos.download.ytdlp_json import (
    parse_info_tree,
    quality_label,
    quality_tag,
    resolved_top_height,
)

完整信息树 = {
    "id": "abc123",
    "title": "示例视频",
    "duration": 212.5,
    "uploader": "某频道",
    "extractor": "BiliBili",
    "webpage_url": "https://example.com/v/abc123",
    "thumbnail": "https://example.com/t.jpg",
    "formats": [
        {
            "format_id": "137",
            "ext": "mp4",
            "height": 1080,
            "fps": 30,
            "vcodec": "avc1.640028",
            "acodec": "none",
            "filesize": 123456789,
            "tbr": 4500.5,
            "format_note": "1080p",
            "protocol": "https",
        },
        {
            "format_id": "140",
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "mp4a.40.2",
            "filesize_approx": 3000000,
            "tbr": "128",
        },
    ],
    "subtitles": {
        "zh-Hans": [
            {"ext": "vtt", "name": 123},
            {"ext": "srt", "name": "简体中文"},
        ],
    },
    "automatic_captions": {
        "en": [{"ext": "vtt", "name": "English (auto)"}],
    },
}


def _format_with_height(height: int | None) -> FormatInfo:
    return FormatInfo(
        format_id="x",
        ext=None,
        height=height,
        fps=None,
        vcodec=None,
        acodec=None,
        filesize=None,
        tbr=None,
        note=None,
        protocol=None,
    )


def test_完整信息树解析各字段() -> None:
    info = parse_info_tree(完整信息树)
    assert info.video_id == "abc123"
    assert info.title == "示例视频"
    assert info.duration_seconds == 212.5
    assert info.uploader == "某频道"
    assert info.extractor == "BiliBili"
    assert info.webpage_url == "https://example.com/v/abc123"
    assert info.thumbnail == "https://example.com/t.jpg"
    assert len(info.formats) == 2
    first = info.formats[0]
    assert first.format_id == "137"
    assert first.ext == "mp4"
    assert first.height == 1080
    assert first.fps == 30.0
    assert first.vcodec == "avc1.640028"
    assert first.acodec == "none"
    assert first.filesize == 123456789
    assert first.tbr == 4500.5
    assert first.note == "1080p"
    assert first.protocol == "https"
    assert first.quality_tag == "1080p"


def test_filesize_缺失时取_filesize_approx() -> None:
    info = parse_info_tree(完整信息树)
    second = info.formats[1]
    assert second.filesize == 3000000
    assert second.height is None
    assert second.tbr == 128.0
    assert second.quality_tag is None


def test_字幕合并顺序与非自动在前() -> None:
    info = parse_info_tree(完整信息树)
    assert len(info.subtitles) == 2
    first, second = info.subtitles
    assert first.lang == "zh-Hans"
    assert first.auto is False
    assert first.name == "简体中文"
    assert first.formats == ["vtt", "srt"]
    assert second.lang == "en"
    assert second.auto is True
    assert second.name == "English (auto)"


def test_同一语言非自动与自动都保留() -> None:
    payload = {
        "id": "x",
        "subtitles": {"zh": [{"ext": "vtt", "name": "中文"}]},
        "automatic_captions": {"zh": [{"ext": "vtt", "name": "自动中文"}]},
    }
    info = parse_info_tree(payload)
    assert len(info.subtitles) == 2
    assert [item.auto for item in info.subtitles] == [False, True]


def test_字段缺失时的兜底取名() -> None:
    payload = {"id": "onlyid", "extractor_key": "Youtube", "original_url": "https://example.com/a"}
    info = parse_info_tree(payload)
    assert info.title == "onlyid"
    assert info.extractor == "Youtube"
    assert info.webpage_url == "https://example.com/a"
    assert info.duration_seconds is None
    assert info.formats == []
    assert info.subtitles == []


def test_播放列表抛_ytdlp_unsupported() -> None:
    with pytest.raises(YtdlpUnsupported):
        parse_info_tree({"_type": "playlist", "id": "pl"})


def test_quality_tag_各分支() -> None:
    assert quality_tag(audio_only=True, format_height=720, height_cap=None) is None
    assert quality_tag(audio_only=False, format_height=720, height_cap=None) == "720p"
    assert quality_tag(audio_only=False, format_height=None, height_cap=1080) == "1080p"
    assert quality_tag(audio_only=False, format_height=None, height_cap=2160) == "最高"
    assert quality_tag(audio_only=False, format_height=None, height_cap=None) == "最高"


def test_quality_label_各分支() -> None:
    assert quality_label(audio_only=True, format_height=720, height_cap=None) == "仅音频 MP3"
    assert quality_label(audio_only=False, format_height=720, height_cap=None) == "720P"
    assert quality_label(audio_only=False, format_height=None, height_cap=1080) == "≤1080P"
    assert quality_label(audio_only=False, format_height=None, height_cap=2160) == "最高"
    assert quality_label(audio_only=False, format_height=None, height_cap=None) == "最高"


def test_resolved_top_height_有上限与无上限() -> None:
    formats = [_format_with_height(360), _format_with_height(720), _format_with_height(1080)]
    assert resolved_top_height(formats, None) == 1080
    assert resolved_top_height(formats, 720) == 720
    assert resolved_top_height(formats, 500) == 360
    assert resolved_top_height([_format_with_height(None)], None) is None
