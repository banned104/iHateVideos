import pytest

from ihatevideos.media.timestamps import (
    format_clip_label,
    format_seconds_label,
    format_timestamp,
    parse_seconds,
    parse_seconds_list,
)


def test_parse_seconds_accepts_colon_forms():
    assert parse_seconds("90") == 90
    assert parse_seconds(90.5) == 90.5
    assert parse_seconds("1:30") == 90
    assert parse_seconds("01:30.5") == 90.5
    assert parse_seconds("1:02:03.250") == 3723.25


def test_parse_seconds_rejects_bad_input():
    for value in ("", "1:xx", "1:2:3:4", "-1", True):
        with pytest.raises(ValueError):
            parse_seconds(value)


def test_parse_seconds_list_drops_empty_items():
    assert parse_seconds_list(" 12 , 1:30 ,, ") == [12, 90]


def test_parse_seconds_list_rejects_empty_value():
    with pytest.raises(ValueError, match="时间点列表是空的"):
        parse_seconds_list(" , ")


def test_format_timestamp_switches_to_hours():
    assert format_timestamp(0) == "00:00"
    assert format_timestamp(59.9) == "00:59"
    assert format_timestamp(3600) == "01:00:00"


def test_format_seconds_label_avoids_dots():
    assert format_seconds_label(12) == "12s"
    assert format_seconds_label(12.5) == "12p5s"


def test_format_clip_label_keeps_milliseconds():
    assert format_clip_label(30) == "00m30s"
    assert format_clip_label(59.96) == "00m59.960s"
    assert format_clip_label(60) == "01m00s"
    assert format_clip_label(3723.5) == "01h02m03.500s"


def test_format_clip_label_separates_neighbouring_ranges():
    assert format_clip_label(59.96) != format_clip_label(60)
