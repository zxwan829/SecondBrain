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

**新的 Companion MVP 门槛（D077，已批准、尚未整体实现/验收）：** 日常 Chat 无检索提示地关联长期个人记忆与可信知识；获准对话低风险学习、跨 Session 召回与纠正；精确事实回源；自然语言 Journal、简单 Task、Capture 与主动建议。原 V1 MUST 保持不变。D080 两次 GLM-4.5-Air Run 中，首轮自动学习写入通过，跨 Session 自然召回失败；D082 的情境保留修复已进入最新 main，但生产重新验证仍未完成，详见 Issue #28/#30。

**总体状态：NOT DONE。** D084 PR #49 App-only 镜像于 2026-10-17 按 Issue #44 评论 #6233322671 部署。120 秒健康门槛、生产 `/chat` HTML/静态资源和匿名 Chat API 鉴权均通过；Hermes/Guard 未变。浏览器合成 Journal/Task 会话活动卡、刷新恢复、跨会话隔离及幂等重试尚未完成验收，因此不视为功能/用户验收完成。Edge 自动化在扩展界面处被阻断；没有提交业务表单、写入 Journal/Task 合成记录或调用模型。运行证据见 `Environment-Baseline.md` 与 Issue #44 评论。真实模型记忆质量仍未验收。

### 当前工作分层状态（不能互相替代）

| 工作 | 代码审查 | 本地/合成验证 | 已合并位置 | NAS 部署 | 真实模型/浏览器验收 |
|---|---|---|---|---|---|
| D084 后续：Chat 内 Journal/Task 会话活动留痕（Issue #44） | PR #49 已完成 ChatGPT 独立复审并合并 | Core Journal/Task/BFF 35 项、前端 Chat/Capture/timeline 42 项通过；本次镜像内 typecheck/build 通过。覆盖跨零点幂等、活动恢复、旧记录日期兼容与 Hermes 秒/毫秒时间戳排序 | **已合入 main**，Merge `fa2ad4126b5e9acb6983fdae8445a4fb0ebdda79` | **App-only 已部署**；health、`/chat` HTML、assets 及匿名 API 401 通过 | 未完成生产登录态业务合成和浏览器验收；未调用真实模型；Chat 扩展界面阻断自动化，待用户恢复浏览器后继续 |
| D082 个人记忆情境保留修复 | PR #32 已审；随 PR #45 合入 main | `test_personal_learning.py` 17 项通过；此前 D080 真实召回失败不可由源码/Mock 抵消 | PR #45 merge `c8a2b348f9e5ae4e17663b9d8e0403c5da227efa` 的 App 基线保留该修复 | 旧 App 镜像 `d084-c8a2b348` 当前运行；真实召回效果未验证 | 生产真实召回复验未完成；浏览器验收未完成 |
| D081 Journal、D082 Chat Journal、D083 Task | PR #31/#34/#36 各自代码审查通过 | 统一本地合成验证：Core 80 项、相关前端 46 项通过；typecheck/build 通过 | PR #45 已合入 main（merge `c8a2b348f9e5ae4e17663b9d8e0403c5da227efa`） | PR #49 App 镜像已部署；Journal/Task 根仍为 `1026:100 / 0700`，没有扩大挂载/权限 | 登录态合成写入与浏览器验收待完成；未调用真实模型 |
| PR #37 普通 Chat 文件写入单次审批 | ChatGPT 二次代码审查通过；原 PR 仍 open | 集成分支 Guard 22 项、Core 审批/BFF、前端审批与 Capture 验证通过；见本轮统一验证证据 | PR #45 已合入 main，包含 PR #37 两项已审提交；原 PR #37 仍独立 open，勿重复合并 | D084 基础 App 包含已合入代码；生产 Hermes API Run 审批链路未完成端到端核验 | 用户验收与真实模型验收未完成 |

本轮以实时 GitHub main `a8019ab1bc453c3c42e6ecf82ccfacdd97bde583` 为基线；与 `dev/parallel-v1-next-20261017` 在 `d7a48fe` 分叉后，main 独有 6 个提交（含 D082 记忆修复及后续治理文档），并行分支独有 3 个功能切片提交。集成分支保留 main 历史并合入 3 个切片；`personal_learning.py` 与其回归测试相对 main 未改动。唯一源码冲突为 `App.tsx` 的 Journal/Task 与通用 Run 审批解析器导入，已人工合并；CURRENT 文档冲突保留 main 文本并在本轮校准。代码审查、定向测试、分支合入、main 合入、NAS 部署、真实模型运行与用户验收分别记录；任一层通过都不自动代表后一层通过。

## D084：统一功能集成已部署（基础范围的限定合成验收通过）

本轮从 GitHub 实时 main `a8019ab1bc453c3c42e6ecf82ccfacdd97bde583` 建立独立集成分支，合入 Journal / Chat Journal / Task 切片并移植已审 PR #37 文件写入审批提交；保留 D082 个人记忆修复。按[集成与统一测试计划](D084-Integration-and-Validation-Plan.md)完成 Core 80 项、Hermes Guard 22 项、前端相关 46 项本地合成验证，前端 typecheck/build 通过。`Environment-Baseline.md` 未改动：本轮无 NAS 新运行证据。

**最新部署结果 / 下一步：** PR #49 已于 2026-10-17 合入 main（merge `fa2ad4126b5e9acb6983fdae8445a4fb0ebdda79`）。按 Issue #44 评论 #6233322671 的一次授权，仅部署 App：使用 `web-app/Dockerfile.app` 与对应 `web-app` 构建上下文，镜像 `secondbrain-app:pr49-fa2ad412-full` / Image ID `sha256:1c7ed4cb953951eb2ab8691516651d170171305af6172326174e64f4115dd6ca`；120 秒健康门槛通过。隔离无网络 ASGI 检查和生产只读 HTTP smoke 均验证 `/chat 200 text/html`、2 个静态资源 200、匿名 Chat API 401 JSON。Hermes/Guard 容器与镜像未变化。具体运行快照、Compose 哈希、回滚点和未通过的业务验收项见 `Environment-Baseline.md`。**2026-10-17 登录态合成验收与最小源码诊断：** 在生产 App 的空白 Chat Session 通过显式 Journal/Task 路径各写入一条合成记录（标记 `D084-SYNTH-20261017-7KQ4`）；两张操作卡首次显示成功，首次刷新后曾恢复（上述项保留 PASS）。之后 UI 标题显示“会话 1”；返回 UI 标题“会话 3”时活动卡未显示，与刷新结果不一致（会话切换恢复 FAIL / INCONSISTENT）。这些标题不等于 Hermes Session ID；当时未记录 create 响应 ID、sessions 列表 ID、当前选择 ID 或 activities 请求路径/响应 ID，故实际生产根因 **UNKNOWN**，不得按标题推断。
源码核验：前端新建会话从 `POST /api/chat/sessions` 取 `session_id`，用它更新 selected ref/state 和 localStorage；切换时 `selectSession(id)` 清空可见活动，并对 `/api/chat/sessions/{id}/messages`、`/activities` 发请求。异步响应还经过请求序号与当前 selected ID 双重检查，活动再按 `activity.session_id === requestedSessionId` 过滤。Core 将 Hermes 返回的 `id`/ `session_id` 归一化为 `session_id`；活动路由先校验该 Hermes Session 存在，再按同一 ID 汇总 Journal、Task 和投影记录。源码路径在 API 按约定返回稳定 ID 时是 session-scoped 的，尚无证据能解释生产观察中的 ID/数据不一致。
最新 main `18c91f78ec692ad0a522f3b7b3ba12d80bdb115c` 的隔离本地合成验证：临时 Vitest 用不透明 ID `hermes-synth-A/B/C` 检查创建选择、活动 URL ID、切换隔离、返回恢复和 remount/刷新恢复，**1 passed**；Core `pytest tests/test_web_app_bff.py -k session_activity`，**3 passed, 22 deselected**（TestClient 有一条 Starlette/httpx 弃用警告）。这证明正常 ID 契约下的本地路径与 Core session scope 可通过，不证明此前生产实际使用的 ID，也没有复现根因。生产业务既有记录状态继续保留：跨会话恢复 FAIL / INCONSISTENT；幂等重试、审计核验 BLOCKED；合成资产保留，未访问生产接口/私人正文、未写生产数据或调用模型。
最新 main `c958d2c7337f890acad1ef00d04c27fe500e1585` 的定向故障注入发现两个 UI 状态边界：1）localStorage 中的 `secondbrain.chat.session` 不在 Hermes sessions 列表时，初始化会跳过默认选择并显示空会话；2）新建 Session 请求等待期间若用户切换到 B，稍后返回的创建响应会覆盖该更新选择。已在本 PR 分支修复：无效持久 ID 回退到列表中真实 Hermes `session_id` 并更新 localStorage；新建/分支会话异步完成时仅当用户选择意图未变化才切换。另验证 activities 响应 `session_id` 与请求 ID 不匹配时会被过滤；A 请求延迟到用户切换 B 后返回时，不会覆盖 B。该本地缺陷覆盖相应合成状态与竞态，但没有证明它就是先前生产观察的根因；生产 create/list/selected/activities ID 仍未记录，因此生产根因保持 **UNKNOWN**。既有验收状态不变：首次卡片及首次刷新 PASS；会话切换恢复 FAIL / INCONSISTENT；幂等重试、审计核验 BLOCKED；无生产访问/写入/重试、无模型调用、合成资产保留。
**PR #61 已复审并合入 main**（merge `b3c8fe08ea04e1f20ccadcf70e393bf80a30672c`），仅实现本地确认的 stale Session ID 回退和创建/分叉选择竞态保护；**未部署**。2026-10-18T01:50:41Z 限定只读核验确认 NAS 仍运行 App 镜像 `secondbrain-app:pr49-fa2ad412-full` / `sha256:1c7ed4cb…11dd6ca`（healthy，RestartCount 0）和 Hermes v0.22.2 Guard 镜像 `secondbrain-hermes:v0.22.2-failclosed-84d1cbaf` / `sha256:b99b1762…5357e9a`（running，RestartCount 0）；故 PR #61 的两项修复尚未进入生产 App，相关路径在当前版本仍可能存在。Edge 当前标签清单没有 SecondBrain App 页面；没有打开 `/chat`、恢复或查看私人 Session，也没有按所有会话读取 Hermes 列表或宽泛日志。因此 Hermes create/list、selected/localStorage、activities 请求/响应 ID 与状态时间均无法关联到先前异常，生产根因仍 **UNKNOWN**；历史验收保持首次卡片/首次刷新 PASS、会话切换恢复 FAIL / INCONSISTENT、幂等重试与审计 BLOCKED。完整只读快照与证据缺口见 `Environment-Baseline.md`。
**唯一 NEXT：** 等待 ChatGPT 独立复审本次只读结果。若仍需判定生产异常是否由 PR #61 两个状态边界导致，应先取得可安全指向既有合成活动 Session 的精确 opaque ID，或提供无需打开私人 Session 的 metadata-only 读取入口；随后只查该目标的 create/list/selected/localStorage/activities ID、HTTP 状态和时间。不得打开私人 Session、读取正文、查询无关 Session、读取宽泛日志、生产写入/重试、模型调用、部署/重启 NAS 或清理历史数据。

### 并行开发状态：D085-C2a 统一 Inbox 与人工逐项审批演示（已合并、未部署）

PR #54 已在 ChatGPT 二次独立复审后合入 main（merge `4a0a9a73b1765cd1236bba5974eb24dd69ca8232`），状态为 **MERGED / NOT DEPLOYED / NOT PERSISTENT APPROVAL / NOT USER ACCEPTED**。合入版本保留 Capture Inbox 预览、下载、`partial_success` 重试、错误/状态、刷新和 Organizer 入口，并在同页加入 Notes Drafts 与确定性 Mock 建议；演示词表与未知候选分开，状态词不作为标签，页面模拟同意不持久化或执行。后续修正由 PR #57 跟踪（当前待审）：保护手动类型/标签修正并明确模拟审批边界；尚未合入或部署。来源安全审批持久化和 Issue #55 正式词汇库仍需独立设计。本段不改变上方 D084 唯一 NEXT，也不授权真实 Vault、付费模型或 NAS 操作。

### 并行开发状态：D086 标签与类型中心（Issue #55；已合并、未部署）

PR #58 经 ChatGPT 两轮独立复审、消除 Core 名称唯一性和锁文件安全阻断后，已同步 main 并正式合入 main（merge `e1eafb5613793fa23f5be98afc6a4ca62959da97`）。新增 Core 私有类型/标签/同义词词库与独立 `/vocabulary` 管理页，初始化五种类型、标签为空；显式确认、revision/If-Match、跨进程锁、原子写入、审计与停用保留历史引用。规范标签与 alias 双向 NFC+casefold 唯一性；catalog 与审计共用 2 MB 上限，写满时 507 fail-closed，不截断或自动归档，后续须另行设计审计扩容。Codex Core 定向 11 项、早前前端 3 项及 typecheck/build 通过，未由 ChatGPT 重跑。**MERGED / NOT DEPLOYED / NOT REAL-VAULT-VALIDATED / NOT USER ACCEPTED**。本切片未扫描真实 Vault、未改写 Markdown，不代表完整自动分类或元数据回写功能。D084 唯一 NEXT 不变；无 NAS、付费模型或真实笔记操作授权。

### 并行开发状态：D085-C1 Notes 主应用导航接入

PR #50 在原功能分支开发，现已将最新 main `468971b49b1bf63b98930ee0b875c133a314b429` 合入并处理共享 `App.tsx` 冲突。Notes 通过 `/notes` 路由接入桌面/移动侧栏；`VITE_ENABLE_NOTES` 默认关闭，显式开启仍要求 Core `notes.read` 预检成功，Notes 读写继续由 Core 权限门禁控制。NotesPage 懒加载；跨页面导航保留未保存保护。Markdown 正文为权威来源，图形 JSON 附件仅由 SecondBrain 编辑，不扩张 Obsidian 原生兼容承诺。本轮前端定向回归 63 项、typecheck 与 build 通过；PR 仍未合并、未部署、未做用户验收；未访问真实笔记或启动 D085-C2。此并行状态不改变上方 D084 唯一 NEXT。

### 新批准的产品规则：D086 对话收录与标签类型管理

`Decision-Log.md` D086 与 [`业务规范.md`](业务规范.md) 已确认：普通 Chat 保持自然对话，Hermes 可有节制地询问是否收录；用户明确收录或同意后，Core 先将原文存入统一 Inbox，日记意图也须经 Inbox 和用户确认后再写 Journal。Hermes 可在授权范围回顾并主动建议，主动/被动调用分开设每日及每月估算金额额度；标签与类型集中管理，类型最多 10 种，既有有效标签可自动应用。**这些均是批准的目标，尚未按新规则实现、部署或验收**；当前已合入/部署的 Chat 显式 Journal 直写路径仍是既有实现，需后续任务按新规范调整。Issue #55 跟踪标签与类型功能，不授权读取真实 Vault、改写历史文件、启动付费模型或生产变更。本节不改变 D084 唯一 NEXT。

### 未结 Issue 与接续边界（2026-10-17 审计）

- **#28 — D080-B 真实模型验证：** 2/5 Run 已执行，跨 Session 自然召回失败；剩余 Run 未执行，已有授权不可被解释为此次自动重跑许可。统一真实测试时再确认模型、次数、预算和范围。
- **#30 — D082 记忆召回与文件写入副作用：** main 已包含本地验证的记忆提取修复和通过 PR #45 集成的文件写入审批代码，均未生产复验/部署。两项不得混为已解决。
- **#14 — D077/D078 历史安全与运行阶段：** 已按阶段目标 completed 关闭；遗留真实验收在 #28/#30 继续追踪。
- **#27 — D080-B0 模型/预算预检：** 已按阶段目标 completed 关闭；原核价证据可复用，不自动重新查询密钥或发起模型请求。
- **PR #37：** 已完成第二次代码审计，其已审提交通过 PR #45 集成合入 main；原 PR 仍 OPEN，不得再单独重复合入。

## D077 产品体验验收契约（批准的目标；真实效果尚未验收）

下列规则从原独立产品方向归并到 CURRENT，作为 Companion MVP 与 V1 业务收口的可重复验收项，不改变当前已部署/合成测试/用户验收之间的状态区别：

| 能力 | 验收动作与通过条件 |
|---|---|
| 无检索提示的联想 | 用户只自然谈论相关问题，Agent 能使用确有来源的历史偏好/项目/知识，不要求用户明确说“搜索”；数字、日期、版本须回源 |
| 跨会话的个人记忆 | 新 Session 在相关时主动使用之前明示的当前偏好；不相关时不强行提起，模型推断不冒充用户事实 |
| 纠正与失效 | 用户修正或撤销记忆后，后续 Session 不再把旧值当现行，历史修订与原始来源可核验；重复学习不得无限增加条目 |
| 日记与碎碎念 | 明确“记一下/写日记”时先由 Core 保留原文、时间及来源至统一 Inbox；用户确认后才写 Journal；普通闲聊不误生成 Inbox/Journal |
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
| Journal | 用户原文留存；目标支持新增/按日期追加，不允许普通 Agent 随意覆写 | D081 Core/API + D082 显式 Chat 意图在并行开发分支 DEV-TESTED，未合入 main/未部署；生产 `SB_JOURNAL_ROOT` 未配置/核验 | 集成后验证 Core 专用根、授权和日期追加；**业务是目标能力，但 Web App V1 的快捷录入属于 SHOULD，不能擅自冒充核心 MUST** |

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
| Private exclusion / Human Approval | PARTIAL：Private 无挂载、Knowledge 主挂载 RO 已验证；仍需真实业务权限及审批验收 | 运行时写入边界、API 拒绝、审核与失败回滚验收 |

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
| 碎碎念与 Journal 自然语言记录 | D086 已取代 D064 对话直写顺序；现有显式直写代码已合入/部署，但新入口规则 NOT IMPLEMENTED，业务浏览器验收未完成 | 明确“记一下”先经 Core Inbox 保存原话，再经用户确认由专用 Journal API 新增/按日追加；普通闲聊不意外收录或写日记 |
| 自然语言待办/日程 | D083 Task Core/API、Today 页面和 Chat 显式命令在并行开发分支 DEV-TESTED；尚未合入 main 或部署，生产 `SB_TASK_ROOT` 未配置/核验；提醒发送 **NOT IMPLEMENTED** | 集成后验证真实持久数据/权限；提醒通知必须单独实现并验收，不将待办 CRUD 通过等同提醒送达 |
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

**依赖矩阵说明：** 本表描述能力交付依赖，不取代 Section 1 的唯一 NEXT。Issue #14 保留 D078 阶段证据；API Terminal 保持关闭。

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
| 最高产品目标、双闭环原则及当前验收路线 | `Decision-Log.md` D077（批准方向）与本文（当前验收/NEXT） |
| 笔记、对话收录、标签与类型业务规则 | [业务规范](业务规范.md)；正式取舍见 `Decision-Log.md` D086 |
| V1 业务范围与 MUST/SHOULD/DEFERRED 契约 | [Web App V1 业务规格](business-specs/SecondBrain-Web-App-V1-Business-Spec.md)、[Universal Capture 业务规格](business-specs/Universal-Capture-Business-Spec.md) |
| 稳定架构、模块关系、数据流与信任边界 | `Architecture.md` |
| 正式决定、理由及替代关系 | `Decision-Log.md` |
| 最近已核验的 NAS 运行快照、权限、端口与恢复入口 | `Environment-Baseline.md` |
| D084 多切片集成顺序、统一合成验收矩阵及真实验证前置门槛 | [集成与统一测试计划](D084-Integration-and-Validation-Plan.md) |
| 历史实施、测试、部署、用户验收与失败复盘 | `Progress-Log.md` |
| SecondBrain 特有执行与安全规则 | `Agent-Rules.md` |
