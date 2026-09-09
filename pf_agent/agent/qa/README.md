# PF 1e 规则问答 Agent 回答质量评测集（59 题）

由 dnd5e-srd-qa（HuggingFace `datapizza-ai-lab/dnd5e-srd-qa`，56 题 RAG 评测集）迁移
并追加 SP3 职业法术列表列举题 3 题（medium-31~33）而成的
**Pathfinder 1e 版回答质量评测集**。目的：量化验证 PF 规则问答 Agent 的检索与回答质量，
支撑一期联调（各模块检索端降权项、book '?' 口径等）。

## 交付物

| 文件 | 内容 |
|---|---|
| `pf_qa_items.json` | 59 题问题集（问题/维度/迁移动作/溯源锚点/关键事实点框架；56 迁移 + 3 SP3 新增） |
| `迁移难点_5e无法映射.md` | 无法映射题（X 题 + 勉强 R 题）的问题/原因/解决方案 |
| `evaluate.py` | 评测脚本（A 批规则化三维度 + B 批 LLM-as-judge 接口） |
| `README.md` | 本文件 |

## 评测集结构

### Schema（`pf_qa_items.json`）

```json
{
  "version": "1.0",
  "source": "dnd5e-srd-qa (datapizza-ai-lab) 56 题迁移 + SP3 F-007 新增 3 题职业法术列表列举题",
  "items": [
    {
      "id": "easy-0",
      "tier": "easy | medium",
      "dimension": "比较对比 | 事实点查 | 应用计算 | 全量枚举 | 数值最优解 | 交叉判定",
      "status": "D | R | X",            // D=直接迁移 R=等价替换 X=放弃（不进评测集）
      "source_question": "原 dnd5e 英文题（溯源）",
      "question": "PF 1e 问题（中文）",
      "module": "spell,class,feat,...", // 逗号分隔，对应向量库模块
      "expected_chunks": ["chunk_id 或 tocPath 锚点"],
      "golden_answer_points": ["关键事实点1", "..."],
      "answer": "",                     // 第二阶段 golden answer 填此
      "notes": "迁移说明/难度标注"
    }
  ]
}
```

### 当前统计（v1.0）

- **总数**：59（easy 25 + medium 34）
- **迁移动作**：D=30、R=23、X=6
  - 其中 medium-31~33 为 SP3 F-007 新增（全量枚举 / 职业法术列表列举，均 D），锚定官方职业
    法术列表页 tocPath，预期 Agent 走 `getSpellList` @Tool 直查。
- **六维度分布**：比较对比=10、事实点查=20、全量枚举=5、应用计算=7、交叉判定=7、数值最优解=7
- X 题（6）：easy-0、easy-20、medium-6、medium-16、medium-28、medium-30——全部进 `迁移难点_5e无法映射.md`

## 如何运行评测

### 前置：启动 Agent

```bash
cd /Users/chezi/code/java/pf_agent/pf_agent/agent
mvn spring-boot:run   # 需 DeepSeek key + 本地 Ollama bge-m3 + 8 向量库
```

### 评测命令

```bash
cd /Users/chezi/code/java/pf_agent/pf_agent/agent/qa

# 全量评测（A 批三维度；B 批跳过并标注「待 golden answer」）
python3 evaluate.py

# 抽样观察
python3 evaluate.py --sample 5

# 指定 base-url / 输出目录
python3 evaluate.py --base-url http://localhost:8080 --report-dir ./out

# 启用 B 批 LLM-as-judge（需 DEEPSEEK_API_KEY；golden_answer_points 非空才判）
DEEPSEEK_API_KEY=sk-xxx python3 evaluate.py --judge

# 只测 gap 题（expected_chunks 为空、预期报缺口的题）
python3 evaluate.py --gap-only
```

参数：`--timeout`（单题 API 超时，默认 120s）、`--delay`（题间延迟，默认 1s，限流保护）。

### 输出

- `qa_report.json`——每题 5 维度得分 + 总分 + 明细
- `qa_report.md`——汇总表（按维度/按模块聚合）+ 每题明细（问题/回答/来源/judge 理由）

## 判分规则（五维度，分两批）

### A 批 · 规则化（无需 golden answer，开箱即用）

| 维度 | 得分 | 规则 |
|---|---|---|
| 溯源正确性 | 0/1 | `sources[].tocPath/book` 命中 `expected_chunks`（相等 / 前缀 / book 缩写） |
| 拒绝诚实性 | 0/1 | 正常题断言 `gapReported==false` 且 sources 非空；gap 题断言 `gapReported==true` 且 answer 含诚实短语（未检索到/无法回答等） |
| 回答结构 | 0~3 | 非空结构化文本 +1；Markdown（标题/列表/表格）+1；带来源引用 +1 |

### B 批 · LLM-as-judge（第二阶段启用，`golden_answer_points` 完成后）

| 维度 | 得分 | 规则 |
|---|---|---|
| 事实准确性 | 0~2 | DeepSeek 按 golden_answer_points 判关键事实是否正确覆盖 |
| 完整性 | 0~2 | 覆盖了多少个 golden_answer_points |

B 批接口已留好：`judge_llm()` 调 DeepSeek chat API（`temperature=0` + `response_format=json_object`），
`golden_answer_points` 为空时跳过并标注「待 golden answer」。

## 错误标注闭环（线上问题收集）

用户提问时发现错误回答，可在问答页点击「⚠️ 标错」提交标注，驱动 prompt/检索/数据迭代：

- **前端**：回答下方「标错」按钮 → 选错误类型（事实错误/检索漏召回/编造来源/答非所问/结构差）+ 修正 + 备注 → `POST /api/chat/feedback`
- **后端**：`FeedbackRecorder` 追加写入 `${user.home}/.pf_agent/annotations.jsonl`（含 question/answer/sources **回答快照**，可精确复现错误现场；对齐 data_gaps 模式）
- **分析**：

  ```bash
  cd /Users/chezi/code/java/pf_agent/pf_agent/agent/qa
  python3 annotations_report.py                                      # 读 ~/.pf_agent/annotations.jsonl
  python3 annotations_report.py --file /path/annotations.jsonl --out ./out
  ```

  输出 `annotations_report.md`：errorType 聚类分布 + 被标错来源 Top（问题 chunk）+ 逐类优化建议（指向 prompt/检索/数据）。

与评测集互补：`evaluate.py` 离线批量测（59 题中 status∈{D,R} 的 53 活跃题，X 题不进评测）；标注是线上真实错误收集。两者合并进同一「准确率优化」口径。

## 与 dnd5e 对照

- **id 映射**：dnd5e easy 0-24 → `easy-N`；medium 0-30 → `medium-N`（按原数据集数组顺序一一对应）。
- **SP3 追加**：medium-31~33 无 dnd5e 原题，为 F-007 职业法术列表列举验证题（source_question 为空）。
- **迁移原则**：实体可换，维度不变。考察的认知维度（比较/点查/计算/枚举/最值/交叉）与原题一致，
  实体替换为 PF 有语料支撑的对应物（如 5e 术士/法师 → PF 术士自发施法/法师准备施法）。
- **无法映射**的题（怪物 stat block 缺失、短休机制、Adv/Disadv、统一施法位表、子职结构）见
  `迁移难点_5e无法映射.md`，原因/方案/待人工优化点逐题记录。

## 已知边界（诚实标注）

- `expected_chunks` 以 **chunk_id（全量哈希）或 tocPath 锚点**两种形式给出：
  - 职业模块（`vectorization_prep_profession/chunks.jsonl`）无 chm_toc_path，用 chunk_id 全哈希；
  - 其余模块用 `tocPath` 前缀锚（如 `spell_Spell CRB_0414`），判分时做前缀匹配。
- 装备模块单件护甲/盾牌 AC 数值 stat block 截断未入库 → medium-13/19 的 golden points 不依赖裸数字。
- 部分题的核心数值来自**标准 PF 规则**（如升级每 4 级 +1 属性）而非语料 chunk，已在 notes 标注。
- 自审时移除了依赖「未整理」目录 / book='?' 的锚点（medium-1 神裔变体、medium-21 水栖精灵免疫），替换为可检索 chunk——替换记录见 `迁移难点_5e无法映射.md` §三。
