import re
from datetime import date
from pathlib import Path

from .platform import sanitize_filename_component

_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def session_dir_name(*, title: str, pubdate: str = "", bvid: str = "") -> str:
    # 文件夹格式：日期-标题；日期取视频发布时间，拿不到取当天
    match = _DATE_PREFIX_RE.match((pubdate or "").strip())
    day = match.group(1) if match else date.today().isoformat()
    safe_title = sanitize_filename_component(title or bvid or "untitled", max_length=50)
    name = f"{day}-{safe_title}"
    if bvid and not name.endswith(bvid):
        name = f"{name}-{bvid}"
    return name


def prepare_session_dir(
    root: Path | str, *, title: str, pubdate: str = "", bvid: str = ""
) -> Path:
    # 中间产物目录：已存在就加序号，不覆盖旧产物
    base = Path(root).expanduser()
    candidate = base / session_dir_name(title=title, pubdate=pubdate, bvid=bvid)
    index = 2
    while candidate.exists():
        candidate = base / f"{candidate.name}_{index}"
        index += 1
    candidate.mkdir(parents=True)
    return candidate


def subtitle_artifact_paths(session_dir: Path | str, stem: str) -> tuple[Path, Path]:
    directory = Path(session_dir)
    return directory / f"{stem}_sub.txt", directory / f"{stem}_sub_items.json"
