# KN244/KN246 Spell Title Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 修复法术标题归一与条目边界，使 KN244 的碎片标题、KN246 的合并/丢失条目及其下游环级和派生清单按源文恢复。

**Architecture:** 在 `SpellFormat` 现有归一链中增加一个有字段上下文守卫的标题边界修复步骤，仍由现有 `split_into_items` 统一切分。保留 rescue 和 union 的现有安全闸，通过真实产物重跑恢复正确数据，不修改原始 Markdown 或 Java 检索逻辑。

**Tech Stack:** Python 3、pytest、现有 vectorizer pipeline/build/cicd、JSONL、Java/Maven 与 53 题 HTTP 评测。

**设计依据：** `docs/design/方案_KN244_KN246法术标题簇与切分缺陷统一修复_20261029.md`

---

### Task 1: 固化基线并编写标题族失败测试

**Files:**
- Create: `pf_data/phase1/vectorizer/tests/test_spell_title_cluster.py`
- Modify: `pf_data/phase1/vectorizer/cicd/verify.py:196-201`
- Read: `pf_data/phase1/vectorizer/formats/spell.py`
- Read: `pf_data/phase1/docs/已知问题记录.md` KN244/245/246

- [x] **Step 1: 快照当前产物并记录基线数量**

```bash
cd /Users/chezi/code/java/pf_agent/pf_data/phase1
mkdir -p /tmp/pf_spell_kn244_246_baseline/法术
cp vectorizer/output/法术/chunks.jsonl vectorizer/output/法术/index.json \
  vectorizer/output/法术/spell_lists.json vectorizer/output/法术/spell_lists_union.json \
  vectorizer/output/法术/spell_list_export_report.json \
  vectorizer/output/法术/spell_list_union_report.json \
  /tmp/pf_spell_kn244_246_baseline/法术/
python3 - <<'PY'
import json, re
from pathlib import Path
p = Path('vectorizer/output/法术/chunks.jsonl')
rows = [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()]
roman = [r['chunk_id'] for r in rows if re.fullmatch(r'[IVX]{1,6}', r.get('title', ''))]
print({'chunks': len(rows), 'roman_titles': len(roman), 'roman_ids': roman})
PY
```

预期：chunks 为当前基线数量，罗马标题清单写入终端；快照文件用于后续逐条 diff，不修改基线。

- [x] **Step 2: 写真实源形态的正向和负向测试**

创建测试文件，核心辅助函数与用例如下；每个用例直接调用完整 `normalize → promote → split_into_items` 链：

```python
from vectorizer.formats.spell import SpellFormat


def split_titles(raw):
    fmt = SpellFormat()
    promoted = fmt.promote(fmt.normalize(raw))
    return promoted, fmt.split_into_items(promoted)


def test_crossline_roman_title_keeps_full_name():
    raw = "【塑能】撕扯肢体\nI（Rend Body I）\n\n**等级**：异能者 5\n"
    _, items = split_titles(raw)
    assert [(x['name'], x['name_en']) for x in items] == [
        ('撕扯肢体 I', 'Rend Body I')
    ]


def test_nested_chinese_subschool_and_english_title():
    raw = "【咒法】藏密箱(召唤) (Secret\nCoffer)\n\n**等级**：女巫 2\n"
    _, items = split_titles(raw)
    assert [(x['name'], x['name_en']) for x in items] == [
        ('藏密箱', 'Secret Coffer')
    ]


def test_translator_prefix_does_not_drop_spell_title():
    raw = (
        "【变化】高等油腻术（Grease, Greater）\n**等级**：魔战士 5\n"
        "◎[隐藏武器]译文来自笨哈【变化】隐藏武器(Hide Weapon)\n"
        "**等级**：魔战士 1\n"
    )
    _, items = split_titles(raw)
    assert [x['name'] for x in items] == ['高等油腻术', '隐藏武器']


def test_chapter_intro_does_not_swallow_next_spell():
    raw = (
        "【死灵】暗影打击(UMBRAL STRIKE)\n**等级**：女巫 7\n"
        "你创造一支黑暗能量箭。**半影法术\n"
        "尽管许多人认为阴影与光亮不同。**◎[起舞于黯]译文引自[笨哈]"
        "【塑能】起舞于黯(Dancing Darkness)[黑暗]\n**等级**：女巫 1\n"
    )
    _, items = split_titles(raw)
    assert [x['name'] for x in items] == ['暗影打击', '起舞于黯']
    assert all(x['name'] != '半影法术' for x in items)


def test_crossline_english_with_descriptor_and_link():
    raw = "【塑能】弧焰击(Burning\nArc)[火][珂莱士人](http://example.test)\n**等级**：女巫 2\n"
    _, items = split_titles(raw)
    assert [(x['name'], x['name_en']) for x in items] == [
        ('弧焰击', 'Burning Arc')
    ]


def test_prose_roman_reference_is_not_a_new_title():
    raw = (
        "【塑能】撕扯肢体 II（Rend Body II）\n**等级**：异能者 6\n"
        "该法术的功能如同撕扯肢体 I 一般。\n"
    )
    _, items = split_titles(raw)
    assert [x['name'] for x in items] == ['撕扯肢体 II']


def test_pure_translator_note_is_still_removed():
    fmt = SpellFormat()
    assert fmt._strip_translator_notes('◎ 纯译者说明\n**火球术 (Fireball)**') == (
        '\n**火球术 (Fireball)**'
    )
```

- [x] **Step 3: 将新测试纳入 spell cicd 验收面**

在 `CATEGORIES['spell']['tests']` 的 `test_spell_metadata_v0_3.py` 后添加：

```python
            "test_spell_title_cluster.py",  # KN244/246 标题归一与条目边界
```

- [x] **Step 4: 运行测试并确认按预期失败**

```bash
cd /Users/chezi/code/java/pf_agent/pf_data/phase1
python3 -m pytest vectorizer/tests/test_spell_title_cluster.py -q
```

预期：前五个真实缺陷用例 FAIL；两个负向护栏用例 PASS。若失败原因不是目标标题/边界，先修正测试输入，使其与真实源形态一致。

### Task 2: 实现 formats 标题边界归一

**Files:**
- Modify: `pf_data/phase1/vectorizer/formats/spell.py:182-253,292-303,836-874`
- Test: `pf_data/phase1/vectorizer/tests/test_spell_title_cluster.py`

- [x] **Step 1: 修正译者注清理，保留带学派标记的标题**

将 `_strip_translator_notes` 的两步规则改为支持“引自/来自”，并禁止含 `【` 的行走纯注释整行删除：

```python
        text = re.sub(r'[◎○]\[[^\]]+\]译文(?:引自|来自)[^\]]*\]', '', text)
        text = re.sub(r'^[◎○]\s*(?!.*【).*$', '', text, flags=re.MULTILINE)
```

同步更新函数注释，使其与实现一致。

- [x] **Step 2: 在 `_pre_unify_text` 快照前修复标题边界**

新增 `_repair_school_title_boundaries`，依次完成：中文子学派移位、跨行罗马标题合并、章节粗体结束后的学派标题换行。实现采用以下三组定向替换，并在 `_strip_title_suffixes` 后、`_pre_unify_text` 赋值前调用：

```python
    def _repair_school_title_boundaries(self, text: str) -> str:
        text = re.sub(
            r'(【[^】]+】)([^（(\n]+?)[（(]([一-鿿][^）)]*)[）)]\s*[（(]([A-Za-z][^）)]*)[）)]',
            lambda m: f'{m.group(1)}({m.group(3)}){m.group(2)}({m.group(4)})',
            text,
        )
        text = re.sub(
            r'(【[^】]+】(?:\([^)]*\))?[^（(\n【]+?)\r?\n\s*([IVX]{1,6})\s*(?=[（(])',
            lambda m: f'{m.group(1).rstrip()} {m.group(2)}',
            text,
        )
        return re.sub(r'(?<=[。！？])\*\*(?=【[^】]+】)', '\n', text)
```

调用位置：

```python
        text = self._strip_title_suffixes(text)
        text = self._repair_school_title_boundaries(text)
        self._pre_unify_text = text
```

- [x] **Step 3: 扩展现有学派标题归一的合法后缀**

将 `_unify_school_bracket_titles` 两个正则中的“单个可选描述符”改为可重复、可带链接的标题后缀；保持中文名、英文名及行首/行内守卫不变：

```python
r'(?:[ \t]*\[[^]]*\](?:\([^)]*\))?)*'
```

该后缀替换原 `(?:[ \t]*\[[^]]*\])?`，不得放宽标题主体。

- [x] **Step 4: 运行聚焦测试和既有 spell 格式测试**

```bash
cd /Users/chezi/code/java/pf_agent/pf_data/phase1
python3 -m pytest vectorizer/tests/test_spell_title_cluster.py \
  vectorizer/tests/test_spell_metadata_v0_3.py \
  vectorizer/tests/test_spell_level_cleaning.py -q
```

预期：全部 PASS。若新增规则影响既有样本，按结构不变量修正实现，不删除或放宽既有负向断言。

### Task 3: 增加产物闸口并重跑 spell 全量链

**Files:**
- Modify: `pf_data/phase1/vectorizer/verify/verify_spells.py:82-100`
- Test: `pf_data/phase1/vectorizer/tests/test_spell_title_cluster.py`
- Generate: `pf_data/phase1/vectorizer/output/法术/*`

- [x] **Step 1: 增加标题碎片与关键条目验收**

在 `verify_spells` 的格式污染检查后增加：

```python
    roman_titles = [
        c.get('chunk_id', '?') for c in chunks
        if re.fullmatch(r'[IVX]{1,6}', c.get('title', '').strip())
    ]
    if roman_titles:
        print(f'❌ KN244 罗马碎片标题: {roman_titles}')
        ok = False
    required_titles = {'藏密箱', '弧焰击', '隐藏武器', '起舞于黯'}
    titles = {c.get('title', '') for c in chunks}
    missing_titles = sorted(required_titles - titles)
    if missing_titles:
        print(f'❌ KN246 关键条目未恢复: {missing_titles}')
        ok = False
```

同时在文件顶部 `import re`，并把验收说明更新为包含标题簇和关键条目。

- [x] **Step 2: 运行 spell 完整四步链**

```bash
cd /Users/chezi/code/java/pf_agent/pf_data/phase1
python3 -m vectorizer.cicd verify --category spell
```

预期：pytest、pipeline、verify_spells、数据不变量全部 PASS；若出现非预期标题、正文、book/toc 或总数变化，停止并逐项定性。

- [x] **Step 3: 与基线做全量结构化 diff 并生成 ID 映射**

用 Python 分别读取 `/tmp/pf_spell_kn244_246_baseline/法术/chunks.jsonl` 和新产物，按 `(doc_id, title, name_en)` 优先对齐，无法稳定对齐的条目列入人工清单；输出新增/删除/标题/text/spell_level/book/toc 变化，以及旧新 chunk_id 映射。不得只用行号强行配对顺移后的 chunk。

验收：所有变化都能归入 KN244/246 修复族；非目标 book/toc/source 变化为零，正文无未解释丢失。

- [x] **Step 4: 连续第二次运行并比较字节**

```bash
cd /Users/chezi/code/java/pf_agent/pf_data/phase1
cp vectorizer/output/法术/chunks.jsonl /tmp/pf_spell_kn244_246_first.jsonl
python3 -m vectorizer.cicd verify --category spell
cmp /tmp/pf_spell_kn244_246_first.jsonl vectorizer/output/法术/chunks.jsonl
```

预期：命令退出码 0，`cmp` 无输出。

### Task 4: 重导清单并核对两笔回流账

**Files:**
- Generate: `pf_data/phase1/vectorizer/output/法术/spell_lists*.json`
- Generate: `pf_data/phase1/vectorizer/output/法术/spell_list*_report.json`
- Modify only if measured baseline changes require it: `pf_data/phase1/vectorizer/cicd/verify.py:188-194`

- [x] **Step 1: 重导 official 与 union 清单**

```bash
cd /Users/chezi/code/java/pf_agent/pf_data/phase1
python3 -m vectorizer.build lists.spell --force
python3 -m vectorizer.build lists.spell_union --force
python3 -m vectorizer.build check
```

预期：三步退出码 0，`diff_unclassified=0`。

- [x] **Step 2: 核对 QA-K1、union 和 KN245 三份清单**

用 Python 检查：

- KN245 文档 QA-K2 表的 12 个旧 chunk 对应源条目均恢复为非空正确 spell_level；以修复后的 chunk_id/title 为键记录映射，不按旧行号查找。
- union 中纯罗马数字 derived 标题为 0，原报告“标题污染”38 条均有正确去向。
- KN245 垃圾串 12 条仍未自动回填；如标题修复改变了其证据，只输出裁定清单，不修改排除集。

- [x] **Step 3: 收紧空值棘轮到新实测**

仅在全部值回源核对通过后，将 `--max-spell-level-empty` 改为新实测值，并同步注释和 KN 记录。不得为了通过闸口提高门参数。

### Task 5: 全量回归、向量库和文档闭环

**Files:**
- Modify: `pf_data/phase1/docs/已知问题记录.md`
- Modify: `pf_data/phase1/docs/法术/原始Markdown非标准格式登记.md`
- Modify: `docs/数据一致性技术债务登记.md`
- Modify: `docs/项目文档总索引.md`
- Modify: `PROJECT_HANDOVER.md`

- [x] **Step 1: 跑数据侧全量测试和构建检查**

```bash
cd /Users/chezi/code/java/pf_agent/pf_data/phase1
python3 -m pytest vectorizer/tests/ -q
python3 -m vectorizer.build check
```

预期：全部 PASS；若构建指纹不一致，先确认所有受影响产物已由 manifest 对应步骤重建。

- [x] **Step 2: 重灌 spell 向量库并跑 Java 验证**

按 `docs/数据一致性技术债务登记.md` DVG-008 的既有内存模式临时实例流程备份并重灌 `~/.pf_agent/vector_store_spells.json`，核对新库条数、修复标题和 spell_level 与 chunks 一致。随后：

```bash
cd /Users/chezi/code/java/pf_agent/pf_agent/agent
mvn test
cd qa
python3 evaluate.py
```

预期：Maven 全绿；53 题相对本批开工基线无回退，既有 AKN-014 波动单列。不得用 Java metadata 重放代替 chunks 重灌。

- [x] **Step 3: 更新状态与格式登记**

- 关闭 KN244/246，记录最终数量、真实恢复条目、半影法术勘误、chunk_id 映射位置和验证证据。
- 更新 KN245/247 的 QA-K1 与 union 回流结果；KN245 垃圾串仍待裁定的保持开放。
- 将 SMF001～006 标为“容错已覆盖”，SMF007 保持“登记”。
- 新增 DVG 重灌记录，同步总索引和 PROJECT_HANDOVER。

- [x] **Step 4: 最终只读检查**

```bash
cd /Users/chezi/code/java/pf_agent
git diff --check
git status --short
```

预期：无空白错误；变更仅限本方案代码、测试、产物状态与文档。总结已执行命令和实测结果，未执行或失败项不得宣称闭环。
