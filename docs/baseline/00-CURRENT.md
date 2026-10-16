---
created: 2026-09-30
updated: 2026-10-16
status: current
source: GitHub SecondBrain Monorepo
---
# SecondBrain — 当前交付基线（V1 + Personal Intelligence）

> 本文件只维护最新完成定义、原 V1 完整 MUST 矩阵、新批准的智能伙伴核心能力状态、NOW/BLOCKED/DEFERRED 与文档导航。**2026-10-16 D077 已确定新产品最高目标：自然联想、持续个人学习、主动规划；详见 `Personal-Intelligence-Product-Spec.md`。** 稳定架构见 `Architecture.md`；正式取舍见 `Decision-Log.md`；运行环境见 `Environment-Baseline.md`；历史证据见 `Progress-Log.md`。

## 1. V1 完成定义与当前状态

**原 V1 业务交付门槛（保留、不缩水）：** 用户能在受支持入口完成原始内容采集、生成 Review、查看并明确批准/暂缓、由 Core 安全写入 Knowledge、再检索和使用知识；Web App V1 MUST 页面使用可信真实数据，具备基本跨设备可用性、Private 隔离和恢复能力。代码或单项页面验收不能替代完整闭环。

**新的 Companion MVP 门槛（D077，已批准、尚未实现/验收）：** 日常 Chat 不提示搜索也能自然关联长期个人记忆与可信知识；获准对话自动学习低风险偏好/经验并跨会话可用，可纠正/过期；准确事实可回源；自然语言 Journal、简单待办与 Universal Capture 共用可信数据基础；初步具备与目标/项目/任务相关的主动建议。**仅满足原 V1 搜索和 UI 功能，不等于实现 SecondBrain 的最终产品目标。**

**阶段安排：** 先做 Companion 能力审计和隔离实证，再按验证结果最小返工，随后继续完成旧 V1 所有 MUST 与多端业务收口；不要因新增目标将既有 MUST 静默延期为永久不做。

**总体状态：`NOT DONE`。** 2026-10-15 已将 GitHub `b34319a` 部署到 NAS 的 `secondbrain-app`；当前 App-only 部署快照、接口验证和回滚点见 `Environment-Baseline.md` 与 `Progress-Log.md`。D076 Organizer 设置页及本地 Mock 检查接口已部署，模型和 Scheduler 均关闭；尚待用户浏览器验收，真实用户数据自动整理未启用。此前一条合成消息完成的 SiliconFlow DeepSeek-V4-Flash 真实 API 闭环仅验证模型链路，¥0.001302 为估算而非账户账单；视觉兼容性为 `DEFERRED`。完整交付状态以以下矩阵为准。

## 2. V1 交付与验收总矩阵（回答“还缺什么”的唯一总清单）

**当前总体状态仍为 NOT DONE。** 下列旧 V1 MUST 保留原有验收事实；新增 Companion 能力在 Section 2.D 单独追踪。批准目标不等于实施/部署。

状态说明：`ACCEPTED` 已有真实用户验收；`PROD-PARTIAL` 生产部分功能可用；`DEV-TESTED` 仅代码/隔离测试；`NOT CONNECTED` 未接入真实数据；`NOT DONE` 尚无完整生产闭环；`UNKNOWN` 未取得足够证据。**此表须逐项覆盖正式规格的 MUST；若以后更改范围，先同步此表，再实施。**

### A. Agent、技能与知识工作流

| V1 项目 | 要求 / 验收要点 | 当前状态 | 仍需完成 |
|---|---|---|---|
| Hermes Agent / Chat | SecondBrain 自有 Chat 使用 Hermes 会话、Skills、工具及 Agent 能力，业务数据不绑 Agent 内存 | PROD-PARTIAL：Hermes v0.21.5；App 按 `749220ef` 适配真实响应；63013 Chat capabilities/sessions API smoke 通过，已有 Chat 浏览器验收记录 | 本轮未发送 Chat 消息；后续只在出现回归时验证，完整 V1 业务模块仍待接入 |
| Daily Capture | 低摩擦保存日常素材；不得把内容自动提升成正式 Knowledge | PROD-PARTIAL | 对照 Skill 的正式触发和行为做必要回归 |
| Knowledge Retrieval | 从批准的目录读取/搜索已存在的正式知识 | ACCEPTED：V0 已生产验收 | 仅在真实效果问题出现时优化，不强行接 RAG |
| Universal Capture：文本/Markdown/TXT | 保存 Raw、建立 Review、元数据与路径真实落盘、不自动 Promote | PROD-PARTIAL：Hermes 文本 Raw→Review 已验收；D075 App 63013 文本真实 Raw/Review 与 Inbox/Review API 验证通过 | 用户浏览器验收；微信端到端仍未接入 |
| Universal Capture：URL/Web | 保留原 URL/时间，安全抓取/提取，再形成 Review | PROD-PARTIAL：63013 真实抓取 `example.com`；Raw URL/采集时间与 SHA-256 保持不变，Review 保存提取文本 | 多站点与失败恢复的生产覆盖仍有限；用户浏览器验收 |
| Universal Capture：PDF | 保存 PDF 原件、提取正文、生成 Review | PROD-PARTIAL：D076-A.1 200 DPI 自适应已部署；独立 Canary 的合成扫描 PDF OCR 实测命中对照文字，可读 PDF 仍走 pypdf；用户反馈真实扫描件乱码/漏字；用户已接受桌面 Review 布局/滚动/排序 | 用户对照原件验收真实 OCR 质量；手机布局待验收；扩大真实 PDF 覆盖 |
| Universal Capture：图片/截图 | 保存图片、必要识别、生成 Review | PROD-PARTIAL：D076-A.1 Review/状态体验已部署；独立 Canary 中文/中英合成图片 OCR 命中对照文字；缺少视觉描述时仍为 partial | 用户浏览器复验 Review 阅读与图片 OCR；AI 视觉描述处理器 |
| Universal Capture：语音/音频 | 保存音频、转写、生成 Review | PROD-PARTIAL：63013 音频 Raw 状态持久化；D076 已适配 Hermes v0.21.5 STT 接口、限长和显式关闭开关；当前 Hermes 容器没有可验证的 STT 后端，未真实转写 | 授权并配置已验证处理器后，完成真实样本与成本验证 |
| **微信输入渠道** | **正式 UC v1.1 已明确：微信是 V1 的采集输入渠道，汇入同一 Raw→Review 流程** | **NOT DONE / 生产接入未验证** | 决定当前 Hermes 支持的可维护微信接入方式，验证真实消息端到端；聊天/各附件在微信端的细则尚未在正式规格冻结 |
| Web App 输入渠道 | Web App 也汇入同一 Universal Capture 流程，不另建写入系统 | PROD-PARTIAL：Commit `55977c8` 的统一 Composer 已部署至 63013，Inbox 与首页快速收录共用现有 Capture API；认证 API smoke 通过 | 用户验收拖放、粘贴、IME、成功清空/失败保留及手机选择；音频处理器和微信渠道 |
| Review 读取 | Web App 统一会话下展示列表/详情、来源和内容 | ACCEPTED：现有 D071 Dashboard v0.2.4；独立 App 63013 HTTPS 浏览器已显示 8 条真实 Review 与详情 | 独立 App 用户最终验收；补齐正式审批状态/动作部署 |
| Organizer 自动整理（D076） | 设置页管理 SiliconFlow/已验证模型、服务端 API Key、软预算状态、模型和 Scheduler 开关及计划；执行仍产出 Review 草稿并记录 usage/预算/游标 | PROD-DEPLOYED：`b34319a` App-only 部署，模型/Scheduler/Promote 关闭、Knowledge RO、Private 未挂载。浏览器验收发现 Mock 检查缺少可见反馈；`c619f56` 起的本地 UI 修复新增 loading/成功/错误反馈、三组响应式布局和唯一模型只读展示；本地交互测试 3 passed、typecheck/build 通过 | 此修复尚未部署；部署后待用户验收设置页交互与布局及既有 Chat/Inbox/Review。真实用户数据出站及 Scheduler 启用仍须另行批准；软预算非供应商硬上限 |
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
| Inbox | PROD-PARTIAL：D075.2 预览/定位及 PDF 文件名验收保留；D076-A.1 + Unified Capture/中文提示已部署；用户已接受 `9962001` 桌面 Review 布局/滚动/排序 | 用户浏览器/手机验收统一 Composer、Review 双栏/阅读与真实扫描件质量；音频处理和微信渠道仍待完成 |
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

### D. 新批准的 Personal Intelligence / Companion MVP（D077；全部待验证）

| 新增核心能力 | 当前证据/状态 | 最小成功验收 |
|---|---|---|
| 无提示主动关联 | NOT VERIFIED：旧 Knowledge Retrieval V0 已 ACCEPTED，但仅证明可用搜索/读取；不能证明自动联想 | 不说“搜索知识库”，自然对话能正确使用相关长期记忆；精确事实自动回源 |
| Personal Memory Core（Phase 1-A） | DEV-TESTED：默认关闭、独立注入根、追加式来源/修订记录；同一来源可保存多个不同候选并稳定幂等；未核验事实在模型召回视图中脱敏并要求回源；不表示生产已部署 | PR #4 已合并；后续阶段回归结果见 Progress-Log；生产未部署、未接真实数据 |
| 自主个人记忆学习（Phase 1-B） | DEV-TESTED：默认关闭的 Core 候选提炼与相关记忆召回挂钩；成功 Run 必须匹配 Run 前消息 ID 水位之后新增的持久消息。纠错要求去除已知表达前缀后与唯一记忆完整等价；歧义时不写；失败/取消/停止清理 pending。使用现有 Hermes `instructions` 请求字段注入受限上下文，用户 input 不改写。真实 Hermes v0.21.5 运行兼容性、长期在线行为和用户验收 UNKNOWN | PR #6 已独立审核并合并；生产启用、真实 Hermes/会话数据和模型行为验证仍须另行授权 |
| 真实 Hermes/Core 记忆链路（Phase 1-C） | BLOCKED pending runner：已完成固定源码/API 契约核查、Core `run.interrupted` pending 清理（Core 全测 156 passed / 2 subtests）并新增本地 Stub 的手动 GitHub-hosted E2E harness；真实 v0.21.5 运行尚未验证 | 正确镜像 index 为 `nousresearch/hermes-agent@sha256:d4da4a40cd7a28aba983775d9fd31d94cbf153eeb0cb9e844d6d0f612b7c24db`，amd64 config/image ID 对应 upstream `749220ef`；当前 Mac 无 Docker/Podman/Colima。新 workflow 固定版本并隔离运行；真实 LLM 质量、NAS 部署与用户验收仍 UNKNOWN |
| 分层记忆、时间/冲突管理 | TARGET DESIGN：逻辑 L1–L4 已批准为路线，物理存储和 Provider/Adapter 未冻结 | 关键偏好、当前项目、关键经历和完整证据按需关联，能识别过期/推断/冲突 |
| 碎碎念与 Journal 自然语言记录 | 业务 D064 APPROVED，生产 Journal 写入 NOT DONE | 明确“记一下”即可新增/按日追加原话；普通闲聊不意外写日记 |
| 自然语言待办/日程 | 旧 Web App Calendar 为 PARTIAL；完整 Task 写入/提醒链路 NOT VERIFIED | 能创建、查看、修改、完成真实待办；提醒送达独立验证 |
| 文件收录→理解→记忆关联 | Capture 有 PROD-PARTIAL，OCR/STT、Review→Promote 缺口仍在 | 保留原件、正确提炼候选/关联，不擅自提升第三方断言为用户事实 |
| 主动建议与规划 | NOT DONE：现有 Home/Projects/Activity 聚合仍不完整 | 根据真实目标/事件给出可解释、可关闭/节流的建议，不擅自执行 |
| 自主 Skills 学习 | NOT VERIFIED：原有 Skill 产出及审核流程不等于自动学习闭环已验收 | 重复反馈产生可复用经验；核心/高风险 Skills 仍走隔离与审批 |

**工作准则：** 不预设 Hermes v0.21.5 支持最新版官方记忆接口；不因新技术趋势直接上 Jev、世界模型、Honcho、图 DB 或 RAG。分层记忆和 loop 是目标能力的实现方式，先复用、测试现有能力再选型。

## 3. NOW / BLOCKED / DEFERRED、依赖和阻断

| 顺序 | 当前要解决的业务问题 | 完成判定 | 当前制约 |
|---|---|---|---|
| **Phase 1-A** | **可纠正、可撤销、可溯源的 Personal Memory Core** | 已合成测试；默认关闭、独立根目录与审计历史；实现及审核状态见 PR #4/后续主线 | 不等于生产部署或用户验收 |
| **Phase 1-B（已合并；DEV-TESTED）** | **受控提炼与 Chat 召回集成** | PR #6 已合并至 main；合成链路通过，默认关闭；Core/Linux 154 passed、2 subtests passed（GitHub Actions Run 38857429530）；测试不再依赖 `/private/tmp` 垫片 | Hermes v0.21.5 实际服务执行、学习质量、真实会话与 NAS 部署均未验证；生产启用须另行批准 |
| P0 | 独立 Web App 首阶段：Home、内置 Chat、Review、同源 Core/BFF 和单次 App 登录 | App image `secondbrain-app:d076-organizer-b34319a` healthy；HTTPS health/login/session、Chat capabilities、Inbox、Review 及受保护设置 API smoke 通过；匿名设置 API 401；Hermes 未重启 | 用户浏览器验收新版本设置页、Composer 和手机 Review；真实扫描 PDF 质量仍待验收；DSM Container Manager GUI 旧定义仍单独跟踪。Promote 关闭、Knowledge RO |
| P1 | Universal Capture Web 入口 + 多类型 | D076-A.1 + Unified Capture 已部署：合成中文图片/200 DPI 扫描 PDF OCR 的隔离真实验证通过；可读 PDF Fast Path、Raw/Review 哈希验证通过；Promote 和 STT 保持关闭 | 用户复验真实扫描 PDF 质量及 Composer 页面交互；AI 图像描述、Hermes STT 后端和微信端到端仍未完成。DSM GUI 项目缓存独立跟踪、不阻塞业务开发 |
| P1 | Web App 真实业务模块 | 所有正式 MUST 页面接真实数据或符合真实空态，不能 DEMO 代替；跨端可用 | Projects、Brief、Activity 等尚未接入 |
| P2 | V1 端到端回归与安全收口 | Capture→Approval→Knowledge→Retrieval；权限拒绝、回滚、同步与设备体验均有证据 | 以上依赖完成后集中执行 |

**不要把阻断项变成无限研究：** 权限和认证须够安全且有证据；其他问题遵循 FAST-EXEC，优先复用现有能力，不提前建设企业级体系。

### DEFERRED：不属于当前 V1 完成门槛

- OpenClaw：**用户已明确不再考虑**，不作为候选 Runtime 或接入前置方案（历史决策需标记被最新选择取代）。
- DOC/DOCX、PPT/PPTX、XLS/XLSX、视频、任意二进制、复杂知识图谱、语义去重、向量数据库/RAG、强制关联发现：UC 规格 DEFERRED。
- Books/People/Finance/Travel/Health 等扩展业务页、原生移动 App、完整独立管理后台：Web App 规格 DEFERRED。
- 公网直接开放、客户外网配置和商业发行包：当前阶段延期；但本人 V2 的 DSM HTTPS 兼容必须在 V1 内验收。
- WorkBuddy、n8n 等曾讨论的生态工具：**在本次已核对的 V1 正式规格中未发现其 MUST 约束**；不得擅自标为已取消或已纳入，未来如用户确认范围再更新总矩阵。
- Jev/Jev-Mem、世界模型、独立记忆 SaaS、重型向量/知识图谱：D077 明确暂缓，除非真实测试指出必要性；不作为 NEXT-0 的默认施工清单。

## 4. 文档导航

| 内容 | 权威位置 |
|---|---|
| 最高产品目标、核心体验、两种学习/知识闭环、返工路线及 NEXT-0 | `Personal-Intelligence-Product-Spec.md`、决策 D077 |
| V1 业务范围与 MUST/SHOULD/DEFERRED 契约 | `SecondBrain-Web-App-V1-Business-Spec.md`、`Universal-Capture-Business-Spec.md` |
| 稳定架构、模块关系、数据流与信任边界 | `Architecture.md` |
| 正式决定、理由及替代关系 | `Decision-Log.md` |
| 最近已核验的 NAS 运行快照、权限、端口与恢复入口 | `Environment-Baseline.md` |
| 历史实施、测试、部署、用户验收与失败复盘 | `Progress-Log.md` |
| SecondBrain 特有执行与安全规则 | `Agent-Rules.md` |
