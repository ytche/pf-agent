#!/usr/bin/env python3
# ⚠️ SUPERSEDED（2026-09-01 · CP3）
# 本脚本逻辑已收敛进 vectorizer/verify/verify_profession.py（VerifyBase 八检查，
# cicd/verify.py profession 类目唯一验收入口）。保留仅作历史参考，不再在 cicd
# 调用；如需复跑请用 `python3 -m vectorizer.verify.verify_profession`。
"""V003 negative test：汲毒巫（Venom Siphoner）变体信息完整且归属正确。"""
import json
import re
import sys

CHUNKS_PATH = "vectorization_prep_profession/chunks.jsonl"

EXPECTED_ARCHETYPES = [
    "汲毒巫（Venom Siphoner）",
    "汲毒巫（Venom Siphoner）［女巫变体］",
]

EXPECTED_FEATURES = {
    "毒物魔宠",
    "毒液专家",
    "毒性血液",
}


def main() -> int:
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f if line.strip()]

    ok = True

    # 1. 检查 archetype chunk 完整且未被截断
    arch_chunks = [
        c
        for c in chunks
        if c.get("component_type") == "class_archetype"
        and "汲毒巫" in c.get("title", "")
    ]
    if not arch_chunks:
        print("FAIL: 缺少汲毒巫 class_archetype chunk")
        ok = False
    else:
        for c in arch_chunks:
            title = c.get("title", "")
            text = c.get("text", "")
            if not text:
                print(f"FAIL: {title} 的 archetype chunk 为空")
                ok = False
                continue
            if text.rstrip().endswith("该能力取代了1级时获得的"):
                print(f"FAIL: {title} 的 archetype chunk 被截断")
                ok = False
            # 边界漂移检查：archetype chunk 不应以珊瑚女巫的推荐巫术列表开头
            if re.search(r"^(> 来源：[^\n]+\n+)?(?:兽眸|赐命|邪眼|野嚎|水息)", text.strip()):
                print(f"FAIL: {title} 的 archetype chunk 混入了前段推荐巫术文本")
                ok = False
            if "汲毒巫" not in text:
                print(f"FAIL: {title} 的 archetype chunk 缺少变体介绍")
                ok = False

    # 2. 检查三个职业能力作为独立 class_feature chunk，且归属汲毒巫
    found_features = {}
    for c in chunks:
        if c.get("component_type") != "class_feature":
            continue
        if c.get("archetype_name") != "汲毒巫":
            continue
        title = c.get("title", "")
        cn = title.split("（")[0].strip()
        if cn in EXPECTED_FEATURES:
            found_features[cn] = title

    missing = EXPECTED_FEATURES - set(found_features)
    if missing:
        print(f"FAIL: 缺少归属汲毒巫的职业能力 chunk：{sorted(missing)}")
        ok = False

    # 3. 检查 Hex 文件 overview 不再包含错置的职业能力描述
    hex_overview_texts = []
    for c in chunks:
        if (
            c.get("class_name") == "女巫"
            and c.get("component_type") == "class_feature"
            and c.get("title", "").startswith("巫术（Hexes）")
            and "P&P" in c.get("doc_id", "")
        ):
            hex_overview_texts.append(c.get("text", ""))

    misplaced = []
    for keyword in ("毒液专家", "毒性血液"):
        for text in hex_overview_texts:
            if keyword in text:
                misplaced.append(keyword)
                break
    if misplaced:
        print(f"FAIL: Hex 章节 overview 仍错置职业能力：{misplaced}")
        ok = False

    if ok:
        print("PASS: 汲毒巫变体 chunk 完整，职业能力归属正确，无错置。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
