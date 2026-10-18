---
created: 2026-09-28
updated: 2026-10-18
status: current
type: environment-baseline
---
# Environment Baseline

## 最新生产快照（2026-10-18T09:44:06Z 起；PR #72 合并后 M1 App-only 部署）

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

本文件记录最近一次经验证的运行快照，并非实时监控。顶部是 2026-10-18 M1 App-only 部署后的最新 App/Compose/Hermes 运行事实；其下 PR #61 与 PR #49 段落均为历史快照。Hermes overlay 段是此前核验的 Guard 配置与 Hook 证据，本轮仅确认 Hermes 容器/镜像/启动时间未变化，没有重新读取插件文件。下一次生产操作前仍须重新只读核验。Private 与凭据正文不入库。旧阶段恢复说明和历史资产审计均移交 Progress-Log.md 与 Issue #14，不作为现行运行或恢复指令。

## 常态运行路径与尚待验证的边界

## NAS 与 Compose

- NAS：Synology DS920+，DSM 7.4.1 Build 90080；LAN 地址 `192.168.3.27`。本机与路由器网络设置不由 SecondBrain 文档治理修改。
- 正式 Compose：/volume1/docker/secondbrain/compose.yaml；Compose Project secondbrain；Docker 网络 secondbrain_default。最近一次 2026-10-18 App-only 生产切换后**有证据的 Compose SHA-256** `5d15c9ac51d4bd9f3cd682ef60e4e97d77b5d7e212ae73d0bf5e3126aad0da8d`，属主/权限 `1026:100 / 0640`（依 Codex 当次报告，未于本轮重新连接 NAS）。上次切换**仅改 App image**；前一 Compose SHA `5c12fda28f3e5e9cd001d238515bd6599adaf5e502686f5d30fcbcb4a8c72f80` 是回滚快照的部署前值，**不是现行值**。更早首次 M1 部署才修改 App image 与两项 Notes 配置；既有 build context、Hermes、网络、挂载和其他服务未改。
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
