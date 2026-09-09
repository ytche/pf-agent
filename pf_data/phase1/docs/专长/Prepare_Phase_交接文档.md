# 专长模块 Prepare Phase 交接文档

> **状态：✅ Prepare Phase 已关闭**（2026-07-31，三轮返工终审通过，commit `5bdba32`，189 份记录 / 条目合计 3635）。终审结论见 `Prepare_Phase_三轮返工终审结论.md`，后续进 k3 汇总阶段（format_clusters / source_spec / test_seeds）。

> k3 设计（2026-07-30）→ 执行模型（deepseek-v4-pro / minimax3）执行 → k3 汇总审计。
> 本文档是**整包交付**：执行方只需读这一份 + 分批清单 `vectorizer/exploration/专长/prepare_batches.json`。

## 〇、任务一句话

通读专长模块全部 190 个源 md（约 3.1MB，17 批），**理解每个文件的语义结构和条目形态**，产出逐文件勘探记录 `per_file.jsonl`，为后续格式簇归并、元数据 schema 设计、formats/feat.py 解析器开发提供事实基础。

## 一、为什么强调"阅读与语义理解"

本阶段**不是模式计数**——机械可数的（链接数、〔〕标记分布、图片行、表格行数）由 k3 的机检脚本另行产出 `scan_report.md`，不占用你的上下文。

你的核心价值是机检做不到的事：

1. **读懂条目**：每类形态至少完整读 2~3 个条目，理解"一个专长条目由哪些部分组成、边界在哪、标题和正文怎么衔接"，而不是数正则命中。
2. **判定文件性质**：这个文件是一本书的专长章节？一张统计表？一个聚合一览页？还是规则散文？（→ `doc_role`，见 §四）
3. **陷阱定性**：发现异常模式时，判断"这会坑到解析器吗、怎么坑"，给出业务定性而非模式描述。
4. **格式簇建议**：判断"这个文件的写法和哪几个文件是同一类"，给出可归正则表达的簇特征。

**反例**（法术模块真实教训）：只数 `**` 命中数就当条目数，结果漏掉了断行标题的条目；看到表格就当条目表，结果把修饰词调整表当成专长条目。这两类错误本阶段必须靠"真的读了"来避免。

## 二、范围与批次

- 范围：`pf_rules_md_organized/专长*.md`（顶层 62 个）+ `pf_rules_md_organized/专长/`（含子目录，128 个），共 **190 文件 / 3181KB**。
- 批次：`vectorizer/exploration/专长/prepare_batches.json`，**17 批，每批 ≤200KB**（你的上下文窗口约 200k，超限会被压缩，严格按批执行，不要并批）。
- **机检除外项**：`专长/page_202.md`（全专长列表，1252 表格行）不在批次内，由 k3 脚本解析，你不用读。
- 每批一次会话/任务跑完即写产出，批间无依赖。

## 三、已知背景（读完再开工）

### 3.1 三类特殊文档（doc_role 判定依据）

| doc_role | 含义 | 实锤示例 |
|---|---|---|
| `overview` | 概述页：讲专长的组成部分与意义，**不产条目**，是元数据设计输入 | `专长/page_194.md`（专长概述 Feat Concept） |
| `index_table` | 类表页：整页表格统计专长，**不产条目**，是审计基线来源 | `专长/page_202.md`（机检）、`专长/page_196.md` 等表头占比高的 page |
| `aggregation` | 一览聚合页：把散在各书的同系列专长统合到一页，**与原始正文页条目重复** | `专长/page_1367.md`（超魔专长一览）、`专长/造物专长一览.md`、`专长/流派专长一览/page_1564.md` |
| `detail` | 条目正文页：chunk 的主要来源（大多数文件） | 各书 `_专长.md`、`专长NN.md` |
| `mixed` | 兼有以上两种及以上 | `专长.md`（正文+修饰词调整表） |

**聚合页判定时多想一步**：某些专长可能**只**在一览页有正文（原始规则书未单独成页）。遇到聚合页，在 `dedup_note` 里记录你的判断：条目看起来像"转载摘要"还是"唯一出处"。

### 3.2 专长条目已知形态（勘探假设，用你的阅读验证/推翻）

- 标题行形态：`**中文名（English）**〔战斗〕` —— `〔〕` 内是 feat_type，官方 10 类：**战斗/重击/勇毅/造物/演武/超魔/派头/流派/故事/团队**（权威来源：page_202 前言）。
- 字段标签：`**先决条件**`、`**专长效果**`、`**通常状况**` 等，可能独立行也可能内联。
- 已实测的坑：
  - **断行英文名**：`（English` 和 `）` 断成两行（`专长.md` 开篇即是；机检共 1721 行）。
  - **裸 CR 行内断裂**：28 个文件（主要是类表页）混用 CR/LF/CRLF，表格单元格被 `\r` 断成多行。用 Python 读文件请 `open(..., newline="")` 再自行切分；表格行重组参考 `prepare_scan.py` 的 `read_logical_lines()`。
  - **表格双语分行**：表格里英文名一行、中文名下一行（`专长/page_276.md`）。
  - **表格名单元格三形态**：英文在前 / 中文在前（`引导力刃  Channeling Force`）/ 纯单语；紧贴中文名前的全角空格 `　` 个数 = 链式深度（进阶链标记）。
  - **表格可能无 `| --- |` 分隔行**（如 page_202 勇毅专长表，表头后直接是数据行）。
  - **feat_type 双标签**：类型单元格可能是 `重击 战斗` 两标签；`〔〕` 也有 `〔战斗，团队〕` 复合形态及 `****战斗` 加粗粘连形态。
  - **链接陷阱**：`](http` 密集（`专长11.md` 103 处），链接后正文可能缺失（法术 KN023 同型缺陷）。
  - **译者行**：`译者：xxx` 不是条目。
  - **PFS 图标行**：行首图片标记，可能是 PFS 合法标记（元数据机会，不是噪声；机检 305 行）。
  - **同文件重复条目**：如"突袭警惕"在同文件出现两次。
  - **非条目表格**：修饰词调整表、效果对照表与专长条目表共存（`专长.md`），注意区分。

> **机检产出已就绪**：`scan_report.md`（总量与 TOP 榜）、`machine_scan.jsonl`（逐文件计数）、`audit_baseline.jsonl`（page_202 解析：1226 行 / 1072 专长（R8 口径：name_zh+name_en 联合去重，原机检为单口径去重）/ 8 来源书）。勘探时可对照参考，但**不要照抄机检结论**——你的价值在语义判定（见 §一）。

### 3.3 HTML 对照回溯机制

md 乱到无法判定条目边界时，**读对应原始 HTML 确认结构**：

- 映射文档：`pf_data/CHM_FULL_TOC.md`（逐条记录 `目录标题 ↔ page_NNN.html / 名字.htm`）。
- HTML 源目录：`~/.openclaw/workspace/pf_rules/`（1383 个）。
- 回溯方法：`page_NNN.md` 同名直查 `page_NNN.html`；命名 md 按标题在 CHM_FULL_TOC.md 反查。
- **红线**：HTML 只用于看懂结构，勘探结论描述的是 md 现状；触发过回溯的文件在 `traps` 里加 `"html_consulted": true`。

## 四、交付物：per_file.jsonl

**每批写回一个文件**：`vectorizer/exploration/专长/per_file_BNN.jsonl`（NN=批号，对齐 manifest），每行一个文件：

```json
{
  "file": "专长/page_276.md",
  "batch": 7,
  "size_kb": 24,
  "doc_role": "detail",
  "title_forms": [
    {"pattern": "**中文名（English）**〔战斗〕", "count": 12, "note": "〔〕为feat_type"}
  ],
  "field_layout": "独立行",
  "field_labels_seen": {"先决条件": 12, "专长效果": 12, "通常状况": 3},
  "feat_type_tags": ["战斗"],
  "estimated_count": 12,
  "count_basis": "完整阅读后逐条计数；表格双语分行已合并计1条",
  "first_entry": "奥多里剑斗学徒",
  "last_entry": "怒流剑式",
  "traps": [
    {"kind": "表格双语分行", "example_line": "L31-32", "risk": "行解析会把一条拆成两条"},
    {"kind": "断行英文名", "example_line": "L8", "risk": "标题锚定失败", "html_consulted": true}
  ],
  "dedup_note": "本页条目与《内海战斗》原始章节重复，属转载",
  "format_cluster_hint": "表格型专长页-双语分行变体",
  "notes": "读完后的任何语义层面观察，一两句即可"
}
```

**字段硬要求**：

- `estimated_count` 必须配 `count_basis`（用什么依据数的），空口数字视为未交付。
- `doc_role` 五选一，不确定时标 `mixed` 并在 `notes` 说明。
- `title_forms[].pattern` 要**可归正则表达**（"**加粗开头、（英文）收尾"这种），禁止"看着像标题"。
- `traps` 里的 `kind` 用稳定词表（断行英文名/链接陷阱/表格双语分行/译者行/PFS图标/重复条目/非条目表格/无标题正文/其他），新类型用"其他：xxx"并在 notes 描述。
- 没有条目的文件（overview/纯散文）：`estimated_count: 0`，`count_basis` 写明"通读全文，无独立专长条目"。

## 五、红线

1. **只读源数据**，只对 `vectorizer/exploration/专长/` 有写权限；不改任何 `pf_rules_md_organized/` 文件。
2. **逐批交付**：跑完一批立即写 `per_file_BNN.jsonl`，不要攒多批合并写。
3. **行数自检**：每批写完自查 jsonl 行数 == manifest 中该批文件数，缺一补一。
4. **不猜不省**：读不完的大文件（如单文件 >100KB）至少完整读开头 3 条 + 中间 2 条 + 结尾 1 条 + 全文结构扫视，并在 `count_basis` 写明抽样方式。
5. **机检不重复做**：链接计数、`〔〕` 标记统计等由 k3 脚本负责；你只需在 traps 里**定性**（"这个链接模式会导致什么后果"），不用精确计数。
6. 遇到和 §3.2 假设冲突的形态，**以你读到的为准**并写进 notes——假设就是用来被推翻的。

## 六、k3 侧配套（执行方知悉即可）

| 交付物 | 产出者 | 说明 |
|---|---|---|
| `per_file_BNN.jsonl` ×17 | 执行模型 | 本文档 §四 |
| `scan_report.md` ✅ | k3 脚本 | 五合一机检：链接/断行/〔〕标记/图片行/表格块/裸CR（`prepare_scan.py` 已产出） |
| `audit_baseline.jsonl` ✅ | k3 脚本 | page_202 全专长列表解析：1226 行 / 1072 专长（R8 联合去重口径）/ 8 来源书，召回验收基线 |
| `format_clusters.md` | k3 汇总 | 格式簇归并，每簇带判别正则 |
| `source_spec.md` | k3 汇总 | 含聚合页去重策略、sole_source 处理 |
| `test_seeds.jsonl` | k3 汇总 | 从各簇挑代表条目，供 formats/feat.py TDD |

**对账规则**（k3 执行）：你的 estimated_count 与机检特征计数偏差 >20% 的文件会被抽样复读；每簇 k3 亲自读 1~2 个代表文件验证归属。

## 七、每批 Prompt 模板

```
你在执行 PF1e 规则书向量化的 Prepare Phase 勘探（专长模块）。
先读交接文档：pf_data/phase1/docs/专长/Prepare_Phase_交接文档.md（全文）。
再读批次清单：pf_data/phase1/vectorizer/exploration/专长/prepare_batches.json，你只跑第 NN 批。
逐文件通读（大文件按交接文档 §五.4 抽样），逐文件写一行 JSON 到
pf_data/phase1/vectorizer/exploration/专长/per_file_BNN.jsonl。
完成后报告：本批文件数、jsonl 行数、doc_role 分布、发现的新陷阱类型（"其他：xxx"清单）。
```

## 八、完成标准

- [ ] 17 个 `per_file_BNN.jsonl` 齐全，行数与 manifest 一致
- [ ] 每行 11 个必填字段完整，`count_basis` 非空
- [ ] 每批完成报告含 doc_role 分布与新陷阱清单
- [ ] 触发 HTML 回溯的文件均有 `html_consulted: true`
