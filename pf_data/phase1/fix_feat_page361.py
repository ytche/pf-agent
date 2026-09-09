"""
fix_feat_page361.py — page_361 甲斗流派段 21 专长跨行 4 星断裂标题归一（P0 级，est=59 got=52 丢 7）

背景（2026-08-02 KN026 复算审计，P0 级）：page_361（《护甲大师手册》专长页）
详情区 = 盾牌掌握专长 15 个（standard 闭合标题已产出）+ **甲斗流派段 21 个
流派专长**（鲨蜥流/金雕流/鹰啄流/铁壁流/铁手流/强击流/先锋流 × 基础+进阶）。
流派专长标题为 RE2 断裂形态：中文行 4 星包裹（`鲨蜥流**** ` / 进阶
`鲨蜥****·****扑**** `，断行点 `·` 被 4 星包裹）+ 续行 EN 4 星包裹
（`Bulette Charge Style****（战斗，流派专长）****`）。normalize 无覆盖 →
21 个流派详情 100% 丢失。判别器 est=59（FC-7:8 只认出部分，est 低估），
got=52（36 索引 + 15 盾牌详情 + 1 小节标题）。

修复（改源数据不改脚本，对齐 KN044 跨行标题归一先例）：
  - 21 对（行 A + 行 B）合并为单行 `**中文（EN）（类型）**`（FC-1r 可识别）
  - 进阶形态 `****·****` → `·`（鲨蜥·扑）
  - 介绍段内嵌形态（`鲨蜥流**** \nBulette Charge**：` 续行以 `**：` 结尾）
    非行 B，不误合并；页标题（行尾非 4 星）不匹配
  - 行 A 为 CRLF（文件 512 行 = 150 CRLF），合并行继承行 A 的 `\r`，
    其余继承行字节级原样保留

验证：21 对转换、512 → 491 行、CRLF 150 不变、行 B 形态残留 0、
继承行字节守恒、重跑 pipeline + verify。

用法：python3 fix_feat_page361.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长/page_361.md"

# 行 A：基础形态 `中文**** ` / 进阶形态 `中文****·****子名**** `（行尾 4 星，
# 允许尾空格；行 A 是 CRLF 行时 \r 由调用方剥离）
_RE_A_BASE = re.compile(r"^([一-鿿·]{2,})\*{4}\s*$")
_RE_A_ADV = re.compile(r"^([一-鿿·]+?)\*{4}·\*{4}([一-鿿·]+?)\*{4}\s*$")
# 行 B：`EN****（类型）****`（EN 可含空格/撇号/连字符；类型全角括号）
_RE_B = re.compile(r"^([A-Za-z][A-Za-z0-9 '.,()\-]*?)\*{4}（([^）]+)）\*{4}$")


def parse_line_a(text: str) -> str | None:
    """行 A → 中文名（剥 4 星与 `·` 星包裹）。非行 A 返回 None。"""
    m = _RE_A_ADV.match(text)
    if m:
        return m.group(1) + "·" + m.group(2)
    m = _RE_A_BASE.match(text)
    if m:
        return m.group(1)
    return None


def main() -> int:
    raw = open(PATH, "rb").read()
    lines = raw.split(b"\n")
    n = len(lines)
    print(f"输入：{n} 行，CRLF {raw.count(b'\r\n')}")

    out: list[bytes] = []
    fixed = 0
    report: list[str] = []
    fixed_orig: list[bytes] = []

    i = 0
    while i < n:
        content = lines[i].decode("utf-8")
        has_cr = content.endswith("\r")
        text = content[:-1] if has_cr else content

        cn = parse_line_a(text)
        if cn and i + 1 < n:
            nxt = lines[i + 1].decode("utf-8").strip("\r")
            mb = _RE_B.match(nxt)
            if mb:
                en, typ = mb.group(1), mb.group(2)
                out.append(f"**{cn}（{en}）（{typ}）**".encode("utf-8")
                           + (b"\r" if has_cr else b""))
                report.append(f"L{i+1}+L{i+2} → **{cn}（{en}）（{typ}）**")
                fixed += 1
                fixed_orig.append(lines[i])
                fixed_orig.append(lines[i + 1])
                i += 2
                continue
        # 非配对（介绍段内嵌形态 / 其他）：原样保留
        out.append(lines[i])
        i += 1

    out_bytes = b"\n".join(out)
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证 ----
    assert fixed == 21, f"预期修复 21 对，实际 {fixed}"
    assert len(new_lines) == n - 21, \
        f"预期 {n-21} 行（21 对合并），实际 {len(new_lines)}"
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n"), \
        "CRLF 计数变化，行尾被污染"
    residual = [l.decode("utf-8", errors="replace")
                for l in new_lines if _RE_B.match(l.decode("utf-8", errors="replace"))]
    assert not residual, f"行 B 形态残留 {len(residual)} 处"
    fixed_orig_set = set(fixed_orig)
    for l in set(lines) - fixed_orig_set:
        assert new_lines.count(l) == lines.count(l), \
            f"继承行字节不守恒：{l[:40]!r}"
    # 全部 21 个中文名落位检查（归一后标题形态）
    for cn in ["鲨蜥流", "鲨蜥·扑", "鲨蜥·狂", "金雕流", "金雕·卸", "金雕·袭",
               "鹰啄流", "鹰啄·迅", "鹰啄·疾", "铁壁流", "铁壁·坚", "铁壁·固",
               "铁手流", "铁手·击", "铁手·技", "强击流", "强击·返", "强击·绝",
               "先锋流", "先锋·盾", "先锋·佑"]:
        assert any(f"**{cn}（" in l.decode("utf-8") for l in new_lines), \
            f"{cn} 未落位"

    if out_bytes == raw:
        print("无变更")
        return 1

    with open(PATH, "wb") as f:
        f.write(out_bytes)
    print(f"== {PATH}：修复 {fixed} 对")
    for r in report:
        print("   ", r)
    print(f"CRLF: {raw.count(b'\r\n')} -> {out_bytes.count(b'\r\n')} "
          f"| 总行数: {n} -> {len(new_lines)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
