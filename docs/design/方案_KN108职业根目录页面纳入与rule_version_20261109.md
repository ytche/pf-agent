# 方案：KN108 职业根目录页面纳入与职业 rule_version 标注

日期：2026-11-09 / 状态：**已闭环 ✅（2026-11-10）**（2026-11-10 用户批准书面设计并批准实施；实施、验收与职业库重灌完成，DVG-014 清偿，测试报告 `docs/test-reports/测试报告_KN108职业根页面与rule_version_20261110.md`）

## 背景与目标

KN108：7 个职业相关源页面位于 `pf_data/phase1/pf_rules_md_organized/` **根目录**（不在 `职业/` 子目录内），职业流水线因路径收敛逻辑把它们整体排除，导致产物缺失：

- 当前职业产物 `vectorizer/output/职业/chunks.jsonl` 共 13922 块，7 个目标 doc_id 均为 0（无产出）。
- page_53 武僧 8 种清规全缺；page_134 龙徒本体全缺（龙脉血统扩展不能替代）；page_411 原版幻灵仅部分覆盖（UM 水生型等缺失）；page_30/128/244/609 整页缺失。
- 职业 chunk 无 `rule_version` 字段；现有先例：技能 `processors/skill.py:168` 用 `unchained`，规则 `processors/rule.py:421`、装备 `processors/equipment.py:735` 用 `book_abbreviation.lower()`。

本批同时完成两件事：① 显式清单纳入 7 个根目录页面；② 职业 chunk 增加 `metadata.rule_version`。

## 需求对照表

| 方案条目 | 对应需求/口径 | 说明 |
|---|---|---|
| §方案设计-1 显式清单（ROOT_PAGE_MANIFEST） | 拍板口径 1、2 | 7 文件保留原位，逻辑路径映射 |
| §方案设计-2 文件选择与 process 接入 | 拍板口径 1 | 复用现有扩展点，不移动/复制源文件 |
| §方案设计-3 rule_version 三级优先级 | 拍板口径 3 | 显式清单 > Unchained 路径前缀 > book 小写 |
| §方案设计-4 page_244 特殊化（class_overview + PFS 来源覆盖） | 拍板口径 4 | 数据驱动覆盖，非硬编码特判 |
| §方案设计-5 数据侧-only | 拍板口径 5 | Java Mapper 不改 |
| §实施步骤 TDD/CI/DVG/重灌/文档同步 | 拍板口径 6 | 含回滚方式 |
| 负向断言与结构不变量 | 项目红线 | 防误产、防回归 |
| 备选方案（移动源文件 / chm_toc 判定 / book=PU 判定） | 拍板口径 1、3 | 已否决，记录理由 |

无对应原始需求的新增条目：无（全部条目均可追溯）。

## 现状分析

### 排除根因（已核实）

- `formats/profession.py:19`：`INPUT_DIR = .../pf_rules_md_organized/职业`。
- `processors/profession.py:3274-3281` `_profession_file_condition()`：用 `file_path.resolve().relative_to(INPUT_DIR)` 收窄遍历范围。**7 个目标文件实际位于 `pf_rules_md_organized/` 根目录**（已用 `find` 核实：`page_30/page_53/page_128/page_134/page_244/page_411/page_609.md` 均不在 `职业/` 下），`relative_to` 抛 `ValueError` → 不匹配 profession 类目 → pipeline 永不派发 → doc_id 为 0。
- `processors/profession.py:3386-3401` `ProfessionProcessor.process()`：`abs_path.relative_to(INPUT_DIR)` 计算 `rel_path`，`rel_path` 是 doc_id（`create_processor` 内 `doc_id = rel_path.as_posix()`，见 :1992）、职业名推断（`infer_class_name(rel_path,...)`）、toc 解析（`resolve_chm_toc_path(rel_path,...)`，`formats/profession.py:56`）的统一输入。**给这 7 个文件一个“逻辑 rel_path”后，canonical/preprocess/process 链即可接管；真实产物验证追加的根页标题正文保留例外见方案设计 §2。**
- canonical 去重：`load_resources`（:3318-3346）固定 `INPUT_DIR.rglob("*.md")` 扫描，同样漏掉根目录文件。

### 目标文件与 toc（`pf_data/md_mapping.json` 实测）

| 文件 | toc_path | book_source |
|---|---|---|
| page_30.md | 职业 | null |
| page_53.md | 职业 → 核心职业 → 武僧 → 武僧清规 | null |
| page_128.md | 职业 → 进阶职业 | null |
| page_134.md | 职业 → 进阶职业 → CRB进阶职业 → 龙脉术士 | null |
| page_244.md | 职业 → 掉链子（Unchained） | null |
| page_411.md | 职业 → 基础职业 → 召唤师 → 幻灵 | null |
| page_609.md | 职业 → 神话冒险 | null |

### rule_version 判定的关键数据（拍板口径依据）

- 按 doc 路径前缀 `掉链子（Unchained）/` 判定：1060 块。
- 按 toc 前缀判定会多标 369 个核心职业/盗贼/野蛮人 chunk（toc 前缀不可靠）。
- 按 book=PU 判定只覆盖 785 块（不足）。
- **结论：必须按（逻辑）源文件路径判定**，与用户拍板一致。

### 先例（复用目标）

- 技能 `processors/skill.py:171-186`：模块级显式清单常量 `_UNCHAINED_B1_RELS` / `_UI_ROOT_FILES` / `_B2_REL_RULE_VERSION`，按 doc 相对路径映射 rule_version。**本方案清单放法与判定方式完全沿用此先例**（数据表，非 `if class_name == X` 流程特判）。
- 特化 Processor 注入：`create_processor`（:1961-1995）已按路径分派 Witch/Paladin/Oracle/Sorcerer/Warpriest/Summoner/Shifter 特化 Processor；page_411 默认沿用该分派。page_244 不新增 Processor 子类，只在 `_to_standard` 应用清单覆盖。

### 内容结构（验收锚点依据，已实测 grep）

- page_30（154 行）：职业概述 + 术语定义（核心/基础/施法者等级等大表格），粗体跨行标题。
- page_53（96 行）：武僧清规 + 不邪淫戒/囚执戒/清净戒/持斋戒/不杀生戒/安贫戒/不语戒/不妄语戒，共 8 戒，粗体星壳标题。
- page_128（181 行）：进阶职业 + 全进阶职业一览大表格。
- page_134（170 行）：龙徒（Dragon Disciple）角色定位/阵营/进阶要求正文，粗体星壳。
- page_244（19 行）：短文“有关新书Unchained对PFS官方游戏的影响”，PFS 官方 Blog 说明性质。
- page_411（980 行）：召唤师幻灵（Eidolon）完整正文 + 等级/生命骰/BAB/技能/专长表，跨行粗体严重。
- page_609（50 行）：神话冒险 6 条道途正文（大法师/斗士/守护者/圣者/统帅/诡术大师），无 Markdown 标题、全为粗体段。

## 方案设计

### 1. 显式根页面清单（新增唯一数据结构）

在 `processors/profession.py` 模块级新增常量（与 skill.py `_UNCHAINED_B1_RELS` 同风格）：

```
ROOT_PAGE_MANIFEST: Dict[str, RootPageSpec]   # key = 根目录文件名（如 "page_244.md"）
RootPageSpec 字段：
  logical_rel: str          # 职业模块内逻辑相对路径（posix 形式）
  rule_version: str|None    # 显式 rule_version 覆盖；None = 走默认三级优先级
  component_type: str|None  # 覆盖 component_type（仅 page_244 用 "class_overview"）
  book_override: dict|None  # 覆盖 book_abbreviation/book_name_cn/book_name_en（page_30/page_128/page_244，见 §4）
  class_name: str|None      # None = 不覆盖；空字符串 "" = 显式不归单职业（仅 page_244）
  processor: str|None       # 可选；None = 正常分派，"base" = 强制基础 Processor（仅冒烟证明有需要时启用）
```

应用覆盖时，`class_name` 仅在值不为 `None` 时写入；因此 `""` 不会被误当作“无覆盖”。其余可选字段同理，`None` 均表示不覆盖。

7 条目 logical_rel 按 toc 对齐（使路径判定/职业名推断/toc 前缀全部自然正确）：

| 文件 | logical_rel | rule_version | 其他覆盖 |
|---|---|---|---|
| page_30.md | 职业概述/page_30.md | None（默认→crb） | book_override=CRB（§4.1） |
| page_53.md | 核心职业/武僧/武僧清规/page_53.md | None | — |
| page_128.md | 进阶职业/page_128.md | None（默认→crb） | book_override=CRB（§4.1） |
| page_134.md | 进阶职业/CRB进阶职业/龙脉术士/page_134.md | None | — |
| page_244.md | 掉链子（Unchained）/page_244.md | unchained | component_type=class_overview，class_name=""，book_override 见 §4 |
| page_411.md | 基础职业/召唤师/幻灵/page_411.md | None | 默认正常分派；processor="base" 仅作风险回落 |
| page_609.md | 神话冒险/page_609.md | None | — |

注意：logical_rel 只是逻辑路径，**不创建任何真实目录**；`abs_path` 始终指向源文件原位，读写源文件不变（红线）。

### 2. 接入点（三处入口，均为既有扩展点）

1. **文件选择**：`_profession_file_condition`（:3274）扩展为“`relative_to(INPUT_DIR)` 成功 **或** 文件名在 ROOT_PAGE_MANIFEST 且文件位于 `pf_rules_md_organized/` 根目录”。判定用 `file_path.parent == INPUT_DIR.parent` + 文件名查表，不引入新框架。
2. **canonical 去重与预扫描**：`load_resources`（:3318）在 `INPUT_DIR.rglob("*.md")` 之后追加遍历 `ROOT_PAGE_MANIFEST` 指向的 7 个文件（按字节哈希同样过 canonical 去重，逻辑不变）；canonical 集仍存 resolve 后绝对路径，现有 process 的 `abs_path in self._canonical_paths` 判断兼容。canonical 后的变体主表预扫描也消费同一逻辑 `rel_path`，不得对根页面直接调用 `file_path.relative_to(INPUT_DIR)`，否则会在 process 前抛 `ValueError`。
3. **process 派发**：`ProfessionProcessor.process`（:3386）在 `rel_path = abs_path.relative_to(INPUT_DIR)` 处改为：先尝试 `relative_to(INPUT_DIR)`，失败且文件名在清单内 → `rel_path = Path(spec.logical_rel)`。此后 `create_processor` / `clean_file` / `infer_class_name` / `resolve_chm_toc_path` 全部消费逻辑路径，数据流与目录内文件完全一致。源文件读取仍用 `abs_path`（`FileProcessor` 构造传 `file_path=abs_path`）。

数据流变化：仅“rel_path 的来源”一处分叉；既有页面的 clean/split/expand/merge/9 Provider 来源链零回归。真实产物复核发现根页的粗体标题可能在清洗后从 text/title 同时消失，因此仅对清单 7 页在 clean 后把每个 Markdown 标题保留一份为正文文本，满足锚点不得丢失的验收要求；不放宽锚口。`vectorizer/build_manifest.json` 的 `chunks.profession.inputs` 必须另加 7 个根目录源文件的精确路径，确保统一构建能追踪这些新增输入。

### 3. rule_version 三级优先级（在 `_to_standard` 注入）

在 `ProfessionProcessor._to_standard`（:3403）的 metadata 构造中新增 `rule_version`。清单覆盖统一通过 `chunk.doc_id == spec.logical_rel` 找到目标条目，不得只用 basename 查表，避免职业目录内同名文件误套用根页面覆盖。取值优先级：

1. **显式清单覆盖**：匹配到的 `RootPageSpec.rule_version`（page_244 → `unchained`）。
2. **Unchained 路径前缀**：chunk 的 doc_id（逻辑路径）以 `掉链子（Unchained）/` 开头 → `unchained`。判定依据为**源文件逻辑路径**，不使用 chm_toc_path、不使用 book=PU（数据依据见现状分析）。
3. **默认 book 小写**：`c.book_abbreviation.lower()`，与规则 `processors/rule.py:421`、装备 `processors/equipment.py:735` 同惯例。
   - book 为空 / 为占位符（"?"或空串）→ **不写 rule_version 键**（保持 metadata 稀疏，与现有 None 字段处理一致），并在现行 `verify_profession` 验收报告中统计数量；不新增旧脚本 quality_report 的第二写出通道。

仅加字段，不重排既有 metadata 键序中已有键。

### 4. page_244 特殊化（数据驱动，走既有覆盖机制）

- component_type 覆盖为 `class_overview`、class_name 通过清单空字符串 `""` 显式置空：**不**新增流程特判，由清单的 `component_type`/`class_name` 字段在 `_to_standard` 统一应用（清单内全部条目适用，只是仅 page_244 取值非 None）。
- 来源书：正文为 PFS 官方 Blog 说明，md_mapping `book_source=null`，不应默认成 PU。复用机制 = **manifest `book_override`**（数据表驱动的来源字段覆盖），避免为单页新增 Processor 子类。固定覆盖值：
  - `book_abbreviation="PFS"`
  - `book_name_cn="探索者协会"`
  - `book_name_en="Pathfinder Society"`
- `rule_version` 仍由清单显式设为 `unchained`，不得因 `book_abbreviation="PFS"` 而经默认规则写成 `pfs`；不使用 `pfs_eligible`，本批不引入该字段。

### 4.1 page_30/page_128 核心规则书（CRB）来源裁定（Task 4 补记）

**裁定**：page_30、page_128 经清单 `book_override` 登记 CRB 来源，覆盖值与代码实际一致：

- `book_abbreviation="CRB"`
- `book_name_cn="核心规则书"`
- `book_name_en="Core Rulebook"`

两页 rule_version 不设显式清单值，走 §3 默认第 3 级「book 小写」→ `crb`。

**源文依据**（`pf_rules_md_organized/`，行号为清洗前原始文件）：

- `page_30.md:56`：术语定义正文自述「核心规则书（CRB）中出现的11项标准职业之一」——该页为 CRB 职业概述章节材料。
- `page_128.md:22`：全进阶职业一览表首行「进阶职业 | CRB | 魔射手（Arcane Archer） | …」。
- `page_128.md:64-67`：一览表出处列连续「核心规则书CRB」（魔射手/诡术师/刺客/龙脉术士等）。

**背景与后果**：md_mapping 中两页 `book_source=null`（§目标文件与 toc 表），9 Provider 链无法从路径/标记解析来源；若不加覆盖，真实产物这两页全部 chunk 的 `book_abbreviation` 为占位「?」。原方案（本文初版）口径为 book=null 不覆盖、rule_version 省略计 5（page_30×4、page_128×1）。Task 4 全量重建时该省略使数据不变量闸口 `book '?' ≤ 0`（顶格棘轮）无法满足，且「保留根页标题锚点」修正救回的锚点块同样带「?」。为避免触碰棘轮参数、并为两页内容给出真实归属，按 page_244 同一 `book_override` 机制登记 CRB。**最终真实产物因此无空/? 来源省略：rule_version 标注 14060/14060、省略 0，数据不变量 `book '?' 0/0` 通过。**如后续对 CRB 归属有异议，走 KN 裁定改 `book_override` 即可，不涉及棘轮参数与闸口断言。

### 5. 明确不改的部分

- Java `StandardChunkMapper` / `ProfessionChunkMapper` 不转发 `rule_version` —— **本批不改 Java**。Java 模型可读取完整 `metadata` Map，但现有 Mapper 不为 `rule_version` 暴露专用字段；检索端消费方式后续单独立项。
- 不动 `merge_small_blocks` / 9 Provider 来源链 / POSTPROCESSORS；清洗链仅增加清单 7 页的标题正文保留，不改变任何既有页面。
- 其他模块（专长/法术/种族等）的 unchained/PU 口径统一 —— 不在本批。

## 备选方案与取舍

1. **把 7 个文件移动/复制进 `职业/` 对应子目录**（拒绝）：改动源数据布局，触碰“不得修改源 Markdown/源数据组织”红线；且 page_30/128/609 无自然归属子目录。拍板口径 1 已否决。
2. **按 chm_toc_path 前缀判定 Unchained**（拒绝）：会多标 369 个核心职业/盗贼/野蛮人 chunk（见现状分析实测数据）。拍板口径 3 已否决。
3. **按 book=PU 判定 Unchained**（拒绝）：只覆盖 785 块，漏 275。已否决。
4. **为 page_244 新增专用 Processor 子类**（不选）：可行但为 19 行短文引入类不值得；清单数据驱动 + 既有 `_to_standard` 覆盖即可，与 skill.py 清单先例一致。
5. **只纳入不修 rule_version**（不选）：两次全量重灌成本高，一次做完更省（拍板口径 6 已含）。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| page_411 逻辑路径含“召唤师” → `create_processor` 命中 SummonerProcessor 特化逻辑，行为与目录内召唤师页不同 | 实施时先用单文件冒烟跑 page_411，比对 chunk 结构；仅当冒烟证明 SummonerProcessor 对该页正文或结构有害时，才在清单追加 `processor: "base"`，回落基础 Processor；否则保持正常分派 |
| page_609 无 Markdown 标题、纯粗体段 → 可能整页合并成 1–2 个大块或块标题异常 | 验收锚点以 6 条道途正文（大法师/斗士/守护者/圣者/统帅/诡术大师）必须出现在 chunk text 为准，不强求标题形态 |
| page_30/128 大表格被 MIN/MAX_CHUNK_CHARS 切碎或吞并 | 锚点断言表格关键词（术语定义/全进阶职业一览）存在；数量断言给区间而非精确值 |
| `pf_rules_md_organized/` 根目录中清单外文件被误纳入 | 清单按“根目录 + 精确文件名”匹配；负向断言确保清单外根目录文件不因本批新增职业 chunk |
| canonical 去重新纳入文件与职业目录内文件字节相同 | 走既有哈希去重，若命中已存在文件则按 `_canonical_score` 裁决，行为不变 |
| 产物是 Java 输入 | 完成后登记 DVG 并全量重灌职业库，不走 Java 元数据重放第二写路径（见待办汇总 DVG-001 方向） |
| 冻结红线 | 不修改任何源 md、不动 Java；既有页面块层零回归，仅清单 7 页保留清洗后标题正文。按红线列结构不变量并补真实产物负向测试（见验收标准） |

## 验收标准草案

### 结构不变量（重灌前后逐条核对，防回归）

1. 既有 13922 块中**非 7 目标文件来源**的 chunk：`chunk_id`、`doc_id`、`toc`、`class_name`、`title`、text 逐字段完全一致（即本批零回归）。
2. 全部 chunk_id 全局唯一；doc_id 非空且不出现字面 "0"。
3. page_411 纳入后，重灌前既有召唤师目录页 chunk 的 class_name/component_type 分布不变。
4. 既有 chunk 的 metadata 新增键仅 `rule_version`，其余键集不变。

### 数量与去重

5. 7 个 doc_id 各产出 ≥1 chunk；总块数在 13922 + 预期增量区间内（增量由单文件冒烟实测登记，测试记录具体值；防误产上限：单页块数不超过该页按 MAX_CHUNK_CHARS 估算上限）。
6. 以 doc_id 分组无 chunk_id 重复；以 (doc_id, title) 检查无非空重复标题块（表格切碎导致的同名空块为 0）。

### 每页正文锚点（必须出现在对应 doc_id 的某 chunk text 中）

| 页 | 最小锚点 |
|---|---|
| page_30 | “职业概述”、“术语定义”、“施法者等级” |
| page_53 | “武僧清规”、“不邪淫戒”、“囚执戒”、“清净戒”、“持斋戒”、“不杀生戒”、“安贫戒”、“不语戒”、“不妄语戒”（8 戒全到） |
| page_128 | “进阶职业”、“全进阶职业一览” |
| page_134 | “龙徒”、“进阶要求”、“角色定位” |
| page_244 | “Unchained对PFS官方游戏的影响”（或“对PFS官方游戏的影响”子串） |
| page_411 | “幻灵”、“生命骰”、“基本攻击加值”、“技能”、“专长” |
| page_609 | “大法师”、“斗士”、“守护者”、“圣者”、“统帅”、“诡术大师”（6 道途全到） |

### rule_version 断言

7. `doc_id` 以 `掉链子（Unchained）/` 开头的所有 chunk `rule_version == "unchained"`（含目录内既有 1060 块的口径确认：本批起它们也带 rule_version，值恒为 unchained）。
8. 核心职业/盗贼/野蛮人 chunk 的 rule_version **不等于** unchained（负向，防 toc 误标回归）。
9. 非 Unchained 职业 chunk：book_abbreviation 非空非 "?" 时 `rule_version == book_abbreviation.lower()`；book 为空或 "?" → 无 rule_version 键。
10. page_244 chunk：`rule_version == "unchained"`、`component_type == "class_overview"`、`class_name` 为空、`book_abbreviation == "PFS"`、`book_name_cn == "探索者协会"`、`book_name_en == "Pathfinder Society"`、无 `pfs_eligible` 键。

### 负向断言（防误产）

11. 清单外的 `pf_rules_md_organized/` 根目录文件不得因本批新增职业 chunk；职业目录内既有文件由结构不变量 1 的“非目标块零回归”覆盖。
12. 7 页的 `metadata.source_paths == [doc_id]`，且二者都等于清单 `logical_rel`；不得把逻辑目录误当真实物理目录创建，文件选择测试须证明实际读取仍来自整理目录根层。
13. 7 个源文件字节级哈希与变更前一致（证明未动源数据）。

## 实施步骤建议

1. **TDD 红**：先写测试（职业 processors 测试目录新增清单映射/rule_version 优先级/page 锚点用例；负向断言用例），跑红。
2. **批次 1（单文件冒烟）**：实现清单 + 三处接入；先单跑 page_244 与 page_411（SummonerProcessor 分派验证点），人工核对 chunk 结构，登记每页预期块数。
3. **批次 2（全 7 页 + rule_version）**：实现 `_to_standard` 注入；全量重跑职业 pipeline；产出新 chunks.jsonl + quality_report。
4. **批次 3（验证）**：执行验收标准全部条目（结构不变量比对脚本 + 锚点脚本）；跑职业完整 cicd 验证 + 全量数据测试。
5. **批次 4（交付）**：按项目规则登记 DVG（数据产物变更）；全量重灌职业向量库（不走 Java 元数据重放路径）；更新 KN108 记录与 `docs/一期当前待办与问题汇总_临时.md`。
6. **回滚**：数据侧改动集中于 `processors/profession.py` 单文件与产物；回滚 = revert 该文件 + 用上一版 chunks.jsonl 重灌职业库。源数据全程未动，无需回滚源侧。

### 交付记录（2026-11-10 闭环补记）

- 实施按 `docs/superpowers/plans/2026-11-10-kn108-profession-root-pages-rule-version.md` 五个 Task 执行完毕；真实产物 14060 块（13922→+138，全部新增限于 7 个 logical doc_id），旧块零回归（唯一差异 = 旧块 metadata 新增 `rule_version`）。
- 真实产物复核新增两处本方案初版未预见的修正（已在 §2、§4.1 记明）：① 根页标题行经「标题→title」剥离后锚点不出现在 text，闸口检查 10 在真实产物上失败，遂对清单 7 页在 clean 后保留标题纯文本副本并对携带锚点副本块加 keep() 豁免（≤5000 字符守卫）；② page_30/page_128 登记 CRB 来源（book_override），原「rule_version 省略 5」口径作废，终态标注 14060/14060、省略 0。
- 验收：职业 CICD 完整链（集成验收 11/11、不变量全过）、全量 pytest 1848、源哈希 7/7、双跑指纹一致、build check 14/14；职业向量库全量重灌 14060 条（DVG-014 清偿）。102 个历史重复 chunk_id 为既有债，登记不修。
- Java 侧零改动（本批不改 Mapper，rule_version 不暴露专用字段）；KN108 已闭环。
- 追加修复（合并验证暴露，2026-11-10，TDD）：`vectorizer/build.py::expand_inputs()` 的 glob 输入曾把 `.DS_Store` 计入内容指纹，致主工作区合并后 chunks.feat/race/equipment/profession 输入指纹失败；最小修复为展开时忽略 basename `.DS_Store`（不动显式 config_deps/script 语义），RED→GREEN 后全量 pytest 1848、build check 14/14，产物与 state 零变化——构建链文件不在本方案原范围/交付清单内，此处补记为 KN108 合并验证追加修复（详见测试报告 §6.1）。

## 不在本次范围

- Java 路由 / Mapper 转发 rule_version、检索端消费逻辑。
- `pfs_eligible` 字段扩展。
- 其他模块（专长/法术/种族/规则/装备）unchained vs pu 口径统一。
- `pf_rules_md_organized/` 整理目录根层的其他未登记文件纳入（潜在后续批次）。
- 既有产物中非本批引入的 chunk 质量问题（如发现，登记新问题，不在本批顺手修）。
