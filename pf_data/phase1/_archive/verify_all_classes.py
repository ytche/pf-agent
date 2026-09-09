"""全职业变体识别验收脚本。

加载 `expected_variants/<职业>.json`，与 `vectorization_prep_profession/chunks.jsonl`
中实际产出的 `class_archetype` chunk 对比，逐职业输出：
    OK / WRONG（来源书不符） / MISSING（expected 未出现） / EXTRA（非 expected 的变体）

匹配规则（复用并泛化 `verify_paladin_archetypes.py` 的规范化逻辑）：
- 从 chunk title / archetype_name 去掉各类变体标记后缀；
- 取前导连续中文字符作为规范名；
- 与 expected key 等值比较，避免子串误匹配。
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


PHASE1 = Path(__file__).parent
CHUNKS = PHASE1 / "vectorization_prep_profession" / "chunks.jsonl"
EXPECTED_DIR = PHASE1 / "expected_variants"

# 职业名别名：chunk 中的 class_name 可能与 expected 文件名不同
CLASS_ALIASES = {
    "圣骑士": ["圣骑士", "圣武士"],
}


def load_chunks():
    chunks = []
    with open(CHUNKS, encoding="utf-8") as f:
        for line in f:
            chunks.append(json.loads(line))
    return chunks


def _canonical_name(name: str) -> str:
    """去掉变体标记与英文括号后，取前导连续中文字符。"""
    if not name:
        return ""
    n = name
    # 各类变体标记：【X变体】、（X变体）、〔X变体〕、［X变体］
    for pat in [
        r"【[^】]*变体[^】]*】",
        r"[（(][^）)]*变体[^）)]*[）)]",
        r"〔[^〕]*变体[^〕]*〕",
        r"［[^］]*变体[^］]*］",
        # 英文变体标记
        r"\(.*?\s*[Aa]rchetype\s*\)",
        r"\(.*?\s*[Aa]lternate\s+Class\s*\)",
    ]:
        n = re.sub(pat, "", n).strip()
    m = re.search(r"^[一-鿿]+", n)
    return m.group(0) if m else n.strip()


def _class_names_for(expected_class: str) -> list[str]:
    return CLASS_ALIASES.get(expected_class, [expected_class])


def verify_class(class_name: str, expected: dict, chunks: list[dict]):
    """对单个职业返回 (ok, wrong, missing, extra)。"""
    ok, wrong, missing, extra = [], [], [], []
    class_names = _class_names_for(class_name)
    archetype_chunks = [
        c for c in chunks
        if c.get("component_type") == "class_archetype"
        and c.get("class_name") in class_names
    ]
    got_map = defaultdict(list)  # canonical_name -> [(title, abbr), ...]
    for c in archetype_chunks:
        raw = (c.get("archetype_name") or c.get("title") or "").strip()
        can = _canonical_name(raw)
        if not can:
            continue
        got_map[can].append({
            "title": c.get("title", ""),
            "archetype_name": c.get("archetype_name", ""),
            "abbr": c.get("book_abbreviation", ""),
            "doc_id": c.get("doc_id", ""),
        })

    for exp_name, exp_abbr in expected.items():
        matches = got_map.get(exp_name, [])
        if not matches:
            missing.append(exp_name)
            continue
        # 只要有一条来源正确即算 OK（同一变体可能多文件重复）
        if any(m["abbr"] == exp_abbr for m in matches):
            ok.append(exp_name)
        else:
            wrong.append((exp_name, exp_abbr, matches[0]["abbr"], matches[0]))

    # extra：实际出现但不在 expected 中的变体（规范化后）
    expected_names = set(expected.keys())
    for can, matches in got_map.items():
        if can not in expected_names:
            extra.append((can, matches[0]))

    return ok, wrong, missing, extra


def main():
    if not CHUNKS.exists():
        print(f"ERROR: chunks.jsonl 不存在: {CHUNKS}")
        print("  请先跑 python3 vectorization_prep_profession.py")
        sys.exit(2)

    chunks = load_chunks()
    print(f"加载 {len(chunks)} 个 chunks\n")

    json_files = sorted(EXPECTED_DIR.glob("*.json"))
    total_ok = total_wrong = total_missing = total_extra = 0
    fail_classes = []

    for jf in json_files:
        class_name = jf.stem
        expected = json.loads(jf.read_text(encoding="utf-8"))
        if not expected:
            continue
        ok, wrong, missing, extra = verify_class(class_name, expected, chunks)
        total_ok += len(ok)
        total_wrong += len(wrong)
        total_missing += len(missing)
        total_extra += len(extra)
        status = "PASS" if not wrong and not missing else "FAIL"
        if wrong or missing or extra:
            fail_classes.append(class_name)
        print(f"[{status}] {class_name}: OK={len(ok)} WRONG={len(wrong)} "
              f"MISSING={len(missing)} EXTRA={len(extra)}")
        if wrong:
            for name, exp, got, m in wrong:
                print(f"  WRONG: {name} 应为 {exp}，实际 {got} "
                      f"(title={m['title'][:50]!r})")
        if missing:
            for name in missing:
                print(f"  MISSING: {name}")
        if extra:
            for name, m in extra:
                print(f"  EXTRA: {name} (title={m['title'][:50]!r}, abbr={m['abbr']})")

    print(f"\n汇总: OK={total_ok} WRONG={total_wrong} MISSING={total_missing} EXTRA={total_extra}")
    if total_wrong == 0 and total_missing == 0:
        print("ALL PASSED")
        sys.exit(0)
    else:
        print(f"FAILED 职业: {', '.join(fail_classes)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
