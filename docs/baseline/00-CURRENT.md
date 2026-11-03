---
created: 2026-09-30
updated: 2026-11-03
status: current
source: GitHub SecondBrain Monorepo
---
# SecondBrain — 当前项目状态

> 本文件是项目唯一进度入口。它记录可核验的主线、运行快照、验收状态、当前下一步和少量核心任务；历史过程见 `Progress-Log.md`，稳定架构见 `Architecture.md`，批准的决定见 `Decision-Log.md`，最后一次运行快照见 `Environment-Baseline.md`。未实时复核的运行状态一律标为 UNKNOWN。

## 当前快照

- **审计基准 main：** `54a94d5c2b00c809604f25721580d45bcf8483a0`（2026-11-03 本轮盘点时的 GitHub `main`）。合并本状态 PR 后，以 GitHub `main` 实际 HEAD 为准。
- **总体：** V1 尚未完成。GitHub main 的代码/文档状态不代表生产部署、真实数据验证或用户验收。
- **最近已核验生产快照：** `Environment-Baseline.md` 记录的 2026-10-24 App-only 快照，源代码 `ce247d0c2f014c67f407c7b8721022da6afe2753`。本轮未访问 NAS；该日期之后的生产状态 **UNKNOWN**。
- **生产安全闸门（仅截至 2026-10-24 的核验值）：** `SB_PROMOTE_ENABLED=false`、Knowledge RO、Private 未挂载；2026-11-03 当前值 **UNKNOWN**，本轮未复测，不得从历史快照推断为当前运行事实。
- **开发阶段：** 本次 GitHub 状态收口完成前暂停新功能开发。未合入 main 的 PR、隔离分支和原型不算交付。

## 能力状态

原 V1 MUST/SHOULD 与 D077 Companion 产品合同继续以[Web App V1 业务规格](business-specs/SecondBrain-Web-App-V1-Business-Spec.md)、[Universal Capture 业务规格](business-specs/Universal-Capture-Business-Spec.md)、`Decision-Log.md` D077 为准。本矩阵只汇总 main、最近有日期的生产证据和用户验收，不缩减正式范围。D086 合成来源授权/Consent 候选不等于微信渠道；微信输入渠道按 P4-2 / D087 单独记录。

| 模块 | main 代码 / 集成 | 最近已核验生产（2026-10-24） | 用户验收 / 阻断 |
|---|---|---|---|
| App Shell / 登录与路由 | main 有 Shell、鉴权与路由实现 | `/health`、`/`、`/notes`、`/login` 为 200；匿名 Notes API 为 401 | 未登录执行本轮用户流程；完整跨页验收未完成 |
| Home | main 有 Home 页面与部分聚合 | `/` 返回 200；未验证卡片是否完整反映真实模块数据 | 动态 Home 的完整聚合验收未完成 |
| Chat / Hermes / D077 | main 有 Chat-Hermes 接口；D077 Companion 仅部分实现 | Hermes `/health` 与 App→Hermes health 为 200；未做登录 Chat/Run | 跨会话记忆、学习/纠正和 Companion 验收未完成 |
| Today / Calendar / Journal / Task | main 有页面/API 的部分实现；D077 Journal/Todo 闭环仍未完成 | 未执行登录态读写或业务旅程 | 显式 Journal/Todo 操作与完整日历验收未完成 |
| Capture：文本 / Markdown / TXT | main 有 Raw→Review 路径及文本入口 | 镜像源包含代码；该快照仅做健康/路由检查，无真实 Capture | 历史 M1 有限验收不等于当前完整 V1 验收；本轮未复验 |
| Capture：URL / Web | main 有抓取与 Review 路径 | 本次未提交 URL 或验证 Raw/Review 产物 | 多站点、失败恢复和用户流程仍未完整验收 |
| Capture：PDF / 图片 / 音频 | main 有 PDF/OCR 与图片处理的部分实现；音频处理未闭环 | 本次未处理任何附件；生产质量 UNKNOWN | 历史合成 OCR 不等于真实文件验收；STT 后端/真实样本仍阻断 |
| 微信输入渠道（P4-2 / D087） | main 有渠道相关来源；D086 合成 Authority/Consent PR 不等同微信渠道实现 | 插件文件存在但 `not enabled`，Core 微信开关为 false；未扫码/收发消息 | **未接入、未用户验收**；真实渠道另行授权 |
| Review / Approval | main 有 Review 与受控审批部分实现 | 本次未登录查看 Review 或执行审批 | 端到端 Review→Approval→Knowledge 仍未完成；Promote 生产启用受限 |
| Knowledge / Notes / 标签 | main 有只读检索、Notes 与词库；PR #242 已合入（#55 完成） | `/notes` 返回 200、匿名 Notes API 返回 401；未登录读写/访问 Vault | 历史有限 UI 验收不覆盖当前完整安全编辑；真实 Vault 验收未做 |
| Projects | main 有读接口与页面的部分实现 | 未核验项目数据旅程 | 真实来源完整性和用户验收 UNKNOWN |
| Daily Brief | main 有读接口与页面的部分实现 | 未执行简报数据或模型旅程 | 真实生成、数据来源及用户验收 UNKNOWN |
| Activity / Agent Health | main 有部分 Activity 与健康状态实现；来源覆盖不完整 | 未做登录态或业务数据核验 | 来源范围、状态准确性和用户验收未完成 |
| 响应式 / 多端 / Obsidian 同步 | main 有响应式样式；历史浏览器测试仅适用于对应固定 SHA | 2026-10-24 快照未做本轮设备交互；同步未复测 | 当前 main 的手机/平板体验与 Mac↔NAS 双向同步未验收 |
| Security / Writer / Promote / Private | main 有 fail-closed 与受控写入相关代码；D090 Writer 候选未合入 | 最近快照值：Promote=false、Knowledge RO、Private 未挂载（仅截至 10-24） | 当前运行配置 UNKNOWN；跨进程/OS 隔离及正式 Promote 未验收，需单独授权 |

## 唯一 NEXT

收口完成后，在分别取得只读运行核验及真实业务操作所需授权的前提下，核实 2026-10-24 之后的实际运行版本，按已批准范围进行现有 V1 核心使用验收，并记录通过项与阻断。只读环境核验不授权生产修改；用户登录、真实数据读写、真实渠道或模型调用仍须与操作相匹配的单独授权。

## 核心任务队列

1. [#261 Knowledge 文件夹与标签筛选](https://github.com/zxwan829/SecondBrain/issues/261) — 仅隔离开发；候选分支的 CI 未通过，Chromium Gate 未运行，尚无 PR；不得合入或接触真实 Vault。
2. [#74 Inbox 请求范围隔离风险](https://github.com/zxwan829/SecondBrain/issues/74) — 已知安全/范围风险；核实当前 main 与受控合成测试后再提出方案，生产变更需单独授权。
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

- GitHub main、最新生产代码和用户实际浏览器验收是三个独立状态；目前 main 后生产版本与本轮真实运行情况 UNKNOWN。
- #261 远端隔离分支的 CI 失败（Actions #41334785303 有 4 项旧/待核断言失败）；尚无 PR，Chromium Gate 未运行，不能合并。
- #74、#30、#78 的风险或授权边界没有因历史测试、PR 关闭或文档更新而解除。
- D084 历史浏览器业务验收仍无新证据（旧宽范围 Issue #44 已按未计划关闭，不是验收完成）。
- 用户浏览器验收、真实 Vault/Private 检查、生产部署、OS 权限和安全架构变更均未在本轮执行。

## 导航

- V1 范围与业务契约：[Web App V1](business-specs/SecondBrain-Web-App-V1-Business-Spec.md)、[Universal Capture](business-specs/Universal-Capture-Business-Spec.md)
- 稳定架构：`Architecture.md`；正式取舍：`Decision-Log.md`
- 最近已核验运行证据：`Environment-Baseline.md`；历史证据：`Progress-Log.md`
- 执行与安全边界：`Agent-Rules.md`、仓库根目录 `AGENTS.md`
