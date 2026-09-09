# PF 数据清洗项目 - 交接文档

> **交接日期：** 2026-06-17  
> **最后更新：** 2026-08-09（**装备模块 M1~M5 全部完成收口**：分支 `feat/equipment-module`，5386 chunks（gear 2538/wondrous 1987 等 15 component_type）、verify 八检查全过（slot 严格 13 枚举 + KN159/160 防回退断言）、pytest 1165、判别器矩阵 297 rel 全独立对账 est=5097↔got=5386 静默丢失 0、book '?' 5（超游神器设计保留）、toc 空 0、星壳 0；源数据修复 3 处（UI奇物 B1 残渣 + 黑市指南BM 剧透块标题泄漏）+ BackfillChmTocPath `_resolve_doc_file` hook 扩展（消歧 doc toc 回填 40→0，公共层零回归）；出口条件 `python3 -m vectorizer.cicd verify --category equipment` 单命令全绿 ✅；KN161~186 登记；下一步 M6 独立复测审计 + 交付三件套，详见 §3H）；**2026-08-07（**技能模块 M1~M6 全部完成 + KN159/160 瑕疵修复闭环**：556 chunks（557→556 = KN159 伪条目净清除）、verify 七检查全过（含 KN159/160 防回退断言）、pytest 1018、判别器 est=382↔got=559 零静默丢失、book '?' 0、toc 0；M6 独立复测审计发现 P1 来源书系统性失实（557/557 全标 CRB，DirectoryNameProvider「技能」子串误命中）已修复（processor 专属表短路 + verify 检查 7，CRB 214/PU 225/FAQ 63/AA 31/OCCULT 10/GIANT 5/TG 5/PotR 3）+ P2×2 闭环；交付三件套 `审计结论_20260807` / `数据使用说明` / `技能名规范表`；KN150~158 登记闭环 + **KN159 表格行行中 CR 腰斩修复**（fix_skill_table_cr.py 17 文件 339 处，e4be517）+ **KN160 斜体星壳剥离**（format 剥星 TDD，6ac73dc）+ verify 防回退断言（ebecd8e）；详见 §3G）；**背景特性模块全闭环**（2026-08-06：任务 #146/#147、KN149 修复后终态 1222 chunks、pytest 988、verify 6/6、KN140/144/148 登记 P3）；**向量化设计优化批次全落地**（2026-08-05：A1/A2/A3/B1/B2/C1/C2，commits 见 §3F）；**种族模块全闭环**（2026-08-05：KN134/135 残留清零、pytest 843、verify_races 八检查、跨模块经验沉淀 `docs/跨模块经验沉淀_种族模块_20260805.md`，详见 §3F）；**专长模块已告一段落**（KN095 修复闭环 + 语义切分质量评估 ✅ + 交付文档 + KN112 公共层守卫回归修复，详见 §3E）  
> **交接方：** 骰娘（PF 跑团专用 Agent）  
> **接收方：** 开发 Agent（k3 设计 / deepseek-v4-pro · minimax3 执行）  
> **项目目标：** 建立高质量 PathFinder 1e 中英术语对照表 + 规则书向量化，支持规则问答 Agent（一期）与车卡辅助（二期）

---

## 1. 项目概述

### 1.1 背景
- **用户：** 车子（Java 后端程序员，PF 1e 玩家）
- **数据来源：** 从 CHM 格式规则书提取的 Markdown 文件（~1500+ 文件）

### 1.2 目标
| 阶段 | 目标 | 状态 |
|------|------|------|
| **一期** | 规则问答Agent，回答内容基于Pf规则，提供对应的目录引导，用户可以根据目录引导找到准确的信息来源进行对回答的验证| 🟢 进行中（术语表 ✅；职业向量化 ✅ V001~V009；法术模块 ✅ v1.0 召回 99.6%；专长模块 ✅ chunk 化完成（召回 100%，5897 chunks）+ 元数据设计 ✅（人工门 2 通过）+ 元数据提取 ✅（字段值落地）+ 行内来源顶层提升 ✅ → source_spec / 检索端形态降权） |
| **二期** | 车卡辅助工具（自动计算、Build 建议） | ⏳ 未开始 |


---

## 2. 文件结构

```
pf_agent/                               # 项目根
├── CLAUDE.md                           # Claude Code 项目说明
├── PROJECT_HANDOVER.md                 # 本文件
├── .github/workflows/ci.yml            # CI 质量闸口（pytest → pipeline → 四后处理 → verify → 不变量 → artifact）
│
└── pf_data/                            # 数据处理域（数据 + 脚本 + 文档）
    ├── CHM_FULL_TOC.md                 # CHM 目录结构
    ├── CHM_FULL_TOC_WITH_LEVELS.md     # 带层级标注的 CHM 目录
    ├── CHM_STRUCTURE_ANALYSIS.md       # CHM 结构分析
    ├── README_CHM_CONVERT.md           # CHM 转换说明
    ├── 未整理目录整理规则.md           # 规则书整理规范
    ├── source_chm/                     # CHM 解压源
    ├── _archive/                       # 历史归档（CHM 脚本等）
    │
    └── phase1/                         # 一期工作目录
        ├── _archive/                   # 历史归档（整理脚本/报告/旧术语/旧迁移）
        │
        ├── docs/                       # 项目文档（完整索引见 memory「PF 项目文档索引」）
        │   ├── WORKFLOW.md             # 🟢 V/N 迭代工作流 v2.1
        │   ├── VECTORIZER_ARCHITECTURE_DESIGN.md  # 🟢 终局架构设计 v2.1
        │   ├── 流程教训沉淀.md         # 专长全流程复盘五类教训（A 环境/B 链路/C 审计/D 源数据/E 质量闸口）
        │   ├── 格式杂乱聚合文档标准处理工作流.md   # 聚合文档 HTML 重建 SOP
        │   ├── 标准流程_校验问题处理.md # 验收失败/抽样问题处理流程
        │   ├── 问题与修复记录.md       # 闭环 bug 记录
        │   ├── 已知问题记录.md         # KN001~095 权威登记
        │   ├── 规则书向量化规则.md     # 向量化规则
        │   ├── 专长/                   # 专长模块文档（开工前清单/Prepare 交接/审计链/方案/映射报告/交付/t63 闸口）
        │   ├── state/                  # 模块状态（feat_exemptions_20260801.md 豁免、feat_chunks_baseline 基线）
        │   ├── HANDOVER_*.md           # 模块交接（法术启动/专长 Prepare Phase）
        │   ├── 法术*                   # 法术模块文档（元数据设计/KN011-018 统一修复/质量返工/审计系列）
        │   └── ...
        │
        ├── vectorizer/                 # 🟢 向量化核心包（包结构见 VECTORIZER_ARCHITECTURE_DESIGN.md）
        │   ├── pipeline.py             # 类目流水线
        │   ├── formats/                # 类目格式解析（spell*/feat.py，TDD）
        │   ├── processors/             # 类目处理器（含后处理覆写）
        │   ├── verify/                 # 验收（verify_feats.py 五检查等）
        │   ├── tests/                  # pytest 全量 530
        │   ├── exploration/法术/ 专长/ # Prepare 勘探（判别器矩阵/权威清单/逐文件记录）
        │   └── output/法术/ 专长/      # chunks.jsonl 产物（gitignored，CI/脚本重跑生成）
        │
        ├── regen_feat_chunks.sh / regen_spell_chunks.sh  # 本地重生成单入口（pipeline→四后处理→pytest→verify，与 CI 同链路）
        │
        ├── ===== 术语表 =====
        ├── 术语提取报告_分类版.md      # 🟡 基线（勿改）
        ├── 术语提取报告_优化版.md      # 🟢 交付版（1075 术语）
        ├── 术语提取报告_清洗版.md      # Phase 1 中间产物
        ├── 术语提取报告_重分类版.md    # Phase 1 中间产物
        ├── terms.json                  # 🟢 机器可读术语表
        ├── 规则书缩写对应表.md         # 来源书缩写对照
        ├── PF_缩写表.md                # 缩写附录
        │
        ├── ===== 当前脚本 =====
        ├── vectorization_prep_profession.py  # 职业向量化主脚本（模块已冻结，不再改动）
        ├── cleanup_phase3.py           # 术语清洗（当前主用）
        ├── term_rules.py               # Phase 3 公共规则
        ├── manual_overrides_phase3.py  # 人工分类覆盖
        ├── extracted_overrides.py      # 法术/专长覆盖
        ├── apply_chm_toc_mapping.py    # 后处理四脚本（顺序不可变，pipeline 重跑后必跑）
        ├── apply_feat_creation_source_promote.py
        ├── backfill_chm_toc_path.py
        ├── backfill_feat_source.py
        ├── normalize_*.py (4)          # 源文件格式归一化
        ├── cleanup_subtype_mismatch.py # subtype 误标清理
        ├── dedupe_all_chunks.py        # 通用去重
        ├── generate_expected_variants.py # 预期变体清单
        ├── html_fallback.py            # HTML 回退处理
        ├── census_profession_formats.py # 格式普查
        │
        ├── ===== 验收脚本 =====
        ├── verify_*.py (11)            # 全量/归属/heading/subtype/变体/传世名作
        ├── verify_data_invariants.py   # 数据不变量闸口（CI 用）
        │
        ├── ===== 数据 =====
        ├── pf_rules_md/                # 源数据（~2156 MD 文件）
        ├── pf_rules_md_organized/      # 按来源书/主题整理
        │   ├── 职业/（已处理 ✅）
        │   ├── 法术/（已处理 ✅）
        │   ├── 专长/（已处理 ✅）
        │   └── ...
        ├── vectorization_prep_profession/  # 职业向量化输出（gitignored）
        ├── baselines/                  # 基线数据
        ├── expected_variants/          # 预期变体清单（55 JSON）
        └── 整理规则_详情/              # 整理规则文档
```

---

## 3. 当前状态（截至 2026-08-07；法术/专长模块详见 §3D / §3E，种族模块见 §3F，背景特性见 §3F-2，技能模块见 §3G）

### 3.1 已完成工作

#### 未整理规则书归档（✅ 完成，2026-07-18 前）
- `pf_data/phase1/pf_rules_md/未整理/` 下 **145 本 L2 规则书**已全部完成第一步归档
- 其中 143 本已按来源书拆分到 `pf_rules_md_organized/` 对应分类目录
- 2 本怪物种族来源书（`怪物法典MC`、`内海怪物志`）按特殊方案整包归档到 `种族/怪物种族/`
- 所有 Markdown 格式问题已记录并关闭（`未整理目录整理问题记录.md` 74 条全部结案）
- 相关脚本、报告、进度文档、HTML 回退处理记录均已同步更新并提交 Git

#### 术语表 Phase 1~3（✅ 完成）
- **Phase 1**：修复"推荐翻译"污染（50+ 术语）、拆分"其他"分类 75%→41.3%
- **Phase 2**：生成 `术语提取报告_优化版.md` 与 `PF_缩写表.md`
- **Phase 3**：1075 术语，15 分类 + 来源书籍，"其他"降至 **114（10.6%）**；`verify_phase3.py` 自动化验收全部通过；已知误分类全部修正（`Combat Expertise`、`Weapon Focus`、`Neutralize Poison` 等 20 项）

#### 职业 chunk 质量攻坚 V001~V009（✅ 2026-07-21~23 完成 9 轮迭代）
详见 §3B。已沉淀：5 类 Processor、9 个 Provider 链、27 种 subtype、1192 chunk 去重、WORKFLOW.md 标准化迭代流程、4 类典型问题闭环（001~004）。

### 3.2 当前术语统计（15 分类 + 来源书籍，1075 术语）

| 分类 | 数量 | 占比 | 备注 |
|------|------|------|------|
| 法术 | 558 | 51.9% | 含 `Detect Evil`、`Dimension Door`、`Neutralize Poison` 等 |
| 专长 | 80 | 7.4% | 含 `Craft Wondrous Item`、`Weapon Focus`、`Combat Expertise` 等 |
| 职业能力 | 122 | 11.3% | 含 `Fast Movement`、`Class Skills` 等 |
| 状态/条件 | 7 | 0.7% | `Light Blindness`、`Filth Fever` 等 |
| 装备/物品 | 88 | 8.2% | 含 `Forge Ring`、`Flaming Burst` 等 |
| 技能 | 11 | 1.0% | `Perception`、`Sense Motive` 等 |
| 怪物/生物 | 9 | 0.8% | `Deep One`、`Shadow Mastiff` 等 |
| 动作/战技 | 0 | 0.0% | 已合并至专长或规则概念 |
| 位面 | 10 | 0.9% | `Ethereal Plane`、`Material Plane` 等 |
| 神祇 | 18 | 1.7% | `Cayden Cailean`、`Baba Yaga` 等 |
| 种族 | 8 | 0.7% | |
| 地域 | 6 | 0.6% | |
| 组织/势力 | 5 | 0.5% | `Pathfinder Society` 等 |
| 规则概念 | 15 | 1.4% | `Hit Die`、`Saving Throw` 等 |
| 来源书籍 | 24 | 2.2% | `Ultimate Magic`、`Core Rulebook` 等 |
| **其他** | **114** | **10.6%** | 已满足 <20% 目标 |

### 3.3 已知问题

> 向量化 KN 权威登记表：`pf_data/phase1/docs/已知问题记录.md`（法术时代 KN001~024，状态以该文件为准；下方 §3B 的 KN001~005 为职业时代历史记录）。法术剩余：A/C 类维持登记 + KN020~024 登记不修（**KN019 D 类 23 条全部闭环 2026-08-04：第一类 20 条 + B 类 3 条守卫修复 chunk 4221→4175；第二类 3 条跨行 HTML 残留（page_1177_0000/page_1365_0191/0188）守卫扩展 + 源数据补中文名「手舞足蹈」修复 chunk 4175→4172、pytest 642、verify_spells 全过——go/no-go 项闭环**）。

#### 🟡 中优先级
1. **根目录重复副本**：`pf_rules_md_organized/page_*.md` 等早期复制留档与新的聚合文件重复
2. **"其他"分类仍有 114 个**：虽已满足 <20% 目标，但可继续细化拆分到职业、种族特性、法术成分等子类

#### 🟢 低优先级
3. **全局去重**：跨来源书的同名条目（如 `Fervor Juice`、`波涛骑士团`、`Aquachymist` 等）需统一或建立链接（专长模块将以"一览聚合页去重"试点）
4. **术语关联关系**：法术↔职业↔专长 的关联尚未建立（二期准备）

---

## 3A. 方向决议（2026-07-21，职业 chunk 质量攻坚）

背景：职业 chunk 已全量产出（10495 chunks / 42 职业），但女巫、圣武士抽查发现质量不高；修复模式为"改脚本适应格式"，成本高且互相引入回归。经讨论确立新模式：

### 决议 1：准确率标准（按错误类型分级）
- 归属错误（职业/来源书）、变体漏识别/误识别：**目标 100%**，验收必须覆盖
- chunk 边界切分不精确：容忍少量噪声，不投入精力

### 决议 2：修复模式从"改脚本"转为"改源数据"
- 脚本只认一种规范格式（如 `## 中文名（English）【XX变体】`），发现新格式 → 修源文件（补结构标记），不改脚本代码
- 格式簇驱动：先对源文件做结构指纹聚类，同格式文件共享一次修复 + 一次验收，不再逐职业抽查
- 验收先行：每格式簇从 CHM 目录导出 expected 清单建 verify 基线（含 negative test），再动手修

### 决议 3：范围与顺序
1. 职业类目全格式簇验收通过 → 2. 重构脚本（见 4.3）→ 3. 接入法术类目（类目层抽象与重构一次做完）
- 职业未验收完不进法术

### 决议 4：源文件原地修改，不做目录 copy
- `pf_rules_md_organized/`（4999 个 md，83MB）已 100% 被 git 跟踪，原地修复 + 按格式簇分批提交即可 diff/回滚
- 开工前打基线 tag `pre-normalization-baseline`

### 决议 5：含专项覆写的处理模块改动前的不变量清单（2026-07-21 沉淀，源于 KN004 复盘）
修改任何含专项后处理覆写（subclass override / `_fix_*` 函数 / 文件专属 Processor）的核心处理模块前，必须先回答"本次改动涉及哪些结构不变量（heading 层级、chunk 边界、归属、来源书等）"，并在 `verify_*.py` 中对每条不变量有断言，跑通后才算完成。chunk 级"OK 数合理"不构成验证；negative test（"不该出现的 chunk 没出现"）同样必要。

---

## 3B. V001~V009 迭代完成情况（2026-07-21~23）

### 迭代时间线

| 轮次 | 范围 | 关键变更 |
|------|------|---------|
| **V001** | 变体误识别 | 修复圣律沿循者子誓约被误识别为独立变体（`#004`）；新增 `verify_no_false_archetypes.py` |
| **V002** | 汲毒巫、女巫 P&P | 修复 P&P 女巫巫术错误 chunk 与缺失 chunk（`#d30919b`） |
| **V003** | 汲毒巫变体 | 修复变体数据截断与错置（`#75ae0b2`） |
| **V004** | 吟游诗人 | 补齐 68 首传世名作 Bardic Masterpieces（`#03e41a0`） |
| **V005** | 操念使+吸血鬼猎人 | 发现 KN003（操念使 404 个原力无 subtype）+ KN004（吸血鬼猎人源文件格式） |
| **V006 Phase A1** | subtype 扩展 | subtype_mapping 扩展 13 项；27 种 subtype（原 12 种）；CLASS_DEFAULT_BOOK；Unchained 狂暴之力修复 |
| **V006 Phase A2** | 类隔离 Processor | 新建 Oracle/Warpriest/Summoner/Shifter 4 个 Processor；create_processor 路由 |
| **V006 Phase A3** | subtype 误标清理 | 76 项误标清理；新增 `cleanup_subtype_mismatch.py` + `verify_subtype_coverage.py` |
| **V006 Phase B** | 跨类错归 | 杀手目录移除 page_59（Ranger 内容错归，28 chunk 消除）；纯洁勇士多职业合辑拆分 |
| **V006 Phase C** | 通用去重 | `dedupe_all_chunks.py` 标记 1192 deprecated chunk |
| **V008 Batch B+D** | Processor 扩展 | OracleProcessor 新增秘示域→revelation（先知 28→86）；SorcererProcessor 新建（术士 15→228） |
| **V008 Batch C** | 源文件修复 | 圣骑士 page_562 加 `(English)` 括号，overview 13→7；战士 page_1218 加 `## 职业概览` 锚点 |
| **V009** | 来源书判定 | **AggregationTableProvider** 解析 33 个聚合页顶部来源书表格，置信度 65；野蛮人 page_36 CRB 157→77 |

### 当前 chunk 数据规模

```
541 规范文件 → 13895 chunks
                 ├─ 42 职业
                 └─ 1088 archetype
chunks.jsonl   20 MB
index.json     1.4 MB
```

### 本次迭代（2026-07-24）新增产出

| 产出 | 说明 |
|------|------|
| `VECTORIZER_ARCHITECTURE_DESIGN.md` v1.2 | 终局架构：7 模块包结构 + 16 项设计决策 + TDD 6 类测试 + 审计三级流水线 |
| `WORKFLOW.md` v2.0 | 类目无关化 + 根因驱动审计 + 5 分支决策 + 反馈闭环（Step 0~5） |
| 目录整理 | `pf_data/` + `phase1/` 根目录 417→71 文件，历史归档到 `_archive/` |
| KN004 已修复 | 吸血鬼猎人源文件规范化（commit 3b6dc1d） |
| 156 未知来源已修复 | 当前 book_abbreviation = `?` 或空 = **0 条** |
| 职业模块暂停 | 等法术接入时触发 CategoryPipeline 重构 |

### 沉淀的基础设施

**5 类 Processor**（`create_processor()` 按 class_name 路由）：
```
FileProcessor（基类，模板方法 build_chunk/resolve_source/infer_feature_subtype）
 ├─ WitchProcessor       （巫术来源表 page_92 解析 + 庇护主识别）
 ├─ PaladinProcessor     （_fix_paladin_page_55 子钩子，lookbehind (?<=[^#])）
 ├─ OracleProcessor      （V008 扩展：秘示域→revelation）
 ├─ WarpriestProcessor   （V006 新建）
 ├─ SummonerProcessor    （V006 新建）
 ├─ ShifterProcessor     （V006 新建）
 └─ SorcererProcessor    （V008 新建：血统→bloodline）
```

**9 个 SourceProvider**（链式置信度聚合，`resolve_source()`）：
| 置信度 | Provider | 触发条件 |
|---|---|---|
| 95 | ExplicitMarkerProvider | HTML 注释 / `> 来源：` / `出自《...》` |
| 85 | 文件名/目录名 Provider | `OO_圣骑士变体.md` |
| 80 | ArchetypeMasterProvider | 变体主表 |
| 75 | InlineSourceProvider | 当前块前 800 字 / 前一块末尾 / 标题 |
| 65 | **AggregationTableProvider**（V009） | 聚合页顶部 Markdown 来源书表格 |
| 60 | DirectoryTocProvider | 目录/CHM TOC |
| 30 | ClassDefaultProvider | 职业默认书 |
| 20 | ContainerDefaultProvider | 容器默认书 |
| 10 | CRB 兜底 | 兜底 |

### 已闭环问题（001~004）

详见 `pf_data/phase1/问题与修复记录.md`：

| ID | 问题 | 状态 |
|---|---|---|
| **001** | 行首图片链接导致加粗变体标题无法识别 | ✅ 已关闭 |
| **002** | 女巫巫术/庇护主来源书错标 | ✅ 已关闭 |
| **003** | 圣武士/圣骑士变体来源书错标 | ✅ 已关闭 |
| **004** | 圣律沿循者子誓约误识别 + heading 降级 | ✅ 核心已修复，遗留 3 项源数据问题 |

### 当前 KN 状态（5 个，2026-07-24）

| ID | 问题 | 严重度 | 状态 |
|---|---|---|---|
| **KN001** | 聚合页来源书未解析 | 中 | ✅ **V009 已修复** |
| **KN002** | 唤魂师 emotional_focus 无 subtype（15 个） | 中 | 暂不修 |
| **KN003** | 操念使 404 个原力类型无 subtype | 中 | 暂缓（等源文件结构修复） |
| **KN004** | 吸血鬼猎人源文件格式 | 高 | ✅ **已修复**（2026-07-24） |
| **KN005** | 战士 289 / 游荡剑客 135 个 class_feature 无 subtype | 低~中 | 暂不修 |

**已闭环**（不在 KN 列表中）：156 条未知来源 → 已修复归零（2026-07-24 确认）

详见 `pf_data/phase1/docs/已知问题记录.md`。

### WORKFLOW.md（2026-07-23 新增，标准化迭代流程）

`pf_data/phase1/docs/WORKFLOW.md` 沉淀：
- 4 步迭代流程（审计 → 分类 → 修复 → 验证）
- 5 Group subagent 并行审计结构（A 核心战斗 / B 核心施法 / C 技能隐秘 / D 召唤异界 / E 混合特殊）
- 8 种问题类型分类法 + 风险评估矩阵（🔴 高 / 🟡 中 / 🟢 低）
- 修复方式选择决策树（改脚本 / 改源数据 / 后处理）
- Subagent prompt 模板
- Type 2 修复 checklist
- 新增 subtype 决策流程
- 当前基础设施索引

### 待启动（V001~V009 后）

- [x] **主脚本重构**：`vectorization_prep_profession.py` 4112 行单文件 → `vectorizer/` 包 ✅（法术模块落地，见 §3D）
- [x] **KN004 吸血鬼猎人**：源文件规范化完成（commit 3b6dc1d），23 个独立 chunk
- [ ] **KN003 操念使**：404 个原力类型需源文件结构修复后才能 subtype 化
- [x] **职业验收后接入法术类目** ✅（§3D，类目层抽象随法术/专长逐步落地，见架构文档 §7/§8）
- [ ] **专长模块** 🟢 chunk 化完成（召回 1061/1061 = 100%，5948 chunks）+ 元数据设计 ✅（架构决策 29 人工门 2 通过）+ 元数据提取 ✅（registry_feat + infer_metadata，2026-08-02 重跑产物落地）+ K7 格式修复 ✅（KN069-071/076/078/081-083/075 闭环，KN072 连带消解）+ chm_toc_path 映射表 ✅（未知 1780→136）+ 造物专长一览行内来源顶层提升 ✅（54 chunks，conf=65，源数据修复二轮后正文独立切分 45→54）+ KN084 feat_type 污染 ✅（2026-08-03 闭环，泄漏 180→0，见 §3E-13）→ **下一步：source_spec / 检索端形态降权**（§3E）
- [ ] **二期准备**：术语关联关系、Build 数据、车卡辅助接口

---

## 3C. 跨模块泛化路径（职业→法术→其他类目）

职业模块的 V001~V009 迭代沉淀了**可复用基础设施**与**职业特有部分**两层。后续接入新类目（法术/专长/装备/怪物）时严格区分复用与新建。

### 3C.1 通用层（任何类目都适用）

| 组件 | 说明 |
|------|------|
| `WORKFLOW.md` | V/N 迭代流程（4 步 / 5 Group / 8 Type），类目替换即可 |
| **SourceProvider 链**（9 个） | 来源书判定通用框架，所有 chunk 的公共问题 |
| **FileProcessor 模板方法** | `build_chunk / resolve_source / infer_*_subtype` 三钩子 |
| **verify_*.py 框架**（11 个） | 数量下限 + 正向 + 负向 三件套模式 |
| **normalize_*.py 脚本模式** | 剥离 `**` + 正则识别 + 替换为 `##` 标题 |
| **cleanup / dedupe 后处理** | 按 key 分组保留最优 |

### 3C.2 职业特有层（不要泛化复制）

| 组件 | 说明 |
|------|------|
| `subtype_mapping`（27 种） | 职业能力子分类（hex/patron/bloodline/revelation 等），法术/专长不适用 |
| `archetype_masters` 主表 | 变体识别 + 来源书继承，仅职业有"变体"概念 |
| `_fix_paladin_page_55` 等特判 | 单一职业/单一文件的专项覆写，新类目需新建 |
| `WitchProcessor.parse_witch_hex_source_table()` | 女巫巫术来源表专解 |

### 3C.3 跨模块路径与触发条件

```
当前进度：
职业模块（V001~V009 ✅） ─→ 法术模块 ─→ 专长模块 ─→ 装备/物品 ─→ 怪物/生物
                                │
                                ▼ 触发 CategoryPipeline 重构（一次性）
                          vectorizer/ 包
                          (pipeline / formats / processors / fixups / verify)
```

| 模块 | 优先级 | 依赖 | 备注 |
|------|--------|------|------|
| **法术** | P0 | 职业（已就绪） | 触发 CategoryPipeline 重构；术语表 558/1075 是法术；与职业能力耦合（spell-like） |
| 专长 | P1 | 职业（很多专长属职业特性） | 复用 Provider + Processor；新增 `FeatProcessor` |
| 装备/物品 | P2 | 法术（魔法物品需法术关联） | 含防具/武器/魔法物品；术语表 88/1075 |
| 怪物/生物 | P3 | — | 量大但相对独立 |

### 3C.4 CategoryPipeline 抽象触发条件

> 完整设计见 `pf_data/phase1/docs/VECTORIZER_ARCHITECTURE_DESIGN.md`。

**Why 推迟？**（2026-07-20 与用户对齐）
- 第二个类目（法术）接入时一次性做完最经济
- 单样本（仅职业）猜不出边界，硬抽象会过度设计

**触发条件（任一即触发）**：
1. 法术模块开始接入
2. 第三个类目（专长）需要接入
3. 职业模块验收全量通过 + 至少 1 周稳定期

**终局架构**（7 模块）：

```
pf_data/phase1/vectorizer/
├── pipeline.py       # 流水线编排 + 类名规范化
├── diagnostics.py    # 源文件质量诊断门（处理前）
├── audit.py          # 通用审计引擎 Tier 1~3（处理后）
├── formats/          # Phase 1 normalize + Phase 2 promote 两阶段
├── processors/       # FileProcessor 模板方法（三钩子）+ 类目注册
├── fixups/           # 特判 @fixup 装饰器 + 不变量校验
├── sources/          # SourceProvider 链（置信度 10~95）
├── tests/            # TDD 6 类普适测试
└── verify/           # 集成回归验收
```

**前置条件**：4112 行单文件中 5 个 Processor + 9 个 Provider + 27 种 subtype_mapping 已是天然模块边界，重构时按此切分（不是从零切）。

### 3C.5 法术模块的特殊性（与职业的差异，提前对齐）

- **无 archetype 概念**，但有 school（防护/塑能/死灵/咒法等）
- **来源书判定更简单**：法术通常单文件单来源（不像职业一页多书）
- **数量远大于职业**：558 法术 vs 42 职业
- **可复用 vs 新建**：
  - 复用：SourceProvider 链、FileProcessor 模板方法、normalize/dedupe/cleanup 模式
  - 新建：`spell_school_mapping`（替代 `subtype_mapping`）、`SpellProcessor`（含 school 推断）

---

## 3D. 法术模块（✅ v1.0 验收闭环，2026-07-28~30）

> 里程碑 tag：`spell-module-v1.0-20260730`；架构基线：`pf_data/phase1/docs/VECTORIZER_ARCHITECTURE_DESIGN.md` v2.0（决策 1~29）

### 产出规模

- **4200 chunks**（4199 法术 + 1 法术索引），**15 个元数据字段** + `field_status` 三态（parsed/missing/not_applicable）
- `vectorizer/` 包落地：pipeline / formats / processors / sources / registry / diagnostics / audit / verify / tests（**pytest 264 通过**）
- **召回验收**：26 职业法术列表 258/259 = **99.6%**（`verify_spell_list_recall.py`，唯一缺失"起舞于黯"已登记 KN022）

### 过程资产（专长模块直接复用）

- **KN 体系**：KN001~024 全部闭环或登记（`pf_data/phase1/docs/已知问题记录.md`）。剩余：A/C 类登记、KN020~024 登记随 KN020+ 迭代（**KN019 D 类 23 条全部闭环 2026-08-04：第一类 20 + B 类 3 守卫修复；第二类 3 条跨行 HTML 残留守卫扩展 + 源数据补中文名「手舞足蹈」，chunk 4175→4172、pytest 642、verify_spells 全过**）
- **5 轮审计 → 8 项流程补丁**：基线快照 / regen 单入口 / verify-audit 同口径 / 豁免程序 / 复算命令红线 / 清单机检 / 宽启发式 / 裸数字 grep
- **Prepare Phase 范式**：勘探 → 格式簇 → 源数据规格 → 测试种子，法术已验证可拦 13~15/24 条 KN
- **产出即检三件套**：title 合法性 / 字段值健康度 / 列表召回率，首轮即检（正则缺陷类 KN 唯一防线）

---

## 3E. 专长模块（✅ Prepare 已关闭 + K5/K6 源数据修复 召回 100% + K7 格式修复 + 元数据设计人工门 2 通过 + chunk 化完成 + 元数据提取落地，2026-07-30 启动）

> 分支：`feat/feat-module`；文档目录：`pf_data/phase1/docs/专长/`
> 终审结论：`docs/专长/Prepare_Phase_三轮返工终审结论.md`（commit `5bdba32`）

### 启动资产（已就位）

| 资产 | 位置 |
|------|------|
| 开工前文档（8 补丁包 + 五合一扫描 + 资产四分类 + 7 步顺序） | `docs/专长/专长模块开工前_流程抽象与预防清单.md` |
| Prepare Phase 交接包（17 批 ×≤200KB / 190 文件 / doc_role 五分类 / HTML 回溯） | `docs/专长/Prepare_Phase_交接文档.md` |
| 分批清单 | `vectorizer/exploration/专长/prepare_batches.json` |
| 机检产出 ✅ | `prepare_scan.py` → scan_report.md + machine_scan.jsonl + audit_baseline.jsonl（**1226 行 / 1067 专长 / 8 来源书**） |

### Prepare Phase 收尾状态（2026-07-31 ✅）

- **产出**：189 份逐文件勘探记录（`专长_per_file.jsonl`），estimated_count 合计 **3635**，verify 8 项阻断全过
- **审计链**：首轮有条件通过（R1~R5）→ 二轮 `871856e` 基本通过（T1~T5）→ 三次 `ee255ef` 通过 → 三轮 `5bdba32` **通过关闭**（T6：幻影 raw_example 84 条清零 + 12 份编号文件错位报告整体重推导）
- **固化闸口**（后续模块复用）：`t63_census_audit.py`（raw_example 逐字普查 + 6 种合法放行形态）/ `t63_firstlast_check.py`（first/last 自包含，跨文件串扰确定性信号）/ `t63_phantom_forensics.py`（幻影三分类取证）
- **汇总阶段待消化**：file 字段前缀口径 29 份、同书多份并存（编号系列 vs 书名目录取主版本）、6 种放行形态写入 format_clusters 规范、偏差>20% 132 文件既有基线

### K5/K6 源数据修复与召回（2026-08-02 ✅ 100%）

> 攻坚决议：数据问题改源数据层（`fix_feat_*.py`），解析器不动（真 bug 除外——`_RE_TABLE_CONT` 注释与实现矛盾，TDD 修复）

- **召回轨迹**：78.2%（K5 开工基线）→ 89.7%（`4aa3887` 核心书修复）→ 96.2%（`5872f36` 拆行支持跨行英文名+〔类型〕）→ **100%**（`aa6b3ff`，1061/1061，`verify_feats.py`）
- **口径**：audit_baseline 原始 1226 行 → (name_zh, name_en) 联合去重 1072 → 噪声清洗合并 11 组 → **1061**；命中 = chunk.title/aliases 集合**精确成员匹配**（非子串）
- **三层根因**（缺口 41 → 0）：
  1. **表格行 `\r` 定位符**：CHM 转换产物 EN/CN 列用独立 `\r`（U+000D）分隔，Python `splitlines()` 将其当换行符 → 表格行腰斩成两半、条目全丢（37 条缺口，CRB/ARG/UC/UM 大部；page_195 专长表 ~150 行 → 0 产出）
  2. **`_RE_TABLE_CONT` 无行首锚定**（伴生解析器真 bug）：`\|` 可匹配上一行行尾闭合 `|`，完整表格行逐行粘成一行、仅首行产条目——修复加 `(?m:^)` 锚定 + 回归测试 `test_seed_05b_full_table_rows_not_merged`
  3. **基线噪声**：name_zh 尾随空白+全角空格、name_en 尾随句号/反引号，精确成员匹配永远失败（ACG 4 条）
- **修复脚本**：
  - `fix_feat_glue.py`（K5）：行内粘连拆行（跨行英文名+可选〔类型〕），page_199 189 处
  - `fix_feat_table_cr.py`（K6）：行中独立 `\r(?!\n)` → 空格，**4681 处 / 25 文件**（CRLF 行尾排除，`newline=""` 保留行尾约定）
  - `fix_audit_baseline_noise.py`（K6）：基线 45 行字段清洗（zh 尾空白 / en 尾标点 / 反引号→弯引号），幂等可复算
  - 表格行解锁后判别器 got 4290 → **5142**（亚产能 WARN 不阻断）；pytest 382 全过（含新回归测试）

### 执行分工

- **执行模型**（deepseek-v4-pro / minimax3，200k 窗口）：17 批语义勘探 → `per_file_BNN.jsonl`（✅ 含三轮返工）
- **k3**：机检 ✅ → 对账复核 ✅ → format_clusters 规范 ✅（`docs/专长/format_clusters_规范与偏差对账.md`，六放行形态人工确认门已过）→ test_seeds ✅（58 条驱动 TDD）→ **source_spec（待做）**
- **人工确认门**：
  - 门 1（format_clusters 六放行形态）✅ 2026-08-01 通过
  - 门 2（元数据 schema，架构决策 29）✅ **2026-08-01 通过**（`docs/专长/专长元数据设计.md`，6 项决策定稿：14 规范字段 + field_status 三态 + 任务链三阶段 `task_goal/task_reward/advanced_reward` + 造物字段族 `craft_cost/craft_conditions/craft_aura`）
- **元数据实现** ✅（Processor TDD `0ed27c0` 起落地）：`registry_feat.py`（`FEAT_CANONICAL_FIELDS`/`FEAT_FIELD_LABEL_ALIASES`/`FEAT_TYPES` 等）+ `processors/feat.py` `infer_metadata` 钩子（parse_fields 双格式 + prerequisites 结构化 + field_status 三态）。2026-08-02 重跑产物落地实测：benefit parsed 3344 / prerequisites 3271 / feat_type 1958 / format_cluster 5872（100%）/ 任务链三字段 82~94 parsed 其余 not_applicable / 造物三字段 6~7 parsed 其余 not_applicable——覆盖率与设计预期一致（lb_marker 索引行与无字段条目判 missing 属正确行为）

### 源数据实测要点（机检已证实）

- 断行英文名 1721 行 / 链接 `](http` 427 处（KN023 同型，头号预防项）/ 裸 CR 行内断裂 4500 处 28 文件（✅ 已修复：K6 表格行 `\r` 定位符 4681 处 / 25 文件，commit `aa6b3ff`）
- feat_type 在标题行 `〔战斗〕`（含复合 `〔战斗，团队〕`、双标签「重击 战斗」）；官方 10 类见 page_202 前言
- 三类特殊文档：概述页（page_194，元数据输入）/ 全专长列表（page_202，审计基线）/ 一览聚合页（去重 + sole_source 防漏）

### K7 空 text 调查与格式修复（2026-08-02 ✅ 纯洁勇士平账 8/8 + 2 伪条目清除）

> 调查触发：空 text chunk 全量排查（KN069 激励指挥官 P0 空 text）。SOP 原则：格式问题一律回原始 HTML 回溯确认（`~/.openclaw/workspace/pf_rules/page_515.html` 等）。

- **KN069（P0 已闭环）**：任务与战役_专长.md 激励指挥官「出自Quests and Campaigns」同行粘连（KN053 聚合重建退化形态）→ M1a 拆行后「出自」伪标题吞正文 → chunk 空 text。改源数据回齐 organized 根目录已验证形态（`fix_feat_inspirational_commander.py`，1 处拆 2 行）
- **KN070（P1 已闭环）**：4 星粘连家族 `中文（****EN****，类型）****正文`（转换器三连加粗段星合并产物，HTML 回溯确认**合法形态被脚本误杀 → 修脚本**）——`_RE_PAREN_NESTED_STAR`（括号内嵌套星剥皮，222 行全库正确）/ `_RE_CN_EN_ADJACENT_STAR`（括号外粘连 EN 剥星，英文开头+括号前瞻防 10574 行字段序列误剥）/ `_RE_BOLD_GLUE_SPLIT`（4 星粘连拆行）+ D 分支组2 排除括号（防 `（（EN））` 双括号）。6 目标条目全恢复（黄金军团 112 / 终焉之墙 122 / 吮毒 140 / 召唤善良怪物 1401 / 美德信条 1009 / 世界之伤 238），纯洁勇士 9→8 条平账 est=8；seed 11 elided→standard 行为变更（信息保留完整）；P2 残留：`**条件：****BAB` 4 星 + 空 `**` 行
- **KN071（P1 已闭环）**：A 分支列表续行误包伪条目（组3 逗号开头）——爱与和平/静思者 2 伪条目清除（全库 184 行候选实测仅 2 误包，守卫误伤面趋零），内容并入主条目 text
- **KN072（P2，部分随 KN075 消解）**：48 空 text chunk = 18 章标题 + 28 造物一览 lb_marker 索引 + 瓦瑞西亚 + ~~URL~~（URL 空 chunk page_553 链接行 + title URL 污染 1 个已随 KN075 `_strip_http_links` 消解，48→47，其余设计内登记不修）
- **KN073/KN074（P2 登记不修，追加）**：专长53/闹鬼专长 2 rel est 虚高（trace 差集 0，16 条目逐条核实全产出）；专长40 碎钢心境之秘 title 带 `【3.5R】` 前缀（HTML 回溯确认原书自带标记，召回 0 影响）
- **KN075（P2 已闭环，追加）**：KN023 同型链接 `](http` 源数据 427 处 → 产出残留 25 个 chunk 正文参考链接（18 文件：PA/DR/BotA/CoG/永罪之书/HHH 等已整理 + page_* 未整理）。修复：`_strip_http_links` normalize 层（TDD 7 测试 test_59~65，挂 `_mark_pfs` 之后）——三形态：①`[锚文本](httpURL)` 锚≠URL 留锚文本（HTML 回溯确认 `<A href>` 锚文本即有效内容）；②页头链接行整链剥空（含紧邻星壳，星壳紧邻匹配不跨空格）；③`](httpURL)` 残缺剥空。残留 25→0，`](http` 0 个；连带消解 KN072 URL 空 chunk（48→47）；章首 chunk 恢复 7 个；pytest 486 全绿；verify_feats 全过（召回 100%，5889→5888 chunks 唯一差异即 KN072 URL 消解）
- **KN076（P1 已闭环，追加）**：编注同行接条目标题——豭突势/雷灵/月夜虚招效果值后 `【编注…】` 非标点结尾漏拆行 → 化敌为盾/雷魂/月夜伏击者 3 条目完整正文被吞 + benefit 字段吞入下一条目标题+斜体描述。源数据拆行修复（`fix_feat_editorial_glue.py`，字节级保留行尾 diff 仅 3 行）：豭突势 393→182 字，3 条目独立 standard 恢复，5872→5875 chunks（+3），verify 5/5 + 召回 100% 保持
- **KN077（P2 登记不修，追加）**：根目录 `page_199.md` 旧副本（表格 `\r` 定位符形态 + 混合行尾 + 行内 `\r\n` 残留，直接 split 仅 3 standard 大坨粘连）——pipeline 同 stem 去重取 `专长/` 主版本，旧副本被跳过无产出影响；随「根目录重复副本清理」遗留项处理
- **KN078（P1 已闭环，追加）**：狂暴撞飞条目被狂暴投掷吞并（跨行英文名 `（Raging \nThrow…）` 使整理拆行漏拆 + 标题同行非行首）+ 「又译」注记污染 feat_type（产出级 2 chunk：诈欺师/抗拒死亡）。修复：源数据拆行 1 处（`fix_feat_title_glue_split.py`，diff 仅 1 行）+ `_split_paren_content` 剥离 `^又译` 段（TDD 3 测试，全库 78 形态统一不产类型）：狂暴撞飞 standard 恢复、5875→5876 chunks（+1）、feat_type 又译污染 2→0、verify 5/5 + 召回保持、pytest 460 passed
- **KN079（P2 登记不修，追加）**：无标题章节引言段吞入上一条目（季节之眼←万神殿引言 / 足下缠斗←冥想专长引言）——HTML `<STRONG>` 章节标题整理时星号丢失成裸段落，split 设计行为并入当前条目；判别器 est=got 一致无召回缺口，补标题方案无效（section header 跳过不产条目、段落仍并入 cur），留待章节级 chunk 化设计
- **KN080（P2 登记不修，追加）**：同行注记并入字段值（触发导能【能力速查】/专职工匠【例如】）——同条目原文补充注记非字段标签形态，parse_fields 边界并入上一字段值；内容完整无损，随元数据字段净化阶段处理
- **KN081（P1 已闭环，追加）**：4 星粘连系列名括号标题（page_566 能力掌握/力场盾掌握/武器觉醒掌握 3 条目被吞）——`**中文**** EN(****系列名****)**` 半角括号 4 星形态 `_RE_ELIDED_QUAD` 不消费、`_RE_QUAD_STAR` 配对剥星致全标题正则失配。修复：`_fix_mastery_series_paren`（链序先于 `_fix_quadruple_star`，行尾 `$` 锚定防误伤）→ elided 标准标题，系列名进 feat_type
- **KN082（P1 已闭环，追加）**：page_744 数学魔法节同行条目（`<BR>` 段落边界转同行致整节挤一行，split 无标题可认 → 段落并入 cur=None 丢弃，数学魔法引言 + 算术占卜/神圣几何学/算术思维 3 条目彻底丢失）。修复：HTML 回溯确认 `<STRONG>` 独立标题段 → 源数据拆行 13 处（`fix_feat_page744_split.py`，锚点唯一性校验 + 字节级 CRLF/LF 保留）+ split FC-8n 字段标签佐证扩展
- **KN083（P1 已闭环，追加）**：冒号标题粘连（page_529 6 条 + page_530 10 条正文静默丢失）——`**中文[：:]\*{0,2}英文\*{2,}**` 三形态残留（全角冒号尾 4 星 / 半角冒号英文闭合星 / **4 星开头+2 星尾** page_530）；判别器 FC-3b 带冒号变体不匹配 → est=got 假一致未报警。附带根因：organized CRLF 行尾使 `_RE_CROSS_EN` 跨行合并失效（`Blinding \r\nFlash` 不合并）。修复：`_fix_colon_title_glue`（守卫字段标签/翻译署名）+ `_fix_label_trailing_star`（剥字段标签残留星防伪条目）+ `\r?\n` CRLF 兼容（LF 不受影响）
- **结果**：召回 1061/1061 = 100% 保持；5876→5889 chunks（+13 条目恢复：page_566 3 + page_744 3 + page_529 6 + page_530 10 = 22 恢复，净 +13 含边界合并）；pytest **479 passed**；verify 8 项全过；title 空 0、空 text 48 无新增

### 后续步骤（开工文档 §六 7 步，实际进展 2026-08-02）

| 步 | 内容 | 状态 |
|---|---|---|
| ① | Prepare 勘探 | ✅ 2026-07-31 三轮返工通过关闭（189 份勘探、3635 est） |
| ② | 元数据 schema 设计（人工门） | ✅ 架构决策 29 已出，人工门 2 通过（2026-08-01） |
| ③ | 补丁包配齐 | ✅ 39 个 `fix_feat_*.py` 源数据修复已执行（KN035~KN071 系列） |
| ④ | 修 KN023 | ✅ 已闭环（2026-08-02）：`_strip_http_links` 三形态清洗（KN075），残留 25→0，连带消解 KN072 URL，pytest 486 全绿 |
| ⑤ | TDD `formats/feat.py` | ✅ 457 tests（seed 06 家族/4 星粘连/列表续行守卫等全回归） |
| ⑥ | 产出即检三件套 + 召回 | ✅ verify_feats 全过：召回 **1061/1061 = 100%**、5872 chunks、title 空 0、空 text 48 设计内 |
| ⑦ | V/N 迭代 | ✅ 产出即检首轮（`产出即检_首轮_20260801.md`）；K7 空 text 调查 + 格式修复（KN069~074）完成 |

**当前阶段（2026-08-02 起，chunk 质量巡检）**：
1. **source_spec 阶段**（§七 第 2 条）✅ 已做（2026-08-01）：`vectorizer/exploration/专长/专长_source_spec.md` 产出（189 文件勘探 + 五合一扫描）；来源书判定 `MdMappingTocProvider` 纯富化模式已在元数据设计（架构决策 29）定稿
2. **k3 汇总遗留消化** ✅ 已做（2026-08-01）：file 字段前缀口径（29 份，已统一）/ 同书多份取主版本（pipeline 按 stem 去重）/ 6 种放行形态入规范（已入 format_clusters 文档）/ 偏差对账（+629/+17.3%，`format_clusters_规范与偏差对账.md` 四节接管）——汇总交付三件套：source_spec / test_seeds（58 条）/ format_clusters 均就位
3. **chm_toc_path → 书缩写映射表** ✅ 已落地（2026-08-02）：`docs/专长/chm_toc_path_映射表.md`（83/85 文件，跨书索引类 page_1367 超魔专长一览 91 + 造物专长一览 45 不映射）+ `apply_chm_toc_mapping.py`（doc_id 粒度套用，conf=70 与既有目录判定档一致）；**未知 1780 → 136（92.4% 消解）**，顺带修正既有残缺缩写 'Handbook' 14 chunks → DSH；verify_feats 全过（召回 100%，结构不变）；映射表作为跨模块通用资产复用。注：pipeline 已内置来源判定链（页头书名/chm_toc_path 目录），重跑后 apply 脚本实际映射 0 个（兜底/校验语义），未知剩余 145 = page_1367 91 + 造物专长一览 54（后者由行内来源顶层提升消解，见第 4 条）
4. **KN030 ②③类自动消解**（✅ 方案已定，部分随映射表落地）：②页头有《书名》但判定链没识别（page_200《极限战役》/page_555《近战工具箱》）——随映射表已消解（mapping 直接判）；③行内【CRB】等标注没接住（造物专长一览）→ ✅ **已闭环（2026-08-02）**：`apply_feat_creation_source_promote.py` 按 metadata.source 顶层提升 54 chunks（28 列表行标注 + 4 正文出处 + 3 期刊出处 + 19 空源条目归属补源，conf=65 行内标注档），前置源数据修复二轮：子物品标题跨行 3 处（施法者刺青/贮法刺青/法术刺青）+ 铭刻符文标题缺闭合星（HTML `<BR>` 在闭合标签前），正文条目独立切分（45→54 chunks），期刊缩写 PF16/PF74/PF5 新增（Endless Night / Sword of Valor / Sins of the Saviors，PF_缩写表登记）
5. **检索端形态降权**（三形态，format_clusters 规范 §五 用途 + KN085）：①elided 名称截断条目不参与精确标题匹配；②空 text chunk（KN085 最终口径，51 个 = 28 feat_index + 22 章首导航标题 + 瓦瑞西亚，HTML 追溯无正文，向量检索天然不可命中）不参与正文答案生成；③feat_index 命中时用元数据（来源/英文名/类型）组装回答；④**feat_index 与 feat 正文条目重复去重（KN093）**：1715 个唯一 title 中 1176 个双形态并存（同专长速查表摘要行 + 正文详述，约 19.8% chunk 有重复对），检索端按 title/aliases 去重、命中 pair 优先正文条目，feat_index 降权——数据仓库层不动，随检索逻辑一并实现（与 KN092 feat_index 元数据组装同批）；⑤**feat_intro 介绍性 chunk 降权（KN094）**：57 个（23 章首空 text + 34 类别介绍段）标 `component_type=feat_intro`，先于具体条目命中时稀释回答质量，检索端对其降权
6. **KN075 链接残留清洗** ✅ 已闭环（2026-08-02）：`_strip_http_links` normalize 层（TDD 7 测试），残留 25→0，连带消解 KN072 URL（空 text 48→47），章首 chunk 恢复 7 个，pytest 486 全绿 + verify_feats 全过
7. **KN086 流氓剑条目回归修复** ✅ 已闭环（2026-08-02）：page_556「阴招制敌」4 星译名行（HTML 黑色非粗体 `<B normal>` 段，转换器 4 星包裹误识别为独立标题→空 text 伪条目）+ `\r` 定位符残留（aa6b3ff 表格行清洗漏网，splitlines 腰斩标题行）。源数据 3 行合并为单条目标题 `**流氓剑/阴招制敌（Dastardly Trick，战斗，派头专长）**`（`fix_feat_page556_dastardly.py` 字节级，双名「/」分隔对齐制造波普宠/制造人偶先例，双括号会让「阴招制敌」误入 feat_type）。空 text 48→**47**（回到 KN085 口径）；verify_feats 全过（est=4177 got=5950，静默丢失 0）；pytest 492 全绿；KN085 口径同步更新
8. **KN087 page_1367 详述区修复** ✅ 已闭环（2026-08-02）：末日法术正文被吞入拟鬼之术 chunk（「详细」导航标记 4 星包裹残留 + 末日法术标题缺开头星 → 标题识别失败 → 详述区首条粘进表格区末行）。`fix_feat_page1367_doomsday.py` 字节级删「**详细****」行 + 补开头星 → 拆分成功（拟鬼之术恢复纯表格行、末日法术正文独立 chunk），page_1367 91→92、全库 5896→5897；同页纯净法术正文原书重复 ×2 + 蚀日法术红字吐槽（HTML `COLOR: red` 译者批注）登记不修（原书自带）
9. **KN088 表格行对齐空格归一化** ✅ 已闭环（2026-08-02）：HTML 表格英文名单元格单空格 → 转换器 `&nbsp;` 对齐序列转多空格 → title 152 + aliases 371（30 文件）污染。`build_chunk` 字段归一化（`" ".join(s.split())`，TDD 1 测试）→ 全库清零；chunk 总数不变（纯字段清洗）；pytest 493 全绿
10. **KN089 红色多段加粗标题星壳碎片化** ✅ 已闭环（2026-08-02）：HTML 红色标题拆成多个相邻 `<B>` 段 → 转换器逐段星壳（`**中文（****EN****）****〔****类型〕******`）→ `_RE_BOLD_GLUE_SPLIT` 拆行后残留独立行 `**〔**战斗〕****`（page_197 41 chunks text 开头污染 + feat_type 丢失）。`_normalize_custom` 链 `_fix_quadruple_star` 之后新增 `_merge_type_seg_line`（`_RE_TYPE_SEG_LINE` 合并〔〕类型段回标题行，TDD 1 测试）→ 残留 41→0、page_197 feat_type 恢复 55 个；附项 page_194 冒号独立加粗段（`****：**` 空标签 3 处：擒拿手流/百裂拳流/刚烈掌流）`fix_feat_page194_colon_bold.py` 源数据修复 → `**：**` 开头清零；verify 全过、召回 100%、pytest 494 全绿、chunk 总数 5897 不变
11. **KN090 星壳残留家族收口** ✅ 已闭环（2026-08-02）：速查表删除线壳（HTML `<B><S>` 转 `**~~中文（~~****~~EN~~****~~）〔类型〕~~****~~~~**`，`~~` 干扰 split 标题判定）→ 12 个造物系专长详细条目并入前条只剩 feat_index 索引（page_195/198/276 等 40+ 行）。normalize 链最前新增 `_RE_STRIKE_SHELL`（剥 `~{2,}` 恢复标准标题形态，TDD 3 测试）→ 调制药剂/制造权杖/荒芜重击/领导力等全部恢复独立 feat chunk；附项 D 分支 `_RE_BARE_CN_EN_STAR_BOLD` 组1 后 `\s*`→`\s+` 收窄 + 新增 `_RE_ELIDED_CN_EN_GLUE`（`**中文****EN` 紧邻 elided 归一，TDD 3 测试）→ page_311 三条 name 截断（情感导体→情感导）修复、page_529/530 字段行伪条目消除 4 个；chunk 总数 5897→**5934**（+42 速查表条目恢复 -4 伪条目）；pytest **512** 全绿；verify 全过、召回 100%、空 text 51 无回归（KN090 前后 bak/cur 对比清单一致，KN085 最终口径）
12. **KN091 译者/编者吐槽清除** ✅ 已闭环（2026-08-02）：专长 chunks 5 处吐槽（警觉「即神经质」/不屈凶暴「数死早」/精通长鞭熟稔「扯淡吧」/夜之血脉 2 处「闪光尘」「护尸符」）为原书 HTML 原生翻译注释，污染向量检索（非规则词成为条目特征）。源数据**字节级删除 5 处子串**（只删子串不重写整行，4 文件混合行尾天然保留；夜之血脉 2 处括号未闭合按「行内吐槽段」处理）。重跑 5934 chunks 不变、verify 8 项全过召回 100%、pytest 512 全绿、chunks「吐槽」残留 5→0
13. **KN084 feat_type 元数据污染** ✅ 已闭环（2026-08-03）：英文名泄漏 180 → **0**、神话标签缺失 3 → **0**，pytest 512→**522**、chunk 5934→**5948**、召回 100%、verify 5/5。四类修复（feat.py）+ 源数据 1 处：
    - **FC-1r 英文段优先**（消解 164）：MA 页 M8 形态 `**诅咒巫术（神话, Accursed Hex ）（Mythic）**`——`_split_paren_content` 含字母段是真英文名，`en_in_type or group(3)` 优先进 name_en；神话缺失 3（卓越法术/注定荣耀/参与神话）同步修复
    - **能力标记过滤**（消解 13）：`_ABILITY_MARKS = {Ex, Su, Sp}`（非专长类型）——FC-1q 命中则 feat_type 置空、标记前置正文首行（武艺无尽/钢铁勇气/庖丁解牛等进阶武器训练 + MTT 盗贼天赋）
    - **三括号星壳类型**（消解 2）：page_505 BBS 帖 `**圣水攻袭（战斗）****Holy \r\nWater Assault****（****Combat****）******` → `**中文（类型）（EN）〔**TYPE**〕**`——`_RE_NAME_TRAILING_CN_TYPE` 拆组1 尾部中文括号为类型、组3 星壳剥除中英同义去重（中文优先）
    - **「子节标题排除」守卫**：`_RE_ABILITY_MARK_LEAD`（text 以 `（Ex）` 行首开头）放行能力标记分支 standard 条目——标记前缀 5 字符可把 text 147→152 顶过 150 阈值（WMH 庖丁解牛回归）；**顺带救回 14 个长期误删真实进阶武器训练**（战技防御/擅长武具/以剑为盾等，bak 5934 本就少 13 个，5948 为完整数）
    - **源数据 1 处**（改源数据不改脚本）：武术手册「摔角手」feat_type `武僧及Uch武僧变体`——「Uch」= Unchained 缩写残留 → 改官方译名「掉链子」（正文「对于Uch武僧」同步，共 2 处，裸 LF 文件）

14. **KN095 正文区裸标题吞并** ✅ **已闭环（2026-08-03）**：page_311 正文区条目标题为 HTML 转换产物 `中文（类型）****EN`（**无前导星**），normalize 链所有裸标题正则均不覆盖 → split 不识别 → 全部并入前一个 elided 条目（`feat_page_311_0070` 移情感知吞 ~115 条 16028 字符、`feat_武器大师手册_专长_0081` 种族专长吞 15 条 5864 字符、page_555 微吞并 3 条）。**方案 A（源数据修复）执行**：`fix_bare_title_glue.py` 修复 **75 行**（page_311 子目录版 60 + 武器大师手册 15；page_555 子目录版无需修），无括号补前导星（`_RE_ELIDED_CN_EN_GLUE` 命中）、带括号改写标准形态 `**中文（EN）〔类型〕**`（FC-1q 识别）；**⚠️ 教训 1**：判别器矩阵 rel 为子目录版 `专长/xxx.md`，首轮误改根目录副本（git checkout 回滚后 FILES 改指子目录版）；**⚠️ 教训 2**：重跑 pipeline 后必须重跑**四**个后处理脚本（apply_chm_toc_mapping + apply_feat_creation_source_promote + backfill_chm_toc_path + backfill_feat_source），一度遗漏回填两脚本致 source 993→337、toc 回退，重跑后恢复（详见 `来源书链路修复方案.md` §五）。**结果**：chunk 总数 5948→**6022**（+74）、page_311 71→130 chunks、**全库 >5000 字符清零**（最大 1467）、新 chunk 元数据完整（英文名/book/toc 59/59）、feat_intro 57→**58**（「种族专长」类别标题拆出为介绍段，合理）、feat_index benefit 3/1871 修复前后一致（文档 1.5% 为旧错误统计，实测 0.2%）；verify 5/5、pytest 530、召回 1061/1061 = 100%、空 text 51 无回归。检索端护栏保留（text > 5000 降权，防未来回归，见 §3E-5 降权清单 ⑥）
15. **专长模块数据使用说明（交付文档）** ✅ 已交付（2026-08-03，KN095 闭环后数字已同步）：`docs/专长/专长模块数据使用说明.md`——**语义切分质量评估结论：满足一期 Agent 调用**（6022 chunks、召回 100%、verify 5/5、pytest 530、feat 4093 中位 196 字符条目级、book/chm_toc_path 100% 可溯源、英文名 98.0%/aliases 98.2%、feat_type 49.5%（feat 中）、benefit 84.9%（feat 中））；检索端注意事项全量清单（feat_index 元数据组装 KN092/093、feat_intro 降权 KN094、超大 chunk 通用护栏 KN095、拼组 chunk 定性、来源书四级口径、field_status 三态展示策略、后端对接速查清单）；数据变更规范（重跑 pipeline 后四后处理脚本必跑）

## 3F. 种族模块（✅ 全闭环：产出即检 + 首轮审计 + 全量核查 + 验收返修 + KN134/135，2026-08-05，#97~#101）

**状态**：**产出即检闭环 + 首轮审计闭环（2026-08-04，`26ea729`，k3 审计立项 §⑦ 5 项全过）+ 全量核查闭环（22 机制 M1~M22，KN113~129）+ k3 验收返修闭环（KN130~133，`ca4f26e`/`a7dbdb3`/`5fb8206`）+ KN134/135 残留闭环（2026-08-05，`51d9e02`，page_10 组标题归 race_intro + 译注/「：」行首/replaces 前缀清零）——模块告一段落；verify_races 六→八检查、终态 3654 chunks、pytest 843**

### 流程速览（#97~#101）

1. **TDD**（#97）：`test_race_format.py` 7 格式簇样本（A~H）→ 实现 `formats/race.py`（#98）+ `processors/race.py` + pipeline 注册（#99）→ verify_races 六检查 + cicd 装配 + 不变量扩展（#100，commit `d777ff7`/`e80ec0e`/`62d6465`）
2. **产出即检三件套**（#101）：title 合法性扫描 + 字段健康度 + 召回率 + 新正则触发计数 + 高危 probe——完整报告见 `docs/种族/产出即检_首轮_20260804.md`

### 终态数字（2026-08-04 全量核查 + 验收返修后）

- **pipeline 产出**：3654 chunks / 112 输入文件（2 豁免）/ 11 component_type（终态 2026-08-04 实测：alt_trait 859 / race_trait 679 / fcb_entry 631 / race_archetype 464 / race_feat 332 / race_item 253 / race_overview 152 / race_spell 134 / race_intro 103 / monster_block 32 / race_sidebar 15）
- **召回**：基线 37 种族 37/37 = 100%；verify_races **八检查**全过（六字段规范化比对 37/37 全一致 + 【7/8 page_11 行级召回】37/37 + 【8/8 page_752 component_type】59/59）
- **判别器回归**：矩阵 112 rel、静默丢失 0、矩阵覆盖外 0
- **pytest 836** + pipeline 重跑 + verify_races 八检查 + 数据不变量闸口全过（空 text 0、>5000 1/3、book '?' 2483 设计保留、toc 0）
- **产出对账**：est 2132 ↔ got 2390（+258，首轮审计后）；全量核查 22 机制批次修复至 3654（每个增减全定性，见 `docs/种族/全量核查问题汇总与修复计划_20260804.md` 进度表）

### KN 登记（2026-08-04）

- **KN098**：矮人汇总 29 条 race_spell 误判（章节关键字子串）——**已闭环**（KN103 修复，43 chunks 全 alt_trait）
- **KN099**：page_401-404 种族构建 4 文件产出 0（未整理页，设计豁免）
- **KN100**：title='毒素' 1（字段行伪条目既有行为，登记）
- **KN101**：K 簇修复闭环（怪物字段章节并入主条目，28 伪条目消除 + 差 1 待定位 R5）
- **KN102**：**字段链家族闭环**——四星嵌套字段链伪条目 41→0 + school 吞值修复（簇 I/I2）+ **豺狼人字段链首尾星壳误剥修复**（簇 I3：`**价格：**11000gp **重量：-**` 拆行后整行首尾星壳被 split 剥壳分支 1 误剥——守卫「剥壳后仍含 `**` 不剥」，TDD 2 测试）
- **KN103**：**race_spell 误判规模化修复闭环（首轮审计，P1）**——`_match_section` 双条件判据（组1 法术结尾 + EN `Spells?$` IGNORECASE / 裸标题无虚词 31 字集合）+ `_split_bare_section_titles` 虚词表扩展（防正文句截断包星）；race_spell 174→92、全库 2264→2390（+126 全定性，race_trait +156/alt_trait +37/其余 +16/sidebar -1）、正文句伪条目 8 消除；TDD 簇 I4/I5/I6 17 用例、pytest 629、cicd 全链过
- **KN104**：race_spell source 字段类目级缺口（92/92 missing，P2 **登记不修 2026-08-04**——修复前提不成立：race 全类目 0 个 `> 来源：` 引用块（feat 656 同款形态不存在）、race_spell 源数据法术块无条目级出自行；源数据层面缺口同 KN106 口径，chm_toc_path 100% 兜底溯源）
- **KN105**：page_814「种子密探」吞并 = 既有行为（章节切换不清 cur，P3 登记，三个时代行为相同非回归）
- **KN106**：book '?' 闸口参数变更 1450→1600（1404→1518 随 +126 聚合目录 chunk，E1 规则登记）
- **KN107**：**核心种族详情页输入缺口（P0，✅ 已闭环 2026-08-04：9 页纳入 +845 chunks，k3 终态审计正式通过）**——organized 根目录 9 页未纳入种族类目（page_12~18 七核心种族 + page_129 神裔 + page_245 魔裔），体貌/社会/关系/阵营宗教/标准特性正文全部无 chunk；KN077「根目录均为重复副本」假设对此 9 页不成立；验收报告 `docs/种族/KN107_KN109_KN112_汇总交付_k3验收报告_20260804.md`
- **KN108**：职业 CHM 范围缺口（根目录 7 页：page_411 幻灵/page_53 武僧清规/page_134 龙脉术士真实缺口 + 4 索引页）——登记，修复随职业模块重构（职业模块仍用旧单文件脚本，未用通用框架）
- **KN109**：专长 CHM 范围缺口（根目录 2 页：page_622 MA 神话引言/page_1563 流派专长一览，本体已覆盖缺汇总层）——登记，修复排在种族模块完结后

### 首轮审计（2026-08-04，k3 审计立项 §⑦ 执行）

- **报告**：`docs/种族/审计报告_首轮_20260804.md`——5 项全过（①race_spell 质量复核 92 全干净 ②字段解析终态（source 92/92 缺口 KN104）③判别器对账 est 2132↔got 2390 +258 ④召回 37/37 ⑤P1 KN103 审计内闭环）
- 产出即检 §⑥ 遗留表 R1/R2 状态已更新（R1 闭环、R2 复核+KN104）；R3~R6/R8 不变；R7 book '?' 1518（KN106）
- **遗留**：检索端语义降权评估（KN098/100 影响面，随一期 Agent 检索联调）；KN104 已复核登记不修（2026-08-04，见 KN104 条目）
- **二轮审计后新发现（2026-08-04，人工抽查）**：**KN107 P0 核心种族详情页输入缺口**（根目录 9 页未纳入，含审计要求——修复后须过 k3 审计立项复核）；KN108 职业 / KN109 专长同模式缺口登记（修复时机见 KN 条目）；排查报告 `docs/chm范围缺口排查_20260804.md`（脚本 `audit_chm_scope_gap.py` 可复算）

### 全量核查与验收返修（2026-08-04，交接文档 + k3 验收报告）

- **交接任务**：`docs/种族/种族chunk全量质量核查_交接文档_20260804.md`（KN113~120，六组 subagent 全量排查 A~F）→ `docs/种族/全量核查问题汇总与修复计划_20260804.md`（22 机制 M1~M22 三批次，全部闭环）
- **验收返修**：`docs/种族/种族全量质量核查_k3验收报告_20260804.md` 第五章——**KN130**（page_11 三族整行静默丢失找回，70→76）+ **KN131**（page_752 52→59 条全 alt_trait + page_398 全量修复 35→42）+ **KN132**（race_name 四级兜底链：intro 登记 > 路径归属 > 「X——Y」拆分 > title 兜底）+ **KN133**（边界/清洗残留家族 + CtIE 嗜火者 intro 吞并）
- **verify_races 六→八检查**（验收建议 5）：新增【page_11 行级召回】37/37 命中（源表 37 族 × 2 表对账）+【page_752 component_type】59/59，TDD 先行（`test_race_verify_checks.py` 10 用例），commit `5fb8206`
- **终态**：3654 chunks / pytest **843**（KN134/135 闭环后，2026-08-05 k3 复跑）/ verify_races 八检查全过 / 闸口全过（book '?' 2483 设计保留同口径，见 cicd verify.py 注释链）
- **KN134/135 闭环（2026-08-05，`51d9e02`）**：KN134 page_10 组标题/概念段 4 个 race_overview→race_intro；KN135 译注漏网 1 处 +「：」行首 7 处 + replaces「此特性替换」前缀全清零；k3 逐项实测验证 + 回归链全绿
- **遗留**：检索端语义降权评估（KN098/100 影响面，随一期 Agent 检索联调）；**另立任务**：阿斯托莫伊人 8 特性粒度拆分、page_401~404 构建规则（维持豁免）；KN104 已复核登记不修；**KN136 修复**（方案已定：spell 侧标题校验拒收 `[PZO` 开头伪标题，修复后 spell `test_chunk_count` 恢复 4172；排期：随 spell 模块重构批次解决）；**闸口双顶格参数审议**（race book '?' 2483/2483、feat 100/100，余量 0，用户拍板）

### 向量化设计优化批次（2026-08-05，step 7 文档回写）

A1/A2/A3/B1/B2/C1/C2 七项优化全落地，对应 commits：`92e6438`（A3 闸口余量 WARN）/ `a66df0b`（A1 `regen_race_chunks.sh` 单入口）/ `22f5c30`（A2 CI 矩阵加 race + 共享层 path 触发全量回归）/ `de1d3ce`（C2 audit 弃用收尾）/ `3abd644`（B1 行级召回检查泛化到 `verify/base.py`）/ `8340928`（B2 `entity_name_resolvers` 机制 + race 实体枚举 81+41 + verify 第 9 项判伪检查）。

验证基线：pytest **861**、race **3654 chunks** **九检查**全过、feat **6032** 全绿。

**双顶格遗留项**：race book '?' 2483/2483、feat 100/100，余量均 0。**首次双顶格审议已完成（2026-08-05，用户拍板）**：两侧存量全部已定性（race 55 文件全在 KN106/KN110/KN111 家族、feat = page_1367+造物专长一览设计保留），不调参、维持顶格不预放；race 注释链缺口 68 已补对账注释（KN111 追记审议结论）。此后任何带 `'?'` 增量的任务开工前必须再审（沉淀 #10）。

**KN136 登记**（随 spell 模块重构解决，2026-08-05 用户拍板）：`a46e68f` 共享层收窄跨类目回归，spell page_1363 书目链接伪标题 +1 chunk（4172→4173）+128 chunk 重编号；修复方案已定（spell 侧标题校验拒收 `[PZO` 开头伪标题）。**产物已回滚 4172 基线**（2026-08-05 用户拍板：旧代码 worktree `../pf_agent_spell4172_worktree` @ dd2abe6 重生成，KN011 链接 100%，pytest 861 全绿）；HEAD 代码 bug 仍在，CLAUDE.md 已立「严禁重跑 spell/职业 pipeline」禁令，修复验收前持续有效。

---

## 3G. 技能模块（✅ M1~M6 全部完成：Prepare + 元数据设计 + TDD + pipeline + 审计 + 交付，2026-08-07 收口）

**终态**：556 chunks（8 component_type）、verify 七检查全过（含 KN159/160 防回退断言）、pytest **1018**、判别器 est=382 ↔ got=559 零静默丢失、book '?' 0、toc 空 0、chm_toc_path 100% 可溯源（557→556 = KN159 伪条目净清除，见 KN 登记）。

**M1~M5 里程碑**：Prepare Phase（56 rel 矩阵 4 批勘探、t63 三闸口、人工门 1 五件套 `Prepare_Phase_交接文档.md`）→ 元数据设计（`技能元数据设计.md`，11 字段 + field_status 三态 + 8 component_type）→ TDD（`test_skill_format.py` 29 seeds）→ pipeline 四批接入：S1~S8 CRB 技能页（26 技能 + 95 任务 + 23 速查）→ UI 8 页（S6，ui_supplement）→ S7 Unchained 6 文件（226 rule）→ S10 装备卡（工具和技能工具包 31）→ **S9 FAQ 837 问答流（2026-08-07，61 Q&A + 2 节标题 intro，`_split_faq` 锚点判据）**——M5 批次 B 收口（git tag `skill-module-m5-20260807`）。

**M6 审计+交付（2026-08-07，本段收口）**：
- **审计要求与豁免程序**：`docs/技能/技能模块审计要求与豁免程序.md`（8 补丁包对齐专长链）
- **独立复测审计**：5 项复核（判别器/召回/字段健康/形态逐字核对/结论遗留），发现 **P1 + P2×2 全闭环**：
  - **P1 来源书系统性失实**（557/557 全标 CRB）：DirectoryNameProvider 对 directory_hints（含文件名 parts）做「技能」子串匹配误命中；修复 = processor 专属表短路 `_B2_SOURCE_OVERRIDES`（rel 前缀 → conf=75，不动公共层 KN136）+ verify 检查 7「来源书一致性」防回退（fcc0bfc）→ 终态 CRB 214 / PU 225 / FAQ 63 / AA 31 / OCCULT 10 / GIANT 5 / TG 5 / PotR 3
  - **P2-①**：`_SKILL_EXEMPTIONS` endswith 误豁免「工具和技能工具包.md」→ 精确 basename，est=382 ↔ got=560
  - **P2-②**：基线快照表述修正（git tag + gitignored 产物，不落 state 副本）
- **交付三件套**：`技能模块审计结论_20260807.md` / `技能模块数据使用说明.md`（component_type 八类降权策略 + rule_version 过滤语义 + 来源书四级置信度）/ `技能名规范表.md`（KN155 跨模块锚点：26 技能权威清单 + 子类 + 扩展书新增名）
- **KN 登记**：KN150~157 闭环/交付；**KN158 游泳 key_ability 源数据缺陷修复闭环**（2026-08-07，commit 6ba5180：根因 = 标题分隔符全角逗号 vs 其余【减】技能分号 → `fix_skill_kn158.py` 源数据规范化 `，`→`; `（内容锚定幂等 + CRLF 保留，改源数据不改解析器）→ pipeline 重跑 557 chunks 不变 → verify 新增 26 技能权威清单断言（检查 5 内，决策 11 口径）→ 7/7 全过 → TDD 回归 seed_30 → pytest 1018）；**KN159 表格行行中 CR 腰斩修复闭环 + KN160 斜体星壳剥离闭环**（2026-08-07，用户拍板「修复瑕疵」：KN159 = `fix_skill_table_cr.py` 清洗 17 文件 339 处（e4be517，prepare_batches 精确 rel 与判别器同源、CRLF 保留幂等）+ KN160 = format `_normalize_custom` 剥单星（6ac73dc，TDD seed_22/26 红绿）+ verify 检查 5 防回退断言（ebecd8e）→ pipeline 重跑 **556 chunks**（557→556：-1 = page_647 5 个 CR 腰斩伪条目净清除——4 个「表：」残迹合并完整 + 1 个「准备时间」伪标题条目消失，真条目零丢失；判别器 got 560→559 同口径）→ verify 七检查全过、KN159 管道残迹 0、KN160 星壳 25→0、pytest 1018）
- **遗留**：检索端降权项（skill_note 23 / ui_supplement 8 / skill_index 60 / FAQ 空 text intro 2 / 语言空 text 5 / page_162 超大 chunk 1 / skill_rule 空 title_en 140）待一期 Agent 检索联调

**跨模块经验沉淀** ✅（2026-08-07，`docs/跨模块经验沉淀_技能模块_20260807.md`，第四条经验链——专长 → 种族 → trait → 技能，新模块（装备/怪物）按四链合并阅读；核心教训：来源书系统性失实（557/557 全标 CRB，目录「技能」子串误命中）+ 专属表短路修复范式 + verify 断言「解析错了」而非只查「缺」+ 文件名判定禁子串匹配）。

---

## 3H. 装备模块（✅ M1~M5 全部完成：Prepare + 元数据设计 + TDD + pipeline 三批 + verify 八检查 + cicd 装配，2026-08-09 M5 收口；M6 审计待启动）

**终态**：5386 chunks（15 component_type，gear 2538/wondrous 1987/equipment_intro 118 等）、verify **八检查**全过（含 slot 严格 13 枚举 + KN159/160 防回退断言 + 来源书一致性）、pytest **1165**、判别器矩阵 297 rel 全独立对账 est=5097 ↔ got=5386 **静默丢失 0**（est 修正 28 条全定性）、book '?' 5（全超游神器 d20pfsrd 通用，设计内保留同 KN106 口径）、toc 空 0、slot 13 枚举 1320 有值全合法、星壳 0、BBCode 0、format_cluster 五簇 {chm_page 3618/aggregation 1434/isg 188/isc 56/b1_b1 90}。

**M1~M5 里程碑**：Prepare（297 rel 矩阵、t63 三闸口、人工门 1 五件套）→ 元数据设计（M2，10 规范字段 + extra 保真 + field_status 三态 + 16 主类 3 辅助；用户拍板：奇物 wondrous_item 单类 + slot 13 枚举）→ TDD（`test_equipment_format.py` 94 seeds + `test_equipment_processor.py`）→ pipeline 三批（P1 书聚合直入 A/B 形态 / P2 CHM 大页 C 形态 page_206~234 等切块 / P3 D 形态散件去重）→ **M5 收口（2026-08-09）**：
- **verify_equipment 八检查**：①判别器回归（297 rel 全独立对账——5 对同 stem 重复文件 doc_id 消歧 `__{父目录}` 后缀，processor `_build_chunk_template` 覆写 + verify `_doc_id_of` 同源，KN136 公共层零改动；原 17 个重复 chunk_id 清零）②召回（装备包 11 命名包 + 13 位置页精确产物数 794）③条目级 QA（诱饵戒指 12000gp/神意指引包 67磅/page_223 锚点）④负向断言（P&P 法术零泄漏/KN181 伪标题 0/enchantment 无 slot/page_946 类目纯净）⑤字段健康度（slot 严格 13 枚举 + 附魔 slot 归 not_applicable `_SLOT_RELEVANT_CT` 8 奇物类目白名单 + KN159/160 防回退）⑥title 合法性（空 title 104 全 intro，噪声豁免 7 登记）⑦来源书一致性（296 doc 专属表 0 表外 0 不匹配 + rule_version==book.lower()）⑧entity 枚举（produced 15 全产出/reserved 5 零产出）
- **源数据修复 3 处**：UI奇物 B1 表格行右列残渣 ×2 + 黑市指南BM 剧透块标题泄漏（KN159 家族，CRLF 保留）
- **公共层 hook 扩展**：`BackfillChmTocPath._resolve_doc_file` 扩展点（默认行为不变），EquipmentBackfillChmTocPath 覆写剥 `__` 后缀 → 消歧 doc toc 回填 40→0（unfilled 0）；经全量 pytest 1165 + trait 完整链回归零影响
- **不变量闸口 + cicd 装配**：CATEGORIES 加 equipment 行（--max-empty 115/--max-oversize 25/--min-total 4500/--main-component gear/--min-main-count 2200/--max-book-unknown 5 顶格棘轮/--max-toc-empty 0）+ `regen_equipment_chunks.sh` + ci.yml 矩阵 feat/race/trait/equipment 四类目；**出口条件 `python3 -m vectorizer.cicd verify --category equipment` 单命令全绿 ✅**
- **KN 登记**：KN161~186 全量（M5 收口 KN174 星壳 A 462 专项评估——行首尾 0 闭环 + 行内残留 3 类定性待 M6；KN181 规则段伪标题专项闭环——负向断言 + est 修正 + reserved 三保险；KN186 本模块 M5 汇总含巨型条目 21 定性/book '?' 顶格审议/闸口参数全记录）
- **遗留**：检索端降权项（equipment_intro 118/空 text 113/巨型条目 21/KN174 行内残留 ~11 条/KN185 重力石粘连 1 例）待一期 Agent 检索联调；**M6 独立复测审计 + 交付三件套（审计结论/数据使用说明/装备名规范表）待启动**

---

## 4. 技术债务

### 4.1 脚本问题
- **cleanup_phase1.py / cleanup_phase2.py**：旧脚本基于简单规则匹配，误判率高，已逐步被 `cleanup_phase3.py` 取代
- **cleanup_phase3.py**：当前主脚本，采用精确覆盖 > 来源书识别 > 多信号打分 > 回退的优先级管道，但仍依赖人工覆盖表，对新增术语需要持续维护
  - 建议：后续可引入基于源文件路径/共现分析的自动分类，减少人工覆盖表维护成本

### 4.2 数据问题
- **源数据质量**：`pf_rules_md/` 中部分文件为 OCR 提取，存在乱码
- **术语提取方式**：基于正则表达式，可能漏提或误提
- **出现次数统计**：基于简单文本匹配，可能不准确

### 4.3 向量化脚本结构债
- ~~vectorization_prep_profession.py 单文件 4112 行~~ **已清偿（2026-07-28 法术模块）**：`vectorizer/` 包落地（pipeline / formats / processors / sources / verify / tests），见 §3D
- 剩余：`registry.py` 随专长模块拆包（spell 字段注册表硬编码）、`audit.py` Tier 2 规则泛化（CategoryPipeline 剩余抽象）——触发条件与方案见 `docs/VECTORIZER_ARCHITECTURE_DESIGN.md` §8

---

## 5. 待办事项（按优先级）

### Agent 侧交付（2026-08-13）
- [x] **Agent 工具调用计数**（2026-08-16，F-006，`pf_agent/agent/`）：统计每次问答的工具调用情况（工具类型/次数/成败/耗时/轮次）——`ChatService.executeTools` 埋点 → `ToolCallTracker`（ThreadLocal 会话级收集，并发隔离）→ `ToolCallRecorder` 追加 JSONL（`~/.pf_agent/tool_calls.jsonl`）→ `qa/tool_calls_report.py` 聚合分析（按工具统计 + 会话工具序列 + 失败清单）。配套 TDD 14 用例（ToolCallTrackerTest 6 + ToolCallRecorderTest 5 + ChatServiceTest 扩展 3），全量 140 测试通过。纯后端复盘遥测，为评测集 baseline 对比与检索联调提供「LLM 走了哪些检索工具」的观测数据。
- [x] **一期 Agent 回答质量评测集（56 题）**（`pf_agent/agent/qa/`）：dnd5e-srd-qa（datapizza-ai-lab）56 题迁移为 PF 1e 版——`pf_qa_items.json`（D=27/R=23/X=6，easy 25/medium 31，全量 124 锚点实查命中、无 book='?'/未整理依赖）+ `迁移难点_5e无法映射.md`（6 X 题 + 勉强 R 题，原因/方案/待人工优化点）+ `evaluate.py`（A 批规则化三维度：溯源/诚实/结构 + B 批 LLM-as-judge 接口预留）+ `README.md`（使用说明 + 判分规则 + 与 dnd5e 对照）。用途：为「一期 Agent 检索联调批次」提供量化验证工具（`python3 evaluate.py` 跑 A 批，`--judge` 需 golden answer 完成后启用）。
- [x] **Agent 错误标注闭环**（2026-08-16，`pf_agent/agent/`）：用户提问发现错误回答可一键标注，形成「标注 → 分析 → 优化 prompt/代码」的准确率提升闭环——前端回答下方「⚠️ 标错」按钮（错误类型 5 类：事实错误/检索漏召回/编造来源/答非所问/结构差 + 修正 + 备注）→ `POST /api/chat/feedback`（ChatController）→ `FeedbackRecorder` 追加落盘 `${user.home}/.pf_agent/annotations.jsonl`（含 question/answer/sources **回答快照**，可精确复现错误现场；对齐 data_gaps 模式，失败不阻塞主链路）→ `qa/annotations_report.py` 聚类分析（errorType 分布 + 被标错来源 Top 问题 chunk + 逐类优化建议指向 prompt/检索/数据）。配套 TDD 12 用例（FeedbackRecorderTest 5 + ChatControllerTest 扩展 7），全量 117 测试通过。用途：为「提升 Agent 准确率」提供线上真实错误收集，与 56 题评测集互补（评测离线批量、标注线上真实）。
- [x] **Agent 工具循环超限 500 修复（v1.9，2026-08-20，`pf_agent/agent/`）**：聚合/跨 chunk 综合类问题 LLM 反复检索不收敛致 6 题 500（`easy-7/18/22`、`medium-17/18/23`）。三层修复——A `searchByMetadata` 结果字符截断（`pf.search.metadata-result-chars` 默认 4000）；B 修正 `maxHistoryChars` 守卫统计口径（`ToolResponseMessage.getText()` 漏算工具结果致 50K 上限失效）+ 超限转强制收敛；C `maxToolRounds` 超限改强制收敛（15→10，不再抛 500）。**全量 50 题重跑 error=0**，溯源 33/50（修复前恒 0）、诚实 49/50、结构均值 2.90/3。剩余 17 题溯源=0 二分：② spell 向量库旧版错位（旧 4200 store vs 新 4172 jsonl，chunk_id 错位 2015 条）+ ③④ 真实检索偏离。**② 已闭环（2026-08-21）**：重建 `vector_store_spells.json`（4172 基线，chunk_id 错位归 0），重跑 baseline 溯源 33→**38/50**、诚实 49→**50/50**、结构 145→148（均值 2.96）；9 道含 spell 题溯源 0→1（含虹光法墙 CRB_0414），4 题 1→0 属 LLM 检索随机波动。剩余 12 题溯源=0 全部属 ③④ 真实检索偏离（P0-B 检索联调对象）。**2026-08-21~24 溯源继续 38→44/50**（修复 1 topK 5→15 + 修复 3 聚合题宽松 + 修复 4 class hash 锚点 8 题改 doc 级 tocPath，6 题恢复；诚实 49/50、结构 2.98）。剩余 6 题溯源=0 归因：① 2 题 LLM module 路由错误（easy-7/medium-0「兼职」误判 rule，F-006 实锤）；② 4 题召回精度/波动（easy-15/22、medium-4/21）+ `isBaseClassPage` 前缀「基础职业」vs「核心职业」bug（class-base-bonus 疑似失效）。详见 `agent/docs/检索溯源归因与修复方案_20260821.md` 与 `Agent功能TODO.md` F-002。**P0-B / P0-B2 检索联调闭环（2026-08-25，溯源 44→46→50/50 满分）**：P0-B 修 isBaseClassPage 前缀（补「核心职业」）+ LLM 模块路由提示（兼职→class），6 题中 2 路由题恢复；P0-B2 修法 A（searchByMetadata title 过滤全模块开放，原仅 spell）+ 修法 B（rerank-extra-candidates=10 候选扩容 + title/aliases 词元加权 +0.05）+ AKN-008（SourceCollector.drain 去重键 doc_id→chunk_id，治页面级 doc_id 吞同页锚点），剩余 4 题全恢复。诚实 49/50、结构 2.96，单测 157 全绿。方案：`agent/docs/P0-B检索联调批次实施方案_20260825.md`、`agent/docs/剩余4题溯源修复方案_20260825.md`。

- [ ] **Agent 侧未实现想法 backlog**（`pf_agent/agent/docs/Agent功能TODO.md`，F-003/005/007/008/009/010/011/013/014 共 9 条未排期）：会话持久化（F-003/F-005）、职业法术列表预整理（F-007）、chunk 元数据入目录（F-008）、独立 API Key 计费（F-009）、请求限频（F-010）、未登录轮次限制（F-011）、主从库（F-013）、论文式上标来源标注（F-014）。其中 P1 级 F-010/011（限频/轮次限制）属一期上线前成本控制项，与 P0-B 同等优先。详见 `Agent功能TODO.md`。

### 🔴 P0 - 阻塞性问题
- [x] Git 提交：建立可回滚的基线（含 `pre-normalization-baseline` tag；2026-07-30 起推送远程 `git@github.com:ytche/pf_agent.git`）
- [x] 修正自动分类错误（Phase 3 完成 20 项）
- [x] 职业 chunk 质量攻坚 V001~V009（2026-07-21~23）
- [x] WORKFLOW.md v2.0 + 终局架构设计（已演进至 v2.0，2026-07-30）
- [x] 目录整理：pf_data/ + phase1/ 根目录清理（2026-07-24）
- [x] **法术模块向量化**（2026-07-28~30，见 §3D）：vectorizer/ 包落地 + KN001~024 闭环 + 召回验收 99.6%
- [ ] **专长模块向量化**（🟢 进行中，见 §3E）：Prepare ✅（07-31）+ 源数据修复召回 100% ✅（08-02）+ k3 汇总 ✅（08-01）+ 元数据设计 ✅ + TDD formats/feat.py ✅（457 tests）+ pipeline 产出 ✅（08-01）→ chunk 质量巡检 ✅（08-02，KN076~090 全闭环：链接残留/星壳家族收口/速查表删除线壳吞条目/D 分支截断）→ chm_toc_path 映射表 ✅（08-02，未知 1780→136）+ KN075 链接残留 ✅（08-02，`_strip_http_links`，残留 25→0）+ 行内来源顶层提升 ✅（08-02，`apply_feat_creation_source_promote.py` 54 chunks，源数据修复二轮 4 处）+ **来源书链路修复 ✅（2026-08-03，`来源书链路修复方案.md` §六：重跑两 apply 脚本 book 未知 1806→100 + `backfill_chm_toc_path.py` 三级链路回填 toc 空 1348→0（chunk 级 642 + 文件级 706））+ metadata.source 补齐 ✅（2026-08-03，`backfill_feat_source.py`：656 个可解析未解析（text 含 `> 来源：` 引用块）全部补齐，337→1007 = 16.7%）** → **检索端形态降权（elided 截断条目 / 空 text KN085 / feat_index 元数据组装；KN084 已闭环 2026-08-03）** → **语义切分质量评估 ✅ 满足一期 Agent 调用 + 交付文档（2026-08-03，`专长模块数据使用说明.md`）** → **KN095 裸标题吞并 ✅ 已闭环（2026-08-03，源数据修复 75 行 → 5948→6022 chunks、全库 >5000 清零、四后处理脚本重跑）** → **KN112 公共层守卫回归修复 ✅ 已闭环（2026-08-04：e80ec0e race 专属守卫误入公共函数 `_fix_quad_star_halfparen` 致 feat 武器技法 6 条类别标题丢失——参数化 `guard=False` 默认 feat 旧行为、race 调用点 `guard=True`，武器大师手册 110→116、6026→6032 chunks、verify_feats 5/5、召回 1061/1061、全量 pytest 662；教训：公共层正则类目专属守卫必须参数化 + 跨类目回归验证）——专长模块阶段收口，KN 全量见 `已知问题记录.md`**
- [ ] **种族模块向量化**（🟢 进行中，见 §3F）：TDD ✅（07-08-04，#97）+ 实现 ✅（#98/#99）+ verify 六检查 + cicd 装配 + 不变量扩展 ✅（#100）→ **产出即检三件套 ✅（2026-08-04，#101，`产出即检_首轮_20260804.md`：title 合法/字段健康/召回 37/37/新正则触发计数/高危 probe）** → **KN102 字段链家族闭环 ✅（2026-08-04：伪条目 41→0 + school 吞值 + 豺狼人剥星，pytest 618，产出 2340→2264）** → 产出对账报告按 2264 终态更新 ✅（est 2132 ↔ got 2264 +132 全定性）→ **首轮审计 ✅（2026-08-04，`审计报告_首轮_20260804.md`：k3 审计立项 §⑦ 5 项全过；KN103 race_spell 误判规模化修复闭环——174→92、全库 2264→2390 +126 全定性、pytest 629；KN098 随之闭环；KN104~106 登记）** → 产出对账报告按 2390 终态更新 ✅（est 2132 ↔ got 2390 +258 全定性）→ **全量核查 ✅（2026-08-04，`种族chunk全量质量核查_交接文档_20260804.md`：22 机制 M1~M22 三批次全闭环，KN113~120 交接任务 + KN121~129 批次修复全部闭环）** → **k3 验收返修闭环 ✅（2026-08-04，`种族全量质量核查_k3验收报告_20260804.md` 第五章；KN130~133）**：KN130（page_11 三族整行找回，70→76）+ KN131（page_752 59 条全 alt_trait + page_398 全量修复 35→42）+ KN132（race_name 四级兜底链）+ KN133（边界/清洗残留家族 + CtIE 嗜火者 intro 吞并）→ **verify_races 六→八检查 ✅（新增 page_11 行级召回 37/37 + page_752 component_type 59/59，TDD 先行 10 用例）** → 终态 **3654 chunks**、pytest **843**（KN134/135 闭环后）、闸口全过（book '?' 2483 设计保留同口径）→ **KN134/135 残留闭环 ✅（2026-08-05，`51d9e02`：page_10 组标题归 race_intro + 译注/「：」行首/replaces 前缀清零）** → **跨模块经验沉淀 ✅（2026-08-05，`docs/跨模块经验沉淀_种族模块_20260805.md`）** → **遗留：检索端语义降权评估（KN098/100 影响面，随一期 Agent 检索联调）；另立任务：阿斯托莫伊人 8 特性粒度拆分、page_401~404 构建规则（维持豁免）；KN104 已复核登记不修（2026-08-04：修复前提不成立，race 全类目 0 个 `> 来源：` 引用块，源数据层面缺口）**

### 🟡 P1 - 重要改进
- [ ] **装备模块向量化**（🟢 **M1~M5 全部完成收口**，2026-08-09，分支 `feat/equipment-module`）：5386 chunks、verify **八检查**全过（判别器 297 rel 全独立对账静默丢失 0 / 召回 / 条目级 QA / 负向断言 / 字段健康度 slot 13 枚举 / title / 来源书一致性 / entity 枚举）、pytest **1165**、`python3 -m vectorizer.cicd verify --category equipment` 单命令全绿（cicd 装配 + ci.yml 矩阵 + `regen_equipment_chunks.sh`）；KN161~186 登记（KN174 星壳专项 / KN181 伪标题专项已闭环）；详见 §3H；下一步：**M6 独立复测审计 + 交付三件套**（审计结论 / `装备模块数据使用说明.md` / `装备名规范表.md`）
- [x] “其他”分类降至 10.6%（已达标 <20%）
- [x] “其他翻译”列清理
- [x] 边界案例复核
- [x] 女巫/圣骑士变体来源书修复
- [x] KN001（聚合页来源书）+ KN004（吸血鬼猎人源文件）+ 156 未知来源 → 全部已修复
- [x] **主脚本重构** + **CategoryPipeline 第一步**：随法术模块落地（registry/Tier 2 泛化随专长模块收尾）
- [x] **KN019 D 类 23 条**（法术）**全部闭环**（2026-08-04）：第一类 20 + B 类 3 条 `_wrap_bare_spell_titles` 正文段守卫修复（chunk 4221→4175、pytest 637）；**第二类 3 条跨行 HTML 残留**（page_1177_0000/page_1365_0191/0188）J 簇 `[^\n*。]` 守卫 + Step 0f `(?<!\*)` 守卫 + 源数据补中文名「手舞足蹈」（译名来源 page_1037 唤魂师交叉引用）恢复 stat block 归属——chunk 4175→**4172**、pytest **642**、verify_spells 全过、page_1177 5/5 召回；一期上线前 go/no-go 项闭环；A 类罗马数字 44 条 + C 类 2 条维持登记不修（KN019 全量修复记录见 `pf_data/phase1/docs/已知问题记录.md`）
- [ ] **KN092 benefit 覆盖率不足**（专长，P1 登记暂缓）：benefit parsed 仅 57.2%（3404/5948）。构成：速查表行 1868/1871「专长效果」列进 text 未组装 benefit + 正文 ~620 条纯文本/斜体收益无 `**收益：**` 标签未提取（真正信息缺失仅 ~50 章首/介绍小节，其余信息在 text 检索可用）。计划：A. 速查表三列映射（机械可靠）；B. 正文无标签收益提取（需人工兜底）；与后端 feat_index 元数据组装分工对齐
- [x] **KN023 链接剥离修复**：已闭环（2026-08-01，commit 6f79c90，见 已知问题记录.md KN023）
- [x] **KN020~024 登记项**（法术）：随 KN019 迭代处理完毕（KN023 修复，其余登记不修）

### 🟢 P2 - 增强功能
- [x] 根目录重复副本清理（✅ 已闭环 2026-08-07，08fb7eb：phase1 下 CHM_FULL_TOC ×2 副本 git rm，权威在 pf_data/ 根）
- [x] 全局去重（✅ 已闭环 2026-08-07，b4b8673 + 批次 3：terms.json 7 组同词异形合并 1075→1068 + 人工拍板执行——神恩×3 译名区分/6 来源书 CHM 权威中文名补全/神秘技能解锁分类修正，verify_phase3 6/6；方案 `docs/术语表P2清理方案_20260807.md`）
- [ ] **KN093 feat_index 与 feat 正文重复去重**（专长，P2 登记）：1176 对同专长双 chunk（速查表摘要 + 正文详述），检索端按 title/aliases 去重优先正文，数据层不动（随后端检索逻辑实现，与 KN092 同批）
- [x] **KN094 component_type=feat_intro 枚举**（专长，P2 已闭环 2026-08-03）：介绍性 chunk（23 章首空 text + 34 类别介绍段，57 高置信零误伤）format 层打 intro 标记 → processor 层映射 feat_intro；lb_marker 优先（KN085 28 个空 text 不误伤）、字段拼组（4 个）保持 feat；TDD 8 用例、pytest 522→530、verify 5/5、召回 100%；检索端对 feat_intro 降权（见 §3E-5 降权清单 ⑤）
- [x] verify_*.py 验收体系（职业 11 个 + 法术 pytest 264）

---

## 6. 关键文件说明

### 6.0 向量化关键文档索引（2026-07-30 更新）

| 文档 | 用途 |
|------|------|
| `pf_data/phase1/docs/VECTORIZER_ARCHITECTURE_DESIGN.md` | **终局架构设计 v2.0**（决策 1~29 + pipeline 流程图 + 法术验证结论） |
| `pf_data/phase1/docs/WORKFLOW.md` | **V/N 迭代流程 v2.0**（Step 0~5，类目无关 + subagent 并行） |
| `pf_data/phase1/docs/专长/专长模块开工前_流程抽象与预防清单.md` | 🆕 专长开工基线（8 补丁包 + 五合一扫描 + 资产四分类 + 7 步顺序） |
| `pf_data/phase1/docs/专长/Prepare_Phase_交接文档.md` | 专长 Prepare Phase 交接包（17 批 / doc_role / HTML 回溯 / 红线）✅ 已关闭 |
| `pf_data/phase1/docs/专长/Prepare_Phase_三轮返工终审结论.md` | 🆕 Prepare Phase 终审（三轮返工链闭环：幻影 84→0、12 份错位报告重推导、总数 3635、t63 三闸口固化） |
| `pf_data/phase1/规则书向量化规则.md` | 清洗/分块/组件识别/来源书识别规则 |
| `pf_data/phase1/docs/已知问题记录.md` | KN001~135 权威登记表（状态以此为准） |
| `pf_data/phase1/docs/种族/产出即检_首轮_20260804.md` | 🆕 种族产出即检报告（三件套 + 高危 probe + 修复记录 + 遗留 R1~R8 + k3 审计要求 §⑦） |
| `pf_data/phase1/docs/种族/产出对账报告.md` | 🆕 种族 est ↔ got 对账（2390 终态，簇级全定性） |
| `pf_data/phase1/docs/种族/审计报告_首轮_20260804.md` | 🆕 种族首轮审计（k3 审计立项 §⑦ 5 项全过 + KN103 P1 修复闭环） |
| `pf_data/phase1/docs/种族/种族chunk全量质量核查_交接文档_20260804.md` | 🆕 种族全量核查交接（KN113~120 + 抽查 case + 验收要求）✅ 全部闭环 |
| `pf_data/phase1/docs/种族/全量核查问题汇总与修复计划_20260804.md` | 🆕 22 机制 M1~M22 三批次修复计划与进度（全闭环） |
| `pf_data/phase1/docs/种族/种族全量质量核查_k3验收报告_20260804.md` | 🆕 k3 验收报告（KN130~133 返修要点 + 第五章闭环确认） |
| `pf_data/phase1/docs/种族/KN107_核心种族详情页纳入_交付_20260804.md` | KN107 P0 修复交付（根目录 9 页纳入 +845 chunks） |
| `pf_data/phase1/docs/种族/KN107_KN109_KN112_汇总交付_k3验收报告_20260804.md` | KN107/KN109/KN112 k3 终态审计正式通过（审计链关闭） |
| `pf_data/phase1/docs/KN107门1后至KN112_汇总交付_20260804.md` | KN107 门 1 后至 KN112 执行模型汇总交付 |
| `pf_data/phase1/docs/chm范围缺口排查_20260804.md` | CHM 范围缺口排查（种族 9 页 / 职业 7 页 / 专长 2 页，audit_chm_scope_gap.py 可复算） |
| `pf_data/phase1/docs/种族/种族全量质量核查_交付验收文档_20260804.md` | 全量核查 22 机制交付（M1~M22 三批次闭环，3612 chunks / pytest 789） |
| `pf_data/phase1/docs/种族/KN130-133_验收返修_交付_20260804.md` | KN130~133 返修交付（终态 3654 / pytest 836 / verify 八检查） |
| `pf_data/phase1/docs/跨模块经验沉淀_种族模块_20260805.md` | 🆕 跨模块经验沉淀（新模块开工前必读：速查表 + 12 条元教训 + 一次性经验防误用） |
| `pf_data/phase1/问题与修复记录.md` | 5 个闭环 bug（001~005，含根因+修复+验证） |
| `pf_data/phase1/HANDOVER_K2_7_PROFESSION_CHUNK_QUALITY.md` | V001~V009 总体设计（已执行完毕） |
| `pf_data/phase1/HANDOVER_K2_7_WITCH_FIX_AND_REFACTOR.md` | FileProcessor + CategoryPipeline 原点设计 |
| `PROJECT_HANDOVER.md §3C/§3D/§3E/§3F` | 跨模块泛化路径 + 法术模块验收 + 专长模块启动 + 种族模块 |

### 6.1 术语报告格式

```markdown
## 分类名称（X 个术语）

| 英文术语 | 推荐翻译 | 其他翻译 | 出现次数 |
|---------|---------|---------|---------|
| Term Name | 译名 | 不同译名/上下文例句 | 次数 |
```

**示例：**
```markdown
| Arcane Bond | 奥术联结 | 奥术联结(3), 魔宠大师必须选择魔宠作为他的奥术联结(2) | 28 |
```

### 6.2 脚本使用方式

```bash
# Phase 3 清洗与验收（当前推荐流程）
cd /Users/chezi/code/java/pf_agent/pf_data/phase1
python3 cleanup_phase3.py
python3 verify_phase3.py

# 旧流程（保留历史脚本）
python3 cleanup_phase1.py
python3 cleanup_phase2.py
```

---

## 7. 约束与规范

### 7.1 文件操作规范
- **原始文件 `术语提取报告_分类版.md` 不可修改**（基线）
- 所有修改通过脚本自动化执行，禁止手工编辑
- 每个阶段完成后必须 Git commit

### 7.2 分类体系
当前 15 个分类，建议新增：
- **职业 (Classes)** — 从"其他"中拆分
- **种族特性 (Racial Traits)** — 从"其他"中拆分
- **法术成分 (Components)** — V/S/M/DF 等

### 7.3 翻译规范
- **推荐翻译**必须是纯净译名，不能混入描述句子
- **其他翻译**列应只保留不同译名，去除上下文例句
- 保留出现次数统计作为术语重要性参考

### 7.4 向量化输入范围（2026-08-04，KN107 沉淀）
- **类目数据范围 = CHM 目录该类目子树对应全部文档 ∪ `pf_rules_md_organized/` 全量的并集**，不得缺失 CHM 目录对应文档
- 新模块 Prepare Phase 第 0 步必跑 `audit_chm_scope_gap.py`（CHM TOC × md_mapping × organized 三方比对），缺口逐项定性（纳入/索引页豁免/重复副本豁免）后才允许开工
- 两个口径陷阱：per_file 勘探清单 ≠ 真实输入；organized 根目录留档区「均为重复副本」假设须逐页验证

---

## 8. 参考资源

- **PF 规则库路径：** `~/.openclaw/workspace/pf_rules/`
- **角色卡路径：** `~/.openclaw/workspace/characters/`
- **Obsidian 资料库：** `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/main/02-Areas/游戏/PathFinder/`
- **优化计划 SPEC：** `phase1/优化计划_SPEC.md`

### 8.1 V001~V009 关键脚本与产物（新增索引）

| 类别 | 文件 | 用途 |
|------|------|------|
| **主脚本** | `vectorization_prep_profession.py` | 4112 行单文件（待重构为 vectorizer/ 包） |
| **输出** | `vectorization_prep_profession/` | `chunks.jsonl`（20MB）/ `class_archetype_index.json`（1.4MB）/ `manifest.json` / `quality_report.md` |
| **归一化** | `normalize_masterpiece_titles.py` | 吟游诗人传世名作标题 |
| | `normalize_paladin_deities.py` | 圣骑士 deity 页面 |
| | `normalize_vampire_hunter.py` | 吸血鬼猎人（**已就绪未运行**） |
| | `normalize_profession_sources.py` | 职业来源 |
| **去重** | `dedupe_all_chunks.py` | 通用去重（1192 deprecated） |
| | `dedupe_masterpiece_chunks.py` | 传世名作专项去重 |
| **清理** | `cleanup_subtype_mismatch.py` | 76 项 subtype 误标清理 |
| | `cleanup_phase1/2/3.py` | 术语清洗（Phase 3 主用） |
| **验收** | `verify_all_classes.py` | 全量职业验收 |
| | `verify_class_attribution.py` | 归属验收 |
| | `verify_subtype_coverage.py` | 27 种 subtype 数量下限 |
| | `verify_paladin_archetypes.py` | 圣骑士变体+归属 |
| | `verify_heading_levels.py` | heading 层级回归（**KN004 教训沉淀**） |
| | `verify_no_false_archetypes.py` | negative test（防变体误识别） |
| | `verify_no_false_hex_sections.py` | 女巫巫术假阳性检查 |
| | `verify_venom_siphoner.py` | 汲毒巫专项 |
| | `verify_bardic_masterpieces.py` | 68 首传世名作 |
| | `verify_phase3.py` | 术语 Phase 3 验收 |

---

## 9. 联系人

- **车子（用户）：** 直接沟通，风格直接、不废话；要求 **k3 一次性整包交付 k2.7**，不要多轮接力（已明确纠正过）
- **骰娘（前任 Agent）：** 本项目前任负责人，可查询历史决策
- **小爪（通用 Agent）：** 主会话，通用问题可咨询
- **墨墨（记账 Agent）：** 记账/日程，与本项目无关

### 9.1 模型分工（2026-07-20 与用户定稿）

| 角色 | 职责 |
|------|------|
| **k3**（设计） | 只做设计，不写修复实现 |
| **k2.7**（执行） | 跑长任务，护栏内自主决策 |
| **用户**（车子） | 抽查验收、拍板方向 |
| **交接原则** | k3 讨论完 → 一次性整包交付 k2.7，不接力；已诊断清楚的给精确指令，依赖现场数据的给原则+护栏+模式目录起点+逃生舱协议 |

---

## 10. 附录

### A. 术语表示例（前 10 行）

| 英文术语 | 推荐翻译 | 出现次数 | 当前分类 |
|---------|---------|---------|---------|
| Charm Person | 魅惑人类 | 81 | 法术 |
| Extend Spell | 法术延时 | 70 | 法术 |
| True Seeing | 真知术 | 45 | 法术 |
| Dispel Magic | 解除魔法 | 42 | 法术 |
| Resist Energy | 抵抗能量伤害 | 40 | 法术 |
| Spell Resistance | 法术抗力 | 38 | 法术 |
| Warp Wood | 曲木术 | 37 | 法术 |
| Break Enchantment | 破除结界 | 37 | 法术 |
| Cause Fear | 惊恐术 | 34 | 法术 |
| Enlarge Person | 变巨术 | 32 | 法术 |

### B. 已修正误分类列表（Phase 3 完成）

| 术语 | 原分类 | 修正后分类 | 状态 |
|------|--------|-----------|------|
| `Combat Expertise` | 怪物/生物 | 专长 | ✅ 已修正 |
| `Weapon Focus` | 装备/物品 | 专长 | ✅ 已修正 |
| `Neutralize Poison` | 装备/物品 | 法术 | ✅ 已修正 |
| `Remove Disease` | 动作/战技 | 法术 | ✅ 已修正 |
| `Detect Poison` | 装备/物品 | 法术 | ✅ 已修正 |
| `Spring Attack` | 动作/战技 | 专长 | ✅ 已修正 |
| `Whirlwind Attack` | 动作/战技 | 专长 | ✅ 已修正 |
| `Improved Trip` | 动作/战技 | 专长 | ✅ 已修正 |
| `Improved Disarm` | 动作/战技 | 专长 | ✅ 已修正 |
| `Improved Bull Rush` | 动作/战技 | 专长 | ✅ 已修正 |

---

*文档版本：v1.3*  
*最后更新：2026-07-23（V001~V009 完成 + WORKFLOW.md 标准化）*  
*由骰娘整理，开发 Agent 持续更新*

### C. V001~V009 迭代速查（2026-07-21~23）

| 轮次 | 提交范围 | 关键产出 |
|------|---------|---------|
| V001 | 变体误识别 | `verify_no_false_archetypes.py`；圣律沿循者子誓约修复 |
| V002 | 汲毒巫、女巫 P&P | `#d30919b` P&P 女巫巫术修复 |
| V003 | 汲毒巫变体 | `#75ae0b2` 数据截断与错置 |
| V004 | 吟游诗人 | `#03e41a0` 68 首传世名作补齐 |
| V005 | 操念使+吸血鬼猎人 | 发现 KN003/KN004 |
| V006 A1 | subtype | 13 项扩展，27 种 |
| V006 A2 | 类隔离 Processor | Oracle/Warpriest/Summoner/Shifter 4 个新建 |
| V006 A3 | subtype 误标 | 76 项清理 |
| V006 B | 跨类错归 | page_59 杀手目录移除；纯洁勇士拆分 |
| V006 C | 去重 | 1192 deprecated |
| V008 B+D | Processor | OracleProcessor 扩展；SorcererProcessor 新建 |
| V008 C | 源文件 | 圣骑士 page_562 + 战士 page_1218 锚点 |
| V009 | 来源书 | `AggregationTableProvider`（置信度 65） |
