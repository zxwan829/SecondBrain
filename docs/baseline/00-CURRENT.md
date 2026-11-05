---
created: 2026-09-30
updated: 2026-11-06
status: current
source: GitHub SecondBrain Monorepo
---
# SecondBrain — 当前项目状态

> 本文件是项目唯一进度入口。它记录可核验的主线、运行快照、验收状态、当前下一步和少量核心任务；历史过程见 `Progress-Log.md`，稳定架构见 `Architecture.md`，批准的决定见 `Decision-Log.md`，最后一次运行快照见 `Environment-Baseline.md`。未实时复核的运行状态一律标为 UNKNOWN。

## 当前快照

- **最新代码与生产版本：** GitHub main 已包含 PR #279 部署记录；生产 App 仍运行 PR #277 固定源码 SHA `7272b7388d9453a4abe212e6aa8d528e7e0dcd82`。本轮状态记录 PR 仅更新文档，不改变 App 部署目标。
- **总体：** V1 尚未完成。GitHub main 的代码/文档状态不代表生产部署、真实数据验证或用户验收。
- **最近已核验生产快照：** 2026-11-05 PR #277 部署后，App revision `7272b7388d9453a4abe212e6aa8d528e7e0dcd82`、Image ID `sha256:d73bb0fb73b77a728c4f6eecde44c8309695abb573e00048c6ba3affb50fc1e1`、running/healthy；Compose SHA-256 `f5760550d5d9fe197cd58bd07c77bc178fb04fec27a9e990342d642530ace020`。详情见 `Environment-Baseline.md`。
- **生产安全闸门（2026-11-05 部署后复核）：** Promote=false、Weixin 未开启、App Knowledge 挂载只读、Private 未挂载；App UID/GID `1026:100`，端口仍为 `127.0.0.1:9120→8000`，两个 Secret 文件只读挂载。归一化 Compose 仅 App image 改变；Hermes 容器、镜像与启动时间未变。详情见 `Environment-Baseline.md`。
- **开发阶段：** V1 核心业务闭环收口。#269/#274 App-only UI 已部署；工程浏览器 Gate PASS，用户已明确放弃旧版 Chat UI 人工视觉验收，状态为 `USER_WAIVED / NOT RUN`（绝不记为 `USER_UAT_PASS`）；VNext 保持冻结。
- **PR #274 工程验收与部署：** Daily Brief 合成旅程的 Journal 请求断言按页面阶段记录基线；完整 Gate [Actions #41967914277](https://github.com/zxwan829/SecondBrain/actions/runs/41967914277) PASS、独立审查 PASS。PR #274 固定 merge commit `268ccae7255c1e2f4fea057d9630d40d7dcca704` 已于 2026-11-05 部署，生产健康和安全门禁通过。工程 Gate 与部署验证都不替代新版 Chat UI 用户验收。
- **PR #277 App-only 部署与生产合成 UAT：** 固定 merge SHA `7272b7388d9453a4abe212e6aa8d528e7e0dcd82` 已部署，App running/healthy；Compose 仅 App image 变化，Hermes、挂载及权限不变。生产合成 UAT 部分通过：Notes Draft 新建、编辑、保存、刷新重开及精确 API 回读通过；Journal 空白合成日期新增两条不同幂等键记录，刷新后两条按序回读。相同幂等键重放仍 NOT RUN，故整项 UAT 尚未通过。详情见 `Environment-Baseline.md`。
- **本阶段状态：** `PARTIAL / LIMITED_CHAT_UAT_PASS / CHAT_UI_DEPLOYED / CHAT_UI_ENGINEERING_GATE_PASS / USER_WAIVED_NOT_RUN / NOTES_JOURNAL_ISOLATED_ENGINEERING_PASS / PR277_DEPLOYED_AND_VERIFIED / NOTES_JOURNAL_PRODUCTION_SYNTHETIC_UAT_PARTIAL / UAT_SCOPE_DEVIATION_ACCEPTED`。PR #269、#274、#277 App 均已合并部署；PR #277 生产健康及安全核验通过。Notes Draft 与 Journal 部分生产合成旅程通过；Journal 同 key replay 尚未运行。另：登录后页面自动落至 Home，一次完整可访问性快照包含现有业务摘要；此前 Notes 页快照包含列表标题。未打开既有记录详情，未修改/删除记录或将内容保存、外发；该读取超出本轮仅处理合成数据的边界。PMO 已裁定接受该低严重度测试范围偏差记录，不要求补跑生产同键重放；裁定见 [PR #281 comment](https://github.com/zxwan829/SecondBrain/pull/281#issuecomment-6658259876)。Chat UI 人工视觉 UAT 仍 `USER_WAIVED / NOT RUN`，不是用户验收通过；其他 V1 未验收项保持原状。

## 能力状态

原 V1 MUST/SHOULD 与 D077 Companion 产品合同继续以[Web App V1 业务规格](business-specs/SecondBrain-Web-App-V1-Business-Spec.md)、[Universal Capture 业务规格](business-specs/Universal-Capture-Business-Spec.md)、`Decision-Log.md` D077 为准。本矩阵只汇总 main、最近有日期的生产证据和用户验收，不缩减正式范围。D086 合成来源授权/Consent 候选不等于微信渠道；微信输入渠道按 P4-2 / D087 单独记录。

| 模块 | main 代码 / 集成 | 最近有证据的生产状态 | 用户验收 / 阻断 |
|---|---|---|---|
| App Shell / 登录与路由 | main 有 Shell、鉴权与路由实现 | HTTPS `/health`、`/`、`/login`、`/notes` 为 200；匿名 session、Tasks、Capture summary、Knowledge search、Promote API 均为 401；用户已在 2026-11-04 登录并完成部分真实页面操作 | 本轮有限登录旅程通过；未覆盖所有模块/路由，完整跨页体验仍待验收 |
| Home | main 有 Home 页面与部分聚合 | HTTPS `/` 返回 200；未认证浏览器不执行 App 内容聚合 | 动态 Home 完整聚合未验收；首次从 `/` 登录会读取聚合数据，体验时可直接打开目标模块 |
| Chat / Hermes / D077 | main 包含 PR #269/#274 Chat UI；PR #32 已修复情境偏好截断；合成 Core JSONL→相关性选择→Hermes `/v1/runs` 请求传递通过；D077 Companion 仅部分实现 | App revision `7272b738`；本轮沿现有 Core→Hermes 完成 6 次合成真实模型 Run；详见本节与 Progress Log | #30 真实模型行为观察为 PARTIAL：无关问题未提及偏好、纠正后回答使用新值、撤销后未复述偏好，初始自然召回缺颜色；因未记录逐 Run 注入上下文，目标记忆因果归属 UNKNOWN；冲突处理未运行。人工视觉 UAT `USER_WAIVED / NOT RUN` |
| Today / Calendar / Journal / Task | main 有页面/API 的部分实现；显式 Task API 与持久化实现存在 | 用户于 2026-11-04 实测 Task 创建、完成及恢复；PR #277 Journal 生产合成日写入两条不同 key 的记录并刷新/API 回读通过 | Notes/Journal 合成 UAT 部分通过；生产同 key replay NOT RUN，真实数据/用户验收未通过；完整 Calendar 未验收 |
| Capture：文本 / Markdown / TXT | main 有 Raw→Review 路径及文本入口；`/inbox` 使用显式 Capture/Notes scope | 用户已用合成内容验证文本 Capture→Inbox→Review 保存、回读、关联及刷新持久化；Linux Chromium Inbox capture/retry/source-protection 三视口通过；#269 未改该旅程代码 | 仅限上述文本 Capture 旅程；附件、URL 和 Promote 未验收/不在本次操作范围 |
| Capture：URL / Web | main 有抓取与 Review 路径 | 本轮未提交 URL 或读取 Raw/Review 数据 | 多站点、失败恢复和用户流程仍未完整验收 |
| Capture：PDF / 图片 / 音频 | main 有 PDF/OCR 与图片处理的部分实现；音频处理未闭环 | 本次未处理生产附件；生产质量 UNKNOWN | 合成 OCR 不等于真实文件验收；STT 后端/真实样本仍阻断 |
| 微信输入渠道（P4-2 / D087） | main 有渠道相关来源；D086 合成 Authority/Consent PR 不等同微信渠道实现 | 插件文件存在但 `not enabled`，Core 微信开关为 false；未扫码/收发消息 | **未接入、未用户验收**；真实渠道另行授权 |
| Review / Approval | main 有 Review 与受控审批部分实现 | 匿名 Promote API 为 401；本次未登录查看或执行审批 | 用户登录后可检查授权范围内 Review；端到端 Approval→Knowledge 未完成，生产 Promote 关闭 |
| Knowledge / Notes / 标签 | main 有只读检索、Notes 与词库；PR #242 已合入（#55 完成） | Notes Draft 合成记录在生产通过新建、编辑、保存、刷新重开与 API 回读；授权集合仅 Drafts，Knowledge 集合负向请求返回 404；未访问 Vault/Knowledge 正文 | 仅 Notes Draft 合成 UAT PASS；真实 Vault collection/笔记写入未运行，Knowledge 用户验收待完成 |
| Projects | main 有读接口与页面的部分实现 | 未核验项目数据旅程 | 真实来源完整性和用户验收 UNKNOWN |
| Daily Brief | main 有读接口与页面的部分实现 | 未执行简报数据或模型旅程 | 真实生成、数据来源及用户验收 UNKNOWN |
| Activity / Agent Health | main 有部分 Activity 与健康状态实现；来源覆盖不完整 | 未做登录态或业务数据核验 | 来源范围、状态准确性和用户验收未完成 |
| 响应式 / 多端 / Obsidian 同步 | main 有响应式样式 | Linux Chromium 合成旅程在 1440×1000、820×1180、390×844 通过；精确 768px 未运行；同步未复测 | 真机/当前用户浏览器体验与 Mac↔NAS 双向同步未验收 |
| Security / Writer / Promote / Private | main 有 fail-closed 与受控写入相关代码；D090 Writer 候选未合入 | Promote=false、App Knowledge RO、Private 未挂载；Hermes safe root 三个捕获目录；`SB_WEIXIN_INBOX_ENABLED` 未设置 | 跨进程/OS 隔离及正式 Promote 未验收；不在本轮开启 |

## 2026-11-04 首轮用户 UAT 与 Chat 安全核验收口

- 用户登录实测：Task 创建/完成/恢复、Capture 文本原文保存→Inbox→Review 持久化、Knowledge 搜索/阅读、Journal 2026-10-18 历史正文、Chat 历史会话读取均有页面证据；本项只代表相应有限旅程，不代表整个 V1 功能通过。
- Notes 历史版本可预览但未执行恢复；回收站界面可打开，Trash 根未配置；Projects 与 Daily Brief 缺可信数据源/配置。笔记保存与 Journal 追加在隔离合成环境的 Core/API/浏览器工程验证结果见本轮 PR；这不代表生产写入授权或真实数据验收。旧 V1 UI 问题统一追踪于 #260；VNext 保持冻结，尚未启动开发。
- **Chat 实际核验纠错（2026-11-04）：** 此前把模块级字符串常量 `PRE_TOOL_CALL_HOOK_UNAVAILABLE` 错误地要求出现在 `_pre_tool_block` 函数体内，误判生产 Hermes 镜像缺失 fail-closed 补丁。随后由 Codex 直接核验生产容器，确认执行文件 SHA-256 为 `b600d5bf028e5500c04b8a899f49882769e52a110fe1b633d624454a94d92c40`，与固定源码应用补丁后的完整执行文件一致，且异常分支引用阻断常量。**正式撤回缺补丁结论，不因该误报重建生产 Hermes；本次未部署或回滚。**
- **#269 合并、部署与用户验收边界：** PR [#269](https://github.com/zxwan829/SecondBrain/pull/269) merge commit `d06e3f3bde2cf8ee260992644c2ae5d67aeef362`；三视口 Linux Chromium Gate [Actions #41785664124](https://github.com/zxwan829/SecondBrain/actions/runs/41785664124) PASS；精确 SHA 构建 [Actions #41788688422](https://github.com/zxwan829/SecondBrain/actions/runs/41788688422) SUCCESS。App image ID `sha256:250437fc8b57642770347d6de73d86e791ffd8aaebdaba399170bc5018fe2270`，`linux/amd64`。原始 artifact `13301449533` / digest `sha256:e6040f9c7262b8477169ef0e5fd8a1a1e7959d1b2857e423dd33c0cae7a89b9c`；NAS App-only 包 SHA-256 `49905f26e9fc7780a1a58be693f7d1558b989421291ffcfa417a3856674e684a`。App-only 部署与健康/安全检查通过；新版 UI 的用户实际体验仍 NOT RUN。
- **Chat 安全与基础 UAT：** 此前的插件活动 Hook/策略探针、真实 Hermes AIAgent API Run 审批/拒绝/Skills 集成测试、App→Hermes health 与真实模型普通文本回复/刷新恢复均已有通过记录；此前“缺少 fail-closed 补丁”判断已正式撤回。上述有限证据不代表跨会话记忆、完整 Companion 或所有工具场景验收。

## 近期执行规划（2026-11-06 PMO 更新）

**目标：在收口已部署成果的同时，优先证明“跨会话记住、纠正并有效帮助用户”，减少重复审批和 Hermes 长期维护成本，再完成全部 V1。** 本节定义当前工作顺序；[V1 交付规划](V1-Delivery-Plan.md)保留 P1—P6 全量分解与验收标准。下列七个工作包是原 P1—P6 的执行重排（新增明确的编辑器接续包），不是新增产品阶段，不缩减 V1 范围；旧 A/B 波次和 #76/#96/#97 不再作为任务启动入口。VNext 继续冻结。

| 顺序 / 对应原阶段 | 目标与拆解 | 汇合条件与当前状态 |
|---|---|---|
| 1. 现有成果收口（P1、P4、P5） | 接续已部署 #277；准备 Notes Draft 创建/编辑/重开与 Journal 追加/回读的有限旅程，明确数据位置、失败恢复、与 Obsidian 的关系；授权后执行业务 UAT 并定向修补 | #277 已部署且运行门禁通过；真实业务 UAT 待单独授权。JSONL 持久化不等于 Obsidian 同步；不重复部署已完成版本 |
| 2. Hermes 补丁盘点与复用（P2、P5） | 对固定上游版本列出源码补丁、插件、配置及 Core 适配器；逐项记录用途、必要性、上游扩展替代方式、升级验证方法，分类为保留/可迁出/可删除/待验证；以合成数据评估原生记忆接口能否服务现有受控链路 | 交付可追溯到源码/版本的清单与最小建议；未检查的能力标 UNKNOWN。必要安全补丁保留，不以升级整个 Hermes 为前置；盘点结论不自动授权删除补丁或更换记忆权威来源 |
| 3. 跨会话记忆闭环（P2-1～4） | 接续 #30，沿保存→检索选择→上下文传递→模型采用定位故障；优先最小修复，核验自然召回、纠正、撤销、无关请求及事实回源；只对已证明的缺口比较 Hermes 原生能力或检索改进 | 隔离链路与真实模型证据分开；真实新会话能用正确记忆、纠正后采用新值、撤销后不再使用、无关时不过度召回，才通过对应业务验收。JSONL 写入和 Stub 回答不代替实际效果 |
| 4. 自然对话与日常记录（P1-2/3、P3） | 梳理 Chat 收录、Journal、Task 的实际确认次数、保存回执和重试；先修现行规格内的重复提示及状态错误；涉及合并确认或改变批准语义，集中提出正式规格修订后实施 | 保留 Core 统一处理、D086 Inbox 原件和专用写入边界；正式 Knowledge 仍须明确批准。用户清楚知道保存了什么、在哪里、是否成功；不能用简化体验之名绕过审批 |
| 5. BlockSuite 编辑器接续（P4-3/5，#46） | 紧接 #287 的合成业务闭环交付；复用归档试验，按兼容差距→用户确认→Core Notes/附件接线→保存重开→Obsidian 往返的顺序推进；明确支持子集和回退，不从零重做 PoC | 当前为已排入计划、尚未实施。前置只限现有 Notes 合同、Markdown/图形数据方案与编辑体验确认，不等待记忆完全验收或整套 V1 完成。正式选型/迁移及实施边界按下文五步执行；无损不成立时提出具体取舍，不静默锁入专有格式 |
| 6. 记忆驱动的日常价值（P2-5、P3） | 复用 Task/Project/Journal、Daily Brief、预算与反馈能力；补来源可信的回顾、建议和受控业务动作；Daily Brief 范围为 Task/Project 加 Journal 回顾 | 来源可回查，建议与实际执行区分；主动/被动额度、频次、拒绝与恢复按既有合同验证；真实模型/费用/数据处理仍依对应授权 |
| 7. 剩余 V1 与完整验收（P1、P4～P6） | 对照全量矩阵补齐 Knowledge 审批闭环、多格式输入、微信、编辑器与文件生命周期、日历/项目、Activity、多端和同步；复用已有实现及有效证据，分组集成 | 每项正式 MUST 有对应能力及验收证据，缺项明确保留；完整 V1 不以 PR 数或部分闭环宣布完成。飞书范围待决按原规格处理，不能静默删减或扩张 |

**并行与汇合：** 当前主任务仍为工作包 4 / #287；工作包 3 已按有限真实模型 PARTIAL 收口，不再为编辑器前置追加 Run。工作包 5 的归档资产/兼容差距只读核对可与 #287 并行，在 #46 记录；#287 合成闭环交付后优先接续工作包 5，再进入工作包 6、7。编辑器不依赖记忆完全验收、Daily Brief 完整或整个 P4 完成；只等待直接接口及兼容方案。Web/Core/独立 Review 由主 Agent 调度，明确文件所有权，不同时改共享 Notes/路由文件。已获授权的独立工作继续，普通错误包内修复，不因个别待决项全线待命，不重复有效测试。

**备份恢复贯穿执行（P5/P6）：** 先核对已有文档和配置定义，列清个人记忆、Journal、Task、Notes、Inbox 原件及必要元数据的权威位置，区分不可重建数据与可重建索引；核实备份覆盖、保留与恢复证据，缺证标 UNKNOWN。准备隔离恢复演练与校验步骤；真实 NAS/业务数据读取、备份配置和恢复操作按对应授权执行。Compose 回滚不等于业务数据备份，不为此预建新备份平台。

**技术取舍：** 固定 Hermes 版本是可复现措施；业务定制优先配置、插件和窄适配器。现有必要安全补丁未经替代验证不得移除。Core JSONL 继续作为个人记忆权威；原生记忆的评估不等于启用第二套权威存储。先定位记忆链路失败，再决定是否需要关键词/向量混合检索；不把新数据库或 Runtime 重写当默认前置。

### 当下框架策略：编辑器、Obsidian 与搜索

**排程已调整：BlockSuite 为 #287 之后的下一工作包，接续 #46；兼容差距核对可以提前并行。** 本次批准工作包顺序和准备方向，不将 BlockSuite 写成已选型或已集成；#260 整站 VNext 仍冻结。复用既有归档源码/运行证据，只迁入经审查的必要增量，不恢复旧试验整包，不重做 PoC。正式编辑器选型和实施范围在下列步骤 2 集中确认一次；范围内普通问题持续推进，不逐项请示。Vault 开写、生产部署、付费模型及索引服务另依对应授权。

| 领域 | 框架建议与拆解 | 准入 / 汇合条件 |
|---|---|---|
| Obsidian 与正文权威 | Vault Markdown 继续作为笔记正文权威；Core-state Draft/Journal 的现状如实标注，先明确与 Inbox/`50-Journal` 的映射再谈同步。支持中文文件名、相对附件、YAML 属性、wiki links、嵌入及未知块的保留策略；脑图/画板源文件通过 Markdown 相对链接关联 | 用代表性合成笔记验证打开→编辑→保存→Obsidian 重开及外部修改→App 重读。验证并发版本冲突、附件引用和失败恢复；不能安全往返的内容只读或源码回退，不静默损坏 |
| BlockSuite 适配 | 对照上述样本检查现有试验成果；若采用，优先让它作为 Core Notes 接口之上的编辑视图。结构化快照只可作为有版本绑定、可失效的辅助表示，不能与 Markdown 各自独立修改、互相覆盖 | 如核心内容只能由 BlockSuite 专有结构保存，且不能满足 Markdown/Obsidian 无损要求，停止正式替换提案，提出范围取舍供用户确认。不能以“能导出 Markdown”证明双向兼容；正式选型/迁移须获用户体验批准 |
| 全局检索 | 先盘点复用现有 Knowledge、Notes、Task、Journal、Memory 和 Session 读取能力，设计统一查询/结果合同：来源类型、稳定引用、版本/哈希、标题、受限摘要、位置和可回源链接。保持各数据源权威独立，通过 Core 聚合，必要索引为可重建派生数据 | 先用标题/全文/属性/标签和范围过滤验证基线；逐源接入，不一次遍历所有库。仅索引获授权范围，Private 排除，撤权后及时失效；已建索引或缓存不授予读取权，返回结果与打开来源均重新验权 |
| AI 搜索与分析 | Hermes 调用 Core 受控检索，取得少量相关证据，按需回源后回答；知识正文作为低信任资料传递，不能升级为系统指令。自然记忆联想和用户显式全局搜索可复用检索适配，但触发、范围与预算分别控制 | 用同一批相关/无关/冲突/过期/撤权样本比较效果、时延和费用；答案需对应具体来源版本，证据不足说明缺口。不得让模型直接扫描全 Vault；分析结果默认是回答/候选，不自动写 Knowledge |
| 语义检索演进 | 先判断问题出在检索还是上下文传递，再基于代表查询评估关键词+向量/重排。若需要 embedding，沿用版本化来源引用，记录模型/切块版本及失效重建方式 | 数据出站和费用先明确；新依赖、服务或数据副本需论证，不默认新增数据库。索引陈旧、来源删除或权限变化时过滤并回源校验，不返回旧敏感正文 |

**工作包 5 的五步拆解与汇合（统一记录于 #46，不新建权威文档）：**

1. **复用与差距核对：** 定位归档试验的固定版本、源文件和已有证据，对照现有 Notes/附件接口及代表性 Markdown 样本列出缺口；不得要求用户重新寻找已保存材料，也不把试验通过当正式集成通过。此步只读准备可与 #287 并行。
2. **兼容方案与体验集中确认：** 给出可运行的既有预览、明确的支持矩阵与最小 diff/接线计划，确认普通正文 Markdown 权威、属性/未知语法保留、图形源文件及附件关联、外部修改冲突和回退。若 BlockSuite 特性必须以专有快照为权威，应说明损失并提出具体产品取舍；不能暗中另建正文 SoT。用户一次确认正式选型及非生产实施范围后，主 Agent 在该范围连续执行，不逐函数请示；准备不足时只补真实缺口，不做无限选型。
3. **Core 接线与持久闭环：** 复用 Notes/附件 API，完成创建/编辑/自动保存/失败保留/版本冲突/关闭重开；只补有证据的接口缺口，不顺手重写存储、Hermes、全局 UI 或调度系统。合成根里先跑通一条完整链路，再扩支持内容。
4. **Obsidian、搜索与 AI 兼容汇合：** 用中文路径、YAML、wiki links/嵌入、相对附件、未知块与脑图/画板代表样本验证受支持内容往返；不支持项只读/源码回退且原文不丢。保存后的正文/属性通过既有 Core 检索适配可查并回到同一来源版本；图形按支持矩阵提供文本投影或明确不可检索，不默认为已支持。AI 仅通过现有授权检索取证，合成接口测试不调用付费模型；此步只要求 Notes 数据合同可接入，不以全源搜索平台完成为前置。
5. **工程验收与候选交付：** 相关定向测试、独立 Review、授权范围内 Linux Chromium 保存/重开及必要视口旅程，普通 PR 按现行门禁处理。交付支持矩阵、可体验候选和回退说明；实际 Obsidian 双向同步、NAS 发布与最终用户验收分别记录并取得对应授权。正常开发问题包内解决，只有确实无法满足 Markdown 权威或新增数据/权限边界才升级 PMO。

**接续原则：** #287 交付后不再派发新的记忆预检来推迟编辑器；工作包 5 完成上述候选闭环后再进入工作包 6。全局检索合同可并行核对，但不将新向量库、完整 AI 搜索或所有图形格式兼容当作编辑器启动条件。

### ChatGPT 与 Codex 的任务发布要求

ChatGPT 先读本文件的快照、近期规划与唯一 NEXT，再按需读交付规划及对应正式规格；优先核查已有实现与 Hermes 扩展能力。ChatGPT 负责目标、验收及重要取舍，Codex 主 Agent 按现有授权自主拆解、实施、集成和接续工作包，普通 PR 审核按 Agent-Rules 执行。

每个长任务明确：用户能力目标、现有基础与实际缺口、可自主推进的范围、依赖/文件所有权、可观察的验收与失败条件、需要另行授权的动作，以及完成后的接续工作。普通调试和必要修复不逐项请示；重大规格冲突、信任/权限拓扑变化、不可逆操作或生产/真实数据/费用授权缺失才升级相应裁定。证据留在现有业务 Issue/PR，当前状态和下一步回写本文件，不新增权威文档或恢复人工 A/B 转发模式。

## 唯一 NEXT

**已完成的有限真实 Chat UAT（2026-11-04）：** 用户在正式 Web 新建会话并发送普通问题，获得真实回答，Run 完成且刷新后问答保留。该验收发生在 `d06e3f3b` 旧 UI 上；新版 UI 的工程浏览器 Gate 已 PASS，但人工视觉 UAT 为 `USER_WAIVED / NOT RUN`，不得记为 `USER_UAT_PASS`。#30 跨会话有限真实模型 UAT 于 2026-11-05 部分通过（6 Runs），细节与限制见下；Companion、冲突处理及其他未验收功能仍 NOT RUN。Promote/Writer/Weixin 保持关闭。

**阶段收口（工作包 3 / Issue #30）：** PMO 已于 2026-11-06 [正式裁定](https://github.com/zxwan829/SecondBrain/issues/30#issuecomment-6663061801)接受本轮为 `PARTIAL / LIMITED_REAL_MODEL_UAT`，不宣称完整 PASS 或用户验收。实际使用 6/10 次付费 Run：首次自然召回用了方框但遗漏蓝色，无关问题未受偏好干扰，纠正后新会话使用新标记，撤销后不再复述失效偏好。合成记忆有 create→correct→revoked 事件链，最终状态 revoked；逐 Run 注入上下文及因果归属 UNKNOWN，冲突处理 NOT RUN，实际 token usage、账户账单及费用 UNKNOWN。**本轮停止追加 Run，剩余 4 次不再执行，也不自动结转为其他任务授权。** 代码/状态 PR #285、#286 已合并；#30 保留尚未完全验收的项目缺口。

**唯一 NEXT（工作包 4：自然对话与日常记录）：** 用户已明确批准继续非生产开发，以 [Issue #287](https://github.com/zxwan829/SecondBrain/issues/287) 为本包唯一执行入口。Codex 主 Agent 依照 D077/D086 与现有 V1 规格，先核验并复用已有 Chat→Core Inbox 原文收录→独立确认后按日 Journal append，以及自然语言 Task 创建/查询/更新/完成的业务链路；优先修复重复确认、持久化回执、幂等重放、来源/授权隔离及刷新恢复的真实缺口。目标为合成环境的最小代码闭环、定向测试、独立 Review、合格普通 PR 合并与状态更新；当前状态 **已授权开工 / 实施及验收尚未完成**。**不授权**生产 NAS/容器/权限/真实 Vault 变更、付费模型 Run、Obsidian `50-Journal` 同步、Writer/Promote/Weixin 启用或 VNext/BlockSuite 正式集成。PR #277 Notes/Journal 生产合成 UAT 仍 `PARTIAL`、同 key replay `NOT RUN`。Promote/Writer/Weixin 保持关闭，VNext 保持 FROZEN. **本包之后优先接续工作包 5（#46 BlockSuite 编辑器）；现在可并行只读核对归档资产与兼容差距，正式实施按上文步骤 2 集中确认。此排程不打断 #287，也不直接启动冻结原型或整站改版。**

2026-11-04 定向集成证据：固定 Hermes `d923a5eb`（含已有 fail-closed 补丁），真实 AIAgent + API Run/dispatcher/Guard/审批路由，仅替换模型响应，3 passed（12.13s）。未批准时文件不存在；deny 后 Run completed 且文件不存在；once 后合成文件内容正确；Skills 路径以 `skills_write_gate` 拒绝且无文件。独立 Reviewer 确认本轮断言满足有限 UAT 门槛。测试是隔离执行链验证，生产未修改、无付费模型调用。复现脚本见 `web-app/hermes-agent/tests/real_agent_api_approval_probe.py`；详细记录见 Progress Log。

## 核心任务队列

以下是未完成事项索引，不按编号代表执行优先级；调度以“近期执行规划”和“唯一 NEXT”为准。

1. [#261 Knowledge 文件夹与标签筛选](https://github.com/zxwan829/SecondBrain/issues/261) — 仅隔离开发；候选分支的 CI 未通过，Chromium Gate 未运行，尚无 PR；不得合入或接触真实 Vault。
2. [#74 Inbox 请求范围隔离风险](https://github.com/zxwan829/SecondBrain/issues/74) — 范围隔离修复 PR #79 已合入，包含于当前生产 App revision `7272b7388d9453a4abe212e6aa8d528e7e0dcd82`；Linux 合成浏览器通过，未登录读取生产 Inbox；Issue 保持开放至用户验收。
3. [#75 M1 幂等重放与浏览器请求证据](https://github.com/zxwan829/SecondBrain/issues/75) — 历史生产证据缺口尚未重新核验；任何生产复测需单独授权。
4. [#30 跨会话记忆召回故障](https://github.com/zxwan829/SecondBrain/issues/30) — 合成真实模型 UAT 部分通过；初始偏好自然召回遗漏颜色、冲突场景未测，详见本轮记录。
5. [#78 Review→Promote 安全闭环](https://github.com/zxwan829/SecondBrain/issues/78) — 仅记录剩余设计/隔离实现；生产 Writer、Promote 与真实 Knowledge 写入需单独授权。
6. [#46 Markdown 可视化编辑器](https://github.com/zxwan829/SecondBrain/issues/46) — 工作包 5，紧接 #287；复用 BlockSuite 归档试验，先并行核对兼容差距，按本文件五步推进与确认，不重做 PoC。
7. [#260 VNext 工作台产品基线与隔离原型](https://github.com/zxwan829/SecondBrain/issues/260) — 产品讨论/原型冻结入口；不表示批准整站替换或生产切换。

## 本轮资产处置

- **保留在 main：** 已合并成果；#55 的标签/类型能力已由 PR #242 merge commit `c3c2c6d81c87c14b2450890fa8e68b7262d58129` 交付。
- **远端冻结：** VNext commit `45bf5f7d...` 保存在 `codex/vnext-workbench-20261103`，无 PR、无合并、无用户验收。旧集成快照已原 SHA 归档到 `codex/frozen/a-b-real-http-issue96-20261020` (`9ddd8acb...`)、`codex/frozen/issue83-integration-candidate-20261018` (`7380ab22...`) 和 `codex/frozen/issue86-gate2-retest-20261019` (`19fe5f97...`)；均无 PR、未合并。Web 合成集成另保存在既有分支 `codex/a-web-synthetic-integration-20261020` (`098f4bfa...`)。#261 与 Writer/D086/D090 候选按各 Issue/PR 原 SHA 保留，不作 main 交付。
- **本地归档且不纳入主线：** Puck、BlockSuite 编辑器试验及恢复材料保存在独立目录/bundle；它们不进入 SecondBrain main。编辑器比较 Issue #255–#259 关闭为未计划/重复项，未来若重新选择以 #46/#260 为唯一入口。未删除这些本地材料。
- **已清理弃用远端引用：** PR #213/#204/#161/#9/#8 的 head SHA 与 GitHub PR 记录逐一核对后，删除对应的 5 个远端分支引用；PR 均为 closed/not merged，审查 diff、提交 SHA 与历史仍留在 GitHub。未删除任何冻结候选分支。
- **正式 Clone 未跟踪内容：** `MINDMAP-DRAG-INVESTIGATION.md`、`docs/SecondBrain_Codex_UX_References_20261026/`、`typescript`、`{{.Destination}}` 原样保留；不在本次提交中。

## 主要风险与验收边界

- GitHub main、生产代码和用户验收分开记录：PR #277 固定源码 SHA `7272b738` 已部署并通过运行门禁；生产合成 Notes/Journal UAT 为 `PARTIAL`（Journal 同 key replay NOT RUN），真实业务数据与用户 UAT 仍 `NOT RUN`。本轮另发生可访问性快照显示既有业务摘要/列表标题的读取范围偏差，详情见本阶段状态和环境记录。#269/#274 工程浏览器 Gate PASS，用户明确放弃旧版 Chat UI 人工视觉验收，状态 `USER_WAIVED / NOT RUN`。PR #279 与本轮状态记录只更新文档，不改变生产 App image。
- #261 远端隔离分支的 CI 失败（Actions #41334785303 有 4 项旧/待核断言失败）；尚无 PR，Chromium Gate 未运行，不能合并。
- #74 的安全范围修复已合并并部署，剩余用户验收未完成；#30 首次自然召回仅部分遵循且冲突场景未测；#78 生产审批边界仍未解除。
- D084 历史浏览器业务验收仍无新证据（旧宽范围 Issue #44 已按未计划关闭，不是验收完成）。
- 新版 Chat UI 用户视觉验收、真实 Vault/Private 检查、OS 权限和安全架构变更均未执行；Chat UI 人工验收 `USER_WAIVED / NOT RUN`。#269 部署于 2026-11-04 完成，#274 App-only 更新于 2026-11-05 完成。Notes/Journal 隔离测试不构成生产写入或真实业务数据验收。

## 导航

- V1 范围与业务契约：[Web App V1](business-specs/SecondBrain-Web-App-V1-Business-Spec.md)、[Universal Capture](business-specs/Universal-Capture-Business-Spec.md)
- V1 全量分解与验收：[V1-Delivery-Plan.md](V1-Delivery-Plan.md)；当前工作顺序与唯一 NEXT 以本文件为准
- 稳定架构：`Architecture.md`；正式取舍：`Decision-Log.md`
- 最近已核验运行证据：`Environment-Baseline.md`；历史证据：`Progress-Log.md`
- 执行与安全边界：`Agent-Rules.md`、仓库根目录 `AGENTS.md`
