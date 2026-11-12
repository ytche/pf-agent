<!-- 归档：2026-11-11。本文为已批准的一期五项 Spec 开发实施计划源文件，按用户指示归档到 docs/superpowers/plans/；归档时依据合并记录、测试与真实验收证据将全部 Step 标记为完成。执行结果与证据见 docs/test-reports/测试报告_一期五项Spec收口_20261111.md。 -->

# 一期五项 Spec 开发实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按已确认 Spec 完成法术清单去重、大范围查询门禁、工程归因规范、元数据重放退出，以及前端多会话与引用展示改版。

**Architecture:** 使用三个串行交付波次，波次内以独立 worktree 和子 agent 并行。数据侧产物仍是唯一事实源；Java 只消费产物，不新增第二套数据处理路径。主会话负责接口契约、共享文件归属、合并、真实环境验收和文档销账。

**Tech Stack:** Python 3 / pytest；Java 17 / Spring Boot / Spring AI / JUnit；PostgreSQL 16 / Flyway / Testcontainers；Vue 3 / TypeScript / Vite / Pinia / Vitest / Playwright。

---

## Context

输入 Spec：

1. `docs/superpowers/specs/2026-11-10-f025-spell-list-deduplication-design.md`
2. `docs/superpowers/specs/2026-11-10-f026-broad-query-narrowing-gate-design.md`
3. `docs/superpowers/specs/2026-11-10-f012-attribution-and-artifact-versioning-design.md`
4. `docs/superpowers/specs/2026-11-10-dvg001-remove-spell-metadata-replay-design.md`
5. `docs/superpowers/specs/2026-11-11-f020-f022-frontend-implementation-design.md`
6. 前端唯一 UI 基线：`docs/superpowers/specs/2026-11-03-f020-frontend-final-design.md`

当前基线：主分支 `dev/pf-agent`，工作区干净；最近验证为数据侧 1848 passed、构建检查 14/14。执行时重新跑基线，不能把历史数字当作本轮证据。

## Approach

### 交付拓扑

| 波次 | 并行 lane | 工作内容 | 合并前置 |
|---|---|---|---|
| Wave 0 | 主会话 | 基线、worktree、公共契约和任务台账 | 无 |
| Wave 1 | A/B/C/D | A=F-025 Python；B=F-025 Java；C=F-012 文档；D=DVG-001 | A+B 都评审后集成；C/D 可独立合并 |
| Wave 2 | E/F | E=F-026 工具与提示词；F=F-026 V6 事件 | 主会话先提供事件接口；E+F 都评审后集成 |
| Wave 3 | G/H | G=F-020/F-022 后端；H=前端与构建 | Wave 2 已合并，V6 已存在；G+H 都评审后集成 |
| Final | 主会话 | 全量测试、真实问答、浏览器、文档与销账 | 全部实现合并 |

每个 lane 使用 `.worktrees/<lane>` 和功能分支。子 agent 只能修改分配文件；共享文档 `docs/一期当前待办与问题汇总_临时.md`、`docs/项目文档总索引.md`、`PROJECT_HANDOVER.md` 由主会话在集成时统一更新。不得 push 或操作正式 8080 实例。

### 并行规则

- 一个文件同一时刻只能有一个 owner；接口依赖先由主会话提交最小契约，再并行实现。
- 每个子 agent 先写失败测试，再实现，跑聚焦测试并提交；主会话做代码审查和集成验证。
- 独立 tester 子 agent 在实现后做黑盒与白盒复核；Critical/Important 必须修复后重验。
- 新发现问题只登记，不顺手扩范围。内容类源数据修改仍需用户单独审批；本计划不需要此类修改。

## Key changes

### Task 0：基线、隔离区与执行台账（主会话）

**Files:**
- Create: `.worktrees/` 下各 lane（gitignored）
- Modify: 无源码

- [x] **Step 1：确认主工作区干净并跑基线**

```bash
cd /Users/chezi/code/java/pf_agent/pf_agent/agent
mvn test -B
cd /Users/chezi/code/java/pf_agent/pf_data/phase1
python3 -m pytest vectorizer/tests -q
python3 -m vectorizer.build check
```

Expected：Java、Python 全绿，构建 14/14 通过；若有失败先登记环境或既有问题，不将失败基线当成新回归。

- [x] **Step 2：建立 Wave 1 worktree**

```bash
cd /Users/chezi/code/java/pf_agent
git worktree add .worktrees/f025-data -b feat/f025-data dev/pf-agent
git worktree add .worktrees/f025-java -b feat/f025-java dev/pf-agent
git worktree add .worktrees/f012-docs -b feat/f012-docs dev/pf-agent
git worktree add .worktrees/dvg001 -b feat/dvg001-replay-removal dev/pf-agent
```

- [x] **Step 3：为数据 worktree 准备 gitignored 产物**

```bash
cp -R pf_data/phase1/vectorizer/output .worktrees/f025-data/pf_data/phase1/vectorizer/output
```

Expected：复制后数据基线全绿；不得把 output 加入 Git。

- [x] **Step 4：派单时附 Spec、文件 owner、红线和验证命令**

每个子 agent 的 prompt 必须含：Spec 路径、worktree 绝对路径、允许修改文件、禁止改共享汇总、TDD 要求、提交要求、已知未覆盖点报告格式。

### Task 1：F-025 Python 去重产物（lane A）

**Files:**
- Modify: `pf_data/phase1/spell_list_union_export.py`
- Test: `pf_data/phase1/vectorizer/tests/test_spell_list_union_export.py`
- Modify: `pf_data/phase1/vectorizer/build_manifest.json`
- Regenerate: `pf_data/phase1/vectorizer/state/build_state.json`
- Regenerate locally: `vectorizer/output/法术/spell_lists_union.json`、`spell_list_union_report.json`

- [x] **Step 1：先写纯函数失败测试**

新增可单测的 `fold_entries(entries)` 契约：输入同职业同环级的官方/派生条目，输出折叠组。测试必须覆盖中文命中、英文命中、传递合并、官方内部重复、主来源和 `matched_by`。

```python
def test_any_key_fold_preserves_all_sources_and_primary():
    entries = [
        {"cn": "自然之道", "en": "Nature's Paths", "book": "COMP",
         "chunk_id": "spell_a", "source": "derived"},
        {"cn": "自然之路", "en": "Nature’s paths", "book": "COMP",
         "chunk_id": "spell_b", "source": "derived"},
    ]
    groups = fold_entries(entries)
    assert len(groups) == 1
    assert [s["chunk_id"] for s in groups[0]["sources"]] == ["spell_a", "spell_b"]
    assert groups[0]["sources"][1]["matched_by"] == "derived_en"
```

同时写官方交叉、官方内部重复、空英文占位、数量守恒和冲突报告测试。

- [x] **Step 2：运行聚焦测试并确认失败**

```bash
cd pf_data/phase1
python3 -m pytest vectorizer/tests/test_spell_list_union_export.py -q
```

Expected：因 `fold_entries` 不存在或新字段缺失而失败；不得跳过。

- [x] **Step 3：实现保守归一、传递折叠和报告**

导出器中实现：

```python
def fold_entries(entries):
    parent = list(range(len(entries)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[b] = a

    seen = {}
    for i, entry in enumerate(entries):
        for kind, key in (("cn", _norm_cn(entry.get("cn", ""))),
                          ("en", _norm_en(entry.get("en", "")))):
            if not key:
                continue
            if (kind, key) in seen:
                join(i, seen[kind, key])
            else:
                seen[kind, key] = i

    groups = {}
    for i in range(len(entries)):
        groups.setdefault(find(i), []).append(i)

    folded = []
    for members in groups.values():
        official = [i for i in members if entries[i]["source"] == "official_list"]
        primary_index = official[0] if official else members[0]
        ordered = [primary_index] + [i for i in members if i != primary_index]
        sources = []
        source_keys = set()
        for i in ordered:
            entry = entries[i]
            if entry["source"] == "official_list":
                matched_by = "official_primary"
            elif i == members[0] and not official:
                matched_by = "derived_new"
            else:
                peers = [entries[j] for j in members if j < i]
                peer = next(p for p in peers if _same_identity(entry, p))
                prefix = "official" if peer["source"] == "official_list" else "derived"
                cn_hit = bool(_norm_cn(entry.get("cn", "")) and
                              _norm_cn(entry.get("cn", "")) == _norm_cn(peer.get("cn", "")))
                en_hit = bool(_norm_en(entry.get("en", "")) and
                              _norm_en(entry.get("en", "")) == _norm_en(peer.get("en", "")))
                matched_by = prefix + ("_cn_and_en" if cn_hit and en_hit else
                                       "_cn" if cn_hit else "_en")
            source = {
                "book": entry.get("book", ""),
                "chunk_id": entry.get("chunk_id"),
                "source": entry["source"],
                "matched_by": matched_by,
            }
            if entry.get("level_evidence") is not None:
                source["level_evidence"] = entry["level_evidence"]
            source_key = (source["chunk_id"], source["source"])
            if source_key not in source_keys:
                source_keys.add(source_key)
                sources.append(source)

        primary = dict(entries[primary_index])
        primary["sources"] = sources
        primary["matched_by"] = sources[0]["matched_by"]
        folded.append(primary)
    return folded
```

```python
def _same_identity(a, b):
    cn_a, cn_b = _norm_cn(a.get("cn", "")), _norm_cn(b.get("cn", ""))
    en_a, en_b = _norm_en(a.get("en", "")), _norm_en(b.get("en", ""))
    return bool(cn_a and cn_a == cn_b) or bool(en_a and en_a == en_b)
```

导出器保留完整连通命中明细供冲突报告使用，不能只保留上面的摘要 matched_by。

实现必须以实际代码完整完成上述契约，不在 Java 再补去重。保留 `kn246_duplicate_level_candidates`，`spell_lists.json` 字节不变，union/report 版本升级 1.1，manifest `expected=1.1`。

- [x] **Step 4：重建并验证真实产物**

```bash
cd pf_data/phase1
python3 -m pytest vectorizer/tests/test_spell_list_union_export.py -q
python3 -m vectorizer.build lists.spell_union --force
python3 -m vectorizer.build check
```

Expected：测试全绿；女巫 1 环 205→165（68 官方 + 97 派生，40 个派生副本折叠）；`diff_unclassified=0`；OA 五职业零派生；构建 14/14。保存全量 per_class_level 新旧计数与来源对账报告，逐职业逐环检查，不只验女巫。

- [x] **Step 5：全量回归并提交 lane**

```bash
python3 -m pytest vectorizer/tests -q
git add spell_list_union_export.py vectorizer/tests/test_spell_list_union_export.py vectorizer/build_manifest.json vectorizer/state/build_state.json
git commit -m "feat(f025): 数据侧折叠法术清单重复来源"
```

### Task 2：F-025 Java 消费与分页（lane B）

**Files:**
- Modify: `pf_agent/agent/src/main/java/com/pfagent/agent/rag/SpellListService.java`
- Test: `pf_agent/agent/src/test/java/com/pfagent/agent/rag/SpellListServiceTest.java`
- Modify if tool text requires: `pf_agent/agent/src/main/java/com/pfagent/agent/rag/RetrievalTools.java`

- [x] **Step 1：写 1.1、1.0 和降级失败测试**

固化 1.0 fixture；1.1 fixture 含 official/derived 和 sources。核心断言：

```java
@Test
void union11ReadsFoldedEntriesWithoutAppendingOfficialTwice() throws Exception {
    SpellListService service = loadedWithUnion(Fixtures.union11Json());
    String result = service.formatLevel("法师", 1, 10_000, 0, 50);
    assertThat(result).contains("共 2 条", "[PSP/COMP]");
    assertThat(result).doesNotContain("3. 燃烧之手");
}
```

另测 `levelOverview`、`levelTotal`、footer 同数；union 缺失、畸形、未知版本、缺 sources 降级官方；1.0 保留旧行为并警告。

- [x] **Step 2：确认新测试失败**

```bash
cd pf_agent/agent
mvn -Dtest=SpellListServiceTest test
```

Expected：1.1 字段/版本/多书断言失败，旧测试应继续通过。

- [x] **Step 3：实现版本化读取与统一条目序列**

模型增加 `UnionSource` 和 `UnionEntry.sources`；`UnionFile` 读取 version。1.1 直接读完整 levels；1.0 走旧官方+derived；概览与分页共享同一序列。书缩写按 sources 去重，主来源 derived 才显示〔派生〕。

- [x] **Step 4：运行聚焦和 Java 全量测试**

```bash
mvn -Dtest=SpellListServiceTest test
mvn test -B
```

Expected：全绿，0 新增跳过。

- [x] **Step 5：提交 lane**

```bash
git add src/main/java/com/pfagent/agent/rag/SpellListService.java src/test/java/com/pfagent/agent/rag/SpellListServiceTest.java
git commit -m "feat(f025): Java消费去重清单与多来源"
```

若实际修改 RetrievalTools，提交中加入该文件及对应测试。

### Task 3：F-012 工程规范落地（lane C）

**Files:**
- Create: `docs/templates/问题归因与变更验收模板.md`
- Modify: `docs/WORKFLOW.md`
- Modify: `CLAUDE.md`
- Modify: `pf_agent/agent/docs/Agent功能TODO.md`
- Modify: `docs/项目文档总索引.md`
- 主会话集成时修改：一期临时汇总

- [x] **Step 1：按 Spec 写模板和角色检查点**

模板正文必须含六段：登记、分层排证、修复、构建、消费、闭环。KN/AKN 条目是唯一事实源，模板不创建第二份问题实例。示例使用 KN108 与 AKN-003 的真实源路径。

WORKFLOW 明确：architect/轻量主 Agent 查分层，coder 交构建消费证据，tester 查原问题和实例，主 Agent 缺项打回。

- [x] **Step 2：更新短指针和 F-012 源 TODO**

根 CLAUDE 只加一条红线和模板/WORKFLOW 指针。F-012 改为已落地，链接 Spec 和模板；不得把模板全文复制进 CLAUDE。

- [x] **Step 3：验证文档与构建状态**

```bash
git diff --check
cd pf_data/phase1
python3 -m vectorizer.build status
```

Expected：无文档格式错误；本批不产生新 stale；不需要重建产物。

- [x] **Step 4：提交 lane**

```bash
git add docs/templates/问题归因与变更验收模板.md docs/WORKFLOW.md CLAUDE.md pf_agent/agent/docs/Agent功能TODO.md docs/项目文档总索引.md
git commit -m "docs(f012): 落地问题分层与版本闭环模板"
```

### Task 4：DVG-001 删除重放写路径（lane D）

**Files:**
- Delete: `pf_agent/agent/src/main/java/com/pfagent/agent/rag/SpellMetadataReplayTool.java`
- Delete: `pf_agent/agent/src/test/java/com/pfagent/agent/rag/SpellMetadataReplayToolTest.java`
- Create: `pf_agent/agent/src/main/java/com/pfagent/agent/rag/DeprecatedMetadataReplayGuard.java`
- Test: `pf_agent/agent/src/test/java/com/pfagent/agent/rag/DeprecatedMetadataReplayGuardTest.java`
- Modify: `pf_agent/agent/src/main/resources/application.yml`
- Modify: `pf_agent/agent/src/main/java/com/pfagent/agent/telemetry/TelemetryImporter.java`
- Modify: `docs/DEPLOYMENT.md`
- Modify: `docs/数据一致性技术债务登记.md`
- Modify: `docs/已知问题记录_agent.md`
- Modify: `pf_agent/agent/docs/一期规则问答Agent决策链设计.md`

- [x] **Step 1：写闸口失败测试**

```java
@Test
void legacyReplayPropertyFailsWithReloadInstructions() {
    DeprecatedMetadataReplayGuard guard = new DeprecatedMetadataReplayGuard();
    assertThatThrownBy(guard::run)
        .hasMessageContaining("SpellMetadataReplayTool 已删除")
        .hasMessageContaining("docs/DEPLOYMENT.md");
}
```

增加缺失/false 不装配、最高优先级和 spy runner 顺序测试；spy 必须证明 guard 抛异常后 DataLoader runner 未调用，不能用既有 store 字节不变冒充证据。

- [x] **Step 2：确认测试失败后实现闸口并删除旧工具**

```java
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
@ConditionalOnProperty(name = "pf.stores.metadata-replay", havingValue = "true")
public class DeprecatedMetadataReplayGuard implements CommandLineRunner {
    @Override
    public void run(String... args) {
        throw new IllegalStateException(
            "SpellMetadataReplayTool 已删除；请移除 pf.stores.metadata-replay=true，"
            + "并按 docs/DEPLOYMENT.md 的 chunks 全量重灌流程处理。");
    }
}
```

删除 replay 类和测试；移除现役 yml 配置说明；TelemetryImporter 改通用一次性开关注释。

- [x] **Step 3：新增 DEPLOYMENT 全量重灌章节**

写清备份、同 `user.home`/store 路径、临时实例、对账、失败回滚、正式实例、真实问答和备份保留。命令必须含实际模块示例，不得只写原则。

- [x] **Step 4：同步历史注记**

DVG-001 验证后清偿；DVG-002 标注重放仅为历史操作；AKN-011 保留 merge 历史并注明工具退役；决策链设计的现役指引改全量重灌。

- [x] **Step 5：验证并提交**

```bash
cd pf_agent/agent
mvn -Dtest=DeprecatedMetadataReplayGuardTest test
mvn test -B
```

再做默认启动和旧配置 true 的真实进程验证；本批不重灌向量库。

```bash
git add -A
git commit -m "refactor(dvg001): 删除元数据重放第二写路径"
```

### Task 5：F-026 公共事件契约（主会话，先于 Wave 2 并行）

**Files:**
- Create: `pf_agent/agent/src/main/java/com/pfagent/agent/rag/QueryGateEventRecorder.java`
- Create: `pf_agent/agent/src/main/java/com/pfagent/agent/telemetry/QueryGateEventService.java`
- Modify: `pf_agent/agent/src/main/java/com/pfagent/agent/rag/ToolCallTracker.java`
- Test: `pf_agent/agent/src/test/java/com/pfagent/agent/rag/QueryGateEventRecorderTest.java`

- [x] **Step 1：写无上下文和持久化委托的失败测试**

```java
@Test
void missingRequestContextSkipsPersistence() {
    QueryGateEventRecorder recorder = recorderWithoutRequestContext();
    recorder.record("searchByMetadata", "rule", "book_only", false, Map.of());
    verifyNoInteractions(queryGateEventService);
}
```

另写 JDBC 服务存在时收到 `BLOCKED/ALLOWED`、请求级 conversationId/question 和序列化 query_json 的测试。

- [x] **Step 2：运行测试并确认缺少契约**

```bash
cd pf_agent/agent
mvn -Dtest=QueryGateEventRecorderTest test
```

Expected：因 RequestContext、QueryGateEventService 或 recorder 行为缺失而失败。

- [x] **Step 3：提交完整公共契约**

`ToolCallTracker` 增加：

```java
public record RequestContext(String conversationId, String question) {
}

public RequestContext currentContext() {
    SessionState state = current.get();
    return state == null ? null : new RequestContext(state.conversationId(), state.question());
}
```

`QueryGateEventService` 定义为接口：

```java
public interface QueryGateEventService {
    void persist(String conversationId, String question, String toolName,
                 String module, String eventType, String reason,
                 String queryJson, Instant now);
}
```

`QueryGateEventRecorder` 完整实现：

```java
@Component
public class QueryGateEventRecorder {
    private static final Logger log = LoggerFactory.getLogger(QueryGateEventRecorder.class);

    @Autowired
    private ObjectProvider<QueryGateEventService> eventServiceProvider;
    @Autowired
    private ToolCallTracker toolCallTracker;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public void record(String toolName, String module, String reason,
                       boolean allowed, Object query) {
        ToolCallTracker.RequestContext context = toolCallTracker.currentContext();
        if (context == null) {
            return;
        }
        try {
            String queryJson = objectMapper.writeValueAsString(query);
            QueryGateEventService service = eventServiceProvider.getIfAvailable();
            if (service == null) {
                log.warn("查询门禁事件服务不可用，跳过本次事件");
                return;
            }
            service.persist(context.conversationId(), context.question(), toolName, module,
                    allowed ? "ALLOWED" : "BLOCKED", reason, queryJson, Instant.now());
        } catch (JsonProcessingException e) {
            log.warn("查询门禁参数序列化失败，跳过事件", e);
        } catch (RuntimeException e) {
            log.warn("查询门禁事件写入失败，主流程继续", e);
        }
    }
}
```

- [x] **Step 4：验证并提交契约后再开 E/F worktree**

```bash
mvn -Dtest=QueryGateEventRecorderTest test
git add src/main/java/com/pfagent/agent/rag/QueryGateEventRecorder.java \
  src/main/java/com/pfagent/agent/rag/ToolCallTracker.java \
  src/main/java/com/pfagent/agent/telemetry/QueryGateEventService.java \
  src/test/java/com/pfagent/agent/rag/QueryGateEventRecorderTest.java
git commit -m "feat(f026): 固定查询门禁事件契约"
cd /Users/chezi/code/java/pf_agent
git worktree add .worktrees/f026-tools -b feat/f026-tools HEAD
git worktree add .worktrees/f026-events -b feat/f026-events HEAD
```

E/F 不得各自修改公共契约；确需变更时停下来由主会话评审。

### Task 6：F-026 工具门禁与提示词（lane E）

**Files:**
- Modify: `rag/MetadataSearchQuery.java`
- Modify: `rag/ListEntriesQuery.java`
- Create: `rag/BroadQueryGuard.java`
- Modify: `rag/SearchService.java`
- Modify: `rag/RetrievalTools.java`
- Modify: `rag/PromptBuilder.java`
- Tests: `rag/RetrievalToolsTest.java`、`RetrievalToolsListEntriesTest.java`、`ListEntriesQueryTest.java`、`RetrievalToolsToolSchemaTest.java`、`SearchServiceTest.java`、`PromptBuilderTest.java`

- [x] **Step 1：写行为矩阵失败测试**

覆盖 Jackson 缺省/false/true；无条件、仅书、多书 OR、书+条件、keyword-only、空白 keyword、仅分页；未放行不调用 SearchService/ListExportService；放行后无条件查询；校验失败无事件；每页带 true。

```java
@Test
void bookOnlyMetadataIsBlockedBeforeSearch() {
    MetadataSearchQuery query = new MetadataSearchQuery();
    query.setFilters(Map.of("book", "CRB"));
    String result = retrievalTools.searchByMetadata("rule", query);
    assertThat(result).contains("book_only", "allowBroadQuery=true");
    verify(searchService, never()).searchByMetadataPaged(any(), any());
}
```

既有 record 构造补新组件；仅书格式化测试显式放行；无条件旧文案断言改门禁建议。

- [x] **Step 2：实现统一判定和参数**

`BroadQueryGuard` 返回 `broad/reason`；`allowBroadQuery` 不计入 `hasAnyCondition()`。参数校验先于门禁，门禁只处理 `no_conditions/book_only`。listEntries 无条件未放行仍返回概览。

- [x] **Step 3：实现无条件服务路径和稳定排序**

无用户过滤表达式时使用 null filter，而非跳过；单库 topK 仍为 500。新增无条件路径默认 `title → module → chunk_id`，显式排序追加 module/chunk_id 兜底；不改既有条件查询默认序。

- [x] **Step 4：实现提示词建议和确认规则**

PromptBuilder 明确跨/单模块宽查询先建议、2～4 个有效示例、已有概览和原范围继续；首次明确全量也先建议；小集合不拦；确认后每页携带 true，改业务条件重新判断。

- [x] **Step 5：验证并提交**

```bash
mvn -Dtest='*Metadata*,*ListEntries*,RetrievalTools*,SearchServiceTest,PromptBuilderTest' test
mvn test -B
git add src/main src/test
git commit -m "feat(f026): 增加大范围枚举门禁与放行"
```

### Task 7：F-026 V6 持久化事件（lane F）

**Files:**
- Create: `src/main/resources/db/migration/V6__query_gate_event.sql`
- Create: `telemetry/QueryGateEventEntity.java`
- Create: `telemetry/QueryGateEventRepository.java`
- Create: `telemetry/JdbcQueryGateEventService.java`
- Tests: `telemetry/JdbcQueryGateEventServiceTest.java`、`rag/QueryGateEventRecorderTest.java`；公共契约已有 `ToolCallTrackerTest` 变更由主会话补齐

- [x] **Step 1：写事件失败测试**

覆盖 BLOCKED/ALLOWED、reason、query_json、请求级 question（翻页可为“继续”）、无 begin 跳过、memory/异常不阻断、非宽查询不写事件。

- [x] **Step 2：实现 V6 与 telemetry**

```sql
CREATE TABLE query_gate_event (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL,
  conversation_id VARCHAR(36) NOT NULL,
  question TEXT NOT NULL,
  tool_name VARCHAR(64) NOT NULL,
  module VARCHAR(32) NOT NULL,
  event_type VARCHAR(16) NOT NULL,
  reason VARCHAR(32) NOT NULL,
  query_json JSONB NOT NULL
);
CREATE INDEX idx_query_gate_event_conv_time
  ON query_gate_event(conversation_id, created_at);
```

实现 Entity/Repository 和 `JdbcQueryGateEventService implements QueryGateEventService`，复用 JDBC 条件装配和编程式事务。公共 RequestContext/accessor 已在 Task 5 固定，本 lane 不修改 ToolCallTracker；不得让 LLM 传 conversationId/question。

- [x] **Step 3：验证并提交**

```bash
mvn -Dtest='*QueryGate*,*ToolCallTracker*' test
mvn test -B
git add src/main src/test
git commit -m "feat(f026): 持久化查询门禁事件"
```

### Task 8：Wave 1/2 集成与真实验收（主会话）

- [x] **Step 1：审查并本地合并各 lane**

按 F-025 data → F-025 java → F-012 → DVG-001 → F-026 contract → F-026 events → F-026 tools 顺序处理冲突；每次合并跑相关聚焦测试。不得 push。

- [x] **Step 2：F-025 真实消费验证**

union 是独立 JSON，不重灌向量库；重启临时消费者，确认 union 1.1 已加载。真实提问“女巫 1 环法术有哪些”，分页取全 165，无重复、无漏项、多书可见，引用仍为列表页汇总。

- [x] **Step 3：F-026 真实对话验证**

依次验证：

1. “CRB 里所有类型的规则条目”先建议，无条目检索、无来源编号、`gapReported=false`；
2. “CRB 所有专长，完整列出”仍先建议；
3. “仍按原范围查询”后携带放行执行；
4. “武僧清规有哪些”不触发；
5. 改书或业务条件后重新判断；
6. capped 时不宣称真实全量；
7. JDBC 写事件成功，memory/写库失败主流程不受影响。

在加载新产物的临时实例（计划端口 18080）上执行现有问答评测：

```bash
cd /Users/chezi/code/java/pf_agent/pf_agent/agent
python3 qa/evaluate.py \
  --base-url http://localhost:18080 \
  --items qa/pf_qa_items.json \
  --report-dir qa/out_five_specs_wave12_20261111
```

Expected：溯源 ≥52/53、诚实 ≥50/53、结构均值 ≥2.89；清单期望数量按去重后口径复核，不能为保旧数字改实现。

- [x] **Step 4：文档同步**

闭环 F-025、F-026、F-012、DVG-001；F-025 同时收口 KN-247 QA-2/QA-3。更新 F/AKN/KN/DVG 源文档、一期汇总、总索引、README/DEPLOYMENT 和测试报告。按当前计数逐项递减，不用历史数字覆盖新状态。

### Task 9：F-020/F-022 后端统一会话（lane G，V6 合并后）

- [x] **Step 0：确认 V6 已合并并建立 Wave 3 worktree**

```bash
cd /Users/chezi/code/java/pf_agent
test -f pf_agent/agent/src/main/resources/db/migration/V6__query_gate_event.sql
git worktree add .worktrees/f020-backend -b feat/f020-backend HEAD
git worktree add .worktrees/f020-frontend -b feat/f020-frontend HEAD
```

Expected：V6 文件存在；两个 worktree 都从包含 F-026 的同一 HEAD 创建。

**Files:**
- Create: `memory/ConversationStore.java`
- Create: `memory/ConversationContracts.java`
- Create: `memory/JdbcConversationStore.java`
- Create: `memory/InMemoryConversationStore.java`
- Modify: `memory/JdbcChatMemory.java`、实体和 Repository
- Create: `src/main/resources/db/migration/V7__conversation_snapshots.sql`
- Modify: `chat/ChatService.java`、`chat/ChatController.java`
- Create: `conversation/ConversationController.java`、`conversation/ConversationService.java`
- Modify: `config/AuthInterceptor.java`、`config/WebConfig.java`
- Modify: `pom.xml`（Testcontainers PostgreSQL）
- Tests: memory/chat/conversation/config 对应测试

- [x] **Step 1：先定义 Store 契约与失败测试**

```java
public interface ConversationStore {
    void create(String conversationId, Long ownerUserId, Instant now);
    List<Message> history(String conversationId, int lastN);
    ConversationContracts.Detail get(String conversationId);
    ConversationContracts.Page list(Long ownerUserId, String cursor, int limit);
    ConversationContracts.Page lookupAnonymous(List<String> ids, String cursor, int limit);
    ConversationContracts.WriteResult append(ConversationContracts.Exchange exchange);
    ConversationContracts.WriteResult replaceLastAssistant(
        String conversationId, int expectedLastSeq,
        ConversationContracts.AssistantSnapshot snapshot);
    void rename(String conversationId, String title);
    void setPinned(String conversationId, boolean pinned);
    void delete(String conversationId);
    ConversationContracts.ClaimResult claim(Long ownerUserId, List<String> ids);
    int generationAttempts(String conversationId);
    int incrementGenerationAttempts(String conversationId);
}
```

`ConversationContracts` 在同一文件中定义：

```java
public final class ConversationContracts {
    private ConversationContracts() {
    }

    public record ConversationSummary(String id, String title, boolean pinned,
                                      Long ownerUserId, Instant lastActiveAt) {
    }

    public record Page(List<ConversationSummary> items, String nextCursor, boolean hasMore) {
    }

    public record MessageSnapshot(Long id, int seq, String role, String content,
                                  List<ChatResponse.SourceRef> sources,
                                  boolean gapReported, Instant createdAt) {
    }

    public record Detail(ConversationSummary summary, List<MessageSnapshot> messages) {
    }

    public record AssistantSnapshot(String answer, List<ChatResponse.SourceRef> sources,
                                    boolean gapReported, Instant completedAt) {
    }

    public record Exchange(String conversationId, Long ownerUserId, String question,
                           AssistantSnapshot assistant, Instant now) {
    }

    public enum WriteStatus { WRITTEN, NOT_FOUND, DELETED, CONFLICT }

    public record WriteResult(WriteStatus status) {
    }

    public record ClaimResult(int claimed, List<String> rejectedIds) {
    }
}
```

两种 Store 实现执行同一契约测试，并验证 `WRITTEN/NOT_FOUND/DELETED/CONFLICT` 的映射。

- [x] **Step 2：实现 V7 和 Store**

V7 增加 title、pinned、owner_user_id、generation_attempts、sources JSONB、gap_reported 和索引；owner 外键 `ON DELETE SET NULL`。generation_attempts 用 `total_rounds` 回填。列表和 lookup 只显示 `message_rounds>0`。

删除 `JdbcChatMemory.doAdd` 的 orElseGet 自动重建；所有写路径父行缺失即不写入。内存实现同时支持 ChatMemory 和配额计数。

pom 新增 Testcontainers PostgreSQL 测试依赖并锁定版本；PG16 测试验证 V5→V6→V7、JSONB、FK、SET NULL 和配额回填。

- [x] **Step 3：实现问答与重生成写入**

ChatService 在 cited-only 过滤和编号重映射后，将当轮完整响应 sources/gapReported 与助手消息一起写入。失败不写不完整问答。

重生成排除旧助手上下文，成功后按 expectedLastSeq+assistant 条件替换同一消息 ID；不改 totalRounds/messageRounds。普通问答和重生成在模型调用前增加 generation_attempts 并过匿名配额；冲突 409，删除 410，失败保留旧回答。

- [x] **Step 4：实现 API 与权限**

实现终态设计的 conversation endpoints。AuthInterceptor 在 auth 开启时：无 token 可匿名，非法 token 401；WebConfig 把 `/api/conversations/**` 纳入鉴权和限频。

owner 为空时匿名 UUID 可访问，登录用户 403 须显式认领；owner 非空仅所属账号，匿名/他账号 404。认领幂等且不覆盖他账号。晚到删除返回 410，从未存在 404。

- [x] **Step 5：验证并提交**

```bash
mvn -Dtest='*Conversation*,*ChatService*,*ChatMemory*,*AuthInterceptor*,*WebConfig*' test
mvn test -B
git add pom.xml src/main src/test
git commit -m "feat(f020): 统一会话存储与引用快照"
```

### Task 10：F-020/F-022 前端与构建（lane H）

**Files:**
- Create: `pf_agent/agent/frontend/package.json`、lockfile、Vite/TS/Playwright 配置
- Create: `frontend/src/api/`、`stores/`、`components/`、`views/`、`types/`
- Modify: `.gitignore`
- Modify: `pf_agent/agent/src/main/resources/application.yml`（与主会话协调，Wave 3 独占）
- Delete after replacement verified: `src/main/resources/static/index.html`
- Modify: `.github/workflows/agent-ci.yml`
- Modify: `pf_agent/agent/Dockerfile`
- Modify: `README.md`、`docs/DEPLOYMENT.md`

- [x] **Step 1：建立工程和静态服务失败验证**

配置 Vite 输出 `../src/main/resources/static/dist`，hash 路由、API 代理、npm scripts。根 controller forward 到 dist/index.html 由 lane G 或主会话明确 owner，不能两边重复修改。

先写构建/页面测试，再实现 AppShell、ConversationView、Composer 和 API client。`.gitignore` 加 node_modules/dist。

- [x] **Step 2：实现 Pinia 与多会话交互**

Pinia 管理消息、分页、请求、未读、账号、匿名 ID 和认领。覆盖后台完成、切换、20 轮、失败重试、401/409/410/429、退出清缓存；同会话只在前端禁并发。

- [x] **Step 3：实现消息、来源和标错**

按 UI 基线实现 MessageList/MessageItem、SourceCards、FeedbackForm、AuthDialog。来源默认 3 张、展开全部、上标定位；历史消息使用自己的 ID/时间/快照。marked+DOMPurify 白名单，来源纯文本，外链 noopener。

核心测试示例：

```ts
it('expands sources and locates the cited card', async () => {
  renderConversationWithSources(5)
  expect(visibleSourceCards()).toHaveLength(3)
  await clickCitation(4)
  expect(visibleSourceCards()).toHaveLength(5)
  expect(sourceCard(4)).toHaveClass(/highlighted/)
})
```

- [x] **Step 4：接入 CI 与 Docker**

agent-ci 先 setup-node、npm ci、Vitest/build，再 Maven；Playwright 使用真实 Spring + Testcontainers PG + 打桩 ChatModel，不在 PR 调 DeepSeek/Ollama。

Dockerfile 增加 Node 构建阶段，把 frontend build 生成的 dist 放入 Maven 构建上下文；JRE 运行阶段不变。不得提交 dist。

- [x] **Step 5：验证并提交**

```bash
cd pf_agent/agent/frontend
npm ci
npm test -- --run
npm run build
npx playwright test
```

Expected：前端单测、构建和打桩浏览器测试全绿；手机与桌面均覆盖。

```bash
git add frontend ../src/main/resources/static ../src/main/resources/application.yml Dockerfile
git commit -m "feat(f020): 落地多会话前端与引用卡片"
```

工作流/README/DEPLOYMENT 若由主会话归属，则在提交前交给主会话修改，避免共享文件冲突。

### Task 11：最终集成、评审与销账（主会话）

- [x] **Step 1：全分支代码评审与 tester 独立复核**

每个 lane 先审 Spec 覆盖，再由 tester 做黑盒真实调用、测试代码审计和边界补测。Critical/Important 清零；Minor 按用户拍板登记或修复。

- [x] **Step 2：执行完整验证矩阵**

```bash
cd pf_data/phase1
python3 -m pytest vectorizer/tests -q
python3 -m vectorizer.build check

cd ../../pf_agent/agent
mvn test -B

cd frontend
npm ci
npm test -- --run
npm run build
npx playwright test
```

另跑 Testcontainers PG16 的 V5→V6→V7 迁移、JSONB/FK/SET NULL/配额回填测试。不得用 H2 替代。

- [x] **Step 3：真实 Agent 冒烟**

在临时实例执行：

1. 女巫 1 环分页取全 165；
2. F-026 首次建议、确认放行、改条件重新判断；
3. 武僧清规正常回答；
4. 默认配置正常问答，metadata-replay=true 明确失败；
5. 匿名→登录认领→跨设备读取→退出清缓存；
6. 删除进行中会话返回 410 且不复活；
7. 重生成失败保留旧回答，成功替换且对话轮数不变；
8. 历史来源默认 3 张、展开与上标定位正确。

真实模型只跑上线前 1～2 条核心冒烟，CI 保持打桩；两者结果分别报告。

- [x] **Step 4：文档和待办销账**

更新五份 Spec 的实施状态、源 F/AKN/KN/DVG、一期临时汇总、总索引、README、DEPLOYMENT、PROJECT_HANDOVER 和测试报告索引。

若全部闭环，汇总从当前 13 功能+18 问题/债务（31 项）变为：

- F-025、F-026、F-012、F-020、F-022 五项功能移出：13→8；
- KN-247 QA 后续和 DVG-001 两项问题/债务移出：18→16；
- 最终剩余 **8+16=24 项**。

只有实际闭环的条目才能移除；任何未完成项保留，不能用上述目标数倒推状态。

- [x] **Step 5：清理与交付**

确认 `git status` 干净，删除无未提交改动的临时 worktree 和功能分支；保留测试证据，删除临时响应/日志。汇报提交、测试、真实验收、已知限制和剩余待办；不 push，由用户决定后续发布或分支处理。

## Verification

### 每 lane 最低证据

- 失败测试先于实现的记录；
- 聚焦测试和全量测试命令、退出码与结果；
- 改动文件清单、Spec 覆盖、已知未覆盖点；
- 数据/消费变更的构建状态与真实实例身份；
- 文档与源状态同步。

### 全局不可降级门槛

- 女巫 1 环为 165，无重复、分页无漏项、来源不膨胀；
- 门禁首次不检索、确认后放行、500/capped 不变；
- replay 写库能力不存在，旧配置 true 不会触发其他 runner；
- 引用快照与响应一致，删除不复活，重生成不覆盖冲突消息；
- 真实 PG 迁移、前端构建、打桩浏览器和真实 Agent 冒烟分别通过；
- 不以编译、导入、截图或 mock 单独宣称端到端完成。

## Assumptions

- 用户已明确选择子 agent 并行，因此采用 subagent-driven development，不再询问 inline/subagent 执行方式。
- 默认本地合并到 `dev/pf-agent`，不 push；任何正式发布仍由用户执行。
- 每项实施默认使用 `.worktrees/` 隔离，无需逐次询问。
- F-026 必须先于 F-020/F-022 合并，以占用 V6；V7 不提前抢占。
- F-020/F-022 的服务端并发锁明确不做；仅前端禁同会话并发，重生成保留 expectedLastSeq 终态校验。
- 认证开启时允许匿名是用户已确认的安全语义变化；非法 JWT 仍 401。
- 删号后 owner 置空、会话转匿名是用户已确认的隐私取舍。
- 现有常驻实例和用户向量库不在开发过程中触碰；真实验证使用临时实例。
- 本计划不需要内容类源数据审批；若实施发现需要修改规则语义，暂停并单独请求审批。
