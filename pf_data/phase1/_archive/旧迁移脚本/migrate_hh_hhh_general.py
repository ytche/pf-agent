#!/usr/bin/env python3
"""
迁移 HH/HHH 通用规则到已有页面，删除源书聚合文件（仅保留源书特有规则部分）。

按规则文档 §4.0 源书聚合原则：
- 通用规则 → 已有同类型文件（Spell CRB.md, 反派法典VC_专长.md 等）
- 源书特有规则 → 保留在 <来源书>_<类型>.md
"""

import re
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1/pf_rules_md_organized")


def find_entry_span(content: str, source_marker: str, title: str) -> tuple:
    """
    找到带 source_marker 的条目起止位置。
    条目格式：
      <!-- <source_marker>:<page>:title -->
      **title（English Name）**
      > 来源：...
      ... 正文 ...
    """
    # 找到该 marker 的起始行
    marker_pat = re.compile(
        r'<!--\s*' + re.escape(source_marker) + r':[^\n]*?-->\s*\n'
        r'\*\*\s*' + re.escape(title) + r'[^\n]*\n'
    )
    m = marker_pat.search(content)
    if not m:
        return None, -1, -1

    start = m.start()

    # 找到下一个 marker（下一个条目的开始）或文件末尾
    next_marker_pat = re.compile(r'<!--\s*[A-Z]+-source:')
    next_m = next_marker_pat.search(content, m.end())
    if next_m:
        # 删除最后一个条目末尾的空行
        end = next_m.start()
        # 退回到上一个换行符
        end = content.rfind('\n', 0, end) + 1
    else:
        # 没有下一个 marker，取到末尾
        end = len(content)

    return content[start:end].rstrip() + '\n', start, end


def remove_entry_from_source(content: str, source_marker: str, title: str) -> tuple:
    """从源文件内容中删除指定标题的条目，返回 (new_content, removed_count)。"""
    entry_text, start, end = find_entry_span(content, source_marker, title)
    if entry_text is None:
        return content, 0
    new_content = content[:start] + content[end:]
    # 清理多余空行
    new_content = re.sub(r'\n{3,}', '\n\n', new_content)
    return new_content, 1


def append_to_file(target_path: Path, entry_block: str):
    """追加条目到目标文件末尾，确保前缀有空行分隔。"""
    content = target_path.read_text(encoding='utf-8')
    if not content.endswith('\n'):
        content += '\n'
    content += '\n' + entry_block.rstrip() + '\n'
    target_path.write_text(content, encoding='utf-8')


# ============ HH 通用治疗/女巫法术 → Spell CRB.md ============
HH_GENERAL_SPELLS = [
    "医疗标记",
    "疗效升华",
    "医疗圣炎",
    "净化躯体",
    "鼓舞复苏",
    "痛苦平衡",
    "愚者之灾",
]


def migrate_hh_spells():
    """HH 通用治疗/女巫法术 → Spell CRB.md"""
    target = BASE / "法术/Spell CRB.md"
    sources = [
        BASE / "法术/治疗者手册HH_医疗法术.md",
        BASE / "法术/治疗者手册HH_女巫法术.md",
    ]

    moved = []
    for src in sources:
        if not src.exists():
            continue
        content = src.read_text(encoding='utf-8')
        for title in HH_GENERAL_SPELLS:
            entry_text, _, _ = find_entry_span(content, "HH-source", title)
            if entry_text:
                append_to_file(target, entry_text)
                content, count = remove_entry_from_source(content, "HH-source", title)
                if count > 0:
                    moved.append(title)
        src.write_text(content, encoding='utf-8')

    # 删除空的源文件
    for src in sources:
        remaining = src.read_text(encoding='utf-8').strip()
        if len(remaining) < 30:
            src.unlink()
            print(f"  删除: {src.name}")

    print(f"HH 通用法术 → Spell CRB.md: 迁移 {len(moved)} 条")
    return moved


# ============ HHH 通用驱魔仪式 → UW_自然仪式.md ============
HHH_GENERAL_RITUALS = [
    "地缚结界",
    "驱除作祟",
    "采集亵渎之魂",
    "诅咒之音",
]


def migrate_hhh_rituals():
    """HHH 驱魔仪式 → 极限荒野UW_自然仪式.md（已有通用仪式聚合文件）"""
    src = BASE / "法术/闹鬼英雄手册HHH_驱魔仪式.md"
    target = BASE / "法术/极限荒野UW_自然仪式.md"

    if not src.exists():
        print("HHH 驱魔仪式: 源文件不存在")
        return []

    content = src.read_text(encoding='utf-8')
    moved = []
    for title in HHH_GENERAL_RITUALS:
        entry_text, _, _ = find_entry_span(content, "HHH-source", title)
        if entry_text:
            append_to_file(target, entry_text)
            content, count = remove_entry_from_source(content, "HHH-source", title)
            if count > 0:
                moved.append(title)

    src.write_text(content, encoding='utf-8')

    remaining = content.strip()
    if len(remaining) < 30:
        src.unlink()
        print(f"  删除: {src.name}")

    print(f"HHH 驱魔仪式 → UW_自然仪式.md: 迁移 {len(moved)} 条")
    return moved


# ============ HH 无部位奇物 → body-slot pages ============
HH_SLOTLESS_WONDROUS = {
    "抒情竖琴": "奇物/page_228.md",      # 手部（手持演奏）
    "凤凰之羽": "奇物/page_228.md",      # 手部（手持触发）
    "独角兽邪角": "奇物/page_228.md",    # 手部（手持）
    "医师挎包": "奇物/page_232.md",      # 肩部（背挎）
    "巨魔皮革止血带": "奇物/page_233.md",  # 腕部（缠绕肢体末端）
    "悼念之根": "奇物/page_233.md",      # 腕部（带在腕部使用）
}


def migrate_hh_slotless_wondrous():
    """HH 奇物无部位条目 → 按物品性质分配到身体部位页"""
    src = BASE / "装备_魔法物品/魔法物品/奇物/治疗者手册HH_奇物.md"

    if not src.exists():
        print("HH 奇物: 源文件不存在")
        return []

    content = src.read_text(encoding='utf-8')
    moved = []
    for title, target_rel in HH_SLOTLESS_WONDROUS.items():
        entry_text, _, _ = find_entry_span(content, "HH-source", title)
        if entry_text:
            target = BASE / f"装备_魔法物品/魔法物品/{target_rel}"
            append_to_file(target, entry_text)
            content, count = remove_entry_from_source(content, "HH-source", title)
            if count > 0:
                moved.append(f"{title} → {target_rel}")

    src.write_text(content, encoding='utf-8')

    remaining = content.strip()
    if len(remaining) < 30:
        src.unlink()
        print(f"  删除: {src.name}")
    else:
        print(f"  保留: {src.name} (有未迁移内容)")

    print(f"HH 无部位奇物 → 身体部位页: 迁移 {len(moved)} 条")
    for m in moved:
        print(f"  {m}")
    return moved


# ============ HH 通用专长 → 反派法典VC_专长.md ============
HH_GENERAL_FEATS = [
    "触发医疗法术",
    "治愈掌握",
    "生命界限",
    "战斗活力",
    "强韧活力",
    "复原活力",
    "借机喘息",
    "不屈决意",
    "生龙活虎",
    "限制法术",
    "阴险治疗",
    "痛苦治愈",
]


def migrate_hh_feats():
    """HH 通用专长 → 反派法典VC_专长.md（已有同类型聚合文件）"""
    src = BASE / "专长/治疗者手册HH_专长.md"
    target = BASE / "专长/反派法典VC_专长.md"

    if not src.exists():
        print("HH 专长: 源文件不存在")
        return []

    content = src.read_text(encoding='utf-8')
    moved = []
    for title in HH_GENERAL_FEATS:
        entry_text, _, _ = find_entry_span(content, "HH-source", title)
        if entry_text:
            append_to_file(target, entry_text)
            content, count = remove_entry_from_source(content, "HH-source", title)
            if count > 0:
                moved.append(title)

    src.write_text(content, encoding='utf-8')

    remaining = content.strip()
    if len(remaining) < 30:
        src.unlink()
        print(f"  删除: {src.name}")
    else:
        print(f"  保留: {src.name} (有未迁移内容)")

    print(f"HH 通用专长 → VC_专长.md: 迁移 {len(moved)} 条")
    return moved


# ============ HHH 通用专长 → 反派法典VC_专长.md；保留 HHH 源书特有专长 ============
HHH_GENERAL_FEATS = ["解说之策"]
# 源书特有：依赖"鬼上手"前置的专长链 + 精魄/英灵/魅影/十方鬼众等灵界机制
HHH_SPECIFIC_FEATS = [
    "鬼上手", "自动手", "人手分离", "手不释卷", "手心长眼",
    "精魄受体", "英灵受体", "精魄盟友", "精神训练",
    "虚幻杀手", "灵魂打击", "魂刃", "魅影盟友", "十方鬼众", "作祟拾荒者",
]


def migrate_hhh_feats():
    """HHH 通用专长 → VC_专长.md；源书特有专长保留 HHH 文件"""
    src = BASE / "专长/闹鬼英雄手册HHH_专长.md"
    target = BASE / "专长/反派法典VC_专长.md"

    if not src.exists():
        print("HHH 专长: 源文件不存在")
        return []

    content = src.read_text(encoding='utf-8')
    moved = []
    for title in HHH_GENERAL_FEATS:
        entry_text, _, _ = find_entry_span(content, "HHH-source", title)
        if entry_text:
            append_to_file(target, entry_text)
            content, count = remove_entry_from_source(content, "HHH-source", title)
            if count > 0:
                moved.append(title)

    src.write_text(content, encoding='utf-8')

    remaining_count = content.count(f'<!-- HHH-source:')
    print(f"HHH 通用专长 → VC_专长.md: 迁移 {len(moved)} 条; 保留 {remaining_count} 条源书特有专长")
    return moved


# ============ HH 通用背景特性 → 背景特性17.md ============
HH_GENERAL_TRAITS = [
    "血腥复仇", "医疗特使", "战争伤痕", "灵魂搜寻者之力", "知名医师",
    "楚业后裔", "艾欧巴瑞亚幸存者", "镇咒者", "受训药剂师", "法力废土医师",
    "熟练外科医生", "濒死体验", "女巫借贷", "雅德维加医学", "庇护主之赐",
    "无信决意", "续命表演", "兽魂活力", "游击改进者", "芒吉草药传统",
    "英灵从者",
]


def migrate_hh_traits():
    """HH 通用背景特性 → 背景特性17.md（已有同类型聚合文件）"""
    src = BASE / "背景特性/治疗者手册HH_背景特性.md"
    target = BASE / "背景特性/背景特性17.md"

    if not src.exists():
        print("HH 背景特性: 源文件不存在")
        return []

    content = src.read_text(encoding='utf-8')
    moved = []
    for title in HH_GENERAL_TRAITS:
        entry_text, _, _ = find_entry_span(content, "HH-source", title)
        if entry_text:
            append_to_file(target, entry_text)
            content, count = remove_entry_from_source(content, "HH-source", title)
            if count > 0:
                moved.append(title)

    src.write_text(content, encoding='utf-8')

    remaining = content.strip()
    if len(remaining) < 30:
        src.unlink()
        print(f"  删除: {src.name}")
    else:
        print(f"  保留: {src.name} (有未迁移内容)")

    print(f"HH 通用背景特性 → 背景特性17.md: 迁移 {len(moved)} 条")
    return moved


if __name__ == "__main__":
    print("=" * 60)
    print("HH/HHH 通用规则迁移")
    print("=" * 60)

    print("\n--- HH 通用法术 → Spell CRB.md ---")
    migrate_hh_spells()

    print("\n--- HHH 通用仪式 → UW_自然仪式.md ---")
    migrate_hhh_rituals()

    print("\n--- HH 无部位奇物 → 身体部位页 ---")
    migrate_hh_slotless_wondrous()

    print("\n--- HH 通用专长 → VC_专长.md ---")
    migrate_hh_feats()

    print("\n--- HHH 通用专长 → VC_专长.md ---")
    migrate_hhh_feats()

    print("\n--- HH 通用背景特性 → 背景特性17.md ---")
    migrate_hh_traits()