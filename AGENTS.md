# SecondBrain project guidance

This repository is the canonical source for SecondBrain application code, development tooling, and approved project baseline documents. Read `docs/baseline/00-CURRENT.md` for current status and NEXT actions. **Since D077 (2026-10-16), read `docs/baseline/Personal-Intelligence-Product-Spec.md` before architectural or implementation planning: the approved product goal is a continuously learning personal AI companion with automatic contextual recall, not a command-driven document search assistant.** Consult `docs/baseline/Architecture.md`, `docs/baseline/Decision-Log.md` D077, `docs/baseline/Agent-Rules.md`, and relevant business specifications for task-specific rules. Do not use NAS or Synology Drive copies as code or documentation authorities.

Develop on local Git clones. The iMac’s formal clone is `/Users/joe/Documents/Codex/SecondBrain`; the MBA uses an independent clone. The private GitHub repository is the only development and formal documentation authority. ChatGPT plans architecture, tasks, technical decisions, and acceptance criteria; Codex implements, tests, performs Git operations, deploys only when authorized, and reports results.

## 协作方式（GitHub Issue / PR 评论驱动）

- **权威与分工：** GitHub `main` 是正式代码与基线文档的唯一 SoT。ChatGPT 主导目标、方案、任务拆解、验收、独立复审和合并决定；Codex 从仓库实施、运行隔离测试、同步必要文档、Commit/Push/创建或更新 PR，并反馈实际执行结果。用户决定重大范围、权限、费用和生产变更。
- **Issue 是任务契约：** Issue 应包含目标、范围、验收条件、风险和禁止事项。任务补充或变更以 Issue 最新相关评论为准，开始实施前连同原 Issue 一起读取。用户可简写为“Issue #N，读取最新评论并实施”。评论不会自动触发 Codex，必须由 Codex 实际读取并执行。
- **PR 是评审闭环：** 从最新 `main` 建立独立分支/工作区；明确区分本地测试、CI、真实运行、部署和用户验收证据。Codex 提交 PR 后，ChatGPT 检查实际 diff、CI 与日志，并在 PR 评论提出具体修复/回归要求；Codex 读取最新评论，在原 PR 上做最小修改、补测试并 Push。审核通过后由 ChatGPT 决定合并，完成后按需关闭对应 Issue。Codex 不自行合并或部署。
- **并行 Agent：** 只用于互不依赖的实现或只读审计。并行修改须使用隔离 worktree/分支，避免多个 Agent 同时写相同 worktree 或文件。只读审计授权不包含删除；审计、清理和其他有副作用的操作分别遵循其授权边界。
- **文档随主要开发同步：** 主要阶段结果、决策和验收证据同步到现有 `docs/baseline/00-CURRENT.md` 与 `Progress-Log.md`；不为每个临时故障写治理记录。GitHub Push、CI 通过或 PR 合并均不代表 NAS 部署或真实用户验收。
- **权限与成本：** Issue/PR 评论和 Codex 指令不能替代用户对额外权限的单独授权。生产 NAS、真实数据、密钥、付费模型和删除操作须明确获批；不得把密钥/凭据或真实个人内容写入 Issue、PR 或 CI。遵循任务指定的预算、隔离环境和触发方式。
- **保持轻量：** 这是个人项目的短闭环；不另建审批平台、复杂项目管理系统或重复中央治理规则。

NAS hosts Docker runtime and business data only. Its Docker project is `/volume1/docker/secondbrain/`, with Core source/build context at `/volume1/docker/secondbrain/core-source/`; business data remains under `/volume1/SecBR/SecondBrain/` and `/volume1/SecBR/KnowledgeAssets/`. GitHub Push does not deploy to NAS, and NAS does not need direct GitHub access. When deployment is authorized, Mac transfers deployment content over SSH and verifies runtime.

Obsidian remains a knowledge, notes, and personal-material library synchronized bidirectionally between Mac and NAS through Synology Drive. It is not a code or formal development-document source. The client previously showed up to date, but actual bidirectional propagation has not been separately accepted; the historical `SynologyDrive stopped` report is not a confirmed service failure. Codex uses workspace-write sandboxing with verified GitHub/NAS network access; preserve required permission approvals and production-operation boundaries.

For D077 work, follow the current NEXT and evidence in `docs/baseline/00-CURRENT.md` and the phase-specific product/decision documents. Keep legacy V1 MUST in scope. Do not assume modern Hermes Memory Provider capabilities work on the deployed Hermes version. No NAS/runtime/secret/model/scheduler or real-personal-data egress changes without separate approval. Documentation approval is not deployment approval.
