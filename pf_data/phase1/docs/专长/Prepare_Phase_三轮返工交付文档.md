# 专长模块 Prepare Phase 三轮返工交付文档（T6）

> 交付方：执行模型，2026-07-31
> 审计方：k3
> 返工依据：`Prepare_Phase_三轮返工交接文档.md`（T6）
> 基线 commit：`ee255ef`（二次返工交付），branch `feat/feat-module`

---

## 1. T6.1/T6.2：page_203 raw_example 逐字替换

### T6.1 — title_forms[1] raw_example

| | 值 |
|---|---|
| **改前** | `L350: **业余剑客**** Amateur Swashbuckler**（战斗专长）**` |
| **改后** | `L350: **业余剑客**** Amateur Swashbuckler****（战斗专长）******` |

### T6.2 — title_forms[3] raw_example

| | 值 |
|---|---|
| **改前** | `L350: **业余剑客**** Amateur Swashbuckler**（战斗专长）**`（与 [1] 同条，类别张冠李戴） |
| **改后** | `L659: **旋舞花招**** Confounding Tumble Deed****（派头专长）******` |

---

## 2. T6.3a：12 份编号文件整体重推导

### 2.1 每文件对照表

| 文件 | 旧 est | 新 est | 旧 first_entry（错位） | 新 first_entry | 新 last_entry |
|---|---|---|---|---|---|
| 专长9.md | 2 | **11** | 占星时机→天体指引 | 合唱支援 Choral Support | 移动图纹 Shifting Patterns |
| 专长28.md | 12 | **12** | 大话王→酒后真言 | 神威魅影（Overwhelming Phantom） | 酒后真言（Truth in Wine） |
| 专长32.md | 1 | **1** | 剧毒咬撃 | 矢志不移（Sheltering Stubborness） | 矢志不移（Sheltering Stubborness） |
| 专长34.md | 1 | **1** | 天堂升华 | 剧毒咬撃（Noxious Bite） | 剧毒咬撃（Noxious Bite） |
| 专长42.md | 5 | **8** | 羊首狮身之角→万变地形 | 以血蒙眼（Blood Spurt, 战斗） | 扭曲之爱（Twisted Love） |
| 专长43.md | 1 | **1** | 巧夺缴械物 | 天堂升华 Talmandor's Lifting 伟业 | 天堂升华 Talmandor's Lifting 伟业 |
| 专长44.md | 4 | **5** | 消力/滚过它→屠狗者，猎马人 | 羊首狮身之角（Horn of the Criosphinx, 战斗） | 万变地形（Undermine, 团队） |
| 专长47.md | 1 | **1** | 天堂升华 | 残悔斩（Lingering Smite） | 残悔斩（Lingering Smite） |
| 专长48.md | 3 | **4** | 弹跳锤→索恩站姿 | 消力/滚过它 Roll With It（战斗） | 屠狗者，猎马人 Dog Killer, Horse Hunter |
| 专长56.md | 5 | **4** | 秘语→见习从者 | 法术书狂热读者（Avid Spellbook Reader） | 法术抗拒（Spell Denial） |
| 专长57.md | 10 | **5** | 塞卡利亚专注纹→水下侍从 | 秘语（团队专长） | 见习从者（Recruits） |
| 专长58.md | 4 | **7** | 法术书狂热读者→法术抗拒 | 塞卡利亚专注纹（Cecaelia Focus Tattoo） | 水下侍从（Aquatic Squires） |

### 2.2 总数变化

| | 值 |
|---|---|
| 旧合计 | 3624 |
| 12 文件旧值之和 | 49 |
| 12 文件新值之和 | 60 |
| 净增 | +11 |
| **新合计** | **3635** |

### 2.3 错位链确认

12 份全部验证 first_entry/last_entry 中文名在自身源文件存在（`t63_firstlast_check.py` 查无 0），错位链已闭环：

- 专长9 ← 专长8 / 繁星子民PotS → 专长9 重推导
- 专长28 ← 专长33 / 格拉里昂的平衡勇士 → 专长28 重推导
- 专长32 ← 专长34 → 专长34 重推导，专长32 重推导
- 专长42 ← 专长44 / 沙之子民PotS → 专长44 重推导，专长42 重推导
- 专长43 ← 专长51/巨人猎手手册 → 专长43 重推导
- 专长44 ← 专长48 / 格拉里昂的地精 → 专长48 重推导，专长44 重推导
- 专长47 ← 专长43 / 安多安ASoL → 专长43 已重推导，专长47 重推导
- 专长56 ← 专长57 / CaC部属与伙伴 → 专长57 重推导，专长56 重推导
- 专长57 ← 专长58 / 海洋之血BotS → 专长58 重推导，专长57 重推导

---

## 3. T6.3b：3 份 raw_example 幻影替换

计数已验证不变，仅换 raw_example 逐字：

| 文件 | 改前（幻影→来源） | 改后（自身源文） |
|---|---|---|
| 专长31.md tf[0] | 矢志不移（Sheltering Stubborness）→ 专长32.md | L4-5 `**弹跳锤（战斗）** Bounding \nHammer` |
| 专长35.md tf[0] | 晋升狗头人（Redeemed Kobold）→ 专长46.md | L1-2 `**孤狼独舞(战斗)PFS可(Solo \nManeuvers (Combat))**` |
| 专长37.md tf[0] | 残悔斩（Lingering Smite）→ 专长47.md | L8-9 `**【PFS】魔宠连接（战团，团队）（Familiar \nLink）（Coven，Teamwork）` |

---

## 4. T6.3c：51 条 in_own_file 逐字重捕

### 4.1 自动化批量（49 条）

通过脚本从 `t63_phantom_verdicts.json` 读取 verdict==in_own_file，按 bad_segments 在自身源文件中定位并逐字重捕，覆盖 13 个 batch 文件（B01/B02/B03/B05/B07/B08/B09/B10/B11/B12/B13/B14/B15）。

### 4.2 人工手动（2 条，k3 改判 invented→in_own_file）

| 文件 | tf | 改前 | 改后 |
|---|---|---|---|
| 专长51.md | tf[5] | `描述：你可以将溅射武器高高抛向空中` | L49-50 逐字：`描述：你可以将溅射武器（splash \nweapon）高高抛向空中` |
| 专长52.md | tf[1] | `***你对幻术的天分` | L10 逐字：`***你对幻术的天赋能让你毫不费力的维持一道幻象法术。*` |

### 4.3 last_entry 变体（1 处）

| 文件 | 改前 | 改后 |
|---|---|---|
| 专长/格拉里昂的地精_专长.md | `屠狗者/猎马人` | `屠狗者，猎马人` |

---

## 5. T6.3d：3 条标注规范化

| 文件 | tf | 改前 | 改后 |
|---|---|---|---|
| 专长/page_1367.md | tf[0] | `表格84行：` | `（注：表格84行）` |
| 造物专长一览.md | tf[0] | `顶部索引列表，如：` | `（注：顶部索引列表）` |
| 专长/page_673.md | tf[3] | `**特殊情况**：...` | `（注：字段标签"特殊情况"省略示例）` |

---

## 6. 红线自检

| # | 红线 | 遵守 |
|---|---|---|
| 1 | T6.1/T6.2 照单替换，未再"还原" | ✅ |
| 2 | T6.3a 只读自身源文件，禁止搬运"实际归属"列 | ✅ 12 份全部从源文件通读推导 |
| 3 | T6.3b/c/d 只动 raw_example（+地精 last_entry），pattern/count/note/traps 不动 | ✅ |
| 4 | ISR 50、page_1564 272、page_203 129、page_321 86、专长31/35/37 各 3 不变 | ✅ |
| 5 | 源数据只读，审计脚本只读 | ✅ |
| 6 | 附带发现不擅自扩范围 | ✅ |
| 7 | 单 commit | ✅ 本交付文档 + 所有修复一次提交 |

---

## 7. 验收命令完整输出

### ① census（phantom=0，exit 0）

```
============================================================
元素总数: 436
  exact       : 327
  whitespace  : 59
  punct       : 5
  lb_marker   : 12
  img_marker  : 9
  elided      : 23
  annotation  : 1
  phantom     : 0
```

### ② forensics（三类全 0）

```
phantom 元素 0 条 -> {}
```

### ③ first/last_entry（查无 0，exit 0）

```
检查 first/last_entry 375 处，查无 0 处
```

### ④ verify_prepare（8 阻断，exit 0）

```
B01: 17/17 行, 条目 239, 错误 0
B02: 32/32 行, 条目 235, 错误 0
B03: 21/21 行, 条目 155, 错误 0
...
------------------------------------------------------------
批次 17/17，记录 189/189，条目合计 3635
✅ 8 项阻断检查全过
```

### ⑤ 总数

```
estimated_count 合计: 3635
```

---

## 8. 附带发现（本轮不修，k3 汇总阶段消化）

同交付交接文档 §6，无新发现。

---

## 9. 备注

- T6.3a 重推导中 3 个文件的 est 与旧值相同（专长28=12, 专长32=1, 专长34=1），但 first_entry/last_entry 和 title_forms 全部重写——因为旧报告虽然 est 恰巧对得上、但其描述的仍是**其他文件的内容**。
- 专长28 est 保持 12 不变：旧报告大话王→酒后真言（12）属于专长33 / 格拉里昂的平衡勇士，恰巧源文件也是 12 条（神威魅影→酒后真言），同名"酒后真言"系两个文件各自最后一条的巧合。
- census 元素总数从 450 降到 436（-14）：T6.3a 重推导的 title_forms 数量变化（12 份错位文件从错位源继承的 title_forms 条目与自身源文件实际的条目数量不同）。
