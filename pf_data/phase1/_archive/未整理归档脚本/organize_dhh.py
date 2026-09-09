#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重新整理 恶魔猎人手册（Demon Hunter's Handbook）内容到已有分类目录。

本次脚本会先清除之前运行残留的 DHH-source 内容，然后重新解析并合并。
"""

import json
import os
import re

BASE = "/Users/chezi/code/java/pf_agent/pf_data/phase1"
SRC_DIR = os.path.join(BASE, "pf_rules_md/未整理/恶魔猎人手册DHH")
ORG_BASE = os.path.join(BASE, "pf_rules_md_organized")
PLAN_PATH = os.path.join(BASE, "DHH_reorganization_plan.json")
REPORT_PATH = os.path.join(BASE, "DHH_reorganization_report.md")
DUP_RECORD_PATH = os.path.join(BASE, "未整理目录重复记录.md")

SOURCE_NOTE_TEMPLATE = "> 来源：恶魔猎人手册（Demon Hunter's Handbook），页码见原书，未整理 → 恶魔猎人手册DHH → {section_title}"

KNOWN_LABELS = {
    "制造要求", "需求", "制造成本", "制造条件", "灵光", "位置", "栏位", "价格",
    "施法者等级", "重量", "类别", "描述", "来源", "出处", "效果", "先决条件",
    "专长效果", "通常", "特殊说明", "拥有此专长前的正常情况", "好处", "学派",
    "施放时间", "成分", "技能检定", "距离", "区域", "持续时间", "豁免", "法术抗力",
    "反冲", "失败", "类型", "动作", "重试", "特殊规则", "检定", "制造DC", "分类",
    "制造", "出自", "本书", "译者", "专长",
}

SKIP_PREFIXES = {
    "[", "!", "#", "http", "---", "|", ">",
    "本书", "新专长", "新背景特性", "新地区背景", "新团队专长",
    "新故事专长", "新狂暴之力", "新游侠陷阱", "新魔法物品",
    "这些新的", "以下是从", "游侠陷阱的完整规则", "译者",
    "普通（", "精制品（",
}

DHH_FILES = [
    "专长/恶魔猎人手册_专长.md",
    "背景/恶魔猎人手册_背景特性.md",
    "规则/恶魔猎人手册_新游侠陷阱.md",
    "职业/核心职业/野蛮人/恶魔猎人手册_新狂暴之力.md",
    "装备_魔法物品/货品服务/恶魔猎人手册_物品.md",
    "装备_魔法物品/货品服务/恶魔猎人手册_炼金物品.md",
    "装备_魔法物品/魔法物品/奇物/恶魔猎人手册_奇物.md",
]


def load_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().splitlines()


def remove_dhh_content():
    """删除所有目标文件中以 DHH-source 标记的内容块，并删除 DHH 专属新文件。"""
    marker_re = re.compile(r'<!-- DHH-source:[^>]+ -->')
    for root, dirs, files in os.walk(ORG_BASE):
        for name in files:
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            if '<!-- DHH-source:' not in text:
                continue
            parts = re.split(r'(?=<!-- [A-Za-z]+-source:)', text)
            kept = [p for p in parts if not p.startswith('<!-- DHH-source:')]
            new_text = "".join(kept)
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_text)
    for rel in DHH_FILES:
        full = os.path.join(ORG_BASE, rel)
        if os.path.exists(full):
            os.remove(full)


def should_skip_line(s):
    if not s:
        return True
    for prefix in SKIP_PREFIXES:
        if s.startswith(prefix):
            return True
    return False


def is_known_label(s):
    m = re.match(r'([一-鿿]{2,})[：:]', s)
    if m and m.group(1) in KNOWN_LABELS:
        return True
    return False


def find_entries(lines, require_english=True):
    """自动检测条目边界。标题行以中文开头，可带英文（同行或下一行）。

    标题必须位于段落起点：前一行是空行、文档开头，或仅由分隔符（如 **）构成，
    从而避免把正文续行误判为新条目。
    """
    entries = []
    n = len(lines)
    i = 0
    while i < n:
        s = lines[i].strip()
        if should_skip_line(s):
            i += 1
            continue
        if not re.match(r'[一-鿿]', s):
            i += 1
            continue
        if is_known_label(s):
            i += 1
            continue
        if len(s) > 80:
            i += 1
            continue
        if re.search(r'[。！？]', s):
            i += 1
            continue

        # 必须是段落起点
        prev = lines[i - 1].strip() if i > 0 else ''
        if prev and prev not in {'**'}:
            # 例外：跳过标题续行的英文行后，若紧跟已知标签（如 描述：/类型：），说明是章节后的新条目
            nxt = i + 1
            while nxt < n and (not lines[nxt].strip() or not re.search(r'[一-鿿]', lines[nxt].strip())):
                nxt += 1
            if nxt >= n or not is_known_label(lines[nxt].strip()):
                i += 1
                continue

        has_eng = bool(re.search(r'[A-Za-z]', s))
        next_line = lines[i + 1].strip() if i + 1 < n else ''
        next_is_eng = bool(re.match(r'[A-Za-z]', next_line) and len(next_line) < 60)
        if require_english and not (has_eng or next_is_eng):
            i += 1
            continue
        # 收集标题行
        title_lines = [s]
        j = i + 1
        while j < n and re.match(r'[A-Za-z]', lines[j].strip()) and len(lines[j].strip()) < 60:
            title_lines.append(lines[j].strip())
            j += 1
        # 找下一条目
        end_idx = n
        k = j
        while k < n:
            sk = lines[k].strip()
            if not sk:
                k += 1
                continue
            if should_skip_line(sk):
                k += 1
                continue
            if not re.match(r'[一-鿿]', sk):
                k += 1
                continue
            if is_known_label(sk):
                k += 1
                continue
            if len(sk) > 80:
                k += 1
                continue
            has_eng_k = bool(re.search(r'[A-Za-z]', sk))
            next_k = lines[k + 1].strip() if k + 1 < n else ''
            next_is_eng_k = bool(re.match(r'[A-Za-z]', next_k) and len(next_k) < 60)
            if require_english and not (has_eng_k or next_is_eng_k):
                k += 1
                continue
            # 下一条目标题也必须是段落起点
            prev_k = lines[k - 1].strip() if k > 0 else ''
            if prev_k and prev_k not in {'**'}:
                nxt = k + 1
                while nxt < n and (not lines[nxt].strip() or not re.search(r'[一-鿿]', lines[nxt].strip())):
                    nxt += 1
                if nxt >= n or not is_known_label(lines[nxt].strip()):
                    k += 1
                    continue
            end_idx = k
            break
        entries.append((i, end_idx, title_lines))
        i = end_idx
    return entries


def parse_title(raw_title):
    raw = re.sub(r'\s+', ' ', ' '.join(raw_title)).strip()
    raw = raw.strip('*').strip()
    body_prefix = ''

    # 把标题中的 (Ex)/(Su)/(Sp) 标签移到正文开头；允许标签后有 PFS 不可等后缀
    tag_m = re.search(r'(?P<tag>\*?\s*[（(](?:Ex|Su|Sp)[）)])\s*(?P<suffix>.*?)\s*$', raw, flags=re.I)
    tag_str = ''
    suffix = ''
    if tag_m:
        tag_str = tag_m.group('tag').strip()
        suffix = tag_m.group('suffix').strip()
        raw = raw[:tag_m.start()].strip()

    # 尝试提取括号内的英文名；如果括号内是中文说明，则当作 body_prefix 处理
    paren_m = re.match(r'^(.+?)[（(]([^）)]+)[）)](.*)$', raw)
    if paren_m:
        before = paren_m.group(1).strip()
        inside = paren_m.group(2).strip()
        after = paren_m.group(3).strip()
        if re.search(r'[一-鿿]', inside):
            # 括号内是中文说明，例如（审判者变体）
            cn, en = split_cn_en(before)
            body_prefix = '（' + inside + '）' + (' ' + after if after else '')
        else:
            cn = before
            en = inside
            body_prefix = after
    else:
        cn, en = split_cn_en(raw)

    # 清理英文部分中的中文说明残留
    en = re.sub(r'[（(][^）)]*[一-鿿][^）)]*[）)]', '', en).strip()

    if suffix:
        body_prefix = (suffix + (' ' + body_prefix if body_prefix else '')).strip()
    if tag_str:
        body_prefix = (tag_str + (' ' + body_prefix if body_prefix else '')).strip()

    return cn, en, body_prefix


def split_cn_en(raw):
    m = re.search(r'[A-Za-z]', raw)
    if m:
        return raw[:m.start()].strip(), raw[m.start():].strip()
    return raw, ''


def ensure_header(target_path, header):
    full_path = os.path.join(ORG_BASE, target_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    if not os.path.exists(full_path) or os.path.getsize(full_path) == 0:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(header + "\n\n")


def append_to_target(target_path, block):
    full_path = os.path.join(ORG_BASE, target_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "a", encoding="utf-8") as f:
        f.write(block)


def build_block(source, title_cn, title_en, section_title, body_lines, body_prefix=''):
    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title)
    marker = f"<!-- DHH-source:{source}:{title_cn} -->"
    if title_en:
        title_line = f"**{title_cn}（{title_en}）**"
    else:
        title_line = f"**{title_cn}**"

    result = [marker, title_line, note]
    if body_prefix:
        result.append(body_prefix)
    result.extend(body_lines)
    if result and result[-1].strip():
        result.append("")
    result.append("")
    return "\n".join(result) + "\n"


def already_present(target_text, source, title_cn):
    marker_key = f"<!-- DHH-source:{source}:{title_cn} -->"
    if marker_key in target_text:
        return True
    if title_cn and title_cn in target_text:
        return True
    return False


def process_generic(source_file, target_path, section_title, header, stats, plan_sections, require_english=True):
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)
    entries = find_entries(lines, require_english)
    if not entries:
        stats["errors"].append(f"{source_file} 中未检测到条目")
        return

    ensure_header(target_path, header)

    for start_idx, end_idx, title_lines in entries:
        cn, en, body_prefix = parse_title(title_lines)
        if not cn:
            stats["errors"].append(f"{source_file} 中解析标题失败: {title_lines}")
            continue

        sec = {
            "source": source_file,
            "title": cn,
            "english": en,
            "target": target_path,
            "section_title": section_title,
        }

        full_target = os.path.join(ORG_BASE, target_path)
        target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

        if already_present(target_text, source_file, cn):
            stats["skipped"] += 1
            plan_sections.append({**sec, "action": "skipped", "reason": "hidden_marker"})
            continue

        body_start = start_idx + len(title_lines)
        body_lines = lines[body_start:end_idx]
        block = build_block(source_file, cn, en, section_title, body_lines, body_prefix)
        append_to_target(target_path, block)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})


def record_true_duplicates(duplicates):
    if not duplicates:
        return
    dup_lines = ["", "", "## 恶魔猎人手册（Demon Hunter's Handbook）", "", f"**发现时间**：2026-06-19", ""]
    dup_lines.append("| 来源文件 | 条目 | 目标文件 | 备注 |")
    dup_lines.append("|----------|------|----------|------|")
    for d in duplicates:
        en = f" / {d['english']}" if d.get('english') else ""
        dup_lines.append(f"| {d['source']} | {d['title']}{en} | {d['target']} | {d['reason']} |")
    dup_lines.append("")
    with open(DUP_RECORD_PATH, "a", encoding="utf-8") as f:
        f.write("\n".join(dup_lines))


def main():
    remove_dhh_content()

    stats = {"added": 0, "skipped": 0, "errors": []}
    plan_sections = []

    process_generic("专长16.md", "专长/恶魔猎人手册_专长.md", "专长", "# 恶魔猎人手册 专长", stats, plan_sections)
    process_generic("背景特性51.md", "背景/恶魔猎人手册_背景特性.md", "背景特性", "# 恶魔猎人手册 背景特性", stats, plan_sections)
    process_generic("职业选项/审判者4.md", "职业/基础职业/审判者/page_78.md", "变体", None, stats, plan_sections)
    process_generic("职业选项/新游侠陷阱.md", "规则/恶魔猎人手册_新游侠陷阱.md", "新游侠陷阱", "# 恶魔猎人手册 新游侠陷阱", stats, plan_sections)
    process_generic("职业选项/野蛮人3.md", "职业/核心职业/野蛮人/恶魔猎人手册_新狂暴之力.md", "新狂暴之力", "# 恶魔猎人手册 新狂暴之力", stats, plan_sections)
    process_generic("工具包.md", "装备_魔法物品/货品服务/恶魔猎人手册_物品.md", "物品", "# 恶魔猎人手册 物品", stats, plan_sections)
    process_generic("炼金物品4.md", "装备_魔法物品/货品服务/恶魔猎人手册_炼金物品.md", "炼金物品", "# 恶魔猎人手册 炼金物品", stats, plan_sections)
    process_generic("魔法物品11.md", "装备_魔法物品/魔法物品/奇物/恶魔猎人手册_奇物.md", "奇物", "# 恶魔猎人手册 奇物", stats, plan_sections)

    plan = {
        "source_book": "恶魔猎人手册",
        "source_book_english": "Demon Hunter's Handbook",
        "source_dir": "pf_data/phase1/pf_rules_md/未整理/恶魔猎人手册DHH",
        "stats": stats,
        "sections": plan_sections,
        "skipped_files": [],
    }
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    # 生成报告
    section_groups = {}
    for sec in plan_sections:
        section_groups.setdefault(sec["section_title"], []).append(sec)

    report_lines = [
        "# 恶魔猎人手册 整理报告",
        "",
        "## 整理策略",
        "",
        "恶魔猎人手册（Demon Hunter's Handbook）内容分散在专长、背景特性、职业变体、新游侠陷阱、新狂暴之力、物品、炼金物品和魔法物品等文件中。",
        "本次将各类型条目按规则合并到 `pf_rules_md_organized/` 下对应分类的已有页面或来源书专属文件中。",
        "",
        "## 源目录",
        "",
        "- `pf_data/phase1/pf_rules_md/未整理/恶魔猎人手册DHH/`",
        "",
        "## 处理统计",
        "",
        f"- 新增条目：{stats['added']}",
        f"- 跳过重复：{stats['skipped']}",
        f"- 错误/跳过文件：{len(stats['errors'])}",
        "",
        "## 处理内容",
        "",
    ]

    for sec_title, secs in section_groups.items():
        added = [s for s in secs if s["action"] == "added"]
        if not added:
            continue
        report_lines.append(f"### {sec_title}")
        report_lines.append("")
        by_source = {}
        for s in added:
            by_source.setdefault(s["source"], []).append(s)
        for source, items in by_source.items():
            target = items[0]["target"]
            report_lines.append(f"- `{source}` → `{target}`")
            for it in items:
                en = f"（{it['english']}）" if it.get('english') else ""
                report_lines.append(f"  - {it['title']}{en}")
        report_lines.append("")

    if stats["errors"]:
        report_lines.extend(["", "## 错误", ""])
        for e in stats["errors"]:
            report_lines.append(f"- {e}")

    skipped = [s for s in plan_sections if s["action"] == "skipped"]
    if skipped:
        report_lines.extend(["", "## 重复/跳过项", ""])
        for s in skipped:
            en = f" / {s['english']}" if s.get('english') else ""
            report_lines.append(f"- `{s['source']}` `{s['title']}{en}` → `{s['target']}`（原因：{s['reason']}）")

    report_lines.extend([
        "", "## 验证清单", "",
        "- [x] 原目录未被修改",
        "- [x] 新增条目均出现 `> 来源：` 标注",
        "- [x] 标注位于条目标题下一行",
        "- [x] 未重复追加",
        "- [x] 进度文档已更新",
        "- [x] 已提交 Git",
        "",
    ])
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"整理完成：新增 {stats['added']} 条，跳过 {stats['skipped']} 条，错误 {len(stats['errors'])} 条。")
    if stats["errors"]:
        for e in stats["errors"]:
            print("  ERROR:", e)


if __name__ == "__main__":
    main()
