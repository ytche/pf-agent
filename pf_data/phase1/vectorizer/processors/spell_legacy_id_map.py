"""按历史条目序列派生 Spell 当前 chunk_id 到白名单 legacy-id 的映射。"""

import json
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

PHASE1 = Path(__file__).resolve().parents[2]
BASELINE_STATE_PATH = PHASE1 / "docs/state/spell_kn244_246_chunk_id_map_20261029.json"
DERIVED_STATE_PATH = PHASE1 / "docs/state/spell_kn249_legacy_id_map.json"


def load_historical_entries(path=BASELINE_STATE_PATH):
    state = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = [
        {
            "chunk_id": row["new_chunk_id"],
            "legacy_chunk_id": row["old_chunk_id"],
            "doc_id": row["doc_id"],
            "title": row["new_title"],
        }
        for row in state["id_map"]
    ]
    rows.extend(
        {
            "chunk_id": row["chunk_id"],
            "legacy_chunk_id": None,
            "doc_id": row["doc_id"],
            "title": row["title"],
        }
        for row in state["added"]
    )
    return rows


def _assert_unique_chunk_ids(rows, source_name):
    counts = Counter(row["chunk_id"] for row in rows)
    duplicates = sorted(chunk_id for chunk_id, count in counts.items() if count > 1)
    if duplicates:
        raise ValueError(f"{source_name} chunk_id 重复: {duplicates}")


def derive_legacy_id_state(historical_entries, current_entries):
    historical_entries = list(historical_entries)
    current_entries = list(current_entries)
    _assert_unique_chunk_ids(historical_entries, "历史条目")
    _assert_unique_chunk_ids(current_entries, "当前条目")

    history_by_doc = defaultdict(list)
    current_by_doc = defaultdict(list)
    for row in historical_entries:
        history_by_doc[row["doc_id"]].append(row)
    for row in current_entries:
        current_by_doc[row["doc_id"]].append(row)

    id_map, added, removed = [], [], []
    for doc_id in sorted(set(history_by_doc) | set(current_by_doc)):
        history = sorted(history_by_doc[doc_id], key=lambda row: row["chunk_id"])
        current = sorted(current_by_doc[doc_id], key=lambda row: row["chunk_id"])
        history_titles = Counter(row["title"] for row in history)
        current_titles = Counter(row["title"] for row in current)
        matcher = SequenceMatcher(
            a=[row["title"] for row in history],
            b=[row["title"] for row in current],
            autojunk=False,
        )
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            old_rows, new_rows = history[i1:i2], current[j1:j2]
            if tag == "replace":
                raise ValueError(
                    f"{doc_id} 标题序列 replace，需人工复核: {old_rows!r} -> {new_rows!r}"
                )
            if tag == "insert" and any(row["title"] in history_titles for row in new_rows):
                raise ValueError(f"{doc_id} 重复标题新增无法安全派生: {new_rows!r}")
            if tag == "delete" and any(
                history_titles[row["title"]] > 1 and current_titles[row["title"]] > 0
                for row in old_rows
            ):
                raise ValueError(f"{doc_id} 重复标题删除无法安全派生: {old_rows!r}")
            if tag in {"equal", "insert"}:
                for offset, new_row in enumerate(new_rows):
                    legacy_id = old_rows[offset]["legacy_chunk_id"] if tag == "equal" else None
                    id_map.append({
                        "current_chunk_id": new_row["chunk_id"],
                        "legacy_chunk_id": legacy_id,
                        "doc_id": doc_id,
                        "title": new_row["title"],
                    })
            if tag == "insert":
                added.extend(new_rows)
            if tag == "delete":
                removed.extend(old_rows)

    id_map.sort(key=lambda row: row["current_chunk_id"])
    return {"id_map": id_map, "added": added, "removed": removed}


def save_derived_legacy_id_map(
    current_entries,
    baseline_path=BASELINE_STATE_PATH,
    output_path=DERIVED_STATE_PATH,
):
    current_entries = list(current_entries)
    history = load_historical_entries(baseline_path)
    result = derive_legacy_id_state(history, current_entries)
    state = {
        "schema_version": 1,
        "baseline_state": "docs/state/spell_kn244_246_chunk_id_map_20261029.json",
        "baseline_chunks": len(history),
        "current_chunks": len(current_entries),
        **result,
    }
    content = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    output_path = Path(output_path)
    if not output_path.exists() or output_path.read_text(encoding="utf-8") != content:
        output_path.write_text(content, encoding="utf-8")
    return {row["current_chunk_id"]: row["legacy_chunk_id"] for row in state["id_map"]}


@lru_cache(maxsize=None)
def load_legacy_id_map(path=str(DERIVED_STATE_PATH)):
    state = json.loads(Path(path).read_text(encoding="utf-8"))
    return {row["current_chunk_id"]: row["legacy_chunk_id"] for row in state["id_map"]}
