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
- **生产安全闸门：** Promote 关闭；Knowledge 保持只读；Private 不接入。不得从本状态推断权限已扩大。
- **开发阶段：** 本次 GitHub 状态收口完成前暂停新功能开发。未合入 main 的 PR、隔离分支和原型不算交付。

## 能力状态

| 范围 | 当前已核验状态 | 未完成/限制 |
|---|---|---|
| Capture / Inbox / Review | 多个 Web 与 Core 路径曾部署或隔离验证，详情见最近运行快照和历史记录 | 全量 V1 闭环及当前生产状态 UNKNOWN；微信端到端未接入 |
| Knowledge / Notes / 标签 | V1 既有只读检索；Notes 标签与类型管理 PR #242 已合入 main，Issue #55 可按完成关闭 | 当前生产部署及真实 Vault 验收未复核；知识文件夹/标签筛选仍是独立开发候选 |
| Chat / Hermes | 历史生产快照有接口与服务验证 | 当前版本、跨会话记忆及用户验收未复核 |
| Home / Projects / Brief / Activity | 已有部分页面或隔离实现 | 不能据此宣称全部连接真实业务数据或完成 V1 |
| Markdown 编辑器 | 旧版本功能与用户验收记录见 #46、`Progress-Log.md` | 当前完整范围、现有笔记安全编辑和移动体验待定向验收 |
| Writer / Promote / D090 | 仅有未合并候选与设计记录 | **NOT IN MAIN / 未授权生产启用**；候选 PR #106、#206、#205 保留审查记录，不合并 |
| D086 渠道/微信 | 仅有叠放的合成候选 PR #101、#148、#150–#153、#237、#241 | **NOT IN MAIN / 未接入**；不得从单个中间分支挑选合并 |
| UI 可视化原型 | VNext 原型保存在 `codex/vnext-workbench-20261103`，commit `45bf5f7d918e3396e2bb8d195445ff465ed5a703` | **FROZEN / NOT IN MAIN**；未做用户验收，不是生产 UI |

## 唯一 NEXT

完成本次基线 [PR #262](https://github.com/zxwan829/SecondBrain/pull/262) 的常规独立审查、必要检查和合并；随后只从下列核心队列选定一个工作包及其验收门槛。恢复功能开发前须先确认顺序；任何生产、真实数据、权限/安全架构、Writer/Promote、付费调用仍需各自明确授权。

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
- **正式 Clone 未跟踪内容：** `MINDMAP-DRAG-INVESTIGATION.md`、`docs/SecondBrain_Codex_UX_References_20261026/`、`typescript`、`{{.Destination}}` 原样保留；不在本次提交中。

## 主要风险与验收边界

- GitHub main、最新生产代码和用户实际浏览器验收是三个独立状态；目前 main 后生产版本与本轮真实运行情况 UNKNOWN。
- #261 当前隔离 PR/CI 未通过且 Chromium Gate 未执行；不能合并。
- #74、#30、#78 的风险或授权边界没有因历史测试、PR 关闭或文档更新而解除。
- D084 历史浏览器业务验收仍无新证据（旧宽范围 Issue #44 已按未计划关闭，不是验收完成）。
- 用户浏览器验收、真实 Vault/Private 检查、生产部署、OS 权限和安全架构变更均未在本轮执行。

## 导航

- V1 范围与业务契约：`SecondBrain-Web-App-V1-Business-Spec.md`、`Universal-Capture-Business-Spec.md`
- 稳定架构：`Architecture.md`；正式取舍：`Decision-Log.md`
- 最近已核验运行证据：`Environment-Baseline.md`；历史证据：`Progress-Log.md`
- 执行与安全边界：`Agent-Rules.md`、仓库根目录 `AGENTS.md`
