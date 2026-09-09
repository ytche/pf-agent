# 专长模块 Prepare Phase 三轮返工终审结论

> 撰写：k3（审计方），2026-07-31
> 审计对象：三轮返工交付（commit `5bdba32`，交付文档 `Prepare_Phase_三轮返工交付文档.md`）
> 判定依据：`Prepare_Phase_三轮返工交接文档.md` §5 验收口径，全部由 k3 独立重跑复算，未采信交付自述

---

## 〇、判定

**三轮返工交付通过，Prepare Phase 正式关闭。**

最终状态基线：commit `5bdba32`（branch `feat/feat-module`）——189 份勘探记录，estimated_count 合计 **3635**，verify 8 项阻断全过。

---

## 一、验收命令复算（k3 独立重跑，全部通过）

| # | 命令 | 交付声明 | k3 复算 |
|---|---|---|---|
| ① | `t63_census_audit.py` | phantom=0，exit 0 | ✅ 436 元素，phantom=0，exit 0 |
| ② | `t63_phantom_forensics.py` | 三类全 0 | ✅ phantom 元素 0 条 |
| ③ | `t63_firstlast_check.py` | 查无 0，exit 0 | ✅ 375 处检查，查无 0，exit 0 |
| ④ | `verify_prepare.py` | 8 阻断全过，exit 0 | ✅ exit 0，17/17 批、189/189 记录、条目 3635（偏差>20% 132 文件为既有基线） |
| ⑤ | estimated_count 合计 | 3635（3624−49+60） | ✅ 3635，与交付对照表算术一致 |

## 二、git 范围与红线复核

- 改动仅落在：13 个 `per_file_B*.jsonl` + `专长_per_file.jsonl`（merge 重建）+ `prepare_verify_report.md` + 交接/交付文档 + k3 审计脚本（t63_*）。源数据、`prepare_batches.json`、`machine_scan.jsonl`、`audit_baseline.jsonl`、`verify_prepare.py`、`merge_batches.py` **零改动**；工作区 clean，单 commit。
- 红线计数全部不动：内海种族ISR 50、page_1564 272、page_203 129、page_321 86、专长31/35/37 各 3（R1/R3 独立重数结论）。

## 三、抽样复核（命令层之外 k3 加做）

- **T6.1/T6.2**：page_203 tf[1]/tf[3] 与 k3 预置逐字串逐字符一致。
- **T6.3b**（专长31/35/37）：3 条替换全部逐字且行号真实（31 L4-5 弹跳锤、35 L1-2 孤狼独舞、37 L8-9 魔宠连接）。
- **T6.3a**（12 份错位重推导）：count_basis 中 **42 个行号引用全部锚定真实源行**；重点抽查——专长28 十二名十二行全对、专长48 L1/14/22/29 全对、专长9 表格段 8 条（L4-L21 无 ** 标题、机检盲区）+ 尾部 3 条 = 11；12 文件 est 算术 49→60 与总数 3624→3635 一致。
- **T6.3c/d** 抽样 13 条：k3 粗检 4 条"不符"经 census verbose 复核全部落在合法放行类（elided×3、whitespace×2，全角空格/省略截断），非缺陷。

## 四、核查过的疑点（判定不阻断）

专长28 title_forms count 和 11 < est 12：est=12 由 12 个行号引用证实；第 12 条（酒后真言）图片 URL 为 `aonprd.com/...SymbolN.gif` 变体未入模式分类。全库口径扫描显示 tf count和≠est 是 schema 常态（21 份 <、39 份 >，R3 已验收的专长31/35/37 亦为 1<3）——title_forms 是模式分类而非划分，不构成缺陷。

## 五、遗留事项（进 k3 汇总阶段消化，非缺陷）

1. **file 字段口径不一**：29/189 份带 `pf_rules_md_organized/` 前缀（t63 脚本已兼容两种），汇总阶段统一。
2. **同书多份并存**：`专长N.md` 编号系列与 `专长/<书名>_专长.md`、`未整理/` 存在同书内容多份（跨文件串扰幻影总成双出现的根源）；dedup 阶段需人工定主版本，非重复错误。
3. **放行类形态规范化**：whitespace/punct/lb_marker/img_marker/elided/annotation 六种合法非逐字形态（105+/436 ≈ 24%）须写入 format_clusters 规范，其余一律视为缺陷。
4. **偏差 >20% 文件 132 个**：既有基线（机检 vs estimated_count 口径差异），随汇总阶段对账复核处理。

## 六、审计链闭环记录

| 轮次 | 交接 → 交付 | k3 判定 | 关键结论 |
|---|---|---|---|
| 首轮 | `Prepare_Phase_交接文档.md` → 执行交付 | 有条件通过 | R1~R5 返工包（ISR 计数、page_203 行号口径、专长31/35/37、MD5 普查等） |
| 二轮 | `Prepare_Phase_返工交接文档.md` → `Prepare_Phase_返工交付文档.md`（`871856e`） | 基本通过 | R1/R3/R4 全过；遗留 page_203 一记录 5 处（T1~T5） |
| 三次 | `Prepare_Phase_二次返工交接文档.md` → `Prepare_Phase_二次返工交付文档.md`（`ee255ef`） | 通过（含新发现） | T1~T5 全过；终审新发现 raw_example 失真非孤例 → 全库普查（T6） |
| 三轮 | `Prepare_Phase_三轮返工交接文档.md` → `Prepare_Phase_三轮返工交付文档.md`（`5bdba32`） | **通过，Prepare Phase 关闭** | T6 四层：幻影 84 清零 + 12 份错位报告重推导 + 标注规范化 |

流程沉淀（已固化资产，后续模块直接复用）：

- `t63_census_audit.py`：raw_example 逐字普查（6 种合法放行形态分类，phantom 必须为零）；
- `t63_firstlast_check.py`：first/last_entry 自包含闸口——同批多文件勘探跨文件串扰的确定性信号；
- `t63_phantom_forensics.py`：幻影逐条取证（in_own_file / cross_file / invented 三分类）。

## 七、下一步

进入 **k3 汇总阶段**：format_clusters / source_spec / test_seeds → **人工确认门** → 元数据 schema 设计（架构决策 29）。汇总阶段注意事项即本文档 §五遗留事项。
