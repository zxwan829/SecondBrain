---
created: 2026-09-28
updated: 2026-10-17
status: current
type: agent-rules
---
# SecondBrain Agent Rules

本文件只规定 SecondBrain 特有的执行、数据和生产边界。跨项目通用协作规则以 Codex-Governance 中央规则及《开发协作经验手册》为准；不要在此复制或维护通用规则。新任务由 `AGENTS.md` 指向的 `docs/baseline/00-CURRENT.md` 开始。

## 项目权威源与状态核验

- SecondBrain 私有 GitHub Monorepo 是代码和正式项目文档唯一权威源；本地 Clone 通过 Git 共享变更。NAS/Synology Drive 副本不得覆盖仓库。
- `00-CURRENT.md` 是 V1 全量范围与当前开发/验收状态的唯一入口。`Environment-Baseline.md` 只代表标注日期的最近运行证据，不是实时监控；未重新核验的当前运行事实标记 `UNKNOWN`。历史实施和失败证据只放 `Progress-Log.md`。
- 业务细则遵循正式 Business Specification；稳定模块和信任边界遵循 `Architecture.md`；正式取舍遵循 `Decision-Log.md`。旧决策不得覆盖新决定，历史记录不得冒充当前状态。
- Hermes 是当前唯一 Runtime 主线；OpenClaw 已退出当前候选。优先复用 Hermes 官方 Session/Run/SSE/Skill 接口，不重复实现 Agent Runtime。
- **D077 最高产品目标：** 自然对话主动联想长期记忆与知识、获准互动默认自主学习低风险偏好经验、跨会话可纠正、逐渐主动规划。新任务先核对 `Decision-Log.md` D077、`Architecture.md` 和 `00-CURRENT.md`；不把“能手动检索”当作该目标验收通过。Phase 0 已完成；D077 已在 NAS 运行且合成记忆闭环通过，真实模型和用户浏览器行为仍待验收。当前权限工作以 Issue #14 及 D078 为准。

## 按需读取与 Token 控制（SecondBrain 专属）

- **默认不通读两个长 Log 文档：** `Decision-Log.md` 与 `Progress-Log.md`。日常任务优先读取 `00-CURRENT.md`（当前状态、验收、NEXT）、`Agent-Rules.md`（执行边界）、相关业务规格；需了解设计时按需读取 `Architecture.md`，需核对现网时读取 `Environment-Baseline.md` 最新快照。
- **追溯才读取：** 当涉及某个正式决定的批准/替代关系、历史事故、测试证据、争议裁定或阶段复盘时，按 D 编号、Issue/PR、日期、关键词定位对应 Log 的必要章节或行范围；不为“熟悉项目”加载全量日志，不让历史状态覆盖 CURRENT。
- **写入不受此阅读优化限制：** 正式决策变化仍更新 Decision-Log，关键阶段成果/问题/验收证据仍更新 Progress-Log；用户要求全面历史审计时可按需完整阅读。

## GitHub Issue 驱动的唯一协作流程（SecondBrain 中大型任务）

**本节为现行唯一分工，取代此前关于“Codex 在 Issue/PR 汇报”“ChatGPT 读取结果”等未区分责任的旧表述。** Issue 是任务、执行证据与验收结果的主记录；PR 是代码变更和独立代码审查的主记录。不得在两个地方重复张贴完整报告。

1. **ChatGPT 负责规划与发布：** 在 SecondBrain GitHub 新建 Issue，或更新仍在进行的既有 Issue，明确目标、业务需求、技术边界、授权状态、验收条件、交付物与 NEXT。优先沿用已有 Issue，不将每个阶段机械拆分成新 Issue。
2. **Codex 负责执行事实与原始证据：** 开始前阅读 Issue 的最新有效正文、评论及关联 PR/基线，在已获授权的范围内实施、测试、提交代码和创建 PR；完成后在**Issue 评论**汇报实现内容、Commit/PR 链接、测试与部署原始证据、风险、阻塞及待解决事项。PR 描述只概述变更及链接证据，避免复制一整份执行报告。Codex 可以说明“开发完成/测试通过/已部署”，但不能独立宣称“用户最终验收通过”或自行关闭 Issue。
3. **ChatGPT 负责独立复审和收口：** 读取 Codex 在 Issue 留下的执行事实及实际 PR 代码差异；将代码审核意见留在**PR**，再将任务验收结论、未达标项、授权边界及下一步决定记录到**Issue**。达到约定验收标准后，由 ChatGPT 负责关闭 Issue；未经用户明确许可不代替用户认定尚未体验的真实产品功能已验收。
4. **客户端保持简短交接：** 例如「读取 SecondBrain Issue #14 最新有效任务及授权，按范围执行，完成后在 Issue 回复」。详细指令存放在 GitHub；无法访问 Issue 时必须报告，不根据简短口令猜测任务。历史评论如被新决定取代，须在 Issue 明确标注，不能照单全收。
5. **权限与例外：** Issue/PR 或 ChatGPT 的审核不自动扩大用户许可；PR 合并、NAS/生产变更、模型费用、凭据及私人数据使用按各自授权执行。小修复、临时排障、纯解释咨询可不建 Issue，亦无需频繁更新治理文档。该分工**仅适用于 SecondBrain**，不推广到 Codex-Governance 中央规则。

## SecondBrain 数据与安全边界

- Private (`/volume1/SecBR/Private`) 默认不挂载、不扫描、不读取、不索引、不摘要、不记录日志。
- Universal Capture 保留 Raw 原件并按 Raw → Processing → Review 工作；成功状态须由实际文件、哈希和元数据核验，失败保留原件。Capture/Organizer 不自动 Promote。
- 正式 Knowledge 只能由受控 Core Promote Worker 在用户明确批准后写入；普通 Hermes Agent、通用文件工具、模型输出和前端自报身份均无权授权写入。
- 以最近 Environment 快照为准：Hermes 对 Knowledge 只读，`HERMES_WRITE_SAFE_ROOT` 限于三个捕获目录；App Core Knowledge 为只读、`SB_PROMOTE_ENABLED=false`，Private 未挂载。上述是最后记录的已核验状态，不是本轮实时复测结论；生产变更前必须重新验证。
- 普通 Capture/Organizer 写入不得扩展到 SecondBrain 根目录、Knowledge 或 Private。Journal 只可按正式规格以专用新增/追加边界开放，不授予普通 Agent 通用写权。
- **既有 D076 Organizer** 只整理新增用户消息；不得把 AI 推断冒充用户经历或决定。Organizer 模型结果只进入 Review；生产数据出站需明确授权，并满足模型、凭据、输入/输出、超时、并发和费用门禁。Token 估算或软预算不得宣称为供应商硬费用上限。
- **D077 Personal Learning Loop** 与正式知识整理不同：可在明确授权范围内自动提炼低风险个人偏好/经验，但只能通过收窄、可追溯/纠正的记忆通道，不得未经确认自动写入正式 Knowledge、覆盖 Journal 原文、扩大 Hermes 写权限或访问 Private；新的真实对话学习处理、外部模型数据出站及生产启用仍需单独确认。

## D078 Agent 工具监督边界（2026-10-16 决策；2026-10-17 已部署有限验证）

- **能力保留、执行受控：** 不以永久关闭 `file`、`terminal`、`skills` 作为最终设计。普通低风险聊天、获准 Knowledge 读取和 Capture 按既有范围自动进行；敏感文件、跨 Session 读取、危险命令及重要 Skills 修改必须由真实的服务端强制规则或人工审批控制，禁止仅靠提示词声明“请先询问”。
- **已部署与目标分开（2026-10-17）：** D078 Hermes guard、Skills 原生 `write_approval=true` 及 Core/Web 单次工具审批桥已部署；API Server 当前 toolset 为 `file,skills,vision`，**Terminal 仍未启用**。PR #18 的固定 v0.22.2 fail-closed overlay 已部署并通过有限合成权限验证，但生产真实模型 Chat/Run/SSE 与用户记忆体验尚未验收。审批 UI 已部署不代表 terminal 已开放，Skills 自主学习闭环也尚未验收。当前镜像/权限细节看最新 `Environment-Baseline.md`。
- **审批原则：** API terminal 只有在按动作/命令范围的真正强制审批、拒绝和审计完成后才能恢复；文件读取/搜索不得绕过 Session、state、Secret 访问控制；Skills 写审核不得被普通 `file` 写入旁路绕过。Core JSONL 是唯一个人记忆权威存储，不能扩大 Hermes 写入 Core memory 的权限。
- **验收与授权：** 安全专项只做针对性真实权限验证，不重复大型 Runner/Harness。外部/付费模型调用与真实个人数据出站仍须分别获批；保护 Private、Knowledge RO、Promote OFF、NAS 其他服务与家庭网络。

## SecondBrain 专属执行边界

- 先按 `00-CURRENT.md` 完整 MUST 矩阵确定范围；避免重复建设已有功能或改变已批准架构。项目级验证以任务相关测试为主，完整验收契约以正式规格为准。
- 生产 NAS、Compose、容器、挂载、ACL、Secret、网络和真实业务数据属于独立运行边界；只有用户明确授权后，才执行指定范围的操作。失败不构成扩大权限或恢复 Hermes Knowledge RW 的理由。
- 生产变更前核实当前 Compose、容器、挂载、身份和健康状态，保存可验证的最小回滚资产；优先 App-only 变更，避免无关服务重建。回滚不得恢复 Hermes Knowledge RW、启用 Promote 或接触 Private。
- 报告必须区分源码提交、自动化测试、生产部署、运行验证与用户验收；GitHub Push 不代表 NAS 已部署。
- Container Manager GUI 项目定义曾出现与正式 Compose 不一致的缓存状态。未取得可验证安全流程前，不使用 GUI 项目级操作重建服务；该风险不应阻塞无关 V1 业务开发。

## 当前阶段暂停与恢复条件（2026-10-17）

- 用户已要求**暂停开发，集中收口文档**。本阶段不新增功能、不部署/重启 NAS、不清理历史构建/回滚资料、不进行付费模型调用或真实个人数据出站。仅允许在现有项目治理范围内同步准确的 GitHub 文档与审阅。
- 后续行动以 `00-CURRENT.md` 的明确 NEXT 为准；重新开发、运行生产合成 Chat/Run、调用模型及涉及用户数据的体验须按各自范围重新取得明确授权。保持 Hermes API Terminal OFF、Private unmounted、Knowledge RO、Promote OFF、Core JSONL SoT。
