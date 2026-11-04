---
created: 2026-11-04
status: handoff-snapshot
project: SecondBrain
scope: V1 UAT, VNext UI, engineering handoff
---

# SecondBrain｜新窗口交接：V1 UAT、VNext UI 大升级与工程状态

> **用途：** 新 ChatGPT / Codex 窗口快速续接。**本文件是 2026-11-04 的交接快照，不是新增状态权威或开工授权。** 开始工作时，先读仓库根目录 `AGENTS.md`、`docs/baseline/Agent-Rules.md`、`docs/baseline/00-CURRENT.md`；当前 HEAD、PR、Actions、部署 SHA 以重新核验为准。不要把历史快照当实时状态。正式进度和唯一 NEXT 仍由 `00-CURRENT.md` 管理；决策查 `Decision-Log.md`、产品原文查 Issue #260。

## 1. 一分钟状态与当前行动

- **阶段目标：** 优先收口 V1 的核心实际使用链路和 P0/P1 阻断，达到可日常使用；随后单独评审并启动 **VNext UI 大升级**。不要为了旧 V1 的美观欠账反复进行全站 UI 返工。VNext 设计决策保留、**正式开发仍冻结**，除非用户明确解冻。
- **2026-11-04 V1 有限用户 UAT：** Task 创建/完成/撤销、文本 Capture→Inbox→Review 原文持久化、Knowledge 搜索/阅读、历史 Journal/Chat 读取获得用户页面证据；实际 Chat 经 Hermes 返回水循环问答、Run 完成并在刷新后恢复，故 **LIMITED_CHAT_UAT_PASS**。**不等于 V1 全量 UAT PASS**；Notes 新建保存、Journal 追加、跨会话记忆 #30、Companion、真实来源及部分业务仍未验收。
- **PR #269 Chat 紧凑化：** [PR](https://github.com/zxwan829/SecondBrain/pull/269)，分支 `codex/v1-chat-ui-compact`，截至本文件写入前最后核验 HEAD `a31d6022292f07eadd940351063af4e258ce0718`，**OPEN / NOT MERGED**。已做折叠「上下文与工具」、标题单行、紧凑输入、Run 状态去重，以及 Grid 修复/输入框高度复位；[Actions #41783682072](https://github.com/zxwan829/SecondBrain/actions/runs/41783682072) 固定 `eb6c314920612204e1ff9a00a21b75221c4efdcc` 的 Ubuntu 24.04 + Chromium 合成浏览器、类型检查、构建、脱敏 artifact **SUCCESS**。**注意 PR HEAD 后来已前进到 `a31d602`，不能把旧 SHA 的 PASS 直接宣称为新 HEAD 的浏览器 PASS；须先核对最新改动及增量证据。** 不发布成功截图不等于浏览器 Gate FAIL；截图仍受现有脱敏/allowlist 限制。
- **GitHub main（写入前核验）：** `e248d402fd350bcd7f58fe9496d73c620b6e1cca`；PR 合并、生产部署、用户实际视觉验收是三个独立状态。**不要因为 CI 成功而声称 Chat 新 UI 已上线。**
- **工程 NEXT：** Codex 主 Agent 核对 PR #269 最新 diff/CI/独立 Review → 若满足现有普通 PR 授权与保护则合并 → 核验 main SHA → 不自动部署 NAS；V1 后续按 `00-CURRENT.md` 唯一 NEXT 接续。任何新的安全/真实数据/生产操作按独立授权办理。

## 2. UI 大升级：已确认的产品目标（Issue #260）

**定位：** SecondBrain 是个人 AI 助理 + 知识管理系统，不是复杂后台。Hermes 为唯一通用 Agent Runtime；App/Core 管业务数据与授权，NAS/Vault 是业务数据来源。Web 以工作台为默认首页，不把全量聊天挤进首页。

**PC 整体布局与操作：**
1. **左侧导航栏**负责页面切换，可折叠；工作台、对话、知识库、任务等菜单细节仍待正式定稿。
2. **工作台主区域**：日程/待办最高优先，其次待审核、项目进度。它们只是**首批默认业务卡**，不是永久固定三卡。卡片支持稳定 type/id、可见性、顺序、推荐尺寸、响应式与数据/权限契约，预留将来新闻、AI 知识关联提醒等受控扩展，但**不意味着立刻开发插件市场或任意卡片引擎**。
3. **日期、时间、天气**保留在工作台**顶部紧凑信息区**，不得画成与核心业务卡同级的大天气卡。工作台 AI 快捷输入位于卡片下方：**真正发送才创建新会话并跳到独立对话页；聚焦不建空会话。**
4. **独立 Chat 页面**承载长对话、历史会话与 Hermes Run；返回工作台不丢当前聊天。对话辅助信息应按需展开，消息流优先；#269 是独立的 V1 局部修复，不代替未来全局设计。
5. **右侧文档/知识工作区默认隐藏、按需打开**：手动打开默认 Obsidian 文件列表；点击 AI 生成的文档成果则打开对应编辑器；AI 查询资料则展示可点击的搜索结果。关闭工作区不清空对话。**不做 AI 与用户同一个编辑器里的实时协同编辑**：AI 后端生成/修改并保存新版本，聊天返回成果入口，用户自主查看/编辑并可要求 AI 再修改；保留版本冲突保护。成果文档有独立长期生命周期，不是会话附属物。
6. **知识库/文件管理方向**：优先管理真实 Obsidian 文件及文件夹，支持标签筛选、中文路径、只读浏览/详情；前端呈现必须将 YAML frontmatter/属性与正文清晰区分，文件夹+标签交互要顺畅。此方向尚未构成已冻结的整站像素稿。
7. **任务卡 UX**：首页可直接完成/撤销（实际持久化）、重要/有损动作需确认；优先展示少量重要任务与「查看全部」。**待讨论、未最终批准**：计划日期、可选硬 DDL、提醒时间三者分离；逾期提示、优先级与排序。不得直接臆造 Core 数据字段。
8. **视觉原则**：克制、清晰、适度信息密度，避免空泛科技蓝紫风；重视卡片对齐、字体层级、按钮图标、长文本、暗色对比与响应式。正式栅格/宽高/断点/配色/菜单树/右侧宽度/手机排版**均未冻结**，不能把参考 WorkBuddy、Notion Home、Sunsama、ChatGPT/Claude 当像素级批准稿。

**正式 VNext 状态：FROZEN / NOT IN MAIN / NOT DEPLOYED。** 隔离原型保存于远端分支 `codex/vnext-workbench-20261103`，固定提交 `45bf5f7d918e3396e2bb8d195445ff465ed5a703`；只是合成原型，非真实数据接入或正式用户视觉验收。用户曾明确先完成 V1 UAT 再重启大改版。不要直接将此原型合并为生产 UI。

## 3. 元素级可视化设计：需求与既有 PoC 结论

- **用户硬需求：** 不会 CSS/TSX，需像 PPT 一样直接选中**尽可能多的可见元素**，包括卡片内部标题、图标、按钮、标签、容器、间距、对齐、颜色、字体、顺序，而非只调整卡片外框；中文面板、即时预览、撤销/重做、保存、桌面/手机合理响应式；不能要求用户用截图让 Codex 猜 CSS。
- **工程原则：** 结构化组件树/布局 Schema、可追踪 JSON/设计 tokens、可复用的 React 实际渲染源、稳定选择标识与 Git 精确 diff；保存到实际文件、刷新/重启不丢，支持回滚，编辑权限不得触碰真实业务数据或生产安全组件。约束 Grid/Flex/slot 布局优先，不能承诺任意 DOM 像素拖动并自动正确改写任意现有 CSS。
- **两卡片 JSON 属性原型**：已验证定向保存/撤销等部分可行性，但不具备全页面任意元素编辑能力。
- **Vibedit**：独立合成验证 FAIL（inline width 压制移动端媒体规则；breakpoint/Undo 回滚不完整），不采用；Onlook、VibeLens、react-rewrite 旧路线未证明适配当前 Vite + 普通 CSS，停止反复排障；Glide 未过实测门槛。
- **Puck PoC**：局部元素选择、属性、结构化 JSON、版本/撤销有 PARTIAL/PASS 证据，但任意元素鼠标拖到像素位置未实现；不适合作为整个 SecondBrain 的默认 UI 编辑底座。**不解冻整站开发**；可保留为未来静态 Home/受控卡片编辑候选，不为其自建通用自由画布。
- **下一次正式启动 UI 大升级的合理顺序：** 共同冻结桌面工作台骨架和核心交互 → 做**可运行、同源**的视觉原型（先桌面，后手机）→ 用户逐页直接体验确认 → Codex 核对 Core 接口与权限的「已有/缺失/待调整」矩阵 → 逐步集成 → 真实浏览器回归/用户验收。具体设计依然由用户确定，不擅自替代。

## 4. V1 UAT 改进：把「能跑」与「好用」分开

**已确认节奏：** 先实际核心业务 UAT，按影响分类，仅修 V1 P0/P1；整站视觉/排版欠账统一放 #260。不要因不断翻修老 UI 拖延日常使用。

**四类问题与处理：**
- **立即修复（V1 P0）**：数据丢失、不能保存/回读、严重权限/安全问题、核心路径不可达。
- **最小范围修复（V1 P1）**：严重干扰当前实际使用的局部交互，如 Chat 五个辅助面板遮住消息区。
- **VNext UX backlog**：外观、卡片布局、按钮规范、工作台信息密度、笔记编辑区域/日期控件等整站一致性问题。归并 Issue #260，不逐项打旧 CSS 补丁。
- **未完成业务 / 另行授权**：缺可信来源、未接渠道、跨会话记忆、Companion、Writer/Promote 等，不因改 UI 隐藏或误标完成。

**工程验证要分层，任何一层不自动推导下一层：**
1. **代码与定向验证**：Codex 在隔离分支实施；最小相关组件/DOM/HTTP 测试、typecheck、build；失败直接排根因并修，避免重复启动无关全量 Gate。
2. **正式浏览器 Gate**：遵守 `Agent-Rules.md`，GitHub-hosted **Ubuntu 24.04 + Chromium Playwright**，既有手动 workflow `.github/workflows/a-web-playwright-synthetic.yml`，固定 PR 目标 SHA 并核对 runner checkout HEAD。1440×1000 桌面优先且覆盖已有 820×1180 / 390×844 相关回归；重点验证真实 DOM/Grid/滚动、折叠/展开、长标题、文本换行与复位、发送/停止/完成、空态/失败态、加载和权限。macOS 本机不反复排已知 Playwright 崩溃。
3. **安全证据**：截图/trace/JUnit 不能未经既有 sanitizer allowlist 与敏感内容检查就上传；合成数据的实际 DOM 断言 + 结构化脱敏 artifact 可以作为浏览器 Gate 证据。**截图未发布时必须直说，不能伪称已目视通过**；图片本身也不能替代交互断言。
4. **代码合并**：PR 最新 HEAD 的独立 Review + 必要 CI/保护通过；区分「代码提交」「CI PASS」「PR merged」，有新提交则核对增量影响，不能拿旧 SHA 绿灯直接证明新 SHA。
5. **生产发布**：另行授权，先明确现网 App/Hermes/Core/挂载/Private/Writer 状态和回滚，确认发布目标 SHA；**CI 成功不等于已部署**。
6. **用户真实 UAT**：基于生产真实页面验证业务闭环，按任务记录「步骤→实际表现→是否保存/刷新/恢复→截图或日志证据→PASS/PARTIAL/FAIL/NOT RUN」。要验证基础 Chat 的实际回复和刷新恢复、Task 操作持久化、Capture 原文/Review、Knowledge 搜索阅读，不能让合成 fixture 冒充真实账户/模型或真实数据。页面视觉问题用用户实际截图/互动反馈判定，而不是只靠静态 CI。

**提升协同效率的行动规则：** Codex 主 Agent 在同一轮持续完成「读日志→修复→定向测→固定 SHA GitHub Actions→独立 Review→满足授权后合并」，普通技术细节不反复以“已确认需要改”结束；ChatGPT 负责方案与有证据的验收判断、必要时编写清晰可执行指令；不要以 GitHub 评论代替 Codex 实际执行，也不要频繁让用户做人肉转发协调。只在需要产品选择、生产/真实数据授权、不可逆风险或确有工具能力阻断时停。

## 5. 首轮 UAT 发现的 VNext 具体体验欠账（集中归并，不是 V1 新开发单）

| 区域 | 体验问题与待升级方向 |
|---|---|
| Home / Task | 首页双栏与聚合提示不合理；任务新旧排序、主动建议文案不直观；未来工作台信息层级、日期和 DDL 需重新设计。 |
| Capture / Inbox / Review | Capture Inbox 与 Notes Draft Inbox 语义混淆；`processor_unavailable`、`确定性 Mock`、`不枚举` 等开发术语外露；白色默认按钮、重复标题、对话与收录关联不清、弹窗背景仍滚动。 |
| Knowledge | YAML frontmatter 与双标题直出；正文/属性未分离；来源提示难理解，真实来源缺失是独立业务问题。 |
| Notes | 草稿列表太窄、长标题断行、正文编辑面积不足；深色下默认蓝色链接难辨；历史版本需要独立时间/版本/差异视图。 |
| Journal | 日期控件跨整行、文字与日历图标两端分离且图标低对比；历史正文出现 `&nbsp;`、Markdown 排版差。 |
| Chat | 五组上下文/来源/计划面板挤占聊天；历史标题、输入高度、状态去重。#269 仅做局部 P1 处理；全局布局仍留 VNext。 |
| Activity / Memory / 管理页 | 活动状态含义不明确；记忆偏好重复、卡片过大、信息结构与空态差。 |
| 编辑器通用交互 | 六点手柄、加号、文字需中线对齐；手柄方向和图标显隐一致；导出图标与工具栏平级；悬停反馈/菜单清理与深色可读性。BlockSuite 集成继续冻结。 |

## 6. 已验证业务、待办与安全边界

- **已有限实测：** 正式 Chat 实际回复/刷新恢复，Task 创建/完成/恢复，文本 Capture 原文/Inbox/Review，Knowledge 搜索/阅读，Journal 历史浏览，Chat 历史浏览。只有被实际操作且有记录的路径可以写 PASS。
- **待验收 / 未启用：** Notes 新建保存、Journal 追加、Projects 可信进度源、Daily Brief 可信来源/生成、URL/PDF/音频等完整真实样本、#30 跨会话记忆/Companion、Review→Promote、真实微信/飞书渠道。与 #261 浏览候选状态也要按最新独立核对。
- **生产门禁：** Private 默认不挂载；Knowledge 只读；`SB_PROMOTE_ENABLED=false`；Writer/OS Gate 和真实渠道单独审批，不能为通过 V1 UAT 临时放开。Hermes 的 fail-closed 补丁曾被误报缺失，后经文件 SHA 证实存在；不得以旧误判重建生产 Hermes。
- **Git 权威来源：** 私有仓库 `zxwan829/SecondBrain` 的 main、PR/Issue 和 `00-CURRENT.md`；NAS 是生产运行和真实业务数据权威；iMac/MBA 为独立 Clone。测试、合并、部署、用户体验验收四者分开记录。

## 7. 新窗口开始时只做这些

1. 读取本文件及 `AGENTS.md`、`docs/baseline/00-CURRENT.md`，再核对 [Issue #260](https://github.com/zxwan829/SecondBrain/issues/260)、[PR #269](https://github.com/zxwan829/SecondBrain/pull/269) 的**实时**状态；必要时核对 `Agent-Rules.md` 和正式 Decision Log，不重读所有历史。
2. 若 #269 仍开放：先处理其最新 HEAD 的最终 Review/CI 与合并；**不得以 #41783682072 的 `eb6c314` 绿灯代替后来新增提交的校验**。若已合并，记录 main merge SHA；生产发布仍单独请求用户授权。
3. V1 核心 UAT/缺陷按 `00-CURRENT.md` 的 NEXT 和四类问题分流继续收口；每次只给用户当前一项可执行动作。已做的验收不重复；失败查根因，不陷入同题循环。
4. 用户明确解冻 VNext 时，以 #260 已确认结构与本文件体验欠账为起点，先展示桌面**可运行**原型/线框、讨论并锁定页面骨架，不立刻把 PoC 合并或全站重写。正式颜色、网格、菜单和交互未确认前不擅自定版。

## 8. 直接索引

- [#260 VNext 产品基线与 UAT UX backlog](https://github.com/zxwan829/SecondBrain/issues/260)
- [#260：2026-11-04 V1 不大修旧 UI 决策](https://github.com/zxwan829/SecondBrain/issues/260#issuecomment-6619668705)
- [#260：首轮 UAT 界面欠账](https://github.com/zxwan829/SecondBrain/issues/260#issuecomment-6620612543)
- [#260：Chat 局部 P1 修复验收](https://github.com/zxwan829/SecondBrain/issues/260#issuecomment-6621667699)
- [#269 Chat 紧凑化 PR](https://github.com/zxwan829/SecondBrain/pull/269)
- [#41783682072 固定 eb6c314 的浏览器 SUCCESS](https://github.com/zxwan829/SecondBrain/actions/runs/41783682072)
- [#30 跨会话记忆](https://github.com/zxwan829/SecondBrain/issues/30)、[#261 Knowledge 浏览](https://github.com/zxwan829/SecondBrain/issues/261)、[#78 Review→Promote](https://github.com/zxwan829/SecondBrain/issues/78)
- [正式状态 00-CURRENT](00-CURRENT.md)、[Agent 规则](Agent-Rules.md)、[Decision Log](Decision-Log.md)、[运行快照](Environment-Baseline.md)
