#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 极限荒野（Ultimate Wilderness）内容到已有分类目录。

本次处理：
- 专长：专长11.md
- 物品：物品3.md（冒险装备表格 + 28 个冒险装备条目 → page_210.md；
                  擦剂 → page_212.md；
                  蛮兽裹布 → 装备_魔法物品/魔法物品/奇物/极限荒野UW_奇物.md）
- 魔法植物：魔法植物.md（含奇植培育专长 + 20+ 魔法植物条目）
- 武器附魔：武器附魔9.md（骤降）
- 自然仪式：自然仪式.md（5 个仪式）
- 动物伙伴专长：伙伴/动物伙伴专长.md
- 动物装备栏位修正：伙伴/动物装备栏位修正.md
- 新动物伙伴：伙伴/page_1419.md
- 植物伙伴：伙伴/page_1420.md
- 昆虫伙伴：伙伴/page_1421.md
- 动物伙伴变体：伙伴/page_1422.md
- 魔宠变体：伙伴/page_1461.md
- 新基础魔宠：伙伴/page_1493.md
- 职业变体：职业变体_选项/ 下全部文件

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
SRC_DIR = os.path.join(BASE, "pf_rules_md/未整理/极限荒野UW")
ORG_BASE = os.path.join(BASE, "pf_rules_md_organized")
PLAN_PATH = os.path.join(BASE, "UW_reorganization_plan.json")
REPORT_PATH = os.path.join(BASE, "UW_reorganization_report.md")
DUP_RECORD_PATH = os.path.join(BASE, "未整理目录重复记录.md")
PROBLEM_RECORD_PATH = os.path.join(BASE, "未整理目录整理问题记录.md")

SOURCE_NOTE_TEMPLATE = "> 来源：极限荒野（Ultimate Wilderness），页码见原书，未整理 → 极限荒野UW → {section_title}"

# 职业变体条目配置
# 格式：source 文件路径，marker 定位子串，title 中文名，english 英文名，cls 职业名，target 目标文件
SECTIONS = [
    # 秘学士变体（page_1424.md）
    {"source": "职业变体_选项/page_1424.md", "title": "自然学家", "english": "Naturalist", "cls": "秘学士", "section_title": "变体", "target": "职业/基础职业/秘学士/全变体未整合.md", "marker": "自然学家（Naturalist）"},
    {"source": "职业变体_选项/page_1424.md", "title": "探地者", "english": "Geomancer", "cls": "秘学士", "section_title": "变体", "target": "职业/基础职业/秘学士/全变体未整合.md", "marker": "探地者(Geomancer)"},
    # 骑士变体（page_1425.md）
    {"source": "职业变体_选项/page_1425.md", "title": "恐龙卫士", "english": "Saurian Champion", "cls": "骑士", "section_title": "变体", "target": "职业/基础职业/骑将/page_74.md", "marker": "恐龙卫士(Saurian Champion)"},
    {"source": "职业变体_选项/page_1425.md", "title": "苍翠骑士", "english": "Green Knight", "cls": "骑士", "section_title": "变体", "target": "职业/基础职业/骑将/page_74.md", "marker": "苍翠骑士（Green\nKnight）"},
    # 游荡剑客变体（page_1426.md）
    {"source": "职业变体_选项/page_1426.md", "title": "金牌箭客", "english": "Arrow Champion", "cls": "游荡剑客", "section_title": "变体", "target": "职业/混合职业/游荡剑客/page_120.md", "marker": "金牌箭客(ARROW CHAMPION)"},
    {"source": "职业变体_选项/page_1426.md", "title": "荒野神行客", "english": "Wildstrider", "cls": "游荡剑客", "section_title": "变体", "target": "职业/混合职业/游荡剑客/page_120.md", "marker": "荒野神行客(WILDSTRIDER)"},
    # 战士变体（page_1427.md）
    {"source": "职业变体_选项/page_1427.md", "title": "尖兵战士", "english": "Skirmisher", "cls": "战士", "section_title": "变体", "target": "职业/核心职业/战士/page_49.md", "marker": "尖兵战士Skirmisher"},
    {"source": "职业变体_选项/page_1427.md", "title": "维京", "english": "Vikings", "cls": "战士", "section_title": "变体", "target": "职业/核心职业/战士/page_49.md", "marker": "维京（Vikings）"},
    # 拳师变体（page_1428.md）
    {"source": "职业变体_选项/page_1428.md", "title": "毒拳士", "english": "Venomfist", "cls": "拳师", "section_title": "变体", "target": "职业/混合职业/拳师/page_102.md", "marker": "毒拳士（Venomfist）"},
    {"source": "职业变体_选项/page_1428.md", "title": "先登", "english": "Living Avalanche", "cls": "拳师", "section_title": "变体", "target": "职业/混合职业/拳师/page_102.md", "marker": "先登(Living\nAvalanche)"},
    {"source": "职业变体_选项/page_1428.md", "title": "苍翠擒缚师", "english": "Verdant Grappler", "cls": "拳师", "section_title": "变体", "target": "职业/混合职业/拳师/page_102.md", "marker": "苍翠擒缚师（Verdant\nGrappler）"},
    {"source": "职业变体_选项/page_1428.md", "title": "野性袭者", "english": "Feral Striker", "cls": "拳师", "section_title": "变体", "target": "职业/混合职业/拳师/page_102.md", "marker": "野性袭者（Feral\nStriker）"},
    {"source": "职业变体_选项/page_1428.md", "title": "地形拳士", "english": "Turfer", "cls": "拳师", "section_title": "变体", "target": "职业/混合职业/拳师/page_102.md", "marker": "地形拳士（Turfer）"},
    # 猎人变体（page_1429.md）— 两个变体内容重复（护林官/巡林客），只取一个
    {"source": "职业变体_选项/page_1429.md", "title": "人猿泰山", "english": "Treestrider", "cls": "猎人", "section_title": "变体", "target": "职业/混合职业/猎人/page_104.md", "marker": "人猿泰山（****Treestrider****）"},
    # 游侠变体（page_1451.md）
    {"source": "职业变体_选项/page_1451.md", "title": "潮汐猎人", "english": "Tidal Hunter", "cls": "游侠", "section_title": "变体", "target": "职业/核心职业/游侠/page_55.md", "marker": "潮汐猎人（Tidal\nHunter）"},
    {"source": "职业变体_选项/page_1451.md", "title": "火焰守望者", "english": "Flamewarden", "cls": "游侠", "section_title": "变体", "target": "职业/核心职业/游侠/page_55.md", "marker": "火焰守望者【游侠变体】（Flamewarden）"},
    {"source": "职业变体_选项/page_1451.md", "title": "荒野探险家", "english": "Wilderness Explorer", "cls": "游侠", "section_title": "变体", "target": "职业/核心职业/游侠/page_55.md", "marker": "荒野探险家（Wilderness\nExplorer）"},
    # 野蛮人变体（page_1452.md）
    {"source": "职业变体_选项/page_1452.md", "title": "锐利之牙", "english": "Sharptooth", "cls": "野蛮人", "section_title": "变体", "target": "职业/核心职业/野蛮人/page_49.md", "marker": "锐利之牙（Sharptooth）"},
    {"source": "职业变体_选项/page_1452.md", "title": "荒野之子", "english": "Wildborn", "cls": "野蛮人", "section_title": "变体", "target": "职业/核心职业/野蛮人/page_49.md", "marker": "荒野之子（Wildborn）"},
    {"source": "职业变体_选项/page_1452.md", "title": "野蛮沼人", "english": "Brutish Swamper", "cls": "野蛮人", "section_title": "变体", "target": "职业/核心职业/野蛮人/page_49.md", "marker": "野蛮沼人（Brutish Swamper）"},
    # 炼金术师变体（page_1453.md）
    {"source": "职业变体_选项/page_1453.md", "title": "植者", "english": "Herbalist", "cls": "炼金术师", "section_title": "变体", "target": "职业/基础职业/炼金术师/全变体未整合.md", "marker": "植者（Herbalist）"},
    {"source": "职业变体_选项/page_1453.md", "title": "园林学者", "english": "Horticulturist", "cls": "炼金术师", "section_title": "变体", "target": "职业/基础职业/炼金术师/全变体未整合.md", "marker": "园林学者（Horticulturist）"},
    # 铳士变体（page_1454.md）
    {"source": "职业变体_选项/page_1454.md", "title": "游击枪手", "english": "Commando", "cls": "铳士", "section_title": "变体", "target": "职业/基础职业/铳手/page_76.md", "marker": "游击枪手（Commando）"},
    # 调查员变体（page_1455.md）
    {"source": "职业变体_选项/page_1455.md", "title": "自然贤者", "english": "Natural Philosopher", "cls": "调查员", "section_title": "变体", "target": "职业/混合职业/调查员/page_107.md", "marker": "自然贤者（Natural\nPhilosopher）"},
    {"source": "职业变体_选项/page_1455.md", "title": "星空守望者", "english": "Star Watcher", "cls": "调查员", "section_title": "变体", "target": "职业/混合职业/调查员/page_107.md", "marker": "星空守望者（Star\nWatcher）"},
    {"source": "职业变体_选项/page_1455.md", "title": "绘图师", "english": "Cartographer", "cls": "调查员", "section_title": "变体", "target": "职业/混合职业/调查员/page_107.md", "marker": "绘图师（Cartographer）"},
    # 圣武士变体（page_1457.md）
    {"source": "职业变体_选项/page_1457.md", "title": "守林人", "english": "Forest Preserver", "cls": "圣武士", "section_title": "变体", "target": "职业/核心职业/圣骑士/page_55.md", "marker": "守林人（Forest\nPreserver）"},
    # 吟游诗人变体（page_1458.md）
    {"source": "职业变体_选项/page_1458.md", "title": "妖精侍臣", "english": "Fey Courtier", "cls": "吟游诗人", "section_title": "变体", "target": "职业/核心职业/吟游诗人/page_55.md", "marker": "妖精侍臣（Fey\nCourtier）"},
    {"source": "职业变体_选项/page_1458.md", "title": "耕种师", "english": "Cultivator", "cls": "吟游诗人", "section_title": "变体", "target": "职业/核心职业/吟游诗人/page_55.md", "marker": "耕种师（Cultivator）"},
    # 盗贼变体（page_1460.md）
    {"source": "职业变体_选项/page_1460.md", "title": "妖精戏耍者", "english": "Fey Prankster", "cls": "盗贼", "section_title": "变体", "target": "职业/核心职业/盗贼/page_49.md", "marker": "妖精戏耍者（Fey\nPrankster）"},
    {"source": "职业变体_选项/page_1460.md", "title": "机巧毁坏者", "english": "Sly Saboteur", "cls": "盗贼", "section_title": "变体", "target": "职业/核心职业/盗贼/page_49.md", "marker": "机巧毁坏者（Sly\nSaboteur）"},
    {"source": "职业变体_选项/page_1460.md", "title": "沙漠劫掠者", "english": "Desert Raider", "cls": "盗贼", "section_title": "变体", "target": "职业/核心职业/盗贼/page_49.md", "marker": "沙漠劫掠者(Desert Raider)"},
    {"source": "职业变体_选项/page_1460.md", "title": "林精妖术师", "english": "Sylvan Trickster", "cls": "盗贼", "section_title": "变体", "target": "职业/核心职业/盗贼/page_49.md", "marker": "林精妖术师（Sylvan\nTrickster）"},
    # 先知变体（page_1463.md）
    {"source": "职业变体_选项/page_1463.md", "title": "元素使先知", "english": "Elementalist Oracle", "cls": "先知", "section_title": "变体", "target": "职业/基础职业/先知/全变体未整合.md", "marker": "元素使先知（Elementalist\nOracle）"},
    {"source": "职业变体_选项/page_1463.md", "title": "河灵先知", "english": "River Soul", "cls": "先知", "section_title": "变体", "target": "职业/基础职业/先知/全变体未整合.md", "marker": "河灵先知（River\nSoul）"},
    {"source": "职业变体_选项/page_1463.md", "title": "树灵先知", "english": "Tree Soul", "cls": "先知", "section_title": "变体", "target": "职业/基础职业/先知/全变体未整合.md", "marker": "树灵先知（Tree\nSoul）"},
    # 德鲁伊变体（page_1464.md）
    {"source": "职业变体_选项/page_1464.md", "title": "恐龙德鲁伊", "english": "Dinosaur Druid", "cls": "德鲁伊", "section_title": "变体", "target": "职业/核心职业/德鲁伊/page_49.md", "marker": "恐龙德鲁伊（Dinosaur Druid）"},
    {"source": "职业变体_选项/page_1464.md", "title": "羽巢守护人", "english": "Aerie Protector", "cls": "德鲁伊", "section_title": "变体", "target": "职业/核心职业/德鲁伊/page_49.md", "marker": "羽巢守护人（Aerie\nProtector）"},
    {"source": "职业变体_选项/page_1464.md", "title": "苍翠誓约入信者", "english": "Green Faith Initiate", "cls": "德鲁伊", "section_title": "变体", "target": "职业/核心职业/德鲁伊/page_49.md", "marker": "苍翠誓约入信者（Green Faith\nInitiate）"},
    # 侠客变体（page_1465.md）
    {"source": "职业变体_选项/page_1465.md", "title": "复仇猎兽", "english": "Avenging Beast", "cls": "侠客", "section_title": "变体", "target": "职业/基础职业/审判者/page_78.md", "marker": "复仇猎兽（Avenging Beast）"},
    # 战斗祭司变体（page_1466.md）
    {"source": "职业变体_选项/page_1466.md", "title": "野性斗士", "english": "Feral Champion", "cls": "战斗祭司", "section_title": "变体", "target": "职业/混合职业/战斗祭司/page_43.md", "marker": "野性斗士（Feral Champion）"},
    # 杀手变体（page_1467.md）
    {"source": "职业变体_选项/page_1467.md", "title": "临崖客", "english": "Avalancher", "cls": "杀手", "section_title": "变体", "target": "职业/混合职业/杀手/page_117.md", "marker": "临崖客(Avalancher)"},
    {"source": "职业变体_选项/page_1467.md", "title": "林地狙击手", "english": "Woodland Sniper", "cls": "杀手", "section_title": "变体", "target": "职业/混合职业/杀手/page_117.md", "marker": "林地狙击手（Woodland\nSniper）"},
    {"source": "职业变体_选项/page_1467.md", "title": "沙丘骑手", "english": "Dune Rider", "cls": "杀手", "section_title": "变体", "target": "职业/混合职业/杀手/page_117.md", "marker": "沙丘骑手（Dune\nRider）"},
    # 女巫变体（page_1468.md）
    {"source": "职业变体_选项/page_1468.md", "title": "洪流行者", "english": "Flood Walker", "cls": "女巫", "section_title": "变体", "target": "职业/基础职业/女巫/全变体未整合.md", "marker": "洪流行者【女巫变体】（Flood Walker）"},
    {"source": "职业变体_选项/page_1468.md", "title": "香草药魔女", "english": "Herb Witch", "cls": "女巫", "section_title": "变体", "target": "职业/基础职业/女巫/全变体未整合.md", "marker": "香草药魔女"},
    {"source": "职业变体_选项/page_1468.md", "title": "季节女巫", "english": "Season Witch", "cls": "女巫", "section_title": "变体", "target": "职业/基础职业/女巫/全变体未整合.md", "marker": "季节女巫（Season\nWitch）"},
    # 操念使变体（操念使3.md）
    {"source": "职业变体_选项/操念使3.md", "title": "荒芜渎行师", "english": "Blighted Defiler", "cls": "操念使", "section_title": "变体", "target": "职业/基础职业/秘学士/全变体未整合.md", "marker": "荒芜渎行师（Blighted\nDefiler）"},
    # 反圣武士变体（反圣武士.md）
    {"source": "职业变体_选项/反圣武士.md", "title": "荒疫追随者", "english": "Blighted Myrmidon", "cls": "反圣武士", "section_title": "变体", "target": "职业/基础职业/反圣武士/page_76.md", "marker": "荒疫追随者（Blighted\nMyrmidon）"},
    # 歌者变体（歌者.md）
    {"source": "职业变体_选项/歌者.md", "title": "酒神宾客", "english": "Bacchanal", "cls": "歌者", "section_title": "变体", "target": "职业/混合职业/歌者/page_104.md", "marker": "酒神宾客（Bacchanal）"},
    # 武僧变体（武僧3.md）
    {"source": "职业变体_选项/武僧3.md", "title": "圣遗迹护卫", "english": "Menhir Guardian", "cls": "武僧", "section_title": "变体", "target": "职业/核心职业/武僧/page_55.md", "marker": "圣遗迹护卫（Menhir\nGuardian）"},
    {"source": "职业变体_选项/武僧3.md", "title": "水舞者", "english": "Water Dancer", "cls": "武僧", "section_title": "变体", "target": "职业/核心职业/武僧/page_55.md", "marker": "水舞者Water\nDancer"},
    {"source": "职业变体_选项/武僧3.md", "title": "荒墟禅师", "english": "Wasteland Meditant", "cls": "武僧", "section_title": "变体", "target": "职业/核心职业/武僧/page_55.md", "marker": "荒墟禅师（Wasteland\nMeditant）"},
    # 血脉狂怒者变体（血脉狂怒者1.md）
    {"source": "职业变体_选项/血脉狂怒者1.md", "title": "苍翠血脉", "english": "Verdant", "cls": "血脉狂怒者", "section_title": "变体", "target": "职业/混合职业/血脉狂怒者/page_104.md", "marker": "苍翠血脉（Verdant）"},
    # 召唤师变体（召唤师1.md）
    {"source": "职业变体_选项/召唤师1.md", "title": "莱西呼唤者", "english": "Leshy Caller", "cls": "召唤师", "section_title": "变体", "target": "职业/基础职业/召唤师/page_410.md", "marker": "莱西呼唤者（Leshy\nCaller）"},
    {"source": "职业变体_选项/召唤师1.md", "title": "植物幻灵", "english": "Plant Eidolon", "cls": "召唤师", "section_title": "变体", "target": "职业/基础职业/召唤师/page_410.md", "marker": "植物（Plant）"},
]

KNOWN_LABELS = {
    "制造要求", "需求", "制造成本", "制造条件", "灵光", "位置", "栏位", "价格",
    "施法者等级", "重量", "类别", "描述", "来源", "出处", "效果", "先决条件",
    "专长效果", "通常", "特殊说明", "拥有此专长前的正常情况", "好处", "学派",
    "施放时间", "成分", "技能检定", "距离", "区域", "持续时间", "豁免", "法术抗力",
    "反冲", "失败", "起始数据", "四级进化", "七级进化",
}


def load_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().splitlines()


def find_index(lines, marker, source):
    """查找标记在文本中的位置，支持跨行匹配。"""
    if "\n" in marker:
        marker_parts = marker.split("\n")
        for i in range(len(lines) - len(marker_parts) + 1):
            if all(marker_part in lines[i + j] for j, marker_part in enumerate(marker_parts)):
                return i
        raise ValueError(f"在 {source} 中未找到标记: {marker!r}")
    else:
        for i, line in enumerate(lines):
            if marker in line:
                return i
        raise ValueError(f"在 {source} 中未找到标记: {marker!r}")


def already_present(target_text, section):
    marker_key = f"<!-- UW-source:{section['source']}:{section['title']} -->"
    if marker_key in target_text:
        return True, "hidden_marker"
    if section.get("duplicate_skip"):
        checks = [section["title"], section.get("english", "")]
        for c in checks:
            if c and c in target_text:
                return True, f"existing_content ({c})"
    return False, None


def extract_section(source_lines, start_idx, end_idx):
    return source_lines[start_idx:end_idx]


def normalize_section_lines(section_lines):
    """修正标题与正文挤在同一行的情况（如 **标题** *****正文）。"""
    result = []
    for line in section_lines:
        m = re.match(r'^(\*\*.*?\*\*)(\*{2,})(\*?.*)$', line)
        if m:
            result.append(m.group(1))
            body = m.group(3).lstrip('*')
            if body:
                result.append(body)
        else:
            result.append(line)
    return result


def split_title_body(section_lines):
    """将片段拆分为标题行与正文行。标题为开头连续的加粗块。"""
    section_lines = normalize_section_lines(section_lines)
    title_end = 0
    label_pattern = re.compile(r'^\*\*(' + '|'.join(re.escape(l) for l in KNOWN_LABELS) + r')')
    for i, line in enumerate(section_lines):
        s = line.strip()
        if not s:
            if title_end > 0:
                break
            continue
        if title_end == 0:
            title_end = i + 1
            continue
        # 当前行是正文标签（灵光、价格、先决条件等），标题结束
        if label_pattern.match(s):
            break
        prev = section_lines[i - 1].strip()
        if prev.endswith("**"):
            break
        title_end = i + 1
    return section_lines[:title_end], section_lines[title_end:]


def build_append_block(section, section_lines, section_title=None):
    title_lines, body_lines = split_title_body(section_lines)
    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title or section.get("section_title", ""))
    marker = f"<!-- UW-source:{section['source']}:{section['title']} -->"
    result = [marker]
    result.extend(title_lines)
    result.append(note)
    result.extend(body_lines)
    if result and result[-1].strip() != "":
        result.append("")
    result.append("")
    return "\n".join(result) + "\n"


def append_to_target(target_path, block):
    full_path = os.path.join(ORG_BASE, target_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    prefix = ""
    if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
        with open(full_path, "rb") as f:
            f.seek(-1, os.SEEK_END)
            last_char = f.read(1)
        if last_char != b"\n":
            prefix = "\n"
        mode = "a"
    else:
        mode = "w"
    with open(full_path, mode, encoding="utf-8") as f:
        f.write(prefix + block)


def ensure_header(target_path, header):
    full_path = os.path.join(ORG_BASE, target_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    if not os.path.exists(full_path) or os.path.getsize(full_path) == 0:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(header + "\n\n")


def process_source_sections(secs, stats, duplicates, plan_sections):
    """处理通用 SECTIONS 配置。"""
    grouped = {}
    for sec in secs:
        grouped.setdefault(sec["source"], []).append(sec)

    for source, src_secs in grouped.items():
        src_path = os.path.join(SRC_DIR, source)
        if not os.path.exists(src_path):
            stats["errors"].append(f"源文件不存在: {source}")
            continue
        lines = load_lines(src_path)
        indices = []
        for sec in src_secs:
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


def detect_title_starts(lines, max_len=80):
    """自动检测以中文名称开头的标题行位置（用于专长）。"""
    starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        while s.startswith("*"):
            s = s[1:]
        s = s.strip()
        if not s or len(s) > max_len:
            continue
        if s[-1] in "。！？":
            continue
        m = re.match(r"([一-鿿][一-鿿\w]*)\s*[(（A-Za-z]", s)
        if not m:
            continue
        first = m.group(1)
        if first in KNOWN_LABELS:
            continue
        starts.append((i, s))
    return starts


def process_auto_split_file(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """对专长文件按自动检测的标题行拆分并合并。"""
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return
    lines = load_lines(src_path)
    starts = detect_title_starts(lines)
    if not starts:
        stats["errors"].append(f"{source_file} 中未检测到标题")
        return

    ensure_header(target_path, header)

    for idx, (start_idx, title_line) in enumerate(starts):
        end_idx = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        short_title = title_line.split("（")[0].split(" ")[0].strip("*")
        sec = {
            "source": source_file,
            "title": short_title,
            "english": "",
            "target": target_path,
            "section_title": section_title,
        }
        full_target = os.path.join(ORG_BASE, target_path)
        target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

        present, reason = already_present(target_text, sec)
        if present:
            duplicates.append({
                "source": source_file,
                "title": short_title,
                "english": "",
                "target": target_path,
                "reason": reason,
            })
            stats["skipped"] += 1
            plan_sections.append({**sec, "action": "skipped", "reason": reason})
            continue

        section_lines = extract_section(lines, start_idx, end_idx)
        block = build_append_block(sec, section_lines, section_title=section_title)
        append_to_target(target_path, block)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})


def process_single_file(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """处理单文件多条目（如物品、魔法植物、仪式等）。

    每个条目标题行以 ** 开头，按标题自动拆分。
    """
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)

    # 检测以 ** 开头的标题行
    starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("**"):
            # 去掉 ** 后取中文名
            rest = s[2:]
            m = re.match(r"([一-鿿][一-鿿\w]*)\s*[(（A-Za-z]", rest)
            if m:
                first = m.group(1)
                if first not in KNOWN_LABELS:
                    starts.append((i, s))

    if not starts:
        stats["errors"].append(f"{source_file} 中未找到有效标题")
        return

    ensure_header(target_path, header)

    for idx, (start_idx, title_line) in enumerate(starts):
        end_idx = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        short_title = title_line.strip("*").split("（")[0].split(" ")[0].strip()

        sec = {
            "source": source_file,
            "title": short_title,
            "english": "",
            "target": target_path,
            "section_title": section_title,
        }

        full_target = os.path.join(ORG_BASE, target_path)
        target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

        present, reason = already_present(target_text, sec)
        if present:
            duplicates.append({
                "source": source_file,
                "title": short_title,
                "english": "",
                "target": target_path,
                "reason": reason,
            })
            stats["skipped"] += 1
            plan_sections.append({**sec, "action": "skipped", "reason": reason})
            continue

        section_lines = extract_section(lines, start_idx, end_idx)
        block = build_append_block(sec, section_lines, section_title=section_title)
        append_to_target(target_path, block)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})


def process_companion_file(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """处理动物伙伴/魔宠文件，每个条目以 **名称** 开头。"""
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)
    starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        # 动物伙伴条目以 **名称(** 或 **名称(** 开头
        if s.startswith("**"):
            rest = s[2:]
            # 匹配中文名称后跟英文
            m = re.match(r"([一-鿿][一-鿿\w]*)\s*[(（]", rest)
            if m:
                first = m.group(1)
                if first not in KNOWN_LABELS and "表格" not in first:
                    starts.append((i, s))

    if not starts:
        # 如果没有检测到标题，作为整文件处理
        sec = {
            "source": source_file,
            "title": section_title,
            "english": "",
            "target": target_path,
            "section_title": section_title,
        }
        full_target = os.path.join(ORG_BASE, target_path)
        target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""
        present, reason = already_present(target_text, sec)
        if present:
            duplicates.append({
                "source": source_file,
                "title": section_title,
                "english": "",
                "target": target_path,
                "reason": reason,
            })
            stats["skipped"] += 1
            plan_sections.append({**sec, "action": "skipped", "reason": reason})
            return
        ensure_header(target_path, header)
        block = build_append_block(sec, lines, section_title=section_title)
        append_to_target(target_path, block)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})
        return

    ensure_header(target_path, header)

    for idx, (start_idx, title_line) in enumerate(starts):
        end_idx = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        short_title = title_line.strip("*").split("（")[0].split(" ")[0].strip()

        sec = {
            "source": source_file,
            "title": short_title,
            "english": "",
            "target": target_path,
            "section_title": section_title,
        }

        full_target = os.path.join(ORG_BASE, target_path)
        target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

        present, reason = already_present(target_text, sec)
        if present:
            duplicates.append({
                "source": source_file,
                "title": short_title,
                "english": "",
                "target": target_path,
                "reason": reason,
            })
            stats["skipped"] += 1
            plan_sections.append({**sec, "action": "skipped", "reason": reason})
            continue

        section_lines = extract_section(lines, start_idx, end_idx)
        block = build_append_block(sec, section_lines, section_title=section_title)
        append_to_target(target_path, block)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})


def process_whole_file(source_file, target_path, section_title, header, stats, duplicates, plan_sections, title_override=None):
    """将整个源文件作为一个条目追加到目标聚合文件。"""
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)
    sec = {
        "source": source_file,
        "title": title_override or section_title,
        "english": "",
        "target": target_path,
        "section_title": section_title,
    }

    full_target = os.path.join(ORG_BASE, target_path)
    target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

    present, reason = already_present(target_text, sec)
    if present:
        duplicates.append({
            "source": source_file,
            "title": sec["title"],
            "english": "",
            "target": target_path,
            "reason": reason,
        })
        stats["skipped"] += 1
        plan_sections.append({**sec, "action": "skipped", "reason": reason})
        return

    ensure_header(target_path, header)
    block = build_append_block(sec, lines, section_title=section_title)
    append_to_target(target_path, block)
    stats["added"] += 1
    plan_sections.append({**sec, "action": "added"})


def merge_uw_item_titles(lines):
    """合并物品条目中跨行的中文+英文标题。

    典型场景：
    - 图片行后紧跟英文续行：![[图片]] **中文（English\nName）**
    - 加粗标题内英文跨行：**中文（English\nName）**
    - 纯英文续行：(... Name)
    """
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        merged = line
        # 加粗标题未闭合，下一行以 ** 结尾（且不是独立 `**标题**`）或为纯英文续行
        while (
            i + 1 < len(lines)
            and "**" in s
            and not s.endswith("**")
            and len(s) <= 120
            and (
                (
                    lines[i + 1].strip().endswith("**")
                    and not re.match(r"^\*\*.*\*\*$", lines[i + 1].strip())
                )
                or re.fullmatch(r"[A-Za-z\s,\-'’]+", lines[i + 1].strip())
            )
        ):
            i += 1
            merged = merged.rstrip() + " " + lines[i].strip()
            s = merged.strip()
        # 行末是开括号，下一行是英文续名
        while (
            i + 1 < len(lines)
            and (s.endswith("(") or s.endswith("（"))
            and re.match(r"^[A-Za-z]", lines[i + 1].strip())
        ):
            i += 1
            merged = merged.rstrip() + lines[i].strip()
            s = merged.strip()
        result.append(merged)
        i += 1
    return result


def build_uw_item_block(source, title_cn, title_en, section_title, body_lines):
    """构造 UW 物品条目块。"""
    marker = f"<!-- UW-source:{source}:{title_cn} -->"
    if title_en:
        title_line = f"## {title_cn}（{title_en}）"
    else:
        title_line = f"## {title_cn}"
    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title)
    block = [marker, title_line, note]
    # 去掉 body 开头的空行
    start = 0
    while start < len(body_lines) and not body_lines[start].strip():
        start += 1
    block.extend(body_lines[start:])
    if block[-1].strip() != "":
        block.append("")
    block.append("")
    return "\n".join(block) + "\n"


def process_uw_items(source_file, stats, duplicates, plan_sections):
    """将 `物品3.md` 按子类型拆分合并。

    - 表格与 28 个冒险装备条目 → 装备_魔法物品/货品服务/page_210.md
    - 擦剂（炼金工具）→ 装备_魔法物品/货品服务/page_212.md
    - 蛮兽裹布（奇物）→ 装备_魔法物品/魔法物品/奇物/极限荒野UW_奇物.md
    """
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)

    # 定位每个条目的起始行
    start_indices = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        # 表格标题行不作为条目起点
        if "表格" in s:
            continue
        if re.search(r'!\[\[图片\]\]', s):
            start_indices.append(i)
            continue
        if s.startswith("**"):
            rest = s[2:]
            m = re.match(r"([一-鿿][一-鿿\w]*)\s*[（(]", rest)
            if m and m.group(1) not in KNOWN_LABELS:
                start_indices.append(i)

    if not start_indices:
        stats["errors"].append(f"{source_file} 中未找到有效条目起点")
        return

    # 去掉图片占位行后紧跟的重复标题起点
    # 例如：第 N 行是单独的 `![[图片]]`，第 N+1 行是 `**中文（English` 标题开头
    cleaned_starts = []
    for idx in start_indices:
        if cleaned_starts and cleaned_starts[-1] == idx - 1:
            prev_line = lines[cleaned_starts[-1]]
            if re.search(r'!\[\[图片\]\]', prev_line) and "**" not in prev_line:
                continue
        cleaned_starts.append(idx)
    start_indices = cleaned_starts

    # 构建块：引言/表格 + 各条目
    blocks = [{"type": "intro", "start": 0, "end": start_indices[0]}]
    for k, idx in enumerate(start_indices):
        end = start_indices[k + 1] if k + 1 < len(start_indices) else len(lines)
        blocks.append({"type": "item", "start": idx, "end": end})

    # 删除旧的统一聚合文件
    old_aggregate = os.path.join(ORG_BASE, "装备_魔法物品/魔法物品/极限荒野UW_物品.md")
    if os.path.exists(old_aggregate):
        os.remove(old_aggregate)

    # 确保奇物聚合文件有标题
    ensure_header("装备_魔法物品/魔法物品/奇物/极限荒野UW_奇物.md", "# 极限荒野（Ultimate Wilderness）奇物")

    title_re = re.compile(r'^([一-鿿][^（(]*?)\s*[（(]([A-Za-z\s,\-\'’]+)[）)]')

    for block in blocks:
        block_lines = lines[block["start"]:block["end"]]

        if block["type"] == "intro":
            title_cn = "表格7-1：冒险装备"
            title_en = ""
            section_title = "冒险装备"
            target = "装备_魔法物品/货品服务/page_210.md"
            body_lines = block_lines
        else:
            merged_lines = merge_uw_item_titles(block_lines)
            title_lines, body_lines = split_title_body(merged_lines)
            raw_title = " ".join(title_lines)
            raw_title = re.sub(r'!\[.*?\]\([^)]*\)', '', raw_title)
            raw_title = re.sub(r'\*\*', '', raw_title).strip()
            raw_title = raw_title.split("｜")[0].strip()
            m = title_re.match(raw_title)
            if not m:
                stats["errors"].append(f"{source_file} 中无法解析条目标题: {raw_title!r}")
                continue
            title_cn = m.group(1).strip()
            title_en = m.group(2).strip()
            if title_cn == "擦剂":
                target = "装备_魔法物品/货品服务/page_212.md"
                section_title = "炼金工具"
            elif title_cn == "蛮兽裹布":
                target = "装备_魔法物品/魔法物品/奇物/极限荒野UW_奇物.md"
                section_title = "奇物"
            else:
                target = "装备_魔法物品/货品服务/page_210.md"
                section_title = "冒险装备"

        sec = {
            "source": source_file,
            "title": title_cn,
            "english": title_en,
            "target": target,
            "section_title": section_title,
        }
        full_target = os.path.join(ORG_BASE, target)
        target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

        present, reason = already_present(target_text, sec)
        if present:
            duplicates.append({
                "source": source_file,
                "title": title_cn,
                "english": title_en,
                "target": target,
                "reason": reason,
            })
            stats["skipped"] += 1
            plan_sections.append({**sec, "action": "skipped", "reason": reason})
            continue

        block_text = build_uw_item_block(source_file, title_cn, title_en, section_title, body_lines)
        append_to_target(target, block_text)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})


def main():
    stats = {"added": 0, "skipped": 0, "errors": []}
    duplicates = []
    plan_sections = []

    # 1. 职业变体
    process_source_sections(SECTIONS, stats, duplicates, plan_sections)

    # 2. 专长
    feat_target = "专长/极限荒野UW_专长.md"
    feat_header = "# 极限荒野（Ultimate Wilderness）专长"
    process_auto_split_file("专长11.md", feat_target, "专长", feat_header, stats, duplicates, plan_sections)

    # 3. 物品：按子类型拆分
    process_uw_items("物品3.md", stats, duplicates, plan_sections)

    # 4. 魔法植物
    process_single_file(
        "魔法植物.md",
        "装备_魔法物品/魔法物品/极限荒野UW_魔法植物.md",
        "魔法植物",
        "# 极限荒野（Ultimate Wilderness）魔法植物",
        stats, duplicates, plan_sections
    )

    # 5. 武器附魔
    process_whole_file(
        "武器附魔9.md",
        "装备_魔法物品/武器附魔/极限荒野UW_武器附魔.md",
        "武器附魔",
        "# 极限荒野（Ultimate Wilderness）武器附魔",
        stats, duplicates, plan_sections,
        title_override="骤降"
    )

    # 6. 自然仪式
    process_single_file(
        "自然仪式.md",
        "法术/极限荒野UW_自然仪式.md",
        "自然仪式",
        "# 极限荒野（Ultimate Wilderness）自然仪式",
        stats, duplicates, plan_sections
    )

    # 7. 动物伙伴专长
    process_auto_split_file(
        "伙伴/动物伙伴专长.md",
        "专长/极限荒野UW_动物伙伴专长.md",
        "动物伙伴专长",
        "# 极限荒野（Ultimate Wilderness）动物伙伴专长",
        stats, duplicates, plan_sections
    )

    # 8. 动物装备栏位修正
    process_whole_file(
        "伙伴/动物装备栏位修正.md",
        "规则/极限荒野UW_动物装备栏位修正.md",
        "动物装备栏位修正",
        "# 极限荒野（Ultimate Wilderness）动物装备栏位修正",
        stats, duplicates, plan_sections,
        title_override="动物装备栏位修正"
    )

    # 9. 新动物伙伴
    process_companion_file(
        "伙伴/page_1419.md",
        "规则/极限荒野UW_新动物伙伴.md",
        "新动物伙伴",
        "# 极限荒野（Ultimate Wilderness）新动物伙伴",
        stats, duplicates, plan_sections
    )

    # 10. 植物伙伴
    process_companion_file(
        "伙伴/page_1420.md",
        "规则/极限荒野UW_植物伙伴.md",
        "植物伙伴",
        "# 极限荒野（Ultimate Wilderness）植物伙伴",
        stats, duplicates, plan_sections
    )

    # 11. 昆虫伙伴
    process_companion_file(
        "伙伴/page_1421.md",
        "规则/极限荒野UW_昆虫伙伴.md",
        "昆虫伙伴",
        "# 极限荒野（Ultimate Wilderness）昆虫伙伴",
        stats, duplicates, plan_sections
    )

    # 12. 动物伙伴变体
    process_companion_file(
        "伙伴/page_1422.md",
        "规则/极限荒野UW_动物伙伴变体.md",
        "动物伙伴变体",
        "# 极限荒野（Ultimate Wilderness）动物伙伴变体",
        stats, duplicates, plan_sections
    )

    # 13. 魔宠变体
    process_companion_file(
        "伙伴/page_1461.md",
        "规则/极限荒野UW_魔宠变体.md",
        "魔宠变体",
        "# 极限荒野（Ultimate Wilderness）魔宠变体",
        stats, duplicates, plan_sections
    )

    # 14. 新基础魔宠
    process_companion_file(
        "伙伴/page_1493.md",
        "规则/极限荒野UW_新基础魔宠.md",
        "新基础魔宠",
        "# 极限荒野（Ultimate Wilderness）新基础魔宠",
        stats, duplicates, plan_sections
    )

    # 15. 写入计划文件
    plan = {
        "source_book": "极限荒野",
        "source_book_english": "Ultimate Wilderness",
        "source_dir": "pf_data/phase1/pf_rules_md/未整理/极限荒野UW",
        "stats": stats,
        "sections": plan_sections,
        "skipped_files": [],
    }
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    # 16. 写入报告
    report_lines = [
        "# 极限荒野（Ultimate Wilderness）整理报告",
        "",
        "## 整理策略",
        "",
        "极限荒野（Ultimate Wilderness）内容分散在专长、物品、魔法植物、武器附魔、自然仪式、动物伙伴专长、动物装备栏位修正、新动物伙伴、植物伙伴、昆虫伙伴、动物伙伴变体、魔宠变体、新基础魔宠、职业变体等文件中。",
        "本次将所有规则条目按类型合并到 `pf_rules_md_organized/` 下对应分类目录。",
        "",
        "## 源目录",
        "",
        "- `pf_data/phase1/pf_rules_md/未整理/极限荒野UW/`",
        "",
        "## 处理统计",
        "",
        f"- 新增条目：{stats['added']}",
        f"- 跳过重复：{stats['skipped']}",
        f"- 错误：{len(stats['errors'])}",
        "",
        "## 处理内容",
        "",
        "- 专长：专长11.md → `专长/极限荒野UW_专长.md`",
        "- 物品：物品3.md → 按子类型拆分：",
        "  - 冒险装备表格与 28 个条目 → `装备_魔法物品/货品服务/page_210.md`",
        "  - 擦剂 → `装备_魔法物品/货品服务/page_212.md`",
        "  - 蛮兽裹布 → `装备_魔法物品/魔法物品/奇物/极限荒野UW_奇物.md`",
        "  - 旧聚合文件 `装备_魔法物品/魔法物品/极限荒野UW_物品.md` 已删除",
        "- 魔法植物：魔法植物.md → `装备_魔法物品/魔法物品/极限荒野UW_魔法植物.md`",
        "- 武器附魔：武器附魔9.md → `装备_魔法物品/武器附魔/极限荒野UW_武器附魔.md`",
        "- 自然仪式：自然仪式.md → `法术/极限荒野UW_自然仪式.md`",
        "- 动物伙伴专长：伙伴/动物伙伴专长.md → `专长/极限荒野UW_动物伙伴专长.md`",
        "- 动物装备栏位修正：伙伴/动物装备栏位修正.md → `规则/极限荒野UW_动物装备栏位修正.md`",
        "- 新动物伙伴：伙伴/page_1419.md → `规则/极限荒野UW_新动物伙伴.md`",
        "- 植物伙伴：伙伴/page_1420.md → `规则/极限荒野UW_植物伙伴.md`",
        "- 昆虫伙伴：伙伴/page_1421.md → `规则/极限荒野UW_昆虫伙伴.md`",
        "- 动物伙伴变体：伙伴/page_1422.md → `规则/极限荒野UW_动物伙伴变体.md`",
        "- 魔宠变体：伙伴/page_1461.md → `规则/极限荒野UW_魔宠变体.md`",
        "- 新基础魔宠：伙伴/page_1493.md → `规则/极限荒野UW_新基础魔宠.md`",
        "- 职业变体：职业变体_选项/ 下全部文件 → 各职业对应变体页面",
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

    # 17. 重复记录
    if duplicates:
        dup_lines = ["", "", "## 极限荒野（Ultimate Wilderness）", "", f"**发现时间**：2026-06-19", ""]
        dup_lines.append("| 来源文件 | 条目 | 目标文件 | 备注 |")
        dup_lines.append("|----------|------|----------|------|")
        for d in duplicates:
            en = f" / {d['english']}" if d["english"] else ""
            dup_lines.append(f"| {d['source']} | {d['title']}{en} | {d['target']} | {d['reason']} |")
        dup_lines.append("")
        with open(DUP_RECORD_PATH, "a", encoding="utf-8") as f:
            f.write("\n".join(dup_lines))

    # 18. 问题记录
    if os.path.exists(PROBLEM_RECORD_PATH):
        problem_text = open(PROBLEM_RECORD_PATH, "r", encoding="utf-8").read()
    else:
        problem_text = ""

    def ensure_problem(anchor, block):
        nonlocal problem_text
        if anchor not in problem_text:
            problem_text += block
            with open(PROBLEM_RECORD_PATH, "a", encoding="utf-8") as f:
                f.write(block)

    ensure_problem("UW-FEATS", """

## 极限荒野（Ultimate Wilderness）

### UW-FEATS：专长文件标题跨行且存在重复条目

- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：`影响轻微`
- **涉及文件**：`专长11.md`
- **问题描述**：部分专长的中文名称和英文名称跨行（如 `**突袭警惕（Ambush\nAwareness）**`）。此外，文件中存在重复条目（如 `突袭警惕` 和 `动物凶猛` 各出现两次，一次无标签一次有〔战斗〕标签）。脚本通过 `detect_title_starts` 自动检测标题行，并合并跨行标题；重复条目会被分别提取。
- **当前处理**：已使用 `process_auto_split_file` 处理，按标题自动拆分并合并到 `专长/极限荒野UW_专长.md`。
- **备注**：需人工复核拆分边界是否正确，并处理重复条目。

### UW-ITEMS：物品文件格式复杂

- **问题归类**：`markdown格式` / `条目归属待确认`
- **严重程度**：`需要人工校验`
- **涉及文件**：`物品3.md`
- **问题描述**：物品文件包含大型表格（表格7-1：冒险装备） followed by  individual item descriptions。表格条目和具体物品描述混在一起，自动拆分困难。此外文件末尾还有 `擦剂` 和 `蛮兽裹布` 两个特殊物品。
- **当前处理**：本次将 `物品3.md` 作为整体文件合并到 `装备_魔法物品/魔法物品/极限荒野UW_物品.md`。
- **备注**：建议后续人工按物品子类型分类后，再拆分合并到 `装备_魔法物品/` 各子目录。

### UW-ARCHETYPES：职业变体文件格式不统一

- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：`影响轻微`
- **涉及文件**：`职业变体_选项/` 下全部文件
- **问题描述**：变体标题格式多样，有些以 `**名称(English)**` 开头，有些以 `**名称**` 开头，有些没有加粗。同一文件内可能包含多个变体（如 `page_1428.md` 包含 4 个拳师变体）。
- **当前处理**：在 `SECTIONS` 中为每个变体指定 `marker`，脚本按子串定位。
- **备注**：需人工复核每个变体的拆分边界是否正确。

### UW-PAGE1429：护林官与巡林客内容重复

- **问题归类**：`条目归属待确认`
- **严重程度**：`影响轻微`
- **涉及文件**：`page_1429.md`
- **问题描述**：`page_1429.md` 包含两个内容几乎相同的猎人变体（护林官/Forester 和 巡林客/Forester），只是翻译不同。脚本只处理了 `人猿泰山` 变体，跳过了重复的护林官/巡林客。
- **当前处理**：只合并了 `人猿泰山` 变体。
- **备注**：护林官与巡林客为同一变体的不同翻译，无需重复合并。

### UW-SHIFTER：变形者职业目录缺失

- **问题归类**：`目标位置待确认`
- **严重程度**：`需要人工校验`
- **涉及文件**：`page_1428.md`（野性袭者变体提及变形者）
- **问题描述**：`pf_rules_md_organized/职业/` 下没有 `变形者` 目录，变形者是 UW 引入的新职业，其变体可能应放入新目录。
- **当前处理**：野性袭者作为拳师变体处理（因为它修改拳师职业特性）。
- **备注**：如需为变形者建立独立目录，需后续统一决策。
""")

    print(f"整理完成：新增 {stats['added']} 条，跳过 {stats['skipped']} 条，错误 {len(stats['errors'])} 条。")
    if stats["errors"]:
        for e in stats["errors"]:
            print("  ERROR:", e)


if __name__ == "__main__":
    main()
