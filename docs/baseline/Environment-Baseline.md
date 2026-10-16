---
created: 2026-09-28
updated: 2026-10-16
status: current
type: environment-baseline
---
# Environment Baseline

本文件只记录最近一次有证据的运行环境快照、端口、镜像、挂载、权限与恢复入口。**它不是实时监控**：以下为 2026-10-16 Hermes v0.22.2 部署尝试回滚后的只读快照；升级失败与回滚证据见 `Progress-Log.md`。不记录任何密钥或明文环境配置。

## NAS 与 Compose

- NAS：Synology DS920+，DSM 7.4.1 Build 90080；LAN 地址 `192.168.3.27`。本机与路由器网络设置不由 SecondBrain 文档治理修改。
- 正式 Compose：`/volume1/docker/secondbrain/compose.yaml`；Compose Project `secondbrain`；Docker 网络 `secondbrain_default`。部署前 SHA-256：`e318d4167666877e415203f637eda63a38cde41b01e5d58855dee29ce50a1149`；本次仅更新 App build context 与 image 字段后的 SHA-256：`93fd215b319864d42d8f2223946329f38217cfa7e954b30069f9850eb785398d`。
- 项目目标为两个服务：`secondbrain-hermes` 与 `secondbrain-app`。Container Manager GUI 曾出现旧容器行/旧定义缓存；最后已记录状态为管理界面定义未完成对齐。当前 GUI 状态未在本次核实，标记 `UNKNOWN`；这是部署管理风险，不改变 Docker 运行态记录。

## 最近已核验的容器快照（2026-10-16 回滚后）

| 服务 | 容器 ID | 镜像 / Image ID | 状态 | 入口/说明 |
|---|---|---|---|---|
| `secondbrain-app` | `f3da36a01343e764ac051d81c99fac7e6186c947629dd312301c8547e28c3f82` | `secondbrain-app:d076-organizer-b34319a` / `sha256:6070c61789737bf64b57d7aab726c4bcee20564f2e6df5584344dcc568d9196f` | healthy；启动 `2026-10-15T14:59:58.43579047Z`；运行身份 `1026:100` | 宿主 `127.0.0.1:9120`；LAN-only DSM HTTPS `https://zxwan520.com:63013` |
| `secondbrain-hermes` | `53ad4601ba4b9b067aeb782cbf520244ea0a557a076bcf553ff4455061c35171` | `nousresearch/hermes-agent@sha256:d4da4a40cd7a28aba983775d9fd31d94cbf153eeb0cb9e844d6d0f612b7c24db` / `sha256:e1e87aec2e3f5b9863c127a0f21f3b3c237c8717c57c323c7184a49ca12a0df6` | running；启动 `2026-10-16T11:52:19.749685969Z`（数据恢复后）；v0.21.5 / upstream `749220ef` | LAN HTTP `192.168.3.27:9119`；LAN-only DSM HTTPS `https://zxwan520.com:63012`；API 8642 不发布宿主端口 |

上述为 2026-10-16 回滚后的运行快照。App 仍为 GitHub `b34319af0b928ef6781b9ff4c0cc4ab8bb80c1c0` 构建；Hermes 已恢复 v0.21.5 与升级前 state。两服务 `/health` 均返回 200；Promote 未启用。

## D077 Hermes v0.22.2 部署尝试（2026-10-16，已回滚）

- 目标镜像 `nousresearch/hermes-agent@sha256:a11574b7fe8e1631d7d88d556677dac693bc058abf558cdeb899155688c1bf05` 已核实为 `linux/amd64`，但替换后容器虽运行，内部 API 8642 与 Dashboard 9119 均未监听。v0.22.2 未进入可用状态；未运行 Session/Run/SSE 或模型请求。
- Compose 已恢复到 SHA-256 `93fd215b319864d42d8f2223946329f38217cfa7e954b30069f9850eb785398d`。个人记忆 flags 未配置（默认 false），专用 `personal-memory` 空目录已移除。Hermes v0.21.5 state 已由校验归档恢复；升级尝试后的状态仍保留供后续审查。
- 回滚资产：`/volume1/docker/secondbrain/rollback/d077-v0222-predeploy-20261016T114324Z/`，目录 `0700 root:root`，归档与清单文件 `0600 root:root`。升级前 Hermes state tar SHA-256：`ef497b20177ab8e563c176472806e7b51875af01692c971edebe54faeda24c7b`。目录内另有 `hermes-data-after-v0222-attempt/` 保存失败状态。
- 新 Core/App image `secondbrain-app:d077-b6e30f3` 与源码 `/volume1/docker/secondbrain/app-build-source-d077-b6e30f3/web-app` 保留但未激活；当前 App 仍使用 `secondbrain-app:d076-organizer-b34319a`。未重启其他 NAS 服务或修改家庭网络。
- 最后核验：Private 无挂载；Knowledge RO；`SB_PROMOTE_ENABLED=false`；Hermes API key 文件仍只读挂载且权限受限，正文未读取；API 8642 不发布宿主端口。

## 挂载与权限边界（最近记录的实际配置）

| 容器 | 数据/用途 | 容器路径 | 访问模式/身份 |
|---|---|---|---|
| App | KnowledgeAssets `00-Inbox` Raw | `/knowledge-assets/00-Inbox` | RW |
| App | SecondBrain `10-Review` | `/review` | RW |
| App | `20-Knowledge` | `/knowledge` | RO |
| App | Core 私有 state | `/var/lib/secondbrain-core` | RW；目录独立、最小权限 |
| App | 应用 Secrets | `/run/secrets/...` | RO；UID/GID `1026:100` 持有受限文件 |
| Hermes | SecondBrain 根 | `/secondbrain` | RO |
| Hermes | `00-Inbox`、`10-Review`、KnowledgeAssets Inbox 捕获根 | `/secondbrain-write/00-Inbox`、`/secondbrain-write/10-Review`、`/knowledge-assets/00-Inbox` | 三个捕获目录 RW；safe root 只列出这三项 |
| Hermes | `20-Knowledge` | 无 RW 子挂载，仅经 `/secondbrain` 读取 | RO |
| 两者 | Private | 无挂载 | 不访问 |

App 最近记录的身份为 UID/GID `1026:100`，只读根文件系统、独立 `/tmp` 64 MiB tmpfs。`SB_PROMOTE_ENABLED=false`；Hermes STT 默认关闭。以上值须在下一次生产操作前重新 inspect，不可仅靠文档视为当前事实。

Organizer Core 私有状态位于现有 Core state 挂载内的 `ai-organize` 子目录，UID/GID `1026:100`、权限 `0700`。本次 `model-settings.json` 与 Organizer API Key 文件均不存在，运行状态接口确认模型与 Scheduler 均关闭；配置变更不会自行启动任务。没有新增挂载或放宽权限。

## 网络与浏览器入口

- App 通过 Compose 内部网络访问 Hermes；Hermes API `8642` 不映射到宿主端口。
- Hermes 的策略路由、NAS 双网卡和实际公网出口不在本次检查范围；最新实时路由证据为 `UNKNOWN`。不要仅凭公网 IP 地理位置推断是否经过 `wg0`。
- DSM 63012/63013 反向代理的 LAN-only 规则及登录链曾通过部署测试；本次未重验 DSM 配置、证书或外网可达性。不得由入口历史记录推断公网已开放。

## Obsidian 同步边界

- Obsidian 知识/笔记库由 Synology Drive 在 Mac 与 NAS 间同步；最近记录称客户端显示已同步，但双向传播未单独验收。历史 `SynologyDrive stopped` 报告不构成已确认故障；当前客户端连接与 NAS 实际传播状态均为 `UNKNOWN`。此同步只承载知识、笔记与个人资料，不是代码或正式项目文档源。相关历史核验见 `Progress-Log.md`。

## 恢复入口

- 本次 App-only 回滚快照：`/volume1/docker/secondbrain/rollback/d076-organizer-predeploy-20261015T145538Z/`；目录 `0700 root:root`、文件 `0600 root:root`，`SHA256SUMS` 已验证。包含部署前 Compose、Core state 元数据、App runtime 元数据和 App 镜像元数据，不含 Secret 或业务内容。旧 App 镜像 `secondbrain-app:d076a1.1-9962001`（`sha256:55f40951620fb8b7043933c724f66cbf22a2326a961d654d8671e877c212bcd3`）可用于回退。恢复前重新核对快照/镜像，只回退 App，保留 Core state；不得整体 `compose down` 或重启 Hermes。
- D076-A.1 上一 App 镜像 `secondbrain-app:d076a1-55977c8` 及更早镜像按 Progress-Log 的部署记录保留情况为准；本次未核查镜像存量。
- 生产恢复操作须遵循本文件所列最近快照并先重新核对实际 Compose/数据/镜像；不能直接复制含旧 Hermes 定义的历史 Compose 快照。

## 核验触发与历史导航

容器重建、镜像/版本、Compose、挂载、ACL、Secret、端口、DSM 代理或网络变化后，先重新取得只读运行证据，再更新此处快照。Private 内容与凭据不写入基线。D071 至 D076 的部署、回滚、用户验收和失败复盘按日期记录在 `Progress-Log.md`；其中旧记录保持历史属性，不得用作当前运行证明。
