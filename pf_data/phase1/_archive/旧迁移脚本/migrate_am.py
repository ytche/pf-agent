#!/usr/bin/env python3
"""
迁移炼金术手册AM条目：通用→已有页面，源书特有→AM聚合文件。

源目录: pf_data/phase1/pf_rules_md/未整理/炼金术手册AM/

AM 内容高度按文化/主题拆分，源书特有占多数：
- 通用专长（6 条：4 毒药 + 2 炼金）→ 反派法典VC_专长.md
- 通用野蛮人变体（1 条：狂暴饮者）→ 职业/核心职业/野蛮人/page_35.md
- 通用无位置奇物（4 条：魔法烧瓶和圆瓶）→ 装备_魔法物品/魔法物品/奇物/无位置/page_568.md
- 源书特有：
  - AM_专长.md（创造泥怪）
  - AM_物品.md（所有文化相关炼金物品、矮人魔啤、本草、烟花、工具等）
  - AM_毒药.md（兽人/匕痕/德洛/卡塔佩什毒药与毒品）
  - AM_装备.md（兽人武器 + 卡塔佩什水烟管）
  - AM_强化人造人.md（6 个改装）
  - AM_神话炼金.md（2 道途 + 6 神话物品）
  - AM_自发炼金术.md（系统 + 流程 + 工具 + 2 专长 + 事故表）
  - AM_真菌移植物.md（2 个真菌移植物）
"""

import re
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1/pf_rules_md_organized")
SOURCE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1/pf_rules_md/未整理/炼金术手册AM")

AM = "AM"  # 源书标记


# ============ 工具函数 ============
def merge_multiline_titles(content: str) -> str:
    """
    合并跨行的 ** 标题。
    例如：**浓缩烧瓶(Focusing\nFlask)** → **浓缩烧瓶(Focusing Flask)**
    规则：匹配 **xxx (无闭合) 后续行 (无开头 **) ** 的模式。
    """
    # 合并 **起始 且 未在同一行闭合 的标题
    pat = re.compile(r'^(\*\*[^*\n]+)$\n^([^*\n]+\*\*)$', re.MULTILINE)
    while True:
        new_content = pat.sub(r'\1 \2', content)
        if new_content == content:
            break
        content = new_content
    return content


def split_into_sections(content: str) -> list:
    """
    按 **标题** 行切分文本。返回 [(title, body), ...]
    """
    # 先合并多行标题
    content = merge_multiline_titles(content)
    title_pat = re.compile(r'^\*\*[^*\n]+\*\*[ \t]*$', re.MULTILINE)
    sections = []
    matches = list(title_pat.finditer(content))
    if not matches:
        return [(None, content)]
    pre = content[:matches[0].start()]
    if pre.strip():
        sections.append((None, pre))
    for i, m in enumerate(matches):
        title = m.group(0).strip().strip('*').strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        sections.append((title, content[start:end]))
    return sections


def find_section_span(content: str, title_keyword: str) -> tuple:
    """
    找到含 title_keyword 的章节起止位置。
    返回 (body, start, end)；若未找到返回 (None, -1, -1)。
    """
    content = merge_multiline_titles(content)
    title_pat = re.compile(r'^\*\*[^*\n]+\*\*[ \t]*$', re.MULTILINE)
    matches = list(title_pat.finditer(content))
    for i, m in enumerate(matches):
        title = m.group(0).strip().strip('*').strip()
        if title_keyword in title:
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            return content[start:end].rstrip() + '\n', start, end
    return None, -1, -1


def find_ooze_section(content: str) -> tuple:
    """
    制造泥怪专长章节：标题在 **制造泥怪 OOZE Crafting** 下，
    后面跟着 **创造泥怪** 与 **泥怪瓮** 两个子标题。
    """
    content = merge_multiline_titles(content)
    m = re.search(r'^\*\*制造泥怪', content, re.MULTILINE)
    if not m:
        return None, -1, -1
    start = m.start()
    # 文件末尾即为结束
    return content[start:].rstrip() + '\n', start, len(content)


def remove_section(content: str, start: int, end: int) -> str:
    new_content = content[:start] + content[end:]
    new_content = re.sub(r'\n{3,}', '\n\n', new_content)
    return new_content


def append_to_file(target_path: Path, block: str, header: str = None):
    """追加条目块到目标文件，确保有 AM 标记和来源标注。"""
    if target_path.exists():
        raw = target_path.read_bytes()
        # 检测行尾风格
        has_crlf = b'\r\n' in raw
        nl = '\r\n' if has_crlf else '\n'
        content = raw.decode('utf-8')
    else:
        content = ""
        nl = '\n'
    if content and not content.endswith(nl):
        content += nl
    if header:
        content += nl + header.rstrip() + nl
    content += nl + block.rstrip() + nl
    target_path.write_bytes(content.encode('utf-8'))


def wrap_with_marker(source_file: str, title: str, source_desc: str, body: str) -> str:
    """包装条目：添加 AM 标记、标题、来源标注。"""
    if not body.strip().startswith('**'):
        # 如果 body 没有以 ** 标题开头（被切掉了），添加标题
        body = f"**{title}**\n{body}"
    # 标准化：将首行 **xxx** 后紧跟 > 来源： 标准化
    body = body.rstrip() + '\n'
    # 在第一条 **xxx** 后插入来源标注
    title_match = re.search(r'(\*\*[^*\n]+\*\*[ \t]*\n)', body)
    if title_match:
        title_line = title_match.group(1)
        rest = body[title_match.end():]
        return title_line + f"> 来源：{source_desc}\n" + rest
    return body


def add_am_marker(content: str, source_file: str) -> str:
    """在条目开头插入 AM marker。"""
    return f"<!-- {AM}-source:{source_file} -->\n" + content


# ============ 主流程 ============
def migrate_专长():
    """
    专长7.md:
    - 通用 4 条 + 2 条 → 反派法典VC_专长.md
      毒性时间、精通毒性时间、毒素专攻、精妙施毒者、瞬间炼金、娴熟炼金
    - 源书特有 1 条（创造泥怪 + 泥怪瓮）→ AM_专长.md
    """
    src = SOURCE / "专长7.md"
    content = src.read_text(encoding='utf-8')
    source_desc = "炼金术手册（Alchemy Manual）AM，未整理 → 炼金术手册AM → 专长"

    # 1. 提取 4 个毒药专长
    general_feats = [
        "毒性时间",
        "精通毒性时间",
        "毒素专攻",
        "精妙施毒者",
    ]
    target = BASE / "专长/反派法典VC_专长.md"
    moved = []
    for title in general_feats:
        body, start, end = find_section_span(content, title)
        if body:
            wrapped = wrap_with_marker("专长7.md", title, source_desc, body)
            wrapped = add_am_marker(wrapped, f"专长7.md:{title}")
            append_to_file(target, wrapped)
            content = remove_section(content, start, end)
            moved.append(title)

    # 2. 提取 2 个自发炼金专长（也含在 自发炼金术.md 中，但按 §4.0 应归到 通用专长）
    # 实际位置在 自发炼金术.md，不在 专长7.md，所以这里不处理

    # 3. 提取 创造泥怪 + 泥怪瓮
    ooze_body, ooze_start, ooze_end = find_ooze_section(content)
    if ooze_body:
        # 重新格式化为 AM 专长聚合
        am_feat_path = BASE / "专长/炼金术手册AM_专长.md"
        # 分拆为 创造泥怪 专长 和 泥怪瓮 物品条目
        # 创造泥怪专长
        craft_m = re.search(r'\*\*创造泥怪[^\n]*\n', ooze_body)
        if craft_m:
            craft_start = craft_m.start()
            # 下一个 **xxx** 标题
            next_titles = list(re.finditer(r'^\*\*[^*\n]+\*\*[ \t]*$', ooze_body[craft_m.end():], re.MULTILINE))
            craft_end = craft_m.end() + next_titles[0].start() if next_titles else len(ooze_body)
            craft_body = ooze_body[craft_start:craft_end].rstrip() + '\n'
            craft_wrapped = wrap_with_marker("专长7.md", "创造泥怪", source_desc, craft_body)
            craft_wrapped = add_am_marker(craft_wrapped, "专长7.md:创造泥怪")
            append_to_file(am_feat_path, craft_wrapped, header="# 炼金术手册AM 专长")
        # 泥怪瓮物品
        vat_m = re.search(r'\*\*泥怪瓮[^\n]*\n', ooze_body)
        if vat_m:
            vat_start = vat_m.start()
            vat_body = ooze_body[vat_start:].rstrip() + '\n'
            vat_wrapped = wrap_with_marker("专长7.md", "泥怪瓮", source_desc, vat_body)
            vat_wrapped = add_am_marker(vat_wrapped, "专长7.md:泥怪瓮")
            # 泥怪瓮是物品，归入 AM_物品.md
            am_item_path = BASE / "装备_魔法物品/魔法物品/炼金术手册AM_物品.md"
            append_to_file(am_item_path, vat_wrapped, header="# 炼金术手册AM 物品")
        content = remove_section(content, ooze_start, ooze_end)
        moved.append("创造泥怪+泥怪瓮")

    # 删除源文件
    remaining = content.strip()
    if len(remaining) < 30:
        src.unlink()
        print(f"  删除: 专长7.md")
    else:
        src.write_text(content, encoding='utf-8')
        print(f"  保留: 专长7.md (有未迁移内容 {len(remaining)} 字符)")

    print(f"专长7.md → 反派法典VC_专长.md ({len(general_feats)} 条) + AM_专长.md/AM_物品.md (源书特有)")
    return moved


def migrate_强化人造人():
    """强化人造人.md: 6 个改装 → AM_强化人造人.md"""
    src = SOURCE / "强化人造人.md"
    if not src.exists():
        return
    content = src.read_text(encoding='utf-8')
    source_desc = "炼金术手册（Alchemy Manual）AM，未整理 → 炼金术手册AM → 强化人造人"
    target = BASE / "装备_魔法物品/魔法物品/炼金术手册AM_强化人造人.md"
    wrapped = wrap_with_marker("强化人造人.md", "强化人造人", source_desc, content)
    wrapped = add_am_marker(wrapped, "强化人造人.md")
    append_to_file(target, wrapped, header="# 炼金术手册AM 强化人造人")
    src.unlink()
    print(f"强化人造人.md → AM_强化人造人.md")


def migrate_神话炼金():
    """神话炼金.md: 2 道途 + 6 神话物品 → AM_神话炼金.md"""
    src = SOURCE / "神话炼金.md"
    if not src.exists():
        return
    content = src.read_text(encoding='utf-8')
    source_desc = "炼金术手册（Alchemy Manual）AM，未整理 → 炼金术手册AM → 神话炼金"
    target = BASE / "职业/核心职业/炼金术手册AM_神话炼金.md"
    wrapped = wrap_with_marker("神话炼金.md", "神话炼金", source_desc, content)
    wrapped = add_am_marker(wrapped, "神话炼金.md")
    append_to_file(target, wrapped, header="# 炼金术手册AM 神话炼金")
    src.unlink()
    print(f"神话炼金.md → AM_神话炼金.md")


def migrate_自发炼金术():
    """
    自发炼金术.md:
    - 流程/工具/事故表 → AM_自发炼金术.md（源书特有系统）
    - 2 条专长（瞬间炼金、娴熟炼金）→ 反派法典VC_专长.md（通用）
    标题无 ** 包裹，使用文本搜索定位。
    """
    src = SOURCE / "自发炼金术.md"
    if not src.exists():
        return
    content = src.read_text(encoding='utf-8')
    source_desc_feat = "炼金术手册（Alchemy Manual）AM，未整理 → 炼金术手册AM → 专长"
    source_desc_sys = "炼金术手册（Alchemy Manual）AM，未整理 → 炼金术手册AM → 自发炼金术"

    target_feat = BASE / "专长/反派法典VC_专长.md"

    # 1. 提取 2 条专长（用文本搜索定位）
    # "瞬间炼金" 起始于 "瞬间炼金（Instant" 行，到 "娴熟炼金" 行之前
    # "娴熟炼金" 起始于 "娴熟炼金（Sure-handed" 行，到 "事故" 行之前
    feats_extracted = []

    # 提取瞬间炼金
    m1 = re.search(r'^\s*瞬间炼金（Instant\s*\n\s*Alchemy）', content, re.MULTILINE)
    if m1:
        # 找到下一节起始：娴熟炼金 或 事故
        next_m = re.search(r'^\s*(?:娴熟炼金|事故\s)', content[m1.end():], re.MULTILINE)
        if next_m:
            body = content[m1.start():m1.end() + next_m.start()]
            title_display = f"**{m1.group(0).strip().split('（')[0]}（{m1.group(0).strip().split('（')[1].replace('）', '').strip()}）**"
            # 重组为标准格式
            title_en = m1.group(0).replace('（', '').replace('）', '').replace('\n', ' ').split(' ')[1]
            title_zh = "瞬间炼金"
            block = f"{title_display}\n{body[m1.end() - m1.start():].rstrip()}\n"
            wrapped = wrap_with_marker("自发炼金术.md", title_zh, source_desc_feat, block)
            wrapped = add_am_marker(wrapped, "自发炼金术.md:瞬间炼金")
            append_to_file(target_feat, wrapped)
            content = content[:m1.start()] + content[m1.end() + next_m.start():]
            feats_extracted.append("瞬间炼金")

    # 提取娴熟炼金
    m2 = re.search(r'^\s*娴熟炼金（Sure-handed\s*\n\s*Alchemy）', content, re.MULTILINE)
    if m2:
        next_m = re.search(r'^\s*事故\s', content[m2.end():], re.MULTILINE)
        if next_m:
            body = content[m2.start():m2.end() + next_m.start()]
            title_zh = "娴熟炼金"
            title_display = "**娴熟炼金（Sure-handed Alchemy）**"
            block = f"{title_display}\n{body[m2.end() - m2.start():].rstrip()}\n"
            wrapped = wrap_with_marker("自发炼金术.md", title_zh, source_desc_feat, block)
            wrapped = add_am_marker(wrapped, "自发炼金术.md:娴熟炼金")
            append_to_file(target_feat, wrapped)
            content = content[:m2.start()] + content[m2.end() + next_m.start():]
            feats_extracted.append("娴熟炼金")

    # 清理多余空行
    content = re.sub(r'\n{3,}', '\n\n', content)

    # 2. 剩余内容（流程/工具/事故表） → AM_自发炼金术.md
    am_target = BASE / "装备_魔法物品/魔法物品/炼金术手册AM_自发炼金术.md"
    if content.strip():
        wrapped = wrap_with_marker("自发炼金术.md", "自发炼金术", source_desc_sys, content)
        wrapped = add_am_marker(wrapped, "自发炼金术.md")
        append_to_file(am_target, wrapped, header="# 炼金术手册AM 自发炼金术")
    src.unlink()
    print(f"自发炼金术.md → VC_专长.md ({len(feats_extracted)} 条: {feats_extracted}) + AM_自发炼金术.md (流程/工具/事故表)")


def migrate_野蛮人变体():
    """
    变体/野蛮人2.md: 狂暴饮者 → 职业/核心职业/野蛮人/page_35.md
    """
    src = SOURCE / "变体/野蛮人2.md"
    if not src.exists():
        return
    content = src.read_text(encoding='utf-8')
    source_desc = "炼金术手册（Alchemy Manual）AM，未整理 → 炼金术手册AM → 变体/职业选项 → 野蛮人"
    target = BASE / "职业/核心职业/野蛮人/page_35.md"
    # 标题改为"狂暴饮者"
    wrapped = wrap_with_marker("野蛮人2.md", "狂暴饮者 Drunken Rager（野蛮人变体）", source_desc, content)
    wrapped = add_am_marker(wrapped, "野蛮人2.md")
    append_to_file(target, wrapped)
    src.unlink()
    print(f"变体/野蛮人2.md → 职业/核心职业/野蛮人/page_35.md (狂暴饮者)")


def migrate_魔法物品():
    """
    物品/魔法物品1.md: 4 个无位置奇物 → 装备_魔法物品/魔法物品/奇物/无位置/page_568.md
    """
    src = SOURCE / "物品/魔法物品1.md"
    if not src.exists():
        return
    content = src.read_text(encoding='utf-8')
    source_desc = "炼金术手册（Alchemy Manual）AM，未整理 → 炼金术手册AM → 物品/魔法物品"
    target = BASE / "装备_魔法物品/魔法物品/奇物/无位置/page_568.md"
    items = ["浓缩烧瓶", "精控蒸馏器", "有翼瓶", "药性催化之瓶"]
    moved = []
    for title in items:
        body, start, end = find_section_span(content, title)
        if body:
            wrapped = wrap_with_marker("魔法物品1.md", title, source_desc, body)
            wrapped = add_am_marker(wrapped, f"魔法物品1.md:{title}")
            append_to_file(target, wrapped)
            content = remove_section(content, start, end)
            moved.append(title)
    if not content.strip() or len(content.strip()) < 30:
        src.unlink()
        print(f"  删除: 魔法物品1.md")
    else:
        src.write_text(content, encoding='utf-8')
    print(f"魔法物品1.md → 通用奇物 page_568.md: {moved}")


def migrate_毒药():
    """
    物品/毒药.md: 12 个毒药/毒品 → AM_毒药.md
    （全部为源书特有：兽人、匕痕施毒者、德洛、卡塔佩什文化）
    """
    src = SOURCE / "物品/毒药.md"
    if not src.exists():
        return
    content = src.read_text(encoding='utf-8')
    source_desc = "炼金术手册（Alchemy Manual）AM，未整理 → 炼金术手册AM → 物品/毒药"
    target = BASE / "装备_魔法物品/魔法物品/炼金术手册AM_毒药.md"
    wrapped = wrap_with_marker("毒药.md", "毒药与毒品", source_desc, content)
    wrapped = add_am_marker(wrapped, "毒药.md")
    append_to_file(target, wrapped, header="# 炼金术手册AM 毒药与毒品")
    src.unlink()
    print(f"物品/毒药.md → AM_毒药.md (12 条)")


def migrate_装备():
    """
    物品/装备.md: 痛苦之轮/毒射枪（兽人）+ 水烟管系列（卡塔佩什）→ AM_装备.md
    """
    src = SOURCE / "物品/装备.md"
    if not src.exists():
        return
    content = src.read_text(encoding='utf-8')
    source_desc = "炼金术手册（Alchemy Manual）AM，未整理 → 炼金术手册AM → 物品/装备"
    target = BASE / "装备_魔法物品/魔法物品/炼金术手册AM_装备.md"
    wrapped = wrap_with_marker("装备.md", "装备", source_desc, content)
    wrapped = add_am_marker(wrapped, "装备.md")
    append_to_file(target, wrapped, header="# 炼金术手册AM 装备")
    src.unlink()
    print(f"物品/装备.md → AM_装备.md (5 条)")


def migrate_真菌移植物():
    """
    物品/真菌移植物.md: 2 个真菌移植物 → AM_真菌移植物.md
    （源书特有：碧幻菌机制）
    """
    src = SOURCE / "物品/真菌移植物.md"
    if not src.exists():
        return
    content = src.read_text(encoding='utf-8')
    source_desc = "炼金术手册（Alchemy Manual）AM，未整理 → 炼金术手册AM → 物品/真菌移植物"
    target = BASE / "装备_魔法物品/魔法物品/炼金术手册AM_真菌移植物.md"
    wrapped = wrap_with_marker("真菌移植物.md", "真菌移植物", source_desc, content)
    wrapped = add_am_marker(wrapped, "真菌移植物.md")
    append_to_file(target, wrapped, header="# 炼金术手册AM 真菌移植物")
    src.unlink()
    print(f"物品/真菌移植物.md → AM_真菌移植物.md (2 条)")


def migrate_炼金物品():
    """
    物品/page_1559.md: 大量文化相关炼金物品 → AM_物品.md
    - 贝尔克泽恩物品（兽人）
    - 匕痕施毒者物品（工会）
    - 德洛人物品（德洛）
    - 矮人魔啤 + 酿酒工具
    - 人造人物品（按 AM 规则，保留源书特有文件）
    - 卡塔佩什物品
    - 伊诺皮恩物品（泥怪）
    - 本草配方
    - 清新迷雾、活络灸针
    - 烟花规则 + 进阶工艺 + 5 个烟花

    全部为源书特有：每条都关联特定文化
    """
    src = SOURCE / "物品/page_1559.md"
    if not src.exists():
        return
    content = src.read_text(encoding='utf-8')
    source_desc = "炼金术手册（Alchemy Manual）AM，未整理 → 炼金术手册AM → 物品"
    target = BASE / "装备_魔法物品/魔法物品/炼金术手册AM_物品.md"
    wrapped = wrap_with_marker("page_1559.md", "炼金物品", source_desc, content)
    wrapped = add_am_marker(wrapped, "page_1559.md")
    append_to_file(target, wrapped)
    src.unlink()
    print(f"物品/page_1559.md → AM_物品.md (大量文化相关炼金物品)")


if __name__ == "__main__":
    print("=" * 60)
    print("炼金术手册AM 整理")
    print("=" * 60)

    print("\n--- 专长 ---")
    migrate_专长()

    print("\n--- 强化人造人 ---")
    migrate_强化人造人()

    print("\n--- 神话炼金 ---")
    migrate_神话炼金()

    print("\n--- 自发炼金术 ---")
    migrate_自发炼金术()

    print("\n--- 野蛮人变体 ---")
    migrate_野蛮人变体()

    print("\n--- 魔法物品 ---")
    migrate_魔法物品()

    print("\n--- 毒药与毒品 ---")
    migrate_毒药()

    print("\n--- 装备 ---")
    migrate_装备()

    print("\n--- 真菌移植物 ---")
    migrate_真菌移植物()

    print("\n--- 炼金物品 ---")
    migrate_炼金物品()
