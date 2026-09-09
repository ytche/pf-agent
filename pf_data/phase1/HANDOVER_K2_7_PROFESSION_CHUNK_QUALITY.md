# 交接文档：职业 chunk 质量攻坚总体计划（交给 k2.7 执行）

> 交接目标：由 k2.7 按本文档执行 Phase A~E 全部工作，把职业类目 chunk 质量推进到"全格式簇验收通过"。
> 设计方：Claude Code（k3，2026-07-21），已与用户（车子）讨论定稿。
> 执行方：k2.7（长任务，**护栏内自主决策**）。
> 前置阅读：`PROJECT_HANDOVER.md` §3A（方向决议）、`规则书向量化规则.md`、`问题与修复记录.md` 001~004。
> 执行模式（用户定稿）：**一次性整包交付，不走 k3/k2.7 接力**。已诊断清楚的部分给精确指令；依赖现场数据的部分给原则+护栏，k2.7 自主决策；护栏外走逃生舱（§7）。

---

## 0. 分工、约束与自主权边界

- 本文档是**唯一执行依据**。Phase A→E 顺序执行，每个 Phase 独立验证、独立 `git commit`（Phase D 内部按"簇×模式"再分批 commit）。
- 在**新分支** `fix/profession-chunk-quality` 上工作（从 main 切出），完成后由用户验收合回 main。
- 只用 Python 3 标准库。`术语提取报告_分类版.md` 不可修改。
- 主脚本：`pf_data/phase1/vectorization_prep_profession.py`（3535 行，行号以 main HEAD `33d2e1f` 为准）。
- 工作目录 `pf_data/phase1/`，核心命令：
  ```bash
  python3 vectorization_prep_profession.py
  python3 verify_paladin_archetypes.py && python3 verify_heading_levels.py   # 回归
  ```

### 自主权边界（重要）

| 区域 | k2.7 权限 |
|---|---|
| Phase A（归属修复） | **按精确指令执行**，已实测诊断，不要自行发挥 |
| Phase B（格式普查） | 按 spec 执行；指纹维度可在此基础上**增补**（发现新特征就加列），不可减少 |
| Phase C（基线生成） | 按流程执行；基线内容（变体名↔来源书）由 k2.7 读源文件判定 |
| Phase D（归一化） | **护栏内自主**（§5.2 护栏 + §5.3 模式目录起点）；目录外的新模式可自行创立，但必须同时满足全部护栏 |
| 任何阶段 | 触发护栏红线 → **逃生舱**（§7）：记录、跳过、继续，绝不即兴突破 |

### 准确率标准（用户定稿，验收依据）

- 归属错误（职业/来源书）、变体漏识别/误识别：**100%**
- chunk 边界切分不精确：容忍，不投入精力
- 对不上的项逐个调查：chunk 错→修数据；基线错→改基线并在修复记录中写明理由（参照恩惠/神契先例，见 `问题与修复记录.md` 004）

## 0.1 背景数据（已实测，勿重复排查）

当前 chunks.jsonl（10495 chunks）中 `class_name=未知职业` 共 **1597 个**，分四组：

| 组 | 数量 | 处置 Phase |
|---|---|---|
| 职业子目录但归属失败（操念使 299/异能者 122/变形者 83/唤魂师 75/导魂者 18/吸血鬼猎人 5 等） | 609 | Phase A（CLASS_CONTAINERS 缺容器） |
| `进阶职业/`（路径是来源书非职业名） | 485 | Phase A（专属规则） |
| `神话冒险/`（根层 11 个文件与子目录逐字节相同） | 380 | Phase A（删重复+容器） |
| `职业/`根目录聚合文件+散页（标题无职业标记/URL 垃圾/介绍页） | 123 | Phase D（护栏内自主） |

归属机制现状（`infer_class_name`，脚本 716 行）：路径容器推断 → 任意路径部分匹配 → 标题`【X变体】`标记提取；`known_classes` 由 `discover_known_classes`（703 行）扫描 `CLASS_CONTAINERS`（106 行）子目录生成。

---

## Phase A：归属修复（Step 1~4，精确指令）

### Step 1 — 基线 tag + 分支

```bash
cd /Users/chezi/code/java/pf_agent
git tag pre-normalization-baseline main
git checkout -b fix/profession-chunk-quality
cd pf_data/phase1
# 留档对比基准（当前：total=10495，未知职业=1597）
python3 -c "
import json, collections
chunks = [json.loads(l) for l in open('vectorization_prep_profession/chunks.jsonl', encoding='utf-8')]
print('total:', len(chunks))
print('unknown:', sum(1 for c in chunks if c['class_name']=='未知职业'))
print(collections.Counter(c['class_name'] for c in chunks).most_common(10))
"
```

### Step 2 — 归属规则三处改动（仅限这三处）

**① CLASS_CONTAINERS 补 4 个容器**（106 行，数据改动）：

```python
CLASS_CONTAINERS = {
    "核心职业", "混合职业", "基础职业", "Unchained", "掉链子（Unchained）",
    # 2026-07-21 补充：以下容器此前缺失，导致操念使/异能者/唤魂师/变形者/导魂者等 609 个 chunk 归属失败
    "异能冒险（Occult Adventures）", "极限荒野（Ultimate Wilderness）", "其他职业", "神话冒险",
}
```

注意：`进阶职业`**不能**加入——它的下一级是来源书不是职业名。

**② 进阶职业专属规则**（用户定稿：进阶职业目录下的职业就是其本身，路径记录来源书）。在 `infer_class_name` 规则 1 之前插入：

```python
# 进阶职业：结构为 进阶职业/<来源书>/<进阶职业名>/... 或 进阶职业/<来源书>/page_xxx.md
if "进阶职业" in parts:
    idx = parts.index("进阶职业")
    # 第 3 层是目录 → 目录名即进阶职业名（如 进阶职业/CRB进阶职业/龙脉术士/...）
    if idx + 2 < len(parts) and not parts[idx + 2].endswith(".md"):
        return parts[idx + 2]
    # 直挂文件（含聚合文件）→ 用 chunk 标题的前导连续中文（如 间谍大师/贵族后裔）
    m = re.match(r"^[一-鿿]+", title or "")
    if m:
        return m.group(0)
    # 标题取不到 → 落到通用规则，允许 未知职业
```

**③ CONTAINER_SELF_ATTRIBUTION**（`神话冒险/格拉里昂的英雄HoG_神话异能.md` 是根层唯一保留文件，按"所处目录当职业名称"规则归 `神话冒险`）：

```python
CONTAINER_SELF_ATTRIBUTION = {"神话冒险"}
# 在 infer_class_name 规则 2 之后：
for container in CONTAINER_SELF_ATTRIBUTION:
    if container in parts:
        return container
```

**Step 2 快速验收**（不跑全量）：

```bash
python3 -c "
from pathlib import Path
import vectorization_prep_profession as v
kc = v.discover_known_classes(Path('pf_rules_md_organized/职业'))
for name in ['操念使', '异能者', '唤魂师', '变形者', '导魂者', '吸血鬼猎人', '圣者', '斗士']:
    assert name in kc, f'{name} 不在 known_classes'
for bad in ['APG进阶职业', 'CRB进阶职业', 'PoP进阶之路']:
    assert bad not in kc, f'{bad} 不应进入 known_classes'
print('known_classes OK, 总数:', len(kc))
"
```

### Step 3 — 删除神话冒险根层 11 个重复副本

以下 11 对文件已用 `cmp` 逐字节验证相同（**删除前必须重新验证一遍，任何一对不同 → 逃生舱，不删**）：

| 根层文件（删除） | 子目录正式副本（保留） |
|---|---|
| `神话冒险/page_610.md` | `神话冒险/基础神话能力/page_610.md` |
| `神话冒险/page_613.md` | `神话冒险/获取阶层/page_613.md` |
| `神话冒险/page_614.md` | `神话冒险/大法师/page_614.md` |
| `神话冒险/page_615.md` | `神话冒险/斗士/page_615.md` |
| `神话冒险/page_616.md` | `神话冒险/守护者/page_616.md` |
| `神话冒险/page_617.md` | `神话冒险/圣者/page_617.md` |
| `神话冒险/page_618.md` | `神话冒险/统帅/page_618.md` |
| `神话冒险/page_619.md` | `神话冒险/诡术大师/page_619.md` |
| `神话冒险/page_620.md` | `神话冒险/通用道途能力/page_620.md` |
| `神话冒险/凡人神使.md` | `神话冒险/凡人神使/凡人神使.md` |
| `神话冒险/神眷道途能力.md` | `神话冒险/神眷道途能力/神眷道途能力.md` |

保留 `神话冒险/格拉里昂的英雄HoG_神话异能.md`。`git rm` 删除，独立 commit。

验收：`ls pf_rules_md_organized/职业/神话冒险/*.md` 只剩 `格拉里昂的英雄HoG_神话异能.md`。

### Step 4 — 全量重跑 + 归属验收

新建 `verify_class_attribution.py`，断言以下**结构不变量**（含 negative test）：

1. `未知职业` chunk ≤ 150，逐条列出 doc_id + title 供人工过目（预期剩 ~124：根目录聚合文件 123 + 零星垃圾标题页，Phase D 处理）
2. 正向 spot check：`操念使/`下 299 个 chunk 全部归 `操念使`；异能者/唤魂师/变形者/导魂者同理；`进阶职业/APG进阶职业/page_145.md` → `间谍大师`；`进阶职业/PoP进阶之路/page_784.md` → `贵族后裔`；`进阶职业/CRB进阶职业/龙脉术士/` → `龙脉术士`；`神话冒险/圣者/page_617.md` → `圣者`；`神话冒险/斗士/page_615.md` → `斗士`
3. Negative：无任何 chunk 的 doc_id 等于被删 11 文件；无 class_name 是来源书名（`APG进阶职业`/`CRB进阶职业`/`PoP进阶之路`/`ISG内海诸神` 等）
4. 回归：`verify_paladin_archetypes.py` ALL PASSED、`verify_heading_levels.py` PASS
5. 输出 before/after 对照（total、未知职业数、class_name top 20），粘贴进 commit message

关于 chunk 总数：`chunk_id` 是内容 hash，内容相同的重复文件只产一份 chunk。删除后总数基本不变（预期主路径）或下降 ~370（若重复副本各自产出），两种都正常；骤降数千 → 逃生舱。

---

## Phase B：格式普查（Step 5，spec + 可增补）

### Step 5 — 新建 `census_profession_formats.py`（只读，不改任何数据）

对 `pf_rules_md_organized/职业/` 下全部 558 个 md 计算**结构指纹**，每文件至少包含：

| 维度 | 说明 |
|---|---|
| heading 统计 | `#`/`##`/`###` 数量；`##` 标题中带`【X变体】`/`（X变体）`/`［X变体］`/无标记 的各自数量 |
| 加粗标题 | 独占一行的 `^**...**$` 行数（疑似缺 `##` 的变体标题） |
| 噪声行 | URL 行（含 `http`）、`译者` 行、`返回目录` 行、行首图片 `![` 行、HTML 来源注释行 各自数量 |
| 表格 | 管道表格行数 |
| chunk 产出 | 该文件产出的 chunk 数、archetype 数、未知职业数（关联 chunks.jsonl） |

输出两个文件（gitignored 目录外，直接放 `pf_data/phase1/`）：

1. `职业目录格式簇报告.json`：per-file 指纹
2. `职业目录格式簇报告.md`：按指纹签名聚类，每簇列出——文件清单、文件数、特征摘要、chunk 质量估计（archetype 产出率、噪声行密度）、**疑似问题**（如"加粗标题多而 ## 少 → 疑似缺 ## 前缀"）

发现 spec 之外的新特征 → 增补指纹维度，并在报告里说明。

**验收**：报告覆盖 558/558 文件；至少能区分出"规范簇（## 带标记标题、无噪声）"与若干"问题簇"；报告末尾给出每簇的修复优先级建议（按 chunk 影响面排序）。

---

## Phase C：expected 基线生成（Step 6，流程 + 自主判定）

### Step 6 — 为每个职业生成 expected 变体清单

目标产物：`expected_variants/<职业名>.json`，格式同 `verify_paladin_archetypes.py` 的 EXPECTED 字典：

```json
{"变体规范名（前导中文）": "来源书缩写", ...}
```

流程：

1. 职业清单 = Phase A 后的 `known_classes`（含操念使等新发现职业；进阶职业、神话道途也各自生成）
2. 每个职业：读其主页面（`核心职业/<职业>/page_*.md` 或对应目录）中的变体列表/主表，结合脚本 `archetype_masters` 的既有解析结果，生成变体名 → 来源书映射
3. 基线内容由 k2.7 读源文件自主判定；**判不准来源书的条目标记 `"?"` 并在报告中列出**，不要猜
4. 输出 `expected_variants/生成报告.md`：每职业的变体数、来源书分布、与当前 chunks 的初步 diff（多出/缺失/来源不符），供用户抽查

**验收**：42+ 职业每个都有 json；报告中明确标注"高置信/待确认"清单；圣骑士 json 与 `verify_paladin_archetypes.py` 现有 41 项 expected 一致（如有出入，以圣骑士现有字典为准修正生成器）。

---

## Phase D：按簇归一化（Step 7，护栏内自主）

### Step 7 — 按普查报告逐簇修复源文件

按 Phase B 报告的优先级逐簇处理。**默认动作是改源文件的结构标记，不是改脚本**（决议 2）。

### 5.2 护栏（红线，全部必须同时满足）

1. **只改结构，不改内容**：允许的操作——补/改 `##` 前缀、补/规范`【XX变体】`标记、把 HTML 来源注释移到独立行、去行首图片前缀、删除纯噪声行（URL/译者/返回目录）。**禁止**改写规则描述文字、删改正文段落、翻译或重述内容
2. **每处修改可 diff 审查**：按"簇×模式"分批 commit，message 写明格式特征、涉及文件数、前后样例
3. **验收先行**：修某簇前，该簇涉及职业的 expected 基线（Phase C）必须已就位；修完 `verify` 该职业全 PASS 才提交
4. **脚本通用逻辑不动**：`vectorization_prep_profession.py` 在 Phase A 之后不再修改（发现新格式问题的默认动作是改源文件）；若判断"不改脚本无法解决"→ 逃生舱
5. **拿不准就走逃生舱**（§7）：内容歧义、需要规则知识判断（如"这到底是不是变体"）、压缩行/混行等结构性难题——记录、跳过、继续下一簇，绝不猜
6. **新模式归档**：创立目录外的新修复模式时，同步补进 `规则书向量化规则.md` 和 `问题与修复记录.md`（编号续 005+）

### 5.3 模式目录起点（从既有修复沉淀，可直接复用；可自主扩展）

| # | 模式 | 检测特征 | 修复 | 出处 |
|---|---|---|---|---|
| P1 | 变体标题缺 `##` 前缀 | 独占行 `**变体名**` 且上下文是变体章节 | 补 `## ` + 规范标记 | paladin dc06ffa/da9ce2a |
| P2 | 缺变体标记 | `## 变体名` 无`【X变体】`，路径职业唯一 | 补`【<路径职业>变体】` | paladin 37279cf |
| P3 | 行首图片吞标题 | `![...](...) **变体名**` | 去图片前缀 | 问题记录 001 |
| P4 | HTML 注释吞标题 | `<!-- source -->` 与标题同行 | 注释移到独立行 | 问题记录 002 修复节 |
| P5 | 噪声行 | URL/译者/返回目录 独占行 | 删除该行（仅限不损内容的纯噪声） | AG 聚合文件先例 |
| P6 | 根目录聚合文件无标记变体 | `职业/`根层聚合文件中无`【X变体】`的 `##` 标题 | **读正文判定所属职业**后补标记（如 绽放之光→牧师）；判定依据写进 commit/记录 | 本计划 §0.1 第四组 |
| P7 | CRB 介绍页误产 archetype | page_31/32/33/862 产出 `class_archetype` | 调整页面结构使介绍内容不被识别为变体（如标题规范化），保持内容完整 | 本计划 §0.1 第四组 |
| P8 | 压缩行/混行 | 一行内多标题/多段落粘连 | **逃生舱**（女巫案例证明需算法级处理，不在源文件修复范围） | 问题记录 002 |

### 5.4 验收（每簇）

- 该簇涉及职业的 expected verify 全 PASS（OK=X WRONG=0 MISSING=0）
- 负向检查：不该出现的 chunk 没出现（如 URL 标题、介绍页 archetype）
- 全量回归：paladin/heading/attribution 三个 verify 全 PASS

---

## Phase E：全量验收 + 最终报告（Step 8）

### Step 8 — 验收套件与交付

1. **通用化验收**：新建 `verify_all_classes.py`，加载 `expected_variants/*.json`，复用圣骑士的规范化变体名等值匹配逻辑（把`【圣骑士变体】`特化正则泛化为`【.*?变体】`），逐职业输出 OK/WRONG/MISSING。**严格 100%**：任何 WRONG/MISSING 逐项调查（chunk 错修数据、基线错改基线并记录理由），直到全 PASS 或触发逃生舱
2. 保留 `verify_paladin_archetypes.py` 不动（回归基线）
3. 全部 verify 脚本汇总跑通：`verify_class_attribution.py` + `verify_all_classes.py` + `verify_paladin_archetypes.py` + `verify_heading_levels.py`
4. **最终报告** `职业chunk质量攻坚报告.md`：
   - before/after 对照（10495/1597 基线 → 最终）
   - 各 Phase 修复清单（模式×文件数×commit 哈希）
   - 逃生舱清单（如有）：每个条目的现象、位置、为什么超出护栏、建议处理方向
   - 用户抽查包：expected 基线汇总表 + 抽样 chunk 对照（每职业抽 1 个变体的 chunk 与源文件并排）

---

## 7. 逃生舱协议

触发条件（任一）：① 需要改脚本通用逻辑才能解决；② 需要改写/删除正文内容；③ 需要规则知识判断归属或真伪（如"这是不是变体"无明确依据）；④ 修复可能引起跨文件连锁影响（如全局重命名）；⑤ Step 3 的 cmp 验证有任何一对不同。

动作：**不停整个包**——把该条目记入 `职业chunk质量攻坚报告.md` 逃生舱清单（现象/位置/原因/建议方向），跳过，继续后续工作。涉及逃生舱条目的职业/簇在 verify 中标记 `BLOCKED`（不是 PASS 也不是 FAIL），最终报告如实呈现。

## 8. 关键文件路径

- 主脚本：`pf_data/phase1/vectorization_prep_profession.py`（106 行 CLASS_CONTAINERS、703 行 discover_known_classes、716 行 infer_class_name）
- chunks 输出：`pf_data/phase1/vectorization_prep_profession/chunks.jsonl`
- 源文件根：`pf_data/phase1/pf_rules_md_organized/职业/`（558 个 md）
- 回归脚本：`verify_paladin_archetypes.py`、`verify_heading_levels.py`
- 规则文档：`规则书向量化规则.md`；问题归档：`问题与修复记录.md`
- 既有 expected 样例：`verify_paladin_archetypes.py` 的 EXPECTED 字典（41 项）
