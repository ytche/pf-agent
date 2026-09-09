#!/usr/bin/env python3
"""page_947 表 6-3 详述区粘连修复脚本（M4，2026-08-09）。

背景：
  page_947.md（CRB 表 6-3 魔法物品随机表）详述区 60 条条目中 16 条
  「清单项」与「标题」粘连成一行（如 `正常物品：+2短弓吞噬袋Bag of
  devouring灵光：…`），切分器把清单项中文并入标题（`短弓吞噬袋`）；
  另有 7 条详述区标题与表格权威名存在翻译异体（详述区 `吞噬袋` vs
  表格 `毁灭袋`），表格 51 项行级对账时 22 项无法锚定。

修复方式（改源数据，不动解析器——攻坚决议）：
  规则 1（拆行）：17 处「清单项尾↔标题头」间插入 `\r\n`（与源数据
    CRLF 行尾一致），join 逻辑因前一行为段尾不再合并，标题独立成行，
    清单项前缀（`正常物品：+2短弓`）自然落 intro。
  规则 2（异体改名）：7 处详述区标题改为表格权威名（吞噬袋→毁灭袋、
    喷嚏粉→喷嚏尘、阵营逆转头盔→逆转阵营头盔、阻魔权杖→阻法权杖、
    恶运塑像→恶运雕像、背德手枪→背手枪、衰老药膏→老化药膏），
    其中吞噬袋/阵营逆转头盔正文有同名提及，锚定「标题+英文名」只改标题处。

规则：
  - 顺序：先拆行后改名——改名若先执行会破坏拆行锚（`短弓吞噬袋` 内含 `吞噬袋`）
  - 内容锚定幂等：拆行锚 = 清单项尾+标题头纯中文串，改名锚 = 标题+英文名前缀
  - 规则 3 译者吐槽删除（KN091 同族）：CHM 详述区标题内嵌译者吐槽
    `（明斯克你感觉如何啊？）`/`（艾德温你感觉如何啊…哎，不对）`——括号
    段卡 INLINE_HEAD 组2 前瞻（字符类不含全角括号）致整行沉 intro；
    删除后链头回溯 + INLINE_HEAD 自动修复（狂暴巨剑/性别转换腰带）
  - newline="" 保留 CRLF 行尾（源数据为 CRLF，禁止规范化——否则
    git diff 整文件污染，审计留痕不可读）

用法：
  python3 fix_equip_947_glue.py [--dry-run]
"""
import sys
from pathlib import Path

TARGET = (Path(__file__).parent / "pf_rules_md_organized" / "装备_魔法物品"
          / "魔法物品" / "page_947.md")

# 拆行对：(清单项尾, 标题头)——中间插 \r\n
SPLITS = [
    ("+2短弓", "吞噬袋"),
    ("飞天扫帚", "笨拙剑"),
    ("诡骗斗篷", "暴食戒指"),
    ("维生戒指", "献祭披风"),
    ("任意魔法披风", "盲目王冠"),
    ("任意魔法腰带", "墓魂护甲"),
    ("控亡厚革甲", "憎恨帽"),
    ("+2战锤", "阵营逆转头盔"),
    ("投网", "单向窗"),
    ("愈伤护身符", "石化斗篷"),
    ("任意披风", "破界盾"),
    ("或法术偏转戒指", "实话戒指"),
    ("杂货法袍", "引火烧身权杖"),
    ("灭火权杖", "阻魔权杖"),
    ("不老药膏", "恶运塑像"),
    ("大砍刀", "空虚魔典"),
    ("疾速战鼓", "喷嚏粉"),
]

# 改名对：(标题原文, 表格权威名)——吞噬袋/阵营逆转头盔带英文名前缀
# 只锚标题处（正文 3 处「吞噬袋」+1 处「阵营逆转头盔」提及不带英文名）；
# 石化斗篷/衰弱长袍/笨拙护手为第二批异体（2026-08-09 表格对账补发现，
# `笨拙剑`/`笨拙大砍刀` 是不同物品，锚英文名区分）
RENAMES = [
    ("吞噬袋Bag", "毁灭袋Bag"),
    ("喷嚏粉", "喷嚏尘"),
    ("阵营逆转头盔Helm", "逆转阵营头盔Helm"),
    ("阻魔权杖", "阻法权杖"),
    ("恶运塑像", "恶运雕像"),
    ("背德手枪", "背手枪"),
    ("衰老药膏", "老化药膏"),
    ("石化斗篷Petrifying", "石化披风Petrifying"),
    ("衰弱长袍Robe", "衰弱法袍Robe"),
    ("笨拙护手Gauntlets", "笨拙铁手套Gauntlets"),
]

# 译者吐槽删除（规则 3）：标题段内嵌括号吐槽整段删除（保留行尾结构）
REMOVALS = [
    "（明斯克你感觉如何啊？）",
    "（艾德温你感觉如何啊…哎，不对）",
]


def fix_text(text: str) -> tuple[str, int, int, int]:
    n_split = n_rename = n_removal = 0
    for a, b in SPLITS:
        s = a + b
        if s in text:
            text = text.replace(s, a + "\r\n" + b, 1)
            n_split += 1
    for old, new in RENAMES:
        if old in text:
            text = text.replace(old, new, 1)
            n_rename += 1
    for rem in REMOVALS:
        if rem in text:
            text = text.replace(rem, "", 1)
            n_removal += 1
    return text, n_split, n_rename, n_removal


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    text = TARGET.open(encoding="utf-8", newline="").read()
    new, n_split, n_rename, n_removal = fix_text(text)
    print(f"[{'DRY-RUN' if dry_run else 'FIXED'}] {TARGET.name}："
          f"拆行 {n_split}/17 + 改名 {n_rename}/10 + 吐槽删除 {n_removal}/2")
    # 幂等断言：已修复处重复运行应 0 命中
    if not dry_run and (n_split or n_rename or n_removal):
        TARGET.open("w", encoding="utf-8", newline="").write(new)
    miss_s = [a + b for a, b in SPLITS if a + b not in text]
    miss_r = [old for old, _ in RENAMES if old not in text]
    miss_v = [rem for rem in REMOVALS if rem not in text]
    if miss_s or miss_r or miss_v:
        print(f"  ⚠️ 未命中：拆行 {miss_s} / 改名 {miss_r} / 吐槽 {miss_v}")


if __name__ == "__main__":
    main()
