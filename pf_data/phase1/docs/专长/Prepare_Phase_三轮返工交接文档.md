# 专长模块 Prepare Phase 三轮返工交接文档（T6）

> 撰写：k3（审计方），2026-07-31
> 执行：执行模型（整包交付）
> 返工依据：k3 对二次返工交付（commit `ee255ef`）的终审——T1~T5 全部复算通过；终审新发现 raw_example 失真非孤例，经全库普查证实为**系统性缺陷**
> 基线 commit：`ee255ef`（二次返工交付），branch `feat/feat-module`
> 审计脚本（本目录，只读，k3 已跑通）：`t63_census_audit.py` / `t63_phantom_forensics.py` / `t63_firstlast_check.py`

---

## 0. 当前状态一句话

二次返工 T1~T5 经 k3 独立复算**全部合格**（含复合标签 9 条独立重数一致、verify 8 阻断全过、总数 3624 不变）。但终审对 raw_example 做全库普查后发现**两类系统性缺陷**，Prepare Phase 不能关闭：

1. **幻影 raw_example 84 条**（占 450 个普查元素的 18.7%）：raw_example 不是自身源文件的逐字文本。其中 30 条的专长名**在自身源文件完全不存在**，取证证实来自同批相邻文件——**同批勘探跨文件串扰**。
2. **12 份编号文件报告整体错位**：`专长9/28/32/34/42/43/44/47/48/56/57/58.md` 的勘探报告（title_forms/estimated_count/first_entry/last_entry/count_basis）描述的**不是自身源文件的内容**，first/last_entry 共 23 处在自身文件查无。例：`专长42.md` 报告称 est=5、全是斯芬克斯/团队专长，而源文件实际是 10 个标题行的惧怖冒险专长（以血蒙眼/灵光爆发/归尘拳…）。

**责任划分**：T6.1/T6.2/T6.3b/T6.3c 是原始勘探既有缺陷 + 前两轮审计盲区（未做全量逐字检查），**非执行方过失**；T6.3a 的 12 份错位报告同理，系勘探阶段同批多文件上下文串扰，R1~T5 轮次未触及。

---

## 1. T6.1：page_203 title_forms[1] raw_example 逐字替换（k3 预置）

- 位置：`per_file_B07.jsonl` page_203 记录，title_forms 中 pattern 为 `**中文名** **English**（战斗专长）（带feat_type单行）` 的项。
- 改前：`L350: **业余剑客**** Amateur Swashbuckler**（战斗专长）**`（星号数被美化：实际 4/6 星被写成 2/2）
- 改后（源文件 L350 逐字，k3 已核对）：

```
L350: **业余剑客**** Amateur Swashbuckler****（战斗专长）******
```

## 2. T6.2：page_203 title_forms[3] raw_example 类别纠正 + 逐字替换（k3 预置）

- 位置：同记录，pattern 为 `**中文名** **English**（派头专长）/（团队专长）/（流派专长）（单标签feat_type）` 的项。
- 问题：raw_example 与 [1] 同一条（业余剑客（战斗专长））——**类别张冠李戴**，且同样非逐字。
- 改后（源文件 L659 逐字，k3 已核对，类别匹配的（派头专长）实例）：

```
L659: **旋舞花招**** Confounding Tumble Deed****（派头专长）******
```

## 3. T6.3：全库 raw_example 普查修复（分四层，k3 已取证定性）

k3 已完成全库普查与逐条取证，结论可直接执行。**不要再发明修复方法，按本节的层/表/清单逐条落实。**

### 3.0 普查基线（k3 实测，复算基准）

```
$ python3 pf_data/phase1/docs/专长/t63_census_audit.py     # 当前 exit=1
元素总数: 450
  exact       : 264     # 逐字
  whitespace  : 56      # 去全部空白后匹配（CR/断行/缩进差异，放行类）
  punct       : 5       # 全/半角括号逗号差异（放行类）
  lb_marker   : 12      # [LB] 或 " / " 换行标注（放行类）
  img_marker  : 9       # ![[图片]] 剥 URL（放行类）
  elided      : 19      # ... 省略号截断（放行类）
  annotation  : 1       # （跨行续）纯标注（放行类）
  phantom     : 84      # 以上皆非 → 必须修复，目标 0
```

`raw_example` 的硬要求：**逐字复制、禁止手写还原、禁止美化**；非逐字只允许上述 6 种**声明式放行形态**。取证明细见 `t63_phantom_verdicts.json`（84 条逐条 verdict + bad_segments + token 归属，k3 已生成，可直接当工作清单用）。

### 3.1 T6.3a：12 份编号文件报告整体重推导（报告级错位）

**这是最重的一层。** 下列 12 份报告描述的不是自身源文件内容（证据：first/last_entry 23 处自身查无，见 §3.5；幻影 raw_example 的专长名经全树检索归属相邻文件）：

| 文件 | 现行报告 first→last（est） | 幻影内容实际归属（k3 取证） |
|---|---|---|
| 专长9.md | 占星时机→天体指引（2） | 专长8.md / 专长/繁星子民PotS_专长.md |
| 专长28.md | 大话王→酒后真言（12） | 专长33.md / 专长/格拉里昂的平衡勇士_专长.md |
| 专长32.md | 剧毒咬撃（1） | 专长34.md |
| 专长34.md | 天堂升华（1） | 专长43.md / 专长/安多安ASoL_专长.md |
| 专长42.md | 羊首狮身之角→万变地形（5） | 专长44.md / 专长/沙之子民PotS_专长.md |
| 专长43.md | 巧夺缴械物（1） | 专长51.md / 专长/巨人猎手手册_专长.md |
| 专长44.md | 消力/滚过它→屠狗者，猎马人（4） | 专长48.md / 专长/格拉里昂的地精_专长.md |
| 专长47.md | 天堂升华（1） | 专长43.md / 专长/安多安ASoL_专长.md |
| 专长48.md | 弹跳锤→索恩站姿（3） | 专长31.md / 专长50.md / 专长/格拉里昂的矮人_专长.md |
| 专长56.md | 秘语→见习从者（5） | 专长57.md / 专长/CaC部属与伙伴_专长.md |
| 专长57.md | 塞卡利亚专注纹→水下侍从（10） | 专长58.md / 专长/海洋之血BotS_专长.md |
| 专长58.md | 法术书狂热读者→法术抗拒（4） | 专长56.md / 专长/秘术选集ArcaneAnthology_专长.md |

错位链旁证（源文件头部实测）：专长32.md 实际含矢志不移（专长31 报告所引）、专长34.md 实际含剧毒咬撃（专长32 所引）、专长43.md 实际含天堂升华（专长34/47 所引）、专长47.md 实际含残悔斩（专长37 所引）——串扰沿编号相邻文件成链。

**执行要求**（对这 12 个文件，逐个做）：

1. **只读自身源文件**重新通读（红线：禁止从相邻文件报告或上表"实际归属"列搬运任何内容）；
2. 重推导该记录的 `title_forms`（pattern/count/note/raw_example）、`estimated_count`、`count_basis`、`first_entry`、`last_entry`、`traps`、`field_labels_seen`、`feat_type_tags`、`format_cluster_hint`——全部以自身源文件实测为准；
3. 新 `raw_example` 必须逐字（过 §3.0 普查脚本）；
4. `estimated_count` 以实测为准，**允许与现行值不同**；12 文件全部重推导后更新总数（现行 3624 预期会变），交付文档附"每文件 est 旧值→新值 + 总数旧→新"对照表；
5. 改动落在对应 `per_file_BXX.jsonl`（按 `prepare_batches.json` 的 batch 归属定位），完成后重跑 `merge_batches.py` 重建 `专长_per_file.jsonl`。

### 3.2 T6.3b：3 份报告 raw_example 幻影替换（计数已验证，只换实例）

专长31/35/37 的 estimated_count=3/3/3 已经 R3 独立重数验证，**计数不动**；仅其 title_forms[0].raw_example 是幻影（专长名在自身文件不存在，来自相邻文件）：

| 文件 | 幻影内容（归属） | 修复 |
|---|---|---|
| 专长31.md | 矢志不移（Sheltering Stubborness）→ 专长32.md | 从自身文件 3 条（弹跳锤/滑行斧投掷/索恩站姿所在区间）选真实标题行逐字替换 |
| 专长35.md | 晋升狗头人（Redeemed Kobold）→ 专长46.md | 从自身文件（孤狼独舞…阴招大师区间）选真实标题行逐字替换 |
| 专长37.md | 残悔斩（Lingering Smite）→ 专长47.md | 从自身文件（魔宠连接…战团之触区间）选真实标题行逐字替换 |

只改 `title_forms[].raw_example` 一个字段；保留 `L\d+:` 行号前缀且行号必须真实。

### 3.3 T6.3c：51 条 in_own_file 格式失真逐字重捕 + 1 处 last_entry 变体

专长名**在**自身源文件、但 raw_example 非逐字（错行引用、截断改写、丢括号英文、擅自改字、格式重写等）。逐条处理：

- **清单**：`t63_phantom_verdicts.json` 中 `verdict=="in_own_file"` 的 49 条 + 以下 2 条 k3 人工改判（原判 invented，实测源文存在、系漏抄/改字）：
  - `专长51.md` tf[5] `描述：你可以将溅射武器高高抛向空中` → 源文 L49-50 为 `描述：你可以将溅射武器（splash \nweapon）高高抛向空中`，记录漏抄 `（splash weapon）`；
  - `专长52.md` tf[1] `***你对幻术的天分` → 源文 L10 为 `***你对幻术的天赋...`，`天分` 系 `天赋` 改字。
- 其中 page_203 的 tf[1]/tf[3] 两条**已由 T6.1/T6.2 覆盖**，本层实际待修 **49 条**。
- 修复规则：以 raw_example 标注行号为线索在**自身源文件**定位真实标题行，整行（或跨行标题的多行）逐字复制，保留真实 `L\d+:` 前缀；禁止缩写/补全/改字/调格式。
- 另修 1 处 last_entry 格式变体：`专长/格拉里昂的地精_专长.md` 记录 `last_entry: 屠狗者/猎马人` → 源文 L34 为 `屠狗者，猎马人`（`/` 系 `，` 误写）。
- **注意**：源文件自带的 OCR typo（如 page_538 `Durnken Brawler`、page_673 `DlVlNE`）**照抄源文**，不要"帮忙改对"——raw_example 的职责是取样，不是校对。

### 3.4 T6.3d：3 条标注规范化

以下 3 条是勘探方的描述性标注、非源文引用，统一改为 `（注：…）` 形态（普查脚本对 `（注：…）`/`（跨行续）` 类纯标注自动放行）：

| 文件 | 现状 | 改后 |
|---|---|---|
| 专长/page_1367.md tf[0] | `L9-93 表格84行：` | `L9-93 （注：表格84行）` |
| 造物专长一览.md tf[0] | `顶部索引列表，如：` | `（注：顶部索引列表）` |
| 专长/page_673.md tf[3] | `**特殊情况**：...` | `（注：字段标签“特殊情况”省略示例）` |

### 3.5 证据与复算入口（k3 已跑通，执行方照跑）

```bash
cd /Users/chezi/code/java/pf_agent

# ① 普查（§3.0，当前 phantom=84，修复后必须 0，exit 0）
python3 pf_data/phase1/docs/专长/t63_census_audit.py

# ② 逐条取证（当前 in_own_file 49 + cross_file 30 + invented 5；
#    修复后三类全 0；invented 含 §3.3 两条人工改判与 §3.4 三条标注，修复后同步消失）
python3 pf_data/phase1/docs/专长/t63_phantom_forensics.py

# ③ first/last_entry 自包含（当前查无 24 处=23 错位+1 变体，修复后 0，exit 0）
python3 pf_data/phase1/docs/专长/t63_firstlast_check.py

# ④ 既有闸口回归
python3 pf_data/phase1/vectorizer/exploration/专长/verify_prepare.py   # exit 0
python3 -c "
import json
print(sum(json.loads(l).get('estimated_count',0) for l in open('pf_data/phase1/vectorizer/exploration/专长/专长_per_file.jsonl', encoding='utf-8')))"
# ⑤ 总数：T6.3a 后允许 ≠3624，交付文档必须给逐文件对照与理由
```

---

## 4. 红线（护栏）

1. T6.1/T6.2 照单替换（k3 预置的逐字原文已核对，禁止再"还原"）。
2. T6.3a 重推导**只读自身源文件**；禁止从相邻文件报告、禁止从本文档"实际归属"列搬运内容（该列仅作错位证据，不是修复素材）。
3. T6.3b/c/d 只动 `raw_example` 一个字段（另加地精文件 `last_entry` 一处）；pattern/count/note/traps 等不动。
4. **已验证计数不得再动**：ISR 50、page_1564 272、page_203 129、page_321 86、专长31/35/37 各 3（R1/R3 独立重数结论）。T6.3a 的 12 文件不在此列，以重推导实测为准。
5. 源数据根 `pf_rules_md_organized/` 只读红线不变；审计脚本（docs/专长/t63_*.py）只读，发现脚本缺陷报告 k3，不自行改脚本凑通过。
6. 修复中新发现的**字段外**问题记到交付文档"附带发现"节，不擅自扩范围。
7. 单 commit 提交，message 建议：`fix(prepare): k3终审 T6 — raw_example 幻影84条清零 + 12份错位报告重推导`。

---

## 5. 验收口径与复跑入口

### 5.1 交付要求

三轮交付说明（可极短但要素全）：

1. T6.1/T6.2 改前改后对照；
2. T6.3a 12 文件：每文件 est 旧值→新值 + first/last_entry 新值 + 总数 3624→新值对照表；
3. T6.3b/c/d 逐条修复清单（可引用 `t63_phantom_verdicts.json` 的条目编号方式：文件+tf_index）；
4. §3.5 五条复算命令的**完整输出全文**（截取 ✅ 不计）。

### 5.2 k3 终审范围

- §3.5 全部命令重跑：census phantom=0、forensics 三类全 0、first/last 查无 0、verify exit 0、总数与交付对照表一致；
- T6.3a 12 份新报告**逐份抽查**：first/last 自身存在 + 至少 2 条 raw_example 逐字抽对 + count_basis 与源文件抽数一致；
- T6.3b/c 修复条目按 20% 抽样逐字复核；
- 通过后 **Prepare Phase 正式关闭**，进 k3 汇总阶段（format_clusters / source_spec / test_seeds）。

---

## 6. 附带发现（本轮不修，k3 汇总阶段消化）

1. **file 字段口径不一**：189 份报告中 29 份 `file` 带 `pf_rules_md_organized/` 前缀、160 份不带（k3 审计脚本已兼容两种）。k3 汇总阶段统一，不在本轮修。
2. **同书多份并存**：`专长N.md` 编号系列与 `专长/<书名>_专长.md`、`未整理/` 目录存在同书内容多份（幻影归属总成双出现的根源）。dedup 阶段注意这不是重复错误而是版本并存，需人工定主版本。
3. **放行类形态占比 23%**（105/450）：whitespace/punct/lb_marker/img_marker/elided 五类非逐字放行形态依赖**声明式标注**才被识别，k3 汇总阶段在 format_clusters 规范里写明这 6 种合法标注形态（含 annotation），其余一律视为缺陷。

---

## 7. 流程沉淀

1. **审计命令覆盖范围 = 声明范围**：复算输出必须贴**全文**，截取的 ✅ 不计（二轮教训）。
2. **同类问题一次普查到底**：发现"美化星号"类缺陷当场扩到全库普查（本轮 T6.3 即由此挖出报告级错位）。
3. **同批多文件勘探必须过 first/last 自包含闸口**：跨文件串扰在上下文窗口内无声发生，`first_entry`/`last_entry` 在自身源文件查无是其确定性信号；`t63_firstlast_check.py` 固化为后续所有模块 Prepare Phase 的强制闸口。
4. **普查脚本与取证数据随交接文档走**：`t63_census_audit.py` / `t63_phantom_forensics.py` / `t63_firstlast_check.py` / `t63_phantom_verdicts.json` 与本文件同目录，执行方零配置照跑，k3 终审原样复跑。
