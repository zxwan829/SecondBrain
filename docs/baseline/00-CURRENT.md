---
created: 2026-09-30
updated: 2026-11-04
status: current
source: GitHub SecondBrain Monorepo
---
# SecondBrain — 当前项目状态

> 本文件是项目唯一进度入口。它记录可核验的主线、运行快照、验收状态、当前下一步和少量核心任务；历史过程见 `Progress-Log.md`，稳定架构见 `Architecture.md`，批准的决定见 `Decision-Log.md`，最后一次运行快照见 `Environment-Baseline.md`。未实时复核的运行状态一律标为 UNKNOWN。

## 当前快照

- **审计基准 main：** `d06e3f3bde2cf8ee260992644c2ae5d67aeef362`（2026-11-04；GitHub `main`，PR #269 merge commit）。
- **总体：** V1 尚未完成。GitHub main 的代码/文档状态不代表生产部署、真实数据验证或用户验收。
- **最近已核验生产快照：** 2026-11-04 只读核验确认 App 仍运行 revision `ce247d0c2f014c67f407c7b8721022da6afe2753`、Image ID `sha256:e201c93c7f19ec1ac15f742659ce023a0f12228fd846035090e42f6e69d3cec5`、healthy；Compose SHA-256 为 `0aedb4b104870ddc5ce23a2f1adde10b84b51bf06f7e35d3377356bcc5a84708`。main `d06e3f3b` 相对生产仅有 Chat 前端 `App.tsx`/CSS 运行代码差异，其余差异是合成测试与文档。Hermes 未变更。详情见 `Environment-Baseline.md`。
- **生产安全闸门（2026-11-03 实测）：** `SB_PROMOTE_ENABLED=false`、App Knowledge 挂载只读、Private 未挂载；App/Core 的 Weixin 开关环境变量未设置为开启；Hermes 写安全根仅为 3 个获准捕获目录。具体挂载与值见 `Environment-Baseline.md`。
- **开发阶段：** V1 首轮真实用户体验准备。新功能不因准备验收而自动启动；仅处理影响五个体验场景的 P0/P1 阻断。
- **本阶段状态：** `PARTIAL / LIMITED_CHAT_UAT_PASS / CHAT_UI_DEPLOYMENT_READY_FOR_APPROVAL`。用户已完成基础真实模型 Chat 回复及刷新恢复验收；PR #269 的 Chat UI 修改已合并，Linux 三视口浏览器 Gate PASS。2026-11-04 对精确 main SHA 构建 App 候选并完成隔离启动/健康检查，生产尚未部署该 UI，用户对新版 UI 验收为 NOT RUN。用户首轮其他页面与 Task、Capture→Inbox→Review 有限验收保持原记录；跨会话记忆及其他 V1 业务仍未验收。

## 能力状态

原 V1 MUST/SHOULD 与 D077 Companion 产品合同继续以[Web App V1 业务规格](business-specs/SecondBrain-Web-App-V1-Business-Spec.md)、[Universal Capture 业务规格](business-specs/Universal-Capture-Business-Spec.md)、`Decision-Log.md` D077 为准。本矩阵只汇总 main、最近有日期的生产证据和用户验收，不缩减正式范围。D086 合成来源授权/Consent 候选不等于微信渠道；微信输入渠道按 P4-2 / D087 单独记录。

| 模块 | main 代码 / 集成 | 最近已核验生产（2026-11-03） | 用户验收 / 阻断 |
|---|---|---|---|
| App Shell / 登录与路由 | main 有 Shell、鉴权与路由实现 | HTTPS `/health`、`/`、`/login`、`/notes` 为 200；匿名 session、Tasks、Capture summary、Knowledge search、Promote API 均为 401；用户已在 2026-11-04 登录并完成部分真实页面操作 | 本轮有限登录旅程通过；未覆盖所有模块/路由，完整跨页体验仍待验收 |
| Home | main 有 Home 页面与部分聚合 | HTTPS `/` 返回 200；未认证浏览器不执行 App 内容聚合 | 动态 Home 完整聚合未验收；首次从 `/` 登录会读取聚合数据，体验时可直接打开目标模块 |
| Chat / Hermes / D077 | main 包含 PR #269 Chat UI；D077 Companion 仅部分实现 | 用户已完成有限真实文本对话、回复及刷新恢复；当前生产 App 仍为 `ce247d0c`，#269 候选尚未部署 | 新版 UI 用户验收 NOT RUN；跨会话记忆、学习/纠正和 Companion 未验收 |
| Today / Calendar / Journal / Task | main 有页面/API 的部分实现；显式 Task API 与持久化实现存在 | 用户于 2026-11-04 实测 Task 创建、完成及恢复；合成前端/Core 回归通过 | 仅上述 Task 旅程 PASS；完整 Calendar 与 Journal 追加闭环未验收 |
| Capture：文本 / Markdown / TXT | main 有 Raw→Review 路径及文本入口；`/inbox` 使用显式 Capture/Notes scope | 用户已用合成内容验证文本 Capture→Inbox→Review 保存、回读、关联及刷新持久化；Linux Chromium Inbox capture/retry/source-protection 三视口通过；生产 App 仍为 `ce247d0c`，新版 Chat UI 未部署 | 仅限上述文本 Capture 旅程；附件、URL 和 Promote 未验收/不在本次操作范围 |
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

## 2026-11-04 首轮用户 UAT 与 Chat 安全核验收口

- 用户登录实测：Task 创建/完成/恢复、Capture 文本原文保存→Inbox→Review 持久化、Knowledge 搜索/阅读、Journal 2026-10-18 历史正文、Chat 历史会话读取均有页面证据；本项只代表相应有限旅程，不代表整个 V1 功能通过。
- Notes 历史版本可预览但未执行恢复；回收站界面可打开，Trash 根未配置；Projects 与 Daily Brief 缺可信数据源/配置；笔记新建保存和日记追加写入未运行。旧 V1 UI 问题统一追踪于 #260；VNext 保持冻结，尚未启动开发。
- **Chat 实际核验纠错（2026-11-04）：** 此前把模块级字符串常量 `PRE_TOOL_CALL_HOOK_UNAVAILABLE` 错误地要求出现在 `_pre_tool_block` 函数体内，误判生产 Hermes 镜像缺失 fail-closed 补丁。随后由 Codex 直接核验生产容器，确认执行文件 SHA-256 为 `b600d5bf028e5500c04b8a899f49882769e52a110fe1b633d624454a94d92c40`，与固定源码应用补丁后的完整执行文件一致，且异常分支引用阻断常量。**正式撤回缺补丁结论，不因该误报重建生产 Hermes；本次未部署或回滚。**
- **#269 合并及候选：** PR [#269](https://github.com/zxwan829/SecondBrain/pull/269) 于 2026-11-04 合并，merge commit `d06e3f3bde2cf8ee260992644c2ae5d67aeef362`；三视口 Linux Chromium Gate [Actions #41785664124](https://github.com/zxwan829/SecondBrain/actions/runs/41785664124) PASS。固定 SHA 候选构建 [Actions #41788688422](https://github.com/zxwan829/SecondBrain/actions/runs/41788688422) SUCCESS；App image ID `sha256:250437fc8b57642770347d6de73d86e791ffd8aaebdaba399170bc5018fe2270`，平台 `linux/amd64`，源码 revision 标签与 d06 完全一致。GitHub artifact ID `13301449533` / digest `sha256:e6040f9c7262b8477169ef0e5fd8a1a1e7959d1b2857e423dd33c0cae7a89b9c`；App-only 包 SHA-256 `49905f26e9fc7780a1a58be693f7d1558b989421291ffcfa417a3856674e684a`。隔离容器 startup、`/health`、`/notes` 与 Promote OFF 检查通过。未部署生产。
- **Chat 安全与基础 UAT：** 此前的插件活动 Hook/策略探针、真实 Hermes AIAgent API Run 审批/拒绝/Skills 集成测试、App→Hermes health 与真实模型普通文本回复/刷新恢复均已有通过记录；此前“缺少 fail-closed 补丁”判断已正式撤回。上述有限证据不代表跨会话记忆、完整 Companion 或所有工具场景验收。

## 唯一 NEXT

**已完成的有限真实 Chat UAT（2026-11-04）：** 用户在正式 Web 新建会话并发送普通问题，获得真实回答，Run 完成且刷新后问答保留。此结果适用于当前生产旧 UI；不代表 #269 新 UI 已验收。#30 跨会话记忆、Companion、Notes/Journal 写入及其他未验收功能仍 NOT RUN。Promote/Writer/Weixin 保持关闭。

**唯一 NEXT（#269 App-only 生产发布与新版 UI 验收）：** 目标固定为 `d06e3f3bde2cf8ee260992644c2ae5d67aeef362`。候选镜像、隔离启动测试、SHA 校验、Compose 影响范围和回滚流程已准备；生产仍运行 `ce247d0c`，#269 新 UI 的生产用户验收为 NOT RUN。需要用户明确批准仅将候选 App 镜像导入 NAS、保存当前 Compose 备份并只重建 `secondbrain-app`；不触碰 Hermes、挂载、权限、Secret 或业务数据。部署核验通过后，由用户在桌面 Web 验收新版默认折叠/展开、长标题、输入增长、发送/停止/完成及刷新恢复。该项完成后再领取下一项未通过的 V1 核心业务 UAT（优先评估 Notes 保存与 Journal 追加写入），不解冻 VNext。

2026-11-04 定向集成证据：固定 Hermes `d923a5eb`（含已有 fail-closed 补丁），真实 AIAgent + API Run/dispatcher/Guard/审批路由，仅替换模型响应，3 passed（12.13s）。未批准时文件不存在；deny 后 Run completed 且文件不存在；once 后合成文件内容正确；Skills 路径以 `skills_write_gate` 拒绝且无文件。独立 Reviewer 确认本轮断言满足有限 UAT 门槛。测试是隔离执行链验证，生产未修改、无付费模型调用。复现脚本见 `web-app/hermes-agent/tests/real_agent_api_approval_probe.py`；详细记录见 Progress Log。

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
