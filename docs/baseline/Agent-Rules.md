---
created: 2026-09-28
updated: 2026-10-13
status: current
type: agent-rules
---
# Agent Rules

适用于 ChatGPT 的规划及 Codex、Hermes、OpenClaw 等获准工具的执行。SecondBrain 私有 GitHub Monorepo 是代码与正式项目基线文档的唯一权威源；iMac 与 MBA 各自使用本地 Git clone，通过 Commit / Push / Pull 共享变更。NAS 负责 Docker 服务与业务数据，Obsidian SecondBrain 库保存笔记、知识和适合阅读的项目资料，不作为开发代码或正式基线文档源头。

**最高项目管理优先级：敏捷优先、功能优先、成本优先。** SecondBrain V1 是个人使用的中小型项目，以尽快交付完整、稳定、可用的业务功能为目标；控制基础风险，接受合理工程取舍，小步持续交付。成本包括时间、Codex Token/模型额度、工具调用、计算资源和维护复杂度。不得为未来商业化提前建设当前不需要的系统。

## 最小读取与 FAST-EXEC

1. 项目任务先读 `AGENTS.md` 入口与 `00-CURRENT.md`。仅在涉及架构、实际环境、业务规则时再读 `Architecture.md`、`Environment-Baseline.md` 或对应 Business Specification。
2. `Decision-Log.md` 与 `Progress-Log.md` 默认按决策号、主题或日期检索，不全文加载。历史留在 Progress-Log；其他文档仅引用。
3. **FAST-EXEC：** 锁定本轮业务目标、影响范围、验收和禁项；已定架构不重议，非必要改进记待办。批量完成同类工作，开发期只跑针对性检查；输入未变的成功结果可复用，完成后集中做一次必要集成验证，不重复无关全量回归。
4. **按风险投入工程步骤：** 低风险小改直接实现并做最小检查，不另建测试环境、专项备份或 Bundle；中风险模块复用现有环境，相关测试加一次集成验证；真实数据、权限、认证、公网暴露等高风险操作，保留必要授权、针对性保护、回退和部署后核验，不省略 Promote 人工审批。
5. **控制执行成本：** Token、额度和时间均为项目成本；确定性小任务优先低成本工具，复杂架构由 ChatGPT 规划，Codex 聚焦实施与核验。不重复研究已确认事项、读取大文件或测试。非关键问题约 10–15 分钟无进展时重新评估投入，可记录后继续不依赖它的主线；这是提醒阈值，不是硬性超时。有限定位与重试，不扩大权限绕过失败。
6. **集中收尾：** 实现与必要验证完成后集中更新必要文档，并与代码一同提交到本地 Git 仓库。通过 GitHub 分享仓库变更；不得从 NAS / Synology Drive 或旧镜像回写仓库。NAS 部署是独立操作，只有用户明确授权后才能进行。简洁报告实际修改、测试、提交、部署、阻塞和下一步，并区分已实现、已测试、已部署及用户验收。

### FAST-PATCH（小型修改）

对范围明确、低风险的小型修复，只读相关文件，直接做最小改动并运行一项针对性检查；不另建测试环境、专项备份或 Bundle，不顺带重构、全量扫描或重复测试。若涉及架构、权限、业务契约、生产边界，或任务明确要求更完整验证，则按任务要求执行，不使用 FAST-PATCH 缩减验证。

## Source of Truth 与环境

- **代码和正式项目文档：** 本 GitHub 私有 Monorepo。iMac、MBA 是平等且可离线工作的开发克隆；以 Git 提交历史共享变更。NAS / Synology Drive 上的旧代码副本不再是权威源，也不得反向覆盖仓库。
- **运行与业务数据：** NAS 负责 Docker 服务、SecondBrain 业务数据及运行配置。部署所需环境值和真实凭据留在受控运行环境，不提交到仓库。
- **Obsidian：** NAS 上的 SecondBrain 库保存笔记、知识内容和适合阅读的项目资料，不存放开发源代码或作为项目基线文档发布机制。
- 冲突按仓库中 `00-CURRENT.md`、相关业务规格及后续 Git 决策处理，不凭旧聊天或备份恢复当前状态。
- 重要命令必须明确执行节点：开发机、NAS SSH、iStoreOS 或 Container。网络、权限、容器/服务变更须在授权范围内；不因失败擅自 `sudo`、`chmod`、`chown`、修改 ACL、网络或 sudoers。

## 数据与安全底线

- Private (`/volume1/SecBR/Private`) 默认不扫描、不读取、不索引、不摘要、不写入日志；仅在用户明确要求的任务中按最小范围处理。
- 原始资料与正式资料不得因 Agent 判断而自动删除；覆盖、批量移动/改名、删除和权限变更属于高风险操作，须明确授权并可恢复。
- Universal Capture 遵循对应正式规格：保存原始证据，写入 Raw/Review，核验真实落盘，不自动 Promote；Human Approval 是进入正式 Knowledge 的前置条件。
- Daily Capture 的触发和输出细则以当前 Hermes Skill `/volume1/docker/secondbrain/hermes/data/skills/daily-capture/SKILL.md` 为准；这是低摩擦写入 00-Inbox 的路径，不复制成第二套规则。
- Journal 的目标规则允许新增与按日期追加、保留原始表达；普通 Agent 不得未经授权删除、覆盖或改写既有 Journal。生产 Journal 写入尚未开放，见 00-CURRENT。
- 运行时权限必须按 Environment-Baseline 与 CURRENT 实际证据描述。规范目标不能冒充生产已 enforced：当前 Hermes Knowledge RW 风险和 Promote 生产阻塞以 CURRENT 为准。
- Private 及其他区域权限、实际 mount、write-safe 环境值均以最新核验的环境证据为准；未核验不得推断。

## 当前写入策略

- 普通 Capture 目标为 `/secondbrain-write/00-Inbox`、`/secondbrain-write/10-Review` 及 `/knowledge-assets/00-Inbox`（按对应任务授权）。正式区域写入遵循各自受控流程。
- 正式 Knowledge 只允许用户确认后的 Promote Worker 写入。普通 Agent/通用 `write_file` 不应拥有 Knowledge 写权；**当前生产 mount 尚未收口，该要求是目标规则而非现状**。在独立 Worker 和审批记录隔离验收前不得启用生产 Promote。
- `30-Projects`、`40-Memory`、`50-Journal`、`90-Archive` 不授予普通 Agent 通用 RW；Journal 仅可在未来通过专用新增/追加边界开放。
- 不把 `/secondbrain` 根目录改为 RW；禁止扩大根目录写安全范围来绕过模块边界。

## 开发、文档与部署

- 中大型开发下发时确定需要更新的文档范围；记录决策、阶段结果、测试、阻塞和下一步。小修免强制文档；资料未能更新时如实报告。详见 Decision-Log 中 D065。
- 代码、Skill、部署脚本、模板和无秘密的配置样例应进入项目资产；避免无理由写死个人环境。真实凭据、密钥、令牌、环境文件、运行数据、构建产物和本地备份不得提交。Hermes 是 Runtime/适配层，不替代 SecondBrain 业务 SoT。
- 正式项目文档与代码在同一 Monorepo 中维护；文档更新通过 Git 版本管理并在必要时与代码一同提交。Google Drive、Synology Drive 或 NAS 不负责开发文档同步，也不应被用于覆盖 GitHub 权威版本。旧的 NAS 安全写入器和 Live Mirror 流程只作为历史运维背景，不是当前开发流程。
- 部署按项目现行快照、哈希、验收与回滚要求执行；Build、Deploy、运行验证和用户验收分开报告。任何正式 NAS 部署均须先取得用户授权。不得为恢复功能把 Hermes Knowledge RW 当作常规回滚。

## Hermes Upstream First

- 优先复用当前受支持 Hermes 上游能力；Core 不重复实现 Hermes Runtime、Chat、Skills、Gateway 或 Dashboard 宿主。
- Hermes 版本差异集中在适配层；升级前先按目标稳定版本验证接口与安全边界。
- 不为减少集成工作降低必要安全边界；生产 Knowledge 写权仍只属于经过用户审批的 Core Promote。

## SecondBrain 产品原则

SecondBrain 是单人自用私人系统：业务优先、风险适度、优先复用现有能力，兼顾稳定性、维护成本与效率；不默认增加商业 SaaS 级反自动化或多用户体系。必要底线是 Private 隔离、Knowledge 人工 Promote、重要资料防误删/误覆盖、关键操作可追溯可恢复。
