# CLAUDE.md - AutoDev Agent 项目上下文

## 项目简介

AutoDev Agent -- 自动化 Flutter 应用工厂。从互联网挖掘需求，使用 AI 自动生成 Flutter 代码，构建三端应用（Android / iOS / HarmonyOS），自动上架应用商店。

## 技术栈

- Python 3.11+ / LangGraph（Agent 编排）/ FastAPI（后端 API）
- Next.js 15 + TypeScript + Tailwind CSS v4（Dashboard 前端）
- Flutter 3.7+ / Dart 2.19（移动端代码生成）
- Claude Opus 4.6 通过 claude-max-api 本地代理（CLAUDE_MODE=local）
- PostgreSQL + SQLAlchemy（数据库）
- SQLite（LangGraph checkpoint 持久化）

## 常用命令

```bash
make install              # 安装 Python 依赖
make test                 # 运行 Python 测试
make test-all             # 运行全部测试（Python + 前端类型检查）
make dashboard            # 启动后端 API（端口 9716）
make dashboard-frontend   # 启动前端 Dashboard（端口 9717）
make lint                 # 代码检查
make format               # 自动格式化
make generate-app         # 运行一次完整流水线
```

## 测试

```bash
.venv/bin/python -m pytest tests/ -v
```

## 端口

- 后端 API：9716
- 前端 Dashboard：9717
- claude-max-api 代理：3456

## 代码生成约束

- 目标 Dart 2.19 / Flutter 3.7+，确保 HarmonyOS OHOS 兼容
- 禁止 Dart 3.x 语法：super 参数、records、patterns、sealed classes
- 使用 Material Design 2（useMaterial3: false）
- 禁止 colorSchemeSeed / ColorScheme.fromSeed()
- 构造函数使用 `Key? key` 命名参数风格

## 编码规范

- 代码和生成的应用中禁止使用 emoji
- UI 文本使用中文（面向中国用户的界面）
- Python 代码遵循 ruff 规范（行宽 120）
- 类型注解使用 `from __future__ import annotations`

## 项目结构要点

- `autodev/pipeline/` -- LangGraph 流水线（graph.py 是主图定义）
- `autodev/generator/` -- 代码生成核心（code_generator.py 逐文件调用 Claude）
- `autodev/api/` -- FastAPI 后端（含 WebSocket 实时推送）
- `autodev/llm.py` -- Claude 客户端，自动适配 Anthropic API / 本地代理
- `dashboard/` -- Next.js 15 前端应用
- `workspace/` -- 生成的 Flutter 项目（不提交到 git）
- `data/` -- SQLite checkpoint 数据（不提交到 git）
