from __future__ import annotations

from ihatevideos.download.ytdlp_progress import parse_output_line


def test_downloading_frame_正常解析() -> None:
    parsed = parse_output_line("dlp:downloading|1000|5000|NA|2048.5")
    assert parsed is not None
    assert parsed.kind == "progress"
    frame = parsed.progress
    assert frame is not None
    assert frame.downloaded_bytes == 1000
    assert frame.total_bytes == 5000
    assert frame.speed == 2048.5
    assert frame.stream_done is False


def test_downloading_frame_缺失总量时用估算值() -> None:
    parsed = parse_output_line("dlp:downloading|1000|NA|5000|NA")
    assert parsed is not None
    frame = parsed.progress
    assert frame is not None
    assert frame.total_bytes == 5000
    assert frame.speed == 0.0
    assert frame.stream_done is False


def test_finished_frame_下载字节缺失时取总量() -> None:
    parsed = parse_output_line("dlp:finished|NA|5000|NA|NA")
    assert parsed is not None
    frame = parsed.progress
    assert frame is not None
    assert frame.downloaded_bytes == 5000
    assert frame.total_bytes == 5000
    assert frame.speed == 0.0
    assert frame.stream_done is True


def test_na_字段被当成空值而不是抛异常() -> None:
    parsed = parse_output_line("dlp:downloading|NA|NA|NA|NA")
    assert parsed is not None
    frame = parsed.progress
    assert frame is not None
    assert frame.downloaded_bytes == 0
    assert frame.total_bytes == 0
    assert frame.speed == 0.0


def test_段数不对返回_none() -> None:
    assert parse_output_line("dlp:downloading|1|2") is None
    assert parse_output_line("dlp:downloading|1|2|3|4|5") is None


def test_未知状态返回_none() -> None:
    assert parse_output_line("dlp:bogus|1|2|3|4") is None


def test_普通日志行返回_none() -> None:
    assert parse_output_line("[info] Writing video subtitles to: a.zh.srt") is None
    assert parse_output_line("") is None
    assert parse_output_line("   ") is None
    assert parse_output_line("random text") is None


def test_postprocess_标记行() -> None:
    assert parse_output_line("[Merger] Merging formats into \"a.mp4\"").kind == "postprocess"
    assert parse_output_line("[ExtractAudio] Destination: a.mp3").kind == "postprocess"
    assert parse_output_line("[FixupM3u8] Fixing MPEG-TS in MP4").kind == "postprocess"
    assert parse_output_line("[Metadata] Adding metadata to a.mp4").kind == "postprocess"
    assert parse_output_line("Deleting original file a.webm (pass -k to keep)").kind == "postprocess"


def test_转义_json_路径行() -> None:
    parsed = parse_output_line(r'"C:\\tmp\\a.mp4"')
    assert parsed is not None
    assert parsed.kind == "destination"
    assert parsed.filepath == "C:\\tmp\\a.mp4"


def test_转义_json_中文路径行() -> None:
    parsed = parse_output_line(r'"C:\\\u4e2d\u6587\\a.mp4"')
    assert parsed is not None
    assert parsed.kind == "destination"
    assert parsed.filepath == "C:\\中文\\a.mp4"


def test_裸绝对路径行() -> None:
    parsed = parse_output_line("C:\\tmp\\a.mp4")
    assert parsed is not None
    assert parsed.kind == "destination"
    assert parsed.filepath == "C:\\tmp\\a.mp4"


def test_已下载提示行() -> None:
    parsed = parse_output_line("[download] C:\\tmp\\a.mp4 has already been downloaded")
    assert parsed is not None
    assert parsed.kind == "destination"
    assert parsed.filepath == "C:\\tmp\\a.mp4"


def test_相对路径目的地行返回_none() -> None:
    assert parse_output_line("[download] Destination: a.mp4") is None


def test_实际选中格式行() -> None:
    parsed = parse_output_line("[info] BV1AmhD6wEpx: Downloading 1 format(s): 100026+30280")
    assert parsed is not None
    assert parsed.kind == "formats"
    assert parsed.formats == "100026+30280"


def test_格式行缺前缀返回_none() -> None:
    assert parse_output_line("Downloading 1 format(s): 30016") is None
