# 向量化质量迭代工作流

> 适用范围：`pf_data/phase1/` 向量化流水线的质量问题发现、分类、修复、验证与沉淀。
> 目标：标准化 V/N 迭代流程，确保不同 Agent、不同类目（职业/法术/专长等）接手时能一致地执行。
> 版本：v2.1 · 2026-08-03 · v2.0 基于职业模块 V001~V009 重构；v2.1 同步法术/专长模块落地状态（基础设施从「待搭建」转为实际位置）

> 📌 流程教训沉淀（2026-08-03）：专长模块全程复盘的跨模块可复用教训见 [`流程教训沉淀.md`](流程教训沉淀.md)（五类：环境/回填/审计/源数据/闸口）——新模块开工前与本工作流配套阅读。

---

## 通用约束

以下规则适用于所有步骤：

| 规则 | 说明 |
|------|------|
| **设计层面修改需用户拍板** | 涉及架构、模块边界、抽象层设计、不变量定义的变更，必须记录问题+建议方案后提交用户，用户确认后才执行。不得直接修改设计文档（`VECTORIZER_ARCHITECTURE_DESIGN.md` 等） |
| **每个 Step 完成后提交 Git** | 保持可回滚基线 |
| **类目无关原则** | 工作流本身不绑定任何具体类目（职业/法术/专长），类目特定规则由相应 `formats/*.py` 声明 |

---

### 重生成入口

**重生成 chunks 必须走统一入口**，禁止单独跑 pipeline 后遗漏后处理步骤：

```bash
cd pf_data/phase1
bash regen_spell_chunks.sh        # 法术模块
bash regen_feat_chunks.sh         # 专长模块（pipeline → 四后处理 → pytest → verify，与 CI 同链路）
```

法术脚本按序执行：向量化重生成 → KN011 MA 增强链接 (`link_mythic_base_spells.py`) → pytest 单元测试 → verify_spells + verify_kn011_018 验收。chunk 总数必须保持 4200。

专长模块（双入口同链路）：本地 `regen_feat_chunks.sh`（8-01 建，Step 2 含四后处理脚本）+ CI 闸口（`.github/workflows/ci.yml`）：
pytest → pipeline 重跑 → **四后处理脚本（顺序不可变）** → verify_feats → 数据不变量闸口。⚠️ 重跑专长 pipeline 后遗漏四脚本即回归（book/source/toc 回退），教训见 [`流程教训沉淀.md`](流程教训沉淀.md) B1。

**后续模块（装备/怪物）**：验证链收敛为单一编排命令 `python3 -m vectorizer.cicd verify --category <类目>`（pytest 类目收集 → pipeline 含 finalize 后处理 → verify → 数据不变量），regen 脚本与 CI yml 都只调它，无独立后处理步骤与双份链条（见 `VECTORIZER_ARCHITECTURE_DESIGN.md` §4.9 v2.2 决策 A/B）；专长/法术外挂链为已验收状态，不迁移。

若需要增量调试（如只改一行业务逻辑），可单独跑对应步骤，但**交付前必须全量跑通一键脚本或 CI 链路**。

---

## 核心流程

```
V{N} 迭代
═══════════════════════════════════════

Step 0 — L0 事实检查：自动扫描（秒级，纯计算）
  └─ 🤖 脚本（python3 audit.py），不用 Agent

Step 1 — 审计：根因驱动的语义扫描
  └─ 🤖🤖🤖 多 subagent 并行（按扫描策略分片）

Step 2 — 分类：通用 Type + 类目 Type 归类 + 5 分支决策
  └─ 👤 主 Agent（决策步骤，不并行）

Step 3 — 修复：按风险级 + 修复方式分批执行
  ├─ Batch A：低风险配置 → 👤 主 Agent
  ├─ Batch B：中风险类隔离 → 🤖🤖 可按 Processor 并行
  ├─ Batch C：高风险源数据 → 🤖🤖🤖 可按文件簇并行
  └─ Batch D：后处理 → 👤 主 Agent

Step 4 — 验证：V{N+1} 验证性重审
  └─ 🤖🤖 多 subagent 并行（按验证维度分片）

Step 5 — 沉淀：反馈闭环
  └─ 👤 主 Agent（记录决策，不并行）

每个 Step 完成后提交 Git。
```

### 并行化概述

| Step | 执行者 | 并行策略 |
|------|--------|---------|
| 0 | 脚本 | N/A（秒级单进程） |
| 1 | Subagent | **按扫描策略并行**：每个根因模式 = 1 个 subagent，各扫全模块，互不依赖 |
| 2 | 主 Agent | 不并行（决策依赖 Step 0+1 的完整结果） |
| 3-A | 主 Agent | 不并行（配置改动量小，串行安全） |
| 3-B | Subagent | **按 Processor 并行**：每个新建/修改的 Processor = 1 个 subagent |
| 3-C | Subagent | **按文件簇并行**：同一格式簇的文件归一化 = 1 个 subagent |
| 3-D | 主 Agent | 不并行（后处理有顺序依赖） |
| 4 | Subagent | **按验证维度并行**：修复确认 / 回归 / 残留 可分别给不同 subagent |
| 5 | 主 Agent | 不并行（决策记录需要统一视角） |

---

## Step 0 — L0 事实检查（自动扫描）

### 定位

pipeline 跑完后自动执行的纯计算扫描。**不做语义判断**，只报告「一定有问题」的事实。

L0 告警 = 问题一定存在，直接进修复，Agent 审计不再重复发现。

### 事实检查项（通用，所有类目适用）

```
□ title 含 URL（https?://）
□ title / text 含 【?】 未解析占位符
□ text 中 ** 开闭数量不匹配（bold 断裂）
□ book_abbreviation 为 ? 或空
□ class_name / 类目标识为空
□ text 去空白后 < 10 字符（空 chunk）
□ 同一 doc_id 出现多次（重复 chunk）
□ 输入文件产出 0 个 chunk（被管道丢弃）
```

### 与 Agent 审计（Step 1）的边界

| | L0（Step 0） | Agent 审计（Step 1） |
|---|---|---|
| 方式 | 纯正则/统计 | Agent 语义理解 |
| 能判断「一定有问题」 | ✅ | ✅ |
| 能判断「这个 bold 该不该提升」 | ❌ | ✅ |
| 能判断「这个 overview 内容对不对」 | ❌ | ✅ |
| 能扩散同类问题 | ❌ | ✅ |

---

## Step 1 — 审计（根因驱动的语义扫描）🤖🤖🤖 多 subagent 并行

### 并行策略

```
主 Agent 收到问题 → 分析出 N 个根因模式
  ├── 根因 1 → subagent A（全模块扫描策略 1）
  ├── 根因 2 → subagent B（全模块扫描策略 2）
  └── 根因 N → subagent N（全模块扫描策略 N）
                        ↓ 并行执行，各自输出问题清单
主 Agent 合并去重 → 输出统一问题清单 → 进 Step 2
```

> 每个 subagent 独立扫描全模块。不按职业/文件分片（那会漏掉跨分片的同类问题），而是按根因模式分片——每个 subagent 用不同的过滤策略扫同一批数据。

### 核心变化（v2.0）

旧版 Step 1 按 5 个预定义 Group × 职业类型做统计抽样。问题是：

- 审计范围是预定义的，和 bug 根因无关（Bug 005 的 bold 提升误判跨越所有 Group，但每个 Group 只抽自己负责的职业）
- 统计抽样无法保证覆盖同一根因下的所有受影响文件

v2.0 改为**根因驱动、全模块扫描**。

### 触发条件

- 用户发现质量问题
- L0 事实检查告警
- 上一轮修复的验证反馈

### 与 L0 的衔接

L0 是线索，不是完整清单。subagent 根据 L0 事实理解根因后扫全模块，不是只验证 L0 报告的那几条。

### 执行步骤

```
1. 理解根因模式 — 不是「某职业 chunk 错了」，而是「哪个处理步骤，在什么条件下，
   产生什么错误结果」

   示例：
   ❌ 「先知文件里"选拔与入阁"被错归为变体」            ← 表象
   ✅ 「promote_leading_bold_headings 提升 **章节名** 时，
        looks_like_ability_title 对纯中文章节名返回 False，
        导致非标题 bold 被误提升为 ## heading」          ← 根因

2. 翻译为扫描策略 — 这个根因在什么条件下会触发？用条件去过滤全量数据。

   策略示例（对应上例）：
   - 条件 1：chunk 的 title 来自 bold 提升（breadcrumb 末级不含 # 前缀的原始行）
   - 条件 2：title 不含 (English) 或 Ex/Su/Sp 信号（即 looks_like_ability_title 会漏判的）
   - 条件 3：出现在变体文件 / 补充文件（非基础页）
   - 查询：从 chunks.jsonl 中筛出满足所有条件的 chunk
   - 补充：必要时直接扫源文件中 **xx（English）** 模式的上下文

3. 全模块扫描 — 不按职业分片，不抽样，按策略过滤当前类目下所有文件。
   范围 = 整个 pf_rules_md_organized/<类目>/
   方式 = Agent 逐条审查过滤结果，确认是否误判

4. 输出问题清单 — 按根因模式分组，每条包含：
   (受影响文件, 受影响 chunk 数, 问题描述, 根因, 置信度)
```

### 判断修复的必要性原则

- **必须修**：影响 Agent 检索方向、导致错误答案、内容完全不对
- **可修可不修**：内容正确但分类略不准（Agent 可从文本自纠正）
- **不修**：罕见边界 case，Agent 不会遇到 → 记录到 `已知问题记录.md`

---

## Step 2 — 分类（问题归类 + 5 分支决策）

### 问题类型：通用层（所有类目适用）

| Type | 问题 | 根因 | 风险 |
|------|------|------|------|
| **G1** | 格式污染 | 源文件含 URL/译者注/表格残留混入标题或正文 | 高 |
| **G2** | 归属缺失 | 来源书 ? / 类目标识为空 | 中 |
| **G3** | 结构破坏 | 处理步骤改变了原有层级、合并丢失文本、污染相邻块 | 高 |
| **G4** | 推断失败 | 子类型/元数据缺失，breadcrumb 和正文均无信号 | 中 |
| **G5** | 重复内容 | 多源文件产出相同 chunk | 低 |
| **G6** | 管道丢弃 | 文件被静默跳过或过滤（0 chunk） | 中 |

### 问题类型：类目层（各 formats/*.py 声明）

以上通用层是固定框架。各类目可在其 `formats/*.py` 中追加类目特有 Type，例如：

职业模块（历史模块，`vectorization_prep_profession.py`，已冻结未迁入 vectorizer 包）：
- P1：subtype 缺失（subtype_mapping 未注册）
- P2：overview 污染（聚合文件被误判为 overview）
- P3：跨类内容错归（文件错目录 / 多职业合辑）
- P4：变体误识别（子能力被提升为独立变体）

法术模块（`formats/spell.py`，已接入 v1.0）：
- S1：学派元数据缺失（元数据 15 字段 + field_status 三态落地，见 `已知问题记录.md` KN011~024）
- S2：法术等级误判（同上登记）

专长模块（`formats/feat.py`，已接入并阶段收口）：
- F1：专长类型缺失（combat/metamagic/... → 实际以 `FEAT_TYPE_NORMALIZE` 枚举 + `feat_type` 元数据落地，KN084 闭环）
- F2：先决条件未解析（实际以 `feat_index` 元数据组装方案处理，KN092/093）

> 说明：S1/S2、F1/F2 为 v2.0 预声明的示例 Type。实际模块落地时，类目特有逻辑直接编码进 `formats/*.py`（归一化规则 + 元数据枚举），具体问题统一按 KN 登记到 `已知问题记录.md`，不再维护独立的 Type 枚举清单。

### 风险评估矩阵

| 风险级 | 判断标准 | 处理方式 |
|--------|---------|---------|
| 🔴 **高** | 影响 Agent 检索方向 / 导致错误答案 | 单独定方案 |
| 🟡 **中** | 降低检索精度 / 少量噪声 | 类隔离 / 后处理 |
| 🟢 **低** | 边界 case / 不影响核心功能 | batch 处理 / 配置 |

### 修复方式选择（5 分支决策树）

| 修复方式 | 适用场景 | 示例 |
|---------|---------|------|
| **改源文件** | 源文件格式不规范 | 加 `##` 标题、修复 `**` 断裂、拆分连续段落 |
| **改脚本/配置** | pipeline 逻辑 bug 或配置缺失 | subtype_mapping 加行、修复 regex、新建 Processor |
| **后处理** | 通用逻辑无法覆盖的边界错误 | cleanup_subtype_mismatch.py、dedupe |
| **加诊断规则** | 可通过 diagnostics.py 在下一轮预防 | 连续 N 个 bold 无 heading → ERROR |
| **记架构债** | 设计层面的改进，需用户拍板 | 新增不变量契约、模块边界调整、抽象层重构 |

```
决策流程：

问题确认
  ├── 源文件格式不对？                              → 改源文件
  ├── 脚本逻辑 bug / 配置缺失？                     → 改脚本/配置
  ├── 通用逻辑对的，但极少数边界 case？               → 后处理
  ├── 下一次能自动发现吗？                           → 加诊断规则
  └── 是设计/架构层面的改进？                        → 记架构债 → 提交用户拍板
```

---

## Step 3 — 修复（分批执行）

### 并行策略

| Batch | 执行者 | 并行方式 |
|-------|--------|---------|
| A | 👤 主 Agent | 配置改动量小，串行即可 |
| B | 🤖🤖 可按 Processor 并行 | 每个新建/修改的 Processor 互相独立，可同时开发 |
| C | 🤖🤖🤖 可按文件簇并行 | 同一格式簇的文件归一化可并行（同簇内串行保险） |
| D | 👤 主 Agent | cleanup/dedupe 有顺序依赖，串行 |

### 修复顺序

```
Batch A — 低风险配置（映射/别名/白名单加行）
    ↓ verify（确认无回归）
Batch B — 中风险类隔离（新建/修改 Processor）
    ↓ verify（确认类隔离生效）
Batch C — 高风险源数据修复（改源文件 + normalize 脚本）
    ↓ 重跑向量化 + verify
Batch D — 后处理（cleanup + dedupe）
    ↓ 全量 verify
```

### 标准处理子流程（按需加载，命中条件再读全文）

以下标准路径是修复类目下的子流程，触发时按链接读取，不常驻本文档：

| 子流程 | 触发条件 | 文档 |
|---|---|---|
| **格式杂乱聚合文档重建** | 判别器 est>0 但 got=0/≪est + 源 md 整段粘连 + est 与原始 HTML 条目数一致 | [`格式杂乱聚合文档标准处理工作流.md`](格式杂乱聚合文档标准处理工作流.md)（6 步主线：溯源→定位 HTML→决策门→重建→产 chunk→验收） |
| **校验问题处理** | 自动化验收脚本失败 / 抽样发现问题 | [`标准流程_校验问题处理.md`](../../标准流程_校验问题处理.md)（发现→记录→根因→横向→修复→验证→关闭） |
| **HTML 回退解析** | 源 md 格式损坏无法直接整理 | [`整理规则_详情/12_HTML回退解析.md`](../../整理规则_详情/12_HTML回退解析.md)（SOP 前身：亡灵杀手手册期先例） |
| **产出即检三件套** | 产出 chunk 后首轮 / pipeline 重跑后（不可预防类正则缺陷的最低成本早检） | [`专长/专长模块开工前_流程抽象与预防清单.md`](专长/专长模块开工前_流程抽象与预防清单.md) §四（title 合法性 + 字段值健康度 + 列表召回率 + 新正则全量触发计数 + probe） |
| **来源书链路修复** | book 未知 / chm_toc_path 空 / source 空（后处理产物回退） | [`专长/来源书链路修复方案.md`](专长/来源书链路修复方案.md)（断点 A 重跑两 apply → 断点 B 三级回填 → source 补齐） |

### 修复基础设施

| 基础设施 | 说明 | 当前位置 |
|----------|------|---------|
| TDD 测试（A~G 七类） | 跨类目普适回归护栏（开发阶段）；职业 V001~V009 6 类 → 法术 264 → 专长 530 用例 | `vectorizer/tests/`（已建成） |
| L0 事实检查 | 产出级自动扫描（运行阶段，Step 0）；三级审计：Tier 1 绝对断言 / Tier 2 声明式预期 / Tier 3 统计偏差 | `vectorizer/audit.py`（已建成） |
| diagnostics.py | 源文件质量门（pipeline 前，DiagnosticsGate） | `vectorizer/diagnostics.py`（已建成） |
| subtype_mapping | 子类型面包屑关键词匹配；专长另含 `FEAT_TYPE_NORMALIZE` 类型枚举 | `formats/<类目>.py` |
| Processor 子类 | 类隔离的钩子覆盖 | `vectorizer/processors/` |
| SourceProvider 链 | 链式置信度聚合 | `vectorizer/sources/` |
| normalize 脚本 | 源文件标题归一化 | `normalize_*.py` |
| cleanup 脚本 | 后处理误标清理 | `cleanup_*.py` |
| dedupe 脚本 | 通用去重 | `dedupe_*.py` |
| verify 脚本 | 集成验收 | `verify_*.py` |
| 已知问题记录 | 决定不修的 KN 项 | `已知问题记录.md` |

### 新建脚本模板

**新建 normalize 脚本（源文件归一化）**：参考 `normalize_masterpiece_titles.py` 的剥离 `**` + 正则识别 + 替换为 `##` 标题模式。

**新建 Processor**：参考 `PaladinProcessor` 的类结构，覆盖对应钩子。

**新建 verify 脚本**：参考 `verify_subtype_coverage.py` 的断言模式（数量下限 + 正向 + 负向）。

---

## Step 4 — 验证（V{N+1} 验证性重审）🤖🤖 多 subagent 并行

### 并行策略

```
主 Agent 列出验证维度
  ├── 维度 1：修复确认（逐项对比 V{N} 报告）→ subagent A
  ├── 维度 2：回归检查（未修改部分是否异常）→ subagent B
  └── 维度 3：残留问题（未修复项更新优先级）→ subagent C
                      ↓ 并行执行
主 Agent 合并 → 输出 V{N+1} 验证报告
```

### 验证方法

与 Step 1 相同的根因驱动扫描模式，但验证重点改为：

1. **修复确认** — V{N} 声称修复的项逐一检查 ✅ / ❌
2. **回归检查** — 未修改的部分是否出现新的问题
3. **残留问题** — 未被修复的项，更新优先级或记录为 KN

### 验证报告格式

```markdown
## V{N+1} 验证报告

### 修复确认
| V{N} 问题 | 当前状态 | 确认 |
|-----------|---------|------|
| 问题描述 | 实际结果 | ✅ / ❌ |

### 回归检查
| 检查项 | 结果 |
|--------|------|
| 非目标 chunk 总数无异常下降 | ✓ / ✗ |
| 此前已闭环问题未复现 | ✓ / ✗ |

### 残留问题
| 问题 | 根因 | 建议 |
|------|------|------|
```

### 标准验证检查项

```
□ L0 事实检查：0 新增告警（或新增告警已确认非回归）
□ 所有已知 subtype / 类目元数据数量满足最小阈值
□ 无跨类误标
□ 无管道丢弃（0 chunk 文件在已知跳过清单内）
□ V{N} 修复项全部 ✅ 或已记录为 KN
```

---

## Step 5 — 沉淀（反馈闭环）

### 目的

Bug 修完后，流程不应结束。应将教训编码到以下四个方向，防止同类问题再次出现。

### 5.1 诊断规则

> 这个 bug 能被 `diagnostics.py` 在 pipeline 处理前预防吗？

- 能 → 添加诊断规则，下次跑 pipeline 时自动阻断/告警
- 不能 → 说明理由（语义判断 / 需要 Agent 抽查 / 依赖外部知识）

示例：Bug 005 的「连续 N 个 bold 无 heading」→ 添加 `consecutive_bold_titles` (ERROR)

### 5.2 测试用例

> 这个 bug 对应 TDD 6 类的哪一类？

| TDD 类别 | 典型 bug |
|----------|---------|
| A — 标题提升误判 | Bug 005 |
| B — 标题提升漏判 | Bug 001 |
| C — 结构破坏 | Bug 004 |
| D — 格式缺陷 | KN004 |
| E — 推断通道单一 | KN002, KN003, KN005 |
| F — 来源错标 | Bug 002, 003 |

- 对应到某一类 → 在对应测试文件中补充参数化用例
- 不归属任何一类 → 评估是否需要新增类别

### 5.3 设计约束

> 是架构/设计层面的改进吗？

**判断标准**（满足任一即为是）：
- 涉及模块边界、抽象层、不变量定义
- 涉及 `VECTORIZER_ARCHITECTURE_DESIGN.md` 中描述的设计
- 涉及跨类目通用规则

**流程**：

```
1. Agent 记录：
   - 问题描述（发生了什么）
   - 当前设计的缺口（哪条约束缺失导致了这个 bug）
   - 建议的设计改进（具体方案）
   - 影响范围（涉及哪些模块/类目）

2. 提交用户拍板

3. ⚠️ 用户拍板前，Agent 不得直接修改设计文档
```

示例：Bug 004 → 建议「fixup 模块增加声明式不变量契约」→ 记录到 `VECTORIZER_ARCHITECTURE_DESIGN.md` §4.2（用户拍板后）

### 5.4 源文件/配置修复

非设计层面、非可诊断的一般修复 → 直接修，正常提交。

---

## 附录 A：各阶段 Prompt 模板

### A1. 根因分析 Prompt（Step 1 第 1~2 步）

```
你是 V{N} 审计 Agent。

## 输入
发现的质量问题：{问题描述}
当前模块：{类目名称，如 职业/法术/专长}

## 你的任务 — 仅做根因分析，不做修复

1. 阅读相关源文件和处理脚本，确定根因
   - 是 pipeline 的哪个阶段出的错？
   - 在什么条件下触发？
   - 影响范围预判（哪些文件/格式可能受影响）

2. 将根因翻译为扫描策略
   - 用哪些条件可以从 chunks.jsonl 或源文件中筛出所有受影响项？
   - 给出具体的 python 伪代码或正则模式

3. 输出：
   - 根因描述（一句话 + 传播链）
   - 扫描策略（可执行的过滤条件）
   - 预估影响范围
```

### A2. 全模块扫描 Prompt（Step 1 第 3~4 步）

```
你是 V{N} 审计 Agent。

## 扫描策略
{来自根因分析的过滤条件}

## 执行
1. 按策略在当前模块全量数据中过滤
2. 逐条审查过滤结果，确认是否误判
3. 按根因模式分组输出问题清单

## 输出格式
| 文件 | chunk 标题 | 问题 | 置信度 |
|------|-----------|------|--------|
```

### A3. 验证 Prompt（Step 4）

```
你是 V{N+1} 验证 Agent。

## 背景
V{N} 发现/修复了以下问题：{问题清单}

## 执行
1. 逐项确认 V{N} 修复项 → ✅ / ❌
2. 检查未修改的部分是否出现回归
3. 残留问题更新优先级

## 输出
见 Step 4 验证报告格式。
```

---

## 附录 B：职业模块的类目特定参考（保留自 v1.0）

以下内容为职业模块特有，移入附录供参考。法术（v1.0）、专长（已收口）均已按各自 `formats/*.py` 接入统一管线（`vectorizer/` 包），类目特有规则见对应 `formats/spell.py` / `formats/feat.py`。

### B1. 职业模块旧 Type 对照

| 旧 Type | 映射到新 Type | 说明 |
|---------|-------------|------|
| 1 — subtype 缺失 | G4 + P1 | 推断失败，breadcrumb 无信号 |
| 2 — Overview 污染 | P2 | 类目特有 |
| 3 — 跨类内容错归 | P3 | 类目特有 |
| 4 — 源文件格式解析失败 | G1 | 格式污染 |
| 5 — 重复 chunks | G5 | 通用 |
| 6 — Metadata 缺失 | G2 | 归属缺失 |
| 7 — Subtype 误标 | G4 + P1 | 推断失败 |
| 8 — Unchained 版本不一致 | P1 | 类目特有 |

### B2. Type 2 修复 checklist（改源文件，职业模块）

当修复 overview 污染时：

```
□ 确认污染源文件路径
□ 阅读文件前 5 行，确认真正的 overview 内容在哪里
□ 在真正的 overview 段前加 ## 职业概览 标题
□ 如果是全表类文件（武器训练全表等），应改为 class_feature 而非 overview
□ 对每个添加的标题，确认 （English） 括号存在（触发 looks_like_ability_title）
□ 重跑向量化脚本
□ 确认 overview 数下降，且内容正确
```

### B3. 职业模块基础设施索引

| 组件 | 位置 | 用途 |
|------|------|------|
| `vectorizer/` 包 | phase1/vectorizer/ | 统一管线（pipeline.py + formats + processors + sources + verify），职业/法术/专长共用（原 `vectorization_prep_profession.py` 已重构并入） |
| `verify_subtype_coverage.py` | phase1/ | 27 种 subtype 数量下限验证 |
| `verify_all_classes.py` | phase1/ | 全量职业验收 |
| `verify_class_attribution.py` | phase1/ | 归属验收 |
| `verify_heading_levels.py` | phase1/ | heading 层级回归 |
| `verify_no_false_archetypes.py` | phase1/ | 变体误识别 negative test |
| `verify_no_false_hex_sections.py` | phase1/ | 女巫巫术假阳性 |
| `verify_bardic_masterpieces.py` | phase1/ | 68 首传世名作 |
| `verify_paladin_archetypes.py` | phase1/ | 圣骑士/女巫回归 |
| `verify_venom_siphoner.py` | phase1/ | 汲毒巫专项 |
| `cleanup_subtype_mismatch.py` | phase1/ | 跨类 subtype 误标清理 |
| `dedupe_all_chunks.py` | phase1/ | 通用去重 |
| `normalize_masterpiece_titles.py` | phase1/ | 传世名作标题归一化 |
| `normalize_paladin_deities.py` | phase1/ | 圣骑士 deity 页面归一化 |
| `已知问题记录.md` | phase1/ | KN 全量登记（法术 KN001~024、专长 KN029/076~095 等；规划/审计中发现的问题一律登记此处，不中断主线） |
| `问题与修复记录.md` | phase1/ | 5 个已闭环问题（001~005） |
| `verify_spells.py` / `verify_kn011_018.py` | phase1/ | 法术模块集成验收 |
| `vectorizer/verify/verify_feats.py` | phase1/vectorizer/ | 专长模块集成验收（判别器/召回/字段健康，5 项） |
| `verify_data_invariants.py` | phase1/ | 数据不变量闸口（空 text ≤51 / >5000 字符 =0 / 总数下限，CI 使用） |
| `VECTORIZER_ARCHITECTURE_DESIGN.md` | phase1/ | 终局架构设计 |
| `WORKFLOW.md` | phase1/ | 本文档 |

---

*文档版本：v2.1 · 2026-08-03 · v2.0（2026-07-24）从 v1.0（V001~V009 职业模块实战）重构*
*后续维护：新增类目时在 Step 2 追加类目特有 Type，在附录追加类目特定参考*
