# ⚠️ SUPERSEDED（2026-09-01 · CP3）
# 本脚本逻辑已收敛进 vectorizer/verify/verify_profession.py（VerifyBase 八检查，
# cicd/verify.py profession 类目唯一验收入口）。保留仅作历史参考，不再在 cicd
# 调用；如需复跑请用 `python3 -m vectorizer.verify.verify_profession`。
"""圣骑士变体识别回归测试。

针对 `vectorization_prep_profession/chunks.jsonl` 跑断言：
1. **反例**：10 个子誓约不应作为独立 `class_archetype` 出现
2. **归属**：10 个子誓约的内容必须挂在 `圣律沿循者` 变体下
3. **基线**：43 个 expected 圣骑士变体必须正确归属到对应来源书
4. **女巫回归**：UM 巫术 / 冬女巫 / 四季·林地 来源书保持正确

问题来源：`_fix_paladin_page_55` 步骤 2 的 lookbehind 正则把 `### 标题`
误判为"内容行内嵌的 heading"，导致下挂子能力全部被错误降级为 level 2，
进一步被识别为独立 archetype 变体。
"""
import json
import re
import sys
from pathlib import Path


PHASE1 = Path(__file__).parent
CHUNKS = PHASE1 / "vectorization_prep_profession" / "chunks.jsonl"


# 10 个子誓约 — 它们是 圣律沿循者 的子能力，不应作为独立 archetype
SUB_OATHS = [
    "反腐化誓约",
    "反邪魔誓约",
    "反野蛮誓约",
    "反亡灵誓约",
    "反邪龙誓约",
    "反混乱誓约",
    "仁慈誓约",
    "贞洁誓约",
    "忠诚誓约",
    "复仇誓约",
]

# 43 个 expected 圣骑士变体（来自问题与修复记录 003）
EXPECTED = {
    "神圣防卫者": "APG", "医护骑士": "APG", "神圣使徒": "APG",
    "光耀骑士": "APG", "亡灵制裁者": "APG", "圣光斗士": "APG",
    "救赎者": "ARG", "石之领主": "ARG", "宁静卫士": "ARG",
    "圣律沿循者": "UM",
    "神性猎手": "UC", "天界骑士": "UC", "圣铳卫": "UC",
    "神策使": "UC", "死骸骑士": "UC", "圣盾使": "UC",
    "神圣向导": "ACG", "神殿勇者": "ACG",
    "义洛理圣武士": "ISC", "勇气之刃": "ISM", "幽冥猎手": "OA",
    "艾奥梅黛执法者": "DA",
    "殉道骑士": "HA", "心魂卫士": "HA", "受苦骑士": "HA",
    "灰骑士": "UI", "圣使": "AMH", "神炼勇士": "WMH",
    "守林人": "UW", "狩邪圣武士": "UW", "荒野守望者": "UW",
    "驱魔卫士": "MHH", "鼓舞卫士": "HH",
    "神选之子": "FF", "珍珠寻者": "AqA", "薄暮骑士": "BoS", "神卫": "CaC",
    "克拉肯杀手": "BotS", "泰尔曼多圣从者": "AG",
    "滥觞卫士": "WO", "灵刃骑士": "OO",
}


def load_chunks():
    chunks = []
    with open(CHUNKS, encoding="utf-8") as f:
        for line in f:
            chunks.append(json.loads(line))
    return chunks


def check_no_sub_oath_as_archetype(chunks):
    """反例：10 个子誓约不应作为独立 class_archetype chunk。"""
    errors = []
    for c in chunks:
        if c.get("class_name") not in ("圣骑士", "圣武士"):
            continue
        if c.get("component_type") != "class_archetype":
            continue
        title = c.get("title") or ""
        for oath in SUB_OATHS:
            if oath in title and oath != "圣律沿循者":
                errors.append(
                    f"  [{title!r}] 应为 class_feature，但被识别为 class_archetype\n"
                    f"        archetype_name={c.get('archetype_name')!r} abbr={c.get('book_abbreviation')}"
                )
                break
    return errors


def check_sub_oath_belongs_to_oathbound(chunks):
    """归属：10 个子誓约的内容应归属到 圣律沿循者 变体下。"""
    errors = []
    for oath in SUB_OATHS:
        # 找有这个 oath 的 class_feature chunk（应在 圣律沿循者 下）
        feature_chunks = [
            c for c in chunks
            if c.get("class_name") in ("圣骑士", "圣武士")
            and c.get("component_type") == "class_feature"
            and oath in (c.get("title") or "")
        ]
        if not feature_chunks:
            # 子誓约本身可能没作为 feature 出现（如果源数据里没拆分出独立块）
            # 这是允许的，只要没作为独立 archetype 就行
            continue
        for c in feature_chunks:
            if c.get("archetype_name") != "圣律沿循者":
                errors.append(
                    f"  [{oath}] 的能力 chunk 应归属到 圣律沿循者，"
                    f"实际 archetype_name={c.get('archetype_name')!r}"
                )
    return errors


def _canonical_archetype_name(chunk: dict) -> str:
    """从 chunk 的 title / archetype_name 提取规范化变体名（_master_key + 去变体标记）。

    避免子串误匹配：如 expected '圣使' 不应误匹配 '神圣使徒'。
    """
    raw = (chunk.get("title", "") or chunk.get("archetype_name", "") or "").strip()
    # 去掉变体标记后缀
    for pat in [
        r"【圣骑士变体】", r"【\s*[A-Za-z0-9&]+\s*圣骑士变体】",
        r"[（(]圣武士变体[)）]", r"〔圣武士变体〕", r"［圣武士变体］",
        r"【圣武士变体】", r"（圣武士变体）",
    ]:
        raw = re.sub(pat, "", raw).strip()
    # 取前导连续中文字符（_master_key 的逻辑）
    m = re.search(r"^[一-鿿]+", raw)
    return m.group(0) if m else raw


def check_expected_paladin(chunks):
    """基线：43 个 expected 圣骑士变体必须正确归属到对应来源书。

    匹配用 _canonical_archetype_name 取 chunk 的规范化变体名（_master_key），
    与 expected key 等值比较，避免子串误匹配（'圣使' in '神圣使徒' 这种）。
    """
    ok, wrong, missing = [], [], []
    for name, abbr in EXPECTED.items():
        matched = [
            c for c in chunks
            if c.get("class_name") in ("圣骑士", "圣武士")
            and c.get("component_type") == "class_archetype"
            and _canonical_archetype_name(c) == name
        ]
        if not matched:
            missing.append(name)
            continue
        for c in matched:
            if c["book_abbreviation"] == abbr:
                ok.append(name)
            else:
                wrong.append((name, abbr, c["book_abbreviation"]))
    return ok, wrong, missing


def check_witch_regression(chunks):
    """女巫回归：UM 巫术 / 冬女巫 / 四季·林地 庇护主来源书保持正确。"""
    errors = []
    witch_chunks = [c for c in chunks if c.get("class_name") == "女巫"]

    # UM 巫术应至少有 5 个
    um_hex = [
        c for c in witch_chunks
        if c.get("feature_subtype") == "hex"
        and c.get("book_abbreviation") == "UM"
    ]
    if len(um_hex) < 5:
        errors.append(f"  女巫 UM 巫术仅 {len(um_hex)} 个，预期 ≥5")

    # 冬女巫 应为 ISM
    winter = [
        c for c in witch_chunks
        if "冬女巫" in (c.get("title") or "")
        and c.get("component_type") == "class_archetype"
    ]
    if not winter:
        errors.append("  女巫 冬女巫 archetype 缺失")
    elif winter[0].get("book_abbreviation") != "ISM":
        errors.append(
            f"  冬女巫 应为 ISM，实际 {winter[0].get('book_abbreviation')}"
        )

    # 四季·林地 庇护主应为 UW
    for kw in ("早春", "盛夏", "深秋", "林地"):
        patrons = [
            c for c in witch_chunks
            if c.get("feature_subtype") == "patron"
            and kw in (c.get("title") or "")
        ]
        if patrons and patrons[0].get("book_abbreviation") != "UW":
            errors.append(
                f"  女巫 {kw} 庇护主 应为 UW，实际 {patrons[0].get('book_abbreviation')}"
            )
    return errors


def check_bard_regression(chunks):
    """吟游诗人传世名作的回归保护。

    V004: 68 首传世名作应均有独立 class_feature chunk 且 feature_subtype='bardic_masterpiece'。
    """
    errors = []
    bard_chunks = [
        c
        for c in chunks
        if c.get("class_name") == "吟游诗人"
        and c.get("component_type") == "class_feature"
        and not c.get("is_deprecated", False)
    ]
    bm = [c for c in bard_chunks if c.get("feature_subtype") == "bardic_masterpiece"]
    if len(bm) < 68:
        errors.append(f"  吟游诗人传世名作仅 {len(bm)} 个（预期 ≥ 68）")
    return errors


def _canonical_archetype_key(name: str, source_book: str = "") -> str:
    """生成跨文件变体去重的规范化 key。

    归一化策略：
    - 去掉变体标记后缀：``【圣骑士变体】`` / ``（圣武士变体）`` / ``〔圣武士变体〕`` / ``［圣武士变体］``
    - 去掉 ``（English）`` 内的英文（PF 中英对照常见）
    - 保留中文名 + 英文名（若在 title 中）+ 来源书
    - 这样同一变体的不同 title 写法（如 ``X（English）`` vs ``X【圣骑士变体】``）能归到同一 key
    """
    n = name or ""
    # 去掉各种变体标记
    for pat in [
        r"【圣骑士变体】", r"【\s*[A-Za-z0-9&]+\s*圣骑士变体】",
        r"[（(]圣武士变体[)）]", r"〔圣武士变体〕", r"［圣武士变体］",
        r"【圣武士变体】", r"（圣武士变体）",
    ]:
        n = re.sub(pat, "", n).strip()
    return n + "|" + (source_book or "")


def check_cross_file_duplicates(chunks):
    """检测同一变体在不同文件被重复识别为独立 archetype 的情况。

    返回 dict：``{canonical_name: {"inconsistent": [...], "redundant": [...]}}``
    - inconsistent：title 不一致的重复（真 bug）
    - redundant：title 完全一致的重复（冗余，非 bug，仅 INFO）

    仅当 inconsistent 非空时整体视为 FAIL。
    """
    from collections import defaultdict
    groups: dict = defaultdict(list)
    for c in chunks:
        if c.get("component_type") != "class_archetype":
            continue
        if c.get("class_name") not in ("圣骑士", "圣武士"):
            continue
        name = c.get("archetype_name") or c.get("title") or ""
        if not name:
            continue
        abbr = c.get("book_abbreviation") or ""
        key = _canonical_archetype_key(name, abbr)
        groups[key].append({
            "doc_id": c.get("doc_id", ""),
            "title": c.get("title", ""),
            "archetype_name": name,
            "chm_toc_path": c.get("chm_toc_path", ""),
            "is_canonical": "职业变体" in (c.get("chm_toc_path") or ""),
        })

    result = {}
    for k, infos in groups.items():
        if len(infos) < 2:
            continue
        # 区分 title 是否一致
        titles = set(i["title"] for i in infos)
        if len(titles) > 1:
            result[k] = {"inconsistent": infos, "redundant": []}
        else:
            result[k] = {"inconsistent": [], "redundant": infos}
    return result


def main():
    if not CHUNKS.exists():
        print(f"ERROR: chunks.jsonl 不存在: {CHUNKS}")
        print("  请先跑 python3 vectorization_prep_profession.py")
        sys.exit(2)

    chunks = load_chunks()
    print(f"加载 {len(chunks)} 个 chunks\n")

    # 1. 反例：子誓约不应作为独立 archetype
    print("[1] 反例：子誓约不应作为独立 archetype")
    errs1 = check_no_sub_oath_as_archetype(chunks)
    if errs1:
        for e in errs1:
            print(f"  FAIL: {e}")
    else:
        print("  PASS: 无子誓约被误识别为独立 archetype")

    # 2. 归属：子誓约应归属到 圣律沿循者
    print("\n[2] 归属：子誓约内容应归属到 圣律沿循者")
    errs2 = check_sub_oath_belongs_to_oathbound(chunks)
    if errs2:
        for e in errs2:
            print(f"  FAIL: {e}")
    else:
        print("  PASS: 子誓约内容正确归属（要么不出现，要么在 圣律沿循者 下）")

    # 3. 基线：43 个 expected
    print("\n[3] 基线：43 个 expected 圣骑士变体")
    ok, wrong, missing = check_expected_paladin(chunks)
    print(f"  OK={len(ok)} WRONG={len(wrong)} MISSING={len(missing)}")
    if wrong:
        for name, exp, got in wrong:
            print(f"  WRONG: {name} 应为 {exp}，实际 {got}")
    if missing:
        for m in missing:
            print(f"  MISSING: {m}")

    # 4. 女巫回归
    print("\n[4] 女巫回归")
    errs4 = check_witch_regression(chunks)
    if errs4:
        for e in errs4:
            print(f"  FAIL: {e}")
    else:
        print("  PASS: UM 巫术/冬女巫/四季·林地 来源书正确")

    # 4b. 吟游诗人回归（V004：传世名作子类型与数量）
    print("\n[4b] 吟游诗人回归（V004 传世名作）")
    errs4b = check_bard_regression(chunks)
    if errs4b:
        for e in errs4b:
            print(f"  FAIL: {e}")
    else:
        print("  PASS: 68 首传世名作 feature_subtype 正确")

    # 5. 跨文件变体去重：同一变体不应在不同文件被重复识别为独立 archetype
    print("\n[5] 跨文件变体去重")
    dup_groups = check_cross_file_duplicates(chunks)
    inconsistent_dups = []
    redundant_dups = []
    for k, v in dup_groups.items():
        if v["inconsistent"]:
            inconsistent_dups.append((k, v["inconsistent"]))
        if v["redundant"]:
            redundant_dups.append((k, v["redundant"]))

    if inconsistent_dups:
        for canonical_name, infos in sorted(inconsistent_dups):
            print(f"  INCONSISTENT: {canonical_name}")
            for info in infos:
                marker = " [权威]" if info["is_canonical"] else " [副本]"
                print(f"      {marker} doc={info['doc_id']}")
                print(f"            title={info['title'][:60]}")
                print(f"            archetype_name={info['archetype_name']}")
    else:
        print("  PASS: 无 title 不一致的跨文件重复")

    if redundant_dups:
        print(f"  INFO: {len(redundant_dups)} 处 title 完全一致的冗余副本（已归一化，非 bug）:")
        for canonical_name, infos in redundant_dups:
            print(f"      {canonical_name[:50]}: {len(infos)} 份副本")

    # 汇总
    total_fail = len(errs1) + len(errs2) + len(errs4) + len(wrong) + len(missing) + len(inconsistent_dups)
    print()
    if total_fail == 0:
        print("ALL PASSED")
        sys.exit(0)
    else:
        print(f"FAILED: 共 {total_fail} 个问题")
        sys.exit(1)


if __name__ == "__main__":
    main()