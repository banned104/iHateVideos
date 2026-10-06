import json
import sys
import uuid
from pathlib import Path

from langgraph.types import Command

from ihatevideos.input import verify_login

from .config import AgentPaths, load_model_config, resolve_paths
from .harness import build_agent

BILIBILI_HINTS = ("bilibili", "bilibili", "b23.tv", "BV", "哔哩", "B站")


def needs_bilibili(text: str) -> bool:
    lowered = text.lower()
    return any(hint.lower() in lowered for hint in BILIBILI_HINTS)


def ensure_login(paths: AgentPaths) -> bool:
    ok, detail = verify_login()
    if ok:
        return True
    print(f"B站登录态不可用：{detail}")
    print("1. 浏览器登录 B站，用 Cookie 导出扩展导出 Netscape 格式")
    print(f"2. 把文件复制到 {paths.config_dir} 下，文件名随意")
    for _ in range(3):
        answer = input("复制好后回车继续（输入 q 退出）：").strip().lower()
        if answer == "q":
            return False
        ok, detail = verify_login()
        if ok:
            print(f"登录态可用（{detail}），继续")
            return True
        print(f"仍不可用：{detail}")
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
