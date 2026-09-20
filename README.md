# iHateVideos

Python 工具集合：把视频变成可检索的文字。Python 版本使用 uv 管理（`pyproject.toml`）。

## 目录组成

- `src/ihatevideos/input/`：多平台输入。B 站（含原生字幕优先）/小宇宙/喜马拉雅/本地文件，统一输出音频路径、元数据、资源编号。
- `src/ihatevideos/export/`：内容导出。转录 JSON 转原文 Markdown，总结转干净表格与 B 站时间线。
- `src/ihatevideos/agent/`：有监督 Agent（LangChain）。终端启动，按流程调用上面两个模块，写 temp 外暂停审批。
- `skills/`：随仓库提交的工程 Skills（`ihatevideos-input`、`ihatevideos-export`、`ihatevideos-agent`）。
- `.agents/skills/`：通用工具 Skills，只存本地，不提交。
- `temp/`：中间结果、Cookie 文件，只存本地，不提交。

## 快速开始

```bash
uv sync
uv run ihatevideos-input detect "BV1xx411c7mD"
uv run ihatevideos-export --help
```

## Agent

```bash
uv run ihatevideos-agent run --url "<B站链接>"
```

启动有监督会话：先检查登录态（缺失就在终端提示用户粘 Cookie），执行中写 temp 外当场 y/n 审批，结束打印 JSON（含 `session_dir`）。模型配置：复制 `config.example.toml` 到根目录 `config.toml` 再填真实值（`[model]` 下 `api_base`、`api_key`、`model`，OpenAI 兼容接口，不提交）。调用手册见 `skills/ihatevideos-agent/SKILL.md`。

## B 站登录态

B 站字幕接口只对登录态返回。导入一次，7 天内有效：

1. 在浏览器登录 B 站，用 Cookie 导出扩展（例如 Get cookies.txt LOCALLY）导出 Netscape 格式，把文件粘到 `temp/config/` 目录下，文件名随意。
2. 运行 `uv run ihatevideos-input cookies --file temp/config/<你粘的文件名>`（或设置 `BILIBILI_COOKIES_FILE` 后不传参数）。
3. 运行 `uv run ihatevideos-input cookies --check`，`state` 为 `ok` 表示可用。

`state` 为 `missing` / `empty` / `stale` / `broken` 时，按上面三步重新导入一遍。不要把 SESSDATA 的值贴到聊天里，密钥只留在本地文件。

## Skills

Agent 开发看各 Skill 目录下的 `SKILL.md`。大 Skill 按流程调用小 Skill：输入接入、转录、导出。

## 提交规则

见 `AGENTS.md`。改了 CLI 参数、退出码、输出格式，同步修改对应 Skill 文档。
