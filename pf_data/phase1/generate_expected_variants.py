#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成职业 expected 变体基线。

为每个职业输出一份 <职业名>.json，键为规范化变体名（前导连续中文），
值为来源书缩写；来源书判不准的标记为 "?"。

生成策略：
1. 优先解析各职业的「基础变体页」顶部的来源-变体表（最权威）；
2. 其次扫描根目录下的聚合变体文件（文件名含「变体」）中的显式变体标题；
3. 圣骑士直接复用 verify_paladin_archetypes.py 的 EXPECTED 字典。
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# 复用向量化脚本中的解析与来源推断逻辑
sys.path.insert(0, str(Path(__file__).parent))
from vectorization_prep_profession import (  # noqa: E402
    CLASS_CONTAINERS,
    INPUT_DIR as PROFESSION_INPUT_DIR,
    MD_MAPPING_JSON,
    SOURCE_BOOK_ABBR_MD,
    _book_from_abbr,
    _match_book_name,
    _name_variants,
    _normalize_heading_title,
    classify_base_page,
    discover_known_classes,
    extract_archetype_info,
    infer_class_name,
    load_abbreviation_table,
    load_md_mapping,
    looks_like_archetype_title,
    resolve_chm_toc_path,
)
from verify_paladin_archetypes import EXPECTED as PALADIN_EXPECTED  # noqa: E402

PHASE1 = Path(__file__).parent
CHUNKS_PATH = PHASE1 / "vectorization_prep_profession" / "chunks.jsonl"
OUTPUT_DIR = PHASE1 / "expected_variants"

# 不参与职业名匹配的路径片段/容器名
_NON_CLASS_DIR_NAMES = {
    *CLASS_CONTAINERS,
    "基础神话能力",
    "通用道途能力",
    "神眷道途能力",
    "获取阶层",
    "PotR正义之道",  # 来源书目录，被误识别为职业名
}

# 扫描聚合文件时排除的通用非变体标题
_GENERIC_ARCHETYPE_EXCLUDES = {
    "职业变体",
    "变体",
    "变体职业特性",
    "Class Archetypes",
    "Alternate Class Features",
    "Archetypes",
    "变体列表",
    "职业变体列表",
    # 常见被误识别的能力/章节名
    "科研发现",
    "炼金炸弹",
    "冒险之路",
    "冒险之路AP",
    "本职技能",
    "奖励专长",
    "特殊",
    "技能",
    "偷袭",
    "军用武器熟练",
    "武器和防具擅长",
    "武器和护甲擅长",
    "致残攻击",
    "寻找陷阱",
    "科研发现选项",
    "炼金拟像",
    "分身拟像",
    "保存器官",
    "寄生畸胎",
    "信仰",
    "领域",
    "狂暴之力",
    "盗贼天赋",
    "忍术",
    "巫术",
    "强力巫术",
    "高等巫术",
    "庇护主",
    "血承",
    "学派",
    "流派",
    "优雅姿态",
    "推荐法术",
    "奖励法术",
    "法术列表",
    # 进阶/神话常见非变体
    "进阶条件",
    "进阶要求",
    "先决条件",
    "要求",
    "生命骰",
}


def _leaf_directory_names(input_dir: Path) -> Set[str]:
    """收集 input_dir 下所有叶级目录名（含文件或更深子目录的目录自身）。"""
    names: Set[str] = set()
    for sub in input_dir.rglob("*"):
        if sub.is_dir() and any(sub.rglob("*.md")):
            names.add(sub.name)
    return names


def _is_real_class(class_name: str, leaf_dirs: Set[str]) -> bool:
    """判断 class_name 是否应被视为真实职业。"""
    if not class_name or class_name == "未知职业":
        return False
    if class_name in _NON_CLASS_DIR_NAMES:
        return False
    return class_name in leaf_dirs


def collect_target_classes(chunks_path: Path, leaf_dirs: Set[str]) -> Set[str]:
    """从 chunks.jsonl 收集目标职业名。"""
    classes: Set[str] = set()
    with open(chunks_path, encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            cn = c.get("class_name", "")
            if _is_real_class(cn, leaf_dirs):
                classes.add(cn)
    return classes


def _canonical_variant_name(title: str) -> Optional[str]:
    """变体规范名：前导连续中文，不含括号、英文、空格。"""
    t = _normalize_heading_title(title)
    for pat in [
        r"【[^】]*变体[^】]*】",
        r"〔[^〕]*变体[^〕]*〕",
        r"［[^］]*变体[^］]*］",
        r"（[^）]*变体[^）]*）",
        r"\([^)]*Archetype[^)]*\)",
    ]:
        t = re.sub(pat, "", t).strip()
    m = re.search(r"^[一-鿿]+", t)
    if not m:
        return None
    return m.group(0)


def _looks_like_source_cell(cell: str, book_lookup: Dict[str, Any]) -> bool:
    """判断单元格是否包含来源书信息（中文书名或英文缩写）。"""
    cell = cell.strip()
    if not cell:
        return False
    abbr_map = book_lookup.get("abbr", {})
    cn_map = book_lookup.get("cn_to_abbr", {})
    en_map = book_lookup.get("en_to_abbr", {})
    if re.search(r"[（(][A-Za-z0-9&]{2,}[）)]", cell):
        return True
    if _match_book_name(cell, cn_map, en_map, abbr_map):
        return True
    return False


def _extract_source_abbr(cell: str, book_lookup: Dict[str, Any]) -> Optional[str]:
    """从单元格中提取来源书缩写（保持原大小写）。"""
    cell = cell.strip()
    abbr_map = book_lookup.get("abbr", {})
    cn_map = book_lookup.get("cn_to_abbr", {})
    en_map = book_lookup.get("en_to_abbr", {})

    for token in re.findall(r"[（(]([A-Za-z0-9&]+)[）)]", cell):
        book = _book_from_abbr(token.upper(), abbr_map)
        if book:
            return book[2]

    book = _match_book_name(cell, cn_map, en_map, abbr_map)
    if book:
        return book[2]
    return None


def _extract_variant_chinese_name(cell: str) -> Optional[str]:
    """从变体名单元格中提取中文名（去掉英文括号和备注）。"""
    cell = cell.replace("*", "").replace("~", "").strip()
    # 名称（English Name，备注） 或 名称（English Name）
    m = re.search(
        r"^(.+?)\s*[（(]\s*([A-Za-z][A-Za-z0-9'\-\s]*?)",
        cell,
    )
    if m:
        chinese = m.group(1).strip()
        if chinese and chinese != "来源书":
            return chinese
    # 仅中文
    m = re.search(r"^[一-鿿]+", cell)
    if m:
        return m.group(0)
    return None


def _merge_first_table_rows(raw_lines: List[str]) -> List[str]:
    """合并并只返回第一个连续的 Markdown 表格。

    - 以 ``|`` 开头的行视为表格行；
    - 以空白字符开头的行视为上一行的单元格折行，合并到当前缓冲；
    - 一旦出现非表格行（不以 ``|`` 或空白开头），或空行，即结束第一个表格。
    """
    merged: List[str] = []
    buf = ""
    in_table = False
    for line in raw_lines:
        s = line.rstrip()
        if not s:
            if buf:
                merged.append(buf)
                buf = ""
            if in_table:
                break
            continue
        if s.startswith("|"):
            in_table = True
            if buf:
                merged.append(buf)
                buf = ""
            buf = s
            if s.endswith("|"):
                merged.append(buf)
                buf = ""
            continue
        if s[0].isspace():
            if buf:
                buf += " " + s.lstrip()
            continue
        # 非表格、非续行内容：第一个表格结束
        if buf:
            merged.append(buf)
            buf = ""
        if in_table:
            break
    if buf:
        merged.append(buf)
    return merged


def parse_base_page_table(
    raw_lines: List[str],
    book_lookup: Dict[str, Any],
) -> Dict[str, Optional[str]]:
    """解析职业基础页顶部的来源-变体表。

    返回：{中文变体名: 来源书缩写 or None}
    """
    merged = _merge_first_table_rows(raw_lines)

    # 校验：第一个表格里至少有一行来源单元格和一行变体单元格
    has_source = False
    has_variant = False
    for line in merged:
        cells = [c.strip() for c in line.strip("|").split("|")]
        cells = [c for c in cells if c]
        if any("---" in c for c in cells):
            continue
        for cell in cells:
            if _looks_like_source_cell(cell, book_lookup):
                has_source = True
            elif _extract_variant_chinese_name(cell):
                has_variant = True
    if not (has_source and has_variant):
        return {}

    current_source: Optional[str] = None
    variants: Dict[str, Optional[str]] = {}

    for line in merged:
        cells = [c.strip() for c in line.strip("|").split("|")]
        cells = [c for c in cells if c]
        if not cells:
            continue
        if any("---" in c for c in cells):
            continue
        if any(c in ("来源书", "变体名", "来源", "变体") for c in cells):
            continue

        source: Optional[str] = None
        variant_cell: Optional[str] = None

        if len(cells) == 1:
            cell = cells[0]
            if _looks_like_source_cell(cell, book_lookup):
                src = _extract_source_abbr(cell, book_lookup)
                if src:
                    current_source = src
            else:
                variant_cell = cell
        elif len(cells) >= 2:
            # 优先第一列为来源、第二列为变体
            if _looks_like_source_cell(cells[0], book_lookup):
                src = _extract_source_abbr(cells[0], book_lookup)
                if src:
                    current_source = src
                variant_cell = cells[1]
            elif _looks_like_source_cell(cells[1], book_lookup):
                src = _extract_source_abbr(cells[1], book_lookup)
                if src:
                    current_source = src
                variant_cell = cells[0]
            else:
                variant_cell = cells[0]

        if variant_cell:
            name = _extract_variant_chinese_name(variant_cell)
            if name and name not in ("来源书",) and _is_likely_real_archetype(name):
                variants[name] = current_source

    return variants


def build_archetype_masters(
    input_dir: Path,
    md_mapping: Dict[str, Any],
    book_lookup: Dict[str, Any],
    known_classes: Set[str],
) -> Dict[str, Dict[str, Optional[str]]]:
    """扫描职业基础页，解析变体主表。"""
    masters: Dict[str, Dict[str, Optional[str]]] = defaultdict(dict)
    for file_path in sorted(input_dir.rglob("*.md")):
        rel_path = file_path.relative_to(input_dir)
        toc_path = resolve_chm_toc_path(rel_path, [], md_mapping)
        base_type, _ = classify_base_page(toc_path)
        if base_type != "archetype_base":
            continue
        try:
            raw_lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            class_name = infer_class_name(rel_path, "", [], known_classes)
            table = parse_base_page_table(raw_lines, book_lookup)
            if table:
                masters[class_name].update(table)
        except Exception as e:
            print(f"WARN 解析变体主表失败 {rel_path}: {e}", file=sys.stderr)
    return masters


def _infer_source_from_path(rel_path: Path, book_lookup: Dict[str, Any]) -> Optional[str]:
    """从文件路径/名推断来源书缩写。"""
    abbr_map = book_lookup.get("abbr", {})
    cn_map = book_lookup.get("cn_to_abbr", {})
    en_map = book_lookup.get("en_to_abbr", {})

    for token in re.findall(r"[A-Za-z0-9&]{2,}", rel_path.name):
        book = _book_from_abbr(token.upper(), abbr_map)
        if book:
            return book[2]

    for part in rel_path.parts:
        for variant in _name_variants(part):
            book = _match_book_name(variant, cn_map, en_map, abbr_map)
            if book:
                return book[2]
            for token in re.findall(r"[A-Za-z0-9&]{2,}", variant):
                book = _book_from_abbr(token.upper(), abbr_map)
                if book:
                    return book[2]
    return None


def _extract_title_source_abbr(title: str, book_lookup: Dict[str, Any]) -> Optional[str]:
    """从标题中的 【XX】 / (XX 变体) 等提取来源书缩写。"""
    abbr_map = book_lookup.get("abbr", {})
    for token in re.findall(r"[【［（(]([A-Za-z0-9&]+)[】］）)]", title):
        book = _book_from_abbr(token.upper(), abbr_map)
        if book:
            return book[2]
    return None


def _extract_inline_source_abbr(text: str, book_lookup: Dict[str, Any]) -> Optional[str]:
    """从正文段首的来源标记提取缩写。"""
    abbr_map = book_lookup.get("abbr", {})
    cn_map = book_lookup.get("cn_to_abbr", {})
    en_map = book_lookup.get("en_to_abbr", {})
    snippet = text[:400]

    for m in re.finditer(r"<!--\s*([A-Za-z0-9&]+)-source:", snippet):
        book = _book_from_abbr(m.group(1).upper(), abbr_map)
        if book:
            return book[2]

    for m in re.finditer(r"出自《([^《》]+)》(?:[（(]([A-Za-z][A-Za-z0-9'\-\s]*)[）)])?", snippet):
        if m.group(2):
            book = _book_from_abbr(m.group(2).strip().upper(), abbr_map)
            if book:
                return book[2]
        book = _match_book_name(m.group(1).strip(), cn_map, en_map, abbr_map)
        if book:
            return book[2]

    for m in re.finditer(r"来源[：:]\s*([^，,\n]+)", snippet):
        hint = m.group(1).strip()
        am = re.search(r"[（(]([A-Za-z0-9&]+)[）)]", hint)
        if am:
            book = _book_from_abbr(am.group(1).upper(), abbr_map)
            if book:
                return book[2]
        book = _match_book_name(hint, cn_map, en_map, abbr_map)
        if book:
            return book[2]

    return None


def _determine_source(
    title: str,
    text: str,
    rel_path: Path,
    book_lookup: Dict[str, Any],
    path_abbr: Optional[str],
) -> Optional[str]:
    """综合标题、正文、路径推断来源书缩写；不确定返回 None。"""
    abbr = _extract_title_source_abbr(title, book_lookup)
    if abbr:
        return abbr
    abbr = _extract_inline_source_abbr(text, book_lookup)
    if abbr:
        return abbr
    if path_abbr:
        return path_abbr
    return None


def _is_aggregate_variant_file(rel_path: Path) -> bool:
    """根目录下的聚合变体文件，如 冒险者指南AG_变体.md。"""
    return (
        len(rel_path.parts) == 1
        and ("变体" in rel_path.name or "archetype" in rel_path.name.lower())
    )


def _is_likely_real_archetype(canonical_name: str) -> bool:
    """排除明显的能力/章节名。"""
    if canonical_name in _GENERIC_ARCHETYPE_EXCLUDES:
        return False
    # 排除以常见能力后缀结尾的名称
    for suffix in ("科研发现", "基本数据", "等级", "之力", "天赋", "选项", "奖励法术"):
        if canonical_name.endswith(suffix):
            return False
    return True


def build_variant_to_class_map(chunks_path: Path) -> Dict[str, Set[str]]:
    """从 chunks.jsonl 建立「变体规范名 → 出现过的职业集合」映射。

    仅用于聚合文件中无显式职业标记的变体做归属消歧，不作为 expected 来源。
    """
    mapping: Dict[str, Set[str]] = defaultdict(set)
    with open(chunks_path, encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            if c.get("component_type") != "class_archetype":
                continue
            cls = c.get("class_name", "")
            title = c.get("title", "")
            canonical = _canonical_variant_name(title)
            if cls and canonical and cls != "未知职业":
                mapping[canonical].add(cls)
    return mapping


def scan_aggregate_variant_files(
    input_dir: Path,
    md_mapping: Dict[str, Any],
    book_lookup: Dict[str, Any],
    known_classes: Set[str],
    variant_to_class: Dict[str, Set[str]],
) -> Dict[str, Dict[str, Set[Optional[str]]]]:
    """扫描根目录聚合变体文件，补充 base page 未覆盖的变体。"""
    result: Dict[str, Dict[str, Set[Optional[str]]]] = defaultdict(lambda: defaultdict(set))
    heading_re = re.compile(r"^(#{1,6})\s+(.*)$")

    for file_path in sorted(input_dir.glob("*.md")):
        rel_path = file_path.relative_to(input_dir)
        if not _is_aggregate_variant_file(rel_path):
            continue

        path_abbr = _infer_source_from_path(rel_path, book_lookup)
        raw_text = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = raw_text.splitlines()

        for i, line in enumerate(lines):
            m = heading_re.match(line)
            if not m:
                continue
            title = m.group(2).strip()
            if not looks_like_archetype_title(title):
                continue

            name_part, base_class = extract_archetype_info(title)
            if not name_part:
                continue
            canonical = _canonical_variant_name(name_part)
            if not canonical or len(canonical) < 2:
                continue
            if not _is_likely_real_archetype(canonical):
                continue

            # 职业归属
            class_name: Optional[str] = None
            if base_class and base_class in known_classes:
                class_name = base_class
            else:
                # 无显式职业标记时，用 chunks 中的归属消歧
                candidates = variant_to_class.get(canonical, set())
                candidates = candidates & known_classes
                if len(candidates) == 1:
                    class_name = candidates.pop()

            if not class_name:
                continue

            text = "\n".join(lines[i + 1 : i + 12])
            abbr = _determine_source(title, text, rel_path, book_lookup, path_abbr)
            result[class_name][canonical].add(abbr)

    return result


def merge_expected(
    target_classes: Set[str],
    base_page_variants: Dict[str, Dict[str, Optional[str]]],
    scanned_variants: Dict[str, Dict[str, Set[Optional[str]]]],
) -> Dict[str, Dict[str, str]]:
    """合并主表、扫描结果，冲突时标记 "?"。"""
    expected: Dict[str, Dict[str, str]] = {}

    for cls in sorted(target_classes):
        variants: Dict[str, str] = {}

        # 1. 变体主表（最权威）
        for name, abbr in base_page_variants.get(cls, {}).items():
            canonical = _canonical_variant_name(name)
            if not canonical or len(canonical) < 2:
                continue
            variants[canonical] = abbr if abbr else "?"

        # 2. 聚合文件扫描补充
        for name, sources in scanned_variants.get(cls, {}).items():
            canonical = _canonical_variant_name(name)
            if not canonical or len(canonical) < 2:
                continue
            non_none = {s for s in sources if s}
            if canonical in variants:
                existing = variants[canonical]
                if existing == "?" and len(non_none) == 1:
                    variants[canonical] = non_none.pop()
                elif non_none and existing != "?" and non_none != {existing}:
                    variants[canonical] = "?"
                continue
            if len(non_none) == 1:
                variants[canonical] = non_none.pop()
            else:
                variants[canonical] = "?"

        expected[cls] = variants

    return expected


def _safe_filename(name: str) -> str:
    """生成安全的文件名字段（保留中文）。"""
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def _canonical_chunk_archetype_name(title: str) -> Optional[str]:
    """与 verify_paladin_archetypes._canonical_archetype_name 对齐。"""
    raw = _normalize_heading_title(title or "")
    for pat in [
        r"【圣骑士变体】",
        r"【\s*[A-Za-z0-9&]+\s*圣骑士变体】",
        r"[（(]圣武士变体[)）]",
        r"〔圣武士变体〕",
        r"［圣武士变体］",
        r"【圣武士变体】",
        r"（圣武士变体）",
        r"【[^】]*变体[^】]*】",
        r"〔[^〕]*变体[^〕]*〕",
        r"［[^］]*变体[^］]*］",
        r"（[^）]*变体[^）]*）",
    ]:
        raw = re.sub(pat, "", raw).strip()
    m = re.search(r"^[一-鿿]+", raw)
    return m.group(0) if m else None


def load_current_archetypes(chunks_path: Path) -> Dict[str, Dict[str, str]]:
    """从 chunks.jsonl 加载当前已识别变体：class_name -> {canonical_name -> abbr}。"""
    result: Dict[str, Dict[str, str]] = defaultdict(dict)
    with open(chunks_path, encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            if c.get("component_type") != "class_archetype":
                continue
            cls = c.get("class_name", "")
            title = c.get("title", "")
            abbr = c.get("book_abbreviation", "?")
            canonical = _canonical_chunk_archetype_name(title)
            if not canonical or not cls:
                continue
            if canonical in result[cls] and result[cls][canonical] != abbr:
                result[cls][canonical] = "?"
            else:
                result[cls][canonical] = abbr
    return result


def build_report(
    expected: Dict[str, Dict[str, str]],
    current: Dict[str, Dict[str, str]],
    book_lookup: Dict[str, Any],
) -> str:
    """生成 per-class diff 与汇总报告。"""
    lines = [
        "# 职业 Expected 变体基线生成报告",
        "",
        "生成规则：",
        "- 变体规范名为前导连续中文；",
        "- 来源书缩写优先取自基础变体页表格，其次聚合文件中的显式标记/文件名，判不准标 `?`；",
        "- 圣骑士直接复用 `verify_paladin_archetypes.py` 的 EXPECTED 字典；",
        "- diff 中：多出 = expected 有但 chunks 无；缺失 = chunks 有但 expected 无；来源不符 = 同名但来源不同。",
        "",
    ]

    total_classes = len(expected)
    total_variants = sum(len(v) for v in expected.values())
    high_confidence = sum(1 for cls in expected for abbr in expected[cls].values() if abbr != "?")
    uncertain = total_variants - high_confidence

    lines += [
        "## 汇总",
        "",
        f"- 职业总数：{total_classes}",
        f"- expected 变体总数：{total_variants}",
        f"- 高置信条目：{high_confidence}",
        f"- 待确认条目（?）：{uncertain}",
        "",
        "## 各职业变体概览",
        "",
        "| 职业 | 变体数 | 高置信 | 待确认 | 多出 | 缺失 | 来源不符 |",
        "|---|---|---|---|---|---|---|",
    ]

    per_class_details: List[Tuple[str, List[str]]] = []

    for cls in sorted(expected.keys()):
        exp_variants = expected[cls]
        cur_variants = current.get(cls, {})

        exp_names = set(exp_variants.keys())
        cur_names = set(cur_variants.keys())

        extra = sorted(exp_names - cur_names)
        missing = sorted(cur_names - exp_names)
        mismatch = sorted(
            name
            for name in exp_names & cur_names
            if exp_variants[name] != "?" and cur_variants[name] != "?" and exp_variants[name] != cur_variants[name]
        )

        high = sum(1 for abbr in exp_variants.values() if abbr != "?")
        uncertain_cls = len(exp_variants) - high

        lines.append(
            f"| {cls} | {len(exp_variants)} | {high} | {uncertain_cls} | {len(extra)} | {len(missing)} | {len(mismatch)} |"
        )

        detail_lines: List[str] = []
        detail_lines.append(f"### {cls}")
        detail_lines.append("")
        detail_lines.append(f"- expected 变体数：{len(exp_variants)}（高置信 {high}，待确认 {uncertain_cls}）")

        if exp_variants:
            detail_lines.append("- expected 清单：")
            uncertain_items = []
            confident_items = []
            for name in sorted(exp_variants.keys()):
                abbr = exp_variants[name]
                if abbr == "?":
                    uncertain_items.append(name)
                else:
                    confident_items.append(f"{name}: {abbr}")
            for item in confident_items:
                detail_lines.append(f"  - {item}")
            if uncertain_items:
                detail_lines.append("- 待确认清单（?）：")
                for name in uncertain_items:
                    detail_lines.append(f"  - {name}")

        if extra:
            detail_lines.append(f"- 多出（expected 有 / chunks 无）：{', '.join(extra)}")
        if missing:
            detail_lines.append(f"- 缺失（chunks 有 / expected 无）：{', '.join(missing)}")
        if mismatch:
            detail_lines.append("- 来源不符：")
            for name in mismatch:
                detail_lines.append(
                    f"  - {name}: expected {exp_variants[name]} vs chunks {cur_variants[name]}"
                )
        if not (extra or missing or mismatch):
            detail_lines.append("- 与当前 chunks 初步匹配一致。")

        detail_lines.append("")
        per_class_details.append((cls, detail_lines))

    lines += ["", "## 明细", ""]
    for _, detail_lines in per_class_details:
        lines.extend(detail_lines)

    return "\n".join(lines)


def main() -> None:
    if not CHUNKS_PATH.exists():
        print(f"ERROR: chunks.jsonl 不存在: {CHUNKS_PATH}", file=sys.stderr)
        print("  请先跑 python3 vectorization_prep_profession.py", file=sys.stderr)
        sys.exit(2)

    book_lookup = load_abbreviation_table(SOURCE_BOOK_ABBR_MD)
    md_mapping = load_md_mapping(MD_MAPPING_JSON)
    known_classes = discover_known_classes(PROFESSION_INPUT_DIR)
    leaf_dirs = _leaf_directory_names(PROFESSION_INPUT_DIR)

    target_classes = collect_target_classes(CHUNKS_PATH, leaf_dirs)
    if not target_classes:
        print("ERROR: 未从 chunks.jsonl 识别到目标职业", file=sys.stderr)
        sys.exit(1)

    # 圣武士是圣骑士的旧译/别名，统一到圣骑士
    if "圣武士" in target_classes:
        target_classes.discard("圣武士")
        target_classes.add("圣骑士")

    print(f"目标职业数：{len(target_classes)}")

    print("解析变体主表...")
    base_page_variants = build_archetype_masters(
        PROFESSION_INPUT_DIR, md_mapping, book_lookup, known_classes
    )

    print("扫描聚合变体文件...")
    variant_to_class = build_variant_to_class_map(CHUNKS_PATH)
    scanned = scan_aggregate_variant_files(
        PROFESSION_INPUT_DIR, md_mapping, book_lookup, known_classes, variant_to_class
    )

    expected = merge_expected(target_classes, base_page_variants, scanned)

    # 注入圣骑士权威基线
    expected["圣骑士"] = dict(PALADIN_EXPECTED)

    # 写 JSON
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for cls in sorted(expected.keys()):
        filename = _safe_filename(cls) + ".json"
        (OUTPUT_DIR / filename).write_text(
            json.dumps(expected[cls], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    # 写报告
    current = load_current_archetypes(CHUNKS_PATH)
    report = build_report(expected, current, book_lookup)
    (OUTPUT_DIR / "生成报告.md").write_text(report, encoding="utf-8")

    print(f"输出目录：{OUTPUT_DIR}")
    print(f"职业数：{len(expected)}")
    print(f"expected 变体总数：{sum(len(v) for v in expected.values())}")
    print(f"高置信条目：{sum(1 for cls in expected for abbr in expected[cls].values() if abbr != '?')}")
    print(f"待确认条目：{sum(1 for cls in expected for abbr in expected[cls].values() if abbr == '?')}")


if __name__ == "__main__":
    main()
