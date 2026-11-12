# 测试报告 — KN233 spell_lists 拼接修复与法术别名补录

- 日期：2026-09-21
- 被测：工作区未 commit 改动（分支 dev/pf_agent，基线 HEAD = 1ba2a35）
- 改动文件：`spell_list_export.py`（GLUED_NAME_SPLITS）、`vectorizer/postprocess/spell_chain.py`（SupplementSpellAliases）、`vectorizer/processors/spell.py`（POSTPROCESSORS 登记）、`vectorizer/tests/test_kn233_spell_list_alias.py`（新增 5 用例）、`docs/已知问题记录.md`（KN233 登记节）
- 依据文档：`pf_data/phase1/docs/已知问题记录.md` KN233 节

## 测试设计

- 黑盒（3 项）：spell 四步验证链、`build check`、全量 pytest。
- 白盒（6 项）：①产物全量对账（HEAD 版导出脚本基线 vs 当前 spell_lists.json）；②拆分命中唯一性；③6 条 curated alias 落地与只增不减；④finalize 级幂等（重跑两次）；⑤KN011 link 顺序与不受影响面；⑥审批单 4 条与源文件行号只读核对。
- 未覆盖：spell 向量库重灌效果（DVG 清偿事项，不在本次范围）；审批单源回写（待用户审批，未实施）。

## 黑盒结果

| 用例 | 预期 | 实际 | 结论 |
|---|---|---|---|
| verify --category spell | 四步链全绿 | 全绿（数据不变量通过；既有 WARN：book '?' 余量 0） | 通过 |
| build check | exit 0，9 artifact 指纹一致 | exit 0 ✅ | 通过 |
| pytest vectorizer/tests -q | 全过 | 1480 passed, 2 warnings（8.36s） | 通过 |

## 白盒结果

**① 产物全量对账（自造基线）**：spell_lists.json 不在 git 跟踪内，故用 HEAD 版 `spell_list_export.py`（补丁 OUT_DIR 指向 /tmp）重跑作基线。逐条目比对结论：

- 总条数 10068 → 10069（与 KN233 登记一致）；
- 差异**仅有** 3 条，全部在 `classes/血脉狂怒者/levels/4`：−「精神错乱月狂病（moonstruck）」、+「精神错乱（moonstruck）」、+「月狂病（moonstruck）」。其余全部职业/环级条目（含 chunk_id）逐键一致，**无任何误伤**；
- null 数 65 → 65，null 率 0.006 不变；其他职业环级条目数零变化；
- 拆分两条分别落在 index 24/25，均命中 `spell_Spell APG_0159`（cross_score 6/5，与登记一致）；4 环 75→76。

**② 拆分命中唯一性**：`精神错乱月狂病` 字面仅存在于血脉狂怒者 page_100 的 organized/未整理两份拷贝；CLASS_LISTS 仅引用其一，拆分表仅此 1 对 key，且 key 带小写 en 精确匹配，误伤面为零。源文件 page_100.md:38 字面黏连已复核属实（考据成立）。

**③ alias 落地**：6 个 chunk_id（APG_0245/0159、page_1168_0013/1365_0368、OA_0018、ISWG_0011）在产物 chunks.jsonl 中全部存在且各含目标别名**恰好 1 次**；curated 表 chunk_id 拼写与产物一致。逐 chunk 比对除 aliases 外字段零差异（只增不减成立）。

**④ 幂等**：对 chunks.jsonl 副本连续两次执行 `SupplementSpellAliases.run`：run1 added=0/already=6（产物已过一遍），run2 added=0/already=6，无重复追加；全量 4172 行重跑后无 alias 重复。

**⑤ KN011 顺序**：`POSTPROCESSORS = [LinkMythicBaseSpells, SupplementSpellAliases]`，登记注释与 KN233 登记节一致。verify/build check 全绿，link 产物未受影响（补充别名均非 mythic 基础法术别名，不进 link 索引属预期）。

**⑥ 审批单核对（只读）**：抽查 13 处源文件行号/内容，全部与 KN233 登记节一致——召唤师 page_248:39（幻灵重塑术）、Spell APG.md:11956（条目标题=向导重塑术）、异能者 page_309:245 / 奥能师 page_65:41 / 女巫 page_93:40 / page_92:624（均月狂病）、萨满 page_114:65（连接遗赠）、玩家伴侣 page_1168:187 / page_1365:8882（条目=链接学识）、唤魂师 page_1037:66（乙太凝聚场）/ Spell OA.md:175（以太凝聚场，条目侧正确）、Spell ISWG.md:643（戏言句「叫不屈之心如何」）、召唤师 page_274:34-35（职业特性用幻灵重塑术）。源数据确认未被改动（git status 无 pf_rules_md* 变更）。

**语义评估**（两条不同名列表项指向同一 chunk）：全库被多条列表项引用的 chunk 有 1496/1844 个（跨职业/跨环级常态），同页两名并列指向同一法术 chunk 与既有交叉语义一致；且成因系源页字面黏连两名异译，拆分忠实于源。判定为预期口径，非缺陷。

**单测审计**：新增 5 用例均为真实断言（拆分两条独立性与 book/en 继承、未黏连条目透传、key 规范性、alias 追加与统计、二次幂等），无假测试。

## 缺陷清单

| 编号 | 级别 | 描述 | 复现 |
|---|---|---|---|
| — | — | 未发现 Blocker/Major | — |

Minor：

1. KN233 登记节写「`法术/Spell ISWG.md:643`」，实际文件在 `pf_rules_md_organized/Spell ISWG.md`（顶层，不在法术/ 子目录）。行号与内容正确，仅路径表述不精确。
2. （非本次改动引入，仅观察）verify 输出既有 WARN：book '?' 余量 0.0%，登记节已有参数审议待办提醒，与 KN233 无关。

## 结论与建议

**通过**。黑盒三项全绿；白盒六项核查全部与交付口径一致：拆分外科手术式精确（全量对账仅 ±3 条、null 率不变）、6 条 alias 落地且幂等、KN011 不受影响、审批单 13 处考据属实、登记节与实际改动一致。建议验收方放行；遗留事项按 KN233 登记节执行：①审批单 4 条待用户拍板后回写源 md；②spell 向量库重灌走 DVG 清偿（chunks aliases 已变更，重灌前线上召回对 5 个异译名仍漏属已知未清偿项）。

## 需求澄清项

1. 审批单第 1 条：召唤师 page_274:34-35、page_247:805、page_410:397/673 等多处职业特性正文也用「幻灵重塑术」，回写范围（仅列表页 vs 含正文）待用户裁量（登记节已列，重申）。
2. 拆分后血脉狂怒者 4 环出现「精神错乱」「月狂病」两条同 en 同 chunk 条目，虽与既有交叉语义一致，若产品侧希望列表导出对同 chunk 去重，需另立需求（当前按 KN233 口径保留两条）。
