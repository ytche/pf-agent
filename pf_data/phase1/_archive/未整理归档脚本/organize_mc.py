#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
整理 怪物法典MC（Monster Codex）到 种族/怪物种族/怪物法典MC/ 下。
按种族拆分，每个种族一个文件，保留原文结构，添加来源标注。
"""

import os
import re
import shutil

SRC_DIR = "/Users/chezi/code/java/pf_agent/pf_data/phase1/pf_rules_md/未整理/怪物法典MC"
DST_DIR = "/Users/chezi/code/java/pf_agent/pf_data/phase1/pf_rules_md_organized/种族/怪物种族/怪物法典MC"

# 种族文件名映射：page_XXXX.md -> 种族名.md
RACE_FILES = [
    ("page_1398.md", "沼蜍人.md"),
    ("page_1399.md", "熊地精.md"),
    ("page_1400.md", "卓尔精灵.md"),
    ("page_1401.md", "灰矮人.md"),
    ("page_1402.md", "火巨人.md"),
    ("page_1403.md", "霜巨人.md"),
    ("page_1404.md", "食尸鬼.md"),
    ("page_1405.md", "豺狼人.md"),
    ("page_1406.md", "地精.md"),
    ("page_1407.md", "大地精.md"),
    ("page_1408.md", "狗头人.md"),
    ("page_1409.md", "蜥蜴人.md"),
    ("page_1410.md", "食人魔.md"),
    ("page_1411.md", "兽人.md"),
    ("page_1412.md", "鼠族.md"),
    ("page_1413.md", "沙华鱼人.md"),
    ("page_1414.md", "蛇人.md"),
    ("page_1415.md", "战蜥人.md"),
    ("page_1416.md", "巨魔.md"),
    ("page_1417.md", "吸血鬼.md"),
]

def make_source_note(race_name):
    return f"> 来源：怪物志（Monster Codex）MC，页码见原书，未整理 → 怪物法典MC → {race_name}"


def process_file(src_path, race_name, dst_path):
    with open(src_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    out_lines = []
    title_added = False

    for i, line in enumerate(lines):
        out_lines.append(line)

        # 在种族标题下一行添加总来源标注（只加一次）
        # MC 每个种族文件本身就是该种族全部“新规则”的集合，作为一个整体标注来源
        if not title_added and line.strip() == f"**{race_name}**":
            if i + 1 < len(lines) and not lines[i + 1].strip().startswith("> 来源："):
                out_lines.append("\n")
                out_lines.append(make_source_note(race_name) + "\n")
                title_added = True

    # 确保文件末尾有空行
    if out_lines and not out_lines[-1].endswith("\n"):
        out_lines.append("\n")

    with open(dst_path, "w", encoding="utf-8") as f:
        f.writelines(out_lines)


def main():
    os.makedirs(DST_DIR, exist_ok=True)

    for src_name, dst_name in RACE_FILES:
        src_path = os.path.join(SRC_DIR, src_name)
        dst_path = os.path.join(DST_DIR, dst_name)
        race_name = dst_name.replace(".md", "")

        if not os.path.exists(src_path):
            print(f"[跳过] 源文件不存在: {src_path}")
            continue

        process_file(src_path, race_name, dst_path)
        print(f"[已生成] {dst_path}")


if __name__ == "__main__":
    main()
