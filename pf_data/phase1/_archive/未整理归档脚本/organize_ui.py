#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 极限诡道UI（Ultimate Intrigue）变体/职业选项到职业分类目录。

原则：
- 仅追加到 pf_rules_md_organized/ 下已有分类目录的对应文件。
- 每个条目在标题下一行标注来源。
- 使用隐藏标记去重；已存在的条目跳过并记录为重复。
- 不修改原 pf_rules_md/ 目录。
"""

import json
import os
import re

BASE = "/Users/chezi/code/java/pf_agent/pf_data/phase1"
SRC_DIR = os.path.join(BASE, "pf_rules_md/未整理/极限诡道UI/变体_职业选项")
ORG_BASE = os.path.join(BASE, "pf_rules_md_organized")
PLAN_PATH = os.path.join(BASE, "UI_reorganization_plan.json")
REPORT_PATH = os.path.join(BASE, "UI_reorganization_report.md")
DUP_RECORD_PATH = os.path.join(BASE, "未整理目录重复记录.md")

SOURCE_NOTE_TEMPLATE = "> 来源：极限诡道（Ultimate Intrigue）UI，页码见原书，未整理 → 极限诡道UI → 变体/职业选项 → {cls}"

# 每个 source 文件中的条目，按出现顺序排列。
# start_marker 用于在原文中定位条目起始行（取包含该子串的第一行）。
# target 为相对于 pf_rules_md_organized/ 的路径。
SECTIONS = [
    # page_350 游荡剑客
    {"source": "page_350.md", "cls": "游荡剑客", "title": "引导之刃", "english": "Guiding Blade", "target": "职业/混合职业/游荡剑客/page_120.md", "marker": "**引导之刃（"},
    {"source": "page_350.md", "cls": "游荡剑客", "title": "贵族剑士", "english": "Noble Fencer", "target": "职业/混合职业/游荡剑客/page_120.md", "marker": "**贵族剑士（"},
    {"source": "page_350.md", "cls": "游荡剑客", "title": "潜藏之刃", "english": "Veiled Blade", "target": "职业/混合职业/游荡剑客/page_120.md", "marker": "**潜藏之刃（"},
    # page_351 铳士
    {"source": "page_351.md", "cls": "铳士", "title": "赌侠", "english": "Maverick", "target": "职业/基础职业/铳手/page_76.md", "marker": "**赌侠（"},
    # page_353 炼金术师
    {"source": "page_353.md", "cls": "炼金术师", "title": "炼金爆破手", "english": "Alchemical Sapper", "target": "职业/基础职业/炼金术师/全变体未整合.md", "marker": "**炼金爆破手**** Alchemical", "duplicate_skip": True},
    {"source": "page_353.md", "cls": "炼金术师", "title": "审讯官", "english": "Interrogator", "target": "职业/基础职业/炼金术师/全变体未整合.md", "marker": "**审讯官**** Interrogator", "duplicate_skip": True},
    {"source": "page_353.md", "cls": "炼金术师", "title": "变异人", "english": "Metamorph", "target": "职业/基础职业/炼金术师/全变体未整合.md", "marker": "**变异人**** Metamorph"},
    # page_352 圣武士
    {"source": "page_352.md", "cls": "圣武士", "title": "灰骑士", "english": "Gray Paladin", "target": "职业/核心职业/圣骑士/page_55.md", "marker": "**灰骑士**** Gray"},
    # page_354 歌者
    {"source": "page_354.md", "cls": "歌者", "title": "战爵", "english": "Battle Scion", "target": "职业/混合职业/歌者/page_115.md", "marker": "**战爵**** Battle"},
    {"source": "page_354.md", "cls": "歌者", "title": "战略专家", "english": "Bold Schemer", "target": "职业/混合职业/歌者/page_115.md", "marker": "**战略专家**** Bold"},
    {"source": "page_354.md", "cls": "歌者", "title": "煽动家", "english": "Instigator", "target": "职业/混合职业/歌者/page_115.md", "marker": "**煽动家**** Instigator"},
    {"source": "page_354.md", "cls": "歌者", "title": "军阀", "english": "Warlord", "target": "职业/混合职业/歌者/page_115.md", "marker": "军阀"},
    # page_355 游荡者
    {"source": "page_355.md", "cls": "游荡者", "title": "UI盗贼天赋", "english": "UI Rogue Talents", "target": "职业/掉链子（Unchained）/盗贼/盗贼天赋汇总.md", "marker": "**盗贼天赋：**"},
    {"source": "page_355.md", "cls": "游荡者", "title": "UI高等盗贼天赋", "english": "UI Advanced Rogue Talents", "target": "职业/掉链子（Unchained）/盗贼/盗贼天赋汇总.md", "marker": "**高等盗贼天赋：**"},
    {"source": "page_355.md", "cls": "游荡者", "title": "参谋", "english": "Consigliere", "target": "职业/掉链子（Unchained）/盗贼/page_22.md", "marker": "参谋 Consigliere"},
    {"source": "page_355.md", "cls": "游荡者", "title": "公会特工", "english": "Guild Agent", "target": "职业/掉链子（Unchained）/盗贼/page_22.md", "marker": "Agent~~****~~（游荡者变体）"},
    {"source": "page_355.md", "cls": "游荡者", "title": "飞贼", "english": "Heister", "target": "职业/掉链子（Unchained）/盗贼/page_22.md", "marker": "**飞贼 Heister"},
    {"source": "page_355.md", "cls": "游荡者", "title": "易容大师", "english": "Master of Disguise", "target": "职业/掉链子（Unchained）/盗贼/page_22.md", "marker": "Disguise****（游荡者变体）"},
    {"source": "page_355.md", "cls": "游荡者", "title": "怪盗", "english": "Phantom Thief", "target": "职业/掉链子（Unchained）/盗贼/page_22.md", "marker": "**怪盗 Phantom Thief"},
    {"source": "page_355.md", "cls": "游荡者", "title": "赌徒", "english": "Sharper", "target": "职业/掉链子（Unchained）/盗贼/page_22.md", "marker": "**赌徒 Sharper"},
    {"source": "page_355.md", "cls": "游荡者", "title": "暗探", "english": "Snoop", "target": "职业/掉链子（Unchained）/盗贼/page_22.md", "marker": "**暗探 Snoop"},
    # page_356 反圣武士
    {"source": "page_356.md", "cls": "反圣武士", "title": "暴君", "english": "Tyrant", "target": "职业/基础职业/反圣武士/page_406.md", "marker": "**暴君 Tyrant"},
    # page_357 牧师
    {"source": "page_357.md", "cls": "牧师", "title": "教廷枢机", "english": "Cardinal", "target": "职业/核心职业/牧师/page_41.md", "marker": "**教廷枢机 Cardinal"},
    # page_358 武僧（已存在于 掉链子/武僧/职业变体汇总1.md）
    {"source": "page_358.md", "cls": "武僧", "title": "黑蝰僧", "english": "Black Asp", "target": "职业/掉链子（Unchained）/武僧/职业变体汇总1.md", "marker": "**黑蝰僧 Black Asp", "duplicate_skip": True},
    {"source": "page_358.md", "cls": "武僧", "title": "僧官", "english": "Sage Counselor", "target": "职业/掉链子（Unchained）/武僧/职业变体汇总1.md", "marker": "Counselor****（武僧变体）", "duplicate_skip": True},
    # page_359 调查员
    {"source": "page_359.md", "cls": "调查员", "title": "阴谋家", "english": "Conspirator", "target": "职业/混合职业/调查员/page_107.md", "marker": "**阴谋家**** Conspirator"},
    {"source": "page_359.md", "cls": "调查员", "title": "密探", "english": "Cipher", "target": "职业/混合职业/调查员/page_107.md", "marker": "~~**密探~~"},
    {"source": "page_359.md", "cls": "调查员", "title": "法医", "english": "Forensic Physician", "target": "职业/混合职业/调查员/page_107.md", "marker": "**法医**** Forensic"},
    {"source": "page_359.md", "cls": "调查员", "title": "管家", "english": "Majordomo", "target": "职业/混合职业/调查员/page_107.md", "marker": "**管家 Majordomo"},
    {"source": "page_359.md", "cls": "调查员", "title": "瘾君子", "english": "Hallucinist", "target": "职业/混合职业/调查员/page_107.md", "marker": "**瘾君子Hallucinist"},
    # page_360 游侠
    {"source": "page_360.md", "cls": "游侠", "title": "游侠战斗流派", "english": "Combat Style", "target": "职业/核心职业/游侠/page_58.md", "marker": "**游侠战斗流派 Combat Style"},
    {"source": "page_360.md", "cls": "游侠", "title": "传码员", "english": "Code Runner", "target": "职业/核心职业/游侠/page_58.md", "marker": "传码员 Code Runner"},
    {"source": "page_360.md", "cls": "游侠", "title": "贵公子", "english": "Dandy", "target": "职业/核心职业/游侠/page_58.md", "marker": "**贵公子 Dandy"},
    {"source": "page_360.md", "cls": "游侠", "title": "帮派杀手", "english": "Guildbreaker", "target": "职业/核心职业/游侠/page_58.md", "marker": "**帮派杀手 Guildbreaker"},
    {"source": "page_360.md", "cls": "游侠", "title": "禁卫", "english": "Sentinel", "target": "职业/核心职业/游侠/page_58.md", "marker": "**禁卫 Sentinel"},
    {"source": "page_360.md", "cls": "游侠", "title": "交通员", "english": "Transporter", "target": "职业/核心职业/游侠/page_58.md", "marker": "**交通员 Transporter"},
    # page_448 吟游诗人
    {"source": "page_448.md", "cls": "吟游诗人", "title": "无漏信使", "english": "Impervious Messenger", "target": "职业/核心职业/吟游诗人/page_38.md", "marker": "无漏信使"},
    {"source": "page_448.md", "cls": "吟游诗人", "title": "假面艺人", "english": "Masked Performer", "target": "职业/核心职业/吟游诗人/page_38.md", "marker": "Masked Performer"},
    {"source": "page_448.md", "cls": "吟游诗人", "title": "带头大哥", "english": "Ringleader", "target": "职业/核心职业/吟游诗人/page_38.md", "marker": "Ringleader"},
    {"source": "page_448.md", "cls": "吟游诗人", "title": "悲伤之魂", "english": "Sorrowsoul", "target": "职业/核心职业/吟游诗人/page_38.md", "marker": "悲伤之魂"},
    {"source": "page_448.md", "cls": "吟游诗人", "title": "俏皮客", "english": "Wit", "target": "职业/核心职业/吟游诗人/page_38.md", "marker": "俏皮客"},
    # page_497 先知
    {"source": "page_497.md", "cls": "先知", "title": "阴谋秘示域", "english": "Intrigue", "target": "职业/基础职业/先知/page_88.md", "marker": "**阴谋秘示域"},
    # page_563 德鲁伊
    {"source": "page_563.md", "cls": "德鲁伊", "title": "妖精语者", "english": "Feyspeaker", "target": "职业/核心职业/德鲁伊/page_45.md", "marker": "**妖精语者****"},
    {"source": "page_563.md", "cls": "德鲁伊", "title": "变脸人", "english": "SkinShaper", "target": "职业/核心职业/德鲁伊/page_45.md", "marker": "**变脸人****SkinShaper"},
    {"source": "page_563.md", "cls": "德鲁伊", "title": "毒葛", "english": "Urushiol", "target": "职业/核心职业/德鲁伊/page_45.md", "marker": "**毒葛****Urushiol"},
    # page_592 催眠师
    {"source": "page_592.md", "cls": "催眠师", "title": "无踪客", "english": "Enigma", "target": "职业/异能冒险（Occult Adventures）/催眠师/page_305.md", "marker": "无踪客"},
    {"source": "page_592.md", "cls": "催眠师", "title": "瞳术师", "english": "Eyebiter", "target": "职业/异能冒险（Occult Adventures）/催眠师/page_305.md", "marker": "Eyebiter"},
    {"source": "page_592.md", "cls": "催眠师", "title": "妖精诈欺师", "english": "Fey Trickster", "target": "职业/异能冒险（Occult Adventures）/催眠师/page_305.md", "marker": "Fey Trickster"},
    {"source": "page_592.md", "cls": "催眠师", "title": "窃忆魔", "english": "Thought Eater", "target": "职业/异能冒险（Occult Adventures）/催眠师/page_305.md", "marker": "Thought Eater"},
    {"source": "page_592.md", "cls": "催眠师", "title": "辅士", "english": "Vizier", "target": "职业/异能冒险（Occult Adventures）/催眠师/page_305.md", "marker": "Vizier"},
    {"source": "page_592.md", "cls": "催眠师", "title": "秘语者", "english": "Vox", "target": "职业/异能冒险（Occult Adventures）/催眠师/page_305.md", "marker": "Vox"},
    # page_593 骑将
    {"source": "page_593.md", "cls": "骑将", "title": "宫廷骑士", "english": "Courtly Knight", "target": "职业/基础职业/骑将/page_74.md", "marker": "宫廷骑士"},
    {"source": "page_593.md", "cls": "骑将", "title": "总帅", "english": "Daring General", "target": "职业/基础职业/骑将/page_74.md", "marker": "总帅"},
    {"source": "page_593.md", "cls": "骑将", "title": "骁骑", "english": "Hussar", "target": "职业/基础职业/骑将/page_74.md", "marker": "骁骑"},
    # page_1437 猎人
    {"source": "page_1437.md", "cls": "猎人", "title": "宫廷猎人", "english": "Courtly Hunter", "target": "职业/混合职业/猎人/page_104.md", "marker": "**宫廷猎人（Courtly Hunter）"},
    {"source": "page_1437.md", "cls": "猎人", "title": "穹顶行者", "english": "Roof Runner", "target": "职业/混合职业/猎人/page_104.md", "marker": "**穹顶行者 Roof Runner"},
    # page_1438 杀手
    {"source": "page_1438.md", "cls": "杀手", "title": "华裳剑", "english": "Velvet Blade", "target": "职业/混合职业/杀手/page_117.md", "marker": "华裳剑"},
    # page_1439 召唤师
    {"source": "page_1439.md", "cls": "召唤师", "title": "精类召唤师", "english": "Fey Caller", "target": "职业/掉链子（Unchained）/召唤师/page_274.md", "marker": "精类召唤师"},
    # page_1440 审判者
    {"source": "page_1440.md", "cls": "审判者", "title": "犯罪裁决域", "english": "Crime Inquisition", "target": "职业/基础职业/审判者/page_79.md", "marker": "裁决：犯罪（Crime）UI"},
    {"source": "page_1440.md", "cls": "审判者", "title": "守秘裁决域", "english": "Secrets Inquisition", "target": "职业/基础职业/审判者/page_79.md", "marker": "裁决：守秘（Secrets）UI"},
    {"source": "page_1440.md", "cls": "审判者", "title": "恶狼", "english": "Cloaked Wolf", "target": "职业/基础职业/审判者/page_78.md", "marker": "**恶狼 Cloaked"},
    {"source": "page_1440.md", "cls": "审判者", "title": "信猎使", "english": "Faith Hunter", "target": "职业/基础职业/审判者/page_78.md", "marker": "**信猎使 Faith"},
    {"source": "page_1440.md", "cls": "审判者", "title": "伏影特工", "english": "Umbral Stalker", "target": "职业/基础职业/审判者/page_78.md", "marker": "**伏影特工 Umbral"},
    {"source": "page_1440.md", "cls": "审判者", "title": "护法官", "english": "Vigilant Defender", "target": "职业/基础职业/审判者/page_78.md", "marker": "**护法官 Vigilant"},
    {"source": "page_1440.md", "cls": "审判者", "title": "寻秘者", "english": "Secret Seeker", "target": "职业/基础职业/审判者/page_78.md", "marker": "**寻秘者 SECRET"},
    {"source": "page_1440.md", "cls": "审判者", "title": "无痕执行官", "english": "Traceless Operative", "target": "职业/基础职业/审判者/page_78.md", "marker": "**无痕执行官 TRACELESS"},
    {"source": "page_1440.md", "cls": "审判者", "title": "战术统帅", "english": "Tactical Leader", "target": "职业/基础职业/审判者/page_78.md", "marker": "**战术统帅（Tactical Leader）"},
    # page_1441 唤魂师
    {"source": "page_1441.md", "cls": "唤魂师", "title": "唤影师", "english": "Shadow Call", "target": "职业/异能冒险（Occult Adventures）/唤魂师/page_270.md", "marker": "唤影师"},
    {"source": "page_1441.md", "cls": "唤魂师", "title": "思潮领袖", "english": "Zeitgeist Binder", "target": "职业/异能冒险（Occult Adventures）/唤魂师/page_270.md", "marker": "思潮领袖"},
    # page_1442 秘学士
    {"source": "page_1442.md", "cls": "秘学士", "title": "古老野心家", "english": "Ancestral Aspirant", "target": "职业/异能冒险（Occult Adventures）/秘学士/page_266.md", "marker": "古老野心家"},
    {"source": "page_1442.md", "cls": "秘学士", "title": "秘密掮客", "english": "Secret Broker", "target": "职业/异能冒险（Occult Adventures）/秘学士/page_266.md", "marker": "秘密掮客"},
]


def load_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().splitlines()


def find_index(lines, marker, source):
    for i, line in enumerate(lines):
        if marker in line:
            return i
    raise ValueError(f"在 {source} 中未找到标记: {marker!r}")


def already_present(target_text, section):
    """通过隐藏标记或标题/英文名判断目标文件是否已有该条目。"""
    marker_key = f"<!-- UI-source:{section['source']}:{section['title']} -->"
    if marker_key in target_text:
        return True, "hidden_marker"
    # 显式要求跳过的重复项
    if section.get("duplicate_skip"):
        # 用标题或英文名在目标中检索；此检索仅用于明确已知的重复项。
        checks = [section["title"], section.get("english", "")]
        for c in checks:
            if c and c in target_text:
                return True, f"existing_content ({c})"
    return False, None


def extract_section(source_lines, start_idx, end_idx):
    return source_lines[start_idx:end_idx]


def build_append_block(section, section_lines):
    # 在第一条非空标题行后插入来源标注
    insert_pos = 0
    for i, line in enumerate(section_lines):
        if line.strip():
            insert_pos = i + 1
            break
    note = SOURCE_NOTE_TEMPLATE.format(cls=section["cls"])
    marker = f"<!-- UI-source:{section['source']}:{section['title']} -->"
    # 组装：隐藏标记 + 原文片段 + 来源标注
    result = [marker]
    result.extend(section_lines[:insert_pos])
    result.append(note)
    result.extend(section_lines[insert_pos:])
    # 保证末尾有换行间隔
    if result and result[-1].strip() != "":
        result.append("")
    result.append("")
    return "\n".join(result) + "\n"


def append_to_target(target_path, block):
    full_path = os.path.join(ORG_BASE, target_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    mode = "a" if os.path.exists(full_path) else "w"
    with open(full_path, mode, encoding="utf-8") as f:
        f.write(block)


def main():
    stats = {"added": 0, "skipped": 0, "errors": []}
    duplicates = []
    plan_sections = []

    # 按 source 分组并排序（JSON 中已按顺序）
    grouped = {}
    for sec in SECTIONS:
        grouped.setdefault(sec["source"], []).append(sec)

    for source, secs in grouped.items():
        src_path = os.path.join(SRC_DIR, source)
        if not os.path.exists(src_path):
            stats["errors"].append(f"源文件不存在: {source}")
            continue
        lines = load_lines(src_path)
        # 计算每个条目的起始/结束索引
        indices = []
        for sec in secs:
            try:
                idx = find_index(lines, sec["marker"], source)
                indices.append((idx, sec))
            except ValueError as e:
                stats["errors"].append(str(e))
        indices.sort(key=lambda x: x[0])

        for i, (start_idx, sec) in enumerate(indices):
            end_idx = indices[i + 1][0] if i + 1 < len(indices) else len(lines)
            target_path = sec["target"]
            full_target = os.path.join(ORG_BASE, target_path)
            target_text = ""
            if os.path.exists(full_target):
                target_text = open(full_target, "r", encoding="utf-8").read()

            present, reason = already_present(target_text, sec)
            if present:
                duplicates.append({
                    "source": source,
                    "title": sec["title"],
                    "english": sec.get("english", ""),
                    "target": target_path,
                    "reason": reason,
                })
                stats["skipped"] += 1
                plan_sections.append({**sec, "action": "skipped", "reason": reason})
                continue

            section_lines = extract_section(lines, start_idx, end_idx)
            block = build_append_block(sec, section_lines)
            append_to_target(target_path, block)
            stats["added"] += 1
            plan_sections.append({**sec, "action": "added"})

    # 写入计划文件
    plan = {
        "source_book": "极限诡道UI",
        "source_book_english": "Ultimate Intrigue",
        "source_dir": "pf_data/phase1/pf_rules_md/未整理/极限诡道UI/变体_职业选项",
        "stats": stats,
        "sections": plan_sections,
    }
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    # 写入报告
    report_lines = [
        "# 极限诡道UI 整理报告",
        "",
        "## 整理策略",
        "",
        "极限诡道UI（Ultimate Intrigue）的 `变体/职业选项` 内容以职业变体、职业选项（秘示域、裁决域、战斗流派、盗贼天赋）为主。",
        "本次按条目追加到 `pf_rules_md_organized/职业/` 下对应职业的已有页面中。",
        "",
        "## 源目录",
        "",
        "- `pf_data/phase1/pf_rules_md/未整理/极限诡道UI/变体_职业选项/`",
        "",
        "## 处理统计",
        "",
        f"- 新增条目：{stats['added']}",
        f"- 跳过重复：{stats['skipped']}",
    ]
    if stats["errors"]:
        report_lines.extend(["", "## 错误", ""])
        for e in stats["errors"]:
            report_lines.append(f"- {e}")
    if duplicates:
        report_lines.extend(["", "## 重复/跳过项", ""])
        for d in duplicates:
            en = f" / {d['english']}" if d["english"] else ""
            report_lines.append(f"- `{d['source']}` `{d['title']}{en}` → `{d['target']}`（原因：{d['reason']}）")
    report_lines.extend(["", "## 验证清单", "", "- [ ] 原目录未被修改", "- [ ] 新增条目均出现 `> 来源：` 标注", "- [ ] 标注位于条目标题下一行", "- [ ] 未重复追加", "- [ ] 进度文档已更新", "- [ ] 已提交 Git", ""])
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    # 追加到全局重复记录
    if duplicates:
        dup_lines = ["", "", "## 极限诡道UI（Ultimate Intrigue）", "", f"**发现时间**：2026-06-18", ""]
        dup_lines.append("| 来源文件 | 条目 | 目标文件 | 备注 |")
        dup_lines.append("|----------|------|----------|------|")
        for d in duplicates:
            en = f" / {d['english']}" if d["english"] else ""
            dup_lines.append(f"| {d['source']} | {d['title']}{en} | {d['target']} | {d['reason']} |")
        dup_lines.append("")
        with open(DUP_RECORD_PATH, "a", encoding="utf-8") as f:
            f.write("\n".join(dup_lines))

    print(f"整理完成：新增 {stats['added']} 条，跳过 {stats['skipped']} 条，错误 {len(stats['errors'])} 条。")
    if stats["errors"]:
        for e in stats["errors"]:
            print("  ERROR:", e)


if __name__ == "__main__":
    main()
