# Progress Log

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

- Created and froze `SecondBrain-Web-App-V1-Business-Spec.md` v1.0 canonical.
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
