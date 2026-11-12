# KN（数据侧已知）187/188 装备标题恢复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 恢复 page_220 内联标题后的 4 个条目及两个书聚合文件中的 3 个链接标题条目，修正字段串条与勘探漏计，并以装备完整 CICD、全量回归和向量库重灌证明闭环。

**Architecture:** 不修改源规则正文。书聚合文件在基类整行链接清理前仅剥离“链接包裹粗体标题”的链接壳，保留内部标题给现有 `_RE_STAR_TITLE_FULL`。CHM 大页复用现有 `_RE_CHM_TITLE`，在同一逻辑行含多个星壳标题或标题前粘有上一条字段时拆行，单条行首字段尾保持原行为。

**Tech Stack:** Python 3、pytest、既有 vectorizer CICD、Java SimpleVectorStore JSON 向量库重灌流程。

---

## 根因与不变量

- KN（数据侧已知）188：基类 `_strip_url_lines` 会先删除整行 Markdown 链接，导致整个 `[**标题**](url)` 在 `_normalize_custom` 前消失。
- KN（数据侧已知）187：`_RE_CHM_TITLE` 本身支持 `**中文 EN**灵光：…`，但 `_chm_inline_preprocess` 的负前瞻不拆字段尾标题；多条目粘连成一行时只有首个标题被识别。
- 真实复现：page_220 仅回生之戒被正确命名，巨魔皮革止血带等混入其字段；“尸体重构”被误切成独立条目。ISI 的醉蜂赐/胡蜂腑、HotD 的凝神口香糖没有正确条目归属。
- 不修改 `pf_rules_md_organized/**` 源文件。
- 普通正文链接继续删除；单条 CHM 标题字段尾保持原行为。
- 只有 ISI 的 `estimated_count` 从 2 改为 3；HotD 原本就是 2，不修改其预期。
- page_220 的旧 got=81 不得机械加成 85：恢复 4 条且消除“尸体重构”误切，最终值须由产物实测和逐文件归因确定。
- 实测同族恢复共影响 6 个 doc：page_208、page_220、page_228、page_233、ISI、HotD；装备 chunks 总数 5337→5342。除三个原始目标 doc 外，page_208 恢复龙骑兵定装弹，page_228 恢复回生之戒，page_233 归位巨魔皮革止血带字段并移除“尸体重构”误切。

### Task 1: 固化链接标题失败样本

**Files:**
- Modify: `pf_data/phase1/vectorizer/tests/test_equipment_format.py`
- Modify: `pf_data/phase1/vectorizer/formats/equipment.py`

- [x] **Step 1: 在文件中追加 KN（数据侧已知）188 的失败测试**

```python
class TestKN187188TitleRecovery:
    def test_linked_star_title_halfwidth_is_preserved(self):
        items = run("\n".join([
            "[**醉蜂赐(Calistria's kindness)**](https://example.test/item)",
            "价格：3gp；重量：无",
            "效果：每瓶可供服用30次。",
        ]))
        item = next(x for x in items if x.get("title") == "醉蜂赐")
        assert item["title_en"] == "Calistria's kindness"
        assert item["fields"]["price"] == "3gp"

    def test_linked_star_title_fullwidth_is_preserved(self):
        items = run("\n".join([
            "[**凝神口香糖（Focus chew）**](https://example.test/item)",
            "价格：40gp；重量：无",
            "效果：咀嚼后强化注意力。",
        ]))
        item = next(x for x in items if x.get("title") == "凝神口香糖")
        assert item["title_en"] == "Focus chew"
        assert item["fields"]["price"] == "40gp"

    def test_plain_text_link_is_still_removed(self):
        fmt = EquipmentFormat()
        normalized = fmt.normalize("正文[德洛人](https://example.test/race)继续")
        assert normalized == "正文继续"
```

- [x] **Step 2: 运行测试并确认因标题缺失而失败**

Run: `python3 -m pytest vectorizer/tests/test_equipment_format.py -k 'linked_star_title or plain_text_link' -q`

Expected: 两个 linked 用例 FAIL，plain link 用例 PASS；失败原因是找不到目标标题，不是测试语法错误。

- [x] **Step 3: 在通用链接删除前保留链接内粗体标题**

在 `_RE_INLINE_LINK` 附近新增：

```python
_RE_LINKED_STAR_TITLE = re.compile(
    r"\[(\*\*[^*\n]+[（(][^）)\n]+[）)]\*\*)\]\(https?://[^)]*\)")
```

在 `EquipmentFormat._strip_url_lines` 中先保留标题，再调用基类清理：

```python
text = _RE_LINKED_STAR_TITLE.sub(r"\1", text)
return super()._strip_url_lines(text)
```

- [x] **Step 4: 重跑测试并跑装备格式全文件**

Run: `python3 -m pytest vectorizer/tests/test_equipment_format.py -k 'linked_star_title or plain_text_link' -q`
Expected: 3 PASS。

Run: `python3 -m pytest vectorizer/tests/test_equipment_format.py -q`
Expected: 全绿。

- [x] **Step 5: 提交本阶段**

```bash
git add pf_data/phase1/vectorizer/formats/equipment.py pf_data/phase1/vectorizer/tests/test_equipment_format.py
git commit -m "fix(vectorizer): 保留装备链接内粗体标题"
```

### Task 2: 固化并修复多条目内联链

**Files:**
- Modify: `pf_data/phase1/vectorizer/tests/test_equipment_format.py`
- Modify: `pf_data/phase1/vectorizer/formats/equipment.py`

- [x] **Step 1: 在 `TestKN187188TitleRecovery` 中追加 KN（数据侧已知）187 失败测试与单条对照**

```python
    def test_multiple_inline_star_titles_with_field_tails_split(self):
        items = run("\n".join([
            "**回生之戒 RING OF RESUMPTION**灵光：中等咒法系",
            "制造成本：15400GP**银色魂索 SILVER SOUL CORD**灵光：中等防护系",
            "制造成本：12500GP",
        ]), source_name="page_220.md")
        by_title = {x.get("title"): x for x in items}
        assert by_title["回生之戒"]["fields"]["craft_cost"] == "15400GP"
        assert by_title["银色魂索"]["fields"]["craft_cost"] == "12500GP"

    def test_single_inline_star_title_with_field_tail_is_unchanged(self):
        items = run("\n".join([
            "**回生之戒 RING OF RESUMPTION**灵光：中等咒法系",
            "施法者等级：11",
            "制造成本：15400GP",
        ]), source_name="page_220.md")
        assert len(items) == 1
        assert items[0]["title"] == "回生之戒"
        assert items[0]["fields"]["craft_cost"] == "15400GP"
```

- [x] **Step 2: 运行并确认多条目用例失败、单条对照通过**

Run: `python3 -m pytest vectorizer/tests/test_equipment_format.py -k 'multiple_inline_star_titles or single_inline_star_title' -q`

Expected: multiple 用例因缺少银色魂索或字段串条 FAIL；single 用例 PASS。

- [x] **Step 3: 对多标题或非行首标题启用字段尾拆分**

在原 `_RE_CHM_INLINE_STAR` 后新增：

```python
_RE_CHM_INLINE_STAR_ANY = re.compile(
    r"\*\*([一-鿿]{2,12})\s+([A-Za-z][A-Za-z0-9 '’`\-,]*?)\*\*")
```

把 `_chm_inline_preprocess` 的 `while True` 搜索块替换为：

```python
            heads = list(_RE_CHM_INLINE_STAR_ANY.finditer(ln))
            if len(heads) < 2 and (not heads or heads[0].start() == 0):
                heads = list(_RE_CHM_INLINE_STAR.finditer(ln))
            for m in heads:
                if m.start() > pos:
                    segs.append(ln[pos:m.start()])
                segs.append(ln[m.start():m.end()])
                pos = m.end()
```

`pos = 0`、`segs` 和后续 `if segs` 保持原样。多条目链及标题前粘有上一条字段的形态会被拆开，单条行首字段尾仍走旧正则。

补充边界：当前条目已有 `craft_conditions`、缺少 `craft_cost`，且新行是 `名称（EN）制造成本：…` 时，将名称追加到当前制造条件并解析成本，不开新条目。对应测试使用巨魔皮革止血带→尸体重构真实形态，防止成本再次串条。重灌验收补充：裸字段续行不得吸收下一行 HTML 来源注释，避免 GP 成本被误判为英文断词。

- [x] **Step 4: 验证新增测试与装备格式全回归**

Run: `python3 -m pytest vectorizer/tests/test_equipment_format.py -k 'multiple_inline_star_titles or single_inline_star_title' -q`
Expected: 2 PASS。

Run: `python3 -m pytest vectorizer/tests/test_equipment_format.py -q`
Expected: 全绿。

- [x] **Step 5: 提交本阶段**

```bash
git add pf_data/phase1/vectorizer/formats/equipment.py pf_data/phase1/vectorizer/tests/test_equipment_format.py
git commit -m "fix(vectorizer): 拆回装备多条目内联标题链"
```

### Task 3: 补产物级闸口与勘探口径

**Files:**
- Modify: `pf_data/phase1/vectorizer/verify/verify_equipment.py`
- Modify: `pf_data/phase1/vectorizer/exploration/equipment/equipment_per_file.jsonl`

- [x] **Step 1: 保存修复前产物快照**

Run: `cp vectorizer/output/装备/chunks.jsonl /tmp/kn187_188_equipment_chunks_before.jsonl`
Expected: 文件存在且为当前基线产物。

- [x] **Step 2: 在 `check_item_qa` 添加三文件产物断言**

```python
    expected_titles = {
        "page_220": {"回生之戒", "银色魂索", "抒情竖琴", "巨魔皮革止血带", "独角兽邪角"},
        "内海诡道ISI_炼金物品": {"醉蜂赐", "胡蜂腑", "解毒剂"},
        "幽暗地域英雄HotD_物品": {"凝神口香糖", "穆之巨菌分泌物"},
    }
    for doc_id, expected in expected_titles.items():
        actual = {c.get("title") for c in chunks if c.get("doc_id") == doc_id}
        missing = sorted(expected - actual)
        if missing:
            ok = False
            issues.append(f"❌ {doc_id} 标题恢复缺口: {missing}")

    resumed = next(c for c in chunks
                   if c.get("doc_id") == "page_220" and c.get("title") == "回生之戒")
    resumed_cost = resumed.get("metadata", {}).get("craft_cost")
    if resumed_cost != "15400GP":
        ok = False
        issues.append(f"❌ 回生之戒 craft_cost 应 15400GP，实际 {resumed_cost!r}")
```

同时负向断言 page_220 不得再产生标题“尸体重构”。

- [x] **Step 3: 修正 ISI 勘探计数**

将 `内海诡道ISI_炼金物品.md` 行的 `estimated_count` 改为 3，`count_basis` 改为“3 个条目标题（醉蜂赐/胡蜂腑/解毒剂）”，并保留原 raw_example 供审计。HotD 行不改。

- [x] **Step 4: 跑装备完整链并取得 page_220 新 got**

Run: `python3 -m vectorizer.cicd verify --category equipment`

Expected: 目标标题与字段断言通过。若 page_220 的 est↔got 仍使用旧 81，则只在确认新增 4 条、误切“尸体重构”消失且无其他未归因变化后更新 `_EQUIP_EST_OVERRIDES`；预期为 84，若不是 84 必须停下逐条解释，不得直接改数放行。

- [x] **Step 5: 提交产物闸口与口径**

```bash
git add pf_data/phase1/vectorizer/verify/verify_equipment.py pf_data/phase1/vectorizer/exploration/equipment/equipment_per_file.jsonl
git commit -m "test(vectorizer): 锁定装备标题恢复产物"
```

### Task 4: 全量对账与可复现性

**Files:**
- Modify: `pf_data/phase1/vectorizer/state/build_state.json`（仅由统一构建命令更新）

- [x] **Step 1: 对修复前后 chunks 按 doc 做集合对账**

用 Python 逐行读取 `/tmp/kn187_188_equipment_chunks_before.jsonl` 和当前 `vectorizer/output/装备/chunks.jsonl`，输出新增/删除 chunk_id、变化 doc_id 和标题。Expected: 变化只允许归因于 page_208、page_220、page_228、page_233、ISI、HotD 这 6 个已核实的同族 doc；任何其他 doc 变化都停止并排查。

- [x] **Step 2: 跑数据侧全量测试**

Run: `python3 -m pytest vectorizer/tests -q`
Expected: 全绿；隔离环境的首轮 3 个缺产物失败已由全量构建消除。

- [x] **Step 3: 连续重建并比较装备产物指纹**

Run: `python3 -m vectorizer.build chunks.equipment --force` 两次，分别计算 `sha256`。Expected: 两次装备 chunks 内容指纹一致；构建状态通过统一命令刷新。

- [x] **Step 4: 跑全仓构建对账**

Run: `python3 -m vectorizer.build check`。若装备 chunks 变化导致 lists.equipment 输入/产物指纹漂移，先执行 `python3 -m vectorizer.build lists.equipment --force` 再复查。
Expected: 14 artifact 全绿。

- [x] **Step 5: 提交构建状态**

```bash
git add pf_data/phase1/vectorizer/state/build_state.json
git commit -m "chore(数据): 刷新装备标题恢复构建指纹"
```

### Task 5: 向量库清偿与文档销账

**Files:**
- Modify: `pf_data/phase1/docs/已知问题记录.md`
- Modify: `docs/数据一致性技术债务登记.md`
- Modify: `docs/项目文档总索引.md`
- Modify: `PROJECT_HANDOVER.md`
- Create: `docs/test-reports/测试报告_KN187_KN188装备标题恢复_20261104.md`

- [x] **Step 1: 重灌装备向量库**

备份本机 `~/.pf_agent/vector_store_equipment.json`，使用最新 `chunks.jsonl` 从临时实例完整导入，禁止 Java 侧字段补丁。核对导入条数与产物一致，并抽查回生之戒、醉蜂赐、凝神口香糖可检索且字段正确。

- [x] **Step 2: 更新 KN 与漂移债**

将 KN（数据侧已知）187/188 标记已修复，记录真实产物变化、测试数、CICD 结果和重灌证据；新增一条本次装备库重灌的 DVG（数据漂移债务）清偿记录。

- [x] **Step 3: 写测试报告并同步索引/交接**

报告必须包含根因、红绿证据、真实前后计数、逐文件 diff、完整命令和重灌结果；同步当前工作队列和 PROJECT_HANDOVER 头部。

- [x] **Step 4: 最终检查并提交**

Run: `git diff --check && git status --short`
Expected: 无空白错误，仅有本阶段文档。

```bash
git add pf_data/phase1/docs/已知问题记录.md docs/数据一致性技术债务登记.md docs/项目文档总索引.md PROJECT_HANDOVER.md docs/test-reports/测试报告_KN187_KN188装备标题恢复_20261104.md
git commit -m "docs(数据): KN187/188 装备标题恢复验收销账"
```
