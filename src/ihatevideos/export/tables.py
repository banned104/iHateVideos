"""Markdown table block extraction.

Ported from bilibili2text ``b2t/summarize/llm.py`` (pure helpers only:
``_extract_markdown_table_blocks`` + ``extract_markdown_table_block``).
The LLM-calling parts of ``llm.py`` are intentionally NOT ported.
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

TABLE_ROW_RE = re.compile(r"^\s*\|?.*\|.*\|?\s*$")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")


def _extract_markdown_table_blocks(content: str) -> list[str]:
    """Extract markdown table blocks from mixed markdown content."""
    lines = content.splitlines()
    blocks: list[str] = []
    in_fence = False
    i = 0

    while i < len(lines) - 1:
        stripped = lines[i].strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            i += 1
            continue

        if in_fence:
            i += 1
            continue

        header = lines[i]
        separator = lines[i + 1]
        if TABLE_ROW_RE.match(header) and TABLE_SEPARATOR_RE.match(separator):
            start = i
            end = i + 1
            j = i + 2
            while j < len(lines):
                row = lines[j]
                if not row.strip() or not TABLE_ROW_RE.match(row):
                    break
                end = j
                j += 1

            if end >= start + 2:
                blocks.append("\n".join(lines[start : end + 1]).strip() + "\n")

            i = j
            continue

        i += 1

    return blocks


def extract_markdown_table_block(
    content: str,
    *,
    which: str = "first",
) -> str | None:
    """Extract one markdown table block from content."""
    if which not in {"first", "last"}:
        raise ValueError("which must be 'first' or 'last'")
    blocks = _extract_markdown_table_blocks(content)
    if not blocks:
        return None
    if which == "last":
        return blocks[-1]
    return blocks[0]


def export_table_markdown(
    summary_path: Path | str,
    *,
    which: str = "last",
    keep_time_column: bool = False,
) -> Path | None:
    """Extract one table from a summary file and save it beside the source.

    Returns the new path, or None when the file contains no table (normal
    skip, not an error). ``keep_time_column=False`` matches the pipeline
    behaviour (clean table for humans); ``True`` keeps the raw table.
    """
    from .markdown_fmt import format_markdown_with_markdownlint
    from .timeline import remove_video_time_column

    summary_path = Path(summary_path)
    table_block = extract_markdown_table_block(
        summary_path.read_text(encoding="utf-8"), which=which
    )
    if table_block is None:
        logger.info("No table detected in summary, skipping table Markdown export")
        return None

    if not keep_time_column:
        table_block = remove_video_time_column(table_block)
    table_md_path = summary_path.with_name(f"{summary_path.stem}_table.md")
    table_md_path.write_text(table_block, encoding="utf-8")
    format_markdown_with_markdownlint(table_md_path)
    logger.info("Summary table Markdown generated: %s", table_md_path)
    return table_md_path
