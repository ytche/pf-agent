# Prepare Phase 执行交接

> 写给执行模型：这份文档告诉你当前状态和接下来要做什么。先读后做。

---

## 1. 你接手时项目处于什么状态

### 已完成的讨论

和用户完成了一轮设计讨论，确定了 **Prepare Phase** 的最终设计，已写入 `docs/VECTORIZER_ARCHITECTURE_DESIGN.md`（v1.5）。

### 背景

- 职业模块跑了 9 轮迭代（V001~V009），出了 5 个闭环 bug（001~005）和 5 个已知问题（KN001~005）
- 法术模块首次跑就出了 5 个问题（KN006~010）：UC/ARG/OA/UI 四个文件的格式变体完全漏掉
- 根因：写 `formats/spell.py` 时只看了 3~5 个典型文件，没看到全貌
- **Prepare Phase 就是为了解决这个根因而设计的**

### 关键文件位置

| 文件 | 用途 |
|------|------|
| `docs/VECTORIZER_ARCHITECTURE_DESIGN.md` | 终局架构设计，含 Prepare Phase 完整设计（§4.4） |
| `docs/WORKFLOW.md` | V/N 质量迭代工作流（Step 0~5） |
| `docs/问题与修复记录.md` | 职业模块 5 个闭环 bug（001~005） |
| `docs/已知问题记录.md` | KN001~KN010（5 个职业 + 5 个法术） |
| `vectorizer/` | 包骨架已部分搭建（sources/、formats/spell.py、tests/、verify/ 已有文件） |
| `pf_rules_md_organized/法术/` | 法术源数据：149 个 .md，~220 万字符 |

---

## 2. Prepare Phase 是什么

**一句话**：在写 formats 代码之前，LLM 先读一遍所有源文件，理解全貌，输出 4 个文件供后续阶段复用。

**只跑一次**，结果固定，不塞进 pipeline 热路径。后续 pipeline 反复跑直接读产出文件。

### 勘探维度（每文件回答 3 个问题）

| # | 问题 | 
|---|------|
| ① | 这个文件的条目用什么格式标记边界和字段？有什么异常标记（前缀/后缀/断裂/无包裹）？ |
| ② | 这个文件里有什么会让正则踩坑的点？有没有非条目内容用了同样的格式？ |
| ③ | 约多少条目？靠什么特征数的？首条目和末条目是什么？ |

### 产出物

```
vectorizer/exploration/法术/
├── 法术_per_file.jsonl       # 149 条记录，每条含 3 维度结果
├── 法术_format_clusters.md   # 格式变体聚类（如：管道表格 2文件、Bold标签 4文件、超紧凑内联 1文件...）
├── 法术_source_spec.md       # 哪些源文件需要先修改（列文件 + 问题 + 修改建议）
└── 法术_test_seeds.jsonl     # 测试用例种子（边界格式 → 正向用例，陷阱 → 负向用例）
```

---

## 3. 你需要做什么

### Step 1: Prepare Phase — 数据勘探

对 `pf_rules_md_organized/法术/` 下所有 149 个 .md 文件，**subagent 并发**逐文件做语义勘探。

**执行方式**：每个文件启动一个 subagent，读文件内容，按 3 维度输出结构化结果。并发执行。

**per_file.jsonl 每行格式**：

```json
{
  "file": "Spell UC.md",
  "format_fingerprint": {
    "title_pattern": "**中文（English）** 或 无加粗包裹的中文（English）",
    "field_layout": "Bold标签无冒号（**学派**值）",
    "anomalies": ["英文名空格断行 'Animal \\nAspect'", "英文名逗号断行 'Walk, \\nCommunal'"]
  },
  "traps": [
    "_fix_broken_english_names 的正则要求字母紧跟换行，但UC实际空格+换行",
    "部分法术无 ** 包裹，promote 阶段会漏掉"
  ],
  "estimated_count": 145,
  "count_method": "**环位标签出现次数",
  "first_entry": "超越之障 (Ablative Barrier)",
  "last_entry": "（末条目标题）"
}
```

**format_clusters.md 格式**：按格式指纹聚类后的 Markdown 表格，标注每种变体的文件数、代表文件、风险。

**source_spec.md 格式**：参考设计文档 §4.4 末尾的示例表格。列出需要改格式的文件 + 问题描述 + 修改建议。

**test_seeds.jsonl 每行格式**：

```json
{
  "source_file": "Spell ARG.md",
  "seed_type": "negative",
  "description": "法术名含 [种族] 后缀时不应被漏掉",
  "raw_snippet": "**隆地术 (Groundswell) [矮人]**",
  "expected_behavior": "正确识别为条目标题，提取 '隆地术' + 'Groundswell'"
}
```

### Step 2: 源文件规范化

按 `source_spec.md` 修改源文件（`pf_rules_md_organized/法术/` 下的 .md）。

### Step 3: TDD 循环

按这个流程循环直到通过：

```
读 format_clusters.md + test_seeds.jsonl
  → 写/改 formats/spell.py（补充缺失的格式处理）
  → 写/改 tests/ 下的测试用例
  → 跑测试
  → 修代码
  → 重复
```

### Step 4: 全量验证

```bash
cd /Users/chezi/code/java/pf_agent/pf_data/phase1
python3 -m vectorizer.pipeline --category spell
python3 vectorizer/verify/verify_spells.py
```

---

## 4. 约束与注意事项

- **类目无关原则**：代码和文档中不要出现法术特有的硬编码。用"条目"而非"法术"，用"条目标题"而非"法术名"。
- **不修改设计文档**：`VECTORIZER_ARCHITECTURE_DESIGN.md` 只读。有架构层面的问题记录到 `已知问题记录.md`。
- **每个 Step 完成后提交 Git**。
- **源数据（pf_rules_md_organized/）是可修改的**——改格式缺陷，不改内容。
- **用户是中文用户**，所有文档和注释用中文。
- **TDD 优先**：先写测试，再写实现。已有 `vectorizer/tests/conftest.py` 和 7 个测试文件可以作为模板参考。
- **已有点数据**：法术模块的已知问题记录在 `docs/已知问题记录.md` KN006~KN010，5 个问题都是格式解析缺陷导致提取数远低于预期。
