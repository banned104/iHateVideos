import pytest

from ihatevideos.input.platform import Platform
from ihatevideos.input.url_detect import detect_platform, extract_platform_id

VIDEO_ID = "MuWTmEiNe1g"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={VIDEO_ID}",
        f"https://www.youtube.com/watch?v={VIDEO_ID}&t=30s",
        f"https://www.youtube.com/watch?v={VIDEO_ID}&list=PLabc",
        f"https://youtube.com/watch?v={VIDEO_ID}",
        f"https://m.youtube.com/watch?v={VIDEO_ID}",
        f"https://music.youtube.com/watch?v={VIDEO_ID}",
        f"https://WWW.YouTube.com/watch?v={VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}?t=30",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://www.youtube.com/live/{VIDEO_ID}",
        f"https://www.youtube.com/embed/{VIDEO_ID}",
        f"https://www.youtube.com/v/{VIDEO_ID}",
        f"https://www.youtube-nocookie.com/embed/{VIDEO_ID}",
    ],
)
def test_detect_platform_recognizes_youtube_video_urls(url):
    assert detect_platform(url) == Platform.YOUTUBE


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={VIDEO_ID}",
        f"https://www.youtube.com/watch?v={VIDEO_ID}&t=30s",
        f"https://www.youtube.com/watch?list=PLabc&v={VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}?t=30",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://www.youtube.com/live/{VIDEO_ID}",
        f"https://www.youtube.com/embed/{VIDEO_ID}",
        f"https://www.youtube.com/v/{VIDEO_ID}",
        f"https://www.youtube-nocookie.com/embed/{VIDEO_ID}",
    ],
)
def test_extract_platform_id_returns_video_id(url):
    assert extract_platform_id(url, Platform.YOUTUBE) == VIDEO_ID


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/",
        "https://www.youtube.com/@somebody",
        "https://www.youtube.com/playlist?list=PLabc",
        "https://www.youtube.com/watch?list=PLabc",
        "https://www.youtube.com/watch?v=tooshort",
        "https://www.youtube.com/watch?v=waytoolongvideo",
        "https://www.youtube.com/results?search_query=abc",
        "https://youtu.be/",
        "https://youtu.be/short",
    ],
)
def test_detect_platform_rejects_youtube_urls_without_video_id(url):
    assert detect_platform(url) is None


def test_extract_platform_id_rejects_foreign_host():
    assert extract_platform_id(f"https://example.com/watch?v={VIDEO_ID}", Platform.YOUTUBE) is None
    assert extract_platform_id(f"https://youtube.com.evil.com/watch?v={VIDEO_ID}", Platform.YOUTUBE) is None


def test_existing_platforms_still_detected():
    assert detect_platform("https://www.bilibili.com/video/BV1xx411c7mD") == Platform.BILIBILI
    assert detect_platform("BV1xx411c7mD") == Platform.BILIBILI
    assert detect_platform("https://www.bilibili.com/video/BV1xx411c7mD?p=2") == Platform.BILIBILI
    assert detect_platform("https://www.xiaoyuzhoufm.com/episode/abcdefghijklmnopqrstuvwx") == Platform.XIAOYUZHOU
    assert detect_platform("https://www.ximalaya.com/sound/123456") == Platform.XIMALAYA


def test_extract_platform_id_for_bilibili_unchanged():
    assert extract_platform_id("https://www.bilibili.com/video/BV1xx411c7mD", Platform.BILIBILI) == "BV1xx411c7mD"
