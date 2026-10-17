# Progress Log

> 本文件按时间保存阶段证据。每条“当前/尚未/未部署”只代表该条记录日期的状态，不覆盖后续结果；最新项目状态只看 `00-CURRENT.md`，最新有据可查的生产快照看 `Environment-Baseline.md`。

## 2026-10-17 — 阶段暂停与文档收口决议（最新）

- 用户明确要求当前阶段**暂停开发，集中更新基线并记录清晰 NEXT**。本轮仅进行 GitHub 文档一致性修订，不改变 NAS、模型、配置、容器或业务数据。
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

# 2026-10-17 — D080 恢复开发与浏览器验收准备

- Issue #25 授权 A 阶段：读取项目规则、D079 最终验收及 PR #24；确认 PR #19/#21/#22/#24 均已合并，当前 main 为 `4afe7ecad7584828c3d3ac6be896b97386c11b02`。原正式 Clone 落后且包含未跟踪 `typescript`，因此在独立临时 Clone 完成文档工作，未改动正式工作区。
- 将 `00-CURRENT.md` 中过时的“DEVELOPMENT PAUSED”现行状态改为 D080 恢复开发；记录 PR #24 本地 FakeHermes 集成覆盖和边界，列出最短合成浏览器验收步骤，并明确生产 Run/模型/预算仍需单独授权。
- PR #24 本地测试已提供零外发认证→Session→Run/SSE→学习→跨 Session 召回证据；纠错/过滤/失败停止由既有定向测试覆盖。本轮未重复 44/15 测试，也未修改生产代码。
- 未做 NAS 写入、生产 Session/Run、模型调用、Secret/真实数据访问或清理。真实 Hermes 自然学习与浏览器效果仍未验证；实际 provider/model/费率未核实，下一阶段最多 5 次 Run 的费用上限仍为 UNKNOWN。
