"""
fix_feat_page856.py — page_856 详情区行内粘连条目源数据修复（P0 级，107 条目全丢）

背景（2026-08-02 审计发现，P0 级）：page_856 是「专长」章节页，两部分：
  表 2-1（L56-176，108 条目）→ pipeline 已产出 feat_index 108 个 ✓；
  详情区（L183-447，107 个真实条目）→ 条目标题 `**中文（类型）**EN (Combat)*正文`
  与正文同行粘连、换行任意、标题嵌在行中 → 标题正则（^ 锚定行首）全部失配，
  107 个详情条目 100% 丢失（当前 6 个 feat 中仅 1 个真实条目）。

形态族（行内粘连标题）：
  T1 带类型   `**特技施法者（战斗）**Acrobatic Spellcaster (Combat)*你能够...`
  T2 无类型   `**虚张声势**Blustering Bluff*你能够以强势的口吻...`
  T3 复合类型 `**闪电备战（战斗，派头）**Lightning Draw (Combat, Panache)*你能够...`
  T4 新手特例 `**新手****` + 空行 + `Recruits***正文` + `*先决条件**：字段行`

修复（改源数据不改脚本，对齐 P0a 先例 7607913 / KN035 d8f638f / KN037 83e7aba）：
  - 行内标题切分为独立 FC-1q/FC-1n 行：
      `**特技施法者（Acrobatic Spellcaster）（战斗）**`（中文（EN）（类型））
      `**虚张声势（Blustering Bluff）**`（中文（EN））
  - 正文段 = 开星后到下一标题前，纯文本原样（无开星，对齐 page_670 段 1）
  - 新手特例：标题 `**新手（Recruits）**` + 正文去 `Recruits***` 前缀 +
    字段行 `*先决条件**：` 首星补全为 `**先决条件**：`，L369-370 空行删除
  - 行尾字节级保留（拆段行尾 = 原行行尾；CRLF 296 / 裸 LF 150 不变）
  - 表区/介绍区（L1-182）原样不动；正文中 `**法术名（EN）**` 引用、
    `**专长效果**：` 字段标签不匹配条目正则（后跟 `：`/中文，非英文+`*`）安全

用法：python3 fix_feat_page856.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长/page_856.md"

# 行内条目：**中文（类型）**EN (Combat)* 或 **中文**EN*
# group1 = 中文（可含中文类型括号），group2 = 英文名（懒惰，`(?:\([A-Za-z ,]+\))?`
# 消费英文类型括号 (Combat)/(Combat, Panache)，`\*` 消费正文开星）
RE_ENTRY = re.compile(
    r"\*\*([一-鿿]{2,15}(?:（[^）]{1,15}）)?)\*\*"
    r"([A-Za-z][A-Za-z'\-., `]*?)(?:\([A-Za-z ,]+\))?\*"
)
RE_CN_TYPE = re.compile(r"^(.*?)（([^）]+)）$")


def make_title(cn_type: str, en: str) -> str:
    """归一标题：带类型 → FC-1q **中文（EN）（类型）**；无类型 → FC-1n **中文（EN）**"""
    en = en.strip()
    m = RE_CN_TYPE.match(cn_type)
    if m:
        return f"**{m.group(1)}（{en}）（{m.group(2)}）**"
    return f"**{cn_type}（{en}）**"


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


def main() -> int:
    raw = open(PATH, "rb").read()
    lines = split_lines(raw)
    n = len(lines)
    assert n == 447, f"预期 447 行，实际 {n} 行——行号假设失效，中止"
    assert lines[182][0].startswith("**特技施法者（战斗）**"), \
        f"L183 非详情区首行：{lines[182][0][:40]!r}"

    out: list[tuple[str, bool]] = lines[:182]  # L1-182 表区/介绍区原样
    fixed = 0
    report: list[str] = []

    i = 182
    while i < n:
        text, cr = lines[i]

        # ---- 新手特例（0-indexed L367-371）----
        if i == 367:
            assert text.strip().startswith("**新手**"), f"L368 特例行失配：{text!r}"
            assert lines[368][0].strip() == "" and lines[369][0].strip() == "", \
                "L369-370 应为空行"
            body_line, body_cr = lines[370]
            assert body_line.startswith("Recruits***"), f"L371 失配：{body_line[:40]!r}"
            field_line, field_cr = lines[371]
            assert field_line.startswith("*先决条件**"), f"L372 失配：{field_line[:40]!r}"
            out.append(("**新手（Recruits）**", cr))
            out.append((body_line[len("Recruits***"):], body_cr))
            out.append(("**" + field_line[1:], field_cr))  # *先决条件** → **先决条件**
            fixed += 3
            report.append("L368-372: 新手特例 → **新手（Recruits）** + 正文 + 字段行")
            i += 5
            continue

        # ---- 行内标题切分 ----
        segments: list[str] = []
        last_end = 0
        found = False
        for m in RE_ENTRY.finditer(text):
            found = True
            if m.start() > last_end:
                segments.append(text[last_end:m.start()])  # 前条目正文续段
            segments.append(make_title(m.group(1), m.group(2)))
            last_end = m.end()
        if found:
            tail = text[last_end:]
            if tail:
                segments.append(tail)
            for seg in segments:
                if seg == "":
                    continue
                out.append((seg, cr))
            fixed += 1
            report.append(f"L{i+1}: 行内切分 {len([s for s in segments if s])} 段")
        else:
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
