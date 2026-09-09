# 专长模块 TDD 阶段交付文档（formats + processors + 产出即检）

> 交付方：执行模型，2026-08-01
> 审计方：k3（待审）
> 依据：`专长模块开工前_流程抽象与预防清单.md` §六 第 5/6 步（TDD → 产出即检三件套）
> 基线 commit：`1445bd0`（formats 交付），branch `feat/feat-module`
> 本次交付：`0ed27c0`（Processor TDD）→ `82d3d39`（源数据修复）→ `5429aad`（产出即检报告）→ `f33bda4`（别名边界登记）

---

## 1. 交付范围

| 步骤 | 内容 | 状态 |
|---|---|---|
| §六-5a | TDD 红：`test_feat_format.py`（26 seeds） | ✅ 1445bd0（上阶段交付） |
| §六-5b | TDD 红：`test_feat_processor.py`（44 tests） | ✅ 0ed27c0 |
| §六-5c | TDD 绿：`formats/feat.py` + `processors/feat.py` + 注册 | ✅ 0ed27c0 |
| §六-5d | pipeline 端到端（`--category feat`） | ✅ 2846 chunks |
| §六-6 | 产出即检三件套 + 召回 | ✅ 5429aad |

## 2. 代码交付物

| 文件 | 类型 | 内容 |
|---|---|---|
| `vectorizer/formats/feat.py` | 新增 415 行 | 六放行形态归一（standard/whitespace/punct/lb_marker/img_marker/elided/annotation）+ 条目切分 |
| `vectorizer/processors/feat.py` | 新增 348 行 | parse_fields 双格式 + prerequisites 结构化 + field_status 三态 + 来源书兜底链 |
| `vectorizer/registry_feat.py` | 新增 150 行 | 14 规范字段 + 别名聚合表 + feat_type 白名单/归一化（独立于 spell registry，零耦合） |
| `vectorizer/config/feat_sources.json` | 新增 47 行 | 专长来源书补充表 42 条（共享表未覆盖的书） |
| `vectorizer/config/feat_types.json` | 新增 30 行 | feat_type 白名单/变体归一/无信息标签/PFS 否定集 |
| `vectorizer/tests/test_feat_format.py` | 新增 247 行 | 26 tests（test_seeds.jsonl 驱动，schema 即断言） |
| `vectorizer/tests/test_feat_processor.py` | 新增 431 行 | 44 tests（字段/先决条件/元数据/来源/文件条件） |
| `pf_rules_md_organized/专长/造物专长一览.md` | 源数据修复 | 行内标签链拆行 + `**描述：**` 边界（见 §5） |
| `docs/专长/产出即检_首轮_20260801.md` | 文档 | 三件套结论 + 遗留登记 K1~K7 |

## 3. 关键实现决策

### 3.1 parse_fields 双格式 + 值边界（对齐 spell，KN013 M5 同款）

- 捕获：`**标签：**` / `**标签**：` 双格式正则
- 边界集 = 全量标签 + extra 标签（推荐背景/描述）：**extra 只作值边界不产字段**（防吞值）
- 值边界 = 下一个字段标签（`\n\*\*标签…`）+ 空行 + 文本末尾
- `"效果"` 收入 benefit 别名（设计 §2.2 漏收，registry 补）

### 3.2 prerequisites 结构化（设计 §三：只做形态识别，不做语义理解）

- `{"raw": raw, "items": [...]}`；检索主键是 raw 原文
- 8 形态识别顺序：or 分支（bab 挂 `or` 字段）→ bab → ability → skill（24 技能白名单）→ class_level → race（变身者/种族/血统）→ spell（施放前缀）→ feat（括号英文或纯中文）→ other
- 已实现边界：`"拥有 BAB+6"`（前缀变体）→ other、"感知3级"→ class_level（ability 锚定 `$` 限制），均靠 raw 兜底检索

### 3.3 field_status 三态（设计 §2.4，无 ambiguous）

- parsed / missing / not_applicable
- 任务链三字段 + 造物三字段按**字段族**判 not_applicable（普通专长无 task_goal）
- prerequisites 看 raw 有值；pfs_eligible True→parsed、False→missing；format_cluster 恒 parsed

### 3.4 来源书兜底链（标准链外，专长特有）

- 标准 provider 链（SOURCE_BOOK_ABBREVIATIONS 33 本书）→ "?" 时：
  - 通道 1：来源引用块（`> 来源：中文（English）→ 缩写 →`），置信度 65
  - 通道 2：HTML 注释缩写查 `feat_sources.json` 补充表（42 条）
- 效果：来源 "?" 953/2846（33.5%）→ 571/2846（20.1%）
- 剩余 "?" 全部为 page_* 未整理混排页（无来源标记，保持 "?" 不编造）

### 3.5 值清洗

- 值尾标点/星残留 rstrip（`"无；"`→`"无"`、`"坚忍 **"`→`"坚忍"`）、全角空格→半角

## 4. 验证证据

| 验证 | 结果 |
|---|---|
| TDD 红→绿 | test_feat_format.py 26 → 全绿；test_feat_processor.py 44 → 全绿 |
| 全量回归 | 首轮 **341 passed**（70 feat + 141 spell + 其余）；R1 返工后 test_feat_format 58 seeds + test_feat_processor 全绿（110 passed），全库 374 passed + 2 skipped（排除依赖法术输出的环境项） |
| pipeline | 首轮 2846 chunks（124 输入文件 / 86 处理文件）；R1 返工后 **3706 chunks**（189 rel = 根目录 66 + 专长/ 123，chunk_id 全唯一） |
| 产物抽样 | 造物条目（craft_cost/conditions/aura 全解析）、任务链 34 条（task_goal/reward + prerequisites 结构化含 or 分支） |
| 产出即检①title | 已整理文件全合法；412 问题全在 page_* 未整理页 |
| 产出即检②字段 | 已整理文件全健康；field_status 诚实性 0 问题（标签形态精确复测） |
| 产出即检③召回 | 1072 基线（R8 联合去重口径）整体 78.2%；**已整理文件 100%**（缺口来源书无已整理专长文件，矩阵仅含其未整理 page 文件）；234 缺口全为核心书源数据缺失 |

## 5. 修复项：造物专长一览吞值（82d3d39）

- 现象：craft_cost 值吞描述段（349 字，6 个中 2 个超长）
- **根因**：`split_into_items` 按行拼接 text（`splitlines()` + 空行 `continue`），统一 IR 中无空行 → parse_fields 的 `\n\n` 硬边界在 feat 数据中永不触发；字段链中间的描述段被前值吞入
- 修复（源数据，改数据不改脚本）：
  1. 行内标签链（`**先决条件**：…**专长效果**：…`）拆为独立行
  2. 四星头（`****灵光**：`）归一 + 半标签（`制造条件**：`）补星 + 值尾星清除
  3. 描述段行首加 `**描述：**`（extra 标签作值边界，不产字段）
- 验证：造物专长一览 craft_cost 6→3 超长，3 值全干净；diff 33 行实质变化全部为预期，无误伤

## 6. 遗留登记（k3 汇总输入，详见产出即检_首轮报告）

| # | 项 | 规模 | 建议 |
|---|---|---|---|
| K1 | page_* 未整理页来源 "?" | 571 chunks（20.1%） | 逐页核对或维持 "?" |
| K2 | page_* 列表标题伪条目 | 23 + 27 空 chunk | 列表页不产条目/剔除 |
| K3 | page_* title 形态 | 412 | 随整理消解 |
| K4 | page_* 字段吞值 | ~10 条 | 随整理消解 |
| K5 | 核心书专长正文缺失 | 234 专长（UC 101/CRB 79/ACG 33/ARG 18/UM 3） | 未整理整理立项 |
| K6 | craft_conditions"位置"/craft_aura"施法者等级"别名聚合边界 | 6 条 | 设计 §2.2 别名复核（值无害，信息在 text） |
| K7 | 重复 title 同书多份 | 543 个 | Prepare 已知"同书多份取主版本"对账 |

## 7. 红线与不变量

- 未触碰已冻结模块（spell/profession 无重构；spell.py 的 34 行改动为 KN023 修复，属 6f79c90 交付）
- 共享 provider 链（SOURCE_BOOK_ABBREVIATIONS）未修改——专长补充表独立于 `config/feat_sources.json`
- 测试完整性：无跳过/修改断言绕过 bug（TDD 全绿）
- 基线 `术语提取报告_分类版.md` 未动；造物专长一览修改为规范化格式（语义不变）

## 8. 下一步

1. **V/N 迭代闭环**：按 `专长审计要求与豁免程序.md` 召 k3 审计（审计-返工协议）
2. **k3 汇总**：消化 K1~K7（含 file 前缀口径、同书多份取主版本、6 种放行形态入规范、偏差对账）
3. 核心书专长整理立项（K5，预计 +500 条，取决于 CHM 源提取率）
