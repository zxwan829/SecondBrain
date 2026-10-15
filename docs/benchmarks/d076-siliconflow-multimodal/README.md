# D076 SiliconFlow 多模态综合评测准备

状态（2026-10-15）：文本横评中 DeepSeek 已完成，GLM 已确认计费但响应不可恢复，文本 Qwen 后续账单页显示计费约 ¥0.0068、券抵后账单 ¥0。视觉横评中 Qwen 一次 HTTP 200 但输出截断；DeepSeek Vision 与 GLM-5V-Turbo 各一次 HTTP 400，均无 usage/模型输出，不评分；GLM 返回供应商结构化错误码 20012（官方解释为模型不存在），当前账单页未列出视觉调用，但最终费用仍 UNKNOWN。所有请求均未重试。

评测只使用本目录中的虚构素材与固定答案，不读取 Hermes 会话、正式 Capture/Review/Knowledge，不访问 Private；API 凭据由隔离进程从仓库外的私有文件读取，未输出、记录或提交密钥。本目录中 PDF/图片均为合成内容。

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

客户端限制（不是供应商硬限制）：最多 3 张、每张最多 2 MiB、宽高各不超过 1600、最多 2.56 MP、序列化 JSON 请求体最多 8 MiB、输出参数最多 2000 Tokens、响应体最多 128 KiB。尺寸上限比 Qwen 官方 3584×3584 像素上限更保守，并为其他型号使用统一低负载门槛。输出 JSON 在本地解析；记录完整可用 usage 与 `finish_reason`。`max_tokens` 是最终回复配置，不保证 reasoning tokens 的硬上限或硬费用封顶。非 2xx、429、重定向、超时、无效 JSON 和响应结构异常均返回脱敏错误，不带错误响应正文。

供应商资料核验：官方[视觉指南](https://docs.siliconflow.cn/docs/userguide/capabilities/vision) 展示 Chat Completions 的 Base64 Data URI 示例（JPEG）、`detail` 和多图格式；其[多模态指南](https://docs.siliconflow.cn/docs/userguide/capabilities/multimodal-vision) 给出 Qwen 56×56–3584×3584 与图像 token 处理说明，并称不同型号处理策略不同。官方[Chat Completions API](https://docs.siliconflow.cn/docs/api/chat-completions-post) 说明 `X-Trace-Id`、响应 trace header 和 usage。公开文档没有给出这三个候选模型共同、可确认的 PNG/JPEG Base64 请求体字节硬上限；JPEG Base64 有直接示例，但没有找到三个指定型号逐一承诺两种 MIME 的规范表。因此 PNG/JPEG 请求格式通过本地假服务验证，型号实际接受性仍待真实合成样本联调；2 MiB/图与 8 MiB/body 是本地保护阈值，不得宣称是供应商限额。候选型号的 JSON Mode 记录沿用本项目先前查阅的 SiliconFlow 模型目录结果；该端点兼容性仍待获授权后实测。

离线检查仅使用固定合成 PNG/JPEG 和本地 `httpx.MockTransport` 假 HTTP 服务。之后单独授权的首个真实视觉请求见第 8 节。适配器覆盖请求字段/Base64、白名单、PNG/JPEG 类型检查、非支持格式和大小限制、总请求体限制、模型级 JSON Mode、429 无重试、重定向不跟随、超时与错误脱敏、异常响应/无效 JSON。真实联调只用仓库合成图片，不读取 Hermes 凭据或开启 Organizer。

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

本轮新增 `secondbrain_core/modules/siliconflow_eval_run.py` 和 `run_d076_text_benchmark.py`：使用 UUID 运行 ID、逐模型 `pending/started/completed/unknown` 状态、私有目录与文件权限、原子结果写入和单运行锁。`prepare` / `status` 不发请求；真实 `run` 必须显式指定已有运行 ID、白名单模型、私有 Key 文件路径并传入确认开关。`started` 只表示尝试槽已持久化，不证明请求已发送；执行器重开时，已无活动锁的遗留 `started` 会变为 `unknown`，不会自动重试。完成结果仅保留脱敏的状态、usage、耗时、trace ID 和结构化输出，可追加人工评分及有来源的费用估算；不保存请求头或 Key。可将先前已观察的完成响应或结果未知请求导入同一账本，不触发网络；UNKNOWN 条目不可重发，并会阻止后续模型越过顺序门禁。`tests/test_siliconflow_eval_run.py` 通过 MockTransport / 慢协程覆盖慢响应、执行器取消与重开恢复、并发启动、重复启动、HTTP 429、历史状态导入及已完成状态恢复。两个专项测试文件合计 **17 passed**。此前 DeepSeek/GLM 请求发生在账本建立前，不能追溯伪造原运行 ID；本轮仅用已观察证据做本地对账记录。

已观察到的调用：

| 顺序 | 模型 ID | 状态 | 输入 / 输出 / reasoning / 总 Token | 耗时 | trace ID | 估算费用 | 结果摘要 |
|---:|---|---|---:|---:|---|---:|---|
| 1 | `deepseek-ai/DeepSeek-V4-Flash` | HTTP 200，JSON 有效 | 501 / 925 / 454（含于输出）/ 1426 | 7.2 秒 | `49520d7382b94362910446462520f1b5` | ¥0.009828 | 3 条：日记、合并的工作灵感、待办；闲聊和普通问答未生成草稿；引用 ID 与原文吻合 |
| 2 | `zai-org/GLM-4.5-Air` | 账单确认已计费；HTTP/响应不可恢复 | 账单导出计量 493 / 2715；非响应 usage | 执行结果丢失 | 未恢复 | ¥0.016783 计费；代金券后应付 ¥0 | 账单确认发生调用；无响应质量评分、无伪造状态/trace |
| 3 | `Qwen/Qwen3.5-35B-A3B` | 客户端超时，状态 UNKNOWN | 未知 | 45.0 秒客户端超时 | `e5e254dde6c24c83986f2df4793d3dd9`（客户端生成） | 未知；可能仍计费 | 未取得 HTTP 状态、响应 JSON、usage 或模型质量；不重试 |

DeepSeek 估价按本次时段（北京时间 08:00–次日 02:00）公开非缓存价 ¥3/M 输入、¥9/M 输出计算，不应用缓存折扣；思维令牌已包含在 925 completion tokens 中，没有重复相加。此估价不是后台账单。用户提供的 SiliconFlow 官方导出确认 GLM 计费金额 ¥0.016783、代金券抵扣后应付 ¥0；导出用量 493/2715 是账单证据，不代表找回了 GLM 响应或 HTTP usage。¥5 仍是软预算，不是供应商硬上限。

执行器没有保留 GLM 请求对应的会话句柄，因此无法取得最终 HTTP 状态、API usage、响应或 trace ID。用户后续提供的账单可确认已发生计费，但不能恢复模型输出；该模型不参与质量评分，也不得重试。

之前未能直接连接 SiliconFlow 控制台；本轮依据用户提供的官方账单导出登记 GLM 计费事实，但 HTTP 结果与质量仍为 **UNKNOWN**。新增持久化执行器是在原 GLM 结果丢失后实现；不能追溯补造原请求的状态记录。

本机仓库外的文本对账账本 `e2dabfb6-d4d7-40da-b39f-be5591515b4e`（目录 `0700`、账本文件 `0600`）记录 DeepSeek 完成、GLM 的账单异常终态及 Qwen 一次调用。GLM 从 `unknown` 经用户授权的人工异常处置进入 `billed_result_unavailable`，保留 1 次尝试和账单证据；不包含 HTTP 状态、trace、响应或质量分数。该状态只解除顺序门禁以允许下一模型，不允许 GLM 重试。

Qwen 的单次真实请求于 2026-10-15 19:43 左右启动；客户端等待 45 秒后超时。账本已原子保存 `unknown`、`attempts=1`、`provider_timeout`、45001.2 ms 与客户端生成的 trace ID `e5e254dde6c24c83986f2df4793d3dd9`。没有收到 HTTP 响应，故 HTTP 状态、完整 JSON、分类/引用/去重结果、输入/输出/推理 usage 和费用估算均为 UNKNOWN；请求可能已在服务端处理或计费。禁止重发。SiliconFlow [当前价格页](https://siliconflow.cn/pricing)列出该型号 128K 以下输入 ¥0.40/M、输出 ¥3.20/M，但缺少 usage 且 max_tokens 不构成服务端总费用封顶，不能据此伪造本次费用估算或保证不超过 ¥5。

本批已知计费金额合计 ¥0.026611（DeepSeek ¥0.009828 + GLM ¥0.016783）；两笔代金券抵扣后的应付金额均为 ¥0。此合计不含文本 Qwen：账单页刷新后仍只有 DeepSeek 和 GLM 两个模型汇总行，尚未看到 Qwen 行；因账单可能延迟或汇总口径不同，不能据此认定未计费，文本 Qwen 仍为 UNKNOWN。

## 8. SiliconFlow 视觉横评首请求（2026-10-15）

调用前检查：复用此前成功完成文本请求的 SecondBrain 专用 Key；账户账单页只显示脱敏 Key 标识与描述，没有读取 Key 内容。余额页显示可用余额约 `¥2.9859…`（界面尾数被截断）、3 张可用代金券、透支额度为 ¥0。费用明细按 2026-10-15 刷新后列出 DeepSeek 与 GLM 两行，未见文本 Qwen 行；此为当前页面观察，不代表供应商确认最终不计费。图片样本是仓库中 3 张固定合成 PNG：仿真软件 UI、合成图表、扫描 PDF 页面渲染；请求 JSON 预检约 287,028 bytes，低于本地 8 MiB 上限。

首个视觉模型为 `Qwen/Qwen3.5-35B-A3B`。参数：单请求、3 张合成 PNG、`detail=low`、`max_tokens=800`、`temperature=0`、`n=1`、非流式、不使用 JSON Mode、不发送 tools、`enable_thinking` 或其他未核实参数；客户端超时 45 秒、无重试。真实视觉运行账本为仓库外 `~/.local/state/secondbrain/d076-vision-benchmark/384bb6a7-03cc-4a63-b3d8-c66d81507097.json`，目录 `0700`、文件 `0600`；记录调用前 `started`、合成 fixture SHA-256 和请求参数摘要。

| 模型 | HTTP / 终态 | 耗时 | Token usage | 完整 JSON / 评分 | 估价 / 账单 |
|---|---|---:|---|---|---|
| `Qwen/Qwen3.5-35B-A3B` | HTTP 200；`provider_output_truncated`，账本 `failed`，尝试 1 次 | 32.107 秒 | 本地错误记录缺少 usage；当前账单页未见 Qwen 行 | `finish_reason=length`，未得到完整 JSON，文字/数字/引用/描述均不评分 | 单价见官方[价格页](https://siliconflow.cn/pricing)：128K 内输入 ¥0.40/M、输出 ¥3.20/M；无 usage，不估算本次金额；仍可能计费 |
| `deepseek-ai/DeepSeek-V4-Flash-Vision-Exp` | 未发送 | — | — | — | 未产生本轮请求 |
| `zai-org/GLM-5V-Turbo` | 未发送 | — | — | — | 未产生本轮请求 |

Qwen 请求返回 HTTP 200，但模型输出达到配置上限并以 `finish_reason=length` 结束。已记录的追踪标识为 `fc65a99d-1330-4020-8014-3e29e0555d81`，耗时 32.107 秒。该响应不满足成功条件，依“任何异常即停”约束，未发送 DeepSeek Vision 或 GLM-5V 请求，也没有重试。账单页目前未显示 Qwen 行，但最终费用仍未知，后续应按时间与 trace 在后台复核。账本保存的是失败元数据，不伪造最终 JSON 或评分。

本次错误揭示适配器此前未将 `finish_reason=length` 响应中的 usage 持久化。代码现已调整：对截断/解析错误保留 HTTP 状态、trace、finish reason 及通过白名单筛选的 input/output/reasoning usage；此修复不能恢复本次已丢失的 usage。离线测试验证该行为。

截至此处，视觉横评只有 Qwen 一次失败请求；尚无任何模型视觉准确性结论。总测试软预算 ¥5 仍未证实为硬封顶，折扣券抵扣与模型实际账单应分别核对。

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
## 9. 紧凑提示词后续视觉请求（2026-10-15）

为避免 Qwen 上次长篇输出截断，提示词已改为紧凑 JSON：仅含图片编号、可见原文、关键数字/字段及必要的短证据；每图最多 10 条文字、8 条事实、5 条界面信息。不要求长篇描述、不推测缺失内容。继续使用原三张合成 PNG，SHA-256 见运行账本；请求不启用 JSON Mode，也不传 `enable_thinking`、工具或模型专属参数。单请求 `max_tokens=2000`、45 秒超时、串行、零重试；推理 Token 可能超出最终回复配置并产生费用，¥5 仍为软预算。

本次读取专用 Key 文件前核对其为当前用户拥有的常规文件、非符号链接、权限 `0600`；没有读取或输出其内容。SiliconFlow 控制台显示余额约 `¥2.9859…`（页面尾数省略）、3 张可用券、透支额度 `¥0`。调用前公开价格页面为：DeepSeek Vision 输入 `$0.44/M`、输出 `$1.32/M`；GLM-5V-Turbo 输入 `$1.20/M`、输出 `$4.00/M`。估算依赖实际 usage；未知图像 token 换算及推理额外用量不作猜测，使用优惠券后的实付以控制台为准。[SiliconFlow 官方价格页](https://www.siliconflow.com/pricing)；[DeepSeek Vision 型号页](https://www.siliconflow.com/models/deepseek-v4-flash-vision-exp)；[GLM-5V-Turbo 型号页](https://www.siliconflow.com/models/glm-5v-turbo)。

新建独立私有账本 `~/.local/state/secondbrain/d076-vision-benchmark/ca44dd30-4a0e-4935-8f88-3f1d4ab0877f.json`，仅含 DeepSeek Vision、GLM，固定两者顺序；不触碰旧 Qwen 账本 `384bb6a7-03cc-4a63-b3d8-c66d81507097.json`。离线新增覆盖紧凑提示词/2000 参数、子集顺序门禁、评分写入与 finish reason 持久化；视觉适配器和账本专项测试共 **16 passed, 2 subtests passed**。

| 模型 ID | 状态/HTTP | 耗时 | usage / finish reason | 输出与评分 | 费用 |
|---|---|---:|---|---|---|
| `deepseek-ai/DeepSeek-V4-Flash-Vision-Exp` | `failed`，HTTP 400，尝试 1 次 | 162 ms | usage 未返回/未解析；finish reason 不适用；trace `f2240011-d98b-4498-bc99-0dd5e7943d30` | 没有响应 JSON，不评分 | 无法估算；调用后刷新账单未出现此模型行，但账单可能延迟，金额仍待核实 |
| `zai-org/GLM-5V-Turbo` | 未调用；前一模型异常后按规则停止 | — | — | — | 未发出请求 |

DeepSeek Vision 的唯一请求因 HTTP 400 立即终止该轮；不读取供应商错误正文、不改变参数探测、不重试，也不继续 GLM。账单页刷新后仍显示先前记录（DeepSeek 文本、GLM 文本、Qwen 文本），没有 DeepSeek Vision 行；这只能作为当前观察，不能证明请求未计费。用户可稍后按模型、时间及 trace 在后台复核。下一步若要调用 GLM，须先分析此 400 的已公开原因或由用户决定后续范围；不得直接恢复顺序继续发送。

## 10. DeepSeek Vision HTTP 400 只读诊断（2026-10-15）

### 证据与请求差异

| 项目 | Qwen 已调用请求 | DeepSeek Vision 已调用请求 |
|---|---|---|
| 模型 ID | `Qwen/Qwen3.5-35B-A3B` | `deepseek-ai/DeepSeek-V4-Flash-Vision-Exp` |
| 图片 | 相同的 3 张合成 PNG，SHA-256 与上节一致 | 相同的 3 张合成 PNG |
| 消息 | 单个 user message；3 个 `image_url` 内容项后跟 text | 相同结构 |
| 图片参数 | 每项 `detail=low` | 每项 `detail=low` |
| 通用请求参数 | `stream=false`、`max_tokens=800`、`temperature=0`、`n=1` | `stream=false`、`max_tokens=2000`、`temperature=0`、`n=1` |
| 省略项 | 无 tools、`tool_choice`、JSON Mode、`enable_thinking` | 相同 |
| 结果 | HTTP 200，随后 `finish_reason=length` | HTTP 400，162 ms |

账本只保存模型、固定图片哈希、图片数、`detail=low`、JSON Mode 开关、最大输出 Token、提示词哈希、HTTP 状态、通用错误码和 trace。它**没有**保存原始请求体、图片 Base64 或供应商响应正文，因此不能回溯确切的 provider error code/param，也不能恢复请求体逐字节快照。

### 公开资料能证明什么

- SiliconFlow 型号页列出该准确 DeepSeek 型号为 Available、支持 image input；模型资料还称图像按最多 384 tokens/张计费。[DeepSeek-V4-Flash-Vision-Exp 型号页](https://www.siliconflow.com/models/deepseek-v4-flash-vision-exp)
- SiliconFlow 通用视觉指南展示 `/chat/completions` 的 `image_url`、Base64 Data URI、`detail=low` 和多图消息格式；Base64 示例使用 JPEG。该指南称 `low/high/auto` 是视觉接口通用 detail 选项。[视觉接口指南](https://docs.siliconflow.cn/docs/userguide/capabilities/vision)
- 通用 Chat Completions 文档列出 `messages`、`stream`、`max_tokens`、`temperature`、`n` 等标准字段，也列出了服务端错误示例，但该请求没有保留错误正文，无法把 400 对应到某个错误码。[Chat Completions API](https://docs.siliconflow.cn/docs/api/chat-completions-post)
- 多图指南允许一个 message 包含多个 `image_url`。其中“DeepseekVL2 建议最多 2 张”的说明只针对 DeepseekVL2，不能直接套用到 `DeepSeek-V4-Flash-Vision-Exp`。

### 判断（证据强度）

**结论：原因尚不能确定。** 162 ms 的 400 与模型/请求输入校验失败相符，但这是推断，不是服务端证据。最值得先怀疑的是 DeepSeek Vision 对 PNG Base64 或 `detail` 子字段的型号级兼容性：公开通用示例确实证明 JPEG Data URI，未找到该型号逐一承诺 PNG；不过通用指南又说明支持 detail。三张图片不是当前首要嫌疑，因为通用接口示例支持多图，且 DeepseekVL2 的两图建议不适用于本型号。`max_tokens=2000`、`temperature=0`、`n=1` 和 `stream=false` 都是通用字段，现有证据未指向它们。Qwen 的 200 只能证明相同的整体格式对 Qwen 可用，不能证明 DeepSeek 后端接受每个子字段。

HTTP 400 最可能属于**模型侧输入校验/多模态预处理拒绝**，具体触发字段仍 UNKNOWN。没有足够证据把它归结为图片数量、PNG MIME、`detail` 或 Token 参数中的某一项；也不能据 162 ms 推断没有计费。

### 诊断安全修复

本地修复使未来非 2xx/429 响应仅可持久化供应商结构化的 `type`、`code` 和严格参数名白名单（例如 `model`、`messages`、`detail`、`max_tokens`）。原始错误正文、任意字段、图片、鉴权数据始终不保存；大于 16 KiB 的错误正文不解析。假服务测试覆盖标准格式差异、错误码/参数提取、拒绝异常标识及 message 内容脱敏。该代码不能恢复本次 400 的已丢失细节。

**当时对 GLM 的判断：** 撰写本节时 GLM-5V-Turbo 尚未调用；它支持图像输入但 JSON Mode 不支持，因此请求不启用 JSON Mode。相同 `image_url` 与 PNG MIME 兼容性风险仍存在，无法根据 DeepSeek 结果预测 GLM 结果。后来唯一一次 GLM 请求的证据与结论见第 11 节；不自动执行 JPEG 转换、移除 `detail` 或拆分图片等试探。

## 11. GLM-5V-Turbo 唯一视觉请求结果（2026-10-15）

按用户授权对 `zai-org/GLM-5V-Turbo` 发送一次请求；复用同一组 3 张合成 PNG、SHA-256 与第 9 节一致，使用相同紧凑 JSON 提示词、`detail=low`、`max_tokens=2000`、`temperature=0`、`n=1`、非流式。没有启用 JSON Mode、tools、`tool_choice` 或 `enable_thinking`。专用 Key 文件仅由评测进程读取；权限元数据核验为当前用户所有、`0600`，父目录 `0700`，未输出密钥。

请求前 SiliconFlow 控制台显示余额约 ¥2.9859（界面省略尾数）、透支额度 ¥0、3 张可用券；不能确认这些券对该模型适用，未把它们视为费用保证。官方型号页当前列出模型 Available、支持图像输入，价格输入 $1.20/M、输出 $4.00/M。人民币 ¥5 仍是软预算，不是硬限额。[GLM-5V-Turbo 型号页](https://www.siliconflow.com/models/glm-5v-turbo)；[SiliconFlow 价格页](https://www.siliconflow.com/pricing)

| 模型 ID | 状态/HTTP | 耗时 | usage / finish reason / trace | 输出与评分 | 费用 |
|---|---|---:|---|---|---|
| `zai-org/GLM-5V-Turbo` | `failed`，HTTP 400，尝试 1 次 | 155 ms | usage 未返回；finish reason 不适用；trace `5ab162f3-b924-462e-8431-bc3464cb2996`；安全账本仅保留结构化错误码 `20012` | 无模型输出；仿真界面、图表数字、扫描页文字与引用均不可评分 | 无法估算；请求后账单页尚未出现此模型记录，仍按 UNKNOWN 处理 |

官方错误码文档将 `20012` 解释为 “Model does not exist”。这说明该次请求被服务端按模型不存在拒绝，是当前最强的直接诊断证据；但 SiliconFlow 型号页同时显示准确 ID `zai-org/GLM-5V-Turbo` 为 Available 且支持图像输入。公开证据无法解释这两者冲突，可能与后端模型路由/账户可用性同步有关，但不能确认。未保存或输出供应商错误正文，没有重试，也没有继续探测参数。[官方错误码说明](https://docs.siliconflow.cn/en/faqs/error-code)

**横评结论：** 当前没有获得可用且可评分的视觉模型结果：Qwen 输出被截断，DeepSeek Vision 返回 HTTP 400，GLM 返回 HTTP 400/20012。停止扩大模型测试。后续应先由 SiliconFlow 支持或控制台确认视觉型号在该账户及 `api.siliconflow.cn` 路由上的实际可用性；若供应商确认模型可用，再另行评估要不要创建新运行批次进行一款模型的单次验证。不得自动换供应商、重试既有模型、调整图片格式/参数试探或将失败伪装成成功。
