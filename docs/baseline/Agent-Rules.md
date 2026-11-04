---
created: 2026-09-28
updated: 2026-11-03
status: current
type: agent-rules
---
# SecondBrain Agent Rules

本文件只规定 SecondBrain 特有的执行、数据和生产边界。跨项目通用协作规则以 Codex-Governance 中央规则及《开发协作经验手册》为准；不要在此复制或维护通用规则。新任务由 `AGENTS.md` 指向的 `docs/baseline/00-CURRENT.md` 开始。

## 项目权威源与状态核验

- SecondBrain 私有 GitHub Monorepo 是代码和正式项目文档唯一权威源；本地 Clone 通过 Git 共享变更。NAS/Synology Drive 副本不得覆盖仓库。
- `00-CURRENT.md` 是 V1 全量范围与当前开发/验收状态的唯一入口。`Environment-Baseline.md` 只代表标注日期的最近运行证据，不是实时监控；未重新核验的当前运行事实标记 `UNKNOWN`。历史实施和失败证据只放 `Progress-Log.md`。
- 业务细则遵循正式 Business Specification；笔记、对话收录、标签与类型的当前产品规则见 `业务规范.md`，其中批准的方向不等于已实施或数据操作授权；稳定模块和信任边界遵循 `Architecture.md`；正式取舍遵循 `Decision-Log.md`。渠道架构见 D087，Daily Brief 范围见 D088，Journal 来源选项合同见 D089。旧决策不得覆盖新决定，历史记录不得冒充当前状态。决策/文档获批不证明接口已合并、渠道已接入、生产已部署或验收已通过。
- Hermes 是当前唯一 Runtime 主线；OpenClaw 已退出当前候选。优先复用 Hermes 官方 Session/Run/SSE/Skill 接口，不重复实现 Agent Runtime。
- **D077 最高产品目标：** 自然对话主动联想长期记忆与知识、获准互动默认自主学习低风险偏好经验、跨会话可纠正、逐渐主动规划。新任务先核对 `Decision-Log.md` D077、`Architecture.md` 和 `00-CURRENT.md`；不把“能手动检索”当作该目标验收通过。Phase 0 已完成；D077 已在 NAS 运行且合成记忆闭环通过，真实模型和用户浏览器行为仍待验收。当前权限工作以 Issue #14 及 D078 为准。

## 按需读取与 Token 控制（SecondBrain 专属）

- **默认不通读两个长 Log 文档：** `Decision-Log.md` 与 `Progress-Log.md`。日常任务优先读取 `00-CURRENT.md`（当前状态、验收、NEXT）、`Agent-Rules.md`（执行边界）、相关业务规格；需了解设计时按需读取 `Architecture.md`，需核对现网时读取 `Environment-Baseline.md` 最新快照。
- **追溯才读取：** 当涉及某个正式决定的批准/替代关系、历史事故、测试证据、争议裁定或阶段复盘时，按 D 编号、Issue/PR、日期、关键词定位对应 Log 的必要章节或行范围；不为“熟悉项目”加载全量日志，不让历史状态覆盖 CURRENT。
- **写入不受此阅读优化限制：** 正式决策变化仍更新 Decision-Log，关键阶段成果/问题/验收证据仍更新 Progress-Log；用户要求全面历史审计时可按需完整阅读。
- **时间累积型 Log（本项目具体执行规则）：** 遵循 `Codex-Governance/AGENTS.md` 的跨项目默认：凡以时间为主轴持续新增记录的 Log，最新记录置前，历史记录向后；不将 CURRENT、Architecture、业务规格或按 D 编号管理的 `Decision-Log.md` 混作这类日志。SecondBrain 的 `Progress-Log.md` 必须将每条新增 `##` 章节插在文档开头说明之后、原最新记录之前；不得追加到文末、重复阶段记录或重排历史。提交前核验章节位置和时间顺序。`Progress-Log.md` 首页只保留格式提示，项目 `AGENTS.md` 已引用本规则文件，不重复复制。`Environment-Baseline.md` 的已核验快照按自身既有结构维护；若将来新增独立的时间累积型运行日志，则遵循通用默认或在此明确例外。

## 统一 Codex 主 Agent 与 GitHub 任务驱动协作（2026-10-24 起唯一现行模式）

**本节替代此前“ChatGPT 逐项派发、A/B 各自独立聊天会话、用户手动转达反馈”模式。** 旧 A/B Issue、PR、复审记录及历史快照保留作证据；其“用户负责转发/分别唤醒 A/B”流程不再具规范效力。对任务边界与权限的既有安全限制仍有效。

1. **唯一主执行负责人：** 用户一次确定 V1 目标和授权后，一个 Codex 主 Agent 负责读取 `AGENTS.md`、`00-CURRENT.md`、其中列出的当前开放核心 Issue 与关联 PR 的最新有效事实；自主选择已批准工作包、辨认依赖、分配、验证、集成、按门禁合并普通 PR、归档证据，再领取下一项。#96/#97 及其旧 A/B 长任务记录只作为历史证据；#76 是本次一次性收口执行单，在 PR #262 合并且 main 核验后关闭，此后只作历史证据。上述记录均不作为默认任务入口。用户无需在 A/B 会话间复制指令。
2. **Web/Core 是工作角色而非两个必须分别启动的会话：** 主 Agent 可在当前环境支持时委派 Web、Core、独立 Review 子 Agent，分别使用隔离 worktree/明确文件所有权；不支持子 Agent 时由同一主执行器按依赖顺序处理，不能假称已经并行。原则上主 Agent 是唯一 main 合并协调者；旧 A/B 窗口不再自主同时改写主干。
3. **独立审查不得自证：** 代码实现者（含主 Agent 自己实施的代码）不得将自身复核称为独立 Review。普通 PR 可由未参与该实现的 Review 子 Agent 独立审查；主 Agent 汇总审查结果、增量验证和 GitHub 门禁后再决定是否合并。子 Agent 的审查记录不替代 GitHub 明确要求的审批、状态检查或分支保护。涉及授权、安全、文件删除/恢复、Writer/Promote 等敏感变更必须执行相应安全审查和专门授权。GitHub 不允许作者自审时不得换身份绕过；记录真实阻断并推进其他独立工作。
4. **ChatGPT/用户的定位：** ChatGPT 负责重大架构、业务范围、重要安全合同与重大阶段验收；不是日常任务启动器，也无需逐项复审普通 PR。Review 子 Agent 可执行普通变更的独立源码审查，但安全敏感事项仍需相应独立安全复审，且任何子 Agent 都不能替代 GitHub 必需审批。用户保留业务方向、生产与真实数据/渠道、收费调用、不可逆操作及需单独许可的安全敏感变更的批准权；未经体验不得宣布用户验收通过。
5. **GitHub 协作记录：** Issue 为跨子任务的统一队列与证据记录，PR 为代码审查和合并记录。主 Agent 在当前工作对应的开放 Issue/PR 中清晰标记 owner、依赖、固定 HEAD、实现/已测试/已合并/未验收、阻断和 NEXT；项目全局状态只更新 `00-CURRENT.md`。#96/#97 已关闭，#76 是本次一次性收口执行单并将在收口后关闭；三者均不作为日常任务入口。避免重复整篇粘贴、重复建立治理文档或每个小错误开新 Issue。仅重大事项或外部权限阻断才回报用户等待决定，其余可执行工作继续推进。
6. **执行连续性与真实能力：** 一次启动后在当前 Codex 任务实际可运行期间持续领取下一包；没有子 Agent、调度器、凭据或持久执行环境时不得声称跨会话自动唤醒、无人值守永久运行。以后若建设常驻调度器，必须先另行审批运行位置、认证、预算、并发、停止开关及恢复机制；当前协作决策不自动授权部署它。
7. **合并与验收：** 普通低风险 PR 依据用户已有批量合并授权，由唯一主 Agent 在独立审查、必要定向/组合测试和 GitHub 检查/保护满足后自行合并；不得强推、跳过保护或把空 CI 状态当作无门禁证据。合并 ≠ NAS 部署 ≠ 真实数据验证 ≠ 用户最终验收。复用无运行代码变化的有效证据，增量变化只补必要测试。
8. **安全边界持续不变：** NAS/生产、Private/真实 Vault、个人数据出站、真实渠道、费用、不可逆删除、生产 Writer/Promote、D090 与 OS Gate 仍依原授权。普通集成授权不自动扩大这些权限。

## 并行切片与集中集成验收（D084）

- 独立功能切片可分别开发和代码审查；当 ChatGPT 明确通过代码审查、且任务指定共享开发分支时，可将已审切片合入该开发分支。开发分支合并不等于合入 `main`，更不等于生产部署或用户验收。
- 各切片只运行自身必要的定向合成测试；无需逐切片重复真实浏览器、真实模型或 NAS 验收。集成负责人以最新 `main` 为基线，保留其独有修复，再协调并行切片和未合并 PR 的冲突与依赖。
- 跨模块接口、共享 BFF/UI 和安全门禁完成集成后，按一份统一计划集中运行必要的合成回归。对已由未变代码覆盖且无共享接口影响的测试不重复执行；前置条件缺失的依赖场景应标记 BLOCKED，不得伪报 PASS。
- 集成合成验证完成后，如下一步涉及 NAS、生产配置/权限、真实模型、真实个人数据出站或用户浏览器验收，应停止并取得与该操作相匹配的明确授权。`main` PR 合并与生产操作仍遵循各自审批流程。

## Web 浏览器自动化环境

- Web Playwright 三视口端到端验收的正式运行环境为 GitHub-hosted Ubuntu 24.04 + Playwright Chromium，通过 `.github/workflows/a-web-playwright-synthetic.yml` 执行。该 workflow 为手动触发；触发前须固定目标 SHA 并取得对应运行授权，执行时 checkout `github.sha` 并验证实际 `HEAD` 完全一致。
- macOS 工作站只运行组件/DOM 测试、Core + Vite localhost HTTP 合成联调、typecheck 与 build；不在 macOS 上启动 Playwright 浏览器，不继续排查已知 Edge SIGABRT/Chromium SIGTRAP。不得借用个人浏览器 Profile 或修改系统权限来绕过。
- 本地组件和 HTTP 测试通过不替代 Linux 浏览器验收；Linux 浏览器 Gate 通过也不替代生产、真实数据或用户验收。报告必须区分浏览器未启动、视口旅程未运行和实际页面断言失败。

## SecondBrain 数据与安全边界

- Private (`/volume1/SecBR/Private`) 默认不挂载、不扫描、不读取、不索引、不摘要、不记录日志。
- Universal Capture 保留 Raw 原件并按 Raw → Processing → Review 工作；成功状态须由实际文件、哈希和元数据核验，失败保留原件。Capture/Organizer 不自动 Promote。
- 正式 Knowledge 只能由受控 Core Promote Worker 在用户明确批准后写入；普通 Hermes Agent、通用文件工具、模型输出和前端自报身份均无权授权写入。
- 以最近 Environment 快照为准：Hermes 对 Knowledge 只读，`HERMES_WRITE_SAFE_ROOT` 限于三个捕获目录；App Core Knowledge 为只读、`SB_PROMOTE_ENABLED=false`，Private 未挂载。上述是最后记录的已核验状态，不是本轮实时复测结论；生产变更前必须重新验证。
- 普通 Capture/Organizer 写入不得扩展到 SecondBrain 根目录、Knowledge 或 Private。Journal 只可按正式规格以专用新增/追加边界开放，不授予普通 Agent 通用写权。
- 对话中的明确收录和日记碎片按 `业务规范.md`、D086 先由 Core 保存原文至统一 Inbox；转成 Journal、正式 Knowledge 或回写文件分别遵守专用审批边界。既有直写代码或历史决策不构成新流程已上线的证据。
- **既有 D076 Organizer** 只整理新增用户消息；不得把 AI 推断冒充用户经历或决定。Organizer 模型结果只进入 Review；生产数据出站需明确授权，并满足模型、凭据、输入/输出、超时、并发和费用门禁。Token 估算或软预算不得宣称为供应商硬费用上限。
- **D077 Personal Learning Loop** 与正式知识整理不同：可在明确授权范围内自动提炼低风险个人偏好/经验，但只能通过收窄、可追溯/纠正的记忆通道，不得未经确认自动写入正式 Knowledge、覆盖 Journal 原文、扩大 Hermes 写权限或访问 Private；新的真实对话学习处理、外部模型数据出站及生产启用仍需单独确认。

## D078 Agent 工具监督边界（2026-10-16 决策；2026-10-17 已部署有限验证）

- **能力保留、执行受控：** 不以永久关闭 `file`、`terminal`、`skills` 作为最终设计。普通低风险聊天、获准 Knowledge 读取和 Capture 按既有范围自动进行；敏感文件、跨 Session 读取、危险命令及重要 Skills 修改必须由真实的服务端强制规则或人工审批控制，禁止仅靠提示词声明“请先询问”。
- **已部署与目标分开（2026-10-17）：** D078 Hermes guard、Skills 原生 `write_approval=true` 及 Core/Web 单次工具审批桥已部署；API Server 当前 toolset 为 `file,skills,vision`，**Terminal 仍未启用**。PR #18 的固定 v0.22.2 fail-closed overlay 已部署并通过有限合成权限验证，但生产真实模型 Chat/Run/SSE 与用户记忆体验尚未验收。审批 UI 已部署不代表 terminal 已开放，Skills 自主学习闭环也尚未验收。当前镜像/权限细节看最新 `Environment-Baseline.md`。
- **审批原则：** API terminal 只有在按动作/命令范围的真正强制审批、拒绝和审计完成后才能恢复；文件读取/搜索不得绕过 Session、state、Secret 访问控制；Skills 写审核不得被普通 `file` 写入旁路绕过。Core JSONL 是唯一个人记忆权威存储，不能扩大 Hermes 写入 Core memory 的权限。
- **验收与授权：** 安全专项只做针对性真实权限验证，不重复大型 Runner/Harness。外部/付费模型调用与真实个人数据出站仍须分别获批；保护 Private、Knowledge RO、Promote OFF、NAS 其他服务与家庭网络。

## V1 验收与 Hermes 安全修复的交付闸门（2026-11-04 纠偏）

- **先核验可执行性，后承诺交付：** 每次开始构建或修复前，由 Codex 主 Agent 自行检查固定源码 commit 是否完整可检出、补丁可应用、现成测试运行环境/依赖、Docker 构建条件和测试入口；缺项先使用隔离环境或现有可信资产补齐，不在长任务执行中途才发现基本依赖缺失。
- **单一可验收工作包：** 当期一次聚焦一个具体产物及其验收证据，完成该产物再进入下一阶段。重复 BLOCKED 时必须说明已尝试的替代路径、真实障碍及其证据；不能仅重复权限、Clone 落后或历史风险。ChatGPT 不再通过不断增加大型任务指令代替问题收敛。
- **镜像内容强制验收：** 安全修复必须在隔离环境通过故障路径定向测试；构建后核对候选镜像内*实际执行文件*的补丁特征/哈希与 pinned source、补丁和镜像 ID；生产获批部署后再检查运行容器文件与预期一致。镜像标签、Dockerfile、仓库单测和“插件已加载”均不能独立代替运行代码证据。关键任一失败即不放行安全敏感模型 Run。
- **分开报告四种状态：** 开发合并、隔离测试、生产运行、真实用户 UAT 分开标记 PASS / PARTIAL / FAIL / NOT RUN / BLOCKED。历史基线未经本轮复核不能宣称现网 PASS。
- **必要时才请求用户操作：** 由 Codex 使用已有 SSH/sudo 执行授权范围内的技术只读核验；只有生产变更、真实个人数据、秘密、付费调用或额外高风险权限需要用户具体批准。生产变更前提供最小影响、备份和回滚方案；故障旧镜像回滚只能恢复可用性，不能恢复安全放行状态。
- **现有文件即唯一状态闭环：** 首轮用户 UAT 完成一个有意义的阶段、或关键 P0 安全结论变化时，及时更新本文件所指的 `00-CURRENT.md` 与相关 Issue 证据；不增设并行治理文档。

## SecondBrain 专属执行边界

- 先按 `00-CURRENT.md` 完整 MUST 矩阵确定范围；避免重复建设已有功能或改变已批准架构。项目级验证以任务相关测试为主，完整验收契约以正式规格为准。
- 生产 NAS、Compose、容器、挂载、ACL、Secret、网络和真实业务数据属于独立运行边界；只有用户明确授权后，才执行指定范围的操作。失败不构成扩大权限或恢复 Hermes Knowledge RW 的理由。
- 生产变更前核实当前 Compose、容器、挂载、身份和健康状态，保存可验证的最小回滚资产；优先 App-only 变更，避免无关服务重建。回滚不得恢复 Hermes Knowledge RW、启用 Promote 或接触 Private。
- 报告必须区分源码提交、自动化测试、生产部署、运行验证与用户验收；GitHub Push 不代表 NAS 已部署。
- Container Manager GUI 项目定义曾出现与正式 Compose 不一致的缓存状态。未取得可验证安全流程前，不使用 GUI 项目级操作重建服务；该风险不应阻塞无关 V1 业务开发。
