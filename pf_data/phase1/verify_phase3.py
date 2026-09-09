#!/usr/bin/env python3
"""
PF Phase 3 输出自动化验收脚本

检查项：
1. "其他" 分类占比 < 20%
2. 同一英文术语不出现在多个分类
3. "推荐翻译"不以 bad start 开头，不含两个以上句法粒子
4. 已知误分类已修正（20 个检查点）
5. Markdown 与 JSON 术语数量一致
6. 章节标题无重复计数后缀
"""

import json
import re
import sys
from pathlib import Path

import term_rules


BASE_DIR = Path(__file__).parent.resolve()
MD_FILE = BASE_DIR / "术语提取报告_优化版.md"
JSON_FILE = BASE_DIR / "terms.json"

# 已知误分类检查点（英文术语 -> 期望分类）
CHECKPOINTS = {
    "Combat Expertise": "专长",
    "Weapon Focus": "专长",
    "Weapon Specialization": "专长",
    "Neutralize Poison": "法术",
    "Remove Disease": "法术",
    "Detect Poison": "法术",
    "Detect Undead": "法术",
    "Plant Growth": "法术",
    "Cure Moderate Wounds": "法术",
    "Spring Attack": "专长",
    "Whirlwind Attack": "专长",
    "Improved Trip": "专长",
    "Improved Disarm": "专长",
    "Improved Bull Rush": "专长",
    "Improved Grapple": "专长",
    "Improved Feint": "专长",
    "Improved Initiative": "专长",
    "Mobility": "专长",
    "Nimble Moves": "专长",
    "Improved Critical": "专长",
}


def parse_md(path: Path):
    """解析优化版 Markdown，返回 {category: [terms]}。"""
    content = path.read_text(encoding="utf-8")
    sections = {}
    current_category = None
    current_terms = []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            if current_category and current_terms:
                sections[current_category] = current_terms
            title = line[3:].strip()
            current_category = re.split(r"[（(]", title)[0].strip()
            current_terms = []
        elif line.startswith("|") and current_category:
            parts = [p.strip() for p in line.split("|")]
            parts = parts[1:-1]  # 保留空单元格
            if len(parts) >= 4 and parts[0] != "英文术语" and "---" not in parts[0]:
                current_terms.append({
                    "english": parts[0],
                    "recommended": parts[1],
                    "others": parts[2],
                    "count": parts[3],
                })

    if current_category and current_terms:
        sections[current_category] = current_terms

    return sections


def load_json(path: Path):
    """加载 JSON 术语表。"""
    return json.loads(path.read_text(encoding="utf-8"))


def run_checks():
    errors = []

    if not MD_FILE.exists():
        errors.append(f"文件不存在: {MD_FILE}")
        return errors
    if not JSON_FILE.exists():
        errors.append(f"文件不存在: {JSON_FILE}")
        return errors

    sections = parse_md(MD_FILE)
    json_terms = load_json(JSON_FILE)

    total_terms = sum(len(t) for t in sections.values())
    other_count = len(sections.get("其他", []))

    # 1. 其他分类占比
    if total_terms > 0:
        ratio = other_count / total_terms * 100
        print(f"[统计] 总术语数: {total_terms}, 其他分类: {other_count} ({ratio:.1f}%)")
        if ratio >= 20:
            errors.append(f"'其他'分类占比 {ratio:.1f}%，目标 < 20%")
    else:
        errors.append("术语总数为 0")

    # 2. 同一英文术语不出现在多个分类
    term_to_categories = {}
    for cat, terms in sections.items():
        for term in terms:
            term_to_categories.setdefault(term["english"], set()).add(cat)

    duplicates = {k: v for k, v in term_to_categories.items() if len(v) > 1}
    if duplicates:
        for en, cats in list(duplicates.items())[:10]:
            errors.append(f"术语 '{en}' 出现在多个分类: {', '.join(sorted(cats))}")
        if len(duplicates) > 10:
            errors.append(f"... 共 {len(duplicates)} 个重复术语")

    # 3. 推荐翻译质量
    bad_translations = []
    for cat, terms in sections.items():
        for term in terms:
            rec = term["recommended"]
            if not rec:
                bad_translations.append((term["english"], cat, "推荐翻译为空"))
                continue
            if any(rec.startswith(b) for b in term_rules.BAD_STARTS):
                bad_translations.append((term["english"], cat, f"以不良开头: {rec[:20]}"))
                continue
            particle_count = sum(1 for p in term_rules.SENTENCE_PARTICLES if p in rec)
            if particle_count > 2:
                bad_translations.append((term["english"], cat, f"句法粒子过多: {rec[:20]}"))

    if bad_translations:
        for en, cat, reason in bad_translations[:10]:
            errors.append(f"推荐翻译质量异常 '{en}' ({cat}): {reason}")
        if len(bad_translations) > 10:
            errors.append(f"... 共 {len(bad_translations)} 个推荐翻译质量异常")

    # 4. 已知误分类检查点（仅检查输出中存在的术语）
    term_lookup = {}
    for cat, terms in sections.items():
        for term in terms:
            term_lookup[term["english"]] = cat

    missing_checkpoints = []
    for en, expected in CHECKPOINTS.items():
        actual = term_lookup.get(en)
        if actual is None:
            missing_checkpoints.append(en)
        elif actual != expected:
            errors.append(f"检查点未修正: '{en}' 在 '{actual}'，期望 '{expected}'")

    if missing_checkpoints:
        print(f"[提示] 以下检查点术语未在输出中出现（可能不在基线中）: {', '.join(missing_checkpoints)}")

    # 5. Markdown 与 JSON 数量一致
    if total_terms != len(json_terms):
        errors.append(f"Markdown 术语数 {total_terms} 与 JSON 术语数 {len(json_terms)} 不一致")

    # 6. 章节标题无重复计数后缀
    content = MD_FILE.read_text(encoding="utf-8")
    dup_title_pattern = re.compile(r"^## .+?（\d+ 个术语）（\d+ 个术语）", re.MULTILINE)
    if dup_title_pattern.search(content):
        errors.append("章节标题存在重复计数后缀，如 '（N 个术语）（N 个术语）'")

    return errors


def main():
    print("开始 Phase 3 验收检查...\n")
    errors = run_checks()

    if errors:
        print(f"验收未通过，发现 {len(errors)} 个问题:\n")
        for i, err in enumerate(errors, 1):
            print(f"  {i}. {err}")
        print("\n请检查 cleanup_phase3.py 输出或补充 term_rules.py 规则。")
        sys.exit(1)
    else:
        print("✅ Phase 3 验收全部通过！")
        sys.exit(0)


if __name__ == "__main__":
    main()
