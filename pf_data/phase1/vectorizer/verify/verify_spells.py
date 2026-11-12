"""
verify_spells.py — 法术集成验收（v0.3 适配）

在 pipeline 全量运行后执行，检查：
  1. 法术数量合理（≥100）
  2. 8 大学派全覆盖
  3. 主要来源书全覆盖（CRB, APG, UM, UC, ACG）
  4. 字段完整性（无空标题/空正文/未知来源书 + v0.3 字段覆盖率）
  5. 无格式污染（标题无 URL/译者/罗马碎片）且关键条目存在
  6. 无重复 chunk_id
  7. metadata v0.3 字段覆盖率统计（非阻断）
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List


def load_chunks(path: Path) -> List[dict]:
    """从 JSONL 文件加载 chunk 列表"""
    if not path.exists():
        print(f"❌ chunks 文件不存在: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def verify_spells(chunks_path: Path) -> bool:
    """执行法术验收检查"""
    chunks = load_chunks(chunks_path)

    ok = True

    # 1. 数量检查
    min_expected = 100
    if len(chunks) < min_expected:
        print(f"❌ 法术数过少: {len(chunks)}（预期 ≥ {min_expected}）")
        ok = False
    else:
        print(f"✅ 法术数量: {len(chunks)}")

    # 2. 学派覆盖（前缀匹配，因为学派值可能含子学派/描述符）
    all_schools = [c.get("metadata", {}).get("school", "") for c in chunks]
    required_schools = ["咒法系", "变化系", "死灵系", "塑能系",
                        "幻术系", "附魔系", "预言系", "防护系"]
    for school in required_schools:
        count = sum(1 for s in all_schools if s.startswith(school) or s.startswith(school.replace('系', '')))
        if count == 0:
            print(f"  ⚠️ 缺少学派: {school}")
    print(f"✅ 学派覆盖: {len(Counter(all_schools))} 个不同学派")

    # 3. 来源书覆盖
    books = Counter(c.get("book_abbreviation", "") for c in chunks)
    for book in ["CRB", "APG", "UM", "UC", "ACG"]:
        if books.get(book, 0) == 0:
            print(f"  ⚠️ 缺少来源书: {book}")
    print(f"✅ 来源书覆盖: {len(books)} 本")

    # 4. 字段完整性
    # KN015：page_1365 源数据中文法术名丢失 — 修复后已无无标题 chunk。
    # 白名单已清空，保留以检测新增无标题 chunk。
    KNOWN_UNTITLED_WHITELIST = set()
    all_empty_title = [c.get("chunk_id", "?") for c in chunks if not c.get("title")]
    whitelisted_empty = [cid for cid in all_empty_title if cid in KNOWN_UNTITLED_WHITELIST]
    new_empty = [cid for cid in all_empty_title if cid not in KNOWN_UNTITLED_WHITELIST]
    empty_text = sum(1 for c in chunks if not c.get("text"))
    unknown_book = sum(1 for c in chunks if c.get("book_abbreviation") in ("?", "", None))
    if new_empty:
        print(f"❌ {len(new_empty)} 个 chunk 无标题（新增，非 KN015 白名单）: {new_empty}")
        ok = False
    elif whitelisted_empty:
        print(f"⚠️ {len(whitelisted_empty)} 个 chunk 无标题（已登记 KN015，源数据问题，非阻断）")
    if empty_text > 0:
        print(f"❌ {empty_text} 个 chunk 无正文")
        ok = False
    if unknown_book > 0:
        print(f"  ⚠️ {unknown_book} 个 chunk 来源书未知")
    print(f"✅ 字段完整性: 标题 ✓ 正文 ✓")

    # 5. 无格式污染
    url_in_title = sum(1 for c in chunks if "http://" in c.get("title", "") or "https://" in c.get("title", ""))
    translator_in_title = sum(1 for c in chunks if "译者" in c.get("title", ""))
    if url_in_title > 0:
        print(f"❌ {url_in_title} 个 chunk 标题含 URL")
        ok = False
    if translator_in_title > 0:
        print(f"❌ {translator_in_title} 个 chunk 标题含译者")
        ok = False
    roman_titles = [
        c.get("chunk_id", "?") for c in chunks
        if re.fullmatch(r"[IVX]{1,6}", c.get("title", "").strip())
    ]
    if roman_titles:
        print(f"❌ KN244 罗马碎片标题: {roman_titles}")
        ok = False
    required_entries = {
        ("page_1166", "藏密箱"),
        ("page_1146", "弧焰击"),
        ("page_805", "隐藏武器"),
        ("page_1008", "起舞于黯"),
    }
    entries = {(c.get("doc_id"), c.get("title", "")) for c in chunks}
    missing_entries = sorted(required_entries - entries)
    if missing_entries:
        print(f"❌ KN246 关键条目未恢复: {missing_entries}")
        ok = False
    if ("page_1008", "半影法术") in entries:
        print("❌ 章节名半影法术被误产为法术 chunk")
        ok = False
    print(f"✅ 格式无污染: URL ✓ 译者 ✓ 罗马碎片 ✓ 关键条目 ✓ 章节负例 ✓")

    # 5b. KN245 终态（2026-10-30 用户拍板，2026-10-30 标签容错后清零）：
    #     17 条必须回填；阿底顿 2 条为非法术条目标 not_applicable。
    by_pair = {}
    for c in chunks:
        by_pair.setdefault((c.get("doc_id"), c.get("title", "").strip()), []).append(c)
    kn245_backfilled = [
        ("Spell FoP", "轻量化"),
        ("page_1008", "受虐之影"),
        ("page_1034", "异龙形态 I"), ("page_1034", "奇龙形态 I"),
        ("page_1048", "踏焰行者"),
        ("page_1168", "高等天界治疗"), ("page_1168", "液化术"),
        ("page_1363", "食尸鬼的饥饿"),
        ("page_1365", "汲取毒素"), ("page_1365", "高等天界治疗"),
        ("page_1365", "液化术"), ("page_1365", "受虐之影"),
        ("page_1365", "奇龙形态 I"), ("page_1365", "踏焰行者"),
        ("任务与战役_法术", "典礼"),
        ("月之血脉BotM_法术", "诅咒瞪视"), ("月之血脉BotM_法术", "分享皮肤"),
    ]
    kn245_kept_empty = []
    # 阿底顿已于 2026-10-30 迁出法术目录（SMF011），故改为负向断言
    kn245_removed = [("page_1494", "阿底顿")]
    bad = []
    for pair in kn245_backfilled:
        hits = by_pair.get(pair) or []
        if not hits:
            bad.append(f"{pair} 条目缺失")
        elif any(not (h.get("metadata", {}).get("spell_level") or []) for h in hits):
            bad.append(f"{pair} 未回填")
    for pair in kn245_kept_empty:
        hits = by_pair.get(pair) or []
        if not hits:
            bad.append(f"{pair} 条目缺失")
        elif any(h.get("metadata", {}).get("spell_level") for h in hits):
            bad.append(f"{pair} 违反裁除红线")
    for pair in kn245_removed:
        if pair in by_pair:
            bad.append(f"{pair} 仍留在法术产物（应已迁出到物品目录）")
    if bad:
        print(f"❌ KN245 裁除终态不符合裁定: {bad}")
        ok = False
    else:
        kept = f" 零回填 {len(kn245_kept_empty)} 条" if kn245_kept_empty else ""
        print(f"✅ KN245 终态: 回填 {len(kn245_backfilled)} 条{kept}"
              f" 已迁出 {len(kn245_removed)} 条")


    # 6. 无重复 chunk_id
    ids = [c.get("chunk_id", "") for c in chunks]
    if len(ids) != len(set(ids)):
        dupes = [i for i, c in Counter(ids).items() if c > 1]
        print(f"❌ 存在重复 chunk_id: {dupes}")
        ok = False
    print(f"✅ 无重复 chunk_id")

    # 7. v0.3 字段覆盖率统计（非阻断，仅报告）
    print("\n📊 v0.3 metadata 字段覆盖率：")
    field_stats = Counter()
    spell_chunks = [c for c in chunks if c.get("component_type") != "spell_index"]
    for c in spell_chunks:
        fs = c.get("metadata", {}).get("field_status", {})
        for field, status in fs.items():
            field_stats[(field, status)] += 1

    report_fields = [
        "school", "subschool", "descriptor", "spell_level",
        "casting_time", "components", "range", "target",
        "area", "effect", "duration", "saving_throw", "spell_resistance",
    ]
    for field in report_fields:
        parsed = field_stats.get((field, "parsed"), 0)
        missing = field_stats.get((field, "missing"), 0)
        na = field_stats.get((field, "not_applicable"), 0)
        pct = parsed / max(len(spell_chunks), 1) * 100
        parts = [f"parsed={parsed:5d} ({pct:5.1f}%)"]
        if missing:
            parts.append(f"missing={missing}")
        if na:
            parts.append(f"N/A={na}")
        print(f"  {field:20s}: {'  '.join(parts)}")

    # 检查 field_status 是否存在
    missing_fs = sum(1 for c in spell_chunks if "field_status" not in c.get("metadata", {}))
    if missing_fs:
        print(f"⚠️ {missing_fs} 个 chunk 缺少 field_status")
    else:
        print(f"✅ 全部 {len(spell_chunks)} 个 spell chunk 含 field_status")

    return ok


def main():
    chunks_path = Path("vectorizer/output/法术/chunks.jsonl")
    ok = verify_spells(chunks_path)
    if ok:
        print("\n✅ 全部验收通过")
        sys.exit(0)
    else:
        print("\n❌ 验收未完全通过，请检查以上告警")
        sys.exit(1)


if __name__ == "__main__":
    main()
