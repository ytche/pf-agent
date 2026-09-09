#!/usr/bin/env python3
# ⚠️ SUPERSEDED（2026-09-01 · CP3）
# 本脚本逻辑已收敛进 vectorizer/verify/verify_profession.py（VerifyBase 八检查，
# cicd/verify.py profession 类目唯一验收入口）。保留仅作历史参考，不再在 cicd
# 调用；如需复跑请用 `python3 -m vectorizer.verify.verify_profession`。
# -*- coding: utf-8 -*-
"""职业 chunk 归属验收脚本。

验证 `vectorization_prep_profession/chunks.jsonl` 中的结构不变量，
含未知职业数量、正向 spot check、negative check、回归测试与 before/after 对照。
"""

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
CHUNKS_PATH = _HERE / "vectorization_prep_profession" / "chunks.jsonl"
BASELINE_PATH = _HERE / "baselines" / "profession_chunk_baseline.json"

# 删除的 11 个神话冒险根层重复副本，其 doc_id 不应再出现
DELETED_DOC_IDS = {
    "神话冒险/page_610.md",
    "神话冒险/page_613.md",
    "神话冒险/page_614.md",
    "神话冒险/page_615.md",
    "神话冒险/page_616.md",
    "神话冒险/page_617.md",
    "神话冒险/page_618.md",
    "神话冒险/page_619.md",
    "神话冒险/page_620.md",
    "神话冒险/凡人神使.md",
    "神话冒险/神眷道途能力.md",
}

# 不应作为 class_name 出现的来源书/目录名（CONTAINER_SELF_ATTRIBUTION 例外：神话冒险）
SOURCE_BOOK_CLASS_NAMES = {
    "APG进阶职业",
    "CRB进阶职业",
    "PoP进阶之路",
    "ISG内海诸神",
    "异能冒险（Occult Adventures）",
    "极限荒野（Ultimate Wilderness）",
    "其他职业",
    # "神话冒险" 是 CONTAINER_SELF_ATTRIBUTION 的合法 class_name，单独处理
}

# 单一进阶职业 page 文件（进阶职业/<来源书>/page_xxx.md）的 doc_id 模式
SINGLE_PRESTIGE_PAGE_RE = re.compile(r"^进阶职业/.+/page_\d+\.md$")

# 正向 spot check 规则
SPOT_CHECKS = [
    ("操念使/ 目录下所有 chunk", "操念使", lambda c: "/操念使/" in c["doc_id"]),
    ("异能者/ 目录下所有 chunk", "异能者", lambda c: "/异能者/" in c["doc_id"]),
    ("唤魂师/ 目录下所有 chunk", "唤魂师", lambda c: "/唤魂师/" in c["doc_id"]),
    ("变形者/ 目录下所有 chunk", "变形者", lambda c: "/变形者/" in c["doc_id"]),
    ("导魂者/ 目录下所有 chunk", "导魂者", lambda c: "/导魂者/" in c["doc_id"]),
    (
        "进阶职业/APG进阶职业/page_145.md",
        "间谍大师",
        lambda c: "进阶职业/APG进阶职业/page_145.md" in c["doc_id"],
    ),
    (
        "进阶职业/PoP进阶之路/page_784.md",
        "贵族后裔",
        lambda c: "进阶职业/PoP进阶之路/page_784.md" in c["doc_id"],
    ),
    (
        "进阶职业/CRB进阶职业/龙脉术士/",
        "龙脉术士",
        lambda c: "进阶职业/CRB进阶职业/龙脉术士/" in c["doc_id"],
    ),
    (
        "神话冒险/圣者/page_617.md",
        "圣者",
        lambda c: "神话冒险/圣者/page_617.md" in c["doc_id"],
    ),
    (
        "神话冒险/斗士/page_615.md",
        "斗士",
        lambda c: "神话冒险/斗士/page_615.md" in c["doc_id"],
    ),
]

# 未知职业数量阈值。
# 依据：k2.7 职业 chunk 质量攻坚 Phase A Step 4 要求未知职业 ≤ 150。
# 该阈值相对于当前基线（unknown=1597）是激进目标，用于防止归属规则回退。
UNKNOWN_THRESHOLD = 150


def load_chunks(path: Path):
    chunks = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def run_regression(script: str, expected_marker: str) -> bool:
    print(f"\n[回归] 运行 {script} ...")
    try:
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except FileNotFoundError:
        print(f"  FAIL: 找不到脚本 {script}")
        return False
    output = result.stdout + result.stderr
    if result.returncode != 0:
        print(f"  FAIL: 脚本返回非零退出码 {result.returncode}")
        print(output[-2000:])
        return False
    if expected_marker not in output:
        print(f"  FAIL: 输出中未找到 '{expected_marker}'")
        print(output[-2000:])
        return False
    print(f"  PASS: {script} 输出包含 '{expected_marker}'")
    return True


def main() -> int:
    if not CHUNKS_PATH.exists():
        print(f"FAIL: 找不到 {CHUNKS_PATH}")
        return 1

    chunks = load_chunks(CHUNKS_PATH)
    total = len(chunks)
    print(f"加载 {total} 个 chunks")

    overall_pass = True

    # ---------- 不变量 5：before/after 对照（先算 after，也作为后续不变量的输入） ----------
    class_counter = Counter(c["class_name"] for c in chunks)
    unknown_count = class_counter["未知职业"]
    top20 = class_counter.most_common(20)

    print("\n===== before/after 对照 =====")
    if BASELINE_PATH.exists():
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        print(f"before total : {baseline['total']}")
        print(f"after  total : {total}")
        print(f"before unknown: {baseline['unknown']}")
        print(f"after  unknown: {unknown_count}")
        print("\nTop20 after:")
        for name, cnt in top20:
            print(f"  {name}: {cnt}")
        # 逃生舱：总数骤降数千视为异常
        if total < baseline["total"] - 3000:
            print(f"\nFAIL: total 骤降 {baseline['total'] - total}，触发逃生舱")
            overall_pass = False
        # handover 文档预期：删除重复副本后 total 基本不变或下降约 370；
        # 若实际上升，提示调查基线是否陈旧或输入文件是否有新增。
        if total > baseline["total"]:
            print("\n注意：total 变化与 handover 文档预期不同，建议调查输入文件或基线陈旧性")
    else:
        print(f"未找到 baseline 文件 {BASELINE_PATH}，跳过 before 对照")
        print(f"after total : {total}")
        print(f"after unknown: {unknown_count}")

    # ---------- 不变量 1：未知职业数量 ----------
    print("\n===== 不变量 1：未知职业数量 =====")
    unknown_chunks = [c for c in chunks if c["class_name"] == "未知职业"]
    print(f"未知职业 chunk 数量: {len(unknown_chunks)} (阈值 {UNKNOWN_THRESHOLD})")
    for c in unknown_chunks:
        print(f"  {c['doc_id']} | {c['title']}")
    if len(unknown_chunks) > UNKNOWN_THRESHOLD:
        print(f"FAIL: 未知职业数量 {len(unknown_chunks)} > {UNKNOWN_THRESHOLD}")
        overall_pass = False
    else:
        print("PASS: 未知职业数量在阈值内")

    # ---------- 不变量 2：正向 spot check ----------
    print("\n===== 不变量 2：正向 spot check =====")
    for desc, expected_class, predicate in SPOT_CHECKS:
        matched = [c for c in chunks if predicate(c)]
        if not matched:
            print(f"FAIL: {desc} 未找到任何 chunk")
            overall_pass = False
            continue
        wrong = [c for c in matched if c["class_name"] != expected_class]
        if wrong:
            print(f"FAIL: {desc} 中 {len(wrong)}/{len(matched)} 个 class_name 不是 {expected_class}")
            for c in wrong[:10]:
                print(f"  {c['doc_id']} | title={c['title']} | class_name={c['class_name']}")
            overall_pass = False
        else:
            print(f"PASS: {desc} 共 {len(matched)} 个 chunk，class_name 均为 {expected_class}")

    # ---------- 不变量 3：Negative checks ----------
    print("\n===== 不变量 3：Negative checks =====")

    # 3a: 删除文件 doc_id 不应出现
    deleted_found = [c for c in chunks if c["doc_id"] in DELETED_DOC_IDS]
    if deleted_found:
        print(f"FAIL: 发现 {len(deleted_found)} 个已删除文件的 doc_id")
        for c in deleted_found[:20]:
            print(f"  {c['doc_id']} | {c['title']}")
        overall_pass = False
    else:
        print("PASS: 未发现已删除文件的 doc_id")

    # 3b: 不应有来源书/目录名作为 class_name（神话冒险除外）
    bad_source_class = [
        c for c in chunks
        if c["class_name"] in SOURCE_BOOK_CLASS_NAMES
    ]
    if bad_source_class:
        print(f"FAIL: 发现 {len(bad_source_class)} 个 chunk 的 class_name 是来源书名/目录名")
        seen = set()
        for c in bad_source_class:
            key = (c["doc_id"], c["class_name"], c["title"])
            if key not in seen:
                seen.add(key)
                print(f"  {c['doc_id']} | class_name={c['class_name']} | {c['title']}")
        overall_pass = False
    else:
        print("PASS: 未将来源书/目录名作为 class_name（神话冒险除外）")

    # 3c: 单一进阶职业 page 文件不应出现未知职业
    single_prestige_unknown = [
        c for c in chunks
        if SINGLE_PRESTIGE_PAGE_RE.match(c["doc_id"]) and c["class_name"] == "未知职业"
    ]
    if single_prestige_unknown:
        print(f"FAIL: 发现 {len(single_prestige_unknown)} 个单一进阶职业 page 文件 chunk 的 class_name 为未知职业")
        seen = set()
        for c in single_prestige_unknown:
            key = (c["doc_id"], c["title"])
            if key not in seen:
                seen.add(key)
                print(f"  {c['doc_id']} | {c['title']}")
        overall_pass = False
    else:
        print("PASS: 单一进阶职业 page 文件无未知职业")

    # ---------- 不变量 4：回归测试 ----------
    print("\n===== 不变量 4：回归测试 =====")
    paladin_ok = run_regression("verify_paladin_archetypes.py", "ALL PASSED")
    heading_ok = run_regression("verify_heading_levels.py", "PASSED")
    if not (paladin_ok and heading_ok):
        overall_pass = False

    # ---------- 汇总 ----------
    print("\n===== 汇总 =====")
    if overall_pass:
        print("ALL PASSED")
        return 0
    else:
        print("SOME CHECKS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
