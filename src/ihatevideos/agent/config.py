import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentModelConfig:
    api_base: str
    api_key: str
    model: str


@dataclass(frozen=True)
class AgentPaths:
    root: Path
    temp_dir: Path
    config_dir: Path
    config_file: Path


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return current


def resolve_paths(root: Path | None = None) -> AgentPaths:
    resolved = (root or find_project_root()).resolve()
    temp_dir = resolved / "temp"
    config_dir = temp_dir / "config"
    return AgentPaths(
        root=resolved,
        temp_dir=temp_dir,
        config_dir=config_dir,
        config_file=resolved / "config.toml",
    )


def load_model_config(paths: AgentPaths) -> AgentModelConfig:
    if not paths.config_file.is_file():
        raise FileNotFoundError(
            f"找不到 {paths.config_file}，在 [model] 下填写 api_base、api_key、model"
        )
    with paths.config_file.open("rb") as stream:
        data = tomllib.load(stream)
    section = data.get("model")
    if not isinstance(section, dict):
        raise ValueError(f"{paths.config_file} 缺少 [model] 配置节")
    missing = [key for key in ("api_base", "api_key", "model") if not section.get(key)]
    if missing:
        raise ValueError(f"{paths.config_file} [model] 缺少 {missing}")
    return AgentModelConfig(
        api_base=str(section["api_base"]).strip(),
        api_key=str(section["api_key"]).strip(),
        model=str(section["model"]).strip(),
    )
