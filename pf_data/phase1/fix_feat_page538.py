r"""
fix_feat_page538.py — page_538 神祇信仰专长页标题断裂源数据修复（P0 级，est=29 got=10）

背景（2026-08-02 审计发现，P0 级）：page_538 是神祇信仰专长页（凯登/黛丝娜/
埃拉斯蒂尔…15 个神祇段，28 个真实专长）。判别器 est=29（FC-7:29 = 28 真实
专长 + 1 神祇段误识别 `**莎莱伦**`），当前仅 10 个 chunk（9 个半识别残缺 +
1 个神祇段误识别），19 个真实专长 100% 丢失。

形态族（RE2 星号漂移 + 中文名行/英文名行跨行断裂，pipeline M13 系列要求
`^\*\*` 前缀才拆行，无前缀行全失配）：

  S1 同行 2星/4星前缀   `**中文（EN）*****正文` / `****中文（EN）****（类型）*****正文`
                       （9 条：酩酩侠/灵巧自然盟友/洞观奥秘/以血还血/黄金律/
                       激流冲压/钢刺碎击/不动如山/血溅五步——已半识别但字段行截断）
  S2 跨行无前缀        `中文**** \nEN*****正文` / `中文**** \nEN ****（类型）*****正文`
                       （17 条：占决预导/正义冲锋/防御者之击/赋予希望/火热荣耀/
                       枪矛旋舞/阅岩术/深地行者/秩序之心/特征抹杀/恐怖处决/
                       百毒不侵/闪影/横冲直撞/碾压冲撞/崩溃意志/拥抱痛觉——全丢）
  S3 跨行 3 行          `****彩蝶毒蛰**** \nEN****（类型）****\n***正文`（1 条）
  S4 神段误识别        `**莎莱伦****莎莱伦的使徒…**。**`——被当条目标题，
                       吞掉下一专长「赋予希望」标题行

修复（改源数据不改脚本，对齐 KN037/KN038/KN039/KN040 先例）：
  - S1/S2/S3 → FC-1q/FC-1n 独立标题行 `**中文（EN）（类型）**`，正文行去
    前缀星、原样保留（字段行 `先决条件：**…` 原样不动）
  - S4 → 拆 `**莎莱伦**` 独立行（SECTION_HEADER ≤30 字符跳过，不再误识别
    吞条目）+ 神祇描述行原样
  - 其余神段（`**凯登****．****凯利恩****…`）当前不误识别，保持原样
  - 行尾字节级保留（CRLF/LF 沿用原行行尾）；断言 n==195 + L11 凯登防漂移

修复后：28 真实专长全出 = 100%，判别器 est=29 的 1 个神段误识别计数
登记豁免（docs/state/feat_exemptions_20260801.md），verify 不再 WARN。

用法：python3 fix_feat_page538.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长/page_538.md"

# ---- S1/S2 共用：中文（EN）[（类型）] + 星组 + 正文 ----
# g1=中文, g2=EN, g3=类型（可选）, g4=正文（同行型）或续行型正文
RE_BODY = re.compile(
    r"([一-鿿]{2,15})（([A-Za-z][^*\n]*)）"
    r"(?:\*{2,4}（([一-鿿A-Za-z ，、]+)）)?\*{2,}(.*)$"
)
# S1 同行：星前缀(0-4) + 中文（EN）…
RE_SAME = re.compile(r"^\*{0,4}" + RE_BODY.pattern)
# S2 前缀行：中文 + 2星以上 + 行尾空格（`占决预导**** `）
RE_PREFIX_2 = re.compile(r"^([一-鿿]{2,15})\*{2,}[ ]?$")
# S2 续行：EN[（类型）] + 星组 + 正文（`Divination Guide*****正文` /
# `Charge of the Righteous ****（战斗专长）*****正文`）
RE_CONT_2 = re.compile(
    r"^([A-Za-z][^*\n]*?)(?:\*{2,4}（([一-鿿A-Za-z ，、]+)）)?\*{2,}(.*)$"
)

# S3 彩蝶毒蛰 3 行特判（L18-20）
RE_3_PREFIX = re.compile(r"^\*{2,}([一-鿿]{2,15})\*{2,}[ ]?$")
RE_3_CONT = re.compile(r"^([A-Za-z][^*\n]*?)\*{2,4}（([一-鿿A-Za-z ，、]+)）\*{2,}$")
RE_3_BODY = re.compile(r"^\*{1,4}(.*)$")

# S4 莎莱伦神段（L50）：`**莎莱伦****莎莱伦的使徒…` —— 拆标题 + 描述行。
# 仅拆「描述以中文直接开头」形态（凯登等 `**中文****．****…` 中缀形态不误识别，
# 保持原样，防残留 `．****` 星中缀）；`(?![．\*])` 防误拆。
RE_GODDESC_SPLIT = re.compile(r"^\*\*([一-鿿]{2,6})\*\*\*\*(?![．\*])([^\n]+)$")


def split_lines(raw: bytes) -> list[tuple[str, bool]]:
    """读文件 → [(内容, 是否 CR 行尾)]，保留原始行尾字节信息"""
    return [(l[:-1].decode("utf-8", "ignore"), True) if l.endswith(b"\r")
            else (l.decode("utf-8", "ignore"), False)
            for l in raw.split(b"\n")]


def join_lines(lines: list[tuple[str, bool]]) -> bytes:
    out = []
    for text, cr in lines:
        out.append(text.encode("utf-8") + (b"\r" if cr else b""))
    return b"\n".join(out)


def make_title(cn: str, en: str, type_: str | None = None) -> str:
    en = en.strip()
    if type_:
        return f"**{cn}（{en}）（{type_}）**"
    return f"**{cn}（{en}）**"


def main() -> int:
    raw = open(PATH, "rb").read()
    lines = split_lines(raw)
    n = len(lines)
    assert n == 196, f"预期 196 行，实际 {n} 行——行号假设失效，中止"
    assert lines[9][0].startswith("**凯登"), f"L10 非凯登神段：{lines[9][0][:30]!r}"

    out: list[tuple[str, bool]] = []
    fixed = 0
    report: list[str] = []
    i = 0
    while i < n:
        text, cr = lines[i]
        st = text.strip()
        if not st:
            out.append((text, cr))
            i += 1
            continue

        # ---- S3：彩蝶毒蛰 3 行特判（L18-20）----
        if text.startswith("****彩蝶毒蛰"):
            m3p = RE_3_PREFIX.match(text)
            nxt, nxt_cr = lines[i + 1]
            m3c = RE_3_CONT.match(nxt)
            body, body_cr = lines[i + 2]
            m3b = RE_3_BODY.match(body)
            assert m3p and m3c and m3b, f"彩蝶毒蛰 3 行块失配：{text[:30]!r} / {nxt[:30]!r} / {body[:30]!r}"
            out.append((make_title(m3p.group(1), m3c.group(1), m3c.group(2)), cr))
            out.append((m3b.group(1), body_cr))
            fixed += 1
            report.append(f"L{i+1}-L{i+3}: {m3p.group(1)} 3 行重组")
            i += 3
            continue

        # ---- S4：莎莱伦神段拆行（L50，唯一误识别神段）----
        # 白名单行首特判：`**莎莱伦****莎莱伦的使徒…` —— 拆 `**莎莱伦**`
        # （SECTION_HEADER ≤30 跳过，不再误识别吞「赋予希望」）+ 描述行原样。
        # 其余神段（凯登 `**．**` 中缀 / 黛丝娜等无中缀）当前均不误识别，保持原样。
        if text.startswith("**莎莱伦****"):
            m4 = RE_GODDESC_SPLIT.match(text)
            assert m4, f"L{i+1} 莎莱伦神段失配：{text[:40]!r}"
            out.append((f"**{m4.group(1)}**", cr))
            out.append((m4.group(2), cr))
            fixed += 1
            report.append(f"L{i+1}: {m4.group(1)} 神段拆行（标题 + 描述）")
            i += 1
            continue

        # ---- S2：跨行无前缀（前缀行 + 续行）----
        m2p = RE_PREFIX_2.match(text)
        if m2p and i + 1 < n:
            nxt, nxt_cr = lines[i + 1]
            m2c = RE_CONT_2.match(nxt)
            if m2c:
                out.append((make_title(m2p.group(1), m2c.group(1), m2c.group(2)), cr))
                body = m2c.group(3)
                consumed = 2
                if not body:
                    # `****` 行尾闭合：正文在紧邻下一行（Bullseye Shot 特例）
                    nxt2, nxt2_cr = lines[i + 2]
                    m2b = RE_3_BODY.match(nxt2)
                    assert m2b, f"L{i+3} 正文行失配：{nxt2[:40]!r}"
                    out.append((m2b.group(1), nxt2_cr))
                    consumed = 3
                else:
                    out.append((body, nxt_cr))
                fixed += 1
                report.append(f"L{i+1}-L{i+consumed}: {m2p.group(1)} 跨行归一")
                i += consumed
                continue

        # ---- S1：同行（星前缀 + 中文（EN）…）----
        m1 = RE_SAME.match(text)
        if m1:
            out.append((make_title(m1.group(1), m1.group(2), m1.group(3)), cr))
            if m1.group(4):
                out.append((m1.group(4), cr))
            fixed += 1
            report.append(f"L{i+1}: {m1.group(1)} 同行归一")
            i += 1
            continue

        out.append((text, cr))
        i += 1

    out_bytes = join_lines(out)
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
