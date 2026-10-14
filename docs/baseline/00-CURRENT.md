---
created: 2026-09-30
updated: 2026-10-14
status: current
source: GitHub SecondBrain Monorepo
---
# SecondBrain V1 — 统一项目入口与当前交付基线

> **本文件的职责：** 新会话或新 Agent 只读本文件，即应能说清楚：项目做什么、V1 交付什么、既定技术架构是什么、目前实际完成了什么、还差什么、下一步做什么、哪些事情不做。此文件是**项目总索引和最新状态**，不是第二份业务规格或历史流水账。
>
> **阅读与回答规则：** 回答“V1 还差什么”“现在做到哪里”“下一步”等问题时，必须完整核对下方「V1 交付与验收总矩阵」，而不能只根据 NOW 列表、最近施工或印象作答。只在实施具体任务时按链接增量读取相应 Business Specification、Architecture、Environment-Baseline 和历史记录。没有验收证据的功能不能标记 DONE。
>
> **冲突优先级：** 当前明确的用户决策 / 经批准的正式业务规格 > 本文件最新状态 > Architecture 与 Decision-Log 中的有效决策 > 历史 Progress-Log。重大冲突先标记并追溯，不默默混合两套方案。历史决策保留原文并标记 SUPERSEDED。

## 1. 项目定位与 V1 完成定义

**定位：** NAS 私有部署的单人 AI 第二大脑，以 SecondBrain 文件为业务权威源。**目标**由独立 SecondBrain Web App（含自有 Chat UI）提供完整交互，Core 承载业务与受控写入，Hermes 提供 Agent/Chat/Session/Skills，Obsidian 继续同步知识；不建设第二份正式知识数据库。Hermes Dashboard 原入口保留；D074 App 已暂时部署到 9120/DSM 63013，状态和验收缺口见 Environment-Baseline。

**V1 DONE 的业务含义：** 至少让用户在受支持入口完成 **采集原始内容 → 生成 Review → 在 SecondBrain Web App 看到并明确批准/暂缓 → Core 安全写入 Knowledge → 查询和继续使用知识** 的真实闭环；同时 Web App V1 规定的核心业务页须使用可信真实数据，具备基本跨设备可用性、Private 隔离和恢复能力。完成率不能只看 FE-4 视觉或代码/测试通过率。

**当下整体状态：** `NOT DONE`。D071 只读 Review 已部署并获用户 Edge 验收；文本 Universal Capture Raw→Review 已验收；Knowledge Retrieval V0 已验收。2026-10-13 按批准范围收窄并实测 Hermes Knowledge 权限，Daily/Universal Capture 与 Dashboard Review 列表/详情回归通过。2026-10-14 D074 App 已部分部署到 NAS：React classic JSX 修复与登录状态码提示已部署；App 健康，Hermes API 真实连接，HTTPS Chat SSE 已收到真实事件。App 已使用与 Hermes 不同的独立密码；63013 HTTPS 登录、Cookie 安全属性和 Home/Review API 验证通过，浏览器实际显示登录后 Home 与 8 条真实 Review 的列表/详情。Chat 的浏览器交互及用户最终验收未完成；DSM GUI 项目仍显示旧缓存定义。Promote 仍关闭且 Knowledge RO；附件采集、微信实际接入及多个真实业务模块尚未完成生产验收。

## 2. 已确定的架构与边界（接手项目必须先知）

| 维度 | 当前确定的选择 | 阶段/证据边界 |
|---|---|---|
| 设备和数据 | 群晖 DS920+；业务数据 `/volume1/SecBR/SecondBrain/`，原始证据 `/volume1/SecBR/KnowledgeAssets/` | 生产事实以 Environment-Baseline 为准 |
| 代码与项目文档 SoT | 私有 GitHub Monorepo `zxwan829/SecondBrain`；iMac 与 MBA 独立 Clone；Codex Commit/Push，部署单独授权 | NAS、Google Drive、Synology Drive 旧开发文档副本不是权威源 |
| Agent Runtime | **Hermes 为唯一当前主线**，复用 Agent/Chat/Session/Skill API；不以 Hermes Dashboard 作为目标产品前端；不考虑 OpenClaw | 目标版本与 API 兼容须先验证；当前运行 v0.21.5 |
| 后端领域层 | **两个核心容器**：SecondBrain App（前端静态托管 + Core/BFF/API/登录/审批）与 Hermes（Agent Runtime）；同一 Compose Project | NAS 运行候选 App 与固定版本 Hermes；Container Manager 项目已登记，但 GUI 容器行/Compose 缓存与目标配置未对齐；整体部署验收受阻 |
| Web App | **独立 React/TypeScript/Vite Web App，自有 Chat UI，保留全部原定 V1 功能和 FE-4 视觉基准** | React 运行时修复已部署；63013 HTTPS 登录、Home/Review 浏览器读取与 Hermes Chat SSE 服务端联调通过；Chat 浏览器交互、完整 DSM GUI 项目及用户最终验收未完成；完整 V1 未完成 |
| 数据分区 | `00-Inbox` → `10-Review` → 人工确认 → `20-Knowledge`；原始证据持久保留；Private 默认不挂载/不读取 | 不能让普通 Agent 绕过 Core 直接写 Knowledge |
| 检索 | Knowledge Retrieval V0：Hermes `search_files` + `read_file` 已生产验收 | QMD/RAG/向量检索只在有真实问题证据时评估 |
| 访问/同步 | 标准交付仅 LAN HTTP；本人 V1 LAN/Home-WG 访问 `192.168.3.27:9119`，本人 V2 通过 DSM `https://zxwan520.com:63012`；Obsidian 经 Synology Drive 同步 | V1 必须完成 **LAN HTTP + DSM LAN-only HTTPS 全业务回归**；V2 仅公网接入/安全发布，不返工应用；同步传播待核验 |
| 授权体验 | App 登录一次，查看 Review 后点击批准/暂缓；**无第二密码、Passkey 或生物识别** | Core 验证 App 会话、来源、内容版本和幂等；Hermes 无审批凭据/Knowledge 写权；具体隔离尚未验证 |
| 成本/复杂度 | 两容器、单 HTTP 入口；标准版 LAN-first，客户公网方案为另行收费部署服务 | 不内置 TLS/证书/反代/授权平台/安装向导；参数化部署便于远程交付；不改 V1 业务范围 |

**Personal OS 扩展约束（D074 补充）：** App 是可持续扩展的个人业务入口，不限于 Chat/Knowledge。前端导航由模块配置驱动；Core 保持模块化单体和独立业务 API；单用户登录由通用 action-policy seam 统一校验，不提前实现 RBAC。只有 Knowledge 正式入库走人工审核；Memo、Calendar、新闻订阅等普通业务 CRUD 按各自 Core API 授权。AI 定时任务优先复用 Hermes 原生调度。当前不创建空页面/模块、插件框架、数据库或新容器。

**协作：** ChatGPT 负责范围、技术取舍、任务分解、验收标准；Codex 负责实施、针对性测试、必要文档更新、Git 与经授权的部署。日常遵循 FAST-EXEC。代码 Push ≠ 生产部署 ≠ 用户验收。

## 3. V1 交付与验收总矩阵（回答“还缺什么”的唯一总清单）

状态说明：`ACCEPTED` 已有真实用户验收；`PROD-PARTIAL` 生产部分功能可用；`DEV-TESTED` 仅代码/隔离测试；`NOT CONNECTED` 未接入真实数据；`NOT DONE` 尚无完整生产闭环；`UNKNOWN` 未取得足够证据。**此表须逐项覆盖正式规格的 MUST；若以后更改范围，先同步此表，再实施。**

### A. Agent、技能与知识工作流

| V1 项目 | 要求 / 验收要点 | 当前状态 | 仍需完成 |
|---|---|---|---|
| Hermes Agent / Chat | SecondBrain 自有 Chat 使用 Hermes 会话、Skills、工具及 Agent 能力，业务数据不绑 Agent 内存 | PROD-PARTIAL：生产为 Hermes 原生 Chat；App 已按 v0.21.5 `749220ef` 固定响应契约实现适配并通过 Mock 回归 | NAS 只读核验见 Environment-Baseline：8642 仅监听 Hermes loopback，未能从 App 网络做授权联调；生产启用内部 API/密钥配置需单独授权，且未部署/验收 |
| Daily Capture | 低摩擦保存日常素材；不得把内容自动提升成正式 Knowledge | PROD-PARTIAL | 对照 Skill 的正式触发和行为做必要回归 |
| Knowledge Retrieval | 从批准的目录读取/搜索已存在的正式知识 | ACCEPTED：V0 已生产验收 | 仅在真实效果问题出现时优化，不强行接 RAG |
| Universal Capture：文本/Markdown/TXT | 保存 Raw、建立 Review、元数据与路径真实落盘、不自动 Promote | ACCEPTED：文本 Raw→Review | 检查其他文本格式边界及跨入口表现 |
| Universal Capture：URL/Web | 保留原 URL/时间，安全抓取/提取，再形成 Review | NOT DONE | 抓取、SSRF 防护、提取失败与原件追踪 |
| Universal Capture：PDF | 保存 PDF 原件、提取正文、生成 Review | NOT DONE | 文件处理、安全边界、失败可恢复 |
| Universal Capture：图片/截图 | 保存图片、必要识别、生成 Review | NOT DONE | 图像/OCR 处理与 Raw/Review 验证 |
| Universal Capture：语音/音频 | 保存音频、转写、生成 Review | NOT DONE | 转写、元数据及失败返回 |
| **微信输入渠道** | **正式 UC v1.1 已明确：微信是 V1 的采集输入渠道，汇入同一 Raw→Review 流程** | **NOT DONE / 生产接入未验证** | 决定当前 Hermes 支持的可维护微信接入方式，验证真实消息端到端；聊天/各附件在微信端的细则尚未在正式规格冻结 |
| Web App 输入渠道 | Web App 也汇入同一 Universal Capture 流程，不另建写入系统 | NOT DONE / 未验收 | Web 侧 Capture 输入及状态反馈联调 |
| Review 读取 | Web App 统一会话下展示列表/详情、来源和内容 | ACCEPTED：现有 D071 Dashboard v0.2.4；独立 App 63013 HTTPS 浏览器已显示 8 条真实 Review 与详情 | 独立 App 用户最终验收；补齐正式审批状态/动作部署 |
| Human Approval / Promote | 用户确认、版本哈希校验、Core 受控写入、暂缓、审计、恢复 | DEV-TESTED：阶段 A 15 项测试；生产关闭 | 收口权限、统一登录安全边界、正式部署、HTTPS 用户验收 |
| Knowledge 生命周期 | 正式资料不覆盖、可追溯；保留 Raw/Review，支持检索 | PROD-PARTIAL | 完成 Promote→Knowledge→Dashboard 搜索/查看真实闭环 |
| Journal | 用户原文留存；目标支持新增/按日期追加，不允许普通 Agent 随意覆写 | NOT DONE：生产未开放专用写入 | 按 D064 执行；**业务是目标能力，但 Web App V1 的快捷录入属于 SHOULD，不能擅自冒充核心 MUST** |

### B. Web App / Personal OS（按正式 V1 Business Spec 逐项枚举）

| 正式 V1 MUST | 当前状态 | 仍需交付 / 验收 |
|---|---|---|
| Global App Shell / 导航 / 鉴权 / 路由 | PROD-PARTIAL：FE-4 视觉接受（旧宿主） | 独立 Web App 承接既定 Shell、路由与登录；保留 FE-4 视觉 |
| Home / Dynamic Home | PROD-PARTIAL | 聚合真实 Today/Calendar/Review/Agent/Capture/Projects/Brief/Knowledge，DEMO 与 REAL 清晰区分 |
| Chat | PROD-PARTIAL：Hermes 原生（旧入口） | 独立 Chat UI 与 Hermes Session/Skill/工具/流式行为联调并验收 |
| Today / Calendar | PROD-PARTIAL：Today 真实空态 | Calendar 聚合真实数据（可按 V1 规格只读/部分能力） |
| Inbox | UNKNOWN / 独立真实业务页未确认 | 读取真实 Inbox，展示来源/类型/时间/状态 |
| Review / Approval | PROD-PARTIAL：只读已验收 | Core 审批、状态、暂缓/入库及结果反馈 |
| Projects | NOT CONNECTED：UNAVAILABLE | 真实项目、状态、最近活动、下一步、相关笔记 |
| Knowledge | PROD-PARTIAL：有最近知识数据 | 检索、标签、日期、类型、项目关系等 V1 规定能力 |
| Daily Brief | NOT CONNECTED | 最新简报、摘要、分类、历史的真实业务接口/页面 |
| Activity | NOT CONNECTED | Capture、Review、Promote、Agent、Skill、Project 的可理解真实活动记录 |
| Agent Health / 状态 | UNAVAILABLE | 接入可信可解释的 Agent 状态；位置可在 Home 或次级系统区 |
| 模块注册 / Home 与 Calendar 聚合 | UNKNOWN / 未完成验收 | 导航模块注册、页面契约、Home widget 扩展；模拟未来模块无需重构 Shell |
| Responsive / Desktop/iPad/Mobile | PROD-PARTIAL：Mac/PC 和 iPhone 视觉接受 | iPad 基本可用、iPhone Safari 功能回归、跨设备真实操作 |
| Private exclusion / Human Approval | PARTIAL：Private 隔离；Knowledge 旧 RW 风险 | 运行时写入边界、API 拒绝、审核与失败回滚验收 |

**Web App V1 SHOULD，单独跟踪、不自动阻断 MUST DONE：** Quick Capture、Journal quick entry、badges、notifications、session continuation、keyboard shortcuts、contextual actions、Agent 状态动画。具体完成情况需在对应业务施工时核实。

### C. 生产运行与工程验收

| 事项 | 当前状态 | V1 收口要求 |
|---|---|---|
| Hermes Knowledge 直接写风险 | MITIGATED / DEPLOYED：Hermes Knowledge RW 子挂载已移除，仅 `/secondbrain` RO；safe root 限于三个已核验捕获目录。普通文件工具及终端写探针均被拒；Daily/Universal Capture 与 Dashboard Review 回归通过 | 保持该权限边界；跟进重建后的原生 Chat 重连异常；不以 Hermes Knowledge RW 作为回退 |
| Core 写权限与审批认证 | DEV-TESTED：App 单次登录会话与 Core 审批 API 已在本地整合；生产仍 Promote=false、Knowledge RO | 验证 App 部署边界及 Agent 无法取得 App 会话；生产审批仍关闭，需单独授权部署和验收 |
| Private | 已有禁止挂载/访问的设计与生产静态证据 | 生产与 API 验证拒绝，不读取 Private 内容 |
| 多端与数据同步 | PARTIAL | 核实 Web App 桌面/iPad/手机主要动作及 Obsidian Mac↔NAS 文件实际双向传播 |
| 生产部署、恢复、安全收尾 | PARTIAL | 真实运行检查、变更快照和回退，收口开发期 unrestricted sudoers；验收与文档 Git 收口 |

## 4. 当前优先次序、依赖和阻断

| 顺序 | 当前要解决的业务问题 | 完成判定 | 当前制约 |
|---|---|---|---|
| P0 | 独立 Web App 首阶段：Home、内置 Chat、Review、同源 Core/BFF 和单次 App 登录 | App image `d074-e58a7f4-auth-status-ba2f040` healthy；独立 App 密码登录、HTTPS Cookie、Home/Review 浏览器读取已验证；Chat SSE 服务端已收真实事件 | 完成内置 Chat 浏览器交互与用户最终验收；DSM Container Manager 项目缓存待对齐。Promote 关闭、Knowledge RO |
| P1 | Universal Capture 多类型处理 + 微信/Web 输入渠道 | 每个 MUST 输入类型真实 Raw/Review 成功且失败可核对；微信端到端有效 | Hermes 微信集成方法仍需确证，不以 OpenClaw 作为路线 |
| P1 | Web App 真实业务模块 | 所有正式 MUST 页面接真实数据或符合真实空态，不能 DEMO 代替；跨端可用 | Projects、Brief、Activity 等尚未接入 |
| P2 | V1 端到端回归与安全收口 | Capture→Approval→Knowledge→Retrieval；权限拒绝、回滚、同步与设备体验均有证据 | 以上依赖完成后集中执行 |

**不要把阻断项变成无限研究：** 权限和认证须够安全且有证据；其他问题遵循 FAST-EXEC，优先复用现有能力，不提前建设企业级体系。

## 5. 明确不属于当前 V1 完成门槛

- OpenClaw：**用户已明确不再考虑**，不作为候选 Runtime 或接入前置方案（历史决策需标记被最新选择取代）。
- DOC/DOCX、PPT/PPTX、XLS/XLSX、视频、任意二进制、复杂知识图谱、语义去重、向量数据库/RAG、强制关联发现：UC 规格 DEFERRED。
- Books/People/Finance/Travel/Health 等扩展业务页、原生移动 App、完整独立管理后台：Web App 规格 DEFERRED。
- 公网直接开放、客户外网配置和商业发行包：当前阶段延期；但本人 V2 的 DSM HTTPS 兼容必须在 V1 内验收。
- WorkBuddy、n8n 等曾讨论的生态工具：**在本次已核对的 V1 正式规格中未发现其 MUST 约束**；不得擅自标为已取消或已纳入，未来如用户确认范围再更新总矩阵。

## 6. 信息去向：保持一个入口，不新增治理文档

| 信息类型 | 唯一维护位置 | 本文件保留什么 |
|---|---|---|
| 当前确定的 V1 全量范围、完成状态、阻断与优先级 | **本文件 `00-CURRENT.md`** | 每个 MUST 的一行状态 + 验收差距，所有渠道不隐藏 |
| 具体业务边界、成功/失败契约 | `SecondBrain-Web-App-V1-Business-Spec.md`、`Universal-Capture-Business-Spec.md` 及对应正式规格 | 链接和 MUST/SHOULD/DEFERRED 提纲，不复制长条款 |
| 稳定架构、系统间接口与信任边界 | `Architecture.md` | 已冻结选择的简明表格，不复制部署细节 |
| 当前 NAS 环境、端口、挂载、镜像、回滚资产 | `Environment-Baseline.md` | 阻断状态与查证入口 |
| 为什么这么选、何时被替代 | `Decision-Log.md` | 现行决策编号、已替代提醒 |
| 施工历史、测试命令与复盘 | `Progress-Log.md` | 阶段结果摘要，不复制过程 |
| 项目执行规则 | `AGENTS.md`、`Agent-Rules.md` | 仅保留回答 V1 状态的强制核对动作 |

## 7. 维护约束（保证下次不再漏模块）

1. **任何改变 V1 必须范围或输入渠道的正式决策**，先更新业务规格，再在此总矩阵逐项增删，并标记相应历史决定 SUPERSEDED；禁止只写进 Decision-Log。
2. **重要功能完成开发/部署/用户验收时**，Codex 在同一次相关提交中更新此矩阵对应状态与依据；小修复不单独触发文档治理工作。
3. **ChatGPT 回复「还差什么」前**，须从头核对 A/B/C 三组矩阵，再用 NOW 与环境证据排序；微信及其他输入渠道不因隐藏在子规格中而遗漏。维护此总矩阵时，应使用 `git ls-files` 盘点当前仍生效的 V1 Business Specification，将每条 MUST 与本表对应；没有证据的条目记 UNKNOWN，不凭猜测补齐。
4. **代码测试、生产部署、真实验收分开**；`UNKNOWN` 不猜测；过期状态须清楚写明“上次核验”，尤其在 Codex 正并行施工时。
5. 每次里程碑收口执行「代码/测试 → 用户验收 → 必要文档 → Commit / Push」，但生产部署始终独立授权。回答 V1 百分比时只有存在权重和验收台账才输出正式精确百分比。

---

**架构变更不缩减业务规格：** Web App 全部 V1 MUST/SHOULD、Universal Capture v1.1（含微信、文本、URL、PDF、图片、音频）及既有 Journal 规则原封保留。架构迁移的验收必须覆盖既有已验收行为。

**已明确的历史冲突与最新有效口径：**
- D074 改为独立 SecondBrain App（含自有 Chat），替代此前以 Hermes Dashboard Plugin 为长期产品前端的选择；**App 已部署到临时入口，登录后 Home/Review 浏览器读取已验证；Chat 浏览器交互与 DSM GUI 项目定义仍未完成，详见 Environment-Baseline**。
- D005/D021 曾保留 OpenClaw 作为备选，D073 已明确退出当前路线；历史保留，不再将其推荐为 V1 技术选项。
- D072 原方案仍可作为历史安全研究，但要求额外 Core 密码的部分被 D073 取代；统一会话安全方案未确定，不得标为实现或生产可用。
- Architecture 已同步更新 D071 与 D072 的有效状态；运行版本和验收事实以本文件及 Environment-Baseline 为准。
- D022 曾用三大方向概括 V1，不可据此漏掉 Web App 的具体 MUST 页面和 Universal Capture v1.1 的微信输入渠道。
