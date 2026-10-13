---
created: 2026-09-30
updated: 2026-10-13
source: GitHub SecondBrain Monorepo
status: current
type: project-status
---
# SecondBrain V1 — Current State

本文件是当前状态快照；项目历史见 [Progress-Log.md](Progress-Log.md)，架构见 [Architecture.md](Architecture.md)，环境事实见 [Environment-Baseline.md](Environment-Baseline.md)。业务范围以专项 Business Specification 为准，决策按 [Decision-Log.md](Decision-Log.md) 编号/主题检索。

## 当前结论

- **开发权威源：** 私有 GitHub Monorepo `zxwan829/SecondBrain` 是代码与正式项目文档的唯一权威源。iMac 正式开发克隆为 `/Users/joe/Documents/Codex/SecondBrain`；MBA 后续使用独立 Clone，不依赖 NAS 开发环境。ChatGPT 负责架构设计、任务分解、技术决策和验收标准；Codex 负责代码实施、测试、Git 操作、按授权部署及执行反馈。日常闭环为：ChatGPT 读取 GitHub 状态并制定方案 → Codex 开发、测试、更新必要文档并 Commit / Push → ChatGPT 读取最新结果。
- **开发与部署分离：** GitHub Push 不代表 NAS 已部署。NAS 不需要访问 GitHub；按授权由 Mac 通过 SSH 传入部署内容并验证运行。NAS Docker 正式目录为 `/volume1/docker/secondbrain/`，Core 构建源码目录为 `/volume1/docker/secondbrain/core-source/`；业务数据仍在 `/volume1/SecBR/SecondBrain/` 与 `/volume1/SecBR/KnowledgeAssets/`。
- **Obsidian / Synology Drive：** Obsidian 知识库仍通过 Synology Drive 在 Mac `/Users/joe/SecondBrain/` 与 NAS 之间双向同步，用于知识库、笔记及个人资料，不是代码或正式开发文档来源。客户端此前显示已为最新；实际双向文件传播尚未单独验收。历史 `SynologyDrive stopped` 报告不是已确认故障结论。
- **旧迁移资产：** 旧 NAS SecondBrain V1 开发目录、治理快照、Google Drive 文档镜像、旧发布流程和本地迁移备份已清理；有效生产状态、安全边界及回滚资产见本文件和 Environment-Baseline。
- **Codex 执行环境：** 当前 workspace-write 沙箱下 GitHub 与 NAS 网络访问已验证正常。保留必要权限审批和生产操作边界；网络可达不等于获得生产变更授权。

- SecondBrain V1：**NOT DONE**。正式 Hermes Dashboard `/secondbrain` 已部署；前端与部分真实只读 API 已运行，模块完整性、Universal Capture V1 附件链路及安全收口仍未完成。
- Hermes：生产 v0.21.5 / build 749220ef，镜像按不可变 digest 固定。运行事实与部署回退入口见 Environment-Baseline。
- Universal Capture：生产 Skill v0.1.3；已验收文本 Raw→Review，不自动 Promote。V1 MUST 还包括 URL/Web、PDF、Image/Screenshot、Audio/Voice，均未实现/验收。见 [Universal-Capture-Business-Spec.md](Universal-Capture-Business-Spec.md)。
- Dashboard FE-4：正式版已部署，Mac/PC 与 iPhone 视觉已接受；整体 ACCEPTED WITH KNOWN ISSUES。业务 API 部分真实、部分未连接/不可用；正式 iPhone Safari 独立回归仍缺证据。模块与验收细节见 Progress-Log。
- Hermes + SecondBrain Core 遵循 D066/D067/D068；Core 最近一次已记录状态为现有 SecondBrain 项目内 healthy。阶段 A Core 状态持久化、暂缓决定和失败恢复已实现并提交 GitHub `main`（`2144f23`），15 项离线测试通过；**未部署**。D071 v0.2.4 只读 Review 前端和 FE-4 基线未改，正式 HTTPS Edge 验收仍成立。生产 Promote 仍关闭；本轮 NAS Compose/ACL 只读检查完成，但容器 Docker socket 对 SSH 用户拒绝访问，当前运行挂载/UID/环境值未能复核，详见 Environment-Baseline。

## 主要安全与实施边界

- Private 保持隔离；正式 Knowledge 必须由用户确认后 Promote，普通 Agent 不得直接写入。
- **生产差距仍存在：** NAS 当前生产 Compose 声明 Hermes 的 `20-Knowledge` 为 RW，Core 的 `20-Knowledge` 为 RO 且 `SB_PROMOTE_ENABLED=false`；Hermes 写安全根包含 Inbox、Review 与 Knowledge 的父路径。本轮 SSH 用户 UID 1026 无 Docker socket 访问权，故以上是 NAS Compose 声明及既有运行基线，未确认当前容器实际状态。生产写入切换仍 BLOCKED；不得把 Hermes Knowledge RW 作为常规回滚。
- `50-Journal` 无生产直接写入挂载。已决定的 Journal 新增/追加规则是目标能力，当前 **NOT IMPLEMENTED**；不得将其写成已上线。
- 施工期 unrestricted sudoers 安全债为 OPEN；NAS 生产服务变更及正式部署仍需按现有安全流程维护。
- 旧治理文档发布/同步脚本属于迁移前流程，不再作为正式文档发布渠道；当前正式版本以 GitHub Monorepo 历史为准。NAS 和 Google Drive 中的旧副本不应覆盖仓库。

## 唯一执行入口：NOW / BLOCKED / DEFERRED

- **NOW — Review→Promote 阶段 B：** 阶段 A Core 实现已提交并测试，未部署。已选定保留 D067 Core 独立短时授权：Dashboard 明确点击后浏览器直连 Core；Core 锁定时须用现有 Core 解锁口令，之后每次写入仍需明确确认。免第二次解锁在当前 Hermes 与 Agent 共用认证/执行边界下无法满足用户确认与防伪造要求。生产权限切换前须补齐实时容器证据，并执行 Hermes RW 移除/Core RW 独占的单独部署验收；本快照没有生产切换授权。
- **NOW — V1 Capture：** 按冻结规格实现并验收 URL/Web、PDF、图片/截图、语音输入；保留原始证据、Review 与人工 Promote 流程。
- **NOW — Dashboard：** 补齐当前未连接的真实业务模块，并完成正式 iPhone Safari 功能回归；不得把 DEMO/UNAVAILABLE 标成真实数据。
- **COMPLETE — D071 只读 Review：** v0.2.4 已部署；用户已通过正式 HTTPS Edge 验收 FE-4、8 条真实 Review 列表与详情正文。无需 Core 二次解锁；无 Promote 按钮或 Knowledge 写入。
- **BLOCKED — 生产 Promote 写入：** 本轮 Docker socket `/var/run/docker.sock` 为 `root:root 0660`，SSH 用户 `1026:100` 无读写权限；未使用 sudo。故当前容器挂载、运行 UID、运行环境和 Core 有效 Knowledge 权限均待核。解除条件：取得受控只读运行证据，落实并验证 Hermes RW 移除/Core Knowledge RW 独占、Core 审批状态目录 ACL 与 HTTPS/代理边界，确认可回退；之后仍需单独用户批准正式部署/启用。不得以恢复 Hermes Knowledge RW 作为常规回滚。
- **DEFERRED — V1 前收口：** 在宣布 V1 DONE 前，复核并收口临时 unrestricted sudoers。
- **DEFERRED — 访问与发布：** V1 基本可用后再完成 Agent/Dashboard 公网直接访问，复核 DSM 63012/63013 规则及 ACL；不要求 WireGuard，也不为 SecondBrain 专门改造 AdGuard。
- **DEFERRED — 商业化整理：** V1 完整可用后，再统一处理产品代码与个人数据分离、密钥/环境参数化、发行包、安装和迁移标准化。
- **DEFERRED — 非主线体验债：** FE-3.2 性能定量、轻微视觉瑕疵及 Hermes 0.21.6 评估，除非出现既定触发条件或用户重新排期。

## 状态口径

已实现、测试通过、已部署、生产运行、用户验收是不同状态；本快照仅使用有证据的标记，详细证据与过程保留在 Progress-Log。

## 当前模块状态

| 区域 | 状态 | 当前解释 |
|---|---|---|
| Dashboard Home / Today | PARTIAL / REAL | Today 真实空状态；只读首页已部署。 |
| Review / Knowledge | REAL / gated | D071 Hermes Session 只读 Review 已部署并通过用户 HTTPS Edge 验收；列表 8 条，详情可读。Promote 仍关闭，正式 Knowledge 仍 RO。 |
| Projects | UNAVAILABLE | 当前数据响应不构成可信业务项目列表。 |
| Agent health | UNAVAILABLE | 未接入可信实时状态来源。 |
| Daily Brief / Activity | NOT CONNECTED | 当前无真实模块数据接口。 |
| Charts / weather | DEMO | 必须保持明确演示语义。 |
| Capture / Journal UI writes | CLOSED | 前端入口未开放业务写入。 |
| Chat | Hermes native | 继续复用 `/chat` 与 Hermes 会话。 |

正式版 FE-4 的 Mac/PC 与 iPhone 视觉已用户 ACCEPTED；iPhone KPI 星球定位已接受。用户对正式版整体体验为 ACCEPTED WITH KNOWN ISSUES，不能据此宣称各模块真实接通。测试插件 `/secondbrain-fe-test` 与正式插件身份、资源入口和快照保持隔离。详细发布哈希和路径在 Environment-Baseline，过程证据在 Progress-Log。

当前环境事实只记在 Environment-Baseline；决策背景/演进/验证证据只记在 Decision-Log 与 Progress-Log，避免快照重复承载完整历史。

## 按需读取

- 常规任务：Git 工作区根目录的 `AGENTS.md` 发现入口与本文件；本仓库的 `Agent-Rules.md` 是项目执行规则。
- 架构变更：Architecture.md；路径、容器、版本或回退：Environment-Baseline.md。
- 业务行为：对应 Business Specification；历史问题/测试证据：Progress-Log.md；具体决定：Decision-Log.md 中按编号或主题检索。
- 不全文加载历史日志、归档快照或其他项目内容；Private 不属于本项目审计范围。
