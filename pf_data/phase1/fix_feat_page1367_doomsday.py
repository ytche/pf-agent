#!/usr/bin/env python3
"""fix_feat_page1367_doomsday.py — page_1367 末日法术正文吞并修复（2026-08-02）

根因（HTML 回溯 page_1367.html）：
  1. 「详细」为原书棕色 18pt 导航标题（详述区起始标记），转换器 4 星包裹为
     `**详细****` 独立行——pipeline 无法识别为拆分边界 → 表格区最后一行
     （拟鬼之术）与详述区首条（末日法术）正文粘进同一 chunk（0081）：
     检索「拟鬼之术」会答出末日法术内容，且末日法术正文丢失独立条目。
  2. 末日法术（超魔）标题行缺开头星（`末日法术（超魔）****出自：…`，
     HTML 绿色 14pt 标题段的转换产物残缺）——不以 `**` 开头 → 标题识别失败
     → 无法独立切分。对照同页正常形态：`**纯净法术（超魔）****出自：…`。

修复（字节级，其余行尾原样保留）：
  1. 删除 `**详细****` 行（导航标记，无规则内容）
  2. 末日法术标题行开头补 `**`

结果预期：0081 拆分为拟鬼之术表格行 chunk + 末日法术正文独立 chunk，
page_1367 总 chunk 数 +1（91→92）。
"""

from pathlib import Path

TARGET = Path("pf_rules_md_organized/专长/page_1367.md")

# 「**详细****」整行（LF 行尾）——删除
OLD_DETAIL = b"**\xe8\xaf\xa6\xe7\xbb\x86****\n"  # **详细****\n
# 末日法术标题行开头缺星——补 **
OLD_DOOM = (
    "末日法术（超魔）****出自"
).encode()  # 末日法术（超魔）****出自
NEW_DOOM = b"**" + OLD_DOOM


def main():
    raw = TARGET.read_bytes()

    cnt_detail = raw.count(OLD_DETAIL)
    if cnt_detail != 1:
        print(f"❌ 「**详细****」行出现 {cnt_detail} 次（期望 1），终止")
        return 1
    cnt_doom = raw.count(OLD_DOOM)
    if cnt_doom != 1:
        print(f"❌ 末日法术标题行出现 {cnt_doom} 次（期望 1），终止")
        return 1

    raw = raw.replace(OLD_DETAIL, b"")
    raw = raw.replace(OLD_DOOM, NEW_DOOM, 1)
    TARGET.write_bytes(raw)
    print(f"✅ 删除「**详细****」行 + 末日法术标题补开头星（字节级，其余行尾未动）: {TARGET}")


if __name__ == "__main__":
    raise SystemExit(main())
