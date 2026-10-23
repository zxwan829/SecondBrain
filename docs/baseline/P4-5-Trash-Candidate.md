---
updated: 2026-10-23
status: candidate-not-frozen
type: p4-5-trash-storage-and-web-contract-candidate
baseline: e28db843df53c2ac48c71abbedeb3713c77d338b
---
# P4-5 Trash 物理位置与 Web 行为候选

本文记录 A 线基于当前正式业务规范、仓库代码与合成目录模型形成的候选。**它不是已冻结的 Core 接口、生产目录授权或执行批准。** 正式业务规范目前仍写明物理位置、搜索排除与清理策略待确认；在 Core 负责人核对运行时挂载和权限之前，不创建真实 Trash 目录、不迁移或删除真实文件。

## 盘点证据与边界

- `docs/baseline/业务规范.md` 记录用户确认的 Vault 可见顶层：`00-Inbox/`、`10-Review/`、`20-Knowledge/`、`30-Projects/`、`40-Memory/`、`50-Journal/`、`90-Archive/` 与 `Home.md`。它明确 `90-Archive` 不是 Trash；截图没有展示子目录，不能推断内部布局。
- 当前 Notes Core 从 `SB_NOTES_DRAFTS_ROOT` 与显式 `SB_NOTES_AUTHORIZED_ROOTS` 构造 `NotesStore`，并拒绝与 Knowledge、Review、Capture Raw、Journal、Private 保护域重叠的根。仓库配置没有 Trash root；Notes router 暴露创建、读取、更新、历史和附件操作，没有删除/恢复端点。
- `.env.example` 仅展示配置键和示例路径；本次没有读取机器上的 Vault、NAS、生产配置或真实目录，故当前物理根、Owner/ACL、挂载拓扑、Obsidian 删除设置与 Synology Drive 对隐藏目录的同步行为均为 **UNKNOWN**。
- Obsidian 官方《Manage notes》说明可在 Settings → Files & Links 配置删除目标，其中 Obsidian trash 使用 Vault 内 `.trash` 目录：[官方文档](https://github.com/obsidianmd/obsidian-help/blob/master/en/Files%20and%20folders/Manage%20notes.md)。这证明 `.trash` 是产品兼容候选，不证明 SecondBrain 当前设置或同步行为。

## 物理位置候选

**首选候选：** Vault 根下 `.trash/secondbrain/<opaque-trash-id>/`，与 Obsidian 的 Vault 内 `.trash` 约定兼容，并在 SecondBrain 专属子目录中避免与 Obsidian 自身删除文件名冲突。目录中的 Markdown 原件与最小恢复清单应在同一文件系统，以支持原子移动；清单保留原始 collection、相对路径、原 ETag/内容摘要、附件引用与删除时间。

这只是路径形状，不含已核验的绝对路径。正式落地前 B 线必须确认该位置位于明确授权的 Notes 存储边界内、与 Capture Raw/Review/Knowledge/Journal/Private 不重叠，Core 对该目录具备单独且最小的访问权限，并能安全同卷移动。若无法证明同卷与目录权限，操作须失败关闭，不用 copy-then-delete 伪装原子性。若 Obsidian/Synology Drive 不同步该隐藏目录，需重新裁定兼容方案，不能静默改成可见的普通文件夹。

## 排除规则候选

1. Trash 不作为普通 Notes collection，不出现在普通目录列表、搜索、Organizer、Activity、Capture/Raw、知识检索或自动索引结果中；仅专用 Trash 页面/API 能枚举其 opaque id 与用户需要的恢复预览。
2. 仅允许 B 明确标记且已授权的普通 Markdown Notes。默认拒绝 `10-Review`、`20-Knowledge`、`40-Memory`、`50-Journal`、Capture Raw、Private、`.obsidian` 配置、整个目录、符号链接、未知 collection、共享附件及所有未分类路径。
3. `00-Inbox` 在 Capture Raw 与原生 Inbox Notes 的物理映射被正式分开之前整体排除；不能因目录名相同而推定同一权限或存储域。
4. Trash 内容不允许被 Capture、AI 学习/Organizer 或公开来源引用读取；拒绝和审计日志不得记录正文、附件字节或不必要的个人绝对路径。

## 删除、预览和恢复语义候选

- 删除是用户在 Web 对一个已读 note 明确确认的单项可恢复操作；提交必须携带当前 ETag/版本，服务端重验 `notes.delete` 等最终授权动作、collection、规范化相对路径、无符号链接、文件身份与版本。当前 API 没有该权限动作或端点；其命名与请求合同须经 B 线评审，不由前端自授权限。
- 移入 Trash 后保留 Markdown 原始字节与完整相对路径语义，不改 frontmatter、正文、日期或未知 Obsidian 语法。先展示目标与影响，成功以服务端回执为准；失败或结果不确定时保留原/回收项并提供状态查询，不宣称成功。
- 笔记移动不自动移动或删除附件。候选清单记录当时可见的相对附件引用；附件可能被其他笔记共享，未有可信引用计数和单独批准之前一律保留在原位置。
- 恢复先展示原 collection/路径及冲突状态。只能恢复至原路径；目标已存在、授权撤销、原目录失效、父路径变成符号链接或版本不匹配时返回冲突/拒绝并保持 Trash 项不变，不覆盖、不自动改名、不顺带创建未授权目录。需要替代路径时后续另作用户显式选择和合同。
- 本候选不包括永久清理、自动保留期、批量删除/恢复或附件垃圾回收。将来永久清理必须另有保留期限、影响预览、二次确认与恢复证据；当前无任何定时 purge。
- 并发删除/恢复使用稳定的 opaque Trash ID 与内容版本条件；同一请求重放应返回同一操作结果，冲突不得产生第二份数据。Core 若无法判定跨文件移动处于哪一阶段，应记录不含正文的 `recovery_required` 元数据并拒绝进一步修改。

## Web/Core 汇合与合成 Gate

Web 候选交互：只读列表 → 单项恢复预览 → 明确确认 → 显示真实服务端回执；恢复冲突保留原 Trash 项并提供重新读取。未取得 Core 冻结接口前，不在 Web 中造 production-like Mock 页或显示可执行按钮。

实现前置项：B 固定物理根及宿主/容器视图、最小 UID/权限、跨目录访问隔离、同文件系统证明、原子提交与故障恢复合同、授权动作、返回 DTO、ETag/幂等冲突语义。完成后仅在离线合成目录验证移动、完整字节、原路径恢复、目标冲突不覆盖、共享附件保留、401/403、符号链接拒绝、撤权、失败恢复和无搜索泄漏。真实 Obsidian 双向同步仍需单独获准并与本合成结果分开报告。
