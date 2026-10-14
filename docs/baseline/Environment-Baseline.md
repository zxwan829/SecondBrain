---
created: 2026-09-28
updated: 2026-10-14
status: current
type: environment-baseline
---
# Environment Baseline

本文件记录已核验且仍有运维价值的生产环境事实，不定义代码或正式文档的权威源。代码与正式基线文档由 SecondBrain GitHub Monorepo 管理；iMac、MBA 各自开发。NAS 负责 Docker、业务数据与运行配置；Obsidian 库负责笔记、知识及可阅读资料。生产配置变更、容器重建或版本变化后更新；历史阶段过程与测试叙述放在 Progress-Log。不可从此处读取到的秘密不得记录。文中路径、内网地址、服务拓扑、Drive 标识和版本信息属于内部运维资料；推送私有 GitHub 前应确认仓库访问成员范围合适，禁止加入真实凭据或环境文件。

## NAS / 数据路径

- Synology DS920+, DSM 7.4.1 Build 90080；NAS LAN `192.168.3.27`，iStoreOS `192.168.3.2`。家庭网关、PBR、WireGuard、DNS 是稳定生产环境，不属 SecondBrain 随手修改范围。
- iMac 唯一正式开发克隆：`/Users/joe/Documents/Codex/SecondBrain`；MBA 使用独立 Clone。私有 GitHub `zxwan829/SecondBrain` 是唯一代码和正式项目文档源。Codex 当前采用 workspace-write 沙箱，GitHub/NAS 网络访问已验证正常；仍须遵守权限审批和生产操作授权边界。
- NAS Docker 正式目录：`/volume1/docker/secondbrain/`；Core build context：`/volume1/docker/secondbrain/core-source/`。NAS 业务数据位于 `/volume1/SecBR/SecondBrain/`、`/volume1/SecBR/KnowledgeAssets/`，Private 位于 `/volume1/SecBR/Private/`。NAS 只负责 Docker 运行、配置和业务数据，不作为开发环境或文档源。
- Obsidian 知识库位于 Mac `/Users/joe/SecondBrain/` 并通过 Synology Drive 与 NAS 双向同步。其用途是笔记、知识与个人资料，不是代码或正式开发文档来源。客户端曾显示已为最新；实际双向文件传播尚未单独验收。历史 SynologyDrive `stopped` 状态报告尚未确认为套件故障。
- 迁移前旧 NAS SecondBrain V1 开发目录、治理快照、Google Drive 项目文档镜像、旧发布流程及本地迁移备份已清理；有效生产部署与回滚资产仍保留在 Docker 正式目录中。GitHub Push 不代表部署；按授权由 Mac SSH 传入部署内容，NAS 无需直接访问 GitHub。

## Hermes Runtime

- Compose：`/volume1/docker/secondbrain/compose.yaml`；项目根 `/volume1/docker/secondbrain/`；容器 `secondbrain-hermes`。
- Core build context：`/volume1/docker/secondbrain/core-source/`，按 GitHub Monorepo `main` 部署；旧 `/volume1/SecBR/SecondBrain/30-Projects/SecondBrain V1/` 不再作为源码或构建目录。
- Core 原镜像 `secondbrain-core:core4-github-961c07d`（image ID `sha256:d765420f082aae8263e6072249fbc9a1baa9fb117006d06bcb3b31edc2b9e5cc`）保留；其旧容器已由 D074 App 替换并移除。回退镜像 `secondbrain-core:core4`（image ID `sha256:fec9a06032d4462c49643ebaed49d2b41d196b40cd6c737c24608bc29b7e4034`）及原 Core state 目录保留。
- Production Hermes v0.21.5 / build `749220ef`；镜像 `nousresearch/hermes-agent@sha256:d4da4a40cd7a28aba983775d9fd31d94cbf153eeb0cb9e844d6d0f612b7c24db`；已核验运行 image ID `sha256:e1e87aec2e3f5b9863c127a0f21f3b3c237c8717c57c323c7184a49ca12a0df6`。当前 Runtime 默认模型 `zai-org/GLM-4.5-Air`；最终长期默认未冻结。
- Hermes 数据/配置：`/volume1/docker/secondbrain/hermes/data/`、`config.yaml`；Hermes CLI `/opt/hermes/.venv/bin/hermes`。
- Dashboard 监听容器端口 `9119`，宿主仅绑定 `192.168.3.27:9119`，LAN HTTP URL `http://192.168.3.27:9119`；DSM HTTPS `https://zxwan520.com:63012` 保留 LAN-only 入口。Basic Auth secret 在 `/volume1/docker/secondbrain/.env`，权限 600。不得把凭据写入文档。
- 网络 `secondbrain_default`；网段 `172.18.0.0/16`，Gateway `172.18.0.1`，Hermes `172.18.0.2`；容器流量策略路由经 table 200 → `192.168.3.2` → `wg0`。开机脚本 `/volume1/docker/secondbrain/scripts/hermes-policy-route.sh`，DSM Task Scheduler `SecondBrain Boot`（root）；开机恢复未以 NAS 主动重启验证。

### D074 App/Core 与 Hermes API 部署前只读核验（2026-10-14，历史快照）

- 通过现有 NAS SSH 与一次性 `sudo -n docker exec` 只读核验 `secondbrain-hermes`：Hermes v0.21.5 / upstream `749220ef`；`/proc/net/tcp` 显示 `127.0.0.1:8642` LISTEN，loopback `/health` 返回 200，未认证 `GET /api/sessions` 与 `/v1/capabilities` 返回 401。容器当前配置文件没有 `platforms.api_server` 项，`API_SERVER_*` 环境项未设置且未发现可供 App 使用的 API key 配置。API 进程有响应且受认证保护，但 loopback 绑定不能供同 Compose 的 App 容器访问；未进行带凭据的上游请求。
- 当前正式 Compose service 名为 `hermes`，容器名 `secondbrain-hermes`，与旧 Core 处于 `secondbrain_default` 网络；Hermes API 无 8642 宿主端口映射。App BFF 候选地址使用 Compose DNS `http://hermes:8642`。当前 Core 仍是旧镜像/service；D074 App 未部署。只读核验没有修改容器、Compose、密钥或运行配置。
- 候选 App 镜像运行身份与 NAS 现有 Core 一致为 `1026:100`；App password/Hermes API key 文件必须在 App 容器内由 UID 1026 拥有、mode 0600 或更严。`.env.example` 不含密钥。DSM HTTPS 可信 peer 仍按现有基线使用精确 `172.18.0.1`，启动代码只接受单个 IP 字面值，不接受 `*` 或 CIDR；实际 App 生产链路及前端 HTTPS Cookie 尚未运行核验。

## 已核验挂载与安全差距

运行容器 Docker inspect（UC-V1-Attachment-0B）确认：

| Host source | Container destination | Mode |
|---|---|---|
| `/volume1/SecBR/SecondBrain` | `/secondbrain` | RO |
| `/volume1/SecBR/SecondBrain/00-Inbox` | `/secondbrain-write/00-Inbox` | RW |
| `/volume1/SecBR/SecondBrain/10-Review` | `/secondbrain-write/10-Review` | RW |
| `/volume1/SecBR/KnowledgeAssets/00-Inbox` | `/knowledge-assets/00-Inbox` | RW |

**2026-10-13 生产权限收窄后：** Hermes Knowledge 仅经 `/secondbrain` RO 根路径读取；不再挂载 Knowledge RW 子路径。`HERMES_WRITE_SAFE_ROOT=/secondbrain-write/00-Inbox:/secondbrain-write/10-Review:/knowledge-assets/00-Inbox`。Hermes root 与 terminal 仍可用，但文件工具白名单和 RO bind mount 双重限制 Knowledge 写入。

### 2026-10-13 阶段 B 首次普通 SSH 只读复核（历史）

- SSH `secondbrain-nas` 成功；登录账户为 Joe UID/GID `1026:100`，附加组 `administrators`。NAS 当前 `/volume1/docker/secondbrain/compose.yaml` 的只读文本显示：Hermes 服务 `hermes` 的 `HERMES_WRITE_SAFE_ROOT` 仍是 `/secondbrain-write:/knowledge-assets/00-Inbox`，`00-Inbox`、`10-Review`、`20-Knowledge` 三个 SecondBrain 子挂载及 KnowledgeAssets Inbox 均声明 RW；生产 Compose 中未找到 `Private` 路径。Core 服务 `secondbrain-core` 声明 `user: 1026:100`、只读根文件系统；Review、Knowledge bind mount 为只读，Core state 为 RW，Core unlock secret 为只读，`SB_PROMOTE_ENABLED=false`。
- **实时容器检查受阻：** NAS `/var/run/docker.sock` 为 `root:root`、mode `0660`；SSH 用户对 socket 的 `test -r` / `test -w` 均为 no。普通 `/usr/local/bin/docker ps/inspect/exec` 返回 `permission denied while trying to connect to the Docker daemon socket`。未 sudo，也未查询运行容器实际挂载、环境值、有效进程 UID 或容器内访问结果。Compose 声明显示 unlock secret 从 `/volume1/docker/secondbrain/core-secrets/promote_unlock` 只读挂至 Core `/run/secrets/promote_unlock`，Hermes service 未声明此挂载；Core state 从 `core-state` 提供。Compose 未匹配到 Private 路径。以上是静态配置，不是运行容器证明。
- 直接 `stat`：SecondBrain 根、Inbox、Review、Knowledge 目录当前 POSIX mode 均显示 `0777`、owner `1026:100`；`synoacltool -get` 对 Review/Knowledge 显示 ACL owner Joe 具有 RWX、`administrators` 组具有 RWX，并有 Joe 继承的只读 ACE；输出中无 Everyone ACE。NAS shell 当前 SSH 用户对 Review、Knowledge 的主机级 `test -r/-w` 均为 yes。此为 SSH 用户/宿主权限证据，不能推断容器 bind mount 的有效权限。
- `/volume1/docker/secondbrain/core-state` 存在，mode `0700`、owner `1026:100`；`synoacltool` 报告此路径使用 Linux mode（没有 DSM ACL）。它与当前 Core Compose 声明的私有状态目录相符，但 Docker socket 阻断了运行时挂载核对。以上证据由本次只读 SSH 命令取得；未改 NAS 文件、ACL、容器或服务。

### 2026-10-13 一次性 sudo 运行时只读核验

- 通过现有 SSH alias `secondbrain-nas` 和非交互 `sudo -n` 成功运行只读 Docker 查询；未提示/读取管理员密码，未修改 socket、用户组、sudoers、ACL、容器、服务或业务数据。普通 SSH 用户仍无 `/var/run/docker.sock` 读写权限；本次成功不代表应扩大该权限。
- `secondbrain-hermes` 为 `running`，镜像配置 `nousresearch/hermes-agent:latest`，容器内版本 Hermes Agent v0.21.5 / upstream `749220ef`，实际进程 UID/GID `0:0`；Docker `Privileged=false`、未配置额外 CapAdd，根文件系统可写。完整运行挂载清单：SecondBrain 根 `/secondbrain` RO；`00-Inbox` → `/secondbrain-write/00-Inbox` RW；`10-Review` → `/secondbrain-write/10-Review` RW；`20-Knowledge` → `/secondbrain-write/20-Knowledge` RW；KnowledgeAssets Inbox → `/knowledge-assets/00-Inbox` RW；Hermes data → `/opt/data` RW。未发现 Private、Core secret、Core state、宿主根目录或 Docker socket 挂载。运行值 `HERMES_WRITE_SAFE_ROOT=/secondbrain-write:/knowledge-assets/00-Inbox`。容器内 `test -r/-w` 确认 `/secondbrain/20-Knowledge` 可读且不可写，`/secondbrain-write/20-Knowledge` 可读写；Inbox、Review、KnowledgeAssets Inbox 也可读写。因 safe root 包含父路径 `/secondbrain-write`，Knowledge 子路径通过该白名单；旧有 write_file 实测证据确认可直接写 Knowledge。Hermes 以 root 运行且有 terminal，safe-root 仅约束 `write_file`/`patch`，不是终端隔离边界。
- `secondbrain-core` 为 `running/healthy`，实际身份 UID/GID `1026:100`（groups `100`），Docker `Privileged=false`、`CapDrop=ALL`、根文件系统只读，`SB_PROMOTE_ENABLED=false`。`/review` 与 `/knowledge` 可读不可写；`/var/lib/secondbrain-core` 可读写；`/run/secrets/promote_unlock` 可读不可写。容器内 `/private` 与 `/knowledge/Private` 均不存在。实际 mounts 与上述 Compose 声明一致：Review/Knowledge RO，Core state RW，Core unlock secret RO；没有 Private mount。
- NAS 当前 Compose 只读核对与实时 Docker inspect 一致：Hermes 四个业务 bind mount 和 safe-root 如表，Core `user: 1026:100`、Promote false、Review/Knowledge RO、state RW、secret RO。Core 健康状态与 Environment 既有记录一致。Hermes image 标签为 `latest`，运行版本与记录的 v0.21.5 build 一致。
- Hermes v0.21.5 容器内实际 `agent/file_safety.py` 的 `get_safe_write_roots()` 源码按 `os.pathsep` 拆分并规范化路径；对候选三路径值做了单进程环境覆盖解析测试，返回的三个 root 与预期一致，未改运行容器环境。该 guard 只用于文件写工具，不构成 terminal 沙箱；正式边界必须由 RO bind mount 强制。未执行会写入 Knowledge 的测试文件探针。

### 2026-10-13 Hermes Knowledge 权限收窄部署

按 Environment-Baseline 最小方案实施，仅变更 Hermes 服务的两项 Compose 设置。部署前备份位于 `/volume1/docker/secondbrain/rollback/hermes-knowledge-ro-20261013-221912/`：原 `compose.yaml`、`.env`、Hermes/Core inspect 元数据、Hermes 版本和非敏感运行配置摘要；目录 `0700 root:root`，文件 `0600 root:root`。备份逐文件 `cmp` 及 SHA-256 核对通过；`.env` 内容未输出或写入 Git。**原 Compose 快照包含被移除的 Knowledge RW 子挂载，严禁直接复制回生产路径或直接用它重建容器。**快照仅用于取回其他配置；任何恢复操作必须先编辑/过滤，确保该 RW 子挂载缺席且写安全根仍是三个精确捕获目录，然后校验配置并仅重建 Hermes。

实际差异：移除 `/volume1/SecBR/SecondBrain/20-Knowledge:/secondbrain-write/20-Knowledge:rw`；`HERMES_WRITE_SAFE_ROOT` 收窄为 `/secondbrain-write/00-Inbox:/secondbrain-write/10-Review:/knowledge-assets/00-Inbox`。部署前以 Hermes v0.21.5 实际解析函数核实冒号分隔得到三个独立写根。Compose 原子更新后 `docker compose config -q` 通过，模式及 owner/group 保持不变；只执行 `up -d --no-deps --force-recreate --pull never hermes`，未拉取镜像、未重建 Core 或其他容器。

部署后实时 inspect：Hermes running，v0.21.5/build `749220ef` 及镜像 ID 未变；Knowledge RW mount 缺席，`/secondbrain` RO；三个捕获挂载仍 RW，运行 safe-root 与目标完全一致。普通文件 `write_file` 与 `patch_replace` 对 Knowledge 均在调用后端前被 safe-root 拒绝；终端 `touch` 在 RO Knowledge 上返回 `Read-only file system`，探针文件不存在。Core 仍 healthy、UID/GID `1026:100`、Knowledge/Review RO、state RW、secret RO、`SB_PROMOTE_ENABLED=false`；Private 未挂载。没有更改 Core、PBR、NAS 网络或业务文件。

回归通过：Hermes Daily Capture 将唯一测试样本写入 Inbox；Universal Capture 将测试样本写入 KnowledgeAssets Inbox Raw 并生成 Review；Dashboard 真实 Review 列表由 8 条增至 9 条，测试项详情及正文正确显示；之后仅删除三个独立测试样本，确认原有 Review 数量恢复为 8，未触碰既有业务文件。两 Edge Dashboard 页面可加载；但同会话原生 Chat 页面在 Hermes 重建后持续显示“Chat connection interrupted / Reconnecting”，Gateway health 200、状态 Running，日志未见对应 ERROR/Exception。该 Chat UI 连接异常尚未定位；未在本授权范围内重启 Gateway、改反代/网络或扩大排障。此项需单独跟进，不能标记为全面用户验收。

异常回退原则：恢复捕获功能时只能恢复此前安全的 Inbox/Review/KnowledgeAssets 捕获设置，绝不恢复 Hermes Knowledge RW。若不能在此约束内恢复功能，停止并报告。回滚快照保留供核对；之后如需实际回退，必须逐项过滤 Compose，保持 Knowledge 子挂载删除与精确 safe-root。

## Dashboard / FE-4

- 正式插件 `secondbrain`：`/volume1/docker/secondbrain/hermes/data/plugins/secondbrain/dashboard/`，路由 `/secondbrain`；测试插件 `secondbrain-fe-test` 使用独立目录、身份和回滚资产。Hermes 原生 Chat `/chat`。生产 Dashboard 可通过 `http://192.168.3.27:9119` 访问，另有 DSM LAN-only HTTPS `https://zxwan520.com:63012` 入口。
- Home API `GET /api/plugins/secondbrain/home`；认证插件 API 在 Hermes Dashboard 会话下运行。Private 与 00-Inbox 由正式 API 拒绝。业务写入仍受受控流程约束。
- 曾部署 manifest v0.2.3 指向 `index-20261013-fe4-review.js`（SHA-256 `10039c5ec25a2a23cff8fa94f844acc529aeef3cd603fa8297f6afe46b8f3b92`）。该 bundle 以原始 FE-4 `index-20261012-review-page.js` 字节为前缀（78,453 bytes；SHA-256 `6cf72d312adac4c7f4b483f777618c6c040fa9a0f140c5d8f459758add5642fe`），再附加 D071 Review UI。v0.2.3 manifest SHA-256 `bcc33a703b9ba3c1e4ea3088c4eca3ebbc7a36e05f73e73cacfe25b1b6dfd0f1`；插件 API SHA-256 `e648afa1a53a2b6c0fd601344bdddfee1e3ade0b1ed97d614ca0692561ec73d3`；CSS SHA-256 `9de0d0d52b2c7117ea16719d01bca616abdf57bd81548a7ba56d5007cce89990`。v0.2.3 前端在生产持续 Loading，已按下文记录回退到原 FE-4 入口。部署前 v0.2.2 manifest 快照 `/volume1/docker/secondbrain/hermes/data/secondbrain-fe4-rollback/d071-20261013-fe4fix-01/manifest.json`（SHA-256 `655300ebd2f3f664f8b611e6bfec5f0abbf98bd24e92d26c899fece2e7b604f4`）仍保留；所有版本化 bundle 与 D071 后端均保留。
- 正式回滚目录 `/volume1/docker/secondbrain/hermes/data/secondbrain-fe4-rollback/fe4-20261011-155631/`，包含 `rollback.sh` 和被替换资源快照。部署前应重新确认回滚文件存在和目标版本。

## DSM HTTPS / CORE-4 入口与隔离基线

- DSM 7.4.1 使用现有 Let's Encrypt `zxwan520.com` / `*.zxwan520.com` 证书（核验有效期 2026-09-25 至 2026-12-24）。现有 host+port 反代规则上新增两条 SecondBrain 规则：Dashboard `https://zxwan520.com:63012` → `http://192.168.3.27:9119`；Core `https://zxwan520.com:63013` → `http://127.0.0.1:9120`。两条均绑定 `SecondBrain LAN-only` Access Control profile；Dashboard 原 HTTP 入口仍保留。
- AccessControl.json 中 `SecondBrain LAN-only` 的实际规则为允许 `192.168.3.0/24`，拒绝 `0.0.0.0/0` 和 `::/0`；ReverseProxy.json 确认两条规则均绑定其 profile。两条规则采用同一 HTTPS 主机、不同端口，不是同源（Origin 含端口），因此 Core 仍需精确 CORS Origin 与 credentials。
- 既有隔离 Docker 测试中，root + Knowledge RO 写入被拒；Core `1026:100` 可读 Review/secret、写 Knowledge/state、不能写 Review；模拟 Hermes 未挂载 Core secret/state。临时目录已清理，未改真实 ACL/数据。2026-10-13 新鲜 NAS `stat` 实测 Review/Knowledge mode 为 `0777`（并非历史记录的 700），当前 DSM ACL ACE 见上文。此前 Docker socket 拒绝普通 SSH 身份；本次通过现有 `sudo -n` 已完成运行时 mount/UID/环境核验。
- 正式项目 `/volume1/docker/secondbrain/compose.yaml` 中 Core service 仍属于现有 SecondBrain Project。配置 UID 1026:100；Review、Knowledge 为 RO；state RW、Core-only secret RO；Promote=false。DSM 反向代理实际对端从 Core 访问日志确认为 172.18.0.1，`SB_TRUSTED_PROXY_IPS` 现仅设该精确地址；Host allowlist 仍 zxwan520.com。Compose 回退副本 `compose.yaml.pre-review-proxy-20261012` 保留；本次从新构建上下文仅更新 Core，Hermes 仅因 Dashboard API 文件变更而重启。
- Mac 局部 curl --resolve 验证 Core TLS/健康 200；锁定态列表与详情均 401，非法 Origin 403。通过 63013 HTTPS 提交伪造 X-Forwarded-Host 或 X-Forwarded-Proto 未绕过会话校验。新静态 Review 入口可由 NAS 插件目录提供；未解锁读取 Review 内容。用户此前报告真实 Edge Dashboard 登录成功；Codex 可控标准 Edge 仍遇公网 DNS 路径拒绝，最新完整列表/详情需用户在真实 Edge 中刷新并解锁确认。

## Universal Capture / Promote

- Production Skill `universal-capture` v0.1.3，已接受范围为文本 Raw/Review；生产 URL/Web、PDF、Image/Screenshot、Audio/Voice 处理尚未实现。生产 Human Approval 仍是进入 Knowledge 的业务规则。
- Promote 与审批 API 已实现并通过此前隔离测试；正式项目 Compose 中 Core service 当前 healthy，但 `SB_PROMOTE_ENABLED=false`、Knowledge 为 RO。Dashboard 加法 bundle 已发布；Core health API 可访问，真实认证 Review 浏览器读取未验证；无正式 Knowledge 写入。

## 治理安全写入与同步

- NAS `safe-governance-write.sh`、Live Mirror 和 Google Drive 项目文档发布流程已退役；旧项目目录与专属治理快照已清理。正式文档以 GitHub 历史为准，不再从 NAS 发布或回写。旧迁移记录中关于 NAS-first Google Drive 发布脚本“正式采用/迁移”的条目已被此退役状态取代，不代表仍有活动发布入口。
- Synology Drive 保持既有客户端和同步任务关系，未重建任务、修改共享目录或权限。客户端配置指向本地 `/Users/joe/SecondBrain/`，曾显示已为最新；实际双向文件传播尚未单独验收。历史 `SynologyDrive stopped` 是套件状态报告，未确认是套件真实停止还是检测不准确，不据此宣称同步故障。
- 本地迁移备份已按迁移清理完成；NAS 生产回滚镜像、正式插件/Skills 和仍有运行用途的恢复资产保留，具体回滚路径见上文。
- NAS 专用 SSH key 已配置；NAS SCP/SFTP subsystem 曾不可用，普通 SSH 可用于有界核验/传输。连接失败不改 NAS SSH/权限来绕过。

## 重验触发条件

只有命令失败、Hermes 镜像/版本/容器重建、Compose/挂载/网络变化或正式部署后，才重新核验对应环境事实。Private 内容和认证秘密不属于本基线。

## D071 前端状态（2026-10-13）

- D071 后端 API 已部署并保留。由于 v0.2.3 前端页面持续 Loading，正式 manifest 当前恢复到回滚快照 `d071-20261013-01/manifest.json`：v0.2.1，entry `index-20261012-review-page.js`，CSS `style-20261010-v3.css`。FE-4 JS SHA-256 `6cf72d312adac4c7f4b483f777618c6c040fa9a0f140c5d8f459758add5642fe`；CSS SHA-256 `9de0d0d52b2c7117ea16719d01bca616abdf57bd81548a7ba56d5007cce89990`。
- 切换前 v0.2.3 manifest 保存在 `/volume1/docker/secondbrain/hermes/data/secondbrain-fe4-rollback/d071-20261013-fe4rollback-02/manifest-before.json`。当前 D071 `plugin_api.py` 未回滚，SHA-256 `e648afa1a53a2b6c0fd601344bdddfee1e3ade0b1ed97d614ca0692561ec73d3`。D071 前端集成暂缓，用户 Edge 验收未完成。
- Hermes 插件清单缓存刷新后，健康 200、插件清单返回 v0.2.1 并指向 FE-4 资源。匿名静态资源请求被重定向到登录页，资源 HTTP 返回体/MIME 和浏览器视觉仍需登录态 Edge 验收；不能据本地 MIME 映射等同证明生产浏览器已成功渲染。

## D071 v0.2.4 部署状态与 Loading 隔离验证（2026-10-13）

- 正式生产 manifest 已为 v0.2.4，entry `index-20261014-fe4-review.js`，CSS 继续为 `style-20261010-v3.css`。正式 manifest SHA-256 `aed54f754d447b1812583c4659966be9f66521897a03ba6895a87e53d0ff39fb`；新 JS SHA-256 `acd77192393c4ea74a3b55cde61c596bfb0257510b20df91c8073bd1a761fcb4`。FE-4 固定前缀仍为 78,453 bytes / SHA-256 `6cf72d312adac4c7f4b483f777618c6c040fa9a0f140c5d8f459758add5642fe`；原 FE-4 JS、CSS 与 D071 `plugin_api.py` 哈希均保持不变。
- 切换前 v0.2.1 manifest 的独立回滚副本保存在 `/volume1/docker/secondbrain/hermes/data/secondbrain-fe4-rollback/d071-20261013-pre-v024/manifest.json`，SHA-256 `173b069c7ff293a0b3e1c97bad2f7b6139fd42e23a4fe11cda6cc916f3243c1d`；既有快照 `d071-20261013-01/manifest.json` 与旧版 bundle 均保留。只需恢复该 manifest 并刷新 Hermes 插件清单即可回滚前端，D071 API 不变。
- 部署后 `/api/dashboard/plugins` 返回 v0.2.4 与新 entry，`/api/health` 返回 200；匿名 rescan 返回 401，因此仅重启 `secondbrain-hermes` 一次刷新插件缓存，未重启 Core。匿名 Review API 返回 401（预期安全拒绝）；已登录 Edge 上的 Review 列表/详情和跨站浏览器验收仍待用户完成。用户已在全新 Edge 标签验收 FE-4 视觉与首页真实数据。
- `secondbrain-fe-test` 仅更新隔离 JS/CSS，无 Hermes 重启。测试 JS SHA-256 `4300d65cf33cd1dc3e7e112b7230767c413dcb57e066d00e4c97873504582a1e`，CSS SHA-256 `8db124f950e13cb3b9dc5c2cc377f79ad1df8434934dbe1247bfa35714a94bb2`。新 Edge 标签在 LAN HTTP 上实际渲染 FE-4 与隔离 Review 挂点；Review API 因 HTTP Origin 不匹配而按策略拒绝。DSM HTTPS 63012 从自动化浏览器不可达，故仍待可用 Edge 会话验收。
- Hermes v0.21.5 health 200；Core running、`SB_PROMOTE_ENABLED=false`、Knowledge RO、Private 未挂载。生产部署后再次核对这些状态未变化。

## 2026-10-14 D074 App NAS 部分部署与阻断

- 预部署快照：`/volume1/docker/secondbrain/rollback/d074-deploy-preflight-20261014-154943/`；包含原 Compose、必要 `.env`、脱敏容器元数据、镜像清单及恢复说明，目录/文件权限为 `0700/0600 root:root`，逐文件比较与 SHA-256 校验通过。旧 Core image 和 `/volume1/docker/secondbrain/core-state` 均保留。App 登录密码、Hermes API key 分别存于 `/volume1/docker/secondbrain/app-secrets-d074/` 私有文件，未写入 Git 或本文。
- 当前 Compose `/volume1/docker/secondbrain/compose.yaml` SHA-256 `db81653a11877bf6a81935e1b2eecce5235956499dcbd7ee75f9b4d5814ae72a`，`docker compose config --quiet` 通过，services 仅 `hermes`、`secondbrain-app`。运行时容器仅 `secondbrain-hermes` 与 `secondbrain-app`；Hermes 固定 digest 未变且运行，App image `secondbrain-app:d074-e58a7f4-20261014` 运行/healthy，身份 `1026:100`，仅 `127.0.0.1:9120->8000`。Hermes 8642 无宿主映射；9119 仍只绑定 `192.168.3.27`。App 的 Review/Knowledge/secret mounts 为 RO，state RW；Private 未挂载，`SB_PROMOTE_ENABLED=false`。Core 原容器已移除，原镜像及 state 可用于恢复。
- Hermes API key 由私有 `hermes-api.env` 注入，并与 Hermes data `.env` 中实际优先读取的 API key 对齐；App 容器以只读 secret mount 使用同一服务端凭据。Hermes `/api/sessions` 通过 Docker 内部 API 由 App 获取 200；未将 8642 发布到宿主。Hermes 容器路由表仍显示默认网关 `172.18.0.1`，与既有网络设计一致；本轮未改 PBR/WireGuard/iStoreOS，未取得 wg0 逐流证据。
- DSM Container Manager GUI 中已登记项目 `secondbrain`，目录 `/volume1/docker/secondbrain`。首次登记未勾选“创建后立即启动”。但 GUI 项目详情刷新后仍把 Hermes 显示为旧名 `8fad22e58156_secondbrain-hermes`/旧镜像 `nousresearch/hermes-agent:latest`，且 GUI 保存编辑时使用缓存旧定义启动了旧 Core 并尝试绑定已占用的 App 端口。已立即停止并移除旧 Core 容器、恢复 Compose 管理的 App；持久化 state、旧 Core 镜像与部署快照未动。**禁止在该 GUI 项目定义对齐前点击项目级启动/重建；GUI 仅显示 2 条不能视作最终验收。**
- DSM HTTPS `https://zxwan520.com:63013`：服务端真实登录 200，返回 Secure/HttpOnly/SameSite Cookie；`/api/auth/session`、`/api/home`、Review API 均 200，Home 报告 Agent online、8 条 Review。静态 HTML/JS/CSS 及 MIME 均 200，但 Edge 页面目前空白且没有可访问的 DOM 文本。HTTPS Chat SSE 请求握手返回 200，但等待约 60 秒未观察到任何事件内容；须核查浏览器 Console、反向代理缓冲和上游 SSE，不能标记 Chat HTTPS 验收。内网 HTTPS 63013 有效登录/读取已由服务端探针证明；人工浏览器验收未完成。
- Docker 内部 HTTP 的 Hermes Chat 已真实完成多轮 Session、SSE delta、tool.started/tool.completed/run.completed、history、重连状态恢复和 Stop→cancelled 测试。测试 Session `D074 deployment smoke 2026-10-14` 留在 Hermes，未清理。正式 9119 和 DSM 63012 未切换；Promote 未启用，未执行 Knowledge 写入。
- 回滚路径：停止/移除 `secondbrain-app` 后，基于快照中的旧 Compose、保留镜像及 state 重建旧 `secondbrain-core`；恢复 Hermes 前须保持 Knowledge RO、Private 不挂载、Promote false。完整旧 Hermes/Dashboard `.env` 由快照中的受限文件恢复。不要整体 `compose down`，不要把 App secret 写入命令输出或 Git。
- **部署状态：部分完成，待处理阻断。** 下一步先通过 Container Manager 正式项目流程使 GUI 配置准确反映当前审核 Compose（不使用私有 API/数据库）；再定位 Edge 空白与 HTTPS SSE；随后重新验证 GUI 中恰有目标两个运行容器，并由用户完成 App 浏览器验收。Core RW、Promote、正式端口切换仍未获授权。

## 2026-10-14 D074 React P0 热修复部署

- 最小代码修复：`src/main.tsx` 显式导入 React，与 Vite classic JSX runtime 一致；检查发现 `App.tsx` 已导入 React，其他 JSX 入口无同类遗漏。未改 FE-4 视觉、Hermes、权限、网络、Secret 或 DSM 反代。
- 本机及 NAS Docker build 中前端 `npm run typecheck`、`npm run build` 均通过。部署镜像为 `secondbrain-app:d074-e58a7f4-reactfix-738f392`，镜像 ID `sha256:432c85f29cc381ceecb3984f46eb739033ddda7592daf56f2c2321356ab2e331`；前端 bundle `index-CILWX8FO.js` 不含旧错误文本或未绑定的 `React.createElement` 引用。`git diff --check` 通过。
- 仅执行 `docker compose ... up -d --no-deps --force-recreate secondbrain-app`。App 当前 running/healthy，`127.0.0.1:9120->8000`；Hermes 容器 ID、固定镜像、运行状态未变。当前 Compose SHA-256 `ef692c2b5506cccad0e1f666041dfd9c0990e07bfde9871d32553907ccd420e1`；差异只更新 App 构建上下文路径与 image tag。权限/网络/Secret 配置未改。
- 热修复前快照 `/volume1/docker/secondbrain/rollback/d074-reactfix-738f392-20261014/` 保留原 Compose、App 运行元数据与旧镜像 ID；Compose 快照逐字节核验相同、文件 SHA-256 校验通过，可用原镜像 tag 和该快照恢复原 App。
- 63013 HTTPS 返回 HTML 200、JS `text/javascript` 200；浏览器登录页实际渲染，Console error/warn 为 0。服务端登录 200，Cookie `Secure; HttpOnly; SameSite=Strict`；`/api/auth/session`、`/api/home`、Review 真实数据与 Hermes capabilities/sessions 均 200，Home Agent online。登录后的 Home 页面未在浏览器中实际呈现，仍待用户会话验收。
- 63013 Chat 真实运行创建成功，SSE 返回 200 并送达 `message.delta`、`reasoning.available`、`run.completed`；run 状态 completed。先前记录的“200 但无事件”来自诊断脚本只计数独立 `event:` 行，而 BFF 按 `data:` JSON frame 传输，修正解析器后已有事件证据。两次 smoke 运行在 Hermes 中保留；无业务文件被修改。
- 容器管理器 GUI 项目定义旧缓存问题未处理；本轮没有 GUI 项目级操作。9119/63012 入口、Knowledge RO、Private 隔离、`SB_PROMOTE_ENABLED=false` 保持。部署状态仍为部分完成；待 GUI 定义核对和登录后 Home/Review/Chat 浏览器验收，完整 V1 未完成。

## 2026-10-14 D074 App 登录失败诊断

- 生产 App 最近的 `/api/auth/login` 访问日志：09:43:24Z 有一次 403（本地诊断探针未带 `Origin`）；同源 `https://zxwan520.com:63013` 请求随后 200。09:49:17Z、21Z、23Z 为 3 次 401；没有 429 或 500。限流在连续 5 次失败后触发，当前 App 后续单服务重建已清空进程内计数。
- App Secret 源文件 `/volume1/docker/secondbrain/app-secrets-d074/secondbrain_app_password` 以只读 bind mount 到 `/run/secrets/secondbrain_app_password`；两侧 mode `0600`、owner `1026:100`、48 bytes。App 于 09:41:10Z 启动；`AppSessionAuth` 在启动时读取该文件、对文件字节 `.strip()` 后以 UTF-8 输入做常量时间精确比较。用该挂载 Secret 对实际 HTTPS 登录的服务端探针返回 200，并取得 `Secure; HttpOnly; SameSite=Strict` Cookie 和 Home API 200，证明挂载/加载/HTTPS Origin 正常。
- 在 NAS 进程内将 App Secret 与 Hermes 当前 `HERMES_DASHBOARD_BASIC_AUTH_PASSWORD` 做相等比较，只输出匹配结果及长度：不匹配；App 48 bytes、Hermes 9 bytes。明文未输出或记录。故使用与 Hermes 相同的用户输入命中 401，是当前 App Secret 未同步的服务端配置问题；不是 403/代理校验，也没有证据显示输入编码或空格问题。直接同步 9-byte 凭据会被 App 当前 12-byte 最低长度校验拒绝。本轮没有降低该门槛或更改任何 Secret，等待最小安全策略确认。
- 前端登录错误现按 401 凭据校验、403 来源校验、429 限流、5xx 服务异常及其他状态分别提示，不再把所有非 429 一律显示成密码错误。`npm run typecheck` 与 `npm run build` 通过；NAS 单服务构建也通过。部署 `secondbrain-app:d074-e58a7f4-auth-status-ba2f040`，App healthy；Hermes 未重建。当前 Compose SHA-256 `14ebd79e5571d42411652c0eabd40a65ae4da7301c4f5bc6f8f5c183197296f0`，仅 App build context/image tag 变化。
- 本次回滚快照 `/volume1/docker/secondbrain/rollback/d074-auth-status-ba2f040-20261014/`（目录 `0700`，含旧 Compose、旧 App image ID 与运行元数据；不复制 Secret）。63013 HTTPS 登录页仍可渲染，Console error/warn 为 0。以当前 App Secret 登录的真实 Home API 返回 8 条 Review、Agent online；用户浏览器输入旧 Hermes 凭据仍会按 401 拒绝，因此登录后的 Home UI 尚未验收。未改 Hermes、DSM、Project GUI、Knowledge 权限、Private、Network 或 Promote 状态。

## 2026-10-14 D074 独立 App 凭据轮换与登录回归

- 按用户最终决定保留 App 现有 12-byte 密码下限，使用 Mac Terminal 隐藏输入设定与 Hermes Basic Auth 不同的 App 密码。更新前受限快照 `/volume1/docker/secondbrain/rollback/d074-app-password-rotate-20261014/` 保存原 Compose、原 App Secret、旧 App 镜像 ID 与运行元数据；Secret 备份仅供受控回滚，未进入 Git 或聊天。新 Secret 保持源文件原 inode、owner `1026:100`、mode `0600`，App 内只读挂载；在 NAS 进程内比较确认与 Hermes 凭据不同，未输出任一明文。
- 仅 `docker compose ... restart secondbrain-app`；App 2026-10-14 10:19:52Z 启动并健康运行，Hermes 未重建。启动窗口的一次 HTTPS 登录探针收到 502，后续 63013 `/health` 为 200；重新验证时 App 访问日志中 `/api/auth/login`、`/api/auth/session`、`/api/home`、`/api/promote/review/items`、`/api/promote/status` 均为 200。验证程序在继续 GET 前检查登录 Cookie 的 `Secure`、`HttpOnly`、`SameSite=Strict` 标志；没有记录 Cookie 值或密码。
- 用户在 63013 浏览器输入新密码后，页面实际显示登录后 Home（Hermes 在线、8 条待审核、2 条 Knowledge）及 Review 列表/首条详情；批准入库按钮因 Promote 关闭而禁用。此为浏览器运行核验，用户最终验收与 Chat 浏览器交互仍待完成。
- 运行时复核：App `SB_PROMOTE_ENABLED=false`，App `/knowledge` RO；Hermes `/secondbrain` RO，只有 Inbox、Review、KnowledgeAssets Inbox 三处捕获写挂载；Private 未挂载；App Secret mount 为 RO。未改 Compose、Hermes、DSM、项目 GUI、网络或业务数据。DSM Container Manager GUI 旧缓存定义仍是独立阻断项；9119/63012 保持原状态。若需回滚密码，须在保持文件 `1026:100/0600` 和原 inode 的前提下从上述受限快照恢复原 Secret，并只重启 App；不得把旧 Secret 写入命令、日志或 Git。
- 63013 浏览器内置 Chat 已真实加载 Hermes 现有 Session/历史；在既有 D074 smoke Session 发送一条无工具测试消息，页面先显示运行中，随后通过流式传输得到预期回复并显示完成；刷新 `/chat` 后双方消息仍可见。仅新增这条测试对话消息，未调用工具或写业务文件。浏览器停止任务与工具进度尚未重测；此前 Core/Hermes API 级 Stop、tool event 证据不能替代浏览器验收。
