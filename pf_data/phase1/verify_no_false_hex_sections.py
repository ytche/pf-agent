#!/usr/bin/env python3
# ⚠️ SUPERSEDED（2026-09-01 · CP3）
# 本脚本逻辑已收敛进 vectorizer/verify/verify_profession.py（VerifyBase 八检查，
# cicd/verify.py profession 类目唯一验收入口）。保留仅作历史参考，不再在 cicd
# 调用；如需复跑请用 `python3 -m vectorizer.verify.verify_profession`。
"""V002 negative test：通用巫术章节标题不应被标为 hex/major_hex/grand_hex，
且关键具体巫术必须作为独立 class_feature chunk 出现。
"""
import json
import re
import sys

CHUNKS_PATH = "vectorization_prep_profession/chunks.jsonl"

# 1. 通用章节标题白名单：这些标题是节标题，不是具体巫术
FALSE_PATTERNS = [
    r"强力巫术\s*[（(]\s*Major\s+Hexes\s*[）)]",
    r"高等巫术\s*[（(]\s*Grand\s+Hexes\s*[）)]",
    r"^巫术\s*[（(]\s*Hexes\s*[）)]$",
]

# 2. P&P 中应独立出现的具体巫术（按中文短名匹配）
EXPECTED_HEXES = {
    "折耗之礼",
    "高等折耗之礼",
    "毒药之触",
    "不安沉眠",
    "凋零",
}


def main() -> int:
    false_errors = []
    found_hexes = set()

    with open(CHUNKS_PATH, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            c = json.loads(line)

            if c.get("feature_subtype") in ("hex", "major_hex", "grand_hex"):
                title = c.get("title", "")
                if any(re.search(p, title, re.IGNORECASE) for p in FALSE_PATTERNS):
                    false_errors.append(
                        f"  {title} [{c.get('doc_id')}] -> {c.get('feature_subtype')}"
                    )

            if c.get("class_name") == "女巫" and c.get("component_type") == "class_feature":
                title = c.get("title", "")
                cn = title.split("（")[0].strip()
                if cn in EXPECTED_HEXES:
                    found_hexes.add(cn)

    ok = True
    if false_errors:
        print("FAIL: 以下通用章节标题被误识别为具体巫术：")
        for e in false_errors:
            print(e)
        ok = False
    else:
        print("PASS: 未发现通用章节标题被误识别为具体巫术。")

    missing = EXPECTED_HEXES - found_hexes
    if missing:
        print(f"FAIL: 缺失 {len(missing)} 个应独立成 chunk 的巫术：{sorted(missing)}")
        ok = False
    else:
        print(f"PASS: {len(EXPECTED_HEXES)} 个 P&P 巫术均已独立成 chunk。")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
