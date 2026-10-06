from __future__ import annotations

from collections.abc import Sequence

from .models import AlignUnit, Sentence

SENTENCE_END = "。！？!?…"
CLAUSE_END = "，,、；;：:"
# 这些字符不发音，时间戳模型不会给它们时间，比对字符位置时要跳过
SKIPPABLE = "，。！？、；：,.!?;:\"'“”‘’（）()《》〈〉【】[]{}…—-～　 \t\r\n"
MAX_SENTENCE_CHARS = 60
MAX_SENTENCE_SECONDS = 30.0


def _is_skippable(char: str) -> bool:
    return char in SKIPPABLE


def _ends_sentence(piece: str) -> bool:
    stripped = piece.rstrip()
    return bool(stripped) and stripped[-1] in SENTENCE_END


def _clean_to_unit_index(text: str, units: Sequence[AlignUnit]) -> list[int | None]:
    # 识别文本带标点，时间戳模型只输出发音单元，这里把两者的字符位置逐个对上
    clean = [char for char in text if not _is_skippable(char)]
    units_text = "".join(unit.text for unit in units)
    char_to_unit: list[int] = []
    for index, unit in enumerate(units):
        char_to_unit.extend([index] * len(unit.text))
    mapping: list[int | None] = [None] * len(clean)
    left = 0
    right = 0
    while left < len(clean) and right < len(units_text):
        if clean[left] == units_text[right]:
            mapping[left] = char_to_unit[right]
            left += 1
            right += 1
        else:
            # 识别文本里有时间戳模型不认的字符，例如 C++ 的两个加号，跳过它
            left += 1
    return mapping


def _pieces(text: str) -> list[tuple[int, int, str]]:
    # 按任意标点切成小段，标点归到前一段，返回 (起始字符位置, 结束字符位置, 文本)
    pieces: list[tuple[int, int, str]] = []
    buffer: list[str] = []
    consumed = 0
    start = 0
    for char in text:
        buffer.append(char)
        if not _is_skippable(char):
            consumed += 1
        if char in SENTENCE_END or char in CLAUSE_END:
            piece = "".join(buffer).strip()
            if piece:
                pieces.append((start, consumed, piece))
            buffer.clear()
            start = consumed
    tail = "".join(buffer).strip()
    if tail:
        pieces.append((start, consumed, tail))
    return pieces


def _nearest_unit(mapping: Sequence[int | None], index: int, step: int) -> int | None:
    cursor = index
    while 0 <= cursor < len(mapping):
        if mapping[cursor] is not None:
            return mapping[cursor]
        cursor += step
    return None


def _time_range_ms(
    begin: int, end: int, mapping: Sequence[int | None], units: Sequence[AlignUnit]
) -> tuple[int, int]:
    first = _nearest_unit(mapping, begin, 1)
    last = _nearest_unit(mapping, end - 1, -1)
    if first is None or last is None:
        return 0, 0
    return (
        int(round(units[first].start_seconds * 1000)),
        int(round(units[last].end_seconds * 1000)),
    )


def group_sentences(
    text: str,
    units: Sequence[AlignUnit],
    *,
    max_chars: int = MAX_SENTENCE_CHARS,
    max_seconds: float = MAX_SENTENCE_SECONDS,
) -> list[Sentence]:
    # 断句以识别文本的标点为准，时间从字级时间戳取；这样句边界不会切在词中间
    mapping = _clean_to_unit_index(text, units)
    sentences: list[Sentence] = []
    pending: list[tuple[int, int, str]] = []

    def flush() -> None:
        if not pending:
            return
        begin = pending[0][0]
        end = pending[-1][1]
        piece = "".join(item[2] for item in pending)
        begin_ms, end_ms = _time_range_ms(begin, end, mapping, units)
        sentences.append(Sentence(begin_time_ms=begin_ms, end_time_ms=end_ms, text=piece))
        pending.clear()

    for piece in _pieces(text):
        if pending:
            projected_chars = piece[1] - pending[0][0]
            projected_ms = _time_range_ms(pending[0][0], piece[1], mapping, units)
            projected_seconds = (projected_ms[1] - projected_ms[0]) / 1000
            if projected_chars > max_chars or projected_seconds > max_seconds:
                flush()
        pending.append(piece)
        if _ends_sentence(piece[2]):
            flush()

    flush()
    return sentences
