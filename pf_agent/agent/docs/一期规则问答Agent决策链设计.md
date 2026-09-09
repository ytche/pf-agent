# 一期规则问答 Agent 决策链 — 设计文档

> 版本：v1.9（2026-08-20）· 已实现
> 适用范围：`pf_agent/agent` 工程一期（规则问答 Agent），不含二期（车卡/Build）
> v1.9 变更：**工具循环不收敛从抛 500 改为强制收敛作答（F-002 复盘）**——baseline 重跑发现 6 题「工具循环超 15 轮」500（`easy-7/18/22`、`medium-17/18/23`，聚合/跨 chunk 综合题 LLM 反复检索不收敛）。三处修复：A `searchByMetadata` 结果字符截断（`pf.search.metadata-result-chars` 默认 4000，防 `{book:"CRB"}` 宽过滤单次 26K 淹没 LLM）；B 修正 `assertHistorySize` 统计口径（原 `getText()` 漏算 `ToolResponseMessage` 工具结果致 50K 上限失效）并改超限强制收敛；C `maxToolRounds` 超限同样强制收敛（与上下文超限对称，不再抛 500），默认轮数 15→10。§8/§11/§12 同步更新
> v1.8 变更：**职业问答"顺带编造施法方式"修复（AKN-003，A+B 方案）**——A：`PromptBuilder` system prompt 新增两条规则（①每条规则事实必须有检索依据，检索未提供的禁止凭记忆补全；②职业核心机制以"基础职业能力"检索结果为准，变体冲突以基础页为准）。B：`SearchService` class 模块基础职业页（tocPath 恰为 `职业 → 基础职业 → X`）相似度 +0.03 加分重排（仅排序不改 score）+ 候选集 topK+3，缓解变体噪声（226 vs 16）压过基础页、加剧 LLM 把规则标成"推断"。§3.2/§8/§12/§13/§14/§15 同步更新
> v1.7 变更：**检索面扩展至 8 模块（合并 main 后接入 6 个新向量库）**——专长/种族/背景特性/装备/技能/规则 6 个模块的 chunk 产物经统一行模型 `StandardChunk` + 统一映射 `StandardChunkMapper` 接入检索链路。每模块仅建 ~20 行 DataLoader 薄壳（FeatDataLoader/RaceDataLoader/TraitDataLoader/EquipmentDataLoader/SkillDataLoader/RuleDataLoader），共享 ChunkImporter 泛型导入。SearchService 路由 map 扩展 8 库，RetrievalTools.VALID_MODULES 与 FilterTranslator 同步扩展（6 新模块首期仅暴露 book + componentType 过滤，nested metadata 不扁平化）。§3/§5/§13/§14/§15/§17 同步更新
> v1.1 变更：新增 §9 多轮上下文与记忆
> v1.2 变更：§11/§16 新增工具循环轮次上限说明与请求超时兜底
> v1.3 变更：§11/§12/§16 请求超时改为配置属性 `pf.search.chat-timeout`，默认 120s（§13 新增 `ClientHttpRequestFactory` bean）
> v1.4 变更：**工具循环改为手动模式 + maxRounds 上限**（§8/§9/§11/§12/§13/§16）。已论证：单次 HTTP read timeout **无法**终止"LLM 快速无限返回 tool_call"的循环（每次调用都在超时内完成），只有应用层轮次计数才能确定性结束。maxRounds 走配置 `pf.search.max-tool-rounds`，默认 15 次；readTimeout 降为"防单次调用卡死"的辅助防线（60s）；关闭 Spring AI RetryTemplate 重试，避免超时被放大（默认 maxAttempts=10）
> v1.5 变更：**自审修正（A/B/C 级缺陷）**——A1 §15 专长问题超出工具面范围→换法术/职业问题；A2 §8 history 组装 SystemMessage 移至最前；B1 工具参数解析失败返回错误给 LLM 自纠而非 500；B2 vectorSearch 正文截断（`pf.search.vector-result-chars`）；B3 工具循环上下文超限提前终止（`pf.search.max-history-chars`）；B4 SourceCollector 按 doc_id 去重；B5 虚构问题验证标注人工兜底；B6 补 ChatControllerTest；C1 前端 marked.js 输出 HTML 转义；C2/C3 并发与职业名 key 说明；C4 LLM 空内容兜底
> v1.6 变更：**向量库重建定为方案 B（元数据重放）**——实机检查确认：现有 spell 库已为 BGE-M3（1024 维、4200 docs）、mapper 改动仅新增 metadata 扁平键、`Document.text` 不变→向量不变，故全量重建（30 分钟重算 embedding）纯浪费。改为一次性重放工具 `SpellMetadataReplayTool`（`@ConditionalOnProperty(pf.stores.metadata-replay)` 门控，秒级完成）：load 现有库 → 用新 mapper 重映射 metadata → 按 `chunk_id` join → 替换 metadata 保留原 text+embedding → save。§13/§14/§15/§16 同步更新

---

## 1. 背景与目标

PathFinder 1e 规则问答 Agent 的核心诉求是让 **LLM 理解任意自然语言问题**，自主决定如何检索规则库并组织答案。已确认的硬性要求：

| 目标 | 说明 |
|---|---|
| L0（能回答） | 任意问题类型都能走通检索→回答链路 |
| L1（答得准） | 答案准确、可溯源（来源进前端折叠区） |
| 不穷尽问题类型 | 不写 `searchSpells("女巫",1)` 这类具体方法，用户问题无穷 |
| 多轮上下文 | 后问可引用前问信息（"我选了元素庇护主，一环怎么配"） |
| LLM 失败→500 | LLM API 超时/异常时**直接报错 500**，绝不静默降级为语义检索 |

**核心手段：Spring AI 1.0.0-M6 的 Function Calling（`@Tool`）** —— 把底层检索方法暴露给 LLM，LLM 在**一次对话内**自主决定调哪些工具、分几步查、最后拼接答案。

---

## 2. 架构总览

```
┌─ 用户问题 + conversationId（前端生成） ──────────────────┐
│   │                                                      │
│   ▼                                                      │
│  ChatService.ask(question, conversationId)               │
│   │                                                      │
│   ▼                                                      │
│  ChatClient（DeepSeek chat，注册 3 个检索工具）           │
│   │   └─ ChatMemory：循环外层注入历史 / 结束后回存问答对    │
│   │                                                      │
│   │  工具循环（手动执行 + maxRounds 上限，默认 15 轮）     │
│   │   ┌──────────────────────────────────────────────┐   │
│   ├──▶│ LLM 判断 → 调工具 → 看结果 → 再判断 → 最终回答 │   │
│   │   │   · searchByMetadata  元数据精确过滤（枚举）     │   │
│   │   │   · vectorSearch      语义检索（规则细节）       │   │
│   │   │   · reportDataGap     数据缺口记录（优化闭环）    │   │
│   │   └──────────────────────────────────────────────┘   │
│   ▼                                                      │
│  回答(Markdown) + 来源列表（SourceCollector 汇总）         │
│            + gapReported 标记（本次是否记录了数据缺口）     │
└──────────────────────────────────────────────────────────┘
```

**与旧 RAG 流程的差别**：

| | 旧流程（现有代码） | 新流程（本设计） |
|---|---|---|
| 检索时机 | 先 `search()` 固定语义检索 | LLM 自主决定何时调哪个工具 |
| 检索方式 | 只有向量检索 | 元数据过滤 + 向量检索 双路 |
| 多步查询 | 不支持 | LLM 分步调工具自行拼接 |
| 多轮上下文 | 无状态 | ChatMemory 自动注入历史 |
| 检索无结果 | 直接告诉用户"没查到" | 调 `reportDataGap` 记录 + 如实告知 |

---

## 3. 工具面设计（3 个底层方法）

> 核心原则：**只给底层方法，字段名/字段值由 LLM 自己构造**。工具描述即"数据库 schema"，让 LLM 学会组合。

### 3.1 `searchByMetadata(module, filters)` — 元数据精确过滤

```java
@Tool(description = """
    按元数据精确过滤指定模块的规则库，返回命中条目的紧凑列表。
    模块 module: "spell"(法术) / "class"(职业特性) / "feat"(专长) /
    "race"(种族) / "trait"(背景特性) / "equipment"(装备) / "skill"(技能) /
    "rule"(规则)
    过滤条件 filters: 字段名→字段值 映射，多条件为 AND，值需精确匹配。

    法术模块可用字段:
      title(法术名) / school(学派如"咒法系") / subschool(子学派) /
      className(职业名，如"女巫") / level(环数1-9，须配合className) /
      book(来源书缩写，如 CRB)
    职业模块可用字段:
      className(职业名) / archetypeName(变体名) / featureSubtype(特性子类型，
      如 hex/patron/grand_hex) / componentType(class_overview|class_feature|
      class_archetype) / book(来源书缩写)
    专长/种族/背景特性/装备/技能/规则模块通用字段:
      book(来源书缩写) / componentType(条目类型，如 feat/rule_section/trait)

    示例: 女巫1环法术 → {module:"spell", filters:{className:"女巫", level:"1"}}
          咒法系法术  → {module:"spell", filters:{school:"咒法系"}}
          核心书的猛力攻击专长 → {module:"feat", filters:{book:"CRB",
          componentType:"feat"}}
    字段名错误时返回可用字段清单。查询无结果返回空列表。
    """)
String searchByMetadata(String module, Map<String, String> filters);
```

### 3.2 `vectorSearch(question, module)` — 语义检索

```java
@Tool(description = """
    语义检索规则原文。用于：查具体规则细节（如"火球术的射程"）、
    不知道精确元数据字段、元数据过滤无结果时。
    question: 检索问题；module: "spell"(法术) / "class"(职业) / "feat"(专长) /
    "race"(种族) / "trait"(背景特性) / "equipment"(装备) / "skill"(技能) /
    "rule"(规则) / "all"(全部)
    返回相似度最高的若干条规则片段（单条正文截断到 pf.search.vector-result-chars，
    默认 1500 字符，超出部分省略），完整原文见前端来源折叠区。
    """)
String vectorSearch(String question, String module);
```

> v1.5（B2）：单条正文截断防上下文膨胀——topK=5 × 截断 1500 字符 ≈ 7500 字符注入，远低于 64K；完整原文仍由 `SourceCollector` 留给前端溯源，不影响答得准。
> v1.8（AKN-003）：class 模块调用 `SearchService.search(question, "class")` 时扩容候选集 topK+3，排序阶段基础职业页（tocPath 无更细分后缀）相似度 +0.03（`pf.search.class-base-bonus`，仅排序用不改 `Document.score`）——让"必须预先选择并准备法术"类基础页原文更稳进 topK；问变体时基础页相似度 <0.55 不在候选集，加分无影响。

### 3.3 `reportDataGap(question, attemptedFilters, reason)` — 问题报告

```java
@Tool(description = """
    数据缺口报告：当 searchByMetadata / vectorSearch 都无法找到回答
    用户问题所需的规则数据时调用，把问题记录下来供后续优化。
    question: 用户原始问题；attemptedFilters: 已尝试的过滤条件(JSON字符串，可空)；
    reason: 缺什么数据（如"找不到女巫的XX规则"）。
    记录后如实告知用户缺少相关知识。
    """)
String reportDataGap(String question, String attemptedFilters, String reason);
```

### 3.4 LLM 决策链示例

| 用户问题 | LLM 应调用的工具序列 |
|---|---|
| 女巫 1 环法术都有哪些 | `searchByMetadata(spell, {className:女巫, level:1})` → 输出 Markdown 表格 |
| 咒法系有哪些法术 | `searchByMetadata(spell, {school:咒法系})` → 输出列表 |
| 火球术的射程 | `vectorSearch(火球术 射程, spell)` |
| 女巫的巫术都有哪些 | `searchByMetadata(class, {className:女巫, featureSubtype:hex})` |
| 先列女巫巫术，再挑一个说详情 | 分两步：`searchByMetadata(...)` 后 `vectorSearch(某巫术, class)`，自行拼接 |
| 猛力攻击的专长详情 | `vectorSearch(猛力攻击 先决条件 效果, feat)` 或 `searchByMetadata(feat, {book:CRB})` 后取目标 |
| 人类种族特性 | `searchByMetadata(race, {componentType:race_trait})` + `vectorSearch(人类, race)` 组合 |
| 装备武器范畴 | `vectorSearch(长剑 伤害 类别, equipment)` |
| 过滤猜错字段 | 工具返回字段清单 → LLM 自纠，或转 `vectorSearch` |
| 所有工具都查不到 | `reportDataGap(...)` 记录 → 如实告知用户 |

---

## 4. 元数据扁平化（S2）

`SimpleVectorStore` 的 `filterExpression` **只作用于顶层标量 metadata**。法术 chunk 里 `spell_level` 是嵌套数组，必须展开。

### 4.1 数据现状

```jsonc
// 法术 chunk 的 metadata（当前未映射进 Document）
{
  "school": "咒法系",
  "subschool": "创造",
  "spell_level": [
    {"class": "德鲁伊", "level": 1},
    {"class": "女巫",   "level": 1},
    {"class": "法师",   "level": 1}
  ]
}
```

### 4.2 扁平化输出（`SpellChunkMapper` 修改）

```java
// 新扁平键
meta.put("school", c.metadata().get("school"));        // "咒法系"
meta.put("subschool", c.metadata().get("subschool"));  // "创造"
// spell_level 数组展开（值统一转 String，保证过滤类型一致）
meta.put("spell_level_德鲁伊", "1");
meta.put("spell_level_女巫",   "1");
meta.put("spell_level_法师",   "1");
// 仅按职业查（无环数）时用存在性键
meta.put("has_spell_德鲁伊", "true");
meta.put("has_spell_女巫",   "true");
meta.put("has_spell_法师",   "true");
```

> **职业模块无需改 mapper**：`class_name` / `archetype_name` / `feature_subtype` / `component_type` / `book_abbreviation` 已是扁平键。
>
> ⚠️ **法术向量库需重建**：现有持久化文件 `~/.pf_agent/vector_store_spells.json` 没有这些键（约 30 分钟本地 embedding）。
>
> **v1.5（C3）键名兼容性**：`spell_level_<职业>` / `has_spell_<职业>` 的职业名直接拼进 metadata 键。实施时抽查数据侧职业名是否含括号/空格等特殊字符（如"圣骑士(帕拉丁)"），若有则需统一映射为纯净名；`SimpleVectorStore` 的 filterExpression 对任意字符串键名均支持（eq 按值精确匹配），键名本身不解析，风险仅在数据侧命名不一致。

---

## 5. 通用过滤实现（S3）

### 5.1 逻辑字段 → 真实 metadata 键翻译

`searchByMetadata` 内部把 LLM 传来的"逻辑字段"翻译成扁平键（`FilterTranslator`）：

| 模块 | 逻辑字段 | 真实键 | 说明 |
|---|---|---|---|
| spell | `title` | `title` | |
| spell | `school` | `school` | |
| spell | `subschool` | `subschool` | |
| spell | `className`+`level` | `spell_level_<职业>`=`level` | 女巫1环 → `eq(spell_level_女巫, "1")` |
| spell | `className`（无 level） | `has_spell_<职业>`=`"true"` | 女巫所有法术 → `eq(has_spell_女巫, "true")` |
| spell | `book` | `book_abbreviation` | |
| class | `className` | `class_name` | |
| class | `archetypeName` | `archetype_name` | |
| class | `featureSubtype` | `feature_subtype` | |
| class | `componentType` | `component_type` | |
| class | `book` | `book_abbreviation` | |
| feat/race/trait/equipment/skill/rule | `book` | `book_abbreviation` | **v1.7**：6 个标准模块共用同一映射（统一行模型） |
| feat/race/trait/equipment/skill/rule | `componentType` | `component_type` | 仅暴露这两个通用字段；各模块 nested metadata（feat_type/race_name/slot 等）首期不扁平化 |

### 5.2 filterExpression 构造（已验证 API）

```java
FilterExpressionBuilder b = new FilterExpressionBuilder();
Filter.Expression expr = null;
for (var e : translated) {
    var op = b.eq(e.key(), e.value());
    expr = expr == null ? op : b.and(expr, op);
}
SearchRequest req = SearchRequest.builder()
        .query(module)                  // 枚举查询的 query 不影响结果
        .topK(500)                      // 枚举专用大 topK（配置项）
        .similarityThresholdAll()       // 接受全部相似度 → 过滤即全部命中
        .filterExpression(expr)
        .build();
```

> `SearchRequest.builder().similarityThresholdAll()` 已确认存在；`eq/and/in/not/group` 算子齐全。

---

## 6. 来源收集（S4）

工具在函数调用循环里返回结果给 LLM，但 `ChatResponse.sources`（前端来源折叠区）需要**完整 Document**。引入请求级收集器：

```java
@Component
public class SourceCollector {
    private final ThreadLocal<List<Document>> current = new ThreadLocal<>();

    void begin() { current.set(new ArrayList<>()); }
    void add(List<Document> docs) { if (docs != null) current.get().addAll(docs); }
    List<Document> drain() {
        // v1.5：按 doc_id 去重，多步查询同一 chunk 命中多次只进一次来源折叠区（B4）
        Map<String, Document> dedup = new LinkedHashMap<>();
        for (Document d : current.get()) {
            dedup.putIfAbsent(String.valueOf(d.getMetadata().get("doc_id")), d);
        }
        List<Document> r = new ArrayList<>(dedup.values());
        current.remove();
        return r;
    }
    void markGapReported() { ... }   // 记录本次是否有数据缺口
    boolean wasGapReported() { ... }
}
```

- 每个 `@Tool` 命中时 `collector.add(docs)`（同时把**完整正文**留给前端溯源）
- 工具返回给 LLM 的则是**紧凑摘要**（标题/学派/环数/来源），控制上下文体积
- 多步查询：所有工具命中的来源全部进入折叠区（按 doc_id 去重）

---

## 7. 问题报告机制（S5）

```java
@Component
public class DataGapRecorder {
    // 配置: pf.gaps.file-path = ${user.home}/.pf_agent/data_gaps.jsonl
    void record(String question, String attemptedFilters, String reason) {
        // 追加一行 JSONL（含时间戳）
    }
}
```

追加格式（JSONL，一行一条，后续用脚本分析）：

```jsonc
{"question":"女巫的XX变体规则","attemptedFilters":"{className:女巫}",
 "reason":"查不到该变体","timestamp":"2026-07-31T10:15:30"}
```

- `reportDataGap` 工具内部调用 `recorder.record(...)` + `sourceCollector.markGapReported()`
- LLM 记录后仍会如实回答"缺少相关知识"
- `ChatResponse` 增加 `gapReported` 布尔，前端可提示"该问题已记录，将纳入后续优化"

---

## 8. ChatService 编排（S6）

> **v1.4 改为手动工具循环**：M6 框架自动循环 `while(hasToolCalls)` 无轮次上限，单次 HTTP read timeout **无法**终止"LLM 快速无限返回 tool_call"的循环（每轮调用都在超时内正常完成）。因此应用层自持循环、显式计数，超过 `maxToolRounds` 直接抛异常 → 500。`DefaultToolCallingChatOptions.internalToolExecutionEnabled(false)` 关闭框架自动执行；工具通过 `ToolCallback.call(name, args)` 手动执行。全部 API 已反编译验证。

> **v1.9 改为超限强制收敛**：`maxToolRounds` 超限 / `maxHistoryChars` 超限均不再抛 500，而是 `forceAnswer` 追加「基于已有结果作答」指令后无工具作答（原因见版本块 v1.9，默认轮数 15→10）。确定性结束、线程不泄漏仍成立——forceAnswer 无工具单次调用必返回。

```java
public ChatResponse ask(String question, String conversationId) {
    String cid = (conversationId == null || conversationId.isBlank())
            ? UUID.randomUUID().toString()   // 前端未传时生成新会话
            : conversationId;
    log.info("收到问题: {} (会话 {})", question, cid);
    sourceCollector.begin();
    try {
        List<Message> history = new ArrayList<>();
        history.add(new SystemMessage(promptBuilder.buildSystemPrompt())); // ① system 最前（v1.5）
        history.addAll(chatMemory.get(cid, historySize));                  // ② 注入前文（见 §9.3）
        history.add(new UserMessage(question));

        for (int round = 0; round < maxToolRounds; round++) {
            if (historyChars(history) > maxHistoryChars) {       // ③ 上下文超限 → 强制收敛（v1.9）
                return finish(question, forceAnswer(history), cid);
            }
            ChatResponse resp = chatClient.prompt()
                    .messages(history)
                    .tools(retrievalTools)                     // 注册 3 个 @Tool（每轮注入 schema）
                    .options(DefaultToolCallingChatOptions.builder()
                            .internalToolExecutionEnabled(false) // ④ 关闭框架自动执行，循环交给我们
                            .build())
                    .call()
                    .chatResponse();

            AssistantMessage am = resp.getResult().getOutput();
            history.add(am);                                   // ⑤ assistant（本轮 tool_call 或最终回答）

            if (!resp.hasToolCalls()) {
                String answer = (am.getText() == null || am.getText().isBlank())
                        ? "（模型未返回回答内容，请重试）"       // v1.5：空内容兜底（C4）
                        : am.getText();
                chatMemory.add(cid, List.of(new UserMessage(question), am));  // ⑥ 回存 user+最终回答
                return buildResponse(answer, cid);             // 无工具调用 → 最终回答
            }

            // ⑦ 手动执行本轮的每个工具调用，结果拼回 history
            List<ToolResponseMessage.ToolResponse> toolResults = new ArrayList<>();
            for (AssistantMessage.ToolCall tc : am.getToolCalls()) {
                ToolCallback cb = callbacksByName.get(tc.name());
                if (cb == null) {
                    throw new IllegalStateException("LLM 调用了未注册的工具: " + tc.name());
                }
                // v1.5：参数解析/执行失败不中断请求，作为工具结果返回，LLM 自纠后重试（B1）
                String result;
                try {
                    result = cb.call(tc.arguments());           // ToolCallback.call(String) 已验证
                } catch (Exception e) {
                    log.warn("工具 {} 执行失败: {}", tc.name(), e.getMessage());
                    result = "工具执行失败: " + e.getMessage()
                            + "。请检查字段名与值格式后重试，可用字段见工具描述。";
                }
                toolResults.add(new ToolResponseMessage.ToolResponse(tc.id(), tc.name(), result));
            }
            history.add(new ToolResponseMessage(toolResults));  // ⑧ 工具结果
        }
        // 轮次超限 → 强制收敛作答（v1.9，与上下文超限对称，不再抛 500）
        return finish(question, forceAnswer(history), cid);
    } finally {
        sourceCollector.clear();
    }
}

// v1.9：history 字符数——ToolResponseMessage 统计各条工具结果（v1.5 用 getText() 漏算），其余统计文本
private long historyChars(List<Message> history) {
    long chars = 0;
    for (Message m : history) {
        if (m instanceof ToolResponseMessage trm) {
            chars += trm.getResponses().stream().mapToLong(r -> r.responseData() == null ? 0 : r.responseData().length()).sum();
        } else if (m instanceof AbstractMessage am && am.getText() != null) {
            chars += am.getText().length();
        }
    }
    return chars;
}

// v1.9：超限收敛——追加「基于已有结果作答」指令后，用无工具调用让 LLM 直接给出最终回答
private AssistantMessage forceAnswer(List<Message> history) {
    history.add(new SystemMessage("检索上下文已达上限，请基于以上检索结果直接给出最终回答，不要再调用任何工具。"));
    return chatClient.prompt().messages(history).call().chatResponse().getResult().getOutput();
}
```

- **maxRounds 计数**：`maxToolRounds` 来自 `@Value("${pf.search.max-tool-rounds:10}")`，超限强制收敛作答（v1.9，不再抛 500；确定性结束、线程不泄漏仍成立——forceAnswer 无工具单次调用必返回）
- **上下文超限（v1.9）**：`maxHistoryChars` 来自 `@Value("${pf.search.max-history-chars:50000}")`（低于 DeepSeek 64K 留余量），每轮检查 `historyChars(history)`，超限强制收敛作答（v1.5 原为抛异常且 `getText()` 漏算工具结果致上限失效，v1.9 修正统计口径）
- **工具注册表**：`callbacksByName` 由 `ToolCallbacks.from(retrievalTools)`（`@Tool` 方法 → `Map<name, ToolCallback>`，已验证 `ToolCallbacks.from(Object...)` 自动发现 `@Tool`）
- **每轮 `.prompt()` 不重注入 memory**：历史由 `history` 列表自持，避免 advisor 每轮重复注入 → §9 由 advisor 改为**手动 ChatMemory 调用**
- **工具参数错误不中断请求**（v1.5）：LLM 传的字段/JSON 非法时，把错误串作为工具结果返回，LLM 读到后自纠重调；只有"未注册工具名"才抛异常（框架级错误，LLM 无法自愈）
- **异常上抛**：LLM API 超时/异常 → Spring 默认 500，前端显示"稍后重试"
- `buildResponse` 内部：`sourceCollector.wasGapReported()` + `drain()` → `ChatResponse(answer, sources, gap, cid)`

### PromptBuilder 重写

不再预检索注入文档，改为：

```
你是 PathFinder 1e 规则助手。
- 必须使用提供的检索工具查找规则数据，禁止凭记忆编造规则
- 输出 Markdown，禁止输出 HTML 标签；枚举类问题用 Markdown 表格组织
  （法术名 | 学派 | 环数 | 来源书）
- 回答须引用来源（书 + 页码，来自工具返回结果）
- 若所有检索工具都找不到所需数据，调用 reportDataGap 记录，
  然后如实告知用户缺少相关知识
- 区分"明确规则"和"推断内容"
- 每条规则事实（如施法方式、生命骰、豁免、法术位、职业能力）必须有检索
  依据：回答中的任何断言都要能在检索结果原文中找到对应表述；检索结果未
  提供的规则事实，禁止凭记忆补全，若该事实影响回答完整性，先调用
  reportDataGap 报告缺失，再如实说明"规则原文未检索到该信息"（v1.8，AKN-003）
- 职业核心机制（施法方式、生命骰、豁免等）以"基础职业能力"检索结果为
  准；职业变体文本与基础职业页冲突时，以基础职业页为准，除非问题明确
  指向某变体（v1.8，AKN-003）
```

---

## 9. 多轮上下文与记忆（v1.1 新增）

### 9.1 场景

用户连续提问，后问引用前问信息：

| 轮 | 用户问题 | 需要的前文信息 |
|---|---|---|
| q1 | 女巫 1 环有哪些法术 | — |
| q2 | 女巫庇护主有哪些法术 | "女巫"（同一会话延续） |
| q3 | 我选了**元素庇护主**，我**一环**选哪些法术来**补充女巫的控制能力** | q1/q2 的法术列表、q3 自述的新事实 |

q3 能成立的关键：LLM 知道前两轮的"女巫/一环/庇护主"语境，且能对新事实（元素庇护主、控制能力）实时检索拼装。

### 9.2 分层设计

| 层 | 范围 | 机制 | 一期 |
|---|---|---|---|
| **L1 会话内上下文** | 同一会话多轮（q1→q2→q3） | `ChatMemory`（手动注入/回存，见 §9.3） | ✅ 做 |
| **L2 跨会话长期记忆** | 多会话间（用户偏好/选择，如"我选了元素庇护主"） | 用户事实抽取存档，后续会话注入 | 预留扩展，二期 |

### 9.3 L1 实现（v1.4：advisor → 手动 ChatMemory）

> **v1.4 变更原因**：手动工具循环中每轮都调用一次 `.prompt()`，若用 `MessageChatMemoryAdvisor`，它会在**每轮**注入历史 + 回存中间消息（含 tool_call 的 assistant），造成历史重复注入与记忆污染。因此改为 ChatService 手动调用 `ChatMemory`：循环**外层**注入前文、结束后回存，循环**内部**历史完全自持。

```java
// AgentConfig
@Bean InMemoryChatMemory chatMemory() { return new InMemoryChatMemory(); }

// ChatClient 无需 defaultAdvisors，历史由 ChatService 手动管理
@Bean ChatClient chatClient(OpenAiChatModel model) {
    return ChatClient.builder(model).build();
}
```

工作机制（ChatService 内实现，API 已验证）：

1. **注入**：请求开始时 `chatMemory.get(cid, historySize)` 取历史（最近 N 条 user/assistant），加入 `history` 列表头部（§8 步骤①）
2. **回存**：最终回答那轮结束后 `chatMemory.add(cid, [user(question), assistant(最终)])`，**只存问答对，不存工具调用消息**（§8 步骤④）
3. **会话隔离**：`cid` 由 ChatService 参数传递，各会话互不串扰
4. **函数调用兼容**：工具结果只在**当次请求**的 `history` 内传递，不落入记忆；后续回合 LLM 需要数据时**重新调工具**（与 advisor 模式行为一致，仅注入/回存位置从"每轮"变为"循环外层"）

### 9.4 conversationId 来源

- 前端单页每次打开生成 UUID，存 `localStorage`，**刷新页面会话不丢**
- `ChatRequest` 新增 `conversationId` 字段；后端收到空值则生成新 UUID 并随响应返回（`ChatResponse.conversationId`）
- 一期前端只有"一个会话"；多会话管理（历史列表）后续再加

### 9.5 完整链路（q1→q3）

```
q1 "女巫1环有哪些法术"
   → 注入历史[] → 调 searchByMetadata → Markdown 表格
   → 回存 [user(q1), assistant(表格)]
q2 "女巫庇护主有哪些法术"
   → 注入历史[q1对] → 调 searchByMetadata(庇护主法术) → 回答
   → 回存 [q1对, user(q2), assistant]
q3 "我选了元素庇护主，我一环选哪些法术来补充女巫的控制能力"
   → 注入历史[q1对, q2对]
   → LLM 理解：女巫/一环/庇护主是前文语境，元素庇护主是新事实
   → 重新调 searchByMetadata(女巫1环) / searchByMetadata(庇护主) 取实时数据
   → 结合"控制能力"组织推荐清单 + 来源
```

### 9.6 持久化与长期记忆（决策）

| 项 | 决策 | 理由 |
|---|---|---|
| L1 存储 | 一期 `InMemoryChatMemory`（内存） | 单用户本地 agent，前端刷新生成新会话，丢旧会话可接受 |
| L1 可替换性 | `ChatMemory` 接口 | 后续要跨重启续会话，换成文件持久化实现即可（JSONL 按会话分组） |
| L2 长期记忆 | 一期**不做**，预留扩展 | 从对话抽取用户事实（如"我选了元素庇护主"）→ 用户档案 → 后续会话注入，二期范畴 |
| 历史长度 | `lastN=20`（可配） | 防上下文超窗；DeepSeek 64K，工具结果即时注入，历史只需承载语境 |

> **v1.5（C2）并发说明**：`InMemoryChatMemory` 的 `ConcurrentHashMap` 实现本身线程安全；本 agent 一期为单用户本地场景，同一 conversationId 的并发请求不会出现（前端单会话、串行提问），跨会话隔离由 conversationId 天然保证。若后续接多用户/同会话并发，需在 `ChatMemory` 文件实现中按会话加锁并考虑 L1 存储迁移，本设计不改动当前选型。

---

## 10. 输出格式与前端

| 项 | 决定 |
|---|---|
| 输出格式 | **Markdown**（LLM 组织；枚举用表格，代码不组装表格） |
| 前端 | **B 档单页**：输入框 + 回答区 + 来源折叠，`marked.js` 渲染 Markdown |
| 会话 | 单页单会话，UUID 存 localStorage；`gapReported` 时可提示"已记录待优化" |
| 静态文件 | `agent/src/main/resources/static/index.html`，走现有 Spring MVC |
| 安全 | **v1.5（C1）**：`marked.js` 默认渲染 HTML，为防 LLM 输出被 prompt injection 诱导携带 `<script>`，渲染前对 LLM 回答做 HTML 转义（`<`→`&lt;` 等），再交给 `marked.parse`；或引入 `DOMPurify` 白名单净化。本地单用户场景低危，用最简转义即可 |

---

## 11. 错误处理策略

| 场景 | 行为 |
|---|---|
| LLM API 超时/异常 | 异常上抛 → **500**，前端提示"服务异常，请稍后重试"（不做静默降级） |
| **工具循环轮次失控** | **主防线 = 应用层轮次上限**：手动工具循环（§8），超过 `pf.search.max-tool-rounds`（默认 10）强制收敛作答 → **不再 500**（v1.9），确定性结束、线程不泄漏（forceAnswer 无工具单次调用必返回）。M6 框架 `while(hasToolCalls)` **无内建上限**、`ToolCallingManager` 无迭代控制（已反编译确认），单次 readTimeout 无法拦截"快速无限循环"（见下"双层防线"）。正常 DeepSeek 1-3 轮收敛 |
| 工具返回空结果 | 正常链路，LLM 自主决定重试/换工具/`reportDataGap` |
| 过滤字段错误 | `searchByMetadata` 返回可用字段清单，LLM 自纠 |
| 元数据过滤类型不匹配 | 所有扁平值统一存 String，过滤也传 String，类型一致 |

**双层防线：轮次上限 + 读超时（v1.4）**

已论证（反编译验证）：readTimeout 只作用于**单次 HTTP 请求**，而无限循环是"多个全都正常完成的请求的序列"——每轮 LLM 快速返回 tool_call、每轮都在超时内，超时永不触发。因此：

| 防线 | 拦截场景 | 参数 |
|---|---|---|
| **maxRounds（主）** | LLM 快速无限返回 tool_call | `pf.search.max-tool-rounds`（默认 10，超限强制收敛） |
| **readTimeout（辅）** | 单次 LLM 调用卡死（>60s 不返回） | `pf.search.chat-timeout`（默认 60s） |

readTimeout 实现（已确认链路：`OpenAiAutoConfiguration` 经 `ObjectProvider<RestClient.Builder>` 注入 → `OpenAiApi`；Spring Boot `RestClientAutoConfiguration` 自动应用 `ClientHttpRequestFactory` bean，无需覆盖 builder）：

```java
@Bean
public ClientHttpRequestFactory llmHttpRequestFactory(
        @Value("${pf.search.chat-timeout:60s}") Duration readTimeout) {
    var factory = new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(Duration.ofSeconds(10));   // 连接超时固定 10s
    factory.setReadTimeout(readTimeout);                 // 读超时 = 配置属性，默认 60s
    return factory;
}
```

- 该 factory 应用到所有 `RestClient.Builder` 调用（DeepSeek chat + Ollama embedding）；本地 Ollama 秒回，60s 对其无副作用
- 单轮 LLM 调用读超时 → `ResourceAccessException` → 上抛 → 500
- **关闭 RetryTemplate 重试**：Spring AI 默认 `spring.ai.retry.max-attempts=10`（已确认 `SpringAiRetryProperties` 默认值）且 `retryOn(TransientAiException)`——若超时被判为可重试，会把 60s 放大到 ~10 分钟才 500。application.yml 显式设 `spring.ai.retry.max-attempts: 1`（即不重试），超时立即 500

---

## 12. 配置变更（application.yml）

```yaml
pf:
  search:
    top-k: 5                 # 语义检索（现有）
    similarity-threshold: 0.5 # 语义检索（现有）
    enumeration-top-k: 500   # 新增：元数据枚举上限
    max-tool-rounds: 10      # 手动工具循环轮次上限（超限强制收敛作答，v1.9 起不再抛 500）
    max-history-chars: 50000 # 工具循环上下文字符上限，超限强制收敛作答（防 64K 超窗）
    vector-result-chars: 1500 # vectorSearch 单条正文截断长度（防注入膨胀）
    metadata-result-chars: 4000 # v1.9：searchByMetadata 紧凑列表字符上限，超限截断并提示收窄过滤
    chat-timeout: 60s        # 新增：单次 LLM 调用读超时（辅助防线，默认 60s）
    class-base-bonus: 0.03   # v1.8：class 基础职业页相似度加分（仅排序，不改 score）
    class-extra-candidates: 3 # v1.8：class 模块检索候选集扩容（topK + N，给加分重排留空间）
    intro-penalty: 0.03      # F-002：intro/reference 低信息量 chunk 排序减分（仅排序，置 0 关闭）
    filter-blank-text: true  # F-002：空 text chunk 剔除（空 embedding，置 false 关闭）
    oversize-penalty: 0.02   # F-002：oversize 超长 chunk 排序减分（超长 embedding 语义稀释）
    oversize-threshold: 5000 # F-002：oversize 判定阈值（text 字符数，超过才减分）
  gaps:
    file-path: ${user.home}/.pf_agent/data_gaps.jsonl  # 新增：数据缺口记录
  memory:
    history-size: 20         # 新增：会话历史注入条数上限
  stores:
    metadata-replay: false   # v1.6：spell 库 metadata 重放开关（置 true 启动执行一次，幂等，完成后改回 false）
spring:
  ai:
    retry:
      max-attempts: 1        # 新增：关闭 LLM 调用重试，避免超时被放大（默认 10 次）
```

---

## 13. 文件变更清单

**新建**

| 文件 | 职责 |
|---|---|
| `rag/RetrievalTools.java` | 3 个 `@Tool` 方法 |
| `rag/FilterTranslator.java` | 逻辑字段 → 扁平键翻译 |
| `rag/SourceCollector.java` | 请求级来源收集 + gap 标记 |
| `rag/DataGapRecorder.java` | 缺口 JSONL 追加 |
| `rag/SpellMetadataReplayTool.java` | **v1.6 新增**：一次性 metadata 重放工具（`@ConditionalOnProperty(pf.stores.metadata-replay)` 门控 CommandLineRunner），load 现有 spell 库 → 用新 mapper 重映射 metadata → 按 `chunk_id` join → 保留原 text+embedding 替换 metadata → save；缺键检测幂等（重放后启动自动跳过） |
| `rag/StandardChunk.java` | **v1.7 新增**：6 个标准模块（feat/race/trait/equipment/skill/rule）统一行模型 record，14 字段匹配 JSONL 顶部键 |
| `rag/StandardChunkMapper.java` | **v1.7 新增**：统一映射（顶部字段 1:1 → metadata，tocPath=chm_toc_path，aliases 逗号合并，null 安全） |
| `rag/FeatDataLoader.java` 等 6 个 | **v1.7 新增**：每模块 ~20 行 DataLoader 薄壳，共享 ChunkImporter + StandardChunkMapper |
| `docs/一期规则问答Agent决策链设计.md` | 本文档 |

**修改**

| 文件 | 改动 |
|---|---|
| `rag/SpellChunkMapper.java` | 扁平化 school/subschool/spell_level_*/has_spell_* |
| `rag/SearchService.java` | **v1.7 更新**：路由 map 扩展 8 库（spell/class/feat/race/trait/equipment/skill/rule），语义检索「all」跨 8 库召回合并；**v1.8 更新**：class 模块基础页加分重排 + 候选集扩容（`boostedScore`/`isBaseClassPage`）；**F-002 更新**：统一 `rankedScore()` 排序调整（空 text 剔除 + intro/reference 降权，`boostedScore` 收敛其中）；2026-08-16 起注入统一为 `@Autowired` 字段 + `@PostConstruct` 组装（构造器移除，规则见根 CLAUDE.md） |
| `rag/RetrievalTools.java` | **v1.7 更新**：VALID_MODULES 扩展 8 项，工具描述同步 |
| `rag/FilterTranslator.java` | **v1.7 更新**：availableFields/translate 新增 6 标准模块 case（translateStandard 共用） |
| `resources/application.yml` | **v1.7 更新**：新增 6 个 chunks 路径 + 6 个 stores 路径配置 |
| `rag/PromptBuilder.java` | 重写：去掉预检索注入，加工具引导 + Markdown 约束；**v1.8 更新**：新增"规则事实必须有检索依据 + 职业核心机制以基础页为准"两条约束 |
| `chat/ChatRequest.java` | 新增 `conversationId` 字段 |
| `chat/ChatResponse.java` | 新增 `gapReported`、`conversationId` 字段 |
| `chat/ChatController.java` | 透传 conversationId |
| `chat/ChatService.java` | **手动工具循环 + maxRounds 计数**、callbacksByName 工具注册表、手动 ChatMemory 注入/回存、SourceCollector 编排、conversationId 处理 |
| `config/AgentConfig.java` | `ChatMemory` bean + `ClientHttpRequestFactory` 超时 bean（**不再用** `MessageChatMemoryAdvisor`，ChatClient 无 defaultAdvisors） |
| `resources/application.yml` | enumeration-top-k、max-tool-rounds、max-history-chars、vector-result-chars、chat-timeout、retry、gaps、memory、metadata-replay 配置；**v1.8**：新增 class-base-bonus / class-extra-candidates |
| `resources/static/index.html` | 前端单页（B 档） |

---

## 14. 测试计划（TDD，先测试后实现）

| 测试类 | 覆盖 |
|---|---|
| `SpellChunkMapperTest` | 扁平键生成、无 spell_level 时无扁平键、类型统一 String |
| `SearchServiceTest` | `searchByMetadata`：className+level 翻译、className-only、school、未知字段、多条件 AND、大 topK |
| `SourceCollectorTest` | begin/add/drain/clear、gap 标记 |
| `DataGapRecorderTest` | JSONL 追加、含时间戳、文件创建 |
| `RetrievalToolsTest` | 3 个工具的输入→输出（mock SearchService/Recorder/Collector） |
| `PromptBuilderTest` | 重写：输出约束、工具引导、gap 指引 |
| `ChatServiceTest` | 重写：手动工具循环（hasToolCalls 迭代、工具执行、ToolResponseMessage 拼装）、**maxRounds 超限抛异常**、callbacksByName 注册表、手动 ChatMemory 注入/回存、sources 汇总、gapReported、conversationId（空→生成、传入→透传）、LLM null 兜底 |
| `ChatControllerTest` | **v1.5（B6）**：`POST /api/chat` 请求→响应 JSON 结构；conversationId 透传（请求带→响应回带；请求缺→自动生成）；`gapReported`/`sources` 字段序列化；500 场景（mock ChatService 抛异常）返回错误结构 |
| `SpellMetadataReplayToolTest` | **v1.6**：用临时 store 文件模拟旧库（metadata 无扁平键）+ 样例 chunks.jsonl → 重放后 metadata 含扁平键、text/embedding 原样保留、按 `chunk_id` join 正确；漂移告警（store 有而 jsonl 无的 chunk_id 计数）；幂等（重放后再跑跳过） |
| `StandardChunkMapperTest` | **v1.7**：统一字段 1:1 映射、chm_toc_path 缺失回退 doc_id+title、null 安全兜底、aliases 合并 |
| `SearchServiceTest` / `FilterTranslatorTest` / `RetrievalToolsTest` | **v1.7 更新**：新增 6 标准模块用例（路由、字段翻译、工具描述行为） |
| `PromptBuilderTest` / `SearchServiceTest` | **v1.8（AKN-003）**：新增"断言必须有检索依据 + 职业核心机制以基础页为准"prompt 约束断言；class 基础页加分重排（略低相似度基础页胜出 / 问变体不误伤 / 非 class 不加分 / 扩容 topK 透传） |
| `AgentApplicationTests` | 上下文启动含 ChatMemory bean + ClientHttpRequestFactory bean；**v1.7 更新**：6 个新 DataLoader 全部 @MockBean 隔离，避免 store 缺失时真实导入 22K chunks 阻塞集成测试 |

---

## 15. 端到端验证

> **验证状态（2026-08-01，本期交付时）**：
> - §15.1 ✅ 重放成功（4200 条替换，0 漂移）；改回 false 重启幂等跳过（0 条日志）
> - §15.2 ✅ 六题全过（枚举表格/子学派分类/语义数值/职业特性/豁免引用/虚构问题走 gap）
> - §15.3 ✅ 三轮多轮上下文通过（q3 结合"元素庇护主是伤害型"补控制建议）
> - §15.4 ✅ 91 测试全绿
> - 虚构问题 `彩虹独角兽飞升术` 诚实走 `reportDataGap`（gapReported=true），`data_gaps.jsonl` 记录含 question/attemptedFilters/reason/timestamp，无需人工兜底修正
> - 遗留：`~/.pf_agent/vector_store_spells.json.bak` 为重放前备份（确认无误后可清理）；dirty 职业名扁平键待 KN 登记（数据侧）

> **v1.8 补充（2026-08-11，AKN-003 修复验证）**：
> - 问法「女巫职业等级表+豁免+法术位」：不再顺带编造"自发施法"、不再标"推断"（A 规则①：检索未提供即不补全）；20 级截断数据明确标注"基于表格规律的推断"
> - 问法「女巫是准备施法者还是自发施法者」：有依据明确回答"准备施法者"（引用 APG 职业特性原文，B 方案加分让基础页 chunk 稳居检索）；如实区分灵脉守卫变体为自发施法（A 规则②）
> - 检索层：真实 bge-m3 复现三类基础问法，top5 基础页 1~3 → 3~4 个

1. **法术向量库 metadata 重放（方案 B，秒级）**：`application.yml` 置 `pf.stores.metadata-replay: true` → 启动 → `SpellMetadataReplayTool` load 现有库（4200 docs）→ 新 mapper 重映射 metadata → 按 `chunk_id` join → 保留 text/embedding 替换 metadata → save → 日志确认 `已重放 N 条` 与扁平键存在 → 改回 `false` 并重启验证幂等跳过（不再全量重建，仅当更换 embedding 模型或修改 chunk 正文时才需 30 分钟全量重建）
2. 问题集逐条验证（curl + 前端）：

| 问题 | 期望 |
|---|---|
| 女巫 1 环法术都有哪些 | Markdown 表格，含来源 |
| 咒法系有哪些法术 | 列表/表格，来源进折叠区 |
| 火球术的射程 | 准确数值 + 来源 |
| 女巫的巫术都有哪些 | 职业特性枚举 + 来源 |
| 油腻术的豁免检定是什么 | 纯法术/职业语义问题：语义检索 + 准确引用规则（v1.7：原 v1.5 A1 备注已失效——专长等 6 模块已接入，可用专长问题扩展验证面） |
| 一个完全虚构的规则问题 | 触发 `reportDataGap` → `gapReported=true`，`data_gaps.jsonl` 出现记录（v1.5 B5：虚构问题需**人工兜底**——LLM 可能直接编造而非诚实走 gap 工具，验收时需人工核对 `data_gaps.jsonl` 是否有记录，无记录则需微调 prompt 强化"查不到即上报"引导） |

3. **多轮上下文验证**（同一 conversationId 连续）：

| 轮 | 问题 | 期望 |
|---|---|---|
| q1 | 女巫 1 环有哪些法术 | 表格回答 |
| q2 | 女巫庇护主有哪些法术 | 能接住"女巫"语境 |
| q3 | 我选了元素庇护主，我一环选哪些法术来补充女巫的控制能力 | 结合前文 + 新事实，给出推荐 + 来源 |

4. 全量回归（`mvn test`，全部通过）
5. Git commit（含文档）

---

## 16. 技术风险与回退

| 风险 | 应对 |
|---|---|
| DeepSeek 函数调用兼容性 | OpenAI 兼容 API 原生支持 `tools`；若异常，工具调用报错即 500（可发现） |
| `Map<String,String>` 参数 schema | 已验证 `JsonSchemaGenerator` 生成 `additionalProperties` 对象 schema；若运行时不可用，回退为单个 JSON 字符串参数 |
| 纯"1环法术有哪些"（无职业） | v1 不支持精确枚举，提示需职业名，LLM 转 `vectorSearch`；后续可加通用 level 索引 |
| 法术库重建耗时 | **v1.6（方案 B）**：metadata 重放秒级完成（不重算向量，text 不变→embedding 不变，已确认现有库为 BGE-M3 1024 维）；仅更换 embedding 模型或修改 chunk 正文时才需 30 分钟全量重建 |
| 工具返回列表超长 | 工具紧凑摘要输出 + LLM 自然截断；必要时加输出长度上限 |
| 函数调用模式历史不含工具消息 | LLM 依赖 assistant 摘要或重查工具；q3 类多轮问题在 §15 专项验证 |
| InMemoryChatMemory 重启丢失 | 一期可接受；`ChatMemory` 接口预留文件持久化实现 |
| 工具循环无限迭代（无内建上限） | **已根除**：手动工具循环 + `pf.search.max-tool-rounds`（默认 15）超限即抛异常 → 500（确定性，线程不泄漏）；readTimeout（60s）仅兜"单次调用卡死" |
| **工具循环上下文膨胀（v1.5 B3）** | 每轮注入工具结果+LLM 输出，长循环下上下文可能逼近 DeepSeek 64K 上限 → 每轮 `assertHistorySize`（`pf.search.max-history-chars` 默认 50000）超限即抛异常 → 500，确定性与 maxRounds 一致 |
| **InMemoryChatMemory 并发（v1.5 C2）** | 一期单用户本地场景，同会话并发不会出现；跨会话由 conversationId 天然隔离。接多用户时需按会话加锁并考虑持久化迁移（见 §9.6） |
| **元数据 key 特殊字符（v1.5 C3）** | 职业/法术名可含 `·`/`（`/空格 等非 ASCII 字符，作为 filter 字段值直接传参一般安全（按值等值比较），但需在单元测试覆盖含特殊字符的检索用例；异常时由 §4 的字段清单+值回显自纠 |

---

## 17. 二期展望（本设计预留）

- 法术↔职业↔专长等跨模块关联：**v1.7 已完成基础面**——8 模块检索已通，后续可按需加组合查询/跨库推理类 `@Tool`
- 各标准模块 nested metadata 精确过滤（feat_type/race_name/slot 等）：当前仅 book+componentType，有诉求时可独立扩展 StandardChunkMapper 覆盖
- 规则路由兜底：作为 `@Tool`（router tool）接入，无需改框架
- `data_gaps.jsonl` 分析脚本 → 驱动工具面/数据迭代
- L2 长期记忆：用户事实抽取 + 档案 + 跨会话注入
