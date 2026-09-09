# KN011 修复方案：MA 神话增强版本关联基础法术 chunk

> 状态：方案已确定，待统一实现  
> 关联 KN：[docs/已知问题记录.md §KN011](../已知问题记录.md)  
> 讨论时间：2026-07-29

---

## 1. 问题重新定性

MA（Mythic Adventures）来源书 `page_625.md` 共生成 263 个 spell chunk：

| 类型 | 数量 | 说明 |
|---|---|---|
| 规则说明 + 列表前言 | 1 | `spell_page_625_0000`，3280 字符，包含神话法术机制说明和索引表格 |
| 完整规则块新法术 | 9 | `spell_page_625_0001` ~ `0009`，含完整 `**学派/等级/施法时间...**` 字段 |
| 现有法术的神话增强摘要 | 253 | `spell_page_625_0010` 以后，无学派/等级字段，只描述基础法术在神话规则下的增强效果 |

此前 KN011 将 253 个增强摘要误判为"章节说明页"。经复核，这些 chunk **是有价值的内容**，每个都对应一个已有基础法术（通常在 CRB/APG/UM 等规则书中）。因此修复方向不是"删除"，而是**为它们建立指向基础版本 chunk 的链接**。

---

## 2. 目标

为 MA 中 253 个"简写型神话增强" chunk 补充字段，指向其普通版本法术 chunk 的 `chunk_id`，使 Agent 回答"神话XX术"时能联动到基础法术的完整字段。

---

## 3. 匹配策略（A1：单选，CRB 优先）

### 3.1 匹配键

| 优先级 | 字段 | 说明 |
|---|---|---|
| P1 | English name（别名） | 最稳定，如 `Bane` → 找 `aliases` 含 `Bane` 的 chunk |
| P2 | 中文 title | 辅助验证，如 `绝望术` |
| P3 | 排除 self | 不指向 MA 自身 chunk |

### 3.2 候选池

所有 `category == 'spell'` 且 `book_abbreviation != 'MA'` 的 chunk。

### 3.3 多匹配处理

同一个法术可能在多本规则书出现（如 CRB 和 UM 都有 `绝望术`）。策略：

- 优先返回 `book_abbreviation == 'CRB'` 的 chunk_id；
- 没有 CRB 版本时，返回第一个匹配；
- 仍未匹配则 `base_spell_chunk_id = null`，并记录到未匹配清单。

### 3.4 为什么不使用多来源数组

- 语义简单，下游 Agent 处理成本低；
- 需要多来源时可后续扩展为 `base_spell_chunk_ids` 数组，不破坏当前字段。

---

## 4. 字段设计

新增 chunk 顶层字段：

| 字段名 | 类型 | 示例 | 说明 |
|---|---|---|---|
| `base_spell_chunk_id` | string | `"spell_Spell CRB_0176"` | 基础版本法术 chunk_id |
| `base_spell_title` | string | `"绝望术"` | 冗余，便于人工调试 |
| `base_spell_book` | string | `"CRB"` | 冗余，标明基础版本来源书 |

放在 chunk **顶层** 而非 `metadata` 或 `extra`，因为这是跨 chunk 关系，不是法术字段元数据。

---

## 5. 实现位置（C1：独立后处理脚本）

新增 `pf_data/phase1/link_mythic_base_spells.py`：

1. 读取 `vectorizer/output/法术/chunks.jsonl`；
2. 构建 `english_name → chunk_id` 索引（CRB 优先去重）；
3. 遍历 MA 简写 chunk（判定：无 `**学派：**` + 无 `**等级：**`）；
4. 提取 English name，查找 base chunk_id；
5. 写入 `base_spell_chunk_id` / `base_spell_title` / `base_spell_book`；
6. 输出新的 `chunks.jsonl`（默认覆盖，或输出到 `--output` 指定路径）；
7. 打印匹配率统计和未匹配清单。

### 5.1 为什么不集成到 spell.py pipeline

- 这是**数据关系补全**，不是格式解析问题；
- 不污染核心解析器；
- 可独立运行、独立测试、独立回滚；
- 符合项目已有的分析/后处理脚本风格。

---

## 6. 验证指标（D）

跑完后确认：

| 指标 | 目标 |
|---|---|
| 253 个 MA 简写 chunk 成功匹配基础版本 | ≥ 95%（约 240+） |
| 9 个 MA 完整新法术不添加 base_id | 100%（它们没有普通版本） |
| 无 base_id 指向 MA 自身 | 100% |
| 匹配到的 base chunk 真实存在 | 100% |
| 测试通过 | `pytest vectorizer/tests/ -q` 189 passed |

---

## 7. 边界情况

| 情况 | 处理 |
|---|---|
| 多本规则书有同名基础法术 | 优先 CRB；无 CRB 取第一个 |
| 中文 title 相同但 English name 不同 | 以 English name 为准 |
| English name 相同但中文 title 不同 | 视为同一法术，取第一个匹配 |
| 未找到基础版本 | `base_spell_chunk_id = null`，写入未匹配日志 |
| 合并污染 chunk（如 `spell_page_625_0013` 含 3 个法术） | 按 chunk 主 title 匹配；若主 title 无基础版本，尝试从 text 中提取其他 title 分别匹配 |
| 9 个完整新法术（晋升之术等） | 跳过，不添加 base_id |

---

## 8. 后续可扩展

- 若其他规则书也出现"增强/变体版本需要关联基础版本"的场景，可将此脚本泛化为 `link_variant_base_spells.py`；
- 若 Agent 需要多来源基础版本，可将 `base_spell_chunk_id` 升级为 `base_spell_chunk_ids: string[]`。

---

## 9. 待办

- [ ] 实现 `link_mythic_base_spells.py`
- [ ] 运行并验证匹配率 ≥ 95%
- [ ] 跑通 `pytest vectorizer/tests/ -q`
- [ ] 更新 `docs/MA_格式集群报告.md` 或相关文档
- [ ] Git 提交
