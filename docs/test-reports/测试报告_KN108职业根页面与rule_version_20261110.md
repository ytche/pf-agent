# 测试报告：KN108 职业根页面纳入与 rule_version 标注（含职业向量库重灌）

日期：2026-11-10 ｜ 执行：KN108 实施链（Task 1~5）｜ 方案：`docs/design/方案_KN108职业根目录页面纳入与rule_version_20261109.md` ｜ 计划：`docs/superpowers/plans/2026-11-10-kn108-profession-root-pages-rule-version.md`（5 Task，TDD 全程）

## 结论：通过（KN108 闭环，DVG-014 清偿）

职业 chunks **13922 → 14060**（+138 行 / +138 唯一 chunk_id，全部新增属于且仅属于 7 个 logical doc_id）；
旧块零回归（唯一差异 = 全部旧块 metadata 新增 `rule_version` 键）；职业 CICD 集成验收 **11/11**；
全量 pytest **1848 passed**；源哈希 7/7 OK；双跑构建指纹一致；`build check` **14/14 artifact 全绿**；
职业向量库全量重灌 **14060 条**，store 与产物逐条一致，7 页锚点抽验全部命中。

## 1. 根因

- **输入范围缺口**：7 个职业相关源页位于 `pf_rules_md_organized/` 根目录，`formats/profession.py` 的 `INPUT_DIR=.../职业` + `processors/profession.py:3274` `_profession_file_condition()` 的 `relative_to(INPUT_DIR)` 对根目录文件抛 `ValueError` → 永不派发 → 7 doc_id 产物为 0。
- **rule_version 缺失**：职业 chunk 无版本标注；先例技能/规则/装备均按书缩写小写标注。
- **真实产物二次暴露的契约不一致（Task 4 定位）**：职业处理器把 Markdown 加粗标题行解析为 chunk `title`、不进 `text`；而闸口检查 10 只拼接 `text` 做锚点子串匹配 → 6 个锚点（部分连 title 都没有）在真实产物上缺失，单测因用合成数据（锚点直接写进 text）而全绿漏检。

## 2. TDD 红绿证据

- **Task 1/2（纳入与 rule_version）**：文件选择/逻辑路径/优先级/空值/page_244 覆盖测试先红后绿（commit 链见 task-4-report）。
- **Task 4 RED**：`test_profession_kn108.py::test_real_root_pages_pass_verify`——聚合 7 页真实 `proc.process()` StandardChunk，经 `dataclasses.asdict` 调 `check_kn108_root_pages`，首次运行 FAILED，真实缺失与预期完全一致（page_30 职业概述/术语定义、page_53 武僧清规、page_128 全进阶职业一览、page_134 进阶要求、page_244 对PFS官方游戏的影响）。
- **GREEN（commit `2c7dd0a`）**：`_preserve_root_heading_text(lines)`——清单 7 页在 `clean()` 后每条非空 `#` 标题保留原行、下一行插入去 `#` 纯文本标题；`keep()` 增加根页豁免（携带锚点副本块必须保留，带 `len(text) <= 5000` 守卫对齐 oversize 闸口）。
- **副作用处置（commit `ccafbca`）**：豁免救回的无关超大块回落（oversize 15/15）；page_30/page_128 经既有 `book_override` 机制登记 CRB 来源（裁定依据见方案 §4.1：page_30.md:56、page_128.md:22/64-67），book '?' 归零。
- **评审补记（commit `5148da3`）**：方案文档补记 §4.1 CRB 来源裁定，对齐代码实际口径。

## 3. 7 页锚点（真实产物，集成验收检查 10 通过）

| 页 | 锚点 | 产物块数 | 结果 |
|---|---|---:|---|
| page_30 职业概述 | 职业概述 / 术语定义 / 施法者等级 | 8 | ✅ |
| page_53 武僧清规 | 武僧清规 + 8 戒（不邪淫/囚执/清净/持斋/不杀生/安贫/不语/不妄语） | 10 | ✅ 8/8 |
| page_128 进阶职业 | 进阶职业 / 全进阶职业一览 | 2 | ✅ |
| page_134 龙脉术士 | 龙徒 / 进阶要求 / 角色定位 | 14 | ✅ |
| page_244 掉链子 | 对PFS官方游戏的影响 | 1 | ✅ |
| page_411 幻灵 | 幻灵 / 生命骰 / 基本攻击加值 / 技能 / 专长 | 93 | ✅ |
| page_609 神话冒险 | 大法师 / 斗士 / 守护者 / 圣者 / 统帅 / 诡术大师 | 10 | ✅ 6/6 |

7 页 `source_paths == [doc_id]` 逐块验证通过；检查 11（rule_version）通过。

## 4. 真实前后计数与 rule_version 分布

- 行数/块数：基线 13922 → **14060**；全局唯一 chunk_id 13771 → 13909（+138）。
- rule_version：**标注 14060/14060、省略 0**（110 个取值）；top：crb 2743、apg 1822、acg 1329、oa 1069、unchained 1061、uc 561、ui 555、ma 485、um 454、uw 426。
- 7 页分布：page_30 crb×8；page_53 crb×9+pfs×1；page_128 crb×2；page_134 crb×14；page_244 unchained×1；page_411 apg×91+amh×1+ush×1；page_609 ma×10。
- page_244 专项：`component_type=class_overview`、`class_name` 空、`book_abbreviation=PFS` / `book_name_cn=探索者协会` / `book_name_en=Pathfinder Society`、`rule_version=unchained`、无 `pfs_eligible` 键。

## 5. 逐 chunk 对账（零回归）

基线 `/tmp/kn108_profession_chunks_before.jsonl` vs 终产物：旧块缺失 **0**；旧块 `doc_id/toc/class_name/title/text` 与原 metadata 键值零变化、零删除；**唯一差异 = 全部旧块 metadata 新增 `rule_version`**；顶层键零增删；新增 138 块全部属于且仅属于 7 个 logical doc_id（无一旧 doc 新增块）；召唤师及其他非目标 doc 无漂移；负向断言（清单外根目录文件零新增）通过。

**既有债（登记不修，非本批问题）**：基线与现产物各含 **102 个历史重复 chunk_id 行**，重复集合前后完全一致——既有现象，本批未引入、未扩大，只登记。

## 6. 全量 pytest / 双跑指纹 / build check / 源哈希

- 全量 `python3 -m pytest vectorizer/tests -q`：**1848 passed**（13.1s 量级）。
- 源哈希 `shasum -a 256 -c /tmp/kn108_sources_before.sha256`：7 个源文件（page_30/53/128/134/244/411/609.md）**7/7 OK**（源数据零改动）。
- 可复现：`build chunks.profession --force` ×2，chunks.jsonl SHA-256 均为 `f75229ae9dc36e09f3faf7ab8e4321e7c3d5c7a3bfd13c057e2f258b82fce779`（index.json 同口径一致）。
- `python3 -m vectorizer.build check`：**14 个 artifact 全绿**（`build all --force` 统一迁移输入指纹；其余 12 个非目标 artifact 产物输出哈希逐一无变化，可归因）。
- 职业完整 CICD（提交态复跑）：pytest 285 过、集成验收 11/11、数据不变量全过（空 text 0/0、>5000 字符 15/15、book '?' 0/0、toc 空 0/0）。

### 6.1 合并验证追加修复：构建输入忽略 .DS_Store（2026-11-10，TDD）

- **根因**：合并验证暴露 `vectorizer/build.py::expand_inputs()` 把 glob 命中的 `.DS_Store` 当源文件计入内容指纹输入集合；主工作区存在这些 macOS 目录元数据文件而干净 worktree 没有，导致主工作区 `build check` 对 chunks.feat/race/equipment/profession 等输入指纹失败。已确认用相同算法仅排除 `.DS_Store` 后这四项与合并 state 精确匹配。
- **RED**：新增 `test_build.py::TestFingerprint::test_ds_store_excluded_from_expand_inputs`（嵌套目录下的普通源文件 + 两层 `.DS_Store`），断言 `expand_inputs(["src/**"], tmp) == ["src/a.md", "src/nested/b.md"]`；首跑 FAILED（实际返回含两个 `.DS_Store`）。
- **GREEN（最小修复）**：`expand_inputs()` 的 `is_file()` 判断追加 `p.name != ".DS_Store"`（任意层级 basename 过滤）；同步更新该函数 docstring。显式 `config_deps`/`script` 语义不变，无其他排除规则扩展。
- **证据**：聚焦测试 31 passed 全绿；全量 pytest **1848 passed**（1847→+1）；`build check` **14/14 通过**。`git status` 仅 build.py + test_build.py 两个代码文件变更，**产物与 `build_state.json` 零变化——无需重建、无需重灌，产物内容与 state 指纹不变**；不新增待办、不产生数据内容漂移、不新增 DVG。未删除/移动任何 `.DS_Store`。

## 7. 职业向量库全量重灌（DVG-014 清偿）

- **备份**：`~/.pf_agent/vector_store_classes.json` → `~/.pf_agent/vector_store_classes.json.bak_20261110_111024`（210,208,399 字节；唯一时间戳路径，未覆盖任何既有备份）。
- **导入**：worktree `pf_agent/agent/` 下 `PF_CHAT_MEMORY=memory mvn spring-boot:run -Dspring-boot.run.arguments="--server.port=0"`（随机端口临时实例；常驻 8080 实例全程未触碰）。ClassDataLoader 检测到库文件缺失后由 ChunkImporter 从本 worktree 最新 `vectorizer/output/职业/chunks.jsonl` 全量导入（每批 500 条，embedding 由本机 Ollama bge-m3 重算），未使用元数据重放或任何字段补丁，未改 Java。
- **结果**：日志显示导入完成 **14060 条**并持久化（首轮导入曾因执行环境超时中断于 8582/14060，持久化仅在收尾执行故未产生半成品库；旧备份全程完好，重启临时实例（无超时限制）后全量重导成功，耗时 1893 秒）；临时实例已停止，本机无残留 Java 进程，常驻 8080 实例全程未触碰。
- **核对**：全量比对 store 与 chunks 的 `chunk_id`（14060 行对 14060 行，唯一 id 13909 对 13909，含 102 个历史重复行按多重集合口径）、`text` 及 Mapper 已支持标准字段（doc_id/category/component_type/title/book_name_cn/book_name_en/book_abbreviation/tocPath/aliases/class_name/archetype_name/feature_subtype）——逐字段多重集合完全一致、零差异（102 个重复组内文本相同而 book/archetype 各异，为既有历史现象，两边集合一致）。
- **抽验**：武僧 8 戒 8/8、龙徒「进阶要求」、原版幻灵「生命骰/基本攻击加值」、6 道途 6/6、page_244（PFS 来源三键 + class_overview + class_name 空）全部命中。
- **口径说明**：职业 Mapper 本批不暴露 `rule_version` 专用字段（方案 §5 明确不改 Java），store 无该键为既定口径，不视为重灌缺陷；检索端消费方式后续单独立项。
- 旧库备份保留于 `~/.pf_agent/`；常驻 8080 实例下次重启自动加载新库。

## 8. 状态源同步（同批）

- KN108 源记录（`pf_data/phase1/docs/已知问题记录.md`）闭环 + 修复记录；设计方案状态改已闭环并补交付记录；DVG-014 新增并清偿（`docs/数据一致性技术债务登记.md`）；一期临时汇总移除 KN-108（18→17 项，31→30 项）；项目文档总索引当前队列与测试报告索引各加条目；PROJECT_HANDOVER 顶部与 KN108 行更新；实施计划 Task 1~5 步骤全部勾选并补执行状态。其他待办状态一律未动。

## 9. 遗留与说明

1. 102 个历史重复 chunk_id：既有债（前后集合一致），登记不修，不在本批顺手处理。
2. page_30/page_128 CRB 来源登记为任务族内语义裁定（方案 §4.1）；如后续有异议走 KN 裁定改 `book_override`，不涉及棘轮参数。
3. page_411 因 keep 豁免新增 4 个 ≤5000 字符锚点副本块（93 vs 89），均属新增 logical doc_id，对账合规。
4. 评审 2 Minor（keep() 5000 常量化、标题正则 `#` 后空格）按意见登记待办，未处理。
