---
created: 2026-09-30
updated: 2026-10-24
status: current
type: decision-log
---
# Decision Log

本文件仅记录正式取舍、理由及替代关系，不承担当前运行状态或施工流水。`APPROVED` 表示已批准的产品/架构决定；`PROPOSED — NOT APPROVED` 表示方案仍待明确批准，不能据此实施；`SUPERSEDED` 表示已被后续正式决定取代。未标实施状态的决定不代表代码完成或生产启用。历史验证证据见 `Progress-Log.md`。

## Compatibility aliases for reused legacy IDs

D047–D049 were reused for unrelated decisions in the historical log. Preserve every original number and entry, but use these unique aliases in new citations:

| Legacy ID | Unique citation alias | Decision |
|---|---|---|
| D047 | `D047-MODEL` | Model Strategy Not Frozen |
| D047 | `D047-WEBAPP-SPEC` | Web App / Personal OS V1 Business Specification |
| D047 | `D047-WEBAPP-DATA` | SecondBrain Web App Data Boundary |
| D048 | `D048-HERMES-CANARY` | Hermes 0.21.6 Conditional Evaluation |
| D048 | `D048-WEBAPP-PHASE0` | SecondBrain Web App Phase 0 Architecture |
| D049 | `D049-SKILL-SSOT` | Skill Single-Source Deferred |
| D049 | `D049-UC-SCOPE` | Universal Capture V1 Scope Expansion |

Keep legacy numeric headings for compatibility; never cite a duplicated legacy number without its alias. D053's original scope remains historical and is superseded for attachment MUST scope by `D049-UC-SCOPE` and Universal Capture Business Specification v1.1.

- D001 数据与 Agent 解耦。
- D002 /volume1/SecBR 为统一 Shared Folder。
- D003 Private 归入 SecBR，默认不授权 Agent/MCP。
- D004 Docker 继续使用 /volume1/docker。
- D005 Hermes 主选，OpenClaw 备选，DeepSeek Harness 实验。
- D006 不新增 CaptureInbox。
- D007 长期知识先 Review，再人工确认。
- D008 KnowledgeAssets 原始证据不因知识卡而删除。
- D009 Home.md 是 Obsidian 工作台，不是统一 Web 入口。
- D010 DS920+ 不承担重型本地推理。
- D011 六份文档：SUPERSEDED（2026-09-30）；Data-Flow/Properties-Schema 有效内容并入 Architecture。
- D012 /secondbrain RO，Inbox/Review/Knowledge 独立 RW namespace。
- D013 Dashboard LAN-only：192.168.3.27:9119，Basic Auth。
- D014 Portal：SUPERSEDED（2026-09-30），退役。
- D015 Skill Content 属于 SecondBrain Core；Hermes 为 Runtime/Adapter。
- D016 Agent Independence Audit：SUPERSEDED（2026-09-30），可移植性提升为开发期约束。
- D017 Staging 退役，正式项目目录为治理来源。
- D018 Home/Portal 分工：SUPERSEDED（2026-09-30）；Home 保留，Portal 退役，SecondBrain Dashboard 为剩余方向。
- D019 Portability/Packaging/Deployment Kit 为开发期硬约束；核心逻辑不得写死个人环境。
- D020 本次收敛为六份候选文档。

本次重基线：Technical-Debt 的当前问题并入 CURRENT，架构决策并入本文件，纯未来设想删除。


## D021–D029 — 2026-10-07 Architecture Alignment

- D021 Hermes 继续作为当前 Agent Platform；暂不迁移 OpenClaw、AnythingLLM、Dify、Letta、Khoj 等平台。
- D022 V1 范围保持 Universal Capture、Knowledge Retrieval、SecondBrain Dashboard 三项。
- D023 Knowledge Retrieval 采用 native search_files/read_file → QMD lexical → QMD semantic/hybrid → 更重基础设施的渐进路线；后一层须由真实 benchmark 证明必要，默认不使用 RAG / Vector DB / Qdrant。
- D024 Core Skill 开发采用 SecondBrain 业务规格 → Hermes authoring/learning → Codex audit → Human Approval；Codex 不再默认作为 Skill 作者。
- D025 Core Skill 单一真源仍为目标；下一 Hermes stable 后验证 external_dirs / create_dir / skill_manage / write_approval；验证通过才迁移生产 Skill，不预建 Adapter / rsync 层。
- D026 Open Second Brain 与 Obsidian Second Brain 仅作为方法论参考，不成为 V1 技术依赖。
- D027 Codex App-Server 继续作为候选 Runtime，等待 stable 与独立 Canary。
- D028 Hermes Desktop 是可选客户端，不属于 SecondBrain V1 关键依赖；Browser Dashboard 可独立完成 V1 管理。
- D029 Hermes 生产升级采用 stable-only；新稳定版先做 capability / regression / security diff，不追 main / canary。

## D030 — 2026-10-07

Knowledge Retrieval 采用渐进式实施：当前 V0 直接基于 Hermes 已确认可调用的 search_files + read_file。只有 benchmark 证明存在真实召回或检索质量问题，才评估 QMD；不因功能更高级而提前引入 QMD / RAG / Vector DB / Qdrant。

## D031 — 2026-10-07

当前 v0.21.5 的 Skill 实施路径为：

SecondBrain Business Specification
→ Hermes skill_manage
→ Codex Technical Audit
→ Human Approval

当前不依赖 /learn。

skills.write_approval 将先独立验证后再作为生产审批闸门使用。

Core Skill 单一真源迁移继续等待下一 Hermes stable，当前不迁移、不建立 rsync / Adapter 双副本体系。

## D032 — 2026-10-09

Skill staging 验证规则：

- skill_manage 返回 staged=true 不能单独作为 staging 成功依据。
- staging 成功至少必须同时满足：
  1. 对应 pending JSON 实际存在；
  2. pending payload / diff 可以读取。
- 如果 staged=true 但 pending JSON 不存在，应视为 staging failure。
- pending 目录可写性属于 Skill approval gate 的必要运行条件。
- 不允许通过直接写 production skills 绕过审批门。

## D033 — 2026-10-09

knowledge-retrieval 首次真实 staging 审计通过：pending JSON、payload 与 diff 均可读取，production 尚未上线。该 Skill 允许目录仅限 20-Knowledge、30-Projects、40-Memory、50-Journal，并保持只读。批准前仍建议微调冲突处理和输出模板，避免日期机械覆盖与不必要的冗长标签。

## D034 — 2026-10-09

- 50-Journal 升级为 SecondBrain 时间轴层，可承载日记、心情、草稿、随手记、不完整记录、日程、待办和当天事项结果。
- 不新增 60-Tasks 或其他 Tasks 根目录；Schedule / Todo 纳入 50-Journal 的日期文件。
- 规划方向为 50-Journal/YYYY-MM-DD.md，同日可同时承载计划、待办、实际记录和随手记，具体 schema 留待 Schedule / Journal Skill 阶段确定。
- 明确日程执行意图不走 Inbox → Review → Promote，直接进入对应日期 Journal。
- Journal 内容可由人工或 Agent 判断后进入 Review，但不自动成为正式 Knowledge。

## D035 — 2026-10-09

Skill production preflight 在请求 Human Approval 前必须至少验证：

1. pending JSON 实际存在且可读；
2. pending payload 可审计；
3. frontmatter name 存在且符合目标 Skill；
4. description 为单句、不超过 60 字符并以句号结尾；
5. operation 类型与预期一致；
6. production 状态符合预期；
7. 不得只依赖 staged=true 判断成功。

Human Approval 后必须验证 production 实际落地、最终内容、对应 pending 清除，并清理废弃 pending。

正式知识检索必须忠实于 SecondBrain 正式 SoT。若回答与现实状态不一致，应优先修复正式资料，不要求 Agent 用 session memory 偷偷覆盖正式记录。

## D036 — 2026-10-09

SecondBrain 采用 Zero-learning-cost / Low-friction 产品原则：自然语言是默认界面，内部复杂度由系统吸收；仅高风险或不可逆动作需要明确确认。

## D037 — 2026-10-09

Knowledge Retrieval V0 完成生产验收，继续使用 Hermes 原生 search_files + read_file。正式检索范围固定为 20-Knowledge、30-Projects、40-Memory、50-Journal；Fast Path、fresh-read 和历史目录排除规则属于正式业务边界。

## D038 — 2026-10-09

Hermes v0.21.5 / build 749220ef 无原生 Skill routing、query matcher 或 preload。当前不修改源码、不自建路由器、不增加 MCP/服务/复杂脚本；约 25 秒检索延迟作为 V0 已知限制，后续等待官方能力再评估。

## D039 — 2026-10-09

重要 Skill Business Specification 必须作为项目资产持久保存；不得依赖 session、state.db 或历史 conversation 恢复正式规则。检索与 Agent 工作流优先最短可信路径，避免无必要的重复工具调用。


## D040 — 2026-10-09

施工期临时使用较宽 root 权限以降低开发摩擦；这是临时开发措施，不是生产权限模型。SecondBrain V1 完成前强制收口并恢复项目级受限权限。


## D041 — 2026-10-09（SUPERSEDED IN PART by 2026-10-10 clean retest）
本条保留为当时阶段事实；其中 Qwen/GLM 结论已被后续测试部分推翻。

模型筛选与 Universal Capture 实测收口：DeepSeek-V4-Flash Raw/Review 均实际落盘 PASS，约 44 秒、约 ¥0.10，作为关键写入 workflow 主力。Qwen Skill/write_file 表面正常但 Raw/Review 未落盘，保留作轻任务备用；GLM 实际落盘验证 FAIL，保留备用。Step 遇 SiliconFlow HTTP 429/TPM limit，Hunyuan 返回 Function call is not supported，Ling 延迟过高，三者实验 profile 删除。


## D042 — 2026-10-10 Model Retest Correction

D041 is SUPERSEDED IN PART by the 2026-10-10 clean retests. Qwen Universal Capture 0.1.2 successfully landed Raw and Review; its remaining issue is extra terminal/date behavior and slower tool discipline, not write failure. GLM-4.5-Air and DeepSeek-V4-Flash both passed clean skill_view + write_file ×2 workflows without approval interruption.

## D043 — 2026-10-10 Cost-per-Success Strategy

Model selection uses cost per successful task. Qwen enters the default-model candidate set because its successful sample was materially cheaper. Before promotion, run one clean Qwen retest with unnecessary terminal removed through native Hermes toolset/profile boundaries. Do not delete GLM or DeepSeek profiles.

## D044 — 2026-10-10 Hermes 0.21.6 Canary Policy

Production remains Hermes v0.21.5 / build 749220ef and stable-only. Evaluate v0.21.6 only in an independent Canary with separate data, port, state.db/session store, and test write scope. The Canary is planned and has not been executed.

## D045 — 2026-10-10 Skill Single-Source Canary Gate

Core Skill single-source status is READY FOR CANARY VALIDATION. Validate external_dirs, discovery, skill_view, staging, write_approval, and execution in the v0.21.6 Canary first. Production Skills remain unchanged; do not create rsync, Adapter, loader, or router infrastructure. Any production migration requires a test Skill, then one-by-one migration with hash and behavior verification.

## D046 — 2026-10-10 Production Image Pinning Risk

Environment records the production image as nousresearch/hermes-agent:latest, which can drift from the stable-only policy. First verify the running image ID/digest, then evaluate pinning Compose to the verified v0.21.5 digest. This decision records a follow-up only; Compose was not changed.

## D047 — 2026-10-10 Model Strategy Not Frozen (`D047-MODEL`)
Qwen3.5-35B-A3B 为低成本默认候选但需一次 Hermes 原生工具边界下的干净 Fast Path 复测；GLM-4.5-Air 为低摩擦日常候选；DeepSeek-V4-Flash 为复杂/高可靠任务主力与兜底。最终日常默认模型保持 NOT YET FROZEN。运行时当前默认值与战略默认分开记录。

## D048 — 2026-10-10 Hermes 0.21.6 Conditional Evaluation (`D048-HERMES-CANARY`)
Production 继续 v0.21.5 / build 749220ef，V1 主线不因 0.21.6 阻塞。0.21.6 先做轻量 capability/security/release diff；仅在明确安全问题、真实缺口、可删除自研工作的明显原生能力或 v0.21.5 真实阻塞时启动针对性 Canary。不得因新 stable 自动升级。

## D049 — 2026-10-10 Skill Single-Source Deferred (`D049-SKILL-SSOT`)
Business Specification/Core Skill 继续为 Source of Truth，Hermes 为 Runtime。状态调整为 READY FOR FUTURE STABLE VALIDATION / DEFERRED；当前生产 Skill 不迁移，不单独启动升级工程，不建立 rsync / Adapter / 自研 loader。待下一次已有 Hermes 升级理由时顺带验证。

## D050 — 2026-10-10 Hermes v0.21.5 Model-Scoped Tool Boundary NO-GO

v0.21.5 toolset hard filtering is effective, but its scope is Agent/session/platform/global rather than model/profile. Qwen cannot be restricted independently while preserving GLM/DeepSeek behavior. Do not adopt global/platform workarounds, custom Router, permission middleware, or source patches. Qwen clean retest is DEFERRED / BLOCKED BY MISSING NATIVE MODEL-SCOPED TOOL ROUTING, not FAIL. Re-evaluate when upstream provides model/profile-scoped routing or when another real upgrade reason exists.

## D051 — 2026-10-10 Current Construction Model = GLM-4.5-Air

GLM-4.5-Air passed real Universal Capture Fast Path and a minimal no-tool inference. The user selected GLM-4.5-Air as the current V1 construction model; the production runtime default was switched and verified. DeepSeek-V4-Flash remains the complex/high-reliability fallback, Qwen remains a low-cost candidate, and the final long-term default remains NOT YET FROZEN. The v0.21.5 Qwen-only tool restriction is NO-GO, so no further model test is planned absent real data, provider-cost, or upstream capability change.


## D052 — 2026-10-10 Universal Capture V1 Productization Blocked Pending Formal Business Specification (HISTORICAL; blocker resolved by D053)

Universal Capture v0/0.1.2 已完成三模型 Raw/Review 双文件验收；现有 Skill 覆盖绝对路径、成功校验、partial-success 与 Human Approval 边界。排除 Private 后未能定位唯一正式 Business Specification，因此产品化实现 BLOCKED。不得以旧副本、session、state.db 或历史对话替代 Source of Truth；先确认并批准唯一 Business Specification，再按 MUST/S SHOULD/DEFERRED 矩阵实施。本决策不修改 Runtime、Skill 或业务数据。

## D053 — 2026-10-10 Universal Capture V1 Business Specification v1.0 Frozen (HISTORICAL; attachment scope superseded by D049-UC-SCOPE / Spec v1.1)

> Status: the v1.0 freeze and its attachment-DEFERRED list are historical. Canonical scope is Universal Capture Business Specification v1.1; D049-UC-SCOPE moved URL/Web, PDF, Image/Screenshot, and Audio/Voice to V1 MUST.

The canonical `business-specs/Universal-Capture-Business-Spec.md` is the Source of Truth for Universal Capture V1 business behavior. V1 MUST, SHOULD, and DEFERRED scope is frozen: text-first Raw/Review capture, collision-safe retry, verified success, explicit partial failure, and Human Approval before Promote. Web/PDF/Office/image/OCR/audio/video/generic attachments, semantic deduplication, QMD/RAG/vector, mandatory association, complex tagging, and transactional rollback remain deferred. Production Skill v0.1.2 and Runtime are unchanged; any alignment requires a separate minimal review and approval.

## D047 — Web App / Personal OS V1 Business Specification (`D047-WEBAPP-SPEC`)

- SecondBrain Web App / Personal OS is the user-facing product entry point.
- Home owns the dynamic AI workspace visual direction; it does not define every page layout.
- Navigation and page modules must be extensible; Home and Calendar are aggregation layers.
- Books, People, and Personal Events are reserved future modules.
- SecondBrain remains SoT and Hermes remains Runtime; no second formal knowledge database or duplicate Agent Runtime.
- Canonical specification: `business-specs/SecondBrain-Web-App-V1-Business-Spec.md` v1.0.
- Next step: Web App Phase 0 native capability + security audit.

## D048 — SecondBrain Web App Phase 0 Architecture (`D048-WEBAPP-PHASE0`)

SecondBrain Web App V1 will reuse Hermes Dashboard as host shell and plugin platform. SecondBrain owns the product UI/module architecture. Business data access uses a minimal authenticated Thin Adapter rather than Hermes user-plugin Python backend as the long-term business backend. This is an OPTION B-derived architecture: one SecondBrain Main UI Plugin plus native Hermes Chat/session/status APIs. Independent frontend is deferred unless future evidence shows shell/plugin constraints. Hermes upgrade and Canary are not required.

## D049 — Universal Capture V1 Scope Expansion (`D049-UC-SCOPE`)

Universal Capture V1 scope is expanded to URL/Web, PDF, Image/Screenshot, and Audio/Voice. Original evidence remains the source artifact; extraction/OCR/transcript is derived. Office documents, video, and generic binaries remain deferred. WeChat and Web App converge into one Universal Capture pipeline. This governance change does not implement the attachment pipeline or alter the accepted v0.1.3 text pipeline.


## D047 — SecondBrain Web App Data Boundary (2026-10-10) (`D047-WEBAPP-DATA`)

Hermes generic arbitrary-path filesystem API is not an approved SecondBrain Web App business data layer. Web App data access requires an authenticated semantic API and explicit server-side allowlist; Private is excluded by server policy. The current Hermes user-plugin backend is an AUTH BRIDGE / PROOF implementation only, not the final business backend. Tablet/Mobile validation is carried into Phase 2 as tooling-related validation debt, not an observed UI failure.


## D054 — 2026-10-11 Hermes Dashboard Plugin 为当前实施架构

背景：Phase 0–2 文档仍把 Plan A/B/C 记为待评估方向。选择：按实际 FE-3/FE-4 实施冻结 Hermes Dashboard Plugin + React/TypeScript/Vite + Hermes SDK 宿主生命周期，Home API 经认证 Adapter 访问。取舍：复用原生插件与宿主能力，不复制 Gemini React root、不引入第二份 React、不使用全局 Tailwind Preflight；早期 Plan A/B/C 记录保留为历史。结果：Plan A 已实施；独立 Portal 与平行 Runtime 不在当前架构中。

## D055 — 2026-10-11 测试与正式插件隔离

背景：需要在已验收测试基准上发布正式版而保持快速回退。选择：`secondbrain-fe-test` 与 `secondbrain` 使用独立身份、manifest、入口、资源、路由和快照。取舍：保留重复发布资产以获得隔离与回滚能力，不以测试 manifest 覆盖正式身份。结果：FE-4 正式版部署，FE 测试版保留；隔离以 NAS 插件路径和哈希为证。

## D056 — 2026-10-11 Gemini 视觉来源与业务功能来源分离

背景：Gemini 导出 Dashboard 含硬编码展示数据与独立 React 入口。选择：只移植已批准视觉；业务、权限、数据、双语和 Chat 生命周期以 SecondBrain/Hermes 为准。取舍：不复制演示记录、不复制 React root；缺乏可信业务来源时显示 DEMO 或 UNAVAILABLE。结果：适配 `/api/plugins/secondbrain/home`，真实语义不完整模块不伪装为 REAL。

## D057 — 2026-10-11 REAL / DEMO / UNAVAILABLE 数据语义

背景：API 返回值存在不代表其业务含义可靠。选择：REAL 仅用于真实且语义可信的数据；DEMO 必须明确标记；来源/字段缺失或不可信时用 UNAVAILABLE。取舍：宁可保留缺项，也不伪造 Projects、Agent、Review/Knowledge 状态或性能指标。结果：Today REAL 空状态、Review REAL 5 条但元数据不完整、Knowledge REAL 2 条但元数据不完整、Projects/Agent UNAVAILABLE、Brief/Activity 未接入、趋势/Donut/天气 DEMO、写入关闭。

## D058 — 2026-10-11 冻结已验收 PC 与 iPhone 视觉基准

背景：FE-3 Mac/PC 与 iPhone 视觉以及 iPhone KPI 星球定位已获用户验收。选择：正式发布沿用 FE-3 测试版视觉基准；平台专属变更须使用隔离媒体查询。取舍：不扩大为重设计，不让桌面/移动端共用定位意外回退。结果：PC/Mac 与 iPhone V1 视觉 ACCEPTED；已知轻微视觉瑕疵仍 DEFERRED。

## D059 — 2026-10-11 正式发布快照、哈希和可执行回滚

背景：正式发布不得依赖测试版身份覆盖或不可复原的原地改写。选择：发布前保留快照，核验 manifest、固定入口 bundle、CSS 与资产 SHA256，并保存可执行回滚脚本。取舍：增加发布检查步骤以保持可审计与快速恢复。结果：FE-4 快照位于 `/volume1/docker/secondbrain/hermes/data/secondbrain-fe4-rollback/fe4-20261011-155631/`；rollback.sh 存在且 executable；正式资源 SHA 已记录在 Environment-Baseline。

## D060 — 2026-10-11 FAST-PATCH 与正式发布分级

背景：重复完整架构审查拖慢低风险局部修改，但正式发布仍需完整控制。选择：低风险局部修改采用 FAST-PATCH：最小 diff、受影响类型/构建/视口验证、快照/哈希/隔离、简短报告；正式发布核对身份、真实语义、回滚和 BUILD/DEPLOY/BROWSER/USER ACCEPTANCE 分层。取舍：复用未变输入的既有成功证据，不省略变化相关检查。结果：规则记录在 Agent-Rules；未改变数据权限边界。

## D061 — 2026-10-11 Dashboard 滚动性能专项延期

背景：滚动卡顿的 Paint/FPS/Long Task 优化前后量化未完成。选择：保留已完成的安全清理（移除 11 张卡片常驻 `will-change`）并将 FE-3.2 滚动与 iPhone 性能量化标为 DEFERRED。取舍：不以推测优化已解决滚动问题，不删除已验收图表、AI 主视觉、Hover 或模块。结果：需要用户重新排期并采集可比基线后再关闭。

## D062 — 2026-10-11 FE-4 部署成功不等于 SecondBrain V1 完成

背景：正式 `/secondbrain` 已上线且用户认可总体体验，但接口仍部分缺失。选择：分别跟踪部署、视觉接受、API 覆盖、Safari 功能回归及 V1 Definition of Done。取舍：接受当前正式前端价值，同时不对缺失的 Projects/Agent/Brief/Activity 和写入能力作虚假完成声明。结果：FE-4 DEPLOYED；SecondBrain V1 NOT DONE；总体状态为 ACCEPTED WITH KNOWN ISSUES。

## D063 — 2026-10-12 个人自用、业务优先、风险适度与 Promote 隔离

**决策：** SecondBrain 按单人自用、非公开系统设计。优先满足业务需求并平衡稳定性、维护成本和开发效率；复用现有 Hermes 登录会话，允许本人用脚本/自动化调用已授权接口，不新增不必要的人机识别、反自动化或多用户体系。

**安全底线：** Promote 必须有用户明确确认；普通 Hermes Agent 不得直接修改正式 Knowledge；Private 持续隔离；重要资料具备防误删/误覆盖、审计和恢复能力。审批由服务端校验当前 Hermes 会话、同源来源和 Review 内容版本；Worker 只接受服务端生成的审批记录，不接受 Agent 声称的批准状态。

**状态与取舍：** Security-1B Worker 核心及隔离测试完成；1C-0 会话身份来源核验完成；1C-1 确认个人自用风险模型；1C-2 本地 HTTP 路由集成测试通过。生产审批队列的跨进程文件权限隔离与独立 Worker 部署尚未实现/验证，因此审批接口和 Worker 尚不具备生产启用条件。保留现有文本 Capture、Dashboard 读取路径；生产切换须另行批准并先移除普通 Hermes 的 Knowledge RW，再部署隔离审批队列和 Worker。


## D064 — 2026-10-12 Journal 低摩擦新增与追加（对话入口直写部分由 D086 取代）

**决策：** `50-Journal` 用于随手记、备忘录、碎片化想法、日常记录，以及用户明确要求保存的语音转文字。Journal 新增和按日期追加无需人工审批；即使内容不完整或缺乏上下文，也允许保留原样。AI 可补充必要时间、来源和轻量元数据，但必须保留用户原始表达。

**安全边界：** 普通 Agent 未获明确授权不得删除、覆盖或擅自改写已有 Journal 内容。Journal 不是 Knowledge；升级为正式长期知识仍须经过 Review 和用户批准。当前生产 `50-Journal` 未开放直接写入挂载，因此该决策是目标规则，不表示功能已上线。后续只增加 Journal 专用新增/追加路径，不扩大 SecondBrain 根目录 RW 权限。

## D065 — 2026-10-12 中大型开发的代码与文档同步推进

背景：阶段实施若与项目治理记录脱节，会使已实现能力、测试证据、阻塞和下一步失真。决策：中大型开发在任务下发时同步确定文档更新范围；重大决策、阶段结果、测试结果和剩余问题随阶段及时记录。小型修改与临时排查不强制更新治理文档。ChatGPT 主导架构、方案、拆解和验收标准；Codex 负责实施、核验、测试及报告。文档同步失败必须准确报告，不得将阶段标记为全部完成。此决策沿用既有 NAS SoT → Mac 工作副本 → Google Drive Live Mirror 流程。


## D066 — 2026-10-12 Hermes + SecondBrain Core Modular Monolith (PLANNED)

经批准的目标方向为 Hermes + SecondBrain Core 模块化单体：Hermes 保留登录会话、Agent Runtime、Dashboard/Chat 宿主能力；SecondBrain Core 承载 SecondBrain 领域规则和受控业务用例，通过适配接口集成。当前只记录方向，不冻结尚未设计的模块/API/部署细节。无新数据库、LLM、n8n、独立管理后台或第二 Agent Runtime。CORE-0 及 Review/Promote 阶段 A 已在 GitHub `main` 提交 `2144f23` 实现并通过 15 项本地隔离测试，尚未部署；阶段 B 实时容器核验因 Docker socket 权限不足受阻。生产系统不因本决策变更。


## D067 — 2026-10-12 Promote 使用 Core 独立单人授权（认证产品要求由 D073 取代）

**背景：** 生产 Hermes 容器以 root 运行，Basic Auth 登录凭据在其环境边界，普通 Agent/Shell 与 Hermes 共享该容器权限；v0.21.5 `request.state.session` 只在 Hermes 进程内可信。v0.21.7 RC 的 loopback `/api/auth/me` 可返回 token 校验后的 `local` 合成身份，不代表用户审批。

**决策：** Hermes 登录继续用于 Dashboard；正式 Promote 必须单独解锁 SecondBrain Core。解锁和审批由浏览器直接发给 Core，不经 Hermes 转发。Core 校验私有用户凭据、HTTPS、精确 Origin、短期 Core session 和 Review 内容摘要；普通 Agent 不得获得 Core secret、session 或 Knowledge RW。Promote Worker 是唯一 Knowledge 业务写入路径。

**状态与取舍：** Core-only 解锁、HTTP 路由与隔离测试通过；既有 NAS 证据核验过 DSM 路由、代理 peer 与临时 ACL/UID，但当前实际容器挂载尚未重验。2026-10-13 只读复核直接核实生产 Compose 声明，但 NAS Docker socket `root:root 0660` 拒绝 SSH 用户 `1026:100`，未执行提权；实际 ACL metadata 可读，运行时身份/mount/写权限仍 BLOCKED。该方案不引入数据库、SSO、多用户体系或新代理容器。


## D068 — 2026-10-12 Hermes 与 Core 共用现有 SecondBrain Compose Project

正式部署时，Hermes 与 SecondBrain Core 必须归属群晖 Container Manager 现有的同一个 SecondBrain Compose Project；Core 作为新增 service，不另建独立生产项目。容器仍保持各自权限、挂载与认证边界。独立 Compose 仅作为隔离测试候选，正式部署须适配现有项目。SecondBrain V1 完整可用后，再统一整理产品代码、数据、密钥和环境参数化及商业发行包；此前不提前开展。


## D069 — 2026-10-12 SecondBrain V1 轻量敏捷开发与执行成本优先

**决策：** SecondBrain V1 按个人使用的中小型项目管理，最高优先级为敏捷、功能和成本；控制基础风险，接受合理工程取舍，以持续交付可运行、可体验、可验收的业务功能作为进度依据。成本包含开发时间、Codex Token/模型额度、工具调用、计算资源和维护复杂度。

**执行分工与流程：** ChatGPT 负责复杂技术设计、控制方案复杂度和任务拆解；Codex 负责高效实施、最小必要验证及反馈。按低/中/高风险安排检查、集成验证、授权、保护和回退；高风险数据与权限边界仍须严格验证，不得绕过人工 Promote。约 10–15 分钟无进展时重新评估非关键排查的投入，不视为硬性超时。

**取舍：** 优先 MVP、小步交付，不为未来商业化提前建设系统；V1 基本可用后再推进公网访问，完整可用后再整理商业发行包及全面代码/数据/密钥/环境分离。D068 的同一 Compose Project 约束继续有效，本决策不重复定义。


## D070 — 2026-10-12 NAS 正式文档单向发布至 Google Drive

日常项目工作副本继续通过 Synology Drive 在 NAS 与已配置 Mac 之间双向同步；治理文档按需另走 NAS → SSH 读取 → 当前 Mac 发布脚本 → Google Drive 桌面客户端的单向发布路径，禁止用 Mac 可能过时的副本覆盖 NAS。目标统一为 `我的云端硬盘/Project Doc/<项目目录>/`。发布使用项目 Markdown 白名单，仅增量更新、不主动删除；桌面客户端云端上传异步，本地发布成功不等于云端确认。

实现状态须与决策分开陈述：本次核实到的脚本仍在 `SecondBrain V1/tools/sync-chatgpt-live.sh`，SecondBrain 配置内嵌脚本；指定 `_Shared/tools/publish-docs.sh` 和独立多项目配置文件尚不存在。
## D071 — 2026-10-13 Review 只读复用 Hermes Dashboard Session

**决策：** Dashboard 用户登录后，Review 列表与详情自动复用 Hermes 已验证的 Basic Auth Session。浏览器只调用同源 Hermes 插件 API；插件后端必须逐请求验证宿主注入的 `request.state.session`、有效期、认证模式及精确同源 Origin。不得以客户端登录标记、自报身份/请求头或未认证 Core API 作为授权。Review 读取保持只读；Promote 继续独立关闭，Knowledge RO、Private 隔离及 Hermes Knowledge RW 既有安全债不变。

**实现边界：** Hermes 插件服务端直接提供只读 Review API；不新增认证系统、数据库或跨服务信任头。Core 独立授权仍只属于未来 Promote/审批路径，不要求 Review 用户重复输入 Core 口令。代码/针对性测试完成不等于已部署；生产部署须另行批准。

## D072 — 2026-10-13 Review → Promote 阶段 B 授权与权限切换（原二次口令方案 SUPERSEDED by D073）

**审批授权：** Hermes 服务端可在受保护插件 API 中逐请求验证已认证且未过期的 Dashboard Session，适用于 Review 只读访问。该 Session 不单独证明用户审批：Hermes 与 Agent Runtime 共用执行/凭据边界，Agent 可处在相同已登录权限上下文。不得将 Hermes cookie/session、浏览器字段或 `approved=true` 转发为 Core 授权，也不得让 Hermes 插件签发 Agent 可调用的批准凭据。

**采用的最小方案：** 保留 D067 Core-only 解锁与短期 HttpOnly/Secure/SameSite Core session。Review 继续用 D071 Hermes Session 读取；Dashboard 仅在用户明确点「批准入库」并再次确认后，由浏览器直连 Core HTTPS Origin。Core 锁定时先要求现有 Core 解锁口令；Core 服务端验证自己的 session、HTTPS、精确 Origin 与 Review 文件 SHA-256，主体固定为 `owner`，再写 Core 私有审批/状态并由 Promote Worker 写 Knowledge。暂缓决定也由相同 Core 身份保护。此流程保留第二次解锁；在当前 Hermes/Agent 权限模型下，免第二次解锁而又保证 Agent 不能伪造“用户点击”，需要额外可信人类确认因子或隔离签发者，均超出既有组件与本阶段最小方案。不得通过削弱 Core 认证实现免登录。

**权限切换：** Hermes 候选为移除 `20-Knowledge` RW bind、将 `HERMES_WRITE_SAFE_ROOT` 从父目录收窄到 Inbox、Review、KnowledgeAssets Inbox 三个明确路径；Core Knowledge RW 属后续独立写入阶段，不在当前 Hermes 权限收口范围。保持 Core UID/GID `1026:100`、Review/Knowledge RO、Core state RW、unlock secret RO、Promote false，Private 不挂载。生产变更须另行确认，回退不得恢复 Hermes Knowledge RW。


## D073 — 2026-10-13 V1 统一入口、Hermes 主线与审批免二次口令

**V1 项目入口：** `docs/baseline/00-CURRENT.md` 为新会话快速掌握 V1 完整范围、已确定架构、每项 MUST 的状态、缺口与优先顺序的统一索引。正式业务行为仍由各 Business Specification 定义；运行环境细节留 Environment-Baseline，历史留 Progress-Log；不新增平行的治理文件。回答“V1 还差什么”须完整核对矩阵，不仅看 NOW。

**Runtime 选择：** 用户明确不再考虑 OpenClaw；Hermes 是唯一当前实施主线，保留 D005/D021 历史但 OpenClaw 不再是当前备选或微信接入前置方案。未来除非用户重新决策，不主动展开 OpenClaw 路线。

**审批产品要求：** Dashboard 登录会话有效期间，Review 查看、批准与暂缓不得要求第二套 Core 密码；批准仍需用户明确点击确认，普通 Hermes Agent 不得伪造批准或直接写入 Knowledge。此产品要求取代 D067/D072 要求用户再次输入 Core 密码的做法，但**不代表已找到可信的统一会话授权机制**；旧 Core 独立认证实现仍作为未投产的历史/隔离方案保留，禁止删除或绕过现有认证来伪装达标。须先证明 Agent 无法冒充真实用户批准、形成独立权限边界并测试，再另行批准生产部署。

**执行事实：** 此前普通 SSH Docker inspect/exec 因 `/var/run/docker.sock` 权限拒绝而停止。2026-10-13 后续经现有非交互 `sudo -n` 只读授权成功核实运行容器：Hermes v0.21.5 以 root 运行、Knowledge RW 子挂载与宽父级 safe-root 仍在；Core `1026:100`、Knowledge/Review RO、state RW、secret RO、Promote false；Private 未挂载。未修改生产。Hermes 权限收窄候选和验证/回滚计划已记录在 Environment-Baseline，待用户下一次确认后才可实施。阶段 A 代码 `2144f23` 通过 15 项离线测试、尚未生产部署。

**范围边界：** 微信与 Web App 为 Universal Capture V1 输入渠道，按 UC v1.1 汇入统一 Raw→Review；微信详细消息类型/聊天行为在实施前按实际 Hermes 能力确认。WorkBuddy、n8n 当前未列为已冻结 V1 MUST，不在未确认前擅自取消或加入。完整 MUST 以 Web App V1 与 UC V1.1 正式规格及 CURRENT 矩阵为准。

## D074 — 2026-10-14 独立 Web App、业务范围不变与 LAN-first / HTTPS-ready

**架构决策：** 第二大脑产品前端改由独立 React/TypeScript/Vite Web App（含自有 Chat UI）掌控，复用已验收 FE-4 视觉；Hermes 仅负责 Agent/Chat/Session/Skill 等运行能力。采用同一 Compose 的两个核心容器：SecondBrain App（前端托管 + Core 业务/API/BFF + 自有登录/轻量审批）与 Hermes（内部运行服务）。浏览器只访问 App 单一 Origin。原 D048-WEBAPP-PHASE0、D054、D066 中的“长期依附 Hermes Dashboard 宿主”选择由此替代；已部署插件仍是过渡生产事实。

**功能零缩减：** `business-specs/SecondBrain-Web-App-V1-Business-Spec.md` 的 V1 MUST/SHOULD/DEFERRED 及 `business-specs/Universal-Capture-Business-Spec.md` v1.1（含微信与 Web 输入、文本/URL/PDF/图像/音频）全部不变；Journal、Knowledge Retrieval、Agent/Skills、Obsidian 同步与人工 Promote 规则继续有效。架构迁移必须复测所有已验收功能，不将“界面独立”误当成缩减 Chat/Session/工具行为的理由。

**访问和安全：** 标准客户只交付 LAN HTTP IP+端口，客户公网/Lucky 等单独收费部署，不内置 TLS/证书/反代；本人 V1 保留 LAN/Home-WG `192.168.3.27:9119`，本人 V2 复用 DSM `https://zxwan520.com:63012` 转发到同一 App HTTP 入口。**V1 即需完成 LAN HTTP 与 DSM LAN-only HTTPS 全业务兼容回归**（同源 API、流式 Chat、Cookie/Origin/可信代理头），V2 不应重构 App/容器拓扑；公网可达性与安全开放仍独立验收。审批体验为 App 一次登录、查看后点击批准/暂缓，不要求第二密码或生物识别；Core 保留会话/来源/版本哈希/幂等/审计校验，Hermes 无审批凭据及 Knowledge 写权，Private 隔离。此机制不宣称能数学证明真人点击。

**工程门槛/状态（2026-10-14 更新）：** 首阶段已直接在正式源码实现 FE-4 独立入口、App/Core 同源静态与 API 服务、App 会话、Home/Review、Hermes Sessions/Run/SSE/stop BFF 及内置 Chat；typecheck、production frontend build、Core 离线测试和 API 集成测试通过。固定 Hermes v0.21.5 真实运行联调、全量 V1 模块及 LAN/DSM 浏览器验收仍未完成。标准 Compose 和宿主参数配置为后续部署预留，不做安装向导、授权平台或多 NAS 专属代码。**本轮仅改本地源码和基线文档：未修改 NAS/Docker/DSM/网络、未部署独立 App、未开启 Promote；生产仍使用已部署 Hermes Plugin。**

**第二轮兼容修复（2026-10-14）：** 服务端 Hermes Adapter 按生产固定上游提交 `749220ef` 转换 Sessions/Messages 的 `data` 列表和 create/fork 的嵌套 `session.id`，统一 SSE JSON 事件、工具进度和错误状态，并新增 Run 状态查询以在断线/中断后核对结果及刷新会话历史。Uvicorn 转发头只接受明确配置的单个 IP 字面地址，`.env.example` 使用已记录 DSM peer `172.18.0.1`；App 候选容器身份调整为 `1026:100`，Hermes BFF 使用 Compose service DNS `hermes`。前端 typecheck/build 与 Core 21 项测试通过。

NAS 只读核验发现 Hermes API 在 `127.0.0.1:8642` 监听、health 200、未认证 sessions/capabilities 返回 401；该端口未发布且 loopback 不可供 App service 访问，未找到 App 可用的 API key 配置。因此本次未执行带凭据真实联调，也未更改 Compose、容器、密钥或 NAS。需要单独授权配置 Hermes 内部 API bind/key 并以两个容器间验收后，才能进入正式 App 联调/部署。

**Personal OS 扩展边界补充：** 前端导航配置持有路由与模块位置，Shell/登录复用；Core 维持模块化单体，各业务独立 API/业务服务，不增加服务、数据库或通用插件框架。当前单用户登录不预建 RBAC，API 通过语义操作名 `require_action(action)` 进入统一 owner policy seam；Knowledge Promote 单独受人工审核，Memo/Calendar/新闻订阅等未来普通 CRUD 按其各自授权规则实现，不强制走 Promote。AI 定时任务优先复用 Hermes 原生 scheduler，Core 保存用户配置/业务状态及必要授权。V1 LAN HTTP 与 DSM LAN-only HTTPS 要求不变。

## D075 — 2026-10-14 Universal Capture Web 入口与多类型采集

**决策：** SecondBrain App 的 Quick Capture 和 Inbox 作为 Universal Capture Web 输入/查询界面，所有输入进入现有 Raw → Review 生命周期，沿用 UC v1.1 原件保留、元数据和失败语义；不创建第二套 Skill、元数据、数据库或自动 Promote 路径。Capture API 由现有 Core 模块化单体提供，并以 App 单用户 session/action policy 授权。

**安全与处理：** 文本、Markdown、TXT、URL/Web、PDF、图片和音频按安全文件名/大小/格式限制及独占创建保留 Raw；Review 以不覆盖写入并在文件与 SHA-256 实际校验成功后标完成。URL 每跳限制 HTTP(S)、拒绝非公网 DNS 结果、直接连接已核验 IP 并逐个重定向重新校验。处理失败保留 Raw、在 Core 私有状态中记录且可安全重试；Promote=false、Knowledge RO、Private 隔离边界不变。图片/音频只有在真实处理器可用且验证后才允许生成 Review；不得用模拟输出报成功。

**部署与视觉：** 为 App 采集所需的最小生产权限候选为 KnowledgeAssets `00-Inbox` 专用 RW bind，以及现有 App Review bind 从 RO 改为 RW；不增加 Knowledge、Private 或 SecondBrain 根目录写入。该候选仍须单独授权后部署。本阶段 FE-4 视觉冻结；用户已接受当前视觉约 90% 符合预期，暂不重新设计。

**状态：** D075 本地实现与自动化测试完成；生产未部署/未获挂载变更授权。文本、URL、可提取 PDF 已本地测试；图像识别与音频转写能力未在 App/Core 配置，二者当前只能保留 Raw 并报告部分成功。微信仍为 V1 MUST，后续复用本 Capture 流程接入。

## D076 — 2026-10-15 统一对话/收录入口与 AI 智能整理

### APPROVED：产品与数据边界

- Chat 默认发送到 Hermes；只有用户明确切换到“收录到第二大脑”时才调用 Core Capture。禁止自动猜测意图。Inbox 管理已收录素材，Review 独立存在。**2026-10-17 D086 更新：** Hermes 可以主动建议收录；只有用户同意后才由 Core 实际保存，不再要求用户先切换模式。
- Organizer 提供固定时间和间隔两种互斥设置、立即整理与运行状态。调度在 NAS 本地由 App/Core 持久运行；手动与定时任务共用锁、游标和执行器。该决定取代旧的“只有每天 00:30”方案。
- 默认配置为启用每 4 小时；用户切换到固定时间模式时预设 `00:30 Asia/Shanghai`。间隔选项为 1、2、3、4、6、8、12、24 小时，配置持久化且修改无需重新部署。
- Organizer 读取获准的持久化 Hermes 会话，只处理新增用户消息；保留有限上下文和可核验来源，不把 AI 总结写成用户真实经历。配置、游标和作业留在 Core 私有 state；输出是 Review 草稿，不能直接写 Knowledge。
- 只有无工具且满足约束门槛的模型调用器可执行整理。没有可验证安全与费用边界时必须 fail closed；普通 Hermes Agent Runtime 不自动等同于受控整理模型。

### APPROVED：受控模型调用方向

评估后采用 Core 内可替换的文本 ModelAdapter 作为受控调用边界，不经 Hermes Agent Runtime 执行整理；适配器请求不得携带 tools、Skills 或文件执行能力。SiliconFlow 是已评测的候选平台，但模型评测结果不等于生产连接、费用硬封顶、数据出站授权或上线批准。

### APPROVED — 2026-10-15 Core 本地软预算门禁

用户批准以 Core 服务端持久化软预算替代 Organizer 对供应商硬输入 Token / 单作业硬费用证明的强制依赖；仅替代该执行资格门槛，不表示供应商费用硬封顶、Tokenizer 硬输入上限或真实数据出站获批。首选 exact model 为 `deepseek-ai/DeepSeek-V4-Flash`；Core 在请求前原子预留额度，按每作业最多 3 次、每日最多 12 次、每月估算 ¥10、单并发、45 秒超时、输出最多 1,200 Token、请求体字节上限及本地估算输入 6,000 Token 实施限制。费率与 Token 成本是本地估算；供应商返回 usage 也不是结算账单。未知响应保留占用并禁止自动重试；不切换模型。模型和 Scheduler 各自默认关闭，单独开启模型不启动常驻任务。间隔 4 小时 / 固定 `00:30 Asia/Shanghai` 仅为已有可配置计划设置，不构成 Scheduler 启动批准。Knowledge 写入、Promote、Private 隔离和人工 Review 审批边界不变。真实凭据、真实内容分析、数据出站与生产启用仍须另行批准。

### PROPOSED — NOT APPROVED：首次历史回溯

Organizer 首次纳入会话目前以当时的消息数和尾部 ID 建基线，默认跳过已有历史。可考虑增加用户明确选择的“不回溯/当天/最近 4、12、24 小时”有限回溯窗口，并固定时间水位、按 `session_id:message_id` 去重。此方案尚未批准实现；禁止默认全量扫描。源 API 没有已验证的分页快照令牌或删除墓碑，任何有限回溯仍须提示覆盖缺口。

实现、测试、模型评测、生产部署和运行验收均不属于本决策记录；对应证据按日期保存在 `Progress-Log.md`，当前状态见 `00-CURRENT.md` 与 `Environment-Baseline.md`。

## D077 — 2026-10-16 Personal Intelligence：产品最高目标、双闭环与优先返工（APPROVED）

**背景/用户明确确认：** 用户的 SecondBrain 不是需要用户说“去知识库检索”才记得历史的文件搜索 AI，而是与用户共同成长、形成长期个人认知、能够自然联想已有记忆及知识、主动提出有依据的思考/规划建议的个人 AI 伙伴。用户明确批准：可以从获准互动中**默认自主学习低风险偏好、经验、习惯**，无须逐条人工审核；正式 Knowledge 入库、重要业务规则/高风险动作仍需批准；允许必要返工实现产品目标。

**不可退让的产品体验原则（原产品方向独有内容归并）：**
- 不要求用户发出“搜索知识库”指令；日常交谈自动关联相关长期记忆与可靠知识，精确事实从原始资料核实。
- 获准互动持续学习稳定偏好、习惯、目标、重要经历和更正原因；必须区分用户明示、可信重复经验和模型推断，提供来源、历史、撤销和过期控制，不把一次情绪/随口假设直接当永久用户特征。
- 低风险个人记忆默认可自动更新，但不得自动 Promote 正式 Knowledge 或覆盖 Journal 原文；重大 Skill、权限、生产和外部动作保留用户审批。
- 主动规划必须有依据、可节流、可关闭，不把建议宣称为已经执行；功能优先，不为技术概念引入第二 Runtime、图数据库或新平台。
- 原有自然场景保持：碎碎念/日记、待办和提醒、文本/链接/图片/PDF/音频收录、自然聊天、与项目事件相关的建议；用户明确意图触发专用业务 API。非目标包括把所有文件训练进模型参数、用记忆替代证据检索、未经授权自动执行现实动作。

**正式产品决定：**
1. D077 在本 `Decision-Log.md` 记录**最高产品目标及已批准取舍**，`Architecture.md` 管理稳定设计，`00-CURRENT.md` 管理体验验收与路线；现有 V1 业务规格 MUST 不取消，但“采集→Review→Promote→检索 + Web 页面齐备”已不足以单独宣称整个 SecondBrain 目标达成。优先新增可验收的 Companion MVP：自动个人记忆学习、无检索提示的主动关联、跨会话纠正/演进、自然语言 Journal/Task、文件整理与来源核验，逐步提供主动规划建议。
2. **双闭环：** 个人学习闭环允许在收窄权限下自动形成、更新、纠正、失效个人记忆；正式知识闭环依旧 Raw → Review → 用户明确批准 → Core Promote，不允许 Agent 直接改写正式 Knowledge。保存原件、来源与审计。
3. **对 D076 的补充/局部替代：** “普通 Chat 不自动 Capture/入正式 Knowledge”持续有效；但它**不阻止**基于获准聊天的受控个人记忆自动学习。Organizer 现有模型、预算、开关与“输出 Review 草稿”职责继续保留，不能把它误认作已实现个人学习；两类任务如何共享游标/调度由实验后决定。
4. **2026-10-17 D086 补充：** 此处关于明确日记意图直接追加 Journal 的对话入口规则已被 D086 的 Core Inbox 先行规则取代；Journal 专用写入、原文保护及 Knowledge 审批边界继续有效。普通闲聊不自动变成 Journal；Task 仍走自己的专用业务授权。
5. **核心架构不推翻：** Hermes 唯一 Agent Runtime；独立 SecondBrain App/Core+BFF 统一入口；NAS 数据为长期 SoT；不建立第二 Agent Runtime、第二套正式知识库、独立记忆微服务或新数据库。记忆的逻辑分层与自然联想可使用 Hermes 官方机制或 App/Core 最小适配；具体实现仍需隔离验证，不把最新 Hermes 官方功能当成生产 v0.21.5 已具备。
6. **安全与可迁移性不降低：** Private 不接触；Hermes 仍无 Knowledge RW/审批凭据；个人记忆的自动写入限制为可审核/纠正/撤销的专用存储/语义接口。外部模型访问真实个人会话及记忆需独立核准范围、费用与风险；本人一次登录需求和正式 Promote 人工确认边界保持。

**明确不作为当前技术选型：** Jev/Jev-Mem、世界模型、知识图谱、向量数据库、独立记忆 SaaS 等均暂缓。讨论过的逻辑四层记忆、Hermes Memory Provider、BFF pre-turn recall / post-turn learning、主动建议触发实现只是优先验证的**候选工程路线**，不应在未评测前新增为生产依赖。

**对当前阶段的改动：** 明确同意为上述目标返工；暂停无关 UI/模块扩张，以隔离读核验和合成样本测试为下一步最高优先级。测试普通对话不提示搜索、跨会话继承、用户纠正、冲突与精确数值回源、低风险自动学习，记录准确性/误召回、时延、模型费用、安全界限；先出路线对比和最小返工任务，然后经单独授权代码施工与生产变更。原 V1 MUST 与生产缺口继续完整列于 `00-CURRENT.md`。

**状态：** 决策/文档层已批准，**不代表**已测试、已编码、已升级、已部署或已验收。2026-10-16 本次仅更新 GitHub 正式文档，未授权修改 NAS、Hermes、密钥、生产模型/Scheduler、正式 Knowledge 或真实用户数据出站。实际下一步只以 `00-CURRENT.md` 的 NEXT 为准；原 Phase 0 只作为历史阶段验证方案。


## D078 — 2026-10-16 Hermes 原生能力保留与按需监督执行（APPROVED DECISION）

**背景与替代关系：** D077 已完成 Hermes v0.22.2 + Core JSONL 在 NAS 的合成记忆闭环，但真实模型与浏览器体验未验收（Issue [#12](https://github.com/zxwan829/SecondBrain/issues/12)）。Issue [#14](https://github.com/zxwan829/SecondBrain/issues/14) 发现普通 API Chat 原有 `terminal.backend=local`、且 `file` 可访问其他 Hermes Session 路径。初步已从 API toolsets 去掉 terminal，保留 file/skills/vision。随后用户明确推翻“简单长期禁用 file/terminal”方案，要求 **「受控或者受监督即可，不要限制」**、**「一起，改按需申请，不可以直接限制 hermes 的原生能力，要保持可控」**。此条是对 D077 的**权限与自主学习产品原则补充**，不取消 Private/Promote/Knowledge 既有强制边界。

**正式产品决定：** Hermes 作为唯一 Agent Runtime，应保留自主学习、文件阅读、知识检索、受限 Capture、Skills 自我改进与按需执行命令的能力。普通低风险操作不频繁打断；敏感/高风险操作必须由**服务端不可绕过的授权门禁**决定允许、拒绝或等待用户批准，并留下可核验的审批与执行记录；提示词或输出脱敏不能代替强制门禁。

**按操作区分：**
1. **Personal Memory：** 仍由 SecondBrain Core JSONL 权威管理来源、提炼、纠错、版本和撤销；Hermes 的 Session/Memory.md、Skills 不成为竞争性个人记忆 SoT。低风险记忆学习按 D077 已批准范围自动进行。
2. **File/Knowledge/Capture：** 保留必要正常读写工具；正式 Knowledge RO、Capture 仅现有安全写入根、Private 不挂载。跨其他 Session、内部配置、凭据或敏感 state 不能被普通 file read/search/glob 无审批绕过；允许以内部路径硬拒绝替代低价值逐次审批，但不能简单永久移除正常 file 能力。
3. **Terminal：** 最终目标是按需申请，用户看到具体命令/用途/风险后明确批准才执行；普通 API terminal 在真正技术审批门禁完成前**继续暂时关闭**，不能先打开后依赖模型“自觉申请”。
4. **Skills：** 允许模型发现、提出、生成可复用 Skills；重要 create/edit/patch/delete 先暂存并审核。优先复用 Hermes `skills.write_approval`；如果 `file` 等路径可绕过 Skills 审批，必须补足文件系统或动作级约束。暂可 CLI 审核；网页端审批是后续可用性目标，不得宣称现有浏览器支持。

**已验证的能力限制（不是完成状态）：** Hermes v0.22.2 无通用文件读取按路径逐次审批、无所有普通文件动作的通用审批；原生 Run approval endpoint 只处理已有工具 gate，不能自动使 file/terminal 变为受控；Core 尚无完整 approval.request SSE→BFF→Web UI→批准/拒绝链。上述来自 Issue #14 源码/配置诊断。部署中的 toolsets 为 `file, skills, vision`（普通 terminal 已移除），Skills 写批准还未报告生产启用。**该段为 2026-10-16 的历史能力评估，不表示 2026-10-17 的现网状态；部署及验收进度仅见 `00-CURRENT.md` / `Environment-Baseline.md`。**

**实施取舍：** Upstream First，先复用原生已有审批和固定 v0.22.2 的最小工具/路径隔离，不开发大型通用审批框架或第二 Runtime；但不能用“简单”掩盖权限绕过。分离只读设计、代码测试、NAS 配置部署、真实权限验证、浏览器体验五种状态。变更权限、镜像、生产数据与使用外部付费模型各按授权边界执行，且不影响其他 NAS 服务或家庭网络。正式历史和下一步由 `Progress-Log.md` / `00-CURRENT.md` 单独维护。

## D086 — 2026-10-17 对话先收录、Hermes 主动协作与标签类型集中管理（APPROVED PRODUCT DECISION）

**决定与理由：** SecondBrain 的日常入口保持自然聊天，Hermes 作为伙伴和秘书，可以在高价值内容出现时以自然语言询问是否收录，通过用户反馈改善判断，不能逐句打断。用户明确收录或同意建议后，所有待保存笔记内容先经 Core 保留原文、来源和时间进入统一业务 Inbox；日记碎片也如此，随后经用户确认才由 Core 专用接口形成 Journal。这样用户无需在输入时先想好分类，同时保留 Core 统一授权和审计。普通聊天不自动变成 Inbox、Journal 或正式 Knowledge；低风险个人记忆自主学习继续遵循 D077。

**替代关系：** 本决定取代 D064、D077 中“明确日记意图可从对话直接追加 Journal”的入口顺序，也扩展 D076 的“必须主动切换收录模式、禁止 AI 猜测意图”为“AI 可以提出收录建议，用户同意才实际收录”。D064 关于 Journal 保留原文、专用 API、无 Knowledge Promote 审批及禁止擅改已有记录仍有效。现有已部署/已开发的直写路径是待迁移实现，不能因产品决定而称已被改造；既有数据不自动迁移。Task 明确意图仍由独立业务规则管理。

**自主能力与风险边界：** Hermes 可在授权范围回顾历史聊天、SecondBrain/Obsidian、Task、个人记忆，主动建议收录、标签、关联和规划；可搜索公开互联网并标明来源，不得在搜索词中泄露私人内容。Private 保持排除；向外部服务发送私人数据、真实数据分析和付费调用仍按独立授权。初期允许 Hermes 随时主动联系，用户反馈转为可调整的软偏好；Web 设置分别控制主动回顾与主动联系频次。Core 对主动和被动调用分别以每日/月度估算金额门禁监督；主动耗尽暂停，被动耗尽先提示预计消耗，用户可临时追加或稍后继续。估算不等于供应商硬封顶。

**词汇管理与写入边界：** 标签与类型作为独立集中管理功能，具体词库、最多 10 种类型、自动应用、用户纠正、同义词、停用及删除审批规则以 `业务规范.md` 第 4 节为唯一细则来源。Hermes 可选用既有词汇并在获准的 SecondBrain 受控元数据中建立关联；新词、持久映射、正式 Knowledge 文件回写及批量改写分别遵守用户审批，不能绕过 Core/Promote。状态、创建日期和修改日期不是本功能的集中管理项，也不得由该功能自动创建、补写或更新；项目分类由用户手动添加。初始目录/词库盘点只读并需另行授权。

**状态：** 这是已批准的产品与信任边界，不代表实现、生产启用、真实 Vault 读取、付费模型、外部数据出站或用户体验验收。最新阶段状态和唯一 NEXT 仍见 `00-CURRENT.md`；具体业务细则见 `业务规范.md`，实施任务见 Issue #55 等关联 Issue。


## D087 — 2026-10-20 微信/飞书渠道与 Hermes/Core 边界（APPROVED ARCHITECTURE DECISION）

**决定：** Web 继续通过 SecondBrain App/BFF；微信与飞书优先复用 Hermes 原生 Gateway/渠道入口进入同一 Hermes Agent Runtime。各入口共享 SecondBrain Core 提供的业务授权、Inbox/Task/Journal/Knowledge 规则与审计，不为渠道另造第二套业务语义或 Agent Runtime。允许保留 Hermes 在授权范围内的自主学习能力，Core 仍是长期个人记忆业务数据的权威接口和授权边界。

**边界：** 该架构偏好不证明平台接入已可用、合规或已实施。真实渠道接入前须独立核对官方接口/平台规则、身份映射、用户同意证据、附件来源绑定、重放/幂等、权限和费用；未核实的能力应标为未知。合成渠道适配器不等于真实微信/飞书验收。详见 `Architecture.md` 与 `Agent-Rules.md`。

## D088 — 2026-10-20 Daily Brief V1 业务范围与触发边界（APPROVED PRODUCT DECISION）

**决定：** Daily Brief 只覆盖用户个人 Task、Project 与 Journal 回顾，不扩展为新闻或外部信息摘要。首阶段由用户明确触发生成，或由用户明确批准导入已有记录后整理；不采用无用户触发的后台自动生成/定时调度。用户触发的模型调用仍须遵守既有数据范围和费用门禁。Brief 正文与来源仍由 Core 校验和持久化，来源 ID/版本/权限不得由客户端自证。

**状态区分：** #123/#125 已交付 Core 来源验证及人工提交内容持久化切片；不代表用户触发的 AI 撰写、approved_import、后台调度或生产业务闭环已经实现。当前实现和验收以 `00-CURRENT.md` 为准。

## D089 — 2026-10-20 Journal Brief 来源选项只读 API 合同（FROZEN CONTRACT）

**冻结范围：** `GET /api/daily-brief/source-options/journal?date=YYYY-MM-DD&limit=N`。要求规范日期、limit 默认 20 且范围 1–50；校验可信 Origin、App Session、`daily_brief.read` 与 `journal.read`。响应仅包含 `status/items/freshness`，每项仅含 `kind/id/date/version`；不得返回正文、路径、Session、异常细节。只读同日记录，按稳定行 ID 排序并执行 1 MiB 单日字节、5000 行/日及 2 MiB 请求预算，超限 fail closed。

**状态：** D089 合同已由 PR #128 固定 HEAD `203f586a24acd8132620b180e9d1a76a3751a72b` 合并至 main（merge `87671644356e01d58ec2780d0c45bd11f4c3edfe`）；Core 正式只读路由已注册。B 报告 Core 全量和 localhost HTTP 验证通过，A 留有对最终 HEAD 的独立验收记录。该状态仅代表源码合并及本地合成证据，不代表部署、真实 Journal/Vault 访问或用户验收；实施状态见 `00-CURRENT.md`，证据见 `Progress-Log.md`。此 ID 取代 #97/#128 历史评论中误用的 D087 标签，不影响 D087 渠道架构决定。


## D091 — 2026-10-24 统一 Codex 主 Agent 协作（APPROVED GOVERNANCE DECISION）

**决定：** SecondBrain 从原先需要用户在 A/B 两个 Codex 会话间人工转发任务的双线协作，调整为**一个 Codex 主 Agent 统一调度**。Web 与 Core 保留为专业工作角色，不再是需要用户分别启动的固定会话；主 Agent 在现有执行环境允许时委派隔离子 Agent，无法委派时由主 Agent 在隔离 worktree 中按依赖顺序执行。主 Agent 持续读取 GitHub 既有 Issue/PR 与 CURRENT、自主分配/联调/协调复审/验证/满足门禁后合并已授权的普通 PR，并领取下一工作包。ChatGPT 负责重大架构、安全合同与阶段验收，不再逐项充当普通 PR 的复审依赖或 A/B 消息中转；未参与实现的 Review 子 Agent 可独立审查普通 PR，但不能替代 GitHub 必需审批；用户负责最终目标和需专门授权的行动。

**替代范围：** 本决定取代旧治理描述中的“两条聊天线人工协调、各自等待用户重新发令”流程。V1-Delivery-Plan 的 A/B 分工表和历史 Issue 记录保留用于技术所有权、任务依赖和审计，不代表仍需要两个独立 Codex 对话。现行执行规则以 `AGENTS.md` → `Agent-Rules.md` 为准，阶段状态以 `00-CURRENT.md` 为准。

**安全与能力边界：** 一个主 Agent 不构成独立复审：实现者不能自证独立审查；普通 PR 仍需既有复审、测试和 GitHub 门禁，敏感安全变更仍需专门授权。NAS/真实 Vault、生产部署、Private、外部渠道、付费调用、不可逆删除、Writer/Promote 和 D090/OS Gate 沿用现有禁止/审批边界。**单会话内部连续执行不等于跨会话无人值守**；持久调度器及长期凭据、预算、停止机制需以后单独设计授权，不得把本决定写成已部署自动调度服务。

## D092 — 2026-11-07 rich-page 原生富文档持久化（APPROVED ARCHITECTURE DECISION）

**授权依据：** 用户明确批准 Issue #46 的 rich-page 方案，要求完整继承固定归档 `BlockSuite-Editor@b25a75d9a3c474614c79f24ac5396c317e02bf8f` 的全部字体、样式、交互及 22 个补丁，不得用功能降级绕过无损保存。

**数据合同：** 新增 `rich-page` 原生资源，沿用现有 note-scoped BlockSuite v1 资源协议、Yjs 全状态、完整 Snapshot 和同笔记不可变 Blob；富 Page 的完整格式由原生资源保存，Markdown 保留稳定相对引用和可读内容投影。普通 Markdown 笔记仍以其原文件为权威，不自动转换、迁移或改写既有笔记。创建富 Page 必须由明确的用户操作产生新 Draft/新资源；若未来提供既有笔记创建副本入口，也必须显式操作且保留原件。

**保存与冲突：** 原生资源和可读投影复用现有 Note/资源/附件集合 ETag、权限、同笔记锁与原子文件操作；任何外部 Markdown 或资源版本变化均拒绝自动覆盖，保留远端数据和本地未保存 Yjs/Snapshot/Blob 副本。若资源已确认保存而后续 Markdown 投影写入冲突，原生资源不得回退或静默覆盖 Markdown，须显示未完成/冲突并允许显式下载、重新预览及处理双方内容；不暗中合并。稳定资源引用不得因投影导出失败丢失。

**资源治理与发布：** 不另建存储体系，rich-page 纳入既有每笔记资源/Blob 配额、历史闭包容量/保留、摘要校验、恢复及 Trash 一致性。归档 Mock backend、演示种子、迁移或清缓存行为不接入生产资料。全部归档差异逐项保留映射与验证结果；单一最终候选通过独立审查、安全检查及真实 Chromium 全量相关交互、保存/重开/冲突/恢复后，才按既有授权完成 NAS App-only 切换。其他 NAS 服务、Hermes、Private、Writer/Promote、微信及 WP6/VNext 边界不变。

**状态边界：** 本条批准实施合同，不表示已实现、测试、部署或用户验收；实时进度和唯一 NEXT 由 CURRENT 记录。
