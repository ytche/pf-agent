# 交接文档：职业向量化文件级封装 + 女巫补充书修复(交给 k2.7 执行)

> 交接目标：由 k2.7 按本文档执行三个 Step 的修复与轻重构。
> 设计方：Claude Code(k3,2026-07-20)，已与用户(车子)讨论定稿。
> 执行方：k2.7(长任务)。
> 前置阅读：`HANDOVER_KIMI_K3_WITCH_DESIGN.md`(上一棒交接,其中"当前输出 1 个 class_overview"的描述已过时，以本文档根因分析为准)。

---

## 0. 分工与约束

- 本文档是**唯一执行依据**；三个 Step 顺序执行，每步独立验证、独立 `git commit`。
- 源 Markdown 文件**不可修改**；`术语提取报告_分类版.md` **不可修改**；只用 Python 3 标准库。
- 主脚本：`/Users/chezi/code/java/pf_agent/pf_data/phase1/vectorization_prep_profession.py`(2055 行，以下行号以脚本当前版本为准——代码 HEAD `c5b84fd`，其后的 `c814f89` 仅为文档提交，行号不受影响)。
- 运行/验证命令（工作目录 `pf_data/phase1/`):
  ```bash
  python3 vectorization_prep_profession.py
  ```

---

## 1. 根因分析(已实测验证，勿重复排查)

### 1.1 现象比上一棒交接文档描述的更严重

`皇庭英豪HotHC_庇护主.md` 和 `格拉里昂的纯洁勇士_女巫庇护主与巫术.md` 在当前输出中**零 chunk**（不是"1 个 class_overview"):

```bash
# 验证:以下查询无结果
python3 -c "
import json
for line in open('vectorization_prep_profession/chunks.jsonl', encoding='utf-8'):
    c = json.loads(line)
    if '保护生命' in c['text'] or 'Boundaries' in c['text']:
        print(c['doc_id'])
"
```

### 1.2 根因①:`merge_line_breaks` 把正文胶水到 `>` 引用行

`merge_line_breaks`(行 583）的合并条件是"前行无句末标点则拼接后行"。两个补充文件的 `> 来源:...` 引用行无句末标点，于是**后续全部正文被拼到该引用行上**，整行以 `>` 开头；随后 `is_pure_table_or_nav`(行 1547）判定为纯引用/导航 → 在过滤处（行 1811-1813）被丢弃。

实测证据（HotHC):清洗后全文胶水成 1 行 298 字符：
```
> 来源：皇庭英豪（Heroes of the High Court）...女巫庇护主保护：这个庇护主希望...2nd—圣域术（sanctuary）4th—...
```

### 1.3 根因②:压缩行无拆分逻辑，且纯正则无法解决

即使不被过滤，CoP 的整行压缩文本（`女巫庇护主****边界（Boundaries）：2级——...`）也没有拆分逻辑。stash@{0} 的 `split_concatenated_headings` 方向正确但有三处致命伤，**不要直接复用**:
1. 全局启用，误拆基础页 `**巫术（Hex）**` 等独立章节标题，导致 26 个 patron 丢失；
2. 跳过 `>` 开头的行——与根因①叠加后，目标行正好是 `>` 开头，必然失效；
3. patron 名边界歧义无解：`18级——异界之门奉献（Devotion）：` 中"异界之门"是上一级的法术名，"奉献"才是庇护主名，纯正则无法切分。

### 1.4 已实测无问题的部分（勿再花时间）

- 来源书识别：HotHC→`HOTHC`、`格拉里昂的纯洁勇士_...`→`COP`（经 `纯善勇士` 别名命中），均已用 `detect_book` 实测。
- 全书仅这 2 个文件名含"庇护主",`_doc_feature_subtype_hint` 对两者都返回 `patron`。
- 基础页 page_92.md 的 26 个 patron(APG 12 + UM 14）完全正确，不许动基础页相关逻辑。

### 1.5 当前基线（验收对比基准，已实测）

| 指标（class_name == '女巫') | 基线 |
|---|---|
| class_feature / class_archetype / class_overview | 209 / 25 / 19（共 253) |
| hex / major_hex / grand_hex | 37 / 20 / 9 |
| patron | 26(APG 12 + UM 14) |

---

## 2. Step 1 — 文件级薄封装（行为零 diff)

**目的**：给 Step 3 提供挂载点，并把职业特有逻辑收拢出主流程。**不改变任何行为**。

### 2.1 改动内容

1. 新增 `FileProcessor` 基类，模板方法 `run()` 串起以下钩子，默认全部**委托现有模块级函数**，不搬逻辑：
   ```python
   class FileProcessor:
       def __init__(self, file_path, rel_path, ctx): ...   # ctx 打包 book_lookup/md_mapping/known_classes/archetype_masters/deprecated_titles/doc_subtype_hint 等
       def clean(self, lines):   ...   # 默认 = 现有 clean_file 的函数链
       def split(self, lines):   ...   # 默认 = split_into_blocks
       def expand(self, blocks): ...   # 默认 = 现有庇护主奖励表拆分(见下)
       def merge(self, blocks):  ...   # 默认 = merge_small_blocks
       def build(self, block):   ...   # 默认 = build_chunk
       def keep(self, chunk):    ...   # 默认 = 现有短块/纯导航过滤(行 1800-1813)
       def run(self) -> List[Chunk]: ...
   ```
2. `process_profession_corpus`(行 1700）主循环改为：
   ```python
   for file_path in canonical_files:
       processor = create_processor(rel_path, ctx)   # 工厂,Step 1 恒返回 FileProcessor
       chunks.extend(processor.run())
   ```
3. 职业特有逻辑收拢为"职业域"（为将来类目层预留边界，物理上可留在同文件，但归属要清晰）:`classify_component`、`infer_feature_subtype`、`_doc_feature_subtype_hint`、`build_class_index`、`_split_patron_reward_tables`。主流程 1770-1782 行硬编码的"庇护主奖励表拆分"移入 `FileProcessor.expand` 的默认实现。
4. `Chunk`(行 124）增加 `extra: Dict[str, Any] = field(default_factory=dict)`——为将来法术/专长元数据预留，现在加零成本。

### 2.2 验收

```bash
cp vectorization_prep_profession/chunks.jsonl /tmp/chunks_before.jsonl   # 改之前先备份 HEAD 输出
python3 vectorization_prep_profession.py
diff <(sort /tmp/chunks_before.jsonl) <(sort vectorization_prep_profession/chunks.jsonl) && echo "ZERO DIFF OK"
```
必须**零 diff**(chunk_id 含文本哈希，任何行为变化都会暴露）。注意：若备份的基线不是 HEAD 重新生成的，先 `git stash` 后重跑一遍再备份。提交：`refactor(profession): 文件级 FileProcessor 薄封装,行为零 diff`。

---

## 3. Step 2 — 全局修 `merge_line_breaks` 的 `>` 行胶水 bug

### 3.1 改动内容

规则：`>` 开头的引用行作为**段落硬边界**——后续行不得拼接到引用行上（引用行自身仍可与前序普通行按现有规则合并，保持改动最小）。

### 3.2 验收

1. 全量回归对比 Step 1 输出：变化的 chunk 应**全部**是原先被胶水的引用行场景。
2. 42 个职业 chunk 总数无异常下降（允许因正确拆分而增加）。
3. HotHC/CoP 从零 chunk 变为有 chunk（此时 patron 仍未拆对，Step 3 解决）。

提交：`fix(vectorization): 引用行不再吸收后续正文(> 行作为段落硬边界)`。

---

## 4. Step 3 — WitchProcessor + 条目表驱动的补充书改写器

### 4.1 设计核心（已与用户定稿，勿改方向）

**特例处理器 = 文本改写器**：把不规则文本改写成通用管线认识的规整 Markdown(`## 章节` + `### 条目` + 正文），改写后回到标准清洗链，下游零改动。

**策略模式的分发点保留（注册表），策略默认参数化为数据**：HotHC/CoP 算法相同（定位锚点→切分→发射 Markdown)，只有锚点清单不同，故不做每书策略类。注册表 value 类型：
```python
StructureHandler = Union[SupplementSpec, Callable[[List[str]], List[str]]]
# 默认:数据(通用切分器处理)   例外:函数("算法本身不同"时的逃生舱)
```

### 4.2 改动内容

1. 新增 `WitchProcessor(FileProcessor)`；工厂 `create_processor` 仅在 `rel_path` 命中 `基础职业/女巫` 且文件名含 `庇护主` 时返回它（精确覆盖 2 个文件；基础页 page_92.md 走默认流程）。
2. `WitchProcessor.clean()`：`rel_path` 命中 `SUPPLEMENT_STRUCTURE_REGISTRY` 时，先跑基类清洗链的噪音过滤/跨行粗体合并/换行合并，再调 `structure_supplement(lines, spec)` 改写，最后继续标准标题提升链。
3. **通用定位切分器 `structure_supplement`（只写一次）**:
   - 按 Entry 的 CN/EN 名归一化后定位锚点（容忍嵌套 `**`、空格、` , ` 与 `, ` 差异、全半角）;
   - 定位 `spec.sections` 章节关键词（如 `女巫庇护主****`、`强力巫术（Major Hexes） ****`);
   - 全部锚点按位置排序切分，每段 = 条目名 + 到下一锚点前的正文；
   - 发射标准 Markdown：章节 → `## <章节名>`；条目 → `### <中文名>（<English>, <tag>）`（patron 无 tag)。**英文名必须补上**——`classify_component` 判 `class_feature` 需要英文名/ExSuSp 信号，纯中文标题会误判为 `class_overview`;
   - 正文中在 `N级——` / `Nth—` / `Nnd—` / `Nrd—` / `Nst—` 前补换行，奖励法术列表每行一个。
4. **两道运行时校验**（替代"信任 Agent 录入"):
   - 条目表中任何条目定位失败 → **报错**并保留原文，不静默跳过；
   - 文本中发现形似 `中文（English, Su）` / `中文（English）：` 但**未登记**在条目表中的疑似标题 → 输出**警告**，防漏登记。

### 4.3 条目表（已逐项对照源文件核对，照抄并再验证一遍）

```python
SUPPLEMENT_STRUCTURE_REGISTRY = {
    "基础职业/女巫/皇庭英豪HotHC_庇护主.md": SupplementSpec(
        sections=["庇护主"],
        entries=[
            Entry("保护", "Protection", "patron"),
        ],
    ),
    "基础职业/女巫/格拉里昂的纯洁勇士_女巫庇护主与巫术.md": SupplementSpec(
        sections=["女巫庇护主", "女巫巫术", "强力巫术", "高等巫术"],
        entries=[
            Entry("边界",      "Boundaries",            "patron"),
            Entry("奉献",      "Devotion",              "patron"),
            Entry("和平",      "Peace",                 "patron"),
            Entry("净化灵光",  "Aura of Purity",        "hex",       tag="Su"),
            Entry("和平之绊",  "Peace Bond",            "hex",       tag="Su"),
            Entry("女巫的赠礼", "Witch's Bounty",       "major_hex", tag="Su"),
            Entry("女巫的眷顾", "Witch's Charge",       "major_hex", tag="Su"),
            Entry("非暴力诅咒", "Curse of Nonviolence", "grand_hex", tag="Su"),
            Entry("安息",      "Lay to Rest",           "grand_hex", tag="Sp"),
        ],
    ),
}
```

注意:
- CoP 源文本中英文名有噪音(`Peace bond` 小写 b、`Witch’s` 弯引号、` , SU` 空格),定位匹配要归一化,发射标题时用条目表里的规范写法。
- **HotHC `保护` 的英文名 `Protection` 是设计方推断**:源文件未给出英文名,推断依据是其奖励法术列表(圣域术→抵抗能量→…→解锢术)与 Protection 庇护主一致;且基础页现有 26 个 patron 中无"保护/Protection"(已核实,见 §1.5)。k2.7 实施时应再验证一次(如对照原书或 d20pfsrd 的 HotHC witch patron 列表),若英文名有误只改条目表数据,不改代码。

### 4.4 验收

```bash
python3 vectorization_prep_profession.py
python3 -c "
import json
from collections import Counter
sub = Counter(); books = Counter(); comp = Counter()
for line in open('vectorization_prep_profession/chunks.jsonl', encoding='utf-8'):
    c = json.loads(line)
    if c['class_name'] == '女巫':
        comp[c['component_type']] += 1
        if c['feature_subtype']: sub[c['feature_subtype']] += 1
        if c['feature_subtype'] == 'patron': books[c['book_abbreviation']] += 1
print('component:', dict(comp)); print('subtype:', dict(sub)); print('patron books:', dict(books))
"
```

| 检查项 | 目标 |
|---|---|
| patron 总数 | **30**(APG 12 + UM 14 + HOTHC 1 + COP 3) |
| hex / major_hex / grand_hex | ≥ 37 / 20 / 9(CoP 新增 2 hex + 2 major + 2 grand，即 39 / 22 / 11) |
| HotHC patron | 1 个，标题 `保护（Protection）`，来源 HOTHC |
| CoP patron | 3 个（边界/奉献/和平），来源 COP |
| 其他职业 chunk 数 | 与 Step 2 基线相比无明显下降 |

抽样验收（"先理解后向量化"规则）：人工核对 4 个新 patron chunk 的标题/正文/来源书，核对 CoP 6 个巫术 chunk 的 subtype 与正文完整性。

提交：`fix(witch): 条目表驱动改写器拆分 HotHC/CoP 庇护主与巫术`。

---

## 5. 下一步抽象设计（供用户与 k3 后续讨论,k2.7 不实施)

- 终局两层抽象：`CategoryPipeline`（类目层：组件类型体系/classify/索引/subtype 词表）+ `FileProcessor`（文件层，Step 1 已落地）。
- **类目层推迟到接入第二个类目（法术）时再做**：单一样本的抽象边界靠猜；法术是列表型文档，与职业的层级章节型差异大，两个真实样本提取共性更可靠。
- 已预留：`Chunk.extra`、职业域函数边界（Step 1 收拢的清单即未来 CategoryPipeline 子类职责）、特例注册表（`SUPPLEMENT_STRUCTURE_REGISTRY` 将来升级为类目级分发点）。
- 待设计问题：法术类目组件类型（spell/spell_list)、法术元数据（school/level/descriptor）入 extra、类目索引形态、类目注册表入口（`CATEGORY_PIPELINES` 雏形）。

---

## 6. 关键文件路径

- 主脚本：`pf_data/phase1/vectorization_prep_profession.py`
- 规则文档：`pf_data/phase1/规则书向量化规则.md`（修改行为后同步更新）
- 女巫基础页：`pf_data/phase1/pf_rules_md_organized/职业/基础职业/女巫/page_92.md`
- HotHC 补充：`pf_data/phase1/pf_rules_md_organized/职业/基础职业/女巫/皇庭英豪HotHC_庇护主.md`
- CoP 补充：`pf_data/phase1/pf_rules_md_organized/职业/基础职业/女巫/格拉里昂的纯洁勇士_女巫庇护主与巫术.md`
- 输出目录：`pf_data/phase1/vectorization_prep_profession/`(gitignored)
- stash@{0}:`split_concatenated_headings` 失败实验，仅可参考思路，勿直接 pop 复用

---

*文档版本：v1.0 · 2026-07-20 · k3 设计，k2.7 执行*
