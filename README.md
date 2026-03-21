# ZeroDev Agent

自动化 Flutter 应用工厂 -- 从互联网挖掘需求，AI 自动生成 Flutter 代码，三端构建（Android / iOS / HarmonyOS），自动上架应用商店。

## 架构概览

系统采用五层流水线架构，由 LangGraph 有向图编排，支持 SQLite checkpoint 持久化与中断恢复：

```
┌─────────────────────────────────────────────────────────┐
│           Agent 调度中心 (Python + LangGraph)             │
│     StateGraph 有向图编排 + SQLite Checkpoint 持久化       │
│     指数退避重试 + 中断恢复 + 人工审核中断点                │
└──────┬─────────┬──────────┬──────────┬─────────┬────────┘
       │         │          │          │         │
       v         v          v          v         v
   ┌───────┐ ┌───────┐ ┌────────┐ ┌────────┐ ┌────────┐
   │ 需求   │ │ 评估   │ │ 代码   │ │ 构建   │ │ 运营   │
   │ 采集层 │ │ 决策层 │ │ 生成层 │ │ 发布层 │ │ 监控层 │
   └───────┘ └───────┘ └────────┘ └────────┘ └────────┘
```

主图：crawl -> process -> evaluate -> decide -> [人工审核] -> fan_out
子图：generate -> build -> assets -> [人工审核] -> publish

## 技术栈

| 层级 | 技术 |
|------|------|
| Agent 编排 | Python 3.11+ / LangGraph / SQLite Checkpoint |
| LLM | Claude Opus 4.6（API 或 Max Plan 本地代理 claude-max-api） |
| 后端 API | FastAPI + Uvicorn |
| 实时通信 | WebSocket（自动重连，指数退避） |
| 前端 Dashboard | Next.js 15 + TypeScript + Tailwind CSS v4 |
| 移动端 | Flutter 3.7+ / Dart 2.19（兼容 HarmonyOS OHOS） |
| 状态管理 | Riverpod 2.x |
| 数据库 | PostgreSQL + SQLAlchemy（异步） |
| 定时调度 | Celery Beat（可选） |
| 图标生成 | DALL-E 3 API |

## 快速开始

### 前置条件

- Python 3.11+
- Node.js 18+（Dashboard 前端）
- Flutter 3.7+（代码生成与构建）
- Flutter OHOS 社区版（可选，HarmonyOS 构建）
- PostgreSQL（需求数据库）
- Redis（可选，Celery 定时调度）

### 安装

```bash
# 克隆项目
git clone <repo-url> && cd zeroapp

# 安装 Python 依赖
make install

# 安装 Dashboard 前端依赖
cd dashboard && npm install && cd ..

# 复制并编辑环境变量
cp .env.example .env
# 编辑 .env，填入 Claude API Key 或配置 claude-max-api 本地代理
```

### 配置

编辑 `.env` 文件，核心配置项：

- `CLAUDE_MODE`：`local`（Max Plan 本地代理）或 `api`（Anthropic API）
- `CLAUDE_BASE_URL`：claude-max-api 代理地址，默认 `http://127.0.0.1:3456`
- `CLAUDE_MODEL`：默认 `claude-opus-4-6`
- `DATABASE_URL`：PostgreSQL 异步连接字符串
- `PIPELINE_CHECKPOINT_BACKEND`：`sqlite`（推荐）或 `memory`

### 运行

```bash
# 启动后端 API（端口 9716）
make dashboard

# 启动前端 Dashboard（端口 9717）
make dashboard-frontend

# 运行一次完整流水线
make generate-app

# 或使用 CLI
zerodev pipeline
```

## 项目结构

```
zeroapp/
├── zerodev/                    # Python 主包
│   ├── api/                    # FastAPI 后端（路由、WebSocket、事件）
│   ├── assets/                 # 资源生成（图标、截图、商店文案）
│   ├── builder/                # Flutter 构建与发布
│   ├── crawler/                # 需求采集爬虫
│   ├── evaluator/              # 需求评估与决策
│   ├── generator/              # 代码生成（PRD、模板、逐文件生成）
│   │   └── templates/          # Flutter 项目模板注册表
│   ├── models/                 # SQLAlchemy 数据模型
│   ├── monitor/                # 运营监控
│   ├── pipeline/               # LangGraph 流水线（图、状态、checkpoint、重试）
│   ├── tasks/                  # Celery 异步任务
│   ├── config.py               # 配置（pydantic-settings）
│   ├── database.py             # 数据库引擎
│   ├── llm.py                  # Claude 客户端（自动适配 API/本地代理）
│   └── main.py                 # CLI 入口（typer）
├── dashboard/                  # Next.js 15 前端
├── alembic/                    # 数据库迁移
├── tests/                      # 测试
├── workspace/                  # 生成的 Flutter 项目（git 忽略）
├── data/                       # SQLite checkpoint 数据（git 忽略）
├── pyproject.toml              # Python 项目配置
├── Makefile                    # 常用命令
└── flutter_agent_requirements.md  # 完整需求清单
```

## CLI 命令

```bash
zerodev run              # 启动完整流水线（持续运行）
zerodev crawl            # 仅运行需求采集
zerodev evaluate         # 评估待处理需求
zerodev generate         # 为已通过需求生成代码
zerodev build            # 构建已通过的应用
zerodev pipeline         # 运行一次完整流水线
```

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/ws` | WebSocket | 实时事件推送 |
| `/api/dashboard` | GET | 概览统计数据 |
| `/api/demands` | GET | 需求列表（分页、筛选） |
| `/api/apps` | GET | 应用列表（分页、搜索） |
| `/api/builds` | GET | 构建日志 |
| `/api/stats` | GET | 统计数据 |
| `/api/pipeline/status/{thread_id}` | GET | 流水线状态 |
| `/api/pipeline/trigger` | POST | 手动触发流水线 |

后端默认端口：9716，前端默认端口：9717。

## Dashboard 使用

Dashboard 是独立的 Next.js 15 前端应用，通过 API 代理连接 FastAPI 后端。

功能包括：
- 概览卡片（总应用数、已上架、开发中、今日需求等）
- 流水线实时状态（WebSocket 驱动，动画指示当前阶段）
- 需求队列管理
- 构建日志（自动滚动）
- 应用列表（含下载量、评分、收入）
- 活动日志（实时滚动）

启动方式：
```bash
# 终端 1：后端
make dashboard

# 终端 2：前端
make dashboard-frontend
```

## 开发指南

### 测试

```bash
# Python 测试
make test

# 全部测试（Python + 前端类型检查）
make test-all
```

### 代码检查

```bash
# 检查
make lint

# 自动格式化
make format

# 类型检查
make typecheck
```

### 构建

```bash
# Android APK
make build-android

# iOS IPA
make build-ios

# HarmonyOS HAP（需配置 OHOS SDK 环境变量）
make build-ohos
```

### 代码生成兼容性

代码生成目标为 Dart 2.19 / Flutter 3.7+，以确保 HarmonyOS OHOS 兼容性。生成的代码禁止使用以下 Dart 3.x 特性：
- super 参数（使用 `Key? key` + `super(key: key)` 风格）
- records、patterns、sealed classes
- `colorSchemeSeed` / `ColorScheme.fromSeed()`
- Material Design 3（统一使用 `useMaterial3: false`）
