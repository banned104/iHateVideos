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
