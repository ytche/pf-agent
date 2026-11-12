# Agent 功能 TODO（想法清单）

> 定位：记录在 Agent 上想开发的功能想法 / backlog，供复盘与后续排期实现。
> 追加方式：编号递增（F-001 → F-002 …），每条按下方模板补全；已在别处沉淀的待办（AKN/KN/设计文档）以「关联」指向，不重复搬运细节。
> 本清单与《开发决策与修改记录.md》（已实施决策史）、《一期规则问答Agent决策链设计.md》（方案说明书）互补。

## 状态约定

| 状态 | 含义 |
|---|---|
| 💡 想法 | 仅记录想法，未排期 |
| 📋 待排期 | 已确认要做，待排期实现 |
| 🚧 实现中 | 正在进行 |
| ✅ 已实现 | 已完成 |
| ❌ 放弃 | 决定不做 |

优先级：P0（阻塞一期交付）/ P1（近期）/ P2（后续）/ P3（远期或可选）

---

## 想法清单

### F-001 意图路由：区分「列举/聚合」与「事实点查」

- 状态：✅ 已实现　优先级：P1
- 描述：两类问题走不同检索路径——列举/聚合类（如"女巫 1 环法术都有哪些"）走 `searchByMetadata` 元数据枚举过滤 + 全量召回（enumeration-top-k 500），事实点查类（如"火球术射程"）走 `vectorSearch` 语义检索。实现方式：不写死独立意图分类器，由 LLM 在工具决策链中自主判断走哪个工具。
- 关联：AKN-001（已修复）/ `d5cf307` / `42068ff`

### F-002 检索端语义降权评估

- 状态：✅ 已实现（Batch A/B/C/D + 2026-11-12 标题展示兜底 M36）　优先级：P2
- 描述：一期联调批次核心项——对 intro/reference 类低信息量 chunk（feat_intro/rule_intro/rule_reference 等）、空 title/text、oversize 超长 chunk 做检索降权评估，避免噪声挤占有效结果；book '?' 口径与表格结构化（KN221）一并评估。
- 进度：Batch A（空 text 过滤 + intro/reference 降权，f30356e）→ Batch B（oversize 降权 + 配置补齐，8415aec）→ Batch C/D（book '?' / feat 双目录 / KN221 登记，f8c7bed，AKN-004）。全量 126 测试通过；真实检索复现已闭环（方案 §五.A，`feat_intro` 被压后真实条目进 top5、零误伤）。**_overview 第二批评估已闭环**（2026-08-16，决定不纳入，AKN-005——class_overview 对职业介绍类提问是正确命中，降权会误伤）。**评测集 baseline 对比延后**（evaluate.py 56 题，需 DEEPSEEK_PF_API 启动 Agent）——2026-08-16 用户拍板延后（评测会影响后续步骤），后续排期。**2026-08-20 启动 baseline 发现溯源判分口径断裂并修复**：`score_citation` 原用 `expected_chunks`(chunk_id) 对比 `sources[].tocPath` 永不命中→溯源 0/5；改 `SourceRef` 增 `chunkId`（`toSourceRef` 读 `metadata.chunk_id`）+ `evaluate.py` 增 chunk_id 精确/前缀匹配，前端反馈快照同步带 chunkId。147 个评测锚点 100% 命中向量库 chunk_id、140 单测通过。**baseline 已重跑闭环（2026-08-20，50 题 D/R）**：溯源 0→**33/50**（66%，修复前恒 0）、诚实 **49/50**（98%）、结构 **145/50**（均值 2.90/3）。剩余 23 个溯源未命中分层：① **6 题「工具循环超 15 轮」500**（`easy-7/18/22`、`medium-17/18/23`，聚合/跨 chunk 综合类问题 LLM 反复检索不收敛，最优先修）；② spell 向量库旧版错位（`vector_store_spells.json` 由旧 4200 版 chunks 构建，与当前 4172 基线 jsonl 差 28 条，chunk_id↔title 错位 2015 条——**锚点其实对、store 旧了**，如虹光法墙锚点 `CRB_0414` 但 store 里 chunk_id 是 `CRB_0420`）；③ class 检索偏离（class store 错位=0，是检索未召回精确 hash 锚点 chunk，`easy-7/14/18`、`medium-0`）；④ 跨模块真实检索偏离（跨页/跨书，即 P0-B 检索联调要评估的对象）。② 属数据同步 bug（重建 spell 向量库即可，非改锚点），③④ 是真实检索质量。**① 已修复（2026-08-20，v1.9）**：三处改动——A `searchByMetadata` 结果字符截断（`pf.search.metadata-result-chars` 默认 4000）；B 修正 `maxHistoryChars` 守卫统计口径（原 `getText()` 漏算工具结果致 50K 上限失效）+ 超限转强制收敛；C `maxToolRounds` 超限改强制收敛（默认 15→10，不再抛 500）。6 题重测全部不再 500（诚实 6/6）；**v1.9 后全量 50 题重跑（2026-08-20）error=0**，溯源 +6（27→33）、诚实 +7（42→49）、结构均值 2.64→2.90。**spell 向量库已重建闭环（2026-08-21，4172 基线，chunk_id 错位归 0）**：重跑 baseline 溯源 33→**38/50**、诚实 49→**50/50**、结构 145→148（均值 2.96）。9 道含 spell 题溯源 0→1 恢复（easy-2/3/9/10/23、medium-8/10/12/21，含虹光法墙 CRB_0414），4 题 1→0 退化（easy-1/21、medium-7/20，主锚点非 spell，属 LLM 检索随机波动非回归）。剩余 12 题溯源仍 0 全部属 ③④ 真实检索偏离（class hash64 锚点 / rule 跨页 / feat / equipment / race，无 spell 错位题），即 P0-B 检索联调对象。**2026-08-21~24 溯源 38→44/50**（修复 1 topK 5→15 + 修复 3 聚合题宽松 + 修复 4 class hash 锚点 8 题改 doc 级 tocPath，6 题恢复）。剩余 6 题溯源=0 归因：① 2 题 LLM module 路由错误（easy-7/medium-0「兼职」误判 rule，F-006 实锤）；② 4 题召回精度/波动（easy-15/22、medium-4/21）。新发现 `isBaseClassPage` 前缀「基础职业」vs 实际「核心职业」不匹配 → class-base-bonus 疑似失效，待联调批次核实。详见 `检索溯源归因与修复方案_20260821.md`。**P0-B 检索联调批次完成（2026-08-25）**：溯源 **44→46/50**、诚实 49、结构 2.94。T1 isBaseClassPage 补核心职业前缀（`34e8d8d`）+ T2 模块路由提示（`fa00ec7`），easy-7/medium-0 恢复（tool_calls 确认 vectorSearch module rule→class）。本轮溯源=0：easy-22/medium-4/medium-21/medium-25（T4 复刻归因：短文本锚点 embedding 弱 + 排序被压 + LLM 引用波动；easy-15 意外恢复、medium-25 baseline 波动掉点），修法建议见方案 §六，待 k3 设计。T5 KN098 无残留关闭 / KN100 残留 11 字段行伪条目（AKN-006）。**P0-B2 批次完成（2026-08-25）**：溯源 **50/50 满分**（46→44→50；诚实 49、结构 2.96）。修法 A（title 过滤全模块开放）+ 修法 B（候选扩容 + title 词元加权）落地，4 目标题全恢复（easy-22/medium-4/medium-21/medium-25）；**AKN-008 drain 去重 bug（doc_id 页面级 → chunk_id）是修法 A 生效的隐蔽根因**——title 过滤命中锚点被同页邻居挤出。无退化。验收 V3 全达标，详见 `检索溯源归因与修复方案_20260821.md` §六。
- 关联：`docs/已知问题记录_agent.md`（AKN-004）/ `检索端语义降权优化方案_20260816.md` / 数据侧 `docs/已知问题记录.md`（KN098/100/KN221 等）
- **2026-11-12 第二批闭环（M36，M37 统一验收）**：F-002 / KN-204 / KN-219 的剩余 title/展示治理落到**展示层统一兜底**——`ChatResponse.SourceRef.title` 空 title 取正文首个有效行（去 Markdown/表格符号，40 字截断），无有效正文回退 `tocPath` 末段；非空 title 去尾中英文冒号、>60 字截断。检索匹配/过滤仍用原始 title，数据侧仍按 KN-204/KN-219 原处置登记不修。Playwright 临时实例走查通过（默认 3 条；点击「查看全部」后 DOM 来源数与 API 相等 10=10，完整 `title` 数组逐项相等，空标题/尾冒号/超长均为 0）。证据：`docs/test-reports/测试报告_一期第二批五项问题验收_20261112.md`。

### F-003 会话历史持久化（重启不丢上下文）

- 状态：✅ 已实现（2026-09-05 SP1，jdbc 模式 `JdbcChatMemory`，验收通过）　优先级：P1
- 描述：当前 `InMemoryChatMemory` 重启即失，一期本地单用户可接受。预留文件持久化实现（`ChatMemory` 接口扩展），解决多轮上下文跨重启延续。归属 P1 但实现顺序靠后——不占一期检索联调/准确率优化主线，排在标错闭环（F-015）等优先项之后。
- 关联：设计文档 §9.6（持久化与长期记忆决策）

### F-004 二期：车卡辅助 + Build 建议

- 状态：💡 想法　优先级：P3
- 描述：二期规划——车卡（角色创建）辅助与 Build 建议，非一期范围，立项时单独设计。
- 关联：CLAUDE.md 二期规划 / 设计文档 §17（二期展望）

### F-005 会话历史后端保存轮数

- 状态：✅ 已实现（2026-09-05 SP1，`pf.chat.history-rounds` 默认 20 轮写入时裁剪，验收通过）　优先级：P2
- 描述：对话历史持久化到后端并限制保存轮数（如最近 N 轮），避免无限增长且支持重启恢复。
- 关联：F-003 / 设计文档 §9.6

### F-006 工具调用情况计数

- 状态：✅ 已实现　优先级：P2
- 描述：统计每次问答中的工具调用情况（工具类型 / 次数 / 成功失败 / 耗时），供复盘 Agent 检索行为、调优 prompt 与检索策略。实现链路：`ChatService.executeTools` 埋点（nanoTime 计时 + 成败标记，成功/失败都记录）→ `ToolCallTracker`（ThreadLocal 会话级收集，单例并发请求不污染）→ `ToolCallRecorder` 追加 JSONL（`~/.pf_agent/tool_calls.jsonl`，失败只记日志不拖垮主链路）→ `qa/tool_calls_report.py` 聚合分析（按工具次数/成功率/均耗时/结果字符 + 会话工具序列 + 失败调用清单）。纯后端，无前端展示；无工具调用的问答不落盘。
- 关联：F-002 / 评测集 baseline（观测工具调用行为支撑检索联调复盘）

### F-007 职业法术列表预整理

- 状态：✅ 已实现（2026-09-06 SP3，26 职业环级清单 + `getSpellList` 直查工具，验收通过）　优先级：P1
- **增强（2026-10-29，A+B1 批次）**：清单页书范围缺口（译者注只收 CRB/APG/UM/UC/ACG）由派生补充清单补齐——`spell_lists_union.json`（KN247，official+derived 带 source 标注）+ getSpellList 合并读取 + offset/limit 分页；女巫 1 环 68→**207** 全量可获取（2026-10-30 复测；条目口径，去重后 169 个不同法术；去重见 F-025；KN248 清假环级后 **205 / 去重 167**）。前置 A=spell_level 元数据清洗（KN242，空率 34.8%→10.1%）。
- 描述：把「职业 + 环级 → 法术列表」预整理为结构化清单（覆盖 26 职业），使"XX职业N环法术有哪些"类列举提问直接命中，摆脱 topK 截断。
- 关联：F-001 / AKN-001（2026-10-29 终态闭环）/ `docs/SP3_职业法术列表预整理方案_20260906.md` / `docs/design/方案_B1法术派生补充清单_20261029.md`

### F-008 Chunk 块元数据加入目录

- 状态：💡 想法　优先级：P2
- 描述：将 chunk 元数据（tocPath / 来源书 / 组件类型等）纳入目录索引体系，支持按目录层级定位、过滤与溯源 chunk。
- 关联：—

### F-009 Agent 单开 API Key 统计与计费预测

- 状态：💡 想法　优先级：P2
- 描述：为 Agent 使用独立 API key，统计每次问答的 token 消耗并预测计费，监控运行成本。
- 关联：D03（`DEEPSEEK_PF_API`）

### F-010 用户请求限频（rate limiting）

- 状态：✅ 已实现（2026-09-06 SP2，按 IP 限频 `pf.rate-limit.*` 默认关闭，验收通过）　优先级：P1
- 描述：为 `/api/chat` 增加请求限频（按 IP / 会话 ID 的 QPS 或每分钟上限），防滥用与 token 成本失控。当前无鉴权（AuthInterceptor 未启用），接口外露，属一期上线前成本控制项。涉及访问控制，实施前需评估对正常用户的影响与绕过风险。
- 关联：AuthInterceptor / F-009 / F-011

### F-011 未登录用户轮次限制

- 状态：✅ 已实现（2026-09-06 SP2，匿名会话配额 `pf.quota.*` 默认关闭，验收通过）　优先级：P1
- 描述：未登录/匿名用户每会话问答轮数上限（如达到上限后提示需登录/等待），防无限调用消耗 token。当前无登录体系，先做匿名配额；登录体系引入后按用户/账号配额，与 F-005 会话轮数保存叠加时注意边界。
- 关联：F-005 / F-010

### F-012 工程纪律：数据问题与检索问题分开 + 数据脚本版本同步

- 状态：✅ 已实现（2026-11-11，规范轻量落地：WORKFLOW 新节 + 独立模板；不含运行时代码）　优先级：P1
- 描述：排障时先界定问题归属——数据层（chunk 缺失/质量/元数据）vs 检索层（召回/排序/降权/溯源），分开展证，避免混为「检索 bug」；数据 pipeline 与后处理脚本任何改动必须与产物同版本提交并跑通 verify，**禁止脚本版本低于已生成产物**（否则产物无法复现）。教训关联：数据侧 spell/职业已冻结（KN136）、规则 KN207 剥离前须固化来源提取链路。
- 设计 Spec：`docs/superpowers/specs/2026-11-10-f012-attribution-and-artifact-versioning-design.md`。已确认数据/消费/检索/生成四层、主责层+因果链、分阶段证据、局部/共享重建、变更与 build_state 同提交及 Java 消费闭环；以 WORKFLOW + 独立模板轻量落地。
- 落地（2026-11-11）：`docs/WORKFLOW.md`「问题归因与数据版本闭环」节（证据门槛映射 architect/coder/tester/主 Agent，缺项即打回）+ `docs/templates/问题归因与变更验收模板.md`（登记/分层排证/修复/构建/消费/闭环六段，KN108、AKN-003 示例）；KN/AKN 源登记库维持唯一事实源，根 CLAUDE 仅加短红线与指针。
- 关联：数据侧 `docs/已知问题记录.md`（KN136 / KN207）/ `docs/templates/问题归因与变更验收模板.md`

### F-013 主从库（读写分离 / 部署架构演进）

- 状态：💡 想法　优先级：P2
- 描述：会话/用量等持久化数据演进到数据库时，考虑主从库读写分离（主写从读）支撑并发与可用性。当前一期内存存储（InMemoryChatMemory）无 DB，待 F-003 持久化落地后评估；部署环境资源受限（2 核 2G），需一并评估资源占用。
- 关联：F-003 / 部署规划（embedding 云 API + 本地兜底方案）

### F-014 回答正文论文式上标标注（来源编号对应）

- 状态：✅ 已实现（2026-09-07 SP4，prompt 约束 + 后端编号对齐 + 前端引用列表，验收通过）　优先级：P1
- 描述：回答正文像论文一样做**上标编号标注**——Agent 生成的句子/段落后标注上标数字（1、2、3…），每个数字对应页面上该来源的引用内容（书 / tocPath / chunk），用户可逐句追溯验证。实现要点：
  1. LLM prompt 约束引用编号规则：引用某 chunk 内容的句子后附编号，编号顺序对应 `sources` 数组索引；
  2. 后端校验/兜底编号与 `sources` 一致性（LLM 编号可能错位，需后处理对齐）；
  3. 前端页面按编号展示对应引用内容（类似论文文末引用列表）。
- 全角归一（2026-11-11，`69107dd`）：`CITATION_MARK` 识别 `［＃N］`/`［#N］`/`[＃N]` 等全角与混用形态，全角数字归一后按原越界/畸形规则判定，输出统一重写为半角 `[#N]`；修复了模型输出全角上标时 cited-only 误判为无引用、`sources=[]` 的问题（临时实例复验放行路径来源 0→11）。
- 关联：F-008 / `agent/qa/evaluate.py`（溯源正确性判分——引用编号可用于强化判分口径）

### F-015 错误标注闭环：前端标错 + 后端落盘 + 分析报告

- 状态：✅ 已实现　优先级：P1
- 描述：用户提问时发现错误回答可一键标注，形成「标注 → 分析 → 优化 prompt/代码」的准确率提升闭环：
  1. 前端回答下方「⚠️ 标错」按钮 → 表单选错误类型（事实错误/检索漏召回/编造来源/答非所问/结构差）+ 修正 + 备注 → `POST /api/chat/feedback`；
  2. 后端 `ChatController.feedback` → `FeedbackRecorder` 写入 `error_annotation` 表（F-021 起入库；此前为 `${user.home}/.pf_agent/annotations.jsonl` 追加落盘），记录 question/answer/sources **回答快照**，可精确复现错误现场；未入库时代码分档且不谎报成功：入参非法（字段超列宽）→ 400 + reason=`invalid_input`，DB 不可用/写入失败 → 503 + reason=`db_unavailable`/`write_failed`；
  3. 分析脚本 `agent/qa/annotations_report.py` 按 errorType 聚类 + 被标错来源 Top（问题 chunk）+ 逐类优化建议（指向 prompt/检索/数据三处优化点）；
  4. 与 56 题评测集互补：评测集离线批量测（`evaluate.py`），标注是线上真实错误收集，合并进同一优化口径。
- 关联：F-014（论文式上标编号回校可自动识别「编造来源」）/ F-001、F-002（检索漏召回）/ F-003（快照自带上下文，不依赖会话历史）

### F-016 来源收集器上限（sources 数量 / 响应体积护栏）

- 状态：🔀 部分落地（2026-10-10 M16 试点合并）——sources 在响应出口**只保留被正文 [#N] 实际引用的条目** + 编号重映射（`ChatService.filterCitedSources` 替代 `stripInvalidCitations`），sources 总数 −82.5%（2570→450），评测仅 medium-17 溯源 −1（见 AKN-014）。「收集器数量上限/top-K 护栏」**未做**（2026-10-01 用户拍板方案 C 不做）；如需再加护栏另议。
- 优先级：P2（2026-11-09 一期排期；追加护栏仍需另行决策，不默认并入前端改版）
- 描述：SP4 验收观察项——宽过滤检索场景下 sources 达 **552 条、响应体 1.1MB**（v1.5 既有语义：宽过滤命中的 chunk 全量进 SourceCollector）。虽非缺陷，但响应体积与前端渲染存在隐患。建议给 `SourceCollector` 加上限护栏：数量上限（如 top N，对齐展示需求）或总字符截断，超限部分不进 sources；注意与 F-014 上标编号对齐逻辑联动（截断后编号仍须连续一致），改动需重跑评测确认溯源基线（≥52/53）不回退。
- 关联：`docs/handover/KIMI_K3_SP4验收_20260907.md`（观察项）/ F-014 / `SourceCollector`（AKN-008 已修复的 drain 去重逻辑同处）

### F-017 条目文本引用离线抽取入 metadata（J6 Layer 1）

- 状态：📋 已登记（2026-09-18 拍板记录在案，不预立项）　优先级：P2
- 描述：规则原文中大量「（见 X）/详见《Y》」文本引用，J6 Layer 0（纯 metadata 解析，SP8c）覆盖不了。做法：数据侧离线抽取脚本 → 全库 title/alias 候选校验（仅保留精确命中）→ 写回 chunk `entry_links` 字段 → Java 侧 mapper 白名单 + metadata 重放，LLM 侧零改动（getEntryLinks 透明多一层文本引用）。估全库真引用 1000~1500 处。
- 启动条件：J6 Layer 0 上线后，按 `listDataGaps` / `tool_calls.jsonl` 中引用类问题占比评估再启动。
- 关联：`docs/design/方案_Agent检索工具增强_20260917.md` J6 节（Layer 1/2 设计）

### F-019 职业成长表查表工具（J5 getClassTable）

- 状态：✅ 已实现（2026-09-22 SP8 J5，ClassTableService + getClassTable + prompt 引导落地；评测重跑随 SP8 评测批）　优先级：P1
- 描述：给 Agent 一个成长表查表工具——输入职业+等级，直接返回 BAB/强韧/反射/意志豁免/特殊能力/每日法术位等派生值（数据侧 D3 产出的 class_tables.json 结构化成长表），解决"LLM 按公式算数值不可靠"的痛点。职业名归一复用 SpellListService 规范键通道（共享 CANONICAL_CLASS 别名空间）；D3 未覆盖职业诚实返回并引导 vectorSearch 回退；兼职/神话阶层一期不做（LLM 查表+查规则自行合成）。LLM prompt 约束数值成长类问题必须查表、禁止自行计算。
- 关联：`docs/design/方案_J5成长表查表工具_20260922.md`（本工具方案）/ `docs/design/方案_Agent检索工具增强_20260917.md`（J 系列总方案，J5 原漏覆盖）/ `docs/design/方案_数据侧产物增强_20260917.md` §D3（数据产物，并行开发中）/ F-007（getSpellList 消费先例）

### F-018 CI 挂数据产物构建链 check（build check 入 CI）

- 状态：✅ 已落地（2026-09-21，构建链批 2 随 KN227 一并实施）　优先级：P2
- 描述：数据产物可复现构建链（`build_manifest.json` + `vectorizer/build.py`）一期落地后，二期在 CI 挂 `python3 -m vectorizer.build check`——校验产物与 manifest/build_state.json 一致 + schema version 匹配，防"改了源 md/脚本却忘重跑产物"的漂移。
- 实现：`.github/workflows/pf-data-build-check.yml`——push/PR（paths 收窄数据侧）先 `python3 -m vectorizer.build all` 增量重建（产物 gitignored，CI 裸 checkout 无产物，直接 check 必报 missing），再 `python3 -m vectorizer.build check` 只读对账。数据侧 Python 3.12 + pip install pytest（同 ci.yml 教训 B5）。
- 启动条件：构建链任务（批 1：manifest + build.py + 单测）落地并本地跑稳后。
- 关联：`docs/design/方案_数据产物可复现构建链_20260918.md` §4 / 决策记录第 3 条 / KN227

### F-020 前端页面改版优化

- 状态：✅ 已实现（2026-11-11；会话后端 `ed057ce`、前端 `43cad9f`、契约补缺 `d71b32c`，合并 `29d99ff`/`b8c3f4a`/`c85f344`；三轮复审 final clean）　优先级：P2
- 描述：问答页升级为 Vue 3＋TypeScript＋Vite＋Pinia 多会话 SPA：浅色单栏消息流、20 轮历史、完整引用快照、匿名本机会话与登录认领、后台请求、移动端历史页层。最终设计见 `docs/superpowers/specs/2026-11-03-f020-frontend-final-design.md`。
- 实施 Spec：`docs/superpowers/specs/2026-11-11-f020-f022-frontend-implementation-design.md`。已确认独立 frontend + CI 先构建、统一 ConversationStore、V7 迁移、响应级引用快照、UUID 匿名访问、删除后 410 及仅前端同会话并发限制。
- 实施结果（2026-11-11）：`pf_agent/agent/frontend/` Vue 3 工程落地，Vite 输出 `static/dist`，Spring 根路径显式 forward；`ConversationStore` JDBC/内存双实现，V7 增加 title/pinned/owner/generation_attempts、消息 sources JSONB 与 gap_reported；匿名 UUID 访问、登录认领、删除后 410、重生成 expectedLastSeq 条件替换；Vitest 40、Playwright 12、全栈 E2E（真实 Spring + PG16 + 打桩 ChatModel）通过。证据见 `docs/test-reports/测试报告_一期五项Spec收口_20261111.md`。
- 关联：F-014（引用列表展示）/ F-022（引用精简，UI 层面联动）/ M（塔任务）14（静态原型）

### F-021 反馈标注入库（替代 jsonl 落盘）

- 状态：✅ 已实现（2026-09-24 M5 批，V4 迁移建 error_annotation/data_gap 两表 + 实体/仓储/服务 + 双 recorder 改 DB 写入 + 历史 JSONL 幂等迁移 + 分析脚本改读库）　优先级：P2
- 描述：用户标记的错误和 Agent 自己标记的错误（reportDataGap）原先落在文件里（`~/.pf_agent/annotations.jsonl` / data_gaps 文件），改为入库（**实际持久化设施是 PostgreSQL 16**，SP1 落地的会话持久化层，非 SQLite/MySQL），便于查询、统计、闭环跟踪。含既有数据迁移 + `annotations_report.py` 分析脚本改读库。
- 实现要点：
  1. `V4__telemetry.sql` 建 `error_annotation`（id 即 ann- 记录 ID，sources 用 JSONB）与 `data_gap`（BIGSERIAL 合成键 + `dedup_key` 内容哈希唯一）两表，`ddl-auto=validate` 下与实体对齐启动；
  2. 新包 `com.pfagent.agent.telemetry`（实体/仓储/服务）追加进 `JdbcDataConfig` 的 `basePackages`，服务仅在 `pf.chat.memory=jdbc` 装配，写入走编程式 `TransactionTemplate`（同 `JdbcChatMemory`）；
  3. 降级（用户拍板 2026-09-24）：memory（DB 不可用）模式下**不写文件也不谎报成功**——`FeedbackRecorder.record` 返回 ok=false（原因 `db_unavailable`/`write_failed`），`/api/chat/feedback` 回 503；入参非法（字段超列宽）先拒，reason=`invalid_input` 回 400（客户端问题不算服务端降级）；`DataGapRecorder.record` 返回 false，`reportDataGap` 据实回话且不置 gapReported；读侧 `listGaps` 用 available 标记区分「库不可用」与「无记录」，`listDataGaps` 不再把库故障说成「暂无记录」；
  4. 历史数据一次性幂等迁移：`TelemetryImporter`（`PF_TELEMETRY_IMPORT_ENABLED=true` 启动执行一次）导入两个 JSONL，annotations 按 id（无 id 行按全部内容字段合成稳定 id）、data_gap 按 `dedup_key` 去重，可重复执行；**不丢行**——只有 JSON 无法解析才算坏行，缺/坏 timestamp 按 epoch 落库并报出「合成时间戳 N 条」，data_gap 缺 question 补空串保留；
  5. `agent/qa/annotations_report.py` 改经 psycopg2 读 `error_annotation` 表，聚类/明细/热点来源/建议四段输出口径不变。
- 关联：F-015（错误标注闭环，原 jsonl 实现）/ reportDataGap 工具 / SP1 持久化

### F-022 引用展示精简优化

- 状态：✅ 已实现（2026-11-11，随 F-020 前端改版落地；后端 cited-only 已于 2026-10 上线）
- 优先级：P2（2026-11-09 一期排期；与 F-020 前端改版合并设计和验收）
- 描述：每轮默认 3 张紧凑来源卡片、展开全部与上标定位，不做来源分页；后端 cited-only 与编号重映射保持不变。与 F-016（收集器上限护栏）分别负责展示与后端体积，追加护栏不默认并入。
- 实施结果：`SourceCards.vue` 默认展示 3 张、展开全部、按上标定位并高亮；桌面/手机 Playwright 与全栈 E2E 覆盖；历史消息使用自己的来源快照，旧数据缺 sources 时显示「历史来源未保存」。
- 实施 Spec：`docs/superpowers/specs/2026-11-11-f020-f022-frontend-implementation-design.md`。
- 关联：F-016 / F-014（上标编号一致性联动）

### F-023 管理后台（注册开关 + 用户管理）

- 状态：📋 已登记（2026-09-23 用户提出）　优先级：P2
- 描述：① 注册入口可通过配置开放/隐藏；② 简单 admin 界面，对用户增删改查。
- admin 凭证方案（2026-09-23 主 Agent 建议，待拍板）：admin 初始密码走**环境变量**（不进 git 的配置文件），首次启动写入 DB 时 BCrypt 哈希存储；之后可在 admin 界面改密。比纯配置文件明文强：不入版本库、不明文落盘、可自助改密。注册开关放 admin 界面里做成可切换项（配置文件给默认值）。
- 关联：SP7（单体鉴权，已有用户体系）/ F-021（入库共用持久化设施）

### F-024 清单枚举工具 listEntries（B4，J 系列"结构化枚举"需求）

- 状态：✅ 已实现（2026-09-23 SP8 B4，泛化单工具 `listEntries(module, query)` 落地；评测重跑随评测批）　优先级：P1
- 描述：给 Agent 专长/种族/装备的权威全清单枚举能力（消费数据侧 D2 三清单 JSON），解决"枚举式问题只能靠 searchByMetadata 拼结果"的缺口。泛化单工具 + `ListEntriesQuery` 参数对象（keyword/filters/orFilters/limit/offset/sortBy）+ 无条件概览模式 + 溯源复用 J5 通路；`ListExportService` 单类承载三模块独立容错。getSpellList 不收敛（法术"职业×环级"二级嵌套与扁平过滤模型不同）。
- 关联：`docs/design/方案_B4清单枚举工具_20260923.md` / `docs/test-reports/测试报告_B4清单枚举工具_20260923.md`（16 真实数据黑盒 + 3 Minor 修复）/ F-007（getSpellList 先例）/ F-019（getClassTable 先例）

### F-025 清单去重口径：union / getSpellList 折叠重复法术（2026-11-11 已实现）

- 状态：✅ **已实现并合并**（2026-11-11；数据侧 `815bf31`/`7087bed`，Java `2443fc6`/`7174da3`/`ec23ed3`）　优先级：P1（2026-11-09 从 P2 提升：直接影响清单总数、分页与溯源正确性）
- 设计 Spec：`docs/superpowers/specs/2026-11-10-f025-spell-list-deduplication-design.md`。已确认任一中英文键命中折叠、主字段 + sources、官方/派生完整合并、union 1.1、Java 直读 1.1 与 1.0 兼容降级；实施计划 `docs/superpowers/plans/2026-11-11-phase1-five-specs-implementation.md`。
- 实施结果（2026-11-11，真实重建）：union 由 23031 条折叠为 **18431** 条（version 1.1，`diff_unclassified=0`）；女巫 1 环 205→**165**（68 官方 + 97 新增派生，折叠 40 个重复派生来源，multi_source_entries=103）；雪球术/精确施法/护卫伙伴/速凝术各只出现一次且 sources≥2；`spell_lists.json` 字节不变。真实提问「女巫 1 环法术有哪些」翻页取全 **165 条、无重复、无缺号**，来源仍为清单页汇总 1 条。证据见 `docs/test-reports/测试报告_一期五项Spec收口_20261111.md`。
- 原派生问题清单（去重键/位置/多书/分页/报告/schema/评测）已在 Spec §3 逐项定案并落地；下文保留为历史讨论。
- 现状：`spell_lists_union.json` 只丢弃「标题污染」类，跨 chunk 重复条目仍并入产物，仅打 `条目合并` 标签进报告；`SpellListService.formatLevel` 的总数是 `official.size() + derived.size()`，**无任何去重**。实测女巫 1 环 = 68 官方 + 139 派生 = **207 条**（KN248 清假环级后 68 + 137 = **205 条 / 去重 167**），去重后 **169 个不同法术**（38 条重复：雪球术 ×3、精确施法 ×3、护卫伙伴 ×3、速凝术 ×3、读唇者视力 ×2、起舞于黯 ×2 等）。
- 已定：去重必做。官方 68 条名称各不相同、且与派生 101 个名称零交叉，所以去重只作用在派生内部，不会误伤清单页。
- **待定：去重键**（`cn` 归一 / `en` / 两者任一命中）、**去重位置**（数据侧 union 生成时折叠，或 Java 侧 formatLevel 折叠）。

**衍生问题清单（修复时逐项收口）**

1. **book 多值**（用户待定）：折叠后同一法术来自多本书——`book` 改数组（`["COMP","UM"]`）还是保留首条 + `books` 副字段？涉及 `SpellListEntry`/`UnionEntry` 模型、工具输出行 `中文名（English）[书缩写]` 的展示格式、溯源 metadata 的 `book_abbreviation` 单值假设。
2. **溯源线索**：重复条目的 `chunk_id` 是折叠成一个还是保留多值（影响 sources 展示与「这条来自哪本书」的追问）。
3. **分页与计数**：`total`、`has_more`、`offset` 语义按去重后口径重算（女巫 1 环 207 → 169），单页可容纳条数随之变化。
4. **报告口径**：`diff_counts` 的 `条目合并` 标签（现 38+ 条）在去重后会归零或改变语义；`variant_candidates`、`conflicts`、`书范围外` 是否受影响需回归。
5. **schema 兼容**：union `version` 是否升版（1.0 → 1.1）、`vectorizer.build` 的 schema 校验与 build_state 指纹、Java 读取旧 union 的降级路径（book 单值 / 无 books 字段）。
6. **工具说明与文档**：getSpellList 工具描述与 `formatLevel` 输出的「共 N 条」是条目数还是法术数，需明确写死；AKN-001 终态数字 207 在去重后改 169。
7. **评测回归**：53 题中清单类题目的期望条数、`expected_chunks` 溯源断言需按新口径复核；女巫 1 环 E2E 需重跑。
8. **交叉去重边界**：若某法术同时出现在官方清单与派生（导出时已用 `k_cn`/`k_en` 跳过，当前为 0 例），去重后要保证不重复计数。

- 登记依据：2026-10-30 复核「女巫 1 环 199 条」文档口径时发现——199 是 2026-10-29 union 22722 快照的条目数，KN244/246 重建 union 后为 207；同时暴露 199/207 都不是「法术数」。
- 关联：F-007（getSpellList）/ AKN-001（列举式提问终态）/ 数据侧 `spell_list_union_export.py`（`条目合并` 标签）/ KN246（跨 chunk 重复族）

### F-026 大范围枚举前置收敛建议（LLM 查询量门禁）

- 状态：✅ **已实现并合并**（2026-11-11；契约 `456e652`、工具护栏 `6db8e62`、V6 事件 `43fe289`，三项评审 clean）　优先级：P1
- 描述：在现有意图路由与元数据枚举之前增加一层大范围查询收敛建议。LLM 判断用户提问可能产生较大查询量时（例如「CRB 里所有类型的规则条目」，尤其是 `module=all`、仅限定来源书而没有主题/条目类型/职业/环级等收窄条件），不立即发起大范围检索，先返回缩小范围的建议，并给出可直接选择的示例，如「只查法术、专长还是装备？」「是否限定职业、环级或主题？」「是否先查看各模块数量概览？」。目标是减少无效跨库检索、工具循环与 token 消耗，同时避免误拦明确需要全量枚举的问题。
- 设计 Spec：`docs/superpowers/specs/2026-11-10-f026-broad-query-narrowing-gate-design.md`。已确认提示词引导 + 工具护栏、跨/单模块覆盖、`allowBroadQuery` 按逻辑查询放行、无条件查询确认后放行、500 上限不变及工具事件持久化；实施计划 `docs/superpowers/plans/2026-11-11-phase1-five-specs-implementation.md`。
- 实施结果（2026-11-11，真实模型冒烟）：首次「CRB 所有类型的规则条目」返回收窄建议，0 来源、`gapReported=false`、无条目检索；「仍按原范围查询」后 `allowBroadQuery=true` 分页执行，V6 表写入 13 条 ALLOWED（book_only）事件；改查装备后重新返回建议且无事件；「武僧清规有哪些内容」正常回答（15 来源）。已知限制：同会话先确认宽查询、再改模块问「CRB 所有专长」时，2 次同会话复跑中 1 次沿用放行直接执行、1 次正确重新建议（新会话首轮建议正确）；工具层无会话级确认状态，提示词已要求重新判断，属模型遵循度波动。**该限制已拆分为独立待办 AKN-024（P2，待收敛/待复现），并计入一期待办计数**，F-026 本身不再视为无遗留闭环项；详见测试报告。
- 证据：`docs/test-reports/测试报告_一期五项Spec收口_20261111.md`
- 关联：F-001（意图路由）/ F-024（清单枚举工具）/ AKN（Agent已知）018（跨模块 capped 文案）/ `pf.search.enumeration-top-k`
