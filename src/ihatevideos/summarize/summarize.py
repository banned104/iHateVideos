import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from ihatevideos.agent.config import AgentModelConfig

from .client import complete
from .presets import CUSTOM_PRESET, get_preset_template, validate_template

logger = logging.getLogger(__name__)

_BVID_PREFIX_RE = re.compile(r"^(BV[0-9A-Za-z]{10})[_-]?", re.IGNORECASE)
_COMMENT_TOTAL_RE = re.compile(r"^- 评论区总数:\s*(\d+)\s*$", re.MULTILINE)
_COMMENT_FETCHED_RE = re.compile(r"^- 已抓取主评论:\s*(\d+)\s*$", re.MULTILINE)
_COMMENT_FETCHED_REPLIES_RE = re.compile(r"^- 已抓取子评论:\s*(\d+)\s*$", re.MULTILINE)
_COMMENT_SENTIMENT_SECTION_RE = re.compile(
    r"^###\s*舆情统计\s*$\n?(.*?)(?=^#{2,3}\s|\Z)",
    re.MULTILINE | re.DOTALL,
)
_COMMENT_EMOTION_SECTION_RE = re.compile(
    r"^###\s*情绪倾向\s*$\n?(.*?)(?=^#{2,3}\s|\Z)",
    re.MULTILINE | re.DOTALL,
)
_COMMENT_SENTIMENT_FIELDS = ("有效评论", "正面", "负面", "中性", "已过滤")


def _infer_title_from_path(md_path: Path) -> str:
    stem = md_path.stem
    if stem.lower().endswith("_transcription"):
        stem = stem[:-14]
    inferred = _BVID_PREFIX_RE.sub("", stem, count=1).strip("_- ")
    return inferred or stem or "Untitled Video"


def _format_publish_time(metadata: Mapping[str, Any] | None) -> str:
    if metadata is None:
        return "Unknown"
    pubdate = str(metadata.get("pubdate") or "").strip()
    timestamp = metadata.get("pubdate_timestamp") or 0
    try:
        timestamp = int(timestamp)
    except (TypeError, ValueError):
        timestamp = 0
    if timestamp > 0:
        if not pubdate:
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        return pubdate
    return pubdate or "Unknown"


def _demote_top_level_headings(markdown: str) -> str:
    lines = markdown.splitlines()
    normalized_lines: list[str] = []
    in_fence = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            normalized_lines.append(line)
            continue
        if not in_fence and stripped.startswith("# "):
            leading = line[: len(line) - len(stripped)]
            normalized_lines.append(f"{leading}## {stripped[2:].strip()}")
            continue
        normalized_lines.append(line)
    return "\n".join(normalized_lines).strip()


def post_process_summary_markdown(
    summary: str,
    *,
    metadata: Mapping[str, Any] | None = None,
    fallback_title: str = "",
) -> str:
    title = ""
    author = "Unknown"
    if metadata is not None:
        title = str(metadata.get("title") or "").strip()
        author = str(metadata.get("author") or "").strip() or "Unknown"
    title = title or fallback_title.strip() or "Untitled Video"
    body = _demote_top_level_headings(summary.strip())
    parts = ["# " + title, "", f"- Creator: {author}", f"- Published: {_format_publish_time(metadata)}"]
    if body:
        parts.extend(["", body])
    return "\n".join(parts).rstrip() + "\n"


def summarize_markdown(
    md_path: Path | str,
    model_config: AgentModelConfig,
    *,
    preset: str | None = None,
    template: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    timeout: int = 300,
) -> Path:
    md_path = Path(md_path)
    content = md_path.read_text(encoding="utf-8")
    if not content.strip():
        raise ValueError(f"转录文件为空：{md_path}")
    if template is not None:
        body_template = validate_template(template)
        preset_name = CUSTOM_PRESET
    else:
        body_template = get_preset_template(preset or "")
        preset_name = (preset or "").strip() or "timeline_merge"
    prompt = body_template.format(content=content)
    logger.info("总结调用模型 %s，preset %s", model_config.model, preset_name)
    raw = complete(prompt, model_config, timeout=timeout)
    summary = post_process_summary_markdown(
        raw, metadata=metadata, fallback_title=_infer_title_from_path(md_path)
    )
    summary_path = md_path.parent / f"{md_path.stem}_summary.md"
    summary_path.write_text(summary, encoding="utf-8")
    logger.info("总结已写 %s", summary_path)
    return summary_path


def build_viewpoints_prompt(comments_markdown: str) -> str:
    return (
        "请基于下面的视频或播客精选评论，提炼观众讨论中的相关观点，"
        "输出 Markdown 片段并以二级标题 `## 精选评论观点` 开头。\n"
        "要求：\n"
        "- 总结高频观点、争议点、补充信息和情绪倾向。\n"
        "- 先过滤无信息量或与视频、播客主题无关的评论，不得将其纳入观点、"
        "情绪倾向或频次判断。\n"
        "- 应过滤的内容包括但不限于：`第一`、`前排` 等抢楼评论；"
        "仅 @ 他人或机器人的评论；`@xxx，请帮我总结一下这个视频` 等求总结、"
        "求解析指令；纯表情、无意义符号、重复刷屏、广告引流和无关闲聊。\n"
        "- 不要仅因观点低频或表达负面就过滤；包含具体事实、论据、纠错、"
        "反例或与主题相关质疑的评论应保留。\n"
        "- 对过滤后的有效评论逐条进行舆情分类。每条主评论和每条子评论各计 1 条，"
        "不得按点赞数加权，也不得把同一条评论重复计数。\n"
        "- 正面、负面判断的是评论者对视频或播客内容、核心观点或创作者表达的态度，"
        "不是评论所讨论事件本身的正负性质。认可、赞同、支持归为正面；反对、批评、"
        "质疑归为负面；提问、事实补充、混合态度或态度不明确归为中性。\n"
        "- 固定输出 `### 舆情统计` 小节，依次列出 `有效评论`、`正面`、`负面`、"
        "`中性`、`已过滤` 的条数；正面、负面、中性同时给出占有效评论的百分比，"
        "保留 1 位小数。必须满足 正面 + 负面 + 中性 = 有效评论。有效评论为 0 时"
        "百分比均写 `0.0%`。该小节会在后处理中合并到评论统计，不要在其他位置"
        "重复这些数据。\n"
        "- 在输出末尾固定添加 `### 情绪倾向` 小节，用自然语言概括评论区的整体情绪、"
        "典型表达和少数不同声音；保留分析性叙述，不要在该小节重复正面、负面、"
        "中性的统计数字。\n"
        "- 舆情数量只能依据本次提供的评论逐条统计，不得依据平台显示的评论区总数"
        "推算；无法可靠完成统计时应明确说明，不得编造数量。\n"
        "- 重点关注标记为 `UP主回复` 的内容。\n"
        "- 涉及 UP 主回复的结论或原话必须使用 Markdown 加粗。\n"
        "- 不要输出表格。\n"
        "- 不要编造评论中不存在的观点。\n\n"
        f"{comments_markdown.strip()}"
    )


def _extract_sentiment_stats(comment_summary: str) -> dict[str, str]:
    section_match = _COMMENT_SENTIMENT_SECTION_RE.search(comment_summary)
    if not section_match:
        return {}
    fields: dict[str, str] = {}
    for line in section_match.group(1).splitlines():
        normalized = line.strip().lstrip("-* ").replace("**", "")
        for field in _COMMENT_SENTIMENT_FIELDS:
            match = re.match(rf"^{field}\s*[：:]\s*(.+?)\s*$", normalized)
            if match:
                fields[field] = match.group(1)
                break
    return fields


def _move_emotion_section_to_end(comment_summary: str) -> str:
    section_match = _COMMENT_EMOTION_SECTION_RE.search(comment_summary)
    if not section_match:
        return comment_summary.strip()
    emotion_body = section_match.group(1).strip()
    remaining = _COMMENT_EMOTION_SECTION_RE.sub("", comment_summary).strip()
    emotion_section = "### 情绪倾向"
    if emotion_body:
        emotion_section = f"{emotion_section}\n\n{emotion_body}"
    return f"{remaining}\n\n{emotion_section}".strip()


def _comment_stats_block(comments_markdown: str, sentiment_stats: dict[str, str]) -> str:
    total_match = _COMMENT_TOTAL_RE.search(comments_markdown)
    fetched_match = _COMMENT_FETCHED_RE.search(comments_markdown)
    fetched_replies_match = _COMMENT_FETCHED_REPLIES_RE.search(comments_markdown)
    total_count = total_match.group(1) if total_match else "未知"
    fetched_main = fetched_match.group(1) if fetched_match else "未知"
    fetched_replies = fetched_replies_match.group(1) if fetched_replies_match else "未知"
    if fetched_match and fetched_replies_match:
        summarized = str(int(fetched_main) + int(fetched_replies))
    else:
        summarized = "未知"
    up_count = comments_markdown.count("**UP主回复**")
    lines = [
        "评论统计：",
        "",
        f"- 视频总评论数: {total_count}",
        f"- 本次总结评论数: {summarized}（主评论 {fetched_main}，子评论 {fetched_replies}）",
        f"- UP主回复评论数: {up_count}",
    ]
    if sentiment_stats:
        lines.append("")
        lines.append("舆情统计（本次总结）：")
        lines.append("")
        for field in _COMMENT_SENTIMENT_FIELDS:
            if field in sentiment_stats:
                lines.append(f"- {field}: {sentiment_stats[field]}")
    return "\n".join(lines)


def append_viewpoints(
    summary_path: Path | str,
    comments_md_path: Path | str,
    model_config: AgentModelConfig,
    *,
    timeout: int = 300,
) -> bool:
    comments_path = Path(comments_md_path)
    comments_markdown = comments_path.read_text(encoding="utf-8").strip()
    if not comments_markdown:
        logger.info("评论文件为空，跳过观点总结")
        return False
    raw = complete(build_viewpoints_prompt(comments_markdown), model_config, timeout=timeout)
    sentiment_stats = _extract_sentiment_stats(raw)
    body = _COMMENT_SENTIMENT_SECTION_RE.sub("", raw).strip()
    body = _move_emotion_section_to_end(body)
    block = _comment_stats_block(comments_markdown, sentiment_stats)
    summary_file = Path(summary_path)
    original = summary_file.read_text(encoding="utf-8").rstrip() + "\n"
    summary_file.write_text(f"{original}\n{body}\n\n{block}\n", encoding="utf-8")
    logger.info("观点已追加 %s", summary_file)
    return True
