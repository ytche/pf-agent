"""
fix_feat_page670.py — page_670 三分段源数据修复（P0 级，est=19 got=2）

背景（2026-08-02 审计发现，P0 级）：判别器 est=19 但当前产出仅 2 个 chunk，
且 2 个全是误识别（'冠位专长' 节标题 + '强大敌手' 术语定义）——19 个真实专长
100% 丢失。三分段形态：

  段 1（L7-10，3 个冠位专长）——RE2 标题断裂变体：中文名在上一行行尾 +
    英文名跨行拆段（`**冠位抗力**Ennobled ` + 下行 `Resistances*`），
    另有 `***` 三连星漂移（`惊人***先决条件：**`）与同行标题+正文
    （`Vested Power*你被赐予...`）。整段拼接正则解析后重组为：
    节标题行（`**冠位专长（Vested Feats）**`，19 字符触发 SECTION_HEADER
    跳过）+ 介绍行（cur=None 丢弃）+ 每条目 3 行：FC-1n 独立标题行 +
    独立正文行 + 原样字段行（**先决条件：**... 已完整闭合）。

  段 2（L24-68，13 个纯文本条目）——FC-8m 裸中文效果行（源数据原生无
    加粗结构，论坛帖格式，非 RE2 破坏）：`乐府训练你在位于...`。
    pipeline 无此形态支持 → 归一为 PUNCT_TITLE 形态：
    `**乐府训练：**` 独立行 + 正文行原样保留（含裸字段标签与跨行英文）。
    13 个中文名均不在 _ALL_FIELD_LABELS，无 R2 误判风险。

  段 3（L78-100，3 个故事专长）——RE2 断裂 + `****` 双星漂移 + 全角空格：
      L78 `**有志贵族（Aspiring ` + L79 `Noble）（故事）****　　正文`
      L80 `　　先决条件**：...**　　即时收益**：...`（裸标签 + 行中 ** 段）
    归一：FC-1q 独立标题 `**有志贵族（Aspiring Noble）（故事）**` +
    正文行 + 字段行 `**先决条件：**...**即时收益**：...`。

修复原则（对齐 page_276 先例 4e2bc24 / P0a 先例 7607913 / KN035 d8f638f）：
  - 改源数据不改脚本：归一为 pipeline 已支持的标准形态（FC-1n/FC-1q/PUNCT_TITLE）
  - 行尾字节级保留：重组行沿用源内容所在行的行尾（L7-L9 衍生 CR，
    L10 衍生裸 LF；段 2 拆行沿用原行行尾）
  - L104-109 术语定义段（强大敌手/角色等级/完胜）不动——标题 `：` 尾天然
    不匹配标题正则，误识别随修复自然消失
  - 未识别/跨行内容一律原样保留（RE_CROSS_EN 等既有机制负责）

用法：python3 fix_feat_page670.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长/page_670.md"

# ---- 段 1：L7-L10 整段拼接正则（跨行英文名在拼接处自然合并）----
# `***` 三连星 = `**`（字段标签 opens）+ `*`（漂移）：用 `\*` 消费漂移星、
# `\*\*先决条件：\*\*` 显式锚定字段行开头（2 星归字段行，不吞）
RE_S1 = re.compile(
    r"^\*\*冠位专长\(Vested Feats\)\*\*"
    r"(?P<intro>.*?)"
    r"\*\*冠位抗力\*\*Ennobled Resistances\*"
    r"(?P<body1>.*?)\*(?P<fields1>\*\*先决条件：\*\*.*?)"
    r"\*\*额外权能\*\*Extra Investiture Points\*"
    r"(?P<body2>.*?)\*(?P<fields2>\*\*先决条件：\*\*.*?)"
    r"\*\*额外冠位之力\*\*Extra Vested Power\*"
    r"(?P<body3>.*?)\*(?P<fields3>\*\*先决条件：\*\*.*)$"
)

# ---- 段 2：13 个纯文本条目（FC-8m → PUNCT_TITLE）----
S2_NAMES = [
    "乐府训练", "贤明贵族", "贵族津贴", "楷模臣子", "暗藏蔑视",
    "永恒帝王追迹者", "苏露奈门徒", "惯承龙威", "乘间伺隙", "循规阅读",
    "正义雄辩者", "隐藏灵光", "感知魔法问询",
]
RE_S2 = re.compile(rf"^({'|'.join(S2_NAMES)})(.*)$")

# ---- 段 3：故事专长（标题前缀行 + 下行英文段/正文 + 字段行）----
RE_S3_TITLE_LN = re.compile(r"^(\*\*[一-鿿]+)（([A-Za-z \-]+) $")
RE_S3_BODY = re.compile(r"^(Noble|Impostor)）（故事）\*\*\*\*　　(.*)$")
RE_S3_FIELDS = re.compile(r"^　　先决条件\*\*：(.*?)\*\*　　即时收益\*\*：(.*?)\*?$")


def split_lines(raw: bytes) -> list[tuple[str, bool]]:
    """读文件 → [(内容, 是否 CR 行尾)]，保留原始行尾字节信息"""
    return [(l[:-1].decode("utf-8", "ignore"), True) if l.endswith(b"\r")
            else (l.decode("utf-8", "ignore"), False)
            for l in raw.split(b"\n")]


def emit(lines: list[tuple[str, bool]], text: str, cr: bool):
    lines.append((text, cr))


def join_lines(lines: list[tuple[str, bool]]) -> bytes:
    out = []
    for text, cr in lines:
        out.append(text.encode("utf-8") + (b"\r" if cr else b""))
    return b"\n".join(out)


def main() -> int:
    raw = open(PATH, "rb").read()
    lines = split_lines(raw)
    report: list[str] = []
    fixed = 0
    n = len(lines)
    assert n == 109, f"预期 109 行，实际 {n} 行——行号假设失效，中止"

    out_lines: list[tuple[str, bool]] = []

    # ---- 段 1：L7-L10 整段重组（CR 行衍生 → CR，L10 裸 LF 衍生 → 裸 LF）----
    s1_joined = "".join(t for t, _ in lines[6:10])
    m1 = RE_S1.match(s1_joined)
    assert m1, f"段 1 正则未命中：{s1_joined[:80]!r}"
    for text in [
        "**冠位专长**",                          # 节标题（纯中文，SECTION_HEADER 跳过）
        m1.group("intro"),                        # 介绍（cur=None 丢弃）
        "**冠位抗力（Ennobled Resistances）**",   # FC-1n 独立标题
        m1.group("body1") + "。",
        m1.group("fields1"),
        "**额外权能（Extra Investiture Points）**",
        m1.group("body2") + "。",
        m1.group("fields2"),
        "**额外冠位之力（Extra Vested Power）**",
        m1.group("body3") + "。",
        m1.group("fields3"),                      # L10 衍生 → 裸 LF
    ]:
        emit(out_lines, text, cr=text != m1.group("fields3"))
    report.append(f"L7-L10: 段1 重组 11 行（3 条目 + 节标题 + 介绍）")
    fixed += 1

    # ---- 段 2/段 3 + 其余行：逐行过 ----
    i = 0
    while i < n:
        if i in (6, 7, 8, 9):
            i = 10  # 段 1 已处理
            continue
        text, cr = lines[i]

        # 段 3：标题前缀行（**有志贵族（Aspiring  尾）→ 与下行英文段合并成独立标题
        m3 = RE_S3_TITLE_LN.match(text)
        if m3 and i + 1 < n:
            nxt, nxt_cr = lines[i + 1]
            mb = RE_S3_BODY.match(nxt)
            if mb:
                title = f"{m3.group(1)}（{m3.group(2)} {mb.group(1)}）（故事）**"
                emit(out_lines, title, cr)
                emit(out_lines, mb.group(2), nxt_cr)
                report.append(f"L{i+1}-L{i+2}: 段3 标题合并 -> {title}")
                fixed += 1
                i += 2
                continue

        # 段 3：字段行（裸标签 + 全角空格 → **先决条件：** 形态）
        mf = RE_S3_FIELDS.match(text)
        if mf:
            emit(out_lines, f"**先决条件：**{mf.group(1)}**即时收益**：{mf.group(2)}", cr)
            report.append(f"L{i+1}: 段3 字段行归一")
            fixed += 1
            i += 1
            continue

        # 段 2：13 个纯文本条目 → **中文名：** + 正文行
        m2 = RE_S2.match(text)
        if m2:
            emit(out_lines, f"**{m2.group(1)}：**", cr)
            emit(out_lines, m2.group(2), cr)
            report.append(f"L{i+1}: 段2 {m2.group(1)} -> **{m2.group(1)}：**")
            fixed += 1
            i += 1
            continue

        emit(out_lines, text, cr)
        i += 1

    out_bytes = join_lines(out_lines)
    if out_bytes == raw:
        print("无变更")
        return 1

    with open(PATH, "wb") as f:
        f.write(out_bytes)
    print(f"== {PATH}：修复 {fixed} 处")
    for r in report:
        print("   ", r)
    print(f"CRLF: {raw.count(b'\\r\\n')} -> {out_bytes.count(b'\\r\\n')} "
          f"| 裸LF: {raw.count(b'\\n')-raw.count(b'\\r\\n')} -> {out_bytes.count(b'\\n')-out_bytes.count(b'\\r\\n')} "
          f"| 总行数: {n} -> {len(out_lines)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
