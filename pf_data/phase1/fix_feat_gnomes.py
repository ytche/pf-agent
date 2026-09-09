"""
fix_feat_gnomes.py — 格拉里昂的侏儒 跨行断裂标题源数据归一（P0 级，est=13 got=4，专长52 K3 聚合副本）

背景（2026-08-02 审计发现，P0 级）：专长52 是《侏儒职业指南》专长页（13 真实
专长 + 1 节标题「社会，侏儒巧舌」）。判别器 est=13（FC-1o:7 + FC-1n:3 +
FC-1q:1 + FC-6e:1），当前仅 4 个 chunk（有 `（EN）` 括号的跨行标题被部分识别，
title 丢 EN 名），9 个专长 100% 丢失。

形态族（RE2 换行断裂，`**` 前缀标题跨行，EN 名拆词）：

  T1 括号跨行（5 条含节标题）`**中文（EN前 ` + 续行 `EN后）`/`EN后）（类型）**`：
     惊奇大师 Master of / Wonders；轻松欺骗 Effortless / Trickery；
     额外侏儒魔法 Extra Gnome / Magic；威胁幻象 Threatening / Illusion（超魔）；
     社会，侏儒巧舌 Social，Speaking / Gnome（节标题，EN 含全角逗号）
  T2 无括号跨行（7 条）`**中文EN前 ` + 续行 `EN后`（行尾无 `）`）：
     学派鼓吹手 Arcane School / Spirit；血脉共鸣 Blood / Ties；
     尖酸辱骂 Caustic / Slur；无助囚徒 Helpless / Prisoner；
     唤起本能 Invoke Primal / Instinct；妙语虚招 Witty Feint / （战斗）（类型续行）；
     惑心公案 Bewildering Koan / 空行（单行尾空格，无续行）
  T3 同行无括号（1 条）`**巧舌商贩Babble-Peddler`
  T4 同行带类型（1 条）`**撒泼打滚Tantrum（战斗）`

修复（改源数据不改脚本，对齐 KN042 c821cef / KN043 504b66b 先例）：
  - T1/T2/T3/T4 → FC-1q/FC-1n 独立标题行 `**中文（EN）（类型）**`
  - 正文/字段行原样保留（含 `***` 前缀星——非标题行并入 text，不干预）
  - 合并行沿用前缀行行尾（CRLF 保持 30 不变）；断言 n==114 + L1 惊奇大师锚点

修复后：13 专长全出 + 节标题 = est=13 对账通过（节标题为额外产出，got>est 不 WARN）。

用法：python3 fix_feat_gnomes.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长/格拉里昂的侏儒_专长.md"

# ⚠️ 前缀行必须「行尾空格」锚定跨行（`Master of ` / `Arcane School `），
#    同行形态无尾空格——不 strip 直接匹配，防止 T2 误吞 T3
# T1 前缀：`**中文（EN前 `（EN 可含全角逗号——社会，侏儒巧舌 Social，Speaking）
RE_T1 = re.compile(r"^\*\*([一-鿿，]{2,15})（([A-Za-z][A-Za-z'’\.\- ，]*?)[ ]$")
# T1 续行：`EN后）` / `EN后）（类型）**` / `EN后）**`（闭合括号为全角 `）`）
RE_T1_CONT = re.compile(
    r"^([A-Za-z][A-Za-z'’\.\- ，]*?)）(?:（([一-鿿A-Za-z ，、]{1,12})）)?\*{0,2}$"
)
# T2 前缀：`**中文EN前 `（行尾空格）
RE_T2 = re.compile(r"^\*\*([一-鿿，]{2,15})([A-Za-z][A-Za-z'’\.\- ，]*?)[ ]$")
# T2 续行：`EN后` / `EN后**` / `（类型）`（妙语虚招续行）
RE_T2_CONT = re.compile(r"^([A-Za-z][A-Za-z'’\.\- ，]*?)\*{0,2}$")
RE_T2_TYPE = re.compile(r"^（([一-鿿A-Za-z ，、]{1,12})）$")
# T3 同行无括号：`**中文EN`（无尾空格——负向断言防吞跨行前缀的尾空格）
RE_T3 = re.compile(r"^\*\*([一-鿿，]{2,15})([A-Za-z][A-Za-z'’\.\- ，]*?)(?<![ ])$")
# T4 同行带类型：`**中文EN（类型）`
RE_T4 = re.compile(
    r"^\*\*([一-鿿，]{2,15})([A-Za-z][A-Za-z'’\.\- ，]*?)（([一-鿿A-Za-z ，、]{1,12})）$"
)


def main() -> int:
    raw = open(PATH, "rb").read()
    lines = raw.split(b"\n")
    n = len(lines)
    assert n == 121, f"预期 121 行，实际 {n} 行——行号假设失效，中止"
    assert lines[5].startswith(b"**\xe6\x83\x8a\xe5\xa5\x87\xe5\xa4\xa7\xe5\xb8\x88"), \
        f"L6 非惊奇大师：{lines[5][:40]!r}"

    out: list[tuple[str, bool]] = []
    fixed = 0
    report: list[str] = []
    i = 0
    while i < n:
        # 去 CR 但保留行尾空格（跨行锚定）；空行原样保留
        text = lines[i].decode("utf-8").rstrip("\r")
        cr = lines[i].endswith(b"\r")
        st = text.strip()
        if not st:
            out.append((text, cr))
            i += 1
            continue

        # ---- T1：括号跨行（前缀行尾空格 + EN续行含 `）`）----
        m1 = RE_T1.match(text)
        if m1 and i + 1 < n:
            nxt = lines[i + 1].decode("utf-8").strip()
            m1c = RE_T1_CONT.match(nxt)
            if m1c:
                cn, en1 = m1.group(1), m1.group(2).strip()
                en2, type_ = m1c.group(1), m1c.group(2)
                title = f"**{cn}（{en1} {en2}）" + (f"（{type_}）" if type_ else "") + "**"
                out.append((title, cr))
                fixed += 1
                report.append(f"L{i+1}-L{i+2}: {cn} 括号跨行归一")
                i += 2
                continue

        # ---- T2：无括号跨行（前缀行尾空格 + EN/类型续行）----
        m2 = RE_T2.match(text)
        if m2 and i + 1 < n:
            nxt = lines[i + 1].decode("utf-8").strip()
            m2c = RE_T2_CONT.match(nxt) if nxt else None
            m2t = RE_T2_TYPE.match(nxt) if nxt else None
            if m2c:
                cn, en1 = m2.group(1), m2.group(2).strip()
                out.append((f"**{cn}（{en1} {m2c.group(1)}）**", cr))
                fixed += 1
                report.append(f"L{i+1}-L{i+2}: {cn} 无括号跨行归一")
                i += 2
                continue
            if m2t:
                cn, en1 = m2.group(1), m2.group(2).strip()
                out.append((f"**{cn}（{en1}）（{m2t.group(1)}）**", cr))
                fixed += 1
                report.append(f"L{i+1}-L{i+2}: {cn} 类型续行归一（妙语虚招）")
                i += 2
                continue
            if not nxt:
                # T2 单行尾空格（惑心公案：续行为空行）——EN 完整在行内
                cn, en = m2.group(1), m2.group(2).strip()
                out.append((f"**{cn}（{en}）**", cr))
                fixed += 1
                report.append(f"L{i+1}: {cn} 单行尾空格归一")
                i += 1
                continue

        # ---- T4：同行带类型 ----
        m4 = RE_T4.match(text)
        if m4:
            out.append((f"**{m4.group(1)}（{m4.group(2).strip()}）（{m4.group(3)}）**", cr))
            fixed += 1
            report.append(f"L{i+1}: {m4.group(1)} 同行带类型归一")
            i += 1
            continue

        # ---- T3：同行无括号 ----
        m3 = RE_T3.match(text)
        if m3:
            out.append((f"**{m3.group(1)}（{m3.group(2).strip()}）**", cr))
            fixed += 1
            report.append(f"L{i+1}: {m3.group(1)} 同行归一")
            i += 1
            continue

        out.append((text, cr))
        i += 1

    out_bytes = b"\n".join(t.encode("utf-8") + (b"\r" if c else b"") for t, c in out)
    if out_bytes == raw:
        print("无变更")
        return 1

    with open(PATH, "wb") as f:
        f.write(out_bytes)
    print(f"== {PATH}：修复 {fixed} 处")
    for r in report:
        print("   ", r)
    print(f"CRLF: {raw.count(b'\r\n')} -> {out_bytes.count(b'\r\n')} "
          f"| 裸LF: {raw.count(b'\n')-raw.count(b'\r\n')} "
          f"-> {out_bytes.count(b'\n')-out_bytes.count(b'\r\n')} "
          f"| 总行数: {n} -> {len(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
