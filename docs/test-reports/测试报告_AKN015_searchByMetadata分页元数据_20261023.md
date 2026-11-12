# 测试报告：AKN-015「searchByMetadata 分页元数据补全」

- 日期：2026-10-23
- 测试者：tester（独立于 coder）
- 被测改动：工作区未提交改动（`git status`：SearchService.java / RetrievalTools.java / application.yml / RetrievalToolsTest.java / SearchServiceTest.java），基线 commit `0b60c2d`
- 结论：**有条件通过（不建议直接关单）**——分页提示本身工作正常且真实会话验证有效，但存在 1 个 Major：`enumeration-top-k=500` 截断被当作"真实总数"输出，模型已原样采信并对外宣称错误总数。

---

## 1. 测试对象与范围

| 项 | 内容 |
|---|---|
| 被测 | `SearchService.searchByMetadataPaged` + `PagedResult(totalCount/offset/limit/hasMore)`；`RetrievalTools` J2 工具改走 paged；`formatCompact` 分页提示 |
| 设计/需求来源 | `docs/已知问题记录_agent.md` AKN-015；coder 交付说明（573 全绿，修复 1 处漏改 verify、1 处 stub 分页参数不一致、2 处过期注释） |
| 不在范围 | 向量召回质量、prompt 硬约束（上一 commit `0b60c2d` 已单独验收）、其他工具 |

## 2. 测试设计

| 类别 | 用例数 | 说明 |
|---|---|---|
| coder 新增用例审计 | 5（+2 处旧用例改造） | 逐个判断断言强度 |
| tester 补充单测（新增文件） | 19（12 + 7，其中 2 个 `@Disabled` 记录缺陷） | 见 §4 |
| 黑盒-工具层（真实向量库 + Ollama bge-m3） | 8 个探针场景 | 走真实 spell store（4172 chunks），打印工具真实输出文本 |
| 黑盒-端到端（真实服务 + DeepSeek） | 3 轮真实提问 | 8091 端口独立实例 |
| 真实数据真值核对 | 5 项 | 直接从 `chunks.jsonl` 统计作为 ground truth |

真实数据真值（从 `pf_data/phase1/vectorizer/output/法术/chunks.jsonl` 统计，共 4172 条法术）：
女巫 1 环 = **143**；女巫任意环 = **1007**；school=变化系 = **611**；book=COMP = **1489**；塑能系 = 267。

## 3. 黑盒测试结果

### 3.1 工具层（真实向量库，进程内探针）

| 用例 | 预期 | 实际 | 结论 |
|---|---|---|---|
| 女巫 1 环（AKN-015 原始场景，limit=50） | 总数 143；字符截断提示带真实区间与 next offset | `total=143`；尾部提示 `…（共 143 条，本次返回第 1~35 条，has_more=true；续取：…query.offset=35）` | ✅ |
| 女巫 1 环 offset=50（第二页） | 区间 51 起，next offset 动态 | `…（共 143 条，本次返回第 51~85 条，has_more=true；…query.offset=85）`，pageSize=93，hasMore=false | ✅ |
| 完整结果（spell title=火球术，2 条） | 无任何分页提示 | 输出仅两行紧凑列表，无 `has_more`/`query.offset` | ✅ |
| 女巫任意环（真实 1007） | 应报 1007 或明确标注上限 | `total=500`，输出 `共 500 条`，hasMore=false | ❌ **Major（观察项①）** |
| book=COMP（真实 1489） | 同上 | `total=500` | ❌ 同上 |
| offset=500（越界） | 应提示"已翻完/共 N 条" | `无命中。建议：减少一个过滤条件（如去掉 book）…` | ⚠️ **Minor（观察项③）** |
| 翻页稳定性（offset=0/limit=500 与 offset=100/limit=100 对拍） | 第二页 == 第一页子区间，且重复调用顺序一致 | `page2==page1[100:200]=true`、`repeat identical order = true`、distinctPage1=500 | ✅ |

> 说明：上述探针用 `@SpringBootTest(pf.chat.memory=memory，七个非 spell 库路径指向空文件 + DataLoader mock)` 加载真实 spell 向量库，真实 Ollama bge-m3 向量化，直接调用 `RetrievalTools.searchByMetadata` 打印返回文本（即 LLM 实际看到的字符串）。

### 3.2 端到端（真实服务 + DeepSeek，端口 8091 独立实例，`PF_CHAT_MEMORY=memory`）

启动：`SERVER_PORT=8091 PF_CHAT_MEMORY=memory PF_TOOLS_FILE_PATH=/tmp/pf_probe/tool_calls.jsonl mvn -o spring-boot:run`；`/api/health` = OK。用毕已停进程、8091 已释放（未触碰 8080 常驻实例）。

| 用例 | 预期 | 实际 | 结论 |
|---|---|---|---|
| E2E-1「女巫的 1 环法术有哪些？请尽量完整列出」 | 走 searchByMetadata 并顺提示翻页 | 模型改走 `getSpellList{className:女巫, level:1}`（68 条官方列表），未触发本次改动路径；回答无编造 | ⚠️ 路由差异（需求澄清项 a） |
| E2E-2「女巫能用的所有变化系法术有哪些？请尽量完整列出」 | 拿到"共 176 条"后按 offset 续取、不编造 | 工具链：`limit=200` 首次；随后**严格按提示** `offset=36 → 72 → 109 → 145`，共 5 次；回答开头即写"共命中 **176 条**（分 5 页翻完，无遗漏）"，末页 145+31=176 完整，无编造补齐 | ✅ **修复目标达成** |
| E2E-3「数据库里一共有多少条变化系法术？用元数据检索统计」 | 报真实 611 | 回答第一行："**总数：500 条**（检索工具在每次返回中都标注"共 500 条"…）"；真实 611；并自行推断"第 390–500 条未能取到" | ❌ **Major（观察项①）**：模型把 `共 500 条` 当事实转述给用户 |

E2E-2 的 tool_calls 原文（`~/.pf_probe` 隔离落盘）：
```
1 searchByMetadata {"module":"spell","query":{"filters":{"className":"女巫","school":"变化系"},"limit":200}} chars=4071
2 searchByMetadata {... "limit":200,"offset":36}} chars=4026
3 ... "offset":72  4 ... "offset":109  5 ... "offset":145 (末页无提示 → 停止)
```
E2E-3 翻页到 `offset=349` 后因 `max-tool-rounds=10` 收敛，模型明确声明未取到的区间，未编造。

### 3.3 三个行为面复核（要求项）

| 行为面 | 结论 | 证据 |
|---|---|---|
| ① 字符截断提示含真实总数与动态 offset | ✅（单模块 ≤500 条时） | 143 场景 `第 1~35 条 / offset=35`；第二页 `第 51~85 条 / offset=85`；E2E-2 五次续取 offset 全对 |
| ② limit 静默截断（无字符截断）也出提示 | ✅ | 单测 `searchByMetadataLimitTruncatedWithoutCharCapAlsoHints`（coder）+ tester 的 `secondPageHintRangeAndNextOffsetFollowOffset`（无字符截断、offset=10） |
| ③ 完整结果无提示 | ✅ | 单测 `searchByMetadataCompleteResultHasNoPaginationHint`（coder）+ tester `lastPageCompleteHasNoHint`/`exactSinglePageHasNoHint` + 真实库 `火球术` 2/2 输出无提示 |

## 4. 白盒审计结果

### 4.1 coder 测试代码审计

| 项 | 结论 |
|---|---|
| 是否存在无断言/注释掉/永远通过的测试 | 未发现无断言或注释掉断言；新增 5 例均有断言 |
| `RetrievalToolsTest:502` 字符截断提示例 | **断言偏弱（真测试但会漏 bug）**：仅 `containsPattern("本次返回第 1~\\d+ 条")` + `containsPattern("query\\.offset=\\d+")`。若 `next_offset` 退化为常量 0，`query.offset=0` 同样匹配 → 用例仍绿，而生产上会"原地打转"无限翻页。未断言 next_offset 与"实际展示条数"一致，也未断言确实发生了截断（shown<10） |
| `:524` limit 静默截断例 | ✅ 强断言（`共 10 条` / `第 1~3 条` / `offset=3` 精确值） |
| 完整结果无提示例 | 基本可用；只断言 `doesNotContain("has_more")`，未断言 `query.offset` 也不出现（tester 补强） |
| `SearchServiceTest` 新增 2 例 | ✅ 真断言 totalCount=3 / page=2 / hasMore 翻转；缺 offset 越界、负 offset 钳制、limit 钳制三类边界 |
| coder 自述"修复 1 处漏改 verify" | 已核对：`RetrievalToolsTest` 中残留的 `searchService.searchByMetadata(...)` stub/verify（L63/96/111/201/218/225）均属**旧 Map 重载**路径，与实现一致，无漏改 |
| 覆盖盲区（相对本次改动） | 第二页提示（offset≠0）、最后一页提示缺失、offset 越界、负 offset 钳制、`limit<=0` 钳制、`hasMore()` 边界、旧 Map 重载兼容、字符截断停止点不前进 → 均已补测 |

### 4.2 tester 补充测试（新增文件，未改动被测实现与 coder 用例）

- `src/test/java/com/pfagent/agent/rag/RetrievalToolsPaginationAuditTest.java`（12 例，2 例 `@Disabled` 记录缺陷）
  - 第二页提示区间/next_offset 随 offset 前移；末页完整无提示；恰好单页无提示；字符截断第一页/第二页/末页的**内部一致性不变量**（`终点 == next_offset == offset + 展示条数`，展示条数用行数正则实测）——这条可直接抓住"next_offset 恒 0"的退化；旧 Map 重载完整/截断两种兼容行为；`hasMore()` 六种边界；负 offset 提示不出现"第 0~"
  - `@Disabled` 两例分别固化缺陷②（`第 X~X-1 条` + offset 不前进）与缺陷③（越界返回"无命中"），修复后去掉注解即可作为回归门禁
- `src/test/java/com/pfagent/agent/rag/SearchServicePagedAuditTest.java`（7 例）
  - offset==totalCount、offset>totalCount 返回空页但 totalCount 保留且 hasMore=false；负 offset 钳制为 0 且当页从首条开始；`limit=10000` 被钳到 500 但 totalCount 不受影响；`limit=0` 钳为 1；旧签名委托与 `page()` 等价；空结果 totalCount=0

### 4.3 运行结果

```
mvn -o test   →  Tests run: 592, Failures: 0, Errors: 0, Skipped: 2   BUILD SUCCESS
                 （coder 基线 573 + tester 新增 19；2 skipped 为上述 @Disabled 缺陷记录）
```

## 5. 缺陷清单

| 编号 | 级别 | 描述 | 复现步骤 |
|---|---|---|---|
| AKN015-T1 | **Major** | `enumeration-top-k=500` 截断被当作"真实总数"：`totalCount = docs.size()` 取的是 store 已按 topK=500 截断后的条数。真实 611 条变化系法术，工具输出"共 500 条"且 `has_more=false`，DeepSeek 在回答首行宣称"总数：500 条"并据此推断"390–500 条取不到"。同类：女巫任意环 1007→500，book=COMP 1489→500。这属于 AKN-015 同类危害（错误总数被当事实输出），不是"观察项"级别 | 见 §3.1 / §3.2 E2E-3；本报告 §2 有真值 |
| AKN015-T2 | Minor | 字符上限小于单行长度（shown==0）时提示为"本次返回第 X~X-1 条"且 `query.offset=X`（不前进）→ 模型原地重试；实测输出 `…（共 10 条，本次返回第 1~0 条，has_more=true；续取：…query.offset=0）`。默认 4000 下几乎不可达，但配置调小或单条元数据超长即触发（探针证据已留存） | 单测 `zeroShownShouldNotEmitDegenerateRangeAndStuckOffset`（@Disabled） |
| AKN015-T3 | Minor | offset 越界（==total 或 >total）时工具返回"无命中。建议：减少一个过滤条件…"，对翻页场景属误导（数据并非缺失）。与 T1 叠加时（offset=500 仍有数据）会直接误导 | 单测 `offsetBeyondTotalShouldTellExhaustedInsteadOfNoHit`（@Disabled）；真实库 `offset=500` 探针 |
| AKN015-T4 | Minor | 旧 Map 重载（非 @Tool）复用了 `formatCompact`，其提示文案"保持其他参数不变，query.offset=Z"对该签名不成立（该重载无 query/offset 参数）；且 totalCount 传的是当页大小，语义与新版不一致 | `searchByMetadata("spell", Map.of("book","CRB"))`，字符上限调至 300 时输出 `共 50 条 … query.offset=N` |
| AKN015-T5 | Minor（既存） | `formatCompact` 用 `ids.get(i-1)` 取来源编号：若调用方未 `sourceCollector.begin()`（如直接调用工具类的非 Web 场景），`collector.add` 返回空列表 → `ArrayIndexOutOfBoundsException`，而非可读错误。生产路径 `ChatService.ask` 入口有 `begin()`，本次已被真实触发一次（探针首版未 begin 即崩） | 直接构造 `RetrievalTools` 调 `searchByMetadata`，不调用 `collector.begin()` |
| AKN015-T6 | Info | 分页提示后模型会翻多页，整页 Document 全部 `collector.add`（最多 500）→ `ChatResponse.sources` 显著变大（实测 173 条）。既存行为，但分页修复会放大触发概率，建议评估 sources 上限 | E2E-2 响应 sources=173 |
| AKN015-T7 | Info（测试层） | coder 用例 `:502` 的 next_offset 断言过弱（见 §4.1），存在漏 bug 风险；已由 tester 不变量用例补足，建议 coder 顺手收紧 | 代码审阅 |

## 6. 5 个观察项处置建议

| # | 观察项 | tester 判断 | 建议 |
|---|---|---|---|
| ① | enumeration-top-k=500 导致真实总数被低估，且翻不到 500 以后 | **够 Major，需立即处理**（已在真实会话中造成"总数：500 条"的错误输出） | 二选一：a) totalCount 与分页基于**未截断**过滤结果计数（可只 count 不取 doc，或按 1000+ topK 取 id 计数）；b) 保留 500 上限，但提示文案改为"已返回前 500 条（已达到检索上限，实际总数可能更多），可用 book/level 等进一步收窄"——绝不能输出"共 N 条"式假总数，并需同步修 `has_more` 语义（当前 500 时 hasMore=false，模型据此认定"已全取"） |
| ② | shown==0 → "第 X~X-1 条"且 offset 不前进 | Minor（默认配置不可达），但一旦触发即死循环 | 加防御：shown==0 时至少输出首条（突破字符上限一次）或改成"结果单条过长，请用 getEntryById(chunk_id=…) 查看" |
| ③ | offset 越界返回"无命中"误导 | Minor（模型严格循提示不会越界），但与 ① 叠加会放大误导 | 区分："已翻完（共 N 条，offset 已到末尾）" vs "无条件命中"；实现成本低，建议与 ① 一起修 |
| ④ | 旧 Map 重载带 offset 提示但不接受 offset | Minor，无需立即处理 | 生产侧无 LLM 调用路径（仅测试/内部）；建议 `@Deprecated` 并让该重载不计提示（或提示里去掉 query.offset 指引） |
| ⑤ | `hasMore()` 仅测试使用 | 不构成问题 | 但 `PagedResult.hasMore()` 与 `formatCompact` 内联公式 `offset+docs.size()<totalCount` 是两处同义逻辑，存在漂移风险 → 建议工具层改用 `paged.hasMore()`（可维护性 Minor） |

## 7. 结论与建议

- **有条件通过**：核心修复（提示含真实总数 + 区间 + has_more + 动态 next_offset）在单模块 ≤500 条结果时行为正确，真实 DeepSeek 会话中已能顺着提示翻完 5 页、报出正确总数 176 且不编造；`mvn test` 592 全绿。
- **放行前必须处理**：AKN015-T1（Major）。它会在最常见的"宽枚举"问法下把错误总数交给用户，与 AKN-015 的验收意图（模型不编造/不误导）直接冲突。
- **建议同批处理**：T3（与 T1 同源，文案分叉点相同）、T5（防御，成本低）。
- 可延后：T2、T4、T6、T7。
- 验收关注点：修 T1 后需回归本报告 §3.1/§3.2 的 3 个总数场景（611 / 1007 / 1489），并确认 `has_more` 在达到检索上限时的正确语义。

## 8. 需求澄清项

1. **"总数"口径**：检索存在 500/库 的硬上限时，产品希望输出"真实总数"（需改计数方式）还是"已达上限，至少 N 条"（需改文案）？
2. **首问路由**：`女巫的 1 环法术` 实测模型优先走 `getSpellList`（官方列表 68 条），而元数据路径统计为 143 条；AKN-015 原始现象发生在元数据路径。两个口径（官方列表 vs 元数据标注）是否需要产品明确谁为准、是否要在 prompt 里规定优先序？
3. **旧 Map 重载**是否还有生产调用方？确认无则建议 `@Deprecated`/删除，避免继续分叉行为。
4. **sources 上限**：翻页场景下单请求 sources 可达数百条，前端/接口是否有上限要求？

---

### 附：验证用进程与数据清理

- 8091 实例已停止（`kill` + 端口校验为空），8080 常驻实例未触碰。
- 运行时产物隔离在 `/tmp/pf_probe/`（tool_calls.jsonl、app8091.log、resp1-3.json），未污染 `~/.pf_agent`。
- 临时探针测试类（`TmpLiveToolProbeTest`、`TmpPaginationProbeTest`）已删除；仓库仅新增 2 个 tester 审计测试文件。

---

## 第二轮复验（coder 返修 T1 + T3 后，2026-10-23）

### 结论

**通过**（可放行）。T1/T3 修复有效且方向诚实：宽枚举场景不再输出任何"共 N 条"假总数，真实 DeepSeek 会话明确回答"无法给出准确总数 / 至少 389 条 / 不能推断为 500 / 不能凭记忆补足"；cap 内翻页与未触 cap 场景（143）行为与修复前逐字一致。遗留 3 项 Minor（均为文案一致性/边缘指引），不阻塞放行。

### 本轮改动审阅

- `SearchService`：`hits.size() >= enumerationTopK` → `capped=true`，`PagedResult` 扩为 6 字段（`capped`/`cap`），保留 4 参兼容构造（`capped=false, cap=0`）。
- `RetrievalTools`：capped 分支输出诚实版（`已达检索上限 500 条（实际命中可能更多）…`，末页追加 `本工具最多只能取前 500 条，请收窄…`），零"共 N 条"；`docs.isEmpty()` 内新增 T3 三态分叉；提示触发统一 `paged.hasMore()`（全仓已无内联公式残留）。

### 逐场景复核（真实 spell 向量库 4172 chunks + 真实 bge-m3）

| 场景 | PagedResult | 工具输出（尾部） | 结论 |
|---|---|---|---|
| 变化系（真实 611） | total=500 capped=true cap=500 | `…（已达检索上限 500 条（实际命中可能更多），本次返回第 1~38 条，has_more=true；续取：…query.offset=38）` | ✅ 无假总数 |
| 女巫全环（真实 1007） | total=500 capped=true | 同上形态，`第 1~34 条…offset=34` | ✅ |
| book=COMP（真实 1489） | total=500 capped=true | `第 1~41 条…offset=41` | ✅ |
| 女巫 1 环（真实 143，未触 cap） | total=143 capped=false | `…（共 143 条，本次返回第 1~35 条，has_more=true；…query.offset=35）` | ✅ 与修复前逐字一致 |
| cap 内翻页 limit=200 p1/p2 | offset 0 / 200 | `第 1~38 条…offset=38` / `第 201~240 条…offset=240` | ✅ next_offset 正确且不越 500 |
| cap 末页 offset=400/limit=200 | page=100, hasMore=false | `第 401~440 条，has_more=true…offset=440；本工具最多只能取前 500 条，请收窄…` | ⚠️ 见 N2 |
| T3 uncapped 越界（offset=143） | page 空, total=143 | `已翻完全部结果（共 143 条）` | ✅ |
| T3 capped 越界（offset=500, capped） | page 空, total=500 | `已翻完工具可返回的前 500 条（已达检索上限，实际命中可能更多），请收窄过滤条件…` | ✅ |
| 真无数据（offset=0 与 offset=5） | total=0 | `无命中。建议：减少一个过滤条件…` | ✅ 未误报"已翻完" |

**端到端（真实服务 8092 + DeepSeek）**：「数据库里一共有多少条变化系法术？」→ 模型 10 轮工具调用严格按提示 `offset 0→38→76→114→153→192→231→270→310→349`（从未越过 500），结论："**未能取到准确总数**；至少 389 条；真实总数大于 389，**不能据 500 上限推断为 500，也不能凭记忆补足**"。对照上一轮同题："总数：500 条"——T1 已闭环。

### 白盒复核

| 检查项 | 结论 |
|---|---|
| capped 判定位置 | 在 `bookFilter` / 去重**之前**（`hits.size() >= enumerationTopK`）。语义：保守方向——原始 500 命中被书过滤到 200 时仍标 capped，宁可说"可能更多"也不谎报精确总数。已用单测 `cappedDetectedBeforeBookFilter` 固化（300 条 `?` + 200 条 CRB → capped=true、totalCount=200） |
| 499/500 边界 | `≥` 判定：499→false、500→true（独立复测通过） |
| 6 字段兼容 | 4 参构造 `capped=false, cap=0`，旧文案形态保留；生产侧仅旧 Map 重载使用（见 N5） |
| `hasMore()` 单一真值源 | `grep` 确认 `RetrievalTools` 已无 `offset + docs.size() < totalCount` 内联公式，仅 `paged.hasMore()` |

### 本轮新发现问题（均为 Minor，不阻塞）

| 编号 | 级别 | 描述 | 证据 |
|---|---|---|---|
| AKN015-N1 | Minor | **跨库 capped 且 merged totalCount > cap 时文案自相矛盾**：`module=all` 某一库饱和（spell 645 条 > 500）时，输出 `已达检索上限 500 条…本次返回第 501~503 条；本工具最多只能取前 500 条`；T3 capped 越界同理（`已翻完工具可返回的前 800 条`）。单模块不可达，`all` + book=CRB 类查询可达 | `RetrievalToolsCappedHintAuditTest.crossModuleCappedTotalBeyondCapShouldNotClaimCapBoundary`（@Disabled 记录）；`SearchServicePagedAuditTest.cappedIfAnyStoreSaturates`（capped + totalCount=503） |
| AKN015-N2 | Minor | **capped 末页 + 字符截断同时给"续取 offset=X"与"请收窄"**，指引矛盾（真实会话中模型据此提前收口作答）。应由"是否还有未展示条目"而非"是否还有下一页"决定给收窄 | `…offset=440；本工具最多只能取前 500 条，请收窄…`（真实库 offset=400/limit=200）；`cappedTruncatedLastPageShouldPreferContinuationOverNarrowing`（@Disabled） |
| AKN015-N3 | Minor | capped 判定 `>=` 无法区分"恰好 500 条"与">500 条"：真实恰好 500 条也永远显示"实际命中可能更多"，且拿不到精确数。保守方向无害，建议文案改为"最多返回前 500 条（已达单库检索上限）" | `SearchServicePagedAuditTest.cappedFlagBoundaryAt499And500` |
| AKN015-N5 | Minor（既存） | 旧 Map 重载（非 @Tool）用 4 参构造，**丢弃 capped**：宽枚举时仍输出"共 500 条"假总数。非 LLM 路径，无用户面影响，但与新语义不一致 | 代码审阅 `RetrievalTools:200-203` |
| AKN015-T2 | Minor（未修，既存） | shown==0（字符上限小于单行）仍输出"第 1~0 条"且 offset 不前进 | 保留 `@Disabled` |

### coder 新增测试审计（8 新增 + 1 启用）

- 真断言，无假测试：capped 三要素、`doesNotContain("共 500 条")`、offset 越界两态、cap 内两页区间均为精确值断言。
- 缺口（已由 tester 补 13 例）：① 负向断言只锁字面量"共 500 条"，未锁任意"共 N 条"（已补正向正则 `共 \d+ 条` 不存在）；② 未覆盖 capped 判定在 bookFilter 之前（已补）；③ 未覆盖 `totalCount==0` 且带 offset 的真无数据分叉（已补）；④ 未覆盖 4 参兼容构造语义（已补）；⑤ 未覆盖跨模块 capped 文案矛盾（已补，@Disabled）。
- 我上一轮审计文件中 T3 的 `@Disabled` 用例被启用移除（改为 `RetrievalToolsTest` 内启用版），本轮已在 `RetrievalToolsCappedHintAuditTest` 重建三态覆盖。

### 本轮 mvn 结果

```
mvn -o test → Tests run: 613, Failures: 0, Errors: 0, Skipped: 3   BUILD SUCCESS
              (coder 600 + tester 新增 13；3 skipped = T2 + N2 + N1 的缺陷记录用例)
```

### 复验用进程清理

8092 实例已停止（端口校验为空），8080/8091 未触碰；探针类（`TmpCappedProbeTest` / `TmpDefectProbeTest`）已删除；运行时产物隔离在 `/tmp/pf_probe2/`。
