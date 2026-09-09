#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 冒险者指南AG 职业变体聚合文件按职业拆分到对应职业目录。

输入：pf_rules_md_organized/职业/冒险者指南AG_变体.md
输出：职业/<分类>/<职业>/冒险者指南AG_<职业>变体.md

拆分规则：
- 按 hidden_marker 拆分成源文件块；
- 在每个块内检测二级变体标题（同一源文件含多个变体的情况）；
- 根据标题中的职业名映射到目标目录；
- 保留 hidden_marker 与来源标注格式。
"""

import json
import os
import re

BASE = "/Users/chezi/code/java/pf_agent/pf_data/phase1"
AGGREGATE_PATH = os.path.join(BASE, "pf_rules_md_organized/职业/冒险者指南AG_变体.md")
ORG_BASE = os.path.join(BASE, "pf_rules_md_organized")
PLAN_PATH = os.path.join(BASE, "AG_reorganization_plan.json")
REPORT_PATH = os.path.join(BASE, "AG_reorganization_report.md")

# 已知多变体源文件及其关键字（用于解决跨行/格式异常导致的识别失败）
MULTI_VARIANT_TITLES = {
    "page_1384.md": ["灵辅修士", "巨人伏击客", "附魂唤师"],
    "page_1385.md": ["泰尔曼多圣从者", "塔玛多信嗣"],
    "page_1387.md": ["旭骑兵", "宁静德鲁伊", "风暴德鲁伊"],
    "page_1388.md": ["带头大哥", "厚颜妄徒"],
    "page_1390.md": ["雷斯兰暴徒", "花间浪客"],
    "page_1392.md": ["铃花浚洫客", "毒爪"],
    "page_1395.md": ["魔符战士", "魔武者"],
}

# 源文件 → 职业名（标题中未带职业信息时的 fallback）
SOURCE_CLASS = {
    "page_1382.md": "牧师",
    "page_1383.md": "武僧",
    "page_1384.md": "野蛮人",
    "page_1385.md": "圣武士",
    "page_1386.md": "骑士",
    "page_1387.md": "德鲁伊",
    "page_1388.md": "吟游诗人",
    "page_1389.md": "战士",
    "page_1390.md": "游荡剑客",
    "page_1391.md": "秘学士",
    "page_1392.md": "盗贼",
    "page_1393.md": "侠客",
    "page_1394.md": "法师",
    "page_1395.md": "魔战士",
    "唤魂师2.md": "唤魂师",
    "猎人1.md": "猎人",
    "血脉狂怒者2.md": "血脉狂怒者",
    "通灵者2.md": "通灵者",
}

SOURCE_NOTE_TEMPLATE = "> 来源：冒险者指南（Adventurer's Guide）AG，页码见原书，未整理 → 冒险者指南AG → 职业变体/{source_file}"

# 职业名 → 目标文件相对路径（§4.1：追加到该职业已有的职业变体页面）
CLASS_TARGET = {
    "牧师": "职业/核心职业/牧师/page_41.md",
    "武僧": "职业/核心职业/武僧/page_52.md",
    "野蛮人": "职业/核心职业/野蛮人/page_35.md",
    "圣武士": "职业/核心职业/圣骑士/page_55.md",
    "骑士": "职业/基础职业/骑将/page_74.md",
    "德鲁伊": "职业/核心职业/德鲁伊/page_45.md",
    "吟游诗人": "职业/核心职业/吟游诗人/page_38.md",
    "战士": "职业/核心职业/战士/page_49.md",
    "游荡剑客": "职业/混合职业/游荡剑客/page_120.md",
    "秘学士": "职业/异能冒险（Occult Adventures）/秘学士/page_266.md",
    "盗贼": "职业/核心职业/盗贼/page_22.md",
    "侠客": "职业/极限诡道/侠客/page_346.md",
    "法师": "职业/核心职业/法师/page_67.md",
    "魔战士": "职业/基础职业/魔战士/page_82.md",
    "唤魂师": "职业/异能冒险（Occult Adventures）/唤魂师/page_270.md",
    "猎人": "职业/混合职业/猎人/page_104.md",
    "血脉狂怒者": "职业/混合职业/血脉狂怒者/page_98.md",
    "通灵者": "职业/异能冒险（Occult Adventures）/通灵者/page_262.md",
}


def detect_class(title, source_file=None, marker_title=None):
    """从标题中检测职业名，返回 (class_name, matched_text)。

    标题中无法识别时，依次使用 marker_title、SOURCE_CLASS 作为 fallback。
    优先匹配长职业名，避免"魔战士"被误识别为"战士"。
    """
    candidates = [title]
    if marker_title:
        candidates.append(marker_title)
    for cand in candidates:
        # 按职业名长度降序，优先匹配"魔战士"等复合名
        for class_name in sorted(CLASS_TARGET, key=lambda x: -len(x)):
            patterns = [
                rf"[（(【\[]\s*{re.escape(class_name)}\s*变体\s*[）)】\]]",
                rf"{re.escape(class_name)}\s*变体",
            ]
            for pat in patterns:
                m = re.search(pat, cand)
                if m:
                    return class_name, m.group(0)
    if source_file and source_file in SOURCE_CLASS:
        return SOURCE_CLASS[source_file], f"（{SOURCE_CLASS[source_file]}变体）"
    return None, None


def normalize_subtitle_line(line):
    """将源文件内的子变体标题行清洗为聚合标题格式。

    处理以下情况：
    - `**巨人伏击客**（GIANT STALKER，野蛮人变体）  `
      → `## 巨人伏击客（GIANT STALKER，野蛮人变体）`
    - `**附魂唤师 Geminate Invoker \n【野蛮人变体】**`
      → `## 附魂唤师 Geminate Invoker（野蛮人变体）`
    - `**厚颜妄徒**（Brazen Deceiver，吟游诗人变体）BRAZEN DECEIVER ...`
      → `## 厚颜妄徒（Brazen Deceiver，吟游诗人变体）`
    """
    s = line.strip()
    # 去掉所有 ** 标记
    s = s.replace("**", "")
    s = s.strip()
    # 统一括号为中文圆括号
    s = s.replace("【", "（").replace("】", "）")
    s = s.replace("［", "（").replace("］", "）")
    s = s.replace("(", "（").replace(")", "）")
    # 截断到第一个"变体）"之后，去掉尾部重复英文
    m = re.search(r"变体[）)]", s)
    if m:
        s = s[: m.end()]
    s = s.strip()
    return f"## {s}"


def is_variant_title(line):
    """判断一行是否为子变体标题。"""
    s = line.strip()
    if not s.startswith("**"):
        return False
    if "变体" not in s:
        return False
    # 取第一个 **...** 片段
    m = re.match(r"\*\*(.+?)\*\*", s)
    if not m:
        return False
    inner_segment = m.group(1).strip()
    # 排除能力描述，如 `**能力名（Name，Ex）：**`（片段以冒号结尾）
    if inner_segment.endswith("：") or inner_segment.endswith(":"):
        return False
    # 排除 `**能力名（Su）：** 正文`（片段后立即跟冒号）
    after = s[m.end():].strip()
    if after.startswith("：") or after.startswith(":"):
        return False
    # 排除整行以冒号结尾的情况
    if re.search(r"[：:]$", s):
        return False
    # 排除纯英文 **
    if s.count("**") < 2:
        return False
    # 长度限制
    if len(s) > 200:
        return False
    return True


def split_aggregate(content):
    """将聚合文件内容拆分为源文件块。

    返回 [(marker_line, source_file, marker_title, block_lines), ...]。
    marker 格式：<!-- AG-source:职业变体/<filename>:<title> -->
    """
    marker_re = re.compile(r"(<!-- AG-source:职业变体/([^:]+):(.+?) -->)")
    parts = marker_re.split(content)
    # parts: [prefix, marker1, source_file1, marker_title1, block1, ...]
    result = []
    i = 1
    while i < len(parts):
        marker = parts[i]
        source_file = parts[i + 1]
        marker_title = parts[i + 2]
        block = parts[i + 3] if i + 3 < len(parts) else ""
        result.append((marker, source_file, marker_title, block))
        i += 4
    return result


def split_block_into_variants(marker, source_file, block):
    """将一个源文件块拆分为单个变体条目。

    返回 [(title, lines), ...]。
    """
    lines = block.splitlines()
    # 第一个标题行通常是 `## 标题`
    first_title = None
    start_idx = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("## "):
            first_title = s[3:].strip()
            start_idx = i + 1
            break

    variants = []
    if first_title:
        variants.append((first_title, lines[start_idx:]))

    # 继续扫描后续子标题
    current_idx = 0
    current_title = first_title
    current_lines = []
    for i, line in enumerate(lines[start_idx:], start=start_idx):
        if is_variant_title(line):
            # 保存前一个变体
            if current_title:
                variants.append((current_title, current_lines))
            current_title = normalize_subtitle_line(line)[3:]  # 去掉 ##
            current_lines = []
        else:
            current_lines.append(line)
    if current_title and current_lines:
        variants.append((current_title, current_lines))

    # 如果前面已经有 first_title 为第一个，去重
    if first_title and variants and variants[0][0] == first_title:
        # 合并第一个变体的正文
        # 实际上 first_title 对应的 lines 是 start_idx 之后的所有行，包含了子变体
        # 这种简单处理会重复，需要更精确地重建
        pass

    # 重新精确拆分：基于子标题索引
    return split_block_precisely(marker, source_file, block)


def merge_bold_titles(lines):
    """合并跨行的加粗标题，返回 (logical_line, original_start_index) 列表。

    变体标题偶尔跨行，例如：
        ['**附魂唤师 Geminate Invoker ', '【野蛮人变体】**']
    合并条件：当前行以 ** 开头但未闭合，且下一行包含"变体"并以 ** 结尾。
    其他普通加粗能力名（如 **能力名（Name，\nEx）：**）不会被合并。
    """
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if (
            s.startswith("**")
            and "**" not in s[2:]
            and i + 1 < len(lines)
        ):
            next_line = lines[i + 1].strip()
            if "变体" in next_line and next_line.endswith("**"):
                merged = [line.rstrip(), lines[i + 1].rstrip()]
                logical = " ".join(merged)
                result.append((logical, i))
                i += 2
                continue
        result.append((line, i))
        i += 1
    return result


def split_block_explicitly(marker, source_file, block):
    """基于 MULTI_VARIANT_TITLES 显式关键字拆分块。

    返回 [(title, body_lines), ...]；若源文件未在映射中则返回 None。
    每个关键字只取第一个匹配（跳过正文中的重复标题）。
    对显式关键字放宽"变体"限制，以兼容跨行/格式异常的标题。
    """
    if source_file not in MULTI_VARIANT_TITLES:
        return None
    keywords = MULTI_VARIANT_TITLES[source_file]
    lines = block.splitlines()
    logical = merge_bold_titles(lines)

    positions = []
    seen_kws = set()
    for i, (line, _orig_idx) in enumerate(logical):
        s = line.strip()
        if not (s.startswith("**") or s.startswith("## ")):
            continue
        for kw in keywords:
            if kw in s and kw not in seen_kws:
                positions.append((i, line))
                seen_kws.add(kw)
                break

    if not positions:
        return None

    positions.sort(key=lambda x: x[0])
    variants = []
    for idx, (start, title_line) in enumerate(positions):
        end = positions[idx + 1][0] if idx + 1 < len(positions) else len(logical)
        s = title_line.strip()
        if s.startswith("## "):
            title = s[3:]
        else:
            title = normalize_subtitle_line(title_line)[3:]
        # 若标题因格式异常缺失职业变体标注，补充 SOURCE_CLASS 中的职业
        if "变体" not in title and source_file in SOURCE_CLASS:
            class_name = SOURCE_CLASS[source_file]
            title = f"{title}（{class_name}变体）"
        body = [logical[k][0] for k in range(start + 1, end)]
        variants.append((title, body))
    return variants


def split_block_precisely(marker, source_file, block):
    """更精确地按标题索引拆分块。"""
    lines = block.splitlines()
    logical = merge_bold_titles(lines)

    # 找到所有标题行位置
    title_indices = []
    for i, (line, original_idx) in enumerate(logical):
        s = line.strip()
        if s.startswith("## "):
            title_indices.append((i, s[3:].strip(), "heading"))
        elif is_variant_title(line):
            title_indices.append((i, normalize_subtitle_line(line)[3:].strip(), "bold"))

    if not title_indices:
        return []

    variants = []
    for idx, (start, title, kind) in enumerate(title_indices):
        end = title_indices[idx + 1][0] if idx + 1 < len(title_indices) else len(logical)
        # 若标题因格式异常缺失职业变体标注，补充 SOURCE_CLASS 中的职业
        if "变体" not in title and source_file in SOURCE_CLASS:
            class_name = SOURCE_CLASS[source_file]
            title = f"{title}（{class_name}变体）"
        # 正文使用逻辑行，但去除标题行本身
        body_logical = [logical[k][0] for k in range(start + 1, end)]
        variants.append((title, body_logical))
    return variants


def clean_body(body_lines, title, source_file):
    """清理正文：去掉原始来源标注、URL、译者、分隔符和重复标题行。"""
    # 取标题的中文名部分作为 key（去掉英文括号和英文名）
    title_key = title.split("（")[0].split("(")[0].strip().lower()
    if " " in title_key:
        title_key = title_key.split()[0]
    title_key = title_key.strip("*")

    skip_patterns = [
        re.compile(r"^> 来源："),
        re.compile(r"^\[http://"),
        re.compile(r"^译者[:：]"),
        re.compile(r"^来自 \*Adventurer['’]s Guide"),
        re.compile(r"资料来源"),
        re.compile(r"^\*+资料来源"),
        re.compile(r"【AG】"),
        re.compile(r"^-{3,}$"),
    ]
    result = []
    for line in body_lines:
        s = line.strip()
        if any(p.search(s) for p in skip_patterns):
            continue
        # 跳过与标题重复的加粗标题行（含变体关键字）
        if s.startswith("**") and "变体" in s and title_key and title_key in s.lower():
            continue
        result.append(line)
    return result


def build_block(marker, source_file, title, body_lines):
    """生成追加到目标文件的块。"""
    note = SOURCE_NOTE_TEMPLATE.format(source_file=source_file)
    cleaned = clean_body(body_lines, title, source_file)
    lines = [marker]
    lines.append(f"## {title}")
    lines.append(note)
    # 去掉正文开头的空行
    while cleaned and cleaned[0].strip() == "":
        cleaned = cleaned[1:]
    lines.extend(cleaned)
    # 确保末尾有两个空行
    while len(lines) >= 2 and lines[-1].strip() == "" and lines[-2].strip() == "":
        lines.pop()
    if lines and lines[-1].strip() != "":
        lines.append("")
    lines.append("")
    return "\n".join(lines) + "\n"


def detect_newline(path):
    """检测目标文件换行风格（§4.4），返回 '\r\n' 或 '\n'。"""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    with open(path, "rb") as f:
        raw = f.read()
    if b"\r\n" in raw:
        return "\r\n"
    return "\n"


def write_text_preserve_nl(path, text, mode="a"):
    """按目标文件既有换行风格写入文本，避免 diff 噪声。"""
    nl = detect_newline(path) or "\n"
    # 先归一化再转目标风格，避免重复 \r
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", nl)
    with open(path, mode, encoding="utf-8", newline="") as f:
        f.write(text)


def ensure_header(target_path, header, org_base=ORG_BASE):
    full_path = os.path.join(org_base, target_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    if not os.path.exists(full_path) or os.path.getsize(full_path) == 0:
        write_text_preserve_nl(full_path, header + "\n\n", mode="w")


def split_aggregate_file(aggregate_path, org_base=ORG_BASE):
    """将聚合文件拆分为按职业分类的目标文件。

    返回 (stats, plan_sections)，不写入计划/报告文件。
    """
    if not os.path.exists(aggregate_path):
        raise FileNotFoundError(f"聚合文件不存在: {aggregate_path}")

    with open(aggregate_path, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = split_aggregate(content)
    stats = {"added": 0, "skipped": 0, "errors": []}
    plan_sections = []
    target_contents = {}  # target_path -> accumulated content

    for marker, source_file, marker_title, block in blocks:
        variants = split_block_explicitly(marker, source_file, block)
        if variants is None:
            variants = split_block_precisely(marker, source_file, block)
        for title, body_lines in variants:
            class_name, _ = detect_class(title, source_file, marker_title)
            if not class_name:
                msg = f"无法识别职业: {source_file} -> {title}"
                stats["errors"].append(msg)
                continue

            target_path = CLASS_TARGET[class_name]
            header = f"# 冒险者指南AG {class_name}变体"
            ensure_header(target_path, header, org_base=org_base)

            # 基于标题生成稳定的子标题 marker
            short_title = title
            for sep in ["（", "(", " ", "**"]:
                if sep in short_title:
                    short_title = short_title.split(sep)[0]
            short_title = short_title.strip("* ")
            sub_marker = f"<!-- AG-source:职业变体/{source_file}:{short_title} -->"

            full_target = os.path.join(org_base, target_path)
            if target_path not in target_contents:
                target_contents[target_path] = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

            if sub_marker in target_contents[target_path]:
                stats["skipped"] += 1
                plan_sections.append({
                    "source": source_file,
                    "title": title,
                    "target": target_path,
                    "action": "skipped",
                    "reason": "hidden_marker",
                })
                continue

            block_text = build_block(sub_marker, source_file, title, body_lines)
            existing = target_contents[target_path]
            if existing and not existing.endswith("\n"):
                block_text = "\n" + block_text
            write_text_preserve_nl(full_target, block_text, mode="a")
            target_contents[target_path] += block_text.replace("\r\n", "\n")
            stats["added"] += 1
            plan_sections.append({
                "source": source_file,
                "title": title,
                "target": target_path,
                "action": "added",
            })

    return stats, plan_sections


def main():
    stats, plan_sections = split_aggregate_file(AGGREGATE_PATH, org_base=ORG_BASE)
    print(f"找到 {len(plan_sections)} 个变体条目")

    # 更新计划文件
    if os.path.exists(PLAN_PATH):
        with open(PLAN_PATH, "r", encoding="utf-8") as f:
            plan = json.load(f)
    else:
        plan = {"source_book": "冒险者指南AG", "source_book_english": "Adventurer's Guide"}
    plan["archetype_split"] = {
        "stats": stats,
        "sections": plan_sections,
    }
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    print(f"\n拆分完成：新增 {stats['added']} 条，跳过 {stats['skipped']} 条，错误 {len(stats['errors'])} 条")
    if stats["errors"]:
        for e in stats["errors"]:
            print("  ERROR:", e)


if __name__ == "__main__":
    main()
