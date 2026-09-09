"""
fix_feat_page673.py — page_673 无信者专长段 7 处「裸标题+EN+正文粘连」归一（P0 级，est=21 got=14 丢 7）

背景（2026-08-02 KN026 复算审计，P0 级）：page_673（《万神录》专长页）
= 冥想专长段 7 + 自然专长段 6 + 万神殿段（万神祝福）+ 无信者专长段 6。
丢 7 = 万神祝福（L72）+ 无信者专长段 6 个（L134-149，got 0 个）。

形态 B（normalize 无覆盖）：裸标题 + 全大写 EN + 正文直接粘连，无星号包裹——
  `万神祝福 PANTHEISTIC BLESSlNG作为…`（L72）
  `神力抵抗 DlVlNE DEFIANCE你对于…`（L134）
EN 含 OCR 噪声（l/I 混用，`DlVlNE`/`ATHElST`），归一保留原文 EN。
B2 变体（L146 偶像破坏者）：EN 后带半角括号类型 `ICONOCLAST (COMBAT)你知道…`
  ——半角括号不在 B1 的 EN 字符集内，需独立正则。

判别器 est=21 = 冥想 7 + 自然 6 + 万神祝福 1 + 无信 6 + 万神殿 1（FC-8m/FC-8q/FC-3
只认部分），got=14（冥想 7 + 自然 6 + 乌笃喇神殿 1，万神祝福与无信 6 全丢）。

修复（改源数据不改脚本，对齐 KN044/KN048 源数据归一先例）：
  - B1（6 处）：`中文 EN中文正文` → `**中文（EN）**正文`（与 L12 冥想大师
    `**冥想大师 MEDITATION MASTER**` 带星标题产出形态一致的括号变体，
    FC-1r 可识别）
  - B2（1 处）：`中文 EN (COMBAT)中文正文` → `**中文（EN）（COMBAT）**正文`
  - 行数不变（148 行，无跨行合并）；逐行保留原行尾（CRLF 计数不变断言）

验证：7 处转换、行数不变、CRLF 计数不变、B1/B2 形态残留 0、
继承行字节守恒、7 个中文名落位、重跑 pipeline + verify。

用法：python3 fix_feat_page673.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长/page_673.md"

# B1：`中文 EN中文正文`（EN 全大写可含 OCR l/I 噪声、撇号、连字符、空格；
# 非贪婪 + 中文锚定，正文必须以中文开头）
_RE_B1 = re.compile(r"^([一-鿿]{2,}) ([A-Z][A-Z0-9lI'’\- ]{2,}?)([一-鿿].*)$")
# B2：`中文 EN (COMBAT)中文正文`（半角括号类型变体，L146 偶像破坏者）
_RE_B2 = re.compile(r"^([一-鿿]{2,}) ([A-Z][A-Z0-9lI'’\- ]{2,}?) \(([A-Z]+)\)([一-鿿].*)$")

# 归一后必须落位的 7 个中文名
CN_NAMES = ["万神祝福", "神力抵抗", "无信防护", "神力斥责者",
            "聚焦无信", "偶像破坏者", "怀疑之种"]


def main() -> int:
    raw = open(PATH, "rb").read()
    lines = raw.split(b"\n")
    n = len(lines)
    print(f"输入：{n} 行，CRLF {raw.count(b'\r\n')}")

    out: list[bytes] = []
    fixed = 0
    report: list[str] = []
    fixed_orig: list[bytes] = []  # 被替换的原文行（守恒检查时排除）

    for i, line in enumerate(lines):
        content = line.decode("utf-8")
        has_cr = content.endswith("\r")
        text = content[:-1] if has_cr else content

        m2 = _RE_B2.match(text)
        if m2:
            cn, en, typ, body = m2.groups()
            new = f"**{cn}（{en}）（{typ}）**{body}"
        else:
            m1 = _RE_B1.match(text)
            if not m1:
                out.append(line)
                continue
            cn, en, body = m1.groups()
            new = f"**{cn}（{en}）**{body}"
        out.append((new + ("\r" if has_cr else "")).encode("utf-8"))
        report.append(f"L{i+1} → {new[:60]}")
        fixed += 1
        fixed_orig.append(line)

    out_bytes = b"\n".join(out)
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证 ----
    assert fixed == 7, f"预期修复 7 处，实际 {fixed}"
    assert len(new_lines) == n, f"预期行数不变 {n}，实际 {len(new_lines)}"
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n"), \
        "CRLF 计数变化，行尾被污染"
    residual = [l.decode("utf-8", errors="replace") for l in new_lines
                if _RE_B1.match(l.decode("utf-8", errors="replace"))
                or _RE_B2.match(l.decode("utf-8", errors="replace"))]
    assert not residual, f"B1/B2 形态残留 {len(residual)} 处"
    fixed_orig_set = set(fixed_orig)
    for l in set(lines) - fixed_orig_set:
        assert new_lines.count(l) == lines.count(l), \
            f"继承行字节不守恒：{l[:40]!r}"
    for cn in CN_NAMES:
        assert any(f"**{cn}（" in l.decode("utf-8") for l in new_lines), \
            f"{cn} 未落位"

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
