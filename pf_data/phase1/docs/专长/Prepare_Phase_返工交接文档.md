# 专长模块 Prepare Phase 返工交接文档

> 撰写：k3（审计方），2026-07-30
> 执行：执行模型（deepseek-v4-pro / minimax3，整包交付，护栏内自主决策）
> 返工依据：k3 对 Prepare Phase 成果的交付审计（机械全量复算 + 12 文件语义抽样复核）
> 基线 commit：`0bbffe9`（Prepare Phase 语义勘探完成），branch `feat/feat-module`

---

## 0. 当前状态一句话

Prepare Phase **主体通过**：189 文件全覆盖、verify 8 项阻断真实通过（k3 重跑字节级一致）、doc_role 五分类抽样 12/12 全对、格式簇与 raw_example 陷阱普查可用。本轮返工为**定点更正**：4 个文件计数失真（含 2 个 ❌ 级漏数）、2 个文件陷阱编造/错误、9 个小文件补抽、全库 MD5 重复普查。**只改 `vectorizer/exploration/专长/` 下的勘探记录与派生产物，不动源数据、不动校验脚本、不动机检产出。**

k3 已把需要判断的内容全部预置（修正终值、陷阱增删清单、补抽方法、普查脚本），执行方**照单更正 + 复算核对**即可；仅 R3 补抽的数字以执行方实测为准（k3 未预置）。

---

## 1. 返工项总览

| # | 内容 | 改动文件 | 阻断性 | 预估 |
|---|---|---|---|---|
| R1 | 4 个文件 estimated_count 及关联字段修正 | `per_file_B07/B08/B11/B17.jsonl` | 🔴 阻断 | 小 |
| R2 | 伪造/错误陷阱更正与漏报补登（5 个文件 / 6 条记录） | `per_file_B03/B04/B07/B11/B15/B17.jsonl` | 🔴 阻断 | 中 |
| R3 | 真风险象限 9 个小文件补抽复读 | 对应批次 jsonl | 🔴 阻断 | 中 |
| R4 | 全库 MD5 重复普查 + 造物孪生标注 | 新 `md5_dupes.md` + B03/B15 两条记录 | 🟡 非阻断（source_spec 输入） | 小 |
| R5 | 收尾：重跑 merge + verify + 更新 prepare_phase_report.md | `专长_per_file.jsonl`、`prepare_verify_report.md`、`prepare_phase_report.md` | 🔴 阻断 | 小 |

审计背景数据（备查）：12 个抽样文件判定 8✅ / 2⚠️ / 2❌；135 个对账偏差按象限分解 = 63 机检盲区（无需处理）+ 1 overview + 71 双方>0 分歧（本次返工覆盖其中的高风险子集）。

---

## 2. R1：4 个文件计数修正（k3 预置终值，照单执行）

修正 `estimated_count`、`count_basis`、`field_labels_seen`、`feat_type_tags`（如涉及）。**这些数字是 k3 审计逐条实测的终值**；执行方复算不符时列异议单独讨论，不得静默改回。

### 2.1 `专长/内海种族ISR_专长.md`（B11）：34 → **50**

- 实测依据：50 个条目标题行逐条核实；字段闭合 = `**专长效果**` 恰 50 行 / `**先决条件**` 恰 49 行（唯一例外：刀剑共鸣 L71-77 无先决条件行，属合法缺失）。
- `field_labels_seen` 更正：先决条件 **49**、专长效果 **50**、通常状况 **2**（L18/L175）、特殊说明 **3**（L150/160/238）。
- `count_basis` 重写为："逐条清点 50 个条目标题；字段闭合验证（专长效果 50 / 先决条件 49，刀剑共鸣合法无先决）；44 条带〔战斗〕/〔团队〕标签 + 6 条无标签 = 50"。
- first/last_entry 不变（外星心智通路 / 阴影换位，已核实）。

### 2.2 `专长/流派专长一览/page_1564.md`（B17）：200 → **272**

- 实测依据：**89 个流派家族**（非记录所称"约 60 个"）= 88 家族 ×3 条 + 完美流家族 7 条 + 单条武道专家 = 272。三种计数方法收敛：标题模式 245 + 括号后断行 21 + 无加粗半角括号 6 = 272；全部 272 标题下方 12 行内均有 `先决条件`；全文 283 处 `先决条件` 无孤立（余 11 处为正文引用）。
- `count_basis` 重写为上述家族算术。
- `field_labels_seen` 更正：先决条件提及 **283**、加粗 `**来源**` **252**（另有 ~34 处无加粗来源行，含 20 个战策块）、加粗 `**专长效果**` **223**、加粗 `**好处**` **10**。
- first/last_entry 不变（奥多里决斗流 / 飞龙翼击，已核实）。

### 2.3 `专长/page_203.md`（B07）：121 → **129**

- 实测依据：125 条常规 `**中文**** English**` 标题 + 4 条非常规标题 = 129：
  - 进无可进 Counter Reflexes（L549-550，英文名断行）
  - 狂傲技巧（L643，**标题无英文名**，仅 `**狂傲技巧（战斗专长）**`）
  - 额外引导 Extra Channel（L892-893，断行）
  - 挂金勾 Kick Up（L1685-1686，断行）
- 字段闭合：`**专长效果：**` 恰 129 行；`**先决条件：**` 恰 126 行（3 条合法无先决：冲锋干扰 L661、迎身上前 L1592、坚定常识 L2421）；`**特殊情况：**` 27 行。
- `field_labels_seen` 相应更正为 126/129/27。
- first/last_entry 不变（异变疖体 L165 / 折箭伤爪 L2637）。

### 2.4 `专长/page_321.md`（B08）：89 → **86**

- 实测依据：85 个 `**先决条件**` 条块 + 1 条无先决条件条目（火炬手 Torch Bearer L656-662，仅 `**效果：**` + `**正常情况：**`）= 86。"先决条件"总出现 86 次中 L257 为效果文本内引用（干扰项）。
- `field_labels_seen` 更正：先决条件 **85**、效果 **86**。
- `feat_type_tags` 更正为 `["战斗", "重击", "Combat"]`——原记录的"团队/流派/故事"在本文件零命中，删除。
- `count_basis` 末条覆盖范围更正为 L687（其先决条件延至 L693）。

**R1 对总数的净影响**：+16 +72 +8 −3 = **+93**（3523 → 3616，若 R3 有新修正再累加）。

---

## 3. R2：伪造/错误陷阱更正与漏报补登（照单执行）

### 3.1 `专长/page_203.md`（B07）：删 2 条伪造陷阱 + 补 2 条真陷阱

**删除**（k3 抽查实证系凭空捏造）：

1. "索引表 8 处中文名 typo"——抽查 5 处全假：至尊打/狂傲技巧/进无可进/额外引导/挂金勾在索引表与正文中名称完全一致，所称 typo 变体全文不存在。
2. "字段标签挤同一行"（声称 L227 `**先决条件**：...**专长效果**：...`）——L227 是空行，全文不存在任何同时含两标签的行。

**补登**：

```json
{"kind": "断行英文名", "example_line": "L549-550/L892-893/L1685-1686", "risk": "3 条条目英文名断行导致标题锚定失败，是原计数漏数主因"}
{"kind": "其他：标题无英文名", "example_line": "L643", "risk": "**狂傲技巧（战斗专长）** 无英文名，按（English）锚定标题的正则必漏"}
```

**同步更正**：记录中全部行号引用（原行号体系与实际文件整体偏移：首条目实际 L165 非 L311、索引表实际 L14-156 非 L14-301）；删除 dedup 举例"精通法术共享同时归两个子表"（该条目仅单标签、表中出现 1 次，不实）。

### 3.2 `专长/page_196.md`（B04，单文件批次，勿改到 B05）：count_basis 推导与 dedup_note 更正

1. `count_basis` 更正：实测正文有 **170 个标题结构**（166 顶级 + 4 化兽态子选项），非记录所称"166 heading − 4 子选项 = 162"。estimated_count=166 取自表格侧（166 数据行），结论正确但归因须改正。
2. `dedup_note` 中"正文按 162 顶级专长分 chunk"的建议**必须改为 166**——按 162 会丢 4 条删除线 hero point 专长（碧血丹心 L319、工艺协作 L506、洪福齐天 L1442、好运连连 L1835）。
3. `title_forms` 补第 6 形态：

```json
{"pattern": "**~~中文名（~~****~~English\\nName~~****~~**，删除线标题", "count": 4, "raw_example": ["L319: **~~碧血丹心（~~****~~Blood ", "（跨行续）"], "note": "现有 5 种 pattern 全部匹配不到此类，删失线 4 条"}
```

4. 补登 2 条陷阱：

```json
{"kind": "其他：引用块伪装子选项", "example_line": "L1720-1721/L2688-2689", "risk": "【特性速查】**灵敏嗅觉（Scent, Ex）**：… 形态与化兽态子选项完全相同，按 ）**： 数子选项会得 6 而非 4"}
{"kind": "其他：表文译名不一致", "example_line": "奥法天赋/奥术天赋、额外科研发现/额外发现、迅捷协助/迅捷援助", "risk": "表格与正文 166 对中有 3 对译名不一致，用中文名做表↔文 join key 会失配"}
```

### 3.3 `专长/流派专长一览/page_1564.md`（B17）：补 5 条漏记

```json
{"kind": "其他：英文在括号后断行", "example_line": "L501/L607/L1222/L1467/L1811/L3406/L3508/L3576", "risk": "**地趟流****（战斗，流派）（Earth ⏎ Child Style)** 形态，约 21 条，标题正则盲区"}
{"kind": "其他：无加粗半角括号标题", "example_line": "L1965/L1988/L2040/L2064/L3044/L3068", "risk": "Wisdom(战斗) 形态 6 条，加粗锚定必漏"}
{"kind": "其他：标题与来源同行", "example_line": "L2202", "risk": "条目边界锚定干扰"}
{"kind": "其他：条目无来源行", "example_line": "L913/L923/L2213/L2223/L2824/L2834", "risk": "按来源行切分会漏这 6 条"}
{"kind": "其他：战策伪来源块", "example_line": "L352-406", "risk": "20 个战策注解块自带 **来源** 掉链子Unchained 行（L404 甚至加粗），足以骗过按来源行切分的解析器；计数时必须排除"}
```

（若原记录已有"战策非条目块"陷阱，则将其 risk 强化为上述表述，不重复添加。）

### 3.4 `专长/内海种族ISR_专长.md`（B11）：补 3 条漏记

```json
{"kind": "其他：标题闭合**缺失", "example_line": "L116/L232", "risk": "**弑亲者（Kinslayer） 标题右边界丢失，** 被斜体标记吸收，跨行正则也救不回，需特判"}
{"kind": "其他：正文英文断词", "example_line": "L10-11/L24-26", "risk": "机检 broken_en=86，正文英文词系统性断裂（circumstance ⏎ bonus），切断内联字段正则"}
{"kind": "其他：6条无类型标签", "example_line": "L65/L154/L168/L232/L344/L369", "risk": "feat_type_tags 暗示条条有标签，实际 6 条裸标题，按〔〕提取会漏"}
```

同时修正原"断行英文名"陷阱的表述："每个条目的英文名都断成两行"夸大——L93 协调轰击、L363 三角学为单行完整标题，改为"多数条目"。

### 3.5 造物专长一览（B03 顶层 + B15 `专长/` 双记录）：更正 + 陷阱互补

**B03 记录（顶层，26）**：

1. `estimated_count` 26 → **28**（真实口径：索引 28 条目占 42 物理行 + 正文 28 块/27 独立 + 制造权杖仅索引 L12）。
2. `count_basis` 重写：删除"索引 43 行含 43 条目 + 详细 20 条去重≈26"（折行误计、算术不自洽），改为上述真实口径。
3. 删除线计数更正：8 块/7 独立（L65/104/184/216/234/249/322/494），非 5 条。

**B03 与 B15 两条记录均补登**：

```json
{"kind": "重复条目", "example_line": "L184-193 vs L216-225", "risk": "制造法杖正文块文件内逐字重复出现两次，朴素解析产重复向量"}
{"kind": "其他：索引有而正文缺", "example_line": "L12", "risk": "制造权杖（Craft Rod）仅索引出现、全文无正文块，表↔文对账会判缺失"}
{"kind": "其他：非专长物品混入", "example_line": "L150-159", "risk": "泥怪瓮为魔法物品非专长，按条目提取会误纳"}
```

**B15 记录**另修正：非条目表格行号 L19-29 → **L137-146**；`count_basis` 删除"全文均有详细描述"（制造权杖无正文）；`field_labels_seen` 备注 MHH 条目用"效果："、创生工艺用"好处："（L465）。

---

## 4. R3：真风险象限 9 个小文件补抽（执行方实测，k3 未预置数字）

"勘探 < 机检基准"象限中未经复核的 9 个文件（位面谐律、治疗者手册、ISR 已由 k3 审计复核，不在此列）：

| 文件 | 批 | 现 est | 机检基准 |
|---|---|---|---|
| `专长13.md` | B01 | 8 | 12 |
| `专长23.md` | B01 | 1 | 7 |
| `专长31.md` | B02 | 1 | 3 |
| `专长35.md` | B02 | 1 | 2 |
| `专长37.md` | B02 | 1 | 3 |
| `专长/元素血脉BotE_专长.md` | B10 | 1 | 6 |
| `专长/第一世界TFWRotF_专长.md` | B15 | 1 | 2 |
| `专长/荒野源始WO_专长.md` | B15 | 8 | 12 |
| `专长/CRB 核心规则手册/page_950.md` | B17 | 1 | 4 |

**方法**：均为小文件，全文通读（裸 CR 文件用 `open(..., newline="")` 读逻辑行），按"名称+效果描述 = 1 条目"独立逐条计数。**机检>勘探不等于漏数**（机检会把散文标题/字段标签/双锚点计数，治疗者手册实证如此），以你实际读到的条目为准。

**交付要求**：逐文件给出独立计数 + `count_basis`（逐条名称清单，空口数字视为未交付）；偏差属实则修正 `estimated_count`/`count_basis`/`first_entry`/`last_entry`/`field_labels_seen`，并补登导致原计数失真的陷阱；勘探原值正确则只更新 `count_basis` 注明"k3 审计补抽复核：原值正确 + 复核依据"。

---

## 5. R4：全库 MD5 重复普查（脚本级，产出供 source_spec）

已知实锤：`造物专长一览.md`（顶层）与 `专长/造物专长一览.md` **MD5 相同、字节级完全重复**，两批分别勘探且计数不一致（26 vs 28），两条记录均未发现孪生。需普查是否还有其他孪生。

```bash
cd /Users/chezi/code/java/pf_agent/pf_data/phase1/pf_rules_md_organized
python3 - <<'EOF'
import hashlib, glob, collections
groups = collections.defaultdict(list)
for p in glob.glob('专长*.md') + glob.glob('专长/**/*.md', recursive=True):
    groups[hashlib.md5(open(p, 'rb').read()).hexdigest()].append(p)
dupes = {h: ps for h, ps in groups.items() if len(ps) > 1}
print(f"扫描 {sum(len(v) for v in groups.values())} 文件，重复组 {len(dupes)}")
for h, ps in sorted(dupes.items()):
    print(h[:8], ps)
EOF
```

- 结果写入 `vectorizer/exploration/专长/md5_dupes.md`（每组：MD5、文件对、建议保留方）。
- B03/B15 两条造物记录的 `dedup_note` 互相标注孪生（"与 <对方路径> MD5 相同，字节级重复，向量化只摄入一份——保留方待 source_spec 定"）。
- **边界声明**：MD5 只查字节级重复；内容级重复（如 ISR vs 专长41.md 的 `__aggregate__` 注释对、聚合页转载）不在本项范围，归 source_spec 阶段处理。

---

## 6. R5：收尾（重跑 + 报告更新）

1. 原地修改各 `per_file_BNN.jsonl` 后：
   ```bash
   cd /Users/chezi/code/java/pf_agent/pf_data/phase1/vectorizer/exploration/专长
   python3 merge_batches.py
   python3 verify_prepare.py    # 必须 8 项阻断全过、退出码 0
   ```
   `prepare_verify_report.md` 由脚本重生成，**禁止手改**。
2. 更新 `prepare_phase_report.md`：
   - §3.1 条目合计改为修正后实测总数（R1 净 +93，若 R3 有新修正再累加；附复算命令输出）；
   - §3.1 偏差文件数按 verify 重生成结果如实更新；
   - 文末追加"审计与返工记录"小节：k3 审计（12 抽样 8✅/2⚠️/2❌）→ 本轮 R1~R4 修正清单（改前/改后）。
3. 改完全文 **裸模式 grep 旧数字**（`3523`、`200`、`121`、`89` 及 R2 涉及的旧表述），确认无残留。

---

## 7. 红线（护栏）

1. **只改 `vectorizer/exploration/专长/` 下的勘探记录与派生产物**；不改 `pf_rules_md_organized/` 源文件；不改 `verify_prepare.py` / `merge_batches.py` / `prepare_scan.py` / `machine_scan.jsonl` / `audit_baseline.jsonl`。发现脚本 bug 单列讨论，不得顺手改。
2. **R1/R2 照单更正**：§2/§3 的数字与清单是 k3 审计实测终值；复算不符列异议单独讨论，禁止静默改回、禁止重新定性。
3. **R3 以实测为准但必须给依据**：逐条名称清单为 `count_basis` 最低要求。
4. **所有数字可复算**：交付文档每项 ✅ 附复算命令输出，跑不出就停下来查，禁止手填。
5. **批次归属注意**：page_196 在 B04 单文件批次，不要改到 B05。
6. **Git 安全**：提交前 `git status` 确认改动范围仅限 `vectorizer/exploration/专长/`；单 commit 提交，message 建议 `fix(prepare): k3审计返工 R1~R5 — 4文件计数修正+陷阱更正+9文件补抽+MD5普查`。

---

## 8. 验收口径与复跑入口

### 8.1 交付要求

返工交付文档（可简）：R1~R5 逐项给改前/改后对照 + 复算命令输出；R3 逐文件给独立计数与依据；明确声明"§2/§3 全部照单执行"或列出异议项。

### 8.2 复算命令（k3 复审将原样重跑）

```bash
cd /Users/chezi/code/java/pf_agent/pf_data/phase1

# 全局：verify 8 阻断
python3 vectorizer/exploration/专长/verify_prepare.py   # 期望 exit 0

# R1-ISR：期望 专长效果 50 / 先决条件 49
python3 - <<'EOF'
import re
t = open('pf_rules_md_organized/专长/内海种族ISR_专长.md', encoding='utf-8', newline='').read()
ls = re.split(r'\r\n|\r|\n', t)
print('专长效果:', sum('**专长效果**' in l for l in ls), '先决条件:', sum('**先决条件**' in l for l in ls))
EOF

# R1-page_203：期望 效果 129 / 先决 126 / 特殊 27
python3 - <<'EOF'
import re
t = open('pf_rules_md_organized/专长/page_203.md', encoding='utf-8', newline='').read()
ls = re.split(r'\r\n|\r|\n', t)
print('效果:', sum('**专长效果：**' in l for l in ls), '先决:', sum('**先决条件：**' in l for l in ls), '特殊:', sum('**特殊情况：**' in l for l in ls))
EOF

# R1-page_196：期望 正文 **专长效果**： 166
python3 -c "
import re
t = open('pf_rules_md_organized/专长/page_196.md', encoding='utf-8', newline='').read()
print('专长效果:', len(re.findall(r'\*\*专长效果\*\*：', t)))"

# R1-page_1564：期望 先决条件提及 283
python3 -c "
t = open('pf_rules_md_organized/专长/流派专长一览/page_1564.md', encoding='utf-8', newline='').read()
print('先决条件:', t.count('先决条件'))"

# R1-总数复算
python3 -c "
import json
print(sum(json.loads(l).get('estimated_count',0) for l in open('vectorizer/exploration/专长/专长_per_file.jsonl', encoding='utf-8')))"

# R4-MD5 普查：见 §5 脚本，输出应与 md5_dupes.md 一致
```

### 8.3 k3 复审范围

只看改动 diff + 复跑 §8.2 命令 + R3 逐文件依据抽查，**不再全量重抽样**。通过后即进 k3 汇总阶段（format_clusters / source_spec / test_seeds），其中 page_203/page_1564/ISR 的补登陷阱是 test_seeds 的直接输入。

---

## 9. 给 k3 汇总阶段的连带输入（执行方知悉即可，不在本轮交付）

1. `field_labels_seen` / `title_forms[].count` / `feat_type_tags` 在多份记录中与实测有出入——**formats/feat.py 设计只引用 `raw_example` 与源文件实测，不引用勘探的字段统计数字**。
2. 机检基准=0 的 63 个偏差文件实证为机检盲区（机检对非标准格式全盲），对账清单中该象限无需处理。
3. 大文件（>100KB）抽样外推是计数失真主因（page_1564 "60 家族" 外推 vs 实测 89）——后续模块 Prepare Phase 应考虑大文件分段全读或家族结构先锚定再计数。
