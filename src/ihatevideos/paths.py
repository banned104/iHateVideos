from pathlib import Path


def find_project_root(start: Path | None = None) -> Path:
    """从起始目录向上找含 pyproject.toml 的目录，找不到就用起始目录本身。"""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return current
