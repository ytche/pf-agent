"""
fix_feat_page9.py — 专长9 表格行 8 专长同行粘连拆分（P0 级，est=11 got=3 丢 8）

背景（2026-08-02 审计发现，P0 级）：专长9 含 11 个真实专长——表格区 8 个
（《第六翼学院》来源）+ 详情区 3 个图纹专长（受控图纹/图纹讯息/移动图纹，已
正常产出）。表格区 8 个专长全部同行粘连在一个表格行（L4）内：
`中文EN（类型）正文先决条件：值专长效果：值` 标题/正文/字段无换行（RE2
表格行内换行残留为裸 `\r`），pipeline 无标题行可识别，8 个专长 100% 丢失。

L4 物理行含 17 个裸 `\r`（非 CRLF），切 18 段，每 2 段一组 = 一个专长：
  seg0  介绍文本 + `合唱支援Choral `（标题 EN 拆词前缀，尾空格）
  seg1  `Support（团队专长）通过与盟友一起高唱…先决条件：…专长效果：…`
  seg2  `天界破敌Heavenly ` / seg3 `Bane当你的武器…`（无类型括号）
  …（8 组）
字段形态：正文与 `先决条件：`/`专长效果：` 同行粘连；**传递恩惠无「先决
条件：」字段**（仅专长效果）；流光闪正文含跨行括号 `（When \r you make
…a thrown \r weapon）`；流光耀/流光闪/流光式正文含 `编注：亦作…` 中缀。

修复（改源数据不改脚本，对齐 KN043 异能选集PA 504b66b 先例）：
  - L4 合并（`\r` + 后续前导空格 → 空）：介绍段与 8 专长连续文本
  - 去表格管道符（首 `| ` / 尾 ` |`），删 L5 表格分隔行 `| --- |`
  - 按 8 个标题锚点切块（`中文EN` 或 `中文EN（类型）`，EN 可含空格）
  - 每块拆行：`**中文（EN）（类型）**` 标题 + 正文行 + `先决条件：` 行 +
    `专长效果：` 行（partition 切标签；传递恩惠无先决条件拆 3 行）
  - 新行全裸 LF（L4 原为 LF 行）；L1-L3/L6-L33 继承行字节级原样保留
  - 断言 n==33 + L4 锚点 + L5 分隔行 + 8 锚点递增 + 块字段分布

修复后：8 专长 + 3 图纹 = 11 = est=11 精确匹配，verify 不再 WARN。

用法：python3 fix_feat_page9.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长9.md"

# 标题锚点（`中文EN` 或 `中文EN（类型）`，EN 可含空格——Choral Support）
RE_ANCHOR = re.compile(
    r"^([一-鿿]{2,8})([A-Za-z][A-Za-z'’\.\- ]*?)(?:（([一-鿿A-Za-z ，、]{1,12})）)?$"
)
# 8 个锚点按源数据顺序（L4 内 seg 对）
ANCHORS = [
    "合唱支援Choral Support（团队专长）",
    "天界破敌Heavenly Bane",
    "融身入翼Joined Wings（团队专长）",
    "流光耀Lantern Glare（战斗专长）",
    "流光闪Lantern Light（战斗专长）",
    "流光式Lantern Style（战斗专长，流派专长）",
    "传递恩惠Passing Grace（团队专长）",
    "复兴导能Reviving Channel",
]


def main() -> int:
    raw = open(PATH, "rb").read()
    lines = raw.split(b"\n")
    n = len(lines)
    assert n == 33, f"预期 33 行，实际 {n} 行——行号假设失效，中止"
    l4 = lines[3].decode("utf-8")
    assert l4.startswith("| 在第六翼学院中受训的神圣战士"), \
        f"L4 非介绍段表格行：{l4[:40]!r}"
    assert l4.rstrip().endswith(" |"), f"L4 尾非表格闭合：{l4[-20:]!r}"
    assert lines[4] == b"| --- |", f"L5 非表格分隔行：{lines[4]!r}"

    # ---- 合并 L4（裸 \r + 后续前导空格 → 空；保留跨行处原有尾空格分词）----
    merged = re.sub(r"\r\s*", "", l4).strip()
    assert merged.startswith("| 在第六翼学院中受训的神圣战士"), "合并后首异常"
    assert merged.endswith("生命值首先恢复到0。 |"), "合并后尾异常"
    # 去表格管道符（首 `| ` / 尾 ` |`）
    merged = merged[2:-2].strip()

    # ---- 8 锚点切块（顺序递增校验）----
    spans: list[tuple[int, int]] = []
    pos = 0
    for a in ANCHORS:
        i = merged.find(a, pos)
        assert i >= 0, f"锚点缺失：{a}"
        assert i >= pos, f"锚点乱序：{a}"
        spans.append((i, i + len(a)))
        pos = i + len(a)
    assert len(spans) == 8, f"锚点数 {len(spans)} ≠ 8"

    intro = merged[: spans[0][0]]
    assert intro.startswith("在第六翼学院") and "以下专长代表了这些技巧。" in intro, \
        f"介绍段异常：{intro[:60]!r}"

    out: list[bytes] = []
    report: list[str] = []

    # ---- L1-L3 原样保留 ----
    out.extend(lines[:3])

    # ---- 介绍段（独立行，裸 LF）----
    out.append(intro.encode("utf-8"))

    # ---- 8 专长块 ----
    fixed = 0
    for idx, (s, e) in enumerate(spans):
        cn = ANCHORS[idx]
        m = RE_ANCHOR.match(cn)
        assert m, f"锚点解析失败：{cn}"
        title = f"**{m.group(1)}（{m.group(2)}）" + \
                (f"（{m.group(3)}）" if m.group(3) else "") + "**"

        blk_start = e
        blk_end = spans[idx + 1][0] if idx + 1 < len(spans) else len(merged)
        block = merged[blk_start:blk_end].strip()
        assert block, f"{cn} 块内容为空"

        body, sep1, rest = block.partition("先决条件：")
        if sep1:
            pre, sep2, eff = rest.partition("专长效果：")
            assert sep2 and eff, f"{cn} 缺「专长效果：」字段"
            out.append(title.encode("utf-8"))
            out.append(body.strip().encode("utf-8"))
            out.append(f"先决条件：{pre.strip()}".encode("utf-8"))
            out.append(f"专长效果：{eff.strip()}".encode("utf-8"))
            report.append(f"#{idx+1}: {cn} 拆 4 行（先决条件+专长效果）")
        else:
            # 传递恩惠：无先决条件字段，仅拆专长效果
            body, sep2, eff = block.partition("专长效果：")
            assert sep2 and eff, f"{cn} 缺「专长效果：」字段"
            out.append(title.encode("utf-8"))
            out.append(body.strip().encode("utf-8"))
            out.append(f"专长效果：{eff.strip()}".encode("utf-8"))
            report.append(f"#{idx+1}: {cn} 拆 3 行（无先决条件，仅专长效果）")
        fixed += 1

    # ---- L6-L33 原样保留（跳过 L5 表格分隔行）----
    out.extend(lines[5:])

    out_bytes = b"\n".join(out)
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证：继承行全等 + CRLF 计数不变 ----
    # 输出 = L1-3(3) + 介绍(1) + 专长块(31=7×4+3) + L6-33(继承) → 继承行起点 35
    head_len = 3 + 1 + (7 * 4 + 3)
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n"), "CRLF 计数变化，中止"
    assert new_lines[:3] == lines[:3], "L1-L3 被改动，中止"
    assert new_lines[head_len:] == lines[5:], "L6-L33 被改动，中止"

    if out_bytes == raw:
        print("无变更")
        return 1

    with open(PATH, "wb") as f:
        f.write(out_bytes)
    print(f"== {PATH}：修复 {fixed} 处")
    for r in report:
        print("   ", r)
    print(f"CRLF: {raw.count(b'\r\n')} -> {out_bytes.count(b'\r\n')} "
          f"| 总行数: {n} -> {len(new_lines)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
