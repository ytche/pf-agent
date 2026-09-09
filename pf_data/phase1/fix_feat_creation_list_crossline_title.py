#!/usr/bin/env python3
"""fix_feat_creation_list_crossline_title.py — 造物专长一览跨行标题合并（KN030 ③ 前置，2026-08-02）

根因：HTML（造物专长一览.htm）正文条目标题为 `<STRONG>` 独立段，源码内软换行
渲染为单行（'Brew \nFleshcrafting' 同一 STRONG 段）；转换器转 md 时把软换行带成
行内换行 + 行尾闭合星丢失 → 跨行标题（行尾无 `**`）→ split 条目边界识别失败 →
条目粘入前一 chunk（抵异作成 chunk 内粘调制塑肉毒素全文、制造强化火器 chunk 内
粘恶魔移植物/塑肉者/骇人饰物 3 条目）→ metadata.source 错配/为空。

HTML 回溯确认：标题 + 出处行为同一 `<STRONG>` 段内完整单行内容。

修复：13 处跨行合并为单行（对齐 HTML 渲染），标题行补闭合星。
字节级保留行尾（LF 文件，逐字节不动其余内容），锚点唯一性校验。

修复后：条目独立切分 → source 正确落到各自条目 → 配合 parse_fields source
行尾锚定（processors/feat.py）与顶层提升（apply_feat_creation_source_promote.py）。
"""

from pathlib import Path

TARGET = Path("pf_rules_md_organized/专长/造物专长一览.md")

# 13 处跨行：锚点（old）→ 合并后（new）。标题行补闭合星，出处行不补。
MERGES = [
    # --- 跨行标题（补闭合星）---
    ("**【3.5R】调制塑肉毒素（造物专长）（Brew \n"
     "Fleshcrafting Poison，Item Creation）",
     "**【3.5R】调制塑肉毒素（造物专长）（Brew Fleshcrafting Poison，Item Creation）**"),
    ("**创造泥怪（CRAFT \nOOZE）（造物专长）**",
     "**创造泥怪（CRAFT OOZE）（造物专长）**"),
    ("**泥怪瓮（Oozing \nVat）**",
     "**泥怪瓮（Oozing Vat）**"),
    ("**制造人偶（造物专长）（Craft Poppet，Item \nCreation）",
     "**制造人偶（造物专长）（Craft Poppet，Item Creation）**"),
    ("**制造影钉（Craft Shadow \nPiercing）［造物］**",
     "**制造影钉（Craft Shadow Piercing）［造物］**"),
    ("**奇植培育（造物专长）（Cultivate Magic \nPlants，Item Creation）",
     "**奇植培育（造物专长）（Cultivate Magic Plants，Item Creation）**"),
    ("**恶魔移植物（造物专长）（Demon Grafter，Item \nCreation）",
     "**恶魔移植物（造物专长）（Demon Grafter，Item Creation）**"),
    ("**塑肉者（造物专长）（Fleshwarper，Item \nCreation）",
     "**塑肉者（造物专长）（Fleshwarper，Item Creation）**"),
    ("**种植植物生物（造物专长）（Grow Plant \nCreature，Item Creation）",
     "**种植植物生物（造物专长）（Grow Plant Creature，Item Creation）**"),
    ("**作祟拾荒者（造物专长）（Haunt \nScavenger，Item Creation）",
     "**作祟拾荒者（造物专长）（Haunt Scavenger，Item Creation）**"),
    ("**灌法毒药（物品制造）（Infuse Poison (Item \nCreation)）",
     "**灌法毒药（物品制造）（Infuse Poison (Item Creation)）**"),
    # --- 跨行出处行（值跨行，不补星）---
    ("****出自**：Pathfinder \n#5: Sins of the Saviors pg. 57",
     "****出自**：Pathfinder #5: Sins of the Saviors pg. 57"),
    ("**Source Monster \nHunter's Handbook pg. 24",
     "**Source Monster Hunter's Handbook pg. 24"),
    # --- 第二轮：绘制魔法刺青条目子物品标题跨行（HTML `<B>…<BR></B>`，
    # 转换器把闭合星输出到下一行 → 标题行无星、跨行；修复为单行 + 补星）---
    ("施法者刺青（Caster’s \n"
     "Tattoo）",
     "**施法者刺青（Caster’s Tattoo）**"),
    ("贮法刺青（Reservoir \n"
     "Tattoo）",
     "**贮法刺青（Reservoir Tattoo）**"),
    ("法术刺青（Spell \n"
     "Tattoo）",
     "**法术刺青（Spell Tattoo）**"),
    # --- 第二轮：铭刻符文正文标题缺闭合星（HTML `<STRONG>…<BR></STRONG>`，
    # 转换器把 `</STRONG>` 的闭合星输出到下一行 → 标题缺星、出处行变 4 星）---
    ("**【3.5R】铭刻符文（造物专长）（Inscribe Rune，Item Creation）\n"
     "****出自**",
     "**【3.5R】铭刻符文（造物专长）（Inscribe Rune，Item Creation）**\n"
     "****出自**"),
]


def main():
    data = TARGET.read_text(encoding="utf-8")
    if "\r\n" in data:
        print("⚠️ 文件含 CRLF（预期 LF），终止以防行尾污染")
        return 1

    skipped, applied = [], []
    for old, new in MERGES:
        cnt = data.count(old)
        if cnt == 0:
            skipped.append(old[:30])  # 已合并过（幂等重跑）
        elif cnt == 1:
            data = data.replace(old, new)
            applied.append(old[:30])
        else:
            print(f"❌ 锚点唯一性校验失败（出现 {cnt} 次）: {old[:40]!r}")
            return 1

    TARGET.write_text(data, encoding="utf-8")
    print(f"✅ 合并 {len(applied)} 处（本轮新增），跳过 {len(skipped)} 处已合并（幂等）: {TARGET}")
    for s in applied:
        print(f"  ✓ {s}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
