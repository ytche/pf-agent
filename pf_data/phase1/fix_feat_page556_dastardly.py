#!/usr/bin/env python3
"""fix_feat_page556_dastardly.py — page_556 流氓剑条目 4 星行 + \\r 定位符合并（2026-08-02）

根因（HTML 回溯 + 字节级验证）：
  1. `****阴招制敌****` 独立 4 星行——HTML（page_556.html）里「阴招制敌」是
     流氓剑（Dastardly Trick）条目标题前的译名行（黑色非粗体 `<B normal>` 段），
     转换器 4 星包裹 → FC-7 星族误识别为独立标题 → 空 text 伪条目 chunk
     （format_cluster=standard 全字段 missing，pipeline 重跑后新增回归）。
  2. `流氓剑 Dastardly \r\nTrick（战斗，派头专长）**`——`\r` 定位符残留
     （aa6b3ff 表格行 \\r 清洗漏网，splitlines 把 \\r 当换行腰斩标题行）→
     跨行缺闭合星 → 标题识别失败。

修复：三行合并为单条目标题（保留双译名 + 英文名 + 类型，防信息丢失）。
双名用「/」分隔（对齐「制造波普宠/制造人偶」先例，单括号形态保证
括号拆分正确：双括号会让「阴招制敌」误入 feat_type）。
字节级操作，仅动该 3 行，其余 120 CRLF + 422 LF 行尾原样保留。
"""

from pathlib import Path

TARGET = Path("pf_rules_md_organized/专长/page_556.md")

OLD = (
    "****阴招制敌****\n"
    "流氓剑 Dastardly \r\n"
    "Trick（战斗，派头专长）**"
)
NEW = "**流氓剑/阴招制敌（Dastardly Trick，战斗，派头专长）**"


def main():
    raw = TARGET.read_bytes()

    # 幂等兼容：首轮已合并的「双括号」形态 → 归一为「/」分隔单括号形态
    b_first = "**流氓剑（阴招制敌）（Dastardly Trick，战斗，派头专长）**".encode("utf-8")
    if b_first in raw:
        raw = raw.replace(b_first, NEW.encode("utf-8"), 1)
        TARGET.write_bytes(raw)
        print(f"✅ 双括号形态归一为「/」分隔（幂等）: {TARGET}")
        return 0

    b_old, b_new = OLD.encode("utf-8"), NEW.encode("utf-8")
    cnt = raw.count(b_old)
    if cnt != 1:
        print(f"❌ 锚点唯一性校验失败（出现 {cnt} 次），终止")
        return 1
    raw = raw.replace(b_old, b_new)
    TARGET.write_bytes(raw)
    print(f"✅ 合并 3 行为单条目标题（字节级，其余行尾未动）: {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
