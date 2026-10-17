---
created: 2026-09-28
updated: 2026-10-17
status: current
type: environment-baseline
---
# Environment Baseline

## 最新运行核验（2026-10-17，PR #49 App 部署尝试后已回滚）

- PR #49 merge `fa2ad4126b5e9acb6983fdae8445a4fb0ebdda79` 的候选 App 镜像 `secondbrain-app:d084-pr49-fa2ad412` / Image ID `sha256:9858d618ab6a7a99dfe2c6cf38fa4989351c32c4405fc64b0959f73bf07d6f45` 曾短暂运行并在 30 秒内健康；浏览器导航“对话”到 `/chat` 显示 `Not Found`，按授权立即回滚。候选镜像当前非运行态，保留在本机供后续调查，不视为部署成功。
- 当前 App 已恢复为 `secondbrain-app:d084-c8a2b348` / Image ID `sha256:ef60d7de4ff3f3b3edc49cb0d565c45df3b996fe7014fc49ff3446ead7592feb`，容器 ID `15f17a917c992d85c534c2bfab13caf237d0b03a006456138520c88faf9fcbd0`，running/healthy、RestartCount 0，用户 `1026:100`；NAS loopback health HTTP 200。旧 App 在回滚后 15 秒内恢复健康。
- 正式 Compose 已从独立快照恢复，SHA-256 `33f45f5cdca72cea05ddd21a265d129bc770684dfb6b1b9d3790cb12725fa0b9`，属主/模式 `1026:100 / 0640`；当前 App 与 Hermes tag 指向原部署。App 回滚材料保留于 `/volume1/docker/secondbrain/rollback/d084-pr49-app-20261017T100900Z/`，目录 `0700`，快照文件 SHA256SUMS 校验通过。快照记录了部署前 App/Hermes 镜像身份和 Compose 哈希。
- Hermes 容器仍为 `057324a9e438969320e84d7c3cbad58e3f010637d7dd00d5967123b034eada79`，镜像 `secondbrain-hermes:v0.22.2-failclosed-84d1cbaf` / Image ID `sha256:b99b1762631846d5ed3f8648ccc2c7ef2625b004234bbf276add2f8855357e9a`，running、RestartCount 0，启动时间未变。本轮没有对 Hermes/Guard 进行写入或重建；容器身份与部署前一致。
- 既有 Core state、Journal、Task 根权限保持 `1026:100 / 0700`，现有 Journal/Task 文件 `0600`。候选 App 初始化时在现有 Core state RW 挂载中创建了空的 `chat-activity` 私有目录，权限 `1026:100 / 0700`；其目录和部署前快照均按“不清理”规则保留。没有新增挂载、权限扩大或真实 Journal/Task 写入。
- 本次生产验收在 Chat 导航处停止；没有执行生产 Journal/Task 合成写入、刷新恢复、跨 Session 隔离或幂等重试。因此这些验收项仍为 **NOT VERIFIED**；本地测试记录沿用 Issue #44 既有证据，没有重跑完整测试。

## 历史 Hermes 核验（2026-10-17，PR #18 / fail-closed overlay）

- PR #18 squash 合并至 main，merge commit `84d1cbaf7daebb188fc93c369fba4a59b80895e5`。Hermes 基于上游 v0.22.2 源码 Commit `d923a5eb487a17c0a68801bba9ef0f56c81040a8` 与补丁 SHA-256 `b53818487205733039378a8e3c7218cc298eca1c39e1a34dec997dd306f855b0`，从官方 amd64 镜像 digest `sha256:a11574b7fe8e1631d7d88d556677dac693bc058abf558cdeb899155688c1bf05` 构建一文件 overlay。NAS 当前 Hermes 镜像 tag `secondbrain-hermes:v0.22.2-failclosed-84d1cbaf`，Image ID `sha256:b99b1762631846d5ed3f8648ccc2c7ef2625b004234bbf276add2f8855357e9a`，平台 linux/amd64。
- Compose SHA-256 `6d7b1be1abb4479b93e5cebc473e2f20ba6bddb6bd62ea5019322ef260908818`，属主/模式 `1026:100 / 0640`。仅 Hermes image 引用变更；Hermes 单服务以 `--no-deps --force-recreate` 重建，未触碰 App/Core 或其他服务。当前 `secondbrain-hermes` running，RestartCount 0；API `/health` 200，Dashboard 9119 可达并重定向登录（302）。重建后曾观察到 API 尚未监听，持续等待后服务恢复，无二次重启/回滚。
- Hermes `Plugin Doctor` 对 `secondbrain-d078-guard` 报告 manifest/import/registration 成功、注册 1 hook。Profile 有 `file,skills,vision`，无 terminal；Skills write approval=true、approval mode=manual。NAS 合成 `docker exec` 验证：敏感 Session 文件 read 被拒、允许的合成业务文件路径通过、Skills 只读工具通过、注入 dispatcher RuntimeError 被 fail-closed 阻断；零模型调用、零 Session 写入。生产 API 未创建 Session/Run。
- 安全边界重核：Private 无挂载；`/secondbrain` 主挂载 RO，Knowledge 主目录 RO；既有 `/knowledge-assets/00-Inbox` Capture 专用 RW 子挂载保持不变。Promote false。Core 记忆根 `/volume1/docker/secondbrain/core-state/personal-memory` mode 0700、owner `1026:100`，0 files/0 bytes，mtime 与升级前记录相同；未读取内容。API Terminal 保持关闭。
- 回滚点 `/volume1/docker/secondbrain/rollback/d078-hermes-hook-failclosed-20261016T173140Z/`：目录 0700，`compose.yaml`（SHA-256 `d2865340ab82fec7086048c55798b3e1c29dabfca3d8999d2ab36b5e94e0c4c9`）、旧 `plugin.yaml`、恢复元数据均 0600。旧官方 Hermes image ID `sha256:02e7aa0e84123fa0e9b22686e7a2bfb7d85fd59821d4d28812a3e07f3061cf41` 保留在 rollback tag `secondbrain-hermes:rollback-v0222-official-20261016T173140Z`。回滚前应重核快照并只恢复 Hermes/manifest；不可回滚 Core state、D077 JSONL 或 App。
- 上述是运行态与合成权限验证，不代表真实模型、真实个人数据或浏览器学习体验已验收。此前 D078 Stage 1 信息保留在下方历史快照段，凡与本节冲突以本节为当前状态。

本文件记录最近一次经验证的运行快照，并非实时监控。顶部是 PR #49 App 尝试回滚后的现行 App/Compose/Hermes 运行事实；Hermes overlay 段记录此前已核验的 Guard 配置与 Hook 证据。本轮 Hermes 容器未发生变化，但没有重新读取其插件文件。下一次操作必须重新只读核验。Private 与凭据正文不入库。旧阶段恢复说明和历史资产审计均移交 `Progress-Log.md` 与 Issue #14，不作为现行运行或恢复指令。

## 常态运行路径与尚待验证的边界

## NAS 与 Compose

- NAS：Synology DS920+，DSM 7.4.1 Build 90080；LAN 地址 `192.168.3.27`。本机与路由器网络设置不由 SecondBrain 文档治理修改。
- 正式 Compose：`/volume1/docker/secondbrain/compose.yaml`；Compose Project `secondbrain`；Docker 网络 `secondbrain_default`。PR #49 App 尝试后已恢复到部署前 SHA-256 `33f45f5cdca72cea05ddd21a265d129bc770684dfb6b1b9d3790cb12725fa0b9`，属主/权限 `1026:100 / 0640`。此次尝试仅替换 App image tag，随后由已校验快照恢复；网络、挂载与其他服务未改。
- 项目目标为两个服务：`secondbrain-hermes` 与 `secondbrain-app`。Container Manager GUI 曾出现旧容器行/旧定义缓存；最后已记录状态为管理界面定义未完成对齐。当前 GUI 状态未在本次核实，标记 `UNKNOWN`；这是部署管理风险，不改变 Docker 运行态记录。

## 历史 Stage 1 容器快照（已被 2026-10-17 patched overlay 取代）

| 服务 | 容器 ID | 镜像 / Image ID | 状态 | 入口/说明 |
|---|---|---|---|---|
| `secondbrain-app` | `674e7aa05af22a485ec9d769c370dddd0cda88c45d3e9412ee4c23cf3a54173e` | `secondbrain-app:d078-1d92242` / `sha256:3cfeeb01e9c1772c59bfca394722b22b9e87c7ce8d098a9ee5742ac530d41487` | healthy；启动 `2026-10-16T15:58:07.666779883Z`；运行身份 `1026:100`；只读 rootfs、非 privileged、no-new-privileges | 宿主 `127.0.0.1:9120`；Core source 为 main merge commit `1d922422b419f7c6773df1849ce7a7c130392006`（build input PR #16 head `d78a6bfd376c97043ffab0d5fc18371baf33148a` 的 tracked `web-app` archive） |
| `secondbrain-hermes` | `2cf7cec6d44dc49de37f0fb16c36f8e71f4bea5747aeecc2782efabf09eeb86f` | `nousresearch/hermes-agent@sha256:a11574b7fe8e1631d7d88d556677dac693bc058abf558cdeb899155688c1bf05` / `sha256:02e7aa0e84123fa0e9b22686e7a2bfb7d85fd59821d4d28812a3e07f3061cf41` | running；v0.22.2 / upstream `d923a5eb487a17c0a68801bba9ef0f56c81040a8`；Stage 1 restart `2026-10-16T16:27:20.362558655Z` | API 8642 health 200、仅容器网络；Dashboard 9119 health 200，仅映射 `192.168.3.27:9119` |

该表中的旧 Hermes 容器 ID、镜像及 Plugin Doctor 告警仅属于 Stage 1 历史事实；**现行 Hermes 身份和 Hook 状态一律以上方最新核验为准**。历史演变详见 `Progress-Log.md`。

## 挂载与权限边界（最近记录的实际配置）

| 容器 | 数据/用途 | 容器路径 | 访问模式/身份 |
|---|---|---|---|
| App | KnowledgeAssets `00-Inbox` Raw | `/knowledge-assets/00-Inbox` | RW |
| App | SecondBrain `10-Review` | `/review` | RW |
| App | `20-Knowledge` | `/knowledge` | RO |
| App | Core 私有 state | `/var/lib/secondbrain-core` | RW；目录独立、最小权限 |
| App | Personal Memory JSONL（Core 唯一权威） | `/var/lib/secondbrain-core/personal-memory` | `1026:100 / 0700` 专用子目录；仅 App 可写；测试结束后为空 |
| App | 应用 Secrets | `/run/secrets/...` | RO；UID/GID `1026:100` 持有受限文件 |
| Hermes | SecondBrain 根 | `/secondbrain` | RO |
| Hermes | `00-Inbox`、`10-Review`、KnowledgeAssets Inbox 捕获根 | `/secondbrain-write/00-Inbox`、`/secondbrain-write/10-Review`、`/knowledge-assets/00-Inbox` | 三个捕获目录 RW；safe root 只列出这三项 |
| Hermes | `20-Knowledge` | 无 RW 子挂载，仅经 `/secondbrain` 读取 | RO |
| 两者 | Private | 无挂载 | 不访问 |

App 最近记录的身份为 UID/GID `1026:100`，只读根文件系统、独立 `/tmp` 64 MiB tmpfs。`SB_PROMOTE_ENABLED=false`；Hermes STT 默认关闭。以上值须在下一次生产操作前重新 inspect，不可仅靠文档视为当前事实。

Organizer Core 私有状态位于现有 Core state 挂载内的 `ai-organize` 子目录，UID/GID `1026:100`、权限 `0700`。本次 `model-settings.json` 与 Organizer API Key 文件均不存在，运行状态接口确认模型与 Scheduler 均关闭；配置变更不会自行启动任务。没有新增挂载或放宽权限。

## 网络与浏览器入口

- App 通过 Compose 内部网络访问 Hermes；Hermes API `8642` 不映射到宿主端口。
- Issue #12 曾观察到 API 工具定义包含 terminal；Issue #14 通过 Hermes v0.22.2 原生 platform_toolsets.api_server 设置移除 API Run 的 terminal。重启后固定版本 resolver 实测 API Server 工具集合为 file, skills, vision；terminal.backend=local 仍是 CLI 配置，但 API Server 请求不获 terminal 工具定义。Docker 网络仅附加 App 与 Hermes，API 8642 不发布宿主端口。
- Hermes 的策略路由、NAS 双网卡和实际公网出口不在本次检查范围；最新实时路由证据为 `UNKNOWN`。不要仅凭公网 IP 地理位置推断是否经过 `wg0`。
- File/Skills 的现行安全边界：2026-10-17 patched overlay 已通过合成 Session 路径拒绝、允许路径访问、Skills 只读与 Hook 异常阻断；API Terminal 未开放。旧版无路径 guard 的分析只保留在 `Progress-Log.md`，不得作为现网风险结论。真实模型与完整生产 API Run 仍未验收。
- DSM 63012/63013 反向代理的 LAN-only 规则及登录链曾通过部署测试；本次未重验 DSM 配置、证书或外网可达性。不得由入口历史记录推断公网已开放。

## Obsidian 同步边界

- Obsidian 知识/笔记库由 Synology Drive 在 Mac 与 NAS 间同步；最近记录称客户端显示已同步，但双向传播未单独验收。历史 `SynologyDrive stopped` 报告不构成已确认故障；当前客户端连接与 NAS 实际传播状态均为 `UNKNOWN`。此同步只承载知识、笔记与个人资料，不是代码或正式项目文档源。相关历史核验见 `Progress-Log.md`。

## 现行恢复入口

- 当前 Hermes 回滚点：`/volume1/docker/secondbrain/rollback/d078-hermes-hook-failclosed-20261016T173140Z/`。包含原 Hermes Compose、插件 manifest、恢复元数据及固定官方旧镜像 tag；镜像标识与校验和见文件顶部“最新核验”。**仅对 Hermes 定向恢复**，须先重新核验实际配置并取得操作授权；不得回滚 App/Core state、D077 JSONL 或其他 NAS 服务。
- D078 Stage 1、D077 和更早的恢复步骤属于**历史施工证据**，不在本文件提供可直接复制的旧版回滚命令；其原始路径、哈希及复盘见 `Progress-Log.md` 和对应 Issue，不能用作当前自动回滚方案。

## 核验触发与历史导航

容器重建、镜像/版本、Compose、挂载、ACL、Secret、端口、DSM 代理或网络变化后，先重新取得只读运行证据，再更新此处快照。Private 内容与凭据不写入基线。D071 至 D076 的部署、回滚、用户验收和失败复盘按日期记录在 `Progress-Log.md`；其中旧记录保持历史属性，不得用作当前运行证明。
