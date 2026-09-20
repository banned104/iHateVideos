from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel

from .config import AgentModelConfig, AgentPaths
from .tools import build_tools

SYSTEM_PROMPT = """你是 iHateVideos 的视频处理 Agent。一次只做用户交代的一件事。
工具用法：run_cli 跑项目 CLI（ihatevideos-input 处理输入与字幕评论，ihatevideos-export 做导出），read_file 读文件，write_file 只写 temp/。
约定：B站任务先跑 cookies --check，非 ok 就停下请用户按 README 导入；字幕用 subtitle 命令进 temp 会话目录；exit 3 表示无原生字幕转 ASR 路线；评论可选，失败不阻断；不要编造文件路径，只报命令实际打印的路径。"""


class FinalReport(BaseModel):
    session_dir: str = ""
    artifacts: list[str] = []
    status: str = ""
    note: str = ""


def writes_outside_temp(request: object, temp_dir_str: str) -> bool:
    from pathlib import Path

    args = request.tool_call["args"]
    target = Path(str(args.get("path", ""))).expanduser()
    return not target.resolve().is_relative_to(Path(temp_dir_str).resolve())


def build_agent(paths: AgentPaths, model_config: AgentModelConfig) -> object:
    model = ChatOpenAI(
        base_url=model_config.api_base,
        api_key=model_config.api_key,
        model=model_config.model,
    )
    temp_dir_str = str(paths.temp_dir)
    return create_agent(
        model=model,
        tools=build_tools(paths.root, paths.temp_dir),
        system_prompt=SYSTEM_PROMPT,
        middleware=[
            HumanInTheLoopMiddleware(
                interrupt_on={
                    "write_file": {
                        "allowed_decisions": ["approve", "reject"],
                        "when": lambda request: writes_outside_temp(request, temp_dir_str),
                    },
                    "run_cli": False,
                    "read_file": False,
                },
            ),
        ],
        response_format=FinalReport,
        checkpointer=InMemorySaver(),
    )
