"""Content-export module (belongs to the iHateVideos project).

Layer 1 only: pure-stdlib exports every pipeline run produces.

    from ihatevideos.export import (
        convert_json_to_md,           # transcription.json -> 原文.md
        export_summary_table_without_video_time,  # 总结.md -> *_table.md
        export_summary_timeline_text,             # 总结.md -> *_timeline.txt
    )
"""

from .json_to_md import TIMELINE_SCHEMA_VERSION, convert_json_to_md, ms_to_mmss
from .markdown_fmt import batch_format_markdown, format_markdown_with_markdownlint
from .tables import export_table_markdown, extract_markdown_table_block
from .timeline import (
    TimelineEntry,
    export_summary_table_without_video_time,
    export_summary_timeline_text,
    extract_timeline_entries,
    remove_video_time_column,
)

__all__ = [
    "TIMELINE_SCHEMA_VERSION",
    "TimelineEntry",
    "batch_format_markdown",
    "convert_json_to_md",
    "export_summary_table_without_video_time",
    "export_summary_timeline_text",
    "export_table_markdown",
    "extract_markdown_table_block",
    "extract_timeline_entries",
    "format_markdown_with_markdownlint",
    "ms_to_mmss",
    "remove_video_time_column",
]
