#!/usr/bin/env python3
"""fix_bare_title_glue.py — 裸标题补星修复（KN095，源数据）

背景：page_311（120 行）/武器大师手册_专长（15 行）/page_555（3 行）的条目标题是
HTML 表格/加粗段转换产物 `中文（类型）****EN` / `中文****EN`（**无前导星**），
normalize 链所有裸标题正则（_RE_BARE_CN_EN_*）均要求星前有英文或前导星 →
split 不识别为条目 → 全部并入前一个 elided 条目：
  - feat_page_311_0070 移情感知吞 ~115 条 → 16028 字符（chunk 总数之最）
  - feat_武器大师手册_专长_0081 种族专长吞 15 条 → 5864 字符
  - page_555 微吞并 3 条

修复（源数据，保留原行尾——organized 源数据 CRLF 约定，page_311 为混合行尾，
逐行保留原行尾，diff 只显示修改行）：
- 无括号 `中文****EN`（EN 到行尾）→ 补前导星 `**中文****EN`
  → normalize `_RE_ELIDED_CN_EN_GLUE` 命中 → `[[fc:elided]]**中文（EN）**`
- 带括号 `中文（类型）****EN`（含 2 行跨行英文，页 130/216）→ 标准形态
  `**中文（EN）〔类型〕**`（EN 去尾部 ` (Combat, Stare)` 冗余类型括号）
  → split FC-1q 识别为 standard，name_en/feat_type 完整提取

用法：python3 fix_bare_title_glue.py [--dry-run]
"""

import re
import sys

# ⚠️ pipeline 输入是子目录版（判别器矩阵 189 rel 中 page_311/page_555 的 rel 为
# 专长/xxx.md，根目录副本不在矩阵内不产出）——修复必须指向子目录版
FILES = [
    "pf_rules_md_organized/专长/page_311.md",
    "pf_rules_md_organized/专长/武器大师手册_专长.md",
    "pf_rules_md_organized/专长/page_555.md",
]

# 无括号裸标题：中文****EN（EN 到行尾，允许弯引号 ’——唤魂师之祈 Spiritualist’s Call）
RE_NO_PAREN = re.compile(r"^([一-鿿/]{2,})\*{4}\s*([A-Za-z][A-Za-z0-9 .'’\-]*)$")
# 带括号裸标题：中文（类型）****EN（EN 到行尾，可含尾部 (Combat, Stare) 冗余类型）
RE_WITH_PAREN = re.compile(r"^([一-鿿/]{2,})（([^）]{1,30})）\*{4}\s*(.+)$")
# EN 尾部冗余类型括号（英文类型与中文类型重复）：(Combat, Stare)/(Metamagic)/…
RE_EN_TAIL = re.compile(r"\s*\([A-Za-z][A-Za-z ,']*\)\s*$")


def fix_en(en: str) -> str:
    """EN 清洗：去尾部冗余类型括号（跨行截断英文已由上游合并）"""
    return RE_EN_TAIL.sub("", en).strip()


def process_file(path: str, dry: bool) -> tuple[int, list[str]]:
    data = open(path, "rb").read()
    text = data.decode("utf-8")
    # 拆行并保留原行尾（混合行尾文件逐行保留）
    parts = re.split(r"(\r?\n)", text)
    lines = []
    for i in range(0, len(parts) - 1, 2):
        lines.append([parts[i], parts[i + 1]])
    if parts[-1]:
        lines.append([parts[-1], ""])

    n_fixed = 0
    changes: list[str] = []
    out: list[str] = []  # (line, sep)
    i = 0
    while i < len(lines):
        line, sep = lines[i]
        m = RE_WITH_PAREN.match(line)
        if m:
            cn, ctype, en_part = m.group(1), m.group(2), m.group(3)
            if re.search(r"\s$", en_part) or re.match(r"^[A-Za-z]", lines[i + 1][0] if i + 1 < len(lines) else ""):
                # 跨行英文：合并下一行（行尾取当前行 sep）
                en_full = en_part + lines[i + 1][0].strip()
                new_line = f"**{cn}（{fix_en(en_full)}）〔{ctype}〕**"
                out.append([new_line, sep])
                n_fixed += 1
                changes.append(f"  {line!r}\n    + {lines[i+1][0]!r}\n    → {new_line!r}")
                i += 2
            else:
                new_line = f"**{cn}（{fix_en(en_part)}）〔{ctype}〕**"
                out.append([new_line, sep])
                n_fixed += 1
                changes.append(f"  {line!r}\n    → {new_line!r}")
                i += 1
            continue
        m2 = RE_NO_PAREN.match(line)
        if m2:
            cn, en = m2.group(1), m2.group(2)
            new_line = f"**{cn}****{en}"
            out.append([new_line, sep])
            n_fixed += 1
            changes.append(f"  {line!r}\n    → {new_line!r}")
            i += 1
            continue
        out.append([line, sep])
        i += 1

    if not dry:
        new_text = "".join(l + s for l, s in out)
        if new_text != text:
            open(path, "wb").write(new_text.encode("utf-8"))
    return n_fixed, changes


def main() -> int:
    dry = "--dry-run" in sys.argv
    total = 0
    for p in FILES:
        n, changes = process_file(p, dry)
        total += n
        print(f"{'[DRY] ' if dry else ''}{p}: 修复 {n} 行")
        for c in changes[:8]:
            print(c)
        if len(changes) > 8:
            print(f"  …共 {len(changes)} 行改动")
        print()
    print(f"{'DRY-RUN 合计' if dry else '已修复合计'}: {total} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
