---
created: 2026-10-20
status: proposed-for-product-review
source: PMO #76 / A #96 / CURRENT / Web App V1 Business Spec / 业务规范
scope: product decision candidate; no authority to read, deploy or write real data
---
# Projects 主档、Daily Brief 形成规则与最小真实来源验收授权（A 决定稿候选）

> 本文为 **A_PRODUCT_SOURCE_PLAN_CANDIDATE**。除已批准的业务边界外，涉及新增简报形成方式的产品选择须经用户/PMO 确认。文档与合成实现本身不授权任何生产操作。

## 1. 已批准的边界 / 待确认的取舍

**已批准：** Vault 逻辑目录 `30-Projects` 是项目资料区域；Inbox-first、AI 只能建议分类/关联、用户审批及正式 Knowledge/Private 边界不变。Projects 数据不能从目录名、Task 标题、AI 猜测直接推断；Home 只是聚合层。Web V1 MUST 有 Projects、Daily Brief、History、跨端及真实业务数据，现仍 NOT DONE。Core 已合入的 `/api/projects`、`/api/daily-brief` 严格 GET wire 及安全降级不变。

**待用户确定的一个主要产品取舍：简报形成触发方式。** 推荐 **先人工触发或明确批准的已有记录导入/保存**，形成 Core 可回源的日期快照；**定时自动生成 + 调模型**列为后续独立决策。不得因本文件默认启动生成、写入或付费。

## 2. Projects 权威主档（建议采纳 v1）

1. 每个项目由用户明确创建/维护唯一稳定 `project_id`，不等于文件夹名或可变展示标题；主档是 `30-Projects` 中用户维护的结构化项目元数据或显式只读索引，具体物理文件名/模式在不读取真实目录前保持 UNKNOWN。
2. 最小字段：`project_id`、`title`、`status`（active/paused/completed/archived/unknown）、`updated_at`、`source_ref={opaque id, sha256/version}`；可选 `next_step`、`recent_activity` 与 `linked_notes`。`unknown` 是明确缺失，不由文件时间/目录推断。
3. 用户手动维护项目标题、状态、下一步及关联意图；AI 可提出编辑/关联建议但无审批不得修改项目主档，也不得替换原文或绕过 Inbox。项目文档/笔记优先**关联**，非强制迁移文件。
4. Task/Notes 关联采用显式 ID + 版本/hash + 具权限的权威元数据 API 回查。逐条核验项目归属/可见范围/漂移。未证实则**隐藏该关联**、标 partial；不得把 JSON 中写有某个 ID 当作 verified；禁止读取/返回原文、隐私路径、会话 ID。
5. Project `real` 仅表示当次返回的明确项目字段和所声称关联已完整核验。索引存在但关联验证缺失 -> partial；配置不存在 -> not_configured；配置有且为空 -> empty；源不可读/不可信 -> unavailable。保留分页、资源上限及显式配置的最小根，不扫描整个 Vault。

## 3. Daily Brief 权威形成与历史（建议采纳 v1）

1. **写路径与读路径分离。** 受控形成过程在单独明确授权后，把简报持久写为 Core 权威日期快照；`GET /api/daily-brief` **永不**临时生成、抓聊天、调用模型或扫描来源。需要版本与原始来源可追溯，不将 Web 拼接内容当已生成简报。
2. 每条记录：`brief_id`、`date`、`timezone=Asia/Shanghai`（本轮默认业务日）、`generated_at`（UTC 存储）、`generation_status`、`categories`、`summary`、`source_refs=[{kind,id,version}]`，及 Core 内部审计/生成渠道元数据。允许服务端时间与业务日期区分；不根据用户设备时区暗改日期。单个日期目前只接受一权威时区格式；如需多时区须单独设计迁移，不能 silent fallback。
3. 来源只来自经授权的 Core 正式模块及已核验版本（例如 Task、Journal、Notes、Capture、Review、Project）；verifier 对每条 ref 必须核对 opaque ID、authority、版本/hash、访问范围及状态，且要覆盖记录形成时的实际来源快照。支持的 kind 逐一声明；unsupported/无授权不得视作 verified。
4. 来源全部受信且生成状态成功 -> `real` 并可展示正文；有缺失/权限不足/验证器缺席 -> `partial` 并 withholding 不能证明可信的摘要；版本变化 -> `stale` 且不按当前摘要使用；形成失败 -> `failed`；已配置但该日期无记录 -> `empty`；根未配置 -> `not_configured`；根不可用/损坏 -> `unavailable`。禁止伪造 `real`。失败/陈旧历史在用户选择后可查看其**状态和来源元数据**，正文能否展示须再次验真。
5. 历史记录按业务日期查询、日期/来源/生成时间/版本可见。首阶段读接口是**精确单日 GET**；完整历史分页/列表尚需单独 Core 合同与测试，在未实现前 Web 不得把“当前日”冒充“历史已可用”。
6. 推荐形成方式为**用户显式触发并确认的导入或受控生成→验证→持久记录→只读展示**。实际形成 API、持久原子写、幂等、版本冲突、审计与回滚需经独立安全/写入权限设计。定时器、主动生成、外部联网、AI 付费一律不在本阶段授权。

## 4. A↔B 最小 verifier 冻结建议（B owner 最终确认）

- 输入： `{kind, opaque_id, expected_version, principal_or_scope, project_id?, purpose, max_budget}`；仅服务端受控读取，禁止客户端按 opaque ID 任意读取文件。
- 输出仅最小元数据：`{result: verified|missing|stale|unauthorized|unsupported|unavailable, actual_version?, authority_kind, checked_at}`，不得回传 Task/Notes/Brief 正文、路径、私有字段。
- 必须根据权威 Task/Notes/Journal/Capture/Review 读取 API 校验身份、所请求对象、绑定和版本；不允许 generic fake verifier 或目录树扫描替代验证。
- Core 输出继续遵循 #97 已冻结 HTTP envelope 与预算。未实现 kind 明确列为 unsupported，Projects 与 Brief 继续 partial/withheld；A 只做必要 UI 精确状态适配。
- B 交付：kind 覆盖矩阵、source ID/version 映射证据、权限/失效/漂移/资源预算与路由真实 TestClient 合成正反例，以及固定 PR HEAD。A 在本地临时合成环境做一次 Core↔Web/Edge 联调与独立审查。

## 5. 最小真实来源只读授权包（**请求草案，尚未授权**）

**授权目的：** 仅判断项目主档格式/Task-Notes 关联与现有 Brief 记录能否满足可信来源规则；不对整个 Vault 作探测。

**建议最小样本：** (a) 由用户选定的 **1 个项目主档**（仅项目 ID、显示名、状态、下一步、更新时间、来源版本）及该项目显式关联的 **最多 1 Task 和 1 Note** 的 ID/版本/权限元数据；(b) **最多 1 条已存在且经用户明确挑选的 Daily Brief** 的日期、时区、生成时间、生成状态及最多 3 个 source-ref 的 ID/版本元数据；不存在则记录 NOT CONFIGURED，**不创建或生成替代记录**。如 Note 内容核验不可避免，应再次请求逐文件正文授权，不能由本包自动推导。
**范围：** 指定的只读文件或显式目录，不允许递归 `/SecondBrain` / `20-Knowledge` / `Private`、不允许任意文件名匹配或目录枚举；只读无 chmod/chown/ACL/mount、无写入/删除/移动。无外发、模型 API、Hermes 聊天或第三方同步。
**时间与审计：** 一次性短时用户现场授权，运行前列出精确样本与路径（本阶段路径 UNKNOWN）、操作主体、访问时间、预期字段与权限；保留仅字段/成功失败/脱敏 source-ref 的审计，不保存业务正文或登录凭据在 Issue、PR、测试快照。
**停止条件：** 样本/路径不明确、权限不足、需读取额外正文、源版本漂移、任何越权/非预期网络请求立即停止该子项。无需真实来源仍能继续本地合成验证。
**用户须明确批准：** 哪些准确路径/文件、能否只读正文（默认否）、最多哪些引用字段与一次性访问窗口；不授权任何 NAS 部署或 Promote。

## 6. 生产 App 只读发布验收方案（**只准备，不实施**）

- **版本和变更清单：** 以发布时实际受审 main 固定 SHA 构建候选；列出现有 NAS App 镜像 SHA 与目标变更 PR、DB/schema/env 影响。前次记录的 App-only 镜像为 `sha256:e55b0e9c65433a208df0f66a68ec2f91e2341b163108e5d09030ac4a7b343f47`（历史快照，发布前必须重新核验，不据此判断当前在线镜像）。
- **前置条件：** 用户另行批准部署且所有 rollback/compose 配置与镜像备份点真实核验；生产 `SB_PROMOTE_ENABLED=false`，Knowledge RO，Private 未挂载，禁止迁移/改挂载或真实 Writer；不得暗中开启模型/外部服务。
- **验收流程：** 先合成候选验收和权限审计，再经授权 App-only canary/发布：/health、登录/匿名 401、错误 Origin 403、明确导航 Home/Chat/Today-Calendar/Inbox/Review/Projects/Knowledge/Brief/Activity；桌面 1440×1000、平板 820×1180、手机 390×667 无遮挡/溢出；仅当前页面模块 GET，无被动跨模块或正文泄漏；Projects/Brief 未配置必须诚实降级；Brief 可信正文仅在真实 verifier 与真实记录获准核验后测试，否则 NOT RUN。
- **回滚与停止：** 任一身份/来源泄漏、非法写入、Promote 非 OFF、Private 意外挂载、业务内容错误宣称 real、长时间 5xx/前端 401 退化、不能回退旧镜像，立即终止发布并按事先审定的旧镜像/配置原位回滚；不在本方案中执行回滚。保留最小脱敏 HTTP 与截图证据。
- **验收分层：** 源码合入 / 合成读链 / 受控生产只读 Smoke / 真实用户业务验收 / OS Writer 生产安全分别独立判定；V1 MUST 必须含真实数据完整闭环及授权写入，不能因只读发布宣称 DONE。

## 7. A 主线下一步与明示阻断

1. 用户/PMO 审阅并确认 **Brief 先人工触发/导入保存还是定时自动生成** 的产品取舍；未确认前推荐人工触发/导入-first 方案仅是候选。
2. B #97 按最小 verifier 接口在合成数据环境独立开发并给固定 HEAD；A #96 如有必要做 Web 精确状态适配，不新增 Mock 页面。
3. A 在 `A_SOURCE_PLAN_READY + B_VERIFIER_LOCAL_READY` 后做一次真实 loopback 合成 HTTP+Edge 多视口、定向 Core/Web、安全回归与独立代码审查；只有无 P0/P1 且 HEAD/差异核验后才按依赖合并并更新 CURRENT。**不得因本文先合并真实部署或获准读取。**
4. 最小真实来源/发布授权必须另由用户针对精确资源与部署范围显式批准；未授权前持续 NOT RUN。OS isolation Writer #106、Promote ON、真实 Hermes/付费模型不在本任务。

参考：`docs/baseline/business-specs/SecondBrain-Web-App-V1-Business-Spec.md`、`docs/baseline/业务规范.md`、`docs/baseline/00-CURRENT.md`、#76 #6284807350、#96 #6284809864、#97 frozen wire。
