# -*- coding: utf-8 -*-
"""背景特性17 篷车星系表格冗余修复（任务 #144，审计 P1）

背景：源数据同一内容双份并存——L12-35 表格形态（13 星座 + 会切点，d% 表）
与 L41+ 标准条目形态（13 星座，**【PFS】** 标记）都被切分器切出，
13 星座 chunk 重复（背景特性17 got 50 vs est 35，超产能 15，est 未计表格）。
另有 L8-9 篷车星系裸标题（标题后无正文 → 空 text chunk）。

修复（内容锚定，行号仅参考）：
1. 删除 L8-9 篷车星系裸标题（`**篷车星系（Cosmic` + `Caravan）**`）
2. 删除 L12-35 星座表格块（表头/分隔/13 星座/会切点整块）
3. 追行者座条目正文后补会切点标准条目形态（**【PFS】会切点（Sign）** +
   需求 + 正文；正文取自表格行；13 星座全带 PFS 标记 → 会切点同组参照）

结果预期：背景特性17 got 50→36（est 35 + intro 1，est↔got 全对齐），
全库 1171→1157，空 text 2→1（仅剩切利亚斯支持者，KN144）。
幂等：锚定行缺失时 SKIP，不重复执行。
"""
from pathlib import Path

PATH = Path("pf_rules_md_organized/背景特性/背景特性17.md")

# 会切点标准条目（正文取自表格行）
CUTPOINT_ENTRY = (
    "**【PFS】会切点（Sign）**\n"
    "**需求**：-\n"
    "你正好出生在两个连续星座的分割线上，让你可以选择采用哪个星座。"
    "重骰d%；之后选择结果星座，或是其邻近星座之一。"
)


def main() -> None:
    lines = PATH.read_text(encoding="utf-8").split("\n")
    changed = False

    # 1. 删除篷车星系裸标题两行（**篷车星系（Cosmic / Caravan）**）
    idx = next((i for i, ln in enumerate(lines) if ln.startswith("**篷车星系（Cosmic")), None)
    if idx is not None and idx + 1 < len(lines) and lines[idx + 1] == "Caravan）**":
        print(f"[OK] 删除篷车星系裸标题 L{idx+1}-L{idx+2}")
        del lines[idx:idx + 2]
        changed = True
    else:
        print("[SKIP] 篷车星系裸标题不存在或形态变化")

    # 2. 删除星座表格块（| d% | 星座（Sign）… 到 | 92-100 | 会切点… 连续块）
    start = next((i for i, ln in enumerate(lines) if ln.startswith("| d% | 星座（Sign）")), None)
    end = next((i for i, ln in enumerate(lines) if ln.startswith("| 92-100 | 会切点（Sign）")), None)
    if start is not None and end is not None and end > start:
        print(f"[OK] 删除星座表格块 L{start+1}-L{end+1}（{end - start + 1} 行）")
        del lines[start:end + 1]
        changed = True
    else:
        print("[SKIP] 星座表格块不存在或锚定异常")

    # 3. 追行者座正文后补会切点标准条目（锚定「你出生于篷车星系尾端」）
    anchor = next((i for i, ln in enumerate(lines) if ln.startswith("你出生于篷车星系尾端")), None)
    if anchor is not None and not any("【PFS】会切点" in ln for ln in lines):
        lines[anchor:anchor + 1] = [lines[anchor], CUTPOINT_ENTRY]
        print(f"[OK] L{anchor+1} 追行者座正文后补会切点条目（{len(CUTPOINT_ENTRY)} 字符）")
        changed = True
    elif anchor is None:
        print("[SKIP] 追行者座正文锚定行缺失")
    else:
        print("[SKIP] 会切点条目已存在（幂等保护）")

    if changed:
        # 纯 LF 行尾（已确认 0 CRLF），split("\n")/join 无损
        PATH.write_text("\n".join(lines), encoding="utf-8")
        print("[DONE] 写回", PATH)
    else:
        print("[DONE] 无改动，未写回")


if __name__ == "__main__":
    main()
