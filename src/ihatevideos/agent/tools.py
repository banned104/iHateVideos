import shutil
import subprocess
from pathlib import Path

from langchain.tools import tool

ALLOWED_COMMANDS = {
    "ihatevideos-input": {
        "detect", "normalize", "ids", "ximalaya", "resolve",
        "cookies", "subtitle", "comments",
    },
    "ihatevideos-export": {"json2md", "table", "timeline"},
}
OUTPUT_CAP = 20000


def build_tools(root: Path, temp_dir: Path) -> list:
    resolved_root = root.resolve()
    resolved_temp = temp_dir.resolve()

    def _resolve_readable(path: str) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = resolved_root / candidate
        return candidate.resolve()

    @tool
    def run_cli(command: str, arguments: list[str]) -> str:
        """Run a project CLI. command is ihatevideos-input or ihatevideos-export,
        arguments starts with the subcommand plus its flags."""
        if command not in ALLOWED_COMMANDS:
            return f"error: command {command}不在白名单"
        if not arguments or arguments[0] not in ALLOWED_COMMANDS[command]:
            return f"error: subcommand {arguments[0] if arguments else None}不在白名单"
        uv = shutil.which("uv") or "uv"
        try:
            completed = subprocess.run(
                [uv, "run", command, *arguments],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
                cwd=str(resolved_root),
            )
        except FileNotFoundError:
            return "error: 找不到 uv"
        except subprocess.TimeoutExpired:
            return "error: 命令超时"
        output = (completed.stdout or "") + (completed.stderr or "")
        if len(output) > OUTPUT_CAP:
            output = output[:OUTPUT_CAP] + "\n...[截断]"
        return f"exit={completed.returncode}\n{output}"

    @tool
    def read_file(path: str, max_chars: int = 20000) -> str:
        """Read a text file. Project, temp and external paths are all readable."""
        target = _resolve_readable(path)
        if not target.is_file():
            return f"error: 文件不存在 {target}"
        try:
            with target.open("rb") as stream:
                head = stream.read(8192)
                if b"\x00" in head:
                    return f"error: 拒绝读取二进制文件 {target}"
                stream.seek(0)
                text = stream.read(max_chars + 1).decode("utf-8")
        except OSError as exc:
            return f"error: 读取失败 {exc}"
        if len(text) > max_chars:
            return text[:max_chars] + "\n...[截断]"
        return text

    @tool
    def write_file(path: str, content: str) -> str:
        """Write a text file. Only paths under temp/ are writable."""
        target = _resolve_readable(path)
        if not target.is_relative_to(resolved_temp):
            raise ValueError(f"拒绝写入 temp 外路径 {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"ok {target} {len(content)}字"

    return [run_cli, read_file, write_file]
