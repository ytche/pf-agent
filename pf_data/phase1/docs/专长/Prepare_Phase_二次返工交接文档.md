# 专长模块 Prepare Phase 二次返工交接文档

> 撰写：k3（审计方），2026-07-31
> 执行：执行模型（整包交付）
> 返工依据：k3 对首轮返工交付（commit `871856e`）的复审报告——95% 复算通过，page_203 一条记录 5 处残留需更正
> 基线 commit：`d985523`（首轮返工交付文档提交），branch `feat/feat-module`

---

## 0. 当前状态一句话

首轮返工（R1~R5）经 k3 独立复算**几乎全部合格**：R1 四文件计数复算全对、R3 三文件逐字复核全对、MD5 普查独立复现一致、verify 8 阻断真实通过、总数 3624 正确。本轮只修 `per_file_B07.jsonl` 中 **page_203 一条记录的 5 处字段**（T1~T5），预估 10 分钟，改完重跑 merge + verify 即闭环。

**责任划分声明**：T3/T4 是 k3 首轮交接文档 §3.1 写错了行号（采信了审计子代理的错误口径），执行方照单执行反而改错——本轮是改回正确值，**不是执行方的过失**。T1/T2/T5 是执行方首轮收尾不细与新造假，需更正。

---

## 1. 返工项总览

| # | 内容 | 位置 | 责任 |
|---|---|---|---|
| T1 | 删除 notes 中伪造的 typo 结论句 | page_203 记录 `notes` | 执行方 |
| T2 | notes 旧计数口径 121→129（两处） | page_203 记录 `notes` | 执行方 |
| T3 | first_entry 行号 L165→**L311**（k3 交接写错，改回） | page_203 记录 `first_entry` | k3 |
| T4 | last_entry 行号 L2637→**L2783**（同上） | page_203 记录 `last_entry` | k3 |
| T5 | title_forms 复合标签项 raw_example 伪造替换 + 成员清单核实 | page_203 记录 `title_forms` | 执行方 |

**行号口径统一**：本文件所有行号 = **逻辑行**（`open(..., newline="")` 读入后按 `\r\n|\r|\n` 切分，与 `prepare_scan.py::read_logical_lines()` 同口径）。全文件逻辑行 2801 行（LF 物理行 2655 行，两者不要混用）。

---

## 2. T1：删除 notes 中的伪造 typo 结论句

**删除对象**（notes 第 ③ 点，整句删除）：

> ③索引表8处中文名typo（至尊打/狂傲技巧/进无可进/挂金勾/精通神选武器等），detail heading用规范名；

**删除依据**：k3 首轮审计已抽查其中 5 处全部失实——至尊打（索引 L51 = 正文 L1361）、狂傲技巧（索引 L104 = 正文 L643）、进无可进（索引 L102 = 正文 L549）、额外引导（L35 = L892）、挂金勾（L120 = L1685），索引表与正文名称完全一致，"typo 变体"全文不存在。首轮返工已从 `traps` 删除该伪造陷阱，但同一结论漏删在 `notes` 里。删除后 ③ 编号顺次重排或保留空缺均可，其余 ①②④⑤ 内容不动。

## 3. T2：notes 旧计数口径 121→129（两处）

1. "L302+正文121个heading" → "L302+正文**129**个heading"。
2. notes 末尾整句替换：

   - 原文："estimated_count按detail heading计121，与机检表格76+45+5+8+3=137（不去重）有差异，因为表格允许同条目出现在多个type子表"
   - 替换为："estimated_count=**129**（正文 heading 口径：125 常规标题 + 4 非常规标题——进无可进/狂傲技巧/额外引导/挂金勾）。索引表 137 数据行 = 128 唯一名 + 9 条复合类型专长各双列；表文一一对应，仅祝福之击 Blessed Striker（L402）为正文独有、索引表未列"

## 4. T3/T4：first/last_entry 行号改回正确值（k3 纠错）

k3 首轮交接文档 §3.1 称"首条目实际 L165 非 L311、索引表实际 L14-156 非 L14-301"——**此说法错误**。k3 复审实测（逻辑行口径）：

- 索引表区间 = **L14~L301**（143 个 `|` 起始行）——原勘探记录本来就对；
- 首个正文标题 = **L311** `**异变疖体**** Aberrant Tumor**`（L165 实为索引表内"战技突击"行，L305 为 `** **` 空加粗行）；
- 末条目标题 = **L2783** `**折箭伤爪**** Wounded Paw Gambit****（战斗，团队专长）**`。

**修改**：

- `first_entry` → `异变疖体（Aberrant Tumor） L311`
- `last_entry` → `折箭伤爪（Wounded Paw Gambit） L2783`

## 5. T5：title_forms 复合标签项更正

### 5.1 raw_example 伪造替换

当前值（**伪造，必须替换**）：`L564: **精通法术共享**** Improved Spell Sharing**（战斗，团队专长）`

- 实测 L564 是空行；精通法术共享真实标题在 **L1585** `**精通法术共享**** Improved Spell Sharing ****（团队专长）******`——单标签（团队专长），与"复合标签"形态不符，且该字符串在源文件任何行都不存在。
- `raw_example` 硬要求：**从源文件逐字复制，禁止手写还原、禁止美化**。

**替换为**（二选一，从源文件对应行逐字复制，禁止照抄本段文字应付）：

- `L677`：` **准线规避**** Coordinated Shot****（战斗，团队专长）****** ` 或
- `L1627`：` **精通换位**** Improved Swap Places****（战斗，团队专长）**** ****** `

复制后以 §7.2 的 grep 命令自检该字符串在源文件中真实存在。

### 5.2 成员清单与 count 核实

该项 note 目前列举 8 条，其中 2 条非复合（狂傲技巧（战斗专长）单标签、精通法术共享（团队专长）单标签），且漏了冲锋干扰 L807、折箭伤爪 L2783（均（战斗，团队专长））。k3 不预置终值，执行方用下述命令实测后更正 `count` 与成员清单：

```bash
cd /Users/chezi/code/java/pf_agent/pf_data/phase1
python3 - <<'EOF'
import re
t = open('pf_rules_md_organized/专长/page_203.md', encoding='utf-8', newline='').read()
ls = re.split(r'\r\n|\r|\n', t)
for i, l in enumerate(ls, 1):
    if re.search(r'（[^（）]*，[^（）]*专长）', l) and l.strip().startswith('**'):
        print(f"L{i}: {l.strip()[:90]}")
EOF
```

复合标签定义：`（）` 内含 `，` 的多类型组合（如（战斗，团队专长）/（战斗，派头专长）/（战斗，流派专长））。单标签（团队专长）/（战斗专长）不计入。

---

## 6. 红线（护栏）

1. **只改 `per_file_B07.jsonl` 的 page_203 一条记录**；其余 188 条记录、其余批次文件、源数据、全部脚本一律不动。
2. **T3/T4 照单改回**（L311/L2783 为 k3 实测终值）；T1/T2 按 §2/§3 文本执行；T5.2 以 §5.2 命令实测为准，但必须给出 count 与成员清单的实测依据。
3. **raw_example 必须逐字复制**：替换后用 §7.2 grep 自检，禁止凭记忆写。
4. 改完重跑 `merge_batches.py` + `verify_prepare.py`，8 项阻断必须仍全过；**条目总数 3624 不得变化**（本轮无计数改动）。
5. 裸模式 grep `121`、`typo`、`L165`、`L2637`、`L564` 确认 page_203 记录无旧值残留。
6. 单 commit 提交，message 建议：`fix(prepare): k3复审二次返工 T1~T5 — page_203 notes/行号/raw_example 更正`。

---

## 7. 验收口径与复跑入口

### 7.1 交付要求

二次返工交付说明（可极短，几行即可）：T1~T5 逐项给改前/改后 + §7.2 复算输出。可以就写在交付回复里，不必单独成文。

### 7.2 复算命令（k3 终审将原样重跑）

```bash
cd /Users/chezi/code/java/pf_agent/pf_data/phase1

# T1/T2：notes 残留检查（期望：typo 0 命中；121 在 page_203 记录中 0 命中）
python3 - <<'EOF'
import json
for l in open('vectorizer/exploration/专长/专长_per_file.jsonl', encoding='utf-8'):
    r = json.loads(l)
    if r['file'].endswith('page_203.md'):
        n = r['notes']
        print('typo 残留:', n.count('typo'), '| 121 残留:', n.count('121'))
        print('first:', r['first_entry'], '| last:', r['last_entry'])
EOF

# T3/T4：行号实测（期望 L311=异变疖体、L2783=折箭伤爪）
python3 - <<'EOF'
import re
t = open('pf_rules_md_organized/专长/page_203.md', encoding='utf-8', newline='').read()
ls = re.split(r'\r\n|\r|\n', t)
print('L311:', ls[310].strip()[:50])
print('L2783:', ls[2782].strip()[:50])
EOF

# T5：raw_example 逐字存在性自检（期望至少 1 命中）
python3 - <<'EOF'
import json, re
src = open('pf_rules_md_organized/专长/page_203.md', encoding='utf-8', newline='').read()
for l in open('vectorizer/exploration/专长/per_file_B07.jsonl', encoding='utf-8'):
    r = json.loads(l)
    if r['file'].endswith('page_203.md'):
        for tf in r['title_forms']:
            raw = tf.get('raw_example')
            raw = ''.join(raw) if isinstance(raw, list) else str(raw or '')
            body = re.sub(r'^L\d+[:\：]\s*', '', raw).strip()
            print(tf['pattern'][:30], '→ 源文件存在:', body in src if body else '空')
EOF

# 全局：verify + 总数不变
python3 vectorizer/exploration/专长/verify_prepare.py   # 期望 exit 0
python3 -c "
import json
print(sum(json.loads(l).get('estimated_count',0) for l in open('vectorizer/exploration/专长/专长_per_file.jsonl', encoding='utf-8')))"  # 期望 3624
```

### 7.3 k3 终审范围

只看 page_203 一条记录的 diff + 复跑 §7.2 全部命令，不再扩散。通过后 Prepare Phase 正式关闭，进 k3 汇总阶段（format_clusters / source_spec / test_seeds）。

---

## 8. 流程沉淀（执行方知悉）

1. **行号口径**：LF 物理行（2655）与裸 CR 逻辑行（2801）并存是本轮行号罗生门的根源。后续所有勘探/审计/交接文档引行号，统一逻辑行口径并可注明口径。
2. **notes 也是交付物**：伪造结论从 traps 删除时，必须同步全文 grep 清理 notes/dedup_note/count_basis 中的同根表述——首轮的教训是"traps 删了 notes 还留着"。
3. **raw_example 零手写**：该字段存在的意义就是给 formats/feat.py 提供逐字证据，任何"凭理解还原"都等于没有。
