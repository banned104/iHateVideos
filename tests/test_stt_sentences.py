from ihatevideos.stt import AlignUnit, group_sentences


def unit(text: str, start: float, end: float) -> AlignUnit:
    return AlignUnit(text=text, start_seconds=start, end_seconds=end)


def test_splits_on_sentence_end():
    units = [
        unit("你", 0.0, 0.2),
        unit("好", 0.2, 0.4),
        unit("。", 0.4, 0.5),
        unit("再", 0.5, 0.7),
        unit("见", 0.7, 0.9),
        unit("。", 0.9, 1.0),
    ]
    sentences = group_sentences(units)
    assert [item.text for item in sentences] == ["你好。", "再见。"]
    assert sentences[0].begin_time_ms == 0
    assert sentences[0].end_time_ms == 500
    assert sentences[1].begin_time_ms == 500
    assert sentences[1].end_time_ms == 1000


def test_flushes_remaining_text_without_punctuation():
    sentences = group_sentences([unit("甲", 0.0, 0.1), unit("乙", 0.1, 0.2)])
    assert [item.text for item in sentences] == ["甲乙"]


def test_breaks_long_run_at_clause_boundary():
    head = [unit("甲", index * 0.1, index * 0.1 + 0.1) for index in range(30)]
    comma = unit("，", 3.0, 3.1)
    tail = [unit("乙", 3.1 + index * 0.1, 3.2 + index * 0.1) for index in range(40)]
    sentences = group_sentences(head + [comma] + tail, max_chars=60)
    assert len(sentences) >= 2
    assert sentences[0].text.endswith("，")
    assert sentences[0].text.count("甲") == 30


def test_forces_break_on_max_seconds():
    units = [unit("字", index * 0.5, index * 0.5 + 0.5) for index in range(100)]
    sentences = group_sentences(units, max_chars=1000, max_seconds=10.0)
    assert len(sentences) > 1
    for item in sentences:
        assert item.end_time_ms - item.begin_time_ms <= 11000


def test_empty_input_returns_nothing():
    assert group_sentences([]) == []


def test_whitespace_only_units_are_dropped():
    units = [unit(" ", 0.0, 0.1), unit(" ", 0.1, 0.2)]
    assert group_sentences(units) == []


def test_strips_surrounding_spaces():
    units = [unit(" ", 0.0, 0.1), unit("你", 0.1, 0.2), unit("好", 0.2, 0.3)]
    sentences = group_sentences(units)
    assert [item.text for item in sentences] == ["你好"]
