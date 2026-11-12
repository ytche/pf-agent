# F-025 法术清单去重设计 Spec

- 日期：2026-11-10
- 状态：✅ 已实施并合并（2026-11-11；数据侧 `815bf31`/`7087bed`，Java `2443fc6`/`7174da3`/`ec23ed3`，合并 `8d24f35`/`b5256f3`）
- 实施计划：`docs/superpowers/plans/2026-11-11-phase1-five-specs-implementation.md`（Task 4/5/8）
- 实施证据：`docs/test-reports/测试报告_一期五项Spec收口_20261111.md`；数据评审 clean（合并 `8d24f35`）、Java 评审 clean（合并 `b5256f3`）
- 实施结果：真实重建 union 1.1（23031→18431 条目）；女巫 1 环 205→**165**（68 官方 + 97 新增派生，折叠 40 个重复派生来源）；先失败后通过的 Python/Java 测试覆盖 1.0/未知版本/畸形降级与多书展示
- 关联：F-025、F-007、AKN-001、KN-247
- 主要读者：后续负责数据侧导出器、Java 清单服务、测试与验收的实施者

## 1. 背景与问题

`spell_lists_union.json` 当前保留跨 chunk 的重复派生条目，`SpellListService` 又将官方清单与 union 中的派生条目直接相加。同一法术因此会在一个职业、一个环级内出现多次，并影响：

- 清单总数与“共 N 条”的含义；
- `offset / limit / has_more` 分页边界；
- 来源书展示与 chunk 溯源；
- 问答答案和评测中的历史数量口径。

当前真实产物中，女巫 1 环有 68 条官方条目和 137 条派生条目，共 205 条原始条目。按本 spec 的已确认规则只读试算，折叠后为 **165 个不同法术**：68 个官方法术 + 97 个新增派生法术，40 个重复派生来源被合并。此前文档中的 169 是早期估算，不作为本次验收终值。

## 2. 目标与非目标

### 2.1 目标

1. 在同一职业、同一环级内，每个法术只出现一次。
2. 保留同一法术的全部来源书、chunk 和命中证据，不以丢弃来源换取去重。
3. 让 union 产物、Java 概览、清单标题和分页 footer 使用同一个“不同法术数”口径。
4. 保持数据侧产物为唯一事实源，Java 不再实现第二套去重逻辑。
5. 明确新旧 schema 的兼容、降级、报告与验收行为。

### 2.2 非目标

- 不修改 `spell_lists.json` 的内容或字节。
- 不扩大派生职业范围；OA 五职业仍只有官方清单，脏职业键仍不派生。
- 不处理 `spell_level` 缺失、清单页缺录或 169 条既有权威冲突本身。
- 不把每个法术的全部 chunk 自动加入 `SourceCollector`，不恢复大清单的来源膨胀。
- 不在本批设计前端引用展示；F-020/F-022 另行处理。
- 不在 Java 中对旧产物临时补做去重。

## 3. 已确认的核心决策

| 决策点 | 结论 |
|---|---|
| 去重范围 | 同一职业、同一环级内；不跨职业或环级折叠 |
| 法术身份 | 规范化中文名或英文名任一键命中即属于同一组，允许传递合并 |
| 官方内部重复 | 与派生使用同一规则折叠，保留首个官方主条目 |
| 官方/派生交叉 | 派生来源并入官方条目的 `sources`，不重复计数 |
| 主来源 | 官方条目优先；纯派生组保持当前首次命中 |
| 多来源结构 | 保留现有主字段，新增完整 `sources` 列表 |
| 名称归一 | 保守兼容归一，不通过激进删词扩大匹配 |
| 名称冲突 | 按规则合并，所有名称、来源和命中键完整入报告 |
| 工具展示 | 展示全部去重书缩写，如 `[PSP/COMP]` |
| 引用收集 | 整个清单仍只挂职业列表页汇总来源 |
| 去重落点 | 数据侧完整折叠；Java 直读 union 1.1 |
| Schema | union 升级为 1.1，构建清单同步改 `expected=1.1` |
| 旧产物 | Java 兼容读取 1.0 并警告，不做运行时二次去重 |
| `matched_by` | 记录到每个 source，保留真实命中依据 |

## 4. 架构与数据流

### 4.1 数据侧

`spell_list_union_export.py` 继续读取：

- `spell_lists.json`：官方清单；
- `chunks.jsonl`：库侧 `spell_level` 派生证据。

导出器按“职业 + 环级”收集官方与派生候选，完成名称归一、分组、主来源选择和来源折叠，再写出：

- `spell_lists_union.json`，版本 1.1；
- `spell_list_union_report.json`，包含去重统计和冲突明细。

标题污染条目仍在折叠前排除，不进入 union；其他既有差异分类继续基于原始候选记录，避免去重后丢失审计线索。

### 4.2 Java 侧

`SpellListService` 按 union 版本选择消费路径：

1. **union 1.1 可用**：直接读取其中已经折叠的完整条目序列，不再执行“官方条目 + derived 条目”相加。
2. **union 1.0 可用**：走现有官方 + derived 兼容路径并记录警告；缺失的 `sources` 可由主字段视为单来源，但不进行去重。
3. **union 缺失或畸形**：退回 `spell_lists.json` 官方清单，保持现有不炸启动的降级语义。

union 1.1 只替代条目序列。职业别名索引、列表页 `source_excerpt / source_toc_path / list_chunk_id / source_page` 及 `listPageDocument` 仍来自 `spell_lists.json`；该文件在 1.1 路径下仍是必需依赖，其缺失时整个清单工具降级的语义不变。

`levelOverview`、`levelTotal`、`formatLevel` 和分页计算必须共享同一份已解析条目序列，禁止概览继续只读官方清单而详情读取 union。

## 5. 法术身份与归一化

### 5.1 中文键

沿用现有 `_norm_cn` 与 KN017 已批准译名映射，去除既有规则覆盖的空白差异。不得在本批擅自增加新的译名映射或删除实义词。

### 5.2 英文键

在现有 trim、小写和连续空白归一基础上增加保守兼容处理：

- Unicode 全半角兼容归一；
- 大小写不敏感；
- 连续空白折叠为一个空格；
- 常见直弯 apostrophe 归一，如 `'`、`’`、`‘`、`ʼ`、`′`；
- 常见直弯双引号归一；
- 空串、`n/a`、`na`、`none`、`null`、`-`、`—`、`?`、`？` 视为无英文键，不参与匹配。

不得仅因标点差异之外的语言、单复数、词形或删词相似而合并。

### 5.3 分组规则

1. 中文键或英文键任一命中即可把两个候选放入同一组。
2. 分组采用传递闭包：A 与 B 中文键相同，B 与 C 英文键相同，则 A/B/C 同属一组。
3. 官方条目之间也应用相同规则。
4. 组内有官方条目时，首个官方条目为主条目；否则以当前导出顺序的首个派生条目为主条目。
5. 主条目的 `cn/en` 是展示名称；其他名称不删除，进入名称冲突报告。

## 6. union 1.1 条目契约

### 6.1 示例

```json
{
  "cn": "精确施法",
  "en": "Sure Casting",
  "book": "PSP",
  "chunk_id": "spell_初探探索者协会_法术_0002",
  "source": "derived",
  "level_evidence": "spell_level: 女巫 1",
  "matched_by": "derived_new",
  "sources": [
    {
      "book": "PSP",
      "chunk_id": "spell_初探探索者协会_法术_0002",
      "source": "derived",
      "level_evidence": "spell_level: 女巫 1",
      "matched_by": "derived_new"
    },
    {
      "book": "COMP",
      "chunk_id": "spell_page_1155_0002",
      "source": "derived",
      "level_evidence": "spell_level: 女巫 1",
      "matched_by": "derived_cn_and_en"
    }
  ]
}
```

### 6.2 字段约定

- 1.1 的 `levels` 同时包含官方与派生主条目；官方主条目的 `source` 仍为 `official_list`，纯派生主条目为 `derived`。Java 1.1 路径读取全部条目，不再沿用 1.0 的 derived-only 过滤。
- 顶层 `book / chunk_id / source / level_evidence / matched_by` 镜像主来源，保持旧字段可读。
- `sources` 按首次出现顺序保存完整来源，主来源位于首位。
- 每个 source 至少保存 `book / chunk_id / source / matched_by`；派生来源继续保存 `level_evidence`。
- 官方来源的 `chunk_id` 可为 null，派生来源的 `chunk_id` 必须非空；字段键本身必须存在。
- 相同 `(chunk_id, source)` 不重复写入；同一 chunk 同时承担官方与派生证据时允许保留两种角色。
- `book` 允许为空或未知来源的既有值，但不得因折叠而丢失原始值。
- 官方主条目的主证据为 `official_primary`；顶层官方条目可继续省略旧版本就没有的 `matched_by`，其 source 中必须记录。

### 6.3 `matched_by` 枚举

| 值 | 含义 |
|---|---|
| `official_primary` | 官方主来源 |
| `derived_new` | 未命中官方或此前派生组的首个派生来源 |
| `official_cn` | 通过中文键并入官方组 |
| `official_en` | 通过英文键并入官方组 |
| `official_cn_and_en` | 中英文键均并入官方组 |
| `derived_cn` | 通过中文键并入既有派生组 |
| `derived_en` | 通过英文键并入既有派生组 |
| `derived_cn_and_en` | 中英文键均并入既有派生组 |

若一个来源通过不同键连接多个既有组，报告必须记录全部命中关系；条目上的枚举表示主来源或直接命中类型，详细传递链以去重报告为准。

## 7. 工具输出、分页与引用

### 7.1 输出

单条格式保持“序号. 中文名（English）[书缩写]”，但书缩写位置展示 `sources` 中全部非空书缩写的去重结果：

```text
1. 精确施法（Sure Casting） [PSP/COMP]〔派生〕
```

顺序为主来源书在前，其余按 `sources` 首次出现顺序。重复书只显示一次。只有主来源为 `derived` 的条目才带〔派生〕标记；官方主条目即使合并了派生来源也不带该标记。chunk_id 不直接拼入紧凑清单文本。

### 7.2 数量与分页

- “共 N 条”统一表示该职业、该环级折叠后的不同法术数。
- 官方组仍排在新增派生组之前，各组保持既定主来源顺序。
- `offset / limit / has_more / next_offset` 全按折叠后的条目序列计算。
- 多书缩写会增加单行长度，每页实际条数继续由现有字符预算决定，不固定每页条数。
- 同一 union 产物内，分页顺序必须稳定；跨不同版本产物不承诺 offset 可复用。

### 7.3 引用收集

`RetrievalTools.getSpellList` 继续只把职业列表页 Document 加入 `SourceCollector`。完整 `sources` 是 union 的结构化溯源契约，不自动把当前页或整表的所有 chunk 加入收集器，避免响应体积和引用编号膨胀。

## 8. 报告与数量守恒

### 8.1 每职业每环统计

`per_class_level` 保留并明确：

- `official`：折叠前官方来源条目数；
- `derived_candidates`：排除标题污染后参与折叠的派生来源数；
- `derived_added`：未并入官方组的新增派生法术组数；
- `union`：最终不同法术数。

新增：

- `official_duplicates_merged`：官方内部被折叠的重复来源数；
- `official_merged`：并入官方组的派生来源数；
- `derived_duplicates_merged`：纯派生组内被折叠的重复来源数；
- `multi_source_entries`：最终包含多个来源的法术组数。

设 `official_retained = official - official_duplicates_merged`，必须满足：

```text
derived_candidates = derived_added + official_merged + derived_duplicates_merged
union = official_retained + derived_added
official + derived_candidates - union
  = official_duplicates_merged + official_merged + derived_duplicates_merged
```

### 8.2 差异与冲突报告

- `diff_counts["条目合并"]` 等于 `derived_duplicates_merged`，表示被折叠的重复派生来源数，不表示重复组数。
- 新增 `kn246_duplicate_level_candidates`，单独保存所有带 `_dup` 标记的原始候选及明细；无论该候选是否与其他组键命中、是否最终被折叠，都不得让 KN246 原始异常审计静默消失。该字段不参与数量守恒。
- 官方内部合并和官方/派生交叉合并分别通过上述新增计数表达，不混入既有“清单页缺录”等标签。
- 新增 `dedup_name_conflicts`：保存同组不同表面名称、规范化键、全部来源和命中关系。
- 名称冲突按已拍板规则合并，不单独阻断构建；空主键、来源丢失、数量不守恒、`diff_unclassified != 0` 等仍必须阻断。
- 现有 `conflicts` 继续只表示“清单页权威冲突”，不与 `dedup_name_conflicts` 混用。

## 9. 错误处理与兼容性

- union 1.0：兼容读取并警告，保留旧计数行为；这是版本过渡，不是新 Java 的二次去重通道。
- union 缺失：WARN 并降级为官方清单。
- union JSON 畸形：WARN 并降级为官方清单，必须新增测试覆盖 KN-247 QA-3。
- union 1.1 条目缺 `sources`：视为无效 1.1 产物并降级官方清单，不静默补造来源。
- `sources` 中主来源与顶层镜像字段不一致、必需字段缺失或数量守恒失败：数据侧构建失败；Java 加载时发现结构不一致则按 union 不可用处理并记录明确警告。
- 未知更高版本：按不支持的 union 处理，降级官方清单并警告，不按 1.1 猜测解析。

## 10. 测试与验收

### 10.1 Python 测试

覆盖：

1. 中文键命中、英文键命中、中英文同时命中；
2. 传递合并与多组连接；
3. 直弯标点、全半角、大小写、空白与 `n/a` 空键；
4. 官方内部重复、官方/派生交叉、纯派生重复；
5. 官方优先和纯派生首次命中的主来源规则；
6. 多来源顺序、`(chunk_id, source)` 去重和顶层镜像；
7. 每个 source 的 `matched_by`；
8. KN246 `_dup` 原始候选报告、名称冲突明细、数量守恒和构建失败边界；
9. 重跑字节一致。

### 10.2 Java 测试

覆盖：

1. 1.1 直接消费完整 union，不再重复拼接官方条目；
2. 多书缩写展示、派生标记和稳定顺序；
3. 概览、`levelTotal`、标题与 footer 总数一致；
4. 多页连续取全、offset 越界、负 offset、字符截断；
5. 使用固化的 1.0 fixture 验证兼容读取与警告，不依赖重建后工作区仍保留旧产物；
6. union 缺失、畸形、未知版本、无效 1.1 的降级；
7. `SourceCollector` 仍只收到列表页汇总来源。

### 10.3 真实产物验收

- 女巫 1 环：**205 → 165**，即 68 官方 + 97 新增派生，40 个重复派生来源被折叠。
- 雪球术、精确施法、护卫伙伴、速凝术等原重复组各只出现一次。
- 折叠前后的所有原始来源均能从 `sources` 或去重报告追溯；实施时提供可复跑的来源对账命令，不允许只验证条目数而丢失 chunk。
- 召唤师（掉链子）6 环“冰晶传送UM / 冰晶传送”和秘学士 2 环“编码语言 / 密语术”按官方内部重复规则折叠并入报告。
- 保存全量 `per_class_level` 新旧计数基线和变化清单，逐职业逐环核对，不仅检查女巫 1 环。
- `diff_unclassified=0`，OA 五职业零派生，脏职业键零派生。
- `spell_lists.json` 字节不变，union `version=1.1`，构建清单 `expected=1.1`。

### 10.4 端到端与回归

- 真实提问“女巫 1 环法术有哪些”，翻页最终总数为 165，无重复法术、无分页漏项，多书缩写可见。
- 回答中的引用仍为列表页汇总来源，不出现全 chunk 来源膨胀。
- 执行数据侧全量 pytest、`python3 -m vectorizer.build check`、Java 全量测试及现有问答评测。
- 评测锚点和期望数量按新口径复核；不得为保留旧数字而修改正确实现或跳过测试。
- 闭环时同步更新 F-025、F-007、AKN-001、KN-247、项目文档总索引和一期临时汇总中的状态与历史数字。

## 11. 后续实施方案应拆分的边界

本 spec 只固定设计，不代替实施计划。后续计划至少应区分：

1. 导出器、schema、报告与 Python 测试；
2. Java 1.1 消费、旧版兼容、分页展示与 Java 测试；
3. 真实产物重建、数量与来源对账；
4. 真实 Agent 问答、评测和文档销账。

每一阶段都必须保持脚本、产物、构建状态和文档同版本提交。
