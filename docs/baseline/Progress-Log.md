# Progress Log

## 2026-11-09 — WP5 412 缺失资源修复部署与生产复验待登录

- **根因与修复：** 复核生产错误 `Note references a missing BlockSuite resource` 后，发现恢复副本生成的 fenced/inline Markdown code 中保留源笔记旧资源链接；Core 将 code literal 误判为新笔记的活动 BlockSuite 引用。PR #316 的 NotesStore 共用引用扫描现在忽略 fenced/inline code 中的引用；真实正文里的活动缺失资源仍在写入前以 409 拒绝。加入 Core 正/负例及前端恢复 fork 负例（缺 Blob 时不创建伪新笔记）和合成资源/yjs 正例。
- **工程门禁：** PR #316 head `726673185d29d6686408455d35bbb3f331200a3b1` 独立 Review PASS、无 P1/P2；固定 SHA Linux Chromium Gate [Actions #42558941565](https://github.com/zxwan829/SecondBrain/actions/runs/42558941565) PASS，覆盖 Core 回归、前端 fork 测试、typecheck、production build、artifact 脱敏和 Notes Chromium probe。修复合并为 `3d2a4e9735ebac9878337ebd810aab5c09c4c795`；当前 main tree `74b6c2f65c782a9322ac48d5a3bed2fcf66a8346`。相对 PR #313 候选，应用源码只增加本修复及其测试；没有启动 WP6。
- **App-only 构建/部署：** NAS 以 main SHA 生成 `web-app` archive，SHA-256 `b47634568dfa0503f4dd2cf903dd3389d2553c83801279182f6f074aa2dc58fd`。候选 tag `secondbrain-app:candidate-3d2a4e9735ebac9878337ebd810aab5c09c4c795` 的 revision label 匹配 main SHA，Image ID `sha256:2dc7793d36a4397a4c7f53cf22ad058a5f6c7afcd32076757e42f542965cc6e0`、平台 `linux/amd64`。镜像构建内 typecheck/build PASS；隔离无网络、只读 rootfs smoke 的 `/health` 和 `/notes` 均 200。
- **回滚与生产：** 切换前快照 `/volume1/docker/secondbrain/rollback/wp5-412-fork-predeploy-20261109T040038Z/`（`0700 root:root`，内部文件 `0600 root:root`，校验通过），旧 App 镜像 ID `sha256:6e2f2c14d5c434d6217626b254a874a98e07cef975ba5d6e76cf11646d377bc9`，旧 Compose SHA-256 `2cc49e2b16c3a9322398b7021d39d7da948f3d56c9f42a010d31ef21500179e3`。部署时 Compose 只修改 SecondBrain App image 行；App-only `--no-deps --no-build --force-recreate` 后新容器 healthy、RestartCount 0，HTTPS `/health`、`/`、`/login`、`/notes` 均 200。Live Compose SHA-256 `f25599072f15c2c989029aa2ff7728a9bcef6b307bc168cf0eceeffbcd4b5130`。Promote=false、Weixin 未启用、Knowledge RO、Private 未挂载、Secrets RO、Hermes identity/image/start/restart 未变化。
- **生产交互状态：** 修复后浏览器刷新导致登录态过期并显示登录页，Edge 密码管理器扩展弹层阻止继续自动化；因此修复后的真实生产编辑/恢复旅程尚未运行。旧镜像下的 412 fork 失败是问题来源，不代表新镜像失败或通过。没有触碰真实笔记/Vault/Obsidian，也没有调用模型。当前 `ENGINEERING_PASS / DEPLOYED / PRODUCTION_TEST_PENDING_LOGIN / USER_UAT_PENDING`；等待重新登录后完成生产合成 Notes 与 412 正/负例，再等待用户最终体验确认。

## 2026-11-09 — WP5 最终 Notes UX App-only 部署与生产合成交互验收

- **部署源码：** PR #313 候选 `b68c1cfe61bc92a3aa966821cc02aaa7ca35ffda` 已通过独立 Review、四条 Linux Chromium Gate、typecheck、production build、trace 脱敏与 Native Notes 独立 build；候选 tree `18863acd770457255b12e2fa4c7c00062dbd35bc` 与 merge commit `c76b06f725a5eab02b88866515d6d9943d5df163` 一致。PR #312 部署记录文档合并为 main `3ac9c8c73d32cd090027f12457491721ab2c03e4`；相对 #313 合并 tree 只有 `00-CURRENT.md`、`Environment-Baseline.md`、`Progress-Log.md` 差异，`web-app/` 与 `.github/` 无差异。
- **切换前检查与回滚：** 实时确认旧 App 镜像 `sha256:533660ecd3dcdc67fd2ab309390dc9bd09ea2f3397fde0ac55537759d52d3229` healthy、Hermes identity、当前 Compose 和 App-only 配置。切换前快照 `/volume1/docker/secondbrain/rollback/wp5-notes-final-predeploy-20261108T181339Z/`，目录 `0700 root:root`、Compose 与 image tar `0600 root:root`；Compose SHA-256 `ecd61561d45e14227c18cff614bbd017cd10506bf0ac37456db3df1ec1bd45d2`，旧 image tar SHA-256 `d43061ebc5aee33a6f330650cbb1859065461e7771cbf636312aa5cdba447f46`。未使用凭据暴露 helper。
- **App-only 部署：** NAS 仅更新 Compose 中 `secondbrain-app` image 至 `secondbrain-app:candidate-3ac9c8c73d32cd090027f12457491721ab2c03e4`，执行 `--no-deps --no-build --pull never --force-recreate --wait`。部署源码输入 SHA-256 `e0cf1e5cf73f8378ca890965401fc3f8c3f57477eec45231b474637d775ffb06`。新镜像 ID `sha256:6e2f2c14d5c434d6217626b254a874a98e07cef975ba5d6e76cf11646d377bc9`，revision label `3ac9c8c73d32cd090027f12457491721ab2c03e4`；App 容器 `6cea3d5c44d694a093534d7dfcd9ce8916cc1be2de41e5fb6928c0288c15aa56` healthy、RestartCount 0。Live Compose SHA-256 `2cc49e2b16c3a9322398b7021d39d7da948f3d56c9f42a010d31ef21500179e3`，相对快照仅 App image 行改变。
- **安全与健康验证：** `/health`、`/`、`/login`、`/notes` HTTPS 均 200，health JSON 表示 `status=ok`、`promote_enabled=false`、`hermes_configured=true`。Hermes 容器、镜像、StartedAt、RestartCount 未变；App UID/GID `1026:100`、只读 rootfs、no-new-privileges、Knowledge RO、Private 未挂载、现有 Secrets RO、端口和其他配置不变。未改其他容器、Secret、ACL、挂载、网络、Vault、Obsidian 或业务数据。
- **登录态生产合成交互：** 用户在 Edge 手工登录后，本轮只创建/操作 WP5 合成 Draft，未打开或更改已有笔记。新建直接进入 Notes 内嵌 BlockSuite，不显示弹窗；标题 `SB-WP5-PROD-20261109-A7F1` 唯一，正文包含两段中文。浏览器逐字输入、Enter 分段、Backspace、撤销/重做、保存、返回、重开和整页刷新均通过；实际 OS 输入法未测试。六点手柄、加号可见；加号菜单可打开；手柄拖动两段换序并拖回，保存刷新后顺序正确。普通表格插入及合成单元格写入通过。另建纯合成 Markdown Draft 验证 Database/Kanban（2 组、3 卡片）保存刷新重开；Edgeless 画布便签写入、保存与刷新重开通过。
- **412 与安全恢复：** 同一合成 Rich Page 在两个登录态标签加载；第二标签保存 `REMOTE-SAVE REMOTE-2`，第一标签以旧版本追加 `LOCAL-UNSAVED` 后保存，UI 返回 `版本冲突（412）` 并明确显示远端与本地均保留、Core 未覆盖。界面成功下载完整恢复副本（状态说明含 Yjs update、快照、引用画布和图片）；刷新后远端内容保留，本地冲突标记未写入远端。随后尝试备用“另存为新笔记（保留原件）”，失败并显示 `Note references a missing BlockSuite resource`；没有确认该 fork 成功。这是本轮发现的生产交互缺陷，保留完整下载恢复副本与远端版本，不宣告备用 fork PASS。
- **部署后健康与安全复核：** `/health`、`/`、`/login`、`/notes` 为 HTTP 200；health `status=ok`、`promote_enabled=false`、`hermes_configured=true`。App Image ID `sha256:6e2f2c14d5c434d6217626b254a874a98e07cef975ba5d6e76cf11646d377bc9`、revision `3ac9c8c73d32cd090027f12457491721ab2c03e4`、RestartCount 0、healthy；Hermes image/StartedAt/RestartCount 不变；Promote 关闭、Weixin 未设置开启，Knowledge RO、Private 未挂载、Secrets RO。未读取 Vault/Obsidian、未调用模型、未修改其他容器或安全配置。
- **交付状态：** `ENGINEERING_PASS / DEPLOYED / PRODUCTION_TEST_PARTIAL_RECOVERY_FORK_FAILED / USER_UAT_PENDING`。生产主体交互和下载恢复副本通过，但备用 fork 恢复失败；用户真实体验仍待确认，不标记 `USER_UAT_PASS`。状态文档更新 PR #314 仍 OPEN。工作包 6 未启动，未追加视觉精修。

## 2026-11-09 — WP5 最终 Notes UX 合并与 App-only 部署前置阻断

- **工程合并：** PR [#313](https://github.com/zxwan829/SecondBrain/pull/313) 固定候选 `b68c1cfe61bc92a3aa966821cc02aaa7ca35ffda` 已按预期 head SHA 合并，merge commit `c76b06f725a5eab02b88866515d6d9943d5df163`。main tree `18863acd770457255b12e2fa4c7c00062dbd35bc` 与候选 tree 相同，确认八项修复及其经过验证的代码进入 main，没有额外源码差异。
- **门禁复核：** 固定 SHA 上四条 Linux Chromium Gate #42497477160 / #42497475747 / #42497731848 / #42497920166 均 SUCCESS。三个 `synthetic-browser` job 的 Web regression/typecheck、production build、artifact trace redaction 均成功；Native Notes job 也完成精确 SHA 检查、前端 build 和独立 Chromium journey。PR 独立只读 Review PASS、无 P1/P2。没有重复运行工程回归。
- **部署前置检查与停止原因：** NAS SSH 专用别名成功连接，远端 `Joe` 为 UID 1026，归属 `users` 和 `administrators`；Compose SHA-256 与最近 2026-11-08 快照相同。NAS Docker CLI 虽可执行，但调用 daemon 返回 `permission denied`；Docker socket 是 `root:root 0660`。相关 rollback 目录为 `root:root 0700`，只能看到目录名称，无法核验即时快照、旧镜像、运行容器、镜像 ID、健康状态、挂载和安全开关。因无法完成必要的实时检查和回滚准备，立即停止；不使用 sudo/helper，不改生产文件或容器。
- **生产与用户验收边界：** PR #313 的修复未部署，本次新版本生产合成测试 `NOT RUN`；2026-11-08 对 PR #311 App 镜像的生产运行/合成验收仅是旧版本历史证据，不覆盖新修复。状态为 `ENGINEERING_PASS / NOT_DEPLOYED / PRODUCTION_TEST_NOT_RUN / USER_UAT_PENDING`。既有 `USER_UAT_FAIL` 仍是问题来源，不宣称用户验收通过。访问入口此前记录为 `https://zxwan520.com:63013/notes`，本次未探测。
- **后续条件：** 用户已授权 App-only 更新，不需要重复申请该授权；继续前只需通过受支持、最小权限的部署路径使 App/Compose/镜像/回滚资产可实时核验，并确保可保留既有 Hermes、真实 Vault/Obsidian、其他容器、Secrets、ACL、挂载、网络和安全开关。获得该访问能力后按本授权继续，不启动工作包 6、不扩展视觉范围。

## 2026-11-08 — WP5 / PR #309 Database Kanban DOM 根因与修复

- **真实 Chromium 诊断：** 独立 Linux Chromium DOM 探针 [Actions #42455661925](https://github.com/zxwan829/SecondBrain/actions/runs/42455661925) 在产品修复候选 `033cd86e440294a6b4d0a7ac3785394093826978` 上，不通过正式 Playwright runner 直接读取 synthetic Database：新增看板后 `currentViewId` 与 sessionStorage `blocksuite:databaseBlock:view:currentViewList` 的 viewId 一致；DOM 有 2 个 Kanban group、3 个 card 节点，实际“测试记录”卡片含“仅供体验”和“进行中”；关闭重开及整页刷新后上述视图、分组、卡片、Yjs 数据仍在。该探针只输出诊断日志，不生成/伪造正式验收产物。
- **根因与定向修复：** 归档 `views-view.ts` 的 `addView()` 原先 `viewAdd()` 后调用 `setCurrentView()`，却遗漏现有 `onChangeView(id)` 持久化回调；创建视图后只在当前内存显示，资源重新挂载会回到表格。现新增该回调，并更新 overlay SHA manifest。随后正式 gate 在 `bec587d` 失败于卡片文字断言；失败诊断和截图显示看板确实渲染。独立探针枚举 DOM 发现卡片列表前两个是空占位节点，含“测试记录”的节点不在首位；将初始、资源重开、整页刷新三处 locator 改为按实际卡片标题过滤，保留原有文本断言。
- **验证：** 最终代码候选 `b860c6eb5ebd5516a1bd43e5d27081bdad7e07ca` 上，正式 Linux Chromium [Database roundtrip #42456639973](https://github.com/zxwan829/SecondBrain/actions/runs/42456639973)、[归档 UX #42456782309](https://github.com/zxwan829/SecondBrain/actions/runs/42456782309)、[Rich Page/Edgeless 模式 #42456784526](https://github.com/zxwan829/SecondBrain/actions/runs/42456784526) 均 PASS；每次均执行 frontend regression/typecheck、build、原有产物脱敏门禁和 Chromium journey。独立 probe #42455661925 PASS。本地归档准备、typecheck、32 项 `rich-page-projection` / `NotesPage` 测试、production build、Playwright test discovery、`git diff --check` 均 PASS。
- **交付边界：** 修复和测试选择调整已推送到 PR #309；独立 Review 尚未完成，PR 未合并。没有修改 NAS/生产、真实 Vault、数据/权限或正式 CI 诊断产物门禁；生产部署与用户 UAT 均未执行。

## 2026-11-06 — WP5 / PR #294 Markdown 集成工程验收

- **合并与范围：** PR [#294](https://github.com/zxwan829/SecondBrain/pull/294) 已合并，merge commit `e9f323b3f90d53473964fe991a968fcd046d85bf`；固定候选 HEAD `8ce5a5e7559f8cfea5345ccf21ed0bb1a1a31f2a`。未修改 NAS、生产容器/配置/权限、真实 Vault 或业务数据；未调用付费模型；工作包 6 未启动。
- **完整浏览器与回归：** Linux Chromium 全旅程 [Actions #42201007416](https://github.com/zxwan829/SecondBrain/actions/runs/42201007416) 于精确 SHA 完成，JUnit 3 tests、0 failures、0 skipped：桌面 1440×1000 29.652s、平板 820×1180 10.492s、手机 390×844 13.355s。真实 localhost Core HTTP + local Vite，Hermes 使用 fixture-only Chat，Knowledge 文件数 0、Promote=false；输出摘要 PASS，未发布截图。Build/typecheck/regression 与 artifact 脱敏步骤通过；PR build-and-smoke [Actions #42201001485](https://github.com/zxwan829/SecondBrain/actions/runs/42201001485) 通过。额外定向前端测试 29 passed，typecheck 通过。独立 Review PASS。
- **失败原因与修复：** 先前固定 SHA `fe1e5ebc` 的浏览器执行在约 30.9s 处触及 Playwright 全测试 30s 限时；脱敏诊断和截图已到达 Setext 安全回退及源码保留断言，没有显示 Core 写入。只将包含完整桌面旅程的用例总预算调至 60s，没有改动单项等待、选择器、断言、视口或业务代码。后续固定 SHA 全 Gate PASS。实际浏览器确认活动 BlockSuite 编辑器对 Setext 触发 fallback，正文含标题和 `===` 被旧编辑器安全源码视图保留，精确合成 Draft 没有 Core PUT；其后隔离冲突/412、外部内容保留、恢复保存和 API 回读仍执行并通过。冲突专项此前已由 PMO 接受，不在此重复排障。
- **依赖风险评估：** `npm audit --omit=dev --json` 在锁文件报告 58 项 vulnerability records：50 High、4 Moderate、4 Low、0 Critical。主要 High 为 Zod 3.25.76 依赖链对应 [GHSA-mrhx-c7xc-m3w5](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5)：攻击者提交不受长度限制的大数组使 Zod 累积过多校验错误、耗尽内存，修复版本为 Zod 4.6.6；该重大版本升级当前无可用兼容性修复（`fixAvailable=false`）。相关 Zod 位于新增 BlockSuite 前端依赖图，编辑器为懒加载客户端 chunk。当前没有证据证明用户控制内容会进入该漏洞所需的 Zod 数组 schema；因此不把审计告警直接等同可利用漏洞。此风险不阻止非生产 PR 合并，但**生产部署前须完成兼容修复，或对实际可达路径完成评估并作明确安全风险处置**。审计还列出 Vitest mocker、uuid 等依赖告警，需随正式发布前依赖处置一并复核；本轮不强行升级以免破坏兼容。
- **阶段结论：** `WP5_MARKDOWN_INTEGRATION_ENGINEERING_PASS`；集成只证明隔离 Core/合成数据闭环，不表示真实 Vault/Obsidian 同步、生产部署或用户 UAT 通过。保持 Promote/Writer/Private/Weixin 及 VNext 冻结；唯一后续由用户决定是否授权真实 Vault 验收或生产发布，本轮不启动工作包 6。

## 2026-11-06 — #287 工程收口：Chat Task 查询与更新合并

- **实现与修复：** PR #289 已合并（`deab530b13ee755609a9375ee22449913ef1ed4a`），交付 Chat→Inbox→Journal 的显式收录与独立 Journal 审批链。后续 PR [#291](https://github.com/zxwan829/SecondBrain/pull/291) 合并（`814c04b7abb343620014da65d83c9f1b075b4141`），补齐今天未完成 Task 查询、按唯一精确标题完成及修改截止日期。Task 更新使用既有专用 API、task.write、乐观版本和幂等键；异步投影可从原子 Task 账本恢复。独立 Review 发现并促使修复一个会话归属缺陷：同 key 但改变 Session/原命令原本可能返回错误归属活动；现将二者纳入 Chat-scoped fingerprint 与原子记录，异归属重放 409。
- **验证与复审：** 前端 Capture/Task 定向套件 96 passed，Core BFF + Task Store + projection 套件 55 passed；typecheck、build 通过（既有大 chunk 提示）。独立 Reviewer 最终 PASS。Ubuntu 24.04 Chromium Gate [Actions #42080651081](https://github.com/zxwan829/SecondBrain/actions/runs/42080651081) 在固定源码 SHA `d4b0ee62a354499ae51f0d89b21d0362a0df3c79` 全部通过，包含前端回归、Core+Web 浏览器合成旅程和 artifact 脱敏；构建工作流校验了实际 checkout SHA。#289 Gate [Actions #42076994861](https://github.com/zxwan829/SecondBrain/actions/runs/42076994861) 亦通过。
- **状态边界：** #287 工程目标 `WP4_ENGINEERING_COMPLETE`。输入解析为有限、明确的消息开头命令，不代表真实模型自然语言理解；真实模型、NAS/Obsidian 同步、生产写入及用户业务 UAT 均 `NOT RUN`。本轮无生产修改、无付费模型调用、无 Vault/真实业务数据访问；#30 仍 `PARTIAL` 且剩余 4 Run 不结转；#277 生产 Notes/Journal UAT 仍 `PARTIAL`，同 key replay 未执行。Promote/Writer/Weixin 关闭，VNext FROZEN。唯一后续工作包按排程为 #46；本轮未启动。

## 2026-11-06 — #287 Chat→Inbox→Journal / Chat→Task 工程闭环

- **#30 状态切换：** `PARTIAL / LIMITED_REAL_MODEL_UAT`，6/10 Runs；剩余额度不结转，不再调用。因果归属与冲突处理仍 UNKNOWN/NOT RUN；不阻断本工作包。PR #277 生产 Notes/Journal 状态继续为 `PARTIAL`，未重跑生产验证。
- **实现：** Chat 对话新增明确、消息开头的中文 Journal/Task 请求表达；叙述性提及和无分隔符的模糊 Task 文字继续进入普通 Chat。Journal 意图先走现有 D086 Inbox 原文与持久化回读；完成条目现可进入精确单 Capture 审批页，复用现有 Journal proposal→单独 `approved_recorded`→绑定来源/版本的 `journal.append` 预览→用户确认执行，不直写 Journal API，不把 Inbox 同意等同 Journal 执行授权。Capture 单来源页只读取精确 ID，未启用 Notes 时仍可用；不枚举 Notes 或全量 Inbox。Task 创建复用现有 Task API 和幂等键，并保留原命令/失败重试。
- **验证与交付：** 前端 6 个定向套件 194 passed；`npm run typecheck` 与 Vite production build 通过（存在 >500 kB chunk 提示）；Core 定向 Inbox/Proposal/Journal/Task/BFF 回归 54 passed、38 deselected。独立 Review PASS；其提出的测试夹具 P2 已修复：合成执行端现在要求已批准 Journal proposal、`confirmed=true`、预览哈希和日期/正文完全匹配，并精确断言请求体；修复后集成文件 11/11 通过。GitHub Ubuntu 24.04 Chromium Gate [Actions #42076994861](https://github.com/zxwan829/SecondBrain/actions/runs/42076994861) 对固定 SHA `3f3c0d0752f638625a04fb55131bff279e2b2a72` 全部通过，含 Web 回归、typecheck/build、artifact 脱敏与隔离 Core+Web 浏览器验收；之后仅更新正式记录，应用代码未变，最终 PR HEAD 为 `355197c8c625b8ba66c5e38f4a60888813494e8f`。PR [#289](https://github.com/zxwan829/SecondBrain/pull/289) 等待合并。`git diff --check` 通过。测试使用合成响应与 Core 临时测试存储；没有 NAS/生产、真实 Vault/业务数据、付费模型、权限或配置变更。
- **边界/状态：** 本记录的 Chat→Inbox→Journal UI 集成旅程以合成 API 响应验证；Core Journal/Proposal/Task 的真实路由、持久化/幂等由既有临时存储 API 测试分别覆盖，不将它们合称生产端到端。真实 Hermes 自然理解与实际用户 Chat、NAS/Obsidian Journal 同步及生产 UAT均 `NOT RUN`；固定命令路由测试不代表真实模型自然语言效果。VNext 仍 FROZEN。

## 2026-11-05 — #30 跨会话真实模型有限 UAT（6 Runs）

- **通道与授权：** 用户确认 SecondBrain 与挂载 Knowledge 仅含测试资料，并允许通过现有 Core→Hermes 执行本次自然检索和 citation 元数据保存；不改 NAS 配置、容器、权限或补丁。活动模型 `zai-org/GLM-4.5-Air`，provider `custom`（SiliconFlow）。共发起 6/10 次获准 Run。本轮仅主动创建并审计虚构标记 `ZetaQuill-7391` 的记录；未主动读取其他记录正文、Secret、Private 或其他目录。用户确认环境内容均为测试资料；但生产 `instructions_for()` 可在正常 Run 中读取/评分已有 active memory，本轮未取得逐 Run 所选上下文，因此其他现存 memory 是否进入模型上下文 **UNKNOWN**。
- **实际模型结果（观察值，不证明单一记忆因果）：** (1) 保存偏好后，模型确认希望每条清单项以蓝色方块开头；(2) 新会话问“给我写一个 ZetaQuill-7391 的简短清单示例”，模型给出 `□` 方框清单但没有颜色，观察为 **PARTIAL**；(3) 无关火星奥林匹斯山问题正常作答，未提及偏好，观察为 **PASS**；(4) 用户将偏好纠正为清单前缀 `ZETA-STAR-7391`，模型确认新值替换旧值，观察为 **PASS**；(5) 新会话问同类清单项，模型实际以 `ZETA-STAR-7391:` 开头，观察为 **PASS**；(6) 撤销后新会话再问，模型表示缺少 ZetaQuill 上下文并请求说明，没有复述旧值或新值，观察为 **PASS**。这些输出是否由本轮目标记忆单独导致均 **UNKNOWN**，因为未取得逐 Run 选中上下文；冲突处理未运行。
- **存储核验：** 仅筛选唯一合成标记对应的记忆事件并输出元数据：3 条、同一记录 revision 1/2/3，operation `create → correct → revoked`，最终状态 revoked；没有读取或输出其他行正文。撤销后无 active 版本。
- **用量与费用：** 生产 Chat UI/Core 当前未向本次可见结果暴露逐 Run input/output token usage；账户余额/账单未读取。活动模型供应商页面列示 `$0.14/M` 输入、`$0.86/M` 输出，但缺少实际 token 数，故实际用量与费用 **UNKNOWN**；不以公开单价或估算冒充账单。只确认 6 个用户发起 Run，未从 API 取得 provider 内部可能的附加计费请求数。
- **结论与范围：** #30 真实模型观察 **PARTIAL**：输出层面纠正、纠正后召回、无关过滤、撤销符合预期；原始偏好漏了颜色，冲突测试未执行。因逐 Run memory context 未记录，不能把这些观察归因于目标记忆本身。未改代码或生产配置、未部署、未主动读取 Secret/Private 或其他记录正文；App/Hermes 保持原配置。用户已明确允许本轮 Knowledge 检索，PR #285 原“需另行授权”的阻断已解除。

## 2026-11-05 — #30 独立合成 JSONL 测试隔离（无生产/无模型）

- **固定开发基线：** GitHub `main` `10bf24bd8a182c80bb6513a5dca6b521bdf6f2ea`。生产最近记录 revision 为 `7272b7388d9453a4abe212e6aa8d528e7e0dcd82`；该 revision 与 main 的 Core runtime source diff 为空，本次未改生产运行代码。此前 PR #283 已将 `0/10` Run 与数据隔离阻断正式记录。
- **隔离入口：** 复用 `create_app()` 已有 `SB_PERSONAL_MEMORY_ROOT` 启动注入，不新增运行时配置或第二记忆源。集成测试在 `tempfile` 下预先创建权限 `0700` 且初始为空的 `isolated-uat/40-Memory`，使用 `patch.dict(..., clear=True)` 设置全部测试环境，之后才构造 Core；`app.state.personal_memory_store.root` 精确等于该临时根。测试在 Core 初始化前包装 `PersonalMemoryStore._read_events_unlocked`，逐次校验其 `self.path` 解析结果都位于该临时根，覆盖构造后的读取、写操作校验和 Chat 相关性筛选；唯一被读取的 JSONL 路径为该根下的 `personal-memory.jsonl`。
- **请求链与数据断言：** 经真实 FastAPI Core `/api/personal-memory` create/correct/revoke、`/api/chat/sessions` 和 `/api/chat/sessions/{id}/runs` 路由；只使用一条虚构 `ZetaQuill-7391` 偏好，事件文件仅 3 条、同一 memory ID、操作序列 create→correct→revoked。实际 Core BFF→HermesAPI 的 `/v1/runs` 请求由本地 `httpx.MockTransport` 截获（没有真实 Hermes 或模型请求）：相关请求 payload 恰含一条合成记忆；无关问题、撤销后的问题没有 `instructions`；纠正后仅含新文本，不含旧值。缺失 `SB_PERSONAL_MEMORY_ROOT` 或指向不存在目录时 `create_app()` 启动失败，测试未产生任何 `/v1/runs` 请求。
- **验证：** 隔离记忆相关测试此前为 **65 passed**。首次 GitHub Linux 完整 Core suite 暴露两处既有 Activity 测试断言遗漏已存在的 `review`、`promote` 来源；按 API 当前精确顺序更新来源期望，并让原六个可撤销来源的 I/O 计数只针对已仪表化存储。无生产逻辑变化、未删除断言。修正后本地完整 Core suite **657 passed、5 skipped、59 subtests passed**；隔离记忆及两处 Activity 集成定向组合 **67 passed**。`git diff --check` 通过。由于仅测试/文档改动，不需生产部署；无真实 Session/Memory 数据访问、Run、费用或配置变更。
- **模型与计费通道预检（只读静态证据）：** 当前有效 model ID、provider、账户余额和实际 usage 仍 `UNKNOWN`。`web-app/secondbrain-core/.env.example` 仅声明 Compose 内 `SB_HERMES_API_URL=http://hermes:8642` 与只读 Secret 文件路径模板；D078 config fragment 不选择 Chat 模型。Core `HermesAPI.capabilities()` 只取 `/v1/capabilities`，`get_run()` 的输出字段白名单不含 `usage`；SSE 虽透传事件，但仓库无证据证明实时 Chat 流包含可核验 provider 账单数据。唯一历史真实模型元数据见 Issue #30 comment `6228113053`：2026-10-17 一个旧 Run 记录 `zai-org/GLM-4.5-Air`、Provider `custom`，该 Run token/费用 UNKNOWN，不代表当前模型。现有 `.github/workflows/d077-hermes-live.yml` 是手动历史实验：跑官方 Hermes 临时容器并由 runner proxy 直连 SiliconFlow，脚本固定 `deepseek-ai/DeepSeek-V4-Flash`，直接调 Hermes `/v1/runs` 而非 Core BFF；最多 15 个合成 turn/60 provider requests，启用 background review，本地 `$0.22` 是估算软限而非供应商硬限额。它不满足当前≤10 Run 限额，也不验证 Core 真实链路；本轮未执行。
- **下一步边界：** PR #284 已合并（`ec053b46913cbd9d80a46da5f983b1419c144b72`）；隔离 Core→Mock Hermes PASS 不证明真实模型采用。当前缺少无需生产访问的有效模型/provider 与账户 usage 元数据，也没有现成的 Core→真实 Hermes 非生产路径。唯一后续为一次性读取当前生效模型/provider 的非秘密字段及 provider 余额/usage 摘要；获得授权前不进 NAS/生产、不读 Secret、不调用模型。确认模型后核对官方单价，再决定既有≤10 Run授权能否在隔离 Core→Hermes链路中安全使用。

## 2026-11-05 — #30 真实模型跨会话记忆验收预检（未发起 Run）

- **授权与计数：** Issue #30 最新 PMO 评论 `6658720963` 明确授权最多 10 次真实付费模型 Run。本轮实际 Run `0/10`，无模型费用；未创建生产 Session/Memory，未访问 Chat、Memory、Notes、Journal、Knowledge 或 Vault 页面数据，未改生产环境。
- **安全预检证据：** GitHub `main` 为 `e61eb8d510ad726c137f971f048cdd801c1123c5`。生产最近记录 App revision `7272b7388d9453a4abe212e6aa8d528e7e0dcd82`、healthy，Hermes 未随 App 部署变更；之前安全检查的 `/api/auth/session` 为 authenticated，`/api/agent/health` 为 online（均为本次之前的当日记录）。
- **真实阻断：** `web-app/secondbrain-core/secondbrain_core/modules/personal_learning.py` 的 `instructions_for()` 在每次 Chat Run 中先调用 `store._read_events()` 读取事件流，再用原始记忆正文对最多 20 条 active 记录打分；匹配项会放入 Hermes `instructions`。`personal_memory.py::active_view()` 自身也读取完整事件流；现有 Chat Run 没有精确 memory-ID allowlist。故仅使用唯一 UAT 前缀不能保证其他既有记忆正文不被该生产链路读取/评分或被选中发送。Issue 指令要求无法保证时先停，故在付费 Run 和生产写入前停止；未打开会展示全量记忆的页面，也未查询现有 Memory。
- **计费预检：** 历史资料曾记录 Hermes 默认 `zai-org/GLM-4.5-Air` / SiliconFlow，但本次安全 metadata 未提供实时有效 model 或账户余额，不能当作当前确认。供应商公开页当前列示 GLM-4.5-Air 输入 `$0.14/M`、输出 `$0.86/M`；这只能作单价参考，不能证明生产当前模型、账户可用余额、单次实际 tokens 或账单。
- **状态与下一步：** 跨会话真实模型验收 `BLOCKED_BEFORE_RUN`，分项均 `NOT RUN`：保存与回读、自然召回/模型采用、无关过滤、纠正、撤销、冲突处理。恢复前需先有可验证的单记录范围控制，并单独完成有效模型/计费元数据预检；不得放宽其他记忆隔离。没有修改代码或生产配置。

## 2026-11-05 — #30 PMO 更正后的现有模型通道预检（Knowledge 边界待授权）

- **裁定更正：** Issue #30 comment `6659497939` 明确撤回先前要求的独立 JSONL 根/白名单前置；用户确认项目尚未投入正式使用，NAS 为开发/部署/验收环境且没有业务数据。保留 PR #284 的隔离测试，不再扩建隔离层。本条记录更正后事实，不抹除上一条 `BLOCKED_BEFORE_RUN` 的历史。
- **运行与计费：** 经 SSH 只读取 SecondBrain App/Hermes 的目标容器状态、App 镜像 tag、Hermes 活动配置的 `model.default` / `model.provider` / endpoint host。App tag 标识 `7272b7388d9453a4abe212e6aa8d528e7e0dcd82`；Hermes 为 `zai-org/GLM-4.5-Air`、`custom`、`api.siliconflow.cn`。SiliconFlow [官方型号页](https://www.siliconflow.com/models/glm-4-5-air) 当前列示输入 `$0.14/M tokens`、输出 `$0.86/M tokens`。Core `HermesAPI.get_run()` 固定字段白名单不含 `usage`；SSE 是原样转发，现阶段没有取得余额或逐 Run 账单证据。费率用于按 usage 估算，不能当作账户余额/硬限额。未读 Secret、Cookie 或其他配置字段。
- **数据边界预检：** 只从 `/var/lib/secondbrain-core/personal-memory/personal-memory.jsonl` 读取所需审计元数据，不输出/查看记忆正文：共 2 个 memory、2 个 `create` 事件，来源 `user_message`，类别 `preference`、状态 `active`、fact kind `user_stated`，最晚时间 `2026-10-17T01:32:48Z`；没有显式 `test`/`uat` source_ref 标记。依据用户确认的环境阶段，继续按未投入业务使用处理；后续仅操作本轮唯一虚构 UAT 记录，不查询旧记忆正文。NAS 运行容器/配置/挂载/权限未修改。
- **真实链路阻断与纠正：** 用户在既有 Edge 完成登录；转到 `/chat/blank` 后未创建 Session。代码核验发现每个已认证 Chat Run 在启动 Hermes 前都会按输入调用 `knowledge_store.chat_recall()`（限 3 条、单条 8 KiB、总计 16 KiB），并将已验证引用的路径/标题/哈希写入本地 citation store；正文不进入 Hermes `run_body`。`/chat/blank` 只不加载普通会话列表，不隔离该后端检索。Issue #30 PMO 未授权读取 Knowledge，故在新授权前不运行真实模型。另一次 CUA 登录后状态观察自动返回 Home 的完整 accessibility tree，意外暴露了超出本任务范围的 Home 内容；未再访问或复述、未作为证据。这是执行范围失误，已停止扩大访问并如实记录。
- **状态与最小决策：** 真实 Run `0/10`、费用 `0`、无测试 Session/Memory 写入、无配置/容器变更。继续使用现有 Core→Hermes 链路需用户明确允许：最多 10 个虚构提示触发 Core 对 Knowledge 的有界本地只读检索，并允许新合成 Run 的 citation store 保存命中条目的路径/标题/哈希；Knowledge 正文不发送给模型或输出。若不允许，当前无不修改生产权限/代码而跳过 Knowledge 的正式 Chat Run 路径。Private/Vault/Notes/Journal 等仍排除，实际 usage/费用若运行后不能从 SSE/账户元数据取得则标 UNKNOWN。

## 2026-11-05 — PR #277 生产 Notes / Journal 合成 UAT（部分通过）

- **固定运行目标：** 生产 App revision `7272b7388d9453a4abe212e6aa8d528e7e0dcd82`，运行且 healthy；Compose SHA-256 `f5760550d5d9fe197cd58bd07c77bc178fb04fec27a9e990342d642530ace020`。本轮未改变配置、镜像、容器、权限或挂载；Hermes 容器/镜像不变，未调用模型。
- **唯一合成前缀：** `SB-UAT-20261105-57c00fe12af44edab907fbd1f8b326ff`。Notes Draft ID `57924f04-f176-4aac-85c4-64586a11bbac`：创建、两次编辑保存、刷新重开及 API 回读通过；合成正文 SHA-256 `16d1b33147a0fb2fcaf03d83411cf16d1f950bef05266b6117f3e586c120dbb3`。Draft 专用根文件 `0600 / 1026:100`。
- **Journal：** 写入前确认 `2099-12-30.jsonl` 不存在，只通过正式已认证 UI 新增两条显式合成原话，采用不同操作键。页面刷新和精确日期 API 回读均为两条且顺序 A→B；该日期文件仅有两条本轮合成行，SHA-256 `df8538178277a05f277155797116ed575d50e1269e8e3f138cb8a0613af5ba98`，权限 `0600 / 1026:100`。
- **授权/隔离：** 匿名 Session/Notes/Journal API 为 401；已认证 Notes collection 仅 `drafts`，对唯一合成不存在路径的 Knowledge collection 请求返回 404。Knowledge 挂载只读、Private 未挂载、Notes 授权根 `{}`、Promote=false。未打开既有记录详情，未修改/删除任何既有记录，未访问 Obsidian Vault/Knowledge/Private。
- **执行偏差：** 用户登录后 App 自动导航至 Home；一次完整 AX 快照包含现有业务摘要，较早的 Notes 快照包含已有列表标题。这些摘要/标题曾进入本次自动化工具输出；未打开记录详情，未主动复制/导出到文件、GitHub 或其他服务，也未修改或删除任何既有记录。该读取超出授权范围，发现后停止进一步页面读取，状态为 `UAT_SCOPE_DEVIATION_REVIEW_REQUIRED`，需用户裁定后方可继续生产 UAT。
- **剩余验收缺口：** 同一幂等键的生产重放 `NOT RUN`。前端正式成功路径清空重试键，当前受限 UI 接口无法安全重放自定义 key；未读取登录 Cookie/Secret、未注入脚本或绕过鉴权。已有隔离 Core route 与前端模拟测试证明 duplicate/retry 合同，但不等于生产运行验证。故当前仅 `PARTIAL`，不能标记 `PRODUCTION_SYNTHETIC_UAT_PASS`；是否继续同 key replay 先待用户对上述读取偏差裁定。

## 2026-11-05 — PR #277 App-only NAS 部署与验证

- **固定目标与候选：** PR #277 merge SHA `7272b7388d9453a4abe212e6aa8d528e7e0dcd82`；Ubuntu Chromium Gate [#42007023705](https://github.com/zxwan829/SecondBrain/actions/runs/42007023705) PASS，固定 SHA 构建 [#42009466695](https://github.com/zxwan829/SecondBrain/actions/runs/42009466695) SUCCESS。Artifact digest 与下载内容匹配；App-only 镜像归档内部 SHA-256 `caa8829243d4cd1a85e2730ee963559bdb8ef3e7998aab2a892f7c1cff2d50ef`，image ID `sha256:d73bb0fb73b77a728c4f6eecde44c8309695abb573e00048c6ba3affb50fc1e1`、平台 `linux/amd64`、revision 与 SHA 一致。NAS 仅加载 App 镜像。
- **部署与回滚材料：** 部署前 Compose SHA `21fcb91e6b4233ef7a680fa4cfe16577b8c43f266d577ee2da0b2be11390c520` 已即时备份并逐字节哈希匹配，快照在受限目录。目标 Compose 结构化比较确认只变 App image；部署后 Compose SHA `f5760550d5d9fe197cd58bd07c77bc178fb04fec27a9e990342d642530ace020`。若需恢复，仅将该快照还原并对 App 指向已保留的 `268ccae` 镜像执行定向重建；不回滚数据或触碰 Hermes。未演练回滚。
- **生产验证：** App revision `7272b7388d9453a4abe212e6aa8d528e7e0dcd82`，Image ID 与候选一致，running/healthy、RestartCount 0。`/health`、`/`、`/login`、`/notes` 均 200；匿名 Session/Notes/Journal API 均 401；App→Hermes health 200。Knowledge RO、Private 未挂载、Promote=false、Notes 授权根 `{}`、Journal/Notes 根仍为既有独立 `0700` Core-state 子目录。Hermes 容器 ID、镜像、启动时间未变化，其他容器未重建。
- **范围边界：** 未读写真实 Notes/Journal/Knowledge/Private 数据，未调用模型；未改变挂载、权限、Secret、端口或服务拓扑。Journal 是 Core-state JSONL，未证明与 Obsidian `50-Journal` 同步。部署/运行 Gate 通过不等于真实 Notes/Journal 用户验收，仍为 NOT RUN。

## 2026-11-05 — Notes 保存与 Journal 追加隔离工程闭环（PR #277）

- **Notes：** 复用现有受控 Drafts API 与真实 Core+Web 合成浏览器旅程，三视口均新建 Draft、保存编辑并刷新后重新读取一致；已有前端失败/版本冲突用例确认失败时保留输入且不报成功。未授权任何真实 Vault collection。
- **Journal：** Ubuntu 24.04 Chromium 三视口通过真实本机 Core API 向临时 Journal 根分别 POST 明确“记一下”原文，收到 `created` 回执，刷新后读回一致。最终合成摘要 `raw_record_count=3`、`journal_source_fixture_files=1`、`journal_files=3`、`journal_mutated_files=3`；验收程序逐字节确认原始 source JSONL 前缀未变，只允许追加三条合成记录及两个空的 `0600` 锁文件。失败诊断只允许固定的 Journal 浏览器断言 ID，路由测试隔离地仅准许无 Query 的指定 GET 日期路由和 POST `/api/journal/entries`。
- **失败与重试：** 新增 Core 鉴权路由测试，覆盖匿名拒绝、普通聊天文本 422、同 key 重试返回 duplicate、同 key 不同内容 409、原日记记录不变及回读追加行；前端模拟响应丢失，确认保留原文、复用同一幂等键并显示无重复成功提示。过程中发现网络错误原文被直接暴露，已最小修复为中文网络失败反馈，服务端 HTTP/冲突原因仍保留。
- **验证：** Core `tests/test_journal.py tests/test_notes.py` 24 passed；前端完整 Vitest 41 files / 490 passed；定向 Journal/Notes 前端 28 passed；Artifact sanitizer 59 passed；`npm run typecheck`、`npm run build`、本地隔离 Core+Web HTTP smoke 与 `git diff --check` 通过。Ubuntu 24.04 + Chromium Actions [#42006382893](https://github.com/zxwan829/SecondBrain/actions/runs/42006382893) 在固定 HEAD `58cc6c181207a18445bd7c805fa34d57f197559d` SUCCESS：checkout SHA 校验、全前端回归、类型检查、构建、artifact sanitizer、隔离 Core+Web 浏览器旅程及脱敏产物上传全部通过；JUnit 3/3 viewport pass、0 failures。仅上传既有脱敏 allowlist 下的 JUnit/summary，无截图。独立 Reviewer PASS。
- **状态边界：** PR [#277](https://github.com/zxwan829/SecondBrain/pull/277) 实现与隔离工程证据；未修改 NAS 生产、Compose、挂载、权限或真实 Notes/Journal 数据，未调用付费模型、未使用真实 Hermes/个人数据，也未改变 Knowledge RO、Private、Promote/Writer、Weixin 或 VNext。工程 PASS 不等于生产写入授权或真实业务用户验收。若需要启用生产 Journal，先单独批准 App-only 配置/部署与 Journal 专用 Core RW 路径核验；Notes 真实 Vault collection 与真实数据验收也需各自授权。Chat #269/#274 人工视觉 UAT 按用户决定记为 `USER_WAIVED / NOT RUN`，不是 `USER_UAT_PASS`。

## 2026-11-05 — PR #274 App-only 生产部署与运行收口

- **固定目标与构建：** PR #274 merge commit `268ccae7255c1e2f4fea057d9630d40d7dcca704`；完整 Chromium Gate [#41967914277](https://github.com/zxwan829/SecondBrain/actions/runs/41967914277) PASS，精确 SHA 构建/隔离启动 [#41969167078](https://github.com/zxwan829/SecondBrain/actions/runs/41969167078) SUCCESS。候选 App image `sha256:ad2b5a71f97d8de40fbcfeefd720c13f579eae74422943082bf78d27f4678461`，`linux/amd64`，revision 与目标 SHA 一致。Artifact ID `13389067298`；bundle SHA-256 `07ea18a4118526719149b13490f46d275650e668cf396fd4ef8253846e63993b`；只含 App 的导入归档 SHA-256 `a941538e0974b4388fd81e4d753ecf706a0b02f2cb33848e35f5300c8b3cf3bd`。生产仅导入并部署 App image。
- **部署和验证：** NAS App-only 重建约 37 秒后 healthy，容器 `519ce635c5d5becb0e3a24d26d6ba335522589f0288177e5ea7e326e752b8b3a`、Image ID `sha256:ad2b5a71f97d8de40fbcfeefd720c13f579eae74422943082bf78d27f4678461`、revision `268ccae...`、RestartCount 0。Compose 只改 App image；归一化配置 SHA 前后同为 `ab40680a6c811d1db9a2787e2c76bddd0031e313e8a9b95e0223b807083b3922`，部署后原文件 SHA `21fcb91e6b4233ef7a680fa4cfe16577b8c43f266d577ee2da0b2be11390c520`。`/health`、`/`、`/login`、`/notes` 200；匿名 session/tasks/notes 401；App→Hermes health 200。
- **边界与回滚：** App UID/GID、loopback 端口、Knowledge RO、Private 未挂载、Promote=false、Weixin 未开启、Capture/Review/Core state 既有挂载均保持；Hermes 容器 ID、镜像、StartedAt、RestartCount 未变。发布前 Compose 快照与旧 d06 App image 已验证并保存在 Environment-Baseline 记录的受保护目录；未触发回滚。没有读取 Secret/业务正文、写入真实业务数据或调用模型。新版 Chat UI 用户视觉/交互验收仍 `PENDING`，VNext 仍 FROZEN。

## 2026-11-05 — PR #274 Daily Brief Gate 修复与 Chat UI 合成验收

- **根因与最小修复：** Daily Brief 浏览器旅程把整个多页面 journey 中累计的 Journal source GET 数量误当作 Daily Brief 页面内计数，导致此前已合法加载 Journal 的请求被误判为隐式加载。测试现于 Daily Brief 标题显示后记录计数基线；手动准备阶段断言不增加，显式点击加载后断言计数增加并呈现合成来源。未删除或放宽验收断言，Daily Brief 产品代码未修改。
- **验证与复审：** 原代码 HEAD `d2e99ee5c7fc36c6ec32c0855903f392ed1ddf6c` 的 Gate [#41967382741](https://github.com/zxwan829/SecondBrain/actions/runs/41967382741) 已通过；最终含本状态记录的 PR HEAD `9de2c5db8c3095e12c18663b2d0dbbdf5290f81d` 再经 Ubuntu 24.04 Chromium 完整 Gate [#41967914277](https://github.com/zxwan829/SecondBrain/actions/runs/41967914277) SUCCESS。Web 回归、typecheck、build、sanitize 检查及隔离 Core+Web 浏览器旅程均通过，Chat 三视口覆盖保留。独立 Review PASS；指出项目源定位器略脆弱但不影响验收，无合并阻断。
- **合并与状态边界：** PR #274 于 2026-11-05 合并，merge commit `268ccae7255c1e2f4fea057d9630d40d7dcca704`。此处只记录代码合并时点；同日稍后已完成 App-only 生产部署，详见本日志下一节。合成浏览器与生产部署均不等同新版 UI 用户验收；`00-CURRENT.md` 唯一 NEXT 仍为用户本人验收。VNext 保持 FROZEN。

## 2026-11-04 — PR #269 App-only 部署与运行验收

- **合并与候选：** PR #269 merge SHA `d06e3f3bde2cf8ee260992644c2ae5d67aeef362`；Ubuntu 24.04 三视口浏览器 Gate [#41785664124](https://github.com/zxwan829/SecondBrain/actions/runs/41785664124) PASS。精确 SHA 构建/隔离启动 [#41788688422](https://github.com/zxwan829/SecondBrain/actions/runs/41788688422) SUCCESS；生产 App Image ID `sha256:250437fc8b57642770347d6de73d86e791ffd8aaebdaba399170bc5018fe2270`，平台 linux/amd64。App-only 包 SHA-256 `49905f26e9fc7780a1a58be693f7d1558b989421291ffcfa417a3856674e684a`，镜像结构及 blobs 校验通过，无 Hermes 引用。
- **生产部署与回滚：** 经用户批准，仅更新 Compose App image 并重建 `secondbrain-app`。首次探针错误识别 mount 序列化格式及 Host，触发脚本自动回滚；旧 App 恢复 healthy，Core state 未变，Hermes 容器 ID/镜像/启动时间不变。修正探针后重试成功。最终 App revision d06、running/healthy、UID/GID `1026:100`、端口 `127.0.0.1:9120→8000`；Compose SHA-256 `3c9b1892d5a0f155050055545789c910f63db6a910007ee1a8c1b6436ee61c77`，语义差异仅 App image。`/health`、`/`、`/login`、`/notes` 200，匿名 session 401，App→Hermes health 200；挂载、只读 Knowledge、Private 未挂载、Promote=false 保持。未调用模型或改业务数据。
- **恢复材料与用户验收：** 发布前 Compose 快照位于 `/volume1/docker/secondbrain/rollback/chat-ui-d06-20261104T0721Z/compose.yaml`（root:root 0600，原 SHA `0aedb4b104870ddc5ce23a2f1adde10b84b51bf06f7e35d3377356bcc5a84708`）；App-only 候选归档在 NAS candidates 路径，SHA 与上方一致。回滚只恢复 Compose 并重建 App，保留 Core state，不触碰 Hermes。生产运行门禁通过不等于新版 UI 用户验收：用户仍需进行桌面浏览器验收；完成后再推进 Notes 保存、Journal 追加等 V1 UAT。跨会话记忆未验收，VNext FROZEN。

## 2026-11-03 — V1 首轮真实用户体验准备与线上只读复核

- **基线：** GitHub `main` `9c37cea6babd933d488f2adab546e4b761860abf`；NAS App revision 为 `ce247d0c2f014c67f407c7b8721022da6afe2753`。Hermes 无 SecondBrain revision label，Image ID 与 2026-10-24 快照一致。GitHub compare 确认 SecondBrain App/Core 的 `ce247d0c..9c37cea` 只有文档差异、无源码变化。NAS Compose SHA 与 2026-10-24 快照一致。
- **线上只读证据：** App running/healthy、RestartCount 0、UID/GID `1026:100`；Hermes running、RestartCount 0。HTTPS `/health`、`/`、`/login`、`/notes` 200；匿名 session、Task、Capture summary、Knowledge search、Promote API 401。Hermes loopback 与 App→Hermes health 均 200。实测 Promote=false、Knowledge RO、Private 未挂载、App/Core Weixin 开关未设置为开启；Hermes safe root 保持三个获准捕获目录。未登录、未读取业务正文/Secret/Private、未写生产数据或执行模型调用。
- **隔离测试：** 独立浅 Clone `main`；前端定向 9 个文件 **255 passed**，Core Capture/Task/BFF/Notes **104 passed + 4 subtests**；typecheck、Vite build 通过（既有单个大 chunk >500 kB 警告）。GitHub Actions [#41657897177](https://github.com/zxwan829/SecondBrain/actions/runs/41657897177) 固定 checkout `9c37cea6` 并核对 SHA；Ubuntu 24.04 workflow 全部步骤成功，包含全量 Web tests/typecheck/build、sanitized artifact gate 及真实 localhost Core HTTP + Linux Chromium。三项浏览器旅程在 1440×1000、820×1180、390×844 各 PASS；精确 768px 未运行。Hermes 为 fixture-only、Promote=false、Knowledge 文件为 0、Journal 未改写；脱敏 JUnit 为 3 tests / 0 failures，未上传截图。
- **第一轮可验收范围：** 线上版本无需为了追 main 文档 SHA 重部署。登录/只读页面入口可用；Task 持久化与 Capture/Inbox scope 有合成验证；Knowledge/Notes、Chat/真实模型、真实 Task/Capture/Review 操作尚无用户验收。Chat 真实回答涉及个人会话/模型数据出站和费用；Promote、Writer、Weixin 继续关闭。
- **结论：** `PARTIAL / BLOCKED_ON_USER_SCOPE_ACCEPTANCE`。可准备用户本人开始体验，但必须先明确接受登录后的指定模块数据读取；如测试持久化需同意创建合成 Task/Capture；真实模型 Chat 需另外确认模型与费用上限。完整状态、入口和逐项验收步骤见 `00-CURRENT.md`。

## 2026-10-24 — V1 第一阶段 NAS 部署与健康验收

- 将 GitHub main `ce247d0c2f014c67f407c7b8721022da6afe2753` 对应 App/Core 与固定 Hermes v0.22.2/D078/Weixin 镜像部署到 DS920+。Actions #40075395885 artifact 的 ZIP、镜像包、内部 `SHA256SUMS`、Docker Image IDs、App revision label、Hermes upstream/overlay labels 全部匹配。
- App 与 Hermes 分服务重建；Compose 仅更改两项镜像引用。App healthy；`/health`、首页、Notes、登录页 200，未认证 Notes API 401。Hermes API 200、Dashboard 302；活动 D078 user plugin enabled，Weixin plugin 文件存在但未启用。D078 合成非法 terminal 输入被阻断且未执行。
- App UID/GID、Hermes root、网络/端口/挂载保持原值，Private 未挂载；Weixin、Promote、API Terminal 关闭。其他 NAS 容器未重启。未执行真实登录业务、真实微信扫码/消息、个人数据操作或用户体验验收。
- 回滚目录与资产摘要、旧镜像 ID、回滚步骤及详细验收见 [Environment-Baseline.md](Environment-Baseline.md)。无回滚触发。

## 2026-10-24 — P4-1/P4-3 合成收口与 Journal 队列审计

- **main：** 当前 `4d4577eb43a9e66e607e416bed75600e814cfd0a`，正常合入 #210、#230、#231。无生产部署、真实个人文件、真实 Vault/NAS、模型费用或 Writer/Promote 操作。
- **P4-1 多格式 Capture：** #210 HEAD `d0dee983295efef44e1f2ad0ea45c72cfb6591ed` 通过独立复审和 Linux D077 run [#40055008815](https://github.com/zxwan829/SecondBrain/actions/runs/40055008815)：Ubuntu 24.04/Python 3.12/pypdf 6.21.2，Memory preflight 14 passed，Core 615 passed/51 subtests，compileall/diff-check PASS。#231 test-only exact HEAD `f139fee0ba97f1097dd7d9d30fd3d6c0d3cfb5df` 独立复审 PASS 后合并 `4d4577eb`；聚焦测试 35 passed/4 subtests，补成功 `.txt`/`.md` 上传及完整 `capture_context` Raw 保留、Review 内容和来源/context 元数据。现有合成 P4-1 缺口审计未发现额外可安全复验项；真实文件质量仍 NOT RUN。
- **P4-3 Notes：** #230 exact HEAD `11581b7d8bde64c3968c8fa2be7e297d168f7240` 独立复审 PASS_WITH_LIMITS 后以 `ee4eadb09bac7053f24e00f2cdee98ec4099b062` 合入。Linux run [#40055285712](https://github.com/zxwan829/SecondBrain/actions/runs/40055285712) exact SHA success：Web 483 passed，typecheck/build、trace sanitizer、隔离 Core+Chromium journey、844×390 short-landscape modal/control bounds 通过。仅为合成视口验收；真机 picker/touch/IME、真实 Notes/Vault 和 Mac↔NAS Obsidian sync 未测。
- **P4-5 Trash：** #216 exact HEAD `c0f6a6c0e8e8defd416f6191a763c05628fd5345` 的 Linux D077 run [#40055253536](https://github.com/zxwan829/SecondBrain/actions/runs/40055253536) success：Memory 14 passed，Core 625 passed/51 subtests；只验证临时合成路径。仍因 C2 物理 root 策略和登录 owner session 默认 `notes.delete/restore` 授权语义未冻结而阻止合入/UI；没有访问真实 Vault/NAS。
- **P3-4/P3-5 审计与 NEXT：** P3-4 `approved_import` 已由 #207 实现；#225 仅修正一个 stale 501 测试断言。独立精确-main 定向组合 36 passed；不另造实现。P3-5 `/api/activity` 已有 Journal/Task/Project/Brief/Memory/Capture 来源；Review/Promote/Agent/Skill 需先冻结 DTO 与权限预检，Hermes session 读取不作为当前默认实现。下一项为用户已授权的 #138 Journal GET 合成 loopback 契约刻画，仅测试、不改业务行为。完整 V1、P5 生产安全与 P6 用户验收仍 NOT DONE。

## 2026-10-24 — 统一主 Agent 集成复核与 P4 收口更新

- GitHub main 已推进至 `1ffd4b48a4825812b1b5f6459c40ee4194a3f4a7`。本节是本日日志的最新纠正；下方同日记录描述其记录时的快照，不再表示当前 PR 状态。#221 Core、#222 Web、#220 Notes/Home→Task、#223 Organizer 均按正常 GitHub Merge 路径合入；#220/#223 固定 HEAD 分别为 `d3e6d253ad44292a8470e06e5056985b9ee3473f`、`f0c1fc8f4c02dbcd2da4fa441dcfb21a10748c7a`，merge commits 为 `4157fc6cc38026aadd2df0425869360c5adf6603`、`1ffd4b48a4825812b1b5f6459c40ee4194a3f4a7`。
- #220/#223 均获独立源码复审 `PASS_WITH_LIMITS`。最新 main + 两 PR 依赖顺序组合的 Git tree 相同；`App.navigation.test.tsx` 61/61、typecheck、build、`git diff --check` 均通过。只组合 #223 时 60/61，唯一失败由尚未合入的 #220 Home→Task 修复解决，证明先合依赖再合后续 PR 的必要性。未启动新 Actions。
- #219 文档复审发现并修正 #221/#222 过期状态及 Progress-Log 末尾重复旧记录；用户验收、Obsidian 双向同步、P4 多格式质量、Trash OS/权限门槛、P5 生产验证与 P6 全范围验收仍未完成。无生产部署、真实数据/模型访问或 Writer/Promote/费用门禁变更。

## 2026-10-24 — Capture Activity Web 复审与 Organizer status 竞态修复

- **固定基线：** GitHub main `2782f73fa44a21549f7758c4e449076304875917`。#221 Core `41e9729d693e80f4f37c1a5543dc8fb1e1411124`、#222 Web `438a7e2b570370d1c742bc8b9f50caa9941fdc76` 的既有隔离 Vite→Uvicorn HTTP 组合 `edb17ec78eeedb96b5015dc5fcc7429bf27472d2` 保留为 `PASS_WITH_LIMITS`，未重复运行。#222 A 线增量源码复审 Review #5633533074 为 `PASS_WITH_LIMITS`：Capture Activity 六种状态本地化、Capture DTO 字段收窄、未知状态/多余字段 fail-closed；不代表 Core #221 准入或浏览器覆盖 Capture 专项。
- **P4-6 Web 缺陷：** 在独立 main clone 的 `ScopedCaptureInbox` 复现 Organizer 状态请求竞态：较新的 403 已撤销可用状态后，旧 200 `execution_available=true` 仍可迟到并重开操作 UI。#223 `f0c1fc8f4c02dbcd2da4fa441dcfb21a10748c7a` 为 Organizer status 请求增加 latest-request revision guard，并在离开 Capture scope 时使未完成响应失效；Core 服务端授权未改。另依据 Core 回执合同明确显示 `no_candidates`，对未知/畸形 HTTP 200 不再伪报 0/NaN 成功结果，而提示检查状态。
- **验证：** 状态竞态回归在修复前失败、修复后通过；最终 HEAD 的 `App.navigation.test.tsx -t 'Inbox explicit source scopes'` 20 passed；`npm run typecheck`、`npm run build`、`git diff --check` PASS。Build 保留既有 Canvas chunk 大小提示。更早在 main 基线上执行的完整 `App.navigation.test.tsx` 为 56 passed、1 failed；失败是 #220 已定位并修复的 Home→Task 表单入口，不归因于 #223，最终 HEAD 未重跑整文件。未触发手动 Actions。#223 Draft/Open，等待独立复审。
- **剩余项与边界：** #221 Core 仍待 B 同步 main 并复核净差异；#220 最新 HEAD `d3e6d253...` 三视口已 PASS，但独立复审未完成。P4-1 的逐格式 OCR/STT 内容质量及手机文件选择、Obsidian 双向同步仍未验收。没有合并、部署、真实数据/模型或生产操作；Writer/Promote、费用门禁 OFF，D090 不变。

## 2026-10-24 — #164 合入与最新 Capture/Notes 合成验收推进

- **main 与 Today→Task：** main `2782f73fa44a21549f7758c4e449076304875917` 已包含 PR #164 固定 HEAD `f020d303a38153c7a8a0bb06c7609a4228b5770a`。其成功创建回执后恢复按钮可用的修复，TaskPage post-merge 定向回归 29/29，typecheck/build/diff-check 通过；独立增量复审记录 PASS_WITH_LIMITS。该状态不表示生产部署。
- **Capture Activity 固定组合：** 以 main `2782f73f` 为基线，与 Core #221 `41e9729d693e80f4f37c1a5543dc8fb1e1411124`、Web #222 `438a7e2b570370d1c742bc8b9f50caa9941fdc76` 在隔离 worktree 形成组合 HEAD `edb17ec78eeedb96b5015dc5fcc7429bf27472d2`；组合无 Git 冲突，`git diff --check` 通过。复用现有 `p3_consolidated_vite_gate.py` 的真实本地 Vite→Uvicorn HTTP 路径，结果 `P3_1_5_HTTP=PASS_WITH_LIMITS`：覆盖 Capture 四字段 Activity DTO、撤销 `inbox.read` 后来源移除/恢复后返回，以及既有 Home、Projects、Today/Task 创建重放与更新 CAS、Journal、Calendar、Brief approved_import、Planning 审批/执行/task_created 回执重放、权限拒绝、失败恢复、并发 CAS、会话隔离和 Core 重建后读回。所有数据在脚本创建的私有 `/private/tmp/sb-p3-gate-d07cbm6q` 合成根中；该 Gate 不是浏览器、PR 独立复审或 Core 生产/OS 验收。
- **PR #221/#222 状态：** 两项仍 Draft/Open，固定 HEAD 未变；相对 main `2782f73f`，main 对 #221 ahead 25、对 #222 ahead 21（两 PR 各 ahead 1）。本地组合验证不能代替 B 对 Core #221 净差异的复核，尤其 `app.py` 曾在两侧同时修改。#222 还等待独立 Web 复审。浏览器未覆盖 Capture 专项。
- **Notes/Home→Task 浏览器：** PR #220 Draft/Open，HEAD `d3e6d253ad44292a8470e06e5056985b9ee3473f`。Run [#40009881231](https://github.com/zxwan829/SecondBrain/actions/runs/40009881231) 对上一 HEAD `44af77ee` checkout SHA 校验通过、Chromium 安装成功，随后 `App.navigation.test.tsx` 55/56；Home→Today 到达 `/today`，但创建表单折叠且缺 accessible name。源码比较确认 #164 将表单改为折叠但 Home 入口仍只普通导航，分类 **WEB_BUG**。#220 最小修复新增一次性 `create=1` 路由意图，TaskPage 打开表单并消费查询参数，恢复双语 accessible name；新增 URL 清理回归。新 HEAD `d3e6d253` 的导航 56/56、typecheck、build、diff-check 通过。Run [#40011373183](https://github.com/zxwan829/SecondBrain/actions/runs/40011373183) 对精确 HEAD 成功，checkout SHA 一致，所有步骤通过；脱敏 JUnit 3/3、0 failures/skips，Desktop 1440×1000、Tablet 820×1180、Mobile 390×844 全 PASS。`inbox-browser.spec.ts` 含 Inbox 与 Notes 创建、编辑保存、刷新重开/读回及横向溢出断言；artifact `result=PASS`、local Vite/Core HTTP、Notes files 9、Brief files 4、Journal mutation 0、Knowledge files 0、Promote=false、Hermes fixture-only；0 screenshots/HTML report uploaded。Run #40009881231 的 build/browser/artifact 未运行，三视口为 NOT RUN，已被新 SHA Run 覆盖；较早 HEAD `27bc4711` 的 Notes 三视口 PASS 是旧版本证据。
- **安全与剩余状态：** 未修改 B 所有权代码、未合并 #221/#222/#220/#219；未部署、未连接真实 Vault/NAS、未访问真实数据或付费模型。#220 三视口 Gate 为 PASS_WITH_LIMITS，但最新 HEAD 独立复审仍待完成；#221/#222 P3-5 收口仍待 B 同步/独立复审。`A_NEXT_READY=NOT_READY`，Writer/Promote、Chat cost gate 保持 OFF，D090 OS Gate 不变。完整 V1 仍 `NOT DONE`。

## 2026-10-24 — P4 Notes 移动三视口与 P3-5 Activity Web 接口适配

- **最新基线：** main `22b536e79e67cb746f8ea4039686ca8b5031b84e`。#220 分支从 `5fd9df3c` 普通同步到该 main，净 PR 差异仍限于 E2E harness、Playwright 用例、sanitizer 与既有 Notes 图形对话框 CSS；合并无冲突，`git diff --check` 通过。
- **故障证据与修复：** #220 Run [#40006256529](https://github.com/zxwan829/SecondBrain/actions/runs/40006256529) checkout `40bfc828`。Tablet/Mobile 在 `notes_readback` 失败，脱敏记录显示 Notes collection/detail GET 均 200；截图显示多个相同可访问名称的合成笔记按钮。分类为 **TEST_BUG**（跨视口复用标题造成 locator 歧义），无 API 故障证据。提交 `ab0f7939f0f34fcb87ba18df5ff4877f057561b4` 为各视口使用独立合成笔记标题，保留保存、精确 GET 200 与正文读回断言。Playwright discovery 3/3、diff-check 通过。
- **固定基线复验：** Run [#40007875993](https://github.com/zxwan829/SecondBrain/actions/runs/40007875993) 在修复 HEAD `ab0f7939` 上三视口均 PASS。同步 main `22b536e` 后最终 #220 HEAD `27bc4711ccd1d0ff6a91777b32723beba0899b64`；Run [#40008488314](https://github.com/zxwan829/SecondBrain/actions/runs/40008488314) checkout SHA 完全匹配，workflow PASS，脱敏 JUnit 为 3 tests / 0 failures / 0 skipped：Desktop 1440×1000、Tablet 820×1180、Mobile 390×844 全 PASS。实际步骤含 Web 回归/typecheck、build、artifact sanitizer、Vite→真实 localhost Core HTTP 与三视口浏览器旅程。summary：`result=PASS`、Brief file set verified、Notes files 9、Journal mutation 0、Knowledge files 0、Promote=false、Hermes fixture-only；无失败截图上传。
- **P3-5 Capture Activity：** Web PR #222 `438a7e2b570370d1c742bc8b9f50caa9941fdc76` 严格接入已接受的四字段 Capture DTO，未知状态/额外字段 fail-closed；3 项定向组件合同测试、typecheck、build、diff-check 通过。与 Core PR #221 `41e9729d693e80f4f37c1a5543dc8fb1e1411124` 的既有临时合成 HTTP Gate 在 main `2fe5be1` 上 PASS（Vite→Uvicorn、Capture DTO、撤权移除/恢复重现）；**该组合不是 latest main `22b536e`，也不是浏览器验收**。GitHub 显示 #221 base `5fd9df3c`、当前 main `22b536e` ahead 1 / behind 17，merge state clean，且两边均修改 `app.py`；需 B 同步后再核对实际集成。#222 base 为 `2fe5be1`，仍 Draft，独立 Web 复审未记录。
- **边界与状态：** #220 保持 Draft/Open，等待对 HEAD `27bc4711` 的独立增量复审；#221/#222 未合并。Obsidian 双向同步、真实 Vault/NAS、生产 Writer/Promote、付费模型及用户生产验收均未运行。当前 Notes 浏览器子 Gate PASS_WITH_LIMITS；V1 overall 仍 NOT DONE。

## 2026-10-24 — #201/#207/#202 固定组合合入与 Linux 三视口 Gate

- **源码与合并：** 从 main `d8e58585dcb2e6b03707861b1a3233c666c466fa` 出发，按 #201 固定 HEAD `ea70fca9dde78793b05d5aaed7523f26bf432a72` → merge `e611ecc46354eec0c28ffe1bc573cf218f12ee30`，#207 `aff4171f86b00bb8420e0cfe2af8a0978fdb2f37` → `6c372ff609a5f9252c0c2197cdbf240190827bea`，#202 `69f39cccfbae56c66a4db6f483e8dc75aee0cf7b` → `5fd9df3cd05981a89a495b748bcc5bf541ab7788` 正常 Ready/Merge。每次指定精确 HEAD；GitHub 返回 MERGED、main 前进。无管理员绕过、强推、reset 或回滚。
- **增量与复审：** #201 原功能、缺 grant fail-closed 修复、后续 fixture-only 增量分别获独立 `PASS_WITH_LIMITS` 源码复审（#5628071244、#5629186192、#5629351990）；本次安全敏感合并有用户单独授权。#207 从已复审实现到旧 HEAD 仅测试 fixture，随后同步 main 的新 HEAD 无 Core 文件变化；两份既有复审 #5628070590/#5629352916 继续适用。#202 当前 HEAD 增量复审 #5630364588 为 `PASS_WITH_LIMITS`。三次合并的 main tree 均与预先无冲突的候选 tree 相同，diff-check PASS。最终 tree `f1b012cd160788a9c965d001065f253a59d59084` 与上一固定 #201/#207/#202 本地组合完全一致；复用 82 Web、158 Core 和 `P3_1_5_HTTP=PASS_WITH_LIMITS`，没有重跑无变化测试。
- **真实 Linux 合成浏览器：** 对 #202 精确 HEAD 触发一次既有 `a-web-playwright-synthetic.yml`，Run [#39984102838](https://github.com/zxwan829/SecondBrain/actions/runs/39984102838) `workflow_dispatch`，实际 head SHA 与固定 HEAD 相同，全部步骤成功。脱敏 JUnit 3 tests / 0 failures / 0 errors：Desktop 1440×1000、Tablet 820×1180、Mobile 390×844 均 PASS；现有业务旅程与横向溢出断言随同一用例通过。脱敏 artifact #12514632289，digest `sha256:3584c0b4c6f55c70546e32f688594cdbf80957ca14b7076a4ed820659b993812`，只有 JUnit 与 run-summary，无失败截图。摘要为 `result=PASS`、`brief_file_set_verified=true`、Journal fixture 1 / mutation 0、Knowledge files 0、Promote=false、Hermes fixture-only。该工作流在 #202 分支快照上运行；与 Core 合并后的 main tree 等效性由上述 tree 核对及既有 HTTP Gate 支撑，不把它误称为生产浏览器验收。
- **边界：** 合成 Web `A_NEXT_READY=READY_WITH_LIMITS`；#201 已知的进程内缺 grant fail-open 修复通过范围内验收。跨进程持久撤权、Writer/Promote OS Gate、真实模型/渠道、生产部署、真实 Vault/NAS、Notes 移动交互和 Obsidian 双向同步均未由本次验证。V1 整体仍 NOT DONE，生产 Writer/Promote 与费用门禁保持 OFF。

## 2026-10-23 — #201/#207/#202 fail-closed 与合成集成收口

- **基线与固定 PR 版本：** GitHub main `d8e58585dcb2e6b03707861b1a3233c666c466fa`（新增 #217 docs-only；运行代码基线 `e33b836c`）。#201 当前 `ea70fca9dde78793b05d5aaed7523f26bf432a72`，#207 当前 `a5560d90cf138847558395af8eab7a2d7a077465`，#202 当前 `6c650c9518870f69f830afe5c0945f871d2e1e42`，base 为 main。
- **#201 安全增量：** `ac1c171d3c5efd3e89fbcc6b578ac354a3d145d1` 已令有效 session 缺 grant 时 `require_action()` / `set_session_action()` fail closed（403）；A 的安全增量复审 #5629186192 为 `PASS_WITH_LIMITS`。从 `0267a2ce` 到当前 `ea70fca9` 仅五个合成测试夹具显式初始化登录 grant map，A 对该 fixture-only 增量复审 #5629351990。B 报告当前 #201/#207/#209 集成候选 12 个相关 Core 模块 158 passed（#97 #6366547203）；A 未重复运行。
- **#207 增量：** 从已复审实现 `d1cd0904` 到 `a5560d90` 仅更新 `test_daily_brief_import.py` 的合成 session fixture，没有改 `approved_import` 实现/合同；A fixture-only 复审 #5629352916。此前实现复审 `PASS_WITH_LIMITS` 保持适用。
- **Web/Core HTTP Gate：** 在本地隔离候选上合入 main `e33b836c`、#201 `0267a2ce`、#207 `d1cd0904`、#202 `62c97ff0` 与测试修订，组合提交 `0ed4048610da2ed0419fe1e878ba4776ff9431ef`。复用 `p3_consolidated_vite_gate.py`，结果 `P3_1_5_HTTP=PASS_WITH_LIMITS`。覆盖 Home、Activity、Projects、Today/Task 创建幂等回执/更新 CAS 冲突/读回、Journal、Calendar、Brief `approved_import` 创建/重放/读回/409、Planning approve/execute/`task_created` 回执与精确重放、会话隔离、权限拒绝先于来源校验、失败恢复与进程重建后持久读回。仅临时合成 roots/Uvicorn+Vite；无真实数据/模型。
- **测试合同修正：** Gate 原先错误地把 Task PATCH 误当作支持 Idempotency-Key 的幂等重放。实际合同使用 `expected_updated_at` CAS；同一旧版本第二次请求应返回 409。#202 提交 `950f02260e887e212bba549b0cd4627f22723747` 修正为断言首个更新 200、过期版本重放 409 和权威列表读回。随后 #202 同步 main docs-only merge，当前 HEAD 为 `6c650c95`；运行代码未变。定向 Gate 在修正后通过；`git diff --check` 与 Python 语法检查通过。
- **未验收/边界：** #202 当前 SHA 没有新的三视口浏览器运行（`NOT RUN`）；旧 Run 只适用于其固定 HEAD，当前 `A_NEXT_READY=NOT_READY`。没有全量 Core 测试、Actions、main 合并/部署或真实数据访问。Writer/Promote 与费用门禁保持 OFF；#201 安全敏感 PR 不按普通 PR 自动合并授权处理。

## 2026-10-23 — 普通 Web PR 批量集成收口（Issue #96 授权）

- **固定基线与合并顺序：** 从 main `e28db843df53c2ac48c71abbedeb3713c77d338b` 起，按 #198 → #212 → #214 → #215 使用 GitHub 正常 Ready/Merge 流程，未绕过保护或检查。对应 main merge commit：#198 `5fff974bae9f31f6149fabc7fd087b7374507489`；#212 `f58ecfd28c5fbe4c4bae37aaf94433830689daef`；#214 `db81065413e71d832f2cf6c88f9995b105dc1757`；#215 `e33b836c67095df1537ac4fb3da76adc236f4a96`。最终 main 为 `e33b836c67095df1537ac4fb3da76adc236f4a96`。
- **合并前准入：** 四个固定 HEAD 均有此前记录的独立源码 `PASS_WITH_LIMITS`、相关定向回归及 typecheck/build/diff-check 证据；#214/#215 还复用本地组合 HEAD `84b29ad5f306bdee0706db61b63548f72ffa951a` 的 2 项回归。最新 main 上对 #212/#214/#215 的三方树检查均无冲突；#214/#215 仍仅改相邻 Inbox 页面与测试。GraphQL 对 main 返回 `branchProtectionRules=[]`、`rulesets=[]`；REST 保护/rules 查询受私有仓库套餐限制返回 403，不能将 REST 错误解释为绕过许可。仓库现有 pull_request workflow 仅对 `d077-hermes-smoke.yml` 文件路径触发，与本批文件不匹配；其余浏览器/Linux 工作流为手动触发。本批没有触发 Actions。
- **逐项合并后验证：** #198 在 main `5fff974b` 运行 `npm test -- src/App.navigation.test.tsx` → **48 passed**；#212 在 main `f58ecfd2` 运行 `npm test -- src/VocabularyPage.test.tsx` → **5 passed**；#214 在 main `db810654` 运行其 stale Inbox poll 测试 → **1 passed, 74 skipped**；#215 在 main `e33b836c` 运行 Inbox stale poll + Organizer 403 组合回归 → **2 passed, 74 skipped**。测试依赖首次尝试使用用户 npm 缓存时因现有权限错误失败；未更改缓存/系统权限，改在隔离临时仓库和 `/private/tmp` cache 安装锁定依赖后测试通过。没有因该环境错误重复无关测试。
- **审查与边界：** 所有合并均指定并校验预期 PR HEAD；无 force push、admin bypass 或 main reset。没有发生回滚。未触发 Actions、未部署、未访问真实数据，Writer/Promote 与费用门禁保持 OFF。
- **剩余集成状态：** #201 旧 HEAD `353fc9614c77a5e7a9f5d3549f602bb394afd4d2` 的缺失 grant fail-open 已由候选 HEAD `0267a2ce01be0f7898ca6dd7b54a21edd339e8ec` 中提交 `ac1c171d3c5efd3e89fbcc6b578ac354a3d145d1` 修复：`require_action()` 与 `set_session_action()` 对缺失授权记录均拒绝；B 的 55 项定向证据见 #97 评论 #6366400709。A 在当前 PR HEAD 对该安全增量复审 `PASS_WITH_LIMITS`（Review #5629186192），未重跑测试。该结论只覆盖进程内 fail-closed 修复，不表示整项 Core PR、生产或 OS Gate 通过。#207 `d1cd0904c85e606d03ff4479d181dc0164cfc560` 保留既有 `PASS_WITH_LIMITS`；#202 `62c97ff0c66bee6ec8a673790f14098ecb94b898` 仍需核对最新 base/净差异及固定跨层合同。#216 `96d36dcf5248195178f5e86ad132893590987efb` 的 source-level no-replace/recovery 修复复审 `PASS_WITH_LIMITS`；Linux `renameat2`、生产同卷挂载/ACL 与 Synology Drive 未运行。Notes 移动浏览器和 Obsidian 双向同步仍 `NOT RUN`.

## 2026-10-22 — Writer/Promote OS 安全准入与 Linux 隔离实验方案（Issue #96 PMO #6333663799）

- **固定基线与审查输入：** 从 main `563a6fa8e4d6032a34536d879321738c20cf3c24` 的隔离 clone/branch 开始。读取项目 AGENTS、Agent-Rules、CURRENT、审计计划、Environment-Baseline 与 D067/D072/D073/D078/D086 相关边界，并引用 B #97 #6333624251。Environment-Baseline 最近记录为 2026-10-15；只作历史快照，不能当作当前运行事实。
- **设计修订：** 更新 `Production-Readonly-Security-Audit-Plan.md`，提出独立 Core/Raw、Approval Authority、Writer identities；Authority-only Unix socket + `SO_PEERCRED`；Core/Hermes 无 Knowledge 写权限、Private 不挂载；单次授权 capability 与 exact-target create-only；禁止覆盖/删除/重命名；显式指出普通 POSIX 目录写权限不能单独实现 create-only，要求验证 Landlock 或等价内核策略，不支持即阻断；补充源版本竞态、幂等恢复、损坏状态保留及补偿回滚要求。
- **授权包及 Linux 矩阵：** 生产审计要求精确 host/operator/window/container/path/commands/evidence allowlist，字段仍 UNKNOWN。Linux 后续实验只计划在全新 disposable、断网 VM + 临时盘 + synthetic roots 执行，覆盖 UID:GID/peer credentials/socket ACL、Core 直写拒绝、Writer create-only、撤权/版本竞态、崩溃恢复、日志与副作用；不挂载主机/生产数据，不使用容器 socket、Secret 或模型。`OS_ISOLATION_DESIGN=READY_FOR_REVIEW`，`PRODUCTION_READONLY_AUDIT=READY_FOR_TARGETED_AUTHORIZATION`，`LINUX_ISOLATION_TEST=PLAN_ONLY`。
- **最小验证及边界：** 文档/引用/状态静态核对、`git diff --check`；无代码运行测试。未创建 VM/系统用户，不实际测 Linux 身份/socket/mount/ACL，不连接 NAS/生产，不读 Secrets/Private/业务数据，不修改 B 线文件或权限，不启用 Writer/Promote。
- **未决项：** Authority 如何独立证明已认证用户确认需契约复审；真实生产目标/身份/挂载/ACL 与实验 runner/kernel/filesystem 都 UNKNOWN。该方案不能证明生产安全、也不授权生产审计或 Linux 实验。

## 2026-10-22 — Hermes 离线合成角色隔离与生产审计授权包（Issue #96 PMO #6333466319）

- **基线/范围：** 从 GitHub main `140bf90620a922ec6e855e3fae8853952fd65019` 创建隔离分支。只新增 D078 Guard 安全回归和审计计划文档修订，无 Core/运行逻辑变化。
- **离线 Gate：** `HERMES_OFFLINE_ROLE_ISOLATION_GATE=PASS_WITH_LIMITS`。Fake Hermes `httpx.MockTransport` BFF 用例 3 passed：Session A/B citation 绑定、Knowledge 未授权与撤权先于引用/来源 I/O、无授权来源不生成引用；来源/consent binding 测试 29 passed；D078 Guard 单测 23 passed，新增两合成 Session 私有路径均 fail-closed 且拒绝 receipt/log 不含源 marker。全程临时 synthetic roots；未启动 Hermes 或使用网络、真实模型、凭据、业务数据。此证据只覆盖现有代码 seam，不证明生产 hook/容器 UID/真实 ACL。
- **生产计划独立复核：** 发现前版授权表缺少精确命令、Docker 权限影响、输出留存和容器身份/target 未知时的明确停止规则；已补入 `Production-Readonly-Security-Audit-Plan.md`。命令限定 exact-container `docker inspect --format`、单路径 `stat`/可选 Synology ACL、逐个 exact secret target 的 `docker exec stat`；排除 `Config.Env`/env values、广泛 discovery、shell/wildcard/递归/读取 Secrets 正文。指出 Docker socket 风险、Private 内容边界、脱敏/本地安全存档和无写入回退。
- **授权状态：** `PRODUCTION_READONLY_AUDIT_PLAN=READY_PLAN_ONLY`。host/IP、operator/权限、时间窗、当前 container ID/UID:GID、精确路径和 secret targets、证据位置均仍 `UNKNOWN`；未连接生产/NAS，未运行命令。实际审计需另行明确批准完整 allowlist。
- **P0/P1 与最小测试：** 未发现新 P0/P1 或可复现 Core 缺陷；没有底层缺陷交 B。引用 PR #190 固定 HEAD `849ab4199affa2b2b4dcf88bec4e1efd47769b86` 上既有 Web 6 files/102 tests + typecheck/build/diff-check（PMO #6333466319），按 #6333522455 未重跑。仅跑本轮必要测试：Guard 23、BFF 3、source/consent binding 29；未跑 Core/Web 全量、浏览器、Vite/HTTP、build/typecheck（无相关运行代码/依赖修改）。
- **安全与交付：** 没有真实数据、Writer/Promote、model、外网、NAS/Container/Secrets/ACL/mount 操作；无部署/合并/CI。Issue #96 为执行结果主记录；本候选含安全回归测试和计划实质修订，开 Draft PR 供独立复审。

## 2026-10-22 — P0/P1 回归、Companion 与响应式检查（Issue #96 PMO #6333339018）

- **固定输入与实现：** 从 main `4e51fd23d830db3b263271e7a61acda8433cd074` 创建隔离候选。Task 创建成功后按 open 状态显式读回；若旧筛选隐藏刚创建的 Task，则清除筛选并展示。Core 回执有效但列表 GET 失败时单独显示“创建已确认”和读回错误，避免将创建误报为失败。为这两个场景补回归测试。
- **P0/P1 回归 Gate：** 六个 Web 定向测试文件（Task、Capture/Inbox/Review、Journal、Companion、Planning、Review）共 **102 passed**。覆盖 Capture 保存失败保留 Raw、重试后关联正确 Review；Journal 人工追加与读回失败；Task 过滤器隐藏、成功回执/失败读回拆分；Companion revision/retry 与跨 Chat Session 隔离。`P0_P1_REGRESSION_GATE=PASS_WITH_LIMITS`。没有修改 Core，未重跑未变化 Core 套件。
- **响应式检查：** `MOBILE_RESPONSIVE_GATE=PASS_WITH_LIMITS`，依据现有 760px CSS 断点、Review 单栏布局/Task 单列布局及 jsdom 移动内部滚动回归。没有独立可切换视口的浏览器会话，Edge mobile screenshot/browser `MOBILE_BROWSER=NOT_RUN`；未安装浏览器，未声称设备验收。
- **其他验证：** `npm run typecheck` PASS；`npm run build` PASS（现有 Canvas 大 chunk 警告）；`git diff --check` PASS。未触发 CI。
- **生产只读审计准备：** 新增 `Production-Readonly-Security-Audit-Plan.md`，定义只读取经单独 allowlist 批准的主机/容器/UID:GID/挂载/目录 POSIX 与 ACL 元数据、Secrets 名称/存在性/权限，不读取值或业务内容、不递归、不写入、不提权绕过；含停止条件与零写入恢复说明。区分仓库历史记录和 UNKNOWN 的当前运行状态。单独提出离线 synthetic Hermes 角色隔离验证。`PRODUCTION_READONLY_AUDIT_PLAN=READY_PLAN_ONLY`；生产审计与 Hermes 测试 `NOT_RUN`，没有生产连接。
- **安全与交付：** 未触碰真实 Task/Journal/Knowledge/Private/Session；未操作 NAS、Compose、UID/GID、ACL、mount、Secrets、Writer/Promote；未部署、合并或触发 CI。Draft PR 和固定 HEAD 在候选最终推送后回填；生产授权仍需另行明确。

## 2026-10-22 — V1 P0/P1 连续任务 Capture→Inbox→Review 与关键入口（Issue #96 PMO #6332771271）

- **固定输入与范围：** 从 main `3efef1939011fd755842602ef85b79d516dd7e48` 建隔离分支 `codex/v1-p0-p1-closeout-20261022`。仅 Web + 基线文档有改动；未改 Core。只用私有临时目录、合成账户/Task/Journal/Capture 内容与 Core Uvicorn + Vite 同源 localhost。
- **Capture 正向路径：** Edge 实际登录并提交合成文本；Capture 返回成功并保留 `Capture-Inbox-Review.md`；Inbox 明确切至 Capture 范围后读回 `capture.md` 原文，再打开对应 Review，验证待审核状态、来源元数据与正文一致。当前页面仅有“暂缓”，Promote 为关闭状态；没有批准或写入 Knowledge，因此 `CAPTURE_REVIEW_POSITIVE_GATE=PASS_WITH_LIMITS`，`PROMOTE_BLOCKED_BY_DESIGN`。
- **用户入口与合成业务：** Today 首页禁用“新建记录”改为“新建待办”导航到 Task 表单；创建前后 Core 回执核验 Task ID/title/due/status/source/timestamps，创建后分别读取 Task 列表，区分写成功和列表刷新失败。相同内容的模糊失败重试沿用同一 Idempotency-Key，内容变化生成新键。Edge 完成 Home→Task 创建→列表读回。Journal 页面用合成原文点击“追加原话”并读回成功；既有显式入口没有源码变更。Daily Brief `approved_import` 仍 501，手动入口已显示不支持说明。
- **回归与测试：** 新增 Task 创建成功/读回、网络结果不确定时复用幂等键、首页入口导航测试；Daily Brief 增加 `approved_import` 未实现说明测试。Task/App 定向 Web 2 files/54 passed；Brief 定向 1 file/16 passed；Brief 改动后再次 Web 全量 38 files/422 passed；typecheck、build、diff-check PASS。Core Task/Capture/Inbox+Review 定向 44 passed、4 subtests；Core BFF/Auth 定向 32 passed。没有 Core 源码变化，未重跑未变化的 Core 全量。Build 保留现有 Canvas/Notes 大 chunk 提示。
- **安全与 Gate：** 未认证 Core `/api/tasks` 返回 401，带 `Cache-Control: private, no-store`。桌面 Edge 1770px Journal DOM 无横向溢出；移动视口 `BLOCKED_ENV`。`P0_P1_ENTRY_GATE=PASS_WITH_LIMITS`；`V1_MUST_GATE=PASS_WITH_LIMITS`；`COMPANION_GATE=NOT_RUN`；`REAL_BROWSER_GATE=PASS_WITH_LIMITS`（桌面合成）；`PRODUCTION_SECURITY_GATE=BLOCKED_ENV`。真实模型、生产/NAS、真实 Vault/Private/用户内容、外部渠道、正式 Writer/Promote、用户验收均未执行。
- **交付：** `00-CURRENT.md` 已更新 P0/P1 状态及旧 Capture 正向“NOT_RUN”缺口。Draft PR #189 已打开，最终固定 HEAD 以 PR head 和 Issue #96 最终回填为准。本轮不触发 CI；唯一 PR workflow 的 paths 只匹配该 workflow 文件；不合并、不部署。

## 2026-10-22 — V1 可用性收口与 P0/P1 浏览器修复（Issue #96 PMO #6332253939）

- **基线与范围：** 从 GitHub 最新 main `30976e87ca9f03940e2a4d9b13f684d7b93459f7` 建隔离 A 候选。仅使用私有临时目录、合成 Task/Project/Journal/Brief/App 凭据、本地 Uvicorn Core + Vite + Hermes stub；模型调用关闭。未触生产/NAS/真实 Vault/Private，未启 Writer/Promote，未合并或部署。
- **矩阵与门禁：** 更新 `00-CURRENT.md` 现有 V1 MUST 和 D077 Companion 矩阵，采用 `IMPLEMENTED / SYNTHETIC_PASS / BLOCKED_ENV / NOT_RUN / NOT_DONE`，按 P0→P1→P2/P3 排列。报告 `V1_MUST_GATE=PASS_WITH_LIMITS`、`COMPANION_GATE=PASS_WITH_LIMITS`、`REAL_BROWSER_GATE=PASS_WITH_LIMITS`（Edge 桌面合成；iPad/Mobile 视口工具阻断）、`PRODUCTION_SECURITY_GATE=BLOCKED_ENV`。
- **普通缺陷修复：** Core Planning 创建回执现在与 preview step DTO 一致（`decision=pending`, `execution_status=not_started`），消除有效创建被 Web 拒绝；Companion Preferences UI 按 Core 的 `settings` 嵌套成功回执验证并安全恢复状态，防止 Today 面板启用后崩溃；Journal 页面同时匹配裸 entry ID 与 date-qualified 来源 ID，Brief 回跳后正确高亮原 Journal 条目。三项均新增回归测试。
- **真实 Edge 桌面浏览器（localhost 合成）：** 登录、Inbox/Review 中性空态、Chat 合成 Session、Knowledge 可信空态、Projects、Today/Calendar、Daily Brief、Journal 路由可见。实际完成 Brief 手工来源选择→保存→回读，Task/Project/Journal 引用回跳；Planning 从 Task/Project/Journal 元数据创建、逐项批准、每项独立 `effect=none` 合成执行、刷新恢复和跨 Session 隔离；Companion 仅用户显式启用/计算，反馈仅记录。Journal 引用命中高亮修复在重启后的最新 Edge 页面复验通过。当前浏览器视口 1770×1150，文档宽度相同，无横向溢出；无法用当前 Edge automation 改变视口，平板/手机 `BLOCKED_ENV`。
- **合成安全 Gate：** 在固定候选树运行 `web-app/e2e/scripts/p3_consolidated_vite_gate.py`，`P3_1_5_HTTP=PASS_WITH_LIMITS`；真实 `create_app()` + Uvicorn 经 Vite 同源代理，纯临时合成数据。覆盖 session 不匹配、权限撤销先于来源读取、CAS 单胜者/幂等重放与冲突、来源版本漂移、显式拒绝/取消/重复动作、业务来源字节不变、response no-store、敏感正文/本地路径不外泄、重启后状态回读及 `effect=none`。
- **测试证据：** Core 全量 `PYTHONPATH=. /private/tmp/secondbrain-p2-1-venv/bin/python -m pytest -q` → 510 passed、26 warnings、28 subtests；Web 全量 `npm test` → 38 files / 419 tests；`npm run typecheck`、`npm run build`、`git diff --check` PASS。Web build 保留既有 Canvas 2.3 MB / Notes 532 KB chunk 提示；此前锁依赖时报告 4 项 low/moderate advisories，未改依赖。
- **BLOCKED_REQUIRES_AUTHORIZATION：** 真实 Hermes 角色隔离、Writer OS UID/GID/ACL/mount/peer、Raw admission、Private、生产 Compose、真实 Vault/个人 Session、微信/飞书、付费/外部模型及任何外发或正式 Writer/Promote。最小后续包建议限于指定运行环境/路径与身份的只读核验，不读正文、不写业务数据，明确停止/回退条件；外发或模型测试另列数据范围/成本并另授权。本轮未执行授权门外操作。
- **未验收与下一授权门：** Capture/Raw→Review 正向完整浏览器路径、真实模型回答 grounding、真实记忆学习、平板/手机视口、生产 UID/GID/ACL/mount/peer、Private、Writer/Promote、NAS/Compose、真实 Vault/用户内容、外部渠道/付费模型均未本轮执行；相关项仍为 `NOT_RUN`、`NOT_DONE` 或 `BLOCKED_ENV`。完成情况与最终固定 SHA 由对应 Draft PR 及 Issue #96 交接记录提供；不把本地 synthetic pass 表述为生产或用户验收。

## 2026-10-22 — Stage 2 #181 收口与 Stage 3 P3-1～P3-5 累计 Web 联合 Gate

- **Stage 2 收口：** PR #181 固定 HEAD `7cf9ac10ce67efdcce779c71fb8c29fb81b519a4` 获 PMO 最终源码/Gate `PASS_WITH_LIMITS` 与 `MERGE_READY_FOR_APPROVAL`（#181 review #5608840413）；随后 GitHub 于 2026-10-22 03:26 UTC 合并到 main `aff7d9efdf758e0e957f30bf9749bd7b95a054fa`。该合并在 A 执行阶段三期间由 GitHub 状态确认，A 未执行合并。
- **Stage 3 固定输入与 Core 修复：** 起始 main `57d0d3d94f92d235dd8c0c088bb1561cde76f3ae`；#181 合并后更新到 `aff7d9efdf758e0e957f30bf9749bd7b95a054fa`，并将整个 P3 累计候选重放到该最新 main；候选中累计 Core HEAD `574da42803e0681d95095f48ec97bb2ce1660fc7`。累计 Core #182 `17c76b7652b06bc9de18ba5d92c3ed1ca3340b85` → #183 `ef82e36e2047321a5088cb79896702281b74e766` → #184 `a722988bf9b9061b2209fe325b485d29f5a02f3f` → #185 `c3c755cd792bdbad43ab11955ec1fdcf4586f7ac` → #186 `128a45548c2315e478329011a84b0112f8b219df`。A 独立复审发现：合法 calendar_window 不得允许空 source_refs；非字符串 kind、decision、command、rating 必须 HTTP 400 而非未处理异常。B 将修复放在 #182 并顺序重放堆叠；更新固定 SHA：#182 `fd940daa535db0dd18935337c865e771e2d64f9c` → #183 `c02fbb5413232088a26b69cc174f2b0e09ec6145` → #184 `0e65b5c2fe278e11357586b2f387792df05629f5` → #185 `c290976762e629009ad4a3bd09ccc966b2cb308f` → #186 `d21cf6297754520ddbc10e10e08fdf4e599cff17`。B 报告定向 Core HTTP 测试 11 passed；A 在最终堆叠树重跑 `pytest -q tests/test_planning.py tests/test_app_auth_action_registry.py` 得 **11 passed，1 条 Starlette/httpx deprecation warning**。
- **A Web 候选：** 从更新后的 #186 累计固定树开展并重放到 #181 合并后的 main；Chat UI commit `2633c37efb597716b0311539728f46ee9a1cc4b4`，Gate 修订 commit `1137681d690dbbe998f10d64c4924663c7042e34`，最终文档另行提交。新增 Chat 显式计划面板：用户加载并选择 Task/Project/Journal metadata refs（不读取 Journal 正文）、可选有界 Calendar window；Core 再核验版本。支持 Session-scoped 恢复、逐步 approve/reject、独立 synthetic `effect=none` execute、pause/resume/cancel/retry-ready、只读 retrospective/feedback。验证响应 event/session/revision/身份/来源格式，按精确操作 payload/session 保存幂等键；模糊失败复用原 key，已成功回执与后续列表刷新错误分开呈现。来源刷新会清除过期候选选择。
- **Web 验证：** `npm test` → **38 test files / 417 tests passed**；`npm run typecheck` PASS；`npm run build` PASS（既有 Canvas/Notes chunk-size 提示）。新增 4 个 PlanningPanel DOM regression tests，覆盖显式来源读取、来源选择创建、Session 隔离、Core 确认与合成执行、模糊网络失败重试同 key、UTF-8 500-byte 目标和跨月 Calendar 拒绝。
- **同源联合 Gate：** 在 Core cwd 执行 `PYTHONPATH=. /private/tmp/secondbrain-p2-1-venv/bin/python ../e2e/scripts/p3_consolidated_vite_gate.py` → `P3_1_5_HTTP=PASS_WITH_LIMITS`。脚本实际启动 `create_app()`/Uvicorn 与 Vite 同源 `/api` proxy，只使用 0700 临时 roots/合成 App 凭据；验证 Task/Project/Journal metadata、Journal 正文不出线、候选/复盘/反馈 exact replay 与冲突、Session mismatch 404、权限撤销先于来源读取、批准与每步 effect=none 合成执行、pause/resume/cancel、注入执行失败后显式 retry_ready 再恢复、并发 CAS 只有一个成功、来源漂移拒绝、业务来源文件在计划操作后字节不变、Core 重建后状态/反馈回读与 no-store。
- Core 在最新 `aff7d9e` 累计候选重跑全量 `pytest -q` → **510 passed, 26 warnings, 28 subtests passed**；warnings 为 Starlette/httpx 及既有 Notes TestClient cookie deprecation。`git diff --check` PASS。安装锁定前端依赖时 npm 输出 4 项 low/moderate advisories；没有修改依赖。前端 build warning 与主线现有大型 Canvas/Notes bundle 同类。
- **分层结果：** 源码与 Core 全量 510 项、Web 全量 417 项测试 PASS；真实 Uvicorn+Vite localhost synthetic HTTP PASS_WITH_LIMITS。真实浏览器点击、模型、生产、真实数据、用户验收 NOT RUN；`MODEL_CONTEXT_ADMISSION=BLOCKED`。所有 P3 PR 及 A 候选保持 Draft；无合并、部署、CI/Actions、Writer/Promote。
- A 候选已在重放到最新 main 后重新运行 Core/Web 全量及同源 Gate；最终 PR fixed HEAD 由 GitHub readback 与 Issue #96/#97 收口评论记录。P3 等待 PMO 独立复审；任何合并须另有明确授权。


## 2026-10-22 — PR #181 Companion Feedback revision 合同修复

- 按 Issue #96 PMO 评论 #6331548178 修复跨层缺陷：Core 的 suggestion 公共 DTO 现返回每条建议的正整数 `revision`；重复 evaluate 再次发布仍有效候选时递增该候选 revision，使旧 UI 的反馈 CAS 明确得到 409。Web 严格校验候选 revision、用服务端 revision 提交反馈、校验回执，并在 revision 冲突后重读当前列表并显示提示。
- Web 反馈在网络/服务端模糊失败后保留同一 payload 的幂等键，重试原操作使用相同 key；成功回执校验通过后才从 UI 移除候选。
- 回归证据：`PYTHONPATH=web-app/secondbrain-core /private/tmp/secondbrain-p2-1-venv/bin/python -m pytest -q web-app/secondbrain-core/tests/test_companion_suggestions.py` → 5 passed；覆盖真实 localhost Uvicorn HTTP、首发 revision=1、再 evaluate revision=2、revision=1 stale 409、revision=2 成功、原回执精确重放、改 payload 冲突以及来源漂移失效。Web 组件定向 `npm test -- --run src/CompanionSuggestionsPanel.test.tsx` → 2 passed，覆盖 revision=3 提交、503 后相同幂等键/请求体重试、409 刷新。
- 完整同源 HTTP 合成 Gate：`PYTHONPATH=/private/tmp/p2-2-3-ab-gate-20261022/web-app/secondbrain-core /private/tmp/secondbrain-p2-1-venv/bin/python /private/tmp/p2-2-3-ab-gate-20261022/web-app/e2e/scripts/p2_4_5_vite_gate.py` → P2-4 既有检查通过；P2-5 observed re-evaluate revision=2、stale feedback=409、当前 revision feedback=200、exact replay=True、changed replay=409、来源完成后隐藏、disable 后 empty、no-store 且 GET 未创建 `.tasks.lock`。纯合成临时根，无真实数据/模型/Writer/Promote。
- `npm run typecheck` PASS；`npm run build` PASS（保留既有 Canvas/Notes 大 chunk 提示）；`git diff --check` PASS。仅运行受影响 Core/Web 定向测试与完整既有 localhost 集成 Gate，未重跑无关全量套件。
- 当前候选 PR #181 保持 Draft；本条记录中的新固定 HEAD 以修复提交为准，等待 PMO 对新 SHA 独立复审。未合并、未部署、未访问真实数据、未触发 CI。

## 2026-10-22 — P2-4/P2-5 最终联合 Gate（Issue #96/#97）

- 从 main `57d0d3d94f92d235dd8c0c088bb1561cde76f3ae`（#178 merge）建立隔离分支。核对 #179 `ecb4b18b26e467643b7f0b2ef0d69e036796c5ff` 的历史累计依赖后，只移植净 P2-4；核对 #180 `d16773d61edbbc41a115f2c826eee84ee3832902` 后移植到当前 main，`app.py` 路由注册冲突同时保留 Context Preview 与 Companion Suggestions。未改写 #175/#179/#180 原分支。
- 独立审查发现并修复：相同幂等请求应回放完全一致的原回执；Companion Suggestions 读取 Task 投影不得创建 `.tasks.lock`；P2-4 Grounding Candidates 在响应前二次校验 source version 并剔除漂移项。Today 增加用户显式展开的 Companion 设置/立即计算/反馈入口；未自动读取建议、未触发 Run 或副作用写入。
- 本轮发现的额外 Web 缺口：P2-4 的 Grounding Candidates API 原先没有交互 UI；已在 Chat 增加用户点击触发的只读面板，严格验证 event/session/schema/SHA/no-store，并明确 `answer_attribution=not_established`。P2-5 的 Today 建议面板仅在用户展开时读取，只在点击“立即计算”时 evaluate；反馈使用正确的建议 revision，失败时清掉旧建议，设置重试只对相同 payload 复用幂等键。
- 联合 HTTP 命令（cwd Core）：`PYTHONPATH=/private/tmp/p2-2-3-ab-gate-20261022/web-app/secondbrain-core /private/tmp/secondbrain-p2-1-venv/bin/python /private/tmp/p2-2-3-ab-gate-20261022/web-app/e2e/scripts/p2_4_5_vite_gate.py`。真实 `create_app()` + Uvicorn，经 Vite 同源 `/api` 代理，纯合成临时根；P2-4 observed: login 200、unauth 401、available 200/no-store、no match 200、source drift 200/partial、session mismatch 404、permission revoke 403；响应不含 source text/path。P2-5 observed: default off、evaluate disabled、preference save 200、GET 200 且无 `.tasks.lock`、explicit evaluate 200、feedback 200 + exact replay equality、changed replay 409、Task completion 后建议隐藏、disable 200 后 GET empty 200。Hermes Run 未调用。
- **Gate：** `P2_4_CORE_HTTP_GATE=PASS_WITH_LIMITS`、`P2_4_AB_SYNTHETIC_GATE=PASS_WITH_LIMITS`；`P2_5_CORE_HTTP_GATE=PASS_WITH_LIMITS`、`P2_5_AB_SYNTHETIC_GATE=PASS_WITH_LIMITS`。Web DOM/contract 定向 4 files / 23 tests passed，覆盖显式展开/计算、准确请求体、会话/查询变化清除及严格响应验证；typecheck/build/diff-check PASS。Core 全量 501 passed + 28 subtests 为无变化 Core HEAD 的既有验证；Web 全量 34 files / 407 tests 是改动前基线，不重复运行。Build 保留既有 Notes/Canvas 大 chunk 警告。
- 分层结论：CODE、Uvicorn+Vite 同源合成 HTTP、Web DOM 测试 PASS_WITH_LIMITS；真实浏览器点击 `NOT RUN`（DOM 并非真实浏览器）、模型 `NOT RUN`、生产与用户验收 `NOT RUN`；`MODEL_CONTEXT_ADMISSION=BLOCKED`。未合并、部署、访问真实数据或触发 CI。
- 候选 PR [#181](https://github.com/zxwan829/SecondBrain/pull/181) 保持 Draft；从 #178 main 开始。最终固定 HEAD 以本条后续 docs-only 修订提交为准。联合 Gate 已完成，净新增代码等待 PMO 对最终 SHA 独立复审和合并裁定；不转 Ready、不合并、不部署。

> 本文件按时间保存阶段证据。每条“当前/尚未/未部署”只代表该条记录日期的状态，不覆盖后续结果；最新项目状态只看 `00-CURRENT.md`，最新有据可查的生产快照看 `Environment-Baseline.md`。
>
> 排序：最新记录在前，历史记录在后；具体写入规则以 `Agent-Rules.md` 为准。


## 2026-10-22 — P2-1/P2-2/P2-3 集中合并准备候选

- 按 Issue #96 评论 #6330661993，在 main `df9971bc1aeecc83ed6bd3c10aed2e1dd1eb8a0a` 上汇总固定 PR 输入：Core #173 `535d8f934f7e922ada7e5542dfd84bb391f4a2c0` → Web #174 `e868c35d2196a13663969be2d32c03a7813ccb1a` → Core #177 `ce38826fd469eef11f2894f04bb4fe918797503e` → Core #175 `5c22ee664ca9573b036f30f34669d237ecebef43` → Web #176 `368f10c8e5ebd0bfcf5bfc376e747017b657a5e1`。来源 PR 全部保持 OPEN/Draft。
- #175/#177 对 `personal_memory.py` 的重叠由单一集成结果化解：保留 8 MiB 实际读取上限和读取前后 dev/inode/size/mtime/ctime 稳定性校验，同时保留跨进程锁、revision CAS、幂等回放及冲突拒绝。联合文件测试覆盖全部对应行为；没有把局部解决方案写回 B 的原分支。
- 固定候选上 Core `/private/tmp/secondbrain-p2-1-venv/bin/python -m pytest -q tests/test_context_preview.py tests/test_personal_memory.py tests/test_personal_learning.py`：43 passed。Web 四个 Context/Citation/Personal Memory 文件：35 passed；`npm run typecheck`、`npm run build`、`git diff --check` 通过。Build 保留既有 Canvas 大 chunk 警告。先前 B/A 独立全量测试不重复运行。
- 本地 main+候选 merge-tree 无冲突；仅 Core `personal_learning.py` 和 `personal_memory.py` 有预期重叠，审查后共同结果通过定向套件。五个源 PR 的 Actions 查询均无 pull-request workflow run；本候选仅改应用和基线文档，工作流触发路径过滤为 workflow 文件，未手动触发 CI。GitHub branch protection/rulesets API 对私有仓库返回 403，保护规则状态 UNKNOWN。
- 证据分类：CODE / 本机定向自动化 PASS；HTTP SYNTHETIC 沿用双 Gate #96 #6330632680 的证据；REAL_BROWSER NOT RUN；REAL_MODEL NOT RUN，`MODEL_CONTEXT_ADMISSION=BLOCKED`；PRODUCTION / USER_ACCEPTANCE NOT RUN。候选仍需独立审阅；不把源码准备写成已合并、部署或模型实际使用记忆。
- NEXT：审查集中 Draft 候选与 #96 的 `MERGE_READY`/`MERGE_BLOCKED` 报告；保留原 PR/Draft，等 PMO 后续裁定合并拓扑与审批。不得合并 main 或部署。


## 2026-10-22 — P2-1 A Web Context Preview READY

- 基于文档收口后的 main `df9971bc1aeecc83ed6bd3c10aed2e1dd1eb8a0a`，A Draft PR #174 固定应用提交 `cf7f06f79d7eff409288157127649f75268cf0e9`，状态标记 `A_P2_1_WEB_READY`；结果见 [#96 #6324063852](https://github.com/zxwan829/SecondBrain/issues/96#issuecomment-6324063852) / [#97 #6324066362](https://github.com/zxwan829/SecondBrain/issues/97#issuecomment-6324066362)。
- Chat 显式调用 Context v1 metadata preview；只提交 `{query}`，严格检查 session/schema、来源类型、条数与 8 KiB 上限及 `private, no-store`。仅展示 opaque ID、类型、版本、SHA、时间与状态。输入/会话切换时清除并取消旧请求，403 与无效响应 fail closed；不把来源正文或元数据送入 Hermes，也不声称 grounding。
- Web 全量 32 files / 397 tests、定向 2 files / 25 tests、typecheck、build、diff-check 通过。合成 Mock/DOM 验证不代表 Core+Web localhost、真实浏览器、数据、Hermes/模型、生产或用户验收。Vite build 保留大 chunk 体积警告。
- B PR #173 的固定 HEAD `f7a50fb5e70db2cc513258e3059fb726eed7ad30` 与测试数量记录在 PR 描述；截至本条更新，#97 尚无 `B_P2_1_CONTEXT_READY`，联合合成 Gate 未运行。下一步是双 READY 后由 A 做一次联合 Gate；`MODEL_CONTEXT_ADMISSION=BLOCKED`。

## 2026-10-22 — 阶段一六部分收口，进入 P2-1 Web（Issue #96/#97）

- 按 Issue #96 V2 的明确授权，以 GitHub 普通 merge 顺序合并阶段一第 6 部分：Core PR #171 固定 HEAD `dcb252060d1067ad322837085648942097c4b1a5` → main merge `2abdf4b25420a2efea3088448238cfc4d48af9d8`；Web PR #170 固定 HEAD `c778ae6932ae8ccb091afeb6e82aa2d065aa6855` → main merge `b590c15d81a3a1822304c955c788bfa4c912fea1`。#170 更新前的 A Web 审阅 HEAD 为 `ad54e081d4865307e7d6c9ef2ad08f903d8e6949`；Core merge 是历史父提交。两次 merge 均以 GitHub expected head SHA 锁定，未 force。PR #171 首次请求因 Draft 返回 405；转 Ready 后使用同一 SHA 合并。#170 在 main 前进后 mergeability 短暂为 false，重新读取为 true，且本地 merge-tree 无冲突后按固定 HEAD 合并。GitHub 私有仓库 branch-protection 查询返回套餐限制 403；未绕过规则，最终 GitHub merge API 正常接受两项合并。
- 阶段一六部分盘点见 `00-CURRENT.md` 顶部。现有 #96/#97 阶段账本没有找到第 1–2 部分独立编号 Gate，因此没有追认通过；第 3 部分为 `STAGE1_PART3_SYNTHETIC_GATE=PASS_WITH_LIMITS` 且无新增源码 PR；第 4 部分 #165/#166 已合并，语义仅为可信 Knowledge“检索参考”，不证明模型 grounding；第 5 部分 #167/#168 已合并，Brief 仍是手工内容闭环；第 6 部分 #171/#170 合成 Gate `PASS_WITH_LIMITS`。
- 阶段六固定版本合成证据记录于 [#96 #6323445544](https://github.com/zxwan829/SecondBrain/issues/96#issuecomment-6323445544)，独立源码复审见 [#96 #6323490860](https://github.com/zxwan829/SecondBrain/issues/96#issuecomment-6323490860)。候选运行：Core+Vite localhost HTTP PASS；Core 定向 28 passed、4 subtests；Web 定向 10 passed；Web typecheck/build/diff-check PASS。未变化的全量套件未重跑；真实浏览器仍 `BROWSER_BLOCKED_ENV/NOT RUN`。
- 实际开放缺口：V1 与 D077 Companion MVP 仍 `NOT DONE`；#130 D086 Chat→Inbox 已 merged（`1954f88d1546c3c802c82a97a708aff7c32461f7`）；#164 Today Task 创建仍 Draft/Open。#106 Restricted Writer 的生产独立 OS UID/GID/ACL/mount/peer 准入保持 BLOCKED；#151 Raw 合成 admission 的同 UID namespace/commit 时间窗风险使生产信任边界仍 BLOCKED。真实 Hermes 低信任上下文/grounding、真实数据、浏览器/设备用户验收、部署均未完成。
- 更新 CURRENT 与本条 Progress Log 的治理文档 PR 单独提交；仅修改以上两个基线文档，不混入应用源码或长期治理规则。纯文档改动运行 `git diff --check`，不重跑应用测试。文档 PR merge 后的实际 merge commit 和最终 main 记在 Issue #96 本任务结论。
- **NEXT：阶段二 P2-1 Web。** B 已在 [#97 #6323865325](https://github.com/zxwan829/SecondBrain/issues/97#issuecomment-6323865325) 冻结 Context v1，并在 [#96 #6323867891](https://github.com/zxwan829/SecondBrain/issues/96#issuecomment-6323867891) 同步。A 可立即按 `POST /api/chat/sessions/{session_id}/context-preview` 开发 metadata-only UI；每次按当前 Session 重新请求，依合同处理撤权、漂移、预算与失败，不缓存、不把内容/metadata 发送给 Hermes。`MODEL_CONTEXT_ADMISSION=BLOCKED`；Web 必须区别检索到来源元数据与模型真正使用来源回答，不标 grounded。不得把源码/合成状态写成生产或真实用户验收。

## 2026-10-20 — D089 #128 合并与治理基线追平

- PR #128 的固定 HEAD `203f586a24acd8132620b180e9d1a76a3751a72b` 于 2026-10-20 合并至 main，merge commit `87671644356e01d58ec2780d0c45bd11f4c3edfe`。D089 的 `GET /api/daily-brief/source-options/journal` 正式 Core 路由已进入源码主线。
- B 报告全量 Core 420 tests + 28 subtests、正式 localhost HTTP 路由与定向用例通过；A 对最终 HEAD 的独立验收记录真实 `create_app()` + Uvicorn 正式路由定向测试 1 passed，未报告 P0/P1。测试执行细节见 PR #128 与 Issue #97；本次治理文档更新未运行测试。
- 这确认 Core 源码与本地合成验证，不代表 NAS 部署、真实 Journal/Vault 访问或用户业务验收。本次治理基线 PR #131 补齐 CURRENT、D089 状态和历史进度记录；未操作生产环境、未读取或写入真实业务数据。

## 2026-10-20 — M2 源码进度复核与治理基线纠偏（#76/#96/#97；#128 合并前状态快照）

- GitHub main 固定为 `bff59297b0c33430c9ab2760d74231d32b3d6f71`。Daily Brief 来源 verifier #123、Core 测试路径修复 #124、人工内容持久化 #125 均已合并；这确认源码能力，不等于用户触发的 AI Brief 撰写已实现、后台定时调度已获批、生产数据已接入或用户验收已通过。
- Daily Brief #126 保持 Draft：固定候选已报告隔离 HTTP 来源读取、POST→GET、幂等和冲突验证；Edge 子进程 SIGABRT、Chromium SIGTRAP，真实点击/三视口验收 BLOCKED_ENV / NOT RUN。不重复诊断同一崩溃环境。
- A 线 #127/#129 保持 Draft，来源审查及自动化验证报告通过；浏览器门禁未通过。新 PR #130 为 D086 Web-only Chat→Inbox 候选，报告 283 Web tests、typecheck/build 与合成 Core HTTP 回归通过；未合并，真实浏览器 NOT RUN。B 线 #128 固定 HEAD `203f586a24acd8132620b180e9d1a76a3751a72b`，报告 Core 420 tests + 28 subtests 与本地真实 HTTP 路由验证；A 对固定 HEAD 的独立复审待完成。#106 OS 隔离与 #101 真实渠道接入仍未验收。
- 用户确认 2026-10-22 目标为基本 V1 业务闭环、可接受后续小修；截至本记录仍 AT RISK。原 V1 MUST、Daily Brief 用户验收、Knowledge Promote、安全隔离与生产/真实模型验收仍有未完成项。
- 本轮基线纠偏：CURRENT 将合并后的 #123/#125 与 Draft/阻断清楚分层，并记录新开 PR #130 的未合并候选状态；笔记规范取消状态/创建日期/修改日期的自动维护要求；D087 仅表示微信/飞书渠道架构，D088 表示 Daily Brief 业务范围，D089 表示 Journal source-options 冻结合同。Environment-Baseline 仍是 2026-10-19 最后生产快照，本轮未核验生产。
- 本记录仅由待审治理文档 PR 提议；PR 合并后才进入正式基线。未运行测试，未合并 PR、部署、读取或写入真实业务数据，未调用模型。

## 2026-10-19 — Hermes 静态 IP 冲突修复与单服务恢复（Issue #76）

- 按 Issue #76 评论 #6268120112 执行一次 Hermes-only 修复。实时 Compose 前 SHA-256 `d34cb7492d3740ea13d6518ec17532ac855bded9bd921d318827c25aaea949d3`，Hermes 固定请求 `172.18.0.2`，而 App endpoint 已占用同一地址；这与失败容器 `.State.Error=Address already in use` 相符。仓库运行示例使用 `hermes:8642` 服务 DNS；没有发现部署模板对该静态地址的依赖。
- 建立精确回滚快照 `/volume1/docker/secondbrain/rollback/hermes-ip-conflict-20261019T132138Z/compose.yaml`：目录 `0700 root:root`、文件 `0600 root:root`，SHA `d34cb7492d3740ea13d6518ec17532ac855bded9bd921d318827c25aaea949d3`，与切换前正式 Compose 逐字节一致；元数据记录旧容器/镜像。候选 `docker compose config --quiet` 通过，唯一差异为删除 Hermes `ipv4_address: 172.18.0.2`。正式 Compose 更新后 SHA `5703458d5db4703d3a1e9377c3aafbfacc470863b92c15f4305e802f64b1c17b`。
- 只执行一次 Hermes-only `up -d --no-deps --no-build --force-recreate --pull never hermes`。新容器 `908a4b37c41344e97441013a18995e727971a10242d49dee65e39f3bf00c43d6` 使用原镜像 `sha256:b99b1762631846d5ed3f8648ccc2c7ef2625b004234bbf276add2f8855357e9a`，running、RestartCount 0，动态 endpoint `172.18.0.3` 与 App `.2` 不同。`http://hermes:8642/health` 从 App 网络返回 200，宿主 Dashboard `192.168.3.27:9119/` 返回 302 登录重定向；App health 200。新启动后短暂未就绪，约 35 秒检查通过，未重复重建。
- App 与 Vaultwarden 容器身份、镜像和健康状态未改变；13 个容器总数不变，Docker daemon/DSM/Container Manager 未重启，其他服务未操作。Promote OFF、Knowledge RO、Private 无挂载及 Hermes 既有挂载/安全边界保持。没有业务写入、真实 Vault 内容读取或模型调用；用户业务验收未运行，无回滚。
- 结论：静态地址冲突根因 **CONFIRMED**，Hermes-only 恢复 **PASS**。恢复状态及 Compose 动态分配策略同步到 `Environment-Baseline.md`；历史环境快照保留。源码无部署模板使用静态 `.2`，因此本次无代码改动。完整脱敏执行证据已提交 Issue #76；具体回滚快照及现场状态见该 Issue。

## 2026-10-19 — M2 P1 App-only 生产部署（Issue #90）

- 按 Issue #90 授权，固定源码 `443991061ea446686b54bfb9e8b2d980183f1338`；用 `web-app/Dockerfile.app`、`web-app/` 构建上下文和 `VITE_ENABLE_NOTES=true` 构建完整 App，候选 `secondbrain-app:m2-44399106-app-only`，Image ID `sha256:e55b0e9c65433a208df0f66a68ec2f91e2341b163108e5d09030ac4a7b343f47`。构建前已核验 NAS 资源、旧 App 镜像、Compose 和回滚条件；使用 NAS legacy builder 并限制 CPU 0-1、内存 8 GiB。构建日志警告包括 4 项 npm audit（2 low/2 moderate）、弃用依赖、Vite 大 chunk、pip root 安装提示及 legacy builder 弃用；未升级依赖。
- 隔离预检使用无网络、只读 rootfs、合成凭据/目录且无生产卷/Secret/端口的临时容器。健康、`/chat/blank`、Inbox/Review/Knowledge/Notes 路由、14 个静态资源及匿名 Chat/Promote API 鉴权通过；临时容器与合成目录已按精确路径移除。候选镜像与构建证据保留。
- 切换前正式 Compose SHA `5d15c9ac51d4bd9f3cd682ef60e4e97d77b5d7e212ae73d0bf5e3126aad0da8d`，即时回滚快照 `/volume1/docker/secondbrain/rollback/m2-44399106-predeploy-20261018T175818Z/compose.yaml`（目录 0700、文件 0600），快照与 live 文件一致。只更改 App image，部署后 SHA `a0d6775e8a785845ee32369a68141410e99988df316714f507b0d98743734686`。执行 App-only `--no-deps --no-build --force-recreate --wait --wait-timeout 120`，37 秒 healthy；容器 `a574dd88d9bd87c3d94f584791312473e91eeeeb2ffdac64c6684f972be506cb`，RestartCount 0。无回滚。
- 生产只读 Smoke：`/health` 200；`/chat/blank`、`/inbox/source`、`/review`、`/knowledge`、`/notes` HTML 200；14 个静态资源 200；匿名 Chat/Promote API 401 JSON。Hermes/Guard 未重建或重启，Hermes 容器、镜像、StartedAt、RestartCount 与切换前一致。Promote OFF、Knowledge RO、Private 未挂载；Core-state 新建 `b1b-operations` 空目录 `1026:100 / 0700`，audit 文件不存在。
- **状态：DEPLOYED / HEALTH PASS / ROLLBACK NONE / BUSINESS ACCEPTANCE NOT RUN / USER ACCEPTANCE PENDING。** 未访问真实 Vault/私人正文、未创建生产业务记录、未调用模型或启用 Promote/B3。宿主与容器对 Review、Knowledge、Capture Raw 的 bind 根目录 mode 分别观察到 0700 与 0777；原因 UNKNOWN，本轮未改 ACL/权限，仍属运行风险。完整部署证据已在 Issue #90 报告；本条是部署时的原始证据，后续 ChatGPT 已复审 DEPLOYED / HEALTH PASS；下一阶段任务以 `00-CURRENT.md` 唯一 NEXT 为准，业务验收仍未执行。

## 2026-10-18 — 用户批准 M2 P0-A 本地实施及 P0-B 只读设计

- 用户确认「按你的规划进 m2」，A 主线在 [M2 总控 #76](https://github.com/zxwan829/SecondBrain/issues/76) 记录新阶段授权边界。此前 M1 #66 已有限验收并 CLOSED；GitHub main 仍为 `b446913525284762acdc249101c1da7c3e0babf7`（PR #73 仅文档），生产 App 最后已验证源码仍是 `473948dd2e9b3d448b71eeba56a1474454883353`，本轮未重新连接 NAS。
- **P0-A 第一执行任务：** [#74](https://github.com/zxwan829/SecondBrain/issues/74) 旧 `/inbox` 默认安全入口、本地请求级隔离、明确选择 Capture/Notes 作用域及精确来源才加载正文；A 负责架构/测试契约，B/Codex 可在独立 worktree 开发、合成验证和提交 PR，但不可自行合并或部署。
- **P0-B 并行设计：** [#78](https://github.com/zxwan829/SecondBrain/issues/78) 现行 Review→人工批准→受控 Core Promote→Knowledge→回源检索的只读接口、权限、幂等与恢复方案；尚不授权正式写入实现。P1 D086 保持普通聊天不自动收录，只有明确收录/同意建议才将指定内容先存 Inbox；Personal Memory 的低风险学习是另一受控机制。
- **安全限制**：#75 生产 HTTP 重放和 Network 缺口、#55 共享词库生产写入 BLOCKED、#44 D084 历史根因、C2c-2 延后 M2 仍独立追踪；Knowledge RO、Promote OFF、Private 不访问、Hermes/Guard 不动。PR #77 文档状态同步继续 OPEN、等待独立 review/用户合并许可。本轮未部署、未使用真实数据、未调用模型。

## 2026-10-18 — M1 用户有限验收结项与 M2 规划交接

- 用户明确批准 **M1 LIMITED ACCEPTED / WITH EXPLICIT EXCLUSIONS**，并授权在 GitHub 完成最终记录后关闭 [Issue #66](https://github.com/zxwan829/SecondBrain/issues/66)；A 主线写入完整交付/风险归属并以 `completed` 关闭，复查为 CLOSED。**这是阶段有限结项，不是 M1 全部能力通过，更不代表 SecondBrain V1 DONE。**
- 最新生产 App **仅按最近一次有证据的部署记录**为源码 `473948dd2e9b3d448b71eeba56a1474454883353`，镜像 `sha256:70f8277f4d29c2bf8e50d3f7d135f034f04a90b421928d9836515d79a7143b3d`，App-only 健康检查 PASS；GitHub PR #73 已合并，仅更新文档，main `b446913525284762acdc249101c1da7c3e0babf7` 不代表重新部署。
- M1 接受的分层证据：D084 前一 M1 镜像的 Journal/Task、跨 Session、Core Store 重放有限合成 PASS；D085 新 M1 镜像 B1 精确来源 5 条 Proposal、Journal/Review 各 1 个受控执行、Project 拒绝与刷新恢复有限 PASS；D086 词库代码/隔离合成 PASS，但共享 catalog 后续生产写入继续 BLOCKED，既有合成 revision=1/审计保留。新镜像 D084 未重测，历史异常根因 UNKNOWN。
- **明确排除项及跟踪：** 旧全量 Inbox 来源安全隔离 [#74](https://github.com/zxwan829/SecondBrain/issues/74) BLOCKED；生产 HTTP 同键重放 NOT RUN / 完整 Network 和数字 HTTP 状态 UNKNOWN [#75](https://github.com/zxwan829/SecondBrain/issues/75)；D086 全局词库/真实内容 [#55](https://github.com/zxwan829/SecondBrain/issues/55)；D084 历史异常 [#44](https://github.com/zxwan829/SecondBrain/issues/44)；C2c-2 项目关联延期 M2，原 Project execute 501 不变；正式 Knowledge Promote 仍 OFF、Knowledge RO，真实 Vault/私人内容、付费模型、微信及完整 Web App V1 MUST 未据此验收。
- 已建立 [M2 规划总控 #76](https://github.com/zxwan829/SecondBrain/issues/76)，首要建议为安全 Inbox 来源选择与 Review→明确批准→受控 Promote→Knowledge→可回源检索，**仅规划**；任何新开发、合并、NAS 改动、模型/数据使用须另行授权。用户要求全面审计文档，已在 #76 记载基线遗漏和修正范围，使用独立 docs PR 审核；本轮未修改 NAS/Secret/真实业务数据或调用模型。

## 2026-10-18 — M1 B1 单来源生产闭环有限验收

- 在已部署的 M1 App `473948dd` 上，仅使用已授权的 B1 合成 Draft 和其 Proposal IDs。5 条来源绑定 Proposal（journal/review/project/type/tags）创建并刷新恢复；Journal 与 Review 经审批、精确预览、明确确认后各成功执行一次；Project 提案明确拒绝且未执行；刷新后执行与拒绝状态恢复。
- **有限 PASS：** B1 来源与提案创建、Journal/Review 单次执行、Project fail-closed 拒绝、刷新恢复。该结论不是 M1 整体用户验收，也不代表 D084 新镜像复验通过。
- **遗留状态：** 生产同键幂等重放 **NOT RUN**（无安全可确认的原始下游键）；完整浏览器 Network 审计及数字 HTTP 状态 **UNKNOWN**；旧全量 `/inbox` UI **BLOCKED**；D086 共享词库后续生产写入 **BLOCKED**（既有合成标签/revision 保留，不再写入）；C2c-2 **OUT OF M1**。D084 历史根因继续 **UNKNOWN**。
- 未访问其他来源、私人 Session 或真实 Vault 内容，未调用模型、未部署/重启或修改 NAS。生产业务证据和 A 裁定见 [Issue #66](https://github.com/zxwan829/SecondBrain/issues/66#issuecomment-6248598848)；等待 A 收尾风险评估后由用户决定是否接受 M1 有限验收。


## 2026-10-18 — PR #72 合并后 M1 App-only 更新部署

- 按用户授权，从固定源码 `473948dd2e9b3d448b71eeba56a1474454883353` 的 `web-app/` 上下文和 `Dockerfile.app` 构建完整 App，显式 `VITE_ENABLE_NOTES=true`。本机无 Docker daemon，使用 NAS Docker legacy builder（buildx 不可用），限制到 CPU 0-1 / 8 GiB；构建完成，Image ID `sha256:70f8277f4d29c2bf8e50d3f7d135f034f04a90b421928d9836515d79a7143b3d`，tag `secondbrain-app:m1-473948dd-notes`。前端定向 `App.navigation.test.tsx` 与 `UnifiedInboxPage.test.tsx` 25 项、typecheck、Vite Notes=true build 通过。npm audit 提示 2 low/2 moderate，另有弃用包、Vite 大 chunk 和 legacy builder 警告；未升级依赖。
- 无网络隔离预检使用 synthetic environment/credentials、read-only rootfs、临时 tmpfs、无生产 Secret 或业务挂载。`/health`、`/chat/blank`、`/inbox/source`、入口 JS/CSS、Notes chunk 通过；匿名 Chat API 为 401 JSON。首个夹具因合成 password 文件权限不是 0600 被 Core 按设计拒绝；修正夹具后预检通过，临时容器已移除。
- 部署前验证旧 App Image ID `sha256:4adcf9cfe3f6257c733efa911455ca02653783ba763f9e2f512f4d3582694ce1`、Hermes 身份、Compose SHA `5c12fda28f3e5e9cd001d238515bd6599adaf5e502686f5d30fcbcb4a8c72f80`、UID/GID、Notes 配置及挂载权限边界；`docker compose config --quiet` 通过。只更改 Compose 中 App image 一行。即时回滚快照 `/volume1/docker/secondbrain/rollback/m1-473948dd-predeploy-20261018T094236Z/compose.yaml`，目录 0700、文件 0600、哈希与 live Compose 完全一致。
- 仅执行 App-only `compose up -d --no-deps --no-build --force-recreate --wait --wait-timeout 120 secondbrain-app`。新容器 `0ab478227d89d81981142493a51e917bac98926b5d4f1089268893f41c5a6a30`，Image ID 与候选一致，39 秒 healthy，RestartCount 0；Compose SHA 更新为 `5d15c9ac51d4bd9f3cd682ef60e4e97d77b5d7e212ae73d0bf5e3126aad0da8d`。生产 `/health`、`/chat/blank`、`/inbox/source`、JS/CSS/Notes chunk 200，匿名 Chat API 401 JSON。未回滚。
- Hermes 容器/镜像/StartedAt/RestartCount 不变，Guard 没有独立容器；仅 App 镜像改变，Notes 配置、Promote=false、Secrets 引用和挂载边界保留。未改写个人记忆设置；Organizer model/scheduler 关闭。没有 Chat Run、模型调用或业务写入，也没有读取私人/真实业务正文。部署前后 Core-state 目录元数据未做差分，精确新增内部状态目录数量 UNKNOWN。
- **交付边界：** 新镜像构建、隔离预检和生产 health/路由/静态资源/匿名鉴权 PASS；本轮 D084/D085/D086 生产业务验收 NOT RUN，历史 D084 根因 UNKNOWN。没有回滚。实际部署证据已提交 Issue #66；CURRENT、Environment-Baseline 与本日志的状态同步通过独立文档 PR 提交，等待 A 主线复审。


## 2026-10-18 — M1 固定源码正式 App-only 部署

- 按用户明确授权，部署固定源码 `74d698dc97dd9df423664141b80fd8003fbca534` 对应已验证候选 `secondbrain-app:m1-74d698dc-notes`，Image ID `sha256:4adcf9cfe3f6257c733efa911455ca02653783ba763f9e2f512f4d3582694ce1`。未重新构建；仅重建 App，Compose 命令使用 `--no-deps --no-build --force-recreate --wait --wait-timeout 120`。App 在约 31 秒内 Healthy，RestartCount 0。
- 切换前/后 Compose SHA-256 分别为 `9c0932c04d6984cd2e491738d51eb6235d7182ccfca8146678fc18cdabe6097d` / `5c12fda28f3e5e9cd001d238515bd6599adaf5e502686f5d30fcbcb4a8c72f80`。结构差异仅为 App image 和两项 Notes 配置。精确切换前快照位于 `/volume1/docker/secondbrain/rollback/m1-app-only-20261018T072428Z/compose-before.yaml`，目录 0700、文件 0600，哈希与切换前正式 Compose 一致。
- Notes Drafts 仅在现有 Core-state RW 挂载中建立空目录，容器路径 `/var/lib/secondbrain-core/notes-drafts`，owner/mode `1026:100 / 0700`；授权根 `{}`，未扩大真实 Vault、Knowledge、Private 或 Projects 授权。Promote 保持关闭，原挂载权限边界未变。
- GET smoke：`/health`、`/chat/blank`、入口 JS/CSS、Notes JS chunk 均 HTTP 200；匿名 Chat API 为 401 JSON。Hermes/Guard 容器 ID、镜像 ID、StartedAt 与 RestartCount 均未变。没有回滚。
- 未执行业务验收：无生产 Session/Journal/Task/Inbox/Notes 记录、无模型调用、无私人正文读取。D084 根因 UNKNOWN，业务验收仍未完成。部署事实与脱敏证据已提交 Issue #66；Issue #44 评论审批限制未绕过。当前状态文档校准通过独立文档 PR 提交，等待 A 主线复审。

## 2026-10-18 — D085-C2c-1 PR #63 崩溃恢复与并发补测

- 按 PR #63 Review #5561132224 与评论 #6244818115，在原 Worktree/分支补充 Journal、Review 两类故障恢复和同 proposal 并发执行合成测试。故障注入覆盖目标已持久化、Core `finish_execution` 尚未调用后以新 Core/Capture store 重启；同一预览恢复到原 target ID、单一产物、一条 attempt 和一致成功审计。并发测试在两请求都越过 Core reservation 后同步进入目标接口，验证两响应为 200、仅一个新建/另一个 duplicate、目标唯一，后续重试为 duplicate。
- 测试发现 Review 首次成功响应误报 `duplicate=true`（原逻辑把 completed 状态直接当作重复）。CaptureService 现在返回仅供内部路由判定的幂等重放标志，路由清除该内部字段后准确报告首次执行与恢复/重试状态；未改变持久化状态格式和目标内容。
- Core `tests.test_inbox_proposals tests.test_capture` **38 项通过**；Inbox `UnifiedInboxPage.test.tsx` **7 项通过**；前端 `tsc --noEmit` 与 `vite build` 通过，build 有大型 CanvasEditor chunk 提示；`git diff --check` 通过。PR #63 已转为 Ready for review。本轮仅使用合成数据；未触碰真实 Vault、付费模型或 NAS；未合并、未部署，用户验收待定。

## 2026-10-18 — D085-C2c-1 Journal / Review 受控执行（Draft PR #63）

- 按 Issue #46 最新评论 #6244537788，从 main `3080506b053d3876d292d9199049fd12e3247b88` 建立独立 Worktree/分支。保留 CURRENT 中 D084 唯一 NEXT，以及 main 的 D084、D086 和运行环境记录。
- 在 C2b 来源绑定审批上增加独立预览和执行确认：旧 `approved_recorded` 不自动执行；执行时检查来源读取权限、Notes ETag/Capture 原件摘要、词库 revision、提议状态与版本、目标动作权限和预览哈希。执行状态/尝试 ID、执行者、目标引用、源/输出摘要、失败码及历史事件由 Core 持久化。
- Journal 通过专用 JournalStore 追加用户预览的原文及稳定幂等键；Review 通过 CaptureService 的专用可恢复方法写入合成 Raw 并生成 Review，不走 Promote。项目关联显示 NOT IMPLEMENTED 且无执行入口。前端审批后另行展示目标预览与明确确认/重试，不因审批点击而调用目标 API。
- Core Inbox Proposal/Capture 定向合成测试 **37 项通过**；统一 Inbox 前端定向测试 **7 项通过**；前端 typecheck、build 通过，build 有大型 CanvasEditor chunk 提示；`git diff --check` 通过。代码已 Commit/Push 并建立 Draft PR #63；后续仅提交本次交付状态文档。本记录只证明本地合成开发验证；PR 尚未合并、未部署、未做用户验收；未触碰真实 Vault、付费模型或 NAS。

## 2026-10-18 — D084 PR #61 App-only 受控部署与浏览器验收阻断

- 依据既有用户授权部署指定候选 `secondbrain-app:d084-pr61-4a58393-full`，Image ID `sha256:e63ab1611b2a30ffd9dd2a9cb901066fa6b2da2e7e85c9c1c9d72dbabac0e4ab`；未重建。候选基于 `4a58393`，执行时 GitHub main 已推进到 `3080506b053d3876d292d9199049fd12e3247b88`（其后的 PR #59 D085-C2b 变更不在候选内）。
- 切换前 App PR #49 镜像 `sha256:1c7ed4cb…11dd6ca` healthy；Hermes Guard 镜像 `sha256:b99b1762…5357e9a` running。Compose 原 SHA-256 `28636dec…1d6e06`；只替换 App image 引用，更新后 SHA-256 `9c0932c04d6984cd2e491738d51eb6235d7182ccfca8146678fc18cdabe6097d`，权限仍 `1026:100 / 0640`，Compose config 校验通过。执行 `up -d --no-deps --no-build --force-recreate --wait --wait-timeout 120 secondbrain-app`；候选容器在约 30 秒内 healthy，容器 ID `665bb381…c1bc2710`，RestartCount 0。
- 只读 HTTP smoke：在 App 容器内使用现有 Host allowlist（不输出 Host 值）验证 `/health`、`/chat` 为 200，两个 JS 和一个 CSS 资源为 200，匿名 `/api/chat/sessions` 为 401 JSON。Hermes 容器 ID、镜像 ID、StartedAt 与 RestartCount 未变。已核验 PR #49 镜像、旧 D084 App 镜像、现有回滚目录 checksum，并保存切换前 Compose 精确副本；无需回滚。
- 浏览器验收使用新建 IAB 标签，但登录后页面自动恢复既有 Session，未满足空白合成 Session 条件。自动化可访问性快照意外包含会话列表标签与选中会话的操作卡摘要；未打开其他会话或展开消息正文，未保存这些文本或 Session ID，立即停止并关闭标签页。未创建 Session、写 Journal/Task、重试或调用模型。Journal/Task 操作卡、刷新恢复、会话隔离、幂等均 BLOCKED；历史生产根因 UNKNOWN。没有 App 健康/路由异常，不触发自动回滚。
- 复用 PR #49 与 PR #61 已通过的测试/构建审查证据；本次不重复完整测试。生产部署与运行 smoke 通过，业务用户验收未完成。Issue #44 评论未提交（此前审批限制保持），状态更新仅进入治理文档待审 PR。

## 2026-10-18 — D084 PR #61 合并后生产元数据只读核验

- 按最新 main `d33fe062e9065d3b7047e386f491ff8b55592908` 的 `AGENTS.md`、`00-CURRENT.md`、`Agent-Rules.md` 与 PR #61 复审结论执行一次限定只读核验。PR #61 已合入 main（merge `b3c8fe08ea04e1f20ccadcf70e393bf80a30672c`），复审确认 stale localStorage ID 回退和创建/分叉选择意图保护的本地修复 PASS、生产根因 UNKNOWN；另提醒 activeRun 恢复可能按 sessionStorage 的 activeSession 重新选择，此路径未在 PR #61 验证。
- 2026-10-18T01:50:41Z 通过现有 SSH 与 `sudo -n` 只读 Docker 查询确认：App 容器 `272b9fee7e62cf4b6b9c39f82d8c1e2eeceffaee82215a9cf34dc35098570601`，镜像 `secondbrain-app:pr49-fa2ad412-full` / `sha256:1c7ed4cb…11dd6ca`，healthy、RestartCount 0、UID/GID 1026:100；Hermes 容器 `057324a9e438969320e84d7c3cbad58e3f010637d7dd00d5967123b034eada79`，镜像 `secondbrain-hermes:v0.22.2-failclosed-84d1cbaf` / `sha256:b99b1762…5357e9a`，running、RestartCount 0、身份 root。本次只核验容器元数据，未检查或修改 Compose、挂载、配置、权限、容器日志，也未重启/部署；Environment-Baseline 保存完整镜像 ID、启动时间和状态。
- Edge 标签清单没有 SecondBrain App 页面。为避免 `/chat` 自动恢复已有私人会话，本次未导航 App、未读取会话正文；也因缺少目标 opaque ID，未查询全量 Hermes Session 列表或宽泛日志。浏览器 selected/localStorage ID、相关 activities 请求/响应 ID、状态与时间均 UNKNOWN。PR #61 的两个旧版 UI 边界在当前 PR #49 生产镜像中仍可能存在，但没有 ID/时序证据将其与既有 FAIL 关联；生产根因保持 UNKNOWN。历史验收仍为首卡/首次刷新 PASS、会话切换恢复 FAIL/INCONSISTENT、幂等与审计 BLOCKED。
- 未创建/修改/删除 Session、Journal、Task；未调用模型；无 NAS 文件/config/权限更改或资产清理。Issue #44 评论未写入；此前 Issue 写入被审批拒绝，本轮未尝试从其他渠道绕写。诊断状态与最新有限运行证据同步到 CURRENT、Environment-Baseline；后续如需定向关联，只使用精确的既有合成 Session ID 或不打开私人会话的 metadata-only 读取方式，等待 ChatGPT 独立复审。

## 2026-10-18 — D085-C2b PR #59 同步最新主线

- 按 PR #59 Review #5561020708 在原分支同步 main `4a5839346b938ef28f852fe249058c84eddb31cd`。仅 `Progress-Log.md` 有内容冲突；保留本分支 C2b 历史和 main 的 D084 生产元数据核验记录。CURRENT 与 Environment-Baseline 自动合并，无其他冲突。
- 确认 CURRENT 采用 main 最新 D084 唯一 NEXT，D084 生产根因仍 UNKNOWN；Environment-Baseline 保留 2026-10-18 限定只读容器元数据证据。D086 词库与 C2b 状态均保留。
- PR #59 相关 Core/前端定向测试、typecheck/build 已在前一次 main 同步后通过；本次只改文档冲突，不重跑无关测试。待完成本次 `git diff --check`、推送并核验 PR 状态。

## 2026-10-17 — D086 PR #58 同步最新 main 与合并门禁核验

- 按 Issue #55 评论 #6234901749 在原隔离分支核对并获取最新 `origin/main` `1c73b0f3449725815443c22ba503104df0cb8eff`。合并预检发现唯一真实文本冲突为 `docs/baseline/Progress-Log.md`；采用双侧保留，保留 main 的 D085-C2a 最新记录和 D086 复审/实施记录。代码文件无冲突。CURRENT 自动合并保留 main 的 D084 唯一 NEXT，确认未改写。
- 合并提交 `3823af2d4be9973ee14dfdfa24e8d08c1e78ebf5` 已 Push 至原分支 `codex/d086-vocabulary-center-20261017`。同步后 Core `tests/test_vocabulary.py` **11 passed**，`git diff --check` 通过。未运行与冲突无关的前端测试。
- Push 后 GitHub PR #58 实时状态：OPEN、head `3823af2d4be9973ee14dfdfa24e8d08c1e78ebf5`、base main `1c73b0f3449725815443c22ba503104df0cb8eff`、`mergeable=true`；未合并、未部署，等待审阅/用户后续决定。未访问真实 Vault、NAS、Secret 或模型。

## 2026-10-17 — D085-C2a PR #54 首轮审查修复与 main 同步

- 读取 PR Review #5557918034、Issue #46 最新评论 #6234341190，并复核最新 main `docs/baseline/业务规范.md`：类型库最多 10 个；既有类型可自动选择、用户手动修正后不得自动覆盖；有效标签可自动应用，手动移除后不得自动加回；新类型/标签词汇须单独审批。词库功能仍归 Issue #55，本 PR 使用明确标记的合成示例词汇，不读取真实词库。`待整理`为状态，不是标签。D086 对话收录只是获批产品方向，未由此启动对话入口实现。
- 在原 PR 分支将 main `684bb45dbcc58ce7877d9ba3f55643fb80c17a38` 合并进来。并入的 CURRENT/Progress、架构、治理、环境和业务规范改动均保留；D084 当前运行证据及新的唯一 NEXT 原样采用 main 版本；D086 与词库边界亦保留。随后检测到 PR 远端分支新增 main 同步及审查修复提交（`b2000c4`、`75e8cdf`），本地先前推送被安全拒绝；未强推。将远端分支合入时，`App.tsx`、Inbox 页面与测试有冲突，采用远端完整 Capture 主页面嵌入 Notes Drafts 的版本，再叠加本轮最小词表/模拟审批修正；CURRENT 中 D084 唯一 NEXT 未改写。
- 统一 Inbox 恢复旧 Capture 预览（文本/PDF/图像/音频）、原始来源详情、状态/错误说明、部分成功重试和 Organizer 状态/显式触发；补相应合成回归。分类使用固定合成演示词表（不是 Issue #55 真实/持久词库），将已有类型/标签与新词候选分开，移除的标签/手动更正的类型在重新生成 Mock 建议时受保护；类型和已有标签不显示逐条审批按钮。日记/Review/项目建议的“本页模拟同意”明确未提交、未持久化、未排队/执行，刷新后消失；不写目标系统或更改源文件。
- 定向前端 3 个文件 **54 passed**；`npm run typecheck`、`npm run build` 通过，`git diff --check` 待最终提交前复核。Build 有大型 CanvasEditor chunk 警告。未读取真实 Vault/笔记、真实标签库，未调用真实模型、未部署 NAS/生产配置，未合并 PR。提交与 Push 待最终 diff 审查。

## 2026-10-17 — D086 PR #58 首轮复审窄修

- 按 PR Review #5558136143 / Issue #55 评论 #6234861916 在原分支 `codex/d086-vocabulary-center-20261017` 修复词汇唯一性与锁文件校验顺序。标签创建现在同时检查所有现存 canonical tags 和 synonyms；同义词创建同时检查所有 canonical tags 和 aliases，均按 NFC + casefold 比较。停用历史项继续占名；新增双方向 409 回归覆盖大小写/Unicode 等价输入及停用记录。
- `.lock` 现在由 `os.open(..., O_CREAT|O_NOFOLLOW, 0600)` 安全尝试打开后先 `fstat` 验证属主、普通文件类型和严格权限，再 flock；不再对现存对象调用 `fchmod`。预置 0640 锁文件测试证明请求 fail-closed，锁权限和原 catalog/audit 字节不变。
- 明确容量策略：2,000,000-byte 上限同时覆盖 catalog 与内嵌审计。序列化后的下一状态超限时在创建临时文件前返回 HTTP 507；不会替换旧文件、丢弃审计或部分提交。满载后写入会停止，既有数据仍可读取。长期扩展前需另行设计可导出/校验的 append-only 审计分区/归档及快照恢复，再迁移旧嵌入审计；本切片不截断、不自动归档或放宽上限。
- 仅运行 Core `tests/test_vocabulary.py`：**11 passed**；未改前端，故未重复 frontend typecheck/build。`git diff --check` 通过。未访问真实 Vault、NAS、秘密或模型；未合并。

## 2026-10-17 — D086 标签与类型中心（本地合成切片）

- 按 Issue #55 评论 #6234480613 从 GitHub 最新 main `e332172dc812ed46dd54685e2d0aa53fe52dd534` 建立独立分支 `codex/d086-vocabulary-center-20261017`。Core 私有状态目录下新增版本化词库与同文件审计；以跨进程锁、临时文件原子替换和 `If-Match` revision 防止并发覆盖。管理 API 分离 `vocabulary.read` / `vocabulary.write` 动作并复用 owner session 鉴权。创建类型/标签/永久同义词均要求显式确认；类型最多 10 种，标签禁用保留记录与引用。
- 管理 UI 新增独立 `/vocabulary` 页面，不编辑笔记 Markdown。只初始化业务规范中的五种类型，标签库为空；系统字段不进入词库。新增纯函数契约测试：手动锁定类型不被自动覆盖、手动移除标签不被自动补回；未来 Vault 候选预览只接收调用者提供候选，不扫描路径、不持久化、不构成盘点授权。
- 定向验证：Core `tests/test_vocabulary.py` **7 passed**；前端 `src/VocabularyPage.test.tsx` **3 passed**；`npm run typecheck`、`npm run build`、`git diff --check` 通过。Python 测试运行于 `/private/tmp` 独立 venv；前端依赖安装于隔离 clone，npm 显示锁文件中既有 4 项审计告警（2 low、2 moderate），未执行修复或更改 lockfile。构建保留既有大 chunk 警告。
- Commit `c739619a6fbaf39ec81251ca217e2d982ae87a77` 已 Push；PR #58 指向 `main`，OPEN、未合并。未访问真实 Vault/私人笔记、NAS 或 Secret，未调用模型、未改写历史 frontmatter、未部署。CURRENT 的 D084 唯一 NEXT 原文保持不变，仅增加并行开发状态。

## 2026-10-17 — D085-C2a 统一 Inbox 与人工逐项审批（待审 PR）

- 按 Issue #46 最新要求，从 GitHub 最新 main `ed6dc7fd14cc3c0860ddc5609f67cd02098452e9` 创建独立 Worktree/分支 `codex/d085-c2a-unified-inbox-20261017`。新增统一 Inbox 页面，读取现有 Core Capture Inbox 与 Notes `drafts` 集合，提供经 Core 既有权限门禁的新 Drafts 笔记入口；不扫描 authorized/Knowledge/Review/Private 集合。新建合成 Capture 示例仅存在页面内存。
- 本地确定性 Mock 按正文提出类型/标签、日记摘录、Knowledge Review 草案和项目关联；所有建议逐条可编辑、批准待执行或拒绝。批准不执行写入，原始来源保持不变；该限制来自现有 Journal/Review/Knowledge API 缺少可验证的来源绑定能力。决策暂存页面内存，不承诺跨 Session 持久化。未调用真实/付费模型。
- 定向前端回归 5 文件 **63 passed**（统一 Inbox、导航、Notes、Capture、Chat 活动）；`npm run typecheck` 通过；`npm run build` 通过，仍有大型 CanvasEditor chunk 警告；`git diff --check` 通过。
- 未访问真实笔记、NAS、生产配置或生产数据；未部署、未合并 main、未用户验收。D084 的 `/chat Not Found` 离线根因分析仍为 CURRENT 唯一 NEXT，未覆盖。

## 2026-10-17 — D085-C1 PR #50 同步最新 main 与导航回归

- 按 Review #5557295754，在原分支 `codex/d085-c1-notes-navigation-20261017` 合并 GitHub 最新 main `468971b49b1bf63b98930ee0b875c133a314b429`。合并保留 main 的 D084 PR #49 合并状态、唯一 NEXT（仅生产部署预检待单独授权）及 D084 Chat Journal/Task 最新证据；同时保留本 PR Notes 路由、功能开关、Core `notes.read` 门禁和未保存离开保护。`App.tsx` 手动合并 Journal「日记」命名、D084 Chat 活动导航回调与 D085 Review/Inbox 历史路由管理；CURRENT 和 Progress-Log 以 main 为底稿，补记 D085-C1 并行状态及此同步证据。
- main 同步新增 Core Chat Journal/Task 活动持久化代码、前端 Chat 时间线与相关测试；前端 `App.navigation.test.tsx`、`NotesPage.test.tsx`、`MindMapEditor.test.tsx`、`capture-flow.test.tsx`、`chat-activity.test.ts` **63 passed**。`npm run typecheck` 与 `npm run build` 通过；NotesPage 仍为独立异步 chunk（531.15 kB），CanvasEditor 为 2,325.54 kB 并保留 Vite 大 chunk 提示。`git diff --check` 通过。此次未运行未受影响的 Core 回归。
- 未访问 NAS、真实笔记、生产配置或 C2；未合并 main、部署或操作真实业务数据。PR #50 仍待复审及 GitHub 可合并状态确认。

## 2026-10-17 — PR #49 新版 App 受控生产部署失败并回滚

- 按 Issue #44 授权评论 #6232479408，以 PR #49 merge `fa2ad4126b5e9acb6983fdae8445a4fb0ebdda79` 构建候选 App：tag `secondbrain-app:d084-pr49-fa2ad412`，Image ID `sha256:9858d618ab6a7a99dfe2c6cf38fa4989351c32c4405fc64b0959f73bf07d6f45`。构建归档 SHA-256 `617a2569e5db3d700072a68789dd2279bd0ee925e367497eb77f744872172047`。不重跑既有完整测试。
- 预检确认 Compose SHA `33f45f5cdca72cea05ddd21a265d129bc770684dfb6b1b9d3790cb12725fa0b9`、属主/模式 `1026:100 / 0640`；Core state、Journal、Task 根为 `1026:100 / 0700`。部署前在 `/volume1/docker/secondbrain/rollback/d084-pr49-app-20261017T100900Z/` 建立 App/Compose 快照，目录 `0700`，SHA256SUMS 校验通过。Compose 只更改 App image tag，并用 `--no-deps` 单独重建 App。新镜像 30 秒内 running/healthy，RestartCount 0。
- 浏览器从导航打开“对话”后 `/chat` 显示 `Not Found`。按异常停止规则立即使用快照恢复 Compose 并只重建 App；旧 tag `secondbrain-app:d084-c8a2b348` / Image ID `sha256:ef60d7de4ff3f3b3edc49cb0d565c45df3b996fe7014fc49ff3446ead7592feb` 在 15 秒内恢复 running/healthy，RestartCount 0，loopback health HTTP 200；Compose 哈希恢复为部署前值。
- Hermes 容器/image ID、启动时间与 RestartCount 0 均未改变；本次没有对 Hermes/Guard 写入或重建。没有创建 Journal/Task 合成条目、调用模型、改动真实数据、扩大权限或触及其他服务。App 初始化创建的空 `core-state/chat-activity` 目录（`1026:100 / 0700`）及回滚快照均保留，不清理。
- **结果：PR #49 已合并；候选生产部署已回滚；生产合成验收未完成，未用户验收。** 失败及直接证据报告于 Issue #44 comment #6232678940。此次单次部署授权用完；下一步先离线定位 `/chat` Not Found 的最小根因并提出有证据的修复，之后再请求新受控重试授权。

## 2026-10-17 — D084 PR #49 跨日 Journal 幂等与 Hermes 时间排序窄修

- 按 PR #49 ChatGPT Review #5557199112，在原分支修复跨 Asia/Shanghai 日期零点的响应丢失重试：Core 使用 Journal 根目录私有全局锁串行化写入，并在权威日期 JSONL 中查找 operation ID；同键同内容返回原日期/记录，同键内容或 Session 冲突仍拒绝。没有引入旁路索引或历史数据迁移。
- 新增 Journal Store 跨日并发唯一性回归及 BFF 跨零点响应丢失/重试回归；验证单条业务记录、同一操作活动恢复及原始 Journal 日期保留。Hermes API 原样传递上游 timestamp；前端现在保留字符串/数字，并将 ISO、Unix 秒、毫秒统一为时间线排序值。
- 追加兼容 Review #6232338966：旧 Journal JSONL 缺少 `date` 时，重复响应/活动投影仅在内存中以所属文件名 `YYYY-MM-DD` 补日期；定向回归证明原文件字节不变，且不会在重试日期新增记录。Core `tests/test_journal.py tests/test_tasks.py tests/test_web_app_bff.py` **35 passed**；前端 `src/capture-flow.test.tsx src/chat-activity.test.ts` **42 passed**（本次未改前端，复用前次通过证据）；`npm run typecheck`、`npm run build`、`git diff --check` 通过。Core 有 1 条既有 Starlette/httpx TestClient 弃用警告。隔离测试工具生成的 `web-app/secondbrain-core/uv.lock` 保留并排除于提交。
- 更新 CURRENT 与本日志。代码保留在 PR #49 原分支，等待 ChatGPT 对指定 Review 的复审；**DEV-TESTED / PR OPEN / NOT MERGED / NOT DEPLOYED / NOT USER ACCEPTED**。未访问 NAS/生产数据/Secret，未运行模型或清理历史资产。

## 2026-10-17 — D084 Chat Journal / Task 会话活动留痕修复（开发验证）

- 按 Issue #44 评论 #6231983901，从最新 main `76872e55ce6d966628723ce4336e121b946dd768` 建立独立分支 `codex/session-bound-journal-task-activity-20261017`。Core 在 Journal/Task 的既有幂等业务记录中原子保存 session_id 与 operation_id；活动列表通过 App 鉴权及 Hermes Session 存在性检查，从权威业务记录重建成功活动，并在私有 Core state 中持久记录失败活动。旧记录无 session_id 时不迁移；Hermes 历史与 Run/SSE 未改写。
- Chat 先用正常 API 确保 Session，再提交显式 Journal/Task 原文与操作键；将 Core 活动和 Hermes 消息按记录时间合并呈现，并在切换 Session 时隔离异步响应。sessionStorage 仅保存未确认操作的重试上下文，Core/业务记录仍是持久权威来源。操作卡呈现「系统操作」、结果、原文、日记日期/待办当前状态及导航；左侧「日志」改为「日记」。Fork 不复制来源活动；已删除/不存在 Session 的活动读请求返回 404。
- 定向合成验证：Core `tests/test_journal.py tests/test_tasks.py tests/test_web_app_bff.py` **31 passed**，覆盖未登录、Session 存在性/隔离、幂等与跨 Session 冲突、投影写入失败后重启 Core 从 Journal 记录恢复、Task 状态更新投影、fork/delete 隔离和验证失败不显示成功。前端 `src/capture-flow.test.tsx src/chat-activity.test.ts` **41 passed**，包括 Journal/Task 操作、业务落盘后响应丢失的同键恢复、跨刷新恢复、Session 切换隔离、时间线排序，以及现有 Chat/SSE/Capture/审批交互；中间一次全组重跑有 1 项 Review 滚动测试间歇失败，单测及最终完整重跑均通过。Chat/Task/跨 Session/timeline 定向用例 **8 passed**。`npm run typecheck`、`npm run build`、`git diff --check` 通过。Core 有 1 条既有 Starlette/httpx TestClient 弃用警告。
- Commit `8d4e56e6fad25f9ff8bae5dd9fc2e4bcfb71fcfe` 已 Push 至独立分支；PR #49 已创建并指向 `main`，当前 OPEN、未合并。**状态：DEV-TESTED / NOT MERGED / NOT DEPLOYED / NOT USER ACCEPTED。** 未访问 NAS、未修改生产数据或配置、未调用模型；未写入或清理 Hermes Session/消息，也未改变 D082 记忆 SoT。后续 PR 复审后再由用户验收修复版浏览器行为。

## 2026-10-17 — D084 Journal / Task / Memory / 文件审批统一集成（本地验证）

- 实时核对 GitHub `main` 为 `a8019ab1bc453c3c42e6ecf82ccfacdd97bde583`、并行分支为 `e5f5c72b72511e14a4a1ee403b31cafbdd50fa69`、PR #37 head 为 `e5332f6fa175d0742cacbaec2fbab40ded4781a4`。在独立 clone 创建 `codex/d084-unified-integration-20261017`；合入并行分支 3 个 Journal/Task 切片提交，保留 main 侧 6 个独有提交及 D082 `personal_learning.py` 修复。处理唯一 `00-CURRENT.md` 冲突时保留 main 文本并在本轮校准；PR #37 的两个已审提交按提交粒度移植，避免把其旧分支中对 Journal/Task 的删除带入。`App.tsx` 导入冲突已合并为 Journal/Task 页面与统一 Run 审批卡契约。
- 统一本地合成验证：Core `tests/test_personal_memory.py tests/test_personal_learning.py tests/test_journal.py tests/test_tasks.py tests/test_run_approvals.py tests/test_capture.py tests/test_web_app_bff.py` **80 passed**；Hermes Guard `tests/test_plugin.py` **22 passed**；前端 Journal/Task/审批/Capture 相关测试 **46 passed**，`npm run typecheck`、`npm run build` 通过。Core 使用隔离 Python 3.12 环境；前端依赖在临时 clone 安装，无 package lock。Starlette/httpx `TestClient` 弃用警告 1 条。`git diff --check` 通过。
- 环境说明：初次使用系统 Python 3.9.6 收集测试失败，因现有源码的 `str | None` 注解无法由 Python 3.9 评估；未改业务源码，改用本机 Python 3.12 重跑并通过。
- 未访问 NAS/生产配置、Secret、真实个人数据；未启动 Hermes、未调用真实或付费模型、未创建/修改生产 Session/Memory/Atlas 资产。未合并 main、未部署、未进行浏览器用户验收。提交 `a766c5b409b1042dc1a8bac8b808a8fc82eef19f` 并 Push；PR #45 已创建，指向 `main`，创建时 head 即该 SHA。PR 未合并。当前状态为本地 DEV-TESTED，等待集成 PR 独立审查。

## 2026-10-17 — D084 集成前文档统一与多功能验收计划（仅文档）

- 从 GitHub 最新 main `628bec895e8d95646b5cc583e8ffea8f7e877e10` 创建独立文档分支。只读核对 `dev/parallel-v1-next-20261017` HEAD `e5f5c72b72511e14a4a1ee403b31cafbdd50fa69`；main 独有 1 个提交，开发分支独有 3 个提交。PR #31/#34/#36 已合入该开发分支，未合入 main；PR #37 HEAD `e5332f6fa175d0742cacbaec2fbab40ded4781a4` 仍 OPEN、未合并、未部署。
- 更新 CURRENT 的分层状态表和唯一 NEXT，区分代码审查、开发分支合并、本地测试、生产部署、真实模型与浏览器验收。main 独有 D082 `personal_learning` 修复作为未来集成必须保留的基线。
- Architecture 补记 Journal/Task 专用 Core 根与接口/权限、Chat 显式意图分流及 PR #37 Run 级文件审批提案状态；Agent-Rules 增补并行切片合并、集中集成回归和真实运行前重新授权规则。新增 `D084-Integration-and-Validation-Plan.md`，列出顺序、冲突文件、既有测试目标、统一合成矩阵、生产权限门槛和已知风险。
- 未改 `Environment-Baseline.md` 的快照时间或内容：本轮没有 NAS 新运行证据。未改业务代码，未合并功能 PR，未访问 NAS、Secret、生产数据或模型。
- 定向检查：5 个更新文档的本地 Markdown 链接与代码围栏核对通过，`git diff --check` 通过；确认 Environment 快照未改、CURRENT 中无旧 main SHA/历史 NEXT 文案。未运行业务代码测试。
- 文档 PR 和逐文件差异见 Issue #38。

## 2026-10-17 — D082 普通 Chat 文件变更单次审批（开发中，未部署）

- Issue #30 最新审核指出真实 Run 在普通对话中执行了文件写入。基于 Hermes v0.22.2 上游固定源码 `d923a5eb487a17c0a68801bba9ef0f56c81040a8`，核对 `pre_tool_call` 提供 session/turn/tool-call/API request 标识；API Server 的每个 `/v1/runs` 将原生 approval session key 绑定到该 Run ID，并通过 Run SSE/API 等待审批。
- Guard 将 `write_file` 与单目标 replace `patch` 的每次执行都送入 Hermes 原生审批；目标路径先 canonicalize（包含符号链接解析），同一参数映射用于审批摘要与实际分发；敏感 Hermes 状态、凭据与 Skills 仍硬拒绝，含嵌入多文件目标的 V4A patch 保持拒绝。Core 审批桥校验事件 Run ID、用户/Session 所属、完整参数摘要、有效期及单次消费；前端审批卡显示并默认展开写入参数。现有 Capture API 与 D077 JSONL 不变。
- 针对性验证：Guard `test_plugin.py` **18 passed**；Core Run Approval、BFF 和 Capture **42 passed**；前端审批解析 **5 passed**，`npm run typecheck` 通过。Core 使用现有隔离 Python 3.12 环境，前端依赖仅安装在本次临时 Clone；无 Hermes/NAS 启动、无模型请求。
- **状态：独立 PR 开发中，未部署。** 未触碰 NAS/生产配置、Session/Memory、Atlas 合成文件或原正式工作区未跟踪项；Terminal 仍关闭。开发与本地测试不代表生产权限验证或真实用户验收。

## 2026-10-17 — D082 修复跨会话个人记忆召回（进行中）

- Issue #28 的两次真实 GLM-4.5-Air Run 中，首轮合成偏好学习创建 1 条 active 记忆；第二个 Session 的相关问题未召回，触发 `learning-loop-test` Skill 与失败的 `search_files`，按止损规则未重试。原始执行与费用边界见 Issue #28 评论 #6227702593。
- 只读核对该合成 Memory ID 后确认正文为“先给简短结论”，学习器在中文逗号处截断，并丢失“写技术说明时”语境；该文本与“帮我整理这次测试的说明”没有词元重叠，Core `instructions_for` 因而不注入记忆。
- Hermes v0.22.2 官方 API Server 文档确认 `/v1/runs` 支持可选 `instructions`；Core BFF 调用 HermesAPI 原样转发。主因位于 Core 偏好提取，不是已证实的 Hermes instructions 契约问题。
- D082 指定分支增加情境偏好完整提取与跨 Session BFF 注入/无关主题过滤回归。Core `test_personal_learning.py` 17 项通过；本地 Python 3.9 环境因 Pydantic 无法解析现有 `str | None` 注解未能收集测试，改用隔离 Python 3.12 环境完成验证。
- 代码与文档仍在未合并 PR 分支，未部署、未运行真实模型复验、未修改 NAS/生产 Memory；后续真实复验需要另行授权。


## 2026-10-17 — D083 Issue #35 Task 持久待办最小闭环（开发分支）

- 从最新 `dev/parallel-v1-next-20261017` `74a18ff9e6b787329582cfcaa340dba965537ef8` 创建独立 `codex/d083-task-chat` 工作分支。新增 Core `/api/tasks`：只有在显式 `SB_TASK_ROOT` 指向既存 Core-owned `0700` 专用目录时启用；单 JSON 文件在跨线程锁内原子更新，创建具备持久幂等键，修改使用 `expected_updated_at` 防陈旧覆盖，并记录状态/字段变更历史。支持按状态、截止日期筛选；不提供删除。
- Chat Composer 仅对 `添加待办：xxx` / `建个待办：xxx` 的句首显式命令直达 Task API，不创建 Hermes Session/Run；显式 `截止：YYYY-MM-DD` 后缀按 ISO 日期提供截止日。成功提示 Today 入口，失败保留原命令并复用同命令重试键。普通对话和 D082 Journal 路径保持各自原路。现有 Today 导航打开持久 Task 列表，支持标题/ISO 截止日修改、完成和恢复。未实现提醒投递及自然语言修改目标猜测。
- 定向合成验证：Core `tests/test_tasks.py tests/test_web_app_bff.py` **23 passed**（鉴权、未配置 503、存储重载、20 路并发无丢失、幂等冲突、日期/状态查询、乐观冲突、完成/恢复、历史、symlink 拒绝；1 条既有 Starlette/httpx 弃用警告）。前端 Chat + TaskPage **40 passed**；`npm run typecheck`、`npm run build` 和 `git diff --check` 通过。
- 无 NAS/生产访问或变更、真实 Task/Journal 数据、Secret 或模型调用；未检查生产 Task 配置，因此其状态 UNKNOWN。Issue #28 测试未触及。开发分支未部署；真实浏览器验收待完成；提醒通知 NOT IMPLEMENTED。

## 2026-10-17 — D082 Issue #33 Chat 显式 Journal 记录（开发分支）

- 从 `dev/parallel-v1-next-20261017` 最新已合并基线 `75c83bbcd3ff05b188fabc8f03bdc4eacea2833c` 创建独立工作分支。Chat 输入仅在开头显式出现 `记一下`、`记下来`、`写日记`、`记录一下` 时调用 Journal API；传入完整输入原文，普通消息继续走原 Hermes Run 路径，不创建额外 Chat Session。成功反馈日期和原文保留状态；失败保留输入并在同内容重试时复用 Idempotency-Key。
- Core 在 Journal 未配置时认证后返回明确 503，不创建数据根；按日追加返回日期。同一幂等键同内容安全回放、不同内容返回 409。未改 Hermes Session/Run/SSE 实现，未触及 Task/Memory/Promote/Terminal/Scheduler。
- 针对性合成验证：前端 Chat 交互 **36 passed**，覆盖显式成功不触发 Run、普通消息仍走 Hermes、失败输入保留且复用幂等键、未启用明确拒绝；`npm run typecheck` 与 `npm run build` 通过。Core `tests/test_journal.py tests/test_web_app_bff.py` **20 passed**（含幂等键冲突和未配置 503）；出现 1 条 Starlette/httpx `TestClient` 弃用提示。`git diff --check` 通过；未执行真实模型测试。
- 无 NAS/生产访问或变更、生产 Journal 数据、Issue #28 测试状态/数据、真实模型或秘密访问。当前代码仅为开发分支，不部署；Chat 浏览器用户验收仍待完成。

## 2026-10-17 — D081 Issue #29 Journal explicit-intent slice (local only)

- Started from `dev/parallel-v1-next-20261017` at `d7a48fe3e1f70a40a8b94d4e1e2dacb1d052abaa`, in a separate clone. Added an optional `SB_JOURNAL_ROOT` Core module/router; it mounts only an existing Core-owned `0700` directory. The dedicated API uses the authenticated App owner session, accepts only explicit `记一下` / `记下来` / `写日记` / `记录一下` prefixes, stores the complete original phrase/text with Asia/Shanghai timestamp and source, and appends to a date-scoped JSONL file. `flock`, `O_APPEND`, `O_NOFOLLOW`, private file modes, persistent hashed idempotency keys and partial-write truncation guard append integrity. There is no update/delete route.
- Added a small `/journal` App page to browse a date and explicitly append a natural-language phrase. Ordinary Chat does not call this API; no Hermes Session/Run/SSE code changed. The page/API are a local Journal entrance, **not** an automatic chat intent integration. Chat integration remains a follow-up design to avoid the parallel Issue #28 hot path.
- Synthetic verification: Core `tests/test_journal.py` + `tests/test_web_app_bff.py` **18 passed** (explicit vs ordinary phrase, missing session, original text exactness, append/read, duplicate replay, 24 concurrent appends, invalid dates/path, symlink refusal, and no Review/Knowledge/Hermes side effects). Frontend Journal test **1 passed**; `npm run typecheck` and `npm run build` passed. One existing Starlette/httpx deprecation warning appeared.
- No NAS/production access, mount/ACL/Compose/container changes, real Journal/private data, model calls, Session/Run changes, Promote/Terminal/Scheduler enablement, or production deployment occurred. Production still has no Journal mount. Future deployment requires separately authorized Core-only RW access to the dedicated `/volume1/SecBR/SecondBrain/50-Journal` directory mounted as `/data/SecondBrain/50-Journal` (owned by Core UID and mode `0700`); do not mount the SecondBrain root RW.
- **State:** DEV-TESTED / NOT DEPLOYED / user browser acceptance pending. PR targets `dev/parallel-v1-next-20261017`; this implementation does not complete Task/Reminder or natural-language invocation from the Chat composer.

## 2026-10-17 — D080 恢复开发与浏览器验收准备

- Issue #25 授权 A 阶段：读取项目规则、D079 最终验收及 PR #24；确认 PR #19/#21/#22/#24 均已合并，当前 main 为 `4afe7ecad7584828c3d3ac6be896b97386c11b02`。原正式 Clone 落后且包含未跟踪 `typescript`，因此在独立临时 Clone 完成文档工作，未改动正式工作区。
- 将 `00-CURRENT.md` 中过时的“DEVELOPMENT PAUSED”现行状态改为 D080 恢复开发；记录 PR #24 本地 FakeHermes 集成覆盖和边界，列出最短合成浏览器验收步骤，并明确生产 Run/模型/预算仍需单独授权。
- PR #24 本地测试已提供零外发认证→Session→Run/SSE→学习→跨 Session 召回证据；纠错/过滤/失败停止由既有定向测试覆盖。本轮未重复 44/15 测试，也未修改生产代码。
- 未做 NAS 写入、生产 Session/Run、模型调用、Secret/真实数据访问或清理。真实 Hermes 自然学习与浏览器效果仍未验证；下一阶段计划不超过 5 次 Run，但这不是供应商账单硬封顶；实际 provider/model/费率未核实，费用上限仍为 UNKNOWN。

## 2026-10-17 — 阶段暂停与文档收口决议（历史状态，已被后续恢复指令取代）

- 当时用户明确要求暂停开发并集中更新基线；该历史指令已被 2026-10-17 后续明确恢复开发的用户指令取代，不再作为当前禁令。本条其余内容仍是该日期的历史事实。
- PR #18 已合并，固定 Hermes fail-closed overlay 已部署；PR #19 提供最新运行证据、构建配方及只读资产审计，待合并；本次文档 PR 堆叠在 PR #19 上。两份待合并 PR 的内容不能提前描述为 main 已更新。
- 恢复顺序：文档合并 → 只读状态核验 → 获准的无敏感合成浏览器 Chat/Session/Run/SSE 和记忆纠错验收 → 单独确认模型、费用和真实数据范围后有限真实体验 → 再排剩余 V1 MUST / Companion 项；Terminal 继续关闭。细项以 `00-CURRENT.md` 为唯一当前 NEXT。
- NAS 历史资产清理只是只读审计：11 份构建源、10 份 Compose 历史快照、18 份回滚资料合计约 4.97 GiB；10 份未引用旧构建源约 56.4 MiB，三个 D077 大归档约 4.91 GiB 未证明重复；目前**不授权删除**。


> 2026-10-17 D078 Stage 1 仍是最新生产部署；本文件顶部较新的源码补丁记录不代表生产变更。每条记录只描述当时状态。

## 2026-10-17 — D078 fail-closed Hermes 镜像升级与运行核验

- PR #18 按授权 squash 合并至 main，merge commit `84d1cbaf7daebb188fc93c369fba4a59b80895e5`。基于固定 Hermes v0.22.2 上游源码 `d923a5eb487a17c0a68801bba9ef0f56c81040a8`、已审核补丁 SHA-256 `b53818487205733039378a8e3c7218cc298eca1c39e1a34dec997dd306f855b0` 和官方 amd64 digest `sha256:a11574b7fe8e1631d7d88d556677dac693bc058abf558cdeb899155688c1bf05`，以一文件 overlay 构建 NAS 镜像 `secondbrain-hermes:v0.22.2-failclosed-84d1cbaf`，Image ID `sha256:b99b1762631846d5ed3f8648ccc2c7ef2625b004234bbf276add2f8855357e9a`。镜像构建在缓存官方镜像上完成，Docker build 使用 network none、linux/amd64、2 GiB、CPU 核 0-1；未拉取其他依赖。
- 部署前回滚快照 `/volume1/docker/secondbrain/rollback/d078-hermes-hook-failclosed-20261016T173140Z/` 保留 Compose、旧 manifest 与恢复元数据；官方旧镜像保留 rollback tag。Compose 新 SHA-256 `6d7b1be1abb4479b93e5cebc473e2f20ba6bddb6bd62ea5019322ef260908818`，只替换 Hermes 镜像引用；只重建 Hermes，无 App/Core/其他 NAS 服务重启。旧 Compose SHA-256 `d2865340ab82fec7086048c55798b3e1c29dabfca3d8999d2ab36b5e94e0c4c9`。
- 启动时 API 未立即监听；未快速回滚或重复重启。持续观察后 API `/health` 返回 200，Dashboard `192.168.3.27:9119` 可达并返回登录重定向 302，容器 running、RestartCount 0。Plugin Doctor 显示 D078 guard 成功加载并注册 1 hook。Profile toolset 为 file/skills/vision，不含 Terminal；Skills 写审批启用、审批模式 manual。
- 先前本地隔离镜像检查和部署后 NAS 容器内合成调用均通过：敏感 Session 路径读取 BLOCKED，合成允许路径文件 dispatch ALLOWED，Skills 只读工具 ALLOWED，dispatcher 异常 BLOCKED；零模型调用、零 Session 写入。没有通过生产 API 创建 Run。App/Core 保持 healthy；Private 未挂载、Knowledge 主目录只读（既有专用 Capture Inbox RW 不变）、Promote=false。D077 Personal Memory 根仍 `1026:100 / 0700`、0 文件/0 字节，metadata mtime 未变化；未读取其内容。
- **状态：** Hermes 镜像升级和限定运行验证完成，非完整业务验收。未调用付费模型或处理真实个人资料；真实浏览器记忆体验仍未进行。部署可回退到官方 v0.22.2 digest 与快照 Compose，但不得恢复 API Terminal 或回退 Core Memory 数据。

## 2026-10-17 — NAS 历史构建与回滚资产只读审计

- 只读检查纳入 11 个历史 App 源码副本、10 个旧 Compose 快照和 18 个 D074–D078 rollback 目录。实际分配占用：源码 63,892 KiB、Compose 40 KiB、rollback 5,152,284 KiB，合计 5,216,216 KiB（约 4.97 GiB）。容器挂载不指向这些历史路径；当前 Compose 仍引用 `/volume1/docker/secondbrain/app-build-source-d076-organizer-b34319a`（6144 KiB），其余 10 个 App source 目录（57,748 KiB）不在当前 Compose/检查的部署脚本引用中。10 个 Compose 快照没有当前引用，合计仅 40 KiB。
- D077 大型状态备份包括 `d077-issue12-authorized-20261016T124238Z`（1,025,656 KiB）、`d077-issue12-v0222-predeploy-20261016T1225Z`（2,059,884 KiB）和 `d077-v0222-predeploy-20261016T114324Z`（2,059,688 KiB）。其 Hermes tar 文件尺寸接近，可能包含重叠状态，但本轮未计算归档内容哈希，无法证明重复；不得据大小相似而删除。最新 D078 当前 Hermes rollback `d078-hermes-hook-failclosed-20261016T173140Z`（12 KiB）必须保留；`d078-stage1-20261016T155327Z`（6560 KiB）也保留。D074/D075/D076 较早回滚目录合计较小且未被运行路径引用，是否淘汰需结合所需恢复历史另行确认。
- 完整候选路径与各目录分配大小见本轮审计回复。只读审计未读取凭据或业务文件正文；未删除、移动或修改任何候选资产，没有执行 Docker 镜像/容器/卷清理。若要清理，须对候选逐项授权；当前 Compose 引用的 source 目录和 D078 rollback 快照排除在可清理范围外。

## 2026-10-17 — PR #17 合并与固定 Hermes fail-closed 源码补丁（仅开发，未部署）

- PR #17 的 ChatGPT 复审评论 #6220562603 接受 fbee788d；按固定 head 使用标准 GitHub merge API 合并至 main，merge commit `20392ab6dc00bdce2984446349f60bd7c28a263d`。没有绕过 GitHub 审批/合并规则。NAS 插件和 Hermes 镜像未更新。
- 以 Hermes v0.22.2 固定源码 Commit `d923a5eb487a17c0a68801bba9ef0f56c81040a8` 制作可审核 patch：仅改变 `agent/tool_executor.py::_pre_tool_block` 的 dispatcher/import 异常分支，使其返回固定 `PRE_TOOL_CALL_HOOK_UNAVAILABLE` block；不暴露异常正文或工具参数。健康 dispatch 保留现有 Hook 行为、Hook deny 和 modify 参数路径。补丁与上游回归测试存于 `web-app/hermes-agent/patches/v0.22.2/`。
- 固定源码补丁定向测试 **6 passed**：正常 `read_file` 与 `skill_view` 仍 dispatch；Hook 对敏感路径的 block 保留；dispatcher 抛 `ImportError` 或 `RuntimeError` 时，真实 `_dispatch_authorized_once` 在 guardrail/执行 callback 前阻断。补丁能对干净的固定源码 checkout 执行 `git apply --check`。
- PR #17 中的 manifest capability 修复仍未部署；本补丁目前仅为 SecondBrain 源码仓库中的 Hermes v0.22.2 patch，尚未合并、构建自定义镜像或运行于 NAS。下一步须复审补丁，再另行设计固定源/镜像的可复现构建与部署授权。API Terminal 保持关闭；无模型调用、NAS 变更或真实个人数据。

## 2026-10-17 — D078 第一阶段 NAS 部署（API Terminal 保持关闭）

- 已核对并按依赖顺序合并 PR #13 → #15 → #16。PR #13 merge commit `3b850ec17fc54f6b30a45e1b5cd258372c1e0f67`，PR #15 `822fe2a3f06d1711925bb9388baacbb4710afb38`，PR #16 / GitHub main 当前提交 `1d922422b419f7c6773df1849ce7a7c130392006`。PR #16 源 head 为 `d78a6bfd376c97043ffab0d5fc18371baf33148a`。
- 构建输入取自 PR #16 head `d78a6bfd376c97043ffab0d5fc18371baf33148a` 的 tracked `web-app` archive；该 head 已包含在 GitHub main merge commit `1d922422b419f7c6773df1849ce7a7c130392006`。构建 NAS Core/Web App 镜像 `secondbrain-app:d078-1d92242`，Image ID `sha256:3cfeeb01e9c1772c59bfca394722b22b9e87c7ce8d098a9ee5742ac530d41487`，平台 linux/amd64。镜像构建中的前端 `npm run typecheck`、Vite build 通过；只重建 App 服务。Hermes 沿用 v0.22.2 固定 amd64 digest `sha256:a11574b7fe8e1631d7d88d556677dac693bc058abf558cdeb899155688c1bf05`，upstream `d923a5eb487a17c0a68801bba9ef0f56c81040a8`。
- Hermes 数据目录安装 `secondbrain-d078-guard` 插件；Profile 启用插件、保留原生 `skills.write_approval=true`、`approvals.mode=manual`，API toolset 仍为 `file,skills,vision`。API Terminal 未加入；未改 CLI terminal 配置。Hermes Plugin Doctor 报告 runtime discovery、manifest parsing、import 与 registration 通过（1 hook），同时提示 `pre_tool_call` 未列在 manifest 的 `provides_hooks` 字段；该提示尚未通过后续端到端运行验证消除。
- 运行状态：App 容器 `674e7aa05af22a485ec9d769c370dddd0cda88c45d3e9412ee4c23cf3a54173e` healthy；Core `/health` 200、App `/` 200；Hermes 容器 `2cf7cec6d44dc49de37f0fb16c36f8e71f4bea5747aeecc2782efabf09eeb86f` running，容器内 API 8642 与 Dashboard 9119 `/health` 均 200。API 8642 没有发布到宿主；只保留原 Dashboard `192.168.3.27:9119` 映射。
- 合成守卫烟雾：从 NAS 已安装插件目录导入并调用 guard；合成 Hermes Session 读被拒绝（`hermes_private_path`），普通 file 对 Skills 路径写入被拒（`skills_write_gate`），Capture safe-root 写入目标获准。Hermes CLI Plugin Doctor 的 registration 检查通过。未写入任何合成/真实 Session、Skill 或 Capture 文件。
- 定向本地回归：D078 插件测试 14 passed；Core Memory、Learning、Run Approval、BFF 定向测试 43 passed；前端审批卡 3 passed。Core 的 43 项包含确定性 Mock 下 Sessions/Runs/SSE、跨 Session 记忆、纠正和审批路径，不是生产 Run。NAS Core health 与 UI 静态入口已验证；没有实际生产 Chat/Run/SSE 请求，因为这会使用已配置 Provider，且本次明确禁止付费模型。
- 权限/数据边界：App 用户 `1026:100`、只读 rootfs、非 privileged、`no-new-privileges`；Core Memory/Learning flags true，个人记忆目录 `1026:100 / 0700`，0 文件；Private 未挂载，Knowledge RO，Promote OFF。D077 JSONL、Hermes Session 与现有业务数据均未改写；未操作其他 NAS 服务或家庭网络。
- 首次重启曾因本次配置合并重复添加已存在的 `skills.write_approval` 配置键造成 YAML 重复键，Hermes 回退默认配置且 API 暂时未监听。诊断后只移除本次插入的重复行；Hermes `config check` 通过（另有既有 Home Assistant unknown-toolset warning），重新启动后 API/Dashboard 恢复 200，日志不再报告重复键或配置解析错误。无数据丢失；初次无效配置的 root-only 诊断副本与有效部署前回滚副本都保留。
- 回滚资料：`/volume1/docker/secondbrain/rollback/d078-stage1-20261016T155327Z/`（目录 `0700 root:root`）。部署前 Compose SHA `36c1d6cf14643ad41e5c04ec9ac1374b194dc52ebefbbe6dc6c57d1ac3fdd4a2`；部署前 Hermes config SHA `a105f96d187067975b1a519cc4a83386284f4b10419835fba2c3b542e082f2e`；当前 Compose SHA `d2865340ab82fec7086048c55798b3e1c29dabfca3d8999d2ab36b5e94e0c4c9`；当前 config SHA `34fe0bdad9d6e5990677b87ffa67cfb8fd237a18462da6958737bff23faf9155`。回滚前再次保存当前配置，恢复两个 before 文件及原属主/0640，然后只重建 App、重启 Hermes；保留 D077 Core state 和 JSONL。
- **剩余风险 / 验收状态：** Hermes 日志报告 API server network-accessible 且 terminal backend local；API toolset 未包含 terminal、8642 未发布宿主端口，但 API 容器网络仍具备内部访问路径。上游 `_pre_tool_block` 对 plugin hook dispatch 异常可能 fail-open；Stage 1 部署当时没有 API Run，因此不能据当时证据声称路径守卫已强制执行。后续固定源码隔离 API Run 与 fail-open 复核见下一节。API Terminal 保持关闭；不使用真实私人数据，不把当前状态描述为真实模型闭环或用户验收通过。

## 2026-10-17 — D078 固定源码隔离 API Run 与 Hook 边界复核

- 修正 PR #17 分支中的 D078 `plugin.yaml`，新增 `provides_hooks: [pre_tool_call]`。使用本地 Hermes v0.22.2 固定源码 Commit `d923a5eb487a17c0a68801bba9ef0f56c81040a8` 调用真实 `Plugin Doctor`：runtime discovery、manifest parse、import、registration 全通过，1 hook 注册，无 undeclared hook warning。新增一个最小单测锁住 manifest 声明。
- 隔离环境使用临时 `HERMES_HOME`、合成 Session sentinel、API 仅启用 file tool、API bind `127.0.0.1`、模型 endpoint 为本机 loopback 确定性 Mock；Mock 未连接任何收费/外部模型，也未配置真实凭据。用 Hermes API `POST /v1/runs` 实际启动一次请求（HTTP 202），Hermes 运行读取合成 Session 的 `read_file` 调用；运行日志记录该调用被 D078 hook 拒绝，固定码 `hermes_private_path`。Run 最终 completed；`/v1/runs/{id}/events` 返回 HTTP 200 且 terminal event 为 `run.completed`；Run output 未包含 sentinel。这是固定源码 API 路径实跑，不是 NAS 容器运行。
- 本机过程使用 Python 3.12.14，而 Hermes v0.22.2 部署运行时为 Python 3.14；首次隔离请求因临时 venv 缺少 `snowballstemmer` 在工具 batch dispatch 前失败，仅向该临时环境补装该 Hermes 依赖后，第二次 Run 成功。Gateway 同时报告与 API 路径无关的 Python 3.12 Group Chat worker `Path` import error；API loopback Run 和 file dispatch 正常。D078 插件单测覆盖 `search_files` 与 Skills 路径 generic `write_file` 拒绝；本轮没有为 Skills 路径另发 API Run。
- 上游风险核验：`hermes_cli.plugins_dispatch` 对 `pre_tool_call` callback exception / timeout 会生成 block directive；但 `agent/tool_executor.py::_pre_tool_block` 的外围 `except Exception` 返回 `(None, ref.args)`，即 dispatcher/import 本身异常时仍会继续工具调用。此为固定源码中的真实 fail-open 行为。D078 插件无法捕获其自身未被调用时的异常；本 PR 只修正 manifest capability 声明，不用 monkeypatch 遮盖上游风险。可靠修复需在 Hermes 固定源码/镜像入口增加 fail-closed 行为，或由可验证的强制 API 边界拒绝该路径；本轮未修改 Hermes 源码及 NAS。
- **结论：** 插件正常加载时，固定源码 API Run 的敏感文件读取实际拦截为 `VERIFIED`；manifest warning 在 PR 分支已修复，NAS 当前安装文件尚未更新；上游 dispatcher/import 故障 fail-open 为 `VERIFIED` 且未修复。API Terminal 仍关闭；目前不具备真实个人资料/浏览器模型体验条件。没有 NAS 写操作、容器重启、真实数据或付费模型请求。

## 2026-10-16 — D078 PR #16 固定 Hermes Hook 与审批对象核验（本地合成，未部署）

- 按 ChatGPT 复审评论 [#6218417694](https://github.com/zxwan829/SecondBrain/pull/16#issuecomment-6218417694)，核对固定 Hermes v0.22.2 upstream commit `d923a5eb487a17c0a68801bba9ef0f56c81040a8`。源码注册的内置 file 工具为 `read_file`、`write_file`、`patch`、`search_files`，4 个 schema 的路径属性均为 `path`。`patch` 的内容式多文件模式没有顶层 path，D078 guard 因无可审查路径而 fail-closed。`process_manage` 属 terminal toolset，参数为 action/session_id/data/timeout/offset/limit；`execute_code` 属 code_execution toolset，公开参数为 code/reset。当前 NAS API toolset 保持 `file,skills,vision`，本轮未接触 NAS。
- 使用该固定源码的 Hermes `PluginManager`、临时 `$HERMES_HOME` 与合成 profile 真实加载仓库 D078 插件；通过 Hermes 实际 lifecycle `pre_tool_call` dispatch 验证 terminal `approval.request` 事件、拒绝时阻断以及 once 允许到 tool-dispatch 边界；没有调用 agent、provider 或真实 terminal handler。事件使用 v0.22.2 API Server `_approval_request_event` 构造。测试将仅 `TERMINAL_ENV=local` 配置值替身为 local；没有验证真实 terminal 进程启动或 OS 隔离。Sensitive Session 路径读及 Skills 路径 generic `write_file` 均由已加载插件实际拒绝。
- 源码显示 Hermes terminal 执行时会经 `_resolve_command_cwd` 选择 Session cwd、后端默认 cwd或映射路径。为让审批内容明确对应实际执行上下文，D078 现要求 terminal 提供 canonical absolute `workdir`、仅接受 local backend 和固定 v0.22.2 合同中的参数；其他 backend/非 canonical cwd/额外参数 fail-closed。`process_manage` 与 `execute_code` 的动作/目标/代码参数也按固定 schema 检查。为防其他 `pre_tool_call` Hook 在审批后改写目标，发现任何其他执行 Hook 时 fail-closed。
- Core 校验固定工具允许参数及必需 workdir，审批 digest 继续覆盖完整 canonical `{tool, arguments}`；UI 校验显示命令与 terminal/code 参数一致，显式显示 workdir，并公开全量参数。UI 警示改为准确说明获批程序仍可自行启动程序或访问文件；这是审批门禁，不是 OS 沙箱。
- 针对性测试：Guard/Core approval registry/BFF **34 passed**；前端审批卡 **3 passed**；前端 TypeScript typecheck 通过；`git diff --check` 通过。实际 Hermes 源码 Hook smoke 为 synthetic deny/once、敏感 Session read deny 和 Skills generic write deny 均通过，无工具执行与模型请求。
- 当前证据不证明实际 API Run 触发了生产容器里的插件，也不证明命令的所有程序副作用可静态审计；任意用户批准的 executable 仍以 Hermes worker OS 权限执行。Hermes 上游 `tool_executor._pre_tool_block` 在 plugin hook dispatch 异常时会 fail-open，所以生产 API terminal 必须保持关闭，直到部署环境验证插件已加载且无其他执行 Hook；不能把此次源代码 smoke 当作生产强制策略验收。Session file 拒绝也只有在插件实际部署加载后生效。
- 文档冲突按 PR #15 分支 `docs/d077-governance-stage-20261016` 处理：本 PR 继承其基于 PR #13 的较新 `00-CURRENT`、Decision-Log D078、Progress 及 Environment-Baseline；保留 PR #13 的真实 D077 NAS 部署记录和 PR #15 的 D078 决策，不复制旧 main 快照或改写 Environment 基线。PR #16 是堆叠 PR，需先审核/处理 PR #13 与 #15，再合并本实现。没有修改 NAS、生产配置、Compose、凭据或生产模型设置；没有 Runner、合并或部署。

## 2026-10-16 — Issue #14 工具权限核验与 D078 业务决策（部分加固已部署，方案实施进行中）

- 按 [Issue #14 报告](https://github.com/zxwan829/SecondBrain/issues/14#issuecomment-6216831918)，Hermes v0.22.2 API Server 先前启用 `file,skills,terminal,vision`，且 terminal 为 local/unsandboxed；Codex 将 API toolsets 收窄到 `file,skills,vision` 并仅重启 Hermes。配置解析器确认 terminal 已移出 API Run；Hermes API health 200、Dashboard 302、Core healthy，D077 Memory/Learning flags 未变。该项为**已部署的临时保护**，并非已完成受监督执行方案；历史配置备份与哈希见 Issue #14。
- 同轮核验发现 API `file` 尚缺通用读取授权根限制：worker 可遍历 Session 目录，合成 Session 路径未被默认 read denylist 拒绝；凭据字段输出脱敏并不等于访问拒绝。本轮没有读取真实 Session 或 Secret，没有模型运行。真实模型浏览器体验仍等待安全边界确认。
- [Issue #14 源码结论](https://github.com/zxwan829/SecondBrain/issues/14#issuecomment-6217044891)：Hermes 原生 Skills `skills.write_approval` 提供暂存并由 CLI 审核的门槛；普通 file 没有通用逐次读取审批，Run approval API 不能自动变成 file/terminal gate；Core 尚未连接浏览器审批桥。Skills 开关及强制不可绕过的验证尚未部署。
- **用户最新批准 D078 原则**（[Issue #14 决策记录](https://github.com/zxwan829/SecondBrain/issues/14#issuecomment-6217209671)）：保留 Hermes 原生自主能力，危险 terminal 改为按需申请/批准，敏感 Session/config/file 读取强制受控，重要 Skills 写入审核；普通低风险知识读取/Capture 自动执行，Core JSONL 唯一个人记忆 SoT。先前“永久关闭 file/terminal”建议已被覆盖。Codex 正在研究最小可实施技术方案，**不得提前写成已实施/测试/部署**。
- 文档此次由 ChatGPT 独立补齐状态和正式决策，没有修改 NAS、Compose、代码、运行工具配置、模型凭据或真实数据；PR #13 仍独立待审，文档更新基于其最新 `788b61a` 快照另建分支。


# 2026-10-16 — D077 Issue #12 Hermes v0.22.2 单次部署尝试与回滚

> **历史记录，已被后续成功部署取代。** 本段只保留首次启动观察不足后回滚的事实；后续部署、运行和合成闭环证据见下方 resumed deployment 记录及 Issue #14 更新。

- 用户授权评论 [#6215289230](https://github.com/zxwan829/SecondBrain/issues/12#issuecomment-6215289230)；本次按约 45 分钟边界执行一次。GitHub `main` 与远端 ref 均为 `b6e30f3f1b61cb4f821b7db2c2bca994302be6dc`；PR #8/#9/#10 均 OPEN 未合并，未使用其分支代码。
- 目标 Hermes 镜像身份核验为 linux/amd64，Digest `sha256:a11574b7fe8e1631d7d88d556677dac693bc058abf558cdeb899155688c1bf05`、Image ID `sha256:02e7aa0e84123fa0e9b22686e7a2bfb7d85fd59821d4d28812a3e07f3061cf41`。Core 候选 `secondbrain-app:d077-b6e30f3`（Image ID `sha256:7cce77d702cb51f0c318c91c427d95cff887a99caebb12b9cad287b388b1049c`）已存在，但未部署。
- 在受限快照后，只启动了一次 v0.22.2 Hermes。候选 Compose 通过 `docker compose config -q`；保留默认 dispatcher，显式设置 `API_SERVER_ENABLED=true`、保留 `HERMES_DASHBOARD=true`，并为 Core 候选准备了默认关闭状态下的独立 memory root/flags。s6/PID1 与容器启动流程可见，日志显示 schema 46→50 migration、gateway/dashboard s6 service started；检查时 8642 和 9119 未监听，未发现明确 fatal error。API 启用变量有效，Hermes profile `.env` 未覆盖该变量。
- **结论限定：** v0.22.2 本次运行期间未取得可验收的 API/Dashboard 监听，启动根因 `UNKNOWN`；观察结束时容器已回滚。回滚后的旧 v0.21.5 约一分钟后才开始监听，因此“短时未监听”不足以证明新版最终无法启动。受单次部署授权和止损边界限制，没有继续等待、改配置重启或再试一次。未启动 Core 候选，没有创建 Session/Run/SSE 或记忆数据；记忆四步闭环为 `NOT RUN`。未调用模型、Runner 或真实个人数据。
- 回滚完成后正式 Compose SHA-256 恢复为 `93fd215b319864d42d8f2223946329f38217cfa7e954b30069f9850eb785398d`（属主 1026:100、0640）。当前 Hermes v0.21.5 Image ID `sha256:e1e87aec2e3f5b9863c127a0f21f3b3c237c8717c57c323c7184a49ca12a0df6`，API 8642 / Dashboard 9119 容器内监听、API health 200；App 原镜像 `secondbrain-app:d076-organizer-b34319a` health 200，App→Hermes health 200。Personal Memory/Learning flags absent，`personal-memory` 目录不存在；Private 未挂载、Knowledge RO、Promote=false。其他 NAS 服务与家庭网络未触碰。
- 回滚资产在 `/volume1/docker/secondbrain/rollback/d077-issue12-v0222-predeploy-20261016T1225Z/`：原 Compose SHA `93fd215b…785398d`；Hermes 预部署状态归档 SHA `33bea50efaf70c1541ad2ed0cac6263e2d174889b18e81fd386100f2c3aff845`；SHA256SUMS 中 8 个文件全部通过。尝试后的 Hermes 数据目录另存为 `hermes-data.after-attempt/`，未删除。受限目录约 2.0 GiB；当时可用空间约 861 GiB。脱敏启动日志、候选 Compose 和运行摘要均在该目录，权限为 0600/父目录 0700。
- 当前 D077 仍为 `NOT DEPLOYED / NOT VERIFIED`；本 Issue 单次授权已消费。执行摘要已回复 [Issue #12](https://github.com/zxwan829/SecondBrain/issues/12#issuecomment-6215598399)，等待 ChatGPT 审核。任何后续 v0.22.2 启动/记忆闭环尝试均需新的有界授权，并应先为启动观察时长设置明确门槛。

# 2026-10-16 — D077 Issue #12 resumed deployment and synthetic memory loop

- 用户新授权评论 [#6215695514](https://github.com/zxwan829/SecondBrain/issues/12#issuecomment-6215695514) 覆盖 SecondBrain NAS Hermes v0.22.2 启动诊断、必要最小配置调整/重启、D077 Core 部署与合成记忆闭环；禁止付费模型、真实数据、Private 和无关服务/网络影响。项目规则、当前基线、Agent-Rules、D077 Product Spec 及 Issue #12 已核对。原主 Clone 的 `main`/未跟踪 `typescript` 未触碰；Core 镜像使用当时 GitHub `main`/远端 HEAD `b6e30f3f1b61cb4f821b7db2c2bca994302be6dc`，未用或合并 PR #8/#9/#10。
- Hermes 目标是 v0.22.2 linux/amd64 Digest `sha256:a11574b7fe8e1631d7d88d556677dac693bc058abf558cdeb899155688c1bf05`，Image ID `sha256:02e7aa0e84123fa0e9b22686e7a2bfb7d85fd59821d4d28812a3e07f3061cf41`。原 Hermes 配置迁移到 schema 50 后以 SHA-256 `cdee7b148aa314536e24986f8f0dd57ea5999350e46c6b3bfd65c25a37eecac9` 备份；只读数据/配置内容未输出。Core image `secondbrain-app:d077-b6e30f3` / Image ID `sha256:7cce77d702cb51f0c318c91c427d95cff887a99caebb12b9cad287b388b1049c`，源代码 commit `b6e30f3f1b61cb4f821b7db2c2bca994302be6dc`。
- 正式 Compose 从 `93fd215b319864d42d8f2223946329f38217cfa7e954b30069f9850eb785398d` 更新到 `36c1d6cf14643ad41e5c04ec9ac1374b194dc52ebefbbe6dc6c57d1ac3fdd4a2`（属主/权限 `1026:100 / 0640`）。只切 Hermes 固定镜像、显式启用 API Server、App Core 镜像与 Memory/Learning flags；Hermes 原 dispatcher、Dashboard、端口映射、网络和卷权限保持既有边界。Compose `config -q` 通过。
- Hermes 首次启动时 s6/gateway/dashboard 均启动，8642 API 与 9119 Dashboard 在约 2 分钟后可连接；两端 health/listener 实测通过，未应用代码修复。旧尝试的根因仍为 `UNKNOWN`，本次证明在更长观察后服务能够就绪。为禁止外部模型调用，测试期间将 Hermes profile 临时指向 Core 容器内地址的确定性 Stub（已有 `secondbrain_default` 网络，无新容器/网络/宿主端口），并关闭 Hermes 内置记忆选项。测试结束后原 config 以同一 SHA 原样恢复，Hermes 最终重启时间为 `2026-10-16T12:55:22.167231091Z`，随后执行 16 次、每分钟一次的稳定性观察（2026-10-16 12:57:09–13:12:14 UTC，15 分 5 秒）：16/16 均为 running、restart count 0、API HTTP 200、Dashboard TCP 可连接；完整脱敏结果保存在受限快照目录。
- Core `SB_PERSONAL_MEMORY_ENABLED=true`、`SB_PERSONAL_LEARNING_ENABLED=true`；独立路径 `/var/lib/secondbrain-core/personal-memory` 对应宿主 Core state 子目录，`1026:100 / 0700`。以虚构偏好执行 4 个新 Session、4 个 Run 和 4 条完整 SSE：自动保存及 `user_message` 来源关联、跨 Session 旧偏好上下文、用户纠正的 JSONL 修订、纠正后新偏好注入且旧偏好不再注入均通过。Core Active API 在纠正后返回 1 条 active item、source type `user_message`，历史 2 个 revisions。
- 本地 Stub 收到 15 次请求，全部发往 `http://secondbrain-app:19001/v1`；其中 4 个流式主 Run 请求里，跨 Session/纠正前两次含旧偏好上下文，纠正后请求只含新偏好。Stub 未保存 prompt/body，只保留布尔观测；无付费 API、真实模型或真实个人数据请求。四条流式请求均含 Hermes tool definitions，但 Stub 返回普通完成消息、未发 tool call；故本次没有工具执行证据，也不能据此评价真实模型行为。Gateway 另有 API bind `0.0.0.0` / local unsandboxed terminal 的安全提醒；8642 未发布宿主端口，现有 Compose 网络只附加 App 和 Hermes，挂载/capabilities 未放宽。这是后续需审视的运行风险，不构成本次工具行为验收。
- 清理：4 个合成 Session 定向删除并通过列表确认缺失；合成记忆 JSONL 保存到 root-only 测试证据后，从活动 memory 根目录删除 JSONL/lock，保留启用所需的空 `0700` 目录；Stub 进程及 App `/tmp` 脚本/观测文件已停止并移除。没有增加 Docker 容器、网络、发布端口；Private 未挂载、Knowledge RO、Promote OFF，其他 NAS 容器/家庭网络未变。
- 快照 `/volume1/docker/secondbrain/rollback/d077-issue12-authorized-20261016T124238Z/` 为 `0700 root:root`，文件 `0600 root:root`；包括部署前 Compose、Hermes 数据快照、迁移后原 config、候选 Compose、脱敏日志、Stub 布尔证据、合成 JSONL、测试摘要。旧 Issue #12 回滚目录未改动。未触发 Runner、未部署 PR #8/#9/#10/#13、未合并或发起真实模型请求。D077 NAS 部署与合成闭环为 **PASS**；真实模型质量及用户验收仍 **NOT TESTED / PENDING**。

# 2026-10-16 — D077 Phase 1-B 最终验收及合并收口

- PR [#6](https://github.com/zxwan829/SecondBrain/pull/6) 的最终 head `0efe462cd8dbe6067b25d1e51cf69e1309cc42f7` 经独立代码复审，纠错需规范化完整等价且唯一，失败/取消/停止的 Run 清理 pending 状态；跨平台 Core 测试不再使用 `/private/tmp` 垫片。
- GitHub Actions Ubuntu 24.04 [Run 38857429530](https://github.com/zxwan829/SecondBrain/actions/runs/38857429530) 完成且成功：**154 passed、2 subtests passed**；Personal Memory 模块 **8 passed**，`compileall` 和 `git diff --check` 通过。保留 Starlette/httpx 与 Actions Node.js 20 弃用提示。手动工作流无模型密钥或外部模型调用。
- PR #6 经审核以 squash 方式合并至 `main`，合并 Commit `ca26c42aa915e42b6ed0e5edb4f3580a3ae9a128`。状态是 **DEV-TESTED / MERGED / NOT DEPLOYED**，并非真实 Hermes 或用户体验验收。
- 剩余待独立核实：Hermes v0.21.5 实际执行 `instructions` 的效果、Run 与持久消息的权威关联、长时间无结果的 pending 状态、自动学习质量。所有个人记忆与学习开关仍默认关闭；NAS 生产部署、Hermes 升级、真实个人数据处理或外部提供商调用均未获本次合并授权。

# 2026-10-16 — D077 Phase 0-B2 收口与 Phase 1-A Personal Memory Core

- Phase 0-B2 记录的 GitHub Actions 证据为 **15/15 Runs**。该数字表示对应 Run 执行成功，不等同于学习效果通过；跨 Session 继承、纠错后失效/更新及主动召回仍记录有缺陷，故不能宣称自动学习闭环验收通过。供应商 Token/费用估值不等同账户最终账单。本轮没有部署 NAS、升级生产 Hermes 或处理真实个人数据。
- 按 GitHub Issue #3 / D077 Phase 1-A，在独立临时 Clone 从当时 GitHub 最新 `main` 开始（基线 `7a308f846ecfa192a135d165f8b41791140a1f6e`）。正式工作目录的 `.git/FETCH_HEAD` 写入仍受限，因此未触碰原目录或未跟踪项 `typescript`。
- 新增标准库优先、append-only JSONL Personal Memory Store，数据根由 `SB_PERSONAL_MEMORY_ROOT` 显式注入，必须预先存在、Core UID 所有且权限私有；`SB_PERSONAL_MEMORY_ENABLED` 默认 `false`。关闭时不创建数据根、不扫描会话、不启动任务。每个事件保留来源、类别、事实类型、时间、修订和状态；纠正追加新修订，撤销/失效保留历史；候选级幂等去重；并发写入使用文件锁与 `fsync`。日志异常或半写 fail-closed，不自动截断或重写历史。
- 增加受 AppSessionAuth 保护的 Core API：创建、少量 active recall 候选、按 ID 查修订历史、纠正、撤销、失效。推断不进入 active recall；精确事实回传来源指针并标记 `source_required`，不声称已读取/核验原件。此切片不接 Hermes、聊天自动提炼、外部 Provider、RAG、Journal/Task、Knowledge Promote 或 Private。
- 合成测试使用 `/private/tmp` 临时目录和独立 Python 3.12 venv，无生产挂载、NAS、模型或真实个人数据。`tests/test_personal_memory.py` 覆盖重启恢复、更新历史、撤销、精确来源、推断排除、候选幂等、同源多事实、并发追加、损坏日志 fail-closed、符号链接拒绝及鉴权；`test_web_app_bff.py` 新增真实 Core app 工厂上的默认关闭/注入根 API 测试。初轮测试发现并修正两处测试夹具问题后，针对性测试 **18 passed**。兼容 FastAPI/Pydantic v1/v2。
- 验证收尾：Core 全套回归 **136 passed、2 subtests passed**；`compileall`、`git diff --check` 通过。仅有 Starlette `TestClient` 关于 `httpx` 的弃用提示，不影响结果。
- **状态：** Commit `007f8ba` 已推送；PR [#4](https://github.com/zxwan829/SecondBrain/pull/4) 已打开且当前 GitHub 报告可合并。未部署、未进行真实数据验证或用户验收。Phase 1-B 才处理聊天候选提炼与 pre-turn 召回；真实会话出站和部署另行批准。

# 2026-10-16 — D077 Phase 1-A PR #4 review fixes

- 按 PR #4 最新审核修正同一来源消息的多事实入库：每个候选使用显式幂等键或由来源、正文、类别和事实类型导出的稳定键；不同候选可以并存，同一候选重放保持 exactly-once。
- `fact` 类记忆一律要求来源核验，即使请求省略 `exact`。模型使用的 active recall 对 `source_required` 项仅提供中性核验提示、来源指针和状态，不提供未核验原文；认证 history API 保留原文供审计/纠正。缺失来源原件时仍不可把精确主张当作已验证事实。
- 新增同源双偏好与幂等重放、遗漏 `exact` 且源文件缺失时 recall 脱敏/API 响应与历史原文保留回归。Core 全套 **137 passed、2 subtests passed**；`compileall`、`git diff --check` 通过。仅有 Starlette `TestClient`/httpx 弃用提示。
- 按 PR 后续审核移除测试对 macOS `/private/tmp` 的硬编码，使用平台默认临时目录并规范化路径；模块测试 **8 passed**，全套仍为 **137 passed、2 subtests passed**。本机验证通过；尚未宣称 Linux CI 已运行。
- 本轮未合并、部署、调用付费模型或访问 NAS。修正提交与 PR #4 head、审核状态以当前 GitHub 为准。

# 2026-10-16 — D077 Phase 1-B and Linux Core test portability (Issue #5)

- 从 GitHub 最新 `main` `8c45f281d0d3e7a52c2cb62934a84392524dbe40` 的独立临时 Clone 开始；未修改正式 Clone 或未跟踪项 `typescript`。同一集成分支包含 Phase 1-B 和跨平台测试路径修复。
- Phase 1-B 增加默认关闭的 `SB_PERSONAL_LEARNING_ENABLED`。启用还要求 `SB_PERSONAL_MEMORY_ENABLED=true` 和已有绝对路径 Memory root；不启用时不扫描对话或注入记忆。Chat 前仅作小规模确定性相关性筛选，复用 Memory Core active/redaction 视图；Chat input 原样发送，相关记忆走现有 Hermes API `instructions` 字段。
- Run 后仅在 `run.completed` SSE 或状态为 completed 时读取同 Session 持久消息；必须匹配原始用户文本及有 ID 的消息来源后才提炼和写入。候选提炼器可注入，当前默认实现只抽取有限的明确偏好表达，过滤已知敏感/指令样式文本；无付费模型调用。重复消息源绑定 newest-order 消息有回归覆盖。
- 按固定 Hermes v0.21.5 upstream commit `749220ef0007f8d87bd1531f1c24b0fe93816385` 的 API Server 源码核对：`/v1/runs` 支持 `instructions` 并将其传给 Agent 的 ephemeral system prompt。Hermes 真实 v0.21.5 运行是否实际遵循注入、模型是否自主学习，以及进程重启/多 Worker 下 pending Run 状态行为尚未验证；本地 Mock 仅证明 SecondBrain 适配器传递该字段与 Core 触发逻辑。
- Linux portability 子项将五处 Core 测试夹具改用平台临时目录，移除 Linux workflow 对 `/private/tmp` 的创建垫片，并新增静态防回归检查。GitHub workflow 仍为手动触发、Ubuntu 24.04、无 secrets。
- 集成分支全套 Core 测试 **146 passed、2 subtests passed**；`compileall` 与 `git diff --check` 通过。GitHub Actions 单次 Ubuntu 24.04 Linux workflow run [38856373579](https://github.com/zxwan829/SecondBrain/actions/runs/38856373579) 成功，Core 全套与 compileall 均通过。Action 提示 `checkout@v4` / `setup-python@v5` Node.js 20 运行时弃用，未影响本次结果。
- Phase 1-A PR #4 于本日已合并入 main；本 Issue #5 变更在 PR [#6](https://github.com/zxwan829/SecondBrain/pull/6)，当前 OPEN，未合并。集成分支最终 commit 记录在该 PR head。
- 未升级 Hermes、部署 NAS、处理真实个人数据或调用付费模型。未验证真实 v0.21.5 运行行为、模型学习质量、跨进程 pending 状态恢复或用户体验；这些仍需独立审核/授权。

# 2026-10-16 — PR #6 memory accuracy review fixes

- 按最新审核意见修复旧消息可能被误认作新 Run 来源的问题：Chat Run 前读取同 Session 的持久消息 ID 水位；只有成功 Run 后出现、文本与会话匹配且 ID 不在水位中的消息才可作为学习来源。预读失败时 Chat 正常继续，但该 Run 不学习；相同会话存在并发重复输入时两次都跳过学习，避免来源猜配。
- 收紧纠错目标选择：旧偏好完整短语必须出现在唯一一条当前偏好中；未命中或多条命中均不创建替代项、不改写旧记录。新增旧消息重用、正常新重复文本、并发重复输入、预读故障、歧义纠错和精确纠错回归。
- 定向测试 **12 passed**；Core 全套 **151 passed、2 subtests passed**。Linux workflow 保持手动/无 secrets，既有 `/private/tmp` 兼容性修复未变。
- 更新提交与 PR #6 head 以 GitHub 当前状态为准；本轮未重跑 Linux workflow，未部署或合并。

# 2026-10-16 — PR #6 final memory safety fixes

- 纠错目标现在要求去除已知偏好表达前缀后的规范化文本完全等价，拒绝仅凭子串/词片重合改写记忆；多条相同目标仍 fail closed。
- 新增 pending Run 的 `discard_run`；SSE `run.failed` / `run.cancelled` / `run.canceled` / `run.stopped`、状态 API 对应终态，以及成功返回的 Stop 操作都会清理对应状态。没有加入后台清理任务。
- 新增单条错误子串命中、失败/停止后相同文本新 Run 成功学习回归。定向测试 **15 passed**；Core 全套 **154 passed、2 subtests passed**。Linux 手动 CI 尚待在本次最终代码提交上运行。
- 未调用外部模型、访问真实数据或部署 NAS；Linux 临时目录兼容修复保持原样。

# 2026-09-28

- Hermes Docker 正式环境稳定，固定 IP 172.18.0.2。
- Hermes 独立策略路由完成，新增 hermes-policy-route.sh。
- DSM 增加 SecondBrain Boot 开机任务。
- SecondBrain 受控写 namespace 完成。
- Hermes Dashboard LAN 常驻与认证完成。
- HERMES_WRITE_SAFE_ROOT 调整为 /secondbrain-write。
- Daily Capture V0 创建；首次测试暴露错误 Vault 搜索和 /opt/data fallback，随后优化为固定 Skill 路径。
- 最终真实 Capture 成功写入 00-Inbox，成功回复优化为单行。
- 下一阶段确定为 Review V0。

# 2026-09-29

- 对旧 SecondBrain Staging 基线执行最终合并审计。
- 确认 Architecture 已承接旧架构基线主体，清理旧路径、旧状态和旧优先级。
- 正式项目文档固定为 9 份。
- Home.md 与 SecondBrain Portal 职责重新定界。
- `/SecondBrain-Staging/` 正式进入退役流程。

- Review V0 Skill 创建完成。
- 两条真实样本测试通过。
- 原 Inbox 文件保持不变，10-Review 成功写入。
- 同名保护通过，正式知识区未被写入。
- Review V0 正式进入可用状态。

- Promote V0 Skill 创建完成。
- `20-Knowledge` 独立 RW mount 完成。
- 发现并解决 Synology ACL 写权限问题。
- 最小创建 / 读取 / 删除测试通过。
- 两条真实 Knowledge Promote 成功，Inbox / Review 成功清理。
- 首次验收发现异步时序假失败；第二次约 34 秒稳定完成。
- source 推测问题已发现并修复。
- Promote V0 正式进入可用状态。

- Portability / Packaging / Deployment Kit 已从后期优化提升为 V1 开发期硬约束。
- 明确 Core Skill、Agent Adapter、脚本、配置、模板、Compose 与宿主机步骤必须作为项目资产，消除隐形 NAS 依赖。
- openai-codex 最新测试：provider=openai-codex、model=gpt-5.6-sol 的最小请求超过 3 分钟仍无首个有效模型输出；链路暂不能判断恢复，生产默认仍为 SiliconFlow / DeepSeek-V4-Flash。

# 2026-09-30 Re-baseline

- 暂停施工并重新审视架构。
- 完成 Hermes Native Capability Audit。
- 完成 Codex App-Server Runtime Audit。
- 确认 Daily Capture / Review / Promote 无需返工。
- 退役独立 SecondBrain Portal。
- 收缩 V1 范围。
- 文档治理从 9 份活跃文档收敛为 6 份。
- 确立 Upstream First / Business Differentiation Only 原则。


# 2026-10-07 Resume / Upstream Review

- SecondBrain V1 正式恢复施工。
- 完成 Hermes 最新 upstream / issue / capability 调研。
- 当前没有切换 Agent Platform 的理由。
- 生产保持 v0.21.5，不追 main/canary。
- Knowledge Retrieval 确立渐进检索策略。
- QMD 进入候选升级路径，不进入当前默认架构。
- Skill 开发方式调整为：specification → Hermes authoring → Codex audit → human approval。
- Open Second Brain / Obsidian Second Brain 纳入方法论参考。
- Core Skill 单一真源等待下一 stable 做真实验证。
- Codex App-Server 继续候选。
- V1 剩余核心仍为三项，没有扩大范围。

# 2026-10-07 Phase 0 Capability Verification（历史阶段记录）
以下内容是当时阶段事实，不代表当前状态。

- search_files / read_file 已有生产成功调用证据。
- Knowledge Retrieval V0 = GO。
- skill_manage 已确认可用。
- skills.write_approval 存在但当前未启用。
- 当前 v0.21.5 未确认正式 /learn。
- QMD 当前不安装。
- Core Skill 单一真源继续等待下一 stable。
- 因缺少 sudo credential，未完成 root 级完整 Registry/源码枚举。
- 本轮无 Runtime 修改。

# 2026-10-09 Skill Approval Gate Permission Repair（历史阶段记录）

- skills.write_approval 已正式启用。
- 首次 knowledge-retrieval staging 出现 false-positive staged result。
- pending JSON 实际未落盘。
- 根因是 pending/skills 目录权限不足。
- 已完成最小权限修复：pending 与 pending/skills 设置为 owner=1026、group=100、mode=755。
- Hermes runtime user 写测试 PASS，临时测试残留 NONE。
- production 未受到影响，未重启容器。
- 【当时阶段】下一步重新创建 knowledge-retrieval，并验证真实 pending JSON 落盘。

# 2026-10-09 Knowledge Retrieval V0 Staging Audit（历史阶段记录）

- pending_id=abf53e64 已在宿主机与容器内真实落盘。
- pending JSON 可读取，payload/diff 可审计。
- 【当时阶段】knowledge-retrieval 尚未进入 production skills。
- 实际 staged record 为 batch(create)，pending 权限与哈希已核验。
- Skill 通过读取范围、只读工具边界、来源区分和 V0 范围审计。
- 冲突处理与输出模板建议后续微调：避免将日期优先解释为机械覆盖，并避免每次回答机械输出全部标签。

# 2026-10-09 Knowledge Retrieval V0 Production

- pending 权限修复完成。
- write approval production gate 跑通。
- Skill schema approval 阶段确认 description 必须为单句、长度不超过 60 字符并以句号结尾，frontmatter 必须包含 name。
- 最终 pending 06953a34 preflight PASS。
- Human Approval PASS，production verification PASS。
- 旧 pending 全部清理。
- Knowledge Retrieval V0 已正式进入 production。
- 第一项真实 Retrieval acceptance test PASS。
- 第二项测试暴露 governance SoT 更新滞后，而非 Retrieval 错误。

# 2026-10-09 Knowledge Retrieval V0 Current Status

- Knowledge Retrieval V0 production 已上线。
- 当前 pending queue 已清空。
- 当前进入真实功能验收阶段。

# 2026-10-09 Governance Batch 3 / Retrieval V0 Closeout

- 正式写入 Zero-learning-cost / Low-friction 产品原则与默认 Agent 业务路由。
- Knowledge Retrieval V0 完成生产验收，继续使用 search_files + read_file，并落实显式检索边界、Fast Path 与 fresh-read 规则。
- Hermes v0.21.5 / build 749220ef 核查确认无原生 Skill routing/preload；skills_list → skill_view 属于模型驱动 discovery。
- 旧版 Mac Pro 决策不存在测试耗时约 68.5 秒；Fast Path 收紧后同类测试约 24.8 秒，正确性通过，仍存在 discovery 开销。
- 重要 Skill Business Specification 纳入项目资产持久化原则；不依赖 session、state.db 或历史对话恢复。
- 本批次未修改 Hermes Skill、运行配置、容器、网络、ACL 或 Provider。


# 2026-10-09 Temporary Dev Permission Strategy

- 启用/确认 SecondBrain V1 施工期临时 root 权限策略，用于处理项目范围内 chmod/chown/Docker/Hermes 权限问题。
- 收口要求：V1 完成前删除 `/etc/sudoers.d/secondbrain-codex-dev`，验证 unrestricted NOPASSWD root 已撤销，恢复项目级受限权限并完成审计。


# 2026-10-09 Model Test Cleanup / Strategy Closeout

- 完成本轮低成本模型筛选，施工模型正式收口到 DeepSeek-V4-Flash。
- 保留 Qwen / GLM 作为备用实验 profile，删除 Step / Hunyuan / Ling 实验 profile。
- 清理本轮 Universal Capture 测试残留。
- TEMP-SECURITY-DEBT 仍为 OPEN。


# 2026-10-10 Current State Rebaseline

- Qwen Universal Capture 0.1.2 passed corrected real acceptance: Raw and Review both landed, frontmatter and original_asset/source passed.
- Qwen sample cost was about ¥0.0248 with about 40 seconds elapsed; an extra terminal/date call triggered approval, so functionality passed but Fast Path/tool discipline did not.
- GLM-4.5-Air passed clean Fast Path: skill_view ×1 + write_file ×2, no terminal/search/read and no approval interruption; observed elapsed time was about 18.2–22.5 seconds.
- DeepSeek-V4-Flash passed clean Fast Path: skill_view ×1 + write_file ×2, no terminal/search/read and no approval interruption; observed elapsed time was 16.6 seconds and one sample cost about ¥0.047.
- state.db usage forensics confirmed sessions/messages/session_model_usage. GLM sessions were about 41.6K–41.8K total context; Qwen input was 54,320 with cache_read=0; DeepSeek was 12,286 uncached + 31,232 cached = 43,518 total, about 71.8% cache hit. These are non-standardized samples, not fixed prices.
- D041 Qwen Raw/Review failure conclusion is superseded in part by the later successful clean retest.
- Hermes v0.21.6 stable is now available for Canary evaluation. Canary has not been run; no result is recorded.
- Skill single-source status changed from WAIT FOR NEXT STABLE to READY FOR CANARY VALIDATION.
- Current production remains Hermes v0.21.5 / build 749220ef. No runtime, provider, model, Compose, ACL, or SecondBrain data was changed by this documentation update.

# 2026-10-10 Governance Priority Patch
- 模型最终日常默认保持 NOT YET FROZEN：Qwen 为低成本候选、GLM 为低摩擦候选、DeepSeek 为复杂/高可靠主力与兜底。
- P0 为治理收口、latest image 漂移风险核验、v0.21.5 Profile/Toolset 约束核验及一次性 Qwen 干净复测；P1 为 Universal Capture 产品化收口；P2 为 Dashboard / Journal / Schedule。
- Hermes 0.21.6 为 AVAILABLE STABLE / EVALUATION DEFERRED / CONDITIONAL CANARY，V1 主线不因升级暂停。
- Skill single-source 状态为 READY FOR FUTURE STABLE VALIDATION / DEFERRED；生产不迁移，不建立 rsync / Adapter / 自研 loader。

# 2026-10-10 Hermes Immutable Image Pin

- Production Hermes image 已从 latest 固定到 verified v0.21.5 immutable digest。
- Running container 未 recreate、未 restart；runtime/version/image ID 保持不变。
- Latest drift risk：RESOLVED / PINNED。

# 2026-10-10 Qwen Tool Boundary Audit

- 完成 v0.21.5 Tool Boundary forensic audit：enabled_toolsets / disabled_toolsets 为 Agent/session/toolset scope 的 hard enforcement。
- 确认不存在 model/profile-specific binding；Qwen-only terminal restriction = NO-GO。
- 未修改 config/runtime；未建立 custom Router/middleware。
- Qwen clean retest DEFERRED / BLOCKED BY MISSING NATIVE MODEL-SCOPED TOOL ROUTING。
- P0 model/tool-boundary investigation CLOSED。

# 2026-10-10 GLM Construction Model Switch

- Production default model switched from DeepSeek-V4-Flash to GLM-4.5-Air; config change was default model only。
- Hermes applied configuration successfully; minimal inference PASS with GLM_SWITCH_OK and no tool call。
- Gateway/Dashboard remained healthy；Hermes v0.21.5 / build 749220ef unchanged。
- Production image remained unchanged and pinned；DeepSeek remains fallback，Qwen remains low-cost candidate，final long-term default is not frozen。
- Next mainline: Universal Capture productization closeout。


# 2026-10-10 Universal Capture V1 Productization Gap Audit

- 只读审计完成: 生产 universal-capture v0.1.2，Skill 与 Runtime 未修改。
- Qwen、GLM-4.5-Air、DeepSeek-V4-Flash 均有真实 Raw/Review 双文件落盘证据；Qwen 另有 terminal/date 与 approval 成本，GLM/DeepSeek 为干净 Fast Path。
- 能力矩阵: 文本/Markdown/TXT/可读文本与 Capture Context = DONE；Raw/Review/绝对路径/成功校验/Human Approval = DONE；tags/关联/幂等与 partial-failure = PARTIAL；PDF、Office、图片/OCR、Web、音视频、通用附件及语义去重 = DEFERRED。
- 正式范围内未找到唯一 Business Specification；该缺失是产品化实现 BLOCKER。未执行任何 Runtime、Skill、配置、模型、Compose、ACL、网络或数据修改。

# 2026-10-10 Universal Capture Business Specification Freeze

- Created and froze the canonical Universal Capture Business Specification v1.0.
- V1 MUST, SHOULD, and DEFERRED scope frozen; URL/Web, PDF, Office, image/OCR, audio/video, generic attachments, semantic deduplication, QMD/RAG/vector and transactional rollback remain deferred.
- Raw + Review do not require Human Approval; Review to Knowledge/Promote does require Human Approval.
- Fast Path, safe retry, collision protection, partial-failure reporting, and real artifact verification contracts frozen.
- No Runtime or production Skill modification. Prior Business Specification blocker resolved.

## 2026-10-10 Universal Capture v0.1.3 Canonical Staging Audit

- Universal Capture alignment status: STAGED / AWAITING HUMAN APPROVAL.
- Canonical pending: d1abbad6; single full-content skill_manage operation targeting universal-capture.
- Candidate v0.1.3 passed technical audit against Business Specification v1.0: scope, Fast Path, absolute write paths, safe retry, partial-failure reporting, optional tags/relationships, and no new tool dependencies are preserved.
- Production Skill v0.1.2 remains unchanged; no approve/deploy was performed.

# 2026-10-10 Governance Write Safety Hardening

- Governance truncation incident occurred; affected files were recovered. The exact triggering command is NOT FULLY PROVEN, while direct/non-atomic write risk is confirmed.
- Atomic safe-write protection and recovery snapshots were deployed.
- Live Mirror corruption guard, atomic mirror update, and explicit deletion policy were deployed.
- Failure-injection tests A-G PASS in an isolated temporary test directory.
- Formal governance updates were applied through the safe-write helper; UC pending d1abbad6 and production Skill remained unchanged.

# 2026-10-10 Universal Capture v0.1.3 Final Acceptance

- Human Approval for d1abbad6 succeeded; production v0.1.3 and candidate SHA256 `e30cf214cbceedc6e07648fb94b0d6e4bbb880a0033f9eb88f8295966ba18acb` verified; pending cleared.
- GLM-4.5-Air synthetic real acceptance PASS: Raw + Review landed, paths/frontmatter/original_asset passed, no Knowledge write or auto Promote.
- Collision retry smoke was blocked before tool execution by provider HTTP 429 TPM rate limit; no second artifact was produced. Test artifacts were removed.
- Universal Capture permission fix uses the minimal explicit Joe ACL, not a chmod 777 command; Synology reports mode 777 on the ACL-bearing directory.

# 2026-10-10 Universal Capture Collision Closeout

- Dedicated collision seed created, then identical naming retry completed.
- Original Raw/Review artifacts were preserved byte-for-byte; collision-safe suffixed Raw/Review artifacts were created.
- No Knowledge write, no auto Promote, and all four test artifacts were cleaned.
- Safe Retry / Filename Collision PASS; Universal Capture v0.1.3 final acceptance closed.
- Permission fact recorded: POSIX 0777, root:root, explicit Joe ACL; no chmod 777 command used.

# 2026-10-10 Web App / Personal OS V1 Specification

- Created and froze `business-specs/SecondBrain-Web-App-V1-Business-Spec.md` v1.0 canonical.
- Documented Global App Shell, dynamic Home scope, extensible navigation/page contracts, aggregation contracts, reserved Books/People/Personal Events, SoT/runtime/security boundaries, and V1 acceptance criteria.
- No frontend, Runtime, Hermes, Compose, permission, or business-data changes were made.
- Next: WEB APP PHASE 0 NATIVE CAPABILITY + SECURITY AUDIT.

# 2026-10-10 Web App Phase 0 Closeout

- Phase 0, Phase 0.5, and Phase 0.6 completed; key capability and security unknowns cleared.
- Final architecture accepted: Hermes Dashboard Shell + SecondBrain Main UI Plugin + authenticated Thin Adapter + Hermes native Chat/session/status APIs.
- Security classification S3. No Hermes upgrade or Canary required.
- Next: WEB APP PHASE 1 — MINIMUM SKELETON VALIDATION. No implementation performed.

# 2026-10-10 Universal Capture Scope Re-freeze

- Universal Capture v0.1.3 text pipeline remains ACCEPTED.
- V1 scope expanded: URL/Web, PDF, Image/Screenshot, and Audio/Voice are V1 MUST but NOT IMPLEMENTED.
- New workstream: Universal Capture Attachment Pipeline. No production implementation performed.
- Office, Video, and generic binary remain deferred. Web App Phase 0 remains CLOSED / ACCEPTED.


## 2026-10-10 — Web App Phase 1 Technical Closeout

Closed Phase 1 minimum skeleton validation. Confirmed plugin discovery, authenticated semantic proof bridge, explicit allowlist, Private policy denial, real SecondBrain read, native Chat entry, Desktop rendering, and rollback. Tablet/Mobile actual viewport validation is deferred to Phase 2 because available automation lacks reliable viewport control; this is validation debt, not an observed UI defect.


## 2026-10-10 — Phase 2A-1 Home Semantic API

Implemented and verified authenticated Home aggregation endpoint `/api/plugins/secondbrain/home`. Real statuses: Agent online, Today empty, Review real, Projects real, Knowledge real, Brief not connected, Activity not connected. Unauthenticated access denied; no business writes.


## 2026-10-10 — Phase 2A-2 Final Closeout

Product Shell and Home real-data UI PASS. Desktop PASS. Tablet PASS via real iPad. Mobile PASS via real iPhone. No observed responsive blocker. Phase 1 responsive validation debt resolved. Daily Brief and Activity remain not connected; no business writes performed.

## 2026-10-10 — Phase 2B-0.1 Full-Bleed Immersive Polish

Implemented and verified route-scoped full-bleed styling for `/secondbrain`. Hermes sidebar and host banner are hidden only while the SecondBrain route is active; shell geometry fills the viewport. Native Chat navigation and return to SecondBrain passed; `/skills` admin route remained reachable. Source/runtime CSS hashes match. No compiled Hermes frontend, Compose, auth, or business data changes.

## 2026-10-10 — Phase 2B-0.7 Home Restore + Bilingual Acceptance
- Restored Home real-data cards from `/api/plugins/secondbrain/home` and verified the expected machine states with product language.
- Verified zh-CN and en UI, active-locale label semantics, locale persistence, Chat navigation, immersive full-bleed shell, and readable revisioned assets.
- Phase 2B-0.5 bilingual UI: CLOSED / ACCEPTED; no business writes or mock business data introduced.


## 2026-10-10 — FE-0 to FE-0.9 Frontend Engineering History

- Recovered the missing frontend engineering baseline as a React + TypeScript + Vite source project with Git history.
- Integrated Hermes v0.21.5 SDK registration and host React singleton; fixed duplicate React runtime, nonexistent `jsxRuntime`/JSX mapping, and missing `React.createElement` binding.
- Added reproducible npm/build/manifest/package gates and an executable bundle/render smoke test.
- Built and deployed isolated `secondbrain-fe-test` assets only; production `/secondbrain` and Hermes core were not changed.
- Home real-data API and Mac browser rendering were accepted; isolated iPhone visual acceptance was reported PASS. Locale persistence and Chat ↔ plugin cleanup/return remain PENDING for formal evidence.
- Historical Web App work recorded: Hermes plugin shell, auth/Private boundary, Home semantic API, KPI/Bento iterations, bilingual/responsive work, manifest and plugin registration failures, Home API 404/router remount, SSH recovery, and asset version alignment.
- Future work: Dashboard Visual V3 preparation, Dynamic Cockpit Home, Today/Review/Knowledge modules, Universal Capture follow-on, and WeChat integration.


# 2026-10-11 SecondBrain Dashboard FE-3 / FE-4 Rebaseline

## FE-0 至 FE-2 历程证据校正

- 已有项目记录显示 FE 初期建立 React 页面、Home Adapter、zh-CN/en 双语、Chat 宿主生命周期和响应式基础能力；FE Test 独立插件经历缓存/注册问题收敛，随后固定 JS/CSS 入口及 `deploy-fe-test.sh` 稳定部署方式落地。
- Git 证据可核验的里程碑提交：`bc7ad46`（可复现前端基线）、`46ddf65`（插件 manifest 源码）、`cb347f2`（Visual V3 shell）、`e07ded6`（FE-2.1 dashboard）。提交日期均为仓库记录的 2026-10-10；更早 FE-0 至 FE-2 的具体日期/commit 如无证据不补造。

## FE-3 视觉源码移植与验收

- FE-3.0 审查并移植 Gemini React Dashboard 的视觉实现；保留 Hermes SDK/宿主生命周期、Home Adapter、真实数据边界、双语和 Chat 恢复，不复制 Gemini 独立 React root 或全局 Tailwind Preflight。
- FE-3.1 完成 KPI 柱图/趋势图尺寸调整及 Today 山湖背景等局部精修；后续依用户提供的 PNG 更新星球、AI 立方体和 Today 背景，修正页面主体间距及移动端星球位置。
- 用户验收：Mac/PC 视觉 ACCEPTED；iPhone V1 视觉 ACCEPTED；iPhone KPI 星球位置在 `max-width:760px` 专属规则中相对原移动端位置右移约 20px、下移约 35px，用户 ACCEPTED。已验收 PC 视觉作为正式基准冻结。
- FE-3.2 滚动性能专项：诊断记录移除 11 张卡片常驻 `will-change`；优化前后 Paint/FPS/Long Task 没有完成可比较量化，不能声称滚动卡顿已解决。按用户决定 DEFERRED。轻微视觉瑕疵也 DEFERRED。

## FE-4 正式发布与业务状态

- 用户批准将 FE-3 已验收基准发布到正式 `/secondbrain`。正式 plugin ID/manifest/route 保持原正式身份；测试 `/secondbrain-fe-test` 独立保留。Home Adapter 复用真实 `/api/plugins/secondbrain/home`，没有后端重构或业务数据写入。
- 正式发布前快照位于 `/volume1/docker/secondbrain/hermes/data/secondbrain-fe4-rollback/fe4-20261011-155631/`；本次只读核验确认 `rollback.sh` 存在且 executable。正式 manifest、JS、CSS、三项视觉资产 SHA256 见 Environment-Baseline；测试固定入口哈希亦记录以证明隔离。
- TypeScript、Vite build、Manifest、Bundle、React Render 与 FE 回归测试已有 PASS 记录。已登录 Edge 加载正式路由，检查资源/渲染、Home API 数据与 Chat ↔ Dashboard 返回；沉浸模式诊断文本递归膨胀问题已修复。未经认证的 HTTP 资源请求会 302 到登录页。
- 数据真实性处理：Today 为真实空状态；Review 5 条、Knowledge 2 条均有真实条目但元数据不完整；Projects API 返回目录文件，降为 UNAVAILABLE；Agent 静态 online 无可信实时来源，降为 UNAVAILABLE；Brief/Activity 未接入；趋势、Donut、天气明确为 DEMO；写入功能未开放。
- 正式版 iPhone Safari 独立功能回归尚未完成。用户对正式版整体体验认可，为 ACCEPTED WITH KNOWN ISSUES；这不等于所有模块真实接入，也不等于 V1 完成。FE-4 记录总耗时约 80 分钟。
- NAS 传输历史存在 SCP/SFTP `subsystem request failed` 与 SSH `Operation not permitted`；本次授权执行环境中短超时 SSH 只读核验成功。治理更新阶段不更改传输服务/ACL/Compose/网络。

## 2026-10-11 Rebaseline Closeout

- 当前整体：SecondBrain V1 **NOT DONE**。FE-3 视觉建设完成，FE-4 正式前端已部署；用户接受 PC/Mac 与 iPhone 视觉并认可正式版整体体验，但正式接口覆盖 PARTIAL，Safari 功能回归、Universal Capture V1 附件链路、临时权限债等仍未关闭。
- 下一步顺序：正式版 iPhone Safari 功能回归 → Universal Capture MUST 附件链路与产品化 → 经授权补齐真实 API 语义/元数据 → 收口临时 unrestricted sudoers 与发布/传输债 → 用户重新排期后才恢复 FE-3.2 滚动性能量化及轻微视觉修整。
- 本次仅更新治理基线及同步副本；未重新部署 Dashboard、修改 API/业务数据/Compose/网络或重启 Hermes。

# 2026-10-12 UC-V1-Security-1C-2 HTTP Integration and Governance

- 在 `/tmp` Python 3.9 venv 安装 FastAPI 0.115.0 / httpx 0.27.2；生产 Hermes 依赖未修改。
- 对候选 `plugin_api.router` 实际注册的 `POST /api/plugins/secondbrain/review/approve` 执行 TestClient HTTP 测试：新增 6 项通过；与 Worker/审批适配器既有 16 项合计 22 项通过。覆盖有效会话、无会话、非法 Origin、Review SHA 不匹配、重复 request_id、审批后 Worker 隔离目录写入，以及 Agent 声明 approved 无可信记录时拒绝。
- 会话测试中间件模拟 Hermes 已验证的 `request.state.session` 契约；不代表在生产 Hermes 进程内验收。候选插件 manifest 的 `api: plugin_api.py` 与现有 GET 路由为已知集成形态。
- 队列文件按 0600 原子创建；这是文件模式测试，不足以证明运行中 Hermes 同用户的普通工具无法访问/伪造队列。当前无独立生产队列挂载及 Worker 权限证据，生产审批集成保持 BLOCKED。
- 治理新增 D063“个人自用、业务优先、风险适度与 Promote 隔离”；同步更新 Agent-Rules、Architecture、Decision-Log、00-CURRENT、Progress-Log。未改变 FE-4 视觉、生产服务、Compose、Mounts、Skill 或 Knowledge。
- **下一最小生产集成（另行批准后）：** (1) 普通 Hermes 移除 Knowledge RW 并收窄 write-safe；(2) 审批队列置于普通 Agent 文件工具不可达的独立挂载/权限边界；(3) Dashboard 仅写队列、独立 Worker 仅读队列并独占 Knowledge RW/审计目录；(4) 注册 POST 路由并复用登录 session；(5) 部署后以容器身份/挂载和端到端审计记录验收，再决定是否启用 Promote。

- **Journal 治理决策：** 新增 D064，确立随手记等内容可无审批新增/按日期追加、原文保留、不得无授权改写/删除、Journal 转 Knowledge 必须 Review+用户批准；生产 Journal 直接写入挂载仍未开放。
- **同步故障定位：** 上轮 tar 提示 locale 错误但五个候选文件实际已完整传到 NAS `/tmp`；治理哈希保持原值且无新恢复点。停止发生在 NAS 安全写入脚本的目标根校验：该脚本配置 Mac 工作副本路径，不接受 NAS 路径。后续使用脚本原定 Mac 工作副本作为安全写入入口，再核验 Synology Drive 的 NAS SoT 同步与 Google Drive Live Mirror。

# 2026-10-12 UC-V1-Security-1D Promote 集成准备

- 复用 Security-1B/1C Worker 与审批 HTTP 代码，新增 Review frontmatter 适配、正式插件 GET Review 列表与 POST 审批路由候选、独立文件队列 Worker Runner。Review `type/status/review_status` 按现有结构映射到 Knowledge，并保留用户内容及其他元数据。
- 准备 `production-plugin-route.patch` 与 `production-compose.patch`，均未应用到生产。Compose 目标是移除 Hermes Knowledge RW、收窄 `HERMES_WRITE_SAFE_ROOT`、由隔离 Worker 独占 Knowledge RW，并通过只读 Review/审批输入执行 Promote。普通 Hermes 的 Raw/Review 捕获能力保持。
- 隔离自动化测试 **26/26 PASS**；Python 编译、插件补丁应用一致性、Compose 补丁应用及 YAML 解析通过。Mac 无 Docker/Compose CLI，容器入口与实际运行仍未验证。
- 风险/阻塞：候选审批队列目录虽在 write-safe root 外，但仍对同一 Hermes 容器中的任意可用 shell/文件工具可见；尚无证据证明普通 Agent 无法伪造队列。正式生产切换 **BLOCKED**，需先验证工具边界或提供不暴露给普通 Agent 的队列写入路径，再安排隔离生产联调。回滚应停用路由/Worker并保留队列与 Review，不恢复 Hermes Knowledge RW。
- 本阶段无生产变更；治理同步按 NAS SoT → Mac 工作副本 → Google Drive Live Mirror 进行，并在完成后记录逐文件 SHA-256。

# 2026-10-12 SecondBrain DOC-REFORM-0

- NAS SoT inventory: 9 active Markdown files (rules, current snapshot, architecture, environment baseline, decision log, progress log, two business specifications, and frontend README). `_archive` history and `tools/.governance-recovery` snapshots were inventoried as recovery/history and excluded from active-doc counts.
- Created full pre-edit snapshot for all 9 active docs under `tools/.governance-recovery/20261012T-DOC-REFORM-0-full/`; snapshot hashes recorded before edits.
- Consolidated CURRENT into a state snapshot; reduced duplicated project history from operational docs; established FAST-EXEC and conditional read strategy in Agent-Rules. Architecture now distinguishes deployed Hermes Dashboard from the approved but unimplemented Hermes + SecondBrain Core modular monolith (D066, PLANNED). Environment facts now describe current runtime/mounts and rollback references rather than repeated milestone narratives.
- Preserved Decision-Log entries and legacy numbers while assigning unique aliases to duplicate D047–D049 citations. Marked D053 attachment scope historical/superseded by D049-UC-SCOPE.
- Resolved the explicit internal Universal Capture spec conflict: v1.1 Sections 2/13 now list Text, URL/Web, PDF, Image/Screenshot, and Audio/Voice as V1 MUST; Section 16 retains Office, video, generic binary and advanced semantic capabilities as deferred. No business scope was removed. Updated Web App spec status pointer to the current-state log.
- No code, production services, Compose, mounts, dashboard, Skill, knowledge data, Private, Journal data, network, ACL, or model changed. DOC-REFORM-0 is documentation-only; CORE-0 remains not started.


# 2026-10-12 SecondBrain CORE-0

- 清理 NAS 项目 `tools/.governance-recovery/` 内 52 个旧格式恢复点目录（144 个文件：Markdown 恢复副本及其 Synology `@eaDir` 附属流）；未发现代码、业务文件、符号链接或活动运行时引用。清理前验证独立 NAS 恢复目录两份新快照均完整覆盖 9 份活动 Markdown，manifest 与逐文件 SHA-256 均通过。旧目录通过 Synology Drive 双向同步从 Mac 镜像消失；未改同步任务。
- 在 `web-app/secondbrain-core/` 建立最小 Python 包及 Review/Promote 内部模块；复用原 Promote Worker 的 Review 映射、审批会话校验、内容摘要、防路径穿越/符号链接、拒绝覆盖、幂等与审计实现。Core Router 将审批记录持久化后在同一进程调用 Worker；不使用独立 Worker 容器或跨容器队列。原 26 项回归与新增 3 项 Core HTTP 用例共 **29/29 PASS**，均为临时目录测试。
- Dashboard/Core 可行性仍 **BLOCKED**：HTTP 测试模拟 Hermes `request.state.session`，尚未证明生产插件可取得该可信上下文；生产 Hermes 的 Knowledge RW 与普通 `write_file` 风险仍未收口，Core 文件权限边界未部署/验收。旧 Security-1D Compose/路由补丁已标为过时，不得用于部署。
- 无生产容器、Compose、Dashboard、Skill、挂载、网络、Knowledge 或业务数据变更。未产生新架构决策；继续遵循 D066。下一步 CORE-1：核实真实 Hermes 认证上下文及调用路径，提出并验证 Core 独占 Knowledge RW 的最小部署边界，再决定生产集成。


# 2026-10-12 SecondBrain CORE-1 身份接入与权限隔离核验

- 对照 Hermes v0.21.5 对应官方 tag `v2026.9.24`：Dashboard 插件路由契约为 `/api/plugins/<name>/`；宿主认证中间件验证会话后在插件请求设置 `request.state.session`；`/api/auth/me` 返回已验证身份。当前 Core Router 仍只适用于同进程可信 session，独立 Core 不可直接接收 Hermes 自报的身份字段。
- 推荐保持 FE-4 登录体验：浏览器只调用同源 Hermes 插件 API；插件转发原始 Cookie/Authorization 与 Origin；Core 通过内部请求向 Hermes `/api/auth/me` 回查身份，拒绝自报 `user_id`/session/header。保留精确 Origin、Review SHA、服务端审批与幂等。接口原型及认证调用链未实现、未端到端测试。
- 生产只读基线：`secondbrain-hermes` 为 running，配置身份 root；SecondBrain 根挂载 RO，但 `20-Knowledge` 当前有 RW 子挂载，`HERMES_WRITE_SAFE_ROOT` 仍包含写入根。普通 Agent 的文件工具与 Shell 可直接写 Knowledge。POSIX 目录 mode 为 0777；DSM ACL 工具不可用，ACL 细节未核实。
- 使用生产 Hermes 同版本镜像，对 NAS `/tmp` 合成目录启动两个 `--network none` 临时容器：root 在 SecondBrain RO 挂载写入被文件系统拒绝（PASS）；Core 风格 RW 挂载以 UID 1026/GID 100 写入合成文件成功（PASS）。测试不访问正式挂载或业务数据，不代表生产容器已隔离。无容器/Compose/权限改动。
- Core 源原先仅在 Codex 临时工作区。已核实 NAS 无 Git CLI，正式 Core 路径原先不存在；现将 Core 源码/测试、兼容 Promote Worker 源码/测试存入 NAS `web-app/secondbrain-core/` 与 `web-app/promote-worker/`。`CORE-0.bundle` Git bundle 可本地克隆恢复，bundle SHA-256 `fd068934ceeb6b4346cf1c5cf2e2a6e2a0381b750f37d631704cd3ea2a965244`；其包含 Core 与兼容测试基线。NAS 写入后已检测 Mac 镜像出现 Core 文件。
- 本轮未改动 Core 认证实现，故未重跑 FastAPI 测试；Mac 当前 Python 无 FastAPI，PyPI 访问因 DNS 不可用而无法安装依赖。对 19 个 Python 源码/测试文件的内存语法编译通过；此前 CORE-0 的 29/29 隔离测试结果沿用，不冒充本轮接口回归。
- 未产生新架构决策，继续遵循 D066。CORE-2 前置仍有：实现并隔离测试 Hermes 插件→Core 会话回查；准备 Hermes 移除 Knowledge RW、Core 独占必要 RW 的 Compose 候选；核实实际 DSM ACL；完成 NAS/Mac/Git bundle 的一致性校验。无生产变更。


# 2026-10-12 SecondBrain CORE-2 审批认证边界

- 只读核验确认生产 Hermes `secondbrain-hermes` 为 root；容器环境包含非空 Basic Auth password/username 字段，容器还有 SecondBrain RO、Raw/Review RW、独立 `20-Knowledge` RW 挂载。秘密值未读取。`synoacltool` 不可用；POSIX 元数据显示 Hermes data 目录 0700、NAS `.env` 0600，但 DSM ACL 和目标目录身份边界未验证。
- Hermes v0.21.5 (`v2026.9.24`) `/api/auth/me` 只返回中间件注入的已验证 session；v0.21.7 官方签名 RC `rc.12` 的 loopback 分支可返回 `user_id=local`、`provider=loopback`，Core 不将其视为人工授权。
- 新增 Core 独立解锁、Secure/HttpOnly/SameSite session、精确 Origin/CORS 与 HTTPS-only 保护；浏览器直接调用 Core。一次性无网络容器中 36/36 Promote/审批 HTTP 回归通过，覆盖无凭据、伪造身份字段、非法 Origin、HTTP 降级、重复审批、SHA 变化及正式 Worker 写入模拟目录。
- 准备 Core 单服务 Compose 候选：Review RO、Knowledge RW、Core-only secret/state；Hermes 后续须移除 Knowledge RW。NAS HTTPS 443/5001 有响应，但 DSM HTTPS 路由、证书、代理 peer、NAS 实际 ACL/Core UID 尚未验证。
- 无生产 Compose、容器、Dashboard、Knowledge 或服务变更。生产切换继续 BLOCKED；下一步限于测试目录 UID/ACL 与 DSM HTTPS 直达 Core 的联调准备。


# 2026-10-12 SecondBrain CORE-3 DSM HTTPS 与权限隔离联调准备

- 只读确认 DSM 现有 HTTPS/反代与通配符证书；当前没有 SecondBrain 反代入口，生产 Dashboard 仍 HTTP。真实 DSM proxy peer/头部链路与浏览器端 HTTPS 审批仍 BLOCKED。
- 在隔离目录复制实际 ACL 的 Core UID 对应 Joe 用户规则，Core UID 1026:100 的最小挂载读写通过；Hermes root 的 RO mount 写入被拒，且测试 Hermes 无 Core secret/state 挂载。临时目录和容器已清理；生产 Hermes/ACL/服务未改。
- Core Compose 候选收窄为 Review RO、Knowledge RW 与 Core-only state/secret；新增 exact Host allowlist 与代理头信任测试。完整相关回归 38/38 PASS，Compose YAML、Git diff 与 CORE-3 Git bundle 校验通过。NAS 源码与 Bundle SHA-256 已核验，Mac 镜像一致。
- 下一步须批准 LAN-only HTTPS Dashboard/Core 入口，确认实际代理 peer 并完成真实浏览器端到端测试；通过后再另行审批生产挂载切换。无生产部署或架构决策变更（继续 D066/D067）。


# 2026-10-12 SecondBrain CORE-4 DSM HTTPS 入口与受限联调收尾

- 通过 DSM UI 新增 LAN-only profile 与两条 HTTPS 规则：Dashboard `zxwan520.com:63012` → `192.168.3.27:9119`，Core 预留 `:63013` → `127.0.0.1:9120`；原 HTTP Dashboard 保留。复用现有证书，未改 Hermes、Compose、容器、Knowledge、DNS 或路由器。
- Mac 局部解析 curl 验证 TLS、Dashboard 302 和临时 Core 回显的 Origin/Cookie；非法 Origin 403、伪造 Host 404。观测 DSM 覆盖 Proto 为 https，但透传客户端可影响的 X-Forwarded-For/Host，Core 不得直接信任。临时服务 PID 32270 已核实并停止，三文件删除，9120 端口释放。
- DSM ACL 配置与两条规则绑定已核实；LAN 请求成功。NAS loopback 请求返回 302，不能代表非 LAN 来源验证。路由器未发现 63012/63013 DNAT；Edge 域名访问因本机解析/连接路径失败，真实浏览器 HTTPS 验证 **BLOCKED**。Core 未部署，`:63013` 当前 502；生产 Promote/挂载切换继续 BLOCKED。
- 正式部署同一 Compose Project 的既定决策记录为 D068。


# 2026-10-12 治理调整：敏捷开发与执行成本优先

- CORE 主线最近一次集成已将 Core service 加入现有 SecondBrain Compose Project，Dashboard 加法 bundle 已发布；Core 当前停止、健康检查未通过，Review/Approve→Knowledge 尚未完成，Hermes Knowledge RW 仍未收口。此前本阶段针对性本地测试 13/13 通过；未执行历史全量回归。
- 用户确立敏捷、功能、成本优先原则，按风险投入工程步骤；V1 业务可用优先于公网和商业化整理。本轮仅更新 Agent-Rules、00-CURRENT、Architecture、Environment-Baseline、Decision-Log（D069）和本 Progress-Log。
- 本次治理更新未修改生产服务、Compose、挂载、ACL、网络或 Knowledge；本轮治理任务未运行测试或部署。治理文档同步状态以本次交付报告为准。


# 2026-10-12 Dashboard Review 只读接入

- 正式 FE-4 插件发布只读 Review 视图与详情入口；Core 增加 owner-session 保护的详情/状态 API，并服务端保持 Promote=false。核实 DSM 代理 peer 172.18.0.1 后启用精确代理信任；Core 重新 healthy，Hermes ID 未变。锁定态 API 401、非法 Origin 403；用户仍需在已登录 Edge 刷新并解锁，确认完整真实列表/详情。未写 Knowledge。


# 2026-10-12 NAS-first Google Drive 文档发布路径收口

- 正式采用 NAS 为文件源的按需单向发布：发布脚本经 `secondbrain-nas` SSH 从 NAS 读取白名单 Markdown，写入当前 Mac Google Drive Desktop 已挂载的 `Project Doc/<项目目录>/`；仅更新变化文件，不删除云端内容。云端上传异步，本地复制成功不能冒充云端已确认。SecondBrain 当前正式目标为 `Project Doc/SecondBrain V1 Live/`。
- 方案演变（均为本项目当前未采用的替代方案，不表示技术上不可行）：Mac 本地镜像作源可能在 Synology Drive 尚未同步时发布旧版本；iMac 与 MBA 同时用原生文件夹同步管理同一项目可能产生重复目录、冲突、误删或覆盖；rclone 可行但增加安装、账号授权和维护成本；NAS Cloud Sync 经代理需验证代理兼容性/路由且 DSM 全局代理可能影响其他套件，不值得改动稳定全屋分流；每项目复制脚本易造成逻辑分叉和维护差异。
- 本次路径核验发现，指令预期的 NAS `_Shared/tools/publish-docs.sh` 与外置项目配置文件不存在；实际唯一脚本为 SecondBrain 项目 `tools/sync-chatgpt-live.sh`，SecondBrain 项目配置内嵌在脚本中，目标为新 `Project Doc` 路径。未据设计目标虚报共享脚本/独立配置已实现。
- 核对既有正式记录：D069 已确立敏捷优先；Progress 已保留 2026-10-10 FE-0/FE-0.9 及 Home API、2026-10-11 FE-4 发布与已知缺口；最新 Dashboard Review 记录 Core healthy、只读列表/详情已部署但仍待用户 Edge 解锁验收。生产 Promote 仍关闭，Hermes Knowledge RW 风险未收口；LAN-only HTTPS 已配置，公网访问延期。没有重复复制这些阶段历史。
- 本轮新增 D070，治理与架构文档记录发布方向。未改业务代码、容器、Compose、DSM 网络或知识数据。

# 2026-10-12 公共文档发布脚本迁移

- 将 SecondBrain 发布逻辑迁移至 NAS 公共脚本 `_Shared/tools/publish-docs.sh`，项目配置位于 `_Shared/config/secondbrain.conf`；原 `tools/sync-chatgpt-live.sh` 保留为兼容入口。公共脚本从 NAS SSH 读取八份白名单 Markdown，写入当前 Mac 已存在的 Google Drive `Project Doc/SecondBrain V1 Live/`，支持 dry-run、仅更新变化文件且不删除云端内容。首次 dry-run 检查通过；云端发布结果另以本次执行反馈为准。


# 2026-10-13 NAS 旧开发目录解耦与清理

- GitHub `main` 提交 `961c07d` 将 Dashboard 与审批候选 API 的 `/proof` 响应改为静态项目元数据，不再读取 NAS `30-Projects/SecondBrain V1/00-CURRENT.md`；删除已标记 superseded 的 Promote 部署补丁。Dashboard 页面静态资源未改。
- Core GitHub 源码部署到 `/volume1/docker/secondbrain/core-source/`；Compose build context 改用该目录，镜像更新为 `secondbrain-core:core4-github-961c07d`。旧 `secondbrain-core:core4` 镜像保留作回退。仅重建 Core；为加载 Dashboard API，只重启 Hermes。
- 清理 NAS `/volume1/SecBR/SecondBrain/30-Projects/SecondBrain V1/`（约 976 KiB）及其专属 `/volume1/SecBR/.governance-recovery/SecondBrain V1/` 文档快照（约 1.5 MiB）。保留父级 `30-Projects`、`_Shared`、其他知识/业务数据、KnowledgeAssets、Private、容器数据和插件/Skills。
- 验证：Compose 配置有效；Core `/health` 返回 `ok` 且容器为 `healthy`；Dashboard 返回认证跳转 302；插件与 policy 的 proof 契约在旧治理目录不存在时仍返回原字段。Promote 保持 `false`；Core 的 Review/Knowledge 挂载只读，Hermes 原有 `20-Knowledge` RW 挂载未变。
- 活动 Compose、运行脚本、Core 构建上下文、正式插件和 Skills 均无旧目录/治理脚本引用。Synology Drive 客户端仍指向 `/Users/joe/SecondBrain/` 且一个连接保持关联；NAS 套件报告 stopped，实时同步传播未确认。本轮未更改客户端配置或任务关系。


# 2026-10-13 GitHub 迁移后项目文档收口

- 正式开发与文档权威源为私有 GitHub `zxwan829/SecondBrain`；iMac 正式 Clone 位于 `/Users/joe/Documents/Codex/SecondBrain`，MBA 使用独立 Clone。NAS Docker 根为 `/volume1/docker/secondbrain/`，Core 构建上下文 `/volume1/docker/secondbrain/core-source/`；业务数据仍位于 `/volume1/SecBR/SecondBrain/` 与 `/volume1/SecBR/KnowledgeAssets/`。
- Obsidian 继续由 Synology Drive 在 Mac 与 NAS 间双向同步，但只承载知识、笔记和个人资料，不作为源码或正式开发文档来源。客户端显示已为最新；实际双向传播未单独验收，历史 `SynologyDrive stopped` 状态报告不等于已确认故障。
- ChatGPT 负责架构/任务/决策/验收标准，Codex 负责实施、测试、Git、授权部署与反馈。GitHub Push 不代表部署；授权部署由 Mac 经 SSH 传入 NAS，NAS 不需访问 GitHub。旧 NAS 开发目录、治理快照、Google Drive 文档镜像、旧发布流程及本地迁移备份已清理。
- 更正迁移过程记录：2026-10-12 “NAS-first Google Drive 文档发布路径收口”和“公共文档发布脚本迁移”仅描述当时路径核查/流程试行，后续均已由 GitHub 权威文档体系取代并退役，不是当前正式发布方式。保留历史作为迁移记录，不复活其操作指引。
- Codex workspace-write 沙箱下 GitHub 与 NAS 网络访问已验证；权限审批与生产变更授权边界继续有效。仅更新治理文档，未修改业务规格、代码、NAS、Docker 或 Synology Drive 配置。

# 2026-10-13 D071 Hermes Session 只读 Review 集成（源码，待部署）

- 新增 Dashboard 插件 Review 列表/详情只读 API；后端逐请求验证 Hermes 注入的 Basic Auth `request.state.session`、session 有效期、`auth_required` 与精确同源 Origin。客户端身份字段/请求头不构成授权。Review 文件读取拒绝路径穿越、符号链接和非普通文件。
- D071 Review 扩展通过同源插件 API 读取，不再请求 Core 解锁；列表与详情均受服务端验证。初版 `index-20261013-review.js` 使用了仓库中同名但已过时的 10,079-byte 页面壳作为基础，部署后造成 FE-4 视觉回归；已在下方记录并修复。
- 针对性用例 9/9 通过：有效会话列表/详情、缺失/过期会话、loopback/关闭认证模式、Origin/无 Origin 浏览器 GET 来源校验、路径穿越/符号链接。Promote 仍关闭；未触及 Knowledge、Private、Hermes 挂载、NAS、容器或家庭网络。源码实现和测试不代表生产部署；部署需用户另行批准。

## 2026-10-13 D071 最小生产部署

- 用户批准最小生产部署。运行容器核验为 Hermes v0.21.5 / upstream build `749220ef`、image ID 与基线一致；实际 middleware 在 `auth_required=true` 时逐请求验证 token/cookie，并将验证后的 Session 注入 `request.state.session`。Basic Auth provider 的名称、user_id 与 expires_at 字段与插件契约一致。
- 部署正式插件 `plugin_api.py`、manifest v0.2.2 与 `index-20261013-review.js`；不重建 FE-4、不部署 Core Promote 文件。部署前精确快照位于 `/volume1/docker/secondbrain/hermes/data/secondbrain-fe4-rollback/d071-20261013-01/`；备份 `plugin_api.py` SHA-256 `7baf751d4265118440d967475fec2ae90844f682360387ba03dfb239c978d6e0`，备份 manifest SHA-256 `173b069c7ff293a0b3e1c97bad2f7b6139fd42e23a4fe11cda6cc916f3243c1d`。FE-4 原有回滚快照仍保留。
- 部署后 HTTPS health 返回 200、Hermes 报告版本 v0.21.5/auth_required=true；无 Session 的 Review 列表/详情返回 401。插件测试 9/9 通过，含有会话时跨站 Origin 返回 403、目录穿越与符号链接拒绝；生产的有登录跨站拒绝及浏览器 GET/Origin 兼容性由用户 Edge 验收补齐。
- Core `SB_PROMOTE_ENABLED=false`，Knowledge mount 为 RO；Private 未挂载。未扩大写权限、修改家庭网络或重建容器。

## 2026-10-13 D071 FE-4 资源修复

- 根因：生产已验收 FE-4 `index-20261012-review-page.js` 为 78,453 bytes / SHA-256 `6cf72d312adac4c7f4b483f777618c6c040fa9a0f140c5d8f459758add5642fe`；初版 Review bundle 的 10,079-byte 前缀实际对应过时仓库文件，SHA-256 `5e651fb5b922a9fe8fe03d8d07ab1f7fc133e4e4fd0a138eeb40d0f14eefd478`。生产 FE-4 原 JS 与 CSS 未被覆盖。
- 新增 `index-20261013-fe4-review.js`：逐字节保留生产 FE-4 JS 前缀，再附加 D071 Review 代码；SHA-256 `10039c5ec25a2a23cff8fa94f844acc529aeef3cd603fa8297f6afe46b8f3b92`。发布检查固定 FE-4 前缀长度/哈希，并检查 Review 初始化 guard、DOM 挂点及 manifest 的 entry/CSS/API 引用。
- 更新 manifest 至 v0.2.3，指向新 bundle；CSS 与 `plugin_api.py` 未变。部署前保存当前 manifest 到 `/volume1/docker/secondbrain/hermes/data/secondbrain-fe4-rollback/d071-20261013-fe4fix-01/manifest.json`。如需恢复纯 FE-4 页面，切换到 `/volume1/docker/secondbrain/hermes/data/secondbrain-fe4-rollback/d071-20261013-01/manifest.json` 指向的既有 FE-4 bundle；只回退 manifest，当前 D071 `plugin_api.py` 保留。初版 D071 bundle 与旧 FE-4 bundle 均保留。
- Hermes 插件发现清单按进程缓存；匿名 rescan 返回 401，因此为加载 manifest 执行了必要的 `secondbrain-hermes` 单容器重启。重启后健康端点 200/v0.21.5；未认证 Review 列表与详情为 401。静态资源在无会话 HTTPS 请求下返回登录跳转，已登录 Edge 对新入口加载、视觉、Review 列表/详情的最终验收待用户完成。
- 针对性测试 12/12 通过（Review API 9 项、发布资源 3 项）；新 bundle `node --check` 通过。Core 仍 healthy、`SB_PROMOTE_ENABLED=false`、Knowledge RO、Private 未挂载。

## 2026-10-13 D071 FE-4 最小前端回滚

- 用户批准后，仅将正式 `/opt/data/plugins/secondbrain/dashboard/manifest.json` 恢复为现存快照 `secondbrain-fe4-rollback/d071-20261013-01/manifest.json` 的内容。正式入口现为 v0.2.1 `index-20261012-review-page.js`，CSS 为 `style-20261010-v3.css`；FE-4 JS SHA-256 `6cf72d312adac4c7f4b483f777618c6c040fa9a0f140c5d8f459758add5642fe`，CSS SHA-256 `9de0d0d52b2c7117ea16719d01bca616abdf57bd81548a7ba56d5007cce89990`。切换前 v0.2.3 manifest 另存于 `secondbrain-fe4-rollback/d071-20261013-fe4rollback-02/manifest-before.json`；所有版本化 bundle 均保留。
- `/api/dashboard/plugins/rescan` 未认证请求返回 401；按 Hermes 进程级插件清单缓存机制，仅重启 `secondbrain-hermes` 刷新缓存，未重建或重启其他容器。重启后 `/api/dashboard/plugins` 返回 v0.2.1 并指向 FE-4 资源；Hermes v0.21.5 health 返回 200。资源文件与 Hermes MIME 映射核验存在且完整；静态 URL 在无登录 Session 下被认证中间件重定向至登录页，因此不能宣称已从外部 GET 验证 JS/CSS 返回体或浏览器实际渲染。
- D071 `plugin_api.py` 保持不变（SHA-256 `e648afa1a53a2b6c0fd601344bdddfee1e3ade0b1ed97d614ca0692561ec73d3`）。Core 继续运行，`SB_PROMOTE_ENABLED=false`、Knowledge mount 为 RO、Private 未挂载。用户 Edge 对 FE-4 页面恢复的验收待完成；D071 前端 Review 列表/详情集成暂缓。未改家庭网络或其他服务。

## 2026-10-13 D071 Loading P0 根因与隔离修复

- 根因已确认：旧 D071 扩展以 `MutationObserver(attach)` 观察整个 `documentElement` 的 `childList/subtree`；FE-4 实际存在 `#waiting .module-title`，`attach()` 每次均对 Review 按钮执行 `textContent =`。替换文本节点会再次生成 childList mutation，形成无界 observer 回调并可饿死主线程。服务器回滚 manifest 不会卸载已经在卡死 Edge 标签执行的脚本，故回滚后同一标签仍可能保持无响应。
- Hermes v0.21.5 Dashboard loader 还将插件清单缓存于 `sessionStorage`（`hermes:plugin-manifests`），并以该缓存初始化 manifest 列表；旧标签/缓存可能继续请求旧入口。原用户 Edge 标签因浏览器控制通道超时，无法直接读取它的 console/sessionStorage；这部分是与已观测现象相符的解释，不作为原标签本地缓存值的直接证明。
- 真实浏览器证据：独立 Edge 标签经 NAS LAN HTTP `/secondbrain` 实际加载 `index-20261012-review-page.js` 与 `style-20261010-v3.css`，完整 FE-4/Home 数据渲染、无 Loading，console error/warn 为空。`/secondbrain-fe-test` 也成功渲染；`sb_debug=layout` 显示 immersive init/success 各 1 次、首次页面更新期间 layout measurement 3 次，后续 1.5 秒稳定。FE-4 自身 observer 限定在 Hermes `#root` childList；其 apply 修改属性与 trace，不写 childList，因此未形成递归循环。
- 修复源码 `dashboard/review-addon.js`：按钮文字仅在变化时更新；观察范围限定为插件 root；Review 控件挂载后断开 observer，并在 pagehide 清理。`package-test-plugin.mjs` 现从该源码生成隔离测试插件 JS。新增可重复的候选打包脚本，校验 FE-4 固定前缀 78,453 bytes / SHA-256 `6cf72d312adac4c7f4b483f777618c6c040fa9a0f140c5d8f459758add5642fe`，生成候选 `index-20261014-fe4-review.js`；其 SHA-256 为 `acd77192393c4ea74a3b55cde61c596bfb0257510b20df91c8073bd1a761fcb4`。仓库候选 manifest 为 v0.2.4；正式 NAS 仍为 v0.2.1，未部署候选。
- 隔离测试插件资源更新成功；本机与 NAS 的测试 JS SHA-256 均为 `4300d65cf33cd1dc3e7e112b7230767c413dcb57e066d00e4c97873504582a1e`，CSS SHA-256 均为 `8db124f950e13cb3b9dc5c2cc377f79ad1df8434934dbe1247bfa35714a94bb2`。浏览器实际加载 FE test JS/CSS，Review 按钮成功挂载且无页面卡死。隔离 UI 在 LAN HTTP 点击 Review 得到 `Same-origin request required`；该拒绝符合只允许正式 HTTPS Origin 的策略。DSM HTTPS 63012 从本自动化浏览器连接被拒，未改网络；Review 有效 Session 列表/详情及未认证/跨站/路径保护由针对性 API 测试覆盖。
- 测试：Dashboard Python 资源/API 用例 13/13；前端 typecheck、候选包生成、manifest 校验、bundle 执行/React 注册/observer root 范围、FE-2.5 适配与视觉合同检查均通过。Promote=false、Knowledge RO、Private 未挂载；Core healthy。正式 manifest、D071 API、Core 和网络配置未改；原 Core Promote 未提交修改及 `typescript` 文件保持未触碰。

## 2026-10-13 D071 v0.2.4 受控生产部署

- 用户批准后仅部署版本化 JS `index-20261014-fe4-review.js` 与正式 manifest v0.2.4。部署前核对 FE-4 固定前缀 78,453 bytes / SHA-256 `6cf72d312adac4c7f4b483f777618c6c040fa9a0f140c5d8f459758add5642fe`、旧 FE-4 JS/CSS 与 D071 API 哈希均与基线一致；新 bundle SHA-256 `acd77192393c4ea74a3b55cde61c596bfb0257510b20df91c8073bd1a761fcb4`，manifest SHA-256 `aed54f754d447b1812583c4659966be9f66521897a03ba6895a87e53d0ff39fb`。CSS、`plugin_api.py`、Core 与其他服务未改。
- 部署前 v0.2.1 manifest 已保存在 `/volume1/docker/secondbrain/hermes/data/secondbrain-fe4-rollback/d071-20261013-pre-v024/manifest.json`，SHA-256 `173b069c7ff293a0b3e1c97bad2f7b6139fd42e23a4fe11cda6cc916f3243c1d`；原 `d071-20261013-01` 快照及所有旧 bundle 继续保留。回滚只需切回该 manifest 并刷新 Hermes 插件清单。
- 插件清单 API 返回 v0.2.4 与新 entry；健康端点 200。rescan 因需认证未成功，故只重启 `secondbrain-hermes` 一次；Hermes v0.21.5、Core 均 running。匿名 Review API 401 为预期拒绝。重启后 `SB_PROMOTE_ENABLED=false`、Knowledge RO、Private 未挂载。没有修改 NAS 网络或其他服务。
- 针对性验证：候选 JS `node --check` 通过；Review/API 与资源测试 13/13 通过，覆盖认证 Session、跨站拒绝、浏览器 GET/Origin、路径穿越/符号链接及 FE-4 bundle 固定前缀。一次额外 `test_proof` 导入因本机缺少 FastAPI 依赖无法运行，不属于本次 JS/manifest 部署门禁；候选 bundle 先前隔离 `secondbrain-fe-test` 实际渲染通过。用户已完成 FE-4 首页验收；v0.2.4 正式 HTTPS 资源加载及 Review 列表/详情仍待用户在全新 Edge 标签验收，不将隔离/单元测试视作生产 UI 验收。
- 原未提交 Core Promote 文件和未跟踪 `typescript` 保持未触碰；本次仅更新必要项目状态文档并随部署记录提交推送。

## 2026-10-13 D071 只读阶段用户验收与收口

- 用户通过正式 HTTPS Edge 完成 v0.2.4 真实验收：FE-4 完整视觉正常，无 Loading/页面无响应；Dashboard 登录后无需 Core 二次解锁；Review 列表显示 8 条真实待审核内容，详情正文可正常读取。
- Promote 保持关闭；页面没有审批按钮，没有写入正式 Knowledge。D071 的只读 Session Review 阶段标记为已部署、已完成用户验收。
- 下一阶段为 Review→Promote 审批闭环：优先检查并复用现有 Core Promote 代码，先处理 Hermes Knowledge RW 安全债，再实现用户批准入库。生产写入仍须在安全边界收口后另行验证和授权；本次未修改代码、NAS、容器或业务数据。

# 2026-10-13 Review → Promote 阶段 A 本地实现

- Core 审批状态按 Review 相对路径与 SHA-256 版本持久化，支持 pending、deferred、approved、promoting、promoted、failed；Review 变更后自动呈现为新版本 pending。新增 Core 会话保护的暂缓接口和状态回读。
- 入库仍使用现有不可覆盖原子创建。审批记录先持久化；失败标记可见，同一 request_id 可重试。目标已创建但审计失败时，重试核对目标哈希并补审计；审计日志仅尾部未完成行会在锁内修复，完整损坏记录仍 fail-closed。Review 原件不移动、不删除。
- 移除旧 Hermes Session 直接写入 Router/Service 路径，避免被误挂载绕过 Core 独立授权。Core 仍使用 Core 自有短时会话；消除第二次解锁需要后续设计可验证的一次性用户确认凭据，普通 Agent 不得能签发。Dashboard 页面仍只读，FE-4 未改；保留原本地 `referrerPolicy: same-origin` 差异。
- 生产权限候选要求移除 Hermes `20-Knowledge` RW 子挂载，将 Hermes 写安全根收窄为 Inbox、Review、KnowledgeAssets Inbox 三个精确目录，并保留 `/secondbrain` RO 根挂载；Core UID 1026:100 独占 Knowledge 与私有审批/审计状态 RW。候选 Compose 明确 `SB_PROMOTE_ENABLED=false`。无生产配置或 NAS 改动。
- 离线验证：Core 审批/认证与 HTTP 测试 15 项通过（使用 `/private/tmp` 隔离依赖）；覆盖审计写失败重试、审计尾部中断恢复、版本化暂缓、身份伪造拒绝、Origin/HTTPS 与重复提交。生产部署及用户验收未执行。

## 2026-10-13 Review → Promote 阶段 B 只读权限核验与授权方案

- GitHub `main`、本地 `HEAD` 均为阶段 A 提交 `2144f23`；工作区只保留未跟踪 `typescript`，本轮未碰该文件。`00-CURRENT.md` 原 NOW 项仍停留在“先检查并实现”，据此更新为阶段 A 已实现/测试、未部署，阶段 B 权限切换受阻。
- NAS SSH 只读成功，账户 Joe `1026:100`（administrators 组）。当前生产 Compose 声明 Hermes `HERMES_WRITE_SAFE_ROOT=/secondbrain-write:/knowledge-assets/00-Inbox`，Inbox/Review/Knowledge/KnowledgeAssets Inbox mounts 均 RW；Core `user 1026:100`、根文件系统 RO、Review/Knowledge RO、state RW、secret RO、Promote false。无生产 Compose/容器/服务修改。
- NAS `/var/run/docker.sock` 为 `root:root 0660`，SSH 用户读写均拒绝；Docker ps/inspect/exec 返回 socket permission denied。本轮未 sudo，故实际运行容器 mounts、有效 UID/env 与 Core 容器内 Knowledge 写权限未核实。
- NAS 主机 `stat` 显示 SecondBrain 根、Inbox、Review、Knowledge POSIX mode `0777`、owner `1026:100`；synoacltool 显示 Review/Knowledge ACL 允许 Joe 与 administrators RWX，无 Everyone ACE。SSH 用户主机级对 Review/Knowledge 可读可写。Core state 为 `1026:100`、mode `0700`。主机访问证据不替代 Docker mount 限制或 Hermes 普通文件工具测试。
- D072 选择保留 Core 独立短时授权：Dashboard 的 Hermes Session 只用于 Review 读取；明确用户点击后浏览器直连 Core，Core Cookie/secret、精确 HTTPS Origin、摘要绑定和服务端固定 owner 主体负责批准。Hermes 与 Agent Runtime 共享执行边界，故 Session 不足以证明用户动作；在无新增可信人类确认因子的条件下，无法同时免第二次口令并排除 Agent 伪造，维持现有 Core 解锁是最小替代方案。
- 最小候选差异和回滚见 Environment-Baseline 的阶段 B 条目。部署门禁：取得受控只读运行容器证据；验证 Hermes v0.21.5 对三个精确写根的解析及写入拒绝；确认 Core 1026:100 对 Knowledge/state 可写、Review 只读、secret 只读、Private 未挂载；之后独立批准生产 Compose 切换及 HTTPS Dashboard 浏览器验收。当前未部署、未启用 Promote、未用户验收。

# 2026-10-13 Hermes Knowledge 权限收窄生产部署

- 按用户授权，仅修改生产 Compose 中 Hermes 的两项设置：删除 `20-Knowledge` RW 子挂载；将 `HERMES_WRITE_SAFE_ROOT` 精确收窄至 Inbox、Review、KnowledgeAssets Inbox。部署前快照保存在 `/volume1/docker/secondbrain/rollback/hermes-knowledge-ro-20261013-221912/`，包含 Compose、受限 `.env`、Hermes/Core inspect 元数据和运行时摘要；目录/文件权限分别为 `0700/0600 root:root`，内容比较及 SHA-256 校验通过。秘密未输出、未入 Git。
- Hermes v0.21.5 多路径解析经实际源码函数验证；Compose 校验通过。只重建 Hermes，使用 `--pull never`；未改 Core、PBR、网络或其他容器，镜像 ID 未变。运行时 Knowledge 仅 RO 根挂载；safe-root 准确，三个捕获路径 RW。普通文件工具两类写入均在后端执行前拒绝 Knowledge；terminal 写探针返回 `Read-only file system` 且无探针文件。
- Core 保持 healthy，身份 `1026:100`，Knowledge/Review RO、state RW、secret RO、`SB_PROMOTE_ENABLED=false`；Private 未挂载。未启用或部署 Promote。
- 回归：Daily Capture 成功；Universal Capture Raw 与 Review 成功；Dashboard Review 列表由 8→9、测试详情/正文可读；仅清理三个专用测试样本，原列表恢复 8。浏览器中 Dashboard 页面正常，但原生 Chat 两标签持续“Reconnecting”；Health 200、Gateway Running，当前未定位。未重启 Gateway 或改网络，需单独跟进。权限收窄和 Review/Capture 回归通过，不代表 Chat 或整体 V1 用户验收。
- 回滚快照保留。若恢复配置，必须过滤掉 Knowledge RW 子挂载并维持三个精确写根；不得以放回 Hermes Knowledge RW 作为恢复方案。若捕获功能无法在该安全边界内恢复则停止并升级处理。

## 2026-10-14 D074 架构与业务基线收口（文档阶段）

- 已决定独立 SecondBrain Web App（自有 Chat）+ App/Core/BFF + Hermes 两个核心容器，标准版 LAN-first，本人 V1/V2 同一后端、V1 需完成 DSM LAN-only HTTPS 全业务回归。
- 正式 Web App V1 的 MUST/SHOULD/DEFERRED、Universal Capture v1.1 全部输入（含微信）与既有业务权限/同步规则未删减；先验证 Hermes API 再进行架构迁移。
- 本次仅修改 GitHub 文档，不代表源码开发、环境验证、生产部署或用户功能验收完成。

## 2026-10-14 D074 独立 App 首阶段本地实施

- 将 `secondbrain-frontend` 改为独立 React/Vite 启动入口，移除 App bundle 对 Hermes Dashboard Plugin SDK/宿主注册的依赖；保留 FE-4 页面、样式和视觉资源，Home 中原有 DEMO 内容继续明确标识为示意。
- 在现有 Core 应用进程增加 App 静态托管及同源 API/BFF：App 登录会话覆盖 Home、Chat、Review；Home/Review 从配置目录读取真实文件和服务端审核状态；Hermes Sessions、历史、创建/分叉、更新/删除、Run、SSE、停止由服务端代理，浏览器不接触 Hermes API Key。Review 暂缓和显式确认批准复用已有 Core Promote，批准受 Core 状态门控；`SB_PROMOTE_ENABLED` 缺省关闭。
- 新增单镜像候选 `web-app/Dockerfile.app`，将前端构建产物嵌入 Core/App；新增环境模板与本地开发说明。没有创建第二数据库、Runtime 或网关。
- 验证：前端 `npm run typecheck` 和生产构建通过；Core 全测试 **19 项通过**，覆盖 App 会话/Origin、无会话与伪造批准拒绝、Promote 默认关闭、真实 Review/Knowledge 文件、暂缓状态、服务端 Hermes 凭据、Chat Sessions/Run/SSE/停止及 SPA 静态回退。`git diff --check` 通过。测试只用本地临时目录与 Mock Hermes；未执行容器构建，未证明部署 Hermes v0.21.5 的线上 API 兼容。
- **阶段状态：本地代码已实现、离线测试通过；未部署、未做真实 Hermes 运行联调、未做 LAN/DSM 浏览器用户验收。** 生产仍使用 Hermes Dashboard Plugin；没有改 Compose/NAS/容器/权限/网络，Core Knowledge 保持 RO，Promote 关闭。完整 Web App V1（Today、Capture、Journal、Projects、Brief、Activity、多输入渠道及跨端回归等）未完成，不标记 DONE。

## 2026-10-14 D074 第二轮 Hermes API 与代理兼容

- `HermesAPI` 适配器按生产 Hermes v0.21.5 固定上游 `749220ef` 统一 Sessions/Messages `data` 数组、create/fork `session.id`、SSE JSON `event` 及文本/工具/终态字段；新增 `GET /api/chat/runs/{id}`，Chat 断流、页面恢复和 Stop 后轮询 Run 状态并从 session history 对账。失败、取消、中断会显示结果，不把断线误报成完成。
- App HTTPS 依赖仅信任明确的 `SB_TRUSTED_PROXY_IPS` 地址字面值；已知 DSM peer 为 `172.18.0.1`，拒绝通配符/CIDR。App 设置响应 Cookie Secure 由 ASGI 可信代理 scheme 驱动，精确 Origin/Host 检查保留。候选 App UID/GID 与 NAS Core 数据/secret owner 一致为 `1026:100`；BFF 上游地址改为 Compose service DNS `hermes:8642`。
- 按 D074 Personal OS 补充，导航项现在带可选 route 配置，现有 Home/Chat/Review 保持原页面；未注册具体渲染器的已配置路由会显示通用未接入状态，不会误落到 Chat。Core API 统一经 `require_action(action)` seam；V1 仍是单一 owner 校验，没有新增 RBAC。Knowledge Promote 与未来普通业务 CRUD 在权限语义上分离；调度目标保留为复用 Hermes 原生 scheduler。
- NAS 只读 SSH：Hermes v0.21.5/build `749220ef`，`127.0.0.1:8642` 有监听且 loopback `/health` 为 200；未认证 `/api/sessions` 和 `/v1/capabilities` 返回 401。当前正式 Compose 有 `hermes` service、`secondbrain_default` 网络，无 8642 宿主映射；API loopback 绑定不能供 App 容器调用，且没有 App 可用的服务端 API key。未执行带凭据请求，也没有修改生产 Compose、容器、密钥或服务。
- 验证：前端 `npm run typecheck`、`npm run build` 通过；Core `uv run --extra test pytest -q` **21 passed**，覆盖 pinned DTO、Run SSE/失败/中断、状态查询、服务端 API key、HTTP/HTTPS Cookie、精确代理 peer、未授权/跨站、Promote fail-closed。测试使用 Mock 上游和临时数据；不代表 NAS 真实 Chat 联调或 DSM 浏览器验收。`Dockerfile.app` 未在本机 Docker 构建。
- **状态：本地开发完成并测试；未部署。** 真实 Hermes 联调的阻断是 API 当前只在容器 loopback 监听且 App 服务端授权未配置。下一步需用户单独授权只修改 Hermes 的最小内部 API bind/key 配置并验证 Docker 内部网络访问；不加宿主端口、不改 Hermes 版本/Knowledge 权限、不启动 Promote。LAN HTTP/DSM HTTPS 浏览器验收和 App 部署另行授权。

## 2026-10-14 D074 NAS 部分部署与 Container Manager 阻断

- 基于 `e58a7f4` 部署，未纳入未跟踪 `typescript`。预部署快照 `/volume1/docker/secondbrain/rollback/d074-deploy-preflight-20261014-154943/` 权限 `0700/0600 root:root`，Compose、必要环境配置、脱敏 inspect、镜像清单完整性校验通过；App/Hermes secret 经受限文件注入，秘密未输出。
- 构建 `secondbrain-app:d074-e58a7f4-20261014` 成功。固定 Hermes v0.21.5 digest 不变。目标 Compose services 仅 `hermes`、`secondbrain-app`，`docker compose config --quiet` 通过；App UID/GID 1026:100、healthy、127.0.0.1:9120；Hermes running、192.168.3.27:9119，8642 未发布。App Review/Knowledge mounts RO、Private 缺席、Promote=false。Core 旧容器已停止并移除，旧镜像及 state 目录保留。
- DSM Container Manager GUI 流程已创建 `secondbrain` 项目，目录 `/volume1/docker/secondbrain`，首次创建时取消自动启动。GUI 列表能看到该项目；详情虽显示两条，但 Hermes 仍显示 GUI 缓存旧名/旧镜像，未达到“GUI 准确管理目标 Compose”的验收。编辑保存误触发 DSM 缓存旧 Compose，启动了旧 Core 并使 App 端口冲突；立即停止/移除 Core 并按目标 Compose 恢复 App。未改持久化业务数据或秘密。之后停止进一步 DSM 项目级操作，避免再次按旧配置重建。
- Hermes API 从 App 内网访问成功；真实 Chat 多轮、Session/history、SSE delta 与 tool started/completed、run complete、重连状态查询、Stop→cancelled 已验证。DSM HTTPS 登录/API 登录态、Secure Cookie、Home/Review 读取均 200；静态资源 200/MIME 正确，但 Edge 空白页未解释。HTTPS SSE 返回 200 后约 60 秒无事件 body，未验收。需取得浏览器 Console/network 证据并核对 DSM SSE buffering。
- 离线验收复跑：前端 `npm run typecheck`、`npm run build` 通过；Core `UV_CACHE_DIR=/tmp/secondbrain-uv-cache uv run --extra test pytest -q` **21 passed**（1 个依赖弃用警告）；`git diff --check` 通过。NAS Compose 校验通过，App health healthy。Hermes `/proc/net/route` 默认网关为 `172.18.0.1`；未更改 PBR/WireGuard，逐流经 wg0 仍未单独验证。
- **结论：生产部分部署，未完成 DSM GUI/浏览器验收；不标记 D074 部署完成。** 9119/63012 保持原入口，Promote=false、Knowledge RO、Private 不挂载。快照路径见 Environment-Baseline。下一步先通过受支持 Container Manager 流程对齐项目缓存，再排查 Edge JS 与 HTTPS SSE；不执行项目级重建直到 Compose 对齐。

## 2026-10-14 D074 P0 React classic JSX 修复

- `secondbrain-frontend/src/main.tsx` 增加 React import，修复 production classic JSX transform 下的 `React is not defined`；`App.tsx` 已有 import，未发现其他 JSX 入口同类问题。没有改 FE-4 视觉或扩展架构。
- 本机和 NAS 构建均通过 `npm run typecheck`、`npm run build`；产物 bundle 不含旧错误文本或 `React.createElement` 未绑定引用。NAS 镜像 `secondbrain-app:d074-e58a7f4-reactfix-738f392` 构建成功；只重建 `secondbrain-app`，容器 healthy，Hermes 保持原容器/镜像/运行状态。9120/63013 保持，未执行 Container Manager GUI 操作。
- HTTPS 63013 HTML/JS 返回 200 且 JS MIME 正确；浏览器登录页实际可见，Console error/warn 为 0。HTTPS 登录、Secure/HttpOnly/SameSite=Strict Cookie、session、Home/Review 真数据、Hermes Chat capabilities/sessions 均返回成功。Home 登录后视觉仍待用户浏览器验收。
- 真实 HTTPS SSE 收到 `message.delta`、`reasoning.available`、`run.completed`，run 状态 completed；前一轮“无事件”结论由探针仅统计单独 `event:` 头造成，Hermes/BFF 使用 `data:` JSON frame。烟雾测试创建的两条 Chat session/run 保留；无 Knowledge/业务文件变更。
- 热修复前回滚快照 `/volume1/docker/secondbrain/rollback/d074-reactfix-738f392-20261014/`，保留旧 App image ID 与 Compose。当前 Compose 仅 App build context/image tag 改动；权限、网络、Secret 未变，Promote=false、Knowledge RO、Private 不挂载。
- **状态：P0 代码已实现；App 热修复已部署；构建/在线 API/SSE 验证通过；DSM GUI 缓存定义和登录后 Home/Review/Chat 浏览器验收未完成。**

## 2026-10-14 D074 App 登录失败状态与凭据诊断

- NAS App access log 中 09:49Z 三次用户登录失败为 HTTP 401；无 429/500。此前 403 来自未带 Origin 的诊断探针，带精确 HTTPS Origin 的探针返回 200。最近重新创建 App 后限流计数已清零。
- App Secret 文件只读挂载、mode/owner 正确，启动时读入值以该 Secret 做 HTTPS 登录成功，排除 App 进程未加载或 Cookie/Origin 故障。NAS 内存中比较发现 App Secret 48 bytes、Hermes Dashboard Basic Auth 9 bytes，值不同；App 代码要求至少 12 bytes。因此当前 401 是 App Secret 未与用户确认的旧 Hermes 凭据对齐，而非假设用户输入错误。没有查看或记录任何明文。
- 修复前端错误文案：401 凭据校验、403 来源校验、429 限流、5xx 服务端异常分开显示。前端 typecheck/build、NAS 镜像 build 通过。只部署 `secondbrain-app:d074-e58a7f4-auth-status-ba2f040`，容器 healthy；Hermes 未重建。HTTPS 登录页仍可见，App Secret 登录和 Home API 200，Home 返回真实 Review 与 Agent 状态。
- **阻断：** 直接将 9-byte Hermes 凭据同步为 App Secret 会违反 App 现有 12-byte 最低长度要求。本轮没有降低认证门槛或更改凭据；需决定是否批准此最小安全例外，之后才能让同一旧凭据登录并完成浏览器 Home UI 验收。回滚快照见 Environment-Baseline。未跟踪 `typescript` 保留。

## 2026-10-14 D074 独立 App 密码轮换与浏览器读取

- 用户明确决定 App 与 Hermes 使用不同密码，保持 App 现有 12-byte 最低要求。Mac Terminal 隐藏输入后仅更新 App Secret 并重启 `secondbrain-app`；Secret 为 `1026:100/0600`、容器内 RO，与 Hermes Basic Auth 不同。受限回滚快照见 Environment-Baseline；无明文入 Git/聊天。
- 63013 HTTPS 登录与 Session、Home、Review、Promote 状态接口均返回 200；Cookie `Secure/HttpOnly/SameSite=Strict` 验证通过。浏览器实际显示登录后 Home 与 8 条真实 Review 列表/详情，批准按钮因 Promote 关闭而禁用。App healthy；Hermes 未重建，Knowledge RO、Private 未挂载、Capture 写边界和 `SB_PROMOTE_ENABLED=false` 保持。
- **状态：App 独立密码与 Home/Review 浏览器运行核验完成；Chat 浏览器交互、DSM GUI 项目旧缓存和用户最终验收仍待完成。** 未修改业务数据、Compose、DSM 或网络；未跟踪 `typescript` 保留。
- 后续在同一 63013 浏览器打开内置 Chat：现有 Session 与历史加载，向既有 D074 smoke Session 发送一条无工具测试消息，页面收到 SSE 回复并完成；刷新后消息保留。浏览器 Stop/工具进度未重测，DSM GUI 旧缓存与用户最终验收仍待处理。

## 2026-10-14 D074 Chat 浏览器与 Container Manager 项目核验收口

- 63013 Chat 浏览器用例：Knowledge 精确词 `search_files` 成功，前端显示工具执行事件、结果和完成状态；`read_file` 对临时不存在的 Knowledge 路径返回 `File not found`，前端显示错误详情及 Run 终态。长序列只读任务由前端 Stop 中断，状态从“正在停止…”到“已停止”；随后无工具对话正常回复。刷新页面、切换到先前 smoke Session 再切回后，测试消息、工具结果和取消提示均从持久化历史恢复。没有写 Knowledge、Capture 或生产配置，仅新增测试 Session/messages/runs。
- NAS 只读运行时核验：当前正式 `compose.yaml` SHA-256 为 `14ebd79e5571d42411652c0eabd40a65ae4da7301c4f5bc6f8f5c183197296f0`；`secondbrain-hermes`、`secondbrain-app` 均运行，Docker labels 的 project/service/config/working directory 正确匹配 `secondbrain`、目标两个 service 和正式 Compose 路径。Hermes 镜像 digest、App 镜像与此前配置一致；本轮没有改任何生产服务。
- DSM GUI 项目 `secondbrain` 刷新后仍显示 Hermes 旧容器名 `8fad22e58156_secondbrain-hermes` 及 `nousresearch/hermes-agent:latest`，App 镜像行是当前版本。Synology 官方说明 Project YAML 编辑会部署新设置；历史已出现 GUI 编辑启动旧 Core 并造成端口冲突。因此本轮未保存 YAML、未执行项目级 Build/Start/Stop/Restart/Clean，也未触碰 DSM 内部数据。没有可验证的安全 GUI 定义对齐方式，项目 GUI 管理验收仍阻断。
- 当前运行时安全边界保持：Hermes 固定 v0.21.5；Knowledge 只读，Private 未挂载；App Promote=false、Knowledge RO；App 仅 127.0.0.1:9120 发布，Hermes 8642 无宿主映射；9119/63012、反向代理、网络分流未变。
- **状态：** Chat 浏览器测试完成；生产部署保持部分完成。DSM Container Manager 保存项目定义不同步是本轮部署收口阻断；用户最终验收仍待完成。项目 Compose SHA 已在 Environment-Baseline 更新；未跟踪 `typescript` 保留。

## 2026-10-14 D075 Universal Capture Web 入口与多类型本地开发

- 在现有 Core 增加 App-authenticated Capture API、Inbox 列表/状态/Raw 读取、失败重试和私有持久状态；Raw 独占创建防覆盖，文件路径/签名/大小校验，任务中断后保留原件并可恢复。Review 复用既有 schema，实际文件/hash 验证后才标完成；只使用专用 Raw/Review root，没有 Knowledge 写路径。
- FE-4 Home Quick Capture 改为可提交的文本、Markdown、URL、文件入口；Inbox 导航成为真实 Core API 页面，显示来源、类型、时间、状态、内容预览及原件链接，允许重试 partial 状态。视觉资产和布局未重设计。
- Core URL fetch 对 DNS 解析结果做公网地址校验，按通过校验的 IP 直连，并逐跳重验重定向；抓取 HTML/text 与提取正文。PDF 使用 pypdf 提取可读正文，保留 PDF Raw。图片、音频保留原始文件；当前 App/Core 没有已配置可验证的图像理解/转写服务，返回 `processor_unavailable` 与 partial 状态，不伪造 Review。
- 验证：Core `pytest -q web-app/secondbrain-core/tests` **34 passed**（含登录/未授权、Raw/Review API、URL 私网/重定向防护、PDF 成功/失败、图片/音频明确部分成功、同名防覆盖、重试/中断恢复、无 Knowledge 写入）；前端 `npm run typecheck`、`npm run build` 通过；`git diff --check` 通过。HTTP URL 集成夹具仅连接本机回环测试服务器，不访问生产或外站；浏览器视觉/移动端验收尚未执行。
- 同源本地浏览器 smoke：使用临时本机状态与测试账号登录 App，Home 读取成功，提交文本显示完成；Inbox 展示真实 capture 与 Raw 入口，Review 列表/详情读取到新候选。临时状态已清理；没有连接 NAS/生产 Hermes。没有进行视觉基线对比或移动端验收。
- 生产未修改。候选最小 App RW 权限：KnowledgeAssets `00-Inbox` 专用 mount 新增 RW；现有 App Review mount 从 RO 改 RW；Knowledge 仍 RO，Private 不挂载，Promote=false。生产目录 ACL/UID 写权限及此 Compose 变更需另行授权后再验证。微信渠道仍属 V1 MUST，未从矩阵删除，后续复用同一 Capture API/流程接入。
- 用户确认 FE-4 视觉约 90% 符合预期，本阶段冻结视觉、不重新设计。DSM Container Manager GUI 项目定义缓存单独跟踪，不阻塞 D075 业务开发。

## 2026-10-14 D075 NAS 测试部署与真实采集联调

- 按用户授权仅更新/重建正式 Compose 的 `secondbrain-app`，部署 GitHub `d53cfa3`；NAS 镜像 `secondbrain-app:d075-d53cfa3`、App healthy，Hermes 容器/image/start 时间完全未变。Compose SHA、受限部署前快照、App-only 回滚步骤、挂载和 ACL 证据见 Environment-Baseline。
- App Raw `00-Inbox`、Review 挂载 RW；Knowledge RO、Private 不挂载、state 使用原 `core-state`、`SB_PROMOTE_ENABLED=false`。UID/GID `1026:100`；未递归改 owner/mode/ACL，未给 SecondBrain 根目录 RW。Hermes、9119/63012、PBR/WireGuard、DSM 反代和 Container Manager GUI 均未触碰。
- 经 TLS 校验的 63013 请求完成 App 登录与 Cookie 安全属性核验；Home、Chat capabilities/session、Review list/detail、Inbox 及 Promote 状态均通过，未登录 Inbox 返回 401。五种独立无敏感样本的真实 Raw/Review/state 路径及状态已记入 Environment-Baseline；URL 初始 Raw hash 不变；图片/音频以 `processor_unavailable` 保留 Raw，不生成假 Review。没有向 Knowledge 写入，App Knowledge mount 为只读。
- NAS 构建中前端 typecheck/build 通过；本地 Core 全量测试 35 passed，前端 typecheck/build 通过。生产部署成功不等于用户验收：登录后 Inbox/Review 页面交互与手机布局仍待用户浏览器确认；图片/音频处理器和微信渠道未实现。测试样本保留，不清理。

## 2026-10-14 D075.1 收录体验缺陷修复（本地）

- Inbox 增加受 App Session 保护的 `/api/inbox/{capture_id}/preview`：只允许已登记 Raw 文件的安全扩展名和固定 MIME，路径拒绝遍历/符号链接，响应 `nosniff`；文本以纯文本显示，PDF 由新标签页的浏览器原生查看器打开，图片/音频在页面预览。原件下载仍为独立附件操作；URL、采集时间、状态、失败原因、原件保存和关联 Review 在详情中展示。CSP、认证及 Private 边界未放宽。
- Inbox 使用 `capture.review_path` 定位 `/review?review_path=...`；Review 从服务端列表精确匹配目标、详情高亮，刷新和前进/后退恢复 URL 选中项；目标不存在时显示明确提示，不回退到第一条。
- Quick Capture 支持单文件拖放与原生文件选择、20 MiB/类型校验、文件信息、撤销/更换。服务端响应确认 `capture_id` 和 `raw_path` 后清空输入并显示处理状态、Raw 路径、继续收录与前往 Inbox；未确认保存的失败保留输入，提交 ref 防止并发重复请求。
- Core Capture API 测试覆盖预览会话拒绝、纯文本安全 MIME/`nosniff`、inline 预览与原件附件下载分离、PNG MIME、路径穿越拒绝；既有 URL Raw 哈希成功/失败/重试测试保留。前端新增 Vitest/jsdom 交互覆盖拖放/撤销、成功清空、失败保留、重复提交、预览安全显示、Review 精确定位及目标缺失。
- 验证：Core 全量 **37 passed**；前端交互 **8 passed**，typecheck、production build、`git diff --check` 通过。FE-4 视觉方向未变。
- **状态：本地实现、测试通过；未部署 NAS、未修改生产。** 保留 D075 已有五条生产测试样本；63013 浏览器验收待后续明确部署授权。

## 2026-10-14 D075.1 NAS 测试部署（Commit `777ee38`）

- 已在正式 Compose 中按授权只改 App build context 和 image tag；新上下文独立保留，旧 D075 源码和镜像可回滚。构建内前端 typecheck、Vite build 和 Core image build 通过；快照完整性、Compose 两行差异与 Compose config 校验通过。
- 仅更新 `secondbrain-app`。App healthy、63013 TLS/根页与健康端点正常；Hermes ID、image、启动时间不变。Raw/Review RW、Knowledge RO、Private 未挂载、Promote=false、state/Secrets 不变。五条 D075 测试记录 Raw/state 均存在，三个 Review 文件存在；PNG/WAV 保持 processor_unavailable，无伪造 Review。
- 未登录 Inbox/preview API 返回 401。App 重建使服务端内存会话失效；Edge 自动化被其他扩展 UI 阻断，无法完成重新登录后的原件预览/下载、Review 精确定位和拖放/重置浏览器验收。代码级相关 Core/前端测试证据仍为本地 D075.1 37 + 8 passed；本次不将其替代生产浏览器验收。须用户关闭/处理 Edge 扩展 UI、重新登录 63013 后完成剩余浏览器验收。
- 回滚快照：`/volume1/docker/secondbrain/rollback/d0751-preflight-20261014-120500/`；只需恢复旧 Compose 并仅重建 App，Hermes 不变。没有改动未跟踪 `typescript`、业务原件、Hermes、DSM GUI 项目、Secret、ACL 或网络。

## 2026-10-14 D075.2 NAS 测试部署（Commit `934d0ea`）

- 使用目标 Git commit 的独立 NAS 构建目录，构建 `secondbrain-app:d0752-934d0ea`；前端 typecheck/build、Core 捕获测试 18 项、前端采集交互测试 11 项通过。正式 Compose 仅更改 App build context/image，校验通过；部署前快照 SHA-256 校验通过。
- 仅重建 App；新容器 healthy，HTTPS 63013 根页与 health 200、匿名 Inbox 401。Hermes 容器 ID、镜像 ID、启动时间均未变化；Raw/Review RW、Knowledge RO、Private 未挂载、Promote=false。D075 五条记录、Raw 哈希及已有 Review 未变。
- 浏览器自动化显示真实 Review 页 15 条记录，但随后被 Edge 上的扩展 UI 阻断。Inbox→Review 自动滚动、手机滚动及 PDF 原文件名仍待用户浏览器验收。回滚快照和部署证据见 `Environment-Baseline.md`；未跟踪 `typescript` 保留。

## 2026-10-14 D075.2 用户验收补记与 D076 本地实现

- 用户明确确认 Inbox→Review 自动滚动及 PDF 原始文件名显示通过，CURRENT 已据此记录 ACCEPTED。拖放和成功清空/失败保留仍只记自动化测试覆盖，不替代用户实际验收。
- 只读核实 Hermes v0.21.5：有 `/api/audio/transcribe`（Base64 `data_url` + MIME）并调用已配置 STT provider；当前容器未安装 faster-whisper/Whisper CLI，未发现 STT 云凭据。默认 GLM-4.5-Air 的官方模型卡只示例 text-generation；Hermes Dashboard 的图片上传保存到其 home/images 并供 Chat 使用，不构成已验证的 App Capture 视觉 API。未提交媒体、调用模型或修改 Hermes。
- 本地 Core 新增 Tesseract 中文/英文图片 OCR、扫描 PDF 在 pypdf 无文本时的后备渲染/识别（10 页、120 DPI、单页 12MP、75 秒总时限、单任务串行）；图像 Review 分栏记录 OCR，并明确 AI 描述不可用时为 partial。正式 `Dockerfile.app` 安装 Poppler 和中英 Tesseract 数据，保留前端构建、Core 启动及 UID/GID build args；设置 `/tmp` 环境与目录权限。只读 rootfs 仍须运行时提供至少 64 MiB `/tmp` tmpfs。增加带 20 MiB、30 分钟与 90 秒超时边界、默认关闭的 Hermes STT 适配。Raw SHA-256、路径和 Review 来源关系不变；不写 Knowledge、不 Promote。
- 修复部分成功图片重复重试造成的 Review 副本：只在原 `review_path` 的普通文件 hash 与 state 一致、且内容字节完全相同的情况下复用，绝不覆盖；变化内容仍另起文件。
- 验证：Core Capture/multimodal/Hermes BFF 定向 **34 passed**；Python 编译、`git diff --check` 通过。D076 识别结果和 Hermes API 行为使用隔离 fixture/Mock。本机没有 Docker/Podman/Tesseract，不能通过正式 App Dockerfile 构建，也未真实跑中英图片、扫描 PDF OCR，未测只读 rootfs 下 `/tmp`，无实际耗时/内存证据；未生产构建/部署。图像 AI 场景描述及可靠 STT runtime 仍是阻断。
- **状态：** D076 部分代码/定向测试完成，真实多模态能力未验收。下一步需在可控构建中验证中文 OCR 真实样本，选择并授权无意外费用/数据传输的图像场景描述和 STT 处理器，再另行申请生产部署；不得标为 DONE。

### D076-A NAS 隔离 OCR canary（2026-10-14）

- 目标 Commit `3c57a553bebd47b64ceb8603ab6da96465bb2de8` 的 `web-app/Dockerfile.app` 独立归档已传至临时构建目录并成功构建；NAS Docker 24.0.2 无 buildx，classic build image 为 `secondbrain-app:d076-ocr-canary-3c57a55` / `sha256:06bb37d41df4af32dd8ddda9a3e4df7f449dac12be0da5fc79eebd99a7bd45a4`。Dockerfile 本地与 NAS SHA-256 为 `be3bb7ae0a9c80b3d2a6881c63d90380f5f7d2dff4c5461becb4b67dfa8dbff0`；构建绑定 CPU 3、2 GiB memory，构建成功。
- 运行前预检显示 NAS Docker cgroup v1 不支持 CFS CPU quota；`--cpus=1` 被 daemon 拒绝。也没有 PIDs cgroup，`--pids-limit=128` 明确被忽略。虽可用 `--cpuset-cpus=3` 与 1 GiB 内存限制并通过 Docker inspect 核验，但缺少 PID 限制使完整隔离契约不成立。按边界未执行任何 OCR 代码；只读验证容器被立即移除。没有合成 PNG/PDF 被 OCR 处理，不存在真实识别、耗时、RSS/CPU 样本或 tmpfs 峰值数据。
- 可核实的正式服务前后状态一致：App ID `3ca30d08568ca547bea9fedf924a73d01a0e00ce06c07b5f95ef52026eed1a4c` / Image `sha256:c3801b546b0e9605370b659cc5c3605abf827080fec7a14a1e88856e917f361d`，`healthy`；Hermes ID `f6703ca3e3d41856b6e35348f28cd1c7f833ffb9ab31b19e958656540eed8ac6` / Image `sha256:e1e87aec2e3f5b9863c127a0f21f3b3c237c8717c57c323c7184a49ca12a0df6`，保持运行；启动时间与预检记录相同。Compose、端口、挂载、Secret、权限、服务、业务数据均未更改。临时源码/样本目录和 canary 容器已清理；仅保留 canary 镜像供后续有条件验证。
- **结论：** Dockerfile 的正式 App 镜像构建已验证；OCR runtime 验收阻断，不能视为图片/PDF 多模态 DONE。后续需在可强制 CPU 与 PID 限制的隔离 Docker 环境重新运行本 canary；本轮未部署 D076。

### D076-A NAS 隔离 OCR 复测收口（2026-10-14）

- 按用户授权复用目标 Commit `3c57a553bebd47b64ceb8603ab6da96465bb2de8` 的现有 Canary，不重新构建。因 NAS Docker cgroup v1 不支持 `--cpus` 且不挂载 PIDs cgroup，本次按用户批准改用单核 cpuset，不设 CPU quota/PID 限额；保留并实测 `network=none`、只读根文件系统、`1026:100`、memory/mem+swap 各 1 GiB、全能力移除、`no-new-privileges`、64 MiB 独立 `/tmp` tmpfs。Docker inspect 与容器内 cgroup 读数均确认 1 GiB 生效；唯一 bind mount 是只读合成样本目录。容器内确认 `chi_sim`、`eng`、Poppler 可用，非 root 可写 `/tmp`、根文件系统不可写；Hermes STT 关闭。
- 真实 OCR/流程结果：中文 PNG 得到“第二大脑 OCR 测试 / 请傈留原始文件”（“保”误识别为“傈”）；中英数字 PNG 的 `SecondBrain OCR Test / 中文识别 + ID 2026-10-14` 全部正确；无文本层单页扫描 PDF 通过 Poppler + Tesseract 得到中文两行原文并生成 Review；有文本层 PDF 经 pypdf 读到 `Readable PDF path canary 2026`，未调用 OCR。图片均产生明确的 OCR Review，状态 `partial_success` 且注明 AI 画面描述未配置。Raw SHA-256 前后相同；对部分成功图片重试复用同一 Review 路径/hash，没有副本。缺少 Tesseract 可执行文件时 Raw 保留、无 Review、状态为 `partial_success/processing_failed` 并携带具体 OS 错误。
- 耗时：中文图片 0.781 s，中英图片 0.909 s，扫描 PDF 0.847 s，可读 PDF 0.002 s，缺少 OCR 可执行文件的失败路径 0.073 s。容器 Docker stats 采样 CPU 峰值约 101.2%（绑定单核）；Docker cgroup v1 `memory.max_usage_in_bytes` 峰值 212,049,920 bytes（约 202.1 MiB），Docker stats 采样最大约 167.2 MiB；`/tmp` 使用峰值为 253,582 bytes（约 248 KiB），tmpfs 容量 64 MiB。未 OOM、未超时、未异常退出。上述 CPU 与 Docker stats 为采样值，cgroup 峰值为内核计数器。
- 强制收尾已完成：移除本轮一次性容器、样本/脚本目录、本地临时目录和未被容器引用的 Canary tag/image；未运行任何全局 prune，D075 镜像未清理。NAS Docker volume 可用空间从 912,018,112 KiB 增至 912,188,484 KiB；测试结束后无容器、镜像 tag 或测试目录残留。
- 正式运行未变化：App ID `3ca30d08568ca547bea9fedf924a73d01a0e00ce06c07b5f95ef52026eed1a4c` / image `sha256:c3801b546b0e9605370b659cc5c3605abf827080fec7a14a1e88856e917f361d`，`healthy`；Hermes ID `f6703ca3e3d41856b6e35348f28cd1c7f833ffb9ab31b19e958656540eed8ac6` / image `sha256:e1e87aec2e3f5b9863c127a0f21f3b3c237c8717c57c323c7184a49ca12a0df6`，持续运行；二者启动时间不变。Compose SHA-256 仍为 `6b143e2b39329dadb4a54a31f1c1a0be1ddfbaacac51a8a5a0f31307b926b61a`；9120/9119 端口、Raw/Review/Knowledge 挂载权限、Secret、Private 隔离与 `SB_PROMOTE_ENABLED=false` 均未变化。测试网络隔离且未挂载正式数据目录，未触碰生产 Raw/Review/Knowledge。
- **结论：** 中文/中英图片 OCR、扫描 PDF OCR 与 pypdf Fast Path 已完成真实隔离运行验证；这是 Canary 验证，不是正式部署或用户验收。音频 STT 未启用；AI 图像描述仍未配置，完整 D076 尚不具备全部处理器验收条件。本轮未更新 63013、未进入 D076-B。

## 2026-10-15 D076-A 用户验收后体验修复（本地，未部署）

- 用户报告 63013 图片和扫描 PDF 的 Raw→OCR→Review 链路正常，但扫描 PDF 识别乱码较多；同时 Review 页面整页滚动、frontmatter 干扰阅读，及图片仅缺 AI 描述时误导性提示。
- 桌面 Review 调整为受视口约束的独立列表/正文滚动，避免列表定位滚动整页；切换内容将正文滚回顶部。手机详情优先，审核列表可展开。Review 安全解析简单 Markdown，YAML 元数据折叠查看；HTML 作为文本，不执行脚本、不自动载入远程资源；OCR 内容按原行序预格式显示并附核对提示。批准/暂缓逻辑与 Promote 关闭边界未改。
- 图片 OCR 已生成 Review 且 processor.kind=image_ocr 时，前端保留 partial_success 状态，展示中性“文字识别完成，画面理解暂未接入”，不显示红色错误框或无意义重试；缺少 OCR Review、真实失败等仍展示错误/重试。
- 扫描 PDF 使用按页面尺寸计算的自适应 DPI，目标最高 200 DPI，仍受 12MP/页、最大 10 页、75 秒总限时与既有尺寸约束；Review 增加核对原件提示，不宣称 OCR 准确。新增参数路径测试。本机无 Tesseract/Docker，未复现真实乱码或证明质量提升；真实质量对照与页面复验待部署后完成。
- 验证：前端 Review/Capture 定向 **18 passed**，typecheck、Vite build 通过；Core Capture/多模态定向 **30 passed**。未读写 NAS 或其素材，没有更改 Hermes、Compose、Secret、权限、Knowledge、Promote 或网络。本项代码/文档随本次提交推送；生产仍运行先前部署版本。

## 2026-10-15 D076-A OCR App 部署（业务代码 3c57a55）

- 依据授权从目标提交构建独立 NAS source context，正式 App 镜像 secondbrain-app:d076a-3c57a55（sha256:3f68f807191b1cb56b436dfd1165475e997d29a3db3de2a12d26c874dccd4ff7），仅重建 secondbrain-app。正式 Compose 仅更改 App build context、image tag、/tmp tmpfs 64 MiB；配置校验通过。D075.2 镜像保留。
- App healthy；真实运行镜像含 Tesseract 中文/英文数据、Poppler、Pillow/pypdf。只读 rootfs 下 /tmp tmpfs 为 64 MiB 且 UID 1026 可写；Raw/Review RW、Knowledge RO、Private 未挂载、Promote=false，STT 默认关闭。
- HTTPS 根页/health 200；短时 HTTPS 登录 smoke 的 Home、Chat、Inbox、Review、文本/PDF 预览/下载均成功，匿名 API 401，Secure/HttpOnly/SameSite=Strict Cookie 确认。D075 47 个相关文件前后清单和 Secret 校验值一致。无生产 OCR 上传或 Knowledge 写入。
- Hermes 容器、镜像、启动时间未变化。App-only 回滚快照位于 /volume1/docker/secondbrain/rollback/d076a-predeploy-20261015-003736/；详细哈希、容器与验收证据见 Environment-Baseline.md。
- **状态边界：** D076-A 运行依赖已部署；用户尚需在 63013 上传无敏感中文图片及扫描 PDF 完成页面验收。未自动重试既有素材；图像 AI 描述、STT 后端、微信及 D076-B 未完成，D076 整体仍 NOT DONE。

# 2026-10-15 — Unified Capture Composer（本地）

- 抽出共享 UnifiedCaptureComposer，Inbox 直接内嵌，首页「快速收录」继续使用同一组件和逻辑；移除输入类型切换与独立 capture_context 字段，不改变 FE-4 视觉方向。
- 单一合法 HTTP(S) URL 调用现有 URL API；其余文本原样调用 Text API；带附件时文本作为 `capture_context` 调用现有文件 API。支持剪贴板图片、单文件拖放、系统文件选择、附件本地预览/移除/更换，继续执行允许类型及 20 MiB 限制。
- Enter 发送、Shift+Enter 保留换行并检查 IME composition；请求重复保护。仅服务端确认 `capture_id` 和 Raw 路径后清空输入，状态轮询与 Inbox 刷新保留；失败保留文本和附件。对象 URL 在附件移除/更换或组件卸载时释放。
- 前端定向交互测试 **22 passed**，`npm run typecheck`、`npm run build` 通过。覆盖 URL/Text 分流、Markdown 原文、剪贴板图片和普通文本粘贴、拖放、文件选择/校验、附件 context、IME、并发保护、成功清空与失败保留。
- **状态：本地实现并测试，尚未部署 NAS，也未进行浏览器用户验收。**

# 2026-10-15 — Unified Capture 中文文案收口（本地）

- 增加前端用户提示映射：Capture 常见状态统一为“已完成 / 处理中 / 部分完成 / 处理失败”；Capture 状态错误按错误码和已知原因转为简体中文，未知错误不透传英文正文并保留错误代码。HTTP/API 与 Hermes/Review 错误按状态和已知原因显示中文；英文语言模式继续保留原文。
- Inbox、原件预览、处理重试、Composer 结果及 Review 状态改用映射。图片 OCR 已生成 Review、仅缺视觉描述时显示“文字识别完成，画面理解暂未接入”；真实 OCR 超时/失败仍显示明确的中文失败原因。技术标识、文件名、来源字段和 OCR/聊天原文不翻译。
- 验证：Capture/Review 交互与文案映射 **30 passed**，typecheck/build 通过；覆盖英文错误不直显、OCR partial 状态轮询、OCR 真失败提示、Review API 错误和英文模式保留。
- **状态：本地实现并测试，尚未部署 NAS，也未进行浏览器用户验收。**

# 2026-10-15 — D076-A.1 + Unified Capture 合并部署

- 目标代码 `55977c8173337e8f9ff9174cf6841df5a3d5a715` 从独立版本目录通过正式 `Dockerfile.app` 构建为 `secondbrain-app:d076a1-55977c8`。部署前快照 `/volume1/docker/secondbrain/rollback/d076a1-predeploy-20261015-142941/` 已通过 SHA-256、权限及原 Compose/.env 比对校验。
- 新镜像先进入一次性隔离 Canary。cgroup 实测内存/Swap 各 1 GiB、CPU affinity 3、只读 rootfs、network none、非 root UID/GID 1026:100、64 MiB `/tmp`、cap-drop ALL 与 no-new-privileges 均生效。真实中文/中英图片 OCR、无文字层扫描 PDF 200 DPI OCR、可读 PDF pypdf Fast Path 全部通过；测试对照文字与 Raw/Review SHA-256 已核对。Tesseract 5.5.0、chi_sim/eng、Poppler 25.03.0。容器 memory high-water 215,678,976 bytes，`memory.failcnt=0`、无 OOM；tmpfs 10 ms 采样峰值 274,432 bytes。120 DPI 单样本对照识别相同文本，不据单次耗时评价改进。
- Canary 容器、合成样本目录及隔离 Capture 输出均已清理；保留版本化构建源码、新镜像和受限回滚快照。
- 正式 Compose 只变更 App build context/image 两项；新 SHA-256 `b7ca306b82e03b4eae022b8d9ed68beb82b57d1e5b419bf0a4467a632c8a92dc`，`config --quiet` 通过。仅 Compose CLI 重建 App；新容器 `b96506b44965faa1fe88a12a6d7411efcf3e5ab0cfb9218ff17a1e0dfa1d27b8` healthy，Image ID `sha256:e994da5c0c4a5fb0eef27608728b1091d1442e686ac4a407e7661aea37060505`。Hermes 容器、镜像与启动时间不变。
- HTTPS/API smoke 登录、Secure Cookie、Home、Chat 读取、Inbox、Review 列表/详情、原件预览/下载通过；未登录 Inbox/Review/Capture 拒绝；Promote=false。Raw/Review RW、Knowledge RO、Private 未挂载，STT 关闭，53 个已有 Raw/Review/state 文件哈希未变。未上传生产测试素材或执行 Promote。
- 构建产物含统一 Composer、中文提示、D076-A.1 Review 布局。**状态：代码已部署并通过隔离 OCR 与服务端 smoke；尚未用户浏览器验收。** 等用户在 63013 验收 Composer 桌面/手机交互、Review 阅读布局及其真实中文扫描 PDF OCR 质量；不代表 D076 完成，也未进入 D076-B。

# 2026-10-15 — D076-A.1 Review、排序与素材关联修复（本地）

- Review 桌面双栏改成固定 36/64 比例并约束 min-width/min-height，列表与正文各自滚动；长行换行，切换条目时正文回顶，删去重复 Core 状态展示。手机仍采用详情优先布局，待用户实机验收。OCR 引擎参数行默认隐藏，完整原始 Review 仍可展开；正文/识别行序不变。
- Inbox 与 Review 使用有效 `captured_at` 倒序和确定性 tie-break。Review 时间先读 frontmatter；旧记录缺失时用精确 `review_path` 从 Capture state 补足。日期级来源只展示日期，不补造时间；无效、无来源或存在歧义时标“时间未知”并排最后。Inbox 与 Review 深链接仍按路径/ID保持定位。
- 只读 NAS 盘点：15 条 state 的 Raw 及 13 个关联 Review 的 SHA-256 均与文件一致；2 条部分成功没有 Review。全目录有 23 个 Raw/23 个 Review；8 个 Raw、10 个 Review 无 Capture state 关系，无法安全认定为测试/重复对象。发现唯一 Raw 哈希重复组：capture `2976bd1c32b7440d9e7b407526f3e8be` 与 `8b8a4078ffc34cc98dbf72a30d966d99` 的 PDF 字节相同，但 Raw 路径、Review 路径/hash 不同且没有审批记录。作为待用户确认的清理候选，不删除；具体关联见 Environment-Baseline。现存唯一审批记录是 `capture-1.md` 对应 `deferred`，与重复 PDF 组无关。
- 用户反馈真实扫描 PDF 乱码/漏字。没有以 Review 生成作为准确性证据，也未读取、重试、覆盖或改动旧 PDF。该质量问题保留为待验收项。
- 验证：前端 Capture/Review/layout **31 passed**；`npm run typecheck` 与 Vite build 通过；Core Review auth/list/detail **13 passed**、Capture **18 passed**；`git diff --check` 通过。测试检查响应时间字段、日期回退/未知排序、重复提示、OCR 参数隐藏、正文切换回顶与刷新保持定位、桌面比例/滚动与移动布局 CSS 契约。
- **状态：代码和文档本地修改、测试通过，尚未 Commit/Push 前仍未部署。** 未改 Hermes、Compose、Promote、Knowledge 权限或网络。手机端及真实 PDF OCR 准确度继续待用户验收；任何素材删除/移动需另行批准。

# 2026-10-15 — 早期无日期测试记录清理复核（零删除）

- 按授权只读复核 23 个 Raw、23 个 Review、15 个 Capture state 与 1 条审批状态。15 条 state 均有有效 `captured_at` 且 Raw SHA-256 匹配；13 个关联 Review 的 SHA-256 匹配，另 2 条部分成功状态无 Review。23 个 Review frontmatter 均有可验证日期/时区时间；10 个无 state 的 Review 也均有时间来源。8 个无 state Raw 与 Review 的 `original_asset` 可关联，另 2 个无 state Review 的 Raw 缺失或不在 Inbox。
- 2026-10-09/10 的早期开发/模型测试命名记录虽缺 Capture state，但其 Review 保存有效采集日期，超出本次“缺少有效 captured_at”删除范围，全部保留。相同 SHA-256 的两条 iShot PDF 也有有效 state 时间且各有不同的 capture_id、路径和 Review；保留。唯一审批 `capture-1.md` 为 `deferred`，关联记录有有效日期；保留。按对应原始文件名、Review 路径、capture_id 对 Knowledge 精确检索无引用命中。
- **删除 0 项，备份 0 项。** 没有文件通过删除门槛，因此不创建无用备份；本记录即零删除清单。未读 Raw/Review 正文、未访问 Private，未写入、移动或删除任何业务文件。
- 部署后 App healthy、Hermes running，容器 ID/镜像/启动时间未变；Compose SHA-256 `b7ca306b82e03b4eae022b8d9ed68beb82b57d1e5b419bf0a4467a632c8a92dc` 不变。App Knowledge RO、Hermes SecondBrain RO、Private 未挂载。没有执行任何容器、Compose、权限或网络变更。

# 2026-10-15 — D076-A.1 Review 排序与布局 App-only 部署

- 部署目标 `9962001bf296ee8804a2037891e9a85633cfb8ea`，构建为 `secondbrain-app:d076a1.1-9962001`（Image ID `sha256:55f40951620fb8b7043933c724f66cbf22a2326a961d654d8671e877c212bcd3`），新 App 容器 `4af3586d92b294f0808118676a94f3d0cf643b70785ebf0fc17f79264dfe8f95` healthy。只更新正式 Compose 中 App build context/image 两项并仅重建 App；Hermes 容器、镜像、启动时间未变。
- Compose SHA-256 从 `b7ca306b82e03b4eae022b8d9ed68beb82b57d1e5b419bf0a4467a632c8a92dc` 更新为 `e318d4167666877e415203f637eda63a38cde41b01e5d58855dee29ce50a1149`。Raw/Review/Capture state 61 个文件的路径、大小、权限和 SHA-256 部署前后完全一致；Promote=false、Knowledge RO、Private 未挂载。
- 代码验证：定向前端 31 项、typecheck、Vite build、Core approval auth 13 项、Capture 18 项均通过。HTTPS 根页/health 200、匿名受保护 API 401；正式资源哈希匹配目标构建。隔离运行检查 OCR 依赖存在，本轮没有处理图片或 PDF。
- App-only 回滚快照保留于 `/volume1/docker/secondbrain/rollback/d076a1.1-predeploy-20261015T072713Z/`；旧镜像 `secondbrain-app:d076a1-55977c8` 保留。
- **状态：代码已部署，自动化、静态资源、健康和匿名访问边界验证通过；用户登录后的浏览器验收尚未完成。** 待验收桌面 Review 双栏与时间排序/时间未知显示、Inbox/Review 跳转与阅读、预览/下载、Home 基础页面；手机布局另待验收。没有将部署标为用户 ACCEPTED，也没有清理历史记录、重试 OCR、启用 Promote/STT/视觉或更改 Hermes。

# 2026-10-15 — D076 统一对话/收录入口与 AI 智能整理安全门

- GitHub main 基线核验为 `7e0e2fca1986ef02696a20e43ee6d47d4592ce30`；未跟踪 `typescript` 保留。
- 固定 Hermes v0.21.5 upstream `749220ef` 源码确认 sessions 分页与单 session 消息分页/时间戳/稳定 ID；Core Hermes adapter 保留这些字段。Chat 默认仍读取最新 message page。
- Chat 页面增加显式 Chat / Capture 去向切换；点击/拖放/粘贴附件在 Hermes 能力未验证时明确拦截并支持用户主动切换，同时保留图片本地预览与文本草稿；Inbox 变为历史管理页，不再重复显示 Capture 输入框。Hermes 对话附件解析未验证时明确提示，附件可由用户切换到现有 Capture，避免静默发送。IME Enter 保护保留，并修复 Chat API 启动失败/Run 失败时输入草稿恢复。
- 新增 `AI 智能整理` Settings 页面及 Core 私有原子 JSON 设置 Store，配置支持启停、固定 HH:MM / Asia/Shanghai 与间隔 hours；默认值按 D076 为启用、每 4 小时，切换固定模式默认 00:30。增加状态及立即触发 API。由于 safe no-tools 模型调用和硬成本边界尚未验证，状态明确 blocked，立即触发返回 503 且按钮禁用；没有调用模型、创建 scheduler/job/cursor 或 Review 草稿。
- Hermes `/v1/runs` 是 Agent Runtime 路径，不能据 Prompt 宣称无工具副作用；Organizer 的安全模型调用器、增量游标/恢复与 Review 草稿 worker 暂缓实现。需要先证明运行时工具禁用、费用上限和 SessionDB/profile 读取完整性。
- 验证：前端 `npm run typecheck`、Vite build 通过；Capture/Review 与 unified-mode 前端定向测试 **41 passed**。Core BFF、设置持久化与会话消息分页测试 **10 passed**，Capture 回归 **18 passed**，Python compileall 通过。无 NAS/生产访问。
- **阶段状态：统一入口本地实现并测试；自动整理设置/状态安全骨架本地实现并测试；真实立即整理、周期 scheduler、source cursor、Review 草稿生成尚未实现/未激活。** 生产没有变化。后续需先完成工具受限模型接口验证，再实施增量任务 runner 与自动化/异常验收。

## 2026-10-15 — D076 最小 Organizer 闭环与入口收尾（本地，未部署）

- 复核基线为 GitHub `main` Commit `305c3748ab8ca2ec9e064b3f82d5778641edb427`。Inbox 保持纯历史管理；Home 收录入口转向 Chat，Chat/Capture 显式切换并保留已编辑文字和替换附件；移除独立 QuickCapture 弹窗入口。
- 固定 Hermes `749220ef` Session API 行为已核实：会话/消息分页、稳定 ID、时间戳与消息数可用；BFF 将 App 当前会话列表中的会话登记为 Organizer 来源，首见时基线跳过既有历史。会话删除 404 保留为 coverage warning；计数回退/锚点改变隔离该会话，不阻止其他会话处理。外部渠道/其他 profile 不纳入；无 tombstone/snapshot token，无法检测同计数删除后追加，不能承诺无遗漏。
- Core 新增 file-backed Organizer Runner：持久 settings/session cursor/jobs、跨进程文件锁、用户消息增量扫描、有限历史上下文、消息/字符/候选/请求预算、单请求能力闸门、Review 幂等不可覆盖写入、保存模型结果后的写入恢复、模型结果未知时禁止重试，以及调度失败退避。共享手动/计划执行器及游标；无新增消息跳过模型。草稿含分类、AI 提炼与原文区分、会话/消息/时间/作业来源引用，目标仅 Review。
- 安全阻断仍在：Hermes `/v1/runs` 与 OpenAI 兼容 Chat 路由走 Agent Runtime，不构成已证明的 no-tools、有硬输入/输出 Token、超时、并发和成本限制的模型服务；无获准的独立接口/凭证。本地生产配置 `model=None`，startup 不启动 scheduler，`/run` 返回 503，UI 明示设置只保存、自动整理未运行。未调用真实付费模型、未整理真实历史、未写入真实 Review。
- 验证：Core 全量 **76 passed**（Starlette/httpx 弃用警告 1 项）；前端 `npm run typecheck`、Vitest **42 passed**、Vite build 通过。新增/覆盖并发互斥、空输入、跨会话来源、分页/游标断点恢复、预算拒绝、来源引用验证、失败恢复、模型结果不明停止、用户修改 Review 冲突保护、设置重启持久、配置禁用时的手动运行等。
- **交付状态：** 本地代码和必要文档已更新，未提交前仍是工作树修改；无 NAS/Compose/Hermes/网络/权限/业务数据访问或更改，也没有用户浏览器验收。需先解决受控 no-tools 模型接口和历史完整性策略，再申请真实模型及部署授权。

## 2026-10-15 — D076 SiliconFlow 受控 ModelAdapter 原型（本地，未部署）

- 基于 `8167ffd` 新增独立 SiliconFlow Chat Completions Adapter；目标为 Core 直接调用文本模型，不经过 Hermes Agent Runtime。固定 HTTPS endpoint/model 配置，无重定向、无流式响应、请求体不包含 `tools`、`tool_choice`、Skills 或文件能力；使用 Bearer key、单并发、45 秒硬超时、单次请求/作业、`max_tokens` 输出限额、输入 UTF-8 字节截断；响应校验 JSON/schema/token usage，并拒绝工具调用、超长输出、429、异常响应及超时，不自动重试。私有 Secret 文件读取 helper 要求绝对路径、普通文件、当前 Core UID 所有、权限不宽于 0600、禁止符号链接，并不在错误或 repr 中暴露凭据。
- SiliconFlow 请求/响应由 `httpx` adapter contract 表达；usage 可记录 prompt/completion/total token 与模型标识，不将 usage 当费用账单。官方资料表明 Chat Completions 支持 `max_tokens`、返回 usage，429 表示限流；计费按实际 token 计价。官方资料提及账户面板月度消费限额，但没有核实其对单 Key/单作业的强制边界，且 rate limit 是账户级；接口也没有可供请求侧设置的硬输入 token 参数。因此能力声明有意将 `hard_input_token_limit` 与 `hard_cost_budget` 设为 false，现有 Organizer Runner 会拒绝启用。
- 使用 MockTransport/合成数据测试接口无工具、Secret 文件权限、UTF-8 输入截断、usage、超时、429 不重试、异常 JSON、输出超限和超限预算在请求前拒绝；复用 Organizer 现有断点恢复/幂等/作业调用预算测试。定向测试 `test_siliconflow_organizer.py` + `test_organizer_engine.py`：**29 passed**；Core 全量测试：**85 passed**（1 条 Starlette/httpx 弃用警告），Python compileall 与 `git diff --check` 通过。未访问真实 API、未读取或新增凭据、未启动调度器、未修改生产配置或业务数据。
- 首次会话纳入当前仍跳过已有历史。建议后续提供显式回溯范围 `不回溯 / 当天 / 最近 4 / 12 / 24 小时`；每条来源以 `session_id:message_id` 持久去重，记录消息时间与 Core 接收时间，按消息时间水位及有限倒序分页收集，不扫描全部历史。首次范围选择应固定在作业/配置中，避免重启或改设置产生重复或漏收；当前未实现该回溯选项。
- **状态：** 适配器代码原型与合成测试完成，安全能力门槛未通过，AI 自动整理仍 blocked/未部署。真实付费调用的最小前置授权：用户指定模型与每月平台支出限额，并确认有限 App 可见 Hermes 对话正文可发送到 SiliconFlow；由用户在供应商控制台确认并配置月度限额及其超限拒绝语义；另行批准为 Core 创建独立 API Key、以私有 Secret 文件注入及一次合成/无敏感样本联调。若供应商不能确认强制限额，则不启用任何付费调用。

## 2026-10-15 — D076 SiliconFlow 真实联调准备（仅合成离线验证）

- 基线 `cc7e963155b80eb9d8b97d62237630bc83e4b185`；本地 `main` 与 `origin/main` 一致。未跟踪 `typescript` 保留、未读取或改动。
- 新增合成 Organizer 端到端测试，使用稳定虚构 session/message ID 与 UTC 时间，覆盖日记、工作灵感、待办、普通闲聊过滤、跨会话相同表达合并引用、跨批次补充、Review 写入后中断恢复、游标推进和重复运行无重复模型调用。隔离 Review 目录位于系统临时目录，测试退出后自动删除；运行输出记录了隔离路径、输入 ID、草稿数、游标与第二次运行状态。定向测试 **30 passed**（合成 E2E、SiliconFlow Adapter、Organizer Engine）；Core 全量 **86 passed**，另有 1 条 Starlette/httpx 弃用警告。没有访问 Hermes/生产数据、真实 Review 或凭据。
- Adapter 核对：固定 Chat Completions HTTPS endpoint；`model/messages/stream:false/max_tokens/temperature/n` 请求、Bearer 认证；无 `tools`、`tool_choice` 或 Skills。官方协议展示 `choices[].message.content` 与 `usage.prompt_tokens/completion_tokens/total_tokens`；实现拒绝 429、HTTP 错误、重定向、超时、无效 JSON/schema、工具调用、finish_reason=length 和超输出，不自动重试。响应 usage 是平台返回的用量数据，不等同于结算账单；本地 4500 UTF-8 字节截断不等于模型 tokenizer 的硬输入 Token 限额。适配器测试覆盖上述主要异常及前置预算拒绝。
- 官方页面对版本价格并不完全一致：目标默认模型详情页 `deepseek-ai/DeepSeek-V4-Flash` 展示上下文 **1049K**、输入 **US$0.13/M**、输出 **US$0.28/M**；总价格表另外列出 `DeepSeek-V4-Flash-0731` 为 **US$0.22/M、US$0.66/M**，并列有更新的 `DeepSeek-V4.1-Flash`（**US$0.15/M、US$0.60/M**）。因此 0.13/0.28 是精确默认 ID 的公开模型页报价，但不能确认它是账户实际结算价或当前推荐版本；联调前须从账户模型广场/控制台复核模型 ID 和结算单价，不在此处擅自改默认模型：[DeepSeek-V4-Flash 模型详情](https://www.siliconflow.com/models/deepseek-v4-flash)、[公开价格表](https://www.siliconflow.com/pricing)。官方 Chat Completions 文档定义 `max_tokens`、JSON/usage 响应和 429：[API 参考](https://api-docs.siliconflow.cn/docs/api/chat-completions-post)。官方限流说明为账户级而非 API Key 级：[Rate limits](https://api-docs.siliconflow.cn/docs/userguide/faqs/rate-limit-and-upgradation)。这些资料没有证明按请求/密钥硬支出上限或供应商月限额达到后必定拒绝请求。
- 仅做量级估算：以目标默认模型详情页价格和适配器声明的最多 6,000 输入 Token、1,200 输出 Token 全额计，单次约 **US$0.001116**，最多 3 次约 **US$0.003348**；若实际按价格表中的 V4-Flash-0731 单价，则约 **US$0.002112/次、US$0.006336/3次**。这未含汇率、缓存/计费细则、模型版本差异或非成功但已处理请求；输入上限目前只是本地软估计，不能据此保证真实账单低于用户的 **¥5**。45 秒客户端超时也不能证明供应商未完成或不收费。为降低不确定性，后续授权方案应限制为最多 **3 个总请求**（不是只数成功响应）、单并发、无自动重试、45 秒超时；遇到任一异常立即停止并核对账单，再决定是否继续。此方案仍非硬费用封顶。
- 凭据边界：未创建、读取、传输或提交 API Key。现有 `read_private_secret` 要求绝对路径、非符号链接普通文件、属 Core 运行 UID、无 group/other 权限、最多 4 KiB，并拒绝空白/多行；后续最小方案为专用文件由 Core UID（生产目标 1026）拥有、0600 或更严，Core 容器只读挂载到专用 Secret 路径，不进入环境变量/前端/Hermes/Compose Git。创建 Key、生产注入、向供应商发送合成数据都需另行批准。
- **门禁与下一步：** 本地模型替身和引擎验证通过；没有真实 API 调用、费用、Scheduler、NAS 部署或生产状态变化。Organizer 真实执行仍因缺少硬输入 Token 与硬成本/供应商限额证明而保持禁用。下一阶段最小授权须明确：是否同意创建独立 SiliconFlow Key；确认仅虚构合成聊天文本可发送；指定/确认模型和不超过 ¥5 的试验预算；用户在供应商控制台自行确认实际强制限额并配置月度限额；授权将新 Key 以专用文件注入开发/测试 Core；授权最多 3 个总调用并接受“软预算、非硬封顶”。若无法确认供应商强制限额，真实付费调用仍不具备启动条件。无真实调用授权在本轮取得。

## 2026-10-15 — D076 DeepSeek / GLM / Qwen 横向评测准备

- 基于 `025f61ee1877bdfb82981c3f27845ae8129898ec`。使用本地合成对话及隔离测试目录，不访问生产会话或业务路径，不创建 API Key、不打开独立凭据文件、不调用真实 API、不部署 NAS。保留未跟踪 `typescript`。NAS config YAML 被解析器整体加载的偏差单独如实记录如下。
- 通过 NAS 只读容器配置输出筛选到三个 SiliconFlow provider：`deepseek-ai/DeepSeek-V4-Flash`、`zai-org/GLM-4.5-Air`、`Qwen/Qwen3.5-35B-A3B`；三者配置 Base URL 都是 `https://api.siliconflow.cn/v1`。全局可见的非敏感参数为 `reasoning_effort=low`；没有确认到 provider 级 temperature/top_p/max_tokens。此前 Environment Baseline 已记录 GLM-4.5-Air 为 Hermes 默认模型；本次安全输出只确认配置条目，不独立证明当前活动会话选中的模型。
- **检查偏差如实记录：** 为筛选上述非敏感字段使用的 YAML 脚本调用了完整 YAML 解析器；尽管输出白名单排除了密钥字段、命令输出没有密钥、也未复制或保存配置，但解析器曾将整个 `config.yaml`（包含凭据字段）加载到进程内存。这超出本轮“不读取 API Key”的要求。已停止后续 NAS 配置读取；没有发现密钥进入终端输出、Git、请求或文档。此处不记录密钥内容。
- SiliconFlow 官方模型页面（2026-10-15 查阅）列示：DeepSeek-V4-Flash exact ID `deepseek-ai/DeepSeek-V4-Flash` 可用，1049K 上下文、输入/输出 US$0.13/0.28 每百万 Token；GLM exact ID `zai-org/GLM-4.5-Air` 可用，131K、US$0.14/0.86；Qwen exact ID `Qwen/Qwen3.5-35B-A3B` 可用，262K、US$0.24/1.80。Qwen 页面还标注默认思考模式、支持 JSON Mode；GLM-4.5-Air 标注不支持 JSON Mode。价格表/模型详情有版本或报价差异：DeepSeek-V4-Flash-0731 是不同 ID 且价格不同；Qwen 页面与目录摘录也出现不同费率。官方列表可证明目录中的 Serverless 状态，不证明 Joe 账户当前额度或授权成功。[DeepSeek 模型页](https://www.siliconflow.com/models/deepseek-v4-flash)、[GLM 模型页](https://www.siliconflow.com/zh/models/glm-4-5-air)、[Qwen 模型页](https://www.siliconflow.com/models/qwen3-5-35b-a3b)、[价格表](https://www.siliconflow.com/pricing)。
- 本地 ModelAdapter 已能通过构造参数逐模型设置 ID；本轮将请求 endpoint 对齐至 Hermes 现用/官方参考的 `https://api.siliconflow.cn/v1/chat/completions`，固定同一合成 prompt、`stream=false`、`max_tokens=1200`、`temperature=0`、`n=1`、`enable_thinking=false`，没有 `tools`/`tool_choice`，未统一启用 `response_format`（GLM-4.5-Air 没有 JSON Mode，三者均以同一 prompt-only JSON 规则衡量解析率）。官方文档说明 `max_tokens` 不含思维链 Token；显式关闭思考模式用于减少该项差异与不可见支出，但 Qwen 的默认思考行为及 GLM 参数兼容性尚未经过真实端点验证；真实请求遇到参数不兼容即停止，不重试。
- 按 6,000 输入 / 1,200 输出 Token 假设估算每次：DeepSeek **US$0.001116**、GLM **US$0.001872**、Qwen **US$0.003600**，三次合计 **US$0.006588**。这是以软输入预算及公开页面单价计算的量级估算，不是账单上限；ModelAdapter 输入截断是 4,500 UTF-8 字节而非 tokenizer 硬 Token cap，超时/失败请求也可能被平台计费。预算约束仍为最多三条总请求、单并发、无自动重试、45 秒超时；一条异常立即停止并核对控制台账单。
- 评测结果表（真实请求尚未授权，运行/Token/费用留空）：

  | 模型 ID | 输入/输出价 USD/M | 目录上下文 | 分类质量 | 引用准确率 | 重复率 | JSON 解析 | 耗时 | usage 输入/输出 Token | 估算费用 USD | 控制台实费 |
  |---|---:|---:|---|---:|---:|---:|---:|---:|---:|---|
  | `deepseek-ai/DeepSeek-V4-Flash` | 0.13 / 0.28 | 1049K | 待测 | 待测 | 待测 | 待测 | — | — | 0.001116 | 待核 |
  | `zai-org/GLM-4.5-Air` | 0.14 / 0.86 | 131K | 待测 | 待测 | 待测 | 待测 | — | — | 0.001872 | 待核 |
  | `Qwen/Qwen3.5-35B-A3B` | 0.24 / 1.80 | 262K | 待测 | 待测 | 待测 | 待测 | — | — | 0.003600 | 待核 |

- 评分口径：分类质量按人工标注的日记/灵感/待办/知识候选及应过滤项计算；引用准确率要求来源 session/message ID 和时间正确且 excerpt 是该条用户原文连续子串；重复率按同一主题重复草稿数/有效主题数计算；JSON 解析率按完全满足 Organizer schema 的响应计；耗时用客户端单调时钟；usage 记录 API 返回输入/输出 Token；费用估算以当次模型页费率及 usage 计算，实费必须由用户随后在 SiliconFlow 账单核对。单样本横评结果只代表这组虚构输入，不外推一般模型能力。

- 离线覆盖同一合成数据：生活记录、跨会话重复工作灵感、跨批次补充、待办、普通闲聊及普通问答；三模型 Mock 测试验证除 `model` 外请求体一致，并检查 temperature、最大输出、thinking 标志、单次/非流式和无工具。定向测试 **31 passed**；Core 全量 **87 passed**，compileall 与 `git diff --check` 通过（1 条既有 Starlette/httpx 弃用警告）。真实分类、速度、usage、结算金额均未测。
- **授权门槛：** 如需实际横评，用户需另行批准新建/使用独立 SiliconFlow Key、仅发送虚构样本、三个 exact model ID、最多三次总请求及 ¥5 目标软预算、由用户在控制台确认模型可用性/限额并事后核对账单，以及 Core 专用只读 Secret 文件注入。供应商硬费用封顶和输入 Token 上限仍未证明，不能据此启用 Organizer 定时任务或真实聊天整理。

## 2026-10-15 — D076 SiliconFlow 多模态横评准备（无真实调用）

- 基于 GitHub `a8bd5b1`。读取项目当前规则/基线，保留未跟踪 `typescript`。本轮只新增合成 benchmark 样本、评分计划与状态文档；没有读取 Hermes/NAS 配置或 API Key，没有创建凭据、调用模型、访问真实对话/业务数据、写 Review、启用 Scheduler、部署 NAS 或修改网络。
- 新增 `docs/benchmarks/d076-siliconflow-multimodal/`：虚构 organizer 对话复用既有固定 E2E；新增 TXT、Markdown、可读 PDF、无文字层扫描 PDF、模拟软件 UI PNG、图表 PNG 与扫描页 PNG。样本固定答案由人工定义，不依据模型输出。校验：三 PNG 完整可读；可读 PDF pypdf 有正确文本层，扫描 PDF pypdf 提取为空；所有样本 SHA-256 记于 README。
- 官方目录复核文本模型：`deepseek-ai/DeepSeek-V4-Flash` ($0.13/$0.28 input/output USD/M，1049K，Available，image input 不支持，JSON mode 支持)；`zai-org/GLM-4.5-Air` ($0.14/$0.86，131K，Available，image input 和 JSON mode 均不支持)；`Qwen/Qwen3.5-35B-A3B` ($0.24/$1.80，262K，Available，支持 image input 与 JSON mode)。
- 视觉候选最多三款：`deepseek-ai/DeepSeek-V4-Flash-Vision-Exp` ($0.44/$1.32，1049K，Available，支持图片与 JSON mode，实验型号，官方页面称图片最多按 384 tokens/张计)；`zai-org/GLM-5V-Turbo` ($1.20/$4.00，205K，Available，支持图片、不支持 JSON mode，未找到该型号图像 Token 换算/尺寸上限)；复用 `Qwen/Qwen3.5-35B-A3B`。GLM-4.5V 已 Deprecated，不选。供应商目录可用不代表个人账户授权/额度已验证。官方来源：模型 [DeepSeek 文本](https://www.siliconflow.com/models/deepseek-v4-flash)、[DeepSeek 视觉](https://www.siliconflow.com/models/deepseek-v4-flash-vision-exp)、[GLM Air](https://www.siliconflow.com/models/glm-4-5-air)、[GLM 视觉](https://www.siliconflow.com/models/glm-5v-turbo)、[Qwen 3.5](https://www.siliconflow.com/models/qwen3-5-35b-a3b)、[视觉输入指南](https://docs.siliconflow.cn/docs/userguide/capabilities/vision)、[Chat Completions 参数](https://docs.siliconflow.cn/docs/api/chat-completions-post)。
- 建议最终最多 12 个串行 HTTP 请求：组织合成对话 3 次、TXT/Markdown 3 次、PDF 文本提取/OCR 文本下游分析 3 次、三款视觉候选使用同一 PNG 样本组 3 次；同任务固定 prompt/采样参数/最大输出 Token。零自动重试；每次 45 秒，任一异常停止。扫描 PDF 当前主机未安装 Tesseract，未生成真实 OCR 识别文本；README 明确参考 OCR transcript 只测下游文本理解，真实 OCR 质量需先离线取得，不可将模型摘要当 OCR 通过证据。PDF 视觉路线使用扫描页 PNG 渲染，不直传 PDF。
- 费用量级按每文本模型 Organizer 6k/1.2k、文件 3k/0.5k、PDF 5k/0.8k input/output Token；视觉每候选约 1k/0.6k 加各自图片 Token 估算，合计约 **US$0.021333 + GLM 图像 Token 费用未知**。这仅是量级估算，不能保证不超过 ¥5；文本 Adapter 输入预算是字节截断，不是服务端硬 Token 上限。`usage`/trace 不等于供应商账单，真实费用需用户后台核实。
- **Adapter 核查：** 现有 `SiliconFlowOrganizerModel.extract()` 只把输入序列化成文本 user content，并强制 Organizer `{drafts: [...]}` JSON 输出；没有 `image_url`/二进制 payload/MIME 校验或图像 token/字节限制，故不支持视觉。最小后续实现应新增独立视觉调用适配层，允许清单内模型 ID 与经过签名检测/解码/尺寸压缩的 PNG/JPEG Base64 `image_url`，限单次图片数和请求体字节数、固定 HTTPS endpoint、无工具/非流式/单并发/45 秒/输出限额/usage 与 trace 记录；不让现有纯文本 Organizer 接口隐式接受图片。SiliconFlow 指南显示可经 `/chat/completions` 用 `image_url` 的 URL 或 Base64 以及 `detail`、多图内容；公开资料没有确认三个候选共同图片格式全集/请求体字节上限，因此本地建议最多 2 MiB/图、1600 px 长边、8 MiB 请求体是保守客户端门槛，不是服务商约束。
- **离线验证：** `test_siliconflow_organizer.py` + organizer synthetic E2E **11 passed**；新增 fixtures 通过 Pillow 文件完整性/PNG 尺寸检查及 pypdf 可读/扫描文本层检查；`git diff --check` 通过。测试未发起任何网络模型请求；组织器现有代码未变，Core Adapter 定向测试总量为 11（该组命令）。
- **当前状态/门槛：** 仅资料、固定样本、标准答案和离线验证准备完成；无真实请求数/usage/响应时延/账单。先取得真实 OCR 样本文本、参数支持及当前准确价格复核，再由用户另行授权：指定 exact IDs；最多 12 个总请求；仅虚构样本出网；预算 ¥5 为软目标；同意使用专用新 Key 并以私密文件安全注入；由用户预先核实/设置供应商限额及事后核账。没有本次生产变化，Organizer 仍 disabled。

## 2026-10-15 — D076 视觉评测适配器（离线）

- 基于 GitHub `feea0fc136f0d6d13ec7c2391ecaf41f8cbf5578`，新增独立 `VisionBenchmarkAdapter`，不改 `SiliconFlowOrganizerModel`。只允许 `Qwen/Qwen3.5-35B-A3B`、`deepseek-ai/DeepSeek-V4-Flash-Vision-Exp`、`zai-org/GLM-5V-Turbo`；仅本地 PNG/JPEG bytes -> Base64 data URI；固定 HTTPS endpoint、无 tools、非流式、单实例单并发、不跟随重定向、不重试、超时最高 45s、输出最多 800 tokens。请求前限制最多 3 图、每图 2 MiB、1600×1600/2.56MP、总 JSON body 8 MiB；只记录模型、usage、耗时、error code 与 trace ID，不记录图片/密钥。JSON Mode 依据现有型号能力记录显式区分：GLM 禁止，DeepSeek/Qwen 可选且默认不发送；`enable_thinking` 对三个型号均不发送，因未核实各自兼容证据。
- 官方 SiliconFlow 文档确认 Chat Completions 可接受 Base64 image data URI，指南直接展示 JPEG 示例；通用接口说明 `image_url`、detail 与多图。文档没有提供三型号共同的图像字节/请求体上限，也未找到三型号逐一承诺 PNG Base64 的型号级约束。客户端接受 PNG/JPEG 是基于此兼容接口的受限实现，须由后续合成图片请求验证；本地大小/像素限制不是供应商硬上限。Qwen 官方像素范围为 56–3584，当前客户端 1600px 上限更保守。文档链接见多模态评测 README。
- `test_vision_benchmark_adapter.py` 使用 `httpx.MockTransport` 本地假 HTTP 服务覆盖消息格式及 Base64、模型/JSON 参数、非法与不支持图片格式、单图/总请求/输出限制、429 零重试、重定向拒绝、超时、无效 JSON、异常响应和脱敏 trace/usage。未发真实 API 请求，未创建/读取凭据，未读取 Hermes、生产素材或生产业务数据，未改 Organizer、Scheduler、Compose/NAS。
- **状态：代码/文档已完成，视觉适配器与既有文本适配器定向测试 18 passed、2 subtests passed；compileall 和 `git diff --check` 通过。尚未 Commit/Push；真实视觉 API 联调未授权、未执行。** 后续需要用户单独授权合成图片数据出站、exact model ID、总请求上限及专用 key 的安全注入；¥5 仍是软预算目标，不能保证硬封顶。


## 2026-10-15 — D076 SiliconFlow 横评收尾与基线职责纠偏

- 文本横评最终对账：`deepseek-ai/DeepSeek-V4-Flash` 是唯一获得完整有效输出并可依固定合成答案评分的候选；这不表示全面优于 GLM/Qwen。GLM-4.5-Air 有账单、响应丢失；文本 Qwen 曾超时且无可评分输出。详细 usage/费用证据保留在 `../benchmarks/d076-siliconflow-multimodal/README.md`。
- 视觉横评三款均没有可评分完整输出：Qwen `finish_reason=length`；DeepSeek Vision HTTP 400 且原因未定；GLM-5V-Turbo HTTP 400 / 供应商错误码 `20012`。视觉请求 usage/账单金额未知，未重试。最终状态 `DEFERRED`，停止参数试探与供应商切换。
- 按 Codex-Governance《开发协作经验手册》的职责分工盘点并纠偏：`00-CURRENT` 留 V1 定义、完整矩阵、NOW/BLOCKED/DEFERRED 和导航；Architecture 留稳定架构与信任边界；Decision-Log 区分已批准决定与未批准回溯提案；Environment 只保留最近有证据的运行快照、挂载/权限/入口和恢复点；Agent-Rules 仅保留 SecondBrain 专属边界并引用中央规则。
- Environment 原部署/回滚/验收流水已逐段核对在本 Progress-Log 的对应日期条目中（D071、D074、D075、D076）；Architecture 中被移除的阶段实施证据也由这些历史记录承接。没有删除唯一历史事实。所有旧 Progress 记录均保留为当时快照，不视作当前运行证明。
- 最近记录的生产 App 快照仍是 `9962001` / `secondbrain-app:d076a1.1-9962001`；本轮未现场访问 NAS，故当前运行态标 `UNKNOWN`。D076 Organizer 开发版本未部署，执行器仍因模型适配器硬输入/费用能力门槛不满足而未启用。
- 文档治理仅修改六份正式文档；未改业务代码、NAS、Hermes、网络、权限、真实业务数据或 Codex-Governance。

## 2026-10-15 — D076 Unified Capture / Review 功能恢复核验（本地）

- 本地 `main` HEAD 与实时 `origin/main` 均为 `da8c4bf7d2dd22e6056bedc68882587710a456cc`；工作区原先无已跟踪文件修改，仅有未知未跟踪路径 `typescript`，本轮保留且未读取/改动。未访问 NAS、生产服务或业务数据。
- 检查 Unified Capture Composer：文件选择/单文件拖放/图片粘贴、普通文本粘贴、20 MiB 限制、URL/Text/File 请求分流、附件说明、Enter/Shift+Enter 与 IME composition、重复提交保护、收到 `capture_id` 和 `raw_path` 后清空、失败保留文字与附件均有实现及定向测试覆盖；无可复现代码缺陷。
- 检查 Review：桌面列表/正文独立滚动与移动端详情优先/列表折叠布局、切换回顶、日期排序和未知日期处理、frontmatter 折叠、Markdown 安全渲染、OCR 行序与原始 Review 展开均有实现及测试。Review 页面显示提取内容与来源元数据；原始 PDF 在 Inbox 预览入口新标签页打开，图片在 Inbox 预览弹层显示，文本原件可安全预览，并均提供原件下载和对应 Review 跳转。Review 页没有直接内嵌 PDF/图片预览，用户需从 Inbox 的“预览与详情”查看原件并跳回 Review 对照；此路径待浏览器验收，不据自动化测试宣称体验已验收。
- 验证：前端定向 `capture-flow.test.tsx`、`ReviewMarkdown.test.tsx`、`review-layout.test.ts` **37 passed**；`npm run typecheck`、`npm run build` 通过。构建仅生成本地 `dist`，由忽略规则排除，不构成部署。
- 最短浏览器验收：在已登录的 63013 桌面端从 Chat 切换到“收录”，输入一段无敏感测试文本并提交，确认成功提示后输入框为空；在手机 Safari 重复一次文本收录。随后 Inbox 对一条既有 PDF/图片点“预览与详情”，核对原件显示/下载及“查看 Review”跳转；在 Review 检查正文、来源日期、OCR 核对提示与移动端阅读/列表展开。若需验证文件拖放/图片粘贴和真实 PDF OCR 质量，使用无敏感、可丢弃样本并由用户自行确认可创建相应 Raw/Review 记录。
- **状态：** 代码检查/自动化和构建通过；没有修复项。生产部署状态未在本轮复核，按既有 2026-10-15 快照记录为 `UNKNOWN`；用户浏览器验收未执行/未通过。D076-A 真实 PDF OCR 质量、桌面与手机交互仍须按上述步骤验收；Organizer、安全门与运行状态不在本轮范围。

## 2026-10-15 — D076 Organizer 本地 ModelAdapter 接线与闭环验证

- 基于 `727941254ad2d77f76df3847702554a9212904ee`。确认既有 `OrganizerRunner` 已统一承载手动 `/run` 与定时 `tick`，并共用文件锁、游标、作业恢复和 Review immutable-write；`SiliconFlowOrganizerModel` 已有 DeepSeek-V4-Flash 候选及无工具请求实现，但能力声明不满足硬输入/输出 Token 与硬成本门槛，故既往由 Core 工厂固定传入 `None`。
- 增加 Core 配置构造器：默认 `SB_ORGANIZER_MODEL_ENABLED=false`，不读取 Secret、不创建适配器；显式启用时默认候选为 `deepseek-ai/DeepSeek-V4-Flash`，Secret 仅从 `SB_ORGANIZER_API_KEY_FILE` 指向的私有文件读取。配置/接线不绕过 Runner 门禁：当前 SiliconFlow adapter 仍不可执行，真实手动/定时路径 fail closed；Core 启动不会因此启动定时循环。默认 Organizer 设置仍保留已批准的每 4 小时间隔/固定时间配置，不代表模型执行已启用。
- 本地 Mock/Synthetic 验证覆盖新增消息、分类和跨会话重复合并、Review 草稿及游标/作业状态、首次基线跳过旧历史、无新增跳过、跨会话增量、Review 写入中断后用已保存模型结果恢复、人工编辑保护、未知模型结果持久化并禁止重试、手动/定时共用执行器与并发文件锁，以及停用计划任务。未连接真实 Hermes、未读实际 SecondBrain 内容、未读取真实凭据、未调用 SiliconFlow API、未启动常驻 scheduler。
- 验证：Core 相关测试 **76 passed**（App/Core auth、Capture、Web App BFF、Organizer 配置/Engine/Synthetic E2E、SiliconFlow adapter）；Python 模块编译及 `git diff --check` 通过。一个 Starlette/httpx TestClient 弃用警告，不影响结果。
- **状态/阻断：** Organizer 已形成可运行的本地合成闭环；手动与定时入口复用同一执行器。真实用户数据仍被阻止：适配器未证明 provider enforceable 的硬输入/输出 Token 和单作业成本上限；此外需用户另行批准真实数据出站、实际模型/供应商费用验证、私有凭据注入及 NAS 部署/验收。Promote 继续关闭、Knowledge RO、Private 隔离；本地配置未改变生产。

## 2026-10-15 — D076 Organizer Core 受控软预算门禁

- 按用户批准的风险取舍，移除 Organizer 启用必须证明供应商硬输入 Token / 单作业硬成本的依赖。Core 现以文件锁保护手动与定时共用执行器，并在发送前原子持久化额度预留：每作业 3 次、Asia/Shanghai 每日 12 次、月估算 ¥10；请求体最多 16 KiB、本地输入估算最多 6,000 Token、输出最多 1,200 Token、单并发、45 秒、无自动重试。预算、每日计数、usage/估算成本、作业/游标均写入现有私有状态文件；没有新增数据库或服务。
- 预算费率采用官方 DeepSeek-V4-Flash 模型页当前价格乘以固定汇率/安全系数作本地估算。预估、供应商 usage 与结算账单分开保存和说明；未知响应保留完整预留，暂停作业且不得自动重发。已保存模型结果可恢复写 Review；未确认模型、参数不兼容或请求过大则停止，不切换模型。模型 opt-in 默认 false，Scheduler 有单独默认 false 开关；设置每 4 小时或固定时间不启动后台循环。
- 验证范围为合成 Hermes Source 和 `httpx.MockTransport`，覆盖正常 Adapter 调用/usage、预算限制、每日并发预留、重启持久化、超时未知状态、无新增跳过、已有流程恢复/人工编辑保护、手动与 Scheduler 共用执行器，以及默认关闭与 Scheduler 独立门禁。未连接真实 Hermes、未读取用户内容或真实 Secret、未调用真实 SiliconFlow API、未启动常驻 Scheduler、未部署 NAS。Knowledge 写入、Promote 与 Private 边界未改变。
- 验证：Organizer 配置、Engine、Synthetic E2E、SiliconFlow MockTransport 及既有 Promote 关闭/鉴权边界测试 **55 passed**；Python `compileall` 与 `git diff --check` 通过。Starlette/httpx 出现既有弃用警告，不影响测试结果。
- **状态：** 本地代码与必要文档完成；Commit/Push 状态按本轮交付报告核验。生产未部署、未启动常驻 Scheduler、未调用真实 API，用户浏览器验收未执行。真实用户数据启用仍需另行授权数据出站、专用凭据安全注入、模型账户/参数兼容性核验、用户在供应商控制台核账，并单独批准生产部署与验收。软预算不提供供应商级硬费用封顶。

## 2026-10-15 — D076 SiliconFlow 合成数据最小真实联调

- 使用专用仓库外密钥文件与进程级模型 opt-in；本地全局配置未改，Scheduler 明确关闭。仅向 `deepseek-ai/DeepSeek-V4-Flash` 发送 1 次人工合成 Hermes 消息，无真实 Hermes/SecondBrain 数据、Private、Knowledge、NAS 或生产配置访问。
- 真实响应完成 Organizer 闭环：`todo` 分类，生成 1 个 `pending` Review 草稿，来源 `synthetic-session-001` / `synthetic-user-001`；作业状态 `completed`，游标从 0 推进至 1。供应商 usage：prompt 197、completion 79、reasoning 0、total 276；按公开最高时段价 ¥3/M 输入、¥9/M 输出得本地费用估算 ¥0.001302，**不是供应商账单**，实际账户结算待控制台核验。
- 官方 [Chat Completions 参数文档](https://docs.siliconflow.cn/docs/api/chat-completions-post) 核实 DeepSeek-V4-Flash 支持 `enable_thinking`，请求仅对该获准模型设置 `false`；[价格公告](https://docs.siliconflow.cn/docs/release-notes/overview) 显示自 2026-09-01 起分时计价。相应将本地预算估算费率改为公开最高时段价，避免沿用过低旧值。单次联调另有 ¥5 本地估算预检及单 HTTP 尝试门禁。供应商模型可用性由本次成功响应确认；账户实际折扣/券抵扣与账单金额未核实。
- 首次本地 harness 的同步 HTTPX request hook 在异步 hook `await` 阶段发生 `TypeError`，HTTP 传输尚未开始；Runner 保守持久化为临时 `unknown`，未对该作业重试。修正 hook 后使用新的隔离合成状态成功发出唯一真实 HTTP 请求。没有自动重试或切换模型。
- 验证：Organizer 配置、Engine、Synthetic E2E、SiliconFlow MockTransport 定向测试 **42 passed**；Python `compileall` 通过。生产未部署，Scheduler 未启动，模型仅在该测试进程中启用；全局模型默认关闭、Promote=false、Knowledge RO。用户尚未在 Web App 浏览器验收；真实业务数据启用、生产部署与供应商控制台账单核对仍待分别批准/验收。Review 草稿位于 `/private/tmp/secondbrain-d076-live.ciNbcR/review/AI-Organize-e9722f57a33247b7806dac66a484a5e1-01-522de94504.md`。

## 2026-10-15 — D076 Organizer 模型配置后台化（本地）

- 设置页增加 SiliconFlow 配置、唯一可运行候选 `deepseek-ai/DeepSeek-V4-Flash`、API Key 新增/替换/删除、模型与 Scheduler 独立开关、4 小时/每日固定时间计划、预算/请求额度及已有运行状态。两个执行开关默认关闭；Scheduler 配置只在后续 Core 启动时生效，保存模型配置不会启动它或整理作业。
- Core 复用 App 会话和 `automation.settings.read/write` 授权，将无密钥模型设置、密钥独立写入现有私有 `ai-organize` 状态目录；密钥文件权限 `0600`，接口仅返回 `api_key_configured`，无读取/回显 API。模型 ID/provider 由 Core 严格校验。连接测试 API 明确标识为本地 Mock 配置检查，不访问 SiliconFlow，也不验证真实 Key。
- Organizer 状态补充每日剩余请求数和月度估算余额。保留原预算预留、执行器并发锁、作业/游标、Review 路径；不改变 Knowledge 写入、Promote、Private 边界。本轮未读取已有真实 Key、未真实 API 调用、未读真实 Hermes/业务内容、未启动 Scheduler、未部署。
- 验证：Core Web App BFF、Organizer Engine、合成 E2E、SiliconFlow MockTransport **49 passed**；Core 既有权限/Promote 边界 **14 passed**；Core `compileall`、前端 `typecheck`、Vite build、`git diff --check` 通过。测试覆盖登录拒绝、非法模型拒绝、密钥响应脱敏/权限/删除、设置重读与 Mock 测试零 Hermes HTTP 新调用。系统 Python 缺少 FastAPI/httpx，改用仓库 `.venv` 成功验证。
- **状态：** 代码/文档仅本地修改，待提交推送；未生产部署、未真实联调或用户浏览器验收。上线前至少需用户审阅并部署批准、在生产受保护 Core 状态中配置独立凭据、明确批准 Scheduler 和真实数据出站策略，并浏览器验收设置/Key 管理/Mock 测试及预算显示；供应商账单仍须控制台核对。软预算不是供应商硬费用上限。

## 2026-10-15 — D076 Organizer 配置交付复核

- 对照当前页面、Core API、控制存储和 Runner 复核：仅 `deepseek-ai/DeepSeek-V4-Flash` 可选；API Key 单独保存在 Core 私有状态目录、0600 文件中，响应仅报告配置状态；应用会话和同源校验仍生效。配置更新不发模型请求或启动 Scheduler；模型与 Scheduler 开关独立，默认关闭。连接检查为本地 Mock，无供应商请求。
- 设置页补充费用说明：当前 Mock 不产生供应商费用；未来真实连接测试可能计费，需另行授权后才开放。Review 仍为输出目标，未改变 Knowledge、Promote、Private 边界。
- 验证：Organizer 配置/Engine/合成 E2E 31 passed，SiliconFlow MockTransport 11 passed，Core BFF 11 passed，Core 审批/权限边界 13 passed（合计 66 passed）；前端 typecheck/build 通过，Core `compileall` 与 `git diff --check` 通过。测试仅使用合成数据和本地 Mock；未读真实 Key、未访问真实 Hermes/业务内容、未调用真实 SiliconFlow、未启动 Scheduler、未部署。
- **状态：** 源码与文档在本轮提交并推送；生产未部署，用户浏览器验收待完成。真实业务数据启用仍需用户单独批准部署、真实数据出站、受保护生产凭据和 Scheduler 策略；供应商结算需在控制台核对。软预算不是供应商硬费用上限。

## 2026-10-15 — D076 Organizer App-only 生产部署

- 部署来源为 GitHub `main` / `origin/main` 的 `b34319af0b928ef6781b9ff4c0cc4ab8bb80c1c0`。构建输入由该提交的 `git archive` 提供；工作区未跟踪 `typescript` 保留且未纳入构建。部署前复核了相对生产 `9962001` 的代码差异，未发现新增容器、挂载、权限扩大或自动启动模型/Scheduler 的路径。
- 创建并校验 App-only 快照 `/volume1/docker/secondbrain/rollback/d076-organizer-predeploy-20261015T145538Z/`：目录 `0700`、文件 `0600`，清单校验通过；不含密钥或业务文件内容。构建镜像 `secondbrain-app:d076-organizer-b34319a`，Image ID `sha256:6070c61789737bf64b57d7aab726c4bcee20564f2e6df5584344dcc568d9196f`。正式 Compose 仅修改 App 的 build context 和 image 标签；部署使用限定服务的 `up -d --no-deps --force-recreate secondbrain-app`，未重建/重启 Hermes。
- 部署后 App 容器 `f3da36a01343e764ac051d81c99fac7e6186c947629dd312301c8547e28c3f82` 为 healthy；Hermes 保持原容器 `f6703ca3e3d41856b6e35348f28cd1c7f833ffb9ab31b19e958656540eed8ac6`、镜像及启动时间，状态 running（未配置 healthcheck）。Compose SHA-256 为 `93fd215b319864d42d8f2223946329f38217cfa7e954b30069f9850eb785398d`。
- HTTPS smoke：health 200；未认证 Organizer 设置 API 401；App 登录/session 200；Chat capabilities 200；Inbox 200（只输出条目数 1）；Review 列表 200（只输出条目数 22）；Organizer 设置 API 200，模型为 `deepseek-ai/DeepSeek-V4-Flash`、模型开关 false、Scheduler false、Key 未配置；连接检查 API 200，标记 `local_mock`，无 SiliconFlow 请求。未读取 Hermes 会话/消息，未调用整理接口，未调用真实模型。生产 `SB_PROMOTE_ENABLED=false`；Knowledge RO、Private 未挂载；Organizer 状态目录权限为 `0700`，无设置文件或 Key 文件。
- 本次未重跑此前已通过的代码测试；最近针对该提交的结果为 Organizer/Core/权限测试 66 passed、前端 typecheck/build 通过、Core compileall 与 diff check 通过。此次生产验证为只读 HTTP smoke 与运行状态检查。
- **状态：** App-only 生产部署完成，Organizer 设置与 Mock 检查接口在线；真实自动整理、Scheduler、Promote 均未启用。等待用户在浏览器验收页面呈现与交互；供应商实际账单仍需控制台核账。若需回滚，先复验上述快照和旧镜像，再仅替换 App 镜像并重建 App，保留 Core state 与 Hermes。

## 2026-10-16 — D076 Organizer 设置页浏览器验收问题修复（本地）

- 浏览器反馈后检查前端按钮与 Core `/connection-test`：受保护 Core 路由正常返回本地 Mock 配置结果，不调用供应商或执行 Organizer；前端原实现没有 loading、异常捕获和明确结果区域，网络失败会静默表现为无反馈。现加入进行中、成功及失败提示；成功文案明确未连接 SiliconFlow、无供应商费用，失败展示服务端原因或可读网络/HTTP 提示。测试验证按钮只调用 Mock 端点、不调用 `/run`。
- 设置页收拢为模型配置、自动整理、预算与运行三组；桌面双栏/预算横跨整行，窄屏单栏；统一控件尺寸并减少留白。服务商和唯一支持型号 `deepseek-ai/DeepSeek-V4-Flash` 显示为只读值，不再呈现单选下拉框。未改 Core 鉴权、Key 存储、预算门禁或任何 API 调用范围。
- 验证：新增前端 `organizer-settings.test.tsx` **3 passed**，覆盖 Mock loading/success、授权/API 错误、网络异常、唯一模型呈现、模型/Scheduler 默认关闭且不调用 Organizer run；`npm run typecheck` 与 `npm run build` 通过。未部署 NAS、未调用真实 API、未使用 Key、未读取 Hermes/业务数据。
- **状态：** 代码修复待 Commit/Push；尚未部署。生产仍为 `b34319a`；需部署后由用户在浏览器验收最终视觉布局和交互。

# 2026-10-16 — D077 Issue #14 Hermes API 工具限制与浏览器体验准备

- 按 Issue #14 只核验并调整 SecondBrain Hermes 与相关文档。修改前保存 /volume1/docker/secondbrain/hermes/data/config.yaml 到 /volume1/docker/secondbrain/rollback/d077-issue14-api-toolset-20261016T1334Z/config.yaml.before；原配置 SHA-256 cdee7b148aa314536e24986f8f0dd57ea5999350e46c6b3bfd65c25a37eecac9，备份属主/权限 root:root / 0600，目录 root:root / 0700。
- v0.22.2 原生配置解析确认 API Server 工具集合原为 file, skills, terminal, vision；terminal.backend=local，因此普通 Chat/Run 确有本地命令执行能力。仅在 Hermes profile 加入 platform_toolsets.api_server: [file, skills, vision]，不影响 CLI 配置或其他 NAS 服务。重启后固定版本 resolver 实际结果为 file, skills, vision，terminal 已从 API Server 工具集合移除；文件、Skills 和视觉工具仍在。File tool 的 HERMES_WRITE_SAFE_ROOT 仍只包含三个 Capture 根；Knowledge 挂载只读，Private 未挂载，Promote 关闭。
- 安全路径核对：Agent/Gateway 进程 UID/GID 1026:100、有效/可用 capability 为 0；容器非 privileged。/proc/self/environ 被设备路径检查拒绝；/opt/data/config.yaml 本身不在 read denylist，但固定版本把 Hermes Home 下的 config.yaml 标为 secret-bearing source，并在 file-read YAML redaction 中处理凭据字段。仅用合成 api_key、secret、password_hash 标记验证三项值均被脱敏；未查看、输出或改写任何真实凭据值。没有通过模型实际调用工具。 Hermes file tool 没有通用 read-root allowlist；/opt/data/sessions 目录对 worker 可读/遍历，合成 Session 路径不被 read denylist 拒绝。未列目录或读取真实 Session 内容。这是浏览器真实模型体验的阻断项；需要对 Session 路径增加最小读取拒绝或等效官方隔离。
- 仅重启 secondbrain-hermes。重启后 Hermes 容器运行、API 8642/health 返回 200、Dashboard 9119/ 返回登录重定向 302；Core Docker health 为 healthy，宿主 127.0.0.1:9120 使用受信 Host 192.168.3.27 请求 /health 返回 200，Memory/Learning flags 仍 true，专用记忆目录 1026:100 / 0700 且无文件。正式浏览器入口 https://zxwan520.com:63013/health TLS 校验成功并返回 200。没有创建 Session/Run，没有模型请求、真实数据处理或付费调用。
- 浏览器体验准备：使用已验证入口登录后打开 Chat，创建新 Session。先自然表达合成偏好“技术问题我更喜欢简短回答，最好用三条要点”，不要说“请记住”；新建 Session 后问一个相关但不提示回忆的问题，观察是否自然采用偏好；再纠正为“两条要点”，另开 Session 验证新规则生效且旧规则不再出现；最后提一个无关问题观察是否避免主动提及偏好。全程只用虚构内容。真实模型行为与费用未由本次核验覆盖，执行前用户需确认当前模型/费用。
- 状态：危险的 API local-terminal 工具已移除，必要工具和记忆配置保持；本次不代表真实模型学习质量验收。在补齐 Hermes Session 文件读取边界前不进行真实模型体验；之后还需用户选择模型并确认费用。配置回滚点如上；回滚时恢复 config.yaml.before 到 Hermes 数据路径、保留 1026:100 / 0640，然后只重启 Hermes。

## 2026-10-17 — D084 PR #49 App-only 受控部署（一次授权）

- 按 Issue #44 用户授权评论 #6233322671 部署 PR #49 合并版 App，Hermes/Guard 保持不变。构建输入固定为 merge commit fa2ad4126b5e9acb6983fdae8445a4fb0ebdda79 的 web-app 归档（SHA-256 8dbb4d78f523ee69e59d214a6430528b299e922141a8af36ae778af06423c4d7），使用 web-app/Dockerfile.app 和 web-app 上下文。前端 npm run typecheck 与 npm run build 通过，静态根 /app/static 含 index.html 和 Vite assets；npm ci 报告 4 项 audit findings（2 low、2 moderate），没有升级依赖。
- 在 NAS 隔离容器（network none、read-only rootfs、仅临时 tmpfs、无数据挂载）用 ASGI TestClient 验证 /chat 200 text/html、引用的 JS/CSS 各 200，匿名 GET /api/chat/sessions 401 application/json。没有模型调用或生产数据访问。
- 构建镜像 secondbrain-app:pr49-fa2ad412-full，Image ID sha256:1c7ed4cb953951eb2ab8691516651d170171305af6172326174e64f4115dd6ca。持久构建源目录 /volume1/docker/secondbrain/app-build-source-pr49-fa2ad412/web-app 与构建输入逐文件一致。
- 部署前当前 App 为 d084-c8a2b348、Compose SHA-256 33f45f5cdca72cea05ddd21a265d129bc770684dfb6b1b9d3790cb12725fa0b9；rollback/d084-pr49-app-20261017T100900Z 的 SHA256SUMS 已复核通过，旧镜像仍存在。仅修改 Compose App build context/image；新 SHA-256 28636decfc08e47f57d2a671c68ecc6861cdf7653b860f12f73c020dcc1d6e06，属主/模式 1026:100 / 0640。Compose config 校验通过。
- 仅执行 docker compose up -d --no-deps --force-recreate --wait --wait-timeout 120 secondbrain-app。App 容器 272b9fee7e62cf4b6b9c39f82d8c1e2eeceffaee82215a9cf34dc35098570601 在 120 秒内 healthy，RestartCount 0，用户 1026:100。生产直连 GET /health 与 /chat 均 200；2 个静态资源均 200；匿名 Chat sessions API 返回 401 JSON。
- Hermes 容器 057324a9e438969320e84d7c3cbad58e3f010637d7dd00d5967123b034eada79、镜像 ID sha256:b99b1762631846d5ed3f8648ccc2c7ef2625b004234bbf276add2f8855357e9a、启动时间和 RestartCount 均未变化。Journal、Task、chat-activity 根仍为 1026:100 / 0700；Review 与 Capture Inbox RW、Knowledge RO、Core state RW；未发现 Private 挂载；SB_PROMOTE_ENABLED=false。没有扩大权限、写入 Journal/Task 业务数据或清理资产。
- 生产登录态业务验收未完成：Edge 自动化在浏览器扩展界面阻断；没有提交表单、创建 Session 或写入记录。因而 Journal/Task 系统操作卡、刷新恢复、跨 Session 隔离和幂等重试保持 NOT VERIFIED。没有调用真实/付费模型。后续需恢复浏览器自动化后，使用新空白 Session 与唯一合成数据续验；不要读取或修改现有私人会话和真实 Journal/Task 内容。
- 代码提交/PR #49 已在 main；本日志和 CURRENT、Environment-Baseline 的本次事实更新单独提交，生产镜像 Push 不涉及 GitHub 代码变更，也不代表浏览器用户验收。

## 2026-11-04 — Chat 有限 UAT 最后一项隔离集成验证

复用此前真实 AIAgent API Run 草稿，固定 Hermes d923a5eb 与已验证补丁，在隔离 HERMES_HOME 中 discovery 加载 D078 Guard。仅替换 OpenAI 客户端返回值，保留真实会话循环、dispatcher、Hook、文件 handler、Gateway approval 与 aiohttp API/SSE。原先单项 PASS 的提前检查已移除：它曾在模型调用前检查文件；新测试等待 approval.request 或 Run 终态。

三场景 **3 passed in 12.13s**：deny / once / skills。记录原 path_guard 调用及返回值；审批前文件不存在，真实 POST approval deny 后文件仍不存在；once 对照通过真实文件 handler 写入 synthetic；Skills 原 Guard 返回 skills_write_gate，未发审批、无文件，Run 正常结束。独立 Reviewer 只读复核通过，未发现阻断性假阳性。Python 3.12 隔离环境补充 snowballstemmer，并将 Path.home 定位到合成用户目录以满足固定源码的真实 home I/O 禁止器；HERMES_EXEC_ASK=1 对应实际 Gateway 启动行为。无真实用户目录访问、外部模型、生产更改。

状态推进 READY_FOR_LIMITED_CHAT_UAT；真实模型回复与浏览器刷新恢复由用户验收，跨会话记忆 #30 未通过。脚本复制到固定 Hermes tests/gateway 后运行 pytest；设置 SB_D078_PLUGIN_SOURCE 指向本仓库 web-app/hermes-agent/d078-guard。
