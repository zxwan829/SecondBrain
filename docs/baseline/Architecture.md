---
updated: 2026-10-14
status: current
type: architecture
---
# SecondBrain V1/V2 Architecture

## 稳定边界

- SecondBrain 文件是业务 Source of Truth；Hermes 是 Agent Runtime。**目标**为独立 SecondBrain Web App 作为唯一业务前端；目前生产仍为 Hermes Dashboard Plugin。不复制 Agent Runtime 或正式知识库。
- NAS 正式数据位于 `/volume1/SecBR/SecondBrain` 与 `/volume1/SecBR/KnowledgeAssets`。Private 单独隔离，默认不对 Agent/API 开放。
- 生产与测试插件身份、资源、入口和快照隔离；FE-4 已部署不等于所有业务模块已接通。
- 个人自用、业务优先、风险适度：目标使用 App 自有登录/Chat UI，服务端复用 Hermes Agent/Chat/Session/Skill API；保留人工 Promote、Private 隔离、审计恢复，不引入企业级认证或第二运行时。

## 开发仓库与职责边界

- 私有 GitHub Monorepo `zxwan829/SecondBrain` 是 SecondBrain 代码与正式项目文档的唯一权威源。iMac 在 `/Users/joe/Documents/Codex/SecondBrain` 开发；MBA 使用自己的独立 Clone。开发和本地测试不依赖 NAS 在线。
- NAS 仅负责 Docker 服务、运行配置和业务数据。Docker 项目根为 `/volume1/docker/secondbrain/`，Core 构建上下文为 `/volume1/docker/secondbrain/core-source/`；业务数据位于 `/volume1/SecBR/SecondBrain/` 与 `/volume1/SecBR/KnowledgeAssets/`。
- Obsidian 知识库继续由 Synology Drive 在 Mac 与 NAS 间双向同步，仅承载知识库、笔记、个人资料和适合阅读的参考资料，不承载源码或正式开发文档。实际双向文件传播尚未单独验收，客户端“已为最新”状态不能替代传播测试。
- ChatGPT 负责架构设计、任务分解、技术决策和验收标准；Codex 负责实施、测试、Git 操作、按授权部署及执行反馈。标准流程为 ChatGPT 读取 GitHub 状态并规划，Codex 开发测试、更新必要文档、Commit / Push，随后 ChatGPT 读取最新结果。
- GitHub Push 不会自动部署到 NAS；NAS 不要求直连 GitHub。取得部署授权后，由 Mac 通过 SSH 传入部署内容并验证运行。开发、构建、部署和生产数据操作保持分离。
- 迁移前 NAS / Synology Drive / Google Drive 项目文档镜像、旧 NAS 治理写入与发布流程、旧开发目录及治理快照均已退役/清理，不定义当前版本管理或文档发布机制。有效运行事实与回滚资产见 Environment-Baseline。

## 当前运行架构（已部署）

Hermes Dashboard Shell → SecondBrain Dashboard Plugin → 认证 API/薄适配层 → SecondBrain 文件只读数据与 Hermes 原生 Chat/Session 能力。

正式插件为 `secondbrain`，页面 `/secondbrain`；前端 React + TypeScript + Vite，复用 Hermes Plugin SDK/宿主 React。Home API 提供受限语义读；不能将文件名/目录列表推断为业务状态。当前模块语义与缺口由 00-CURRENT 和 Environment-Baseline 维护。

## 目标架构（D074，已选定；首阶段代码已本地实现，生产未部署）

- **两容器、同一 Compose：** `secondbrain-app` 负责独立 React Web App（含 Chat UI）、静态托管、Core 业务/API、单次登录、审批与 Hermes BFF 适配；`secondbrain-hermes` 只提供内部 Agent/Chat/Session/Skill 能力。浏览器只访问 App 单一 Origin，Hermes 内部凭据不交浏览器。复用 FE-4 视觉与全部现有功能，不依赖 Hermes Dashboard 页面。
- **V1：** 标准版 NAS 内网 HTTP IP+端口；本人 `http://192.168.3.27:9119`，外出经 Home-WG 访问同址。**V1 验收必须同时覆盖** DSM LAN-only `https://zxwan520.com:63012` 的登录、Chat 流式、采集、Review/审批与知识功能，确保本人 V2 无应用架构返工。
- **V2：** 本人另行配置 AX3600 转发及 DSM HTTPS 公网入口，指向同一 App HTTP 端口；标准客户公网方案为增值部署服务，不内置 HTTPS/证书签发/反代或额外网关容器。外网开放仍须单独核验身份认证、网络可达和安全策略。
- **权限：** App 会话与受控 Core 审批独立于 Hermes Agent；查看 Review 后点击确认即可，无第二密码/生物识别；服务端校验会话、来源、文件哈希、幂等与审计。Hermes 无审批密钥和 Knowledge 写权；Private 不挂载。单纯点击不宣称可密码学证明真人。
- **Personal OS 扩展边界：** 前端沿用可配置的导航项和 route 字段，由各业务页面独立实现；登录、Shell 和导航不绑定 Chat/Review。Core 是模块化单体，各模块通过独立 API 和业务服务扩展，不新增容器/数据库/插件平台。当前单用户策略由服务端 `require_action(action)` 授权 seam 统一执行 owner 校验；不实现 RBAC。Knowledge Promote 与未来普通业务写操作分开授权：Memo、Calendar、新闻订阅等经授权 API 可按业务规则 CRUD，不进入 Knowledge 审批流。AI 定时任务优先调用 Hermes 原生调度，Core 保存用户配置/业务状态并做必要权限检查。
- **当前首阶段实现：** 独立 React/Vite 入口、同源 SPA 静态托管、App 登录会话、Home/Review 文件读取、Review 状态 API、Hermes Sessions/Run/SSE/stop BFF 与前端 Chat 已在本地代码完成。适配器按 Hermes v0.21.5 上游固定提交 `749220ef` 统一 `data` 列表、嵌套 `session.id` 和 JSON SSE 事件，并实现 Run 状态恢复；前端 typecheck/build 与 Core 21 项测试通过。尚未部署或完成实际 Hermes Chat 联调。
- **NAS API 只读现状（2026-10-14）：** v0.21.5 API 进程在 Hermes 容器内 `127.0.0.1:8642` 有监听，health 200，未认证 sessions/capabilities 返回 401；loopback 绑定不能供 App 容器调用，且未配置 App 可用的服务端 API key。生产 Compose 服务名为 `hermes`，网络为 `secondbrain_default`。需要单独批准后，才能最小配置内部 API 监听/密钥并验证两容器通信；无需增加端口映射。
- **迁移门槛：** App 代理只信任逐个核实的 DSM peer IP，拒绝通配或网段信任；精确 Origin/Host 校验与代理 HTTPS scheme 下 Secure Cookie 已通过离线测试，DSM 正式代理链及浏览器回归仍待部署后验证。未通过不切生产端口、不启动 Promote、不改 DSM/PBR/WG/AdGuard。NAS UID/GID 1026:100、Hermes API 服务名和 Secret 所有权要求已写入候选配置；生产变更另行授权。

## Core 现状与历史集成方式（目标已由 D074 更新）

原 D066 以 Hermes Dashboard 为产品宿主；D074 改为 App 自有前端/登录，Core 作为 App 内业务与 BFF 层、Hermes 作为独立 Runtime。现有已部署功能和审批测试资产保留。2026-10-13 一次性非交互 sudo 只读查询确认两个服务均在现有 Compose Project 运行，Core healthy；Hermes running。D071 同源 Hermes Session 只读 Review API 已在正式 FE-4 v0.2.4 部署，并完成用户 HTTPS Edge 列表及详情验收；Core 写入/审批尚未正式部署。按 D068，Hermes 与 Core 正式归属 Container Manager 现有同一个 SecondBrain Compose Project，Core 作为新增 service；两个容器仍保持独立权限、挂载和认证边界。`compose.core-isolated.yaml` 仅为隔离测试候选，不能作为独立正式项目部署。V1 完整可用前不进行商业发行包、代码/数据/密钥/环境参数化整理。

Core 的模块边界对应业务能力：Capture、Review/Promote、Knowledge、Journal、Projects、Calendar。模块共享一个应用进程/部署单元并通过显式接口协作；不新增独立数据库、LLM、n8n、第二 Runtime 或独立管理后台。只有已实现模块建立代码，不创建空占位包。

**CORE-0 隔离工程基础（已实现并测试，未部署）：** `web-app/secondbrain-core/secondbrain_core/modules/review_promote/` 收纳 Review Adapter、审批校验、幂等记录、Promote Worker 与 HTTP Router。Promote 在 Core 同进程完成，不使用跨容器审批队列。29 项隔离测试在此前阶段通过。当时源码、测试与 `CORE-0.bundle` 曾放入 NAS 项目资产；此为迁移前归档事实，不改变当前 GitHub 仓库的代码权威地位。

**CORE-1/2 身份与审批边界（CORE-2 隔离实现，未部署）：** Hermes v0.21.5 Basic Auth 中间件验证 session 后写入进程内 `request.state.session`，`/api/auth/me` 返回该身份；但生产 Hermes 以 root 运行、Basic Auth 密码在容器环境中且普通 Agent/Shell 共用该进程边界，因此 Hermes Cookie 转发或 Core 回查都不能证明是本人审批。v0.21.7 RC 的 `/api/auth/me` 在 loopback 模式可返回 token 校验后的合成 `user_id=local`、`provider=loopback`，该身份绝不能提升为人工批准。

经 CORE-2 核验，Hermes 与 Agent Runtime 共用的执行/凭据边界不足以单独证明“用户亲自批准”；因此 D073/D074 不把 Hermes Session 当成审批凭据。D074 首阶段本地代码改为 App 自有一次登录会话，服务端以私有口令文件验证登录、签发 HttpOnly/SameSite Cookie，并在变更请求验证精确 Origin/请求 Host；Core Promote 只接受该 App 会话，前端不能传身份，Promote 默认关闭。离线测试已验证无 App Cookie/跨站来源不能批准，Hermes API key 只由服务端持有。**这只证明本地代码路径，不证明未来生产 Agent 进程无法取得 App 凭据或伪造浏览器会话**；须在部署时把 App password/API key 与 Hermes 隔离并验证普通 Agent 工具无法读取或调用 App 凭据。未经该验证不开放生产审批。D067/D072 的二次解锁方案为历史选项，被 D073 的产品要求取代；保留历史实现，不删除安全校验。

**CORE-4 DSM HTTPS 入口（已配置，浏览器与生产审批联调未收口）：** 复用现有 `zxwan520.com` / `*.zxwan520.com` 证书，新增 `zxwan520.com:63012` → `192.168.3.27:9119` Dashboard 规则及 `zxwan520.com:63013` → `127.0.0.1:9120` Core 预留规则。两者绑定 `SecondBrain LAN-only` profile（允许 `192.168.3.0/24`，拒绝其余 IPv4 与 IPv6），不启用 HSTS；Dashboard 原 HTTP 入口保留。规则按主机+端口，不支持本次已验证的路径转发。Mac 局部解析下 TLS 验证通过：Dashboard 返回 302 登录重定向；临时回显测试曾证明 Core 代理链可达。当前 Compose 中 Core service healthy；Promote 仍关闭、Knowledge 仍为 RO。63013 仅为 LAN-only Core HTTPS 入口，不代表生产 Promote 已启用。临时回显服务的 Origin/Cookie 测试通过，但不是正式 Core 浏览器审批联调。用户已报告在真实 Edge 登录并访问 Dashboard HTTPS；D071 Dashboard Review 列表/详情已由用户在 HTTPS Edge 实际验收，无 Core 二次解锁。DSM profile 配置与绑定已核实；NAS loopback 请求返回 302，不能作为非 LAN 拒绝测试。路由器静态配置及活动 nftables 未发现 63012/63013 DNAT。

Core 启动将 Uvicorn `X-Forwarded-*` 信任限制到 `SB_TRUSTED_PROXY_IPS`；应用校验精确 `SB_CORE_ALLOWED_HOSTS`。本次临时回显发现 DSM 保留客户端可影响的 `X-Forwarded-For` 和 `X-Forwarded-Host`，但将 `X-Forwarded-Proto` 设为 `https`；客户端伪造 Host 得到 404。Core 必须只信任可信本地代理连接，并拒绝或安全解析可伪造的转发头；不得以这些头授予权限。

**Core 文件边界（Compose 已配置，Core 生产写入关闭）：** 2026-10-13 运行时核验确认 Core `1026:100`、Review/Knowledge RO、Core state RW、secret RO、`SB_PROMOTE_ENABLED=false` 且 healthy。Hermes Knowledge RW 子挂载已按批准范围移除，仅通过 `/secondbrain` RO 读取；三个捕获路径仍 RW，精确 safe-root 及终端 RO 写拒绝均已实测。Core Knowledge 在本阶段保持 RO。`compose.core-isolated.yaml` 仅为隔离测试候选，不能独立部署。此前隔离目录测试中，Hermes root 在 RO mount 下写入失败，Core UID 1026 可按模拟授权写 Knowledge/state，这不是生产切换验收。

生产 Promote 仍 **BLOCKED**：Hermes 权限收窄已部署并验证；Core 为 `1026:100`、Knowledge/Review RO、state RW、secret RO 且 Promote=false；Private 未挂载。D074 App/Core 首阶段仅本地实现，未部署；Core Knowledge RW、生产 App 密钥隔离、可信代理头/HTTPS 与 Agent 越权拒绝仍未验证，生产 Promote 部署须另行授权。Hermes 重建后 Dashboard 原生 Chat 在两个浏览器标签持续重连，虽 Health 200、Gateway Running，仍是待单独排查的功能异常。不得以恢复 Hermes Knowledge RW 作为常规回滚。

## 数据区域与写入生命周期

- `00-Inbox` / `KnowledgeAssets/00-Inbox`：原始捕获和原始证据；Raw 不被派生内容替代。
- `10-Review`：待用户审核的候选内容。
- `20-Knowledge`：用户确认后 Promote 的正式长期知识。
- `30-Projects`、`40-Memory`、`50-Journal`、`90-Archive`：各自业务区，普通 Agent 无通用根目录 RW。
- 基本知识流：Input → Raw → Review → 用户批准 → Promote → Knowledge。失败需保留可恢复的原始/Review 证据。

Hermes 当前无 Knowledge RW mount；普通 `write_file`/`patch` 被 safe-root 拒绝，terminal 写入受 RO mount 拒绝。Core service healthy 但 Knowledge 仍 RO、Promote 关闭；生产 Promote 仍因统一审批授权及 Core 写权限部署未完成而 **BLOCKED**。Journal 目标规则支持专用新增/追加，但生产挂载尚未开放。状态以 00-CURRENT 为准。

## Universal Capture

微信与 Web App 均是 UC v1.1 定义的 V1 输入渠道，统一流入 Raw→Review；生产微信端到端接入未验证。当前唯一 Runtime 路线为 Hermes；OpenClaw 已由 D073 退出当前候选。微信聊天与附件具体交互在实现前依据正式规格和可用能力界定，不擅自视为已完成。


输入、元数据、失败/重试与验收以 canonical `Universal-Capture-Business-Spec.md` 为准。V1 MUST 输入是文本、URL/Web、PDF、Image/Screenshot、Audio/Voice；原始证据需保留，输出到 Review 并等待人工批准。Office 文件、Video、通用二进制及语义检索/去重等按规格延期。禁止把架构摘要作为第二份业务契约。

## 前端与业务规格

生产仍使用 Hermes Dashboard Plugin；独立 React Web App 首阶段已在本地代码承接 Home、Review 和 Chat 导航/页面，生产尚未切换。目标仍需完整承接所有 V1 业务页，FE-4 视觉与已验收能力不得退化。数据仍区分 REAL/DEMO/UNAVAILABLE，不得将测试或假数据冒充真实。

Web App 详细产品契约见 `SecondBrain-Web-App-V1-Business-Spec.md`。Home 与 Calendar 是聚合层，模块注册可扩展；业务页不必共用 Home 布局。写入能力必须由服务端语义接口、allowlist 和明确审批控制，不能仅凭 UI 按钮或模型声明授权。

## Journal

`50-Journal` 用于随手记、备忘录、碎片想法、日常记录和用户明确要求保存的语音转文字。目标能力允许无审批新增/日期追加，保留原文，可补轻量元数据；既有内容不得未经明确授权删除、覆盖或改写。Journal 不等于 Knowledge；转为长期正式知识仍经 Review 和用户批准。目标和生产状态不可混写，详见 CURRENT。

## 用户访问目标

V1 内网及 Home-WG 使用 App HTTP，受限 DSM HTTPS `63012` 做全业务兼容验收；本人 V2 才启用公网反代/转发。客户标准交付只包含 LAN，外网接入另计服务；不改 AdGuard/PBR/WG，也不为不同 NAS 开发产品分支。

## 迁移前同步流程（历史说明）

此前项目代码与治理文档通过 NAS、Synology Drive 及 Google Drive 镜像流转，且曾以 NAS 为源头。该流程已由 GitHub 私有 Monorepo 取代，不再作为当前代码或基线文档发布规则。旧同步脚本和 NAS 副本仅供历史追溯；不得把旧镜像反向覆盖 GitHub 版本。NAS 运行服务及业务数据的现行事实仍见 Environment-Baseline。

## 工程治理与历史

日常读取遵循 Agent-Rules 的 FAST-EXEC；技术环境事实集中在 Environment-Baseline；业务契约分别在正式 Business Specification；历史、测试证据与演进只记在 Progress-Log；架构/业务/安全决策以 Decision-Log 唯一别名引用。详细阶段演进和已完成验收不在此重复。
