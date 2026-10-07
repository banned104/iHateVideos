import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def format_markdown_with_markdownlint(md_path: Path | str) -> None:
    """Format a Markdown file using markdownlint-cli2

    自动修掉表格前缺空行、行尾空格、表格列宽一类的常见问题。

    Args:
        md_path: Markdown file path

    Note:
        - markdownlint-cli2 不在 PATH 上时直接跳过
        - 工具报出的规则问题不影响产物，只记日志
    """
    md_path = Path(md_path)

    if not md_path.exists():
        logger.warning("Markdown file does not exist, skipping formatting: %s", md_path)
        return

    if not shutil.which("markdownlint-cli2"):
        logger.debug("markdownlint-cli2 not installed, skipping Markdown formatting")
        return

    completed = subprocess.run(
        ["markdownlint-cli2", "--fix", str(md_path)],
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=md_path.parent,
    )
    if completed.returncode != 0:
        # 报出来的多是行长、表格列宽一类的规则，不影响产物，记一行日志继续
        logger.debug(
            "markdownlint-cli2 退出码 %s：%s",
            completed.returncode,
            (completed.stdout or "").strip(),
        )
    else:
        logger.debug("Formatted with markdownlint-cli2: %s", md_path)


def batch_format_markdown(directory: Path | str, pattern: str = "*.md") -> int:
    """Batch format Markdown files in a directory

    Args:
        directory: Directory path
        pattern: File matching pattern (default: "*.md")

    Returns:
        Number of formatted files
    """
    directory = Path(directory)
    count = 0

    for md_file in directory.glob(pattern):
        if md_file.is_file():
            format_markdown_with_markdownlint(md_file)
            count += 1

    logger.info("Formatted %d Markdown files", count)
    return count
