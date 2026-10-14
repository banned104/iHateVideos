import os
from pathlib import Path

import pytest

from ihatevideos.input.cookies import (
    credential_status,
    find_cookies_file,
    load_bilibili_cookies,
    load_cookies,
    verify_login,
)
from ihatevideos.input.platform import Platform

NETSCAPE_HEADER = "# Netscape HTTP Cookie File\n"


def write_netscape(path: Path, rows: list[tuple[str, str, str]]) -> None:
    body = "".join(
        f"{domain}\tTRUE\t/\tFALSE\t0\t{name}\t{value}\n" for domain, name, value in rows
    )
    path.write_text(NETSCAPE_HEADER + body, encoding="utf-8")


def make_project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    directory = tmp_path / "temp" / "config"
    directory.mkdir(parents=True)
    return directory


def test_load_cookies_keeps_only_matching_domain(tmp_path):
    path = tmp_path / "cookies.txt"
    write_netscape(
        path,
        [
            (".youtube.com", "LOGIN_INFO", "youtube-value"),
            (".example.com", "LOGIN_INFO", "other-value"),
        ],
    )
    assert load_cookies(path, Platform.YOUTUBE) == {"LOGIN_INFO": "youtube-value"}


def test_load_cookies_reads_two_platforms_from_one_file(tmp_path):
    path = tmp_path / "cookies.txt"
    write_netscape(
        path,
        [
            (".bilibili.com", "SESSDATA", "bili-value"),
            (".youtube.com", "LOGIN_INFO", "youtube-value"),
        ],
    )
    assert load_cookies(path, Platform.BILIBILI) == {"SESSDATA": "bili-value"}
    assert load_cookies(path, Platform.YOUTUBE) == {"LOGIN_INFO": "youtube-value"}


def test_load_bilibili_cookies_wrapper_matches_platform_call(tmp_path):
    path = tmp_path / "cookies.txt"
    write_netscape(path, [(".bilibili.com", "SESSDATA", "bili-value")])
    assert load_bilibili_cookies(path) == load_cookies(path, Platform.BILIBILI)


def test_find_cookies_file_picks_by_platform(tmp_path, monkeypatch):
    directory = make_project(tmp_path)
    bilibili = directory / "bili.txt"
    write_netscape(bilibili, [(".bilibili.com", "SESSDATA", "bili-value")])
    youtube = directory / "yt.txt"
    write_netscape(youtube, [(".youtube.com", "LOGIN_INFO", "youtube-value")])
    monkeypatch.chdir(tmp_path)
    assert find_cookies_file(Platform.BILIBILI) == bilibili
    assert find_cookies_file(Platform.YOUTUBE) == youtube


def test_find_cookies_file_skips_file_without_required_cookie(tmp_path, monkeypatch):
    directory = make_project(tmp_path)
    write_netscape(
        directory / "visitor.txt",
        [(".youtube.com", "VISITOR_INFO1_LIVE", "abc")],
    )
    monkeypatch.chdir(tmp_path)
    assert find_cookies_file(Platform.YOUTUBE) is None
    status = credential_status(Platform.YOUTUBE)
    assert status["state"] == "empty"
    assert status["cookie_name"] == "LOGIN_INFO"
    assert status["files"] == ["visitor.txt"]


def test_find_cookies_file_picks_newest_per_platform(tmp_path, monkeypatch):
    directory = make_project(tmp_path)
    older = directory / "yt-old.txt"
    write_netscape(older, [(".youtube.com", "LOGIN_INFO", "old")])
    newer = directory / "yt-new.txt"
    write_netscape(newer, [(".youtube.com", "LOGIN_INFO", "new")])
    os.utime(older, (1_000_000, 1_000_000))
    os.utime(newer, (2_000_000, 2_000_000))
    monkeypatch.chdir(tmp_path)
    assert find_cookies_file(Platform.YOUTUBE) == newer


def test_credential_status_missing_without_config_dir(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    status = credential_status(Platform.YOUTUBE)
    assert status["state"] == "missing"


def test_credential_status_reports_required_cookie_length(tmp_path, monkeypatch):
    directory = make_project(tmp_path)
    write_netscape(directory / "yt.txt", [(".youtube.com", "LOGIN_INFO", "abcdefgh")])
    monkeypatch.chdir(tmp_path)
    status = credential_status(Platform.YOUTUBE)
    assert status["state"] == "ok"
    assert status["cookie_name"] == "LOGIN_INFO"
    assert status["cookie_len"] == len("abcdefgh")


def test_verify_login_rejects_platform_without_check():
    with pytest.raises(ValueError, match="没有为 ximalaya 实现登录态检查"):
        verify_login(Platform.XIMALAYA)
