"""
fix_feat_psychic_anthology.py — 异能选集PA 催眠师专长段同行粘连拆分（P0 级，est=15 got=6）

背景（2026-08-02 审计发现，P0 级）：异能选集PA 是 K3 聚合文件（AA-source 注释），
判别器 est=15（FC-1x:5 操念使 + FC-8:10 催眠师）。操念使段 5 个专长已正常产出，
催眠师段 10 个专长（L14-17）全部同行粘连——`中文（EN）（类型）正文先决条件：
值专长效果：值` 标题/正文/字段无换行（RE2 转换残留），pipeline 无标题行可识别，
10 个专长 100% 丢失。

L14-L17 行间断点全在正文/字段值内部（`（包括大师诡计 \nMasterful \nTricks）`、
`（例如 \nDR 10/-）`），合并后内容完整。

形态族（催眠师 10 专长）：
  `致盲注视（Blinding Stare）（战斗，注视）你的注视夺去了...。先决条件：催眠师
   7级，痛苦注视职业特性专长效果：当你触发痛苦注视时...`
  ——标题（中文（EN）（类型））与正文同行、正文与字段同行、字段标签间无空格

修复（改源数据不改脚本，对齐 KN042 c821cef / KN041 77f42b5 先例）：
  - L14-L17 合并 → 按标题切 10 块（标题模式 `中文（EN）（中文类型）` 后跟正文，
    正文内 `目盲（Blinded）1轮` 等单组括号不匹配，天然免疫）
  - 每块拆 4 行：`**中文（EN）（类型）**` 标题行 + 正文行 +
    `先决条件：值` 行 + `专长效果：值` 行（partition 切标签，无星字段行原样）
  - 块首介绍续行（`Trick）的角色——…`）保留为一行；L11-13 介绍段/节标题不动
  - 行尾字节级保留（全裸 LF，新行 LF）；断言 n==54 + L3 注释 + 10 标题数

修复后：10 催眠师 + 5 操念使 = 15 = est=15 精确匹配，verify 不再 WARN。

用法：python3 fix_feat_psychic_anthology.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长/异能选集PA_专长.md"

# 标题模式：中文（EN）（中文类型），两组连续括号后跟正文（中文或 EN 词首）。
# 正文内「目盲（Blinded）1轮」第二组括号内是数字（不在字符类）→ 不匹配，天然免疫。
RE_TITLE = re.compile(
    r"([一-鿿]{2,10})（([A-Za-z][A-Za-z'’\.\- ]*?)）（([一-鿿A-Za-z ，、]{1,12})）"
)


def main() -> int:
    raw = open(PATH, "rb").read()
    lines = raw.split(b"\n")
    n = len(lines)
    assert n == 54, f"预期 54 行，实际 {n} 行——行号假设失效，中止"
    assert "<!-- 异能选集PA-source:page_725.md:mesmerist_feats -->" in \
        lines[2].decode("utf-8"), f"L3 非催眠师段注释：{lines[2][:50]!r}"
    # L14-17 全裸 LF（源数据无 CRLF）
    assert all(not l.endswith(b"\r") for l in lines[13:17]), "L14-17 含 CRLF，中止"

    # ---- 合并 L14-L17（字节级去换行，保留内容）----
    # ⚠️ 输出必须保留 L1-13（文件头/注释/介绍段）与 L18-54（操念使段）原样，
    #    仅用拆分结果替换 L14-17 四行
    merged = b"".join(lines[13:17]).decode("utf-8")

    # ---- 定位 10 个标题 ----
    titles = list(RE_TITLE.finditer(merged))
    assert len(titles) == 10, f"预期 10 个标题，实际 {len(titles)} 个：{merged[:60]!r}"

    out: list[str] = []
    fixed = 0
    report: list[str] = []

    # L1-13 原样保留（文件头/注释/介绍段）
    for l in lines[:13]:
        out.append(l.decode("utf-8"))

    # 介绍续行（块首到第一个标题）——原样保留为一行（LF）
    intro = merged[: titles[0].start()].strip()
    assert intro, "块首介绍为空？"
    out.append(intro)

    for idx, m in enumerate(titles):
        cn, en, type_ = m.group(1), m.group(2).strip(), m.group(3)
        start = m.end()
        end = titles[idx + 1].start() if idx + 1 < len(titles) else len(merged)
        block = merged[start:end]

        body, sep1, rest = block.partition("先决条件：")
        assert sep1, f"{cn} 无「先决条件：」字段"
        pre, sep2, eff = rest.partition("专长效果：")
        assert sep2, f"{cn} 无「专长效果：」字段"
        assert eff, f"{cn} 专长效果字段为空"

        out.append(f"**{cn}（{en}）（{type_}）**")
        if body.strip():
            out.append(body.strip())
        out.append(f"先决条件：{pre.strip()}")
        out.append(f"专长效果：{eff.strip()}")
        fixed += 1
        report.append(f"#{idx+1}: {cn}（{en}）拆 4 行")

    # 操念使段 L18-54 原样保留
    for l in lines[17:]:
        out.append(l.decode("utf-8"))

    out_bytes = ("\n".join(out) + "\n").encode("utf-8")

    new_lines = out_bytes.split(b"\n")
    print(f"== {PATH}：修复 {fixed} 处")
    for r in report:
        print("   ", r)
    print(f"CRLF: {raw.count(b'\r\n')} -> {out_bytes.count(b'\r\n')} "
          f"| 裸LF: {raw.count(b'\n')-raw.count(b'\r\n')} "
          f"-> {out_bytes.count(b'\n')-out_bytes.count(b'\r\n')} "
          f"| 总行数: {n} -> {len(new_lines)}")

    with open(PATH, "wb") as f:
        f.write(out_bytes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
