# Flutter 自动化开发智能体 — 完整框架开发需求清单

> **项目代号**：AutoDev Agent
> **目标**：24小时不间断从互联网挖掘需求 → AI 自动开发 Flutter App → 自动构建三端 → 自动提交上架
> **技术栈**：Flutter + Dart | Python (Agent 编排) | Claude API (代码生成)

---

## 一、系统总体架构

```
┌─────────────────────────────────────────────────────────┐
│                    Agent 调度中心 (Python)                │
│         Celery / APScheduler 定时任务 + 状态机             │
└──────┬─────────┬──────────┬──────────┬─────────┬────────┘
       │         │          │          │         │
       ▼         ▼          ▼          ▼         ▼
   ┌───────┐ ┌───────┐ ┌────────┐ ┌────────┐ ┌────────┐
   │ 需求   │ │ 评估   │ │ 代码   │ │ 构建   │ │ 运营   │
   │ 采集层 │ │ 决策层 │ │ 生成层 │ │ 发布层 │ │ 监控层 │
   └───────┘ └───────┘ └────────┘ └────────┘ └────────┘
```

全部 5 层共 **42 个子模块**，以下逐层展开。

---

## 二、模块 1：需求采集层

### 1.1 数据源爬虫集群

| 编号 | 子模块 | 说明 | 优先级 |
|------|--------|------|--------|
| 1.1.1 | 应用商店热榜爬虫 | Google Play 热搜 / App Store 趋势 / 华为应用市场排行 | P0 |
| 1.1.2 | 社交平台需求爬虫 | Reddit r/AppIdeas、V2EX、知乎「有什么好用的App」类话题 | P0 |
| 1.1.3 | ProductHunt 新品监控 | 每日抓取新上线产品，提取 idea 关键词 | P1 |
| 1.1.4 | 小红书/抖音评论挖掘 | 抓取「求推荐App」「有没有好用的xxx」相关内容 | P1 |
| 1.1.5 | 竞品差评分析器 | 爬竞品 App 的 1-2 星差评，提取用户未被满足的痛点 | P0 |
| 1.1.6 | Google Trends API | 监控热搜关键词趋势，发现新兴需求 | P2 |
| 1.1.7 | GitHub Trending 监控 | 发现热门开源项目，转化为 App 产品化需求 | P2 |

### 1.2 需求结构化处理

| 编号 | 子模块 | 说明 | 优先级 |
|------|--------|------|--------|
| 1.2.1 | 原始数据清洗管道 | 去重、去噪、语言翻译（统一为中/英文） | P0 |
| 1.2.2 | LLM 需求提取器 | 调用 Claude API 从非结构化文本中提取：App名称、核心功能、目标用户、变现模式 | P0 |
| 1.2.3 | 需求去重引擎 | Embedding 向量相似度比对，避免重复开发同类 App | P0 |
| 1.2.4 | 需求数据库 | PostgreSQL 存储所有采集到的需求，含状态字段（待评估/已通过/已开发/已上架） | P0 |

### 1.3 输出格式

```json
{
  "demand_id": "D20260321-001",
  "title": "极简番茄钟",
  "description": "一个界面极简的番茄工作法计时器，支持白噪音和统计",
  "category": "工具/效率",
  "target_users": "上班族、学生",
  "core_features": [
    "25/5 分钟番茄计时",
    "自定义时长",
    "白噪音播放",
    "每日/周统计图表"
  ],
  "monetization": "免费+广告 / 高级版去广告",
  "estimated_complexity": "low",
  "competition_score": 0.35,
  "trend_score": 0.78,
  "source": "reddit_r_appideas",
  "source_url": "https://...",
  "created_at": "2026-03-21T08:30:00Z"
}
```

---

## 三、模块 2：需求评估与决策层

### 2.1 自动评估引擎

| 编号 | 子模块 | 说明 | 优先级 |
|------|--------|------|--------|
| 2.1.1 | 可行性评估器 | LLM 判断能否用 Flutter 在单文件/少文件内实现，排除需要硬件（NFC、蓝牙配对等）的需求 | P0 |
| 2.1.2 | 竞争度分析器 | 调用应用商店搜索 API，统计同类 App 数量、平均评分、下载量 | P0 |
| 2.1.3 | 变现潜力评估 | LLM 评估该品类的广告 eCPM、付费转化率参考值 | P1 |
| 2.1.4 | 开发复杂度评估 | 根据功能列表估算：页面数、是否需后端、是否需第三方 SDK | P0 |
| 2.1.5 | 综合评分排序 | 加权公式：`score = 0.3*trend + 0.25*feasibility + 0.25*low_competition + 0.2*monetization` | P0 |

### 2.2 决策规则

```yaml
auto_approve_rules:
  - complexity: low          # 仅低复杂度
  - pages: <= 5              # 5个页面以内
  - needs_backend: false     # 不需要后端
  - needs_hardware: false    # 不需要特殊硬件
  - competition_score: < 0.6 # 竞争度中低
  - trend_score: > 0.4       # 有一定热度
  
auto_reject_rules:
  - category: ["赌博", "成人", "政治敏感"]
  - needs_login: true        # 初期不做需要账号系统的
  - estimated_dev_hours: > 8 # 预估超过 8 小时的
```

---

## 四、模块 3：代码生成层（核心）

### 3.1 Flutter 项目模板库

| 编号 | 模板名 | 包含内容 | 适用场景 |
|------|--------|---------|---------|
| T-01 | 单页工具模板 | 单屏工具 + AdMob 广告位 + 设置页 | 计算器、转换器、生成器 |
| T-02 | 列表展示模板 | 列表页 + 详情页 + 搜索 + 本地存储 | 菜谱、知识库、参考手册 |
| T-03 | 计时器模板 | 计时/倒计时 + 通知 + 历史记录 | 番茄钟、健身计时、冥想 |
| T-04 | 追踪记录模板 | 每日记录 + 图表统计 + 数据导出 | 习惯追踪、记账、饮水 |
| T-05 | 信息聚合模板 | RSS/API 数据拉取 + 卡片展示 + 收藏 | 新闻、天气、汇率 |
| T-06 | 小游戏模板 | 游戏主循环 + 分数系统 + 排行榜 | 益智、休闲小游戏 |

### 3.2 模板标准目录结构

```
project_root/
├── lib/
│   ├── main.dart                  # 入口文件
│   ├── app.dart                   # MaterialApp 配置
│   ├── config/
│   │   ├── theme.dart             # 主题配置（颜色、字体）
│   │   ├── routes.dart            # 路由配置
│   │   └── constants.dart         # 常量
│   ├── models/                    # 数据模型
│   ├── screens/                   # 页面
│   │   ├── home_screen.dart
│   │   └── settings_screen.dart
│   ├── widgets/                   # 自定义组件
│   ├── services/                  # 业务逻辑/API
│   ├── providers/                 # 状态管理（Riverpod）
│   └── utils/                     # 工具函数
├── assets/                        # 资源文件
│   ├── images/
│   ├── icons/
│   └── fonts/
├── test/                          # 测试文件
├── android/                       # Android 配置
├── ios/                           # iOS 配置
├── ohos/                          # 鸿蒙 HarmonyOS 配置
├── pubspec.yaml                   # 依赖配置
└── fastlane/                      # 自动化发布配置
```

### 3.3 标准依赖库清单（pubspec.yaml）

```yaml
dependencies:
  flutter:
    sdk: flutter
  
  # 状态管理
  flutter_riverpod: ^2.5.0
  
  # 本地存储
  shared_preferences: ^2.2.0
  hive: ^2.2.3
  hive_flutter: ^1.1.0
  
  # UI 组件
  google_fonts: ^6.1.0
  flutter_svg: ^2.0.9
  cached_network_image: ^3.3.1
  shimmer: ^3.0.0
  
  # 广告变现
  google_mobile_ads: ^5.0.0
  
  # 工具
  intl: ^0.19.0               # 国际化
  url_launcher: ^6.2.0
  share_plus: ^7.2.0
  package_info_plus: ^5.0.0
  
  # 分析
  firebase_core: ^2.24.0
  firebase_analytics: ^10.8.0
  firebase_crashlytics: ^3.4.0
  
  # 图表（按需）
  fl_chart: ^0.66.0
  
  # 通知（按需）
  flutter_local_notifications: ^17.0.0

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^3.0.0
  build_runner: ^2.4.0
  hive_generator: ^2.0.0
```

### 3.4 AI 代码生成流程

| 编号 | 步骤 | 说明 | 超时限制 |
|------|------|------|---------|
| 3.4.1 | 模板选择 | LLM 根据需求描述选择最匹配的模板 | 10 秒 |
| 3.4.2 | 需求转 PRD | LLM 生成详细产品需求文档：页面列表、交互流程、数据模型 | 30 秒 |
| 3.4.3 | 逐文件生成 | 按 PRD 逐个文件调用 Claude API 生成 Dart 代码 | 每文件 60 秒 |
| 3.4.4 | 依赖检查 | 解析 import 语句，自动补充 pubspec.yaml 依赖 | 10 秒 |
| 3.4.5 | 静态分析 | 运行 `dart analyze`，收集错误列表 | 60 秒 |
| 3.4.6 | 自动修复循环 | 将错误信息喂给 LLM 修复，最多 5 轮 | 每轮 60 秒 |
| 3.4.7 | 编译验证 | `flutter build apk --debug` 验证能否编译通过 | 300 秒 |
| 3.4.8 | 编译修复循环 | 编译错误喂给 LLM 修复，最多 3 轮 | 每轮 120 秒 |

### 3.5 代码生成 Prompt 模板

```
你是一个专业的 Flutter 开发者。请根据以下需求生成完整可运行的 Flutter 代码。

## 需求
{demand_description}

## 约束
1. 使用 Flutter 3.22+ 和 Dart 3.4+
2. 状态管理使用 Riverpod
3. 必须包含 AdMob 广告位（Banner 广告在底部）
4. 必须支持深色/浅色主题切换
5. 必须包含设置页面
6. 所有文本使用 intl 国际化（中文+英文）
7. 代码必须通过 dart analyze 零错误
8. 遵循 Material Design 3 规范
9. 适配手机和平板两种屏幕尺寸

## 当前要生成的文件
文件路径：{file_path}
文件职责：{file_purpose}

## 已生成的相关文件（供参考）
{context_files}

请只输出该文件的完整 Dart 代码，不要输出任何解释。
```

---

## 五、模块 4：资源自动生成层

### 4.1 应用图标生成

| 编号 | 子模块 | 说明 | 优先级 |
|------|--------|------|--------|
| 4.1.1 | 图标 Prompt 生成 | LLM 根据 App 名称和功能，生成 DALL-E/Midjourney 风格的图标描述 Prompt | P0 |
| 4.1.2 | 图标 API 调用 | 调用图像生成 API（DALL-E 3 / Stable Diffusion）生成 1024x1024 图标 | P0 |
| 4.1.3 | 图标多尺寸适配 | 使用 `flutter_launcher_icons` 自动生成 Android/iOS/鸿蒙所需的全部尺寸 | P0 |

### 4.2 应用截图生成

| 编号 | 子模块 | 说明 | 优先级 |
|------|--------|------|--------|
| 4.2.1 | 自动截图 | 使用 `integration_test` + `screenshot` 包自动截取核心页面 | P0 |
| 4.2.2 | 截图美化 | 添加设备边框、背景色、宣传文案，生成应用商店要求的截图 | P1 |
| 4.2.3 | 多尺寸适配 | 生成 Google Play（手机+平板）、App Store（6.7"+5.5"）、华为（多尺寸）要求的截图 | P0 |

### 4.3 应用商店文案

| 编号 | 子模块 | 说明 | 优先级 |
|------|--------|------|--------|
| 4.3.1 | 标题生成 | LLM 生成 30 字符以内的 App 标题（含 ASO 关键词） | P0 |
| 4.3.2 | 短描述生成 | 80 字符以内的短描述 | P0 |
| 4.3.3 | 长描述生成 | 4000 字符以内的长描述，含功能介绍、关键词布局 | P0 |
| 4.3.4 | 多语言翻译 | 至少生成中文和英文两个版本 | P1 |
| 4.3.5 | 隐私政策生成 | 根据 App 权限自动生成隐私政策页面（托管在 GitHub Pages） | P0 |

---

## 六、模块 5：构建与发布层

### 5.1 构建管道

| 编号 | 步骤 | 命令/工具 | 说明 |
|------|------|----------|------|
| 5.1.1 | 依赖安装 | `flutter pub get` | 安装所有依赖 |
| 5.1.2 | 代码生成 | `dart run build_runner build` | 生成 Hive adapters 等 |
| 5.1.3 | 单元测试 | `flutter test` | 运行所有测试 |
| 5.1.4 | Android 构建 | `flutter build appbundle --release` | 生成 AAB |
| 5.1.5 | iOS 构建 | `flutter build ipa --release` | 生成 IPA |
| 5.1.6 | 鸿蒙构建 | `flutter build hap --release` | 生成 HAP |
| 5.1.7 | 构建产物归档 | 复制到 `builds/{demand_id}/` | 统一管理 |

### 5.2 签名配置

```yaml
# Android 签名 (android/key.properties)
signing:
  keystore_path: "/secrets/android/upload-keystore.jks"
  keystore_password: "${ANDROID_KEYSTORE_PASS}"
  key_alias: "upload"
  key_password: "${ANDROID_KEY_PASS}"

# iOS 签名 (使用 fastlane match)
ios_signing:
  type: "appstore"
  git_url: "git@github.com:your-org/certificates.git"
  team_id: "${APPLE_TEAM_ID}"

# 鸿蒙签名
harmony_signing:
  profile_path: "/secrets/harmony/provision.p7b"
  cert_path: "/secrets/harmony/debug_cert.cer"
  key_path: "/secrets/harmony/debug_key.p12"
```

### 5.3 自动上架管道

#### 5.3.1 Google Play 上架

```bash
# 使用 fastlane 自动化
fastlane supply \
  --aab build/app/outputs/bundle/release/app-release.aab \
  --track production \
  --json_key /secrets/google-play-api-key.json \
  --package_name com.autodev.{app_id} \
  --skip_upload_metadata false \
  --skip_upload_images false \
  --skip_upload_screenshots false
```

**所需配置**：
- Google Play Console 开发者账号（$25 一次性）
- Service Account JSON Key（API 访问）
- 每个 App 的唯一 package name

#### 5.3.2 App Store 上架

```bash
# 使用 fastlane deliver
fastlane deliver \
  --ipa build/ios/ipa/Runner.ipa \
  --app_identifier com.autodev.{app_id} \
  --team_id ${APPLE_TEAM_ID} \
  --submit_for_review true \
  --automatic_release true \
  --force true
```

**所需配置**：
- Apple Developer 账号（$99/年）
- App Store Connect API Key
- 每个 App 需要在 ASC 中预先创建 App Record

#### 5.3.3 华为 AppGallery 上架

```bash
# 使用 AGC Publishing API
curl -X POST \
  "https://connect-api.cloud.huawei.com/api/publish/v2/app-file-info" \
  -H "Authorization: Bearer ${AGC_TOKEN}" \
  -H "client_id: ${AGC_CLIENT_ID}" \
  -F "file=@build/ohos/hap/app-release.hap" \
  -F "fileType=5"
```

**所需配置**：
- 华为 AGC 开发者账号（免费，需实名）
- AGC API 凭证（client_id + client_secret）
- 每个 App 的 AGC 项目

### 5.4 App 身份管理数据库

每个自动生成的 App 需要独立的身份信息：

```sql
CREATE TABLE app_registry (
  id              SERIAL PRIMARY KEY,
  demand_id       VARCHAR(50) UNIQUE NOT NULL,
  app_name        VARCHAR(100) NOT NULL,
  
  -- 包名/Bundle ID
  android_package VARCHAR(200) UNIQUE,
  ios_bundle_id   VARCHAR(200) UNIQUE,
  harmony_bundle  VARCHAR(200) UNIQUE,
  
  -- 商店信息
  gplay_app_id    VARCHAR(200),
  appstore_app_id VARCHAR(200),
  agc_app_id      VARCHAR(200),
  
  -- 广告单元
  admob_banner_id    VARCHAR(100),
  admob_interstitial VARCHAR(100),
  
  -- 状态
  status          VARCHAR(20) DEFAULT 'building',
  -- building / built / submitted / live / rejected / suspended
  
  -- 签名信息
  keystore_alias  VARCHAR(50),
  
  created_at      TIMESTAMP DEFAULT NOW(),
  published_at    TIMESTAMP,
  last_updated    TIMESTAMP
);
```

---

## 七、模块 6：运营监控层

### 6.1 数据采集

| 编号 | 指标 | 数据源 | 采集频率 |
|------|------|--------|---------|
| 6.1.1 | 下载量 | Google Play / ASC / AGC API | 每日 |
| 6.1.2 | 评分与评论 | 各商店 API | 每 6 小时 |
| 6.1.3 | 崩溃率 | Firebase Crashlytics | 实时 |
| 6.1.4 | DAU/MAU | Firebase Analytics | 每日 |
| 6.1.5 | 广告收入 | AdMob API | 每日 |
| 6.1.6 | 审核状态 | 各商店 API | 每小时 |

### 6.2 自动响应机制

| 触发条件 | 自动动作 |
|----------|---------|
| 评分 < 3.0 | 分析差评 → 触发更新迭代 |
| 崩溃率 > 1% | 分析 Crashlytics → 自动修复 → 发布热更新 |
| 审核被拒 | 解析拒审原因 → LLM 修改 → 重新提交 |
| 日下载 > 100 | 标记为潜力 App → 加大投入（增加功能/优化UI） |
| 30 天下载 < 10 | 标记为低效 App → 考虑下架回收资源 |
| 用户评论请求功能 | NLP 提取功能需求 → 加入迭代队列 |

### 6.3 运营看板 Dashboard

```
┌─────────────────────────────────────────────────┐
│              AutoDev Agent Dashboard             │
├──────────┬──────────┬───────────┬───────────────┤
│ 总 App 数 │ 已上架   │ 审核中     │ 开发中        │
│   156    │   89     │    12     │     7         │
├──────────┴──────────┴───────────┴───────────────┤
│ 今日收入: $47.82  │ 总下载: 23,456  │ 平均评分: 4.1 │
├─────────────────────────────────────────────────┤
│ 最近 24 小时流水线:                               │
│ ✅ 需求采集: 47 条  → 评估通过: 12 条              │
│ ✅ 代码生成: 8 个   → 编译成功: 7 个               │
│ ✅ 提交上架: 5 个   → 审核通过: 3 个               │
│ ❌ 编译失败: 1 个   → 已进入修复队列               │
│ ❌ 审核拒绝: 1 个   → 原因: 缺少隐私政策           │
├─────────────────────────────────────────────────┤
│ Top 5 App (按收入):                              │
│ 1. 极简番茄钟      $12.3/天  ⭐4.6  ↑23%        │
│ 2. 汇率秒转        $8.7/天   ⭐4.3  ↑12%        │
│ 3. 噪音分贝仪      $6.2/天   ⭐4.1  →0%         │
│ 4. 密码生成器      $5.1/天   ⭐4.4  ↑8%         │
│ 5. 色彩提取器      $4.8/天   ⭐4.2  ↓5%         │
└─────────────────────────────────────────────────┘
```

---

## 八、基础设施需求

### 8.1 服务器配置

| 用途 | 配置 | 预算/月 |
|------|------|--------|
| Agent 主控服务器 | 4C8G Ubuntu 22.04 | ~$40 |
| Flutter 构建服务器 | 8C16G（需要编译资源）| ~$80 |
| macOS 构建机 | Mac Mini M2（iOS 构建必须 macOS）| ~$100（云Mac）或一次性 $599 |
| 数据库 | PostgreSQL（可用 Supabase 免费版起步） | $0-25 |
| 对象存储 | 构建产物、截图、图标存储 | ~$5 |

### 8.2 第三方服务与账号

| 服务 | 用途 | 费用 |
|------|------|------|
| Claude API | 代码生成 + 需求分析 | ~$100-300/月（按量） |
| DALL-E 3 API | 图标生成 | ~$20/月 |
| Google Play Console | Android 上架 | $25 一次性 |
| Apple Developer | iOS 上架 | $99/年 |
| 华为 AGC | 鸿蒙上架 | 免费 |
| Firebase | 分析 + 崩溃监控 | 免费（Spark Plan） |
| AdMob | 广告变现 | 免费（收入分成） |
| GitHub | 代码仓库 + CI/CD | 免费 |
| 域名 | 隐私政策/官网托管 | ~$12/年 |

### 8.3 开发者账号矩阵

为降低封号风险，建议准备多套开发者账号：

```
Account Pool:
├── Google Play
│   ├── 主账号 A（前 50 个 App）
│   ├── 备用账号 B（App 51-100）
│   └── 备用账号 C（App 101+）
├── App Store
│   ├── 个人账号（前 20 个 App）
│   └── 公司账号（App 21+）
└── 华为 AGC
    └── 企业账号（无数量限制风险较低）
```

---

## 九、风险控制与合规

### 9.1 反封号策略

| 风险 | 应对措施 |
|------|---------|
| 批量低质量App被Google下架 | 控制上架节奏（每周 ≤ 5 个），确保每个 App 有真实价值 |
| iOS 审核反复被拒 | 维护「审核要点清单」，AI 生成前预检 |
| 被判定为垃圾App工厂 | 每个 App 保持视觉差异化、功能差异化 |
| AdMob 无效流量 | 不刷量、不自点，接入 Firebase 反作弊 |
| 代码雷同被检测 | 每个 App 使用不同的主题颜色、图标、文案 |

### 9.2 合规清单

- [ ] 每个 App 都有独立的隐私政策
- [ ] 隐私政策准确描述数据收集行为
- [ ] 广告符合 GDPR/CCPA 合规要求（含用户同意弹窗）
- [ ] 不收集不必要的用户数据
- [ ] 不侵犯他人知识产权（App名/图标/功能）
- [ ] 截图真实反映 App 实际功能
- [ ] 应用描述不夸大功能

---

## 十、开发路线图

### Phase 1：MVP 验证（第 1-2 周）

- [ ] 搭建 Agent 主控框架（Python + Celery）
- [ ] 实现 1 个数据源的需求采集（Reddit）
- [ ] 实现 LLM 需求评估
- [ ] 实现 1 个模板（单页工具）的代码生成
- [ ] 手动验证生成的 App 能编译运行
- [ ] 手动上架 1 个 App 到 Google Play
- **里程碑**：第一个 AI 生成的 App 上架成功

### Phase 2：自动化闭环（第 3-4 周）

- [ ] 接入 3 个以上数据源
- [ ] 实现 `dart analyze` → 自动修复循环
- [ ] 实现 `flutter build` → 自动修复循环
- [ ] 实现 Google Play 自动上架（fastlane）
- [ ] 实现应用图标自动生成
- [ ] 实现截图自动生成
- **里程碑**：端到端全自动，无需人工干预

### Phase 3：多平台扩展（第 5-6 周）

- [ ] 加入 iOS 构建和上架流水线
- [ ] 加入鸿蒙 HarmonyOS 构建和上架流水线
- [ ] 实现 4 种以上模板
- [ ] 实现运营监控 Dashboard
- **里程碑**：三端同时自动上架

### Phase 4：智能迭代（第 7-8 周）

- [ ] 实现差评自动分析 → 触发更新
- [ ] 实现审核拒绝自动处理
- [ ] 实现 A/B 测试文案/图标
- [ ] 实现 App 间数据分析和策略优化
- **里程碑**：形成自运转的 App 工厂

---

## 十一、关键技术决策摘要

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 跨平台框架 | Flutter | LLM 训练数据最多，CLI 工具链最完善 |
| 状态管理 | Riverpod | 代码生成友好，类型安全 |
| Agent 编排 | Python + Celery | 生态成熟，异步任务调度 |
| LLM | Claude API (Sonnet) | 代码生成质量高，性价比好 |
| 数据库 | PostgreSQL | 结构化数据 + JSON 字段灵活 |
| CI/CD | GitHub Actions + fastlane | 免费额度够用，社区模板多 |
| 广告 | AdMob | Flutter 官方支持，覆盖三端 |
| 分析 | Firebase | 免费，Flutter 深度集成 |
| 图标生成 | DALL-E 3 | API 调用简单，质量稳定 |
| 鸿蒙适配 | Flutter OHOS 社区版 | 与 Flutter 主线代码复用率最高 |
