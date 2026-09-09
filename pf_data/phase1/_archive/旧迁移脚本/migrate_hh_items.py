#!/usr/bin/env python3
"""
迁移 HH/HHH 内容到对应的 page_X.md 已有页面。

按规则"按物品子类型拆分，通过目录/TOC 找到对应已有文件并追加"：
- 戒指 → page_220.md (唯一对应)
- 奇物带具体身体部位 → page_22X.md (按部位)
- 奇物无身体部位 → 保留在源书聚合文件 (符合现有 PA/VC 模式)
"""

import re
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1/pf_rules_md_organized/装备_魔法物品/魔法物品")

# HH 奇物各条目按身体部位的目标页
HH_WONDROUS_MAPPING = {
    "盗命手套": "奇物/page_228.md",      # 手部
    "银色魂索": "奇物/page_223.md",      # 腰部
    "看护项链": "奇物/page_231.md",      # 颈部
    # 以下条目无身体部位，保留在源书聚合文件
    "医师挎包": None,
    "悼念之根": None,
    "凤凰之羽": None,
    "抒情竖琴": None,
    "巨魔皮革止血带": None,
    "独角兽邪角": None,
}

# HH 戒指目标
HH_RING_TARGET = "戒指_权杖_法杖/page_220.md"


def extract_entries(content: str, source_marker: str) -> dict:
    """从源文件提取所有带 source_marker 的条目，按中文标题索引。"""
    entries = {}
    pattern = re.compile(
        r'<!-- ' + re.escape(source_marker) + r':([^:]+):([^>]+?) -->\n'
        r'(\*\*[^*]+\*\*[^\n]*\n(?:[^<]*\n)*)',
        re.MULTILINE
    )
    for m in pattern.finditer(content):
        title = m.group(2).strip()
        body = m.group(3)
        entries[title] = (m.group(1), body, m.group(0))
    return entries


def append_to_file(target_path: Path, entry_block: str, source_marker: str):
    """追加条目到目标文件，确保前缀有空行分隔。"""
    target = BASE / target_path
    content = target.read_text(encoding='utf-8')
    if not content.endswith('\n'):
        content += '\n'
    content += '\n' + entry_block + '\n'
    target.write_text(content, encoding='utf-8')


def remove_entries_from_file(source_path: Path, source_marker: str, titles_to_remove: set):
    """从源文件删除指定标题的条目。"""
    content = source_path.read_text(encoding='utf-8')
    pattern = re.compile(
        r'<!-- ' + re.escape(source_marker) + r':([^:]+):([^>]+?) -->\n'
        r'(\*\*[^*]+\*\*[^\n]*\n(?:[^<]*\n)*)',
        re.MULTILINE
    )
    new_content = pattern.sub(
        lambda m: '' if m.group(2).strip() in titles_to_remove else m.group(0),
        content
    )
    source_path.write_text(new_content, encoding='utf-8')


def migrate_ring():
    """HH 戒指 → page_220.md。"""
    src = BASE / "戒指_权杖_法杖/治疗者手册HH_戒指.md"
    target = BASE / HH_RING_TARGET

    content = src.read_text(encoding='utf-8')
    entries = extract_entries(content, "HH-source")

    moved = []
    for title, (page, body, full) in entries.items():
        if title == "回生之戒":
            append_to_file(Path(HH_RING_TARGET), full, "HH-source")
            moved.append(title)

    # 从源文件删除已迁移条目
    if moved:
        remove_entries_from_file(src, "HH-source", set(moved))
        print(f"HH 戒指: 迁移 {len(moved)} 个条目 → page_220.md")
    else:
        print("HH 戒指: 没有找到条目")
    return moved


def migrate_wondrous():
    """HH 奇物按身体部位迁移。"""
    src = BASE / "奇物/治疗者手册HH_奇物.md"
    content = src.read_text(encoding='utf-8')
    entries = extract_entries(content, "HH-source")

    moved = []
    kept = []
    for title, (page, body, full) in entries.items():
        target_path = HH_WONDROUS_MAPPING.get(title)
        if target_path:
            append_to_file(Path(target_path), full, "HH-source")
            moved.append(title)
            print(f"  {title} → {target_path}")
        else:
            kept.append(title)
            print(f"  {title} → 保留在 HH_奇物 (无身体部位)")

    if moved:
        # 从源文件删除已迁移条目
        remove_entries_from_file(src, "HH-source", set(moved))

        # 如果源文件为空或只剩下标题，删除源文件
        remaining = src.read_text(encoding='utf-8').strip()
        if not remaining or len(remaining) < 50:
            src.unlink()
            print(f"  删除: {src.name}")

    print(f"HH 奇物: 迁移 {len(moved)} 个条目, 保留 {len(kept)} 个无部位条目")
    return moved, kept


if __name__ == "__main__":
    print("=" * 50)
    print("HH 戒指迁移")
    print("=" * 50)
    migrate_ring()

    print("\n" + "=" * 50)
    print("HH 奇物迁移")
    print("=" * 50)
    migrate_wondrous()