# KN249 派生式 legacy-id 映射设计

日期：2026-11-03  
状态：已闭环（2026-11-03 实施与验收完成）

## 背景与目标

KN242 白名单使用修复前 chunk_id。KN244/246 通过 `_SPELL_LEVEL_LEGACY_ID_RANGES` 手写区间兼容旧 ID，但 DVG-012 从法术目录迁出阿底顿和仙人掌粹后，后续 ID 再次前移，产生 92 条误锚 WARN。

本次采用 KN249 登记的推荐方案：构建时根据「源文件 split 顺序 + 历史条目清单」派生当前 ID 到白名单 legacy-id 的映射，写入 state 文件并由 SpellProcessor 读取。删除手写区间，不重建或平移 KN242 白名单，不修改源 Markdown、通用 Pipeline 和其他类目。

## 方案比较

1. **派生式映射（采用）**：复用既有历史 state 和实际 split 结果，增删条目后自动重算；需要构建前预扫描一次源文件。
2. **补前移区间**：改动小，但新增条目容易误挂白名单，且每次增删仍需手补，不采用。
3. **重建白名单 ID**：一次性平移 556 条审批数据，对账成本高，仍会随未来 ID 变化失效，不采用。

## 现状验证

以 `spell_kn244_246_chunk_id_map_20261029.json` 的 `id_map + added` 为 4206 条历史序列，与当前 4202 条 chunks 按 doc_id 和标题序列对齐：

- 精确匹配 4202 条；
- 删除 4 条：`page_1365` 和 `page_669` 各一条仙人掌粹，`page_1494` 两条阿底顿；
- 无新增、替换、文档集合变化或重复标题导致的对齐歧义。

## 组件与数据流

新增 Spell 专用的 legacy-id 派生模块，职责分为两部分：

1. **纯序列对齐**：输入历史条目和当前条目，输出完整映射及 added/removed 对账；不依赖文件系统，便于单元测试。
2. **构建装配**：遍历 Spell 源文件，调用 SpellProcessor 同一份 `pre_normalize → normalize → promote → split_into_items` 逻辑生成当前 `(chunk_id, doc_id, title)` 序列，执行对齐并写 state。

SpellProcessor 在现有 `load_resources` 生命周期钩子中完成派生并加载映射，随后正常处理文件。通用 Pipeline 不增加钩子或类目特判。

历史序列的构造规则：

- `id_map` 行：历史当前 ID 为 `new_chunk_id`，白名单锚为 `old_chunk_id`，标题为 `new_title`；
- `added` 行：历史当前 ID 为 `chunk_id`，没有白名单锚，标题为 `title`；
- 每 doc 按固定宽度数字 chunk_id 排序，与 split 序号一致。

派生 state 使用确定性 JSON，包含 schema 版本、历史 state 路径、基线/当前数量、added/removed 清单及完整 `current_chunk_id → legacy_chunk_id|null` 映射。重复构建内容不变时不改文件内容。

## 对齐与安全规则

使用标准库 `difflib.SequenceMatcher(autojunk=False)` 按 doc 对齐标题序列：

- `equal`：继承历史行的 legacy-id；历史新增行及当前新增行均映射为 `null`；
- `delete`：记入 removed，不生成当前映射；
- `insert`：记入 added，当前 ID 显式映射为 `null`，防止同号新条目误命中白名单；
- `replace`：可能同时包含改名、错切和增删，无法安全自动判定，抛出含 doc_id、历史/当前 ID 与标题的错误，停止构建，不猜映射。
- 历史或当前 chunk_id 重复时失败闭锁；重复标题的新增、部分删除也无法确定身份，失败闭锁。全部同名条目删除且当前无同名时允许。
- 后处理生成的 Spell Index 作为当前条目纳入对账，避免误记删除；预扫描仅过滤重复的 `[split_drop]` 日志，真实处理日志不变。

映射查表规则：

- 当前 ID 在 state 中：返回对应 legacy-id 或 `None`；
- 未登记 ID：保持原 ID，兼容独立单元测试和临时构造的 chunk；
- 白名单、标题 override 和裁除集统一消费派生结果；`None` 不得查白名单或裁除集。

保留 F1 的 rescue 优先、白名单仅校验语义。派生映射只修正锚点，不直接修改 spell_level。

## 测试设计

先写失败测试，再实现：

1. 删除中间条目后，后续当前 ID 正确映射到原 legacy-id。
2. 新增条目显式映射为 `None`，即使同号存在于白名单也不得命中。
3. 历史新增条目继续保持无 legacy 锚。
4. 重复标题的部分增删和重复 chunk_id 抛出明确错误。
5. replace 抛出明确错误，不产生猜测映射。
6. 白名单及裁除集相关旧键全部唯一映射（已删除旧键除外），新增条目防误挂测试继续通过。
7. 真实构建输出不再出现 `KN242-F1 对账异常`，且 chunks 数量、正文、book/toc/source 与开工基线一致。
8. state 保存/加载往返一致、重复保存内容不变；预扫描不重复输出 `split_drop`。

交付前运行 Spell 统一 CICD 验证链、数据侧全量 pytest 和构建检查；Spell 链再复跑一次，产物与派生 state 均应内容一致。

## 实施结果

- 派生 state 为 `pf_data/phase1/docs/state/spell_kn249_legacy_id_map.json`：4202 条完整映射、34 条无历史锚、added 0、removed 4。
- `test_spell_title_cluster.py` 45 passed；全量 pytest 1792 passed（2 个既有弃用警告）。
- 两条 Spell CICD 链均通过，KN242-F1 WARN 从修复前实测 92 降为 0；既有 split_drop 保持单次 87。
- `build chunks.spell --force` 刷新指纹后，`build check` 14 artifact 全绿。
- 两次 chunks/state SHA-256 一致；修复前后 chunks 字节一致，证明 spell_level、正文、book/toc/source 零变化。

## 文档与回滚

修复完成后更新 KN249 状态、DVG-012 遗留说明、项目文档总索引及相关测试证据。回滚时恢复代码和派生 state 提交，再从既有源数据重建，不手工修改 chunks 或白名单值。
