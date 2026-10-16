---
created: 2026-09-30
updated: 2026-10-17
status: current
source: GitHub SecondBrain Monorepo
---
# SecondBrain — 当前交付基线（V1 + Personal Intelligence）

> 本文件只维护最新完成定义、原 V1 完整 MUST 矩阵、新批准的智能伙伴核心能力状态、NOW/BLOCKED/DEFERRED 与文档导航。**2026-10-16 D077 已确定新产品最高目标：自然联想、持续个人学习、主动规划；详见 `Decision-Log.md` D077 / `Architecture.md`。** 稳定架构见 `Architecture.md`；正式取舍见 `Decision-Log.md`；运行环境见 `Environment-Baseline.md`；历史证据见 `Progress-Log.md`。

## 1. V1 完成定义与当前状态

**原 V1 业务交付门槛（保留、不缩水）：** 用户能在受支持入口完成原始内容采集、生成 Review、查看并明确批准/暂缓、由 Core 安全写入 Knowledge、再检索和使用知识；Web App V1 MUST 页面使用可信真实数据，具备基本跨设备可用性、Private 隔离和恢复能力。代码或单项页面验收不能替代完整闭环。

**新的 Companion MVP 门槛（D077，已批准、仍未整体实现/验收）：** 日常 Chat 不提示搜索也能自然关联长期个人记忆与可信知识；获准对话自动学习低风险偏好/经验并跨会话可用，可纠正/过期；准确事实可回源；自然语言 Journal、简单待办与 Universal Capture 共用可信数据基础；初步具备与目标/项目/任务相关的主动建议。Personal Memory / Learning Core 已部署并通过本地 Stub 合成闭环，但真实模型行为与用户体验尚待验收。**仅满足原 V1 搜索和 UI 功能，不等于实现 SecondBrain 的最终产品目标。**

**阶段安排：** 先做 Companion 能力审计和隔离实证，再按验证结果最小返工，随后继续完成旧 V1 所有 MUST 与多端业务收口；不要因新增目标将既有 MUST 静默延期为永久不做。

**总体状态：NOT DONE。** D077 Core 与 Hermes v0.22.2 已部署。按 Issue #14 授权，PR #18 已 squash 合并至 main，merge commit `84d1cbaf7daebb188fc93c369fba4a59b80895e5`；Hermes 使用固定官方 amd64 digest `a11574…c1bf05` 加一文件 fail-closed 补丁的本地镜像 `secondbrain-hermes:v0.22.2-failclosed-84d1cbaf`（Image ID `sha256:b99b1762631846d5ed3f8648ccc2c7ef2625b004234bbf276add2f8855357e9a`）。API `/health` 返回 200，Dashboard 9119 可达并按预期重定向登录；插件 Doctor 确认 D078 guard 注册 1 个 hook；API toolset 仍为 `file,skills,vision`，Terminal 未开放，Skills 写入审核 true、审批模式 manual。隔离无模型 Run 验证敏感 Session 文件读取被拒、业务文件与 Skills 只读调用可执行、dispatcher 异常 fail-closed；D077 Memory 目录仍为 `1026:100 / 0700` 且 0 个文件。Private 未挂载、Knowledge 主目录只读（已有 Capture 专用 inbox RW 挂载不变）、Promote 关闭。生产没有创建 Session/Run 或写入个人记忆；真实模型浏览器体验尚未验收。镜像构建与运行证据、回滚方式和本轮历史资产只读审计见 Environment-Baseline.md / Progress-Log.md。D076 Organizer 模型和 Scheduler 仍关闭；此前 ¥0.001302 是旧合成请求估算，不是本次部署费用或账户账单；视觉兼容性为 DEFERRED。

## 当前阶段决议：暂停开发，集中收口文档（2026-10-17）

**状态：DEVELOPMENT PAUSED / DOCUMENTATION CLOSEOUT。** 用户要求此阶段暂停开发；不得因已合并 PR #18、Hermes 新镜像健康或有限合成检查，就自动开展后续业务开发、NAS 变更、付费模型或真实个人数据测试。当前运行快照及 Hermes fail-closed image ID 以 `Environment-Baseline.md` 最新 2026-10-17 条目为准；PR #19 记录部署事实及资产审计，当前文档收口 PR 与其堆叠，尚非 main。D077 Core JSONL 数据没有新写入；Terminal 仍 OFF，Private 不挂载，Knowledge RO（Capture 专用 Inbox RW 子挂载为既有例外），Promote OFF。

**NEXT — 恢复工作时必须按顺序执行（不是当前立即施工授权）：**

1. **文档合并与基线确认**：先审查合并 PR #19 的部署/资产审计记录，再审查合并本次文档收口 PR；确认 `main` 的 CURRENT、AGENTS、Agent-Rules、Environment、Progress 及产品规格引用一致。不得以文档审查为由操作 NAS。
2. **恢复前只读预检**：用户明确恢复后，读取 NAS 的 Hermes 镜像/digest、API `file,skills,vision`、插件 1 hook、Skills 审核、App/Core/两端 health、Private/Knowledge/Capture/Promote 边界及记忆目录状态，与最新 Environment 快照比对；只读核验不等于真实 Run 验收。
3. **小范围合成浏览器验收（另行授权）**：使用无敏感虚构偏好，在 SecondBrain Web App 验证登录、Session/Run/SSE、首轮记忆保存、跨 Session 自然召回、更正后旧值失效及无关话题不误注入；记录端到端证据并定向清理测试资产。实际模型须另行确认 provider、每次调用费用上限与测试内容；若可用本地确定性 Mock 则先进行零外发链路核验，不把 Mock 当作真实模型效果。
4. **有限真实体验（另行授权）**：前项通过后由用户决定允许发送的数据范围、模型与费用上限，亲自做少量浏览器 Chat/Memory 体验，报告质量、延迟、错误与最终验收状态。**未经用户确认不接触真实私人资料。**
5. **后续业务排期**：再依据原 V1 MUST 与 Companion MVP 的缺口决定 Journal/Task、微信输入、Promote、Projects/Brief/Activity、多端同步等优先级；API Terminal 的单次审批真实链路仍需单独评估与启用授权，绝不因审批 UI 存在而自动开启。
6. **历史资产清理（非当前任务）**：10 份未引用 App build source（约 56.4 MiB）仅为候选；正在被 Compose 引用的 D076 构建源、D078 回滚点不可删除；三个 D077 大归档约 4.91 GiB 尚未内容比对。后续需先精确核验引用/校验和并另行获准才可删。禁止批量 Docker prune。

**当前停止条件：** 只完成文档修订、交叉核对与 PR 审阅，不触发新增代码、生产变更、生产 Run、真实模型、凭据/个人数据访问或 NAS 删除。

## D077 产品体验验收契约（批准的目标；真实效果尚未验收）

下列规则从原独立产品方向归并到 CURRENT，作为 Companion MVP 与 V1 业务收口的可重复验收项，不改变当前已部署/合成测试/用户验收之间的状态区别：

| 能力 | 验收动作与通过条件 |
|---|---|
| 无检索提示的联想 | 用户只自然谈论相关问题，Agent 能使用确有来源的历史偏好/项目/知识，不要求用户明确说“搜索”；数字、日期、版本须回源 |
| 跨会话的个人记忆 | 新 Session 在相关时主动使用之前明示的当前偏好；不相关时不强行提起，模型推断不冒充用户事实 |
| 纠正与失效 | 用户修正或撤销记忆后，后续 Session 不再把旧值当现行，历史修订与原始来源可核验；重复学习不得无限增加条目 |
| 日记与碎碎念 | 明确“记一下/写日记”时按日期保留原文、时间及来源；普通闲聊不误生成 Journal |
| 待办与提醒 | 自然语言创建/查看/修改/完成真实待办，存储状态一致；通知是否实际送达单独验证 |
| 多格式 Capture | Raw 原件不覆盖，Review 可核验并可解释关联；未经明确批准不 Promote，外部文件中的推断不能当用户事实 |
| 自主 Skill 学习 | 重复反馈可产生可复用经验；重要 Skill 修改经审核，不允许通用 file 绕过 |
| 主动建议与规划 | 依据真实目标/项目/时间线提出来源可查的建议，支持关闭/节流，不能假称已经执行 |
| 安全与经济性 | Private 无访问、Knowledge 无直接写入、可恢复、可审计；调用延迟与预算有明确记录，估算不冒充结算 |

**产品路线（目标优先级，不是立即施工授权）：** 先在已部署 D077/D078 基础上完成获准的合成浏览器 Chat/Run/SSE 与跨会话纠错，再经模型/费用/数据范围确认进行有限真实体验；之后补齐自然语言 Journal/Task、微信多格式 Capture、Promote、Projects/Brief/Activity、跨端使用和主动建议。逻辑记忆 L1–L4 的技术细节遵循 `Architecture.md`，不预建四套物理存储；是否引入索引或其他技术只依据效果与成本证据。**当前暂停状态和实际恢复次序仍以上方 NEXT 为准。**

## 2. V1 交付与验收总矩阵（回答“还缺什么”的唯一总清单）

**当前总体状态仍为 NOT DONE。** 下列旧 V1 MUST 保留原有验收事实；新增 Companion 能力在 Section 2.D 单独追踪。批准目标不等于实施/部署。

状态说明：`ACCEPTED` 已有真实用户验收；`PROD-PARTIAL` 生产部分功能可用；`DEV-TESTED` 仅代码/隔离测试；`NOT CONNECTED` 未接入真实数据；`NOT DONE` 尚无完整生产闭环；`UNKNOWN` 未取得足够证据。**此表须逐项覆盖正式规格的 MUST；若以后更改范围，先同步此表，再实施。**

### A. Agent、技能与知识工作流

| V1 项目 | 要求 / 验收要点 | 当前状态 | 仍需完成 |
|---|---|---|---|
| Hermes Agent / Chat | SecondBrain 自有 Chat 使用 Hermes 会话、Skills、工具及 Agent 能力，业务数据不绑 Agent 内存 | NAS-DEPLOYED：Hermes v0.22.2；App/Core 经 BFF 使用 Sessions/Run/SSE；本次 4 个合成 Run 均通过 | 真实模型行为与用户浏览器验收仍待完成；完整 V1 业务模块仍待接入 |
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

### D. 新批准的 Personal Intelligence / Companion MVP（D077；按能力分项跟踪，整体未验收）

| 新增核心能力 | 当前证据/状态 | 最小成功验收 |
|---|---|---|
| 无提示主动关联 | NOT VERIFIED：旧 Knowledge Retrieval V0 已 ACCEPTED，但仅证明可用搜索/读取；不能证明自动联想 | 不说“搜索知识库”，自然对话能正确使用相关长期记忆；精确事实自动回源 |
| Personal Memory Core（Phase 1-A） | NAS-DEPLOYED；独立 `0700` 根目录、追加式 JSONL 来源/修订记录、纠正与失效过滤；真实路径权限核验通过；本次合成记录已清理 | PR #4 已合并；NAS image `secondbrain-app:d077-b6e30f3`；真实数据与用户验收仍待完成 |
| 自主个人记忆学习（Phase 1-B） | NAS 合成闭环通过：Core 自动保存来源关联、跨 Session 召回、用户纠正和纠正后召回；Hermes v0.22.2 实际模型请求经 Stub 观测到注入上下文。Stub 不评价真实模型的自然学习/回答质量；没有付费模型或真实数据出站 | PR #6 已合并；本次运行证据见 Progress-Log；真实模型质量、用户浏览器体验及长时间使用仍待验收 |
| 分层记忆、时间/冲突管理 | TARGET DESIGN：逻辑 L1–L4 已批准为路线，物理存储和 Provider/Adapter 未冻结 | 关键偏好、当前项目、关键经历和完整证据按需关联，能识别过期/推断/冲突 |
| 碎碎念与 Journal 自然语言记录 | 业务 D064 APPROVED，生产 Journal 写入 NOT DONE | 明确“记一下”即可新增/按日追加原话；普通闲聊不意外写日记 |
| 自然语言待办/日程 | 旧 Web App Calendar 为 PARTIAL；完整 Task 写入/提醒链路 NOT VERIFIED | 能创建、查看、修改、完成真实待办；提醒送达独立验证 |
| 文件收录→理解→记忆关联 | Capture 有 PROD-PARTIAL，OCR/STT、Review→Promote 缺口仍在 | 保留原件、正确提炼候选/关联，不擅自提升第三方断言为用户事实 |
| 主动建议与规划 | NOT DONE：现有 Home/Projects/Activity 聚合仍不完整 | 根据真实目标/事件给出可解释、可关闭/节流的建议，不擅自执行 |
| 自主 Skills 学习 | NOT VERIFIED：原有 Skill 产出及审核流程不等于自动学习闭环已验收 | 重复反馈产生可复用经验；核心/高风险 Skills 仍走隔离与审批 |

**D077 / D078 部署状态（2026-10-17）：** D077 Core 的既有 Stub 合成证据保留；本次未写记忆或创建生产 Session/Run，记忆目录仍为 `1026:100 / 0700` 且 0 文件。PR #18 已合并至 main（`84d1cbaf…80895e5`）。已在 NAS 从固定 Hermes v0.22.2 官方 digest `sha256:a11574…c1bf05` 构建并部署一文件 fail-closed overlay：`secondbrain-hermes:v0.22.2-failclosed-84d1cbaf`，Image ID `sha256:b99b1762…5357e9a`；镜像标签记录源码 Commit `d923a5eb…1040a8` 与补丁 SHA `b5381848…55b0`。Hermes API health 200、Dashboard 9119 可达；启动早期 API 尚未监听，持续观察后恢复健康，未再次重启或回滚（RestartCount 0）。Plugin Doctor 注册 D078 guard 的 1 个 hook。API toolset `file,skills,vision`（不含 Terminal），Skills 写入审核 true、审批 manual。隔离无模型运行拒绝敏感 Session 路径、允许合成业务文件和 Skills 只读调用、dispatcher 异常 fail-closed；无模型调用、无 Session 写入。Private 无挂载、Knowledge 主目录 RO（既有 Capture 专用 Inbox RW 例外不变）、Promote false，D077 Memory 目录 0 文件且元数据未变。实际生产 Run/真实用户体验仍未验收。

**工作准则：** Hermes v0.22.2 patched overlay 为当前运行镜像；Core JSONL 是个人记忆权威存储，外部 Hermes Memory Provider 未启用。API Terminal 必须保持关闭。已部署 fail-closed 补丁并通过本地隔离容器的运行断言；生产验证只覆盖健康、插件注册/配置与无模型文件/Skills/异常 Hook 调用，不代表真实模型或真实个人数据体验验收。

## 3. NOW / BLOCKED / DEFERRED、依赖和阻断

| 顺序 | 当前要解决的业务问题 | 完成判定 | 当前制约 |
|---|---|---|---|
| **Phase 1-A（已部署）** | **可纠正、可撤销、可溯源的 Personal Memory Core** | 独立 Core state 子目录、追加式 JSONL、来源与修订历史；NAS 合成验证通过，测试记录已清理 | 用户浏览器验收与后续真实使用仍待完成 |
| **D078（NAS Stage 1 已部署，未完成用户验收）** | **保留 Hermes 原生 Agent 能力，同时以审批/路径守卫控制高风险操作** | Hermes v0.22.2 fail-closed overlay 已部署；API toolset `file,skills,vision`、Terminal 关闭；Skills 写入审核 true、manual approval；Plugin Doctor 注册 1 hook。隔离无模型 Run 验证敏感路径拒绝、正常业务文件/Skills 只读调用和 dispatcher 异常阻断。API 健康 200、Dashboard 可达。 | NAS 未执行生产 Run；真实模型行为与浏览器用户验收仍待完成。Private 未挂载、Knowledge 主树只读且既有 Capture inbox RW 挂载不变、Promote OFF。 |
| **Phase 1-B（已部署；合成运行验证）** | **受控提炼与 Chat 召回集成** | PR #6 已合并至 main；Core Linux 回归 154 passed、2 subtests passed（Run 38857429530）；Hermes v0.22.2 + Core + 确定性本地 Stub 四步闭环通过 | 真实模型的学习与回答质量、真实会话及用户验收仍待完成 |
| P0 | 独立 Web App 首阶段：Home、内置 Chat、Review、同源 Core/BFF 和单次 App 登录 | 当前 NAS App `secondbrain-app:d078-1d92242` healthy，Image ID `sha256:3cfeeb01…d41487`；Hermes v0.22.2 与 D077 JSONL 状态保留；App/Core 与 Hermes health 可用 | 真实模型和浏览器记忆体验未验收；生产真实 Run/SSE 未执行；设置页、Composer、手机 Review、真实 PDF OCR 仍有既有缺口，Promote 关闭、Knowledge RO |
| P1 | Universal Capture Web 入口 + 多类型 | D076-A.1 + Unified Capture 已部署：合成中文图片/200 DPI 扫描 PDF OCR 的隔离真实验证通过；可读 PDF Fast Path、Raw/Review 哈希验证通过；Promote 和 STT 保持关闭 | 用户复验真实扫描 PDF 质量及 Composer 页面交互；AI 图像描述、Hermes STT 后端和微信端到端仍未完成。DSM GUI 项目缓存独立跟踪、不阻塞业务开发 |
| P1 | Web App 真实业务模块 | 所有正式 MUST 页面接真实数据或符合真实空态，不能 DEMO 代替；跨端可用 | Projects、Brief、Activity 等尚未接入 |
| P2 | V1 端到端回归与安全收口 | Capture→Approval→Knowledge→Retrieval；权限拒绝、回滚、同步与设备体验均有证据 | 以上依赖完成后集中执行 |

**当前 NEXT（Issue #14 / D078）：** 用户审核 D078 Stage 1 部署证据并在浏览器执行合成体验；Terminal 保持关闭，真实个人数据或真实模型使用须按另行授权/费用边界进行。当前 NAS 为 Stage 1，Core JSONL 保持权威来源。部署和只读历史资产审计见 Environment-Baseline.md / Progress-Log.md。

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
| 最高产品目标、核心体验、两种学习/知识闭环、返工路线及 NEXT-0 | `Decision-Log.md` D077 / `Architecture.md`、决策 D077 |
| V1 业务范围与 MUST/SHOULD/DEFERRED 契约 | `SecondBrain-Web-App-V1-Business-Spec.md`、`Universal-Capture-Business-Spec.md` |
| 稳定架构、模块关系、数据流与信任边界 | `Architecture.md` |
| 正式决定、理由及替代关系 | `Decision-Log.md` |
| 最近已核验的 NAS 运行快照、权限、端口与恢复入口 | `Environment-Baseline.md` |
| 历史实施、测试、部署、用户验收与失败复盘 | `Progress-Log.md` |
| SecondBrain 特有执行与安全规则 | `Agent-Rules.md` |
