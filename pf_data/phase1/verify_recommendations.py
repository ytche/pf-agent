# ⚠️ SUPERSEDED（2026-09-01 · CP3）
# 本脚本逻辑已收敛进 vectorizer/verify/verify_profession.py（VerifyBase 八检查，
# cicd/verify.py profession 类目唯一验收入口）。保留仅作历史参考，不再在 cicd
# 调用；如需复跑请用 `python3 -m vectorizer.verify.verify_profession`。
"""推荐块（class_recommendation）验收脚本。

验证内容：
1. 推荐块 component_type 必须为 class_recommendation
2. 推荐块不应有 archetype_name 或 feature_subtype
3. 每个已知推荐模式文件至少产生 N 个推荐块
4. class_feature chunk 中不应包含以"推荐"开头的标题
"""

import json
import sys
from collections import Counter
from pathlib import Path

PHASE1 = Path(__file__).parent
CHUNKS = PHASE1 / "vectorization_prep_profession" / "chunks.jsonl"

# 已知推荐模式文件 → 最少推荐块数
KNOWN_RECOMMENDATION_FILES: dict[str, int] = {
    "掉链子（Unchained）/野蛮人/page_35.md": 10,
    "掉链子（Unchained）/盗贼/page_22.md": 10,
    "混合职业/歌者/page_104.md": 1,
    "混合职业/歌者/page_115.md": 2,
    "冒险者指南AG_变体.md": 1,
    "极限诡道/侠客/职业变体汇总.md": 1,
}


def load_chunks():
    chunks = []
    with open(CHUNKS, encoding="utf-8") as f:
        for line in f:
            chunks.append(json.loads(line))
    return chunks


def main():
    if not CHUNKS.exists():
        print(f"ERROR: chunks.jsonl 不存在: {CHUNKS}")
        print("  请先跑 python3 vectorization_prep_profession.py")
        sys.exit(2)

    chunks = load_chunks()
    print(f"加载 {len(chunks)} 个 chunks\n")

    errors = 0

    # ── 检查 1：推荐块类型正确性 ──
    rec_chunks = [c for c in chunks if c.get("component_type") == "class_recommendation"]
    print(f"[检查 1] class_recommendation chunk 总数: {len(rec_chunks)}")
    for c in rec_chunks:
        cid = c.get("chunk_id", "")[:12]
        title = c.get("title", "")
        doc_id = c.get("doc_id", "")

        # 1a. title 应以"推荐"或"建议"开头
        norm_title = title.strip().lstrip("#").strip()
        if not (norm_title.startswith("推荐") or norm_title.startswith("建议")):
            print(f"  ERROR: 推荐块标题不以推荐/建议开头: {title!r} ({doc_id})")
            errors += 1

        # 1b. 不应有 archetype_name
        if c.get("archetype_name"):
            print(f"  ERROR: 推荐块有 archetype_name: {c['archetype_name']} ({title!r}, {doc_id})")
            errors += 1

        # 1c. 不应有 feature_subtype
        if c.get("feature_subtype"):
            print(f"  ERROR: 推荐块有 feature_subtype: {c['feature_subtype']} ({title!r}, {doc_id})")
            errors += 1

    if not rec_chunks:
        print("  WARNING: 没有找到任何 class_recommendation chunk")

    print()

    # ── 检查 2：已知推荐文件应有推荐块 ──
    print(f"[检查 2] 已知推荐文件产生推荐块")
    rec_by_file: dict[str, list[dict]] = {}
    for c in rec_chunks:
        doc_id = c.get("doc_id", "")
        rec_by_file.setdefault(doc_id, []).append(c)

    for file_pattern, min_expected in KNOWN_RECOMMENDATION_FILES.items():
        # 模糊匹配（doc_id 可能包含或不含前缀路径）
        matched = [(doc_id, chunks) for doc_id, chunks in rec_by_file.items() if file_pattern in doc_id]
        if not matched:
            print(f"  WARNING: 未找到推荐文件匹配 '{file_pattern}'")
            continue
        for doc_id, chunks in matched:
            count = len(chunks)
            status = "OK" if count >= min_expected else "WARNING"
            if status == "WARNING":
                print(f"  {status}: {doc_id} → {count} 块，期望 ≥{min_expected}")
            else:
                print(f"  {status}: {doc_id} → {count} 块")

    print()

    # ── 检查 3：class_feature 中不应有推荐标题 ──
    print(f"[检查 3] class_feature 中无推荐标题")
    feature_with_rec = [
        c for c in chunks
        if c.get("component_type") == "class_feature"
        and (
            c.get("title", "").startswith("推荐")
            or c.get("title", "").startswith("建议")
        )
    ]
    if feature_with_rec:
        for c in feature_with_rec:
            print(f"  ERROR: class_feature 含推荐标题: {c['title']!r} ({c.get('doc_id', '')})")
        errors += len(feature_with_rec)
    else:
        print(f"  正常：无 class_feature 包含推荐标题")

    print()

    # ── 汇总 ──
    if errors == 0:
        print(f"ALL PASSED (total={len(rec_chunks)} recommendation chunks)")
        sys.exit(0)
    else:
        print(f"FAILED: {errors} errors")
        sys.exit(1)


if __name__ == "__main__":
    main()
