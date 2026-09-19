# 测试报告：trait（背景特性）book 中文名归一修复（D1 同型）

- 被测 commit：`ab4c273`（未 push），分支 `dev/pf-agent`
- 对应方案：D1 feat 修复（`db479cf`）同型延伸，QA 复测 + 白盒审计
- 测试日期：2026-09-19
- 数据侧工作目录：`pf_data/phase1/`

## 测试对象与范围

- 落点：`vectorizer/config/trait_sources.json` 查表（零 pipeline/processor 代码改动）+ feat 已挂的 `abbr_candidates` 引用块通道
- 修复面：6 个中文 book 值 59 条 → 0；`格拉里昂的平衡勇士` 的 `book_name_en` 由臆造值订正为 `Champions of Balance`
- 验证代码：`vectorizer/verify/verify_traits.py` 检查 7（中文黑名单 + 全量中文兜底）/检查 8（negative 样例 chunk_id）；`vectorizer/tests/test_trait_book_abbreviation.py`
- 范围外（KN 登记范畴）：AA 跨模块撞键（trait=秘术选集 vs feat=冒险者的军械库）、trait_sources「均衡信念」en 误写

## 测试设计

- 黑盒：cicd 四步链、build check、产物独立全量扫描（非 ASCII abbr、`?` 数、总数、chunk_id 唯一性）、修复 chunk 三字段抽查（6 值 × 首 2 条）
- 白盒：verify 检查 7/8 断言强度审计；negative 样例取证（`git show ab4c273^` 还原修复前 mapping 重放）；HoG 人工核定取证（源文件引用块 + 缩写表登记）；GIANT/GoG/OoG 与 feat D1 登记比对；同模块撞键评估 + 补测

## 黑盒测试结果

| 用例 | 预期 | 实际 | 结论 |
|---|---|---|---|
| cicd verify trait 四步链 | 全过 | 全过（8/8 检查，含新增 7/8；`?`=99/205，1222 总数） | ✅ |
| build check | 无漂移 | 9 artifact 指纹一致 | ✅ |
| 产物非 ASCII book_abbreviation | 0（不限黑名单） | 0 | ✅ |
| `?` 数量 | 99 | 99 | ✅ |
| chunk 总数 / chunk_id 唯一 | 1222 / 唯一 | 1222 / 1222 唯一 | ✅ |
| 6 修复值分布 | 59 条 | HoG 24 + GnomeG 13 + GIANT 8 + GoG 7 + OoG 5 + CoB 2 = 59 | ✅ |
| 三字段一致性抽查 | abbr/cn/en 一致 | 6 值 × 2 条均一致；CoB 2 条 en=`Champions of Balance`（订正生效） | ✅ |
| `-k trait` 全量 pytest | 通过 | 165 passed（含 coder 13 用例 + QA 补测 2 用例） | ✅ |

## 白盒审计结果

1. **verify 检查 7**：实现为「黑名单 6 值 ∈ + `_has_chinese` 全量兜底」，硬断言 FAIL 路径完整，非装饰性检查。✅
2. **verify 检查 8（negative）**：6 个 chunk_id 经 `git show ab4c273^` 还原修复前 mapping 重放，5 条修复前 abbr 为中文书名、`巨人猎手手册` 修复前为缺键（走中文书名兜底），确为修复前中文样例。✅
3. **HoG 人工核定取证**：源文件 `格拉里昂的人类_种族背景特性.md` 引用块仅「格拉里昂的人类（Humans of Golarion）」，无 ASCII 缩写；`PF_缩写表.md` 已登记 `HoG ★` 并注明人工核定理由，与 EoG/HaG/DoG/KoG/GnomeG 家族风格一致；trait 模块内无 abbr 撞键。✅ 合理。
4. **GIANT/GoG/OoG 跨模块一致性**：feat `abbr_candidates` 登记值 GIANT/OoG/GoG 与 trait 修复值一致；测试 `test_reuses_feat_d1_abbr` / `test_no_abbr_collision_with_feat` 硬断言。✅
5. **撞键收窄评估**：`test_no_abbr_collision_with_feat` 收窄至本批 5 值是合理的——全表撞键会命中存量 KN（AA），导致永红；跨模块撞键已有 KN 登记。trait 模块内部经全表扫描确认当前 0 撞键，**已补同模块无撞键守卫测试**（见下）。
6. **补测（QA 新增，风格对齐既有）**：`test_trait_book_abbreviation.py` 新增 `TestTraitModuleNoCollision` 2 用例——
   - `test_abbr_maps_to_single_en_within_trait`：trait_sources 全表 abbr 不得对应多个 en（同模块撞键守卫，防后续新增条目悄悄撞键）
   - `test_abbr_nonempty`：全表 abbr/cn/en 非空健康断言
   - 运行结果：15 passed（原 13 + 补 2）

## 缺陷清单

| 编号 | 严重级别 | 描述 | 复现/证据 |
|---|---|---|---|
| T1 | Minor | trait_sources 仍有 13 个条目 abbr 为中文（星辰之民→繁星子民、混种、狗头人、矮人、精灵、秽邪勇士等），本批未清理 | 全表扫描；当前产物 0 命中（这些书未出现在 1222 chunks），verify 检查 7 的全量中文兜底可在其入产物时显形。建议登记 KN 排期下一批 |
| — | — | coder 自报遗留 2 项（AA 跨模块撞键、均衡信念 en 误写 Champions of Balance）范围外，与方案一致，不重复计缺陷 | 抽查属实 |

无 Blocker/Major 缺陷。

## 结论与建议

**通过，建议验收。** 修复面收敛、零代码改动、四步链与 build check 全绿；负样例与人工核定均有可复核取证；中文兜底断言可防同类回退。验收方仅需留意 T1（映射表残留中文条目，已有兜底守卫，可下批清理）。

## 需求澄清项

无。
