# KN015 修复方案：page_1365 无标题 chunk 三类机制治理

> 状态：方案已确定，待统一实现（**源数据类修复，应先于解析器类 KN 落地**）  
> 关联 KN：[docs/已知问题记录.md §KN015](../已知问题记录.md)  
> 讨论时间：2026-07-29

---

## 1. 问题重新定性

KN015 原文定义："page_1365 源数据 5 个法术中文名丢失只剩英文括号名"。

2026-07-29 复测：5 个无标题 chunk 实为 **3 种机制**，原定性只对 2 个成立：

| chunk | 内容 | 真实机制 | 原定性 |
|---|---|---|---|
| `spell_page_1365_0221` | Shared Suffering（PZO9450 秽邪勇士，死灵[邪恶]） | **M-a 真·中文名缺失** | ✅ 符合 |
| `spell_page_1365_0222` | Wracking Ray（同书，死灵[邪恶、痛苦]） | **M-a 真·中文名缺失** | ✅ 符合 |
| `spell_page_1365_0327` | Secret Sign Spells | **M-b 分组标题误产 chunk** | ❌ 不符 |
| `spell_page_1365_0337` | Black Market Magic | **M-b 分组标题误产 chunk** | ❌ 不符 |
| `spell_page_1365_0179` | magic jar | **M-c 正文引用误判标题** | ❌ 不符 |

**重要修正**：KN015 原文的修复方向"从原始 HTML 找回中文名"**不成立**——实查 `~/.openclaw/workspace/pf_rules/page_1365.html`，`【死灵】 (Shared Suffering)[邪恶]` 中中文名本来就被译者留空。只能拟定补录。

### 1.1 M-b 实样（源数据中有中文名，是分组标题不是法术）

```markdown
秘密标记法术****(Secret 
Sign Spells)

****以下的法术利于保存秘密**
```

normalize 把 `中文****(English)` 包装成标题并拆出 chunk，中文名在拆分过程中丢失。

### 1.2 M-c 实样（正文法术名引用被误判为标题）

```markdown
你可以如同使用***魔魂壶******(magic 
jar) ***一般，占据一个动物的身体。
```

星号簇破损（`******`），normalize 把 `(magic jar)` 包装成空中文名标题，拆出一个**只有标题没有正文**的 chunk。

---

## 2. 修复设计（全部改源数据，不改脚本）

目标文件：`pf_rules_md_organized/法术/玩家伴侣/page_1365.md`（管线输入为 `pf_rules_md_organized/法术`；根目录重复副本 `pf_rules_md_organized/page_1365.md` 按遗留问题另行处理，本次不同步）。

### 2.1 M-a：2 个真·中文名缺失 → 补录中文名

```markdown
# 修改前
【死灵】 (Shared 
Suffering)[邪恶]

# 修改后（译名待定，实施时拍板）
【死灵】<中文名待定> (Shared 
Suffering)[邪恶]
```

候选译名（2026-07-29 讨论，用户决定**暂不定译名**，实施时确认）：

| 法术 | 候选 |
|---|---|
| Shared Suffering | 「共担苦难」/「共同受苦」（网络检索到未证实的「共受血祭」，语义存疑） |
| Wracking Ray | 「折磨射线」（与衰弱射线/力竭射线同构） |

### 2.2 M-b：2 个分组标题 → 改为 `####` 标题行（用户已拍板）

```markdown
# 修改前
秘密标记法术****(Secret 
Sign Spells)

****以下的法术利于保存秘密**

# 修改后
#### 秘密标记法术 (Secret Sign Spells)

**以下的法术利于保存秘密**
```

`split_into_items` 以 `## `/`### ` 为章节边界（`formats/spell.py` L1207），分组标题改为 `####` 后不再产 chunk，简介文本保留在源文件中。黑市魔法 (Black Market Magic) 同法处理。

### 2.3 M-c：1 个引用误判 → 清理星号簇

```markdown
# 修改前
***魔魂壶******(magic 
jar) ***

# 修改后
***魔魂壶 (magic jar)***
```

修复后该引用留在原法术（高等分享皮肤）正文中，不再被拆成独立 chunk。

### 2.4 verify_spells.py 白名单

3 类修复落地后，`KNOWN_UNTITLED_WHITELIST` 中 5 个 chunk_id 全部移除（chunk_id 会因索引位移变化，以重生成后的复测为准）。

---

## 3. 结构不变量与实施顺序

**本 KN 是唯一会改变 chunk 总数的 KN**：

- chunk 总数 **-3**：0179（引用）、0327/0337（分组标题）消失；
- 位移点之后的 chunk_id 全部变化；
- **因此实施顺序：源数据类修复（KN015、KN016 源数据部分）→ 解析器类修复（KN012/KN013/KN014）→ 一次重生成 → 统一复测所有 KN 指标**。KN012/KN013 方案文档中的基线数字均以当前 chunks.jsonl 为准，最终复测时需重新校准。

不变量：

1. 2 个真法术（M-a）补名后 title 正确、字段解析不受影响；
2. 分组标题下挂的法术 chunk 不丢失（密语术、心灵手巧等）；
3. 高等分享皮肤 chunk 正文完整保留魔魂壶引用；
4. negative test：0179/0327/0337 三个 chunk_id 在新 chunks.jsonl 中不存在。

---

## 4. 验证指标

| 指标 | 目标 |
|---|---|
| 无标题 chunk | 5 → 0 |
| `KNOWN_UNTITLED_WHITELIST` | 清空 |
| chunk 总数 | 4137 → 4134（-3） |
| verify_spells.py 无标题检查 | ✅ 无白名单豁免也通过 |
| 回归测试 | `pytest vectorizer/tests/ -q` 全绿 |

---

## 5. 关联 KN

- **KN012**：page_1365 同时是行内粘连最大来源（276 个），两个 KN 都在统一实施序列中；
- **KN016**：page_1365 编译帖的合并污染同属源数据整理问题；
- **根目录重复副本清理**（PROJECT_HANDOVER 遗留 #1）：`pf_rules_md_organized/page_1365.md` 与 organized 副本的关系需一并处理。

---

## 6. 待办

- [ ] 实施时确认 Shared Suffering / Wracking Ray 译名
- [ ] 改 `法术/玩家伴侣/page_1365.md` 三处源数据
- [ ] 重生成 chunks.jsonl，复测 §4 指标
- [ ] 移除 `KNOWN_UNTITLED_WHITELIST` 5 个条目
- [ ] 跑通 `pytest vectorizer/tests/ -q`
- [ ] 更新 KN015 状态与数据
- [ ] Git 提交
