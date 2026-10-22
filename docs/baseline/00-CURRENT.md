---
created: 2026-09-30
updated: 2026-10-22
status: current
source: GitHub SecondBrain Monorepo
---
# SecondBrain — 当前交付基线（V1 + Personal Intelligence）

> 本文件只维护最新完成定义、原 V1 完整 MUST 矩阵、新批准的智能伙伴核心能力状态、NOW/BLOCKED/DEFERRED 与文档导航。**2026-10-16 D077 已确定新产品最高目标：自然联想、持续个人学习、主动规划；详见 `Decision-Log.md` D077 / `Architecture.md`。** 稳定架构见 `Architecture.md`；正式取舍见 `Decision-Log.md`；运行环境见 `Environment-Baseline.md`；历史证据见 `Progress-Log.md`。

## 2026-10-22 P0/P1 回归与 Companion/响应式复核（Issue #96，PMO #6333339018）

- **固定基线与改动：** 从指定 main `4e51fd23d830db3b263271e7a61acda8433cd074` 创建隔离分支。只修改 Web Task 创建列表核对和回归测试，并新增生产只读安全审计计划；不改 Core。Task 成功回执后若当前已完成/日期筛选隐藏新建的 open Task，会清除筛选并读回；若 Core 已确认创建但 GET 失败，会分别呈现创建成功、列表读取错误和刷新指引。失败的 POST 仍保留同一请求幂等键语义。
- **P0/P1 回归 Gate：** `P0_P1_REGRESSION_GATE=PASS_WITH_LIMITS`。纯合成 Web 定向回归 6 files / 102 tests passed，包含 Capture→Inbox→Review 保存失败保留原件、重试和精确 Review；Journal 用户显式追加原话与 GET 失败状态；Task 创建/过滤器隐藏和成功后读回失败区分；Review 选择；Planning 跨会话隔离。没有在本轮重复已通过的 Core 全量测试。
- **Companion Gate：** `COMPANION_REGRESSION_GATE=PASS_WITH_LIMITS`。Companion 面板的合成回执、同键模糊失败重试、过期 revision 冲突由定向测试覆盖；Planning 的不同 Chat Session 恢复隔离由同批测试覆盖。没有真实 Hermes、模型、个人 Session、知识库内容或生产会话验证。
- **响应式 Gate：** `MOBILE_RESPONSIVE_GATE=PASS_WITH_LIMITS`（源码/CSS/DOM 测试）；`MOBILE_BROWSER=NOT_RUN`。当前环境没有可安全切换视口的独立浏览器测试会话，未安装浏览器。现有 CSS 在 760px 下将 Review 切为纵向单栏、Task 创建表单切为单列；DOM 回归覆盖移动 Review 内部滚动与避免整页误滚。未作设备截图或真实手机验收。
- **验证：** Task/Capture/Journal/Companion/Planning/Review 定向 Web 6 files / 102 tests PASS；`npm run typecheck` PASS；`npm run build` PASS（保留已有 Canvas 大 chunk 提示）；`git diff --check` PASS。仅在本候选变更范围重跑，不重复基于未变源码的 Core 测试。
- **生产只读审计方案：** 新增 [Production-Readonly-Security-Audit-Plan.md](Production-Readonly-Security-Audit-Plan.md)，仅计划/授权清单，规定主机、容器、UID:GID、挂载、POSIX/ACL、Secrets 名称/存在性/模式等元数据字段；禁止业务正文、Private、凭据值、递归遍历、写入和提权绕过，列明停止与无写入回退边界。Hermes 角色隔离单独设计为本地 synthetic/offline 假 Provider 测试。`PRODUCTION_READONLY_AUDIT_PLAN=READY_PLAN_ONLY`；生产审计和 Hermes 测试均 `NOT_RUN`，等待各自明确授权。
- **分层与交付：** 源码/API/真实浏览器/真实数据/生产/用户接受分层报告。未访问生产/NAS/真实数据，未改 UID/GID、ACL、mount、Secrets、Compose，未运行真实 Hermes/模型、Writer/Promote，未部署、未合并、未触发 CI。当前 PR 与最终 SHA 以本节收尾时的 GitHub/Issue #96 回填为准。

## 历史：2026-10-22 V1 P0/P1 连续任务（Issue #96，PMO #6332771271）

- **源码基线与候选：** 从指定 GitHub `main` 固定 HEAD `3efef1939011fd755842602ef85b79d516dd7e48` 建立隔离分支 `codex/v1-p0-p1-closeout-20261022`。本候选只做 Web 用户入口、合成验收与基线同步；无 Core 改动。
- **Capture→Inbox→Review 正向 Gate：** `CAPTURE_REVIEW_POSITIVE_GATE=PASS_WITH_LIMITS`。Edge 在 Core Uvicorn + Vite 同源 localhost 中登录，提交合成 Capture，确认 Raw 保存后在 Inbox 读回原文并打开对应 Review；Review 显示待审核原文及来源元数据。Review 当前只有暂缓动作，Promote 为关闭态；最终用户批准写入知识库及知识回读未通过，状态 `PROMOTE_BLOCKED_BY_DESIGN`，不得将其宣传为已完成批准/知识写入闭环。
- **P0/P1 用户入口：** 独立 Task 创建与 Today 首页入口已修复。用户点击“新建待办”进入 Today 表单，提交后校验 Core 创建回执及 GET 列表读回；同请求结果不确定时保留幂等键，修改内容换新键。`P0_P1_ENTRY_GATE=PASS_WITH_LIMITS`：Edge 合成 Task 创建/读回及 Journal 专用“追加原话”通过；提醒未实现。手工 Daily Brief 的 `approved_import` 仍返回 501；手动准备入口现在明确说明导入暂不支持，没有虚构功能。
- **定向缺陷与回归：** 修复 Task 创建入口/回执校验，避免刷新列表错误掩盖已成功创建；首页 Today CTA 改为真实 Task 创建导航，并说明日历未接入；Daily Brief 手动入口说明 `approved_import` 尚不支持。新增 Task 成功读回、模糊失败同幂等键重试、首页导航及 Brief 不支持态测试。Journal 既有用户显式追加路径仅用合成原文验证，没有改动。
- **测试：** Task/App 定向 Web 2 files / 54 passed；Daily Brief 定向 1 file / 16 passed；Brief 改动后再次 Web 全量 38 files / 422 passed；`npm run typecheck`、`npm run build`、`git diff --check` PASS。Core 定向 Task/Capture/Inbox+Review：44 passed、4 subtests；Web BFF/Auth/Origin：32 passed。Build 存在既有 Notes/Canvas 大 chunk 提示。未重跑未变化的 Core 全量套件。
- **HTTP / 浏览器证据：** 本地 Core 未认证 `/api/tasks` 返回 401 且 `Cache-Control: private, no-store`。Edge 桌面视口 1770px，当前 Journal 页面 DOM 无横向溢出；Task/Review 业务交互在同源合成栈完成。无真实模型、Hermes、外部渠道或真实业务数据。移动视口未验证（`BLOCKED_ENV`）。
- **汇总 Gate：** `CAPTURE_REVIEW_POSITIVE_GATE=PASS_WITH_LIMITS`；`P0_P1_ENTRY_GATE=PASS_WITH_LIMITS`；`V1_MUST_GATE=PASS_WITH_LIMITS`；`COMPANION_GATE=NOT_RUN`（本轮未复验 Companion）；`REAL_BROWSER_GATE=PASS_WITH_LIMITS`（仅 Edge 桌面合成）；`PRODUCTION_SECURITY_GATE=BLOCKED_ENV`。代码、Core localhost HTTP、Edge localhost synthetic、真实模型、生产及用户接受分层汇报；生产/真实数据/真实用户验收均未执行。
- **安全与交付：** 临时合成 roots、合成账户及 `SB_PROMOTE_ENABLED=false`；无生产/NAS/Compose/权限/凭据操作，无真实 Vault/Private/Session，未调用付费模型/外部渠道，未触发 CI。仓库 pull_request 工作流的 paths 仅匹配其自身 workflow 文件，本 PR 不匹配。代码、矩阵及 Progress Log 已集中提交 Draft PR [#189](https://github.com/zxwan829/SecondBrain/pull/189)；最终固定 HEAD 以 PR head 和 Issue #96 最终回填为准。不合并、不部署。

## 历史：2026-10-22 阶段一收口与阶段二 P2-1/2/3 集中合并准备（Issue #96/#97）

- **GitHub 应用源码基线：** 当前 main `df9971bc1aeecc83ed6bd3c10aed2e1dd1eb8a0a`，已包含阶段一 #170/#171。main 不是 NAS 运行版本；本轮未核验/改变生产。
- **阶段一六部分状态盘点：**

  | 部分 | 源码/实现状态 | 合成证据与限制 |
  |---|---|---|
  | 1–2 | 当前 #96/#97 阶段账本及此前 CURRENT 未找到独立编号的交付/Gate 记录；不从页面存在推断已完成。原 V1 MUST 仍按下方完整矩阵逐项追踪。 | 独立阶段 Gate 未找到可引用证据；不标 PASS。 |
  | 3 Inbox→Review→Knowledge 差距审计 | 源码交叉审查没有确认新 P0/P1；没有新增 PR。 | `STAGE1_PART3_SYNTHETIC_GATE=PASS_WITH_LIMITS`；Core+Vite 合成 HTTP 覆盖 Capture、Inbox、审批执行和 Knowledge 来源状态；不含成功 Promote、生产 Writer 或真实用户数据。[证据](https://github.com/zxwan829/SecondBrain/issues/96#issuecomment-6317106891) |
  | 4 Knowledge 查询与复用 | Core #165 / Web #166 已合并，分别 merge `b825466c2bc8068e5b014adb807a31601c0cdbba` / `b6cd1ffb9423b1941ea2be5cff63e846b07758f8`。有界只读召回、SHA/provenance 重验、SSE/history“检索参考”展示与刷新回读。 | `PASS_WITH_LIMITS`；只证明检索参考元数据，不证明模型真正使用知识回答。最终 Core HEAD 全量未重跑。[合并记录](https://github.com/zxwan829/SecondBrain/issues/96#issuecomment-6318641390) |
  | 5 Journal / Projects / Daily Brief | Core #167 / Web #168 已合并，分别 merge `9455a108b747a317fd37c03c3949b3b2f93761d6` / `a32bf3907878f2f4f2eac5621a5e58ed7e25c`。支持 Task/Project/Journal 受权来源、版本检查、用户手工 Brief 保存/回读与来源回跳。 | `STAGE1_PART5_AB_SYNTHETIC_GATE=PASS_WITH_LIMITS`；Core/Vite localhost HTTP 与 Web 合成测试通过；Brief 仍不自动生成，`approved_import` 为 501。[Gate](https://github.com/zxwan829/SecondBrain/issues/96#issuecomment-6319368596) |
  | 6 V1 综合验收与安全一致性 | Core #171 / Web #170 已合并；PR #170 内含 Review-root-relative path 修复与 Inbox→Review 版本绑定 UI 测试。 | `STAGE1_PART6_AB_SYNTHETIC_GATE=PASS_WITH_LIMITS`；Core+Vite HTTP、Core 定向 28 passed/4 subtests、Web 定向 10 passed、typecheck/build/diff-check 通过。[Gate](https://github.com/zxwan829/SecondBrain/issues/96#issuecomment-6323445544)、[独立复审](https://github.com/zxwan829/SecondBrain/issues/96#issuecomment-6323490860)。真实浏览器未启动。 |

- **V1 MUST / Companion MVP 未完成项：** V1 与 D077 Companion MVP 整体仍 `NOT DONE`。#130 D086 Chat→Inbox 已 `MERGED`（merge `1954f88d1546c3c802c82a97a708aff7c32461f7`）；不等于 Journal/Knowledge 已获人工批准写入。#164 Today Task 创建仍为 Draft/Open，不是已合入功能。#106 Restricted Writer 仍 Draft；生产 OS UID/GID、ACL、mount、peer 隔离与安全准入 `BLOCKED`。#151 合成 Raw admission 仍有同 UID namespace/commit 时间窗风险，生产信任边界 `BLOCKED`。真实浏览器 `BROWSER_BLOCKED_ENV/NOT RUN`；真实 Hermes 低信任上下文与模型 grounding、真实业务数据及用户体验均 `NOT RUN`。Private 继续排除，Writer/Promote 生产保持 OFF；没有部署、真实数据或模型调用。
- **阶段二 P2-1/P2-2/P2-3 集中合并准备：** 输入固定为 Core #173 `535d8f934f7e922ada7e5542dfd84bb391f4a2c0`、Web #174 `e868c35d2196a13663969be2d32c03a7813ccb1a`、Core #177 `ce38826fd469eef11f2894f04bb4fe918797503e`、Core #175 `5c22ee664ca9573b036f30f34669d237ecebef43`（叠加 #173）、Web #176 `368f10c8e5ebd0bfcf5bfc376e747017b657a5e1`（叠加 #174）。#173/#174/#175/#176/#177 均仍 OPEN/Draft。集中候选按 #173→#174→#177→#175→#176 构建；#175/#177 的 `personal_memory.py` 重叠保留两侧 bounded stable read 与 CAS/idempotency。当前候选尚待独立复审和 PMO 决定后续合并授权。`MODEL_CONTEXT_ADMISSION=BLOCKED`；真实浏览器、模型、生产及用户验收均 NOT RUN。
- 最近的生产快照仍以 `Environment-Baseline.md` 为准；本轮未核验或操作 NAS/生产、未读写真实 Vault/Private、未触发 CI/Actions、未调用收费或真实模型、未开启 Writer/Promote。

## 2026-10-22 前一阶段裁定（已被上方收口状态替代；Issue #76/#96/#97）

- **GitHub 当前源码权威基线：** `main a32bf3907878f2f4f2eac5621a5e58ed6e7be25c`，是阶段一第 5 部分两条功能 PR 合并后的提交；这不是 NAS 正在运行的镜像版本。最近一次已证据化的生产运行状态仍以 `Environment-Baseline.md` 为准，本次未核验/变更生产。
- **阶段一第 4 部分（可信 Knowledge 检索参考）已合并：** Core [PR #165](https://github.com/zxwan829/SecondBrain/pull/165) merge `b825466c2bc8068e5b014adb807a31601c0cdbba`；Web [PR #166](https://github.com/zxwan829/SecondBrain/pull/166) merge `b6cd1ffb9423b1941ea2be5cff63e846b07758f8`。[#96 合成证据](https://github.com/zxwan829/SecondBrain/issues/96#issuecomment-6318462056)、[#97 Core 修复证据](https://github.com/zxwan829/SecondBrain/issues/97#issuecomment-6318466092)，评审结论 `PASS_WITH_LIMITS`。交付内容为 Core 受控检索、SHA/provenance 再验证、SSE/history 参考元数据与 Web“检索参考”展示/本地刷新回读；**不证明模型使用 Knowledge 形成回答**。知识正文未注入 Hermes system-level instructions 或原始 input；低信任模型上下文角色验证、跨设备 run 索引与真实模型 grounding 均尚未完成。Core 最终 HEAD 定向 32 passed；此前全量 469 项属于前一 HEAD，最终 HEAD 全量 `NOT RUN`（明确接受限制）。
- **阶段一第 5 部分（Journal / Projects / Daily Brief 手工业务闭环）已合并：** Core [PR #167](https://github.com/zxwan829/SecondBrain/pull/167) merge `9455a108b747a317fd37c03c3949b3b2f93761d6`；Web [PR #168](https://github.com/zxwan829/SecondBrain/pull/168) merge `a32bf3907878f2f4f2eac5621a5e58ed6e7be25c`。Core 提供 Task 的权威 `source_ref`、Task/Project/Journal 来源权限及版本校验、手工 Brief 写入/精确回读/失败恢复与 no-store；Web 完成来源选择/回跳、Projects 分页、Journal 日期与条目定位、保存回执与刷新故障区分。A 报 Core+Vite 本地合成 HTTP 主流程及定向 4 PASS、Web 定向 81/full 380 PASS；B 报 Core 全量 470 PASS + 28 subtests。[#96 A/B Gate 证据](https://github.com/zxwan829/SecondBrain/issues/96#issuecomment-6319368596) 为 `PASS_WITH_LIMITS`，真实浏览器点击受环境停止门 `BLOCKED_ENV/NOT RUN`。Brief 仅用户**明确触发的手工编辑与保存**，`approved_import` 仍 501；**无 AI 自动撰写、后台定时或真实数据验收**。
- **治理与未交付范围：** 原 V1 MUST / D077 Companion MVP 整体仍 `NOT DONE`；D086 Chat→Inbox→Review 批准写入路径、真正 Knowledge Writer 的独立 OS UID/ACL/mount/peer 安全准入、真实微信/飞书接入、真实用户来源与跨端浏览器验收不因上述合并自动完成。#106 Writer 与 #101 渠道等独立候选不在此次合并内；另有 #164 Task 创建 Web Draft，必须独立审查，不得把它当作已合入。Private 维持排除，Knowledge Writer/Promote 生产保持 OFF。没有新 NAS 部署、真实模型调用、生产数据读写或额外 CI。
- **阶段一第 6 部分｜唯一 NEXT：** **先进行安全边界与综合验收准备**：以现行 `main` 和现有契约列出 V1 MUST/Companion MVP 未满足项、可在合成环境完成的端到端正反例、真实浏览器/跨设备阻断与需要单独授权的生产数据/OS Writer/Promote/模型验收门槛；优先独立审阅尚未合并的 D086/Task 等业务关键切片，避免虚构生产能力。A/B 可在各自源码范围内提交隔离验证方案或 Draft PR，但**不得**未经用户新授权自行合并、部署、读取真实 Vault/私人 Session、修改 NAS/Compose/UID/GID/ACL/mount/Secrets、触发付费模型/外部渠道或开启 Writer/Promote。重大新业务/安全取舍须回 Decision-Log 审批；小问题在已授权的本地合成范围内自修。阶段六的真实操作另行授权。

## 2026-10-20 阶段裁定与 NEXT（历史快照，已被 2026-10-22 裁定替代；Issue #76/#96/#97）

- **最新应用源码主线：** `87671644356e01d58ec2780d0c45bd11f4c3edfe`。之后 PR #131（main merge `18fac18f89ce3275d9d693bd89f57cdb83083a96`）仅合并治理文档，不改应用源码。Daily Brief 来源校验 #123、Core 测试路径可移植性 #124、人工内容持久化 #125 均已合并；D089 Journal source-options Core 路由 PR #128 亦已合并（固定 HEAD `203f586a24acd8132620b180e9d1a76a3751a72b`，merge `87671644356e01d58ec2780d0c45bd11f4c3edfe`）。B 报告 Core 全量 420 tests + 28 subtests 与正式 localhost HTTP 验证通过；A 对固定 HEAD 的独立验收记录了真实 `create_app()` + Uvicorn 正式路由定向测试 1 passed，未报告 P0/P1。源码合并与本地合成证据不代表部署、真实 Journal/Vault 访问或用户业务验收。#125 保存的是用户明确提交的人工撰写内容，并在读取时重新验证 Task/Project/Journal 来源；不代表 AI 自动生成、定时调度或生产数据闭环。
- **Projects / Activity / Daily Brief 基础接线：** #107/#108/#111/#114/#116/#119/#120 已合并。当前 Projects 的显式 registry 与状态仅有合成/受限来源证据，尚未连接真实业务项目并完成用户验收；Brief Core 来源验证与人工文本保存已合并，`approved_import` 仍返回 501；用户明确触发的 AI 编写属于批准的产品方向但尚未实现，后台自动生成/调度尚未获批。
- **Daily Brief UI #126：** Draft。固定 HEAD 已通过 source/hash、幂等、POST→GET、冲突与错误响应的隔离 HTTP 验证；Edge 启动 SIGABRT、Chromium 启动 SIGTRAP，真实点击和三视口浏览器验收 **BLOCKED_ENV / NOT RUN**，不得重复消耗主线时间做同环境诊断。
- **A 线 Web #127/#129：** Draft；独立源码审查通过，定向及全量 Web 测试、typecheck/build 报告通过；真实浏览器验收仍受上述环境阻断。
- **A 线 D086 Chat→Inbox #130：** Draft、Web-only；明确 Journal 意图将原文提交统一 Inbox，不直接写 Journal、不创建 Hermes Run。PR 报告 Web 283 tests、typecheck/build 及合成 Core HTTP 回归通过；真实浏览器未运行且尚未合并，main 当前路径未改变。
- **B 线 Core #128 / D089：** 已合并至 main（固定 HEAD `203f586a24acd8132620b180e9d1a76a3751a72b`，merge `87671644356e01d58ec2780d0c45bd11f4c3edfe`）。真实 Core 路由 `GET /api/daily-brief/source-options/journal` 已注册；B 报告 420 Core tests + 28 subtests 和本地正式 HTTP 验证通过，A 对最终固定 HEAD 留有独立验收记录。尚未部署或对真实 Journal/Vault 做业务验收。
- **其他未完成切片：** #106 Restricted Writer 仅为合成候选，OS 身份/ACL/mount/peer 隔离未验证；#101 仅为合成可信渠道适配器，未连接微信/飞书。均保持 Draft，不视为生产能力。
- **总体交付：** 原 V1 MUST 和 D077 Companion MVP 均 **NOT DONE**。源码合并、隔离合成测试、NAS 部署、真实业务数据、生产安全准入和用户验收分层记录。最新环境事实仍仅由 `Environment-Baseline.md` 的 2026-10-19 快照代表，本轮未重新核验生产。
- **10 月 22 日目标风险：** “形成基本 V1 业务闭环，可接受小型修补”目前 **AT RISK**。核心存储切片已进入 main，但 Web 真实点击、真实数据/用户业务验收及正式 Knowledge Promote 闭环仍缺证据；不能把源码合并等同目标达成。
- **唯一 NEXT：** A 继续 #130 及不依赖崩溃浏览器环境的 Web 切片；Daily Brief UI 后续按已合并 D089 Core 合同推进，真实浏览器验收仍受环境阻断。B 在 #97 授权内继续与 #128 不重叠的 Core 合成任务（如 #106 Writer 候选、#101 合成渠道适配器）；不重复实现 D089。各切片分别提交 readiness，再由 PMO 裁定集成。不得部署、读取/写入真实 Vault、启用 Promote、调用付费模型或接入真实渠道，除非另行明确授权。

## 2026-10-20 主线源码进展与分层门禁（历史快照；被本文件顶部后续裁定更新）

- **本阶段最新 main 源码：** 合并安全门禁 PR [#105](https://github.com/zxwan829/SecondBrain/pull/105) `d42e3ce7fb652e77d2b1526dd9031bcbb64468e4`、Web Projects/Activity PR [#107](https://github.com/zxwan829/SecondBrain/pull/107) `525d05870fe31592fdbd6553d485381a5b17e713`、Daily Brief/Agent Health PR [#108](https://github.com/zxwan829/SecondBrain/pull/108) `054b989e3cea1a5b1422dfc5ad53a3436caa6c02`、Home/Calendar PR [#111](https://github.com/zxwan829/SecondBrain/pull/111) `1720e2649dc1b8c96acb44f372b055988625e32e`。#108 堆叠 #107、#111 堆叠 #108，逐项更新 base 并核验剩余文件后合并；此前 #98/#102/#99 亦已合入（参见 #76）。
- **安全门禁：SOURCE MERGED / CODE-LEVEL FAIL-CLOSED（非生产安全准入）。** Core 生产 `create_app()` 对 `SB_PROMOTE_ENABLED=true` 的 `inline` 与同 UID `subprocess` 均拒绝启动；成功 Promote 仅在 tests 内显式组装合成路由。A Codex 报告定向 59 passed/19 subtests + Web BFF 25 passed、语法及 diff-check PASS；A ChatGPT 审查源码增量，未独立重跑。旧 Draft #100/#103 的等效安全变更已通过 #105 合并，旧 Draft 不再单独重复合入；**独立 OS UID/ACL/mount/peer 身份隔离仍未实现或实测，生产 Promote 不可启用**。
- **V1 Web 页面源码：LOCAL_CANDIDATE / MERGED，不等于可用业务功能。** Projects、Activity、Daily Brief、Agent Health 与 Calendar 已有只读页面及禁读正文/会话、可信空态/拒绝、不被动跨模块请求的前端合成用例；A Codex 报告 #107 39、#108 43、#111 45 定向测试通过，typecheck/build/diff-check PASS，构建大 chunk 警告未解，依赖审计 2 low + 2 moderate 尚未处置。**对应 Core 只读接口已由集成 PR #114 合入 main**；隔离合成 Core HTTP 与真实 Edge 视口测试通过，但生产/用户业务验收 NOT RUN。Brief 不生成内容；没有后端时页面只能显示 BACKEND_NOT_IMPLEMENTED 或显式开发 fixture。
- **Core 接口合成集成 #114 已合入：** 固定 HEAD `5d622ccd4d40ed86954579bbed91ce081d3ca260`，merge `d7ca99504f8f34c60b40b1350a6bfed2471d5f26`，等效整合 #109（Projects/Activity）、#110（Brief/Agent Health）、#112（Home/Calendar）；重复 `tasks.py` 2MiB 读取预算/`list_for_projection()` **只保留一份**。原 #109/#110/#112 以 SUPERSEDED 关闭，未独立 merge。独立代码/证据审查 PASS，Codex 本地 Core 组合 51 + Auth/Promote 36 = 87 pytest PASS、Web 48 Vitest PASS，typecheck/build/diff-check PASS；GitHub 无可见自动 CI 检查，不宣称 CI PASS。真实 loopback Core HTTP + Edge 1440×1000、820×1180、390×667 三视口共 18 页访问、认证 401/Origin 403、模块精准请求隔离和无横向溢出有合成证据。Projects `not_configured`、Daily Brief `not_configured` = **NOT BUSINESS CLOSED**；Activity `partial`、Agent Health `not_configured`、Calendar `ok`（2 条合成元数据）、Home `ok` 仅代表合成行为。平板 Home P2 已由 #116 源码修复（本地三视口 PASS）；大 chunk 与 npm audit 2 low/2 moderate 未解决。真实数据、生产部署、用户业务验收 NOT RUN。
- **此前本地 HTTP 合成证据保留：** #96 中真实 Edge + 临时 Core HTTP 的 Proposal History 200 → 显式确认 → Inbox POST 202 → exact GET 200 通过，Chat Run/SSE 是 synthetic stub；不等于可信 Hermes 或生产业务验收。
- **未合并/未授权：** B3 真正受限 Writer、OS UID/ACL/mount/peer credentials，Draft #101 真实外部渠道可信接入，以及 NAS/Compose 部署、真实 Vault/Private、付费模型与生产 Promote。#100/#103 仍 Draft，不因 #105 合并而可直接开启写入。生产现状不变。
- **历史 NEXT（已由文件顶部 2026-10-20 新阶段 NEXT 取代）：** Projects 与 Daily Brief 的可信源设计及跨端收口。OS Writer 安全运行、生产部署与真实用户验收仍需单独授权。**已合并源码 ≠ 已部署 ≠ 业务已可用 ≠ 生产安全准入。**

## 1. V1 完成定义与当前状态

**原 V1 业务交付门槛（保留、不缩水）：** 用户能在受支持入口完成原始内容采集、生成 Review、查看并明确批准/暂缓、由 Core 安全写入 Knowledge、再检索和使用知识；Web App V1 MUST 页面使用可信真实数据，具备基本跨设备可用性、Private 隔离和恢复能力。代码或单项页面验收不能替代完整闭环。

**新的 Companion MVP 门槛（D077，已批准、尚未整体实现/验收）：** 日常 Chat 无检索提示地关联长期个人记忆与可信知识；获准对话低风险学习、跨 Session 召回与纠正；精确事实回源；自然语言 Journal、简单 Task、Capture 与主动建议。原 V1 MUST 保持不变。D080 两次 GLM-4.5-Air Run 中，首轮自动学习写入通过，跨 Session 自然召回失败；D082 的情境保留修复已进入最新 main，但生产重新验证仍未完成，详见 Issue #28/#30。

**V1 总体状态：NOT DONE；M1 于 2026-10-18 有限验收结项，M2 P1 App-only 部署于 2026-10-19 完成。** 用户已接受 [M1 总控 #66](https://github.com/zxwan829/SecondBrain/issues/66) 的 **LIMITED ACCEPTED / WITH EXPLICIT EXCLUSIONS**，Issue #66 已 CLOSED。PR #89 与 PR #88 已合入该固定 main；按 [M2 部署授权 #90](https://github.com/zxwan829/SecondBrain/issues/90)，固定 main `443991061ea446686b54bfb9e8b2d980183f1338` 的 App 候选已部署：Image ID `sha256:e55b0e9c65433a208df0f66a68ec2f91e2341b163108e5d09030ac4a7b343f47`，App-only HEALTH PASS；Promote 保持 OFF、Knowledge RO、Private 未挂载，Hermes/Guard 未变。生产业务验收 NOT RUN，用户体验验收尚未开展；仅 App 健康与匿名只读 Smoke 通过。M1 的生产同键重放 NOT RUN、完整 Network 审计 UNKNOWN、旧全量 Inbox BLOCKED、D086 共享词库写入 BLOCKED、C2c-2 OUT OF M1；D084 历史根因 UNKNOWN。M1 有限验收和本次运行健康检查均不代表 V1 正式 Knowledge Promote、真实模型记忆、微信输入或完整 Web App MUST 验收通过。M2 源码/部署事实不意味着 B3 或 Promote 获准。

**Hermes 运行状态更新（2026-10-19，Issue #76）：** 已确认前 Hermes `172.18.0.2` 静态地址与 App 占用地址冲突，按批准范围仅移除 Hermes 的 Compose `ipv4_address` 并完成 Hermes-only 重建；Hermes 使用原镜像并恢复运行，动态 IP 与 App 不同，API health GET 200、Dashboard 返回登录重定向。App、Vaultwarden、其他容器、Promote OFF、Knowledge RO、Private 未挂载及挂载边界保持。完整运行证据见 `Environment-Baseline.md` 最新快照和 `Progress-Log.md`；此次未进行业务验收，此后下一步已由文件顶部 2026-10-20 NEXT 更新。

### 当前工作分层状态（不能互相替代）

| 工作 | 代码审查 | 本地/合成验证 | 已合并位置 | NAS 部署 | 真实模型/浏览器验收 |
|---|---|---|---|---|---|
| D084 后续：Chat 内 Journal/Task 会话活动留痕（Issue #44） | PR #49、#61 已完成独立复审并合并 | PR #49 定向验证及 PR #61 的 8 项 Chat 合成回归、typecheck/build、diff-check 通过（复用审查证据）；本次 M2 部署未重跑业务验收 | PR #49 与 PR #61 已合入 main | 当前 M2 App 镜像基于 `44399106`；Health、只读路由/静态资源及匿名 API 鉴权 PASS | 业务操作卡与会话恢复本轮 NOT RUN；全量网络审计 UNKNOWN、HTTP 端点并发未测、历史根因 UNKNOWN |
| D082 个人记忆情境保留修复 | PR #32 已审；随 PR #45 合入 main | `test_personal_learning.py` 17 项通过；此前 D080 真实召回失败不可由源码/Mock 抵消 | PR #45 merge `c8a2b348f9e5ae4e17663b9d8e0403c5da227efa` 的 App 基线保留该修复 | 现行生产 App 为 M2 P1 镜像（包含此修复）；真实模型召回仍未验收 | 生产真实召回复验未完成；浏览器验收未完成 |
| D081 Journal、D082 Chat Journal、D083 Task | PR #31/#34/#36 各自代码审查通过 | 统一本地合成验证：Core 80 项、相关前端 46 项通过；typecheck/build 通过 | PR #45 已合入 main（merge `c8a2b348f9e5ae4e17663b9d8e0403c5da227efa`） | PR #49 是历史 App 部署；M2 P1 当前 App 包含这些功能，Journal/Task 业务验收未完成 | 登录态合成验收未完成；未调用真实模型 |
| PR #37 普通 Chat 文件写入单次审批 | ChatGPT 二次代码审查通过；原 PR 仍 open | 集成分支 Guard 22 项、Core 审批/BFF、前端审批与 Capture 验证通过；见本轮统一验证证据 | PR #45 已合入 main，包含 PR #37 两项已审提交；原 PR #37 仍独立 open，勿重复合并 | D084 基础 App 包含已合入代码；生产 Hermes API Run 审批链路未完成端到端核验 | 用户验收与真实模型验收未完成 |

本轮以实时 GitHub main `a8019ab1bc453c3c42e6ecf82ccfacdd97bde583` 为基线；与 `dev/parallel-v1-next-20261017` 在 `d7a48fe` 分叉后，main 独有 6 个提交（含 D082 记忆修复及后续治理文档），并行分支独有 3 个功能切片提交。集成分支保留 main 历史并合入 3 个切片；`personal_learning.py` 与其回归测试相对 main 未改动。唯一源码冲突为 `App.tsx` 的 Journal/Task 与通用 Run 审批解析器导入，已人工合并；CURRENT 文档冲突保留 main 文本并在本轮校准。代码审查、定向测试、分支合入、main 合入、NAS 部署、真实模型运行与用户验收分别记录；任一层通过都不自动代表后一层通过。

## D084：统一功能集成已部署（基础范围的限定合成验收通过）

本轮从 GitHub 实时 main `a8019ab1bc453c3c42e6ecf82ccfacdd97bde583` 建立独立集成分支，合入 Journal / Chat Journal / Task 切片并移植已审 PR #37 文件写入审批提交；保留 D082 个人记忆修复。按[集成与统一测试计划](D084-Integration-and-Validation-Plan.md)完成 Core 80 项、Hermes Guard 22 项、前端相关 46 项本地合成验证，前端 typecheck/build 通过。`Environment-Baseline.md` 未改动：本轮无 NAS 新运行证据。

**PR #49 历史部署与首次登录态验收（2026-10-17；此后已由 PR #61 指定镜像替换）：** PR #49 于 2026-10-17 合入 main（merge `fa2ad4126b5e9acb6983fdae8445a4fb0ebdda79`）。按 Issue #44 评论 #6233322671 的一次授权，仅部署 App：使用 `web-app/Dockerfile.app` 与对应 `web-app` 构建上下文，镜像 `secondbrain-app:pr49-fa2ad412-full` / Image ID `sha256:1c7ed4cb953951eb2ab8691516651d170171305af6172326174e64f4115dd6ca`；120 秒健康门槛通过。隔离无网络 ASGI 检查和生产只读 HTTP smoke 均验证 `/chat 200 text/html`、2 个静态资源 200、匿名 Chat API 401 JSON。Hermes/Guard 容器与镜像未变化。具体运行快照、Compose 哈希、回滚点和未通过的业务验收项见 `Environment-Baseline.md`。**2026-10-17 登录态合成验收与最小源码诊断：** 在生产 App 的空白 Chat Session 通过显式 Journal/Task 路径各写入一条合成记录（标记 `D084-SYNTH-20261017-7KQ4`）；两张操作卡首次显示成功，首次刷新后曾恢复（上述项保留 PASS）。之后 UI 标题显示“会话 1”；返回 UI 标题“会话 3”时活动卡未显示，与刷新结果不一致（会话切换恢复 FAIL / INCONSISTENT）。这些标题不等于 Hermes Session ID；当时未记录 create 响应 ID、sessions 列表 ID、当前选择 ID 或 activities 请求路径/响应 ID，故实际生产根因 **UNKNOWN**，不得按标题推断。
源码核验：前端新建会话从 `POST /api/chat/sessions` 取 `session_id`，用它更新 selected ref/state 和 localStorage；切换时 `selectSession(id)` 清空可见活动，并对 `/api/chat/sessions/{id}/messages`、`/activities` 发请求。异步响应还经过请求序号与当前 selected ID 双重检查，活动再按 `activity.session_id === requestedSessionId` 过滤。Core 将 Hermes 返回的 `id`/ `session_id` 归一化为 `session_id`；活动路由先校验该 Hermes Session 存在，再按同一 ID 汇总 Journal、Task 和投影记录。源码路径在 API 按约定返回稳定 ID 时是 session-scoped 的，尚无证据能解释生产观察中的 ID/数据不一致。
最新 main `18c91f78ec692ad0a522f3b7b3ba12d80bdb115c` 的隔离本地合成验证：临时 Vitest 用不透明 ID `hermes-synth-A/B/C` 检查创建选择、活动 URL ID、切换隔离、返回恢复和 remount/刷新恢复，**1 passed**；Core `pytest tests/test_web_app_bff.py -k session_activity`，**3 passed, 22 deselected**（TestClient 有一条 Starlette/httpx 弃用警告）。这证明正常 ID 契约下的本地路径与 Core session scope 可通过，不证明此前生产实际使用的 ID，也没有复现根因。生产业务既有记录状态继续保留：跨会话恢复 FAIL / INCONSISTENT；幂等重试、审计核验 BLOCKED；合成资产保留，未访问生产接口/私人正文、未写生产数据或调用模型。
最新 main `c958d2c7337f890acad1ef00d04c27fe500e1585` 的定向故障注入发现两个 UI 状态边界：1）localStorage 中的 `secondbrain.chat.session` 不在 Hermes sessions 列表时，初始化会跳过默认选择并显示空会话；2）新建 Session 请求等待期间若用户切换到 B，稍后返回的创建响应会覆盖该更新选择。已在本 PR 分支修复：无效持久 ID 回退到列表中真实 Hermes `session_id` 并更新 localStorage；新建/分支会话异步完成时仅当用户选择意图未变化才切换。另验证 activities 响应 `session_id` 与请求 ID 不匹配时会被过滤；A 请求延迟到用户切换 B 后返回时，不会覆盖 B。该本地缺陷覆盖相应合成状态与竞态，但没有证明它就是先前生产观察的根因；生产 create/list/selected/activities ID 仍未记录，因此生产根因保持 **UNKNOWN**。既有验收状态不变：首次卡片及首次刷新 PASS；会话切换恢复 FAIL / INCONSISTENT；幂等重试、审计核验 BLOCKED；无生产访问/写入/重试、无模型调用、合成资产保留。
**PR #61 合并及部署前只读快照（2026-10-18T01:50:41Z）：** PR #61 已复审并合入 main（merge `b3c8fe08ea04e1f20ccadcf70e393bf80a30672c`），实现本地确认的 stale Session ID 回退和创建/分叉选择竞态保护；此快照时尚未部署。该时点只读核验确认 NAS 仍运行 PR #49 App 镜像 `secondbrain-app:pr49-fa2ad412-full` / `sha256:1c7ed4cb…11dd6ca`（healthy，RestartCount 0）和 Hermes v0.22.2 Guard 镜像 `secondbrain-hermes:v0.22.2-failclosed-84d1cbaf` / `sha256:b99b1762…5357e9a`（running，RestartCount 0）；PR #61 修复在当时尚未进入生产 App。Edge 当前标签清单没有 SecondBrain App 页面；当时没有打开 `/chat`、恢复或查看私人 Session，也没有按所有会话读取 Hermes 列表或宽泛日志。因此 Hermes create/list、selected/localStorage、activities 请求/响应 ID 与状态时间均无法关联到先前异常，生产根因仍 **UNKNOWN**；历史验收保持首次卡片/首次刷新 PASS、会话切换恢复 FAIL / INCONSISTENT、幂等重试与审计 BLOCKED。完整只读快照与证据缺口见 `Environment-Baseline.md`。
**2026-10-18 PR #61 部署结果：** 部署指定候选 `secondbrain-app:d084-pr61-4a58393-full`（Image ID `sha256:e63ab1611b2a30ffd9dd2a9cb901066fa6b2da2e7e85c9c1c9d72dbabac0e4ab`），未重建。候选基于 `4a58393`；当前 main 已前进至 `3080506` 并包含之后合入的 D085-C2b 变更，该候选不包含这些后续变更。App 在 120 秒内 healthy；Hermes/Guard 身份不变。浏览器登录后自动恢复了既有 Session，不能安全地用于空白合成验收，因此没有创建 Session、写 Journal/Task、重试或读取会话内容；相关验收保持 BLOCKED，生产根因 UNKNOWN。没有回滚，因为健康、路由及鉴权检查均通过且未观察到 App 异常。详细快照见 `Environment-Baseline.md`。

**2026-10-18 前一 M1 App-only 部署（当时现行；后由 473948dd 替换）：** 按用户授权，将固定源码 `74d698dc97dd9df423664141b80fd8003fbca534` 的已验证候选 `secondbrain-app:m1-74d698dc-notes`（Image ID `sha256:4adcf9cfe3f6257c733efa911455ca02653783ba763f9e2f512f4d3582694ce1`）切换为现行 App。App 在约 31 秒内 healthy，RestartCount 0；`/health`、`/chat/blank`、入口 JS/CSS、Notes chunk 均 200，匿名 Chat API 为 401 JSON。仅改动 Compose 的 App image 和两项 Notes 配置；Compose SHA 从 `9c0932c04d6984cd2e491738d51eb6235d7182ccfca8146678fc18cdabe6097d` 变为 `5c12fda28f3e5e9cd001d238515bd6599adaf5e502686f5d30fcbcb4a8c72f80`。Notes Drafts 仅在现有 Core-state RW 挂载内创建空目录，owner/mode `1026:100 / 0700`；授权根为空对象，Promote 仍关闭。Hermes/Guard 容器、镜像、启动时间及重启计数不变，挂载边界未扩大。部署前 Compose 精确快照及 SHA/位置见 Environment-Baseline。未执行业务验收、生产 Session/Journal/Task 写入或模型调用；D084 生产根因和原验收未决项保持 UNKNOWN / 未验收。

**2026-10-18 PR #72 合并后 M1 App-only 部署（现已由 M2 P1 镜像替换）：** 固定源码 `473948dd2e9b3d448b71eeba56a1474454883353` 按 `web-app/Dockerfile.app`、`VITE_ENABLE_NOTES=true` 构建并部署；新候选及运行镜像 `secondbrain-app:m1-473948dd-notes` / `sha256:70f8277f4d29c2bf8e50d3f7d135f034f04a90b421928d9836515d79a7143b3d`。部署前 App 是 `m1-74d698dc-notes` / `sha256:4adcf9cfe3f6257c733efa911455ca02653783ba763f9e2f512f4d3582694ce1`；仅修改 Compose 中 App 镜像引用。Compose SHA 从 `5c12fda28f3e5e9cd001d238515bd6599adaf5e502686f5d30fcbcb4a8c72f80` 变为 `5d15c9ac51d4bd9f3cd682ef60e4e97d77b5d7e212ae73d0bf5e3126aad0da8d`。App 在 39 秒内 healthy，RestartCount 0，运行用户 `1026:100`；`/health`、`/chat/blank`、`/inbox/source`、入口 JS/CSS/Notes chunk 与匿名 Chat API 分别按预期返回 200/HTML、200 与 401/JSON。Hermes 容器、镜像、启动时间和重启计数不变；Core-state/Notes、Review、Capture Raw、Knowledge 的现有挂载边界及 Promote=false 未变。精确回滚快照已保存并校验；无回滚。部署当时未做生产业务验收、未调用模型或读取业务正文；后续 B1 单来源闭环结果及剩余风险见下方当前状态与 Issue #66。详细部署证据见 `Environment-Baseline.md`。

**2026-10-18 安全空白入口实现（PR #65，已合并并随 M1 镜像部署；生产业务验收未完成）：** 基于 main `d781541785bbc20c64c3f4f676a1b9d1bd431e06` 新增 `/chat/blank`。空白模式不读取/覆盖普通 `secondbrain.chat.session`，不读取 `secondbrain.chat.activeRun` / `activeSession`，初始不请求 Hermes Session 列表、消息、活动或 Run；仅在用户点击创建后使用创建响应 ID，并在独立的 tab `sessionStorage` allowlist 内刷新/切换。普通 Chat 原有恢复行为保留。Mock 定向测试 51 项、typecheck、build、diff-check 通过。该实现仅限制前端请求，不提供服务端账户或 Session 隔离；PR #65 合并时未访问生产数据或创建 Session，且未调用模型；其代码已随 M1 镜像部署。D084 上一 M1 镜像的受控合成结果按上文记录保留；本次 473948dd 新镜像上的 B1 单来源生产闭环有限 PASS：5 条 Proposal，Journal 与 Review 各成功执行 1 次，Project 提案拒绝，刷新恢复 PASS。生产同键幂等重放 NOT RUN，完整 Network 审计 UNKNOWN，旧全量 Inbox UI BLOCKED，D086 共享词库后续写入 BLOCKED，C2c-2 OUT OF M1。历史生产根因仍 UNKNOWN。

**历史 NEXT（2026-10-19，已由文件顶部 2026-10-20 NEXT 取代）：** M2 P1 App-only 部署已取得独立 **DEPLOYED / HEALTH PASS** 复审结论，**业务/用户验收仍未运行**。A 主线按 [M2 总控 #76](https://github.com/zxwan829/SecondBrain/issues/76) 制定下一阶段两项只读、零业务写入的验收计划：① 核对 Review、Knowledge、Capture Raw 宿主 `0700` 与容器 bind 根目录 `0777` 的权限视图差异及实际访问边界（原因 UNKNOWN，先只读，不修改 ACL/权限）；② 设计不自动恢复私人 Chat Session、无需读取业务正文的登录态浏览器页面/网络验收，明确哪些测试需要用户单独批准。完成方案和安全门槛后再申请相应执行授权；**不得**因本次部署健康而启用 B3/Promote、Knowledge RW、读取真实 Vault/Private、创建生产记录或调用模型。部署快照见 `Environment-Baseline.md`，历史和本轮证据见 `Progress-Log.md`；M1 LIMITED ACCEPTED ≠ V1 DONE。

**M1 双线总控与集成状态（[Issue #66](https://github.com/zxwan829/SecondBrain/issues/66)）：** C2c-2 已裁定延期至 M2；M1 范围为 D084（含 `/chat/blank`）+ D085-C2a/C2b/C2c-1 + D086。集成准入冻结源码为 `83b60ec38da34ae49294cebf02f403016362a622`；经 A 主线批准的最小 Notes Docker 构建契约修复后，正式部署源码为 `74d698dc97dd9df423664141b80fd8003fbca534`；PR #72 后的 M1 生产源码为 `473948dd2e9b3d448b71eeba56a1474454883353`；2026-10-19 M2 P1 当前生产构建固定于 `443991061ea446686b54bfb9e8b2d980183f1338`。冻结源码本地集成准入：前端定向合成测试 86 项、Core 跨模块定向测试 97 项、typecheck 和 build 通过；project 执行保持 HTTP 501，Promote 默认关闭。**本地源码准入 PASS；M1 `473948dd` 部署 HEALTH PASS 后已被 M2 `44399106` App-only 镜像替换，当前 M2 HEALTH PASS；B1 单来源生产闭环有限 PASS；同键幂等重放 NOT RUN、Network 审计 UNKNOWN、旧 Inbox 与 D086 共享词库写入 BLOCKED、C2c-2 OUT OF M1；M1 用户已接受有限验收并结项（#66 CLOSED），M2 本次只授权 App 部署，业务验收仍 NOT RUN。** A 线负责准入、冻结、兼容审查、部署/回滚统筹与验收；B 线负责独立切片及汇合报告，不得自行部署 NAS。本轮不改变 D084 历史根因 UNKNOWN 与未验收项。本项不新增 NEXT，以本文件顶部 2026-10-20 唯一 NEXT 为准。

### D085-C2a 统一 Inbox 与人工逐项审批演示（已合并并随 M1 部署；生产业务验收未完成）

PR #54 已在 ChatGPT 二次独立复审后合入 main（merge `4a0a9a73b1765cd1236bba5974eb24dd69ca8232`），状态为 **MERGED / DEPLOYED WITH M1 / NOT PERSISTENT APPROVAL / BUSINESS ACCEPTANCE NOT RUN**。合入版本保留 Capture Inbox 预览、下载、`partial_success` 重试、错误/状态、刷新和 Organizer 入口，并在同页加入 Notes Drafts 与确定性 Mock 建议；演示候选与已知词条分开，状态词不作为标签，页面模拟同意不持久化或执行。PR #57 已合入 `main`（merge `1c73b0f3449725815443c22ba503104df0cb8eff`），加入人工类型/移除标签修正保护和明确模拟审批边界，并随 M1 镜像部署；这些页面模拟批准不持久化、不执行目标操作。来源安全审批持久化由下方 C2b 单独实现。页面模拟批准不构成真实 Vault、付费模型或其他生产操作授权；当前下一步以本文件顶部 2026-10-20 唯一 NEXT 为准。

### D086 标签与类型中心（Issue #55；已合并并随 M1 部署，真实 Vault 与业务验收未完成）

PR #58 经 ChatGPT 两轮独立复审、消除 Core 名称唯一性和锁文件安全阻断后，已同步 main 并正式合入 main（merge `e1eafb5613793fa23f5be98afc6a4ca62959da97`）。新增 Core 私有类型/标签/同义词词库与独立 `/vocabulary` 管理页，初始化五种类型、标签为空；显式确认、revision/If-Match、跨进程锁、原子写入、审计与停用保留历史引用。规范标签与 alias 双向 NFC+casefold 唯一性；catalog 与审计共用 2 MB 上限，写满时 507 fail-closed，不截断或自动归档，后续须另行设计审计扩容。Codex Core 定向 11 项、早前前端 3 项及 typecheck/build 通过，未由 ChatGPT 重跑。**MERGED / DEPLOYED WITH M1 / NOT REAL-VAULT-VALIDATED**。D086 共享词库属于全局状态，后续生产词库写入保持 **BLOCKED**；保留既有合成标签及 revision，不再新增或回滚。本切片未扫描真实 Vault、未改写 Markdown，不代表完整自动分类或元数据回写功能。本次部署不代表真实 Vault 盘点或笔记内容处理已获授权；当前下一步以本文件顶部 2026-10-20 唯一 NEXT 为准。

### D085-C1 Notes 主应用导航接入（PR #50 已合并并随 M1 部署；功能验收未完成）

PR #50 已合入 main（merge `12af0aa3417a76f0b787cb82c40e00d577b9e20f`），实现 Notes 路由与导航；相关实现随 M1 镜像部署。Notes 通过 `/notes` 路由接入桌面/移动侧栏；`VITE_ENABLE_NOTES` 默认关闭，显式开启仍要求 Core `notes.read` 预检成功，Notes 读写继续由 Core 权限门禁控制。NotesPage 懒加载；跨页面导航保留未保存保护。Markdown 正文为权威来源，图形 JSON 附件仅由 SecondBrain 编辑，不扩张 Obsidian 原生兼容承诺。本轮前端定向回归 63 项、typecheck 与 build 通过；部署后仅确认 Notes JS chunk 可访问，未做 Notes 登录态/业务验收；未访问真实笔记或启动 D085-C2。当前下一步以本文件顶部 2026-10-20 唯一 NEXT 为准。

### 新批准的产品规则：D086 对话收录与标签类型管理

`Decision-Log.md` D086 与 [`业务规范.md`](业务规范.md) 已确认：普通 Chat 保持自然对话，Hermes 可有节制地询问是否收录；用户明确收录或同意后，Core 先将原文存入统一 Inbox，日记意图也须经 Inbox 和用户确认后再写 Journal。Hermes 可在授权范围回顾并主动建议，主动/被动调用分开设每日及每月估算金额额度；类型/标签集中管理代码已由 PR #58 合入 main 并随 M1 镜像部署；尚未对真实 Vault 盘点或应用元数据。类型最多 10 种，既有有效标签可自动应用。**D086 的 inbox-first Chat 路径尚未进入 main 或验收**；PR [#130](https://github.com/zxwan829/SecondBrain/pull/130) 是 Web-only Draft 候选，将明确 Journal 意图改送统一 Inbox，不直接创建 Journal。当前 main 现有 Chat 显式 Journal 直写路径未改变，待 PR 审查、合并及后续业务验收。Issue #55 不授权读取真实 Vault、改写历史文件、启动付费模型或生产变更。当前下一步以本文件顶部 2026-10-20 唯一 NEXT 为准。

### 并行开发状态：D085-C2b 来源绑定建议与审批留痕

PR #59 已合入 main `3080506b053d3876d292d9199049fd12e3247b88`，实现来源绑定 Mock 建议、审批/拒绝审计、幂等重试和版本冲突保护。B1 单来源生产闭环中，5 条来源绑定 Proposal 刷新后恢复；Project 提案拒绝 PASS。来源审阅边界之外的旧全量 Inbox 仍 BLOCKED；本结论不代表真实 Vault 验收。当前下一步以本文件顶部 2026-10-20 唯一 NEXT 为准。

### D085-C2c-1 审批后 Journal / Review 受控执行（PR #63 已合并并随 M1 App 部署；B1 有限生产验收 PASS）

PR #63 已合并至 main，Merge Commit `d781541785bbc20c64c3f4f676a1b9d1bd431e06`；其代码随 M1 App 镜像部署。B1 有限生产验收中，Journal 与 Review 各经人工审批、精确预览和明确确认成功执行一次；刷新后状态恢复 PASS。生产同键幂等重放 **NOT RUN**，不得将单次执行推断为端点重放通过。实现将审批留痕与目标执行分开，执行前重新预览目标正文，核验来源/词库版本并明确确认；Journal 复用专用 JournalStore 幂等追加，Review 复用 CaptureService 的 Raw→Review 流程及可恢复执行键，均不调用 Promote 或新增 Knowledge 写入路径。PR #63 的本地合成故障恢复覆盖目标落盘后进程退出重启；并发覆盖同 proposal 两个请求；Core/Capture 定向测试 38 项、Inbox 前端 7 项、typecheck/build/diff-check 通过，Review 首次响应与 duplicate 响应明确区分。项目关联仅为元数据候选，仍标记 **NOT IMPLEMENTED** 且不可执行；C2c-2 已延期至 M2。完整浏览器 Network 审计 UNKNOWN；旧全量 Inbox UI 仍 BLOCKED。真实 Vault、NAS 生产操作及付费模型调用仍须各自授权。当前下一步以本文件顶部 2026-10-20 唯一 NEXT 为准。

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

**产品路线（目标优先级，不是立即施工授权）：** 在已部署 D077/D078 基础上，后续按独立授权完成合成浏览器 Chat/Run/SSE 与跨会话纠错，再经模型/费用/数据范围确认进行有限真实体验；之后补齐自然语言 Journal/Task、微信多格式 Capture、Promote、Projects/Brief/Activity、跨端使用和主动建议。逻辑记忆 L1–L4 的技术细节遵循 `Architecture.md`，不预建四套物理存储；是否引入索引或其他技术只依据效果与成本证据。**实际阶段次序与批准范围以上方唯一 NEXT 为准；当前等待 M2 部署独立复审。**

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
| Human Approval / Promote | 用户确认、版本哈希校验、Core 受控写入、暂缓、审计、恢复 | **分层状态：** B1 单来源 Proposal 持久审批及 Journal/Review 执行有限生产 PASS；**正式 Knowledge Promote 仍关闭**（`SB_PROMOTE_ENABLED=false`、Knowledge RO），其审批→写入→回源全链路未通过 | 优先在 M2 规划受控 Review→Knowledge Promote 最小权限闭环；与 B1 的 Journal/Review 执行权限严格分离 |
| Knowledge 生命周期 | 正式资料不覆盖、可追溯；保留 Raw/Review，支持检索 | PROD-PARTIAL | 完成 Promote→Knowledge→Dashboard 搜索/查看真实闭环 |
| Journal | 用户原文留存；支持专用受控新增/按日期追加，不允许普通 Agent 覆写 | D081/D082 已经 PR #45 合入并随 M1 App 部署；D084 旧 M1 镜像上的受控 Journal 合成 PASS，新 M1 镜像上的 B1 审批→Journal 专用执行 1 次有限 PASS | D086 新规范要求先收录 Inbox、确认后写 Journal，尚未完整实现/验收；不得把旧显式直写等同新顺序；Web App V1 快捷录入原属 SHOULD |

### B. Web App / Personal OS（按正式 V1 Business Spec 逐项枚举）

状态只表示本轮验收证据，不替代下方历史生产事实。按 P0、P1、P2 排列；`SYNTHETIC_PASS` 仅表示合成环境结果。

| 优先级 | 正式 V1 MUST | 本轮状态 | 仍需交付 / 验收 |
|---|---|---|---|
| P0 | Global App Shell、导航、登录、路由 | `SYNTHETIC_PASS`：Edge 本地登录、路由、会话与 no-store 源码检查 | 生产认证、安全配置、真实用户与跨设备验收 `BLOCKED_ENV` |
| P0 | Home / Dynamic Home | `SYNTHETIC_PASS`：桌面 Home 展示区分 REAL/DEMO/空态 | Home 简报/动态卡仍显示“即将开放”；桌面全视觉/大屏外视口已看，窄屏未验；真实聚合未验收 |
| P0 | Chat / Agent session | `SYNTHETIC_PASS`：本地合成 Session、Planning、刷新恢复与跨 Session 隔离 | 真实 Agent Run/SSE、模型回答与跨 Session 记忆 `NOT_RUN`；来源支持不等于答案归因 |
| P0 | Capture → Inbox → Review → 用户批准 | `SYNTHETIC_PASS`：Edge 本地合成 Capture→Raw→Inbox 原文读回→Review 待审核正文/来源回读通过；Promote 关闭，最终批准/Knowledge 写入 `PROMOTE_BLOCKED_BY_DESIGN` | 正式 Knowledge 写入/回滚与真实数据 `BLOCKED_ENV`；本轮 Gate `PASS_WITH_LIMITS` |
| P1 | Today、Task、Calendar | `SYNTHETIC_PASS`：Today 首页 CTA 进入真实 Task 表单；合成提交、Core 回执校验及列表 GET 读回通过 | 真实提醒 `NOT_DONE`；Home 不提供日历创建，Schedule 未接入 |
| P1 | Projects | `SYNTHETIC_PASS`：合成 Project 页面、Brief 引用回跳/聚焦 | 获准真实项目 registry、跨设备与用户验收 `NOT_RUN` |
| P1 | Knowledge 查询与来源引用 | `SYNTHETIC_PASS`：无数据时可信空态；Chat 无来源时引用动作禁用 | 本轮未重复搜索功能；真实来源 / Session 权限 / 跨会话用户体验 `NOT_RUN`，答案使用来源归因 `NOT_DONE` |
| P1 | Daily Brief | `SYNTHETIC_PASS`：手工来源选择、确认、保存、回读和 Task/Project/Journal 回跳 | AI 撰写/approved_import/后台调度 `NOT_DONE`；真实来源与用户验收 `NOT_RUN` |
| P1 | Journal | `SYNTHETIC_PASS`：Brief 回跳加载 Journal 日期并高亮已引用条目；本轮 Journal 专用“追加原话”在合成根写入并回读成功 | D086 Chat→Inbox→人工确认路径不等于直接 Chat→Journal；真实资料和用户验收 `NOT_RUN` |
| P1 | Activity、Agent Health | `NOT_RUN`：本轮未单独操作页面 | 真实可信状态/完整活动源和失败语义 `NOT_RUN` |
| P1 | 多端 Responsive / Desktop / iPad / Mobile | `SYNTHETIC_PASS`：Edge 桌面 1770px，Journal DOM 无横向溢出 | iPad/iPhone 视口模拟本轮未验 `BLOCKED_ENV`；Safari/触控验收 `NOT_RUN` |
| P2 | Private exclusion、写入授权、Human Approval、安全恢复 | `BLOCKED_ENV`：本轮未接生产；合成 Gate 验过 session、撤权、CAS/幂等、版本漂移、重复/取消/拒绝、no-store、重启恢复 | Private/生产 OS 身份、UID/GID/ACL/mount/peer、Writer/Promote 与真实恢复须另授权；不得由合成 PASS 推断生产准入 |

**Web App V1 SHOULD，单独跟踪、不自动阻断 MUST DONE：** Quick Capture、Journal quick entry、badges、notifications、session continuation、keyboard shortcuts、contextual actions、Agent 状态动画。具体完成情况需在对应业务施工时核实。

### C. 生产运行与工程验收

| 事项 | 当前状态 | V1 收口要求 |
|---|---|---|
| Hermes Knowledge 直接写风险 | MITIGATED / DEPLOYED：Hermes Knowledge RW 子挂载已移除，仅 `/secondbrain` RO；safe root 限于三个已核验捕获目录。普通文件工具及终端写探针均被拒；Daily/Universal Capture 与 Dashboard Review 回归通过 | 保持该权限边界；跟进重建后的原生 Chat 重连异常；不以 Hermes Knowledge RW 作为回退 |
| Core 写权限与审批认证 | 分层 PASS：App 登录/Origin/Core 授权门禁已部署；B1 单来源审批执行有限生产 PASS；正式 Promote 仍关闭、Knowledge RO、Private 无挂载 | 真正的 Core Promote 权限/拒绝/版本/幂等、回滚、用户审批到正式 Knowledge 全链路须另行授权验证 |
| Private | 已有禁止挂载/访问的设计与生产静态证据 | 生产与 API 验证拒绝，不读取 Private 内容 |
| 多端与数据同步 | PARTIAL | 核实 Web App 桌面/iPad/手机主要动作及 Obsidian Mac↔NAS 文件实际双向传播 |
| 生产部署、恢复、安全收尾 | PARTIAL | 真实运行检查、变更快照和回退，收口开发期 unrestricted sudoers；验收与文档 Git 收口 |

### D. 新批准的 Personal Intelligence / Companion MVP（D077；按能力分项跟踪，整体未验收）

按产品优先级追踪；合成交互可用不等于真实模型 grounding、生产用户价值或自主执行已验收。

| 优先级 | 新增核心能力 | 本轮状态 | 最小成功验收 / 剩余缺口 |
|---|---|---|---|
| P0 | 无提示自然联想与可信知识使用 | `NOT_DONE`：Chat 有显式 Knowledge 来源核对 UI，无来源时禁用；P2-4 metadata Gate 不建立回答归因 | 日常对话可自然使用获准记忆/知识；精确事实回源；`answer_attribution=not_established` |
| P0 | Personal Memory 跨 Session 召回、纠正 | `NOT_RUN`：既有生产/Stub 证据为历史记录，本轮未重跑真实 Hermes 或真实记忆 | 需经授权的本地非模型权限审计与独立模型质量/用户验收；不得读真实 Session |
| P1 | Journal 自然语言/原文收录 | `IMPLEMENTED`：显式 Journal 页面与 D086 Inbox 顺序已合入；本轮只验证 Brief metadata 引用回跳 | 用户意图分类、Inbox→人工确认→专用 Journal 写入和追加恢复需独立正向浏览器 Gate |
| P1 | Task / Calendar 用户流程 | `SYNTHETIC_PASS`：Task 元数据、Home→Today 创建/回读、Calendar 聚合、Brief 回跳、Planning 提交/恢复；提醒未实现 | 提醒送达 `NOT_DONE`；真实来源与用户验收未执行 |
| P1 | Capture→理解→记忆关联 | `SYNTHETIC_PASS`：本轮只完成文本 Capture→Raw→Inbox→Review 正向回读；无 OCR/STT 或记忆关联 | 原件保留、人工确认后的可信记忆关联与生产权限仍未验；Knowledge Promote `PROMOTE_BLOCKED_BY_DESIGN` |
| P1 | 主动建议与安全规划 | `SYNTHETIC_PASS`：Today Companion 手动启用来源、显式计算、反馈仅记录；Planning 逐条批准且合成执行 `effect=none` | 真实个人目标、推荐相关性、模型/真实业务数据与任何外部效果均未验；默认关闭 |
| P2 | Session 历史恢复与来源引用 | `SYNTHETIC_PASS`：规划候选 Session 隔离/刷新恢复，Brief 保存与引用回跳；Core Gate 验来源版本变化拒绝 | Chat 的实际回答引用仍不代表模型使用来源；真实跨设备/Session 未验 |
| P2 | Permission revoke、CAS/idempotency、版本漂移、失败恢复 | `SYNTHETIC_PASS`：Core+Vite localhost Gate 覆盖撤权、来源漂移、并发 CAS、精确重放、冲突、重启回读、no-store | 仅当前固定源码+临时合成树结果；生产 UID/ACL/mount/真实恢复 `BLOCKED_ENV` |
| P3 | 分层记忆、时间/冲突管理 | `IMPLEMENTED`：已批准路线设计，物理存储/Provider/Adapter 仍未冻结 | 识别过期、推断、冲突并提供证据回源；未满足不变量前不得自动学习 |
| P3 | 自主 Skills 学习 | `NOT_DONE`：技能产出和人工审核不等于反馈学习闭环 | 重复反馈形成安全、可复用经验；核心/高风险 Skill 仍需隔离和审批 |

**D077 / D078 部署状态（2026-10-17）：** D077 Core 的既有 Stub 合成证据保留；本次未写记忆或创建生产 Session/Run，记忆目录仍为 `1026:100 / 0700` 且 0 文件。PR #18 已合并至 main（`84d1cbaf…80895e5`）。已在 NAS 从固定 Hermes v0.22.2 官方 digest `sha256:a11574…c1bf05` 构建并部署一文件 fail-closed overlay：`secondbrain-hermes:v0.22.2-failclosed-84d1cbaf`，Image ID `sha256:b99b1762…5357e9a`；镜像标签记录源码 Commit `d923a5eb…1040a8` 与补丁 SHA `b5381848…55b0`。Hermes API health 200、Dashboard 9119 可达；启动早期 API 尚未监听，持续观察后恢复健康，未再次重启或回滚（RestartCount 0）。Plugin Doctor 注册 D078 guard 的 1 个 hook。API toolset `file,skills,vision`（不含 Terminal），Skills 写入审核 true、审批 manual。隔离无模型运行拒绝敏感 Session 路径、允许合成业务文件和 Skills 只读调用、dispatcher 异常 fail-closed；无模型调用、无 Session 写入。Private 无挂载、Knowledge 主目录 RO（既有 Capture 专用 Inbox RW 例外不变）、Promote false，D077 Memory 目录 0 文件且元数据未变。实际生产 Run/真实用户体验仍未验收。

**工作准则：** Hermes v0.22.2 patched overlay 为当前运行镜像；Core JSONL 是个人记忆权威存储，外部 Hermes Memory Provider 未启用。API Terminal 必须保持关闭。已部署 fail-closed 补丁并通过本地隔离容器的运行断言；生产验证只覆盖健康、插件注册/配置与无模型文件/Skills/异常 Hook 调用，不代表真实模型或真实个人数据体验验收。

## 3. NOW / BLOCKED / DEFERRED、依赖和阻断

| 顺序 | 当前要解决的业务问题 | 完成判定 | 当前制约 |
|---|---|---|---|
| **Phase 1-A（已部署）** | **可纠正、可撤销、可溯源的 Personal Memory Core** | 独立 Core state 子目录、追加式 JSONL、来源与修订历史；NAS 合成验证通过，测试记录已清理 | 用户浏览器验收与后续真实使用仍待完成 |
| **D078（NAS Stage 1 已部署，未完成用户验收）** | **保留 Hermes 原生 Agent 能力，同时以审批/路径守卫控制高风险操作** | Hermes v0.22.2 fail-closed overlay 已部署；API toolset `file,skills,vision`、Terminal 关闭；Skills 写入审核 true、manual approval；Plugin Doctor 注册 1 hook。隔离无模型 Run 验证敏感路径拒绝、正常业务文件/Skills 只读调用和 dispatcher 异常阻断。API 健康 200、Dashboard 可达。 | NAS 未执行生产 Run；真实模型行为与浏览器用户验收仍待完成。Private 未挂载、Knowledge 主树只读且既有 Capture inbox RW 挂载不变、Promote OFF。 |
| **Phase 1-B（已部署；合成运行验证）** | **受控提炼与 Chat 召回集成** | PR #6 已合并至 main；Core Linux 回归 154 passed、2 subtests passed（Run 38857429530）；Hermes v0.22.2 + Core + 确定性本地 Stub 四步闭环通过 | 真实模型的学习与回答质量、真实会话及用户验收仍待完成 |
| P0 | 独立 Web App 首阶段：Home、内置 Chat、Review、同源 Core/BFF 和单次 App 登录 | 最近核验生产 App `secondbrain-app:m1-473948dd-notes` / 源码 `473948dd`，healthy；Hermes v0.22.2 Guard 不变；M1 用户有限验收结项，尚非完整 V1 | 真实模型和浏览器记忆体验未验收；生产真实 Run/SSE 未执行；设置页、Composer、手机 Review、真实 PDF OCR 仍有既有缺口，Promote 关闭、Knowledge RO |
| P1 | Universal Capture Web 入口 + 多类型 | D076-A.1 + Unified Capture 已部署：合成中文图片/200 DPI 扫描 PDF OCR 的隔离真实验证通过；可读 PDF Fast Path、Raw/Review 哈希验证通过；Promote 和 STT 保持关闭 | 用户复验真实扫描 PDF 质量及 Composer 页面交互；AI 图像描述、Hermes STT 后端和微信端到端仍未完成。DSM GUI 项目缓存独立跟踪、不阻塞业务开发 |
| P1 | Web App 真实业务模块 | 所有正式 MUST 页面接获准真实数据或明确真实空态，不能以 DEMO 代替 | Projects、Daily Brief UI、Activity 等源码已部分接线；真实数据、浏览器和用户验收仍缺，#126 受环境阻断 |
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
| 微信/飞书渠道、Daily Brief 范围与 Journal 来源选项合同 | `Decision-Log.md` D087-D089、`Architecture.md`、本文 |
| 最近已核验的 NAS 运行快照、权限、端口与恢复入口 | `Environment-Baseline.md` |
| D084 多切片集成顺序、统一合成验收矩阵及真实验证前置门槛 | [集成与统一测试计划](D084-Integration-and-Validation-Plan.md) |
| 历史实施、测试、部署、用户验收与失败复盘 | `Progress-Log.md` |
| SecondBrain 特有执行与安全规则 | `Agent-Rules.md` |
