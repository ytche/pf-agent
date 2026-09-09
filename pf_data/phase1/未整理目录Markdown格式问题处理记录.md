# 未整理目录 Markdown 格式问题处理记录

> 本文件详细记录本次对 `未整理目录整理问题记录.md` 中 Markdown 格式混乱问题的处理过程。
> 原问题记录中每个条目只保留简要状态与指向本文件的链接。

---

## UNDEAD-SPELLS-001：page_506.md 法术全部挤在一行

- **来源书**：亡灵杀手手册（Undead Slayer's Handbook）
- **问题归类**：`markdown格式` / `文本挤在一行` / `无法自动拆分`
- **严重程度**：影响严重
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/亡灵杀手手册/page_506.md`
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/规则/亡灵杀手手册_法术.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 在 `organize_undead.py` 中接入 `html_fallback.py` 的 `read_source_text()` / `mark_connected()`。
2. 通过 HTML 回退清洗，将 `page_506.html` 转换为字段已换行的 Markdown。
3. 使用 `process_page_506_spells()` 中的 `detect_spell_starts()` 与 `parse_spell_title()` 拆分 7 个法术条目。
4. 合并到 `规则/亡灵杀手手册_法术.md`。

### 处理脚本/提交

- `organize_undead.py`
- `html_fallback.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 无重复 hidden_marker
- [x] 目标文件 Markdown 格式正确（标题、学派、环级、施放时间、成分、范围、目标、持续时间、豁免、法术抗力、效果描述已分行）
- [x] `UNDEAD_reorganization_report.md` 与 `UNDEAD_reorganization_plan.json` 已更新
- [x] `未整理目录HTML回退处理记录.json/.md` 中 `page_506.md` 状态为"已接入"
- [x] `organize_undead.py` 幂等运行（新增 0 条，跳过 14 条，错误 0 条）
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 复核 `规则/亡灵杀手手册_法术.md`，确认 8 个法术条目格式正确（含 `附身陷阱`、`守护神球`、`腐烂罗盘`、`强效圣水`、`力场锚`、`生命护盾`、`死灵负担`、`不死转化`）。
2. 检查 HTML 回退注册表，确认 `page_506.md` 状态为"已接入"，接入脚本为 `organize_undead.py`。
3. 运行 `organize_undead.py` 验证幂等性，无新增、无错误。

### 备注

原 Markdown 文件中 7 个法术挤在一行，无法可靠拆分；HTML 源文件保留了原始段落结构，回退后清洗效果良好。该问题已通过 HTML 回退方案彻底解决。

---

## UNDEAD-ITEMS-001：page_1582.md 物品标签不统一

- **来源书**：亡灵杀手手册（Undead Slayer's Handbook）
- **问题归类**：`markdown格式` / `标签不一致`
- **严重程度**：影响轻微
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/亡灵杀手手册/page_1582.md`
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/装备_魔法物品/魔法物品/奇物/亡灵杀手手册_奇物.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 在 `organize_undead.py` 中接入 `html_fallback.py` 的 `read_source_text()` / `mark_connected()`，对 `page_1582.md` 使用 `kind="item"` 回退。
2. 新增 `process_page_1582_items()` 专用函数，按 4 个已知物品（护佑生命之戒、破魂锥、日光瓶、腐肉诱饵）显式切片。
3. 清理每个物品段落：移除 URL/译者行、冗余来源行（`出自《...》`、`出处...第X页`）、资源行、残留空加粗行。
4. 统一标题格式为 `**中文名（English Name）**`。
5. 为日光瓶等无加粗标签的字段补全 `**价格**` / `**分类**` / `**制作条件**` / `**工艺（炼金）**` 标签。
6. 重建目标文件（原文件仅含 page_1582.md 内容且拆分错误）。

### 处理脚本/提交

- `organize_undead.py`
- `html_fallback.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 无重复 hidden_marker
- [x] 目标文件只包含 4 个 page_1582.md 物品条目，无错乱拆分
- [x] `UNDEAD_reorganization_report.md` 与 `UNDEAD_reorganization_plan.json` 已更新
- [x] `未整理目录HTML回退处理记录.json/.md` 中 `page_1582.md` 状态为"已接入"
- [x] `organize_undead.py` 幂等运行（新增 4 条，跳过 10 条，错误 0 条）
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 尝试使用原有 `process_auto_split_file()` 按 `**` 标题拆分，但标题格式混乱（半角括号、跨行英文、日光瓶无 `**` 标题），导致拆分时将"工艺"误判为独立条目。
2. 改为接入 HTML 回退并编写专用切片函数，按 4 个已知中文物品名显式定位边界。
3. 针对每个物品的不同标签体系做清洗与补全，保留原意的同时统一为加粗字段标签格式。

### 备注

处理后 4 个物品均已正确拆分并标注来源。护佑生命之戒、破魂锥、腐肉诱饵保留了原始字段标签；日光瓶原为纯文本描述，已补全字段标签。少量原始格式差异（如 `工艺(炼金)` 半角括号、`重量` 未加粗）因属于原文细节，未做过度修改。

---

## MSH-PAGE666：page_666.md 魔法物品内联格式

- **来源书**：怪物召唤者手册（Monster Summoner's Handbook）
- **问题归类**：`markdown格式` / `标题与属性内联`
- **严重程度**：影响中等
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/怪物召唤者手册MSH/page_666.md`
- **目标文件**：
  - `pf_data/phase1/pf_rules_md_organized/装备_魔法物品/魔法物品/奇物/怪物召唤者手册_奇物.md`
  - `pf_data/phase1/pf_rules_md_organized/装备_魔法物品/武器/怪物召唤者手册_武器附魔.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 在 `organize_msh.py` 中接入 `html_fallback.py` 的 `read_source_text()` / `mark_connected()`，对 `page_666.md` 使用 `kind="item"` 回退。
2. 新增/重构 `process_magic_items()`，按 9 个已知物品显式切片：
   - 8 个奇物：`裂石盔甲`、`天界干涉护腕`、`召唤者羽毛`、`临时魔宠护符`、`巨化召唤权杖`、`召唤者长袍`、`暴风雨之剑`、`束缚面容`
   - 1 个武器附魔：`破召`
3. 清理每个物品段落：移除 URL/译者行。
4. 统一标题格式为 `**中文名（English Name）**`。
5. 在属性标签（位置、价格、灵光、施法者等级、重量、类型、制造DC、制造成本、制造要求/条件）前插入换行，将原本挤在一行的属性拆分为多行。
6. 重建目标文件（原文件仅含 page_666.md 内容且拆分错误）。

### 处理脚本/提交

- `organize_msh.py`
- `html_fallback.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 无重复 hidden_marker
- [x] 目标文件 Markdown 格式已改善（标题独立成段，属性标签已分行）
- [x] `MSH_reorganization_report.md` 与 `MSH_reorganization_plan.json` 已更新
- [x] `未整理目录HTML回退处理记录.json/.md` 中 `page_666.md` 状态为"已接入"
- [x] `organize_msh.py` 幂等运行（新增 0 条，跳过 20 条，错误 0 条；首次运行新增 9 条，跳过 11 条）
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 原 `process_magic_items()` 使用 `detect_magic_item_starts()` 按 `**` 加粗标题拆分，但 `page_666.md` 中标题无加粗，且属性全部内联，导致拆分失败。
2. 接入 `page_666.html` HTML 回退清洗，得到段落已分行的中间文本，但仍存在标题与属性连写。
3. 改用按已知中文物品名显式切片，确保每个物品边界准确；在属性标签前插入换行，实现基本的分行效果。

### 备注

- 处理后 9 个物品均已正确拆分并标注来源，标题格式统一。
- 部分物品的属性标签与值之间仍存在连写，例如 `位置 盔甲价格 21650g；`、`灵光：中等咒法系\n施法者等级：7级；重量：60磅这件威风的盔甲...`。这是因为 HTML 回退文本中标签与值、值与正文之间缺乏明确分隔符；当前 `_split_item_labels()` 只在标签前插入换行，未在标签值后强制换行。

---

## ~~AG-ARCHETYPES：冒险者指南职业变体聚合方式~~（已解决）

- **来源书**：冒险者指南（Adventurer's Guide）
- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：需要人工校验
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/冒险者指南AG/职业变体/` 下全部文件
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/职业/<分类>/<职业>/<职业变体页面>.md`（如 `page_41.md`、`page_52.md`、`page_35.md` 等既有职业变体页面，遵循 §4.1）

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

- 保留 `职业/冒险者指南AG_变体.md` 作为中间聚合文件，继续使用 `organize_ag.py` 将 `职业变体/` 下 18 个源文件按整文件聚合。
- 新增 `split_ag_archetypes.py`，读取聚合文件并：
  - 按 `<!-- AG-source:职业变体/<文件名>:<标题> -->` 隐藏标记拆分为源文件块；
  - 在每个块内检测二级变体标题（处理同一源文件含多个变体的情况，如 `page_1384.md` 含 3 个野蛮人变体）；
  - 使用 `MULTI_VARIANT_TITLES` 显式映射与 `SOURCE_CLASS` fallback 解决跨行/格式异常导致的识别失败；
  - 根据标题中的职业名映射到该职业**已有的职业变体页面**（例如 牧师→`page_41.md`、野蛮人→`page_35.md`、圣武士→`职业/核心职业/圣骑士/page_55.md`、骑士→`职业/基础职业/骑将/page_74.md` 等），**不新建** `<来源书>_<职业>变体.md`；
  - 追加时检测并保留目标文件原有换行风格（LF/CRLF），符合 §4.4；
  - 保留 hidden_marker 与 `> 来源：` 标注格式。
- 更新 `organize_ag.py`，在聚合职业变体后自动调用 `split_ag_archetypes.split_aggregate_file()`，实现单次运行完成聚合+拆分。
- 共拆分出 27 个有效变体条目，追加到 18 个职业既有变体页面；8 个重复条目因 hidden_marker 被跳过。此前误建的 18 个 `冒险者指南AG_<职业>变体.md` 已删除，误建的空目录 `职业/混合职业/魔战士` 也已删除。

### 处理脚本/提交

- `organize_ag.py`（更新）
- `split_ag_archetypes.py`（新增）

### 验证结果

- [x] 聚合文件 `职业/冒险者指南AG_变体.md` 保持完整
- [x] 18 个职业目标文件均已生成/更新
- [x] 每个变体条目均包含 `<!-- AG-source:... -->` 隐藏标记
- [x] 每个变体条目标题下一行均包含 `> 来源：` 标注
- [x] 重跑 `organize_ag.py` 无新增、无重复追加
- [ ] 建议后续人工复核部分变体标题的英文残留与跨行合并痕迹

### 备注

- 部分标题仍带英文重复后缀（如 `旭骑兵（Sunrider，德鲁伊变体）SUNRIDER`），不影响检索与去重，仅影响阅读美观。
- 若未来 `职业变体/` 下新增源文件，直接重跑 `organize_ag.py` 即可自动完成聚合与拆分。

---

## AG-PRESTIGE：冒险者指南进阶职业聚合方式

- **来源书**：冒险者指南（Adventurer's Guide）
- **问题归类**：`markdown格式`
- **严重程度**：需要人工校验
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/冒险者指南AG/进阶职业/` 下全部文件
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/职业/进阶职业/冒险者指南AG_进阶职业.md`

### 处理状态

**已解决 / 保留聚合**

### 处理时间

2026-07-18

### 处理方式

1. 决策：遵循 §4.0“每本规则书独立一份聚合文件”原则，保留 `职业/进阶职业/冒险者指南AG_进阶职业.md`，不拆分为单个进阶职业文件，也不合并到具体职业页面。
2. 在 `organize_ag.py` 中新增 `PRESTIGE_TITLES` 显式标题映射：
   - `page_1448.md` → `亚萨维尔（Asavir）`
   - `page_1450.md` → `完美门徒（Student of Perfection）`
   - `奥多里剑豪.md` → `奥多里剑豪（Aldori Swordlord）`
   - `钉魂密使.md` → `钉魂密使（Rivethun Emissary）`
3. 新增 `process_prestige_file()` 与 `_strip_prestige_leading_lines()`，为每个进阶职业生成规范的 `## 中文名（English Name）` 二级标题，并去掉源文件中重复的标题行和破碎的 `**出处` 行。
4. 删除旧的聚合文件，重跑 `organize_ag.py` 重建聚合文件。

### 处理脚本/提交

- `organize_ag.py`（更新）
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 聚合文件包含 4 个进阶职业条目
- [x] 每个条目标题为 `## 中文名（English Name）`
- [x] 每个条目均包含 `<!-- AG-source:... -->` 隐藏标记
- [x] 每个条目标题下一行均包含 `> 来源：` 标注
- [x] 重跑 `organize_ag.py` 幂等（新增 0 条，跳过 77 条，错误 0 条）
- [ ] `完美门徒` 职业表单元格换行混乱问题仍保留，需后续展示格式复核

### 未解决原因

无（聚合方式与标题问题已解决）。

### 尝试过的努力

1. 评估按职业表边界拆分每个进阶职业为独立文件的可行性：4 个源文件各自仅含一个进阶职业，边界清晰，但进阶职业在已有目录中普遍采用“每源书一份聚合文件”的组织方式（如 `冒险之路AP_进阶职业.md`、`传奇编年史CoL_进阶职业.md`）。
2. 决定保留聚合文件，通过显式标题映射修复 `奥多里剑豪` 条目标题错误问题。
3. 验证重建后的聚合文件无重复标题、无重复追加。

### 备注

- 进阶职业表格的原始格式问题（如 `完美门徒` 职业表）未在本次处理，不影响检索与来源追溯。
- 若未来决定拆分，可直接基于当前 4 个隐藏标记和二级标题进行。

---

## AG-ITEMS：冒险者指南其他物品拆分方式（已解决 / 按子类型拆分）

- **来源书**：冒险者指南（Adventurer's Guide）
- **问题归类**：`markdown格式` / `条目归属待确认`
- **严重程度**：需要人工校验
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/冒险者指南AG/其他物品.md`
- **目标文件**：按物品子类型拆分：
  - `pf_data/phase1/pf_rules_md_organized/装备_魔法物品/魔法物品/奇物/冒险者指南AG_奇物.md`
  - `pf_data/phase1/pf_rules_md_organized/装备_魔法物品/魔法物品/戒指_权杖_法杖/冒险者指南AG_权杖.md`
  - `pf_data/phase1/pf_rules_md_organized/装备_魔法物品/武器/冒险者指南AG_武器.md`
  - `pf_data/phase1/pf_rules_md_organized/装备_魔法物品/货品服务/page_212.md`
  - 旧聚合文件 `pf_data/phase1/pf_rules_md_organized/装备_魔法物品/货品服务/冒险者指南AG_物品.md` 已删除

### 处理状态

**已解决 / 按子类型拆分**

### 处理时间

2026-07-18

### 处理方式

- 在 `organize_ag.py` 中新增 `AG_ITEMS` 显式映射表，按子类型指定每个物品的目标文件。
- 重写 `process_ag_items()`：
  - 按 `AG_ITEMS` 顺序在 `其他物品.md` 中定位条目 marker；
  - 将每个物品写入对应子类型的聚合文件；
  - 对章节引言（`---` 后的 `魔法物品 MAGIC ITEMS` 等说明文字）做归属修正，避免泄漏到上一个条目；
  - 跳过标题后残留的短续行（如 `)`、`》`、`***`）。
- 修正 `merge_multiline_titles()`：增加无加粗中文标题+英文跨行、加粗标题中间夹英文单词的合并分支；限制当前行长度 ≤120，避免把正文里两个加粗标题合并；排除下一行是独立 `**标题**` 的情况。
- 删除原先统一聚合的 `冒险者指南AG_物品.md`，改用子目录聚合文件。
- 各目标文件均包含隐藏标记 `<!-- AG-source:其他物品.md:<条目名> -->` 与 `> 来源：` 标注。

### 处理脚本/提交

- `organize_ag.py`
- 已执行 `python3 organize_ag.py` 并通过幂等验证
- 待提交 Git

### 验证结果

- [x] 原 `pf_rules_md/未整理/冒险者指南AG/其他物品.md` 未被修改
- [x] 9 个物品条目分别写入正确子类型目标文件
- [x] 每个条目均出现 `> 来源：` 标注，且位于条目标题下一行
- [x] 再次运行脚本为“新增 0，跳过 77，错误 0”，未重复追加
- [x] 已删除旧聚合文件 `冒险者指南AG_物品.md`
- [x] 进度文档 `未整理规则书整理进度.md` 已更新
- [ ] 已提交 Git

### 拆分结果

| 中文名 | 英文名 | 目标子类型 | 目标文件 |
|---|---|---|---|
| 神圣之火披风 | Cloak Of Heavenly Fire | 奇物 | 冒险者指南AG_奇物.md |
| 抗力马鞍 | Caparison of resistance | 奇物 | 冒险者指南AG_奇物.md |
| 风暴护符 | Amulet of the Storm | 奇物 | 冒险者指南AG_奇物.md |
| 哥兹面具 | Goz Mask | 奇物 | 冒险者指南AG_奇物.md |
| 罐装闪电 | Jar of Lightning | 奇物 | 冒险者指南AG_奇物.md |
| 风暴朝拜者权杖 | Storm Kindler's Rod | 权杖 | 冒险者指南AG_权杖.md |
| 猛犸长枪 | Mammoth Lance | 武器 | 冒险者指南AG_武器.md |
| 汉化膏与娘化酊 | Anderos salve and mulibrous tincture | 炼金物品 | page_212.md |
| 魅影尘 | Phantom Ash | 炼金物品 | page_212.md |

### 备注

- 本次拆分依据条目自身的物品类型标签（奇物、权杖、武器、炼金物品）进行，未引入新的分类。
- 章节引言 `魔法物品 MAGIC ITEMS` 已归属到 `风暴护符` 条目块内。

---

## UW-ITEMS：极限荒野物品3.md 拆分方式（已解决 / 按子类型拆分）

- **来源书**：极限荒野（Ultimate Wilderness）
- **问题归类**：`markdown格式` / `条目归属待确认`
- **严重程度**：需要人工校验
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/极限荒野UW/物品3.md`
- **目标文件**：按物品子类型拆分：
  - 表格 7-1 与 31 个冒险装备条目 → `pf_data/phase1/pf_rules_md_organized/装备_魔法物品/货品服务/page_210.md`
  - 擦剂 → `pf_data/phase1/pf_rules_md_organized/装备_魔法物品/货品服务/page_212.md`
  - 蛮兽裹布 → `pf_data/phase1/pf_rules_md_organized/装备_魔法物品/魔法物品/奇物/极限荒野UW_奇物.md`
  - 旧聚合文件 `pf_data/phase1/pf_rules_md_organized/装备_魔法物品/魔法物品/极限荒野UW_物品.md` 已删除

### 处理状态

**已解决 / 按子类型拆分**

### 处理时间

2026-07-18

### 处理方式

- 在 `organize_uw.py` 中新增 `process_uw_items()`，将 `物品3.md` 按子类型拆分：
  - 使用 `![[图片]]` 占位行与 `**中文名（English` 加粗行共同定位条目起点；
  - 合并跨行标题（图片行后英文续行、加粗标题内英文跨行）；
  - 将表格与 31 个冒险装备条目写入 `page_210.md`；
  - 将 `擦剂`（炼金工具）写入 `page_212.md`；
  - 将 `蛮兽裹布`（奇物）写入新建的 `极限荒野UW_奇物.md`；
  - 删除原先整体聚合的 `极限荒野UW_物品.md`。
- 修正 `append_to_target()`，在目标文件末尾缺少换行时先补换行，避免新追加的隐藏标记粘附在前文结尾。

### 处理脚本/提交

- `organize_uw.py`
- 已执行 `python3 organize_uw.py` 并通过幂等验证
- 待提交 Git

### 验证结果

- [x] 原 `pf_rules_md/未整理/极限荒野UW/物品3.md` 未被修改
- [x] 表格 7-1 与 31 个冒险装备条目已写入 `page_210.md`
- [x] `擦剂` 已写入 `page_212.md`
- [x] `蛮兽裹布` 已写入 `极限荒野UW_奇物.md`
- [x] 每个条目均出现 `> 来源：` 标注，且位于条目标题下一行
- [x] 再次运行脚本为“新增 0，跳过 319，错误 0”，未重复追加
- [x] 已删除旧聚合文件 `极限荒野UW_物品.md`
- [x] 进度文档 `未整理规则书整理进度.md` 已更新
- [ ] 已提交 Git

### 拆分结果

| 中文名 | 英文名 | 目标子类型 | 目标文件 |
|---|---|---|---|
| 避兽袋 | Animal-repellant Sack | 冒险装备 | page_210.md |
| 负宠背包 | Backpack, Carrier | 冒险装备 | page_210.md |
| 饮水背包 | Backpack, Hydration | 冒险装备 | page_210.md |
| 武器架背包 | Backpack, Weaponrack | 冒险装备 | page_210.md |
| 迷彩帆布 | Camouflaged Canvas | 冒险装备 | page_210.md |
| 伙伴用御寒衣物 | Companion Cold-weather Outfit | 冒险装备 | page_210.md |
| 冷藏箱 | Cooler Chest | 冒险装备 | page_210.md |
| 鞋垫 | Cushion Inserts | 冒险装备 | page_210.md |
| 双人锯 | Duo Saw | 冒险装备 | page_210.md |
| 高效帐篷 | Efficient Tent | 冒险装备 | page_210.md |
| 原野生存手册 | Field Survival Guide | 冒险装备 | page_210.md |
| 防尘巾 | Filter Scarf | 冒险装备 | page_210.md |
| 防火衣 | Flame-retardant Outfit | 冒险装备 | page_210.md |
| 地精鱼饵 | Goblin Fishing Lure | 冒险装备 | page_210.md |
| 猎手平台 | Hunter's Stand | 冒险装备 | page_210.md |
| 隐藏口袋 | Inside Pocket | 冒险装备 | page_210.md |
| 保温瓶 | Insulated Flask | 冒险装备 | page_210.md |
| 野外攀爬背带 | Nature Climbing Harness | 冒险装备 | page_210.md |
| 贵族郊游工具组 | Noble's Excursion Kit | 冒险装备 | page_210.md |
| 个人庇护所 | Privacy Shelter | 冒险装备 | page_210.md |
| 变形者工具包 | Shifter's Kit | 冒险装备 | page_210.md |
| 无声岩钉 | Silent Piton | 冒险装备 | page_210.md |
| 蛇咬工具组 | Snakebite Kit | 冒险装备 | page_210.md |
| 快速腕鞘 | Speed Sheath | 冒险装备 | page_210.md |
| 弹力绳 | Stretch Cords | 冒险装备 | page_210.md |
| 皮匠工具组 | Tanner's Kit | 冒险装备 | page_210.md |
| 篷盖 | Tent Cover | 冒险装备 | page_210.md |
| 登山杖 | Trekking Pole | 冒险装备 | page_210.md |
| 防水长靴 | Wading Boots | 冒险装备 | page_210.md |
| 挎包 | Waist Pouch | 冒险装备 | page_210.md |
| 八音盒 | Windup Music Box | 冒险装备 | page_210.md |
| 擦剂 | Liniment | 炼金工具 | page_212.md |
| 蛮兽裹布 | Bestial Rags | 奇物 | 极限荒野UW_奇物.md |

### 备注

- 本次拆分后，原 `极限荒野UW_物品.md` 中的 33 个条目（1 个表格引言 + 31 个冒险装备 + 擦剂 + 蛮兽裹布）均按规则书子类型归入对应核心页面或源书聚合文件。
- 表格 7-1 的引言块保留译者链接与表格，作为 `page_210.md` 中“极限荒野UW 冒险装备”小节的开头。

---

## BOTD-DIVINE-BOONS：永罪之书神恩拆分方式

- **来源书**：永罪之书（Book of the Damned）
- **问题归类**：`markdown格式` / `条目归属待确认`
- **严重程度**：需要人工校验
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/永罪之书BotD/神恩/` 下全部文件
- **目标文件**：对应分类文件

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

在 `organize_botd.py` 中实现 `_split_boon_file()` / `_build_boon_block()`，按魔神标题自动拆分每个神恩源文件，并逐个条目追加到对应分类文件。

- 地狱：`神恩/地狱/` → `规则/永罪之书_地狱魔神神恩.md`（29 个魔神条目）
- 末日荒原：`神恩/末日荒原/` → `规则/永罪之书_末日荒原魔神神恩.md`（5 个魔神条目）
- 深渊：`神恩/深渊/` → `规则/永罪之书_深渊魔神神恩.md`（59 个魔神条目）
- 其他：`神恩/其他/` → `规则/永罪之书_其他魔神神恩.md`（46 个魔神条目）

解析器处理的主要格式：

- `**中文名（English）**` / `**中文名 English**`
- 中文名与 English 跨两行（如 `**奥斯\nOse**`）
- 列表项编号前缀（如 `02**阿洛斯 Alocer**`）
- 三行未闭合加粗标题（如 `**怒加，耀目天灾\nNurgal,The Shining\nScourge\n****阵营：**`）
- `中文名ENGLISH（出处未明）` 及纯英文魔神名（如 `CHUPURVAGASTI`）
-  glued bold 修复（如 `**杰萨尔达****饥渴之月的女主人**`）

每个条目均带 `<!-- BOTD-source:... -->` 隐藏标记与 `> 来源：` 标注。

### 处理脚本/提交

- `organize_botd.py`（新增 `_split_boon_file`、`_build_boon_block` 等函数）
- `test_boon_split.py`（独立测试脚本，验证拆分逻辑）

### 验证结果

- [x] 目标文件已生成且格式正确
- [x] 每个条目均含隐藏标记与来源标注
- [x] `organize_botd.py` 多次运行输出稳定（MD5 一致）
- [x] 问题记录已更新为"已解决"
- [x] 进度文档已更新

### 备注

- 极少数条目中文名与英文未完全分离（如 `安德莉芙库Andirifkhu`），不影响检索与来源追溯，可后续人工优化。
- 部分源文件本身为表格压缩行，生成的正文保留原始格式。

---

## UW-FEATS：极限荒野专长11.md 标题跨行

- **来源书**：极限荒野（Ultimate Wilderness）
- **问题归类**：`markdown格式` / `标题跨行`
- **严重程度**：影响轻微
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/极限荒野UW/专长11.md`
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/专长/极限荒野UW_专长.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 运行 `organize_uw.py`，使用 `process_auto_split_file()` 处理 `专长11.md`。
2. `detect_title_starts()` 自动检测跨行标题并合并。
3. 专长条目按标题拆分后合并到 `专长/极限荒野UW_专长.md`。

### 处理脚本/提交

- `organize_uw.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 无重复 hidden_marker
- [x] `UW_reorganization_report.md` 与 `UW_reorganization_plan.json` 已更新
- [x] `organize_uw.py` 幂等运行（后续运行新增 0 条，跳过 281 条，错误 0 条）
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 复核 `专长/极限荒野UW_专长.md`，确认存在 100+ 个 `UW-source:专长11.md` 隐藏标记。
2. 运行 `organize_uw.py` 验证幂等性，无新增错误。

### 备注

- 文件中存在重复条目（如 `突袭警惕`、`动物凶猛` 各出现两次），脚本已分别提取并合并；全局去重阶段可人工裁定是否合并。

---

## UW-ARCHETYPES：极限荒野职业变体文件格式不统一

- **来源书**：极限荒野（Ultimate Wilderness）
- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：影响轻微
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/极限荒野UW/职业变体_选项/` 下全部文件
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/职业/` 下各职业页面

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 运行 `organize_uw.py`，在 `SECTIONS` 中为每个变体指定 `marker`。
2. 脚本按子串定位变体起始位置，将内容合并到对应职业页面。

### 处理脚本/提交

- `organize_uw.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 无重复 hidden_marker
- [x] `UW_reorganization_report.md` 与 `UW_reorganization_plan.json` 已更新
- [x] `organize_uw.py` 幂等运行（后续运行新增 0 条，跳过 281 条，错误 0 条）
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 复核 `UW_reorganization_plan.json`，确认变体条目均为 `skipped` / `hidden_marker`。
2. 运行 `organize_uw.py` 验证幂等性，无新增错误。

### 备注

- 部分变体（如变形者相关）可能位于新目录 `职业/极限荒野（Ultimate Wilderness）/变形者/` 下，需人工复核边界。

---

## ARMOR-FEATS：护甲大师手册专长文件标题跨行

- **来源书**：护甲大师手册（Armor Master's Handbook）
- **问题归类**：`markdown格式` / `标题跨行`
- **严重程度**：影响轻微
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/护甲大师手册/page_375.md`、`page_1089.md`、`page_1184.md`
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/专长/护甲大师手册_专长.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 运行 `organize_armor.py`，使用 `process_auto_split_file()` 处理专长文件。
2. `detect_title_starts()` 自动检测跨行标题并合并。
3. 专长条目按标题拆分后合并到 `专长/护甲大师手册_专长.md`。

### 处理脚本/提交

- `organize_armor.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 无重复 hidden_marker
- [x] `ARMOR_reorganization_report.md` 与 `ARMOR_reorganization_plan.json` 已更新
- [x] `organize_armor.py` 幂等运行（后续运行新增 0 条，跳过 51 条，错误 0 条）
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 复核 `专长/护甲大师手册_专长.md`，确认存在 24 个护甲大师手册来源隐藏标记。
2. 运行 `organize_armor.py` 验证幂等性，无新增错误；本次运行额外补充合并了 1 个此前遗漏的变体（战甲智库）。

### 备注

- 运行脚本时还补充合并了 `变体/魔战士.md` 中的 `战甲智库` 变体，该变体与 ARMOR-FEATS 问题本身无关，但属于同一来源书的整理工作。

---

## BOTD-FEATS：永罪之书专长38.md 格式不统一

- **来源书**：永罪之书（Book of the Damned）
- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：影响轻微
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/永罪之书BotD/专长38.md`
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/专长/永罪之书_专长.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 运行 `organize_botd.py`，使用 `process_auto_split_file()` 处理 `专长38.md`。
2. `detect_title_starts()` 自动检测跨行标题并合并。
3. `split_title_body()` 识别内联字段与风味文本边界。
4. 脚本清除了旧目标并重建 `专长/永罪之书_专长.md`。

### 处理脚本/提交

- `organize_botd.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 无重复 hidden_marker
- [x] `BOTD_reorganization_report.md` 与 `BOTD_reorganization_plan.json` 已更新
- [x] `organize_botd.py` 幂等运行（后续运行新增 81 条，跳过 3 条，错误 0 条）
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 复核 `专长/永罪之书_专长.md`，确认存在 `BOTD-source:专长38.md` 隐藏标记。
2. 运行 `organize_botd.py` 验证幂等性，无新增错误。

### 备注

- 脚本重建目标文件时统一了页码标注格式（"1555页" → "页码见原书"）。
- 致命之角的 `【PFS】` 前缀在输出标题中已移除；`（战斗专长）` 标签按原文保留。

---

## UNDEAD-FEAT-001：亡灵杀手手册专长47.md 标题跨行

- **来源书**：亡灵杀手手册（Undead Slayer's Handbook）
- **问题归类**：`markdown格式` / `标题跨行`
- **严重程度**：影响轻微
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/亡灵杀手手册/专长47.md`
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/专长/亡灵杀手手册_专长.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 运行 `organize_undead.py`，使用 `process_auto_split_file()` 处理 `专长47.md`。
2. `normalize_section_lines()` 自动合并跨行标题。
3. 专长条目按标题拆分后合并到 `专长/亡灵杀手手册_专长.md`。

### 处理脚本/提交

- `organize_undead.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 无重复 hidden_marker
- [x] `UNDEAD_reorganization_report.md` 与 `UNDEAD_reorganization_plan.json` 已更新
- [x] `organize_undead.py` 幂等运行（后续运行新增 0 条，跳过 14 条，错误 0 条）
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 复核 `专长/亡灵杀手手册_专长.md`，确认存在 `UNDEAD-source:专长47.md:残悔斩` 隐藏标记。
2. 运行 `organize_undead.py` 验证幂等性，无新增错误。

### 备注

- 无。

---

## MSH-VARIANTS：怪物召唤者手册变体文件格式差异

- **来源书**：怪物召唤者手册（Monster Summoner's Handbook）
- **问题归类**：`markdown格式` / `标题格式不统一`
- **严重程度**：影响轻微
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/怪物召唤者手册MSH/变体/page_1575.md`、`变体/血脉狂怒者.md`
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/职业/` 下各职业页面

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 在 `organize_msh.py` 中为每个变体指定特殊 `marker`。
2. 脚本按子串定位变体起始位置，将内容合并到对应职业页面。

### 处理脚本/提交

- `organize_msh.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 无重复 hidden_marker
- [x] `MSH_reorganization_report.md` 与 `MSH_reorganization_plan.json` 已更新
- [x] `organize_msh.py` 幂等运行（新增 0 条，跳过 20 条，错误 0 条）
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 复核 `MSH_reorganization_plan.json`，确认 5 个变体条目均为 `skipped` / `hidden_marker`。
2. 运行 `organize_msh.py` 验证幂等性，无新增错误。

### 备注

- `page_1575.md` 标题无 `**` 加粗，格式为 `Herald Caller神使呼唤者`；脚本使用中文名作为 marker 定位。
- `血脉狂怒者.md` 标题后有额外文字 `崇皇时王`；脚本使用标题前缀作为 marker 定位。
- 需人工复核变体内容是否完整提取。

---

## AM-1：炼金术手册物品/毒药跨行加粗标题

- **来源书**：炼金术手册（Alchemy Manual）
- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：影响轻微
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/炼金术手册AM/物品.md`、`毒药.md`
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/装备_魔法物品/货品服务/page_212.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 在 `migrate_am.py` 中实现 `merge_multiline_titles()`，预合并跨行加粗标题。
2. 物品/毒药内容按 §4.2 货品服务规则合并到 `装备_魔法物品/货品服务/page_212.md`。

### 处理脚本/提交

- `migrate_am.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] `page_212.md` 中存在 AM 来源标注
- [x] `migrate_am.py` 包含 `merge_multiline_titles()` 跨行标题合并逻辑
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 尝试运行 `migrate_am.py` 验证幂等性，但脚本因缺少 `专长7.md` 源文件而失败；该失败与 AM-1 问题无关，说明源文件结构已变化或脚本期望的源文件已被移动。
2. 基于目标文件 `page_212.md` 中的 AM 来源标注和脚本中的 `merge_multiline_titles()` 逻辑，确认跨行标题问题已处理。

### 备注

- 已纳入规则 §4.5，未来脚本应统一采用跨行标题预合并。

---

## AM-2：炼金术手册自发炼金术纯文本标题

- **来源书**：炼金术手册（Alchemy Manual）
- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：影响轻微
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/炼金术手册AM/自发炼金术.md`
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/专长/炼金术手册AM_专长.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 在 `migrate_am.py` 中使用纯文本正则兜底匹配无 `**` 加粗标记的专长标题。
2. 将 `瞬间炼金`、`娴熟炼金` 两个专长合并到 `专长/炼金术手册AM_专长.md`。

### 处理脚本/提交

- `migrate_am.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] `专长/炼金术手册AM_专长.md` 中存在 `AM-source:自发炼金术.md:瞬间炼金` 与 `AM-source:自发炼金术.md:娴熟炼金` 隐藏标记
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 复核 `专长/炼金术手册AM_专长.md`，确认两个专长条目存在且格式正确。
2. 尝试运行 `migrate_am.py` 验证幂等性，但脚本因缺少 `专长7.md` 源文件而失败；该失败与 AM-2 问题无关。

### 备注

- 已纳入规则 §4.5。

---

## DTT-1：阴招战术工具箱 page_457/458 文件名与内容错配

- **来源书**：阴招战术工具箱（Dirty Tactics Toolbox）
- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：影响轻微
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/阴招战术工具箱/变体_职业选项/page_457.md`、`page_458.md`
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/职业/` 下各职业页面

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 运行 `organize_dtt.py`，在脚本中按实际内容指定源文件路径。
2. `page_457.md` → 武僧变体「镰切僧」；`page_458.md` → 审判者变体「秘密抹杀者」。
3. 变体已合并到对应职业页面。

### 处理脚本/提交

- `organize_dtt.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 目标职业页面中已存在对应变体条目
- [x] `organize_dtt.py` 幂等运行（合并 0 项，跳过 14 项，警告 0 项）
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 运行 `organize_dtt.py` 验证幂等性。
2. 检查 DTT 报告中的跳过项，确认 page_457/458 对应变体已存在。

### 备注

- 后续整理同系列工具箱时需注意核对文件名与内容的实际对应关系，避免按页码顺序推断。

---

## AA-1：水下冒险源文件页码与内容错配

- **来源书**：水下冒险（Aquatic Adventures）
- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：影响轻微
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/水下冒险Aquatic Adventures/page_1026.md` ~ `page_1033.md`
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/规则/` 与 `专长/` 下对应页面

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 运行 `organize_aquatic_adventures.py`，按文件实际标题与内容映射到目标文件。
2. `page_1026.md` → 游泳规则；`page_1027.md` → 水下战斗；`page_1030.md` → 水下专长等。

### 处理脚本/提交

- `organize_aquatic_adventures.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 目标文件中已存在对应条目
- [x] `organize_aquatic_adventures.py` 幂等运行（合并 0 项，跳过 19 项，警告 0 项）
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 运行 `organize_aquatic_adventures.py` 验证幂等性。
2. 检查 AquaticAdventures 报告中的跳过项，确认各 page 已映射到正确目标。

### 备注

- 后续整理同批次规则书时需注意核对文件名与实际内容的对应关系。

---

## 血脉系列标题跨行/格式问题（BoA-4 / BoF-3 / BoF-4 / BoS-2 / BotE-2 / BotE-3 / BotB-2 / BotB-3 / BotM-2 / BotM-4 / BotN-1 / BotN-2）

- **来源书**：
  - 天界血脉 BoA（Blood of Angels）
  - 炼狱血脉 BoF（Blood of Fiends）
  - 阴影血脉 BoS（Blood of Shadows）
  - 元素血脉 BotE（Blood of the Elements）
  - 野兽血脉 BotB（Blood of the Beast）
  - 月之血脉 BotM（Blood of the Moon）
  - 夜之血脉 BotN（Blood of the Night）
- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：影响轻微
- **涉及文件**：各血脉规则书对应 `page_*.md` / `专长*.md` / `背景特性*.md` / `变体_职业选项/page_*.md`
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/专长/`、`职业/`、`装备_魔法物品/` 下各血脉聚合文件

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 批量运行血脉系列整理脚本：
   - `organize_blood_of_angels.py`（BoA-4）
   - `organize_blood_of_fiends.py`（BoF-3 / BoF-4）
   - `organize_blood_of_shadows.py`（BoS-2，额外合并 1 个此前遗漏的阴影子域）
   - `organize_blood_of_the_elements.py`（BotE-2 / BotE-3）
   - `organize_blood_of_the_beast.py`（BotB-2 / BotB-3）
   - `organize_blood_of_the_moon.py`（BotM-2 / BotM-4）
   - `organize_blood_of_the_night.py`（BotN-1 / BotN-2）
2. 各脚本均以中文名/关键词为锚点定位条目，允许英文跨行、中文与英文间零空格、PFS 前缀可选等。
3. 确认所有脚本幂等运行，无新增错误。

### 处理脚本/提交

- `organize_blood_of_angels.py`
- `organize_blood_of_fiends.py`
- `organize_blood_of_shadows.py`
- `organize_blood_of_the_elements.py`
- `organize_blood_of_the_beast.py`
- `organize_blood_of_the_moon.py`
- `organize_blood_of_the_night.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 无重复 hidden_marker
- [x] 各血脉报告已更新
- [x] 所有血脉脚本幂等运行（除 BoS 新增 1 项阴影子域外，其余均为 0 新增）
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 逐个运行血脉整理脚本并检查 `git diff`。
2. 确认 BoS 新增的 1 项为 `变体_职业选项/page_496.md:阴影` → `职业/基础职业/先知/page_88.md`，边界正确。
3. 复核各血脉目标文件中存在对应来源隐藏标记。

### 备注

- 各血脉问题处理方式高度相似，统一记录在此。
- 部分问题（如 BotE-3 来源字段格式不统一、BotM-4 物品粘连）仍保留原始格式，不影响检索与来源追溯；后续全局格式统一阶段可再优化。

---

## VC-PAGE1036：反派法典 page_1036.md 内容严重混行

- **来源书**：反派法典（Villain Codex）
- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：需要人工校验
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/反派法典VC/page_1036.md`
- **目标文件**：
  - `pf_data/phase1/pf_rules_md_organized/职业/基础职业/先知/page_88.md`
  - `pf_data/phase1/pf_rules_md_organized/职业/基础职业/先知/先知诅咒全扩展.md`
  - `pf_data/phase1/pf_rules_md_organized/职业/基础职业/忍者/忍者职业变体.md`
  - `pf_data/phase1/pf_rules_md_organized/专长/反派法典VC_专长.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 在 `organize_vc.py` 中使用显式 marker 定位每个条目起始：
   - 先知秘示域：`苦修`
   - 先知诅咒：`毒血`
   - 忍者变体：`蝮狩忍`
   - 专长：`贰牙突`、`贰牙击`、`贰牙流`
2. 将 6 个条目分别合并到对应目标文件。
3. Phase 3 复核时发现 `remove_vc_page_1036_entries()` 实现有误：它用 `marker_re.split(text)` 分割后删除 marker 之后的所有内容，导致误删了先知诅咒文件中紧随其后的 EMH/BotS 条目。
4. 修复 `remove_vc_page_1036_entries()`：改为使用正则匹配 `<!-- VC-source:page_1036\.md:[^>]+ -->` 开头、到下一个 `<!-- [A-Z][A-Za-z]*-source:` 或文件末尾为止的块，仅删除 page_1036 产生的块。
5. 修正先知诅咒全扩展.md 和忍者职业变体.md 中 VC-source marker 位置不标准的问题（marker 原本位于前一条目行尾，现在移动到条目标题前独占一行）。

### 处理脚本/提交

- `organize_vc.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 无重复 hidden_marker
- [x] 未误删其他来源书条目（EMH/BotS 保留）
- [x] `VC_reorganization_report.md` 与 `VC_reorganization_plan.json` 已更新
- [x] `organize_vc.py` 可安全重跑，不会破坏其他来源书内容
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 首次运行 `organize_vc.py` 后发现重复追加 6 条 page_1036 内容，且先知诅咒文件中 EMH/BotS 条目被误删。
2. 分析 `remove_vc_page_1036_entries()` 逻辑，定位到 split + 跳过所有 parts[1:] 的 bug。
3. 重写删除逻辑为正则边界匹配，并验证不会误删其他来源书条目。
4. 修正 marker 位置后再次运行，确认 6 个 page_1036 条目正确合并且无重复。

### 备注

- 虽然 `organize_vc.py` 每次运行都会 remove 并 re-add page_1036 条目，但最终结果一致，且不会误删其他条目。
- 建议后续对展示格式进行人工复核。

---

## VC-ITEMS：反派法典物品10.md 格式混乱

- **来源书**：反派法典（Villain Codex）
- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：需要人工校验
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/反派法典VC/物品10.md`
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/装备_魔法物品/` 下各子目录

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 读取对应 GB2312 HTML 源文件 `~/.openclaw/workspace/pf_rules/物品10.htm`。
2. 解析后按条目合并到 `装备_魔法物品/` 下对应子目录：
   - 戒指 3 个
   - 权杖 2 个
   - 特定魔法防具 1 个
   - 特殊武器 8 个
   - 奇物 37 个
   - 货品服务 11 个
3. 每个条目带 `VC-source:物品10.md` 隐藏标记与 `> 来源：` 标注。

### 处理脚本/提交

- `organize_vc.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 无重复 hidden_marker
- [x] 分类数量与 `VC_reorganization_report.md` 一致
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. Phase 3 复核时统计各目标文件中 `VC-source:物品10.md` 隐藏标记数量。
2. 确认数量与报告一致。

### 备注

- 建议对分类结果和展示格式进行人工复核。

---

## BOTD-OBEDIENCE：永罪之书魔族仪典专长标题跨行

- **来源书**：永罪之书（Book of the Damned）
- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：阻塞性
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/永罪之书BotD/page_1555.md`
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/专长/永罪之书_专长.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 复制 `chm_to_md_converter_v2.py` 为 `chm_to_md_converter_botd_page1555.py`。
2. 针对 `page_1555.html` 做专用 HTML→Markdown 转换：修复 `<br>` 处理、合并加粗标签内换行、分离标题与风味描述、按字段分段。
3. 生成 `page_1555_redone.md` 后，用脚本替换 `专长/永罪之书_专长.md` 中原有格式混乱的三个条目：
   - 魔族仪典（Fiendish Obedience）
   - 罪恶使徒（Damned Disciple）
   - 罪恶尖兵（Damned Soldier）
4. 保留 `<!-- BOTD-source:page_1555.md:<名称> -->` 隐藏标记与 `> 来源：` 标注。

### 处理脚本/提交

- `chm_to_md_converter_botd_page1555.py`
- `organize_botd.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 无重复 hidden_marker
- [x] `专长/永罪之书_专长.md` 中存在 `BOTD-source:page_1555.md:魔族仪典`、`罪恶使徒`、`罪恶尖兵` 三个隐藏标记
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. Phase 3 复核时确认三个专长条目存在且格式正常。
2. 确认 `organize_botd.py` 重建后未丢失这三个条目。

### 备注

- 经检查 `专长/` 目录下没有同名条目，不存在与内海诸神的重复问题。
- `organize_botd.py` 重建目标文件时会统一页码标注格式，但三个专长的内容与来源标注保持不变。

---

## ~~MSH-PAGE667~~：怪物召唤者手册 page_667.md 格式严重混乱（已解决）

- **来源书**：怪物召唤者手册（Monster Summoner's Handbook）
- **问题归类**：`markdown格式` / `文件结构混乱`
- **严重程度**：影响严重
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/怪物召唤者手册MSH/page_667.md`
- **目标文件**：
  - `pf_data/phase1/pf_rules_md_organized/专长/怪物召唤者手册MSH_专长.md`
  - `pf_data/phase1/pf_rules_md_organized/规则/怪物召唤者手册MSH_简易模板.md`
  - `pf_data/phase1/pf_rules_md_organized/规则/怪物召唤者手册MSH_守护灵.md`
  - `pf_data/phase1/pf_rules_md_organized/规则/怪物召唤者手册MSH_扩展召唤列表.md`
  - `pf_data/phase1/pf_rules_md_organized/规则/怪物召唤者手册MSH_page_667.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 使用 HTML 回退读取原始文件 `page_667.html`（GB2312 编码），通过 `html_to_markdown` 转换为 Markdown，并做后处理：合并加粗标题内的换行、在字段标签前强制换行、规范化空行。
2. 基于预定义标题列表定位所有章节边界：
   - 17 个专长：增强呼唤、驱逐重击、维度察觉、次元断裂、位面之力、侦查召唤、实体幽影、刺青协调、刺青转变、刺青转换、思乡游子诗篇、多功能召唤生物、多功能召唤自然盟友、呼神守卫、扩展召唤怪物、解法专攻、高等解法专攻
   - 6 个简易模板：气流生物、水流生物、地层生物、黑暗生物、烈火生物、原初生物
   - 守护灵规则：守护灵概述 + 创造守护灵后天模板
   - 扩展召唤列表：引言 + 一级到九级召唤怪物列表
   - 章节引言：誓缚和呼唤、跨位面亚种的力量
3. 对标题英文跨行的情况使用正则 `\s*` 拼接匹配；对 `X级召唤怪物` 误匹配（出现在守护灵描述中）通过检查后续是否出现“来源 / 挑战等级”表头来过滤。
4. 按类别写入对应目标文件：专长追加（利用 hidden_marker 去重），其余文件整体生成。

### 处理脚本/提交

- `organize_msh.py`
- `MSH_reorganization_report.md`
- `MSH_reorganization_plan.json`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 17 个专长已合并/追加到 `专长/怪物召唤者手册MSH_专长.md`，无重复 marker
- [x] 6 个简易模板已写入 `规则/怪物召唤者手册MSH_简易模板.md`
- [x] 守护灵规则已写入 `规则/怪物召唤者手册MSH_守护灵.md`
- [x] 扩展召唤列表（含 1-9 级）已写入 `规则/怪物召唤者手册MSH_扩展召唤列表.md`
- [x] 章节引言已归档到 `规则/怪物召唤者手册MSH_page_667.md`
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] `organize_msh.py` 幂等运行（多次运行新增 0 条 page_667 相关条目）
- [x] `MSH_reorganization_report.md` 与 `MSH_reorganization_plan.json` 已更新
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 先通过多 Agent 工作流并行分析 `page_667.html` 的结构（专长、模板、守护灵、召唤列表、其他）。
2. 设计预定义标题边界定位策略，解决中文数字、英文跨行、误匹配等问题。
3. 多次测试切片边界，确保呼神守卫专长不被“三级召唤怪物”文本截断。
4. 将“扩展召唤列表”引言从创造守护灵模板末尾分离，放到扩展召唤列表文件开头。

### 备注

- 少数专长条目末尾仍混入相邻章节的引言性文字（如多功能召唤自然盟友后的“简易召唤模板”引言），这是原文本本身无清晰边界导致，不影响分类归属。
- `page_667.md` 已接入 HTML 回退处理记录。

---

## UI-1：变体标题跨行且 Markdown 嵌套不统一

- **来源书**：极限诡道UI（Ultimate Intrigue）
- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：建议优化
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/极限诡道UI/变体_职业选项/page_350.md` ~ `page_1442.md`
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/职业/` 下各职业页面

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 在 `organize_ui.py` 的 `SECTIONS` 列表中为每个变体/职业选项条目配置显式 `marker`，覆盖以下混乱格式：
   - 中英文被多重 `**` 分隔：`**炼金爆破手**** Alchemical \nSapper****（炼金术士变体）****`
   - 英文跨行：`**僧官 Sage \nCounselor****（武僧变体）****`
   - 中英文之间无空格：`古老野心家ANCESTRAL \nASPIRANT（秘学士变体）`
   - 删除线包裹标题：`~~**密探~~ Cipher~~`
   - 纯职业选项标题：`**盗贼天赋：**`、`裁决：犯罪（Crime）UI`
2. 脚本按 `marker` 子串在源文件中定位条目起始行，按顺序截取到下一个条目起始行或文件末尾。
3. 在条目标题下一行插入 `> 来源：极限诡道（Ultimate Intrigue）UI，页码见原书，未整理 → 极限诡道UI → 变体/职业选项 → <职业>` 标注。
4. 通过隐藏标记 `<!-- UI-source:<source>:<title> -->` 与已知重复项 `duplicate_skip` 双重去重。

### 处理脚本/提交

- `organize_ui.py`
- `UI_reorganization_plan.json`
- `UI_reorganization_report.md`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 全部 71 个 `SECTIONS` 条目定位成功，运行 `organize_ui.py` 错误 0 条
- [x] 新增 8 条（page_1440.md、page_497.md 等未处理条目），跳过 63 条（已有 hidden_marker 或已知重复）
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 无重复 hidden_marker
- [x] `UI_reorganization_report.md` 与 `UI_reorganization_plan.json` 已更新
- [x] `organize_ui.py` 幂等运行（多次运行新增 0 条，跳过 63 条，错误 0 条）
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 逐个检查 `变体_职业选项/` 下所有 `page_*.md` 文件的首部标题格式。
2. 为每个条目选取稳定、唯一的 `marker` 子串。
3. 对 4 个已知重复项（炼金爆破手、审讯官、黑蝰僧、僧官）配置 `duplicate_skip=True`，避免与目标文件中已有条目冲突。
4. 运行 `organize_ui.py` 验证幂等性，确认无新增、无错误。

### 备注

- 当前方案通过显式 marker 解决了标题格式不统一导致的定位难题，已可交付。
- 若后续上游 HTML→Markdown 转换规则统一了标题格式，可改用通用正则解析，减少人工 marker 维护成本。

---

## UI-2：已有组织文件包含同名条目，去重逻辑依赖人工标记

- **来源书**：极限诡道UI（Ultimate Intrigue）
- **问题归类**：`条目归属待确认` / `脚本限制`
- **严重程度**：需要人工校验
- **涉及文件**：
  - `pf_data/phase1/pf_rules_md/未整理/极限诡道UI/变体_职业选项/page_353.md`（炼金爆破手、审讯官）
  - `pf_data/phase1/pf_rules_md/未整理/极限诡道UI/变体_职业选项/page_358.md`（黑蝰僧、僧官）
- **目标文件**：
  - `pf_data/phase1/pf_rules_md_organized/职业/基础职业/炼金术师/全变体未整合.md`
  - `pf_data/phase1/pf_rules_md_organized/职业/掉链子（Unchained）/武僧/职业变体汇总1.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 人工对比源文件与目标文件中 4 个变体的详细描述：
   - **炼金爆破手 / Alchemical Sapper**：源文件与目标文件（标题为“炼金工兵”）的核心能力一一对应：弱化炼金术/化合炼成削减、地崩炸弹/爆破炸弹、延时炸弹/定时炸弹、迷彩炸弹、绊线雷、选择性引爆/引爆时点。目标文件额外包含 `工程学大师`，整体更完整。
   - **审讯官 / Interrogator**：源文件与目标文件均包含本职技能、注射针剂、生化血清（乖乖水/魅惑、合作药/遵从、晕头药/困惑、迷魂药/迷魂、记忆修正、麻药/定身、吐真剂/诚实），能力结构与效果完全一致。
   - **黑蝰僧 / Black Asp**：源文件与目标文件的宗派背景、黑蝰之道、秘功绝学列表（蚀骨蛇牙、无念、无尘埃、无尘、无定）完全一致。
   - **僧官 / Sage Counselor**：源文件与目标文件的背景描述、本职技能、迷踪拳、无相绝影、妙法能力完全一致。
2. 判定 4 个变体均为**同一规则的不同翻译/格式版本**，保留目标文件中的原条目，不再从未整理源文件追加。
3. `organize_ui.py` 中已对上述 4 项设置 `duplicate_skip=True`，脚本运行时自动跳过并记录到 `未整理目录重复记录.md`。

### 处理脚本/提交

- `organize_ui.py`
- `未整理目录重复记录.md`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 已读取源文件 `page_353.md`、`page_358.md`
- [x] 已读取目标文件 `全变体未整合.md`、`职业变体汇总1.md`
- [x] 4 个变体均判定为重复，保留原条目
- [x] `organize_ui.py` 运行未追加这 4 个条目（新增 8 条均为其他条目）
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 逐项比对中英文能力与描述。
2. 确认目标文件版本与源文件版本内容覆盖度，避免误删更完整的版本。
3. 运行 `organize_ui.py` 验证跳过行为。

### 备注

- 炼金爆破手的目标文件译名为“炼金工兵”，与源文件“炼金爆破手”不同；全局去重阶段如需统一译名，建议保留目标文件更完整的版本（含工程学大师）。
- 该 4 项的重复判定逻辑已沉淀为 `duplicate_skip` 示例，后续遇到同名变体可复用。

---

## MC-2：同一物品在不同文件中翻译不一致

- **来源书**：怪物法典MC（Monster Codex）
- **问题归类**：`条目归属待确认` / `其他`
- **严重程度**：影响轻微
- **涉及文件**：
  - `pf_data/phase1/pf_rules_md/未整理/怪物法典MC/page_1407.md`
  - `pf_data/phase1/pf_rules_md/未整理/怪物法典MC/其他物品1.md`
- **目标文件**：
  - `pf_data/phase1/pf_rules_md_organized/其他物品1.md`
  - `pf_data/phase1/pf_rules_md_organized/种族/怪物种族/怪物法典MC/大地精.md`
  - `pf_data/phase1/pf_rules_md_organized/种族/怪物种族/怪物法典MC/其他物品.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 人工复核两个译名版本的 `Fervor Juice`：
   - **怒气饮（Fervorjuice）**（`page_1407.md` 大地精装备）：价格 50GP，重量 -，效果为获得 1 小时**凶猛（Ferocity）**通用怪物能力，制造 DC 20 手艺（炼金术）。
   - **凶猛药水（Fervor Juice）**（`其他物品1.md`）：价格 50gp，重量 -，效果为获得 1 小时**凶猛（Ferocity, Ex）**特性，制造 DC 20 工艺（炼金）。
2. 判定两者为**同一物品的不同中文译名**。
3. 按“保留原条目，跳过重复”原则处理：
   - 保留 `pf_rules_md_organized/其他物品1.md` 中的“凶猛药水”作为通用物品原条目；
   - 保留 `pf_rules_md_organized/种族/怪物种族/怪物法典MC/大地精.md` 中的“怒气饮”作为大地精种族装备上下文；
   - 删除与 `其他物品1.md` 完全重复的 `pf_rules_md_organized/种族/怪物种族/怪物法典MC/其他物品.md`。

### 处理脚本/提交

- `organize_mc.py`（未修改，因 `其他物品.md` 非其 RACE_FILES 生成）
- Git commit: 见项目 `git log`

### 验证结果

- [x] 已读取 `page_1407.md` 与 `其他物品1.md` 中 Fervor Juice 条目
- [x] 已确认两版本为同一物品
- [x] 已删除完全重复的 `种族/怪物种族/怪物法典MC/其他物品.md`
- [x] `其他物品1.md` 与 `大地精.md` 中仍保留各自版本
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 逐项比对价格、重量、效果、制造 DC。
2. 确认 `organize_mc.py` 不会重新生成 `其他物品.md`。
3. 决定保留 `大地精.md` 中的条目以维持种族文件完整性。

### 备注

- 全局去重阶段可统一译名为“凶猛药水”或“怒气饮”，并将 `大地精.md` 中的条目链接/合并到通用物品条目。
- 该案例说明同一物品在不同上下文中可能使用不同译名，全局去重阶段需建立中英/译名对照表。

---

## AA-2：炼金术师变体中文译名不一致

- **来源书**：水下冒险（Aquatic Adventures）
- **问题归类**：`条目归属待确认`
- **严重程度**：影响轻微
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/水下冒险Aquatic Adventures/page_1033.md`
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/职业/基础职业/炼金术师/全变体未整合.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 人工复核 AA 源文件中的“海洋化学家（Aquachymist）”与目标文件中的“深潜化学家（Aquachymist）”。
2. 确认两版本能力完全一致：
   - 本职技能：游泳替换飞行
   - 密封炼成/密闭炼成：化合炼成和突变药剂生成防水外壳
   - 深水炸弹/蒸汽炸弹：火焰炸弹造成蒸汽伤害，水下射程增量 5 尺
   - 两栖突变药剂：2 级可在水中和空气中呼吸
3. 判定为同一变体的不同中文译名，`organize_aquatic_adventures.py` 按英文名 `Aquachymist` 检测并跳过追加，保留目标文件中的“深潜化学家”。

### 处理脚本/提交

- `organize_aquatic_adventures.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 已读取源文件 `page_1033.md` 与目标文件 `全变体未整合.md`
- [x] 已确认“海洋化学家”与“深潜化学家”为同一 Aquachymist 变体
- [x] 运行 `organize_aquatic_adventures.py`：合并 0 项，跳过 19 项，无错误
- [x] 目标文件中未新增“海洋化学家”条目
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 逐项比对四个职业能力。
2. 运行脚本验证跳过行为。

### 备注

- 全局去重阶段建议统一译名为“深潜化学家”，并保留目标文件版本。

---

## AA-3：骑将骑士团目标位置未在映射表中明确

- **来源书**：水下冒险（Aquatic Adventures）
- **问题归类**：`目标位置待确认`
- **严重程度**：影响轻微
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/水下冒险Aquatic Adventures/page_1033.md`
- **目标文件**：
  - `pf_data/phase1/pf_rules_md_organized/职业/基础职业/骑将/page_23.md`
  - `pf_data/phase1/pf_rules_md_organized/职业/基础职业/骑将/page_1212.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 人工复核 AA 源文件中的“波涛骑士团（Order of The Waves）”与 `page_1212.md` 中的同名骑士团。
2. 确认两者内容完全一致：守则（探索海底秘密）、挑战（水下豁免加值）、技能（知识地理/察觉）、波涛骑手、水流冲击、探索七海。
3. 判定为同一骑士团，`organize_aquatic_adventures.py` 跳过追加到 `page_23.md`，保留 `page_1212.md` 中的原条目。

### 处理脚本/提交

- `organize_aquatic_adventures.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 已读取源文件 `page_1033.md` 与目标文件 `page_1212.md`
- [x] 已确认两版本为同一波涛骑士团
- [x] `page_23.md` 中未出现波涛骑士团内容
- [x] 运行 `organize_aquatic_adventures.py`：合并 0 项，跳过 19 项，无错误
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 逐项比对骑士团守则、挑战、技能与三个能力。
2. 确认 `page_23.md` 仅作为骑士团索引页面，具体内容收录于 `page_1212.md`。

### 备注

- 全局去重阶段如需将骑士团统一归到 `page_23.md`，需先评估 `page_1212.md` 的定位；当前建议维持 `page_1212.md` 作为骑士团聚合文件。

---

## UW-PAGE1429：护林官与巡林客内容重复

- **来源书**：极限荒野（Ultimate Wilderness）
- **问题归类**：`条目归属待确认`
- **严重程度**：影响轻微
- **涉及文件**：`pf_data/phase1/pf_rules_md/未整理/极限荒野UW/page_1429.md`
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/职业/混合职业/猎人/page_104.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 人工复核 `page_1429.md` 中的两个猎人变体：
   - 护林官 / Forester
   - 巡林客 / Forester
2. 确认两者英文名相同（Forester），中文译名不同，能力描述几乎完全相同，判定为**同一变体的不同翻译**。
3. `organize_uw.py` 只合并 `人猿泰山` 变体，跳过护林官/巡林客，避免重复追加。

### 处理脚本/提交

- `organize_uw.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 已复核 `page_1429.md` 中护林官与巡林客条目
- [x] 已确认两者为同一 Forester 变体的不同译名
- [x] 目标文件中未重复追加该变体
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 对比两个条目的英文名与中文描述。
2. 确认 `organize_uw.py` 已正确跳过重复。

### 备注

- 全局去重阶段可统一译名为“护林官”或“巡林客”，当前无需重复合并。

---

## EMH-FEATS：元素大师手册区域专长章节标题含英文后缀且部分条目以地区描述开头

- **来源书**：元素大师手册（Elemental Master's Handbook）EMH
- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：影响中等
- **涉及文件**：
  - `pf_data/phase1/pf_rules_md/未整理/元素大师手册EMH/专长/page_1111.md` ~ `page_1114.md`
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/专长/元素大师手册EMH_专长.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 在 `html_fallback.py` 中注册 6 个 EMH 专长源文件（page_1111~page_1114 与 page_1116~page_1117），通过 `read_source_text()` 获取 HTML 清洗后的 Markdown。
2. 在 `organize_emh.py` 中新增 `REGIONAL_FEATS` 列表，按 `[火水土气]之域` 四个区域分节提取。
3. 将分节正则从 `\*\*[火水土气]之域\*\*` 放宽为 `\*\*[火水土气]之域[^*]*\*\*`，以匹配 `**火之域LANDS OF FIRE**` 这类带英文后缀的标题。
4. 每个区域内按 `****` 分隔为若干块；对每块在内部搜索专名行（如 `**日耀斩（Sun Strike）〔战斗〕**`），截取从该行开始到块尾的内容作为该专长条目。
5. 清洗每个专长块：移除空行、URL/译者行、残留的分隔星号线，保留 `> 来源：...` 标注与 `<!-- EMH-source:<文件>:<名称> -->` 隐藏标记。
6. 15 个区域专长全部合并到 `专长/元素大师手册EMH_专长.md`。

### 处理脚本/提交

- `organize_emh.py`
- `html_fallback.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 15 个区域专长全部出现在 `专长/元素大师手册EMH_专长.md`
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 无重复 hidden_marker
- [x] `organize_emh.py` 幂等运行（新增 0 条，跳过已存在条目，警告 0 条）
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 首次按 `block.startswith(name)` 提取时，`日耀斩`、`库拉贡敦姿态`、`风暴粉碎者`、`暴风拳` 等条目因块首为地区风味描述而失败。
2. 改为在块内搜索专名行并截取，成功定位全部 15 个专长。
3. 对 `暴风拳` 仅有中文名无英文名的标题做兼容，按原文保留。

### 备注

- 区域专长与地区描述紧密相关，当前保留地区描述作为条目正文前缀，便于阅读时理解专长背景。
- 建议后续人工复核 `库拉贡敦姿态` 等条目的正文起始位置是否自然。

---

## EMH-SPELLS：元素大师手册法术分节标题含英文后缀

- **来源书**：元素大师手册（Elemental Master's Handbook）EMH
- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：影响中等
- **涉及文件**：
  - `pf_data/phase1/pf_rules_md/未整理/元素大师手册EMH/法术/page_1103.md`
  - `pf_data/phase1/pf_rules_md/未整理/元素大师手册EMH/法术/page_1104.md`
- **目标文件**：`pf_data/phase1/pf_rules_md_organized/法术/元素大师手册EMH_法术.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 在 `organize_emh.py` 中接入 `html_fallback.py`，对 `page_1103.md`（水之法术）和 `page_1104.md`（气之法术）使用 HTML 清洗后的文本。
2. 新增 `SPELL_FILES` 配置，指定各文件要提取的章节（`水之法术`/`气之法术`）与目标文件。
3. 因章节标题为 `**水之法术SPELLS OF WATER**`、`**气之法术SPELLS OF AIR**`，标准 `extract_section()` 的字面匹配失效，改用正则：
   - 起始：`re.escape(cfg["section_start"].rstrip("*")) + r"[^*]*\*\*"`
   - 结束：下一个同模式章节标题或文件末尾
4. 在提取出的章节内使用 `detect_spell_starts()` 识别法术标题行，按顺序切片。
5. 清洗每个法术块：去除残留的分隔星号线，规范标题格式，保留来源标注与隐藏标记。
6. `page_1104.md` 还包含 `龙脉术士奖励法术` 等非法术段落，配置 `skip_before` 将其排除在气之法术章节之前。
7. 11 个法术全部合并到 `法术/元素大师手册EMH_法术.md`（6 个水法术 + 5 个气法术）。

### 处理脚本/提交

- `organize_emh.py`
- `html_fallback.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 11 个法术全部出现在 `法术/元素大师手册EMH_法术.md`（驱除血液、提升水位、涛言术、浪尘飞溅、群体浪尘飞溅、防水术、暴风术、携风术、避雷针、(治疗)复苏之风、迷雾之墙）
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 无重复 hidden_marker
- [x] `organize_emh.py` 幂等运行（新增 0 条，跳过已存在条目，警告 0 条）
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 首次使用 `extract_section()` 按 `**气之法术**` 精确匹配，结果未提取到气之法术。
2. 检查源文件后发现标题包含英文后缀，改用正则匹配带后缀的章节标题。
3. 验证水之法术 6 条、气之法术 5 条，共 11 条全部正确合并。

### 备注

- `(治疗)复苏之风` 源标题包含学派前缀 `(治疗)`，已按原文保留；若全局清洗阶段需要纯净名称，可再处理。
- 建议后续人工复核法术字段（学派、环级、成分等）是否被正确换行。

---

## EMH-ITEMS：元素大师手册物品名与引言内联

- **来源书**：元素大师手册（Elemental Master's Handbook）EMH
- **问题归类**：`markdown格式` / `标题定位` / `条目归属待确认`
- **严重程度**：影响中等
- **涉及文件**：
  - `pf_data/phase1/pf_rules_md/未整理/元素大师手册EMH/物品/page_1116.md`
  - `pf_data/phase1/pf_rules_md/未整理/元素大师手册EMH/物品/page_1117.md`
- **目标文件**：
  - `pf_data/phase1/pf_rules_md_organized/装备_魔法物品/武器/元素大师手册EMH_物品.md`
  - `pf_data/phase1/pf_rules_md_organized/装备_魔法物品/魔法物品/戒指_权杖_法杖/元素大师手册EMH_权杖.md`
  - `pf_data/phase1/pf_rules_md_organized/装备_魔法物品/魔法物品/奇物/元素大师手册EMH_奇物.md`
  - `pf_data/phase1/pf_rules_md_organized/装备_魔法物品/魔法物品/奇物/无位置/元素大师手册EMH_元素扩增.md`
  - `pf_data/phase1/pf_rules_md_organized/装备_魔法物品/货品服务/元素大师手册EMH_炼金物品.md`

### 处理状态

**已解决**

### 处理时间

2026-07-18

### 处理方式

1. 在 `organize_emh.py` 中接入 `html_fallback.py`，对 `page_1116.md` 和 `page_1117.md` 使用 HTML 清洗后的文本。
2. 新增 `EMH_ITEMS` 映射表，为 15 个物品指定中文名、英文名、子类型与目标文件。
3. 重写 `_extract_item_block()`：
   - 按 `****` 将页面拆分为若干块；
   - 在块内搜索物品名，找到后截取从该位置开始到块尾；
   - 若同一块内出现下一个物品名，则截取到下一个物品名之前；
   - 剔除章节引言（如“一些魔法物品利用宝石来获得元素的亲和。”）等前置文本。
4. 清洗每个物品块：移除空行、URL/译者行、冗余空加粗行，统一标题格式为 `**中文名（English Name）〔子类型〕**`。
5. 按子类型写入对应目标文件：
   - 武器 1 个：致密之锤
   - 权杖 1 个：石化权杖
   - 奇物 3 个：神秘皇冠、奇妙雕像（赤铁山狮）、宝石雕刻者工具
   - 元素扩增 7 个：灼手热臂、霜骨冰骸、快银之血、燃烧之血、蒸汽肺部、涡流之胃、火眼金睛
   - 炼金物品 5 个：水延剂、阿塔拉之光、腐朽沙砾、死地尘、土缚团块

### 处理脚本/提交

- `organize_emh.py`
- `html_fallback.py`
- Git commit: 见项目 `git log`

### 验证结果

- [x] 原目录 `pf_rules_md/` 未被修改
- [x] 15 个物品全部按子类型写入对应目标文件
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 无重复 hidden_marker
- [x] `organize_emh.py` 幂等运行（新增 0 条，跳过已存在条目，警告 0 条）
- [x] 问题记录已更新

### 未解决原因

无。

### 尝试过的努力

1. 首次尝试用 `block.startswith(name)` 定位，因 `致密之锤` 等物品名紧接在引言同一行后而失败。
2. 改用块内搜索并截取，成功提取全部 15 个物品。
3. 对元素扩增条目之间缺少 `****` 分隔的情况，通过目标物品名列表顺序切片解决。

### 备注

- 建议人工复核元素扩增条目的字段标签与正文边界，尤其是属性标签是否独立成行。
- 部分物品标题中的子类型标签（如 `〔武器〕`、`〔权杖〕`）由脚本根据映射表补充，确保目标文件分类清晰。
