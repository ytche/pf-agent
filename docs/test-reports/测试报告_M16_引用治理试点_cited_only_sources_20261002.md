# 测试报告：M16 引用治理试点 —— sources 只保留正文实际引用条目（cited-only）

- 分支：`feat/cited-only-sources-filter-pilot`（worktree wt-16，base `dev/pf-agent`）
- 实现提交：`28ecd29`
- 评测日期：2026-10-02
- 需求口径（用户 2026-10-01 拍板）：「只保留有效引用，删除无效引用」；「参考了不算，
  按原定义『引用某 chunk 内容的句子后附编号』」——即响应 `sources` 只保留被正文 `[#N]`
  上标实际引用的条目，其余未引用条目删除不返回。

## 一、实现说明

改动文件：

| 文件 | 改动 |
|---|---|
| `pf_agent/agent/src/main/java/com/pfagent/agent/chat/ChatService.java` | `buildResponse` 组装响应时改调 `filterCitedSources`；新增 `filterCitedSources` / `parseCitation` / `CitedResult` record；删除原 `stripInvalidCitations`（其合法性判定收口进 `parseCitation`） |
| `pf_agent/agent/src/test/java/com/pfagent/agent/chat/ChatServiceTest.java` | 新增 4 个用例；2 个旧用例的答案补 `[#1]` 标记（原答案无标记，新语义下 sources 会被正确清空） |

行为：

1. 解析正文中全部闭合 `[#N]`；`N` 为纯数字、位长 ≤9 且 `1<=N<=原 sources 数`才算有效引用。
2. 只保留被有效引用的来源，**保持原相对顺序**（原编号升序）；未引用条目删除不返回。
3. 正文 `[#N]` 按新下标（保留序位次）**重映射改写**，维持「编号 N ↔ sources 第 N 条」对齐。
4. 越界/畸形标记仍从正文剥离、保留句子本身（SP4 D5 原行为），并记 WARN。
5. 无有效引用（含正文无任何标记）时 `sources=[]`，前端自然不显示来源区。
6. `ChatResponse` 结构不变（不加字段、不改 API 形状）；`SourceCollector` 未改动（编号仍按原始收集序分配，过滤发生在出口）。

## 二、单元测试

`cd pf_agent/agent && mvn test`：

```
Tests run: 566, Failures: 0, Errors: 0, Skipped: 16
BUILD SUCCESS
```

基线 562 → 566（+4，只增不减）。新增用例：未引用来源删除+重映射、乱序引用（来源保原序）、
重复引用去重、正文无标记时 `sources=[]`；原有越界/畸形/空来源剥离行为已全部保留回归。

## 三、评测代价（evaluate.py 三口径）

### 方法

评测集 53 题（`status∈{D,R}` 活跃题；较早前 50 题快照多 3 题 SP3 枚举题）。为避免 LLM
非确定性干扰，做两次独立测量：

- **A 实跑对比**：同一 `evaluate.py`、同环境，分别打「基线 jar（dev/pf-agent，无过滤，
  port 8098）」与「分支 jar（cited-only，port 8099）」两个实例。
- **B 配对离线重放**：把**基线实例原始响应**（未过滤 sources + 含标记的正文）过一遍
  `qa/citation_filter_replay.py`（过滤逻辑与 `ChatService.filterCitedSources` 逐条一致），
  得到同一批回答在「过滤前/后」的分数——**噪声无关**，纯量化过滤本身代价。

> 注：仓库既有的 `qa/qa_report.json`（50 题、溯源 50/50）快照早于 SP4 引用编号功能，
> 其 answer 不含任何 `[#N]` 标记，**不可用于本次对比**，故未采用。

### 三口径结果

| 口径 | 基线实跑（无过滤） | 分支实跑（cited-only） | 配对离线重放（噪声无关） |
|---|---|---|---|
| 溯源正确性 | 53/53（1.00） | **52/53（0.98）** | 53 → **52**（Δ −1） |
| 拒绝诚实性 | 53/53（1.00） | 53/53（1.00） | 53 → 53（Δ 0） |
| 回答结构 | 159/53（3.00） | 159/53（3.00） | 159 → 159（Δ 0） |

- **溯源代价 = −1 题**（仅 `medium-17`），仍满足设计口径「溯源 ≥52/53」。
- 诚实、结构零变化：正文不受来源过滤影响，且本题集过滤后 sources 从不为空。
- **正文引用数为 0 的题：0 题**（两个实例、53 题均至少 1 个 `[#N]`）——用户担心的
  「模型引用稀疏甚至为 0 → sources 变空」在现行 prompt 下**未出现**。

### 体积（配对重放）

- sources 总条数：**2570 → 450（−82.5%）**；均值 48.5 → 8.5。
- 53 题中 **43 题**来源被削减；单题削减最大的：`medium-25` 181→48、`medium-21` 158→28、
  `medium-3` 135→22、`easy-11` 123→11、`medium-23` 131→26。
- 分支实跑 sources 总数 437（均值 8.2），与重放一致量级。

### 逐题重点

| 题 | expected 锚点 | sources | 正文引用 | 溯源 | 说明 |
|---|---|---|---|---|---|
| `easy-22` | `rule_page_127_0028` | 75 → 5 | 引 5 条，含 idx73 | 1 → **1（保持）** | 担心的「锚点在 idx63 被硬过滤丢弃」**未发生**——LLM 确实在正文引用了该锚点 chunk |
| `medium-17` | `equipment_page_222_0000`、`equipment_page_220_0000`（loose） | 78 → 9 | 引 9 条：`[1,2,3,5,11,25,26,29,30]` | 1 → **0（唯一下降）** | 聚合题：答案由某页多个 chunk 综合得出，LLM 只给 9 条编号且**未覆盖锚点 chunk**，硬过滤后锚点不在 sources |

**溯源唯一下降题 `medium-17` 明细**：属 `citation_mode=loose` 的跨 chunk 聚合题。基线
78 条 sources 中锚点在列（score_citation 命中），过滤后只留 LLM 实际引用的 9 条，锚点未被
引用 → 掉分。这是本试点唯一可量化的代价。

## 四、结论与建议

1. **代价小且可接受**：三口径中仅溯源 −1/53（medium-17），诚实/结构零变化，满足 ≥52/53 口径。
2. **用户担心的两种极端（大量 0 引用题、sources 变空）未出现**；`easy-22` 类「锚点靠后」
   的题因 LLM 实际引用锚点而未掉分。
3. **剩余缺口集中在聚合/宽松题**（如 medium-17）：答案综合自某页多 chunk，LLM 引用稀疏且
   抓不到 page 级锚点。这属「评测锚点口径」与「正文引用粒度」的错位，非过滤逻辑缺陷。
   可选跟进（非本次范围）：对 `loose` 题在评测侧放宽为「sources 中出现该 page 任一 chunk」，
   或 prompt 引导聚合题补标证据 chunk。
4. 塔可从本分支部署演示给用户看效果（sources 体积 −82.5%，编号对齐正确），再决定是否合并。

## 五、复现步骤

```bash
# 1) 分支构建（wt-16 worktree）
cd <worktree>/pf_agent/agent && mvn -o -DskipTests package

# 2) 起实例（端口避开 8080；memory 模式免 PG；遥测落 /tmp 免污染共享日志）
#    数据路径相对 agent 工程根解析 ../../pf_data，故 cwd 用主 checkout 的 agent 目录
cd /Users/chezi/code/java/pf_agent/pf_agent/agent
java -jar <worktree>/pf_agent/agent/target/pf-agent-0.2.0.jar \
  --server.port=8099 --pf.chat.memory=memory \
  --pf.tools.file-path=/tmp/m16/tool_calls.jsonl \
  --pf.gaps.file-path=/tmp/m16/data_gaps.jsonl \
  --pf.feedback.file-path=/tmp/m16/annotations.jsonl

# 3) 实跑评测
cd <worktree>/pf_agent/agent/qa
python3 evaluate.py --base-url http://localhost:8099 --report-dir /tmp/m16/eval --timeout 180 --delay 0.5

# 4) 基线实例同法起在 8098（用主 checkout target/pf-agent-0.2.0.jar，dev/pf-agent 无过滤），
#    再跑一遍得基线原始响应；然后噪声无关配对重放：
python3 citation_filter_replay.py --snapshot /tmp/m16/base_eval/qa_report.json --json /tmp/m16/base_replay.json
```

`qa/citation_filter_replay.py` 为本次新增的离线重放分析脚本（过滤逻辑与生产代码逐条一致，
便于后续复算过滤代价）。
