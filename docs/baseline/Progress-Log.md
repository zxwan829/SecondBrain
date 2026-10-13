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
- 生产权限候选仍要求移除 Hermes `20-Knowledge` RW 子挂载及 `/secondbrain-write` 写安全根，保留 RO 根挂载与 Inbox/Review 必需写入；Core UID 1026:100 独占 Knowledge 与私有审批/审计状态 RW。候选 Compose 明确 `SB_PROMOTE_ENABLED=false`。无生产配置或 NAS 改动。
- 离线验证：Core 审批/认证与 HTTP 测试 15 项通过（使用 `/private/tmp` 隔离依赖）；覆盖审计写失败重试、审计尾部中断恢复、版本化暂缓、身份伪造拒绝、Origin/HTTPS 与重复提交。生产部署及用户验收未执行。
