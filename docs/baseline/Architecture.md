---
updated: 2026-10-13
status: current
type: architecture
---
# SecondBrain V1 Architecture

## 稳定边界

- SecondBrain 文件与目录是业务数据 Source of Truth；Hermes 是当前 Agent Runtime；Dashboard 是交互入口。不要复制 Agent Runtime、正式知识库或第二份业务数据库。
- NAS 正式数据位于 `/volume1/SecBR/SecondBrain` 与 `/volume1/SecBR/KnowledgeAssets`。Private 单独隔离，默认不对 Agent/API 开放。
- 生产与测试插件身份、资源、入口和快照隔离；FE-4 已部署不等于所有业务模块已接通。
- 个人自用、业务优先、风险适度：复用 Hermes 登录、会话与插件能力；保留人工 Promote、Private 隔离、重要资料保护和审计恢复，不默认引入 SaaS 级复杂控制。详细执行规则见 Agent-Rules。

## 开发仓库与职责边界

- GitHub 私有 Monorepo 是 SecondBrain 代码与正式项目基线文档的唯一权威源；iMac、MBA 各自 clone 并独立开发，通过 Git Commit / Push / Pull 协作。开发与本地测试不依赖 NAS 在线。
- NAS 负责 Docker 服务、业务数据与运行配置。NAS 上的 Obsidian SecondBrain 库仅用于笔记、知识内容和适合阅读的项目资料，不保存开发代码，也不作为基线文档源。
- 代码和文档的正式修改在 Git 仓库中完成。NAS 部署与生产数据操作分开执行，必须取得用户明确授权；部署状态和运行事实仍按需记录在 Environment-Baseline / CURRENT。
- 原 NAS/Synology Drive/Google Drive 同步描述反映迁移前流程，只用于理解历史环境，不再定义当前开发、版本管理或正式文档发布机制。

## 当前运行架构（已部署）

Hermes Dashboard Shell → SecondBrain Dashboard Plugin → 认证 API/薄适配层 → SecondBrain 文件只读数据与 Hermes 原生 Chat/Session 能力。

正式插件为 `secondbrain`，页面 `/secondbrain`；前端 React + TypeScript + Vite，复用 Hermes Plugin SDK/宿主 React。Home API 提供受限语义读；不能将文件名/目录列表推断为业务状态。当前模块语义与缺口由 00-CURRENT 和 Environment-Baseline 维护。

## Core 目标架构与当前状态

经批准的方向为 **Hermes + SecondBrain Core 模块化单体**。Hermes 继续承载登录会话、Agent Runtime、原生 Chat 与 Dashboard 插件宿主；SecondBrain Core 作为单一模块化应用承载领域规则、用例和受控文件数据操作，由 Dashboard 直接调用必要的 Core API。Core service 已在现有 SecondBrain Compose Project 中运行 healthy；Dashboard 只读 Review 视图及 Core 列表/详情 API 已部署，完整列表与详情仍待用户在 Edge 解锁验收。按 D068，Hermes 与 Core 正式归属 Container Manager 现有同一个 SecondBrain Compose Project，Core 作为新增 service；两个容器仍保持独立权限、挂载和认证边界。`compose.core-isolated.yaml` 仅为隔离测试候选，不能作为独立正式项目部署。V1 完整可用前不进行商业发行包、代码/数据/密钥/环境参数化整理。

Core 的模块边界对应业务能力：Capture、Review/Promote、Knowledge、Journal、Projects、Calendar。模块共享一个应用进程/部署单元并通过显式接口协作；不新增独立数据库、LLM、n8n、第二 Runtime 或独立管理后台。只有已实现模块建立代码，不创建空占位包。

**CORE-0 隔离工程基础（已实现并测试，未部署）：** `web-app/secondbrain-core/secondbrain_core/modules/review_promote/` 收纳 Review Adapter、审批校验、幂等记录、Promote Worker 与 HTTP Router。Promote 在 Core 同进程完成，不使用跨容器审批队列。29 项隔离测试在此前阶段通过。当时源码、测试与 `CORE-0.bundle` 曾放入 NAS 项目资产；此为迁移前归档事实，不改变当前 GitHub 仓库的代码权威地位。

**CORE-1/2 身份与审批边界（CORE-2 隔离实现，未部署）：** Hermes v0.21.5 Basic Auth 中间件验证 session 后写入进程内 `request.state.session`，`/api/auth/me` 返回该身份；但生产 Hermes 以 root 运行、Basic Auth 密码在容器环境中且普通 Agent/Shell 共用该进程边界，因此 Hermes Cookie 转发或 Core 回查都不能证明是本人审批。v0.21.7 RC 的 `/api/auth/me` 在 loopback 模式可返回 token 校验后的合成 `user_id=local`、`provider=loopback`，该身份绝不能提升为人工批准。

经 CORE-2 核验，Promote 改用 Core 独立单人授权：用户先在 Dashboard 解锁 Core，之后由浏览器直接向 Core 提交审批；凭据和 HttpOnly/Secure/SameSite 短期 session 不经过 Hermes。Core 仅信任 Core 自己签发且保存在内存中的 session，严格校验 HTTPS、精确 Dashboard Origin/CORS、Review 路径与 SHA-256，审计主体记为 `owner`。Core HTTP app 不注册旧 Hermes-session router；普通 Agent 提供的 `user_id`、session、`approved=true` 均不起授权作用。详细实现和测试见 `web-app/secondbrain-core/`。

**CORE-4 DSM HTTPS 入口（已配置，浏览器与生产审批联调未收口）：** 复用现有 `zxwan520.com` / `*.zxwan520.com` 证书，新增 `zxwan520.com:63012` → `192.168.3.27:9119` Dashboard 规则及 `zxwan520.com:63013` → `127.0.0.1:9120` Core 预留规则。两者绑定 `SecondBrain LAN-only` profile（允许 `192.168.3.0/24`，拒绝其余 IPv4 与 IPv6），不启用 HSTS；Dashboard 原 HTTP 入口保留。规则按主机+端口，不支持本次已验证的路径转发。Mac 局部解析下 TLS 验证通过：Dashboard 返回 302 登录重定向；临时回显测试曾证明 Core 代理链可达。当前 Compose 中 Core service healthy；Promote 仍关闭、Knowledge 仍为 RO。63013 仅为 LAN-only Core HTTPS 入口，不代表生产 Promote 已启用。临时回显服务的 Origin/Cookie 测试通过，但不是正式 Core 浏览器审批联调。用户已报告在真实 Edge 登录并访问 Dashboard HTTPS；Dashboard Review 完整列表/详情的最新部署版本仍待用户解锁验收。DSM profile 配置与绑定已核实；NAS loopback 请求返回 302，不能作为非 LAN 拒绝测试。路由器静态配置及活动 nftables 未发现 63012/63013 DNAT。

Core 启动将 Uvicorn `X-Forwarded-*` 信任限制到 `SB_TRUSTED_PROXY_IPS`；应用校验精确 `SB_CORE_ALLOWED_HOSTS`。本次临时回显发现 DSM 保留客户端可影响的 `X-Forwarded-For` 和 `X-Forwarded-Host`，但将 `X-Forwarded-Proto` 设为 `https`；客户端伪造 Host 得到 404。Core 必须只信任可信本地代理连接，并拒绝或安全解析可伪造的转发头；不得以这些头授予权限。

**Core 文件边界（Compose 已配置，生产切换未验收）：** 现有 SecondBrain Compose 已增加 Core service：Review、Knowledge RO；Core 私有 state/secret；Promote 当前关闭。该配置不给 Core Knowledge 写权限；Core service 当前 healthy，但 Promote 仍关闭。计划的正式边界为 Hermes Knowledge RO、Core Knowledge RW、Core 独占审批凭据；生产 Hermes 当前仍保留 Knowledge RW，切换受阻。`compose.core-isolated.yaml` 仅为隔离测试候选，不能独立部署。Core 配置 UID 1026/GID 100；此前隔离目录测试中，Hermes root 在 RO mount 下写入失败，Core UID 1026 可按模拟授权写 Knowledge/state，这不是生产切换验收。

生产 Promote 仍 **BLOCKED**：需完成浏览器 HTTPS 访问、非 LAN 来源拒绝验证、Core 实际代理头安全处理及生产挂载隔离准备；之后再单独批准生产切换。不得以恢复 Hermes Knowledge RW 作为常规回滚。

## 数据区域与写入生命周期

- `00-Inbox` / `KnowledgeAssets/00-Inbox`：原始捕获和原始证据；Raw 不被派生内容替代。
- `10-Review`：待用户审核的候选内容。
- `20-Knowledge`：用户确认后 Promote 的正式长期知识。
- `30-Projects`、`40-Memory`、`50-Journal`、`90-Archive`：各自业务区，普通 Agent 无通用根目录 RW。
- 基本知识流：Input → Raw → Review → 用户批准 → Promote → Knowledge。失败需保留可恢复的原始/Review 证据。

生产 Hermes 当前仍有 Knowledge RW mount，普通 `write_file` 可绕过 Promote；Core service healthy 但挂载为 RO、Promote 关闭。生产 Knowledge 写权切换仍 **BLOCKED**，生产身份/审批与容器文件权限隔离须按 00-CURRENT 完成后另行批准。Journal 目标规则支持专用新增/追加，但生产挂载尚未开放。状态以 00-CURRENT 为准。

## Universal Capture

输入、元数据、失败/重试与验收以 canonical `Universal-Capture-Business-Spec.md` 为准。V1 MUST 输入是文本、URL/Web、PDF、Image/Screenshot、Audio/Voice；原始证据需保留，输出到 Review 并等待人工批准。Office 文件、Video、通用二进制及语义检索/去重等按规格延期。禁止把架构摘要作为第二份业务契约。

## Dashboard

正式 SecondBrain UI 使用 Hermes Dashboard Plugin；Hermes 提供宿主与原生 Runtime 能力，SecondBrain 控制页面模块和业务语义。UI 只显示可证实为 REAL 的数据；演示值须标 DEMO，来源或含义不可靠时用 UNAVAILABLE。FE-4 视觉基准已接受；不得以文档整理为由改 FE-4。

Web App 详细产品契约见 `SecondBrain-Web-App-V1-Business-Spec.md`。Home 与 Calendar 是聚合层，模块注册可扩展；业务页不必共用 Home 布局。写入能力必须由服务端语义接口、allowlist 和明确审批控制，不能仅凭 UI 按钮或模型声明授权。

## Journal

`50-Journal` 用于随手记、备忘录、碎片想法、日常记录和用户明确要求保存的语音转文字。目标能力允许无审批新增/日期追加，保留原文，可补轻量元数据；既有内容不得未经明确授权删除、覆盖或改写。Journal 不等于 Knowledge；转为长期正式知识仍经 Review 和用户批准。目标和生产状态不可混写，详见 CURRENT。

## 用户访问目标

V1 基本可用后，目标是通过现有域名/DDNS、路由器端口转发和 DSM HTTPS 直接访问 Agent 与 Dashboard；不要求先连接 WireGuard，也不为 SecondBrain 专门改造 AdGuard。公网接入按届时实际入口完成必要认证和访问验证，不作为当前普通业务开发的前置条件。

## 迁移前同步流程（历史说明）

此前项目代码与治理文档通过 NAS、Synology Drive 及 Google Drive 镜像流转，且曾以 NAS 为源头。该流程已由 GitHub 私有 Monorepo 取代，不再作为当前代码或基线文档发布规则。旧同步脚本和 NAS 副本仅供历史追溯；不得把旧镜像反向覆盖 GitHub 版本。NAS 运行服务及业务数据的现行事实仍见 Environment-Baseline。

## 工程治理与历史

日常读取遵循 Agent-Rules 的 FAST-EXEC；技术环境事实集中在 Environment-Baseline；业务契约分别在正式 Business Specification；历史、测试证据与演进只记在 Progress-Log；架构/业务/安全决策以 Decision-Log 唯一别名引用。详细阶段演进和已完成验收不在此重复。
