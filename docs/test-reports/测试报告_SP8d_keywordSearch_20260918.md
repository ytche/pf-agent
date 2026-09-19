# SP8d 测试报告（keywordSearch v1，title/alias 子串匹配）

- 日期：2026-09-18
- 分支：dev/pf-agent（未切分支、未 commit）
- 验证方式：`cd pf_agent/agent && mvn test`（未启动应用）
- 被测改动：`EntryResolver.substringSearch`、`RetrievalTools.keywordSearch`、`PromptBuilder` 兜底引导

## 一、最终结论

- **mvn test：382/382 通过**（364 基线 + coder 新增 14 + tester 白盒补测 4），BUILD SUCCESS。
- 无 Blocker / Major 缺陷。
- Minor 3 项（见第四节），留用户拍板。

## 二、覆盖矩阵

| 覆盖点 | 工具/层 | 用例来源 | 结果 |
|---|---|---|---|
| 三级排序 精确>前缀>子串、短 title 优先 | EntryResolver.substringSearch | coder `substringSearchRanksExactPrefixAndSubstringWithShortTitleFirst` | ✅ |
| 跨模块命中 + module 收窄 | EntryResolver | coder `substringSearchAcrossModulesAndModuleFilter` | ✅ |
| 查无命中/空术语返回空 | EntryResolver | coder `substringSearchNoHitReturnsEmpty` | ✅ |
| 上限截断（maxResults） | EntryResolver | coder `substringSearchCapsAtMaxResults`（Reflection 设为 1） | ✅ |
| 开关关闭 resolver 返回空 | EntryResolver | coder `substringSearchDisabledReturnsEmpty` | ✅ |
| 命中清单按序 + 来源编号 | RetrievalTools.keywordSearch | coder `keywordSearchHitsReturnOrderedCandidatesWithSourceTags` | ✅ |
| 精确同名先行提示 | RetrievalTools | coder `keywordSearchWithExactNamesShowsExactHint` / `...OmitsExactHint` | ✅ |
| module 透传 | RetrievalTools | coder `keywordSearchPassesModuleFilterThrough` | ✅ |
| 无命中回退文案（vectorSearch/searchByMetadata/reportDataGap 引导） | RetrievalTools | coder `keywordSearchNoHitReturnsFallbackHint` | ✅ |
| 空术语/未知模块自纠提示 | RetrievalTools | coder `keywordSearchBlankTermReturnsHint` / `...UnknownModuleReturnsHint` | ✅ |
| 索引关闭固定提示（keywordSearch 单工具） | RetrievalTools | coder `keywordSearchDisabledReturnsFixedHint` | ✅ |
| 向量库缺原文：跳过来源编号不中断 | RetrievalTools | coder `keywordSearchMissingDocSkipsSourceTagButKeepsLine` | ✅ |
| **单字术语默认上限 20 截断 + 短名在前** | EntryResolver | 补测 `singleCharTermCapsAtDefaultMaxResultsWithShortTitleFirst` | ✅ |
| **同条目多名命中去重取最高级别** | EntryResolver | 补测 `sameEntryMatchedByMultipleNamesDedupKeepsHighestScore` | ✅ |
| **双向子串两方向命中级别各自正确** | EntryResolver | 补测 `bidirectionalMatchLevelsAreDistinguished` | ✅ |
| **三工具关闭提示完全一致** | RetrievalTools | 补测 `disabledHintIdenticalAcrossAllThreeEntryTools` | ✅ |

## 三、测试代码审计结论（coder 自报 14 用例）

1. **断言有效性**：13/14 有效。1 例断言偏弱——`substringSearch("强化火球术射程")` 注释声称"前缀命中"，但按 `matchScore` 实际为子串命中（score 2，term 不以 title 开头）；且该查询只有单候选，`containsExactly` 无法区分命中级别（Minor-1）。
2. **正常路径覆盖**：命中排序、别名/全半角归一、module 收窄、溯源挂号、精确提示、缺原文容错均有用例。
3. **错误路径覆盖**：空术语、未知模块、无命中回退、开关关闭均已覆盖；参数校验顺序（开关→空术语→模块）与设计一致。
4. **偏差复核**：coder 自报两项偏差（前缀双向归组、精确提示多一次 resolve 调用）均属实，实现与方案 J7 无其他偏差。
5. coder 自报数字复核：364+14=378 与首次跑测一致；补测后 382。

## 四、缺陷分级

### Minor（留用户拍板）

- **M1 测试断言与注释不符**：`substringSearchRanksExactPrefixAndSubstringWithShortTitleFirst` 中"强化火球术射程"例实为子串命中（score 2），注释称前缀；单候选断言不判别级别。已由补测 `bidirectionalMatchLevelsAreDistinguished` 补强覆盖，是否回改 coder 注释由用户定。
- **M2 关闭提示仅逐工具断言"包含"关键词**：三工具是否返回同一段文案此前无强断言。补测 `disabledHintIdenticalAcrossAllThreeEntryTools` 已用 `isEqualTo` 锁死。实现侧本就复用同一常量，无功能缺陷。
- **M3 默认上限 20 的端到端截断路径此前未测**：coder 用 Reflection 把 maxResults 设为 1 只验证"截断机制"；默认 20 下"截断 + 短名优先"由补测 `singleCharTermCapsAtDefaultMaxResultsWithShortTitleFirst`（25 条候选）覆盖。

### 非缺陷说明

- `formatKeywordHits` 内使用全限定 `java.util.ArrayList/HashMap`：与项目 import 风格不一致，纯风格问题，随下次触碰清理即可。
- 精确同名提示走 `resolve(term, module)` 二次查索引：每次命中多一次 map 查找，开销可忽略，coder 已声明。

## 五、补测清单（tester 新增 4 用例）

1. `EntryResolverTest.singleCharTermCapsAtDefaultMaxResultsWithShortTitleFirst` — 25 条前缀同级候选，验证默认 20 截断、最短 title 排首、第 20 位正确。
2. `EntryResolverTest.sameEntryMatchedByMultipleNamesDedupKeepsHighestScore` — title 子串(2) + 别名精确(0) 命中同 chunk，验证去重且取最高级别排最前。
3. `EntryResolverTest.bidirectionalMatchLevelsAreDistinguished` — 方向一（term 含 name 且以其开头=前缀，对手条目不误命中）；方向二（name 以 term 开头=前缀 vs name 仅含 term=子串，级别可区分）。
4. `RetrievalToolsKeywordSearchTest.disabledHintIdenticalAcrossAllThreeEntryTools` — resolveEntry/getEntryLinks/keywordSearch 在索引关闭时返回完全相同的固定提示。

## 六、验证记录

- `cd pf_agent/agent && mvn test`：Tests run: 382, Failures: 0, Errors: 0, Skipped: 0，BUILD SUCCESS（补测前 378 全绿，补测过程发现 1 例夹具语义错误并已修正后复跑全绿）。
