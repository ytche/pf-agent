# KN014 修复方案：domains∩subdomains 交叉重复（正则排除）

> 状态：方案已确定，待统一实现  
> 关联 KN：[docs/已知问题记录.md §KN014](../已知问题记录.md)  
> 讨论时间：2026-07-29

---

## 1. 问题复核

KN014 原文定义：125 个 chunk 的子域名同时出现在 `domains` 和 `subdomains` 两个字段。

2026-07-29 复测确认：

- 有 subdomains 的 chunk 共 **125 个，100% 全部重复**；
- 实样 `spell_Spell CRB_0005`（魔石术）：
  - raw 环位行：`吟游诗人 1, …, 召唤师 1 领域 家园子域 1`
  - `domains=[家园子域1]`（错桶）、`subdomains=[家园子域1]`（对桶）
  - `spell_level` 已被 F3 正确剥离（无领域残留，无连带问题）；
- 当前数据中 `子领域` 变体 **0 例**（修复时防御性覆盖）；
- 与 KN012/KN013/KN016 无依赖，可独立实施。

---

## 2. 根因

`processors/spell.py` 两个提取函数各自独立匹配同一 raw 环位串：

```python
# L474 _extract_domains_from_level：交替里同时含 领域|子域 ← 病灶
r'([^\s,，、]+(?:领域|子域))\s*(\d+)'
# L483 _extract_subdomains_from_level：又独立匹配一遍 子域
r'([^\s,，、]+子域)\s*(\d+)'
```

子域条目被两个函数各匹配一次 → 同名单同时进两个字段。

---

## 3. 修复设计（方案 A：正则排除）

`processors/spell.py:474` 的 domains 正则改为：

```python
r'([^\s,，、]+(?<!子)领域)\s*(\d+)'
```

- `子域` 不以 `领域` 结尾 → 天然不匹配；
- `子领域` 变体被 `(?<!子)` lookbehind 防御性排除（当前数据 0 例）；
- `家园子域 1` 类条目只落入 subdomains，domains 不再重复。

**不选方案 B（差集）的理由**：不碰正则则 `_extract_domains_from_level` 单独看语义仍是错的（声称剥领域却含子域），且两函数保持耦合。

---

## 4. 结构不变量

1. **真实领域条目不丢失**：`善良领域 1` 等纯领域仍正常进 domains；
2. **subdomains 行为不变**：L483 不动；
3. **spell_level 不受影响**：F3 剥离逻辑不碰；
4. **negative test**：`家园子域`/`XX子领域` 不得出现在 domains。

---

## 5. 实现步骤（TDD）

1. **先写测试**（`test_spell_metadata_v0_3.py` 新增用例）：
   - 正例：`领域 家园子域 1` → domains=[]、subdomains=[家园子域1]；
   - 正例：`善良领域 1, 纯净子域 1` → domains=[善良领域1]、subdomains=[纯净子域1]；
   - 反例：`XX子领域 1` → 不进 domains；
   - 回归：纯领域条目不受影响；
2. 改 `processors/spell.py:474` 正则；
3. 重生成 chunks.jsonl，复测交集归零；
4. `pytest vectorizer/tests/ -q` 全绿。

---

## 6. 验证指标

| 指标 | 目标 |
|---|---|
| domains∩subdomains 交集非空 chunk | 125 → 0 |
| 有 domains 的 chunk 总数 | 305 → 约 180（125 个错桶条目移除后的真实值） |
| subdomains chunk 数 | 125 不变 |
| 回归测试 | `pytest vectorizer/tests/ -q` 全绿 |

---

## 7. 待办

- [ ] 按 §5 TDD 流程实现
- [ ] 重生成 chunks.jsonl 并复测
- [ ] 跑通 `pytest vectorizer/tests/ -q`
- [ ] 更新 KN014 状态与数据
- [ ] Git 提交
