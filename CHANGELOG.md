# CHANGELOG

## 0.1.3 — 2026-09-21

- 评论默认 10 条主评论、每条子评论最多 10 条（`--reply-limit` 可调）。

## 0.1.2 — 2026-09-21

- 字幕中间产物进会话目录：`temp/<日期>-<标题>-<BV号>/`，`subtitle` 默认写 temp，已存在加序号不覆盖。

## 0.1.1 — 2026-09-21

- B 站登录态：浏览器 Cookie 导入与状态检查（`cookies --file/--check`），只走 Cookie，不做扫码登录。
- 字幕落文件：`subtitle` 命令直出文本与时间轴 JSON，`input` Skill 给出三步端到端流程。
- 修复 GBK 控制台下 `bili` 输出宽字符崩死导致字幕误判缺失。

## 0.1.0 — 2026-09-20

- 多平台输入：B 站（含原生字幕优先）/小宇宙/喜马拉雅/本地文件统一接入（`ihatevideos-input`）。
- 内容导出：转录 JSON 转原文 Markdown、总结表格、 B 站时间线（`ihatevideos-export`）。
- 首批随工程 Skill：`ihatevideos-input`、`ihatevideos-export`（通用工具 Skill 留本地 `.agents/`，不进仓库）。
