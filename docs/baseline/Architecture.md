---
updated: 2026-10-17
status: current
type: architecture
---
# SecondBrain V1/V2 Architecture

本文件记录已批准的架构与信任边界；智能伙伴产品目标见 `Decision-Log.md` D077，对话收录与词汇管理取舍见 D086 和 `业务规范.md`；当前业务范围与验收见 `00-CURRENT.md`。其中已批准的是产品能力和现有服务/数据边界；Memory Provider、具体目录/索引与主动规划内部实现仍属待验证技术选型，不能当成现网实现。运行版本、部署阶段、测试结果和未完成施工不在此维护，分别见 `00-CURRENT.md`、`Environment-Baseline.md` 与 `Progress-Log.md`。

## 1. 稳定架构边界

- **产品总目标：** SecondBrain 是随用户互动长期成长、无需用户下达搜索指令就能自然联想相关记忆和知识、在适当时机主动思考和规划的个人智能伙伴；不以“保存文件、手动检索成功”作为产品充分完成条件。
- **双闭环：** Personal Learning Loop 可在授权范围自动学习低风险个人记忆；Knowledge Integrity Loop 仍要求 Raw/Review、用户明确批准才能 Promote。两者互通但绝不混淆；“普通 Chat 不自动 Capture”不禁止受控记忆学习。
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
       ├─ Knowledge Retrieval / Personal Memory（目标：来源、版本、纠错、召回）
       ├─ Journal / Task（专用授权写入；提醒送达需单验）
       ├─ Proactive Suggestions（目标能力，触发与频率待验证）
       └─ Hermes 内部 API（Session、消息、Run、SSE、Skills、可用记忆接口）
              └─ Hermes Agent Runtime（对话、推理、自主经验和 Skills）
```

- 前端导航和页面路由可扩展；Shell、登录和通用导航不与 Chat 或 Review 页面绑定。
- Core 业务按模块划分服务和 API，通过清晰接口共享一个进程与部署单元。单用户身份由统一 action-policy 接口校验，不提前实现复杂 RBAC。
- Knowledge Promote 与普通业务写入分离。进入正式 Knowledge 必须人工审核；Memo、Calendar、新闻订阅等未来业务按各自授权的 Core API 执行 CRUD，不统一进入 Promote。
- Hermes 负责对话、Agent 执行、原生 Session/Skills 与经验证的学习/回忆能力；SecondBrain Core 负责业务状态、Capture 生命周期、审批记录、Organizer 配置/游标/作业、受控 Review 草稿及目标中的长期个人记忆业务接口。不要重新实现 Hermes Agent Runtime。
- **个人记忆与知识分权：** SecondBrain 持久、可导出和可纠错的个人记忆可以自动更新，但只能使用收窄的 Core 记忆操作边界；Hermes 自有记忆不是正式知识或长期个人资料的唯一 SoT。当前采用 Core JSONL 权威存储，BFF 提供受控记忆召回/学习适配；Hermes 外部原生 Memory Provider 关闭。未来替换机制需独立论证，不能把候选写成现行架构。

### D077 智能伙伴的能力分层（批准方向，不等于全部上线）

用户入口为 Web App/Core，微信经验证后加入同一业务入口。普通 Chat 可由 Hermes 主动询问是否收录；用户明确收录或同意建议后，Core 先将原文保存到统一业务 Inbox，再经授权转为 Journal、正式 Knowledge 或其他目标。普通闲聊不自动形成 Inbox/Journal/正式 Knowledge，但获准的低风险偏好与经验可进入可纠正的 Personal Memory。明确 Task 意图走其独立业务授权；具体规则见 `业务规范.md`。

**双闭环**：Personal Learning Loop 在授权范围由 Core 建立带来源、时间、推断标记、版本、纠错/撤销的个人记忆；Knowledge Integrity Loop 仍为 Raw → Review → 用户明确批准 → Core Promote → 正式 Knowledge，不把外部材料摘要和模型推断当成用户事实。

**四层逻辑记忆（不是四套数据库）：** L1 稳定身份/偏好/长期目标；L2 项目、关系、当前任务与近期话题；L3 关键事件、日记、决策、纠正和经验；L4 原始证据、Raw/Review、Journal/Projects/正式 Knowledge。相关上下文按需装载，精确日期、金额、版本和冲突必须回源核验，不将推断强写成已证实事实。当前持久个人记忆权威是 Core JSONL；Hermes 的原生 Session/Skills 与缓存不可成为另一个业务 SoT。

**建议与自主边界：** 主动建议应与目标、项目、待办、事件关联，携带依据并支持去重、节流、关闭；建议不等于执行。Skills 可以形成候选经验，但重要修改须经原生待审核流程；文件/命令/出站行为遵守 D078 强制权限。Journal 只新增/按日追加原文，提醒的任务落盘与通知送达分开验收。

## 3. 核心数据流

### 3.1 Chat

浏览器 Chat → App BFF（目标：预先装入少量高相关长期记忆/项目背景；具体接入点待验）→ Hermes Session/Run API → SSE/状态回读 → App 前端。会话历史以 Hermes 持久化 Session API 为来源，不以浏览器临时状态为唯一记录。

普通 Chat **不会自动变成 Inbox、Journal、Raw 或正式 Knowledge**；Hermes 可在高价值内容出现时征询收录，Core 负责授权和实际保存。在用户批准的范围内，低风险偏好、经验、目标变化可以在对话后被受控提炼为**可检查/纠正的个人记忆**。遇到日期、数据、决策版本或相互冲突的信息时，Hermes 应自动从有权限的正式资料核验，而非仅凭旧记忆自信作答；无需用户手动要求检索。

### 3.2 Universal Capture

用户明确选择收录或同意 Hermes 的收录建议 → App/Core Capture API → 独占保存 Raw 原件与来源元数据至统一业务 Inbox → 处理/提取 → 以可核验关系创建 Review。Raw 是不可覆盖的原始证据；失败时保留 Raw 和可恢复状态。Capture 不直接写 Knowledge。

### 3.3 Review 与 Promote

Review 从 SecondBrain 文件和 Core 审核状态读取。用户明确批准后，Core 验证会话、精确来源、Review 版本哈希、幂等状态并记录审计，再由受控 Promote Worker 写入 Knowledge。暂缓决定保留服务端状态。Hermes Agent、前端自报身份和普通文件工具都不是正式 Knowledge 写入授权来源。

### 3.4 AI 自动整理

**旧 D076 Organizer（保留现有功能边界）：** Core 持久调度器和手动入口共用同一 Organizer、作业锁、消息游标与恢复状态。Organizer 只处理授权来源中新增的用户消息；可携带有限旧上下文，但输出必须区分用户原文与 AI 提炼内容，并保留会话/消息/时间来源。模型接口必须是无工具、受输入/输出/超时/并发/请求预算约束的文本 Adapter。输出只生成 Review 草稿，不写 Knowledge；没有通过安全和费用门槛时执行器必须关闭。

**新增目标：个人学习闭环独立于 Organizer 的正式知识草稿。** 获准的对话和实际结果可以形成可版本化、可撤销的低风险个人记忆；需要避免与 Organizer 重复扫描、重复提炼或自动 Promote。学习触发和质量仍需真实会话验收，已部署 Core JSONL，不再把存储路线写成未决，不能把现有定时整理开关直接当成学习功能开关。

### 3.5 Journal、Task 与主动规划（目标行为）

对话中的“记一下/写日记”按 D086 先由 Core 保存原文至统一 Inbox；用户确认形成日记后再调用 Core 专用 Journal API 新增/按日期追加，无需正式 Knowledge Promote。现有显式命令直写行为是待调整实现，不能视作符合新入口顺序。“添加待办”仍走独立 Core Task 语义 API；普通 Agent 无权覆盖历史 Journal 内容。待办从同一时间轴演进，增改状态和提醒通知必须以持久状态/实际送达证据为准。各数据根与实现状态见 `00-CURRENT.md` 和 `Environment-Baseline.md`，不可根据 API 存在推断已部署。

**D081-D083 Core 合约（已在并行开发分支实现，尚未集成到 main 或部署）：** Journal 使用可选配置 `SB_JOURNAL_ROOT`，存储按日期追加的 JSONL；Core 提供 `GET /api/journal/{day}` 与 `POST /api/journal/entries`，分别校验 `journal.read` / `journal.append`。Task 使用独立可选配置 `SB_TASK_ROOT`，以 `tasks.json` 保存待办和变更历史；Core 提供 `GET/POST /api/tasks` 及 `PATCH /api/tasks/{task_id}`，校验 `task.read` / `task.write`，创建支持幂等键，修改使用乐观版本检查。未配置对应数据根时 API fail-closed，不创建数据目录。生产部署前必须为 Core 单独配置各自受限 RW 根；Hermes 不取得这两个路径的写权限。

**Chat 显式意图（历史实现说明，现行状态见 CURRENT）：** 只有输入开头匹配 Journal 或 Task 的明确命令才调用上述 API；Journal/Task 成功时不创建额外 Hermes Session/Run，普通 Chat 继续走 Hermes Run。Journal 保留完整原文并追加；Task 的通知/提醒送达尚未实现。路由器匹配是入口分流，不替代 Core 的会话鉴权、输入校验、幂等和专用存储边界。D086 要求后续调整 Journal 对话入口，使原文先经 Core Inbox，且转为 Journal 须用户确认。

主动规划使用授权的项目、日程、待办、历史经验与近期知识，输出带来源、可去重/节流/关闭的**建议**。建议不等于执行；外发、权限修改、删除和生产操作仍需对应授权。优先复用现有 Hermes 和 Core 的调度/状态能力，不预建新 Agent、第二调度系统或新容器。

## 4. 数据分区与信任边界

| 区域/能力 | 允许边界 | 禁止边界 |
|---|---|---|
| `00-Inbox` / KnowledgeAssets Inbox | 按 Capture/授权流程接收原件 | 用派生内容覆盖原件；从失败推断可删除 |
| `10-Review` | Core 创建待审核草稿；App 展示来源和审核状态 | AI/Agent 自动 Promote；覆盖人工编辑或审核文件 |
| `20-Knowledge` | 仅受控 Core Promote Worker 在用户批准后写入 | Hermes 普通 Agent、通用文件工具、未授权业务模块写入 |
| `40-Memory`（目标） | 在用户授权范围，受控自动学习低风险偏好/经历；记录来源、时间、推断标记、修改/撤销历史 | 以模型猜测覆盖正式项目状态；无边界的文件写入；把 Hermes session 当唯一持久记忆 |
| `50-Journal` | Core 经 `SB_JOURNAL_ROOT` 专用 RW 根按日期新增/追加原文；需要 `journal.append` | 普通 Agent 未授权改写、删除既有内容；Hermes 不直接取得此存储权限 |
| Task state | Core 经独立 `SB_TASK_ROOT` 读取/创建/更新持久任务；需要 `task.read` / `task.write` | Hermes 通用文件工具或 Journal API 不得越权访问；缺少专用根时不落盘 |
| Private | 默认无挂载、无读取、无索引 | 通过检索、自动整理、日志或工具旁路读取 |

- App Session 是浏览器用户操作的服务端认证依据；Core 校验具体操作权限、Origin/Host、版本与幂等，不信任前端传来的身份字段。
- Hermes Runtime 与 App/Core 的凭据和文件权限必须隔离。Hermes Session 或 Agent 可访问的凭据不能单独证明用户亲自批准。
- **D078 普通 Chat 文件写入审批实现状态：** 目标是 Guard 在 Hermes 实际工具执行前为每次受支持的通用文件写入发起逐 Run 一次审批，Core 绑定当前用户、Session、Run 和精确参数/目标，拒绝、超时、断线或未授权均不得执行。PR #37 的实现仅覆盖 `write_file` 和单目标 replace `patch`，将未支持写工具与无法绑定目标的多文件 V4A patch fail-closed；该 PR 仍 open、未合入 main，生产不可用，Hermes 真实 API Run 审批恢复链未验证。审批 UI/代码不能作为部署或运行证据。
- Knowledge 权限边界由只读挂载与 Core 受控写入共同强制；工具级安全根不是操作系统隔离的替代品。
- 外部模型出站需有明确的数据范围授权、服务端凭据管理和可接受的成本控制；本地估算、`max_tokens`、请求超时或账户级速率限制不能冒充供应商硬费用上限。
- 自动学习不意味着无限期储存、无条件回忆或向第三方发送数据：限定可用输入、单次 token/延迟/费用预算，允许纠错与撤销；Private 依然绝对排除。

## 5. 接口与扩展约束

- 浏览器到 App：同源 HTTPS/HTTP 部署入口、相对路径业务 API、受保护 Cookie、SSE 流式响应。
- App 到 Hermes：Compose 内部服务发现及受认证 API；不发布 Hermes API 端口到宿主或公网。
- App 到业务文件：通过显式根路径和模块服务访问 Inbox、Review、Knowledge 等数据区；Private 不在允许根路径内。
- 新业务优先扩展 Core 模块与 API；只有确认超出模块化单体能力后才重新评估部署边界。不得为了未来设想预建空模块、复杂插件机制或数据库。
- 用户批准的最高产品方向见 `Decision-Log.md` D077，对话收录、主动协作和词汇管理见 D086 与 `业务规范.md`，目标效果、阶段范围和验收门槛见 `00-CURRENT.md`；原 V1 业务细则仍以 `business-specs/SecondBrain-Web-App-V1-Business-Spec.md`、`business-specs/Universal-Capture-Business-Spec.md` 为准。新增 Companion MVP 验收必须与原 V1 MUST 并行跟踪，不能默认为已上线。架构决策与替代关系见 `Decision-Log.md` D077。
