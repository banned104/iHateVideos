from ihatevideos.stt import AlignUnit, group_sentences

SKIPPED = "，。！？、；：,.!?;: "


def units_for(text: str, *, start: float = 0.0, step: float = 0.1) -> list[AlignUnit]:
    # 模拟时间戳模型：只给发音字符出时间，标点没有对应的 unit
    result: list[AlignUnit] = []
    clock = start
    for char in text:
        if char in SKIPPED:
            continue
        result.append(
            AlignUnit(
                text=char,
                start_seconds=round(clock, 3),
                end_seconds=round(clock + step, 3),
            )
        )
        clock += step
    return result


def test_keeps_punctuation_and_splits_on_it():
    text = "你好。再见。"
    sentences = group_sentences(text, units_for(text))
    assert [item.text for item in sentences] == ["你好。", "再见。"]
    assert sentences[0].begin_time_ms == 0
    assert sentences[0].end_time_ms == 200
    assert sentences[1].begin_time_ms == 200
    assert sentences[1].end_time_ms == 400


def test_characters_absent_from_units_are_skipped():
    text = "C++好。"
    units = [
        AlignUnit(text="C", start_seconds=0.0, end_seconds=0.1),
        AlignUnit(text="好", start_seconds=0.1, end_seconds=0.2),
    ]
    sentences = group_sentences(text, units)
    assert [item.text for item in sentences] == ["C++好。"]
    assert sentences[0].begin_time_ms == 0
    assert sentences[0].end_time_ms == 200


def test_without_units_times_are_zero():
    sentences = group_sentences("你好。", [])
    assert [item.text for item in sentences] == ["你好。"]
    assert sentences[0].begin_time_ms == 0
    assert sentences[0].end_time_ms == 0


def test_long_run_breaks_before_exceeding_limit():
    text = "甲" * 40 + "，" + "乙" * 40 + "。"
    sentences = group_sentences(text, units_for(text), max_chars=50)
    assert len(sentences) == 2
    assert sentences[0].text.endswith("，")
    assert sentences[1].text.endswith("。")


def test_breaks_on_max_seconds():
    text = "甲" * 10 + "，" + "乙" * 10 + "。"
    sentences = group_sentences(
        text, units_for(text, step=1.0), max_chars=1000, max_seconds=10.0
    )
    assert len(sentences) == 2
    assert sentences[0].end_time_ms - sentences[0].begin_time_ms <= 11000


def test_clause_marks_do_not_break_a_short_sentence():
    text = "你好，再见"
    sentences = group_sentences(text, units_for(text))
    assert [item.text for item in sentences] == ["你好，再见"]


def test_empty_text_returns_nothing():
    assert group_sentences("", []) == []


def test_extra_unit_character_does_not_shift_later_times():
    # 时间戳模型多输出了一个字符，后面的字符不能被逐个跳过
    text = "你好世界。"
    units = [
        AlignUnit(text="你", start_seconds=0.0, end_seconds=0.1),
        AlignUnit(text="啊", start_seconds=0.1, end_seconds=0.2),
        AlignUnit(text="好", start_seconds=0.2, end_seconds=0.3),
        AlignUnit(text="世", start_seconds=0.3, end_seconds=0.4),
        AlignUnit(text="界", start_seconds=0.4, end_seconds=0.5),
    ]

    sentences = group_sentences(text, units)

    assert sentences[0].begin_time_ms == 0
    assert sentences[0].end_time_ms == 500


def test_unmatched_tail_uses_last_known_unit():
    # 文本尾部出现时间戳模型没有的字符时，时间取最近的已知单元而不是 0
    text = "你好。+++"
    sentences = group_sentences(text, units_for("你好"))

    assert [item.text for item in sentences] == ["你好。", "+++"]
    assert sentences[1].begin_time_ms == 100
    assert sentences[1].end_time_ms == 200


def test_times_stay_ordered_when_units_have_extra_characters():
    text = "第一句。第二句。"
    units = [
        AlignUnit(text="第", start_seconds=0.0, end_seconds=0.1),
        AlignUnit(text="一", start_seconds=0.1, end_seconds=0.2),
        AlignUnit(text="x", start_seconds=0.2, end_seconds=0.3),
        AlignUnit(text="句", start_seconds=0.3, end_seconds=0.4),
        AlignUnit(text="第", start_seconds=0.4, end_seconds=0.5),
        AlignUnit(text="二", start_seconds=0.5, end_seconds=0.6),
        AlignUnit(text="句", start_seconds=0.6, end_seconds=0.7),
    ]

    sentences = group_sentences(text, units)

    assert [item.text for item in sentences] == ["第一句。", "第二句。"]
    assert [item.begin_time_ms for item in sentences] == [0, 400]
    assert [item.end_time_ms for item in sentences] == [400, 700]
