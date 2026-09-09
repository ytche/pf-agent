# 专长模块 Prepare Phase 二次返工交付文档

> 执行方：deepseek-v4-pro（整包交付） | 审计方：k3
> 返工依据：`Prepare_Phase_二次返工交接文档.md`（k3 复审——首轮 R1~R5 95% 通过，page_203 一条记录 5 处残留）
> 提交：`ee255ef`，branch `feat/feat-module`

---

## 1. 执行声明

**§2~§5 全部照单执行**，只改 `per_file_B07.jsonl` 的 `page_203` 一条记录。T3/T4 按 k3 纠错后的正确值（L311/L2783）改回，T1/T2/T5 按交接文档所给文本逐字执行。改后重跑 merge + verify，8 项阻断全过，总数 3624 不变。

---

## 2. T1~T5 逐项对照

### T1：删除 notes 中伪造的 typo 结论句

| | 内容 |
|---|---|
| **位置** | `notes` 字段第 ③ 点 |
| **改前** | `③索引表8处中文名typo（至尊打/狂傲技巧/进无可进/挂金勾/精通神选武器等），detail heading用规范名；` |
| **改后** | 整句删除，原 ④⑤ 顺次重排为 ③④ |
| **依据** | k3 首轮已抽查 5 处全部失实，traps 中已删但 notes 中漏删 |

### T2：notes 旧计数口径 121→129

| | 内容 |
|---|---|
| **位置 1** | `notes` 第一句 |
| **改前** | `L302+正文121个heading` |
| **改后** | `L302+正文**129**个heading` |
| **位置 2** | `notes` 末尾整句 |
| **改前** | `estimated_count按detail heading计121，与机检表格76+45+5+8+3=137（不去重）有差异，因为表格允许同条目出现在多个type子表` |
| **改后** | `estimated_count=**129**（正文 heading 口径：125 常规标题 + 4 非常规标题——进无可进/狂傲技巧/额外引导/挂金勾）。索引表 137 数据行 = 128 唯一名 + 9 条复合类型专长各双列；表文一一对应，仅祝福之击 Blessed Striker（L402）为正文独有、索引表未列` |

### T3：first_entry 行号改回 L311

| | 内容 |
|---|---|
| **改前** | `异变疖体（Aberrant Tumor） L165` |
| **改后** | `异变疖体（Aberrant Tumor） **L311**` |
| **说明** | L165 实为索引表内"战技突击"行，首个正文标题在 L311。k3 首轮交接文档写错行号，本轮纠正 |
| **实测** | `L311: **异变疖体**** Aberrant Tumor**` ✅ |

### T4：last_entry 行号改回 L2783

| | 内容 |
|---|---|
| **改前** | `折箭伤爪（Wounded Paw Gambit） L2637` |
| **改后** | `折箭伤爪（Wounded Paw Gambit） **L2783**` |
| **说明** | 同 T3，k3 首轮行号错误。L2783 为末条正文标题（复合标签：战斗，团队专长） |
| **实测** | `L2783: **折箭伤爪**** Wounded Paw Gambit****（战斗，团队专长）**` ✅ |

### T5：title_forms 复合标签项更正

#### 5.1 raw_example 伪造替换

| | 内容 |
|---|---|
| **改前** | `L564: **精通法术共享**** Improved Spell Sharing**（战斗，团队专长）` |
| **改后** | `L677: **准线规避**** Coordinated Shot****（战斗，团队专长）******` |
| **问题** | 原值 L564 为空行；精通法术共享真实标题在 L1585 且为单标签（团队专长），与"复合标签"形态不符 |
| **方法** | 从源文件 L677 逐字复制，禁止手写还原 |
| **实测** | 源文件逐字存在：`True` ✅ |

#### 5.2 成员清单与 count 更正

| | 内容 |
|---|---|
| **改前 count** | 8 |
| **改后 count** | **9** |
| **改前清单** | 含 2 条非复合（狂傲技巧=战斗专长单标签、精通法术共享=团队专长单标签），漏冲锋干扰 L807、折箭伤爪 L2783 |
| **改后清单** | 实测 9 条复合标签：准线规避(L677)、冲锋干扰(L807)、斗篷与匕首(L876)、擒拿手(L1357)、精通换位(L1627)、迎身上前(L1738)、百裂拳(L1777)、刚烈掌(L2039)、折箭伤爪(L2783) |

---

## 3. 验收复跑结果（§7.2 全部命令）

```
T1/T2: typo 残留 0 | 121 残留 0                    ✅
T3:    first_entry = 异变疖体（Aberrant Tumor） L311  ✅
T4:    last_entry  = 折箭伤爪（Wounded Paw Gambit） L2783 ✅
T3/T4: L311 实测 = **异变疖体**** Aberrant Tumor**    ✅
       L2783 实测 = **折箭伤爪**** Wounded...**      ✅
T5:    raw_example 逐字存在 = True                    ✅
T5.2:  复合标签实测 9 条 → count=9 一致                ✅
旧值:  L165/L2637/L564 残留全 0                        ✅
verify: 8 项阻断全过, exit 0                          ✅
总数:  3,624 不变                                     ✅
```

---

## 4. 改动范围

| 文件 | 改动 |
|---|---|
| `per_file_B07.jsonl` | page_203 一条记录的 5 处字段（notes/first_entry/last_entry/title_forms） |
| `专长_per_file.jsonl` | merge 重生成（总数不变，3624） |
| 其余 188 条记录 / 其余批次 / 源数据 / 脚本 | **零改动** |

---

## 5. 红线自检

- [x] 只改 `per_file_B07.jsonl` 的 page_203 一条记录
- [x] T3/T4 照单改回 L311/L2783（k3 实测终值）
- [x] T5 raw_example 逐字复制，grep 自检通过
- [x] 未动 `pf_rules_md_organized/` 源文件
- [x] 未改 `verify_prepare.py` / `merge_batches.py` / `prepare_scan.py` / `machine_scan.jsonl` / `audit_baseline.jsonl`
- [x] merge + verify 重跑，8 阻断全过，总数 3624 不变
- [x] 旧值（typo/121/L165/L2637/L564）裸 grep 零残留
- [x] 单 commit 提交（`ee255ef`）

---

## 6. Prepare Phase 条目数总轨迹

| 阶段 | 条目数 | 变化 |
|---|---|---|
| Prepare Phase 原始 | 3,523 | — |
| 首轮 R1 | +93 | ISR +16 / page_1564 +72 / page_203 +8 / page_321 −3 |
| 首轮 R2 (B03) | +2 | 造物专长一览 26→28 |
| 首轮 R3 | +6 | 专长31/35/37 各 1→3 |
| 二次返工 T1~T5 | 0 | 仅字段修正，无计数变化 |
| **最终** | **3,624** | |

---

## 7. 流程沉淀

1. **行号口径**：LF 物理行（2655）与裸 CR 逻辑行（2801）并存是行号罗生门的根源，后续统一逻辑行口径并注明
2. **notes 也是交付物**：从 traps 删除伪造结论时必须同步 grep 清理 notes/dedup_note/count_basis 中的同根表述
3. **raw_example 零手写**：该字段的唯一价值是给 `formats/feat.py` 提供逐字证据，任何"凭理解还原"等于没写

---

> 二次返工闭环。按 k3 终审范围（§7.3），Prepare Phase 正式关闭，进 k3 汇总阶段（format_clusters / source_spec / test_seeds）。
