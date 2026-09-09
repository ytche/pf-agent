"""
fix_feat_planar_adventures.py — 位面冒险PA_专长.md 6 处杂糅标题归一（P0 级，est=11 got=6 丢 5）

背景（2026-08-02 KN026 复算审计，P0 级）：位面冒险PA_专长.md（《位面冒险》专长页，
未整理 → 位面冒险PA 整理产物）转换质量差，6 个条目标题为「半角括号类型 + PFS 标签
粘连 + 出处粘连 + 断行」杂糅形态，normalize 现有覆盖（_merge_cross_line_en /
_RE_ELIDED_INLINE_DESC / _fix_quad_star_halfparen / _wrap_bare_titles）均无法处理
→ 5 条目 100% 丢失（闪现步/暗影风暴/治疗者之手/浪徒之幸/精通异界传送），
1 条目 title 残缺（相位打击「相位打击（」）。

修复（改源数据不改脚本，对齐 KN044/KN048/KN052/KN053 源数据归一先例）：
  1. L4-6  闪现步：`**…（Flickering Step (Conduit)）出自《Planar Adventures`+`pg. `+`28》**`
            （标题内嵌出处断行）→ `**闪现步（汲引）（Flickering Step (Conduit)）**`
  2. L19-20 暗影风暴：标题行补闭合 `**`；续行 `***描述*` 剥 1 星 → `*描述*`
            （跨行 elided 变体：未闭合标题 + 3 星包裹描述）
  3. L28-30 治疗者之手：`【PFS不可】 ` 前缀 + 半角括号类型 + 出处后缀断行
            → `**治疗者之手（Healer's Hands）（汲引）**【PFS不可】`（前缀移尾部，
            对齐引导圣临 `**…**PFS不可用` 尾随标签产出形态）
  4. L38-39 相位打击：半角类型括号全角化 + `****` 4 星粘连 PFS 剥星
            → `**相位打击（战斗，汲引）（Phase Strike (Combat, Conduit)）**PFS可`
  5. L53-54 浪徒之幸：同上 → `**浪徒之幸（汲引）（Wanderer's Fortune (Conduit)）**PFS可`
  6. L133-136 精通异界传送：`**【PFS】` 前缀 + `****出自**：` 4 星粘连出处断行
            → `**精通异界传送（Improved Plane Shift）**【PFS】`
  出处信息（出自《…pg. N》/出处 行）剥离——每条已有 `> 来源` 注释行补位，
  与公理化论述等纯化标题形态一致。

归一后 11 条目全部为标准闭合标题（FC-1r/1q 可识别）→ got 6→11 = est 11。

验证：6 处转换、163 → 154 行（合并 9 行）、LF-only 不变（无 CRLF）、
继承行字节守恒、6 个中文名落位、重跑 pipeline + verify + pytest。

用法：python3 fix_feat_planar_adventures.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长/位面冒险PA_专长.md"

CN_NAMES = ["闪现步", "暗影风暴", "治疗者之手", "相位打击", "浪徒之幸", "精通异界传送"]


def main() -> int:
    raw = open(PATH, "rb").read()
    lines = raw.split(b"\n")
    n = len(lines)
    print(f"输入：{n} 行，CRLF {raw.count(b'\r\n')}")

    out: list[str] = []
    fixed = 0
    report: list[str] = []
    fixed_orig: list[bytes] = []

    def take_text(i: int) -> str:
        return lines[i].decode("utf-8")

    def take_raw(i: int) -> bytes:
        fixed_orig.append(lines[i])
        return lines[i]

    i = 0
    while i < n:
        t = take_text(i)

        # 1) 闪现步：3 行标题内嵌出处（`…出自《Planar Adventures` + `pg. ` + `28》**`）
        if t.startswith("**闪现步（汲引）（Flickering Step (Conduit)）出自《Planar Adventures"):
            n1, n2 = take_text(i + 1), take_text(i + 2)
            assert n1 == "pg. " and n2 == "28》**", f"闪现步续行异常: {n1!r} {n2!r}"
            take_raw(i); take_raw(i + 1); take_raw(i + 2)
            out.append("**闪现步（汲引）（Flickering Step (Conduit)）**")
            report.append(f"L{i+1}-L{i+3} 闪现步：剥离内嵌出处，合并为闭合标题")
            fixed += 1
            i += 3
            continue

        # 2) 暗影风暴：标题行补闭合星 + 续行 3 星描述剥 1 星
        if t == "**暗影风暴（Gloomstorm）（汲引，战斗）":
            n1 = take_text(i + 1)
            assert n1.startswith("***") and n1.endswith("*"), f"暗影风暴续行异常: {n1[:50]!r}"
            take_raw(i); take_raw(i + 1)
            out.append("**暗影风暴（Gloomstorm）（汲引，战斗）**")
            out.append(n1[2:])  # `***描述*` → `*描述*`（3 星剥 2 星 → 单星斜体）
            report.append(f"L{i+1}-L{i+2} 暗影风暴：标题补闭合星，续行剥星")
            fixed += 1
            i += 2
            continue

        # 3) 治疗者之手：前缀 + 半角类型括号 + 出处后缀断行
        if t.startswith("【PFS不可】 **治疗者之手(Healer's "):
            n1, n2 = take_text(i + 1), take_text(i + 2)
            assert n1 == "Hands)(汲引)**出处 《位面冒险》（Planar ", f"治疗者之手续行异常: {n1[:60]!r}"
            assert n2 == "Adventures）第28页", f"治疗者之手出处行异常: {n2[:60]!r}"
            take_raw(i); take_raw(i + 1); take_raw(i + 2)
            out.append("**治疗者之手（Healer's Hands）（汲引）**【PFS不可】")
            report.append(f"L{i+1}-L{i+3} 治疗者之手：剥离前缀与出处，半角括号全角化")
            fixed += 1
            i += 3
            continue

        # 4) 相位打击：半角类型括号 + 4 星粘连 PFS
        if t.startswith("**相位打击(战斗,汲引) (Phase Strike (Combat, "):
            n1 = take_text(i + 1)
            assert n1 == "Conduit))****PFS可**", f"相位打击续行异常: {n1[:60]!r}"
            take_raw(i); take_raw(i + 1)
            out.append("**相位打击（战斗，汲引）（Phase Strike (Combat, Conduit)）**PFS可")
            report.append(f"L{i+1}-L{i+2} 相位打击：类型括号全角化，4 星粘连 PFS 剥星")
            fixed += 1
            i += 2
            continue

        # 5) 浪徒之幸：半角类型括号 + 双空格 + 尾随 **PFS可**
        if t.startswith("**浪徒之幸(汲引)  (Wanderer's Fortune "):
            n1 = take_text(i + 1)
            assert n1 == "(Conduit))**  **PFS可**", f"浪徒之幸续行异常: {n1[:60]!r}"
            take_raw(i); take_raw(i + 1)
            out.append("**浪徒之幸（汲引）（Wanderer's Fortune (Conduit)）**PFS可")
            report.append(f"L{i+1}-L{i+2} 浪徒之幸：类型括号全角化，尾随 **PFS可** 剥星")
            fixed += 1
            i += 2
            continue

        # 6) 精通异界传送：**【PFS】 前缀 + 4 星粘连出自标签断行
        if t.startswith("**【PFS】精通异界传送（Improved Plane "):
            n1, n2, n3 = take_text(i + 1), take_text(i + 2), take_text(i + 3)
            assert n1 == "Shift）", f"精通异界传送续行异常: {n1[:60]!r}"
            assert n2 == "****出自**：Planar Adventures pg. ", f"出自行异常: {n2[:60]!r}"
            assert n3 == "30", f"页码行异常: {n3[:60]!r}"
            take_raw(i); take_raw(i + 1); take_raw(i + 2); take_raw(i + 3)
            out.append("**精通异界传送（Improved Plane Shift）**【PFS】")
            report.append(f"L{i+1}-L{i+4} 精通异界传送：PFS 前缀移尾部，剥离 4 星出自标签")
            fixed += 1
            i += 4
            continue

        out.append(t)
        i += 1

    out_bytes = "\n".join(out).encode("utf-8")
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证 ----
    assert fixed == 6, f"预期修复 6 处，实际 {fixed}"
    assert len(new_lines) == n - 9, \
        f"预期 {n-9} 行（合并 9 行），实际 {len(new_lines)}"
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n"), \
        "CRLF 计数变化，行尾被污染"
    fixed_orig_set = set(fixed_orig)
    for l in set(lines) - fixed_orig_set:
        assert new_lines.count(l) == lines.count(l), \
            f"继承行字节不守恒：{l[:40]!r}"
    for cn in CN_NAMES:
        assert any(f"**{cn}（" in l.decode("utf-8") for l in new_lines), \
            f"{cn} 未落位"
    # 半角类型括号 + 4 星粘连 PFS 残留检查（仅行首星标题形态；
    # PA-source HTML 注释内嵌半角括号为合法注释，不误伤）
    residual = [l.decode("utf-8", errors="replace") for l in new_lines
                if re.match(r"^\*\*[^*\n]+\((战斗|汲引|类型)", l.decode("utf-8", errors="replace"))
                or "****PFS" in l.decode("utf-8", errors="replace")]
    assert not residual, f"杂糅形态残留 {len(residual)} 处"

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
