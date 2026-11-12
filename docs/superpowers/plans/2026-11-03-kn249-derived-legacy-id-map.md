# KN249 派生式 legacy-id 映射 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 用构建时派生的完整 current→legacy 映射替换手写顺移区间，消除 92 条误锚 WARN，并保证未来页内增删不会误挂白名单。

**Architecture:** 新增 Spell 专用 `spell_legacy_id_map.py`，以 2026-10-29 state 为历史基线，按 doc_id + 标题序列对齐当前 split 条目，输出确定性 state。SpellProcessor 在 `load_resources` 中用同一 normalize/promote/split 链预扫描源文件，并将后处理索引 chunk 纳入对账；查询时显式区分 legacy ID 与无锚 `None`。

**Tech Stack:** Python 3 标准库（`difflib`、`json`、`pathlib`、`functools`）、既有 SpellProcessor/FileProcessor、pytest。

**设计依据:** `docs/superpowers/specs/2026-11-03-kn249-derived-legacy-id-map-design.md`

---

## 文件结构

- Create: `pf_data/phase1/vectorizer/processors/spell_legacy_id_map.py` — 历史清单装载、序列对齐、state 读写。
- Create: `pf_data/phase1/docs/state/spell_kn249_legacy_id_map.json` — 构建派生的完整映射，提交为可复现事实源。
- Modify: `pf_data/phase1/vectorizer/processors/spell.py` — 删除手写区间，接入派生 state 和构建前预扫描。
- Modify: `pf_data/phase1/vectorizer/tests/test_spell_title_cluster.py` — TDD 覆盖增删、重复标题、replace 闭锁及真实历史对账。
- Modify: `pf_data/phase1/docs/已知问题记录.md`、`docs/数据一致性技术债务登记.md`、`docs/项目文档总索引.md` — 修复状态和证据同步。

### Task 1: 纯序列对齐与 state 读写

**Files:**
- Create: `pf_data/phase1/vectorizer/processors/spell_legacy_id_map.py`
- Test: `pf_data/phase1/vectorizer/tests/test_spell_title_cluster.py`

- [x] **Step 1: 写删除、新增和 replace 的失败测试**

在测试文件追加，输入行统一使用 `chunk_id/doc_id/title`，历史行额外使用 `legacy_chunk_id`：

```python
import pytest

from vectorizer.processors.spell_legacy_id_map import derive_legacy_id_state


def _history(chunk_id, title, legacy_id=None, doc_id='page_1'):
    return {
        'chunk_id': chunk_id,
        'legacy_chunk_id': legacy_id if legacy_id is not None else chunk_id,
        'doc_id': doc_id,
        'title': title,
    }


def _current(chunk_id, title, doc_id='page_1'):
    return {'chunk_id': chunk_id, 'doc_id': doc_id, 'title': title}


def test_derived_legacy_id_map_handles_delete_and_insert():
    history = [
        _history('spell_page_1_0000', '甲'),
        _history('spell_page_1_0001', '乙'),
        _history('spell_page_1_0002', '丙'),
    ]
    current = [
        _current('spell_page_1_0000', '甲'),
        _current('spell_page_1_0001', '新增'),
        _current('spell_page_1_0002', '丙'),
    ]
    # 用两个 opcode 分别覆盖删除与新增，避免 replace 故意闭锁。
    deleted = derive_legacy_id_state(history, [current[0], current[2]])['id_map']
    assert deleted == [
        {'current_chunk_id': 'spell_page_1_0000', 'legacy_chunk_id': 'spell_page_1_0000',
         'doc_id': 'page_1', 'title': '甲'},
        {'current_chunk_id': 'spell_page_1_0001', 'legacy_chunk_id': 'spell_page_1_0002',
         'doc_id': 'page_1', 'title': '丙'},
    ]
    inserted = derive_legacy_id_state(history, current)
    assert inserted['id_map'][1]['legacy_chunk_id'] is None
    assert inserted['id_map'][2]['legacy_chunk_id'] == 'spell_page_1_0002'
    assert inserted['added'][0]['title'] == '新增'


def test_derived_legacy_id_map_rejects_replace_and_ambiguous_duplicate_insert():
    with pytest.raises(ValueError, match='page_1'):
        derive_legacy_id_state(
            [_history('spell_page_1_0000', '旧名')],
            [_current('spell_page_1_0000', '新名')],
        )
    with pytest.raises(ValueError, match='重复标题'):
        derive_legacy_id_state(
            [_history('spell_page_1_0000', '同名')],
            [_current('spell_page_1_0000', '同名'), _current('spell_page_1_0001', '同名')],
        )
```

- [x] **Step 2: 运行测试确认 RED**

Run: `cd pf_data/phase1 && python3 -m pytest vectorizer/tests/test_spell_title_cluster.py -k 'derived_legacy_id_map' -q`

Expected: collection ERROR，原因是 `vectorizer.processors.spell_legacy_id_map` 尚不存在。

- [x] **Step 3: 实现最小纯对齐与 state API**

创建模块，公开接口固定为：

```python
import json
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

PHASE1 = Path(__file__).resolve().parents[2]
BASELINE_STATE_PATH = PHASE1 / 'docs/state/spell_kn244_246_chunk_id_map_20261029.json'
DERIVED_STATE_PATH = PHASE1 / 'docs/state/spell_kn249_legacy_id_map.json'


def load_historical_entries(path=BASELINE_STATE_PATH):
    state = json.loads(Path(path).read_text(encoding='utf-8'))
    rows = [
        {'chunk_id': row['new_chunk_id'], 'legacy_chunk_id': row['old_chunk_id'],
         'doc_id': row['doc_id'], 'title': row['new_title']}
        for row in state['id_map']
    ]
    rows.extend(
        {'chunk_id': row['chunk_id'], 'legacy_chunk_id': None,
         'doc_id': row['doc_id'], 'title': row['title']}
        for row in state['added']
    )
    return rows


def derive_legacy_id_state(historical_entries, current_entries):
    history_by_doc = defaultdict(list)
    current_by_doc = defaultdict(list)
    for row in historical_entries:
        history_by_doc[row['doc_id']].append(row)
    for row in current_entries:
        current_by_doc[row['doc_id']].append(row)
    id_map, added, removed = [], [], []
    for doc_id in sorted(set(history_by_doc) | set(current_by_doc)):
        history = sorted(history_by_doc[doc_id], key=lambda row: row['chunk_id'])
        current = sorted(current_by_doc[doc_id], key=lambda row: row['chunk_id'])
        history_titles = Counter(row['title'] for row in history)
        matcher = SequenceMatcher(
            a=[row['title'] for row in history],
            b=[row['title'] for row in current], autojunk=False,
        )
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            old_rows, new_rows = history[i1:i2], current[j1:j2]
            if tag == 'replace':
                raise ValueError(f'{doc_id} 标题序列 replace，需人工复核: {old_rows!r} -> {new_rows!r}')
            if tag == 'insert' and any(row['title'] in history_titles for row in new_rows):
                raise ValueError(f'{doc_id} 重复标题新增无法安全派生: {new_rows!r}')
            if tag in {'equal', 'insert'}:
                for offset, new_row in enumerate(new_rows):
                    legacy_id = old_rows[offset]['legacy_chunk_id'] if tag == 'equal' else None
                    id_map.append({
                        'current_chunk_id': new_row['chunk_id'], 'legacy_chunk_id': legacy_id,
                        'doc_id': doc_id, 'title': new_row['title'],
                    })
            if tag == 'insert':
                added.extend(new_rows)
            if tag == 'delete':
                removed.extend(old_rows)
    id_map.sort(key=lambda row: row['current_chunk_id'])
    return {'id_map': id_map, 'added': added, 'removed': removed}


def save_derived_legacy_id_map(current_entries, baseline_path=BASELINE_STATE_PATH,
                               output_path=DERIVED_STATE_PATH):
    history = load_historical_entries(baseline_path)
    result = derive_legacy_id_state(history, current_entries)
    state = {
        'schema_version': 1,
        'baseline_state': 'docs/state/spell_kn244_246_chunk_id_map_20261029.json',
        'baseline_chunks': len(history), 'current_chunks': len(current_entries),
        **result,
    }
    content = json.dumps(state, ensure_ascii=False, indent=2) + '\n'
    output_path = Path(output_path)
    if not output_path.exists() or output_path.read_text(encoding='utf-8') != content:
        output_path.write_text(content, encoding='utf-8')
    return {row['current_chunk_id']: row['legacy_chunk_id'] for row in state['id_map']}


@lru_cache(maxsize=None)
def load_legacy_id_map(path=str(DERIVED_STATE_PATH)):
    state = json.loads(Path(path).read_text(encoding='utf-8'))
    return {row['current_chunk_id']: row['legacy_chunk_id'] for row in state['id_map']}
```

另补重复标题部分删除闭锁：当 `delete` 的历史标题在历史中出现多次且当前仍存在同名时抛出 `ValueError('重复标题删除...')`；全部同名条目删除且当前同名计数为 0 时允许。加载历史/当前后分别断言 chunk_id 全局唯一，重复时抛出含 ID 的 `ValueError`。

- [x] **Step 4: 运行纯对齐测试确认 GREEN**

Run: `cd pf_data/phase1 && python3 -m pytest vectorizer/tests/test_spell_title_cluster.py -k 'derived_legacy_id_map' -q`

Expected: 新增测试全部 PASS。

- [x] **Step 5: 提交独立纯函数改动**

```bash
git add pf_data/phase1/vectorizer/processors/spell_legacy_id_map.py pf_data/phase1/vectorizer/tests/test_spell_title_cluster.py
git commit -m "test(vectorizer): KN249 派生 legacy-id 序列对齐"
```

### Task 2: SpellProcessor 接入并删除手写区间

**Files:**
- Modify: `pf_data/phase1/vectorizer/processors/spell.py:696-749,1088-1090,1141-1151,1477-1481,1864-1879`
- Test: `pf_data/phase1/vectorizer/tests/test_spell_title_cluster.py:209-239`
- Create: `pf_data/phase1/docs/state/spell_kn249_legacy_id_map.json`

- [x] **Step 1: 先改真实 state 对账测试并确认 RED**

将旧 `test_legacy_id_ranges_match_state_map` 改为读取派生 state：每个白名单/裁除旧键若未被删除，必须在 `id_map` 中恰好出现一次；`spell_page_1365_0324` 不得出现。将新增防误挂测试改为遍历派生 state 中 `legacy_chunk_id is None` 的当前行，断言白名单 fallback 为空，并显式断言 `spell_page_1365_0324` 无当前映射。

核心断言：

```python
state = json.loads((PHASE1 / 'docs/state/spell_kn249_legacy_id_map.json').read_text(encoding='utf-8'))
rows = state['id_map']
assert [row for row in rows if row['legacy_chunk_id'] == 'spell_page_1365_0324'] == []
for row in rows:
    if row['legacy_chunk_id'] is None:
        chunk = SimpleNamespace(chunk_id=row['current_chunk_id'], doc_id=row['doc_id'])
        assert SpellProcessor._a_bucket_whitelist_level({'name': row['title']}, chunk) == []
```

Run: `cd pf_data/phase1 && python3 -m pytest vectorizer/tests/test_spell_title_cluster.py -k 'legacy_id or added_chunks' -q`

Expected: FAIL，派生 state 文件不存在，且旧区间仍把顺移 ID 映射到错误旧键。

- [x] **Step 2: 替换查询函数并注入实例映射**

删除 `_SPELL_LEVEL_LEGACY_ID_RANGES`，导入 `DERIVED_STATE_PATH/load_legacy_id_map/save_derived_legacy_id_map`。实现：

```python
def _legacy_spell_chunk_id(chunk_id: str, legacy_id_map=None):
    if legacy_id_map is None:
        legacy_id_map = load_legacy_id_map(str(DERIVED_STATE_PATH))
    if chunk_id in legacy_id_map:
        return legacy_id_map[chunk_id]
    return chunk_id


def _is_cut_exclusion(chunk_id: str, title: str, legacy_id_map=None) -> bool:
    legacy_id = _legacy_spell_chunk_id(chunk_id, legacy_id_map)
    return legacy_id is not None and _SPELL_LEVEL_CUT_EXCLUSION_TITLES.get(legacy_id) == title
```

`SpellProcessor.__init__` 增加 `self._legacy_id_map = None`。`infer_metadata`、`_a_bucket_whitelist_level` 和裁除判断均传 `self._legacy_id_map`；查询 `.get` 前允许 legacy_id 为 `None`，不得回退成当前 ID。

- [x] **Step 3: 在 load_resources 预扫描并派生 state**

新增 `_collect_legacy_id_current_entries(input_dir)`：对 `_spell_file_condition` 接受的文件依次执行与 `FileProcessor.process` 相同的读取、`pre_normalize`、`normalize`、`promote`、`split_into_items(source_name=file.name)`，按枚举序号生成 `spell_<stem>_<idx:04d>`。索引加载成功后追加 `_build_spell_index_chunk()` 的 ID/doc/title，保证基线 4206 对当前 4202，仅 4 条源条目 removed。

`load_resources` 先加载 SpellIndexProvider（移除缺失时的提前 return），再执行：

```python
current_entries = self._collect_legacy_id_current_entries(input_dir)
self._legacy_id_map = save_derived_legacy_id_map(current_entries)
logger.info(
    'KN249 legacy-id 映射已派生: %d 当前条目', len(self._legacy_id_map)
)
```

预扫描或 state 读写失败时让构建明确失败，不回退到手写区间或空映射。

- [x] **Step 4: 生成 state 并运行目标测试**

Run:

```bash
cd pf_data/phase1
python3 - <<'PY'
from pathlib import Path
from vectorizer.processors.spell import SpellProcessor
from vectorizer.sources.providers import SourceResolver
SpellProcessor(SourceResolver([])).load_resources(Path('pf_rules_md_organized/法术'))
PY
python3 -m pytest vectorizer/tests/test_spell_title_cluster.py -q
```

Expected: state `baseline_chunks=4206`、`current_chunks=4202`、`removed=4`、`added=0`；整个 `test_spell_title_cluster.py` PASS。

- [x] **Step 5: 提交 Processor 与派生 state**

```bash
git add pf_data/phase1/vectorizer/processors/spell.py pf_data/phase1/vectorizer/processors/spell_legacy_id_map.py pf_data/phase1/vectorizer/tests/test_spell_title_cluster.py pf_data/phase1/docs/state/spell_kn249_legacy_id_map.json
git commit -m "fix(vectorizer): KN249 白名单 legacy-id 映射派生化"
```

### Task 3: 真实构建、全量回归与销账

**Files:**
- Modify: `pf_data/phase1/docs/已知问题记录.md`
- Modify: `docs/数据一致性技术债务登记.md`
- Modify: `docs/项目文档总索引.md`
- Modify: `docs/superpowers/specs/2026-11-03-kn249-derived-legacy-id-map-design.md`（若实现细节有精确化）

- [x] **Step 1: 固化构建前产物指纹并运行 Spell 统一链**

```bash
cd pf_data/phase1
shasum -a 256 vectorizer/output/法术/chunks.jsonl docs/state/spell_kn249_legacy_id_map.json > /tmp/kn249_before.sha256
python3 -m vectorizer.cicd verify --category spell 2>&1 | tee /tmp/kn249_spell_verify_1.log
```

Expected: 命令退出 0；日志中 `KN242-F1 对账异常` 为 0；chunks 4202、空值 373/4201 保持不变。

- [x] **Step 2: 复跑验证可复现性并做产物对账**

```bash
cd pf_data/phase1
shasum -a 256 vectorizer/output/法术/chunks.jsonl docs/state/spell_kn249_legacy_id_map.json > /tmp/kn249_after_1.sha256
python3 -m vectorizer.cicd verify --category spell 2>&1 | tee /tmp/kn249_spell_verify_2.log
shasum -a 256 vectorizer/output/法术/chunks.jsonl docs/state/spell_kn249_legacy_id_map.json > /tmp/kn249_after_2.sha256
diff -u /tmp/kn249_after_1.sha256 /tmp/kn249_after_2.sha256
python3 -m pytest vectorizer/tests -q
python3 -m vectorizer.build check
```

Expected: 两次指纹 diff 为空；Spell 日志无 KN242-F1 WARN；全量 pytest 和 14 artifact check 全绿。将开工前后 chunks 按 chunk_id 对账，除 chunk_id 顺移导致的行位置外，同 ID 的 text/book/toc/source 不应发生非预期变化；以历史标题序列映射后逐条比较 spell_level，变化必须为 0。

- [x] **Step 3: 更新 KN249、DVG-012 和总索引**

KN249 状态改为已修复，记录派生 state、4 条删除、92→0 WARN、spell_level 零变化、测试命令与实测数量。DVG-012 的遗留段改为 KN249 已清偿；总索引从下一轮候选移除 KN249，并记录最新验证结果。若重复标题闭锁、Spell Index 纳入方式等实现细节超出原设计，同步精确化设计文档，不改变已批准范围。

- [x] **Step 4: 最终检查并提交**

```bash
cd /Users/chezi/code/java/pf_agent
git diff --check
git status --short
git add pf_data/phase1/docs/已知问题记录.md docs/数据一致性技术债务登记.md docs/项目文档总索引.md docs/superpowers/specs/2026-11-03-kn249-derived-legacy-id-map-design.md
git commit -m "docs: KN249 派生映射验收与销账"
```

Expected: 工作区无未提交的 KN249 相关改动；最终报告列出实际测试数量、WARN 清零、可复现指纹和提交号。若标准验证失败，不标记完成，不通过修改业务断言或调宽闸口掩盖问题。
