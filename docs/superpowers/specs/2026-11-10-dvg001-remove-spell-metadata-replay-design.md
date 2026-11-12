# DVG-001 删除法术元数据重放第二写路径设计 Spec

- 日期：2026-11-10
- 状态：✅ 已实施并合并（2026-11-11；`f9c5276`，合并 `6b0c78b`；复审 clean）
- 实施计划：`docs/superpowers/plans/2026-11-11-phase1-five-specs-implementation.md`（Task 2）
- 实施证据：`docs/test-reports/测试报告_一期五项Spec收口_20261111.md`；`DeprecatedMetadataReplayGuardTest` 6/6；旧配置 true 在临时实例实测启动失败
- 实施结果：`SpellMetadataReplayTool` 与专属测试彻底删除，配置键移除；旧配置 `pf.stores.metadata-replay=true` 由最高优先级只读闸口 fail-fast；唯一写路径固化为「数据侧产物 → 全量重灌」（`docs/DEPLOYMENT.md` §六）
- 关联：DVG（数据漂移债务）001、AKN（Agent已知）011、F（功能想法）017、F（功能想法）012
- 主要读者：后续负责 Java 启动链、向量库重灌、部署文档、测试与验收的实施者

## 1. 背景与现状

`SpellMetadataReplayTool` 最初用于旧法术向量库的 metadata 迁移：读取 chunks.jsonl，通过当前 `SpellChunkMapper` 生成新 metadata，再合并写回本机 `vector_store_spells.json`，保留 text 和 embedding。

它解决了当时不愿重算 embedding 的迁移成本，但也形成两条写路径：

1. 数据侧产物 → Java DataLoader 全量重灌；
2. Java 启动时通过 metadata replay 改写现有向量库。

当前 `pf.stores.metadata-replay` 默认已是 `false`，因此不是每次启动都写库；但只要 bean 和配置仍存在，就能通过一次启动绕过全量重灌。历次需要该工具的迁移已经完成，近期各模块也已多次验证全量重灌路径，具备彻底删除条件。

## 2. 目标与非目标

### 2.1 目标

1. 彻底删除 Java metadata replay 写库能力，收敛为“数据侧产物 + Java 全量重灌”唯一路径。
2. 旧配置被误设为 `true` 时明确失败，不静默忽略并制造“迁移已执行”的错觉。
3. 用现有临时实例流程形成可执行、可备份、可对账的全量重灌手册。
4. 保留历史迁移事实，同时让现役文档不再提供重放入口。
5. 保证默认启动、检索和现有向量库不受删除影响。

### 2.2 非目标

- 不保留默认禁用的 replay bean 作为后备。
- 不把 replay 改成独立离线 Java 工具。
- 不新增自动重灌脚本或第二重灌入口。
- 不因本批代码删除而重建 chunks 或重灌任何向量库。
- 不改写历史测试报告，抹除曾经存在 replay 的事实。
- 不处理 AKN-016/AKN-020 的旧 Map 重载或其他技术债。

## 3. 已确认的核心决策

| 决策点 | 结论 |
|---|---|
| 清偿方式 | 彻底删除重放工具、专属测试与现役配置说明 |
| 旧配置 `true` | 启动失败并给出全量重灌指引 |
| 旧配置缺失/`false` | 正常启动，无行为变化 |
| 防误用闸口 | 长期保留，只读、不写库 |
| 启动顺序 | 最高优先级，先于其他 CommandLineRunner |
| 唯一重灌路径 | 在 DEPLOYMENT 新增临时实例全量重灌章节，不新增脚本 |
| 历史文档 | 保留历史记录，追加退役结论；现役文档移除可执行重放指引 |
| 本批数据动作 | 不重建、不重灌 |
| F-017 后续元数据 | 数据侧产物 → Mapper → 全量重灌，禁止恢复 replay |

## 4. 删除与防误用设计

### 4.1 删除范围

- 删除 `SpellMetadataReplayTool.java`。
- 删除 `SpellMetadataReplayToolTest.java`，不保留死测试或跳过测试。
- 从 `application.yml` 移除原 replay 工具配置说明。
- 不保留 `replay()` 公共方法、离线 main 方法或其他 Java metadata 写库替代入口。
- `TelemetryImporter` 中对 replay 的参考注释改为通用一次性开关说明，消除语义依赖。

### 4.2 长期防误用闸口

新增 `DeprecatedMetadataReplayGuard`：

- 使用 `@ConditionalOnProperty(name="pf.stores.metadata-replay", havingValue="true")`，仅旧配置显式为 true 时装配；
- 实现 `CommandLineRunner`，运行时抛出明确异常，终止启动；
- 使用 `@Order(Ordered.HIGHEST_PRECEDENCE)`，确保先于其他启动 runner；
- 不读取或修改 store，不调用 Mapper，不执行任何迁移；
- 配置缺失或为 false 时不装配，不影响现有启动。

错误信息至少包含：

```text
SpellMetadataReplayTool 已删除，pf.stores.metadata-replay=true 不再受支持。
请将该配置移除或设为 false，并按 docs/DEPLOYMENT.md 的 chunks 全量重灌流程处理；
不要直接修改 vector_store JSON。
```

闸口长期保留，防止历史部署命令、环境变量或文档在未来被误用。

## 5. 唯一全量重灌手册

在 `docs/DEPLOYMENT.md` **新增全量重灌章节**，固化以下流程。当前 DEPLOYMENT 没有该章节，临时实例经验散见于 DVG 记录；本任务不是寻找一个现成手册。手册使用现有 DataLoader，不新增脚本或 metadata 合并逻辑。

### 5.1 适用范围

仅用于 chunks 内容、边界、元数据或 Mapper 消费字段变化导致的向量库更新。独立清单 JSON 变化走对应消费者重启，不使用本流程重算 embedding。

### 5.2 执行步骤

1. **确认消费面**：明确目标模块、chunks 路径、store 路径和当前运行实例。
2. **备份旧库**：将现有 store 移到带时间戳且不会覆盖既有备份的路径，禁止无备份删除。
3. **临时实例重灌**：临时实例与正式实例使用同一 `user.home` 和同一目标 store 路径；旧 store 已移走后，使用 `PF_CHAT_MEMORY=memory` 和随机端口，从对应 `chunks.jsonl` 全量导入并持久化到该路径。`PF_CHAT_MEMORY=memory` 只隔离会话数据库，不能改变 store 路径；常驻实例暂不受影响。
4. **产物对账**：核对新 store 与数据侧产物的条数、`chunk_id`、text、Mapper 应支持字段和目标锚点。
5. **失败回滚**：若导入或对账失败，停止临时实例，移除仅本次新生成且未通过验收的 store，将备份恢复到原路径；不重启或切换正式实例，保留失败日志供排查。
6. **切换正式实例**：对账通过后停止临时实例，重启正式实例，确认它加载新库。
7. **真实验证**：在已加载新库的实例上执行真实检索或问答，记录端口/实例和结果。
8. **保留备份**：旧库备份不自动删除，后续清理由用户另行决定。

手册必须给出与当前项目配置一致的启动命令、目标 store 路径、条数与字段对账命令示例，不得只写“删除后重启”或只写原则。

## 6. 文档与历史口径

### 6.1 DVG-001

实施验证完成后：

- 状态改为“已清偿”；
- 记录删除的类、旧配置闸口、测试证据和 DEPLOYMENT 手册入口；
- 明确唯一写路径为“数据侧产物 → Java 全量重灌”；
- 一期临时汇总移除该待办并同步计数和项目索引。

设计 Spec 阶段只更新设计状态，不提前销账。

### 6.2 AKN-011

保留 merge 语义的历史修复记录，追加：

- replay 工具已彻底删除；
- merge 语义不再是现役路径；
- AKN-011 不因删除而重开。

历史测试报告和开发决策日志保留原貌。现役配置、部署手册、索引和交接说明不得再把 replay 作为可执行步骤，并需处理两处已知引用：

- `docs/数据一致性技术债务登记.md` DVG-002 的历史重放操作保留，但追加“历史操作，现役不得再执行”及 DVG-001 退役指针；
- `pf_agent/agent/docs/一期规则问答Agent决策链设计.md` 中“复用 SpellMetadataReplayTool 重放”的现役指引改为全量重灌路径。

### 6.3 后续元数据变更

F-017 未来新增 `entry_links` 等元数据时，只能走：

```text
数据侧 chunks.jsonl → Java Mapper → 全量重灌 → 对账与真实验证
```

不得引用 AKN-011 的历史 merge 方案恢复第二写路径。

## 7. 错误处理与边界

- 旧配置为 true：启动失败，错误信息必须可执行，不得只写“未知配置”。
- 旧配置缺失或 false：无警告轰炸，不影响启动。
- 闸口失败时其他 DataLoader 不得先写入 store。
- 默认启动不读取 replay 类，不要求 chunks 或 store 发生任何变化。
- 本批不删除或修改用户现有向量库及备份。
- 如发现其他现役 Java 写库路径，另登记 DVG，不借本批扩大删除范围。

## 8. 测试与验收

### 8.1 静态与单元测试

- `SpellMetadataReplayTool` 及专属测试完全删除，项目可编译。
- 闸口 true 时抛出包含退役说明和 DEPLOYMENT 指引的异常。
- 配置缺失/false 时正常，不装配闸口。
- 闸口具有最高执行优先级。
- 通过实施自查和 code review 确认现役 Java 不存在 replay metadata 写库方法，不新增脆弱的全文 grep 单测。

### 8.2 启动集成测试

1. 默认配置正常启动。
2. 旧配置 true 真实启动失败，并展示明确错误。
3. 使用带顺序记录的 spy runner 验证 guard 先于任一 DataLoader runner 执行，且 guard 抛异常后后续 runner 未被调用。
4. 不得仅用“既有 store 字节不变”作为 guard 有效性的证明，因为 DataLoader 对已存在文件本来就会跳过。
5. 默认实例完成一次真实检索或问答冒烟，确认正常链路不受影响。

### 8.3 回归与文档

- Java 全量测试通过；删除旧测试是预期数量变化，不以跳过保留。
- 本批不改数据产物，不伪造数据重建或重灌证据。
- DEPLOYMENT 手册命令与当前配置一致，备份、同一路径临时实例、对账、失败回滚、正式实例和真实验证步骤完整。
- DVG-001、DVG-002 历史注记、AKN-011、一期临时汇总和项目总索引状态一致。
- 历史文档仍可追溯，现役文档无 replay 可执行指引。

## 9. 后续实施方案边界

本 spec 只固定设计，不代替实施计划。后续计划至少区分：

1. 删除 replay 工具、测试和现役配置说明；
2. 新增最高优先级防误用闸口及测试；
3. 整理 DEPLOYMENT 全量重灌手册；
4. 启动集成验证、默认问答冒烟和全量测试；
5. DVG-001 清偿、AKN-011 注记、一期汇总移除和索引同步。

实施中不得顺手重灌向量库，也不得将 F-017 或其他 Java 写路径改造并入本批。
