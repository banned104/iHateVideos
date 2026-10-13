from ihatevideos.input.comments import (
    PlatformComment,
    PlatformCommentBundle,
    _parse_comment,
    comments_to_markdown,
)


def _raw(message: str, pictures=None) -> dict:
    content = {"message": message}
    if pictures is not None:
        content["pictures"] = pictures
    return {
        "rpid": 1,
        "member": {"uname": "某人", "mid": 42},
        "ctime": 1791887197,
        "like": 7,
        "content": content,
    }


def _bundle(comments: tuple[PlatformComment, ...]) -> PlatformCommentBundle:
    return PlatformCommentBundle(
        bvid="BV1test",
        fetched_count=len(comments),
        requested_limit=None,
        total_count=len(comments),
        sort="hot",
        comments=comments,
    )


def test_parse_comment_reads_picture_urls():
    comment = _parse_comment(
        _raw("看图", [{"img_src": "http://i0.hdslb.com/a.jpg", "img_width": 100}]),
        up_uid=0,
    )
    assert comment.pictures == ("http://i0.hdslb.com/a.jpg",)


def test_parse_comment_keeps_every_picture_of_one_comment():
    comment = _parse_comment(
        _raw("两张图", [{"img_src": "http://x/a.jpg"}, {"img_src": "http://x/b.jpg"}]),
        up_uid=0,
    )
    assert comment.pictures == ("http://x/a.jpg", "http://x/b.jpg")


def test_parse_comment_skips_broken_picture_entries():
    comment = _parse_comment(
        _raw(
            "残缺的图片字段",
            [{"img_width": 100}, {"img_src": "   "}, {"img_src": "http://x/ok.jpg"}],
        ),
        up_uid=0,
    )
    assert comment.pictures == ("http://x/ok.jpg",)


def test_parse_comment_without_pictures():
    assert _parse_comment(_raw("没有图"), up_uid=0).pictures == ()
    assert _parse_comment(_raw("字段类型不对", "http://x/a.jpg"), up_uid=0).pictures == ()


def test_comments_to_markdown_writes_picture_references():
    comment = PlatformComment(
        rpid=1,
        author="某人",
        author_uid=42,
        message="看图",
        like=7,
        ctime="2026-10-13 21:54:08",
        ctime_timestamp=1791887197,
        pictures=("http://i0.hdslb.com/a.jpg",),
    )
    text = comments_to_markdown(_bundle((comment,)))
    assert "![评论图片](http://i0.hdslb.com/a.jpg)" in text


def test_comments_to_markdown_writes_reply_pictures():
    reply = PlatformComment(
        rpid=2,
        author="回复者",
        author_uid=43,
        message="我也有图",
        like=0,
        ctime="",
        ctime_timestamp=0,
        pictures=("http://x/c.jpg",),
    )
    comment = PlatformComment(
        rpid=1,
        author="某人",
        author_uid=42,
        message="主评论",
        like=7,
        ctime="",
        ctime_timestamp=0,
        replies=(reply,),
    )
    text = comments_to_markdown(_bundle((comment,)))
    assert "  ![评论图片](http://x/c.jpg)" in text


def test_comments_to_markdown_without_pictures_has_no_image_lines():
    comment = PlatformComment(
        rpid=1,
        author="某人",
        author_uid=42,
        message="没图",
        like=0,
        ctime="",
        ctime_timestamp=0,
    )
    assert "![评论图片]" not in comments_to_markdown(_bundle((comment,)))
