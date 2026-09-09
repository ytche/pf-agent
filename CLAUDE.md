# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个 PathFinder 1e（PF 1e）跑团辅助 Agent 的数据准备仓库。核心目标是完成一期功能：**基于 PF 规则书的规则问答 Agent**，回答内容基于规则并提供目录引导，让用户可以追溯信息来源验证回答。中英术语对照表只是数据清洗工作的一部分，用于提升查询理解、翻译一致性和规则索引质量。

- 当前工作集中在一期：从 CHM 规则书提取的 Markdown 源数据中清洗、分类术语，为规则问答服务。
- 一期术语表 Phase 1~3 已完成，输出 `术语提取报告_优化版.md`（1075 术语，15 分类 + 来源书籍）与 `terms.json`。
- 二期（车卡辅助 + Build 建议）尚未开始。
- 所有可执行脚本在 `pf_data/`（CHM 解析）和 `pf_data/phase1/`（术语清洗）下。
- 没有构建系统、包管理器或测试框架，直接运行 Python 3 脚本。

## 仓库结构

```
/Users/chezi/code/java/pf_agent/
├── PROJECT_HANDOVER.md          # 项目交接文档，包含完整状态、待办、已知问题
├── CLAUDE.md                    # 本文件
└── pf_data/
    ├── CHM_FULL_TOC.md          # CHM 目录结构（2376 项）
    ├── CHM_FULL_TOC_WITH_LEVELS.md   # 带 L1-L5 层级标注
    ├── CHM_STRUCTURE_ANALYSIS.md     # CHM .hhc 目录解析规则
    ├── README_CHM_CONVERT.md    # CHM→Markdown 转换说明
    ├── chm_to_md_converter_v2.py     # 最终 CHM→MD 转换脚本
    ├── extract_full_toc_v6.py   # 最终 TOC 提取脚本
    ├── analyze_*.py             # 各类分析脚本（CRB、法术、L1 等）
    ├── extract_occupation_*.py  # 职业相关提取脚本
    └── phase1/                  # 一期术语清洗工作区（含 Git）
        ├── 术语提取报告_分类版.md    # 基线文件，不可修改
        ├── 术语提取报告_优化版.md    # 当前最终交付（1075 术语，15 分类 + 来源书籍）
        ├── 术语提取报告_清洗版.md    # Phase 1 中间产物
        ├── 术语提取报告_重分类版.md  # Phase 1 中间产物
        ├── terms.json                # 机器可读术语表
        ├── manual_review_phase3.md   # Phase 3 人工复核清单
        ├── PF_缩写表.md              # 缩写附录
        ├── 规则书缩写对应表.md       # CRB/APG/UM 等缩写对照
        ├── 优化计划_SPEC.md          # 三阶段优化计划
        ├── 优化日志.md               # 自动清洗与分类日志
        ├── 边界案例待复核.md         # 历史边界案例记录
        ├── term_rules.py             # Phase 3 公共规则（分类/信号/清洗）
        ├── cleanup_phase1.py         # Phase 1 清洗：去污染、拆分类、修错位
        ├── cleanup_phase2.py         # Phase 2 优化：精简其他翻译、生成缩写表
        ├── cleanup_phase3.py         # Phase 3 清洗与重分类脚本（当前推荐）
        ├── verify_phase3.py          # Phase 3 自动化验收脚本
        ├── manual_overrides_phase3.py  # Phase 3 人工分类覆盖
        ├── extracted_overrides.py    # 从源文件提取的法术/专长覆盖
        ├── original_optimized_overrides.py  # 从原优化版继承的分类覆盖
        ├── classify_terms.py         # 分类脚本
        ├── deduplicate_terms.py      # 去重脚本
        ├── fix_line_breaks.py        # 换行修复
        ├── vectorization_prep_profession.py  # 职业目录向量化预处理脚本
        ├── 规则书向量化规则.md        # 向量化清洗/分块/组件识别规则（按需阅读）
        ├── pf_rules_md/              # 源数据：约 2156 个 Markdown 文件
        └── pf_rules_md_organized/    # 按来源书/主题整理后的规则书
```

## 常用命令

### CI/CD（2026-08-03 起，Phase 1）

- **工作流**：`.github/workflows/ci.yml`——push 到 `main`/`feat/**` 或 PR 自动触发「专长数据质量闸口」。
- **链路（v2.2 决策 B 收敛为单命令，本地=CI 同一事实源）**：`python3 -m vectorizer.cicd verify --category feat` = pytest 类目收集（装配表 tests glob，feat 验收面 416 = A~G 通用 + feat 专属，法术专属不混入）→ 重跑专长 pipeline（**finalize 后处理链内建**：`FeatProcessor.POSTPROCESSORS` 四步骤，决策 A，无独立脚本）→ verify_feats 5 项 → 数据不变量闸口（`verify_data_invariants.py`：空 text ≤51、>5000 字符 =0、总数 ≥6000、feat ≥4000、**book '?' ≤100、toc 空 =0**）→ 产物归档 artifact（feat-chunks）。
- **本地等效命令**（与 CI 完全同源，跑一次 = CI 验证一遍）：
  ```bash
  cd /Users/chezi/code/java/pf_agent/pf_data/phase1
  python3 -m vectorizer.cicd verify --category feat   # 完整验证链；或 bash regen_feat_chunks.sh
  ```
- **CI 环境差异教训**：CI 用 Python 3.12（本地 3.14 的 PEP 649 惰性注解曾掩盖 pipeline.py 缺失的 FileProcessor 导入，已补）；产物级测试依赖 gitignored 产物，CI 上自动 skip；runner 纯净 Python **不带 pytest**，yml 必须保留「安装依赖（仅 pytest）」步骤（教训 B5，2026-08-03 决策 B 收敛时误删导致 CI 首跑失败）。

### 运行术语清洗流水线

```bash
# 进入一期工作目录
cd /Users/chezi/code/java/pf_agent/pf_data/phase1

# Phase 3（当前推荐流程）：从基线重新生成优化版与 JSON，并自动验收
python3 cleanup_phase3.py
python3 verify_phase3.py

# 旧流程（保留历史脚本）
# python3 cleanup_phase1.py
# python3 cleanup_phase2.py
```

注意：`cleanup_phase1.py` 和 `cleanup_phase2.py` 内部写死了绝对路径（`/Users/chezi/.openclaw/workspace/touniang/pf_data/phase1/...`），但实际输出文件在当前 `phase1/` 目录下；`cleanup_phase3.py` 采用相对路径，可直接在当前目录运行。

### 查看分类统计

```bash
# 统计当前优化版中各分类术语数量
python3 -c "
import re
text = open('术语提取报告_优化版.md', encoding='utf-8').read()
for m in re.finditer(r'## (.+?)（(\d+) 个术语）', text):
    print(f'{m.group(1)}: {m.group(2)}')
"
```

### Git 操作

仓库的 Git 根在 `pf_agent/`（2026-07-30 起，远程 `git@github.com:ytche/pf_agent.git`），覆盖整个仓库。日常工作目录仍在 `pf_data/phase1/`。

```bash
cd /Users/chezi/code/java/pf_agent
git status
git log --oneline -10
```

已有关键提交：
- `911b0a6` rollback: 回滚到原始版本
- `a8c7a81` phase2: 格式优化完成
- `c2c1793` phase1: 数据清洗完成
- `9636d93` docs: KN001 状态更新为已修复（V009）
- `23e3563` docs(workflow): 标准化职业向量化质量迭代工作流
- `2103e44` feat(vectorization): V009 — AggregationTableProvider 解析聚合页来源书表
- `pre-normalization-baseline` tag: V001~V009 开工前回滚基线（2026-07-21）

更多提交与 V001~V009 迭代速查见 `PROJECT_HANDOVER.md` §3B / §10.C。

### 运行分析脚本

```bash
cd /Users/chezi/code/java/pf_agent/pf_data
python3 analyze_all_l1.py         # 分析所有 L1 目录项
python3 analyze_crb_fixed.py      # 分析核心规则结构
python3 analyze_spell.py          # 分析法术结构
python3 extract_full_toc_v6.py    # 提取完整目录
```

## 数据流与架构

1. **源数据**：`~/.openclaw/workspace/pf_rules/`（CHM 解压后的 HTML）和 `pf_rules_md/`（2156 个 Markdown 文件）。
2. **目录解析**：从 CHM 的 `.hhc` 文件提取目录树，关键规则见 `CHM_STRUCTURE_ANALYSIS.md`：
   - 根 `<UL>` 深度为 0；
   - 每个 `<UL>` 深度 +1，每个 `</UL>` 深度 -1；
   - `ul_depth == 1` 的 `<LI><OBJECT>` 为 L1 项（实际共 17 个 L1）。
3. **术语提取**：基于正则从 `pf_rules_md/` 中提取英文术语、出现次数和上下文译名。
4. **清洗流水线**：
   - `cleanup_phase1.py` 读取 `术语提取报告_分类版.md`，输出 `清洗版.md`、`重分类版.md`、`边界案例待复核.md`、`优化日志.md`；
   - `cleanup_phase2.py` 读取 `重分类版.md`，输出 `术语提取报告_优化版.md` 和 `PF_缩写表.md`；
   - `cleanup_phase3.py` 读取 `术语提取报告_分类版.md`（基线，只读），调用 `term_rules.py` 中的覆盖表与信号规则，输出 `术语提取报告_优化版.md`、`terms.json`、`manual_review_phase3.md`，并追加日志到 `优化日志.md`；
   - `verify_phase3.py` 对 `cleanup_phase3.py` 的输出进行 6 项自动化验收检查。

## 规则书向量化

一期术语表完成后，当前工作进入**规则书向量化**：将 `pf_rules_md_organized/` 下的 Markdown 文件清洗、分块、富化元数据，为规则问答 Agent 提供可检索、可溯源的 chunk。

- **核心脚本**：`pf_data/phase1/vectorization_prep_profession.py`
  - 输入：`pf_rules_md_organized/职业`
  - 输出：`vectorization_prep_profession/`（gitignored）
  - 组件类型：`class_overview` / `class_feature` / `class_archetype`
  - 支持 `feature_subtype`（如 `hex`、`major_hex`、`grand_hex`、`patron`）

- **规则文档**：`pf_data/phase1/规则书向量化规则.md`
  - 任何向量化相关修改前应先阅读该文档。
  - 包含清洗、标题提升、组件识别、来源书识别、小块合并、变体主表解析等规则。

- **迭代工作流**：`pf_data/phase1/WORKFLOW.md`（2026-07-23 新增）
  - V/N 迭代 4 步流程：审计（5 Group subagent）→ 分类（8 Type）→ 修复（Batch A/B/C/D）→ 验证
  - 每次修复前必须先查 WORKFLOW.md 决策树（改脚本 / 改源数据 / 后处理）

- **问题记录**：
  - `pf_data/phase1/问题与修复记录.md` — 4 个已闭环典型问题（001~004）
  - `pf_data/phase1/已知问题记录.md` — 5 个 KN（决定不修 / 暂缓 / 已修复）

```bash
cd /Users/chezi/code/java/pf_agent/pf_data/phase1
python3 vectorization_prep_profession.py
```

- **专长模块 pipeline（R7 统一验收入口）**：
  ```bash
  cd /Users/chezi/code/java/pf_agent/pf_data/phase1
  # ⚠️ input 必须是 pf_rules_md_organized 根目录：判别器矩阵 189 rel 中
  # 66 个根级 rel（如 专长41.md）在根目录，传 专长/ 子目录会整批漏扫
  python3 -m vectorizer.pipeline --category feat --input pf_rules_md_organized --output vectorizer/output/专长
  # ⚠️ verify 必须用 -m 运行（直接跑脚本方式 import vectorizer 失败）
  python3 -m vectorizer.verify.verify_feats
  python3 -m pytest vectorizer/tests/ -q
  ```

- **种族模块 pipeline（#97~#101，产出即检已闭环）**：
  ```bash
  cd /Users/chezi/code/java/pf_agent/pf_data/phase1
  python3 -m vectorizer.pipeline --category race --input pf_rules_md_organized --output vectorizer/output/种族
  python3 -m vectorizer.verify.verify_races   # 六检查：判别器回归/召回/六字段/title/字段健康/replaces
  python3 -m vectorizer.cicd verify --category race   # 完整验证链（pytest + 重跑 + verify + 闸口）
  ```
  - 产物：**2390 chunks** / 11 component_type / pytest **629** / est 2132 ↔ got 2390（**+258 全定性**）
  - 遗留：首轮审计已闭环（2026-08-04）；KN098~106 登记（KN104 登记不修）；检索端语义降权评估（KN098/100）待一期联调——详见 `docs/已知问题记录.md`

- **各模块 pipeline 统一验收入口（feat/race/trait/equipment/rule 五类目）**：
  ```bash
  cd /Users/chezi/code/java/pf_agent/pf_data/phase1
  # 单命令完整验证链（pytest 类目收集 → pipeline 含 finalize → verify 公共框架
  # → 数据不变量闸口），本地=CI 同源；feat/race/equipment/rule 另有 regen_*_chunks.sh 快捷入口（trait 无）
  python3 -m vectorizer.cicd verify --category feat       # 专长
  python3 -m vectorizer.cicd verify --category race       # 种族
  python3 -m vectorizer.cicd verify --category trait      # 背景特性
  python3 -m vectorizer.cicd verify --category equipment  # 装备
  python3 -m vectorizer.cicd verify --category rule       # 规则
  ```

## 约束与规范

- **`术语提取报告_分类版.md` 不可修改**（基线）。
- 所有对术语报告的修改应通过脚本自动化执行，避免手工编辑 Markdown 表格。
- 每个阶段完成后应 `git commit`，保持可回滚基线。
- "推荐翻译"必须是纯净译名，不能混入描述句子；"其他翻译"列只保留不同译名变体，去掉上下文例句。
- **先理解后向量化**：整理任何职业或规则主题前，先阅读其 CHM 目录末级基础页和关键补充文件；脚本输出后必须抽样核对核心条目（如基础页列出的巫术/变体数量是否与 chunk 一致），发现常识性错误时回到源文件修正，禁止仅靠正则硬修。
- **先理解代码设计再修 bug**：修改 bug 需要改代码时，先阅读相关模块/类/钩子的现有设计（如 `FileProcessor` 模板方法、`EXPAND_STRATEGIES` 注册表等），优先利用已有扩展点注入规则；避免在通用流程中直接硬编码 `if class_name == "X"` 这类业务特判，防止代码腐化。
- **讨论阶段不动手**：问题/方案讨论期间只读不改——不执行代码修改、不跑修复命令，讨论输出只写方案文档；方案经用户明确拍板后再动手。清理/修复类工作先统一记入方案文档（如 `pf_data/phase1/docs/向量化设计优化方案_20260805.md`），按方案批次执行，不边讨论边改。
- **沉淀先收割既有沉淀**：写经验沉淀/复盘文档时，第一步收割既有沉淀——经验链三条：`pf_data/phase1/docs/流程教训沉淀.md`（专长）→ `跨模块经验沉淀_种族模块_20260805.md` → `跨模块经验沉淀_背景特性模块_20260806.md`（trait，第三条 2026-08-06），另加各模块开工清单、架构文档教训登记中的相关条目，合并引用后再补新条目；禁止只凭本模块文档链总结——已登记的教训被重新发明时会丢原文、丢引用、丢速查入口（2026-08-05 种族沉淀漏收 E4/E5 实例）。
- **spell/职业 pipeline 已解除冻结（2026-09-01 阶段二）**：两模块均已接入 cicd（`--category spell` / `--category profession` 四步链，本地=CI 同源），重跑一律走 `python3 -m vectorizer.cicd verify --category spell|profession`，禁止绕过 cicd 直跑 pipeline。KN136 已修复（[PZO 守卫 c852987）+ 真重跑恢复 4172（k3 裁定新基线）+ 冻结解除，详见 `docs/已知问题记录.md` KN136/KN225。

- **CLAUDE.md 防膨胀（操作指南定位）**（2026-08-09 沉淀，先例：22,620→11,661
  字符瘦身 -48%，commit `76a49b3`）：CLAUDE.md 是**操作指南**（命令 / 行为红线 /
  状态速查），每轮会话全量常驻——**不是档案库**。向 CLAUDE.md 新增内容前自查：
  这条信息对「每次会话干活」有指导价值吗？纯追溯/过程叙述（KN 修复编年史、
  批次过程、中间数字链如 chunk 9377→9366→9256→7847、commit 清单）→ **只写
  一句话终态 + 文档指针**，细节放 `docs/已知问题记录.md` / `PROJECT_HANDOVER.md`
  / 模块文档（按需读取，不常驻）。状态章节各模块固定形态：一句话终态（数字）+
  关键遗留 + 指针；禁止续写过程叙事。
- **含专项覆写的处理模块改动前的不变量清单**：修改任何含专项后处理覆写（subclass override / `_fix_*` 函数 / 文件专属 Processor）的核心处理模块前，必须先回答"本次改动涉及哪些结构不变量（heading 层级、chunk 边界、归属、来源书等）"，并在 `verify_*.py` 中对每条不变量有断言，跑通后才算完成。chunk 级"OK 数合理"不构成验证；negative test（"不该出现的 chunk 没出现"）同样必要。
- **Java 方法命名（2026-08-16 起）**：Java 代码（含单元测试）的方法名必须使用标准英文驼峰命名（camelCase），禁止在方法名/标识符中出现中文字符；方法的中文说明写入方法 Javadoc（`/** 说明 */`）。**仅约束 Java，Python 不受此限制**（Python 方法/pytest 方法名按既有约定）。
- **Java 方法顺序（2026-08-16 起）**：类中方法按访问级别排序——静态public > public > 静态protected > protected > 静态package（默认可见性）> package > 静态private > private（rank 1~8，同级稳定排序保持原相对顺序）。只调整方法块相对顺序：方法前导 Javadoc/注解随方法移动，**字段/构造器/内部类保持原位**；顶层类结束 `}` 不随方法移动。`@PostConstruct`/`@Test`/`@BeforeEach` 等注解方法按访问级别参与排序（package 级测试方法排在 public 之后、private 之前）。**仅约束 Java，Python 不受此限制**（Python 方法/pytest 方法名按既有约定）。
- **Spring 注入方式（Java）**（2026-08-16 起）：Spring bean 的依赖注入统一用 **`@Autowired` 字段注入**，配置值用 **`@Value` 字段注入**，**禁止构造器注入**——不写带参构造器；构造器里的组装/初始化逻辑（如从依赖构建注册表、索引）移到 `@PostConstruct` 方法。多实例 bean（如各模块 `SimpleVectorStore`）在字段上保留 `@Qualifier`。边界：`@Configuration` 类的 `@Bean` 工厂方法参数注入（Spring 官方配置风格）与手动 `new` 的普通类（非 Spring bean）不受此限。**仅约束 Java/Spring，Python 不受此限制**。
- **交接/交付文档统一放置（2026-08-26 起）**：所有 pf_agent 交接/交付文档（含「交付」「交接」「移交」「接手」字样）统一放 `docs/handover/`，禁止放仓库根目录；规则与索引见 `docs/handover/README.md`。例外：`PROJECT_HANDOVER.md`（项目总交接，顶层常驻）保留根目录；kimi 会话导出（`kimi-export-session_*.md`）非交付文档保留原位置。

## 当前状态与优先级

截至 2026-08-25。各模块终态速查；完整编年史、KN 细节与待办见
`PROJECT_HANDOVER.md` 与 `docs/已知问题记录.md`（KN 编号速查）——按需读取，不再常驻。

- **术语表 ✅**：1068 术语（P2 清理闭环 2026-08-07），`terms.json` + `verify_phase3.py` 6/6。术语关联关系（二期准备）。
- **职业向量化 ✅**：5 Processor / 9 Provider / 27 subtype，WORKFLOW.md 标准化迭代流程。阶段一（2026-09-01）迁入 vectorizer 框架 + StandardChunk schema + cicd profession 四步链（13922 chunks、KN222 已闭环），ClassChunk 退役删除。
- **法术模块 ✅**（阶段二 2026-09-01 解除冻结，KN136 修复 + 真重跑恢复 4172）：KN011 link 内建 finalize、cicd spell 四步链接入。遗留：KN225 创造万物尾部链接行残留（P3，spell normalize 定向剥除，禁动共享层）。
- **专长模块 ✅**：6032 chunks、召回 1061/1061 = 100%、pytest 662、KN076~095 全闭环（含 KN112 守卫回归修复）。交付 `docs/专长/专长模块数据使用说明.md`。
- **种族模块 ✅**：2390 chunks、pytest 629、首轮审计闭环（2026-08-04）。KN098~106 登记（KN104 登记不修）。遗留：检索端语义降权评估，待一期联调。
- **背景特性模块 ✅**：1122 chunks、首轮审计闭环（2026-08-05）。KN137~140 登记（KN138 亚产能 16 文件登记不修）。遗留：book '?' 201 顶格（KN137），待一期联调。
- **装备模块 ✅**：5385 chunks（2026-08-09 收口，KN161~189 登记）。交付三件套 `docs/装备/`。
- **技能模块 ✅**：556 chunks、pytest 1018、M6 审计闭环（2026-08-07）。KN150~160 全闭环。遗留：检索端降权项，待一期联调。
- **规则模块 ✅**：7847 chunks（章节型规则文本）、verify 十检查、pytest 1310、全量审计 + 批次 A/B/C 修复闭环（2026-08-09，KN210~220）。KN191~221 登记（KN207 来源行剥离待拍板、KN221 表格结构化待统一处理）。交付三件套 `docs/规则/`。遗留：book '?' 188/238、续N 1265 既有形态、长 title 200（KN219）、检索端降权项——均待一期 Agent 检索联调。

**当前遗留与下一步**（详见 `PROJECT_HANDOVER.md`）：
1. ~~一期 Agent 检索联调批次~~ ✅ **已闭环（2026-08-25）**：P0-B（isBaseClassPage 前缀 + 模块路由提示，44→46）+ P0-B2（title 过滤全模块 + 候选扩容/title 加权 + AKN-008 drain 去重修复，46→**50/50 满分**）；单测 157 全绿。方案/交付文档见 `pf_agent/agent/docs/`（P0-B检索联调批次实施方案、剩余4题溯源修复方案）
2. 规则 KN207「未整理 →」行剥离（剥离前须固化来源提取链路，待拍板）
3. ~~**不重跑冻结模块**（spell/职业，KN136 禁令持续有效）~~ ✅ **已解除（2026-09-01 阶段二）**：spell KN136 修复 + 真重跑 4172 + cicd 接入；职业阶段一已迁框架 + cicd
4. ~~职业 KN222 进阶职业 chunk 缺失（简写表头块整块被纯表格过滤器丢弃，40 页受影响）——数据分支修复~~ ✅ **已闭环（阶段一 CP2）**，详见 `docs/已知问题记录.md`

完整待办、风险与文件说明见 `PROJECT_HANDOVER.md`。

## 外部参考路径

- PF 规则库 Markdown：`~/.openclaw/workspace/pf_rules_md/`
- 原始 CHM 解压文件：`~/.openclaw/workspace/pf_rules/`
- CHM 源文件：`~/Downloads/Pathfinder v2.24 SC.chm`
- Obsidian 资料库：`~/Library/Mobile Documents/iCloud~md~obsidian/Documents/main/02-Areas/游戏/PathFinder/`

## 未整理目录整理规则与进度

处理 `pf_data/phase1/pf_rules_md/未整理 → <来源书>` 下的规则书时，按需阅读以下文档：

- **整理规则文档**：`pf_data/未整理目录整理规则.md`
  - 规范分类、合并、来源标注、去重、增量写入与提交流程。

- **进度追踪文档**：`pf_data/phase1/未整理规则书整理进度.md`
  - 按 `CHM_FULL_TOC_WITH_LEVELS.md` 顺序记录 147 本 L2 规则书的整理状态。
  - 每完成一本规则书需同步更新并提交 Git。
