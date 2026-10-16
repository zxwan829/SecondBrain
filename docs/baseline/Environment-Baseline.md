---
created: 2026-09-28
updated: 2026-10-16
status: current
type: environment-baseline
---
# Environment Baseline

本文件只记录最近一次有证据的运行环境快照、端口、镜像、挂载、权限与恢复入口。它不是实时监控：部署快照于 2026-10-16 Issue #12 核验；API 工具权限、定向重启和健康状态于 Issue #14 更新。不记录任何密钥或明文环境配置。

## NAS 与 Compose

- NAS：Synology DS920+，DSM 7.4.1 Build 90080；LAN 地址 `192.168.3.27`。本机与路由器网络设置不由 SecondBrain 文档治理修改。
- 正式 Compose：`/volume1/docker/secondbrain/compose.yaml`；Compose Project `secondbrain`；Docker 网络 `secondbrain_default`。本次 Stage 1 部署前 SHA-256 `36c1d6cf14643ad41e5c04ec9ac1374b194dc52ebefbbe6dc6c57d1ac3fdd4a2`；部署后 SHA-256 `d2865340ab82fec7086048c55798b3e1c29dabfca3d8999d2ab36b5e94e0c4c9`，属主/权限 `1026:100 / 0640`。Compose 本次只替换 App image tag，未改网络、挂载或其他服务。
- 项目目标为两个服务：`secondbrain-hermes` 与 `secondbrain-app`。Container Manager GUI 曾出现旧容器行/旧定义缓存；最后已记录状态为管理界面定义未完成对齐。当前 GUI 状态未在本次核实，标记 `UNKNOWN`；这是部署管理风险，不改变 Docker 运行态记录。

## 最近已核验的容器快照（2026-10-17 Issue #14 / D078 Stage 1）

| 服务 | 容器 ID | 镜像 / Image ID | 状态 | 入口/说明 |
|---|---|---|---|---|
| `secondbrain-app` | `674e7aa05af22a485ec9d769c370dddd0cda88c45d3e9412ee4c23cf3a54173e` | `secondbrain-app:d078-1d92242` / `sha256:3cfeeb01e9c1772c59bfca394722b22b9e87c7ce8d098a9ee5742ac530d41487` | healthy；启动 `2026-10-16T15:58:07.666779883Z`；运行身份 `1026:100`；只读 rootfs、非 privileged、no-new-privileges | 宿主 `127.0.0.1:9120`；Core source 为 main merge commit `1d922422b419f7c6773df1849ce7a7c130392006`（build input PR #16 head `d78a6bfd376c97043ffab0d5fc18371baf33148a` 的 tracked `web-app` archive） |
| `secondbrain-hermes` | `2cf7cec6d44dc49de37f0fb16c36f8e71f4bea5747aeecc2782efabf09eeb86f` | `nousresearch/hermes-agent@sha256:a11574b7fe8e1631d7d88d556677dac693bc058abf558cdeb899155688c1bf05` / `sha256:02e7aa0e84123fa0e9b22686e7a2bfb7d85fd59821d4d28812a3e07f3061cf41` | running；v0.22.2 / upstream `d923a5eb487a17c0a68801bba9ef0f56c81040a8`；Stage 1 restart `2026-10-16T16:27:20.362558655Z` | API 8642 health 200、仅容器网络；Dashboard 9119 health 200，仅映射 `192.168.3.27:9119` |

App Docker health 为 healthy；Core `/health` 与 App `/` 均 HTTP 200；Hermes API 8642 与 Dashboard 9119 `/health` 均 HTTP 200。D078 Profile 已启用 `secondbrain-d078-guard`，Skills `write_approval=true`、审批 `manual`，API toolset `file,skills,vision`（Terminal 未开放）。插件 Doctor 运行时发现/导入/注册通过，并提示 manifest 缺少 `provides_hooks: pre_tool_call` 声明；合成 Session 路径读与 Skills generic file 写入被拒，Capture safe-root 写入目标允许。上游 Hook dispatch fail-open 风险未通过真实 API Run 验证。Memory/Learning flags 仍 true；memory 根路径 `/volume1/docker/secondbrain/core-state/personal-memory` 为 `1026:100 / 0700`，0 文件；Promote false。Private 无挂载、Knowledge RO。没有新增 Session/Run、没有调用模型；浏览器真模型验收没有执行。

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
- API Server 的 file 工具仍保留，以维持 Capture/Knowledge；有效 HERMES_WRITE_SAFE_ROOT 只有三个 Capture 根，Knowledge 同时是只读挂载，Private 无挂载。Hermes worker 进程 UID/GID 1026:100、CapEff/CapPrm 为 0；容器非 privileged。Hermes file safety 对 /proc/self/environ 返回设备路径拒绝；/opt/data/config.yaml 本身不被 read denylist 拒绝，但 _is_secret_file_arg 将 Hermes Home 配置判为 secret-bearing，file-read YAML redaction 对 credential-shaped 值生效。用合成 api_key/secret/password_hash 值做的离线断言 3/3 脱敏；未查看或输出真实凭据值。该 file 工具没有通用 read-root allowlist；/opt/data/sessions 目录对 worker 可读/遍历，合成 Session 路径不被 read denylist 拒绝。未列目录或读取任何 Session 内容。此项是阻止真实模型浏览器体验的残余权限风险；需要最小 session-path 读取拒绝或等效官方隔离后再开放。
- DSM 63012/63013 反向代理的 LAN-only 规则及登录链曾通过部署测试；本次未重验 DSM 配置、证书或外网可达性。不得由入口历史记录推断公网已开放。

## Obsidian 同步边界

- Obsidian 知识/笔记库由 Synology Drive 在 Mac 与 NAS 间同步；最近记录称客户端显示已同步，但双向传播未单独验收。历史 `SynologyDrive stopped` 报告不构成已确认故障；当前客户端连接与 NAS 实际传播状态均为 `UNKNOWN`。此同步只承载知识、笔记与个人资料，不是代码或正式项目文档源。相关历史核验见 `Progress-Log.md`。

## 恢复入口

- D078 Stage 1 回滚快照：`/volume1/docker/secondbrain/rollback/d078-stage1-20261016T155327Z/`，目录 `0700 root:root`。部署前 `compose.before.yaml` SHA-256 `36c1d6cf14643ad41e5c04ec9ac1374b194dc52ebefbbe6dc6c57d1ac3fdd4a2`、`hermes-config.before.yaml` SHA-256 `a105f96d187067975b1a519cc4a83386284f4b10419835fba2c3b542e082f2e`、`manifest.txt` SHA-256 `7b0ef1040ab654c585a2030680da29661faa7499f4d8e1b333261d1749e54375`，均 `0600 root:root`。构建源码仅为 main commit `1d922422...` 的 PR #16 合并内容；NAS App 镜像 `secondbrain-app:d078-1d92242` Image ID `sha256:3cfeeb01e9c1772c59bfca394722b22b9e87c7ce8d098a9ee5742ac530d41487`，部署前 App 镜像未删除。
- 如需回滚，先重新核验并再保存当前 Compose/Profile；恢复本次 `compose.before.yaml` 与 `hermes-config.before.yaml` 到各自原路径，恢复 Compose `1026:100 / 0640`、Hermes config `1026:100 / 0640`，然后只重建/重启 `secondbrain-app` 与 `secondbrain-hermes`。不回退、不删除 Core state、D077 JSONL、Session、Capture 或其他 NAS 数据；不使用整体 `compose down`。

- Issue #14 API 工具限制回滚点：/volume1/docker/secondbrain/rollback/d077-issue14-api-toolset-20261016T1334Z/config.yaml.before，SHA-256 cdee7b148aa314536e24986f8f0dd57ea5999350e46c6b3bfd65c25a37eecac9；目录 0700 root:root，文件 0600 root:root。回滚前保存当前 Hermes config，再将此文件恢复到 /volume1/docker/secondbrain/hermes/data/config.yaml、属主/模式 1026:100 / 0640，最后只重启 Hermes。Compose 未改。

- 本次部署快照与回滚材料位于 `/volume1/docker/secondbrain/rollback/d077-issue12-authorized-20261016T124238Z/`：目录 `0700 root:root`、文件 `0600 root:root`。包含部署前 Compose（SHA-256 `93fd215b319864d42d8f2223946329f38217cfa7e954b30069f9850eb785398d`）、部署前 Hermes 数据归档、迁移后原 Hermes config、部署候选 Compose、脱敏启动日志、只含布尔值的 Stub 观测、合成记忆 JSONL 与测试摘要；清单验证通过。此前回滚目录 `/volume1/docker/secondbrain/rollback/d077-issue12-v0222-predeploy-20261016T1225Z/` 保留不动。
- 回滚方法：先再保存当前 Hermes 数据和当前 Compose；恢复本次快照中的 `compose.before.yaml` 到正式路径并还原属主/0640，然后只对 `hermes` 和 `secondbrain-app` 执行 Compose `up -d --pull never --no-deps`，使其回到原 v0.21.5 与 `d076-organizer-b34319a` 镜像。若旧版不接受迁移后的 Hermes profile，先保留当前 profile，再参考已校验的部署前状态归档恢复；不得直接覆盖或删除当前数据。Personal Memory 子目录保留，真实使用后不得按测试目录清理。
- 本次 App-only 回滚快照：`/volume1/docker/secondbrain/rollback/d076-organizer-predeploy-20261015T145538Z/`；目录 `0700 root:root`、文件 `0600 root:root`，`SHA256SUMS` 已验证。包含部署前 Compose、Core state 元数据、App runtime 元数据和 App 镜像元数据，不含 Secret 或业务内容。旧 App 镜像 `secondbrain-app:d076a1.1-9962001`（`sha256:55f40951620fb8b7043933c724f66cbf22a2326a961d654d8671e877c212bcd3`）可用于回退。恢复前重新核对快照/镜像，只回退 App，保留 Core state；不得整体 `compose down` 或重启 Hermes。
- D076-A.1 上一 App 镜像 `secondbrain-app:d076a1-55977c8` 及更早镜像按 Progress-Log 的部署记录保留情况为准；本次未核查镜像存量。
- 生产恢复操作须遵循本文件所列最近快照并先重新核对实际 Compose/数据/镜像；不能直接复制含旧 Hermes 定义的历史 Compose 快照。

## 核验触发与历史导航

容器重建、镜像/版本、Compose、挂载、ACL、Secret、端口、DSM 代理或网络变化后，先重新取得只读运行证据，再更新此处快照。Private 内容与凭据不写入基线。D071 至 D076 的部署、回滚、用户验收和失败复盘按日期记录在 `Progress-Log.md`；其中旧记录保持历史属性，不得用作当前运行证明。
