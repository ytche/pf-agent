# 测试报告

## 测试对象与范围

- 被测内容：KN231 — `pf_data/phase1/vectorizer/config/trait_sources.json` 存量清理（工作区未 commit，分支 dev/pf-agent）
  - 7 本书中文 abbr → ASCII 归一：星辰之民→PoS、任务与战役→Q&C、混种→BaG、狗头人→KobG、矮人→DwaG、精灵→EoG、秽邪勇士→CoCorr
  - AA 撞键消歧（撞车侧=trait）：秘术选集 Arcane Anthology abbr AA→ArAn，4 个别名 key 同步
  - 别名 key "Quests and Campaigns" 的 en 拼写统一为 "Quests & Campaigns"
  - 「均衡信念」en（Champions of Balance）挂起未动（待审批）
  - KN231 登记节更新（`pf_data/phase1/docs/已知问题记录.md`）
- 对应文档：`pf_data/phase1/docs/已知问题记录.md` KN231 节
- 代码版本：dev/pf-agent 工作区（基线 HEAD `ae5acf9` 配置 + 未 commit 改动）
- 测试方产出（未纳入被测范围）：新增回归锁测试 `pf_data/phase1/vectorizer/tests/test_trait_kn231_config_lock.py`

## 测试设计

| 类别 | 用例数 | 说明 |
|---|---|---|
| 黑盒 | 2 | verify 四步链首跑 + 复跑；产物漂移检查 |
| 白盒/配置审计 | 8 项脚本检查 | 全表条目数、key 结构完整性、8 书全别名 key abbr 一致性、CJK abbr 残留、feat 撞键比对、KN230 脏值复用、模块内 abbr→en 唯一性、均衡信念 en 未动（git diff 0 命中） |
| 白盒/测试审计 | 1 文件审计 | coder 未新增/修改任何测试（status 证实），既有 `test_trait_book_abbreviation.py` 审计 |
| 产物审计 | 1 | 用 HEAD 基线配置重建产物，逐 key 比对 book_abbreviation 分布 |
| 补充回归锁 | 14 用例 | 新增 `test_trait_kn231_config_lock.py` |

未覆盖项：无（KN231 范围全部可测点已覆盖）。

## 黑盒测试结果

| 用例 | 预期 | 实际 | 结论 |
|---|---|---|---|
| `python3 -m vectorizer.cicd verify --category trait` 首跑 | 四步链（单测/pipeline 重生成/集成验收/数据不变量）全绿 | 全绿，✅ trait 完整验证链通过（8/8 集成验收，不变量全过） | 通过 |
| 复跑 verify | 仍全绿，无漂移 | 复跑全绿；`git status` 仅预期文件变动，feat/race/equipment 等产物 hash 不变 | 通过 |

关键证据：复跑后 `git status --short pf_data/phase1` = docs/已知问题记录.md、build_manifest.json、cicd/verify.py、config/trait_sources.json、state/build_state.json（后三者说明见「缺陷/观察」）；build_state.json 中 feat/race/equipment/rule/spell 输出 hash 与 HEAD 完全一致，仅 chunks.trait 的 chunks.jsonl hash 变化（预期内）。

## 白盒审计结果

**配置全表审计（脚本逐条取证，非抽样式目测）**：

1. 条目数：现表 163 = 旧表 163，别名 key 零丢失、零新增。
2. 8 本书全别名 key abbr 一致性（每书 key 数 / 统一 abbr）：
   - 星辰之民 3 key→PoS ✓；任务与战役 3 key→Q&C ✓（en 全为 "Quests & Campaigns"）；
   - 混种 2→BaG ✓；狗头人 2→KobG ✓；矮人 2→DwaG ✓；精灵 2→EoG ✓；秽邪勇士 2→CoCorr ✓；
   - 秘术选集 4 key（秘术选集/AA/Arcane Anthology/基础页AA）→ArAn ✓。无漏 key。
3. 全表 CJK abbr 残留：0（`re [\u4e00-\u9fff]` 全量扫描）。
4. 与 feat_sources.json 全表（sources + abbr_candidates 两表）撞键比对：新缩写集 {PoS,Q&C,BaG,KobG,DwaG,EoG,CoCorr,ArAn} 与 feat 全表 abbr 交集为空；KN230 脏值 {CoP,CoB,CoC,ArcaneAnthology,Dragonslayer,CAMPAIGN} 零复用。
5. trait 模块内 abbr→en 唯一性：无任何 abbr 映射到多个 en（各 abbr 的多处出现均为同一书的多别名 key）。
6. 「均衡信念」：`git diff` 对该文件 0 行命中，条目 en 保持 Champions of Balance 未动 ✓。
7. KN231 登记节：处置清单（7 书选型理由含 BoG/KoG/DoG 避让、KN230 脏值避让、ArAn 候选说明、挂起项声明）与 diff 实际改动逐条一致 ✓。

**对 coder 测试代码的审计**：

- KN231 未新增/修改任何测试文件（git status 证实）。既有 `test_trait_book_abbreviation.py`（7 test）无假测试，含模块内撞键守卫（`test_abbr_maps_to_single_en_within_trait`）与非空健康断言；注释中"AA 撞键不在本批"的口径已被 KN231 处置取代。
- **覆盖盲区**：没有任何测试锁定 KN231 的 8 个新 abbr 取值、CJK abbr 零残留（config 层，verify 检查 7 只兜产物层黑名单 6 值）、feat 撞键、KN230 脏值、以及"均衡信念 en 挂起期间不得被改动"这条审批约束。配置回归保护缺失。

**补充测试**：新增 `vectorizer/tests/test_trait_kn231_config_lock.py`（14 用例，全部通过；并入 verify 四步链后复跑全绿）：
- 8 书 × 全别名 key abbr 锁定（parametrize，含 key 丢失检测）；
- 全表 CJK abbr 零残留；旧 en 拼写 "Quests and Campaigns" 复活检测；
- 新缩写集 ∩ feat 全表 = ∅；∩ KN230 脏值 = ∅；模块内 abbr→en 唯一性；
- 挂起条目「均衡信念」en 锁定为 Champions of Balance（防静默改动）。

## 产物审计

方法：stash 仅 trait_sources.json → HEAD 基线配置重跑 verify 取基线分布 → pop → 新配置重跑 → 逐 key 比对 `vectorizer/output/背景特性/chunks.jsonl` 的 book_abbreviation 分布。

| 检查 | 预期 | 实际 | 结论 |
|---|---|---|---|
| 分布差异 | 零变化或仅登记口径变化 | 唯一差异：AA 22→15、ArAn 0→7（同一批 Arcane Anthology chunks 重打标，属 KN231 既定消歧的直接产物效果）；其余全部 key 分布一致 | 通过（在 KN231 口径解释范围内） |
| 7 书 CJK 清理产物效果 | — | 无差异：PoS/EoG 等在旧产物中已是 ASCII（这批 chunks 原文即英文缩写，config abbr 不参与），故 7 书清理产物零变化属实 | 通过 |
| 残留 AA 15 条归属 | — | 全部 (冒险者的军械库, Adventurer's Armory)，与"feat 侧 AA 保持不变"拍板一致，非 trait 侧漏改 | 通过 |
| 跨类目漂移 | feat/race/equipment 等 hash 不变 | build_state 中各类目输出 hash 与 HEAD 一致（仅 fingerprint/时间戳更新） | 通过 |

说明：用户背景中"这批配置条目产物 0 命中"的口径对 7 书清理成立，但 AA→ArAn 有 7 条产物重标——这是消歧的预期行为，非意外。

## 缺陷清单

| 编号 | 严重级别 | 描述 | 复现步骤 |
|---|---|---|---|
| D1 | Minor | 工作区混入与 KN231 无关的在途改动：`cicd/verify.py`（KN227 skill 接入 CATEGORIES）与 `build_manifest.json`（chunks.skill via direct→cicd）在本验收期间出现修改，非本验收产生亦非 KN231 范围 | `git status` 可见；`git diff` 内容为 KN227 登记文案 |
| D2 | Minor（已闭环） | coder 未为 KN231 补任何配置回归测试，8 新 abbr/脏值避让/挂起条目约束均无锁定 | 审计 `vectorizer/tests/` 无 KN231 相关新增；已由 tester 补 `test_trait_kn231_config_lock.py` 14 用例闭环 |

无 Blocker/Major 缺陷。实现本身（trait_sources.json 改动 + 登记节）零缺陷。

## 结论与建议

**通过（建议放行 KN231 部分）。** verify 四步链首跑+复跑全绿；8 本书全别名 key 无漏改；feat 撞键与 KN230 脏值避让经全表逐一比对确认；均衡信念 en 经 git diff 证实未动；产物仅 AA→ArAn 7 条预期内重标，无漂移。

给验收方的关注点：
1. 提交时请将 KN231（trait_sources.json + 已知问题记录.md + 新增测试文件）与 KN227 在途改动（verify.py、build_manifest.json）分开 commit，避免审批串味。
2. build_state.json 的 fingerprint/时间戳更新是 verify 链的正常副作用，随提交一并入库即可（参照 KN229 先例）。
3. 遗留挂起项：「均衡信念」en 订正（Champions of Balance → Faiths of Balance）仍待用户审批，本次未动，审批通过后需另行处置并解锁回归测试中相应断言。

## 需求澄清项

无。文档与登记节口径清晰可测。
