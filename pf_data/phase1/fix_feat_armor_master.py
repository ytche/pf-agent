"""
fix_feat_armor_master.py — 护甲大师手册_专长.md 标题断裂源数据修复（P0 级，est=36 got=9）

背景（2026-08-02 审计发现，P0 级）：护甲大师手册 是 K3 整理产物（全裸 LF 301 行，
含 `<!-- ARMOR-source:... -->` 注释与 `> 来源：` 行），判别器 est=36（FC-3:16 +
FC-6d:14 + FC-6c:7）但当前仅 9 个 chunk（其中 4 个是节标题误识别）。真实专长
33 条（18 流派专长 + 13 盔甲掌握 + 护甲技法 + 战策）丢失 27。

形态族（全部是标题断裂/粘连，pipeline 标题正则 ^ 锚定失配）：

  A 流派专长（18 条）——`中文[·]****[中文]EN****（类型）****正文`，4 星漂移
    在中文名内部（`金雕·****卸`），英文名可跨行拆词（`Swift Iron ` + `Style****`）：
      A1 同行   `鲨蜥·****扑 Bulette Leap****（战斗专长）****跃入空中的你...`
      A2 跨行   `金雕流 Swift Iron ` + `Style****（战斗，流派专长）****正文`
      A3 跨行2星 `先锋·****佑 Vanguard ` + `Hustle****（战斗专长）**`（正文下一行）
  B 盔甲掌握专长（13 条）——`**中文 EN（类型）***正文***先决条件：**值**专长效果：**值`
    （类型括号全角/半角混用，EN 跨行拆词）：
      B1 同行   `**盔甲专攻Armor focus (战斗)***你特别擅长...***先决条件：**...`
      B2 跨行   `**进阶盔甲专攻Improved Armor focus ` + `(战斗) ***...`
  C 护甲技法（1 条跨 4 行）——`**护甲技法  Armor Trick ` + `(战斗专长)****来源：**...`
  D 技法节标题（3 条）——`**重甲技法 ` + `Heavy Armor Tricks **正文`
  E 节标题跨行（3 条）——`甲斗流派（Armor Fighting ` + `Styles****）****正文`
    与 `甲斗流派专长 Armor Style ` + `Feats`

修复（改源数据不改脚本，对齐 KN037 83e7aba / KN038 e96f656 / KN039 debeb8f）：
  - 归一 FC-1q/FC-1n 独立标题行：`**金雕·卸（Swift Refuge）（战斗专长）**`
  - 正文/字段行原样保留（同行 B 拆为 标题 + 正文 + `**先决条件：**...` 字段行）
  - 技法子条目（`Blade among the Folds (巧手 3 级)：**` 英文名开头）保持原样
  - 已识别条目（格拉里昂 L4-5 / 战策 L297 / 介绍段 L8）保持原样
  - 行尾字节级保留（全裸 LF，重组行沿用源行行尾；星数 "\\\\*" * 4 显式拼接）

用法：python3 fix_feat_armor_master.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长/护甲大师手册_专长.md"

RE_EN = r"[A-Za-z][A-Za-z'\-., `]*?"
STAR4 = "\\*" * 4
STAR3 = "\\*" * 3

# ---- A：流派专长（同行 or 跨行拼接后匹配）----
# g1=中文段（含·）, g2=中文后缀, g3=EN, g4=类型, g5=正文（2星闭合时 None）
RE_A = re.compile(
    r"^([一-鿿·]{2,15})(?:" + STAR4 + r")?([一-鿿]{1,6})? ?(" + RE_EN + r")"
    + STAR4 + r"（([一-鿿A-Za-z ，、]+)）"
    + r"(?:" + STAR4 + r"(.*)$|" + "\\*\\*" + r"$)"
)
# A 前缀行：行尾 EN+空格（EN 跨行拆词，如 `金雕流 Swift Iron `）
RE_A_PREFIX = re.compile(
    r"^([一-鿿·]{2,15})(?:" + STAR4 + r")?([一-鿿]{1,6})? ?"
    r"[A-Za-z][A-Za-z'\-., ]* $"
)
# A 续行：EN续****（类型）****正文 | EN续****（类型）**（正文在下一行）
RE_A_CONT = re.compile(
    r"^(" + RE_EN + r")" + STAR4 + r"（([一-鿿A-Za-z ，、]+)）"
    r"(?:" + STAR4 + r"(.*)|" + "\\*\\*" + r")$"
)

# ---- B：盔甲掌握专长（同行 or 跨行拼接后匹配）----
# g1=中文, g2=EN, g3=类型, g4=正文, g5=字段行（先决条件：**... 原样，
# 前面 `***` 的 2 星属标签开头、1 星漂移——归一输出补回 `**`）
RE_B = re.compile(
    r"^\*\*([一-鿿]{2,15})(" + RE_EN + r")\s*[（(]([一-鿿A-Za-z ，、]+)[)）]\s*"
    + STAR3 + r"(.*?)" + STAR3 + r"(先决条件：\*\*.*)$"
)
# B 前缀行：**中文EN + 行尾空格
RE_B_PREFIX = re.compile(r"^\*\*([一-鿿]{2,15})(" + RE_EN + r")[ ]$")
# B 续行：EN续?（类型） ***正文***先决条件：**...（L188 为 `expertise（盔甲掌握）`）
RE_B_CONT = re.compile(
    r"^(?:(" + RE_EN + r"))?\s*[（(]([一-鿿A-Za-z ，、]+)[)）]\s*"
    + STAR3 + r"(.*?)" + STAR3 + r"(先决条件：\*\*.*)$"
)

# ---- C：护甲技法 4 行块（L255-258 join 后匹配）----
# `****来源：**` = 4星 + 来源： + 2星（STAR4 已消费 4 星，来源前不再要求星）
RE_C1 = re.compile(
    r"^\*\*护甲技法 {2}Armor Trick\s*[（(]战斗专长[)）]" + STAR4
    + r"来源：\*\* ([^*\n]+)\*(.*?)" + STAR3
    + r"(先决条件：\*\*.*)$"
)

# ---- D：技法节标题（**中文技法 + EN**正文）----
RE_D_PREFIX = re.compile(r"^\*\*([一-鿿]{2,6}技法) $")
RE_D_CONT = re.compile(
    r"^(" + RE_EN + r")(?:（([^）]+)）)?\s*\*\*(.*)$"
)

# ---- E：节标题跨行 ----
# E1：中文（EN 前缀 + 4星）） + 4星 + 正文（甲斗流派/盾战流派）
RE_E1_PREFIX = re.compile(r"^([一-鿿]{2,15})（(" + RE_EN + r")$")
RE_E1_CONT = re.compile(r"^(" + RE_EN + r")" + STAR4 + r"）" + STAR4 + r"(.*)$")
# E2：中文 EN + 行尾空格 + 整行英文续（甲斗流派专长 Armor Style Feats）
RE_E2_PREFIX = re.compile(r"^([一-鿿]{2,15}) (" + RE_EN + r")$")
RE_E2_CONT = re.compile(r"^(" + RE_EN + r")$")


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
    # 跨行拼接处可能产生多空格（前缀行 EN 尾空格 + 续行），压为单空格
    en = re.sub(r"[ ]{2,}", " ", en).strip()
    if type_:
        return f"**{cn}（{en}）（{type_}）**"
    return f"**{cn}（{en}）**"


def main() -> int:
    raw = open(PATH, "rb").read()
    lines = split_lines(raw)
    n = len(lines)
    assert n == 301, f"预期 301 行，实际 {n} 行——行号假设失效，中止"
    assert lines[44][0].startswith("<!-- ARMOR-source:page_375.md:金雕流 -->"), \
        f"L45 非金雕流注释：{lines[44][0][:40]!r}"

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

        # ---- C：护甲技法 4 行块（L255-258）----
        if text.startswith("**护甲技法  Armor Trick"):
            joined = "".join(t for t, _ in lines[i:i + 4])
            m = RE_C1.match(joined)
            assert m, f"护甲技法块失配：{joined[:70]!r}"
            for seg in [
                make_title("护甲技法", "Armor Trick", "战斗专长"),
                f"**来源：** {m.group(1)}",
                m.group(2),
                "**" + m.group(3),  # 3星中 2 星属标签开头，1 星漂移——补回
            ]:
                out.append((seg, False))
            fixed += 1
            report.append(f"L{i+1}-L{i+4}: 护甲技法 4 行块重组")
            i += 4
            continue

        # ---- E1：节标题跨行 中文（EN + 4星）） + 4星 + 正文 ----
        m = RE_E1_PREFIX.match(text)
        if m and i + 1 < n:
            nxt, nxt_cr = lines[i + 1]
            mc = RE_E1_CONT.match(nxt)
            if mc:
                out.append((make_title(m.group(1), m.group(2) + " " + mc.group(1)),
                            cr))
                out.append((mc.group(2), nxt_cr))
                fixed += 1
                report.append(f"L{i+1}-L{i+2}: 节标题 {m.group(1)}（{m.group(2)} {mc.group(1)}）")
                i += 2
                continue

        # ---- D：技法节标题 **中文技法 + EN**正文 ----
        m = RE_D_PREFIX.match(text)
        if m and i + 1 < n:
            nxt, nxt_cr = lines[i + 1]
            mc = RE_D_CONT.match(nxt)
            if mc:
                out.append((make_title(m.group(1), mc.group(1), mc.group(2)), cr))
                out.append((mc.group(3), nxt_cr))
                fixed += 1
                report.append(f"L{i+1}-L{i+2}: 技法节标题 {m.group(1)}（{mc.group(1)}）")
                i += 2
                continue

        # ---- A：流派专长（同行 or 跨行拼接）----
        m = RE_A.match(text)
        consumed = 1
        if not m and i + 1 < n:
            nxt = lines[i + 1]
            if RE_A_PREFIX.match(text) and RE_A_CONT.match(nxt[0]):
                m = RE_A.match(text + nxt[0])
                if m:
                    consumed = 2
        if m:
            cn = (m.group(1) or "") + (m.group(2) or "")
            title = make_title(cn, m.group(3), m.group(4))
            out.append((title, cr))
            body = m.group(5)
            body_cr = lines[i + 1][1] if consumed == 2 else cr
            if body is None:
                # 2星闭合：正文在紧邻下一行（先锋·佑特例）
                nxt2, nxt2_cr = lines[i + consumed]
                assert nxt2.strip(), f"L{i+consumed+1} 正文行应为空"
                out.append((nxt2, nxt2_cr))
                consumed += 1
            elif body:
                out.append((body, body_cr))
            fixed += 1
            report.append(f"L{i+1}" + (f"-L{i+consumed}" if consumed > 1 else "")
                          + f": {cn} -> {title}")
            i += consumed
            continue

        # ---- B：盔甲掌握专长（同行 or 跨行拼接）----
        m = RE_B.match(text)
        consumed = 1
        if not m and i + 1 < n:
            nxt = lines[i + 1]
            if RE_B_PREFIX.match(text) and RE_B_CONT.match(nxt[0]):
                m = RE_B.match(text + nxt[0])
                if m:
                    consumed = 2
        if m:
            title = make_title(m.group(1), m.group(2), m.group(3))
            out.append((title, cr))
            nxt_cr = lines[i + 1][1] if consumed == 2 else cr
            out.append((m.group(4), nxt_cr))
            out.append(("**" + m.group(5), nxt_cr))  # 字段行补回标签开头 2 星
            fixed += 1
            report.append(f"L{i+1}" + (f"-L{i+consumed}" if consumed > 1 else "")
                          + f": {m.group(1)} -> {title}")
            i += consumed
            continue

        # ---- E2：无星节标题跨行（甲斗流派专长 Armor Style Feats）----
        m = RE_E2_PREFIX.match(text)
        if m and i + 1 < n:
            nxt = lines[i + 1]
            if RE_E2_CONT.match(nxt[0]):
                out.append((make_title(m.group(1), m.group(2) + " " + nxt[0].strip()),
                            cr))
                fixed += 1
                report.append(f"L{i+1}-L{i+2}: 节标题 {m.group(1)}（{m.group(2)} {nxt[0].strip()}）")
                i += 2
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
