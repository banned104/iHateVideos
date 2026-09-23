from langchain_openai import ChatOpenAI

from ihatevideos.agent.config import AgentModelConfig


def complete(prompt: str, model_config: AgentModelConfig, *, timeout: int = 300) -> str:
    model = ChatOpenAI(
        base_url=model_config.api_base,
        api_key=model_config.api_key,
        model=model_config.model,
        request_timeout=timeout,
    )
    message = model.invoke(prompt)
    text = message.content if isinstance(message.content, str) else str(message.content)
    if not text.strip():
        raise ValueError("模型返回为空，无法生成总结")
    return text.strip()
