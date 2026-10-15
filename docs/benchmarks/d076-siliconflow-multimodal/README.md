# D076 SiliconFlow 多模态综合评测准备

状态：**第一批真实调用进行中断保护：DeepSeek 已完成；GLM 请求已发出但结果未能取回；Qwen 未发送。没有重试。**

截至 2026-10-15，评测只使用本目录中的虚构素材与固定答案，不读取 Hermes 会话、正式 Capture/Review/Knowledge，不访问 Private；本轮不创建凭据或读取密钥内容，仅核验测试专用凭据文件的权限元数据。本目录中 PDF/图片均为合成内容。

## 1. 材料

| 文件 | 用途 | 标准事实 |
|---|---|---|
| `fixtures/01-technical-note.txt` | TXT 文档理解 | 编号 `SB-MULTI-01`、日期 `2026-10-15`、批次 `A17`、产量 128、缺陷 4、合格率 96.875%、周三前发送报告、FAQ 分 3 组 |
| `fixtures/02-technical-note.md` | Markdown/表格/行序理解 | 与 TXT 相同的业务数字；验证代码格式、表格和显式换行是否保留 |
| `fixtures/03-simulated-software-ui.png` | 仿真软件界面视觉理解 | `DEMO-042`、READY、128 rows、采集日期 2026-10-15、批次 A17、产量 128、缺陷 4、合格率 96.875% |
| `fixtures/04-synthetic-chart.png` | 图中文字/数据提取 | Q1=12、Q2=18、Q3=15；单位 items；纵轴 0/5/10/15/20 |
| `fixtures/05-synthetic-scan.pdf` | 扫描 PDF；无文本层 | `pypdf` 提取为空；印刷事实见下方扫描页答案 |
| `fixtures/06-readable-report.pdf` | 可读 PDF Fast Path | `pypdf` 提取含编号、日期、数字、行动项及简单表格；不应进入 OCR |
| `fixtures/07-synthetic-scan-page.png` | 视觉直读路线使用的本地扫描页渲染 | 来自扫描 PDF 合成页，最长边缩至 1600 px |

扫描页答案：编号 `SB-MULTI-01`；日期 `2026-10-15`；批次 `A17`；产量 128；缺陷 4；合格率 96.875%；任务“周三前发送测试报告”；灵感“将高频问题归类为 3 组”。视觉模型应只报告图中明确可见事实，不推断未标出的个人经历。

对话合成样本继续复用 `web-app/secondbrain-core/tests/test_organizer_synthetic_e2e.py` 中固定的虚构消息：生活记录、跨会话重复工作灵感、下一批次补充、待办、礼貌闲聊、普通问答。该测试用例自带固定答案与消息 ID / 时间，不以模型输出生成答案。

## 2. 当前型号与能力核查

Hermes 已配置的文本整理型号（本次只复用上一轮已记录的脱敏结果，不读取 NAS/Hermes 配置）：

| 场景 | SiliconFlow 模型 ID | 状态/上下文 | 输入/输出价（USD/M Token） | 图像输入 / JSON Mode | 当前选择 |
|---|---|---|---:|---|---|
| 文本整理 | `deepseek-ai/DeepSeek-V4-Flash` | Available / 1049K | $0.13 / $0.28 | 不支持 / 支持 | 纳入文本横评 |
| 文本整理 | `zai-org/GLM-4.5-Air` | Available / 131K | $0.14 / $0.86 | 不支持 / 不支持 | 纳入文本横评 |
| 文本整理/视觉 | `Qwen/Qwen3.5-35B-A3B` | Available / 262K | $0.24 / $1.80 | 支持 / 支持 | 纳入文本横评，也可作为视觉候选 |

最多三个视觉候选：

| 模型 ID | 当前目录状态 | 上下文 | 输入/输出价（USD/百万 Token） | 视觉及参数边界 |
|---|---|---:|---:|---|
| `deepseek-ai/DeepSeek-V4-Flash-Vision-Exp` | Available / Serverless | 1049K | $0.44 / $1.32 | 图像输入、JSON Mode 支持；实验型号；官方页面称每图计费最多 384 tokens |
| `zai-org/GLM-5V-Turbo` | Available / Serverless | 205K | $1.20 / $4.00 | 图像输入支持；JSON Mode 不支持；未找到其图像 Token 换算与模型级图片尺寸上限 |
| `Qwen/Qwen3.5-35B-A3B` | Available / Serverless | 262K | $0.24 / $1.80 | 图像输入、JSON Mode 支持；默认思考模式；官方说明 Qwen 图像缩放/Token 规则 |

三个原文本型号中 DeepSeek-V4-Flash 和 GLM-4.5-Air 官方目录均明确 `Support image input: Not supported`；不能直接拿它们测试视觉。Qwen3.5-35B-A3B 明确支持，因此无需仅为品牌对齐而更换。GLM-4.5V 页面已标记 Deprecated，故不选；GLM 视觉候选改用当前目录可用的 GLM-5V-Turbo。DeepSeek 候选为单独的实验视觉 ID，不能和文本型号混称。

SiliconFlow 多模态文档展示 `/chat/completions` 的 `image_url`，支持远程 URL 或 `data:` Base64，并展示多图消息及 `detail=low/high/auto`。本项目只会发固定 PNG 样本的内联 Base64，避免让供应商抓取任意 URL。官方当前查阅资料没有给出上述三个候选共同的文件格式全集/请求体字节上限；真实联调前需再核查型号 API Reference。评测本地将每图上限设为 2 MiB，缩放到不超过 1600×1600，且总请求体上限 8 MiB，这是本地保守门槛，不是供应商保证。Qwen 的文档像素范围为 56×56 至 3584×3584（约 12.8 MP）；`detail=low` 计 256 image tokens，`high` 按 28 像素 patch 计算。

API 公共参数文档列出 `temperature`、`top_p`、`n`、`stream`、`max_tokens`、`response_format` 等。统一实验参数建议 `temperature=0`、`n=1`、`stream=false`、同任务相同 `max_tokens`；不传 `top_p`（文档建议温度与 top_p 不同时调整），统一使用提示约束 JSON、不传 `response_format`，避免 GLM-5V-Turbo 的 JSON Mode 缺失造成不等价。`enable_thinking=false` 仅在该模型确实接受时发送；否则请求失败即停止，不改参数重试。所有型号的真实端点兼容性尚未联调。

### 2.1 视觉评测适配器边界（2026-10-15）

新增 `web-app/secondbrain-core/secondbrain_core/modules/vision_benchmark.py` 中独立的 `VisionBenchmarkAdapter`；不修改或接入 `SiliconFlowOrganizerModel`。它只允许上表三个视觉模型 ID，以 PNG/JPEG 本地字节构造 `data:image/png;base64,...` 或 `data:image/jpeg;base64,...` 的 `image_url` 内容，不接受远程图片 URL。请求不带 tools/tool_choice，不流式、不重试、单实例并发为 1，固定官方 HTTPS Chat Completions endpoint，45 秒以内超时；记录模型、usage、耗时、错误码和 trace ID，不记录图片或密钥。JSON Mode 兼容性按模型显式白名单：DeepSeek 与 Qwen 可由调用方选择，GLM 请求前拒绝；默认三者均不传 JSON Mode。没有模型页面证据支持 `enable_thinking` 的一致配置，所以全部省略。

客户端限制（不是供应商硬限制）：最多 3 张、每张最多 2 MiB、宽高各不超过 1600、最多 2.56 MP、序列化 JSON 请求体最多 8 MiB、输出最多 800 Tokens、响应体最多 128 KiB。尺寸上限比 Qwen 官方 3584×3584 像素上限更保守，并为其他型号使用统一低负载门槛。输出 JSON 在本地解析；usage 必须包含 prompt/completion/total token 数，且 completion 不得高于请求上限。非 2xx、429、重定向、超时、无效 JSON 和响应结构异常均返回脱敏错误，不带错误响应正文。

供应商资料核验：官方[视觉指南](https://docs.siliconflow.cn/docs/userguide/capabilities/vision) 展示 Chat Completions 的 Base64 Data URI 示例（JPEG）、`detail` 和多图格式；其[多模态指南](https://docs.siliconflow.cn/docs/userguide/capabilities/multimodal-vision) 给出 Qwen 56×56–3584×3584 与图像 token 处理说明，并称不同型号处理策略不同。官方[Chat Completions API](https://docs.siliconflow.cn/docs/api/chat-completions-post) 说明 `X-Trace-Id`、响应 trace header 和 usage。公开文档没有给出这三个候选模型共同、可确认的 PNG/JPEG Base64 请求体字节硬上限；JPEG Base64 有直接示例，但没有找到三个指定型号逐一承诺两种 MIME 的规范表。因此 PNG/JPEG 请求格式通过本地假服务验证，型号实际接受性仍待真实合成样本联调；2 MiB/图与 8 MiB/body 是本地保护阈值，不得宣称是供应商限额。候选型号的 JSON Mode 记录沿用本项目先前查阅的 SiliconFlow 模型目录结果；该端点兼容性仍待获授权后实测。

离线检查仅使用固定合成 PNG/JPEG 和本地 `httpx.MockTransport` 假 HTTP 服务，无真实网络调用、凭据创建或模型费用。覆盖请求字段/Base64、白名单、PNG/JPEG 类型检查、非支持格式和大小限制、总请求体限制、模型级 JSON Mode、429 无重试、重定向不跟随、超时与错误脱敏、异常响应/无效 JSON。真实视觉 API 联调条件尚未满足；需另行授权仅发送这些合成图片、指定准确模型及最多 3 次总请求（或更新后的上限）、串行/零重试/45 秒、使用用户专用 SiliconFlow key 经安全方式注入本地开发环境，并接受 ¥5 为软目标及事后账单核对。不得读取 Hermes 凭据或开启 Organizer。

## 3. 12 次请求上限与执行矩阵

严格串行、每项至多一次，不自动重试；任何超时、429、5xx、参数错误或 JSON 异常立即停止后续调用。实际请求数须用户另行授权。

| 请求序号 | 测试包 | 型号 | 发送内容 |
|---:|---|---|---|
| 1–3 | 对话整理 | DeepSeek-V4-Flash、GLM-4.5-Air、Qwen3.5-35B-A3B | 同一批合成消息、同一 Organizer 提示与 schema |
| 4–6 | 文件理解 | 同上 | 同一 TXT + Markdown 合成材料及同一要点提取提示 |
| 7–9 | PDF 解析 | 同上 | 一个可读 PDF 的 pypdf 文本 + 扫描 PDF 的固定 OCR 参考文本，分段标记来源；模型仅做下游提取。参考 OCR 文本不是 OCR 质量证据 |
| 10–12 | 视觉理解 | DeepSeek-V4-Flash-Vision-Exp、GLM-5V-Turbo、Qwen3.5-35B-A3B | 同一组 PNG（软件界面、图表、扫描页渲染），同一视觉提示和答案 schema |

调用规模：最多 12 个 HTTP 请求、单并发、无重试、每请求 45 秒客户端超时。共同输出上限按每测试类型提前固定（建议 Organizer 1200，其他提取类 800 Token），文本输入按当前 Adapter 的 UTF-8 字节上限预检；视觉请求在本地进行尺寸/字节预检。注意：Adapter 的输入字节裁剪不是服务端硬 Token 上限，`max_tokens` 文档注明不包含思维链 Token，45 秒客户端超时不能保证服务端未继续计费。

扫描 PDF 两条路由：

1. **OCR 文本路线**：本地 Poppler/Tesseract 提取后，将 OCR 文字作为带 `ocr_text` 标记的普通文本送入文本型号。当前开发机没有 Tesseract，因此此轮不声称 OCR 路线已产出真实识别稿；本计划里的固定参考文本仅能评测模型对已识别文字的解析能力。真实评测前需要使用本地 D076 OCR 对该合成 PDF 生成实际输出，并与固定答案逐项比对。
2. **视觉直读路线**：将扫描 PDF 第一页在本地渲染为 PNG，再与另外两张合成图片一同送给视觉候选。此路线测模型看页面的提取质量，不上传 PDF 文件，也不测试本地 OCR。

## 4. 固定答案及评分

### 对话整理

- 应提取：公园/家庭生活感受（日记候选）、客服高频问题知识卡片（工作灵感，同一主题重复表达合并并保留两处来源）、周五前将试点计划发给小林（待办）。下一批消息“先从最近一个月的高频问题开始”只能补充前述工作灵感，不能生成旧消息副本。
- 应过滤：`谢谢，收到。`、普通地理知识问答及助手回答；不能把助手建议改写成用户经历/决定。
- 原有测试文件内提供确切 source `session_id`/`message_id`/UTC timestamp 与引文。

### 文档、PDF、图片

- 所有数字必须精确：128、4、96.875%、A17、日期 2026-10-15。
- 图表数据必须精确为 Q1 12、Q2 18、Q3 15；不得把纵轴刻度当成某季度数值。
- PDF 提取必须区分 pypdf 正文与 OCR 来源文本；不得宣称 OCR 字符准确仅因模型正确归纳了参考文本。
- 视觉结果拆为“可读文字/字段”和“画面描述”；数值错误单独计错；不允许虚构上下文。

### 指标

1. **分类/字段精确率、召回率、F1**：以本文件列明的必需字段、类别和过滤项作人工金标准；对遗漏与幻觉分别记数。
2. **来源/引用准确率**：Organizer 每一引用的 session/message ID、UTC 时间、原文连续子串均正确才计正确。
3. **重复率**：同主题产生的多余草稿数 / 有效主题数；目标为 0。
4. **结构化结果率**：响应可解析且满足固定 JSON Schema 才通过；模型不可用 JSON Mode 时仍按相同 prompt-only 规则评分。
5. **视觉数字准确率**：识别出的明确文本/数值正确项 / 金标准项；错读和缺失分别列出。
6. **成本/时延**：记录 API request ID/trace ID、HTTP 状态、单调时钟时延、返回 usage；按复核时的官方价估算。用户随后在 SiliconFlow 控制台核对实际费用。API usage 与实际账单不是同义证据。

## 5. 第一批文本模型真实调用前置核验（2026-10-15）

用户已授权在本机以合成样本对三款文本模型各最多调用一次，并确认 SiliconFlow 账户有可用余额；用户接受 `max_tokens=1200` 是最终回复配置上限，思维令牌可能另计费用，¥5 为软预算。测试专用凭据文件的存在、属主、权限及仓库外位置已核验；凭据内容未读取或输出。

本次检查发现现有 Organizer 适配器曾对所有型号统一发送 `enable_thinking=false`，但公开 API 文档只称该参数适用于“大多数推理模型”，未逐一确认本次三款型号均兼容。为避免依赖未经确认的统一参数，适配器已改为省略该字段；三模型相同请求的离线测试继续验证参数一致。

限制说明：SiliconFlow 官方 [Chat Completions API](https://docs.siliconflow.cn/docs/api/chat-completions-post) 明确说明 `max_tokens` **不包含思维链部分**；响应示例中的 `completion_tokens` 则包含 `reasoning_tokens`。用户已明确接受这一点。本次适配器不发送未逐型号核实的 `enable_thinking`，且不再把响应 usage 高于 `max_tokens` 当作拒绝/费用控制；它记录完整 usage（包括供应商返回的 reasoning_tokens）、状态、耗时与 trace ID。官方[推理模型说明](https://docs.siliconflow.cn/docs/userguide/capabilities/reasoning)的 `thinking_budget` 兼容性仍不作为本轮统一参数。

本地专项测试 `tests/test_siliconflow_organizer.py`：**10 passed**。测试确保请求不再统一发送未逐型号核实的 `enable_thinking`，并保留可能高于 `max_tokens` 的 completion/reasoning usage；Mock 测试不涉及真实网络或凭据。

本轮新增 `secondbrain_core/modules/siliconflow_eval_run.py` 和 `run_d076_text_benchmark.py`：使用 UUID 运行 ID、逐模型 `pending/started/completed/unknown` 状态、私有目录与文件权限、原子结果写入和单运行锁。`prepare` / `status` 不发请求；真实 `run` 必须显式指定已有运行 ID、白名单模型、私有 Key 文件路径并传入确认开关。`started` 只表示尝试槽已持久化，不证明请求已发送；执行器重开时，已无活动锁的遗留 `started` 会变为 `unknown`，不会自动重试。完成结果仅保留脱敏的状态、usage、耗时、trace ID 和结构化输出，可追加人工评分及有来源的费用估算；不保存请求头或 Key。`tests/test_siliconflow_eval_run.py` 通过 MockTransport / 慢协程覆盖慢响应、执行器取消与重开恢复、并发启动、重复启动、HTTP 429 及已完成状态恢复。两个专项测试文件合计 **16 passed**。此前 DeepSeek/GLM 请求发生在账本建立前，不能追溯伪造原运行 ID；在 GLM UNKNOWN 状态核清前，不应为相同评测创建新运行并重发 GLM。

已观察到的调用：

| 顺序 | 模型 ID | 状态 | 输入 / 输出 / reasoning / 总 Token | 耗时 | trace ID | 估算费用 | 结果摘要 |
|---:|---|---|---:|---:|---|---:|---|
| 1 | `deepseek-ai/DeepSeek-V4-Flash` | HTTP 200，JSON 有效 | 501 / 925 / 454（含于输出）/ 1426 | 7.2 秒 | `49520d7382b94362910446462520f1b5` | ¥0.009828 | 3 条：日记、合并的工作灵感、待办；闲聊和普通问答未生成草稿；引用 ID 与原文吻合 |
| 2 | `zai-org/GLM-4.5-Air` | 请求已发出；执行器在 30 秒等待后返回仍运行会话，后续结果不可取回 | 未知 | 至少 30 秒等待；最终耗时未知 | 未知 | 未知，待后台核对 | 不重试；不可评估响应 |
| 3 | `Qwen/Qwen3.5-35B-A3B` | 未发送 | — | — | — | ¥0 本次调用 | 前一请求结果不可观测，按异常停止条件不继续 |

DeepSeek 估价按本次时段（北京时间 08:00–次日 02:00）公开非缓存价 ¥3/M 输入、¥9/M 输出计算，不应用缓存折扣；思维令牌已包含在 925 completion tokens 中，没有重复相加。此估价不是后台账单。GLM 请求可能已产生费用，用户需在 SiliconFlow 控制台按本表 trace/time 核对。¥5 仍是软预算，不是供应商硬上限。

执行器没有保留 GLM 请求对应的会话句柄，因此无法取得最终 HTTP 状态、usage、响应或 trace ID。不能安全确认该请求成功、失败或是否计费；不得重试。此项结果可观测性问题解决并由用户核对 GLM 后台费用前，不再发起后续模型调用。

本轮没有已连接的 SiliconFlow 控制台账单会话，且用户明确禁止本轮新 API 请求；因此未能只读查询上一笔 GLM 请求记录。其请求是否完成及实际费用仍为 **UNKNOWN**，没有假设未计费。已知 DeepSeek 的 trace ID 可用于控制台核账。新增持久化执行器是在本次丢失事件后实现；不能追溯补造 GLM 原始请求的状态记录。

横评结果仅代表这组人工合成样本，不外推一般能力。预期记录表模板：

| 序号/任务 | 模型 ID | 状态/trace ID | 结果/F1 | 引用准确率 | 重复率 | JSON/结构率 | 视觉字段正确数 | 延时 | 输入/输出 usage | 估算 USD | 控制台实费 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1–12 | 联调时填写 | 未请求 | — | — | — | — | — | — | — | — | 待用户核账 |

## 6. 预算边界与联调前授权

总目标仍为 **人民币 5 元**，只是目标预算，供应商硬封顶未证明。以下只是透明的量级估算，假设对每个文本模型分别使用 Organizer 6k/1.2k、文件 3k/0.5k、PDF 5k/0.8k 输入/输出 Token；视觉每项约 1k 文本输入 + 600 输出，另计图像 Token：DeepSeek 按官方“最多 384 token/图”与 3 图计 1152，Qwen 按 `detail=low` 3×256 计 768。GLM 图像 Token 规则未查到，表中先按纯文字基线计算：

| 组 | 按官方单价的基准估算 USD | 说明 |
|---|---:|---|
| Organizer 3 次 | 0.006588 | 每个文本模型 6000/1200 input/output |
| TXT/Markdown 3 次 | 0.003000 | 每个文本模型 3000/500 |
| PDF 文本路线 3 次 | 0.004902 | 每个文本模型 5000/800 |
| 视觉 3 次 | 0.006843 + GLM 图像费用未知 | DeepSeek/Qwen 使用上述图像 Token 估算；GLM 为 1000/600 纯文字基线，按每 1000 个图像输入 Token 另加约 $0.0012 |
| **合计基线** | **约 $0.021333 + GLM 图像 Token 费用** | 未含费率变动、缓存/思考计费差异、请求失败仍计费等；不能保证折算后不超过 ¥5 |

该估算不是供应商账单或封顶。图片高分辨率处理会改变 Qwen 的 image token；DeepSeek 页面“up to 384”不能替代真实 usage；GLM 不明的图像计价是主要未知项。请求后必须使用服务端 usage 和平台后台账单复核，异常后立即停止。

下一阶段真实联调须单独明确授权：

1. 允许对 SiliconFlow 发送本目录中的虚构文本、PNG 及合成 PDF 渲染页；明确确认数据只传此类公开/虚构样本。
2. 指定批准本表中的 exact model IDs，并确认最多 12 个**总请求**、串行、45 秒、零自动重试、任一异常即停。
3. 确认 ¥5 是软目标而非硬费用封顶；最好由用户在供应商后台预先设置并确认账户消费限制及超限拒绝行为，Codex 不以推测替代。
4. 单独授权创建专用 SiliconFlow API Key 并由用户通过安全隐藏输入/受控 Secret 文件注入开发测试 Core；不得读取 Hermes Key、不得放环境变量/前端/Git。
5. 若本地 Tesseract 对扫描样本识别有严重错误，先暂停 PDF 模型比较；不追加请求。

**未完成/阻断：** 无真实 API 可用性/参数兼容性确认；无供应商硬输入 Token 或硬支出封顶证据；本机无 Tesseract，扫描件 OCR 实际文本需另行完成本地离线验收；GLM 图像输入的具体尺寸/图片计费规则待官方型号资料或联调前控制台复核。Organizer 仍关闭，定时任务不运行。

## 7. Fixture SHA-256

| 文件 | SHA-256 |
|---|---|
| `01-technical-note.txt` | `a11946c9381ab0f2236c09918780a35d96ceec45eecef0d2b46e95017cc0b63c` |
| `02-technical-note.md` | `11a5037d44734e62644a06a30f81a3cf785fa56f878783762b88d9b6909c32fd` |
| `03-simulated-software-ui.png` | `389bb997d727c9a40559e583b582cac5393ff8c5d7574df8500020e5465ffd18` |
| `04-synthetic-chart.png` | `d963b559c0281e75eebdc891636266b17ae25ad3414164fd33dee3e84f42b656` |
| `05-synthetic-scan.pdf` | `7b01fa54529ab163c36c1f050f05a489778cc353d7ae6a3206532a29ec5eaf59` |
| `06-readable-report.pdf` | `37c8f641406dbdc1eea88d8684b01cde26a181c765872fbc7c4544f3094da324` |
| `07-synthetic-scan-page.png` | `e186d7de1ac9ac22c56f05273f032badb6655b407673c5c67253b46c3776ee6b` |
