#!/usr/bin/env python3
"""
PF 术语提取报告 Phase 3 清洗脚本

输入：术语提取报告_分类版.md（基线，只读）
输出：
  - 术语提取报告_优化版.md
  - terms.json
  - manual_review_phase3.md
  - 优化日志.md（追加）

分类管道：精确覆盖 > 来源书识别 > 多信号打分 > 保留原分类 > 其他
"""

import argparse
import json
import re
from pathlib import Path

import term_rules
from extracted_overrides import EXTRACTED_OVERRIDES
from original_optimized_overrides import ORIGINAL_OPTIMIZED_OVERRIDES
from manual_overrides_phase3 import MANUAL_OVERRIDES


# 大小写不敏感的覆盖表（PF 术语英文大小写不统一）
_EXTRACTED_OVERRIDES_LOWER = {k.lower(): v for k, v in EXTRACTED_OVERRIDES.items()}
_MANUAL_OVERRIDES_LOWER = {k.lower(): v for k, v in MANUAL_OVERRIDES.items()}

# 缩写硬编码翻译：这些缩写在源文件中是能力类型标记，没有可提取的完整译名
ABBREVIATION_TRANSLATIONS = {
    "Sp": "类法术能力",
    "Su": "超自然能力",
    "Ex": "特异能力",
}


def parse_args():
    parser = argparse.ArgumentParser(description="PF 术语提取报告 Phase 3 清洗脚本")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path(__file__).parent,
        help="phase1 工作目录，默认脚本所在目录",
    )
    return parser.parse_args()


ARGS = parse_args()
BASE_DIR = ARGS.base_dir.resolve()
INPUT_FILE = BASE_DIR / "术语提取报告_分类版.md"
OUTPUT_FINAL = BASE_DIR / "术语提取报告_优化版.md"
OUTPUT_JSON = BASE_DIR / "terms.json"
OUTPUT_MANUAL = BASE_DIR / "manual_review_phase3.md"
LOG_FILE = BASE_DIR / "优化日志.md"


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------


def extract_category(section_name: str) -> str:
    """从 '法术（157 个术语）' 中提取 '法术'。"""
    return re.split(r"[（(]", section_name)[0].strip()


def parse_baseline(content: str):
    """解析基线 Markdown，返回 [(分类名, [术语记录])] 列表。"""
    sections = []
    current_section = None
    current_terms = []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            if current_section is not None and current_terms:
                sections.append((current_section, current_terms))
            current_section = extract_category(line[3:].strip())
            current_terms = []
        elif line.startswith("|") and current_section is not None:
            parts = [p.strip() for p in line.split("|")]
            parts = parts[1:-1]  # 保留空单元格，去掉首尾空列
            if len(parts) >= 4 and parts[0] != "英文术语" and "---" not in parts[0]:
                current_terms.append({
                    "english": parts[0],
                    "recommended": parts[1] if len(parts) > 1 else "",
                    "others": parts[2] if len(parts) > 2 else "",
                    "count": parts[3] if len(parts) > 3 else "0",
                })

    if current_section is not None and current_terms:
        sections.append((current_section, current_terms))

    return sections


# ---------------------------------------------------------------------------
# 推荐翻译清洗
# ---------------------------------------------------------------------------


def strip_reference(text: str) -> str:
    """去掉末尾的括号数字引用，如 '奥术联结(3)' -> '奥术联结'。"""
    return re.sub(r"\(\d+\)$", "", text).strip()


def is_valid_translation(text: str) -> bool:
    """判断字符串是否像纯净译名。"""
    if not text:
        return False
    if len(text) < term_rules.MIN_TRANSLATION_LEN or len(text) > term_rules.MAX_RECOMMENDED_LEN:
        return False
    if any(text.startswith(b) for b in term_rules.BAD_STARTS):
        return False
    # 句法粒子过多（超过 2 个）则视为句子/片段
    particle_count = sum(1 for p in term_rules.SENTENCE_PARTICLES if p in text)
    if particle_count > 2:
        return False
    return True


def recover_from_others(others_text: str) -> str | None:
    """从'其他翻译'列中寻找最短的合法译名候选。"""
    if not others_text:
        return None

    cleaned = re.sub(r"\(\d+\)", "", others_text)
    candidates = [c.strip() for c in re.split(r"[,，、]", cleaned) if c.strip()]

    valid = []
    for c in candidates:
        c = strip_reference(c)
        # 先尝试去掉描述前缀
        for prefix in term_rules.DESCRIPTION_PREFIXES:
            if c.startswith(prefix):
                c = c[len(prefix):].strip()
                break
        c = strip_reference(c)
        # 候选允许稍长，但仍是译名而非句子
        if len(c) >= term_rules.MIN_TRANSLATION_LEN and len(c) <= term_rules.MAX_OTHER_LEN:
            if not any(c.startswith(b) for b in term_rules.BAD_STARTS):
                if sum(1 for p in term_rules.SENTENCE_PARTICLES if p in c) <= 2:
                    valid.append(c)

    return min(valid, key=len) if valid else None


def clean_recommended(term: dict, log: list[str]):
    """清洗术语的推荐翻译，返回 (新推荐翻译, 是否需要复核)。"""
    original = term["recommended"].strip()
    english = term["english"]

    # 硬编码缩写翻译：Sp/Su/Ex 是能力类型标记，单独出现时无上下文译名
    if english in ABBREVIATION_TRANSLATIONS:
        translated = ABBREVIATION_TRANSLATIONS[english]
        log.append(f"[缩写翻译] {english}: '{original}' -> '{translated}'")
        return translated, False

    if not original:
        # 尝试从其他翻译恢复
        recovered = recover_from_others(term["others"])
        if recovered:
            log.append(f"[自动恢复] {english}: 推荐翻译为空 -> '{recovered}' (从其他翻译提取)")
            return recovered, False
        log.append(f"[需复核] {english}: 推荐翻译为空")
        return "[需人工复核]", True

    # 第一步：如果本身就是合法译名，直接返回
    text = strip_reference(original)
    if len(text) <= 8 and is_valid_translation(text):
        return text, False

    # 第二步：迭代剥离描述性前缀
    cleaned = text
    for _ in range(5):
        prev = cleaned
        for prefix in term_rules.DESCRIPTION_PREFIXES:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break
        cleaned = strip_reference(cleaned)
        if cleaned == prev:
            break

    # 第三步：如果清洗后合法，直接采用
    if is_valid_translation(cleaned):
        if cleaned != original:
            log.append(f"[清洗] {english}: '{original}' -> '{cleaned}'")
        return cleaned, False

    # 第四步：从其他翻译中恢复
    recovered = recover_from_others(term["others"])
    if recovered:
        log.append(f"[自动修复] {english}: '{original}' -> '{recovered}' (从其他翻译提取)")
        return recovered, False

    # 第五步：仍无法确定，标记复核
    log.append(f"[需复核] {english}: 推荐翻译='{original}', 其他翻译='{term['others']}'")
    return "[需人工复核]", True


# ---------------------------------------------------------------------------
# 分类
# ---------------------------------------------------------------------------


def score_signals(term: dict) -> dict[str, int]:
    """对术语进行多信号打分，返回各类别得分。"""
    en = term["english"]
    rec = term["recommended"]
    others = term["others"]
    scores = {
        "法术": 0,
        "专长": 0,
        "职业能力": 0,
        "装备/物品": 0,
        "怪物/生物": 0,
        "动作/战技": 0,
        "状态/条件": 0,
        "组织/势力": 0,
    }

    # 法术信号
    for suffix in term_rules.SPELL_SIGNALS["suffixes"]:
        if rec.endswith(suffix) or any(s.endswith(suffix) for s in others.split(", ") if s):
            scores["法术"] += 2
    combined_text = f"{rec} {others}".lower()
    for kw in term_rules.SPELL_SIGNALS["keywords"]:
        if kw in combined_text:
            scores["法术"] += 1
    for suffix in term_rules.SPELL_SIGNALS["english_suffixes"]:
        if en.lower().endswith(suffix):
            scores["法术"] += 1

    # 专长信号
    for prefix in term_rules.FEAT_SIGNALS["prefixes"]:
        if en.startswith(prefix):
            scores["专长"] += 2
    for kw in term_rules.FEAT_SIGNALS["keywords"]:
        if kw in combined_text:
            scores["专长"] += 1
    for suffix in term_rules.FEAT_SIGNALS["english_suffixes"]:
        if en.lower().endswith(suffix):
            scores["专长"] += 1

    # 职业能力信号
    for suffix in term_rules.CLASS_FEATURE_SIGNALS["suffixes"]:
        if en.endswith(suffix):
            scores["职业能力"] += 2
    for kw in term_rules.CLASS_FEATURE_SIGNALS["keywords"]:
        if kw in combined_text:
            scores["职业能力"] += 1

    # 装备/物品信号
    for kw in term_rules.EQUIPMENT_SIGNALS["keywords"]:
        if kw in rec or kw in others:
            scores["装备/物品"] += 1
    for kw in term_rules.EQUIPMENT_SIGNALS["english_keywords"]:
        if kw.lower() in en.lower():
            scores["装备/物品"] += 1

    # 怪物/生物信号
    if en in term_rules.CREATURE_SIGNALS["exact"]:
        scores["怪物/生物"] += 3
    for kw in term_rules.CREATURE_SIGNALS["keywords"]:
        if kw in combined_text:
            scores["怪物/生物"] += 1

    return scores


def decide_category(term: dict, original_category: str) -> str:
    """应用分类优先级管道。"""
    en = term["english"]

    # 1. 精确覆盖（人工校正）
    if en in term_rules.CATEGORY_OVERRIDES:
        return term_rules.CATEGORY_OVERRIDES[en]

    # 2. 来源书识别
    if en in term_rules.SOURCE_BOOKS:
        return "来源书籍"

    # 3. 来源书识别
    if en in term_rules.SOURCE_BOOKS:
        return "来源书籍"

    # 4. 人工补充覆盖（针对高频/疑难术语）
    manual_cat = _MANUAL_OVERRIDES_LOWER.get(en.lower())
    if manual_cat:
        return manual_cat

    # 5. 来源/历史数据覆盖（源文件提取的法术/专长 + 原优化版分类）
    override_cat = _EXTRACTED_OVERRIDES_LOWER.get(en.lower())
    if override_cat:
        return override_cat

    # 4. 技能精确匹配
    if en in term_rules.SKILL_SIGNALS["exact"]:
        return "技能"

    # 5. 状态/条件精确匹配
    if en in term_rules.CONDITION_SIGNALS["exact"]:
        return "状态/条件"

    # 6. 多信号打分
    scores = score_signals(term)

    # 决策优先级：法术 > 专长 > 职业能力 > 装备/物品 > 原分类（若非其他）
    priority = ["法术", "专长", "职业能力", "装备/物品"]
    for cat in priority:
        if scores[cat] > 0:
            return cat

    # 怪物/生物和动作/战技分数门槛更高，避免误判
    if scores["怪物/生物"] >= 3:
        return "怪物/生物"
    if scores["动作/战技"] >= 3:
        return "动作/战技"
    if scores["状态/条件"] >= 2:
        return "状态/条件"
    if scores["组织/势力"] >= 2:
        return "组织/势力"

    if original_category != "其他":
        return original_category

    return "其他"


# ---------------------------------------------------------------------------
# 其他翻译清洗
# ---------------------------------------------------------------------------


def clean_others(others_text: str, recommended: str) -> str:
    """清理'其他翻译'列，只保留真正的译名变体。"""
    if not others_text or not others_text.strip():
        return ""

    cleaned = re.sub(r"\(\d+\)", "", others_text)
    parts = [p.strip() for p in re.split(r"[,，、]", cleaned) if p.strip()]

    seen = set()
    unique = []
    for p in parts:
        p = strip_reference(p)
        if not p:
            continue
        if len(p) > term_rules.MAX_OTHER_LEN:
            continue
        if any(p.startswith(b) for b in term_rules.BAD_STARTS):
            continue
        # 过滤包含过多句法粒子的片段
        if sum(1 for part in term_rules.SENTENCE_PARTICLES if part in p) > 2:
            continue
        # 过滤人称代词/动作词明显的上下文
        if re.search(r"[你他她它我]|施放|获得|受到|如同|可以|能够|必须", p):
            continue
        # 与推荐翻译相同或为子串关系
        if p == recommended or recommended in p or p in recommended:
            continue
        if p in seen:
            continue
        seen.add(p)
        unique.append(p)

    return ", ".join(unique)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main():
    print(f"读取基线文件: {INPUT_FILE}")
    content = INPUT_FILE.read_text(encoding="utf-8")
    sections = parse_baseline(content)
    print(f"解析到 {len(sections)} 个原始分类，共 {sum(len(t) for _, t in sections)} 个术语")

    log: list[str] = []
    manual_review: list[dict] = []

    # 先统一清洗推荐翻译
    print("清洗推荐翻译...")
    all_terms: list[dict] = []
    for section_name, terms in sections:
        for term in terms:
            recommended, needs_review = clean_recommended(term, log)
            term["recommended"] = recommended
            term["original_category"] = section_name
            if needs_review:
                manual_review.append({
                    "english": term["english"],
                    "recommended": recommended,
                    "others": term["others"],
                    "original_category": section_name,
                    "count": term["count"],
                })
            all_terms.append(term)

    # 分类
    print("重新分类...")
    categorized: dict[str, list[dict]] = {cat: [] for cat in term_rules.CATEGORY_ORDER}
    for term in all_terms:
        new_cat = decide_category(term, term["original_category"])
        if new_cat != term["original_category"]:
            log.append(f"[重分类] {term['english']}: '{term['original_category']}' -> '{new_cat}'")
        categorized.setdefault(new_cat, []).append(term)

    # 清洗其他翻译（在分类后，基于最终推荐翻译）
    print("清洗'其他翻译'列...")
    for cat, terms in categorized.items():
        for term in terms:
            term["others"] = clean_others(term["others"], term["recommended"])

    # 按出现次数排序
    for cat, terms in categorized.items():
        terms.sort(key=lambda x: int(x["count"]) if x["count"].isdigit() else 0, reverse=True)

    # 生成 Markdown
    print(f"生成 Markdown: {OUTPUT_FINAL}")
    output_lines = ["# PathFinder 1e 中英术语对照表（优化版）\n\n"]
    output_lines.append("_推荐翻译已清洗，其他翻译已精简，分类已重新组织，来源书已单独归档_\n\n")

    total_terms = 0
    for cat in term_rules.CATEGORY_ORDER:
        terms = categorized.get(cat, [])
        if not terms:
            continue
        output_lines.append(f"## {cat}（{len(terms)} 个术语）\n\n")
        output_lines.append("| 英文术语 | 推荐翻译 | 其他翻译 | 出现次数 |\n")
        output_lines.append("|---------|---------|---------|---------|\n")
        for term in terms:
            output_lines.append(
                f"| {term['english']} | {term['recommended']} | {term['others']} | {term['count']} |\n"
            )
        output_lines.append("\n")
        total_terms += len(terms)

    OUTPUT_FINAL.write_text("".join(output_lines), encoding="utf-8")
    print(f"  共 {total_terms} 个术语")

    # 生成 JSON
    print(f"生成 JSON: {OUTPUT_JSON}")
    json_terms = []
    for cat in term_rules.CATEGORY_ORDER:
        for term in categorized.get(cat, []):
            json_terms.append({
                "english": term["english"],
                "recommended": term["recommended"],
                "category": cat,
                "count": int(term["count"]) if term["count"].isdigit() else 0,
                "other_translations": [t.strip() for t in term["others"].split(",") if t.strip()],
            })

    OUTPUT_JSON.write_text(
        json.dumps(json_terms, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 生成人工复核清单
    print(f"生成人工复核清单: {OUTPUT_MANUAL}")
    manual_lines = ["# Phase 3 人工复核清单\n\n"]
    manual_lines.append(f"生成时间: 2026-07-18\n\n")
    manual_lines.append("## 自动标记需复核\n\n")
    manual_lines.append("| 英文术语 | 当前推荐翻译 | 其他翻译 | 原分类 | 出现次数 | 建议操作 |\n")
    manual_lines.append("|---------|------------|---------|--------|---------|---------|\n")
    for case in manual_review:
        others_short = case["others"][:60] + "..." if len(case["others"]) > 60 else case["others"]
        manual_lines.append(
            f"| {case['english']} | {case['recommended']} | {others_short} | "
            f"{case['original_category']} | {case['count']} | 人工确认译名 |\n"
        )

    # 高频抽查（出现次数 >= 50）
    high_freq = [t for t in all_terms if t["count"].isdigit() and int(t["count"]) >= 50]
    manual_lines.append(f"\n## 高频术语抽查（>=50 次，共 {len(high_freq)} 个）\n\n")
    manual_lines.append("| 英文术语 | 推荐翻译 | 分类 | 出现次数 | 复核结论 |\n")
    manual_lines.append("|---------|---------|------|---------|---------|\n")
    for term in sorted(high_freq, key=lambda x: int(x["count"]), reverse=True):
        cat = decide_category(term, term["original_category"])
        manual_lines.append(
            f"| {term['english']} | {term['recommended']} | {cat} | {term['count']} | |\n"
        )

    # 各分类代表性条目抽查（每类前 5）
    manual_lines.append("\n## 各分类代表性条目抽查（每类前 5）\n\n")
    for cat in term_rules.CATEGORY_ORDER:
        terms = categorized.get(cat, [])
        if not terms:
            continue
        manual_lines.append(f"### {cat}\n\n")
        manual_lines.append("| 英文术语 | 推荐翻译 | 出现次数 | 复核结论 |\n")
        manual_lines.append("|---------|---------|---------|---------|\n")
        for term in terms[:5]:
            manual_lines.append(
                f"| {term['english']} | {term['recommended']} | {term['count']} | |\n"
            )

    OUTPUT_MANUAL.write_text("".join(manual_lines), encoding="utf-8")

    # 追加日志
    print("更新日志...")
    if LOG_FILE.exists():
        log_text = LOG_FILE.read_text(encoding="utf-8")
    else:
        log_text = "# 优化日志\n\n"

    log_text += "\n## Phase 3 自动清洗与重分类\n\n"
    log_text += f"- 输入: {INPUT_FILE}\n"
    log_text += f"- 输出: {OUTPUT_FINAL}, {OUTPUT_JSON}, {OUTPUT_MANUAL}\n"
    log_text += f"- 总术语数: {total_terms}\n"
    log_text += "- 分类统计:\n"
    for cat in term_rules.CATEGORY_ORDER:
        terms = categorized.get(cat, [])
        if terms:
            log_text += f"  - {cat}: {len(terms)} 个术语\n"
    other_count = len(categorized.get("其他", []))
    if total_terms > 0:
        log_text += f"- 其他分类占比: {other_count}/{total_terms} = {other_count/total_terms*100:.1f}%\n"
    log_text += f"- 需人工复核术语数: {len(manual_review)}\n\n"
    log_text += "### 详细变更记录\n\n"
    for entry in log:
        log_text += f"{entry}\n"

    LOG_FILE.write_text(log_text, encoding="utf-8")

    print("\nPhase 3 完成！")
    print(f"  - 优化版: {OUTPUT_FINAL}")
    print(f"  - JSON: {OUTPUT_JSON}")
    print(f"  - 人工复核: {OUTPUT_MANUAL}")
    print(f"  - 需复核: {len(manual_review)} 个")


if __name__ == "__main__":
    main()
