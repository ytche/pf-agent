#!/usr/bin/env python3
"""P2 批次 3：terms.json 译名/分类定向修正（2026-08-07）

方案：术语表P2清理方案_20260807.md 批次 3（用户 2026-08-07 逐项拍板）。
白名单硬编码锚点，english 精确匹配，命中数 != 期望即终止（幂等）。

9 项修正：
  1. Divine Boon        神恩 → 神赐之力（other_translations 已有此译名）
  2. Divine Grace       神恩 → 神圣恩典（官方常译）
  3. Villain Codex      出自 → 反派法典（CHM 权威）；other 去噪「傻豆」
  4. Inner Sea Gods     出自 → 内海诸神（CHM 权威）
  5. Inner Sea Magic    出自 → 内海魔法（CHM 权威）；other 去噪「专长」
  6. Pathfinder Comics  出自 → 官方漫画（CHM 权威）
  7. Arcane Anthology   来源 → 秘术选集（CHM 权威）
  8. Pathfinder Player Companion 来源 → 玩家伴侣（CHM 权威）；
     other 去噪「详见」「格拉利昂的精灵」
  9. Occult Skill Unlocks 组织/势力 → 规则概念（分类修正）

Divine Favor 保留「神恩」（CRB 官方译名，不动）。

规则：recommended 修正时，other_translations 移除与新 recommended
相同的项（防重复）及 other_drop 噪声；category 直接覆盖。
md 报告定向行重写 + 章节计数同步（组织/势力 4→3、规则概念 14→15、
移动条目按 count 降序插入新章节表格）。

不重跑 cleanup_phase3.py 流水线（防丢 manual_overrides 覆盖）。

用法：python3 fix_terms_p2_batch3.py [--apply]
默认 dry-run 打印变更；--apply 落盘。
"""
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
JSON_FILE = BASE / "terms.json"
MD_FILE = BASE / "术语提取报告_优化版.md"

# english -> {recommended, category, other_drop}（recommended/category 为 None 表示不动）
FIXES = [
    ("Divine Boon", {"recommended": "神赐之力", "category": None, "other_drop": set()}),
    ("Divine Grace", {"recommended": "神圣恩典", "category": None, "other_drop": set()}),
    ("Villain Codex", {"recommended": "反派法典", "category": None, "other_drop": {"傻豆"}}),
    ("Inner Sea Gods", {"recommended": "内海诸神", "category": None, "other_drop": set()}),
    ("Inner Sea Magic", {"recommended": "内海魔法", "category": None, "other_drop": {"专长"}}),
    ("Pathfinder Comics", {"recommended": "官方漫画", "category": None, "other_drop": set()}),
    ("Arcane Anthology", {"recommended": "秘术选集", "category": None, "other_drop": set()}),
    ("Pathfinder Player Companion", {"recommended": "玩家伴侣", "category": None, "other_drop": {"详见", "格拉利昂的精灵"}}),
    ("Occult Skill Unlocks", {"recommended": None, "category": "规则概念", "other_drop": set()}),
]
MOVE = ("Occult Skill Unlocks", "组织/势力", "规则概念")  # 分类移动（md 章节间迁移）


def fix_terms(terms):
    """返回 (修正后 list, 变更描述 list)。命中数异常时抛 ValueError。"""
    by_en = {}
    for t in terms:
        by_en.setdefault(t["english"], []).append(t)
    changes = []
    for english, fx in FIXES:
        hits = by_en.get(english)
        if hits is None:
            raise ValueError(f"条目缺失: {english}")
        if len(hits) != 1:
            raise ValueError(f"命中数异常: {english}={len(hits)}")
        t = hits[0]
        rec_new = fx["recommended"]
        cat_new = fx["category"]
        # 幂等判定：目标均已达成且无待去噪声
        rec_ok = rec_new is None or t["recommended"] == rec_new
        cat_ok = cat_new is None or t["category"] == cat_new
        drop_left = [o for o in t.get("other_translations", []) if o in fx["other_drop"]]
        if rec_ok and cat_ok and not drop_left:
            continue  # 已修正——幂等
        rec_old = t["recommended"]
        cat_old = t["category"]
        others = t.get("other_translations", [])
        if rec_new is not None:
            t["recommended"] = rec_new
            others = [o for o in others if o != rec_new and o not in fx["other_drop"]]
        else:
            others = [o for o in others if o not in fx["other_drop"]]
        t["other_translations"] = others
        if cat_new is not None:
            t["category"] = cat_new
        changes.append(
            f"{english}: recommended「{rec_old}」→「{rec_new or rec_old}」"
            f" | category「{cat_old}」→「{cat_new or cat_old}」"
            f" | other 去噪 {sorted(fx['other_drop'])}"
        )
    return terms, changes


def fix_md(text, changes):
    """md 报告定向重写：行内修正 + 分类移动 + 章节计数。"""
    lines = text.split("\n")
    # 1. 行内修正（recommended/other 列）——按 english 锚定，count 保留
    changed_en = {ch.split(":")[0] for ch in changes}
    fixed_en = set()
    for i, line in enumerate(lines):
        m = re.match(r"^\| ([^|]+) \| ([^|]*) \| ([^|]*) \| (\d+) \|$", line)
        if not m:
            continue
        en, rec, others, count = m.group(1).strip(), m.group(2).strip(), m.group(3).strip(), m.group(4)
        fx = next((f for f in FIXES if f[0] == en), None)
        if fx is None:
            continue
        rec_new = fx[1]["recommended"]
        if rec_new is None:
            continue  # 纯分类移动不在行内处理
        other_list = [o.strip() for o in others.split(",") if o.strip()] if others else []
        other_list = [o for o in other_list if o != rec_new and o not in fx[1]["other_drop"]]
        lines[i] = f"| {en} | {rec_new} | {', '.join(other_list)} | {count} |"
        fixed_en.add(en)
    missing = changed_en - fixed_en - {MOVE[0]}
    if missing:
        raise ValueError(f"md 行未命中: {missing}")
    # 2. 分类移动：删除旧章节行，按 count 降序插入新章节表
    if any("category" in ch for ch in changes):
        en_move, cat_from, cat_to = MOVE
        # 找移动条目的 count（从 terms.json 解析行）
        mv_line = next((l for l in lines if l.startswith(f"| {en_move} |")), None)
        mv_count = int(mv_line.split("|")[4].strip()) if mv_line else None
        # 删除旧章节中的移动行
        lines = [l for l in lines if not l.startswith(f"| {en_move} |")]
        # 在新章节表格中定位插入点（count 降序）
        in_section = False
        insert_at = None
        for i, l in enumerate(lines):
            if l.startswith(f"## {cat_to}（"):
                in_section = True
                continue
            if in_section and l.startswith("## "):
                break  # 到下一章节
            if in_section and l.startswith("| "):
                m2 = re.match(r"^\| ([^|]+) \| ([^|]*) \| ([^|]*) \| (\d+) \|$", l)
                if m2 and int(m2.group(4)) < mv_count:
                    insert_at = i
                    break
                insert_at = i + 1
        if insert_at is None:
            raise ValueError("未找到规则概念章节插入点")
        lines.insert(insert_at, f"| {en_move} | 神秘技能解放 |  | {mv_count} |")
        # 3. 章节计数更新
        for i, l in enumerate(lines):
            m3 = re.match(r"^## 组织/势力（(\d+) 个术语）$", l)
            if m3:
                lines[i] = f"## 组织/势力（{int(m3.group(1)) - 1} 个术语）"
                continue
            m4 = re.match(r"^## 规则概念（(\d+) 个术语）$", l)
            if m4:
                lines[i] = f"## 规则概念（{int(m4.group(1)) + 1} 个术语）"
    return "\n".join(lines)


def main() -> int:
    terms = json.loads(JSON_FILE.read_text(encoding="utf-8"))
    if not isinstance(terms, list):
        print("terms.json 非 list，终止")
        return 2
    terms, changes = fix_terms(terms)
    if not changes:
        print("0 项修正（均已达成——幂等）")
        return 0
    print(f"修正 {len(changes)} 项：")
    for c in changes:
        print(f"  {c}")
    md_text = MD_FILE.read_text(encoding="utf-8")
    md_new = fix_md(md_text, changes)
    if "--apply" not in sys.argv:
        print("dry-run：仅报告，加 --apply 落盘")
        return 0
    JSON_FILE.write_text(
        json.dumps(terms, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    MD_FILE.write_text(md_new, encoding="utf-8")
    print(f"已落盘 terms.json（{len(terms)} 条）与 md 报告")
    return 0


if __name__ == "__main__":
    sys.exit(main())
