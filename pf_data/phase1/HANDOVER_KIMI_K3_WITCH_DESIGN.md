# 针对大模型的交接文档：女巫向量化设计与当前状态

> 交接目标：由 kimi-k3 负责完成女巫向量化部分的模块化设计/实现。
> 当前会话模型：Claude Code（已整理现状，停止代码修改，等待设计交接）。
> 时间：2026-07-20

---

## 1. 项目整体进度

- **一期术语表 Phase 1~3**：已完成。
  - 输出：`pf_data/phase1/术语提取报告_优化版.md`（1075 术语，15 分类）与 `terms.json`。
  - 自动化验收：`verify_phase3.py` 全部通过。
- **未整理规则书归档**：已完成。
  - `pf_data/phase1/pf_rules_md/未整理/` 下 145 本 L2 规则书已归档到 `pf_rules_md_organized/`。
- **规则书向量化（一期核心）**：进行中。
  - 主脚本：`pf_data/phase1/vectorization_prep_profession.py`。
  - 输入：`pf_data/phase1/pf_rules_md_organized/职业`。
  - 输出：`pf_data/phase1/vectorization_prep_profession/`（gitignored）。
  - 规则文档：`pf_data/phase1/规则书向量化规则.md`。

---

## 2. 女巫向量化当前状态

### 2.1 已验证的正确输出（HEAD: `b9f30c3`）

运行 `python3 vectorization_prep_profession.py` 后，女巫（`class_name == '女巫'`）chunk 统计：

| 组件类型 | 数量 | 说明 |
|---|---|---|
| `class_feature` | 209 | 职业能力/天赋 |
| `class_archetype` | 25 | 职业变体 |
| `class_overview` | 19 | 职业概览 |
| **合计** | **253** | |

按 `feature_subtype`：

| subtype | 数量 | 来源 |
|---|---|---|
| `hex` | 37 | 基础页 + 补充书 |
| `patron` | **26** | 仅来自 `page_92.md` |
| `major_hex` | 20 | 基础页 + 补充书 |
| `grand_hex` | 9 | 基础页 + 补充书 |
| 无 | 161 | |

26 个庇护主来源书分布正确：APG 12 个 + UM 14 个。

### 2.2 仍然缺失的问题

**两本补充规则书的庇护主没有被识别为 `feature_subtype='patron'`，而是被吞进了 `class_overview` chunk。**

| 文件 | 当前输出 | 预期 |
|---|---|---|
| `pf_rules_md_organized/职业/基础职业/女巫/皇庭英豪HotHC_庇护主.md` | 1 个 `class_overview` chunk，无 subtype | 1 个 `patron` chunk |
| `pf_rules_md_organized/职业/基础职业/女巫/格拉里昂的纯洁勇士_女巫庇护主与巫术.md` | 1 个 `class_overview` chunk，无 subtype | 3 个 `patron` chunk + 若干 hex |

### 2.3 问题根因

1. **补充文件把内容压成了一整行**：
   - HotHC：`**庇护主**保护：这个庇护主希望...2nd—圣域术...18th—解锢术`
   - CoP：`女巫庇护主边界（Boundaries）：2级——...奉献（Devotion）：...和平（Peace）：...女巫巫术...`
2. HEAD 脚本没有处理这种“单行多标题压缩”的逻辑。
3. `_split_patron_reward_tables` 只认识 `XX庇护主奖励法术` 这种基础页表格头，不认识补充书的 `边界（Boundaries）：` 这种格式。

---

## 3. 已尝试过的修改与现状

### 3.1 已 stash 的实验性修改

当前 Git stash 中有一份 `vectorization_prep_profession.py` 的实验代码：

```text
stash@{0}: On main: WIP: 保护独立章节标题，避免巫术(Hex)等被误拆分
```

这份修改：
- 新增了 `split_concatenated_headings()` 函数，试图把补充书的压缩行拆成独立标题；
- **副作用**：把基础页 `**巫术（Hex）**` 这类独立章节标题也误拆了，导致基础页 26 个庇护主丢失；
- **结论**：方向可行，但实现没保护好基础页，已被回退并 stash。

### 3.2 当前工作区

- `vectorization_prep_profession.py` 已恢复到 `b9f30c3`（HEAD）。
- 全局 `CLAUDE.md` 已新增一条规则：回退前先用 `git stash` 保存未提交修改。

---

## 4. 推荐设计方案

### 4.1 核心思路

**停止在统一大方法里堆特判，改为“基类 + 女巫子类 + 特殊规则书补充处理器”。**

理由：
- 女巫基础页已经正确，不需要大改；
- 只有 HotHC / CoP 两本补充书格式特殊；
- 其他职业暂时 unaffected，走默认流程即可；
- 后续新增职业/主题时，只需要新增子类或补充方法。

### 4.2 推荐架构

```text
vectorization_prep_profession.py
├── BaseProfessionProcessor
│   ├── load(file_path) -> raw_lines
│   ├── clean(raw_lines) -> cleaned_lines
│   ├── split(cleaned_lines) -> blocks
│   ├── expand_blocks(blocks) -> blocks       # 子类覆盖点
│   ├── merge(blocks) -> blocks
│   ├── filter(chunks) -> chunks
│   └── output(chunks) -> files
│
├── WitchProfessionProcessor(BaseProfessionProcessor)
│   ├── clean()              # 基类清洗 + 压缩行拆分（保护好基础页标题）
│   ├── expand_blocks()      # 庇护主奖励法术拆分 + 补充文件拆分
│   ├── _split_hothc_patron_block(block) -> [block]
│   ├── _split_cop_patron_block(block) -> [block]
│   └── _split_concatenated_headings(lines) -> lines   # 可复用或保留为函数
│
├── ProfessionProcessorFactory
│   └── create(rel_path) -> BaseProfessionProcessor
│
└── process_profession_corpus()
    └── for each file:
        processor = factory.create(rel_path)
        processor.run()
```

### 4.3 关键实现要点

1. **`split_concatenated_headings` 的保护逻辑**
   - 必须识别并保护独立章节标题，例如 `**巫术（Hex）**`、`**强力巫术（Major Hex）**`、`**庇护主（Patron）**`。
   - 只有在“章节关键词 + 后续具体能力/庇护主”的压缩行场景下才拆分。
   - 参考 stash 中的实现思路，但修正基础页标题保护。

2. **补充文件拆分**
   - **HotHC 庇护主**：识别 `**庇护主**保护：...` 结构，把 `保护` 作为庇护主名，后续表格行作为奖励法术。
   - **CoP 庇护主**：识别 `边界（Boundaries）：2级——...` 这种段落，按庇护主名切分为独立块。
   - **CoP 巫术**：同文件内还有 `净化灵光（Aura of Purity, Su）` 等 hex，需要正确标记 `feature_subtype='hex'`。

3. **来源书**
   - HotHC → `HOTHC`
   - CoP（纯洁勇士）→ `COP`
   - 优先从文件名/正文 `来源：xxx` 识别，避免被职业默认 `APG` 覆盖。

4. **不要影响其他职业**
   - 默认 processor 保持当前 HEAD 行为；
   - 只有 `rel_path` 匹配女巫相关文件时才启用 `WitchProfessionProcessor`。

### 4.4 验收标准

运行脚本后，女巫 chunk 应满足：

| 检查项 | 目标 |
|---|---|
| 总 patron chunk 数 | **30** = 基础页 26 + HotHC 1 + CoP 3 |
| 基础 patron 来源书 | APG 12 + UM 14 |
| HotHC patron | 1 个，来源 `HOTHC`，`feature_subtype='patron'` |
| CoP patron | 3 个（Boundaries/Devotion/Peace），来源 `COP`，`feature_subtype='patron'` |
| hex / major_hex / grand_hex 数量 | 不减少 |
| 其他职业 chunk 总数 | 与 HEAD 相比无明显下降 |

---

## 5. 关键文件路径

- 主脚本：`/Users/chezi/code/java/pf_agent/pf_data/phase1/vectorization_prep_profession.py`
- 规则文档：`/Users/chezi/code/java/pf_agent/pf_data/phase1/规则书向量化规则.md`
- 女巫基础页：`/Users/chezi/code/java/pf_agent/pf_data/phase1/pf_rules_md_organized/职业/基础职业/女巫/page_92.md`
- HotHC 庇护主补充：`/Users/chezi/code/java/pf_agent/pf_data/phase1/pf_rules_md_organized/职业/基础职业/女巫/皇庭英豪HotHC_庇护主.md`
- CoP 庇护主/巫术补充：`/Users/chezi/code/java/pf_agent/pf_data/phase1/pf_rules_md_organized/职业/基础职业/女巫/格拉里昂的纯洁勇士_女巫庇护主与巫术.md`
- 输出目录：`/Users/chezi/code/java/pf_agent/pf_data/phase1/vectorization_prep_profession/`
- 项目交接文档：`/Users/chezi/code/java/pf_agent/PROJECT_HANDOVER.md`

---

## 6. 下一步行动建议

1. **kimi-k3 接手后**：先阅读本交接文档和 `规则书向量化规则.md`，再查看上述三个女巫源文件。
2. **设计方案**：确定 `BaseProfessionProcessor` 的接口边界，以及 `WitchProfessionProcessor` 的具体实现。
3. **小步实现**：先实现补充文件拆分并验证 patron 数量达到 30，再考虑是否抽基类。
4. **验证**：每次修改后运行 `vectorization_prep_profession.py` 并检查女巫 patron / hex / 变体数量。
5. **提交**：达到验收标准后 `git commit`，并更新本交接文档或 `PROJECT_HANDOVER.md`。

---

## 7. 约束与注意事项

- `pf_data/phase1/术语提取报告_分类版.md` **不可修改**。
- 源 Markdown 文件 **不可修改**，所有清洗逻辑必须在脚本中完成。
- 优先使用原生 Python 3 标准库，避免新增依赖。
- 修改后必须跑对应验证（目前无单元测试，以脚本输出统计为准）。
- 每个阶段性节点都要 `git commit`。
