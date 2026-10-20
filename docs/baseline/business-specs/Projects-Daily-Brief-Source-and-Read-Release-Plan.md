---
created: 2026-10-20
status: partial-product-approved; source-access-and-release-pending
source: PMO #76 / A #96 / CURRENT / Web App V1 Business Spec / 业务规范
scope: product decision candidate; no authority to read, deploy or write real data
---
# Projects 主档、Daily Brief 形成规则与最小真实来源验收授权（A 决定稿候选）

> **产品裁定已批准（2026-10-20）：Daily Brief V1 先通过用户人工触发或用户明确批准的既有记录导入，形成经来源核验、可回源的 Core 持久简报记录；最终支持每日自动生成个人任务简报，分阶段实施：先人工触发/批准导入和可信持久化，再接可关闭的定时调度。** 具体写入 API/安全方案及真实数据读取、生产部署仍需另行授权。本文的 Projects 物理主档细则、真实来源授权包及发布方案仍是待审候选，不能整体标为业务验收通过。

## 1. 已批准的边界 / 待确认的取舍

**已批准：** Vault 逻辑目录 `30-Projects` 是项目资料区域；Inbox-first、AI 只能建议分类/关联、用户审批及正式 Knowledge/Private 边界不变。Projects 数据不能从目录名、Task 标题、AI 猜测直接推断；Home 只是聚合层。Web V1 MUST 有 Projects、Daily Brief、History、跨端及真实业务数据，现仍 NOT DONE。Core 已合入的 `/api/projects`、`/api/daily-brief` 严格 GET wire 及安全降级不变。

**用户已确认的正式产品决定（2026-10-20）：** Daily Brief V1 **先采用用户人工触发，或经用户明确批准的已有记录导入/保存**，形成 Core 权威持久日期快照；**每日自动生成个人任务简报为最终目标；先完成手动/批准导入和可信持久化，再接可关闭的定时调度**。不允许默认开启定时任务、模型调用或数据写入。此处仅批准形成方式，不代表授权实现生产写入或读取真实内容。参见 `Decision-Log.md` D087。

## 2. Projects 权威主档（建议采纳 v1）

1. 每个项目由用户明确创建/维护唯一稳定 `project_id`，不等于文件夹名或可变展示标题；主档是 `30-Projects` 中用户维护的结构化项目元数据或显式只读索引，具体物理文件名/模式在不读取真实目录前保持 UNKNOWN。
2. 最小字段：`project_id`、`title`、`status`（active/paused/completed/archived/unknown）、`updated_at`、`source_ref={opaque id, sha256/version}`；可选 `next_step`、`recent_activity` 与 `linked_notes`。`unknown` 是明确缺失，不由文件时间/目录推断。
3. 用户手动维护项目标题、状态、下一步及关联意图；AI 可提出编辑/关联建议但无审批不得修改项目主档，也不得替换原文或绕过 Inbox。项目文档/笔记优先**关联**，非强制迁移文件。
4. Task/Notes 关联采用显式 ID + 版本/hash + 具权限的权威元数据 API 回查。逐条核验项目归属/可见范围/漂移。未证实则**隐藏该关联**、标 partial；不得把 JSON 中写有某个 ID 当作 verified；禁止读取/返回原文、隐私路径、会话 ID。
5. Project `real` 仅表示当次返回的明确项目字段和所声称关联已完整核验。索引存在但关联验证缺失 -> partial；配置不存在 -> not_configured；配置有且为空 -> empty；源不可读/不可信 -> unavailable。保留分页、资源上限及显式配置的最小根，不扫描整个 Vault。

## 3. Daily Brief 权威形成与历史（建议采纳 v1）

1. **写路径与读路径分离。** 受控形成过程在单独明确授权后，把简报持久写为 Core 权威日期快照；`GET /api/daily-brief` **永不**临时生成、抓聊天、调用模型或扫描来源。需要版本与原始来源可追溯，不将 Web 拼接内容当已生成简报。
2. 每条记录：`brief_id`、`date`、`timezone=Asia/Shanghai`（本轮默认业务日）、`generated_at`（UTC 存储）、`generation_status`、`categories`、`summary`、`source_refs=[{kind,id,version}]`，及 Core 内部审计/生成渠道元数据。允许服务端时间与业务日期区分；不根据用户设备时区暗改日期。单个日期目前只接受一权威时区格式；如需多时区须单独设计迁移，不能 silent fallback。
3. **D087 来源白名单固定为 `task`、`project`、`journal`**：Journal 仅用于可验证的回顾；不含外部新闻。Notes、Capture、Review、Chat、Agent events 及其他来源不得成为 Brief 的独立内容或 `source_refs`。Projects 页面自己的 `linked_notes` 关系另行核验，不因此把 Note 纳入 Brief。verifier 对每条允许的 ref 必须核对 opaque ID、authority、版本/hash、访问范围、状态及记录形成时的来源快照；kind 未实现或未授权时返回 `unsupported`/安全降级，绝不能视作 verified。当前 PR #123 固定候选仅证明 `project`；`task`、`journal` 尚 unsupported，不能宣称三类来源闭环。
4. 来源全部受信且生成状态成功 -> `real` 并可展示正文；有缺失/权限不足/验证器缺席 -> `partial` 并 withholding 不能证明可信的摘要；版本变化 -> `stale` 且不按当前摘要使用；形成失败 -> `failed`；已配置但该日期无记录 -> `empty`；根未配置 -> `not_configured`；根不可用/损坏 -> `unavailable`。禁止伪造 `real`。失败/陈旧历史在用户选择后可查看其**状态和来源元数据**，正文能否展示须再次验真。
5. 历史记录按业务日期查询、日期/来源/生成时间/版本可见。首阶段读接口是**精确单日 GET**；完整历史分页/列表尚需单独 Core 合同与测试，在未实现前 Web 不得把“当前日”冒充“历史已可用”。
6. 已批准的首阶段形成入口是**用户明确触发生成**，或**用户明确选择并批准导入某条既有简报**；二者进入同一 Core 形成服务：校验请求与日期/时区 → 只按白名单选择来源 → 有界读取并验证 ID/版本/权限 → 形成候选 → 原子持久化日期快照 → 只读查询/回源。导入既有记录必须有明确的记录选择和确认；手动生成按钮本身是形成触发。后续每日调度只能作为同一服务的 trigger adapter，需独立设计并获授权，默认关闭。实际形成 API、持久原子写、幂等、版本冲突、审计、恢复和回滚仍需 Core 安全设计与单独授权；当前阶段不实现、不读真实源、不写生产数据、不调用模型或运行调度。

### 共用形成流程与安全状态（设计候选，待 Core/API 复审）

1. **Trigger adapter** 只区分 `manual_generate`、`approved_import`、未来的 `daily_schedule`，再将显式日期、`Asia/Shanghai`、允许的来源选择、调用主体、策略版本和幂等键交给同一个 Core 服务。日调度不是第二套摘要逻辑；用户确认的产品目标不等于当前调度已获准或应开启。
2. **来源选择与核验** 仅允许用户授权范围内的 `task`、`project`、`journal`。Core 通过各自权威接口按 opaque ID 有界读取最小形成字段，验证归属/权限和 canonical version/hash；不扫描目录、遍历全部任务或日记，也不把前端提交的来源列表直接当证据。任一引用 missing/stale/unauthorized/unsupported/unavailable 时，禁止将未验证内容送入摘要器；按规则产出安全 `partial`/`stale`/`failed` 状态并隐藏不能证明可信的摘要。
3. **摘要形成** 只接收已验证来源快照和固定模板/规则版本。确定性 formatter 与可替换的模型 adapter 是实现选择，不能由本计划认定必须调用模型。当前和本地验收禁止真实模型/外部网络；将来若使用外部模型，必须另行批准数据出站、模型/费用预算和关闭开关，且只发送最小已授权快照。外部新闻不进入任何路径。
4. **触发确认**：`manual_generate` 需要用户在 Web/授权渠道发起明确动作；`approved_import` 需用户明确选择既有记录并确认导入；未来 `daily_schedule` 仅在独立批准后启用，并继续调用相同验证/形成/持久化门禁。权限不能由 Session、定时到点、模型输出或客户端声明替代。
5. **持久化与幂等**：建议形成操作先落 durable operation 记录，并使用 Core 生成/校验的 idempotency key；同 key+同规范化请求只能对应一个 operation 和一条日期记录，同 key+不同 payload 返回冲突。并发双击/重复调度不得重复写；写入与审计原子提交。超时后先按 operation key 查询，不盲目重试。一个 `date + timezone` 只能有一个 current Brief；显式重新形成须使用 `expected_revision` 产生可回溯的新 revision，不原位覆盖旧快照。此为待 Core 评审的方案，不冻结新的公开 wire。
6. **状态与恢复**：内部 operation 状态至少区分 `accepted/validating/generating/committed/partial/stale/failed/recovery_required`；外部 Daily Brief GET 仍只读已持久记录，映射为既有 `real/partial/stale/failed/empty/not_configured/unavailable` envelope。无记录不在 GET 时补生成。来源漂移、进程中断或提交响应丢失均通过 operation 查询、哈希/版本重验及幂等恢复处理；无法证明提交结果时 fail closed 并人工恢复，不生成第二条记录。错误和审计只留脱敏 ID、状态、版本/hash 与时间，不记录正文、绝对路径或凭据。
7. **费用门禁**：模型开关与调度开关分别默认 OFF；启动其中一个不得暗中启用另一个。未来预算在调用前原子预留，并限制每次输入/输出、并发、超时、日/月额度；不确定的供应商结果保留预算占用并禁止自动付费重试。若供应商没有可证明的硬上限，必须明确标注本地估算/软预算，不声称硬封顶。

## 4. A↔B verifier 交接（B owner 最终确认）

- 输入： `{kind, opaque_id, expected_version, principal_or_scope, project_id?, purpose, max_budget}`；仅服务端受控读取，禁止客户端按 opaque ID 任意读取文件。
- 输出仅最小元数据：`{result: verified|missing|stale|unauthorized|unsupported|unavailable, actual_version?, authority_kind, checked_at}`，不得回传 Task/Notes/Brief 正文、路径、私有字段。
- 对 Brief，当前允许 kind 只有 `task`、`project`、`journal`；Notes 只可能参与 Projects 自身关联验证，Capture/Review/Chat/Agent events 均不属于 Brief 来源。必须根据权威模块接口校验身份、对象绑定、版本与可见范围；不允许 generic fake verifier 或目录树扫描替代验证。
- Core 输出继续遵循 #97 已冻结 HTTP envelope 与预算。未实现 kind 明确为 unsupported；任一 Brief 来源无法核验时 summary/items 继续 withheld。A 仅做必要 UI 精确状态适配，不扩展公开 wire。
- B 交付：kind 覆盖矩阵、source ID/version 映射证据、权限/失效/漂移/资源预算与路由真实 TestClient 合成正反例，以及固定 PR HEAD。A 在本地临时合成环境做一次 Core↔Web/Edge 联调与独立审查。

## 5. 本地合成验收规格（尚未执行；无真实数据/模型）

使用随机合成 ID、隔离临时根和假的 Core source adapters。测试只在 loopback；网络默认拒绝，所有外部请求计数必须为 0。Mock verifier 只供测试断言，不能作为生产实现证据。

| 范围 | 合成场景 | 必须断言 |
|---|---|---|
| 来源白名单 | verified 的 Project/Task/Journal；注入 Notes、Capture、Review、Chat、Agent 和新闻陷阱源 | 只调用三类允许的来源 verifier；陷阱请求为 0；unsupported kind 不进入摘要输入 |
| 身份/版本 | ID 不匹配、hash 漂移、缺失、越权、source unavailable、读取预算超限 | 逐项准确返回 verified/missing/stale/unauthorized/unavailable/unsupported；任何不完整组合都不把摘要标 real，未验证正文被 withholding |
| 人工触发/导入 | 无用户动作、显式 generate、未确认/已确认 import | 无动作无形成请求；生成只由显式触发启动；导入缺少明确记录选择/确认时拒绝，成功后 refs 可逐条回查 |
| 持久化/幂等 | 同 key 重试、同 key 不同 payload、并发双击、调度重复、日期 revision | 同请求始终只有一个 operation/一条 current 记录；payload 不同返回冲突；重复日调度不重复形成；显式 revision 使用 CAS 且旧快照可回看 |
| 故障恢复 | 来源读取中断、摘要器错误/超时、提交前崩溃、提交后响应丢失、operation 状态不确定 | 失败保留准确状态；响应丢失先 exact-query operation 并恢复同一结果；不得盲目创建第二条记录或显示成功 |
| 读写分层 | 精确日期 GET、无记录 GET、重复 GET、页面导航 | GET 仅读取，不触发 verifier 外的写、摘要器、scheduler 或 provider；无记录返回 empty/not_configured，不现场生成；不请求无关页面 API |
| 认证与隔离 | 匿名/错误 Origin/无权限、越界 ID、Private/外部路径 | 401/403 或合同规定的拒绝；无路径、正文、对象存在性泄露；对 Private 和真实根访问为 0 |
| 调度/费用 | 默认 scheduler/model OFF；仅测试配置打开 scheduler；预算不足与 provider 超时 | 默认没有计划作业/模型请求；测试开启后仍调用同一形成服务并按日键幂等；预算在调用前预留，不自动换模型或付费重试；真实 provider 调用数永远为 0 |

**执行门槛与证据格式：** B 固定 verifier HEAD 后，A 从固定 main + 固定 Core/Web HEAD 建临时集成 worktree，使用合成 Project/Task/Journal roots 运行 Core HTTP → Web helper/UI 一次跨层联调；记录确切 commit、方法/路径/HTTP 状态、operation 状态/合成 ID 和请求 allowlist 计数，不保存正文或凭据。当前 PR #123 固定 HEAD `66821ef717dde8f8a57404e9b0924d5bdba6cbf4` 仅支持 Project verifier；Task 与 Journal 仍 unsupported，所以涉及它们的可信 happy path 必须标 **NOT RUN/BLOCKED**，不能用 Mock 通过代替真实 Core 验证。除非 B 发布新的固定 HEAD，本项不宣称已集成。

## 6. 最小真实来源只读授权包（**请求草案，尚未授权**）

**授权目的：** 在后续明确批准后，只判断 `30-Projects` 项目主档、最多一条用户指定 Task/Journal 引用及现存 Brief 元数据是否能满足当前 Daily Brief 来源契约；不对整个 Vault 作探测。Notes 不属于 Brief 来源；本最小包也不检查 Notes 内容或关联，若要验 Projects 的 `linked_notes`，须另行指定并批准。

**建议最小样本：** (a) 用户指定 **1 个 Project 主档**，只查看稳定 ID、显示字段、状态、下一步、更新时间及来源版本；(b) 仅在对应来源 kind 已有 verifier 时，最多 **1 个用户指定 Task 与 1 条 Journal 回顾记录** 的 ID、日期/业务归属、版本/hash 和权限元数据；(c) 最多 **1 条用户指定的既有 Brief**，仅查看日期、时区、生成/导入时间、状态和最多 3 个 source-ref 的 ID/kind/version，不看 summary/body。任一对象或映射不存在，记录 `NOT CONFIGURED/UNSUPPORTED`，不创建替代数据、不猜路径。准确宿主路径当前 UNKNOWN，执行前需用户提供/指定。
**范围：** 指定的只读文件或显式目录，不允许递归 `/SecondBrain` / `20-Knowledge` / `Private`、不允许任意文件名匹配或目录枚举；只读无 chmod/chown/ACL/mount、无写入/删除/移动。无外发、模型 API、Hermes 聊天或第三方同步。
**时间与审计：** 一次性短时用户现场授权，运行前列出精确样本与路径（本阶段路径 UNKNOWN）、操作主体、访问时间、预期字段与权限；保留仅字段/成功失败/脱敏 source-ref 的审计，不保存业务正文或登录凭据在 Issue、PR、测试快照。
**停止条件：** 样本/路径不明确、权限不足、需读取额外正文、源版本漂移、任何越权/非预期网络请求立即停止该子项。无需真实来源仍能继续本地合成验证。
**用户须明确批准：** 哪些准确路径/文件、能否只读正文（默认否）、最多哪些引用字段与一次性访问窗口；不授权任何 NAS 部署或 Promote。

## 7. 生产 App 只读发布验收方案（**只准备，不实施**）

- **版本和变更清单：** 以发布时实际受审 main 固定 SHA 构建候选；列出现有 NAS App 镜像 SHA 与目标变更 PR、DB/schema/env 影响。前次记录的 App-only 镜像为 `sha256:e55b0e9c65433a208df0f66a68ec2f91e2341b163108e5d09030ac4a7b343f47`（历史快照，发布前必须重新核验，不据此判断当前在线镜像）。
- **前置条件：** 用户另行批准部署且所有 rollback/compose 配置与镜像备份点真实核验；生产 `SB_PROMOTE_ENABLED=false`，Knowledge RO，Private 未挂载；形成写入、调度、模型与真实来源访问各自取得匹配授权。不以 App-only 发布授权推导任何 Core 持久写入/真实来源/模型/定时权限；禁止迁移/改挂载或真实 Writer。
- **验收流程：** 先合成候选验收和权限审计，再经授权 App-only canary/发布：/health、登录/匿名 401、错误 Origin 403、明确导航 Home/Chat/Today-Calendar/Inbox/Review/Projects/Knowledge/Brief/Activity；桌面 1440×1000、平板 820×1180、手机 390×667 无遮挡/溢出；仅当前页面模块 GET，无被动跨模块或正文泄漏；Projects/Brief 未配置必须诚实降级；Brief 可信正文仅在真实 verifier 与真实记录获准核验后测试，否则 NOT RUN。
- **回滚与停止：** 任一身份/来源泄漏、非法写入、Promote 非 OFF、Private 意外挂载、业务内容错误宣称 real、长时间 5xx/前端 401 退化、不能回退旧镜像，立即终止发布并按事先审定的旧镜像/配置原位回滚；不在本方案中执行回滚。保留最小脱敏 HTTP 与截图证据。
- **验收分层：** 源码合入 / 合成读链 / 受控生产只读 Smoke / 真实用户业务验收 / OS Writer 生产安全分别独立判定；V1 MUST 必须含真实数据完整闭环及授权写入，不能因只读发布宣称 DONE。

## 8. A 主线下一步与明示阻断

1. **Daily Brief 产品目标已确认（D087 同日修订）：最终每日自动生成个人任务简报；先实现人工触发/批准导入和可信持久化，再接可关闭的定时调度。** 后续只需复核实现范围、写入安全/来源规则及独立授权，不再重复征询这一产品取舍。
2. B #97 按 D087 白名单完善其权威 verifier，并给固定 HEAD；当前 `project` 已候选支持，`task` 与 `journal` 仍 unsupported。A 不自行伪造来源、扩展 Core 或用测试 Mock 代替 B 的权威检查。
3. B verifier 固定 HEAD 到位后，A 在 `A_SOURCE_PLAN_READY + B_VERIFIER_LOCAL_READY` 门槛上以固定 main/Core/Web HEAD 做一次真实 loopback 合成 HTTP+Web/Edge 集成，覆盖 Projects/Brief 可信来源、partial/stale/failed/empty/not_configured、权限隔离与请求范围，再交 A ChatGPT 独立审查；仅通过审查后由授权责任人决定合并顺序并更新 CURRENT。**不得因本文先合并、部署或读取真实来源。**
4. 最小真实来源/发布授权必须另由用户针对精确资源与部署范围显式批准；未授权前持续 NOT RUN。OS isolation Writer #106、Promote ON、真实 Hermes/付费模型不在本任务。

参考：`docs/baseline/business-specs/SecondBrain-Web-App-V1-Business-Spec.md`、`docs/baseline/业务规范.md`、`docs/baseline/00-CURRENT.md`、#76 #6284807350、#96 #6284809864、#97 frozen wire。
