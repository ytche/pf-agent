#!/usr/bin/env python3
"""Phase 2: 格式优化 - 清理"其他翻译"列 + 生成缩写附录"""

import argparse
import json
import re
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Phase 2: 格式优化 - 清理'其他翻译'列 + 生成缩写附录")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path(__file__).parent,
        help="phase1 工作目录，默认脚本所在目录",
    )
    return parser.parse_args()


ARGS = parse_args()
BASE_DIR = ARGS.base_dir.resolve()
INPUT_FILE = BASE_DIR / "术语提取报告_重分类版.md"
OUTPUT_FINAL = BASE_DIR / "术语提取报告_优化版.md"
OUTPUT_ABBREV = BASE_DIR / "PF_缩写表.md"
OUTPUT_JSON = BASE_DIR / "terms.json"
LOG_FILE = BASE_DIR / "优化日志.md"


def clean_others(others_text, recommended):
    """清理"其他翻译"列：去掉括号数字和句子，只保留不同译名"""
    if not others_text or others_text.strip() == "":
        return ""
    
    # 去掉所有括号数字
    cleaned = re.sub(r'\(\d+\)', '', others_text)
    
    # 按逗号、顿号分割
    parts = [p.strip() for p in re.split(r'[,，、]', cleaned)]
    
    # 过滤：去掉空、去掉和推荐翻译相同的、去掉明显是句子的（长度>15或含描述词开头）
    bad_starts = ["该", "就", "和", "或", "此", "这", "如", "类", "每", "任", "即", "一", "级", "你", "他", "她", "它", "能", "可", "会", "将", "使", "让", "被", "受", "遭", "经", "由", "从", "向", "往", "到", "在", "于", "对", "为", "与", "及", "同", "跟", "比", "较", "更", "最", "很", "非", "无", "没", "未", "别", "勿", "莫", "毋", "如果", "每当", "任何"]
    
    unique = []
    seen = set()
    for p in parts:
        if not p:
            continue
        if len(p) > 15:
            continue
        if any(p.startswith(b) for b in bad_starts):
            continue
        if p == recommended:
            continue
        if p in seen:
            continue
        seen.add(p)
        unique.append(p)
    
    return ", ".join(unique) if unique else ""


def parse_and_clean(content):
    """解析并清理"其他翻译"列"""
    sections = []
    current_section = None
    current_terms = []
    lines = content.split('\n')
    
    for line in lines:
        line = line.strip()
        
        if line.startswith('## '):
            if current_section and current_terms:
                sections.append((current_section, current_terms))
            current_section = line[3:].strip()
            current_terms = []
        
        elif line.startswith('|') and current_section:
            parts = [p.strip() for p in line.split('|')]
            parts = [p for p in parts if p]
            
            if len(parts) >= 4 and parts[0] != '英文术语' and '---' not in parts[0]:
                english = parts[0]
                recommended = parts[1] if len(parts) > 1 else ""
                others = parts[2] if len(parts) > 2 else ""
                count = parts[3] if len(parts) > 3 else "0"
                
                # 清理"其他翻译"
                cleaned_others = clean_others(others, recommended)
                
                current_terms.append({
                    'english': english,
                    'recommended': recommended,
                    'others': cleaned_others,
                    'count': count
                })
    
    if current_section and current_terms:
        sections.append((current_section, current_terms))
    
    return sections


def main():
    print("读取重分类版...")
    content = INPUT_FILE.read_text(encoding='utf-8')
    
    print("清理\"其他翻译\"列...")
    sections = parse_and_clean(content)
    
    # 生成最终优化版
    print("生成最终优化版...")
    output = ["# PathFinder 1e 中英术语对照表（优化版）\n\n"]
    output.append("_推荐翻译已清洗，其他翻译已精简，分类已重新组织_\n\n")
    
    total_terms = 0
    for section_name, terms in sections:
        if terms:
            category = re.split(r"[（(]", section_name)[0].strip()
            output.append(f"## {category}（{len(terms)} 个术语）\n\n")
            output.append("| 英文术语 | 推荐翻译 | 其他翻译 | 出现次数 |\n")
            output.append("|---------|---------|---------|---------|\n")
            sorted_terms = sorted(terms, key=lambda x: int(x['count']) if x['count'].isdigit() else 0, reverse=True)
            for term in sorted_terms:
                output.append(f"| {term['english']} | {term['recommended']} | {term['others']} | {term['count']} |\n")
            output.append("\n")
            total_terms += len(terms)
    
    OUTPUT_FINAL.write_text(''.join(output), encoding='utf-8')
    print(f"已生成: {OUTPUT_FINAL} ({total_terms} 个术语)")
    
    # 生成 JSON 版本
    print("生成 JSON 版本...")
    json_terms = []
    for section_name, terms in sections:
        # 从 "法术（157 个术语）" 中提取分类名
        category = re.split(r'[（(]', section_name)[0].strip()
        for term in terms:
            json_terms.append({
                "english": term['english'],
                "recommended": term['recommended'],
                "category": category,
                "count": int(term['count']) if term['count'].isdigit() else 0,
                "other_translations": [t.strip() for t in term['others'].split(',') if t.strip()]
            })

    OUTPUT_JSON.write_text(
        json.dumps(json_terms, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    print(f"已生成: {OUTPUT_JSON} ({len(json_terms)} 个术语)")

    # 生成缩写表
    print("生成缩写表...")
    abbrev = ["# PF 1e 常见缩写对照表\n\n"]
    abbrev.append("_法术成分、能力类型、动作类型等常见缩写_\n\n")
    
    abbrev.append("## 法术成分\n\n")
    abbrev.append("| 缩写 | 全称 | 中文 |\n")
    abbrev.append("|-----|------|------|\n")
    abbrev.append("| V | Verbal | 语言成分 |\n")
    abbrev.append("| S | Somatic | 肢体成分 |\n")
    abbrev.append("| M | Material | 材料成分 |\n")
    abbrev.append("| F | Focus | 器材成分 |\n")
    abbrev.append("| DF | Divine Focus | 法器 |\n")
    abbrev.append("| XP | Experience Points | 经验值 |\n\n")
    
    abbrev.append("## 能力类型\n\n")
    abbrev.append("| 缩写 | 全称 | 中文 |\n")
    abbrev.append("|-----|------|------|\n")
    abbrev.append("| Sp | Spell-Like Ability | 类法术能力 |\n")
    abbrev.append("| Su | Supernatural Ability | 超自然能力 |\n")
    abbrev.append("| Ex | Extraordinary Ability | 特异能力 |\n\n")
    
    abbrev.append("## 动作类型\n\n")
    abbrev.append("| 缩写 | 全称 | 中文 |\n")
    abbrev.append("|-----|------|------|\n")
    abbrev.append("| SA | Standard Action | 标准动作 |\n")
    abbrev.append("| MA | Move Action | 移动动作 |\n")
    abbrev.append("| FA | Free Action | 自由动作 |\n")
    abbrev.append("| SW | Swift Action | 迅捷动作 |\n")
    abbrev.append("| IA | Immediate Action | 直觉动作 |\n")
    abbrev.append("| AOO | Attack of Opportunity | 借机攻击 |\n\n")
    
    abbrev.append("## 核心属性\n\n")
    abbrev.append("| 缩写 | 全称 | 中文 |\n")
    abbrev.append("|-----|------|------|\n")
    abbrev.append("| AC | Armor Class | 护甲等级 |\n")
    abbrev.append("| HP | Hit Points | 生命值 |\n")
    abbrev.append("| BAB | Base Attack Bonus | 基础攻击加值 |\n")
    abbrev.append("| CMB | Combat Maneuver Bonus | 战技加值 |\n")
    abbrev.append("| CMD | Combat Maneuver Defense | 战技防御 |\n")
    abbrev.append("| SR | Spell Resistance | 法术抗力 |\n")
    abbrev.append("| DC | Difficulty Class | 难度等级 |\n\n")
    
    abbrev.append("## 豁免类型\n\n")
    abbrev.append("| 缩写 | 全称 | 中文 |\n")
    abbrev.append("|-----|------|------|\n")
    abbrev.append("| Fort | Fortitude | 强韧 |\n")
    abbrev.append("| Ref | Reflex | 反射 |\n")
    abbrev.append("| Will | Will | 意志 |\n\n")
    
    abbrev.append("## 其他\n\n")
    abbrev.append("| 缩写 | 全称 | 中文 |\n")
    abbrev.append("|-----|------|------|\n")
    abbrev.append("| CR | Challenge Rating | 挑战等级 |\n")
    abbrev.append("| CL | Caster Level | 施法者等级 |\n")
    abbrev.append("| HD | Hit Dice | 生命骰 |\n")
    abbrev.append("| NPC | Non-Player Character | 非玩家角色 |\n")
    abbrev.append("| PC | Player Character | 玩家角色 |\n")
    abbrev.append("| GM | Game Master | 游戏主持人 |\n")
    abbrev.append("| XP | Experience Points | 经验值 |\n")
    abbrev.append("| PP | Platinum Piece | 白金币 |\n")
    abbrev.append("| GP | Gold Piece | 金币 |\n")
    abbrev.append("| SP | Silver Piece | 银币 |\n")
    abbrev.append("| CP | Copper Piece | 铜币 |\n")
    
    OUTPUT_ABBREV.write_text(''.join(abbrev), encoding='utf-8')
    print(f"已生成: {OUTPUT_ABBREV}")
    
    # 追加日志
    log = LOG_FILE.read_text(encoding='utf-8')
    log += f"\n\n## Phase 2: 格式优化\n\n"
    log += f"- 生成最终优化版: {OUTPUT_FINAL}\n"
    log += f"- 生成缩写表: {OUTPUT_ABBREV}\n"
    log += f"- 生成 JSON: {OUTPUT_JSON}\n"
    log += f"- 总术语数: {total_terms}\n"
    LOG_FILE.write_text(log, encoding='utf-8')
    print(f"已更新日志")
    
    print("\nPhase 2 完成！")


if __name__ == '__main__':
    main()
