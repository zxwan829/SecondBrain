---
created: 2026-09-30
updated: 2026-11-04
status: current
source: GitHub SecondBrain Monorepo
---
# SecondBrain — 当前项目状态

> 本文件是项目唯一进度入口。它记录可核验的主线、运行快照、验收状态、当前下一步和少量核心任务；历史过程见 `Progress-Log.md`，稳定架构见 `Architecture.md`，批准的决定见 `Decision-Log.md`，最后一次运行快照见 `Environment-Baseline.md`。未实时复核的运行状态一律标为 UNKNOWN。

## 当前快照

- **审计基准 main：** `9c37cea6babd933d488f2adab546e4b761860abf`（2026-11-03；GitHub `main`）。
- **总体：** V1 尚未完成。GitHub main 的代码/文档状态不代表生产部署、真实数据验证或用户验收。
- **最近已核验生产快照：** 2026-11-03 只读核验确认 App revision 为 `ce247d0c2f014c67f407c7b8721022da6afe2753`；Hermes Image ID 与 2026-10-24 已记录镜像一致（Hermes 容器无 SecondBrain revision label）。GitHub main `9c37cea6` 与 App 发布 SHA 的差异只有 5 个文档提交、无应用源码差异。详情见 `Environment-Baseline.md`。
- **生产安全闸门（2026-11-03 实测）：** `SB_PROMOTE_ENABLED=false`、App Knowledge 挂载只读、Private 未挂载；App/Core 的 Weixin 开关环境变量未设置为开启；Hermes 写安全根仅为 3 个获准捕获目录。具体挂载与值见 `Environment-Baseline.md`。
- **开发阶段：** V1 首轮真实用户体验准备。新功能不因准备验收而自动启动；仅处理影响五个体验场景的 P0/P1 阻断。
- **本阶段状态：** `PARTIAL / CHAT_BLOCKED_ON_RUNTIME_SECURITY`。用户已完成多数页面的首轮生产 UAT，并以明确合成内容验证 Task 和 Capture→Inbox→Review 写入/回读；真实模型 Chat 尚未调用。生产 Hermes 的执行文件经重新核验与固定源码应用 fail-closed 补丁后的文件 SHA-256 一致，先前“缺少补丁”判断已撤回；Guard 活动注册、File/Skills 审批及 Chat 基础链路仍待运行核验。既有健康检查不等于真实 Chat 验收。

## 能力状态

原 V1 MUST/SHOULD 与 D077 Companion 产品合同继续以[Web App V1 业务规格](business-specs/SecondBrain-Web-App-V1-Business-Spec.md)、[Universal Capture 业务规格](business-specs/Universal-Capture-Business-Spec.md)、`Decision-Log.md` D077 为准。本矩阵只汇总 main、最近有日期的生产证据和用户验收，不缩减正式范围。D086 合成来源授权/Consent 候选不等于微信渠道；微信输入渠道按 P4-2 / D087 单独记录。

| 模块 | main 代码 / 集成 | 最近已核验生产（2026-11-03） | 用户验收 / 阻断 |
|---|---|---|---|
| App Shell / 登录与路由 | main 有 Shell、鉴权与路由实现 | HTTPS `/health`、`/`、`/login`、`/notes` 为 200；匿名 session、Tasks、Capture summary、Knowledge search、Promote API 均为 401 | 未使用真实登录；用户跨页操作待验收 |
| Home | main 有 Home 页面与部分聚合 | HTTPS `/` 返回 200；未认证浏览器不执行 App 内容聚合 | 动态 Home 完整聚合未验收；首次从 `/` 登录会读取聚合数据，体验时可直接打开目标模块 |
| Chat / Hermes / D077 | main 有 Chat-Hermes 接口；D077 Companion 仅部分实现 | Hermes loopback 与 App→Hermes `/health` 均为 200；本轮未登录或提交 Chat/Run | 真实模型调用/费用及个人会话读取须由用户明确接受；跨会话记忆、学习/纠正和 Companion 未验收 |
| Today / Calendar / Journal / Task | main 有页面/API 的部分实现；显式 Task API 与持久化实现存在 | Task 前端/Core 合成回归通过；未对生产 Tasks 读写 | 生产创建/完成/重开待用户操作；Journal 闭环及完整日历未验收 |
| Capture：文本 / Markdown / TXT | main 有 Raw→Review 路径及文本入口；`/inbox` 使用显式 Capture/Notes scope | 当前镜像与 main 源码一致；Inbox scope 前端测试通过，Linux Chromium 的 Chat Inbox capture/retry/source-protection 合成旅程三视口通过；无生产 Capture | 真实文本 Capture 和 Review 内容待用户验收；不要执行 Promote |
| Capture：URL / Web | main 有抓取与 Review 路径 | 本轮未提交 URL 或读取 Raw/Review 数据 | 多站点、失败恢复和用户流程仍未完整验收 |
| Capture：PDF / 图片 / 音频 | main 有 PDF/OCR 与图片处理的部分实现；音频处理未闭环 | 本次未处理生产附件；生产质量 UNKNOWN | 合成 OCR 不等于真实文件验收；STT 后端/真实样本仍阻断 |
| 微信输入渠道（P4-2 / D087） | main 有渠道相关来源；D086 合成 Authority/Consent PR 不等同微信渠道实现 | 插件文件存在但 `not enabled`，Core 微信开关为 false；未扫码/收发消息 | **未接入、未用户验收**；真实渠道另行授权 |
| Review / Approval | main 有 Review 与受控审批部分实现 | 匿名 Promote API 为 401；本次未登录查看或执行审批 | 用户登录后可检查授权范围内 Review；端到端 Approval→Knowledge 未完成，生产 Promote 关闭 |
| Knowledge / Notes / 标签 | main 有只读检索、Notes 与词库；PR #242 已合入（#55 完成） | `/notes` 200、匿名 Notes API 与 Knowledge search 均为 401；未读取 Vault/正文 | 用户对已授权 Knowledge 的搜索/打开待验收；真实笔记写入不在本轮范围 |
| Projects | main 有读接口与页面的部分实现 | 未核验项目数据旅程 | 真实来源完整性和用户验收 UNKNOWN |
| Daily Brief | main 有读接口与页面的部分实现 | 未执行简报数据或模型旅程 | 真实生成、数据来源及用户验收 UNKNOWN |
| Activity / Agent Health | main 有部分 Activity 与健康状态实现；来源覆盖不完整 | 未做登录态或业务数据核验 | 来源范围、状态准确性和用户验收未完成 |
| 响应式 / 多端 / Obsidian 同步 | main 有响应式样式 | Linux Chromium 合成旅程在 1440×1000、820×1180、390×844 通过；精确 768px 未运行；同步未复测 | 真机/当前用户浏览器体验与 Mac↔NAS 双向同步未验收 |
| Security / Writer / Promote / Private | main 有 fail-closed 与受控写入相关代码；D090 Writer 候选未合入 | Promote=false、App Knowledge RO、Private 未挂载；Hermes safe root 三个捕获目录；`SB_WEIXIN_INBOX_ENABLED` 未设置 | 跨进程/OS 隔离及正式 Promote 未验收；不在本轮开启 |

## 2026-11-04 首轮用户 UAT 与安全阻断补记

- 用户登录实测：Task 创建/完成/恢复、Capture 文本原文保存→Inbox→Review 持久化、Knowledge 搜索/阅读、Journal 2026-10-18 历史正文、Chat 历史会话读取均有页面证据；本项只代表相应有限旅程，不代表整个 V1 功能通过。
- Notes 历史版本可预览但未执行恢复；回收站界面可打开，Trash 根未配置；Projects 与 Daily Brief 缺可信数据源/配置；笔记新建保存和日记追加写入未运行；旧 V1 UI 可用性问题统一留给 #260 VNext 讨论，不阻断上述核心安全收口。
- **Chat 实际核验纠错（2026-11-04）：** 此前把模块级字符串常量 `PRE_TOOL_CALL_HOOK_UNAVAILABLE` 错误地要求出现在 `_pre_tool_block` 函数体内，误判生产 Hermes 镜像缺失 fail-closed 补丁。随后由 Codex 直接核验生产容器，确认执行文件 SHA-256 为 `b600d5bf028e5500c04b8a899f49882769e52a110fe1b633d624454a94d92c40`，与固定源码应用补丁后的完整执行文件一致，且异常分支引用阻断常量。**正式撤回缺补丁结论，不因该误报重建生产 Hermes；本次未部署或回滚。**
- **CI 实测：** PR #265 / Actions [41759672367](https://github.com/zxwan829/SecondBrain/actions/runs/41759672367) 已成功构建候选镜像并上传 artifact；其构建流程仍是候选/备用资产，不是当前生产必须替换的证据。artifact 独立完整性校验与最终流程复审尚未完成，PR 未合并。fail-closed 定向测试 6/6 通过；不把其结果扩展为整个 Guard 和审批运行时通过。
- **当前真实 Chat 阻断：** 生产 Guard 活动 Hook 注册、File 写入审批实际执行路径、Skills 保护和 Chat 基础 SSE 链路仍需最小定向运行核验；API Terminal 配置为禁用。未调用付费模型，真实 Chat 用户 UAT 仍 NOT RUN。允许在既有授权内仅作无敏感数据、无付费调用的精确核验；失败才针对证据修复，不允许无故重建容器。

## 唯一 NEXT

**唯一工程 NEXT：** Codex 在现有生产 Hermes 上完成最小只读/合成运行核验：确认 D078 Guard 活动加载与 Hook 注册、File 写审批强制路径、Skills 保护、Terminal 禁用、原有挂载权限，以及 App→Hermes Chat/SSE 基础链路。先复用已确认补丁的现网镜像，不再为补丁重建或申请部署。若证据显示具体缺陷，仅针对该缺陷设计最小修复；任何新增生产变更须与既有具体授权范围一致。PR #265 可以作为备用构建基础设施独立收口，不阻断现网核验。**用户验收 NEXT：** 通过运行门禁后，由用户本人使用约 ¥5 测试预算验证新 Chat 会话、模型回复和刷新恢复；该预算非供应商硬上限。Notes 新建保存和 Journal 追加仍 NOT RUN。Promote/Writer/Weixin 保持关闭。

## 核心任务队列

1. [#261 Knowledge 文件夹与标签筛选](https://github.com/zxwan829/SecondBrain/issues/261) — 仅隔离开发；候选分支的 CI 未通过，Chromium Gate 未运行，尚无 PR；不得合入或接触真实 Vault。
2. [#74 Inbox 请求范围隔离风险](https://github.com/zxwan829/SecondBrain/issues/74) — 范围隔离修复 PR #79 已合入且包含在当前生产 `ce247d0`；本轮 Linux 合成浏览器通过，未登录读取生产 Inbox；Issue 保持开放至用户验收。
3. [#75 M1 幂等重放与浏览器请求证据](https://github.com/zxwan829/SecondBrain/issues/75) — 历史生产证据缺口尚未重新核验；任何生产复测需单独授权。
4. [#30 跨会话记忆召回故障](https://github.com/zxwan829/SecondBrain/issues/30) — 根因/真实链路仍未确认；任何模型或生产复测按单独授权执行。
5. [#78 Review→Promote 安全闭环](https://github.com/zxwan829/SecondBrain/issues/78) — 仅记录剩余设计/隔离实现；生产 Writer、Promote 与真实 Knowledge 写入需单独授权。
6. [#46 Markdown 可视化编辑器](https://github.com/zxwan829/SecondBrain/issues/46) — 保留既有产品目标，先明确低风险、可回滚的范围与用户验收。
7. [#260 VNext 工作台产品基线与隔离原型](https://github.com/zxwan829/SecondBrain/issues/260) — 产品讨论/原型冻结入口；不表示批准整站替换或生产切换。

## 本轮资产处置

- **保留在 main：** 已合并成果；#55 的标签/类型能力已由 PR #242 merge commit `c3c2c6d81c87c14b2450890fa8e68b7262d58129` 交付。
- **远端冻结：** VNext commit `45bf5f7d...` 保存在 `codex/vnext-workbench-20261103`，无 PR、无合并、无用户验收。旧集成快照已原 SHA 归档到 `codex/frozen/a-b-real-http-issue96-20261020` (`9ddd8acb...`)、`codex/frozen/issue83-integration-candidate-20261018` (`7380ab22...`) 和 `codex/frozen/issue86-gate2-retest-20261019` (`19fe5f97...`)；均无 PR、未合并。Web 合成集成另保存在既有分支 `codex/a-web-synthetic-integration-20261020` (`098f4bfa...`)。#261 与 Writer/D086/D090 候选按各 Issue/PR 原 SHA 保留，不作 main 交付。
- **本地归档且不纳入主线：** Puck、BlockSuite 编辑器试验及恢复材料保存在独立目录/bundle；它们不进入 SecondBrain main。编辑器比较 Issue #255–#259 关闭为未计划/重复项，未来若重新选择以 #46/#260 为唯一入口。未删除这些本地材料。
- **已清理弃用远端引用：** PR #213/#204/#161/#9/#8 的 head SHA 与 GitHub PR 记录逐一核对后，删除对应的 5 个远端分支引用；PR 均为 closed/not merged，审查 diff、提交 SHA 与历史仍留在 GitHub。未删除任何冻结候选分支。
- **正式 Clone 未跟踪内容：** `MINDMAP-DRAG-INVESTIGATION.md`、`docs/SecondBrain_Codex_UX_References_20261026/`、`typescript`、`{{.Destination}}` 原样保留；不在本次提交中。

## 主要风险与验收边界

- GitHub main、生产代码和用户验收分开记录：当前 main 比生产源 SHA `ce247d0` 仅领先 5 个文档提交、无源码差异；线上健康与安全配置已于 2026-11-03 只读复核，用户流程仍未验收。
- #261 远端隔离分支的 CI 失败（Actions #41334785303 有 4 项旧/待核断言失败）；尚无 PR，Chromium Gate 未运行，不能合并。
- #74 的安全范围修复已合并并部署，剩余用户验收未完成；#30 真实模型记忆故障和 #78 生产审批边界仍未解除。
- D084 历史浏览器业务验收仍无新证据（旧宽范围 Issue #44 已按未计划关闭，不是验收完成）。
- 用户浏览器验收、真实 Vault/Private 检查、生产部署、OS 权限和安全架构变更均未在本轮执行。

## 导航

- V1 范围与业务契约：[Web App V1](business-specs/SecondBrain-Web-App-V1-Business-Spec.md)、[Universal Capture](business-specs/Universal-Capture-Business-Spec.md)
- 稳定架构：`Architecture.md`；正式取舍：`Decision-Log.md`
- 最近已核验运行证据：`Environment-Baseline.md`；历史证据：`Progress-Log.md`
- 执行与安全边界：`Agent-Rules.md`、仓库根目录 `AGENTS.md`
