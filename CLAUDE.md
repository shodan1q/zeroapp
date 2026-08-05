# CLAUDE.md - ZeroDev Agent 项目上下文

## 项目简介

ZeroDev Agent -- 自动化应用工厂。从互联网挖掘需求，使用 AI 自动生成代码，构建应用并自动上架应用商店。

**两条并行生产线，改代码前先确认在哪一条：**

| | WebView 线（默认，推荐） | Flutter 线（原有） |
|---|---|---|
| 产物 | 鸿蒙原生 ArkTS 壳 + 富 HTML 页面 -> `.hap` | Flutter 三端 -> APK/AAB/IPA/HAP |
| UI | LLM 生成的 HTML/CSS/JS，打包进 `resources/rawfile` 离线加载 | Dart + Material Design 2 |
| 工具链 | 只需 DevEco Studio（自带 SDK/hvigor/ohpm/Node） | Flutter SDK + flutter-ohos 分支 + 独立 OHOS SDK（约 10GB） |
| 入口 | `zerodev factory ...`，`zerodev/pipeline/webview_app.py` | `zerodev pipeline ...`，`zerodev/pipeline/graph.py` |
| 适合 | 无人值守连续出货：无 Dart 编译、无插件解析、无三端插件适配 | 需要原生能力、复杂交互的应用 |

WebView 线是为「7x24 不间断自动出 app」设计的，失败面小得多。两条线共用 LLM 层、评估层、爬虫层与 Dashboard。

## 技术栈

- Python 3.11+ / LangGraph（Agent 编排）/ FastAPI（后端 API）
- Next.js 15 + TypeScript + Tailwind CSS v4（Dashboard 前端）
- Flutter 3.7+ / Dart 2.19（移动端代码生成）
- 多 AI 提供商接入（`zerodev/llm.py` + `zerodev/providers.py`）：默认 Claude Opus 4.8 走官方 Anthropic SDK（CLAUDE_OAUTH_TOKEN 优先，回退 CLAUDE_API_KEY）；另支持 OpenAI / Gemini / DeepSeek / 通义千问 / 智谱 GLM / Kimi / Ollama，统一走各家 OpenAI 兼容端点（httpx 实现）
- 提供商选择优先级：Dashboard 设置（`data/settings.json` → `llmProvider`）> 环境变量 `LLM_PROVIDER` > 默认 `claude`；所有调用点通过 `get_llm_client()` / `get_llm_async_client()` / `get_llm_model()` 获取统一接口（禁止直接引用 `settings.claude_model`）
- 非 Claude 提供商失败抛 `zerodev.llm.LLMError`（RuntimeError 子类）；需要按文件降级的调用点统一 `except (anthropic.APIError, LLMError)`
- Dashboard 设置的运行时读取统一走 `zerodev/settings_store.py`（发布凭证、数据源开关、审批阈值、爬取间隔均已接入，优先级同上）
- LangGraph 主图审核门默认自动续跑；`run_pipeline(human_review=True)` 才会在 fan_out 前暂停等人工 resume
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

WebView 线常用命令：

```bash
zerodev factory doctor                      # 体检：AI 提供商 / 鸿蒙工具链 / 签名 / AGC 凭证
zerodev llm probe --match <模型名>          # 验证提供商可用，列出该端点真实支持的模型
zerodev factory build --name 应用名 --desc 描述   # 单个应用跑完整链路
zerodev factory run                         # 7x24 连续生产
zerodev factory status                      # 看当前进度与最近战绩
zerodev factory queue --name 应用名 --desc 描述   # 往队列塞需求，守护进程优先消费
zerodev factory service                     # 生成 launchd 开机自启配置（需自行 load）
```

## WebView 线要点

- `zerodev/generator/webapp_generator.py` -- LLM 生成离线 HTML/CSS/JS。两阶段：先出设计系统 + 内容计划（JSON），再按 `styles.css -> data.js -> index.html -> app.js` 顺序逐文件生成，后生成的文件能看到前面的
- 生成资产**必须完全离线**：任何 `src=` / `url()` / `@import` 指向 http(s):// 都判为缺陷。打包后没有网络保证，外链等于白屏。校验器会拦截并触发重写（最多 2 轮）
- 生成的 JS 会用 node `--check` 做语法校验：ArkWeb 没有可见控制台，语法错误只会表现为白屏，且构建照样成功，不拦就会一路发到商店
- `zerodev/generator/ohos_project.py` -- 生成 Stage 模型 ArkTS 工程。骨架对齐 DevEco 自带模板（API 24 实测可构建）。图标用 Pillow 现生成，不依赖外部素材
- `zerodev/builder/ohos_builder.py` -- 自动探测 DevEco，注入 `DEVECO_SDK_HOME`/`NODE_HOME`/`PATH` 后跑 `hvigorw assembleHap`。默认 `--no-daemon`：无人值守场景下，残留守护进程持有旧 SDK 路径是反复出错的来源
- `zerodev/pipeline/webview_app.py` -- 四阶段编排（generate/scaffold/build/publish），每阶段计时并落结构化结果，失败时能说清断在哪一步
- `zerodev/pipeline/daemon.py` -- 连续生产。需求来源优先级：队列文件 > 已审批 demand > LLM 自己想。失败退避、心跳、状态原子落盘，单个应用失败绝不终止循环
- 中文应用名 slug 用 sha1 摘要而非 `hash()`：后者按进程加盐，会让同一个应用每次重启落到不同工作目录

## 构建平台

支持三端单独/组合构建，平台标识 `android` / `ios` / `ohos`（鸿蒙）。

- 选择优先级：CLI `--platform` > Dashboard 设置（`data/settings.json`）> `TARGET_PLATFORMS` > 默认 `android`
- CLI：`zerodev generate --platform ohos`、`zerodev pipeline run --platform android,ohos`
- 平台解析在 `zerodev/builder/platforms.py`：`parse_platforms`（纯解析）+ `get_runtime_platforms`（settings.json -> env 回退，运行时默认来源）
- `node_build` 按 `state["target_platforms"]` 分发：android→APK/AAB、ios→IPA、ohos→HAP
- Flutter 线的鸿蒙构建走 flutter-ohos（`flutter build hap`），需 `FLUTTER_OHOS_PATH` / `OHOS_SDK_HOME`；WebView 线不需要这些，见上文
- `node_publish` 按已构建产物匹配商店：aab→Google Play、ipa→App Store、hap→AppGallery
- `HarmonyOSPublisher` 已实现完整 AGC Publishing API 六步：取 token → 申请上传地址 → multipart 上传 .hap → 绑定文件 → 写商店文案 → 提交审核。AGC 逻辑失败也返回 HTTP 200，所以判定看响应体的 `ret.code` 而不是状态码
- 无凭证时走 dry-run，明确报告断在哪一步；`AGC_AUTO_SUBMIT=false` 可只上传不提交审核
- **AppGallery 拒收 unsigned 包**，必须配 `OHOS_SIGN_*` 六项签名材料才能真正上架
- 注意：Dashboard「自定义生成」走 `PipelineRunner`（runner.py），仅做 Android 编译校验；release 构建与上架走 LangGraph 图（CLI / orchestrator 路径）

## 测试

```bash
.venv/bin/python -m pytest tests/ -v
```

## 端口

- 后端 API：9716
- 前端 Dashboard：9717

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

- `zerodev/pipeline/` -- LangGraph 流水线（graph.py 是主图定义）
- `zerodev/generator/` -- 代码生成核心（code_generator.py 逐文件调用 Claude）
- `zerodev/api/` -- FastAPI 后端（含 WebSocket 实时推送）
- `zerodev/llm.py` -- Claude 客户端，自动适配 Anthropic API / 本地代理
- `dashboard/` -- Next.js 15 前端应用
- `workspace/` -- 生成的 Flutter 项目（不提交到 git）
- `data/` -- SQLite checkpoint 数据（不提交到 git）
