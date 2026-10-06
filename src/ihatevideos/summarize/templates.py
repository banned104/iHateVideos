from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import SummarizeError
from .paths import templates_dir


@dataclass(frozen=True)
class Template:
    name: str
    title: str
    path: Path
    body: str


def _parse(path: Path) -> Template:
    text = path.read_text(encoding="utf-8")
    title = path.stem
    body = text
    if text.startswith("# "):
        first, _, rest = text.partition("\n")
        title = first[2:].strip() or path.stem
        body = rest.lstrip("\n")
    return Template(name=path.stem, title=title, path=path, body=body)


def list_templates(root: Path | None = None) -> list[Template]:
    directory = templates_dir(root)
    if not directory.is_dir():
        return []
    return [_parse(item) for item in sorted(directory.glob("*.md"))]


def read_template(name: str, root: Path | None = None) -> Template:
    cleaned = (name or "").strip()
    if not cleaned:
        raise SummarizeError("模板名不能为空")
    directory = templates_dir(root)
    for candidate in (directory / f"{cleaned}.md", directory / cleaned):
        if candidate.is_file():
            return _parse(candidate)
    available = "、".join(item.name for item in list_templates(root))
    if not available:
        raise SummarizeError(f"没有这个模板：{cleaned}；{directory} 里也没有任何模板")
    raise SummarizeError(f"没有这个模板：{cleaned}；可用的是：{available}")
