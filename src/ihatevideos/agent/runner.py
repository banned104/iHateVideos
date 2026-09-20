import json
import sys
import uuid
from pathlib import Path

from langgraph.types import Command

from ihatevideos.input import credential_status, import_bilibili_cookies

from .config import AgentPaths, load_model_config, resolve_paths
from .harness import build_agent

BILIBILI_HINTS = ("bilibili", "bilibili", "b23.tv", "BV", "哔哩", "B站")


def needs_bilibili(text: str) -> bool:
    lowered = text.lower()
    return any(hint.lower() in lowered for hint in BILIBILI_HINTS)


def find_pasted_cookies(config_dir: Path) -> Path | None:
    exact = config_dir / "cookies.txt"
    if exact.is_file():
        return exact
    candidates = sorted(
        config_dir.glob("*.txt"), key=lambda item: item.stat().st_mtime, reverse=True
    )
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        print("temp/config 下有多个 txt：")
        for item in candidates:
            print(f"  {item.name}")
        name = input("输入要用的文件名：").strip()
        chosen = config_dir / name
        return chosen if chosen.is_file() else None
    return None


def ensure_login(paths: AgentPaths) -> bool:
    if credential_status().get("state") == "ok":
        return True
    print("B站登录态不可用，先导入：")
    print("1. 浏览器登录B站，用 Cookie 导出扩展导出 Netscape 格式")
    print(f"2. 把文件粘到 {paths.config_dir} 下，文件名随意")
    for _ in range(3):
        answer = input("粘好后回车继续（输入 q 退出）：").strip().lower()
        if answer == "q":
            return False
        found = find_pasted_cookies(paths.config_dir)
        if found is None:
            print(f"{paths.config_dir} 下没找到 txt，重粘后回车")
            continue
        try:
            import_bilibili_cookies(found)
        except (FileNotFoundError, ValueError) as exc:
            print(f"导入失败：{exc}")
            continue
        if credential_status().get("state") == "ok":
            print("登录态可用，继续")
            return True
        print("导入后仍不可用，重新导出一份再试")
    return False


def ask_approval(action: dict) -> dict:
    args = json.dumps(action.get("arguments", {}), ensure_ascii=False)
    print(f"待审批：{action.get('name')} 参数：{args[:1000]}")
    answer = input("批准执行？[y/n] ").strip().lower()
    if answer in {"y", "yes"}:
        return {"type": "approve"}
    return {"type": "reject", "message": "用户拒绝了这次写操作，换 temp 目录内的路径重做。"}


def run(task: str, *, root: Path | None = None) -> int:
    paths = resolve_paths(root)
    try:
        model_config = load_model_config(paths)
    except FileNotFoundError:
        print(
            "error: 缺模型配置，把 config.example.toml 复制成 "
            f"{paths.config_file} 再填 api_base、api_key、model",
            file=sys.stderr,
        )
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if needs_bilibili(task) and not ensure_login(paths):
        print("error: 登录态未就绪，退出", file=sys.stderr)
        return 2
    agent = build_agent(paths, model_config)
    config = {"configurable": {"thread_id": uuid.uuid4().hex}}
    result = agent.invoke({"messages": [{"role": "user", "content": task}]}, config=config, version="v2")
    while getattr(result, "interrupts", None):
        actions = result.interrupts[0].value.get("action_requests", [])
        decisions = [ask_approval(action) for action in actions]
        result = agent.invoke(Command(resume={"decisions": decisions}), config=config, version="v2")
    value = getattr(result, "value", {}) or {}
    report = value.get("structured_response")
    if report is None:
        messages = value.get("messages", [])
        text = messages[-1].content if messages else ""
        report = {"status": "done", "note": str(text)}
    elif not isinstance(report, dict):
        report = report.model_dump() if hasattr(report, "model_dump") else dict(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0
