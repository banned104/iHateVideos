from pathlib import Path

import pytest

from ihatevideos.download.models import SubtitleTrack
from ihatevideos.input.subtitle import SubtitleItem
from ihatevideos.input.youtube_subtitle import (
    parse_json3,
    parse_subtitle_file,
    parse_vtt,
    pick_subtitle_track,
    track_sort_key,
)

DATA = Path(__file__).parent / "data"
DATA = Path(__file__).parent / "fixtures"

def track(lang: str, *, auto: bool = False, formats: list[str] | None = None) -> SubtitleTrack:
    return SubtitleTrack(
        lang=lang, name=lang, auto=auto, formats=["vtt"] if formats is None else formats
    )


def test_pick_subtitle_track_prefers_manual_over_auto():
    assert pick_subtitle_track([track("zh-CN", auto=True), track("en")]).lang == "en"


def test_pick_subtitle_track_orders_languages():
    tracks = [track("en", auto=True), track("zh-TW", auto=True), track("zh-CN", auto=True)]
    assert pick_subtitle_track(tracks).lang == "zh-CN"


def test_pick_subtitle_track_skips_tracks_without_formats():
    assert pick_subtitle_track([track("zh-CN", formats=[]), track("en")]).lang == "en"
    assert pick_subtitle_track([]) is None
    assert pick_subtitle_track([track("zh-CN", formats=[])]) is None


def test_track_sort_key_puts_manual_first():
    assert track_sort_key(track("en")) < track_sort_key(track("zh-CN", auto=True))


def test_parse_json3_reads_events_and_skips_noise():
    text = (DATA / "youtube-subtitle-sample.json3").read_text(encoding="utf-8")
    items = parse_json3(text)
    assert [item.text for item in items] == ["[Music]", "This is a three."]
    assert items[0] == SubtitleItem(start_ms=0, end_ms=2510, text="[Music]")
    assert items[1].start_ms == 4400
    assert items[1].end_ms == 8559


def test_parse_json3_rejects_payload_without_events():
    with pytest.raises(ValueError, match="没有 events"):
        parse_json3("{}")


def test_parse_vtt_reads_captions_and_merges_lines():
    items = parse_vtt(DATA / "youtube-subtitle-sample.vtt")
    assert items[0] == SubtitleItem(start_ms=4350, end_ms=5570, text="这 是一个3")
    assert items[1].start_ms == 5780
    assert items[1].end_ms == 11050
    assert items[1].text == "一个字迹歪斜 28x28像素 超低分辨率的3"


def test_parse_subtitle_file_dispatches_by_suffix():
    assert parse_subtitle_file(DATA / "youtube-subtitle-sample.vtt")[0].text == "这 是一个3"
    assert len(parse_subtitle_file(DATA / "youtube-subtitle-sample.json3")) == 2
    with pytest.raises(ValueError, match="不认识的字幕格式"):
        parse_subtitle_file(DATA / "youtube-subtitle-sample.srt")
