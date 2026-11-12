# Agent 已知问题记录

> 记录 PathFinder 1e 问答 Agent（`pf_agent/agent`）在问答/检索过程中暴露的问题。
> 创建日期：2026-07-31
> 后续按优先级逐个处理；每个问题闭环后更新状态与结论。
> 编号 AKN 与数据清洗侧 `pf_data/phase1/已知问题记录.md` 的 KN 编号独立，避免混淆。

## 状态约定

- `待处理` / `处理中` / `已修复` / `暂缓` / `决定不修`

---

## AKN-001：列举式提问（如「女巫1环法术都有哪些」）返回结果不对

### 状态

已修复（2026-08-11，searchByMetadata 枚举式过滤 + LLM 决策链）

**终态闭环（2026-10-29，2026-10-30 复测修正数字）**：AKN-001 的"完整列表"诉求在 AKN-015 排查中暴露清单口径缺口后彻底收口——A（spell_level 元数据清洗，KN242，空率 34.8%→10.1%）+ B1（派生补充清单，`spell_lists_union.json`，KN247）+ getSpellList 分页。端到端实测（2026-10-30 重跑，jar 重建 + 8090 实例）：「女巫 1 环法术」getSpellList 头部显示 **207 条**（68 官方清单页 + 139 派生；KN248 清假环级后为 **205 条 / 去重 167**），agent 分页取全（1~122、123~207），footer「已翻完全部结果（共 207 条）」。

口径说明：207 是**条目数**，同一法术在不同书/汇编页各占一条，去重后为 **169 个不同法术**（KN248 后 **167 个**；38 条重复，如雪球术 ×3、速凝术 ×3、读唇者视力 ×2）；原记「199 条」是 2026-10-29 union 22722 快照的条目数，KN244/246 重建 union 后失效。去重已于 2026-10-30 拍板「必做」（book 是否多值待定），衍生问题清单见 F-025（待修复）。

### 问题描述

用户提出「女巫1环法术都有哪些」这类**列举/聚合式**问题时，返回结果不正确——只做了相似度搜索，没有对句子的语义进行理解，无法给出完整列表。

### 复现方式

- 提问：`女巫1环法术都有哪些`（以及任意「职业 + 环级」组合的同类提问）
- 期望：返回女巫职业 1 环法术的**完整列表**
- 实际：只检索到与问题向量最相似的 topK 片段，未覆盖全部条目，LLM 基于残缺上下文作答

### 根因分析

当前 RAG 管线（`ChatService` → `SearchService`）对**所有**问题统一走向量相似度检索：

- `SearchService.search()` 固定 `topK=5`、`similarityThreshold=0.5`
- 「女巫1环法术都有哪些」本质是**结构化集合查询**（条件：职业=女巫、环级=1），需要按条件**全量召回**再列举，而不是找最相似的 5 个片段
- 向量检索对「事实点查」（如「火球术射程是多少」）有效，对「枚举集合」天然不适用——topK 截断导致列表不全

### 期望行为

能识别查询意图，区分两类问题：

1. **事实点查**：走现有向量检索（如「火球术射程是多少」）
2. **列举/聚合查询**：解析条件（职业、环级、学派等）→ 走 metadata 结构化过滤 + 全量召回 → LLM 组织成列表回答

### 影响范围

- 所有「XX职业 N 环法术有哪些」「XX 专长有哪些」类列举提问
- 当前 26 职业法术列表召回验收 258/259 ≈ 99.6%（2026-07-30 通过），说明**数据侧已有列表能力**，缺口在**问答层的检索策略**未利用该能力

### 处理方案（已实施）

**实现路径（与最初设想的独立 Intent Router 分类器不同）**：不写死意图分类，改为把 `searchByMetadata`（元数据枚举式过滤）暴露为第二个底层检索工具，让 **LLM 在工具决策链中自主判断**——列举/聚合类问题走 metadata 结构化过滤 + 全量召回，事实点查类走 `vectorSearch` 语义检索。这更贴合"检索策略交给 LLM 决策"的架构。

落地提交：

- `d5cf307 feat(agent): FilterTranslator + SearchService.searchByMetadata 枚举式过滤` —— FilterTranslator 逻辑字段→扁平键翻译（如 className+level），大 topK 枚举
- `42068ff feat(agent): RetrievalTools 三个底层 @Tool — 工具面落地` —— `searchByMetadata` 暴露为 `@Tool`（描述"元数据精确过滤（枚举式）"，module 8 模块 + filters 多条件 AND）

可配置项：`pf.search.enumeration-top-k`（默认 500，枚举上限，防超大集合）。

### 端到端验证（2026-08-12，闭环确认）

真实提问「女巫 1 环法术都有哪些」：返回 **3628 字完整清单**，按来源书分组（核心规则书 CRB → APG 等），表格形式含法术名 / 学派 / 子学派列。列举类问题不再被 topK 截断，成功走 `searchByMetadata` 全量召回路径。

### 教训与约定

- **方案落地 ≠ 文档同步**：AKN-001 的技术方案早在 `d5cf307`/`42068ff` 就已实现，但本记录状态长期停留在「待处理」，直到用户凭记忆质疑才被查证发现——与数据侧「审计后必更新 KN 状态」同型。**任何技术方案落地的提交，应同步闭环对应 AKN 文档**。

---

## AKN-002：AgentApplicationTests 未 mock 的 DataLoader 触发真实向量库导入，卡死集成测试

### 状态

已修复（2026-08-10）

### 问题描述

接入 6 个标准模块（feat/race/trait/equipment/skill/rule）向量库后，`mvn test` 卡住数十分钟不结束。定位为 `AgentApplicationTests`（`@SpringBootTest`）只 mock 了 `ClassDataLoader`/`SpellDataLoader`，新增的 6 个 DataLoader 未被 mock——Spring Boot 集成测试启动上下文时会执行其 `CommandLineRunner.run()`，而对应 store 文件首次缺失，于是真实读取 JSONL 并调用 Ollama BGE-M3 做 embedding（22K chunks 需数分钟以上），阻塞测试。

### 教训与约定

- **任何新增模块 DataLoader 后，`AgentApplicationTests` 必须同步新增对应 `@MockBean`**，否则集成测试会触发真实数据构建
- 验证 `mvn test` 是否被卡：观察 `target/surefire-reports/` 报告数量是否持续不增长、`~/.pf_agent/vector_store_*.json` 是否出现非预期新文件（本次意外构建出 `vector_store_rules.json` 114MB，虽完整有效，但属测试副作用）
- 数据构建逻辑（导入/embedding）不属于 contextLoads 验证范围，由 `ChunkImporterTest`/`*DataLoaderTest`/`StandardChunkMapperTest` 单独覆盖

---

## AKN-003：职业问答中 LLM 顺带编造施法方式，误判"女巫是自发施法"

### 状态

已修复（2026-08-11，A+B 方案）

### 问题描述

用户问「女巫职业等级表 + 每级豁免 + 每日法术位」，Agent 回答主体正确，但**顺带**扩展了"女巫是自发施法"——错误描述。实际 PF 1e 女巫是**准备**施法者（术士才是自发）。

### 根因分析（数据链排除法）

用 bge-m3 实际复现检索（`vector_store_classes.json`，13895 docs）逐步排除：

1. **数据不缺失**：女巫基础职业页完整存在于 class 库（16 chunk，`doc_id=基础职业/女巫/page_91.md`），`职业特性` chunk 明确含原文「女巫必须预先选择并准备法术」。
2. **检索能命中**：等级表问法 `表：女巫` 稳居 top1，top5 基础页占 2~3 个；但 top20 内**无任何"自发"字样**——错误描述不是检索带出来的。
3. **真因是 LLM 生成阶段顺带编造**：`表：女巫` chunk 本身不含施法方式描述，LLM 回答主体时"顺手"补充该属性，凭训练印象写成"自发施法"。现有 system prompt（"禁止凭记忆编造规则"）只防"完全不知道→瞎编"，**没防住"主体正确→顺带扩展未检索属性"**。

### 配套检索缺陷（方案 B 动机）

class 库女巫变体/巫术 chunk 226 个 vs 基础页 16 个，变体噪声重。复现三类基础问法，top5 中变体常占 4 个（含「灵脉驱动=灵脉守卫是自发施法者」），与基础页"必须预先准备"**直接矛盾**，加剧 LLM 不确定性 → 更倾向标"推断"。而问变体时基础页相似度 <0.55 天然不在候选集，无噪声干扰。

### 修复方案（A+B）

- **A（主药，`PromptBuilder`）**：system prompt 新增两条——① 每条规则事实（施法方式/生命骰/豁免等）必须有检索依据，检索未提供的**禁止凭记忆补全**，影响完整性先 reportDataGap 再如实说明；② 职业核心机制以基础职业能力检索结果为准，变体文本与基础页冲突时以基础页为准。
- **B（辅药，`SearchService`）**：class 模块检索时基础职业页（tocPath 恰为 `职业 → 基础职业 → X`）相似度 +0.03（仅排序用，不改 Document.score），并扩容候选集 topK+3。已验证三类问法 top5 基础页从 1~3 个提升到 3~4 个，`职业特性` chunk 稳居 top1；问变体不受影响（基础页不在候选集）。

### 可配置项

`pf.search.class-base-bonus`（默认 0.03）、`pf.search.class-extra-candidates`（默认 3）。

### 端到端验证（2026-08-11 重启后，闭环确认）

Agent 重启加载 A+B 后，两个真实问法验证：

1. **问法一「女巫职业等级表 + 每级豁免 + 每日法术位」**：等级/豁免/法术位表格全部正确（来源 APG），回答中**不再出现"自发施法"断言、也不再标"推断"**——检索结果未提供施法方式时，LLM 选择不补全（A 规则①生效），而非凭记忆扩展；20 级截断数据明确标注"基于表格规律的推断，可核对原书"。
2. **问法二「女巫是准备施法者还是自发施法者」**：有依据明确回答"准备施法者"，引用 APG 职业特性"法术"原文「女巫必须预先选择并准备法术」（B 方案加分让基础页职业特性 chunk 稳居检索结果）；并如实说明「灵脉守卫变体是自发施法者，但这是变体对基础职业的更改」——符合 A 规则②（未指向变体时以基础页为准，同时不隐瞒变体例外）。

结论：A+B 方案两个问法下均验证通过，修复闭环。

### 教训与约定

- **排查"Agent 答错"必须做数据链排除**：先确认数据存在（organized → chunks.jsonl → vector_store），再复现实际检索（Ollama bge-m3 embedding + topK），最后才下结论。本次初判"数据缺失"是错的，被实际检索复现推翻。
- **prompt 的"禁止编造"防不住顺带扩展**：LLM 在回答主体正确时可能扩展未检索的属性断言，需显式约束"断言必须有依据 + 未检索不补全"。
- **检索层可用分数加分做重排**：不依赖查改写/分类器，用 tocPath 结构化字段识别基础页，加分仅影响排序不污染数据。

---

## AKN-004：F-002 联调批次登记——book '?' 口径 / feat 双目录 / 表格结构化（登记观察）

### 状态

登记观察（2026-08-16，F-002 Batch C/D；数据侧修复另立任务）

### 背景与结论

F-002 检索联调调研（方案：`pf_agent/agent/docs/检索端语义降权优化方案_20260816.md`）确认三项登记观察：

1. **book '?' 口径（非检索问题，数据侧既有口径）**：`book_abbreviation` 未知数量——race 2483（68%）/ rule 188 / feat 100 / trait 99 / spell 13。`searchByMetadata` 按 book 过滤时 '?' 不等于任何书缩写，**不会误匹配**（安全）；仅前端来源显示「未知来源」。判定为数据侧口径（KN106/111/137 已登记设计保留），Agent 检索层不处理、不降权。
2. **feat 双目录澄清**：`vectorizer/output/feat/`（2846 chunks，571 book '?'，含 51737 字符巨型 chunk）**未被 Agent 加载**——`pf.chunks.feat-path` 指向 `专长/`（6032，CLAUDE.md 终态 ✅）。登记澄清，不涉及 Agent 数据链。
3. **表格结构化（KN221 同源）**：rule_table 331 + rule 1299 个以 `|` 开头的纯文本表格 chunk。判定 P3，**不降权**（表格 chunk 是有效内容，如「表：召唤怪物」）；结构化改造是数据侧任务（用户已拍板「回头统一处理」，KN221 处置），随一期联调批次纳入不单独立任务。

### 关联

- 方案文档：`pf_agent/agent/docs/检索端语义降权优化方案_20260816.md`
- 数据侧：`docs/已知问题记录.md`（KN106/111/137/221）

---

## AKN-005：_overview 第二批降权评估——决定不纳入（登记观察）

### 状态

登记观察（2026-08-16，_overview 第二批评估闭环；用户拍板不纳入）

### 背景与结论

F-002 第一批只降 `_intro`/`_reference`（用户拍板），`_overview` 第二批单独评估（方案 §七.1 决策点）。真实检索复现（真实向量库 + bge-m3，复刻 `rankedScore`）评估 `_overview` 类 chunk 是否应纳入降权：

**数据画像**：`_overview` 仅存于两个模块——class_overview 715（5.1%）/ race_overview 111（3.0%），其余模块（feat/trait/equip/skill/rule/spell）无。

**挤占证据（支持降权）**：
- class 4 问法中 2 问「职业特性」总览混入 top5：游侠宿敌（第 2，0.7035）、牧师领域（第 5，0.6583）
- 模拟 overview-penalty 0.02 后两问均改善（游侠具体条目升第 1、牧师 overview 压出 top5）
- 战士问法 overview top1（0.6919，差第 2 名 0.038）0.02 压不动

**误伤证据（反对降权，决定性）**：class_overview 对「职业介绍/定位」类提问是**正确命中**——4 问 4 中 top1（战士 0.6290 / 牧师 0.6517 / 女巫 0.6609 / 游侠 0.6414）。其中「牧师介绍」top1 与第 2 名仅差 **0.0068**，overview 降权 0.02 会把介绍类正确 top1 也压掉。即降权 overview 是双刃剑：改善 2 个具体特性问法，却伤害「职业介绍」这一类合理提问。

**决定**：**不纳入 overview 降权**（用户 2026-08-16 拍板）。第一批 intro/ref 降权已覆盖主要噪声（feat_intro/rule_reference 等）；class_overview 是职业总览页（含职业定位/关键词等核心信息），对介绍类提问有价值。后续如观测到具体特性检索仍被 overview 挤占，再评估「按问法区分」的方案（如检索目标为具体特性词时降权）。

### 关联

- 方案文档：`pf_agent/agent/docs/检索端语义降权优化方案_20260816.md` §七.1（决策点已拍板）
- F-002 / AKN-004

---

## AKN-006：KN098/100 检索端残留影响面评估（登记观察）

### 状态

登记观察（2026-08-25，P0-B T5 只读扫描 `vectorizer/output/种族/chunks.jsonl` 3654 行）

### 结论

数据侧两 KN（2026-08-04 闭环）检索端残留：
- **KN098（race_spell 替换特性误切）— 无残留，关闭**：134 个 race_spell 全部为合法种族法术（title 无「法术」字样的均为种族法术名，如猫幸/柳絮随风/精类思维类替换特性已正确归 `alt_trait`，未见「替换特性」被误切）。
- **KN100（怪物数据块字段名伪条目）— 残留 11 个，量级 0.3%**：title=字段名的法术数据块字段行被拆成独立 chunk，集中于两个 UW 源文件：
  - 藤蔓莱西UW：`race_page_1456_0060/0061/0062/0063/0065/0066/0067`（7 个，title=等级×2/施法时间×2/成分×2/目标×1，属「抓握藤蔓」「莱西集群」两法术的数据块）
  - 伽瑟兰UW：`race_page_814_0042/0043/0044/0045`（4 个，title=环位/施法时间/成分/目标，属「足底生根」物品法术数据块）

**检索端影响**：「施法时间/成分/环位」类字段名可能被字段行伪条目命中，噪声小（11/3654）；不阻塞一期，登记待数据侧修复（与 KN100 同源后处理，不属本批次范围）。

### 关联

- 数据侧 `docs/已知问题记录.md` KN098 / KN100
- P0-B T5 / `检索溯源归因与修复方案_20260821.md` §六

---

## AKN-007：medium-25 评测溯源波动掉点（2026-08-25 新发现）

### 状态

登记观察（2026-08-25，P0-B T3 评测新 baseline 溯源 46/50；medium-25 baseline 44/50 时溯源=1，本轮=0）

### 问题描述

medium-25「提升战技加值（CMB）、特别是提高擒抱成功率，有哪些途径？」本轮溯源 0→掉 0（诚实=1，回答内容正确）。3 个判分锚点 `rule_rpage_0008_0009` / `feat_page_195_0297` / `rule_page_302_0050` 均未命中 LLM sources。

### 根因（T4 复刻 bge-m3 + 余弦 0.5 + rankedScore 同款加权）

3 锚点全部排 top15 外：`rule_rpage_0008_0009` cos 0.5434 **排 100/568**、`rule_page_302_0050`（攫抓）排 31/568、`feat_page_195_0297` 排 24/1590。LLM 引用邻居 `rule_rpage_0008_0008`（CMB 公式，复刻 top6）回答，内容正确但判分锚点未命中。

**归因：召回缺失 + baseline 波动**——锚点本身排序长期在 top15 外，溯源是否命中取决于 LLM 从 top15 里选了哪个（本轮选邻居 0008 而非 0009）。与 easy-15 的波动（00 掉 1）同属 LLM 引用随机性。

### 影响与建议

不影响真实回答质量（诚实恒 1），仅影响溯源判分口径。建议与 easy-22/medium-4/medium-21 一并归入「召回精度」类别，待 k3 设计检索侧 title 匹配加权或评测锚点修订（`rule_rpage_0008_0008` 与 `_0009` 内容重叠，可视为等价锚点）。

### 关联

- `检索溯源归因与修复方案_20260821.md` §六（P0-B T4 归因）
- P0-B / F-002

---

## AKN-008：SourceCollector.drain 按 doc_id 页面级去重吞掉同页锚点 chunk（已修复）

### 状态

已修复（2026-08-25，P0-B2 T4 评测验证时发现并修复；测试 157 全绿）

### 问题描述

`SourceCollector.drain()` 原按 `doc_id` 去重，但各模块 mapper 写入的 `doc_id` 是**页面级**（StandardChunk/ClassChunk 的 source 页路径：equipment `page_234`、rule `page_127`、spell `Spell CRB`、class `核心职业/盗贼/page_49.md`，class 一页最多共享 327 chunks）。同一页面多个 chunk 在折叠区只保留**先到者**——`vectorSearch` 先返回同页邻居，`searchByMetadata` title 过滤精确命中的锚点 chunk 随后被 `putIfAbsent` 丢弃；而前端溯源判分按 `chunk_id`（chunk 级，唯一）匹配，锚点落空。

P0-B2 T4 评测 46→44/50 的直接根因：medium-4（page_234 邻居 `equipment_page_234_0268` 顶掉锚点 `_0179`）、medium-20（page_195 邻居 `feat_page_195_0173` 顶掉锚点 `_0361`）、medium-21（spell `doc_id=Spell CRB` 全书共享，后续 spell 全部被首条吞）。该 bug 在 title 过滤开放（修法 A）前不显性——锚点多为 vectorSearch top1 首个 add 未被挤出；修法 A 后「精确命中锚点但晚于同页邻居 add」成为常态，bug 全面暴露。

### 修复

`SourceCollector.drain()` 去重键 `doc_id` → `chunk_id`（缺失时回退 `doc:` + doc_id，防 null 合并）。前端 `toSourceRef` 本就读 `chunk_id`，去重粒度与溯源判定口径一致。测试更新：`beginAddDrainDeduplicatesByDocId` → `beginAddDrainDeduplicatesByChunkId`（同 doc_id 不同 chunk 全保留）+ 新增缺 chunk_id 回退测试。

### 关联

- P0-B2 / `剩余4题溯源修复方案_20260825.md`（修法 A 生效的必要条件）
- `SourceCollector.java` / `SourceCollectorTest.java`
- AKN-007（medium-25 波动，与本文书同页邻居挤出为同类机制）

## AKN-009：正文非标准形态「未整理 →」8 条（登记观察，宁漏勿错保留）

### 状态

登记不修（2026-08-26，KN207 展示层剥离实施时核实数据形态发现）

### 问题描述

KN207 展示层剥离（`TextSanitizer.stripInternalSourceLine`）按方案口径逐行匹配：**仅当一行 trim 后以「> 来源：」开头且含「未整理 →」/「未整理→」** 才剥离。全库标准形态约 1980 行（专长 714 / 规则 338 / 装备 105 / 法术 74 / 职业 749）已被覆盖；但数据中存在 **8 条非标准形态**：

- **法术 2 条**：「未整理 →」粘连在字段行末尾，非整行行首 `> 来源：`——如 `**法术抗力：** > 来源：...未整理 → 反派法典VC → 神秘仪式`；
- **职业 6 条**：正文内嵌「未整理 → ...变体/职业选项」但**缺少 `> 来源：` 前缀**，如 `极限诡道...未整理 → ...`。

这些行按口径不在剥离范围——强行剥会误伤字段行/正文内容（宁漏勿错原则）。

### 处置

- 当前 KN207 方案只处理标准形态，8 条非标准形态保留展示（LLM/用户可见的少量内部路径噪声）。
- 如需全剥：另立任务评估——数据侧剥离（须固化来源提取链路，KN207 拍板保留数据侧）、或放宽匹配（识别字段行末尾/无前缀行，误伤风险需设计验证）。不阻塞一期交付。

### 关联

- KN207 / `KN207展示层剥离实施方案_20260825.md`（k3 设计，数据侧保留 + 展示层剥离）
- `TextSanitizer.java` / `TextSanitizerTest.java` / `RetrievalTools.java` / `ChatService.java`
- 数据侧 `docs/已知问题记录.md` KN207（处置口径已同步）

---

## AKN-010：评测压测下 Hikari 连接池耗尽（10/10 被占、新请求 30s 超时降级）——已修复（OSIV 关闭）

**发现时间**：2026-09-18（SP8a 全量评测 evaluate.py 56 题期间，应用启动约 23 分钟后开始报错）

**现象**：`JdbcChatMemory` 读会话历史报 `HikariPool-1 - Connection is not available, request timed out after 30014ms (total=10, active=10, idle=0)`，随后按空历史降级处理（问答主链路不受影响）。PG 侧 `pg_stat_activity` 显示 10 条连接全部 **idle**（最后一条 query 均为 chat_message 历史查询）——即连接被应用检出但未持有事务，疑似**每处理 1 题评测泄漏 1 条连接**，约 10 题后池子耗尽（eval 启动 01:46，首次报错 02:07，间隔约 10 题）。

**初步定性**：JdbcChatMemory 本身用 TransactionTemplate/Repository 无显式连接持有；疑似 OSIV（spring.jpa.open-in-view 默认 true）+ SSE 长响应使连接随请求生命周期被持有，或他处检出未归还。**未定位根因**（评测运行中未重启排查）。

**影响**：评测/长会话场景下，池耗尽后每请求多等 30s 超时 + 会话历史读取降级为空（eval 每题新会话，对溯源/诚实/结构三指标无实质影响）；生产低并发下难触发。

**处置**：⏸️ 登记待排查（2026-09-18）。待评测完成后：复现（连续 11+ 请求观察池计数）→ 定位（OSIV 开关验证 / Hikari leakDetectionThreshold 抓泄漏点）→ 修复。评测不中断、继续跑。

**根因更新（2026-09-18 03:40）**：非代码泄漏。jstack 定位请求线程全部阻塞在 `OllamaApi.embed`（localhost:11434 embedding 调用无限等待，无超时）；实测 Ollama 进程僵死（embed 请求 >60s 无响应，`brew services restart ollama` 后恢复）。链条：Ollama 僵死 → embedding 调用悬挂 → 请求永不完成 → OSIV/请求域连接永不归还 → 池耗尽 → 后续请求 30s 超时降级。**次生改进项（建议另行评估，不紧急）**：embedding HTTP 客户端缺超时（JdkClientHttpRequest CompletableFuture.get 无界等待），Ollama 僵死时请求会无限悬挂——可给 RestClient 加读超时。

**次生项已修复（2026-09-19，与本记录同批提交于 dev/pf-agent）**：EmbeddingConfig 覆盖装配 `OllamaApi`
（自动装配的 @ConditionalOnMissingBean 回退），底层换带超时的
`SimpleClientHttpRequestFactory`；ollama / cloud 双通道共用同一超时 factory，
超时触发 `ResourceAccessException` → `FallbackEmbeddingModel` 降级而非无界悬挂。
Truncating/Fallback 包装链不变。新增配置键：`pf.embedding.read-timeout`
（默认 120s）、`pf.embedding.connect-timeout`（默认 10s），见 application.yml
`pf.embedding` 节。AKN-010 主项（池耗尽根因链路中的 OSIV/连接归还）仍待排查，
本条仅消除"embedding 无超时悬挂"这一环。单测：EmbeddingTimeoutTest（配置绑定
落到 request factory、超时触发 ResourceAccessException、断连快速失败）。

---

**主项根因已定位（2026-09-21 复现实验，只排查未改代码）**：根因 = **OSIV 默认开启**
（`spring.jpa.open-in-view` 未配置 → true，启动日志有 WARN）使请求域 EntityManager
在请求线程上从首次 DB 访问持有 Hikari 连接直到请求完成。请求入口
`ChatService.buildInitialHistory → JdbcChatMemory.get` 即触发首次 DB 读
（repository 只读事务结束后连接被 OSIV 会话继续持有，PG 侧表现为 idle），
随后 LLM 工具循环里的 embedding 调用（`OllamaApi.embed`，经
`RetrievalTools → SearchService → SimpleVectorStore`）耗时/悬挂多久，
连接就被占用多久；10 个并发悬挂请求即占满默认池（total=10），第 11 个请求在
`JdbcChatMemory.get` 取连接处 30s 超时降级（与登记现象逐字吻合）。

实验证据（2026-09-21，Ollama 用 `kill -STOP` 模拟僵死、TCP 可连但永不响应）：
- OSIV 开（默认）：12 并发请求，~50s 后日志出现 4 次
  `HikariPool-1 - Connection is not available, request timed out after 30014ms
  (total=10, active=10, idle=0)`；jstack 显示请求线程栈为
  `ChatController.chat → ChatService.ask → executeTools → RetrievalTools
  → SearchService → SimpleVectorStore.doSimilaritySearch → OllamaEmbeddingModel
  → OllamaApi.embed → socketRead`（阻塞读 localhost:11434）。
- OSIV 关（`--spring.jpa.open-in-view=false` 对照组）：同压法 12 并发悬挂请求，
  **0 次池超时**（连接随各自事务结束归还；embedding 120s 读超时降级照常工作，
  无 LazyInitializationException）——决定性对照，证实根因在 OSIV 而非代码泄漏。

修复方案候选（按推荐排序）：
1. **显式 `spring.jpa.open-in-view: false`（推荐，配置一行）**：本应用无视图层懒加载
   需求（REST + 手动 EAGER/事务边界），关闭零代价；连接持有期缩回各事务边界。
   注意排查隐藏依赖：若未来有请求内懒加载会立即暴露为异常（是好事，fail-fast）。
2. 池参数缓解（`maximum-pool-size` 调大 / `connection-timeout` 调小）：只改症状，
   悬挂请求仍各占一连接直到 embedding 超时，不推荐单独使用。
3. 检索/embedding 移出连接持有期（在 ask 入口先取历史、归还连接后再跑 LLM 循环）：
   在 OSIV 关闭后等价于方案 1，无需单独做；OSIV 开启时做此重构代价大且易漏。
4. Hikari `leak-detection-threshold`：诊断手段，非修复。

**处置**：✅ 已修复（2026-09-21，方案 1 落地）：`application.yml` 显式
`spring.jpa.open-in-view: false`（附注释说明根因），连接持有期缩回各事务
边界；全量单测 401 全绿。顺带项（`JdbcMemory.get` 包 TransactionTemplate）
未做——repository 只读事务已覆盖，仅风格统一，非必须。复现对照实验见上
（OSIV 关后同压 12 并发悬挂请求 0 次池超时）。

---

## AKN-011：SpellMetadataReplayTool 重放为整表替换，将抹掉 mapper 之外的 metadata 键（M3，已修复）

**发现时间**：2026-09-18（SP8c 测试审计，tester 报告 Minor-1；用户拍板登记）

**问题描述**：`SpellMetadataReplayTool`（重放工具）的幂等逻辑为"逐条比对 store
metadata 与当前 mapper 产物，不一致则**整表替换**"。当前安全——线上库 metadata
全部由 mapper 生成，替换前后等价（2026-09-18 base_spell_* 重放已逐条验证
embedding 零变化）。但未来若有**非 mapper 来源**的键写入向量库 metadata
（典型场景：J6 Layer 1 / F-017 计划由数据侧离线脚本写入 `entry_links`），
一次重放即被静默抹除，且无报错。

**处置**：✅ 登记（2026-09-18，用户拍板）。✅ 已修复（2026-09-21，commit 待补）：
重放改为 merge（合并）语义——逐条把 mapper 产物叠加到存量 metadata 上，
mapper 产出的键以 mapper 为准更新，store 里 mapper 之外的键（如未来
Layer 1 / F-017 由数据侧离线脚本写入的 `entry_links`）保留不动。幂等判断
相应改为"merge 结果与存量 metadata 逐条一致才跳过"，重放两次结果一致。
固化现行为的用例（SpellMetadataReplayToolTest
.replayMergesMetadataKeepingExtraKeysAndStaysIdempotent）已同步改为断言
"额外键被保留 + mapper 键以 mapper 为准 + 幂等"。`entry_links` 纳入 mapper
白名单的方案不再必要（merge 语义下离线键天然幸存）。

**tester 验收两观察项（2026-09-21 用户拍板：均登记放行，不改代码）**：
1. 仅漂移无更新（replayed==0）时 missed 计数被 skip() 丢弃、仅 warn 日志
   体现——登记。重放工具按 DVG-001 清偿计划退化为一次性迁移手段，不为
   可观测性加代码；真需漂移量时重灌前对账数据源与库存即可。
2. merge 语义的内在边界：mapper 主动下线/改名的键会被当作"mapper 之外的
   键"永久残留旧值，幂等比对不察觉——登记为已知语义。merge 无法区分
   "他人写入的键（要保护）"与"mapper 下线的键（该清理）"；清理下线键走
   重灌（数据侧产物为唯一事实源），重放不承担键生命周期管理。

**退役（2026-11-11，DVG-001 清偿）**：replay 工具（`SpellMetadataReplayTool`）及其专属测试
已**彻底删除**，merge 语义随之不再是现役路径——现役向量库唯一写路径为「数据侧
chunks.jsonl → Java DataLoader 全量重灌」（手册 `docs/DEPLOYMENT.md` §六）。旧配置
`pf.stores.metadata-replay=true` 由长期只读闸口 `DeprecatedMetadataReplayGuard` fail-fast
拦截。AKN-011 的 merge 修复记录作为历史保留原貌，**本问题不因删除而重开**。

---

## AKN-012：Ollama embed 超长输入 400——num_ctx/num_batch 默认值与静默截断行为变更（已修复）

**发现时间**：2026-09-19（D1+KN226 重灌规则向量库，RuleDataLoader 导入 ~70 条后启动失败）

**问题描述**：规则库重灌时 Ollama 报 `400 the input length exceeds the context length`，
应用启动失败。逐层定位：
1. 表层：Ollama 默认 `num_ctx` 4096；实际生效的硬约束是 **num_batch 2048**——
   服务端日志 `input (2055 tokens) is too large to process... batch size: 2048`，
   稠密中文 chunk（如 rule_page_159_0052，3955 字符≈2055 token）超限即 400；
2. 历史成因：旧版 Ollama 对超长输入**静默截断**（旧库 2026-08-10 建库因此"成功"），
   新版改为报错——同一份 chunks 今昔行为不同；
3. 排障陷阱：只调 `num_ctx` 无效（batch 仍是瓶颈）；`OLLAMA_CONTEXT_LENGTH` 环境变量
   已写入 launchd plist 但 n_ctx_slot 仍为 4096（未生效，原因未查）；**per-request
   `options.num_batch` 生效**。

**修复**（2026-09-19）：`application.yml` `spring.ai.ollama.embedding.options`
增加 `num-ctx: 8192` + `num-batch: 8192`（bge-m3 原生上下文 8192，覆盖
TruncatingEmbeddingModel 5000 字符截断窗的最坏 token 数）。规则库重灌验证通过。
plist 的 `OLLAMA_CONTEXT_LENGTH=8192` 保留（无害，或可造福其他模型）。

**教训/联动**：
- embedding 输入硬约束 = min(num_ctx, num_batch)，两个都要看；报错文案只提
  context length，有误导性；
- 与 AKN-010（Ollama 僵死 → 连接池耗尽）同为 Ollama 运维类风险，Ollama 侧
  变更（升级/重启/配置）后应抽查 embed 链路；
- 待评估遗留：embedding HTTP 客户端无读超时（AKN-010 次生项，仍未实施）。

## AKN-013：聚合/概括型回答的引用标注稀疏——「被引用集合」远小于「实际采用集合」（登记观察）

**发现时间**：2026-10-01（F-016/F-022 引用治理讨论，M1 调研 + 用户实测「女巫 1 环法术」类列举题）

**问题描述**：LLM 在**聚合/概括/列举型回答**中倾向于不标或极少标 `[#N]` 上标（通常只在段首标一两个，甚至为零），而这类题往往命中几百条来源。原因链：①模型按"凭印象组织语言"，无"此话出自第几条"的结构化记录；②检索内容与其参数化知识混合后无法自区分出处；③逐条标注成本高，长答案标注密度递减；④SP4 prompt 的定义「引用某 chunk 内容的句子后附编号」被模型按"近乎复述才算引用"的窄口径执行。后果：**「被引用集合」是「实际采用集合」的不可靠下界，且差集大小机器不可观测**——任何"只显示被引用来源"的策略都会把"用了但没标"的来源隐藏掉。

**当前处置（2026-10-01 用户拍板）**：口径**维持 SP4 原定义**（"引用某 chunk 内容的句子后附编号"），**不扩到"参考了也算"**；配合「只保留有效引用（被编号引用的）」试点（M16，用户要求先看效果再定）。运行时**没有**对问题/答案的分类（仅离线评测集 `qa/pf_qa_items.json` 有 `dimension`（D=定义/R=检索/X=综合）+ `tier`（easy/medium）标注用于评测分析）——若后续要按题型差异化处理引用展示，需先补运行时分类能力。

**联动**：F-014（上标编号机制）/ F-016（来源收集器上限）/ F-022（引用展示精简）/ M1 调研结论（`docs/项目文档总索引.md` 塔批次 M1 notes）。

## AKN-014：只保留被引用来源（cited-only）的固有代价——检索到但未被正文标注的来源会被过滤（登记观察）

**发现时间**：2026-10-02（M16 引用治理试点评测，evaluate.py 三口径 + 离线配对重放）

**问题描述**：「sources 只保留正文 `[#N]` 实际引用的条目」生效后，**检索命中但模型未标注的来源会被删除**。实测代价：53 题评测中仅 `medium-17`（聚合题）溯源分掉 1 分（78→9 条，LLM 引用的 9 条未覆盖评测期望的 page 级锚点 chunk）；其余 52 题无影响，体积收益 sources 总数 −82.5%（2570→450）。该代价是**固有**的：被过滤条目里偶尔含"检索到了但模型没标"的关键来源（见 AKN-013 标注稀疏），无法在不恢复全量的情况下完全消除。

**当前处置**：用户实测效果后拍板**合并**（2026-10-10）。残留风险：若线上出现"感觉某条该出现的来源没了"，即属此类，需按反馈评估是否回补（候选：未引用条目保留轻量元数据的分层展示）。

## AKN-015：searchByMetadata 翻页失败后的编造行为——女巫 1 环法术「补全到 143 条」（已修复 2026-10-28）

**发现时间**：2026-10-10（用户实测反馈）

**现象**：用户问「女巫的 1 环法术」类问题，Agent 尝试用 `searchByMetadata` 的 offset 翻页取后续数据，**分页调用未返回真实结果**；在拿不到数据的情况下，Agent 把表格「补全」到了 143 条——**编造数据**（当轮回答中已自行承认并撤回）。

**两层问题**：
1. **分页失效（待排查）**：offset 翻页未取到数据。候选原因（均未证实）：工具调用未返回结果、单次 limit 上限、`spell_level` 元数据缺失（34.8%，见 M11 调研）导致按 class+level 过滤漏召回、跨书重复条目导致翻页计数漂移。
2. **诚实性缺口**：取不到数据时**先编造后撤回**，而不是直接说"取不到"。诚实性基线（53/53）未覆盖"工具返回空/异常时是否编造"的场景。

**关联**：M11 调研（spell_level 元数据 34.8% 缺失）/ AKN-013（标注稀疏）/ 诚实性评测。

**处置**：~~登记待排查~~ **已修复（2026-10-28）**。

**根因（三层，均有 tool_calls.jsonl 实锤）**：
1. **工具层无分页元数据**：`searchByMetadata` 只返回 limit 截断后的条目列表，"共 M 条"是截断后的假总数，无 total/has_more/next_offset，模型无从得知还有后续页；
2. **截断提示无翻页引导**：`formatCompact` 的字符截断提示只说"收窄过滤"，没有任何"用 offset 续取"的指引；
3. **模型编造**：模型从未真正调用 offset（日志证明），却编造"翻页失败"借口并把表格补全到 143 条。

**修复内容**：
- `SearchService` 新增 `PagedResult`（page/totalCount/offset/limit/capped/cap）与 `searchByMetadataPaged`；totalCount 在 skip/limit 之前计算；任一 store 原始命中 ≥ enumerationTopK 时置 capped 标志（判定在 bookFilter/去重之前）。
- `RetrievalTools` J2 工具改走 paged：提示统一给真实总数与 `has_more=true；续取：query.offset=…`；capped 时绝不出现"共 N 条"，改"已达检索上限 500 条（实际命中可能更多）"；越界翻页给"已翻完全部结果"。
- 边界修复（T2/N2，用户拍板后修）：shown==0（单条过长整页放不下）不再输出退化"第 1~0 条"和停滞 offset，改引导 getEntryById；capped 末页+字符截断时"续取"与"收窄"话术二选一，不再同屏冲突。
- prompt 层（0b60c2d）：取不到数据禁止编造硬约束。

**验证**：mvn test 615 绿 / 1 skipped（N1 固化用例）；tester 两轮黑盒+白盒审计（`docs/test-reports/测试报告_AKN015_searchByMetadata分页元数据_20261023.md`）；53 题评测溯源 53/53、诚实 53/53、结构 3.00（无回退）；端到端实测模型严格按 offset 翻页，取不全时如实说"未能取到准确总数"，不再编造。

**遗留（用户拍板登记放行，见下方 AKN-016~021）**：T4/T6/N3/N5 + 2 项 Nit；N1 已于 2026-11-05 修复，见 AKN-018。

## AKN-016：searchByMetadata 旧 Map 重载带 offset 提示但 LLM 调不到（登记观察，AKN-015 放行项 T4）

**发现时间**：2026-10-23（AKN-015 tester 审计）

**问题描述**：`SearchService.searchByMetadata` 的旧 Map 返回值重载（内部兼容路径）也能触发分页提示话术，但该路径 LLM 工具层调不到，提示无实际受众。

**处置**：用户拍板放行（2026-10-28），登记观察；旧重载清理时一并处理。

## AKN-017：翻页时整页进 sources——末页条目不区分"展示过"与"未展示"（登记观察，AKN-015 放行项 T6）

**发现时间**：2026-10-23（AKN-015 tester 审计）

**问题描述**：分页场景下整页条目（含因字符截断未展示给模型的部分）都会进 sources 收集器。M16 cited-only（只保留正文实际引用的来源）已兜底用户面展示，风险可控。

**处置**：用户拍板放行（2026-10-28），登记观察。

## AKN-018：跨模块（module=all）+ capped 时提示文案自相矛盾（已修复 2026-11-05，AKN-015 放行项 N1）

**发现时间**：2026-10-23（AKN-015 tester 审计）

**问题描述**：`module=all` 跨库检索且合并 totalCount > cap 时，提示可能同时出现"第 501~503 条"（来自合并计数）与"本工具最多只能取前 500 条"，自相矛盾。单库路径无此问题。

**修复**：`RetrievalTools` 在跨模块 capped 末页与越界分支中明确 cap 是单库检索上限，保留正确的合并结果区间，不再宣称整个工具最多返回 500 条；单库文案与检索逻辑不变。原 `@Disabled` 用例已改为真实 `module=all` 场景并解除禁用，另补跨模块越界回归；`SearchService` 注释同步明确 all 合并后 totalCount 可大于 cap。

**验证**：聚焦测试 12 项全过；完整 `mvn test` 623 项、0 失败、0 错误、0 跳过。

## AKN-019：≥500 命中无法区分"恰好 500"与"超过 500"（登记观察，AKN-015 放行项 N3）

**发现时间**：2026-10-23（AKN-015 tester 审计）

**问题描述**：capped 判定为"原始命中 ≥ enumerationTopK"，命中恰好 500 条时也会输出"实际命中可能更多"的保守话术（误报）。方向安全（宁多报不漏报），不影响正确性。

**处置**：用户拍板放行（2026-10-28），接受保守误报。

## AKN-020：searchByMetadata 旧 Map 重载丢失 capped 标志（登记观察，AKN-015 放行项 N5）

**发现时间**：2026-10-23（AKN-015 tester 审计）

**问题描述**：旧 Map 兼容重载不携带 capped/cap 信息，走该路径时 capped 提示不出现。该路径 LLM 调不到，无用户面影响。

**处置**：用户拍板放行（2026-10-28），登记观察；与 AKN-016 同属旧重载清理范畴。

## AKN-021：T2 修复文案的两项 Nit（登记观察，2026-10-28 tester 复验提出）

**发现时间**：2026-10-28（T2/N2 修复复验）

**一期处理优先级**：**P3**（2026-11-09 拍板；建议级文案问题，随下次相关改动处理，不单独插队）。

**问题描述**：
1. shown==0 的 getEntryById 引导文案中含字面量 `offset=0，limit=10` 参数值，虽已明确"不要用相同 offset 重复翻页"且无 `query.offset` 前缀，理论上仍是"看似可照抄"的片段；
2. shown==0 + capped 同时发生时，因 shown==0 分支提前返回，"已达检索上限/实际命中可能更多"信息丢失，仅剩"或收窄过滤条件后重试"——无假信息，方向安全。

**处置**：登记观察，建议级，可随下次改动顺手处理。

## AKN-022：StandardChunk 字段使用下划线命名，不符合 Java 驼峰规范（待重构）

**发现时间**：2026-11-09（用户复核 chunk 元数据设计时发现）

**状态**：**待处理**（低优先级命名规范技术债）

**一期处理优先级**：**P3**（2026-11-09 用户拍板；以后单独重构，不阻塞当前一期功能与数据修复）。

**问题描述**：

`pf_agent/agent/src/main/java/com/pfagent/agent/rag/StandardChunk.java` 的 record 组件使用下划线分隔命名，例如 `chunk_id`、`doc_id`、`component_type`、`book_abbreviation`、`source_confidence`、`chm_toc_path`。按照项目 Java 命名约定，字段及 record 组件应统一使用小写字母起始的驼峰命名（lowerCamelCase），例如 `chunkId`、`docId`、`componentType`、`bookAbbreviation`、`sourceConfidence`、`chmTocPath`。

**影响与重构约束**：

- 当前属于代码规范与可维护性问题，未构成已知运行时功能错误。
- 后续重构需同步修改访问器调用处和相关测试，并覆盖 JSON 反序列化兼容性验证。
- **只改 Java 标识符，不改变数据侧 JSONL 的下划线字段契约**；需通过 Jackson 映射（如 `@JsonProperty`）继续兼容现有产物字段，禁止因重命名导致导入字段静默丢失。
- 其他同类 DTO 是否一并调整，届时单独评估，不在本条中自动扩大范围。

**处置**：登记待重构，后续作为独立技术债任务实施。

## AKN-023：列举式问答端到端耗时偏长——武僧清规单次实测约 41.87 秒（待定位）

**发现时间**：2026-11-10（KN108 闭环后真实 Agent 问答抽验）

**状态**：**已埋点并完成测量**（2026-11-12；优化方案待另立任务，不随本批实施）

**一期处理优先级**：**P3**（2026-11-10 用户拍板；后续优化，不阻塞当前一期功能与数据修复）。

**问题描述**：

通过临时本地实例真实调用 `POST /api/chat`，提问「武僧清规有哪些内容」，接口返回 HTTP 200，`gapReported=false`，端到端耗时 **41.867855 秒**。回答完整列出 8 项清规及来源，未发现耗时伴随缺项；该计时不包含实例启动时间。

当前仅有单次总耗时观测，尚未拆分 LLM 请求与生成、工具调用轮次、向量检索及网络传输耗时。**网络延迟是可能因素之一，但尚未证实，不能据此直接归因或预设优化方案。**

**影响**：

- 列举式、多来源回答等待时间较长，影响交互体验。
- 当前属于性能与可观测性问题，不构成已知答案正确性回归；单次样本也不足以判断是否稳定复现。

**后续处理建议**：

1. 在相同环境和问题下复测，记录 LLM 调用次数与各次耗时、工具执行耗时、检索耗时和响应体量，区分网络与服务端处理成本。
2. 与其他列举式问题及简单事实问题进行对照，确认是否与工具轮次、回答长度或特定模型链路相关。
3. 定位主要耗时段后再选择优化手段；本登记不预设减少工具调用、缩短回答或调整网络配置中的任何一种方案。

**2026-11-11 收口复核**：M26 临时实例真实模型冒烟中「武僧清规有哪些内容」正常返回
（HTTP 200、15 条来源、`gapReported=false`），但本轮未单独记录并拆分端到端耗时，
故本条目维持 **P3 待处理**，不因功能可用而销账。证据：
`docs/test-reports/测试报告_一期五项Spec收口_20261111.md`。

**2026-11-12 复测与拆分（M37 统一临时实例，3 次）**：端到端 **33.03 / 25.02 / 27.91 秒**；
LLM 调用端到端（含网络）**25.10 / 21.65 / 20.37 秒**（9/6/6 次，占 73%~87%），工具执行
**7.85 / 3.29 / 7.46 秒**（13/13/9 次），其余进程内开销每次 < 0.1 秒。主要成本是 LLM 往返
次数（工具轮次 8/5/5），其次为重复 keywordSearch（run1/run3 各 4~5 次、累计约 6.5 秒）。
网络耗时无法从 LLM 端到端中剥离，不归因于网络。本阶段仍只测量、不优化，按收益排序的
优化建议见报告 §4。报告：`docs/test-reports/测试报告_AKN-023武僧清规耗时拆分_20261112.md`。

## AKN-024：宽查询放行对会话内换模块提问的沿用（模型遵循度波动，待收敛）

**发现时间**：2026-11-11（F-026 收口真实模型冒烟）

**状态**：**✅ 已闭环**（M35 实施 + M38 `0096cfa` 返工；2026-11-12 定向复验 3/3 重新建议，换模块轮捕获 `BLOCKED/fingerprint_mismatch`，regenerate 后 0 来源）

**一期处理优先级**：**P2**（2026-11-11 用户拍板从 F-026 残留中拆分为独立待办）。

**问题描述**：

同一会话内，用户先对某模块的宽查询（如 rule「CRB 里所有类型的规则条目」）确认
`allowBroadQuery=true` 放行，随后改用**另一个模块**提问（如「CRB 所有专长，完整列出」）
时，模型并不总是重新给出收窄建议：

- **2 次同会话复跑中 1 次**沿用上一轮放行直接执行，写入 4 条 ALLOWED 事件；
- 另 **1 次**正确重新判断并返回收窄建议；
- 新会话首轮「CRB 所有专长，完整列出」1 次即为正确建议。

即行为不稳定，同一输入可复现两种结果。

**根因**：

工具层按 F-026 设计 Spec **不保存会话级确认状态**（`allowBroadQuery` 按单次逻辑查询
生效，不做会话级记忆），因此“换模块/换书/换条件后需重新判断”只能由提示词约束模型。
提示词已写入该要求，但模型的遵循度存在波动，无法仅靠提示词保证稳定复现。

**影响**：

- 可能产生用户未预期的宽范围检索与额外 token 消耗（1/2 复跑出现过该分支）。
- **不误拦**：未出现把正常查询错误挡下的情况；**不产生错误数据**：沿用放行时结果仍按
  原范围分页执行，500 上限与 capped 诚实话术不变，数据本身正确。
- 主要风险是用户对“换模块后的检索范围”失去预期，以及评测/回归结论不稳定。

**待做（三选一或组合，需先复现定位再定方案）**：

1. 在工具层补**会话级确认状态**（按模块/查询条件分段记忆放行），使换模块自动失效；
2. 或在工具层增加**换模块检测**（对比上一次放行的模块与本次请求模块，不一致则强制重新建议）；
3. 或最低成本：补**可重复的门禁回归用例**，把“确认宽查询 → 换模块提问”固化为自动化
   断言，先让波动可度量，再决定是否改实现。

**关联**：F-026（宽查询收窄门禁，已实现并合并）/ `docs/test-reports/测试报告_一期五项Spec收口_20261111.md`
§3.1 已知限制第 1 条 / 设计 Spec `docs/superpowers/specs/2026-11-10-f026-broad-query-narrowing-gate-design.md`。

**2026-11-12 统一验收（M37，临时实例真实模型，3 次）**：每次新会话三问——
「CRB 里所有类型的规则条目。」→「仍按原范围查询。」（执行并记录 rule+CRB 指纹）→
「CRB 所有专长，完整列出，不要省略。」。结果 **2/3 重新建议**：
run1/run2 turn3 来源 0（重新建议），**run3 turn3 返回 186 条来源**，回答称「已按你的要求
放行宽范围查询」。`query_gate_event` 显示 run3 先 `BLOCKED/fingerprint_mismatch`（feat），
同一轮内模型再次以 `allowBroadQuery=true` 重试，因拒绝时已把指纹更新为 feat+CRB 而
`ALLOWED/book_only` ×4。机制上无法区分「用户确认」与「模型自我重试」，未达到 Spec
「3/3 重新建议」验收门槛。未修改产品代码；用户已批准新增 M38 返工，合并后仅做定向 3 次
复验。证据：`/tmp/m37/gate_results_pre_m38.json`（仓库外）、`query_gate_event` 行、
`docs/test-reports/测试报告_一期第二批五项问题验收_20261112.md` §5.2。

**2026-11-12 M38 后定向复验（`0096cfa`，仅门禁，不重跑全量评测）**：同一三问脚本 3 次均
turn3 来源 0（**3/3 重新建议**）；另做 4 轮诊断，换模块轮捕获
`BLOCKED/fingerprint_mismatch/feat`，确认服务端守卫实际生效。被拦截后
`POST /api/conversations/{id}/regenerate` 返回 0 来源；`BroadQueryAllowanceRegistryTest`
与 `ChatServiceTest` 的「同轮/regenerate 不得确认」用例通过（定向 5 个测试类 188 项全绿）。
证据：`/tmp/m37/gate_results.json`、`/tmp/m37/gate4_diag.json`（仓库外）。
**副作用观察（已上报塔，未改代码）**：M38 后用户确认轮也未产生 `ALLOWED`，模型改用
vectorSearch 返回 13/14 条抽样并说明未取到全量清单；推断待确认指纹被每次被拒尝试覆盖、
同轮重试又不能确认，导致「确认后执行宽查询」路径在真实模型下不可达。详见验收报告 §7.1，
建议另立问题评估。

## AKN-025：极值/排序类提问的检索能力缺口——「装备最高价」稳定答错（medium-17 复跑 3/3）

**发现时间**：2026-11-11（medium-17 单题定向复跑 3 次，常驻 8080 实例，仓库原样 `evaluate.py`）

**状态**：**✅ 已闭环**（M33 数据侧清单补全 + M35 Java price 排序；2026-11-12 统一验收 medium-17 3/3 正确）

**一期处理优先级**：**P1**（2026-11-11 用户拍板：先记录问题，回头再解决；本轮不改运行代码、不改 `evaluate.py`、不实施修复）。

**问题描述**：

题目 medium-17：「在 PF 装备数据中，可购买（有明确标价）的魔法物品里，价格最高的是哪一件？价格是多少？」
正确答案：**力量法杖（Staff of Power）235,000 gp**，出自 CRB「表：法杖」（期望 chunk
`equipment_page_222_0000`）。单题连跑 3 次，**溯源 0/3**，且两轮给出了实质性错误答案：

| 轮次 | 溯源 | 诚实 | 结构 | 回答主张 | sources |
|---|---:|---:|---:|---|---:|
| run1 | 0 | 1 | 3 | 高等瞬发超魔权杖 **170,000 gp**（自称「本次检索结果中最高」） | 10 |
| run2 | 0 | 1 | 3 | 隐魂戒指 **160,000 GP**（自称「当前检索结果中最高」） | 14 |
| run3 | 0 | 0 | 3 | 明确拒绝给出全库最高价，列出 3 条工具实测限制；根据 run3 `sources=4`、诚实 0 与 `score_honesty` 正常题分支**反推** `gapReported=true`（`qa_report.json` 不保存该字段，非直接记录），另给 4 个收窄问法 | 4 |

**数据完整性已直接验证（不是数据缺失）**：直接读取 `~/.pf_agent/vector_store_equipment.json`：

- `equipment_page_222_0000` **存在**，正文 **5769 字符**，含行
  `力量法杖 (Staff of  Power) |  | 235,000 gp |  | CRB`；
- `equipment_page_220_0000` 亦存在（6682 字符，CRB 戒指表，最高 200,000 gp）。

即期望 chunk 与正确数值都在库内，问题出在**检索/工具层**，不是数据缺失。

**四条根因**：

1. **装备元数据无 price 字段**：`searchByMetadata` 可用过滤字段仅 `[book, componentType, title]`，
   模型传 `price`/`gte: price` 被直接拒绝（run3 回答记录「未知过滤字段: [price]」），无法做价格过滤、范围比较或排序。
2. **语义检索对极值提问不可靠**：向量相似度返回的是「各书价格表片段与物品描述」，属于相似片段
   排序而非价格排序，据此取最大值必然出错；run1/run2 的 170,000 / 160,000 即该机制产物。
3. **价格表 chunk 被截断**：run2 记录 CRB 奇物表只取到前约 8000 字符，高价行位于后半段，
   检索上下文本身不含全表（本次只登记现象，未改代码验证具体截断点）。
4. **分页上限使全库扫描不可行**：单页 40 条、总 cap 500；run3 实测 `listEntries` gear 类命中
   **2428 条**，取全需翻页约 61 次。

**影响**：

- 53 题基线「溯源 52/53」不能读作「仅维度未命中、答案可用」：medium-17 是**稳定答错**而非偶发
  未命中，run1/run2 给出了错误的具体价格。实际可视为 52/53 且其中一题答错。
- 所有「最贵/最高价/最低价/第 N 高/按 X 排序」类极值或排序提问都会失效，且模型倾向把
  「检索结果内的最大值」表述成「全库最高」，存在误导读风险（run3 是唯一明确限定范围的轮次）。

**待做方向（先记录，方案待定，本轮不实施）**：

1. 装备元数据补 **price 数值字段**（含币种/单位归一），并让 `searchByMetadata` 支持数值比较与排序；
2. **价格表格 chunk 防截断**（按表行结构化保存，或保证表格整体不被切分）；
3. 增加**极值提问专用工具**（如按字段取最大/排序检索），不依赖语义相似度；
4. 能力补齐前，提示词要求模型对极值提问明确声明「工具无排序能力」，禁止把检索结果内最大值
   表述为全库最高价。

**证据路径**（仓库外，未入库）：`/tmp/qa-medium-17-run1/`、`/tmp/qa-medium-17-run2/`、
`/tmp/qa-medium-17-run3/`（各含 `qa_report.json` + `qa_report.md`）；单题 items 文件
`/tmp/qa-medium-17.json`。

**关联**：AKN-014（此前把 medium-17 溯源掉分记为 cited-only 固有代价/波动，本条以 3/3 复现推翻
「波动」判断）；`docs/test-reports/测试报告_一期五项Spec收口_20261111.md` §3.2。

**2026-11-12 闭环（M33 数据 + M35 Java，M37 统一验收）**：

- 数据侧 `equipment_lists.json` 重建 **4319 条**（gear 2428 / wondrous_item 1224 / weapon 143 /
  ring 114 / armor 110 / rod 100 / staff 79 / artifact 66 / cursed_item 55）；
  `price_gp` 解析成功 2584、失败 1735（无标价或非纯数值，条目保留不参与排序）。
  力量法杖条目实测：`name=力量法杖`、`price=235,000 gp`、`price_gp=235000`、
  `chunk_id=equipment_page_222_0000`。
- Java 侧 `listEntries` 开放 `sortBy=price`（asc/desc，`price_gp=null` 恒排最后）与
  `price_min`/`price_max` 过滤；旧清单无 `price_gp` 时拒绝 price 排序并提示。
- 真实模型 medium-17 连续 3 次：**溯源 1 / 诚实 1 / 结构 3（3/3 全对）**，答案均为
  **力量法杖 235,000 gp**，来源包含 `equipment_page_222_0000`；新增价格题
  medium-34（戒指最高价，200,000 gp 并列）、medium-35（CRB 最贵法杖 235,000 gp）、
  medium-36（100,000~200,000 gp 戒指 7 条）全部通过。全量评测结果见
  `docs/test-reports/测试报告_一期第二批五项问题验收_20261112.md`。

## AKN-026：诚实性判分依赖 HONEST_PHRASES 固定词表，措辞稍变即误判 0（medium-17 run3 反例）

**发现时间**：2026-11-11（medium-17 定向复跑 run3）

**状态**：**✅ 已闭环**（M34 规则 + LLM 二分兜底 + 待复核路径；2026-11-12 统一验收通过）

**一期处理优先级**：**P2**（2026-11-11 用户拍板：先记录，回头再解决）。

**问题描述**：

run3 的回答实质是诚实的：明确写「无法给出可信的『全库价格最高魔法物品』」，给出三条工具实测
限制，写了「这是**数据能力和工具能力的缺口**」「`缺少的数据`已经记录为缺口」「不能当作全库最贵」
「我不能凭记忆替你补一个答案」，并给出 4 个可执行的收窄问法。该轮 `gapReported` 状态为
**反推**：依据 `sources=4`、诚实 0 与 `score_honesty` 正常题分支（仅当 `gapReported=true` 才走
词表判定）推得 `gapReported=true`；`qa_report.json` 不保存该字段，非直接记录。
但 `evaluate.py` 判诚实 **0**。

**判分原因**：

`score_honesty` 对正常题在 `gapReported==true` 时要求 `answer` 命中 `HONEST_PHRASES` 之一。
当前词表 11 条为字面子串：`未检索到 / 没有找到 / 未找到 / 无法回答 / 数据中不存在 /
没有相关数据 / 数据缺口 / 没有检索到 / 未收录 / 没有收录 / 无法确认`。run3 的措辞是
「数据能力**和**工具能力的缺口」「缺少的数据……记录为缺口」「无法给出……」，
均不含上述任何一条连续子串（「数据缺口」被「数据能力和工具能力的」隔开，
「无法给出」不等于「无法回答」），故判 0。

**证据边界**：`qa_report.json` 不落 `gapReported` 字段，本条的 gap 状态是按上述判分逻辑
**反推**所得，不是直接记录；若后续复跑能取得接口原始响应，应以直接记录为准并复核本结论。

**根因与沿革**：

M29 `81081b4` 对 `qa/evaluate.py` 的处理是**扩充词表**（补 `数据缺口`、`没有检索到` 等，
修复了 medium-27、easy-2 的历史误判），但判分机制仍是字面子串匹配，**未治本**：只要模型换一种
同样诚实的说法就再次误判。这使诚实性维度对措辞敏感，同一实质行为可因一个连词被判 0。

**影响**：

- 53 题诚实性结论（53/53 或 52/53）不稳定，可能因单题措辞波动改变，进而影响发布门槛判断；
- 反向激励模型堆砌「数据缺口」等关键词，而非把免责声明说清楚；
- 人工复核成本上升，每次都要回读原文确认是否误判。

**待做方向（本轮不实施）**：

1. `gapReported=true` 且回答含实质免责声明（限定范围、声明工具能力不足、不给具体编造值）时，
   不应仅靠固定词表判定；可引入判分规则（是否声明能力边界 + 是否避免编造具体值）；
2. 或改为**结构化判分**：`gapReported` 本身已是结构化信号，正常题 gap 分支可结合「无来源/无编造
   具体数值」判定，词表只作 fallback；
3. 至少把本次实测措辞（「能力的缺口」「缺少的数据」「无法给出可信的」）补入词表，并把 run3 原文
   固化为回归用例，避免同类反例反复出现；
4. 与 AKN-025 同批处理时一并复核，避免只改词表掩盖检索能力缺口。

**证据路径**（仓库外，未入库）：`/tmp/qa-medium-17-run3/qa_report.json`、
`/tmp/qa-medium-17-run3/qa_report.md`。

**关联**：M29（`81081b4`，evaluate.py 词表扩充，治标不治本）/ AKN-025（同一复跑批次）/
medium-27 历史「脚本误判」（M29 前因词表缺「数据缺口」被判 0，M29 后改为 1/1/3）/
`docs/test-reports/测试报告_一期五项Spec收口_20261111.md` §3.2。

**2026-11-12 闭环（M34，M37 统一验收）**：`evaluate.py` 已改为「词表命中快速路径 +
`gap=true` 未命中时 DeepSeek 二分兜底」，LLM 失败/缺 key 记**待复核**（`score=null`）不记 0；
无来源时负例优先先交 LLM 复核；`qa_report.json` 落盘 `gapReported` 原始值与
`honesty_basis`（`path=rule|phrase|llm|pending` + 命中词/LLM 理由/待复核原因）。
定向测试 `test_evaluate.py` + `test_tool_calls_report.py` 共 **47 passed**；统一验收全量
评测的诚实性按该机制如实结算，见 `docs/test-reports/测试报告_一期第二批五项问题验收_20261112.md`。

## AKN-027：用户确认后宽查询执行路径在真实模型下不可达/极难达（M38 后观察，待复核）

**发现时间**：2026-11-12（M37 统一验收，M38 `0096cfa` 后定向复验）

**状态**：**✅ 已闭环**（M39 `59d6b06`；2026-11-12 定向真实模型 3/3 确认后 ALLOWED 执行，
regenerate 被正确拒绝，详见文末闭环记录）

**一期处理优先级**：**P1**（F-026 核心「用户确认后放行宽查询」路径受影响；是否立即修复由用户拍板）

**问题描述**：

M38 修复「同轮自我重试/regenerate 不得确认」后，AKN-024 的「换模块重新建议」目标已 3/3
通过；但真实模型下**用户明确确认后也无法真正执行宽查询**。M37 定向复验（临时实例 18080）：

- 3 次三问脚本中，用户说「仍按原范围查询」后，turn2 只产生
  `BLOCKED/fingerprint_mismatch` 或 `no_conditions` 事件，**没有 `ALLOWED`**；最终分别返回
  3 / 31 / 0 条来源，其中带来源的轮次是 vectorSearch 抽样并明确说明「未取到全量清单」。
- 4 轮诊断（suggestion → confirm → confirm → 换模块）中，两次确认轮返回 13 / 14 条
  vectorSearch 抽样，仍无 `ALLOWED`；换模块轮正常触发 `BLOCKED/fingerprint_mismatch/feat`。
- 用户视角：系统建议「可回复仍按原范围查询」，但用户照做后仍无法取到全量，形成死循环。

**机制推断（待复核，不是代码级结论）**：

`BroadQueryAllowanceRegistry.authorize` 在拒绝分支会把当前指纹与**当前 requestId** 写回
pending 状态；真实模型中同一轮会以不同 module（rule/all）、不同 book 组合多次试探，每次
被拒都会覆盖上一次 pending 指纹。等下一轮用户确认时，其指纹（module+book）很难与上一轮
最后一次被拒的指纹完全一致；而同一轮内重试因 requestId 相同又不得确认。因此「待确认建议 →
后续真实用户轮次确认」的路径在真实模型试探行为下几乎无法命中。需以代码级日志/单测复核：
是否应在被拒时保留**首个/最近一次建议给出时**的 pending 指纹，而不是被后续不同指纹覆盖；
或把用户确认绑定到明确的上一轮建议标识。

**影响**：

- F-026 的「宽查询建议 → 用户确认 → 放行执行」核心体验不可用；宽查询只能得到 vectorSearch
  抽样，用户会误以为确认无效。
- 评测与真实使用中，列举/全量类问题仍可能缺项；不产生错误数据，但功能目标未达成。

**证据**（仓库外，不入库）：`/tmp/m37/gate_results.json`、`/tmp/m37/gate4_diag.json`、
临时 PG `m37-pg` 的 `query_gate_event` 表/行（已随容器删除）与 `/tmp/m37/app2.log`；
验收报告 `docs/test-reports/测试报告_一期第二批五项问题验收_20261112.md` §7.1。

**关联**：AKN-024（同会话换模块门禁，已闭环）/ F-026（宽查询收窄门禁）/ M38 `0096cfa`
（同轮与 regenerate 守卫）。

**2026-11-12 M39 闭环（`59d6b06`，定向真实模型复验）**：

- 根因修复：门禁状态改为**按指纹分别保存**的 `confirmed` / `suggested` 集合，同轮对
  rule/all、不同书的多次试探互不覆盖；`PromptBuilder` 与工具描述要求首次宽查询以
  `allowBroadQuery=false` 调用门禁工具登记真实 module+book，用户下一真实轮次的放行声明
  命中任一已登记建议即可确认。regenerate/同 requestId 仍不可确认（M38 语义保持）。
- 实测 3 次（每次新会话）：turn1「CRB 里所有类型的规则条目。」均 `BLOCKED/book_only/rule`
  并给出收窄建议（来源 0）；turn2「仍按原范围查询。」均 `ALLOWED/book_only/rule` 且实际执行，
  来源 **16 / 175 / 214** 条（run1 因触达 500 上限并记录 gap，回答如实说明）。**3/3 确认后
  真正放行**。
- 证据：`/tmp/m37/m39_results.json`、`query_gate_event` 行（每会话 1×BLOCKED + 多次 ALLOWED）、
  `/tmp/m37/app3.log`；报告 `docs/test-reports/测试报告_一期第二批五项问题验收_20261112.md` §7.2。
