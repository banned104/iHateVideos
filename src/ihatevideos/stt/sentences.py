from __future__ import annotations

from collections.abc import Sequence

from .models import AlignUnit, Sentence

# 句末标点，遇到就断句
SENTENCE_END = "。！？!?…"
# 从句边界，只在一个句子长到必须切开时才用它找切点
CLAUSE_END = "，,、；;：:"
MAX_SENTENCE_CHARS = 60
MAX_SENTENCE_SECONDS = 30.0


def _ends_with(text: str, marks: str) -> bool:
    stripped = text.rstrip()
    return bool(stripped) and stripped[-1] in marks


def _last_clause_index(buffer: Sequence[AlignUnit]) -> int | None:
    # 最后一个 unit 已经判定不是句末标点，所以从倒数第二个往前找
    for index in range(len(buffer) - 2, -1, -1):
        if _ends_with(buffer[index].text, CLAUSE_END):
            return index
    return None


def group_sentences(
    units: Sequence[AlignUnit],
    *,
    max_chars: int = MAX_SENTENCE_CHARS,
    max_seconds: float = MAX_SENTENCE_SECONDS,
) -> list[Sentence]:
    # 把字级时间戳按标点聚成句子，句子的起止时间取首尾 unit 的时间
    sentences: list[Sentence] = []
    buffer: list[AlignUnit] = []

    def flush() -> None:
        if not buffer:
            return
        text = "".join(item.text for item in buffer).strip()
        if text:
            sentences.append(
                Sentence(
                    begin_time_ms=int(round(buffer[0].start_seconds * 1000)),
                    end_time_ms=int(round(buffer[-1].end_seconds * 1000)),
                    text=text,
                )
            )
        buffer.clear()

    for unit in units:
        buffer.append(unit)
        text = "".join(item.text for item in buffer)
        span = buffer[-1].end_seconds - buffer[0].start_seconds
        if _ends_with(unit.text, SENTENCE_END):
            flush()
            continue
        if len(text) < max_chars and span < max_seconds:
            continue
        cut = _last_clause_index(buffer)
        if cut is None:
            flush()
            continue
        head = buffer[: cut + 1]
        tail = buffer[cut + 1 :]
        buffer.clear()
        buffer.extend(head)
        flush()
        buffer.extend(tail)

    flush()
    return sentences
