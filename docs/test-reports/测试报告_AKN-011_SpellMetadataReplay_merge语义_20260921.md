# 测试报告

## 测试对象与范围

- **被测内容**：AKN-011 修复——`SpellMetadataReplayTool.replay()` 由"整表替换"改为 merge 语义（mapper 键以 mapper 为准，mapper 之外的键保留），幂等判断相应改为"merge 结果与存量 metadata 逐条一致才跳过"。
- **改动文件**（工作区未 commit，基线 commit `ccdfd01`，分支 dev/pf-agent）：
  - `pf_agent/agent/src/main/java/com/pfagent/agent/rag/SpellMetadataReplayTool.java`
  - `pf_agent/agent/src/test/java/com/pfagent/agent/rag/SpellMetadataReplayToolTest.java`
  - `docs/已知问题记录_agent.md` AKN-011 节
- **测试范围**：黑盒全量测试（基线 400 用例）+ 白盒审计 merge 实现边界条件 + 边界补测。

## 测试设计

- 黑盒：`cd pf_agent/agent && mvn -q -B test` 全量回归。
- 白盒审计点（逐项见下节）：
  1. mapper 键集合缩小（mapper 不再产出的键）时的行为；
  2. oldMeta 为 null / 空 / 非 Map / 缺 chunk_id；
  3. extra 键与 mapper 键同名冲突的类型覆盖；
  4. 多 chunk 混合场景与幂等（第二次 skipped）；
  5. 泛型拷贝 `String.valueOf(key)` 的键类型隐式转换风险；
  6. `merged.equals(oldMeta)` 幂等比对在 merge 语义下是否成立。
- 未覆盖项：真实启动门控（`pf.stores.metadata-replay=true` 触发 run()）未做端到端启动验证——属一次性运维工具，由 `runSatisfiesCommandLineRunnerContract` 单测覆盖接线契约，风险可接受。

## 黑盒测试结果

| 用例 | 预期 | 实际 | 结论 |
|---|---|---|---|
| `mvn -q -B test` 全量 | 全绿（基线 400） | 401 tests / 0 failures / 0 errors（42 个测试类 surefire 报告全部无 FAILURE/ERROR） | ✅ 通过（+1 为本次边界补测） |

证据：`grep -h "Tests run" target/surefire-reports/*.txt` 汇总得 tests: 401, failures: 0, errors: 0；`SpellMetadataReplayToolTest` 7/7 通过。

## 白盒审计结果

**对 coding agent 测试代码的审计**：既有 6 用例断言有效（含具体值断言，无假测试）；新增 AKN-011 用例 `replayMergesMetadataKeepingExtraKeysAndStaysIdempotent` 真实构造"旧值被 mapper 覆盖 + 离线 entry_links 键"场景，断言覆盖 extra 键保留、mapper 键覆盖、二次 skipped，质量合格。

**merge 实现边界审计（逐项）**：

1. **mapper 键集合缩小（mapper 不再产出的键）**：实现为 `merged = copy(oldMeta) + putAll(fresh)`，mapper 退化的键**保留旧值不被清除**。与 KN-011 登记口径（"mapper 产出的键以 mapper 为准；mapper 之外的键保留不动"）**一致**——退化的键在 merge 语义下即属"mapper 之外的键"。⚠️ 语义后果：若未来 mapper 主动下线某键（如 spell_level_xxx 键名变更），旧键会作为脏数据永久残留，幂等比对（merged.equals(oldMeta)）亦不会察觉。符合登记的 merge 语义，**如实记录、不判 fail**，列为存疑项交主 Agent/用户知悉。
2. **oldMeta 为 null / 非 Map**：`!(metaObj instanceof Map)` → 静默跳过，不计数、不破坏。已补测固化。
3. **oldMeta 为空 Map / 缺 chunk_id**：计入 missed（漂移告警）。已补测固化。
   - 观察项：当 replayed==0 时 `ReplayStats.skip()` 丢弃 missed 计数（本次补测首次断言 missed==1 失败，核实为 skip() 返回 (0,0,true)）——即"只有漂移、无待更新"时统计与 warn 日志有但返回值不体现。行为无害（warn 日志仍在），列为 Minor 观察项。
4. **extra 键与 mapper 键同名冲突**：`putAll(fresh)` 无条件覆盖，mapper 胜；fresh 为 null 值的键会把旧值覆盖为 null（mapper 产出 null 值的可能性低，mapper 侧不产 null 键值）。已有用例覆盖"旧值被覆盖"路径。
5. **多 chunk 混合场景**：jsonl 内重复 chunk_id 时 `index.put` 后者覆盖前者；store 内同一 chunk_id 多条 doc 各自独立 merge。均为合理默认，无共享可变状态泄漏（每条 `mapper.toDocument` 产出独立 metadata）。
6. **幂等**：merge 后再 merge，结果逐字一致（`merged.equals(oldMeta)` 为真）→ 跳过。已有用例（2 个）覆盖；equals 为 Map 内容比较，与 LinkedHashMap 顺序无关，判断成立。
7. **`String.valueOf(key)` 键类型转换**：store JSON 经 Jackson 反序列化后键必为 String，`String.valueOf` 实际为恒等操作，无隐式转换风险。理论残留：若 oldMeta 含 null 键，`String.valueOf((Object)null)` 会得到字符串 `"null"` 键并触发一次无意义写盘——但 JSON 对象键不允许 null，实践中不可达，不补测。

**补充测试**（工作区直接修改测试文件，未 commit）：
- 新增 `replayLeavesMalformedDocsUntouched`：构造 metadata 空 Map / 整体缺失 / 非 Map 三类畸形条目，断言不被破坏、不参与 merge、写盘被跳过（replayed==0 走 skip 路径不覆写文件）。运行结果：7/7 通过。

## 缺陷清单

| 编号 | 严重级别 | 描述 | 复现步骤 |
|---|---|---|---|
| — | — | 本轮未发现 Blocker/Major 实现缺陷 | — |

观察项（不构成缺陷，供拍板）：
- **观察-1（Minor）**：`ReplayStats.skip()` 丢弃 missed 漂移计数——store 全部条目要么已一致、要么漂移时，返回值 missed=0 且 skipped=true，仅 warn 日志体现漂移。如需统计可让 skip 路径透传 missed。
- **观察-2（语义存疑）**：mapper 键集合缩小（mapper 主动下线/改名键）时，旧键按 merge 语义永久保留，无清理机制。与 AKN-011 登记口径一致；若未来出现 mapper 键下线场景，需另行处理（如 KN 登记或加白名单删除）。

## 结论与建议

**通过（有条件）**。merge 语义实现正确，AKN-011 核心诉求（mapper 之外的 metadata 键如未来 `entry_links` 不再被重放抹除）已达成并有测试固化；黑盒 401/401 全绿。放行建议：两个观察项均不阻塞，建议由主 Agent/用户知悉后在 KN 中登记口径（尤其观察-2 的"mapper 键下线残留"语义确认）。

## 需求澄清项

1. mapper 键集合缩小（mapper 不再产出某键）时，存量该键按 merge 语义**保留旧值**——是否与"mapper 键以 mapper 为准"的设计意图完全吻合？当前 KN-011 登记口径支持保留行为，如需"mapper 缺席即删除"需另行实现。
2. 仅漂移无更新时 missed 计数被 skip() 丢弃，是否需要透传？
