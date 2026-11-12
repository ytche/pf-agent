# KN（数据侧已知）108 职业根页面纳入与 rule_version Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将职业根目录 7 个遗漏页面按显式清单纳入职业产物，为职业 chunk 增加可靠的 `metadata.rule_version`，并完成全量验证、职业向量库重灌和问题销账。

**Architecture:** 根页面保留物理原位，通过 `RootPageSpec` 清单映射到职业逻辑路径；文件选择、canonical 预扫描和处理派发共用同一路径解析。`_to_standard` 统一应用 `page_244` 覆盖和 rule_version 三级优先级，块层清洗、拆分、合并和 Java Mapper 均不改。

**Tech Stack:** Python 3、pytest、既有 vectorizer pipeline/CICD/build、Java SimpleVectorStore JSON 全量重灌流程。

**Spec:** `docs/design/方案_KN108职业根目录页面纳入与rule_version_20261109.md`

## Global Constraints

- 不修改、移动或复制 `pf_rules_md_organized/**` 中任何源 Markdown；实施前后核对 7 页 SHA-256。
- 不改 Java、检索端、既有页面的块层行为、9 个来源 Provider 或 POSTPROCESSORS；不引入 `pfs_eligible`。仅清单 7 页在 clean 后保留标题正文，以修复真实产物暴露的锚点丢失。
- `page_244` 固定为 `class_overview`、`class_name=""`、PFS/探索者协会/Pathfinder Society、`rule_version="unchained"`。
- Unchained 只按逻辑 `doc_id` 前缀 `掉链子（Unchained）/` 判断，不按 `chm_toc_path` 或 `book=PU`。
- book 为空或 `?` 时不写 `rule_version`；显式清单覆盖必须按完整 `doc_id == logical_rel` 匹配，不得只按 basename。
- 所有 Python 命令在 `pf_data/phase1/` 执行；职业重跑只走 `python3 -m vectorizer.cicd verify --category profession` 或统一 build，不直跑 pipeline。
- 每阶段提交；产物变化必须登记 DVG（数据漂移债务）并全量重灌职业库，禁止 Java 元数据补丁。

## Review Focus

- 根页面进入 canonical 集后，变体预扫描也直接 `relative_to(INPUT_DIR)` 会报错；Task 1 用真实 `load_resources` 覆盖。
- 职业目录内若存在同名 `page_244.md`，不得套用根页面覆盖；Task 2 用完整 doc_id 负向测试覆盖。
- `page_411` 可能受 SummonerProcessor 特化影响；Task 1 冒烟检查正文，Task 3 对既有召唤师块做零回归。
- 按 toc 标 Unchained 会误标核心职业/盗贼/野蛮人；Task 3 加全产物负向断言。
- 7 个新输入若不进 build manifest，源文件变化不会触发构建漂移；Task 1 登记精确输入，Task 4 用 `build check` 验证。

---

## 执行状态（2026-11-10 收尾补记）

Task 1~5 全部步骤已完成并验收：最终产物 14060 块（13922→+138，全属 7 个 logical doc_id），职业 CICD 集成验收 11/11、全量 pytest 1848 passed、源哈希 7/7、双跑指纹一致（`f75229ae…`）、`build check` 14/14 全绿；职业向量库全量重灌 14060 条（DVG-014 清偿，备份 `~/.pf_agent/vector_store_classes.json.bak_20261110_111024`）。执行细节与证据见 `.superpowers/sdd/2026-11-10-kn108-profession-root-pages-rule-version/task-4-report.md` 与 `task-5-report.md`；交付测试报告 `docs/test-reports/测试报告_KN108职业根页面与rule_version_20261110.md`。

**合并验证追加修复（同日，TDD）**：`build.py::expand_inputs()` 将 glob 命中的 `.DS_Store` 计入输入指纹，致主工作区合并后 chunks.feat/race/equipment/profession 指纹失败；最小修复为 glob 展开忽略 basename `.DS_Store`（显式 config_deps/script 语义不变），RED→GREEN 后全量 pytest **1848 passed**、`build check` 14/14；产物与 state 零变化，无需重建/重灌（详见测试报告 §6.1 与 `/tmp/kn108-ds-store-fix-report.md`）。

### Task 1: 显式清单与逻辑路径接入

**Files:**
- Create: `pf_data/phase1/vectorizer/tests/test_profession_kn108.py`
- Modify: `pf_data/phase1/vectorizer/processors/profession.py`
- Modify: `pf_data/phase1/vectorizer/build_manifest.json`

**Interfaces:**
- Produces: `RootPageSpec` dataclass；`ROOT_PAGE_MANIFEST: Dict[str, RootPageSpec]`。
- Produces: `_profession_rel_path(abs_path: Path) -> Path`，供 canonical 预扫描和 `process()` 共用。
- Produces: `_root_page_spec_for_path(abs_path: Path) -> Optional[RootPageSpec]`，只匹配整理目录根层的清单文件。

- [x] **Step 1: 保存实施前基线**

```bash
cp vectorizer/output/职业/chunks.jsonl /tmp/kn108_profession_chunks_before.jsonl
shasum -a 256 pf_rules_md_organized/page_{30,53,128,134,244,411,609}.md > /tmp/kn108_sources_before.sha256
```

Expected: 基线共 13922 行，7 个哈希均已记录。

- [x] **Step 2: 写文件选择与逻辑路径失败测试**

在 `test_profession_kn108.py` 固定以下映射，并逐条断言 `_profession_rel_path(INPUT_DIR.parent / name).as_posix() == logical`、`_profession_file_condition(...) is True`：

```python
EXPECTED_ROOT_RELS = {
    "page_30.md": "职业概述/page_30.md",
    "page_53.md": "核心职业/武僧/武僧清规/page_53.md",
    "page_128.md": "进阶职业/page_128.md",
    "page_134.md": "进阶职业/CRB进阶职业/龙脉术士/page_134.md",
    "page_244.md": "掉链子（Unchained）/page_244.md",
    "page_411.md": "基础职业/召唤师/幻灵/page_411.md",
    "page_609.md": "神话冒险/page_609.md",
}
```

另测：既有 `INPUT_DIR / "核心职业/圣骑士/page_55.md"` 的相对路径保持原样；根目录 `page_31.md` 和其他模块文件不匹配职业条件；根页面在更深同名路径下不匹配 `_root_page_spec_for_path`。

- [x] **Step 3: 运行路径测试并确认失败**

Run: `python3 -m pytest vectorizer/tests/test_profession_kn108.py -q`
Expected: 因清单/路径helper尚不存在或根页面仍被排除而 FAIL，不是测试语法错误。

- [x] **Step 4: 实现清单与三处路径接入**

在 `processors/profession.py` 定义 `RootPageSpec`，字段为 `logical_rel: str`、`rule_version: Optional[str] = None`、`component_type: Optional[str] = None`、`book_override: Optional[dict] = None`、`class_name: Optional[str] = None`、`processor: Optional[str] = None`。写入上表 7 项；page_244 的其余覆盖在 Task 2 填入。

`_profession_file_condition`、`load_resources` canonical 扫描及变体预扫描、`process()` 全部复用上述helper。根文件读取仍使用 resolve 后的真实 `abs_path`，只把 `rel_path` 换成 `Path(spec.logical_rel)`；不得创建逻辑目录。

- [x] **Step 5: 登记构建输入**

在 `chunks.profession.inputs` 保留 `pf_rules_md_organized/职业/**`，追加 7 个 `pf_rules_md_organized/page_N.md` 精确路径。
Expected: 7 页均能被统一构建追踪，不使用额外通配符扩大输入范围。

- [x] **Step 6: 写并运行真实页面集成测试**

在测试文件追加模块级 `proc` fixture（`ProfessionProcessor(None)` + `load_resources(INPUT_DIR)`）和 7 页集成测试：逐页 `process()` 非空，所有 `doc_id == logical`，`metadata.source_paths == [logical]`。先运行 page_244/page_411，再运行全文件。

Run: `python3 -m pytest vectorizer/tests/test_profession_kn108.py -q`
Expected: 路径与条件测试 PASS；无 canonical 预扫描 `ValueError`；page_411 的“幻灵/生命骰/基本攻击加值/技能/专长”均在产物文本中。仅当 SummonerProcessor 被实证破坏这些锚点或既有召唤师结构时，才将 page_411 的 `processor="base"` 并加 `create_processor` 回落测试；否则保持正常分派。

- [x] **Step 7: 跑职业既有回归**

Run: `python3 -m pytest vectorizer/tests/test_profession_*.py -q`
Expected: 全绿。

- [x] **Step 8: 提交本阶段**

```bash
git add pf_data/phase1/vectorizer/processors/profession.py pf_data/phase1/vectorizer/tests/test_profession_kn108.py pf_data/phase1/vectorizer/build_manifest.json
git commit -m "feat(vectorizer): 纳入职业根目录七页"
```

### Task 2: rule_version 与 page_244 覆盖

**Files:**
- Modify: `pf_data/phase1/vectorizer/processors/profession.py`
- Modify: `pf_data/phase1/vectorizer/tests/test_profession_kn108.py`

**Interfaces:**
- Consumes: Task 1 的 `ROOT_PAGE_MANIFEST`、真实页面 `proc` fixture。
- Produces: `_root_page_spec_for_doc(doc_id: str) -> Optional[RootPageSpec]`。
- Produces: `_resolve_rule_version(doc_id: str, book_abbreviation: Optional[str]) -> Optional[str]`，顺序为清单覆盖 → Unchained 路径 → book 小写。

- [x] **Step 1: 写 rule_version 优先级和空值失败测试**

```python
assert _resolve_rule_version("掉链子（Unchained）/page_244.md", "PFS") == "unchained"
assert _resolve_rule_version("掉链子（Unchained）/盗贼/page_x.md", "PU") == "unchained"
assert _resolve_rule_version("核心职业/武僧/page_53.md", "CRB") == "crb"
assert _resolve_rule_version("核心职业/武僧/page_53.md", "") is None
assert _resolve_rule_version("核心职业/武僧/page_53.md", "?") is None
assert _root_page_spec_for_doc("核心职业/武僧/page_244.md") is None
```

- [x] **Step 2: 写 page_244 真实产物失败测试**

对 `proc.process(INPUT_DIR.parent / "page_244.md")` 的每个 chunk 断言：

```python
assert c.component_type == "class_overview"
assert c.metadata["class_name"] == ""
assert c.book_abbreviation == "PFS"
assert c.book_name_cn == "探索者协会"
assert c.book_name_en == "Pathfinder Society"
assert c.metadata["rule_version"] == "unchained"
assert "pfs_eligible" not in c.metadata
```

另取真实 Unchained 目录页和普通 CRB 页，分别断言 `unchained` 与 `crb`。对普通 CRB 页的一个旧 `Chunk` 使用 `dataclasses.replace(c, book_abbreviation="?")` 构造样本，再调用 `proc._to_standard(...)`，断言结果没有 `rule_version` 键，避免依赖产物中恰好存在某个占位来源页。

- [x] **Step 3: 运行并确认新断言失败**

Run: `python3 -m pytest vectorizer/tests/test_profession_kn108.py -q`
Expected: Task 1 用例保持 PASS；rule_version/page_244 用例因字段缺失或默认来源未覆盖而 FAIL。

- [x] **Step 4: 实现统一字段转换**

在 `_to_standard` 先按 `c.doc_id` 查完整路径清单。仅对非 `None` 覆盖应用 component/book/class_name；`class_name=""` 必须真正写入。rule_version 由 `_resolve_rule_version(c.doc_id, c.book_abbreviation)` 计算，返回非 `None` 时才增加 metadata 键；既有键顺序不变。

page_244 清单填入 `rule_version="unchained"`、`component_type="class_overview"`、`class_name=""` 和固定 PFS 三字段。不得按 toc 或 PU 特判，不得转发到 Java Mapper。

- [x] **Step 5: 验证并提交**

Run: `python3 -m pytest vectorizer/tests/test_profession_kn108.py vectorizer/tests/test_profession_*.py -q`
Expected: 全绿。

```bash
git add pf_data/phase1/vectorizer/processors/profession.py pf_data/phase1/vectorizer/tests/test_profession_kn108.py
git commit -m "feat(vectorizer): 标注职业规则版本与PFS来源"
```

### Task 3: 产物锚点与负向闸口

**Files:**
- Modify: `pf_data/phase1/vectorizer/verify/verify_profession.py`
- Modify: `pf_data/phase1/vectorizer/tests/test_profession_verify_checks.py`

**Interfaces:**
- Produces: `check_kn108_root_pages(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]`。
- Produces: `check_rule_version(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]`。
- 两项加入 `ProfessionVerify.checks`，由职业 CICD 对真实 `chunks.jsonl` 执行。

- [x] **Step 1: 写锚点检查的红测试**

用最小 chunk dict 构造 7 页合法样本，再分别删除一个锚点、写错 page_244 PFS/class_name/component_type、伪造 source_paths，断言检查 FAIL 且问题含页名。合法样本必须 PASS。

`check_kn108_root_pages` 对每页 doc_id 至少 1 块，并覆盖：page_30=职业概述/术语定义/施法者等级；page_53=武僧清规及不邪淫戒/囚执戒/清净戒/持斋戒/不杀生戒/安贫戒/不语戒/不妄语戒；page_128=进阶职业/全进阶职业一览；page_134=龙徒/进阶要求/角色定位；page_244=对PFS官方游戏的影响；page_411=幻灵/生命骰/基本攻击加值/技能/专长；page_609=大法师/斗士/守护者/圣者/统帅/诡术大师。

- [x] **Step 2: 写 rule_version 全库规则红测试**

合法样本断言：所有 Unchained doc 为 `unchained`；核心职业/盗贼/野蛮人不得为 `unchained`；其他有效 book 必须等于小写；空或 `?` 无键。分别制造 toc 含 Unchained 但 doc 不含、有效 book 未标、占位 book 误标、page_244 写成 `pfs` 的样本，均应 FAIL。

空/占位来源数量以 `⚠️ rule_version 省略（book 空或 ?）：N` 报告，不因此失败。

- [x] **Step 3: 运行检查测试并确认失败**

Run: `python3 -m pytest vectorizer/tests/test_profession_verify_checks.py -k 'kn108 or rule_version' -q`
Expected: 两个检查尚不存在或缺少断言而 FAIL。

- [x] **Step 4: 实现检查并接入职业验收**

将两个检查加入 `ProfessionVerify.checks`。负向范围以 doc_id 为准；不扫描其他模块，不根据 title 猜测规则版本。清单外整理目录根层文件不得新增职业 chunk 由 Task 1 文件选择测试与 Task 4 全量 diff 共同保证。

- [x] **Step 5: 验证并提交**

Run: `python3 -m pytest vectorizer/tests/test_profession_verify_checks.py vectorizer/tests/test_profession_kn108.py -q`
Expected: 全绿。

```bash
git add pf_data/phase1/vectorizer/verify/verify_profession.py pf_data/phase1/vectorizer/tests/test_profession_verify_checks.py
git commit -m "test(vectorizer): 锁定职业根页面与版本闸口"
```

### Task 4: 全量重建、零回归对账与可复现性

**Files:**
- Modify: `pf_data/phase1/vectorizer/processors/profession.py`（仅限真实产物暴露的根页标题保留修正）
- Modify: `pf_data/phase1/vectorizer/tests/test_profession_kn108.py`
- Modify: `pf_data/phase1/vectorizer/state/build_state.json`（仅由统一构建命令更新）

**Interfaces:**
- Consumes: Tasks 1–3 的实现和闸口、Task 1 的 `/tmp` 基线。
- Produces: `_preserve_root_heading_text(lines: List[str]) -> List[str]`，只对 ROOT_PAGE_MANIFEST 的 7 个逻辑 doc_id 生效。
- Produces: 最终职业 chunks、实测增量、全量测试与构建证据，供 Task 5 报告引用。

- [x] **Step 1: 用真实 7 页产物固化标题锚点 RED**

在 `test_profession_kn108.py` 聚合 `proc.process()` 的 7 页真实 StandardChunk，用 `dataclasses.asdict` 转换后调用 `check_kn108_root_pages`，断言 `ok is True`。不得把源锚点手工填入 text 构造假绿。

Run: `python3 -m pytest vectorizer/tests/test_profession_kn108.py -k real_root_pages_pass_verify -q`
Expected: FAIL，真实缺失为 page_30 的职业概述/术语定义、page_53 的武僧清规、page_128 的全进阶职业一览、page_134 的进阶要求、page_244 的对PFS官方游戏的影响。

- [x] **Step 2: 最小保留根页标题正文并转绿**

实现 `_preserve_root_heading_text(lines)`：每条非空 Markdown 标题保留原行，并在下一行插入一次去掉 `#` 和首尾空白后的标题文本。`FileProcessor.clean()` 仅在 `_root_page_spec_for_doc(self.doc_id)` 非 None 时调用；既有职业页、其他模块、源文件均不变，page_411 仍走 SummonerProcessor。

Run: `python3 -m pytest vectorizer/tests/test_profession_kn108.py vectorizer/tests/test_profession_verify_checks.py -q`
Expected: 全绿；真实 7 页通过既有闸口，不删除或放宽任何锚点。

```bash
git add pf_data/phase1/vectorizer/processors/profession.py pf_data/phase1/vectorizer/tests/test_profession_kn108.py
git commit -m "fix(vectorizer): 保留职业根页标题锚点"
```

- [x] **Step 3: 跑职业完整 CICD**

Run: `python3 -m vectorizer.cicd verify --category profession`
Expected: pytest、职业重建、两个新检查和数据不变量全部通过；记录真实总块数、7 页各自块数、rule_version 分布和省略数。若既有召唤师或其他非目标 doc 漂移，停止排查，不改测试放行。

- [x] **Step 4: 与基线逐 chunk 对账**

用 Python 读取 `/tmp/kn108_profession_chunks_before.jsonl` 和当前产物：每个旧 chunk_id 必须仍存在，`doc_id/toc/class_name/title/text` 及原 metadata 键值完全一致，唯一允许新增的既有键是 `rule_version`；新增 chunk 只能属于 7 个 logical doc_id；chunk_id 冲突不得扩大，7 页 source_paths 均为 `[doc_id]`。基线已有的 102 个重复 chunk_id 行只核对集合不变，登记既有债，不在本批顺手修。

Expected: 非目标块零回归；把实测增量与所有新增 doc 写入后续报告，不用估算数替代。

- [x] **Step 5: 跑全量数据测试与源哈希复核**

```bash
python3 -m pytest vectorizer/tests -q
shasum -a 256 -c /tmp/kn108_sources_before.sha256
```

Expected: 全量 pytest 全绿；7 个源文件全部 OK。

- [x] **Step 6: 验证可复现构建与全仓对账**

Run: `python3 -m vectorizer.build chunks.profession --force` 两次，分别计算职业 chunks 内容 SHA-256；再运行 `python3 -m vectorizer.build check`。
Expected: 两次 chunks 内容指纹一致；14 个 artifact 全绿。若其他 artifact 仅因本批共享代码/输入指纹而过期，用 `python3 -m vectorizer.build all --force` 统一迁移并逐产物确认内容变化可归因；禁止为刷状态手改 JSON。

- [x] **Step 7: 提交构建状态**

```bash
git add pf_data/phase1/vectorizer/state/build_state.json
git commit -m "chore(数据): 刷新职业根页面构建指纹"
```

若构建状态无变化，不创建空提交。

### Task 5: 职业库重灌与文档销账

**Files:**
- Modify: `pf_data/phase1/docs/已知问题记录.md`
- Modify: `docs/design/方案_KN108职业根目录页面纳入与rule_version_20261109.md`
- Modify: `docs/一期当前待办与问题汇总_临时.md`
- Modify: `docs/数据一致性技术债务登记.md`
- Modify: `docs/项目文档总索引.md`
- Modify: `docs/test-reports/README.md`
- Modify: `PROJECT_HANDOVER.md`
- Create: `docs/test-reports/测试报告_KN108职业根页面与rule_version_20261110.md`

**Interfaces:**
- Consumes: Task 4 的最终产物和实测证据。
- Produces: DVG（数据漂移债务）014 清偿记录、KN（数据侧已知）108 闭环记录和独立测试报告。

- [x] **Step 1: 备份并全量重灌职业向量库**

将 `~/.pf_agent/vector_store_classes.json` 移到带时间戳且不存在同名文件的备份路径，不覆盖旧备份。在 `pf_agent/agent/` 使用以下临时实例从最新产物导入：

```bash
PF_CHAT_MEMORY=memory mvn spring-boot:run -Dspring-boot.run.arguments="--server.port=0"
```

Expected: 日志显示职业库从 chunks 全量导入并保存，导入数等于 Task 4 最终产物数；导入完成后停止临时实例，不触碰常驻 8080 服务，不使用元数据重放或字段补丁。

- [x] **Step 2: 核对向量库与产物**

全量比对 store 与 chunks 的 `chunk_id/text` 及 Mapper 已支持的标准字段；抽验武僧 8 戒、龙徒、原版幻灵、6 道途和 page_244 PFS 来源。职业 Mapper 本批不暴露 rule_version，不得把“store 无该专用字段”误判为重灌失败，也不得为此改 Java。

- [x] **Step 3: 写测试报告并同步所有状态源**

报告包含根因、TDD 红绿证据、7 页锚点、真实前后计数、逐 chunk 对账、全量 pytest、双跑指纹、build check、源哈希和重灌结果。将 KN（数据侧已知）108 和设计方案标为已闭环；新增并清偿 DVG（数据漂移债务）014；同步一期临时汇总、项目索引当前队列、测试报告索引和 PROJECT_HANDOVER 状态。若完整流程跨日，报告文件名和文档日期使用实际交付日。

- [x] **Step 4: 最终检查并提交**

Run: `git diff --check && git status --short`
Expected: 无空白错误，只有本阶段文档与状态记录；无测试日志或临时产物进入仓库。

```bash
git add pf_data/phase1/docs/已知问题记录.md docs/design/方案_KN108职业根目录页面纳入与rule_version_20261109.md docs/superpowers/plans/2026-11-10-kn108-profession-root-pages-rule-version.md docs/一期当前待办与问题汇总_临时.md docs/数据一致性技术债务登记.md docs/项目文档总索引.md docs/test-reports/README.md docs/test-reports/测试报告_KN108职业根页面与rule_version_20261110.md PROJECT_HANDOVER.md
git commit -m "docs(数据): KN108 职业根页面与版本标注验收销账"
```
