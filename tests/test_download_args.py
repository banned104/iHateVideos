from __future__ import annotations

import pytest

from ihatevideos.download.aria2_args import (
    MAX_CONCURRENT_DOWNLOADS,
    MAX_CONNECTION_PER_SERVER,
    SPLIT,
    build_start_args,
    build_task_options,
    format_limit,
)
from ihatevideos.download.filenames import (
    name_from_url,
    predict_ext,
    sanitize_basename,
    video_filename,
)
from ihatevideos.download.models import ALLOWED_TRANSITIONS, TaskStatus
from ihatevideos.download.ytdlp_args import (
    ARIA2_DOWNLOADER_ARGS,
    CONCURRENT_FRAGMENTS,
    build_selector,
    build_subtitle_args,
    downloader_args,
    is_fragmented_protocol,
    normalize_langs,
)


def start_args(**overrides) -> list[str]:
    payload = {
        "exe": "aria2c.exe",
        "port": 6800,
        "secret": "abc",
        "download_dir": r"C:\tmp",
        "pid": 4321,
        "limit_kbps": None,
        "all_proxy": "",
    }
    payload.update(overrides)
    return build_start_args(**payload)


def test_start_args_matches_downlord_list() -> None:
    assert start_args() == [
        "aria2c.exe",
        "--enable-rpc",
        "--rpc-listen-port=6800",
        "--rpc-listen-all=false",
        "--rpc-secret=abc",
        "--continue=true",
        f"--max-connection-per-server={MAX_CONNECTION_PER_SERVER}",
        f"--split={SPLIT}",
        "--min-split-size=1M",
        "--file-allocation=none",
        "--connect-timeout=10",
        r"--dir=C:\tmp",
        "--stop-with-process=4321",
        "--auto-save-interval=1",
        f"--max-concurrent-downloads={MAX_CONCURRENT_DOWNLOADS}",
        "--all-proxy=",
    ]


def test_start_args_adds_limit_only_when_positive() -> None:
    assert "--max-download-limit=512K" not in start_args(limit_kbps=0)
    assert "--max-download-limit=512K" in start_args(limit_kbps=512)


def test_start_args_carries_proxy_value() -> None:
    assert "--all-proxy=http://127.0.0.1:7890" in start_args(all_proxy="http://127.0.0.1:7890")


def test_format_limit() -> None:
    assert format_limit(None) == "0"
    assert format_limit(0) == "0"
    assert format_limit(512) == "512K"


def test_task_options_with_and_without_filename() -> None:
    assert build_task_options(save_dir=r"C:\tmp") == {
        "dir": r"C:\tmp",
        "max-download-limit": "0",
    }
    assert build_task_options(save_dir=r"C:\tmp", filename="a.dat", limit_kbps=64) == {
        "dir": r"C:\tmp",
        "max-download-limit": "64K",
        "out": "a.dat",
    }


def test_selector_branches() -> None:
    assert build_selector(audio_only=True, format_id=None, acodec=None, height_cap=None) == (
        "bestaudio/best",
        None,
    )
    assert build_selector(audio_only=False, format_id="137", acodec="none", height_cap=None) == (
        "137+bestaudio/137",
        "mp4",
    )
    assert build_selector(audio_only=False, format_id="18", acodec="mp4a", height_cap=None) == (
        "18",
        None,
    )
    assert build_selector(audio_only=False, format_id=None, acodec=None, height_cap=720) == (
        "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "mp4",
    )
    assert build_selector(audio_only=False, format_id=None, acodec=None, height_cap=None) == (
        "best",
        None,
    )


def test_is_fragmented_protocol() -> None:
    assert is_fragmented_protocol("m3u8_native") is True
    assert is_fragmented_protocol("http_dash_segments") is True
    assert is_fragmented_protocol("https") is False
    assert is_fragmented_protocol(None) is False


def test_sanitize_basename_rules() -> None:
    assert sanitize_basename('a<b>c:d"e/f\\g|h?i*j') == "a_b_c_d_e_f_g_h_i_j"
    assert sanitize_basename("trailing. ") == "trailing"
    assert sanitize_basename("CON") == "_CON"
    assert sanitize_basename("com1.txt") == "_com1.txt"
    assert sanitize_basename("   ") == "download"
    assert sanitize_basename("标题 [720p]") == "标题 [720p]"


def test_name_from_url() -> None:
    assert name_from_url("https://host/dir/%E4%B8%AD%E6%96%87.zip?x=1") == "中文.zip"
    assert name_from_url("https://host/") == "download"


def test_predict_ext_branches() -> None:
    assert predict_ext(audio_only=True, acodec="mp4a", ext="m4a") == "mp3"
    assert predict_ext(audio_only=False, acodec=None, ext=None) == "mp4"
    assert predict_ext(audio_only=False, acodec="none", ext="mp4") == "mp4"
    assert predict_ext(audio_only=False, acodec="mp4a", ext="webm") == "webm"


def test_video_filename_with_and_without_tag() -> None:
    assert video_filename(title="标题", quality_tag="360p", ext="mp4") == "标题 [360p].mp4"
    assert video_filename(title="标题", quality_tag=None, ext="mp3") == "标题.mp3"


def test_transition_table() -> None:
    assert TaskStatus.RESOLVING in ALLOWED_TRANSITIONS[TaskStatus.QUEUED]
    assert TaskStatus.DOWNLOADING in ALLOWED_TRANSITIONS[TaskStatus.RESOLVING]
    assert TaskStatus.PROCESSING in ALLOWED_TRANSITIONS[TaskStatus.DOWNLOADING]
    assert TaskStatus.PAUSED in ALLOWED_TRANSITIONS[TaskStatus.PROCESSING]
    assert ALLOWED_TRANSITIONS[TaskStatus.COMPLETED] == frozenset()
    assert TaskStatus.DOWNLOADING not in ALLOWED_TRANSITIONS[TaskStatus.ERROR]


def test_normalize_langs() -> None:
    assert normalize_langs([" zh-Hans ", "zh-Hans", "", "en"]) == ("zh-Hans", "en")


def test_subtitle_args_empty_and_full() -> None:
    assert build_subtitle_args(langs=(), sub_format="srt", include_auto=False) == []
    assert build_subtitle_args(langs=["zh-Hans"], sub_format="srt", include_auto=False) == [
        "--write-subs",
        "--sub-langs",
        "zh-Hans",
        "--sub-format",
        "srt/best",
        "--convert-subs",
        "srt",
    ]
    assert "--write-auto-subs" in build_subtitle_args(
        langs=["en"], sub_format="srt", include_auto=True
    )


def test_downloader_args_accel_and_native() -> None:
    accel = downloader_args(accel_path="C:/bin/aria2c.exe", limit_kbps=None, proxy="")
    assert accel[:2] == ["--downloader", "C:/bin/aria2c.exe"]
    assert accel[3] == f"aria2c:{ARIA2_DOWNLOADER_ARGS} --all-proxy="

    limited = downloader_args(
        accel_path="C:/bin/aria2c.exe", limit_kbps=512, proxy="http://127.0.0.1:7890"
    )
    assert " --max-download-limit=512K" in limited[3]
    assert "--all-proxy=http://127.0.0.1:7890" in limited[3]

    native = downloader_args(accel_path=None, limit_kbps=512, proxy="")
    assert native == ["--concurrent-fragments", str(CONCURRENT_FRAGMENTS), "--limit-rate", "512K"]

    unlimited = downloader_args(accel_path=None, limit_kbps=None, proxy="")
    assert unlimited == ["--concurrent-fragments", str(CONCURRENT_FRAGMENTS)]
    assert "--limit-rate" not in unlimited


def test_download_args_order_puts_print_last() -> None:
    from ihatevideos.download.ytdlp_args import build_download_args

    args = build_download_args(
        url="https://example.com/v",
        out_dir="temp",
        output_base="标题 [360p]",
        selector="30016+bestaudio/30016",
        merge_format="mp4",
        ffmpeg_location="C:/ffmpeg.exe",
        proxy="",
        audio_only=False,
        subtitle_args=[],
        accel_path="C:/aria2c.exe",
        limit_kbps=None,
    )
    assert args[-3:] == ["--print", "after_move:%(filepath)j", "https://example.com/v"]
    assert args.index("--downloader") < args.index("--print")
    assert args[0:2] == ["-f", "30016+bestaudio/30016"]
    assert "--merge-output-format" in args


def test_task_options_reject_unknown_status() -> None:
    with pytest.raises(Exception):
        from ihatevideos.download.aria2_engine import map_status

        map_status("nonsense")
