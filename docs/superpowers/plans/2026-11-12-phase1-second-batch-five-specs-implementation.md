# 一期第二批五项问题开发计划

## Context

五项问题已完成方案讨论并各自成 Spec，本计划把 Spec 转成可并行执行的开发任务。
目标是修掉唯一 P1（AKN-025）、刚上线门禁的绕过路径（AKN-024）、评测判分失真（AKN-026）、
标题展示缺陷（F-002/KN-204/KN-219），并为耗时优化取得测量数据（AKN-023）。

Spec 文件：
- `docs/superpowers/specs/2026-11-11-akn025-equipment-price-sorting-design.md`
- `docs/superpowers/specs/2026-11-12-akn024-broad-query-allowance-fingerprint-design.md`
- `docs/superpowers/specs/2026-11-12-akn026-honesty-scoring-llm-fallback-design.md`
- `docs/superpowers/specs/2026-11-12-f002-kn204-kn219-title-display-fallback-design.md`
- `docs/superpowers/specs/2026-11-12-akn023-latency-instrumentation-design.md`

## Approach

按**文件边界**拆 4 条工作流，各自在隔离 worktree 开发（沿用既定约定），独立评审后合并。
编排原则：同一文件只由一条 lane 修改；真实模型验证与全量测试统一收口，不在 lane 内重复执行。

| Lane | 内容 | 主要改动面 | 可并行性 |
|---|---|---|---|
| L1 | AKN-025 数据侧清单补全 | `pf_data/phase1/equipment_list_export.py` 等数据脚本 | 完全独立 |
| L2 | AKN-026 评测判分 + 新增评测题 | `pf_agent/agent/qa/`（`evaluate.py`、`test_evaluate.py`、`pf_qa_items.json`、`tool_calls_report.py`） | 完全独立；qa 目录只此一条 lane |
| L3 | AKN-025 Java price 排序 + AKN-024 门禁指纹 | `ListExportService`、`FilterTranslator`、`ListEntriesQuery`、`BroadQueryGuard`、`RetrievalTools` | 与 L1 按 schema 约定并行；内部顺序执行 |
| L4 | 标题展示兜底 + AKN-023 埋点 | `ChatResponse.SourceRef`、`ChatService`、`ToolCallRecord`、`ToolCallRecorder` | 在 L3 合并后开发，避免 `ChatService` 冲突 |

**合并顺序**：L1、L2 先行（互不冲突）→ L3（检索工具链）→ L4（展示层 + 埋点）。

**跨 lane 契约**：L1 与 L3 以 `price_gp` schema 和一条固定夹具条目为准
（力量法杖 `price_gp=235000`、`chunk_id=equipment_page_222_0000`），L3 可先用夹具开发，不等 L1 完成。

L3 内部顺序：先 price 排序，再门禁指纹。
L4 内部顺序：先标题展示兜底，再埋点。

## Key changes

### L1 — AKN-025 数据侧清单补全

- 解析全部以价格表形式存在的装备类别（法杖/权杖/戒指/奇物/药水/卷轴/魔杖等），
  书范围与现有清单一致，生成清单条目。
- 每条目保留 `price` 原文，新增可空整数 `price_gp`；解析失败置 null，条目保留并计入报告。
- 条目 `chunk_id` 必须指向来源价格表 chunk（溯源口径依赖这一点）。
- 无标价条目保留但不参与排序。
- 导出报告新增：各类目条目数、`price_gp` 解析成功/失败计数与失败样本。
- 验证：数据侧 pytest + `build check`；力量法杖条目存在且 `price_gp=235000`、
  `chunk_id=equipment_page_222_0000`。

### L2 — AKN-026 评测诚实性判分 + 新增评测题

- `evaluate.py`：词表命中仍直接判 1；`gap=true` 且未命中词表时调 LLM 兜底，默认启用、按需调用。
- LLM 判分标准二分：承认数据不足且无来源不编造 → 1；无来源给确定结论/具体数值 → 0。
- LLM 调用失败记 **待复核**，不记 0，汇总单独计数。
- `qa_report.json` 保存 `gapReported` 原始值与判定依据（命中词/LLM 理由/待复核原因）。
- 新增 2-3 道同类题（最贵戒指、指定书最贵法杖、价格区间）入 `pf_qa_items.json`，
  题目断言依赖 L1/L3 的实际行为，故在 L2 收尾阶段编写。
- `qa/tool_calls_report.py` 对 L4 新增的耗时字段保持向后兼容（旧记录无字段不得报错）。
- 验证：`test_evaluate.py` 新增正负与失败路径用例；用 medium-17 run3 实际文本做回归。

### L3a — AKN-025 Java price 排序

- `ListEntry` 增加 `price_gp`（`@JsonProperty("price_gp")`），`price` 原文保留。
- 排序开放 `price`（映射 `price_gp`）+ 升降序；过滤新增 `price_min`/`price_max`（gp）。
- `price_gp=null` 条目排最后，不进入“最高价”结论。
- 旧清单文件无 `price_gp` 时的降级行为需显式定义并写测试，不得静默给出错误排序。
- 工具描述写清：价格字段可用、单位 gp、仅统计有标价条目。
- 验证：相关模块单测（排序/过滤/null 位置/旧文件降级），不跑全量。

### L3b — AKN-024 门禁指纹

- 服务端按会话记录放行指纹，**指纹只含 module + book**。
- `allowBroadQuery=true` 且指纹一致 → 放行（含同条件翻页）；不一致 → 忽略标记、退回收窄建议并更新指纹。
- 状态存内存，随会话生命周期，重启失效。
- `RetrievalTools` 当前**拿不到 conversationId**，需新增请求级会话上下文传递；
  禁止退化为全局单例。实施第一步先确认该传递路径，若线程模型不允许需上报再定方案。
- V6 `query_gate_event` 增加“指纹不匹配被驳回”的可观测记录，不新建表。
- 验证：单测覆盖匹配/换模块/换书/翻页/无会话上下文；
  真实模型同会话复现 3 次放到整批统一验证环境执行。

### L4a — 标题展示兜底

- 在 `ChatService.toSourceRef` / `ChatResponse.SourceRef` 组装处统一处理：
  空 title → 正文首行去 markdown/表格符号后截断 40 字加省略号；
  首行无效则向下取首个有效行，全文无有效文本回退 tocPath 末段；
  尾部中英文冒号去除；>60 字截断加省略号。
- **检索匹配路径用原始 title**，兜底只作用于对外展示字段。
- 前端不做二次截断。
- 验证：三种形态单测；前端展示走查放到整批统一验证环境执行。

### L4b — AKN-023 埋点

- `ToolCallRecord` 已有 `durationMs`/`round`，本项补**请求级总耗时与 LLM 累计耗时/次数**，
  写入 `tool_calls.jsonl` 并打日志。
- 无法拆出纯网络耗时，报告中标注为“LLM 调用端到端耗时（含网络）”。
- 验证：新增字段的单测；武僧清规 3 次复测放到整批统一验证环境执行；
  本阶段不做任何优化。

## Verification

**统一执行的三件事**（lane 内均不重复执行）：

1. **全量评测**：整批合并后跑 1 次。各 Spec 中“53 题全量无回退”按本计划口径执行。
2. **Java 全量测试**：`mvn test` 全量只在整批合并后跑 1 次；lane 内只跑相关模块测试。
   若某 lane 自测发现明确回归风险，可申请加跑，但需记录理由。
3. **真实模型验证环境**：整批验收时用一个临时实例承担全部真实模型验证
   （medium-17 三次、门禁同会话三次、武僧清规三次、前端走查、全量评测），
   各 lane 不各自搭建。

**题数口径**：新增 2-3 道同类题后，评测基数由 53 变为 55 或 56，
所有报告按实际题数写，不再沿用“53 题”作为固定说法。

各 lane 自测通过后，在合并后的基线上做整批验收：

1. `mvn test` 全量绿；前端 Vitest 绿；数据侧 pytest + `build check` 绿。
2. `qa/test_evaluate.py` 全绿。
3. medium-17 连跑 3 次：溯源 3/3、答案 235,000 gp。
4. L2 新增的同类题全部通过。
5. AKN-024 真实模型同会话复现 3 次，3/3 重新建议。
6. **整批唯一一次全量评测**（含新增题，题数以评测集实际为准，预计 55-56 题）无回退；
   同时观察“最贵”提问被门禁拦截的体验是否合理（本批明确不做门禁豁免）。
7. 标题展示前端走查通过。
8. 武僧清规 3 次耗时拆分报告产出，含按收益排序的优化建议。
9. 文档收口：五个 Spec 状态、AKN-025/024/026 与 F-002/KN-204/KN-219 源文档、一期汇总计数
   （27 → 实际剩余）、总索引、README/CLAUDE/PROJECT_HANDOVER 同步；只按真实闭环销账。

## Assumptions

- 每项都在独立隔离 worktree 开发，不直接在主 checkout 改代码。
- 不 push、不发布；只在本地分支合并。
- 真实模型验证使用统一临时实例，不占用常驻 8080、不污染正式向量库。
- `ChatService` 只由 L4 修改，标题兜底与埋点在同一 lane 内顺序完成。
- AKN-023 本阶段只交付测量数据，提速目标待数据出来后另行立项。
- 若 L3b 的会话上下文传递在现有线程模型下不可行，暂停该子项并上报，不自行改用全局状态。
