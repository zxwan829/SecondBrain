---
updated: 2026-10-15
status: current
type: architecture
---
# SecondBrain V1/V2 Architecture

本文件只记录稳定架构、模块关系、数据流、接口与信任边界。运行版本、部署阶段、测试结果和未完成施工不在此维护，分别见 `Environment-Baseline.md` 与 `Progress-Log.md`。

## 1. 稳定架构边界

- SecondBrain 文件是业务数据的权威源；Hermes 提供 Agent Runtime、Chat、Session、Skills 与工具执行能力。SecondBrain 不复制 Agent Runtime 或建立第二份正式知识库。
- 产品入口是独立 SecondBrain Web App。Hermes Dashboard 可以作为既有入口保留，但不是 App 的宿主依赖。
- 部署单元为两个核心服务：SecondBrain App（React/Vite 静态前端 + Core/BFF/API）与 Hermes Runtime。Core 保持模块化单体；不为业务模块增加独立容器、数据库、通用网关或插件平台。
- 浏览器只调用 App 同源相对路径。App 服务端通过内部接口访问 Hermes；Hermes API 凭据不发送到浏览器。
- FE-4 视觉与正式业务规格独立：架构演进不得缩减 Web App V1 MUST、Universal Capture v1.1、微信输入渠道或 Journal 规则。

## 2. 模块与接口关系

```text
浏览器
  └─ SecondBrain App（同源 UI、登录会话、Core API、BFF）
       ├─ Capture / Inbox
       ├─ Review / Approval / Promote
       ├─ Organizer / 持久化调度与状态
       ├─ Knowledge Retrieval
       └─ Hermes 内部 API（Session、消息、Run、SSE、Skills）
              └─ Hermes Agent Runtime
```

- 前端导航和页面路由可扩展；Shell、登录和通用导航不与 Chat 或 Review 页面绑定。
- Core 业务按模块划分服务和 API，通过清晰接口共享一个进程与部署单元。单用户身份由统一 action-policy 接口校验，不提前实现复杂 RBAC。
- Knowledge Promote 与普通业务写入分离。进入正式 Knowledge 必须人工审核；Memo、Calendar、新闻订阅等未来业务按各自授权的 Core API 执行 CRUD，不统一进入 Promote。
- Hermes 负责对话与 Agent 执行；SecondBrain Core 负责业务状态、Capture 生命周期、审批记录、Organizer 配置/游标/作业以及受控的 Review 草稿。

## 3. 核心数据流

### 3.1 Chat

浏览器 Chat → App BFF → Hermes Session/Run API → SSE/状态回读 → App 前端。会话历史以 Hermes 持久化 Session API 为来源，不以浏览器临时状态为唯一记录。Chat 输入不会自动变成永久知识。

### 3.2 Universal Capture

用户明确选择收录 → App Capture API → 独占保存 Raw 原件与来源元数据 → 处理/提取 → 以可核验关系创建 Review。Raw 是不可覆盖的原始证据；失败时保留 Raw 和可恢复状态。Capture 不直接写 Knowledge。

### 3.3 Review 与 Promote

Review 从 SecondBrain 文件和 Core 审核状态读取。用户明确批准后，Core 验证会话、精确来源、Review 版本哈希、幂等状态并记录审计，再由受控 Promote Worker 写入 Knowledge。暂缓决定保留服务端状态。Hermes Agent、前端自报身份和普通文件工具都不是正式 Knowledge 写入授权来源。

### 3.4 AI 自动整理

Core 持久调度器和手动入口共用同一 Organizer、作业锁、消息游标与恢复状态。Organizer 只处理授权来源中新增的用户消息；可携带有限旧上下文，但输出必须区分用户原文与 AI 提炼内容，并保留会话/消息/时间来源。模型接口必须是无工具、受输入/输出/超时/并发/请求预算约束的文本 Adapter。输出只生成 Review 草稿，不写 Knowledge；没有通过安全和费用门槛时执行器必须关闭。

## 4. 数据分区与信任边界

| 区域/能力 | 允许边界 | 禁止边界 |
|---|---|---|
| `00-Inbox` / KnowledgeAssets Inbox | 按 Capture/授权流程接收原件 | 用派生内容覆盖原件；从失败推断可删除 |
| `10-Review` | Core 创建待审核草稿；App 展示来源和审核状态 | AI/Agent 自动 Promote；覆盖人工编辑或审核文件 |
| `20-Knowledge` | 仅受控 Core Promote Worker 在用户批准后写入 | Hermes 普通 Agent、通用文件工具、未授权业务模块写入 |
| `50-Journal` | 按正式 Journal 规则新增/追加 | 普通 Agent 未授权改写、删除既有内容 |
| Private | 默认无挂载、无读取、无索引 | 通过检索、自动整理、日志或工具旁路读取 |

- App Session 是浏览器用户操作的服务端认证依据；Core 校验具体操作权限、Origin/Host、版本与幂等，不信任前端传来的身份字段。
- Hermes Runtime 与 App/Core 的凭据和文件权限必须隔离。Hermes Session 或 Agent 可访问的凭据不能单独证明用户亲自批准。
- Knowledge 权限边界由只读挂载与 Core 受控写入共同强制；工具级安全根不是操作系统隔离的替代品。
- 外部模型出站需有明确的数据范围授权、服务端凭据管理和可接受的成本控制；本地估算、`max_tokens`、请求超时或账户级速率限制不能冒充供应商硬费用上限。

## 5. 接口与扩展约束

- 浏览器到 App：同源 HTTPS/HTTP 部署入口、相对路径业务 API、受保护 Cookie、SSE 流式响应。
- App 到 Hermes：Compose 内部服务发现及受认证 API；不发布 Hermes API 端口到宿主或公网。
- App 到业务文件：通过显式根路径和模块服务访问 Inbox、Review、Knowledge 等数据区；Private 不在允许根路径内。
- 新业务优先扩展 Core 模块与 API；只有确认超出模块化单体能力后才重新评估部署边界。不得为了未来设想预建空模块、复杂插件机制或数据库。
- 入口、数据契约与验收以正式规格为准：`SecondBrain-Web-App-V1-Business-Spec.md`、`Universal-Capture-Business-Spec.md`。架构决策的理由和替代关系见 `Decision-Log.md`。
