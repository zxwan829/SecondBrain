---
created: 2026-09-28
updated: 2026-10-12
status: current
type: environment-baseline
---
# Environment Baseline

仅记录已核验且仍有运维价值的环境事实。生产配置变更、容器重建或版本变化后更新；历史阶段过程与测试叙述放在 Progress-Log。不可从此处读取到的秘密不得记录。

## NAS / 数据路径

- Synology DS920+, DSM 7.4.1 Build 90080；NAS LAN `192.168.3.27`，iStoreOS `192.168.3.2`。家庭网关、PBR、WireGuard、DNS 是稳定生产环境，不属 SecondBrain 随手修改范围。
- 正式项目：`/volume1/SecBR/SecondBrain/30-Projects/SecondBrain V1/`。数据区：`/volume1/SecBR/SecondBrain/`、`/volume1/SecBR/KnowledgeAssets/`、Private `/volume1/SecBR/Private/`。
- 当前 Mac 工作副本：`/Users/joe/SecondBrain/30-Projects/SecondBrain V1/`，由 Synology Drive 与 NAS 双向同步；其他 Mac（iMac、MBA 或新增设备）须各自配置 Synology Drive 与 NAS SSH 访问。Google Drive 桌面客户端当前挂载为 `~/Library/CloudStorage/GoogleDrive-<账户>/我的云端硬盘/`；正式目标为 `Project Doc/SecondBrain V1 Live/`，Drive 文件夹 ID `1LeHoAmFrPSyfBBZfufDCvH49TKRnoNp6`。

## Hermes Runtime

- Compose：`/volume1/docker/secondbrain/compose.yaml`；项目根 `/volume1/docker/secondbrain/`；容器 `secondbrain-hermes`。
- Production Hermes v0.21.5 / build `749220ef`；镜像 `nousresearch/hermes-agent@sha256:d4da4a40cd7a28aba983775d9fd31d94cbf153eeb0cb9e844d6d0f612b7c24db`；已核验运行 image ID `sha256:e1e87aec2e3f5b9863c127a0f21f3b3c237c8717c57c323c7184a49ca12a0df6`。当前 Runtime 默认模型 `zai-org/GLM-4.5-Air`；最终长期默认未冻结。
- Hermes 数据/配置：`/volume1/docker/secondbrain/hermes/data/`、`config.yaml`；Hermes CLI `/opt/hermes/.venv/bin/hermes`。
- Dashboard 监听容器端口 `9119`，宿主仅绑定 `192.168.3.27:9119`，LAN HTTP URL `http://192.168.3.27:9119`；DSM HTTPS `https://zxwan520.com:63012` 保留 LAN-only 入口。Basic Auth secret 在 `/volume1/docker/secondbrain/.env`，权限 600。不得把凭据写入文档。
- 网络 `secondbrain_default`；网段 `172.18.0.0/16`，Gateway `172.18.0.1`，Hermes `172.18.0.2`；容器流量策略路由经 table 200 → `192.168.3.2` → `wg0`。开机脚本 `/volume1/docker/secondbrain/scripts/hermes-policy-route.sh`，DSM Task Scheduler `SecondBrain Boot`（root）；开机恢复未以 NAS 主动重启验证。

## 已核验挂载与安全差距

运行容器 Docker inspect（UC-V1-Attachment-0B）确认：

| Host source | Container destination | Mode |
|---|---|---|
| `/volume1/SecBR/SecondBrain` | `/secondbrain` | RO |
| `/volume1/SecBR/SecondBrain/00-Inbox` | `/secondbrain-write/00-Inbox` | RW |
| `/volume1/SecBR/SecondBrain/10-Review` | `/secondbrain-write/10-Review` | RW |
| `/volume1/SecBR/SecondBrain/20-Knowledge` | `/secondbrain-write/20-Knowledge` | RW |
| `/volume1/SecBR/KnowledgeAssets/00-Inbox` | `/knowledge-assets/00-Inbox` | RW |

运行值 `HERMES_WRITE_SAFE_ROOT=/secondbrain-write:/knowledge-assets/00-Inbox`。Knowledge 实际 RW 与普通 write_file 可直接写入已由 0B/0C 核实；Hermes 仍保持该 RW 子挂载，尚未收窄。

## Dashboard / FE-4

- 正式插件 `secondbrain`：`/volume1/docker/secondbrain/hermes/data/plugins/secondbrain/dashboard/`，路由 `/secondbrain`；测试插件 `secondbrain-fe-test` 使用独立目录、身份和回滚资产。Hermes 原生 Chat `/chat`。生产 Dashboard 可通过 `http://192.168.3.27:9119` 访问，另有 DSM LAN-only HTTPS `https://zxwan520.com:63012` 入口。
- Home API `GET /api/plugins/secondbrain/home`；认证插件 API 在 Hermes Dashboard 会话下运行。Private 与 00-Inbox 由正式 API 拒绝。业务写入仍受受控流程约束。
- 正式 manifest 已指向只读 Review 入口 index-20261012-review.js（SHA-256 22bb5bfad7b0394bbdf852203081901d63fb88e3b945a2e9cbccd84202bb85ed）；manifest SHA-256 7b6bbd306f416d66e18d2ea87cbec2b224149ea0c6f46c886a957eeae97c5349。FE-4 主包与 CSS 保持原样；回退 manifest 为 manifest.json.pre-review-20261012，旧版本化 JS 保留。
- 正式回滚目录 `/volume1/docker/secondbrain/hermes/data/secondbrain-fe4-rollback/fe4-20261011-155631/`，包含 `rollback.sh` 和被替换资源快照。部署前应重新确认回滚文件存在和目标版本。

## DSM HTTPS / CORE-4 入口与隔离基线

- DSM 7.4.1 使用现有 Let's Encrypt `zxwan520.com` / `*.zxwan520.com` 证书（核验有效期 2026-09-25 至 2026-12-24）。现有 host+port 反代规则上新增两条 SecondBrain 规则：Dashboard `https://zxwan520.com:63012` → `http://192.168.3.27:9119`；Core `https://zxwan520.com:63013` → `http://127.0.0.1:9120`。两条均绑定 `SecondBrain LAN-only` Access Control profile；Dashboard 原 HTTP 入口仍保留。
- AccessControl.json 中 `SecondBrain LAN-only` 的实际规则为允许 `192.168.3.0/24`，拒绝 `0.0.0.0/0` 和 `::/0`；ReverseProxy.json 确认两条规则均绑定其 profile。两条规则采用同一 HTTPS 主机、不同端口，不是同源（Origin 含端口），因此 Core 仍需精确 CORS Origin 与 credentials。
- `10-Review`、`20-Knowledge` 的 POSIX owner 均为 Joe UID 1026/GID 100、mode 700；DSM ACL owner Joe 有写权限，administrators 组有写权限。临时项目测试目录复制了 ACL，并核实 Core 对应的 Joe UID 读写规则；未验证 administrators ACE。隔离 Docker 测试：root + Knowledge RO 写入被拒；Core `1026:100` 可读 Review/secret、写 Knowledge/state、不能写 Review；模拟 Hermes 未挂载 Core secret/state。临时目录已清理，未改真实 ACL/数据。
- 正式项目 /volume1/docker/secondbrain/compose.yaml 中 Core service 仍属于现有 SecondBrain Project。配置 UID 1026:100；Review、Knowledge 为 RO；state RW、Core-only secret RO；Promote=false。DSM 反向代理实际对端从 Core 访问日志确认为 172.18.0.1，SB_TRUSTED_PROXY_IPS 现仅设该精确地址；Host allowlist 仍 zxwan520.com。Compose 回退副本 compose.yaml.pre-review-proxy-20261012；Core 运行 healthy，Hermes 未重建。
- Mac 局部 curl --resolve 验证 Core TLS/健康 200；锁定态列表与详情均 401，非法 Origin 403。通过 63013 HTTPS 提交伪造 X-Forwarded-Host 或 X-Forwarded-Proto 未绕过会话校验。新静态 Review 入口可由 NAS 插件目录提供；未解锁读取 Review 内容。用户此前报告真实 Edge Dashboard 登录成功；Codex 可控标准 Edge 仍遇公网 DNS 路径拒绝，最新完整列表/详情需用户在真实 Edge 中刷新并解锁确认。

## Universal Capture / Promote

- Production Skill `universal-capture` v0.1.3，已接受范围为文本 Raw/Review；生产 URL/Web、PDF、Image/Screenshot、Audio/Voice 处理尚未实现。生产 Human Approval 仍是进入 Knowledge 的业务规则。
- Promote 与审批 API 已实现并通过此前隔离测试；正式项目 Compose 中 Core service 当前 healthy，但 `SB_PROMOTE_ENABLED=false`、Knowledge 为 RO。Dashboard 加法 bundle 已发布；Core health API 可访问，真实认证 Review 浏览器读取未验证；无正式 Knowledge 写入。

## 治理安全写入与同步

- NAS 安全写入：`/volume1/SecBR/SecondBrain/30-Projects/SecondBrain V1/tools/safe-governance-write.sh`；按 NAS 当前 SHA-256 校验版本后原子更新。每次提交先创建并验证 9 份活动 Markdown 的完整快照，固定目录为 `/volume1/SecBR/.governance-recovery/SecondBrain V1/`，仅滚动清理超过数量限制的受管且验证有效快照，最多保留 10 份。
- 旧恢复点整理结果与清理范围见 `Progress-Log.md`；新快照恢复目录位于 NAS 独立路径，不参与项目同步。
- Synology Drive 当前任务继续双向同步本地 `/Users/joe/SecondBrain/` 与 NAS `/SecondBrain/`；新快照目录位于该同步根之外。此任务未修改。
- 当前唯一核实的发布脚本：`/volume1/SecBR/SecondBrain/30-Projects/SecondBrain V1/tools/sync-chatgpt-live.sh`（Mac 镜像同路径）；未发现 `/volume1/SecBR/SecondBrain/30-Projects/_Shared/tools/publish-docs.sh` 或独立配置文件。SecondBrain 配置内嵌 `load_project`：NAS 源 `/volume1/SecBR/SecondBrain/30-Projects/SecondBrain V1/`，目标子目录 `SecondBrain V1 Live/`，白名单为六份治理 Markdown 与两份 Business Specification。命令：`tools/sync-chatgpt-live.sh --project secondbrain-v1 --dry-run` 检查，去掉 `--dry-run` 执行本地发布；SSH 使用当前 Mac `~/.ssh/config` 的 `secondbrain-nas` 别名（可用 `SECONDBRAIN_NAS_SSH_TARGET` 覆盖）。脚本自动识别唯一 Google Drive Desktop `CloudStorage` 挂载；必须预先存在目标文件夹。只增量复制白名单文件、不删除云端内容、不用 rclone。桌面客户端将本机复制异步上传；脚本成功只证明本地发布完成，不证明云端已同步。旧项目脚本路径保留但发布逻辑已更新；共享目录脚本尚未实现。
- NAS 专用 SSH key 已配置；NAS SCP/SFTP subsystem 曾不可用，普通 SSH 可用于有界核验/传输。连接失败不改 NAS SSH/权限来绕过。

## 重验触发条件

只有命令失败、Hermes 镜像/版本/容器重建、Compose/挂载/网络变化或正式部署后，才重新核验对应环境事实。Private 内容和认证秘密不属于本基线。
