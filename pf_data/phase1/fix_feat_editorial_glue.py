#!/usr/bin/env python3
"""fix_feat_editorial_glue.py — 编注同行接条目标题拆行修复（专长/page_199.md）

根因（KN076）：源数据整理时把「标点后接条目标题」同行形态统一拆为独立行，
但 3 处条目标题前是【编注…】（非标点）漏拆 → 标题同行留在上一条目效果值后，
split_into_items 只认行首标题 → 下一条目（化敌为盾/雷魂/月夜伏击者）完整正文
被上一条目吞掉，且上一条目 benefit 字段吞入标题+斜体描述。

修复：`【编注…】\n**标题（EN）〔类型〕**` 拆行（与同批豭突千裂/豭突势等
标点拆行同口径）。字节级替换保留行尾（LF/CRLF 混合文件逐字节不动），
diff 仅 3 行。
"""

import re
from pathlib import Path

TARGET = Path("pf_rules_md_organized/专长/page_199.md")

# 3 处编注 → 标题拆行（精确匹配编注全文，防误伤）
SPLITS = [
    ("【编注：根据FAQ，此条已修正】**化敌为盾（", "【编注：根据FAQ，此条已修正】\n**化敌为盾（"),
    ("【编注：雷灵流派专长大概不是一个作者写的吧。】**雷魂（", "【编注：雷灵流派专长大概不是一个作者写的吧。】\n**雷魂（"),
    ("【编注：此处胡说。核心手册说明了从俯卧中站立是一个会引发借机攻击的移动动作。】**月夜伏击者（",
     "【编注：此处胡说。核心手册说明了从俯卧中站立是一个会引发借机攻击的移动动作。】\n**月夜伏击者（"),
]


def main() -> int:
    data = TARGET.read_bytes()
    total = 0
    for old, new in SPLITS:
        ob, nb = old.encode("utf-8"), new.encode("utf-8")
        n = data.count(ob)
        if n == 0:
            raise SystemExit(f"未命中: {old[:30]}…（文件内容与预期不符，中止）")
        data = data.replace(ob, nb)
        total += n
    TARGET.write_bytes(data)
    print(f"完成：{TARGET} 拆行 {total} 处")
    return total


if __name__ == "__main__":
    main()
