---
created: 2026-09-28
updated: 2026-10-16
status: current
type: environment-baseline
---
# Environment Baseline

本文件只记录最近一次有证据的运行环境快照、端口、镜像、挂载、权限与恢复入口。**它不是实时监控**：最新容器元数据来自 2026-10-16 一次获批只读审计；未运行联调、未读取配置值/私人内容，也未改变服务。历史部署过程、旧状态、失败复盘和逐次证据见 `Progress-Log.md`。不记录任何密钥或明文环境配置。

## 最新只读运行快照（2026-10-16）

- NAS 为 DS920+ `192.168.3.27`。两容器均归属 Compose Project `secondbrain`，配置路径 `/volume1/docker/secondbrain/compose.yaml`；Compose SHA-256 `93fd215b319864d42d8f2223946329f38217cfa7e954b30069f9850eb785398d`，与 2026-10-15 基线相同。过滤后的 Compose 结构只有 `hermes`、`secondbrain-app` 两服务。
- `secondbrain-app`：容器 `f3da36a01343…`，运行/healthy；镜像 `secondbrain-app:d076-organizer-b34319a`，ID `sha256:6070c617…`，代码 revision `b34319af0b928ef6781b9ff4c0cc4ab8bb80c1c0`；UID:GID `1026:100`、只读根文件系统、非 privileged、drop ALL capabilities、`no-new-privileges`。宿主仅绑定 `127.0.0.1:9120→8000/tcp`。未配置 Docker memory/CPU/PID 上限。启动时间 `2026-10-15T14:59:58.435790470Z`。
- `secondbrain-hermes`：容器 `f6703ca3e3d4…`，running，未配置 healthcheck；固定镜像 `nousresearch/hermes-agent@sha256:d4da4a40cd7a28aba983775d9fd31d94cbf153eeb0cb9e844d6d0f612b7c24db`，image ID `sha256:e1e87aec…`，架构 `linux/amd64`，revision `749220ef0007f8d87bd1531f1c24b0fe93816385`（对应已记录 Hermes v0.21.5 源码）。容器以 root 运行、根文件系统可写、未 drop capabilities、非 privileged；memory 上限 1.5 GiB，无 CPU/PID 上限。宿主绑定 `192.168.3.27:9119→9119/tcp`，API 8642 无宿主端口绑定。启动时间 `2026-10-14T08:03:44.970619297Z`。
- 两容器唯一共同网络为 `secondbrain_default`，bridge、`internal=false`、子网 `172.18.0.0/16`；本次网络 inspect 显示该网络只有 App（`172.18.0.3`）和 Hermes（`172.18.0.2`）两个端点。容器网络成员彼此隔离于其他 Docker 网络，但 `internal=false` 不阻止普通 bridge 出站；本次没有探测 LAN/公网出站。Hermes 的 9119 端口仍绑定 NAS LAN 地址。
- **实际挂载边界：** App 以 RW 挂载 Core state、Review、KnowledgeAssets Inbox；以 RO 挂载 `20-Knowledge` 和两项 Secret 文件。Hermes 以 RW 挂载 `/volume1/docker/secondbrain/hermes/data→/opt/data`、SecondBrain `00-Inbox`/`10-Review` 与 KnowledgeAssets Inbox；另以 RO 将整个 `/volume1/SecBR/SecondBrain→/secondbrain` 根目录挂入。没有单独的 Private bind mount，但根目录范围比历史文字“Private 未挂载”宽；本次未查 Private 是否存在或读取其内容，故不能再声称 Private 不可被 Hermes 看见。Hermes 的 Safe Root 环境配置未读取，实际写入白名单为 UNKNOWN。
- 仅检查了挂载源的 POSIX 元数据：Core state `0700 1026:100`（根层 regular files 0）；Hermes data `0700 1026:10000`（根层 regular files 57）；SecondBrain 根 `0500 1026:100`；Inbox `0700 1026:100`（根层文件 2）；Review `0700 1026:100`（24）；`20-Knowledge` `0700 1026:100`（2）；KnowledgeAssets Inbox `0700 1026:100`（24）。计数仅针对目录第一层普通文件，不含子目录、文件名或内容，也不是总磁盘占用。两个 App Secret 文件只核对存在、`0600 1026:100`，未读取内容。已知回滚目录存在，目录权限 `0700 root:root`；没有读取或校验其中文件。
- ACL 细节、DSM Container Manager GUI 状态、Synology Drive 同步状态、其他 NAS 服务的网络配置、路由/PBR/WireGuard/AdGuard、业务 API 可用性和容器实际出站状态均未核验。挂载列表未出现单独的 Obsidian/Synology Drive 路径；这不代表同步服务状态已核验。
- 与 2026-10-15 快照相比：容器 ID、镜像 ID、启动时间、Compose SHA 与历史值一致；本次补充发现 Hermes 容器安全参数较宽松，且整棵 SecondBrain 根目录 RO 挂入。现有两个服务不是隔离测试资产：App/Core state、Hermes profile/data 和业务 Inbox/Review 均指向正式路径，因此本轮没有通过它们执行合成 Run。

### 下一阶段 NAS 独立临时 Compose 联调（设计已审，未执行）

- **项目与暂存路径：**Compose project 名 `sb-d077-phase1c-<run-id>`；唯一暂存根 `/volume1/docker/secondbrain-test/d077-phase1c/<run-id>/`（计划权限 `0700 root:root`），仅保存精简 Compose、PR 源码归档/测试脚本、Core 镜像归档和脱敏结果。该路径当前是否存在/有空间未核验。Core 源码树在本轮开始时固定于 PR #8 `955fc16d808349af661e49fc4c33b449db0a0fce`，本轮 Core 运行时代码不改；实际运行前须改用最终经 ChatGPT 审核的 PR head SHA，并校验归档哈希。Hermes 固定 `nousresearch/hermes-agent@sha256:d4da4a40cd7a28aba983775d9fd31d94cbf153eeb0cb9e844d6d0f612b7c24db`。不引用正式 Compose。
- **拓扑/数据：**只创建临时 `hermes`、`core`、确定性 `stub` 三个服务，单一 `internal: true` 网络，无任何 `ports`、host network、第二网络或 Docker socket。Hermes/Core/Stub 均采用非 root、只读 rootfs、drop ALL capabilities、no-new-privileges；仅开受限 `/tmp` 与运行所需 `tmpfs`（Hermes profile `/opt/data`、Core state `/test-data`、Stub scratch）。若测试脚本需 bind mount，只能从上述唯一暂存根 RO 挂入脚本，不将暂存根或任何 NAS 业务目录作为数据卷。Synthetic API 凭据只在隔离运行时生成/注入，不使用 GitHub/NAS Secret。
- **Core 构建与网络边界：**从上述最终审核 SHA 构建临时 Core 镜像，镜像必须标记 `d077.task=phase1c` 与唯一 `d077.run=<run-id>`。避免 NAS build 触发未批准下载：优先在 Mac 生成 `linux/amd64` 镜像归档并在授权后传入唯一暂存根；若跨架构构建、基础层或依赖无法离线复现，则停止，不放通 Docker build 网络。测试容器仅连 internal network；运行前 inspect 白名单校验网络成员、无端口绑定、挂载源范围、用户/capabilities，并确认 LAN/公网出口均拒绝；再确认 Core↔Hermes 与 Hermes↔Stub 健康后，才运行合成 Run/SSE/记忆断言。
- **资源与时限估算：**Hermes 1.5 GiB/1 CPU/128 PIDs，Core 768 MiB/0.75 CPU/96 PIDs，Stub 256 MiB/0.25 CPU/32 PIDs；容器硬上限合计约 **2.5 GiB、2 CPU、256 PIDs**，不含 Docker daemon/build 缓存开销。NAS 当前可用资源 UNKNOWN；授权执行前只读门槛建议 `MemAvailable ≥4 GiB`、目标卷可用空间 `≥6 GiB`，否则停止。单次 Harness 最长 10 分钟，整个准备/运行/清理不超过 20 分钟；超时由容器外控制。
- **定向回滚/清理：**先分别运行 `docker ps -aq --filter label=d077.task=phase1c --filter label=d077.run=<run-id>` 与 `docker network ls -q --filter label=d077.task=phase1c --filter label=d077.run=<run-id>`，对每个返回 ID 用 `docker inspect` 再验两个 label；只把这些逐一核验的 ID 传给 `docker rm -f <IDs>` / `docker network rm <IDs>`。只 inspect 并删除本轮唯一镜像 tag `sb-d077-core:<run-id>`，最后仅在 run-id 符合安全字符白名单且规范化路径精确等于 `/volume1/docker/secondbrain-test/d077-phase1c/<run-id>/` 时删除该暂存根。清理后重复按 label 查容器/网络、inspect 唯一 image tag，并确认唯一暂存根不存在；任何 label/name 不匹配即停止清理并报告残留。不使用 `docker system prune`、全局 Compose down 或模糊通配符；现有 App/Hermes 容器、网络、卷、路径和 App 回滚目录都不参与回滚。
- **前置条件与验收：**另获用户对 NAS 临时目录、离线镜像导入/构建、容器/网络创建及定向删除的明确授权；先重新核验资源余量和当前 Docker；审核最终 SHA/归档哈希及 Compose 白名单；镜像/用户/挂载/网络/egress 前置断言全部通过。验收需有网络预检证据、逐项合成 E2E 结果与唯一最终 PASS 标记，以及容器/网络/镜像/暂存根清理后空清单。若任何边界断言失败，不开始 Run。

风险是 NAS 资源竞争、离线镜像归档/跨架构不一致、临时定义误引用生产路径，以及 Docker `internal` 网络边界验证失败。以上方案需新的逐项操作授权；本轮未创建路径、镜像、容器或网络，也未执行任何回滚命令。

## NAS 与 Compose

- NAS：Synology DS920+，DSM 7.4.1 Build 90080；LAN 地址 `192.168.3.27`。本机与路由器网络设置不由 SecondBrain 文档治理修改。
- 正式 Compose：`/volume1/docker/secondbrain/compose.yaml`；Compose Project `secondbrain`；Docker 网络 `secondbrain_default`。部署前 SHA-256：`e318d4167666877e415203f637eda63a38cde41b01e5d58855dee29ce50a1149`；本次仅更新 App build context 与 image 字段后的 SHA-256：`93fd215b319864d42d8f2223946329f38217cfa7e954b30069f9850eb785398d`。
- 项目目标为两个服务：`secondbrain-hermes` 与 `secondbrain-app`。Container Manager GUI 曾出现旧容器行/旧定义缓存；最后已记录状态为管理界面定义未完成对齐。当前 GUI 状态未在本次核实，标记 `UNKNOWN`；这是部署管理风险，不改变 Docker 运行态记录。

## 最近已核验的容器快照（2026-10-15）

| 服务 | 容器 ID | 镜像 / Image ID | 状态 | 入口/说明 |
|---|---|---|---|---|
| `secondbrain-app` | `f3da36a01343e764ac051d81c99fac7e6186c947629dd312301c8547e28c3f82` | `secondbrain-app:d076-organizer-b34319a` / `sha256:6070c61789737bf64b57d7aab726c4bcee20564f2e6df5584344dcc568d9196f` | healthy；启动 `2026-10-15T14:59:58.43579047Z`；运行身份 `1026:100` | 宿主 `127.0.0.1:9120`；LAN-only DSM HTTPS `https://zxwan520.com:63013` |
| `secondbrain-hermes` | `f6703ca3e3d41856b6e35348f28cd1c7f833ffb9ab31b19e958656540eed8ac6` | `nousresearch/hermes-agent@sha256:d4da4a40cd7a28aba983775d9fd31d94cbf153eeb0cb9e844d6d0f612b7c24db` / `sha256:e1e87aec2e3f5b9863c127a0f21f3b3c237c8717c57c323c7184a49ca12a0df6` | running；启动 `2026-10-14T08:03:44.970619297Z`；v0.21.5 / upstream `749220ef` | LAN HTTP `192.168.3.27:9119`；LAN-only DSM HTTPS `https://zxwan520.com:63012`；API 8642 不发布宿主端口 |

上述为 2026-10-15 本次部署后的核验快照。新 App 源码来自 GitHub `b34319af0b928ef6781b9ff4c0cc4ab8bb80c1c0`；Hermes 容器、镜像和启动时间保持不变。Promote 未启用。

## 挂载与权限边界（历史快照，2026-10-15）

下表保留部署时记录；与上方 2026-10-16 只读 inspect 有差异时以上方为当前证据。特别是 Hermes 的 SecondBrain 根只读 bind mount 实际覆盖整棵根目录，因此旧文字“Private 无挂载/不访问”不再能描述当前可见范围。

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
| 两者 | Private | 2026-10-15 记录为无单独挂载；2026-10-16 确认 Hermes 挂载 SecondBrain 根目录，Private 是否存在/可见未检查 | UNKNOWN；不可据旧快照宣称不可访问 |

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
