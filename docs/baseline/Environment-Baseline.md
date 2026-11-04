---
created: 2026-09-28
updated: 2026-11-04
status: current
type: environment-baseline
---
# Environment Baseline

## 2026-11-04 #269 App-only 发布准备（未部署）

- **源码与候选：** PR #269 merge SHA 及 App 候选固定源为 `d06e3f3bde2cf8ee260992644c2ae5d67aeef362`；当前 GitHub `main` 为 `02dcf9707bdf08df5bea77a79e7206aae4159194`，仅多出 PR #270 文档状态更新。相对当前生产 revision `ce247d0c2f014c67f407c7b8721022da6afe2753`，运行时应用改动仅 `web-app/secondbrain-frontend/src/App.tsx` 与 `src/styles/app.css`；Core、Hermes、依赖和 Dockerfile 无代码差异，没有数据迁移。其余差异仅为合成测试/探针与文档。
- **构建和隔离启动：** Ubuntu 24.04 Actions [#41788688422](https://github.com/zxwan829/SecondBrain/actions/runs/41788688422) 在精确 HEAD `d06e3f3b` 成功。App 镜像构建、隔离网络/只读根文件系统/`1026:100` 启动、`/health` 为 ok、`/notes` 200 及 `SB_PROMOTE_ENABLED=false` 均 PASS。固定 Hermes 步骤也通过既有 smoke；生产 Hermes 未变更。
- **App 镜像与工件：** tag `secondbrain-app:candidate-d06e3f3bde2cf8ee260992644c2ae5d67aeef362`；image/config ID `sha256:250437fc8b57642770347d6de73d86e791ffd8aaebdaba399170bc5018fe2270`；OCI manifest digest `sha256:e2bacc0e6b72ed29116e3ec29c44abaafd458dcf9048168f521307399399ddd7`；revision label 与目标 SHA 一致；平台 `linux/amd64`。GitHub artifact ID `13301449533`、digest `sha256:e6040f9c7262b8477169ef0e5fd8a1a1e7959d1b2857e423dd33c0cae7a89b9c`，原包 `SHA256SUMS` 校验通过（包内镜像归档 SHA-256 `8a150cebff3dbf4920b4116ea82c37174af5a6addf0e72185329889ef5aba31c`）。提取后的 App-only OCI/Docker 兼容归档 SHA-256 为 `49905f26e9fc7780a1a58be693f7d1558b989421291ffcfa417a3856674e684a`；仅含 App image，配置 digest、索引、manifest 和所有引用层 SHA 校验通过，无 Hermes 引用。Actions 原始工件保留 14 日。
- **当前生产只读基线：** App image ID `sha256:e201c93c7f19ec1ac15f742659ce023a0f12228fd846035090e42f6e69d3cec5`、revision `ce247d0c`、running/healthy、UID/GID `1026:100`、restart count 0、仅发布 `127.0.0.1:9120→8000`。Compose SHA-256 `0aedb4b104870ddc5ce23a2f1adde10b84b51bf06f7e35d3377356bcc5a84708`；服务为 `hermes` 与 `secondbrain-app`，App 依赖 Hermes `service_started`，默认网络；挂载为 Core state、Review、Inbox 可写，Knowledge 只读，两个 Secret 文件只读，未挂载 Private。Promote 仍 false，Weixin 开关未设为开启。实际配置的 App 环境字段名、端口、依赖、网络、挂载及权限均已白名单读取；未输出环境值或 Secret。
- **部署与回滚边界：** NAS 当前已存在的 App 镜像已验证可用作回滚目标；Compose 当前 App image tag 为 `secondbrain-app:candidate-ce247d0c2f014c67f407c7b8721022da6afe2753`。计划变更仅将该行替换为上述 d06 候选，并用 `docker compose ... up -d --no-deps --no-build --force-recreate --pull never secondbrain-app` 单独重建 App。用户未授权前没有导入候选、复制/写入生产备份、修改 Compose 或重启服务；获授权后才保存当前 Compose 及 SHA-256，再执行切换。失败时仅恢复该 Compose 快照并用已验证的 ce247d0c 镜像单独重建 App；不回滚 Core state、不触碰 Hermes 或其他数据。

## 2026-11-03 只读运行复核（V1 首轮体验准备）

- **范围：** NAS SSH 只读查看容器列表/inspect、指定非敏感开关、挂载目标与权限、Compose 摘要；对线上 HTTPS 仅发无凭据 GET。未读取 Secret、Compose 正文、Vault/Private、用户正文或生产目录文件；没有登录、写入、模型调用或服务变更。
- **源码基线：** GitHub `main` 为 `9c37cea6babd933d488f2adab546e4b761860abf`。App revision label 为 `ce247d0c2f014c67f407c7b8721022da6afe2753`；Hermes 容器没有 SecondBrain revision label，其 Image ID 与 2026-10-24 已记录快照一致。GitHub compare 确认 SecondBrain `ce247d0c..9c37cea` 的 5 个提交只修改 4 份文档，没有 App/Core 源码差异。正式 Compose SHA-256 为 `0aedb4b104870ddc5ce23a2f1adde10b84b51bf06f7e35d3377356bcc5a84708`，与 2026-10-24 快照一致。
- **App：** `secondbrain-app:candidate-ce247d0c2f014c67f407c7b8721022da6afe2753`，Image ID `sha256:e201c93c7f19ec1ac15f742659ce023a0f12228fd846035090e42f6e69d3cec5`，running/healthy，RestartCount 0，运行身份 `1026:100`，启动时间 `2026-10-29T15:08:31Z`，只发布 `127.0.0.1:9120->8000`。容器挂载 `/knowledge` 为 RO，Private 未挂载；Capture Inbox、Review、Core state 仅挂载到其既有应用路径。Secret 仍以只读文件引用挂载，本轮未读取。
- **Hermes：** `secondbrain-hermes:candidate-ce247d0c2f014c67f407c7b8721022da6afe2753`，Image ID `sha256:73f4f332f36584a4f99c7ee0bc7f13c23b3f722e3960cab9095f7d511cce9821`，running，RestartCount 0，Docker 未配置 healthcheck，运行身份 root；只发布 `192.168.3.27:9119->9119`。Hermes 的 `/secondbrain` 根挂载 RO，Private 未挂载；可写挂载仅为既有 Inbox/Review 捕获路径。`HERMES_WRITE_SAFE_ROOT` 实际值为 `/secondbrain-write/00-Inbox:/secondbrain-write/10-Review:/knowledge-assets/00-Inbox`。
- **安全开关：** App/Core `SB_PROMOTE_ENABLED=false`；App/Core `SB_WEIXIN_INBOX_ENABLED` 未设置（未观察到开启值）。未更改 API Terminal、Writer、Promote、Weixin 或权限。
- **运行探测：** 当前网络对 `https://zxwan520.com:63013` 的无凭据 GET：`/health`、`/`、`/login`、`/notes` 均 200；匿名 `/api/auth/session`、`/api/tasks`、`/api/inbox/summary`、`/api/knowledge/search`、`/api/promote/status` 均 401。NAS 内 Hermes `127.0.0.1:8642/health` 与 App 容器到 `http://hermes:8642/health` 均 200。通过 HTTPS 反向代理的 App health 为 200；容器内直接访问 App HTTP 端口返回 400，未绕过来源校验。
- **生产操作与验收：** 未登录真实账号，未请求任何认证后的业务数据；未读写真实 Task、Inbox、Review、Knowledge 或 Notes；未调用模型、渠道、Writer/Promote。SecondBrain App 源码与 main 一致；Hermes 版本/镜像仅按 Image ID 与最近快照匹配，实际个人业务流程和当前用户浏览器仍待用户验收。

## 最新生产部署与验收（2026-10-24；V1 第一阶段）

- **发布来源：** GitHub `main` `ce247d0c2f014c67f407c7b8721022da6afe2753`；Actions [#40075395885](https://github.com/zxwan829/SecondBrain/actions/runs/40075395885)，artifact `12553425795`。ZIP SHA-256 `4ad0b8eb26eb93ebfcf71f18667487122203ef54f31db4c1cd5dffcf5fc7de37`；镜像包 `secondbrain-candidate-images.tar.gz` SHA-256 `079c99c444be8867ccb4396f5344bc859bbc57ffd2d4a9542b0b6543d7329fce`，内部 `SHA256SUMS` 已在本机与 NAS 校验。App 镜像 ID `sha256:e201c93c7f19ec1ac15f742659ce023a0f12228fd846035090e42f6e69d3cec5`，revision label 与 main SHA 相同。Hermes 镜像 ID `sha256:73f4f332f36584a4f99c7ee0bc7f13c23b3f722e3960cab9095f7d511cce9821`，版本 `0.22.2`，上游源码 `d923a5eb487a17c0a68801bba9ef0f56c81040a8`，D078/Weixin overlay SHA-256 `eb20ef03146b1a15eda7659327f777377fefe8584ce45bc5fef3ba1be406d353`。
- **切换与回滚资产：** 受保护目录 `/volume1/docker/secondbrain/rollback/v1-ce247d0c-predeploy-20261024T080514Z/`（父目录 `0700 root:root`）。包含原 Compose 快照 SHA-256 `5703458d5db4703d3a1e9377c3aafbfacc470863b92c15f4305e802f64b1c17b` 与原 Hermes `config.yaml` SHA-256 `34fe0bdad9d6e5990677b87ffa67cfb8fd237a18462da6958737bff23faf9155`；两个文件保留原 `0640 Joe:users` mode/owner，Core state（55 files / 184320 bytes）停 App 后一致复制且保留其 `0700 Joe:users` 目录元数据，文件清单 SHA-256 `1c0aaef4f0556813d02a1de464ca21bdaa62166885346d4dba34c643be8b4087`；另存镜像包。快照父目录为 `0700 root:root`。所有快照校验通过。新 Compose SHA-256 `0aedb4b104870ddc5ce23a2f1adde10b84b51bf06f7e35d3377356bcc5a84708`；与原文件相比仅变更 App/Hermes 两个 image refs；Compose `config --quiet` 通过。旧 App (`sha256:728fc7d180f7687c90c58be2e9beb970a4010bfb10bd04777371861f3139aeeb`) 与旧 Hermes (`sha256:b99b1762631846d5ed3f8648ccc2c7ef2625b004234bbf276add2f8855357e9a`) 镜像仍在本机可回滚。
- **部署验收：** `secondbrain-app` running/healthy、UID/GID `1026:100`；`/health`、`/`、`/notes`、`/login` 返回 200；未认证 `/api/notes` 返回预期 401。App revision label 正确。`hermes` running/root；Dashboard `192.168.3.27:9119/` 返回 302，App 到 Hermes `http://hermes:8642/health` 返回 200。Hermes 插件列表显示活动用户版 `secondbrain-d078-guard` enabled，bundled 版与用户版 SHA 相同；固定镜像内 `secondbrain-weixin-inbox` 文件存在且插件为 `not enabled`。直接对活动 D078 用户插件函数进行的合成无效终端 pre-tool 调用被阻断，未执行命令；这不是 API Terminal/真实模型 Run 验收。活动 Hermes profile SHA 与快照相同。App/Hermes 网络、端口、身份及挂载路径与部署前一致；Private 未挂载。其他容器均保持运行，未重启。Core `SB_WEIXIN_INBOX_ENABLED` 有效值 false，`SB_PROMOTE_ENABLED=false`；API Terminal 配置未改且仍保持关闭。
- **回滚：** 先将快照 `compose.yaml` 原样恢复到 `/volume1/docker/secondbrain/compose.yaml`，执行 `docker compose -f /volume1/docker/secondbrain/compose.yaml config --quiet`，再仅对受影响服务执行 `docker compose ... up -d --no-deps --no-build --force-recreate --pull never secondbrain-app` 和/或 `hermes`。旧镜像已确认存在。不要因镜像回退自动覆盖当前 Core state；本次未发现启动迁移代码，如出现状态兼容疑问，先保留运行期间 state 并评估快照，不盲目恢复数据。
- **尚未验收：** 未登录执行真实用户会话、Chat/Run 或读写个人数据；未扫码、未启用微信或发送消息；没有用户最终体验验收。此记录只代表部署与上述健康/路由检查通过。

## 部署前只读预检（2026-10-24；已由上方生产部署记录更新）

- 本轮经 SSH 对 NAS 执行只读核验，未构建/拉取镜像、修改文件或配置、重启/重建容器、读取 Secret 或业务数据。SSH 本地 known_hosts 更新因当前执行环境权限受限而告警；远端只读命令仍成功，未修改本地权限或 SSH 配置。
- App `secondbrain-app` 容器 `9562e402f72b67b0eacba3a99a0fc23c7c23098c5b8ecebf8517f552dbb29c39`，镜像 `secondbrain-app:m2-pr94-c7eda992-app-only` / `sha256:728fc7d180f7687c90c58be2e9beb970a4010bfb10bd04777371861f3139aeeb`，running、healthy、RestartCount 0，运行身份 `1026:100`，仅发布 `127.0.0.1:9120->8000`。镜像未提供可核验的 OCI source revision label；`c7eda992` 标签对应源码提交仅是来源线索，不是镜像内容证明。相对当前 main `1ddff32463b06753758cae144d79de05632deb52` 的差异很大，需由当前 main 重建 App 候选。
- Hermes `secondbrain-hermes` 容器 `908a4b37c41344e97441013a18995e727971a10242d49dee65e39f3bf00c43d6`，镜像 `secondbrain-hermes:v0.22.2-failclosed-84d1cbaf` / `sha256:b99b1762631846d5ed3f8648ccc2c7ef2625b004234bbf276add2f8855357e9a`，running、RestartCount 0；无 Docker healthcheck。运行身份 root；发布 `192.168.3.27:9119->9119`。镜像标签记录 Hermes 上游 `d923a5eb487a17c0a68801bba9ef0f56c81040a8` 及 D078 patch SHA-256 `b53818487205733039378a8e3c7218cc298eca1c39e1a34dec997dd306f855b0`，未含 Weixin 插件 overlay；镜像内 `secondbrain-weixin-inbox` 插件目录不存在。D078 Guard 目录在活动 Hermes Home 下存在，profile 配置存在且元数据为 `1026:100 / 0640`；本轮未读配置内容，Plugin Doctor 未取得可用的新输出，因此 Hook 当前注册状态仍以历史核验为依据。
- 两容器位于 `secondbrain_default`；App 地址 `172.18.0.2`、Hermes `172.18.0.3`。从 App 容器对 `http://hermes:8642/health` 的只读请求返回 HTTP 200，确认内部 DNS、网络和 API 健康端点可达。Docker Server `24.0.2` linux/amd64。App 容器挂载目标包括 `/knowledge` RO、Core state RW、Review RW、Inbox RW 及两个只读 Secret 文件引用；Hermes 的 SecondBrain 根为 RO，两个捕获目录与 Inbox 为 RW。两容器当前挂载列表均无 Private。
- 运行容器 Compose labels 指向项目 `secondbrain`、服务 `secondbrain-app`/`hermes`、工作目录 `/volume1/docker/secondbrain` 和配置路径 `/volume1/docker/secondbrain/compose.yaml`。Compose 文件仅检查元数据/摘要：`1026:100 / 0640`，SHA-256 `5703458d5db4703d3a1e9377c3aafbfacc470863b92c15f4305e802f64b1c17b`，与 2026-10-19 记录一致；未输出或检查原始 Compose 内容，避免展开配置值。运行时只选取容器身份、网络、挂载目标、环境变量键名存在性等字段。
- Core/Hermes 容器均不存在 `SB_WEIXIN_INBOX_ENABLED`、`SB_WEIXIN_INBOX_HMAC_KEY`、`SB_WEIXIN_ALLOWED_SENDERS_JSON`、`SB_WEIXIN_CORE_INBOX_URL`、`SB_WEIXIN_CORE_INBOX_HMAC_KEY` 这些环境变量键；没有读取任何环境变量值。Core 源码默认关闭微信 Inbox；当前因此未启用。当前 Hermes 镜像没有 Weixin 插件，不能承载微信 MVP。旧 App 回滚镜像 `sha256:e55b0e9c65433a208df0f66a68ec2f91e2341b163108e5d09030ac4a7b343f47` 仍存在；当前运行 App/Hermes 镜像也保留。历史 Hermes 回滚镜像是否仍存在，本轮未查询。
- 当前部署准备为 **NOT READY**：需要从最新 main 构建 App；使用固定 Hermes v0.22.2/D078/Weixin 源码构建并验证新 Hermes 镜像；将 Weixin 配置片段合并进现有 Hermes profile（保留既有设置）、限制为经白名单的私聊并禁用群聊；Core 继续默认关闭，启用时才注入 HMAC 与 sender 白名单引用，Hermes 设置内部 Core URL 与相同 HMAC 引用。Secret 值只能由受保护的 Secret 注入机制提供，不放入 Compose 明文、仓库、日志或聊天。目标影响服务为 `secondbrain-app` 与 `hermes`；扫码需用户本人另行批准和完成。
- 最小回滚建议：部署获批后先保存并校验当前 Compose 快照及摘要，保留旧 App/Hermes 镜像和现有 Hermes profile；若微信验收失败，先关闭 Core 微信开关并禁用 Hermes 微信插件/平台，再恢复快照中的旧镜像引用与原 profile，仅定向重建相关服务并健康检查。保留 Core state/业务目录，不清理镜像或数据。此为准备方案，不是当前可执行授权。

## NAS SSH 与 sudo 提权凭据引用

- NAS SSH 连接引用为用户 `joe`、主机 `192.168.3.27`、私钥路径 `~/.ssh/id_ed25519_secondbrain_nas`。Mac Keychain 服务名为 `JoeNas-sudo`、账户 `joe`；本机 helper 为 `~/.local/bin/joe-nas-sudo`。服务名是 Keychain 项，helper 是调用脚本，两者不可混淆。此处只登记引用，不记录密码、私钥内容或 Secret 值。
- 历史记录：2026-10-09 曾由 helper 成功经 SSH 提权并返回 `uid=0(root)`。本次（2026-10-24）先用现有 `sudo -n` 执行已授权的只读 Docker 查询并成功，因此未调用 helper，也未读取 Keychain 凭据值。helper 存在且当前文件权限为 `0700`；Keychain 项存在性已检查，不读取其内容。历史成功不保证未来通道始终可用，施工前仍需按具体授权范围做只读验证。
- `/private/tmp/nas-sudo-password` 是历史临时密码文件路径，不是今后标准凭据来源。`/etc/sudoers.d/secondbrain-codex-dev` 是历史施工期提权配置，现存状态未核实；不得依赖或修改。普通 `sudo -n` 不可用时，优先按既有 helper 的原生调用方式复用，不要求用户重复提供已配置密码；不得输出、记录、复制或重新保存明文凭据。
- 已有 sudo 通道仅表示可执行相应授权的管理查询，不构成所有 NAS/生产操作的授权。每次仍须遵循用户对具体操作的范围、生产边界和必要批准。

## 最新生产快照（2026-10-19；Hermes 静态 IP 冲突修复，Issue #76）

- 按 Issue #76 评论 #6268120112 完成一次 Hermes-only 修复。已确认根因是 Hermes Compose 固定请求 `172.18.0.2`，与健康 App 在 `secondbrain_default` 上实际占用的 `172.18.0.2/16` 冲突；失败 Hermes 的 Docker 状态为 Created / `Address already in use`。本次仅移除 Hermes 网络项中的 `ipv4_address`，由 Docker 动态分配；服务名、网络、`192.168.3.27:9119` 发布、镜像、挂载、身份、环境/Secret 引用及其他服务配置保持不变。
- 部署前正式 Compose SHA-256 `d34cb7492d3740ea13d6518ec17532ac855bded9bd921d318827c25aaea949d3`。即时回滚快照位于 `/volume1/docker/secondbrain/rollback/hermes-ip-conflict-20261019T132138Z/compose.yaml`；目录 `0700 root:root`，文件 `0600 root:root`，快照 SHA 与部署前正式文件相同且逐字节比较通过。旁置 `metadata.txt` 同为 `0600 root:root`，记录旧容器及镜像 ID；原 Hermes 镜像 `sha256:b99b1762631846d5ed3f8648ccc2c7ef2625b004234bbf276add2f8855357e9a` 与 writable snapshot image `sha256:401cbdbd5254164c0fd7d6276f12b9e4b14ec8f4dea272ce4a99a333aaa075bb` 均保留。候选配置 `docker compose config --quiet` 通过，语义 diff 仅删除该一行。部署后 Compose SHA-256 为 `5703458d5db4703d3a1e9377c3aafbfacc470863b92c15f4305e802f64b1c17b`。
- 唯一容器操作为 Hermes 服务 `docker compose ... up -d --no-deps --no-build --force-recreate --pull never hermes`，未重启 Docker/DSM/Container Manager，未操作其他服务。新 Hermes 容器 `908a4b37c41344e97441013a18995e727971a10242d49dee65e39f3bf00c43d6`，镜像仍为 `sha256:b99b1762631846d5ed3f8648ccc2c7ef2625b004234bbf276add2f8855357e9a`，running、RestartCount 0、StartedAt `2026-10-19T13:22:45.184181626Z`；无 Docker healthcheck。新 endpoint `172.18.0.3/16`，与 App `.2` 不同，网络 ID 未变；容器 endpoint ID `4855c34882eba07c95396bbaff3d016df083e0f5ccdc9497dbe2283a1c19efda`。Dashboard `192.168.3.27:9119/` 返回 302 登录重定向；App 容器经 Compose DNS 请求 `http://hermes:8642/health` 返回 200；App 自身 `/health` 也为 200。启动最初观察到短暂连接拒绝/重置，未重建或重试；约 35 秒内 API 与 Dashboard 检查通过。
- App 保持容器 `9562e402f72b67b0eacba3a99a0fc23c7c23098c5b8ecebf8517f552dbb29c39`、镜像 `sha256:728fc7d180f7687c90c58be2e9beb970a4010bfb10bd04777371861f3139aeeb`、healthy、RestartCount 0；Vaultwarden 保持容器 `964dd1d5a4b506da62f55e26461be56c08a6d9e253b83b617a6b1a0d9dc01270`、healthy、RestartCount 0。13 个容器总数不变；事件核对只有 Hermes 生命周期变化，未见其他容器生命周期或健康状态变化。Hermes 原镜像、旧容器记录及用户备份未清理。
- Hermes 原有挂载、RW 捕获根、只读 SecondBrain 根、端口和网络保持不变；App 的 `SB_PROMOTE_ENABLED=false`、Knowledge RO、Private 未挂载保持。没有业务写入、真实 Vault 读取、模型调用或用户业务验收；没有回滚。根因 **CONFIRMED**，Hermes 服务恢复 **PASS**。容器启动观察及只读健康检查不等于完整 Chat/Run 或业务功能验收。
- 仓库部署环境变量示例采用 `http://hermes:8642` 的 Compose 服务 DNS，没有生产 Compose 模板硬编码 Hermes `.2`；唯一额外的 `.2:9119` 源码命中是 dashboard auth 测试 URL，不是运行部署配置。本次不改业务源码。完整执行证据见 [Issue #76](https://github.com/zxwan829/SecondBrain/issues/76)；本节为最近一次经现场核验的运行快照。

## 前一生产快照（2026-10-19；M2 P1 App-only 部署，Issue #90）

- 固定源码为 GitHub main `443991061ea446686b54bfb9e8b2d980183f1338`。使用 `web-app/Dockerfile.app`、`web-app/` 上下文及 `VITE_ENABLE_NOTES=true` 在 NAS 构建，候选 `secondbrain-app:m2-44399106-app-only` 的 Image ID 为 `sha256:e55b0e9c65433a208df0f66a68ec2f91e2341b163108e5d09030ac4a7b343f47`；镜像标签记录源码 SHA。App 以 `1026:100` 运行。构建警告包括 legacy builder 弃用、npm audit 4 项（2 low、2 moderate）、若干弃用依赖、Vite 大 chunk 与 pip root 安装提示；未升级依赖。
- 隔离预检使用 `network=none`、只读 rootfs、无生产 Secret/卷/端口的临时容器和合成凭据/目录。`/health`、`/chat/blank`、`/inbox/source`、`/review`、`/knowledge`、`/notes` 均 200；14 个 JS/CSS 资源（含 Notes chunk）均 200；匿名 Chat 与 Promote API 均 401 JSON。临时容器及精确合成目录已移除；候选镜像和构建证据保留。
- 切换前 App 容器 `0ab478227d89d81981142493a51e917bac98926b5d4f1089268893f41c5a6a30`，镜像 `sha256:70f8277f4d29c2bf8e50d3f7d135f034f04a90b421928d9836515d79a7143b3d`，healthy、RestartCount 0。正式 Compose `/volume1/docker/secondbrain/compose.yaml` 切换前 SHA-256 `5d15c9ac51d4bd9f3cd682ef60e4e97d77b5d7e212ae73d0bf5e3126aad0da8d`；部署前即时快照 `/volume1/docker/secondbrain/rollback/m2-44399106-predeploy-20261018T175818Z/compose.yaml`，目录 `0700 root:root`、文件 `0600 root:root`，快照哈希与切换前正式文件一致。只修改 App image 引用；Compose config 校验通过。
- 部署使用 `compose up -d --no-deps --no-build --force-recreate --wait --wait-timeout 120 secondbrain-app`。App 在 37 秒内 healthy；新容器 `a574dd88d9bd87c3d94f584791312473e91eeeeb2ffdac64c6684f972be506cb`，候选 Image ID 一致，RestartCount 0，StartedAt `2026-10-18T18:07:44.121586385Z`。部署后 Compose SHA-256 `a0d6775e8a785845ee32369a68141410e99988df316714f507b0d98743734686`；仅 App image 改变，所有其他 Compose 配置/挂载保持原样。未回滚。
- 部署后经本机容器与既有 DSM HTTPS 反向代理执行只读 smoke：`/health` 200；`/chat/blank`、`/inbox/source`、`/review`、`/knowledge`、`/notes` 200 HTML；14 个静态资源 200；匿名 Chat、Promote API 401 JSON。无登录生产页面、无 Session 或业务请求、无模型调用。
- Hermes 容器 `057324a9e438969320e84d7c3cbad58e3f010637d7dd00d5967123b034eada79`、镜像 `secondbrain-hermes:v0.22.2-failclosed-84d1cbaf` / `sha256:b99b1762631846d5ed3f8648ccc2c7ef2625b004234bbf276add2f8855357e9a`、StartedAt `2026-10-17T08:33:24.151798238Z`、RestartCount 0 与部署前一致；状态为 running（未配置 healthcheck）。Guard 无独立容器。Promote=false、Knowledge RO、Private 无挂载均保持；核心状态中新建 `b1b-operations` 子目录，`1026:100 / 0700`，空目录，`audit.jsonl` 不存在。业务验收 NOT RUN，用户验收待独立复审。
- 宿主路径元数据对 Review、Knowledge、Capture Raw 显示 `0700 / 1026:100`，而容器视角 bind 根目录显示 `0777`；本轮仅确认 Compose RO/RW 标志，未调查 ACL/挂载层差异。该权限视角差异根因 **UNKNOWN**，不得视为已解释或 ACL 安全结论。未执行权限修改或写探针。

## 前一生产快照（2026-10-18T09:44:06Z 起；PR #72 合并后 M1 App-only 部署，已由 M2 P1 替换）

- 按用户明确授权，以固定源码 `473948dd2e9b3d448b71eeba56a1474454883353`、`web-app/Dockerfile.app`、正确 `web-app/` 构建上下文及 `VITE_ENABLE_NOTES=true` 构建完整 App。候选与运行镜像 `secondbrain-app:m1-473948dd-notes`，Image ID `sha256:70f8277f4d29c2bf8e50d3f7d135f034f04a90b421928d9836515d79a7143b3d`；运行身份 `1026:100`、`SB_STATIC_ROOT=/app/static`。本机无 Docker daemon，故经批准在 NAS Docker daemon 构建；使用 legacy builder（NAS 无 buildx），构建限制为 CPU 0-1 与 8 GiB 内存。构建期间 App/Hermes 资源占用保持低位，未发现其他服务异常。构建日志报告 npm 4 项依赖审计发现（2 low、2 moderate）、弃用依赖、Vite 大 chunk 警告及 pip root 安装警告；未升级依赖。前端定向 25 项、typecheck、`VITE_ENABLE_NOTES=true` build 通过。
- 隔离容器预检 PASS：`network=none`、read-only rootfs、无生产端口/Secret/业务卷，只有临时 tmpfs 与随机合成 App password。修正一次合成 password 文件 mode 后，`/health` 200、`/chat/blank` 与 `/inbox/source` 200 HTML、入口 JS/CSS 与 Notes JS chunk 200、匿名 Chat API 401 JSON。临时容器已移除；候选镜像保留。无模型调用或生产业务请求。
- 切换前 App 容器 `bd450fb6b42d32e5a23f4581c5fd76c0454d66904dff3022f81dca2dd95da7d7` / Image ID `sha256:4adcf9cfe3f6257c733efa911455ca02653783ba763f9e2f512f4d3582694ce1`，健康、RestartCount 0。正式 Compose `/volume1/docker/secondbrain/compose.yaml` 前 SHA-256 `5c12fda28f3e5e9cd001d238515bd6599adaf5e502686f5d30fcbcb4a8c72f80`；仅 App `image` 引用改变，Compose `config --quiet` 通过。切换命令为 `compose up -d --no-deps --no-build --force-recreate --wait --wait-timeout 120 secondbrain-app`。App 约 39 秒 healthy；新容器 `0ab478227d89d81981142493a51e917bac98926b5d4f1089268893f41c5a6a30`，RestartCount 0，StartedAt `2026-10-18T09:44:06.325478073Z`。
- Compose 部署后 SHA-256 `5d15c9ac51d4bd9f3cd682ef60e4e97d77b5d7e212ae73d0bf5e3126aad0da8d`。唯一差异是 App 镜像引用；UID/GID `1026:100`、Notes 环境（`SB_NOTES_DRAFTS_ROOT=/var/lib/secondbrain-core/notes-drafts`、`SB_NOTES_AUTHORIZED_ROOTS={}`）、Promote=false、Secrets 引用、端口、依赖、网络及挂载不变。容器视角 Core state 与 Notes Drafts `1026:100 / 0700`；Review 与 Capture Raw 可写、Knowledge 只读，Private 与 Projects 未挂载。现有个人记忆/学习环境开关未变；本次没有 Chat Run，Organizer model/scheduler 均关闭，未调用模型。仅核验 Core-state 目录权限/名称元数据，未读取文件内容；缺少部署前目录清单，无法断言精确新增内部状态目录数。
- 部署后 GET smoke（容器内使用现有 Host allowlist，不输出 Host 或响应正文）：`/health` 200；`/chat/blank` 与 `/inbox/source` 200 HTML；入口 JS、CSS、Notes JS chunk 均 200；匿名 Chat API 401 JSON。没有登录生产 Chat 页面或请求业务数据。
- Hermes/Guard 未重建、重启或修改：Hermes 容器 `057324a9e438969320e84d7c3cbad58e3f010637d7dd00d5967123b034eada79`，镜像 `secondbrain-hermes:v0.22.2-failclosed-84d1cbaf` / `sha256:b99b1762631846d5ed3f8648ccc2c7ef2625b004234bbf276add2f8855357e9a`，running、RestartCount 0、StartedAt `2026-10-17T08:33:24.151798238Z`；切换前后身份一致。Guard 未作为独立容器运行。
- 即时 App-only 回滚快照：`/volume1/docker/secondbrain/rollback/m1-473948dd-predeploy-20261018T094236Z/compose.yaml`，目录 `0700 root:root`，Compose 与 metadata 文件 `0600 root:root`；快照 Compose SHA-256 与部署前 live 文件完全一致：`5c12fda28f3e5e9cd001d238515bd6599adaf5e502686f5d30fcbcb4a8c72f80`。旧 M1 App 镜像仍存在。未执行回滚，没有恢复或更改 Core-state。
- **部署时尚未开展该镜像的业务验收（时点事实）。** 切换和 smoke 期间没有创建生产 Session、Journal、Task、Inbox、Notes 记录或重试，没有调用模型、读取私人正文。**部署之后** B 线已在同一镜像的精确 B1 合成 Draft 上验证 5 条 Proposal、Journal/Review 各一次受控执行、Project 拒绝及刷新恢复有限 PASS；2026-10-18 用户接受 M1 有限结项，详见 [Issue #66](https://github.com/zxwan829/SecondBrain/issues/66)。该业务验收不表示生产同键重放或完整浏览器 Network 通过；D084 前一镜像合成结果与历史根因 UNKNOWN 继续分开记录。部署 smoke 原始报告不应被改写为部署时已验证业务。

## 上一生产快照（2026-10-18T07:26:49Z 起；源码 74d698dc，已由 473948dd 替换）

- 按用户明确授权，部署固定源码 `74d698dc97dd9df423664141b80fd8003fbca534` 对应的已验证候选镜像 `secondbrain-app:m1-74d698dc-notes`，不可变 Image ID `sha256:4adcf9cfe3f6257c733efa911455ca02653783ba763f9e2f512f4d3582694ce1`；未重新构建。部署前 PR #61 App 容器 `665bb3818fa63caefb9fb5fdca38db3ff1babe10caea2c9a8ea389cba1bc2710` / Image ID `sha256:e63ab1611b2a30ffd9dd2a9cb901066fa6b2da2e7e85c9c1c9d72dbabac0e4ab`。部署后容器 `bd450fb6b42d32e5a23f4581c5fd76c0454d66904dff3022f81dca2dd95da7d7`，镜像与候选 ID 完全一致，运行身份 `1026:100`，RestartCount 0，StartedAt `2026-10-18T07:26:49.04549923Z`；Compose `--wait --wait-timeout 120` 在约 31 秒返回 Healthy。
- 正式 Compose `/volume1/docker/secondbrain/compose.yaml` 的部署前 SHA-256 为 `9c0932c04d6984cd2e491738d51eb6235d7182ccfca8146678fc18cdabe6097d`，部署后为 `5c12fda28f3e5e9cd001d238515bd6599adaf5e502686f5d30fcbcb4a8c72f80`。结构核验确认仅改动 App image、`SB_NOTES_DRAFTS_ROOT`、`SB_NOTES_AUTHORIZED_ROOTS`；Compose `config --quiet` 通过。App UID/GID、原有依赖、build context、网络及所有既有挂载未改变。
- Notes 配置为 `SB_NOTES_DRAFTS_ROOT=/var/lib/secondbrain-core/notes-drafts`、`SB_NOTES_AUTHORIZED_ROOTS={}`。仅在现有 Core-state RW 挂载内创建先前不存在的空目录 `/volume1/docker/secondbrain/core-state/notes-drafts`；容器路径 `/var/lib/secondbrain-core/notes-drafts`，owner/mode `1026:100 / 0700`。没有新增真实 Vault、Knowledge、Private 或 Projects 授权根/挂载。`SB_PROMOTE_ENABLED=false`。既有挂载复核：Review 与 Capture Inbox 专用 RW、Knowledge RO、Core state RW、Private 未挂载、Projects 未挂载；Secret 文件仍仅以既有只读挂载存在，内容未读取。
- 部署后限定 GET 检查（使用应用现有 Host allowlist，不输出 Host 或响应正文）：`/health` HTTP 200；`/chat/blank` HTTP 200 HTML；入口 JS 200、CSS 200、Notes JS chunk 200；匿名 Chat API HTTP 401 JSON。未打开生产登录态 Chat 页面。
- Hermes/Guard 未重建、未重启、未修改：容器 `057324a9e438969320e84d7c3cbad58e3f010637d7dd00d5967123b034eada79`，镜像 `secondbrain-hermes:v0.22.2-failclosed-84d1cbaf` / Image ID `sha256:b99b1762631846d5ed3f8648ccc2c7ef2625b004234bbf276add2f8855357e9a`，running，RestartCount 0，StartedAt `2026-10-17T08:33:24.151798238Z`；与切换前身份及运行时间一致。本次只确认容器运行状态，不声称 Hermes health。
- 精确 App-only 回滚快照在 `/volume1/docker/secondbrain/rollback/m1-app-only-20261018T072428Z/compose-before.yaml`；快照 SHA-256 与部署前 Compose 一致（`9c0932c04d6984cd2e491738d51eb6235d7182ccfca8146678fc18cdabe6097d`），目录 `0700 root:root`、文件 `0600 root:root`。PR #61 旧 App 镜像仍可识别并保留。未触发回滚；未删除候选、回滚资料或持久状态。
- **业务验收未运行。** 未创建生产 Session、Journal、Task、Inbox 或 Notes 业务记录；未重试任何操作；未调用模型或读取私人正文。D084 会话切换历史异常根因保持 UNKNOWN，既有业务验收项仍未完成。部署结果已在 [Issue #66 评论](https://github.com/zxwan829/SecondBrain/issues/66#issuecomment-6247141554) 报告；Issue #44 的评论审批限制未绕过。

## 历史生产快照（2026-10-18T02:28:59Z 起；D084 PR #61 App-only 部署；已由 M1 镜像替换）

- 按用户既有授权切换指定候选镜像 `secondbrain-app:d084-pr61-4a58393-full`，未重新构建。切换前候选 ID 与已通过的隔离预检完全一致：`sha256:e63ab1611b2a30ffd9dd2a9cb901066fa6b2da2e7e85c9c1c9d72dbabac0e4ab`。该镜像基于 `4a58393`；当前 GitHub main 已推进到 `3080506b053d3876d292d9199049fd12e3247b88`，后续 PR #59 的 D085-C2b 变更不在此指定镜像内。
- 部署前 App 为 PR #49 镜像 `secondbrain-app:pr49-fa2ad412-full` / ID `sha256:1c7ed4cb953951eb2ab8691516651d170171305af6172326174e64f4115dd6ca`，healthy，容器 ID `272b9fee7e62cf4b6b9c39f82d8c1e2eeceffaee82215a9cf34dc35098570601`。Compose 原 SHA-256 `28636decfc08e47f57d2a671c68ecc6861cdf7653b860f12f73c020dcc1d6e06`，属主/模式 `1026:100 / 0640`。仅将 App image 引用替换为指定候选；更新后 Compose SHA-256 `9c0932c04d6984cd2e491738d51eb6235d7182ccfca8146678fc18cdabe6097d`，属主/模式不变；Compose `config --quiet` 通过。
- 唯一部署命令为 App 服务 `compose up -d --no-deps --no-build --force-recreate --wait --wait-timeout 120 secondbrain-app`。新容器 `665bb3818fa63caefb9fb5fdca38db3ff1babe10caea2c9a8ea389cba1bc2710`，App UID/GID `1026:100`，RestartCount 0；镜像 ID 与候选一致。Compose 的既有 PR #49 build context 保持不变；`--no-build` 确保此次复用已审候选。StartedAt `2026-10-18T02:28:59.061387547Z`；约 30 秒内 healthy（低于 120 秒门槛）。
- 仅做 GET smoke：使用应用现有 Host allowlist 在容器内请求，未输出 Host 值或响应正文。两项 Host 配置对应的 `/health`、`/chat` 均为 200；`/chat` 返回 HTML，HTML 引用的 2 个 JS 和 1 个 CSS 均为 200；匿名 `GET /api/chat/sessions` 均为 401 `application/json`。一次错误地以 `127.0.0.1` Host 直连发布端口的尝试返回 400（TrustedHost 拒绝），随后改用配置允许的 Host 完成上述检查；不作为 App 故障证据。
- Hermes/Guard 未重建、未重启、未修改：容器仍为 `057324a9e438969320e84d7c3cbad58e3f010637d7dd00d5967123b034eada79`，镜像 `secondbrain-hermes:v0.22.2-failclosed-84d1cbaf` / `sha256:b99b1762631846d5ed3f8648ccc2c7ef2625b004234bbf276add2f8855357e9a`，running，RestartCount 0，StartedAt `2026-10-17T08:33:24.151798238Z`。本次只依据 `docker ps/inspect` 报告 running；不声称 Hermes health。
- 回滚准备：切换前核验旧 PR #49 镜像仍在；另核验旧镜像 `secondbrain-app:d084-c8a2b348` / `sha256:ef60d7de4ff3f3b3edc49cb0d565c45df3b996fe7014fc49ff3446ead7592feb`。已再次验证旧回滚目录 `d084-pr49-app-20261017T100900Z` 中 `SHA256SUMS` 全部通过。另保存本次切换前 Compose 精确副本于 `/volume1/docker/secondbrain/rollback/d084-pr61-cutover-20261018T102845/compose-before.yaml`，目录 `0700 root:root`，文件 `0600 root:root`，SHA-256 与原 Compose 一致。未执行回滚，因为 App health、路由、静态资源与 API 鉴权通过且无 App 异常。
- **业务验收：BLOCKED。** 新建的隔离浏览器标签登录后自动恢复了现有 Session，而非空白会话。自动化可访问性快照意外包含现有会话列表标签与选中会话的操作卡摘要；未打开其他会话或展开消息正文，未保存这些文本或 Session ID，随即停止并关闭标签页。没有创建 Session、写入/重试 Journal/Task 或调用模型。Journal/Task 操作卡、刷新恢复、Session 隔离和幂等均未验证；历史生产根因仍 UNKNOWN。此前已获授权的范围不扩张。
- D084 状态文档已更新，Issue #44 评论未提交（此前曾被审批拒绝，本轮未通过其他渠道绕行）。

## 限定容器元数据核验（2026-10-18T01:50:41Z；D084；只读）

- 通过现有 NAS SSH 管理员路径运行 `/usr/local/bin/docker ps/inspect` 只读查询。SSH 用户 `1026:100` 对 Docker socket 的直接访问被拒；既有 `sudo -n` 授权成功，未改 socket 权限或 sudoers。
- **App**：容器 `272b9fee7e62cf4b6b9c39f82d8c1e2eeceffaee82215a9cf34dc35098570601`；镜像 `secondbrain-app:pr49-fa2ad412-full`，Image ID `sha256:1c7ed4cb953951eb2ab8691516651d170171305af6172326174e64f4115dd6ca`；running / healthy，RestartCount 0；StartedAt `2026-10-17T11:43:55.113573688Z`；容器身份 `1026:100`。
- **Hermes**：容器 `057324a9e438969320e84d7c3cbad58e3f010637d7dd00d5967123b034eada79`；镜像 `secondbrain-hermes:v0.22.2-failclosed-84d1cbaf`，Image ID `sha256:b99b1762631846d5ed3f8648ccc2c7ef2625b004234bbf276add2f8855357e9a`；running，RestartCount 0；StartedAt `2026-10-17T08:33:24.151798238Z`；容器身份 `root`。`docker ps` 未报告 health 状态，inspect 输出中也没有 `.State.Health` 字段；本次只确认 running，不报告 Hermes healthy。
- 本次确认 App 仍运行 PR #49 镜像；PR #61 已合入 main，但未部署。因此 stale localStorage ID 回退和延迟 create/fork 选择保护尚未进入当前 App 镜像。此次为有限容器元数据快照，没有重查 Compose、挂载、配置或容器日志，不覆盖上节 2026-10-17 的完整快照。
- Edge 浏览器标签清单中没有 SecondBrain App 页面；未导航 `/chat`，以避免自动恢复已有私人 Session。因无安全可用的目标 Session ID，也未读取全量 Session 列表或宽泛容器日志。浏览器 selected/localStorage ID、目标活动请求/响应 ID 与状态时间戳均为 **UNKNOWN**；未读取任何会话正文、Journal/Task 数据，也未创建或修改 Session/业务记录。

## 历史运行核验（2026-10-17，PR #49 App-only 部署后）

- 按 Issue #44 评论 #6233322671 的单次授权，使用 PR #49 merge fa2ad4126b5e9acb6983fdae8445a4fb0ebdda79 输入和 web-app/Dockerfile.app 构建完整 App 镜像。Mac 源码归档 SHA-256 8dbb4d78f523ee69e59d214a6430528b299e922141a8af36ae778af06423c4d7；NAS 保留构建源于 /volume1/docker/secondbrain/app-build-source-pr49-fa2ad412/web-app。前端 npm run typecheck / npm run build 通过；npm 安装提示 4 项依赖漏洞（2 low、2 moderate），本次未升级依赖。
- 镜像 secondbrain-app:pr49-fa2ad412-full / Image ID sha256:1c7ed4cb953951eb2ab8691516651d170171305af6172326174e64f4115dd6ca，容器 ID 272b9fee7e62cf4b6b9c39f82d8c1e2eeceffaee82215a9cf34dc35098570601，运行身份 1026:100，RestartCount 0，2026-10-17T11:43:55Z 启动并在 120 秒门槛内 healthy。镜像配置 SB_STATIC_ROOT=/app/static；隔离无网络、无数据挂载 ASGI 检查验证 /chat 为 200 text/html、两个链接资源均 200、匿名 Chat API 401 application/json。生产只读 HTTP smoke 得到相同状态；未认证响应正文不入文档。
- 当前 Compose /volume1/docker/secondbrain/compose.yaml SHA-256 28636decfc08e47f57d2a671c68ecc6861cdf7653b860f12f73c020dcc1d6e06，属主/模式 1026:100 / 0640。改动仅限 App 的 build context 指向上述独立源目录及 image tag；Compose 校验通过。部署使用 up -d --no-deps --force-recreate --wait --wait-timeout 120 secondbrain-app，没有重建其他服务。
- Hermes/Guard 保持原样：容器 057324a9e438969320e84d7c3cbad58e3f010637d7dd00d5967123b034eada79、镜像 secondbrain-hermes:v0.22.2-failclosed-84d1cbaf / sha256:b99b1762631846d5ed3f8648ccc2c7ef2625b004234bbf276add2f8855357e9a、启动时间 2026-10-17T08:33:24Z、RestartCount 0、running；切换前后身份一致。本轮没有重启、重建或修改 Hermes/Guard。
- Core state、Journal、Task、chat-activity 根均为 1026:100 / 0700。现有挂载仍为 Review RW、Capture Inbox RW、Knowledge RO、Core state RW；未发现 Private 挂载。SB_PROMOTE_ENABLED=false；没有扩大权限或改变数据目录。此轮未创建 Journal/Task 合成记录，未读取业务文件正文。
- App-only 回滚材料沿用并重新校验 /volume1/docker/secondbrain/rollback/d084-pr49-app-20261017T100900Z/：目录 0700 root:root，SHA256SUMS 中 Compose 与预部署元数据均通过。快照中的 Compose SHA-256 与部署前 33f45f5cdca72cea05ddd21a265d129bc770684dfb6b1b9d3790cb12725fa0b9 相同；旧 App 镜像 secondbrain-app:d084-c8a2b348 / sha256:ef60d7de4ff3f3b3edc49cb0d565c45df3b996fe7014fc49ff3446ead7592feb 仍在本机。回滚时仅恢复该 Compose 并重建 secondbrain-app，保留 Core state 与 Hermes。
- **验收状态：** 生产健康、静态路由、静态资源和匿名 API 鉴权通过；生产登录态下 Journal/Task 系统操作卡、刷新恢复、跨 Session 隔离与幂等重试尚未验证。Edge 自动化遇到扩展 UI 阻断，未提交表单或创建会话；无模型调用，生产 Journal/Task 真实数据未修改。以上业务验收项保持 NOT VERIFIED，待浏览器自动化恢复后使用新建空白 Session 和唯一合成数据完成。

## 历史 Hermes 核验（2026-10-17，PR #18 / fail-closed overlay）

- PR #18 squash 合并至 main，merge commit `84d1cbaf7daebb188fc93c369fba4a59b80895e5`。Hermes 基于上游 v0.22.2 源码 Commit `d923a5eb487a17c0a68801bba9ef0f56c81040a8` 与补丁 SHA-256 `b53818487205733039378a8e3c7218cc298eca1c39e1a34dec997dd306f855b0`，从官方 amd64 镜像 digest `sha256:a11574b7fe8e1631d7d88d556677dac693bc058abf558cdeb899155688c1bf05` 构建一文件 overlay。NAS 当前 Hermes 镜像 tag `secondbrain-hermes:v0.22.2-failclosed-84d1cbaf`，Image ID `sha256:b99b1762631846d5ed3f8648ccc2c7ef2625b004234bbf276add2f8855357e9a`，平台 linux/amd64。
- Compose SHA-256 `6d7b1be1abb4479b93e5cebc473e2f20ba6bddb6bd62ea5019322ef260908818`，属主/模式 `1026:100 / 0640`。仅 Hermes image 引用变更；Hermes 单服务以 `--no-deps --force-recreate` 重建，未触碰 App/Core 或其他服务。当前 `secondbrain-hermes` running，RestartCount 0；API `/health` 200，Dashboard 9119 可达并重定向登录（302）。重建后曾观察到 API 尚未监听，持续等待后服务恢复，无二次重启/回滚。
- Hermes `Plugin Doctor` 对 `secondbrain-d078-guard` 报告 manifest/import/registration 成功、注册 1 hook。Profile 有 `file,skills,vision`，无 terminal；Skills write approval=true、approval mode=manual。NAS 合成 `docker exec` 验证：敏感 Session 文件 read 被拒、允许的合成业务文件路径通过、Skills 只读工具通过、注入 dispatcher RuntimeError 被 fail-closed 阻断；零模型调用、零 Session 写入。生产 API 未创建 Session/Run。
- 安全边界重核：Private 无挂载；`/secondbrain` 主挂载 RO，Knowledge 主目录 RO；既有 `/knowledge-assets/00-Inbox` Capture 专用 RW 子挂载保持不变。Promote false。Core 记忆根 `/volume1/docker/secondbrain/core-state/personal-memory` mode 0700、owner `1026:100`，0 files/0 bytes，mtime 与升级前记录相同；未读取内容。API Terminal 保持关闭。
- 回滚点 `/volume1/docker/secondbrain/rollback/d078-hermes-hook-failclosed-20261016T173140Z/`：目录 0700，`compose.yaml`（SHA-256 `d2865340ab82fec7086048c55798b3e1c29dabfca3d8999d2ab36b5e94e0c4c9`）、旧 `plugin.yaml`、恢复元数据均 0600。旧官方 Hermes image ID `sha256:02e7aa0e84123fa0e9b22686e7a2bfb7d85fd59821d4d28812a3e07f3061cf41` 保留在 rollback tag `secondbrain-hermes:rollback-v0222-official-20261016T173140Z`。回滚前应重核快照并只恢复 Hermes/manifest；不可回滚 Core state、D077 JSONL 或 App。
- 上述是运行态与合成权限验证，不代表真实模型、真实个人数据或浏览器学习体验已验收。此前 D078 Stage 1 信息保留在下方历史快照段，凡与本节冲突以本节为当前状态。

本文件记录最近一次经验证的运行快照，并非实时监控。顶部是 2026-10-19 M2 P1 App-only 部署后的最新 App/Compose/Hermes 运行事实；其下 PR #61 与 PR #49 段落均为历史快照。Hermes overlay 段是此前核验的 Guard 配置与 Hook 证据，本轮仅确认 Hermes 容器/镜像/启动时间未变化，没有重新读取插件文件。下一次生产操作前仍须重新只读核验。Private 与凭据正文不入库。旧阶段恢复说明和历史资产审计均移交 Progress-Log.md 与 Issue #14，不作为现行运行或恢复指令。

## 常态运行路径与尚待验证的边界

## NAS 与 Compose

- NAS：Synology DS920+，DSM 7.4.1 Build 90080；LAN 地址 `192.168.3.27`。本机与路由器网络设置不由 SecondBrain 文档治理修改。
- 正式 Compose：`/volume1/docker/secondbrain/compose.yaml`；Compose Project `secondbrain`；Docker 网络 `secondbrain_default`。截至 2026-10-19 M2 部署后有证据的 Compose SHA-256 为 `a0d6775e8a785845ee32369a68141410e99988df316714f507b0d98743734686`，属主/权限 `1026:100 / 0640`。2026-10-19 切换仅改 App image。上一哈希 `5d15c9ac...` 是部署前值，不是现行值；更早 Notes 配置变更见 M1 历史快照。
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
| App | B1b operation state | `/var/lib/secondbrain-core/b1b-operations` | Core-state 内新建空子目录；`1026:100 / 0700` |
| App | 合成 Notes Drafts（已有 Core state 子目录） | `/var/lib/secondbrain-core/notes-drafts` | 既有 Core-state RW 内，`1026:100 / 0700`；`SB_NOTES_AUTHORIZED_ROOTS={}`，不授权真实 Vault 或新挂载 |
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

- **App-only 最近切换前快照：** `/volume1/docker/secondbrain/rollback/m1-473948dd-predeploy-20261018T094236Z/compose.yaml`；目录 0700、文件 0600、原 Compose SHA `5c12fda28f3e5e9cd001d238515bd6599adaf5e502686f5d30fcbcb4a8c72f80`，旧 App 镜像 ID `sha256:4adcf9cfe3f6257c733efa911455ca02653783ba763f9e2f512f4d3582694ce1` 已在部署时核验。**这是受限回滚资产的位置和历史证据，不是可以直接执行的实时恢复命令**；回滚须用户另行授权并先只读核验当前 live Compose、镜像和持久化状态，绝不可覆盖 Core-state、B1 记录或 Hermes。
- 当前 Hermes 回滚点：`/volume1/docker/secondbrain/rollback/d078-hermes-hook-failclosed-20261016T173140Z/`。包含原 Hermes Compose、插件 manifest、恢复元数据及固定官方旧镜像 tag；镜像标识与校验和见文件顶部“最新核验”。**仅对 Hermes 定向恢复**，须先重新核验实际配置并取得操作授权；不得回滚 App/Core state、D077 JSONL 或其他 NAS 服务。
- D078 Stage 1、D077 和更早的恢复步骤属于**历史施工证据**，不在本文件提供可直接复制的旧版回滚命令；其原始路径、哈希及复盘见 `Progress-Log.md` 和对应 Issue，不能用作当前自动回滚方案。

## 核验触发与历史导航

容器重建、镜像/版本、Compose、挂载、ACL、Secret、端口、DSM 代理或网络变化后，先重新取得只读运行证据，再更新此处快照。Private 内容与凭据不写入基线。D071 至 D076 的部署、回滚、用户验收和失败复盘按日期记录在 `Progress-Log.md`；其中旧记录保持历史属性，不得用作当前运行证明。
