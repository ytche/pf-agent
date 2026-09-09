#!/usr/bin/env python3
"""KN158 源数据规范化：游泳标题关键属性分隔符对齐（2026-08-07）

缺陷：`**游泳 (Swim) (力量，防具检定减值)**` 用全角逗号分隔，而其余
8 个【减】技能标题统一用分号（`**攀爬 (Climb) (力量; 防具检定减值)**`）。
formats/skill.py::_parse_title_suffix 按 `split(";")` 拆分 → 游泳
key_ability=「力量，防具检定减值」且 armor_penalty=False（CHM 权威应为
力量 + 【减】）。

修复：`，` → `; ` 对齐既有形态（改源数据不改解析器，KN139/147/149 先例）。
内容锚定幂等：仅命中精确标题行，重复执行 0 处；CRLF 行尾保留（CRLF 约定）。

用法：python3 fix_skill_kn158.py [--apply]
默认 dry-run 打印命中；--apply 落盘。
"""
from pathlib import Path
import sys

ORGANIZED = Path(__file__).resolve().parent / "pf_rules_md_organized"
TARGET = ORGANIZED / "技能/技能详述/力量决定/page_192.md"
OLD = "**游泳 (Swim) (力量，防具检定减值)**".encode("utf-8")
NEW = "**游泳 (Swim) (力量; 防具检定减值)**".encode("utf-8")


def main() -> int:
    data = TARGET.read_bytes()
    if b"\r\n" not in data:
        print(f"⚠️  {TARGET} 非 CRLF 行尾——约定违反，终止")
        return 2
    hits = data.count(OLD)
    print(f"命中 {hits} 处（{TARGET.name}，期望 1）")
    if hits == 0:
        print("无命中——已修复或形态变化，终止（幂等）")
        return 0
    if hits != 1:
        print("命中 != 1，终止（防误改）")
        return 2
    if "--apply" not in sys.argv:
        print("dry-run：仅报告，加 --apply 落盘")
        return 0
    TARGET.write_bytes(data.replace(OLD, NEW))
    after = TARGET.read_bytes()
    print(f"已落盘：命中 {after.count(OLD)}，新形态 {after.count(NEW)} 处")
    return 0


if __name__ == "__main__":
    sys.exit(main())
