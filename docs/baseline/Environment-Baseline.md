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
- 正式 Compose：`/volume1/docker/secondbrain/compose.yaml`；Compose Project `secondbrain`；Docker 网络 `secondbrain_default`。本次部署前 SHA-256 `93fd215b319864d42d8f2223946329f38217cfa7e954b30069f9850eb785398d`；部署后 SHA-256 `36c1d6cf14643ad41e5c04ec9ac1374b194dc52ebefbbe6dc6c57d1ac3fdd4a2`，属主/权限 `1026:100 / 0640`。差异仅固定 Hermes 镜像并启用 API、切换已在 NAS 的 D077 Core 镜像、启用 Personal Memory/Learning flags 及其专用根目录。
- 项目目标为两个服务：`secondbrain-hermes` 与 `secondbrain-app`。Container Manager GUI 曾出现旧容器行/旧定义缓存；最后已记录状态为管理界面定义未完成对齐。当前 GUI 状态未在本次核实，标记 `UNKNOWN`；这是部署管理风险，不改变 Docker 运行态记录。

## 最近已核验的容器快照（2026-10-16 Issue #12）

| 服务 | 容器 ID | 镜像 / Image ID | 状态 | 入口/说明 |
|---|---|---|---|---|
| `secondbrain-app` | `064e0782cb61df4a0c9fd3ca6968f494063f85f3870caaa7527e897b7d740cc6` | `secondbrain-app:d077-b6e30f3` / `sha256:7cce77d702cb51f0c318c91c427d95cff887a99caebb12b9cad287b388b1049c` | healthy；启动 `2026-10-16T12:55:04.372325515Z`；运行身份 `1026:100` | 宿主 `127.0.0.1:9120`；D077 Core source `b6e30f3f1b61cb4f821b7db2c2bca994302be6dc` |
| secondbrain-hermes | 2cf7cec6d44dc49de37f0fb16c36f8e71f4bea5747aeecc2782efabf09eeb86f | nousresearch/hermes-agent@sha256:a11574b7fe8e1631d7d88d556677dac693bc058abf558cdeb899155688c1bf05 / sha256:02e7aa0e84123fa0e9b22686e7a2bfb7d85fd59821d4d28812a3e07f3061cf41 | running；v0.22.2；Issue #14 定向重启时间 2026-10-16T13:34:38.771773364Z | API 8642 容器内 health 200、不发布宿主端口；Dashboard 9119 登录重定向 302，仅映射 192.168.3.27:9119 |

App 容器 Docker health 为 healthy，Core /health 经宿主 127.0.0.1:9120 和受信 Host 192.168.3.27 返回 200；Hermes API 8642/health 为 200，Dashboard 9119/ 返回登录重定向 302。Issue #14 后 Hermes 运行中；App 未重启。个人记忆/学习 flags 为 true；SB_PERSONAL_MEMORY_ROOT=/var/lib/secondbrain-core/personal-memory 对应宿主目录 /volume1/docker/secondbrain/core-state/personal-memory，属主/权限 1026:100 / 0700，本次未新增 Session/Run，目录无文件。SB_PROMOTE_ENABLED=false。浏览器入口 https://zxwan520.com:63013/health 于本轮 TLS 校验成功并返回 200。

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

- Issue #14 API 工具限制回滚点：/volume1/docker/secondbrain/rollback/d077-issue14-api-toolset-20261016T1334Z/config.yaml.before，SHA-256 cdee7b148aa314536e24986f8f0dd57ea5999350e46c6b3bfd65c25a37eecac9；目录 0700 root:root，文件 0600 root:root。回滚前保存当前 Hermes config，再将此文件恢复到 /volume1/docker/secondbrain/hermes/data/config.yaml、属主/模式 1026:100 / 0640，最后只重启 Hermes。Compose 未改。

- 本次部署快照与回滚材料位于 `/volume1/docker/secondbrain/rollback/d077-issue12-authorized-20261016T124238Z/`：目录 `0700 root:root`、文件 `0600 root:root`。包含部署前 Compose（SHA-256 `93fd215b319864d42d8f2223946329f38217cfa7e954b30069f9850eb785398d`）、部署前 Hermes 数据归档、迁移后原 Hermes config、部署候选 Compose、脱敏启动日志、只含布尔值的 Stub 观测、合成记忆 JSONL 与测试摘要；清单验证通过。此前回滚目录 `/volume1/docker/secondbrain/rollback/d077-issue12-v0222-predeploy-20261016T1225Z/` 保留不动。
- 回滚方法：先再保存当前 Hermes 数据和当前 Compose；恢复本次快照中的 `compose.before.yaml` 到正式路径并还原属主/0640，然后只对 `hermes` 和 `secondbrain-app` 执行 Compose `up -d --pull never --no-deps`，使其回到原 v0.21.5 与 `d076-organizer-b34319a` 镜像。若旧版不接受迁移后的 Hermes profile，先保留当前 profile，再参考已校验的部署前状态归档恢复；不得直接覆盖或删除当前数据。Personal Memory 子目录保留，真实使用后不得按测试目录清理。
- 本次 App-only 回滚快照：`/volume1/docker/secondbrain/rollback/d076-organizer-predeploy-20261015T145538Z/`；目录 `0700 root:root`、文件 `0600 root:root`，`SHA256SUMS` 已验证。包含部署前 Compose、Core state 元数据、App runtime 元数据和 App 镜像元数据，不含 Secret 或业务内容。旧 App 镜像 `secondbrain-app:d076a1.1-9962001`（`sha256:55f40951620fb8b7043933c724f66cbf22a2326a961d654d8671e877c212bcd3`）可用于回退。恢复前重新核对快照/镜像，只回退 App，保留 Core state；不得整体 `compose down` 或重启 Hermes。
- D076-A.1 上一 App 镜像 `secondbrain-app:d076a1-55977c8` 及更早镜像按 Progress-Log 的部署记录保留情况为准；本次未核查镜像存量。
- 生产恢复操作须遵循本文件所列最近快照并先重新核对实际 Compose/数据/镜像；不能直接复制含旧 Hermes 定义的历史 Compose 快照。

## 核验触发与历史导航

容器重建、镜像/版本、Compose、挂载、ACL、Secret、端口、DSM 代理或网络变化后，先重新取得只读运行证据，再更新此处快照。Private 内容与凭据不写入基线。D071 至 D076 的部署、回滚、用户验收和失败复盘按日期记录在 `Progress-Log.md`；其中旧记录保持历史属性，不得用作当前运行证明。
