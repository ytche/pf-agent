"""
fix_feat_distant_realms.py — 遥远国度DR_专长.md 12 处形态归一（P0 级，est=12 got=7 丢 5）

背景（2026-08-02 KN026 复算审计，P0 级）：遥远国度DR_专长.md（《遥远国度》专长页，
未整理 → 遥远国度DR 整理产物）三种形态导致 5 个条目丢失（est=12 = 浮碟术技艺 1 +
子技艺 6 + 引用魔法技艺 1 + 图纹 3 + 表格 1，got=7 丢 5）：

1. 类型括号跨行（3 处：防御性浮碟/浮碟骑手/扩展浮碟）：
   `防御性浮碟 \nDefensive Disk（飞行 3 \n级，擅长盾牌）：**正文**`
   ——`_RE_BARE_CN_EN_CNPAREN` 组3 `[^）)]*` 吞 `\n` 但替换模板不折叠 →
   `〔飞行 3 \n级，擅长盾牌〕` 含换行 → split 标题解析失败 → 条目丢失。
   全库普查仅本文件 3 处（个案 → 改源数据）。
2. 引用魔法技艺：`引用魔法技艺 \n  Magic Trick`——裸中文 + 缩进 EN 无括号，
   A/B/C 分支全不匹配。
3. 表格区 8 条目（合唱支援/天界破敌/融身入翼/流光耀/流光闪/流光式/传递恩惠/
   复兴导能）：详情表格行（L46-64）每行 1 条目（中文+EN 跨行 + 类型括号 +
   正文 + 裸字段标签），表格首格为介绍段无 EN → 非索引表 → split 不识别。

修复（改源数据不改脚本，对齐 KN052-KN054 源数据归一先例）：
  1. 3 处类型括号跨行折叠为一行（`（飞行 3 级，擅长盾牌）`），剥 `）：**` 残留
     （`：**` 是正文粘连残留，剥后 B 分支组4 直接正文）
  2. 引用魔法技艺 → `**引用魔法技艺（Magic Trick）**`
  3. 表格拆 8 条：去竖线与前导缩进，`**中文（EN）（类型）**正文`，
     裸字段标签包裹 `**先决条件：**`/`**专长效果：**`（子节标题过滤器
     `_RE_FIELD_IN_TEXT` 命中所需）；介绍段独立成行；`| --- |` 删除
     （8 条目 ≥ est 中表格 1，got 15→19 ≥ est 12 即可，got>est 不报）

验证：类型括号 3 + 引用 1 + 表格条目 8 = 12 处、90 → 76 行、LF-only 不变、
继承行字节守恒、12 个中文名落位、重跑 pipeline + verify + pytest。

用法：python3 fix_feat_distant_realms.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长/遥远国度DR_专长.md"

CN_NAMES = ["防御性浮碟", "浮碟骑手", "扩展浮碟", "引用魔法技艺",
            "合唱支援", "天界破敌", "融身入翼", "流光耀", "流光闪", "流光式",
            "传递恩惠", "复兴导能"]

# 表格条目行 A：`中文EN`（EN 跨行断点，行尾可尾随空格）
_RE_TA = re.compile(r"^\s*([一-鿿]{2,})([A-Za-z][A-Za-z ]*?)\s*$")
# 表格条目行 B：`EN续（类型）正文`（行尾可带 ` |`）
_RE_TB = re.compile(r"^\s*([A-Za-z][A-Za-z ]*?)（([^）]+)）(.*?)(?: \|)?$")
# 表格条目行 B 无括号变体：`EN续正文`（天界破敌/复兴导能，EN 后直接正文）
_RE_TB_NO_PAREN = re.compile(r"^\s*([A-Za-z][A-Za-z ]*?)([一-鿿][^|]*?)(?: \|)?$")

# 裸字段标签包裹（仅表格条目正文）
_RE_BARE_FL = re.compile(r"((?<![一-鿿])(?:先决条件|专长效果)[：:])")


def _wrap_fields(body: str) -> str:
    """表格条目正文裸字段标签 → `**标签：**`（子节标题过滤器命中所需）。"""
    return _RE_BARE_FL.sub(r"**\1**", body)


def main() -> int:
    raw = open(PATH, "rb").read()
    lines = raw.split(b"\n")
    n = len(lines)
    print(f"输入：{n} 行，CRLF {raw.count(b'\r\n')}")

    out: list[str] = []
    fixed = 0
    report: list[str] = []
    fixed_orig: list[bytes] = []

    def take_raw(i: int) -> bytes:
        fixed_orig.append(lines[i])
        return lines[i]

    i = 0
    while i < n:
        t = lines[i].decode("utf-8")

        # ---- 1) 类型括号跨行折叠（3 处：防御性浮碟/浮碟骑手/扩展浮碟）----
        # 防御性浮碟为 3 行结构（中文名 / EN+括号 / 类型续+正文），其余 2 行
        if t == "防御性浮碟 ":
            n1, n2 = lines[i + 1].decode("utf-8"), lines[i + 2].decode("utf-8")
            assert n1 == "Defensive Disk（飞行 3 ", f"防御性浮碟续行异常: {n1[:40]!r}"
            m2 = re.match(r"^级，擅长盾牌）：\*\*(.+)$", n2)
            assert m2, f"防御性浮碟类型行异常: {n2[:40]!r}"
            take_raw(i); take_raw(i + 1); take_raw(i + 2)
            out.append(f"**防御性浮碟（Defensive Disk）（飞行 3 级，擅长盾牌）**{m2.group(1)}")
            report.append(f"L{i+1}-L{i+3} 防御性浮碟：3 行合并 + 类型括号折叠 + 剥 `：**`")
            fixed += 1
            i += 3
            continue
        m = re.match(r"^([一-鿿]{2,}) (Defensive Disk|Disk Rider|Expanded Disk)（飞行 3 $", t)
        if m:
            n1 = lines[i + 1].decode("utf-8")
            m2 = re.match(r"^级(，[^）]*)?）：\*\*(.+)$", n1)
            assert m2, f"{m.group(1)} 续行异常: {n1[:60]!r}"
            take_raw(i); take_raw(i + 1)
            typ = "级" + (m2.group(1) or "")
            out.append(f"**{m.group(1)}（{m.group(2)}）（飞行 3 {typ}）**{m2.group(2)}")
            report.append(f"L{i+1}-L{i+2} {m.group(1)}：类型括号跨行折叠 + 剥 `：**`")
            fixed += 1
            i += 2
            continue

        # ---- 2) 引用魔法技艺：裸中文 + 缩进 EN 无括号 ----
        if t == "引用魔法技艺 ":
            n1 = lines[i + 1].decode("utf-8")
            assert n1.strip() == "Magic Trick", f"引用魔法技艺续行异常: {n1!r}"
            take_raw(i); take_raw(i + 1)
            out.append("**引用魔法技艺（Magic Trick）**")
            report.append(f"L{i+1}-L{i+2} 引用魔法技艺：裸标题+缩进 EN 归一")
            fixed += 1
            i += 2
            continue

        # ---- 3) 表格区：介绍段 + 8 条目拆行 ----
        if t.startswith("| 在第六翼学院"):
            # L46：`| 介绍段。合唱支援Choral ` → 介绍段行 + 条目首行
            mm = re.match(r"^\| (.+?。)([一-鿿]{2,})([A-Za-z][A-Za-z ]*?)\s*$", t)
            assert mm, f"介绍段行异常: {t[:60]!r}"
            intro, cn, en1 = mm.group(1), mm.group(2), mm.group(3)
            n1 = lines[i + 1].decode("utf-8")
            mb = _RE_TB.match(n1)
            assert mb, f"{cn} 续行异常: {n1[:60]!r}"
            take_raw(i); take_raw(i + 1)
            out.append(intro)
            out.append(f"**{cn}（{en1} {mb.group(1)}）（{mb.group(2)}）**"
                       f"{_wrap_fields(mb.group(3))}")
            report.append(f"L{i+1}-L{i+2} {cn}：表格条目拆行")
            fixed += 1
            i += 2
            continue
        if t.startswith("| --- |"):
            take_raw(i)
            report.append(f"L{i+1} 表格分隔行删除")
            i += 1
            continue
        ma = _RE_TA.match(t)
        if ma and i + 1 < n:
            n1 = lines[i + 1].decode("utf-8")
            mb = _RE_TB.match(n1)
            if mb:
                cn, en1 = ma.group(1), ma.group(2)
                take_raw(i); take_raw(i + 1)
                # 流光闪正文 EN 断行续行（`you make…`/`weapon），…`）并入正文
                body = mb.group(3)
                j = i + 2
                while j < n:
                    nxt = lines[j].decode("utf-8")
                    if re.match(r"^\s*[A-Za-z]", nxt) and not re.search(r"\|$", nxt):
                        take_raw(j)
                        body += "\n" + nxt.strip()
                        j += 1
                    else:
                        break
                out.append(f"**{cn}（{en1} {mb.group(1)}）（{mb.group(2)}）**"
                           f"{_wrap_fields(body)}")
                report.append(f"L{i+1}-L{j} {cn}：表格条目拆行")
                fixed += 1
                i = j
                continue
            # 无类型括号变体（天界破敌/复兴导能）：`EN续正文` → `**中文（EN）**正文`
            # 不要求行尾 ` |`（天界破敌行 B 竖线缺失，表格行尾残缺）
            mb2 = _RE_TB_NO_PAREN.match(n1)
            if mb2:
                cn, en1 = ma.group(1), ma.group(2)
                take_raw(i); take_raw(i + 1)
                out.append(f"**{cn}（{en1} {mb2.group(1)}）**{_wrap_fields(mb2.group(2))}")
                report.append(f"L{i+1}-L{i+2} {cn}：表格条目拆行（无类型括号）")
                fixed += 1
                i += 2
                continue

        out.append(t)
        i += 1

    out_bytes = "\n".join(out).encode("utf-8")
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证 ----
    assert fixed == 12, f"预期修复 12 处，实际 {fixed}"
    # 元素级断言（流光闪正文 EN 断行保留内嵌 \n，实际文件行数 = 元素数 + 内嵌数）
    assert len(out) == n - 15, \
        f"预期 {n-15} 元素（合并 15 行），实际 {len(out)}"
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n"), \
        "CRLF 计数变化，行尾被污染"
    fixed_orig_set = set(fixed_orig)
    for l in set(lines) - fixed_orig_set:
        assert new_lines.count(l) == lines.count(l), \
            f"继承行字节不守恒：{l[:40]!r}"
    for cn in CN_NAMES:
        assert any(f"**{cn}（" in l.decode("utf-8") for l in new_lines), \
            f"{cn} 未落位"
    # 类型括号跨行残留检查（B 分支组3 含换行的行首标题）
    from vectorizer.formats import feat as F
    full = out_bytes.decode("utf-8")
    hits = [m.group(1) for m in F._RE_BARE_CN_EN_CNPAREN.finditer(full)
            if "\n" in m.group(3)]
    assert not hits, f"类型括号跨行残留 {len(hits)} 处: {hits}"
    # 表格竖线残留检查
    assert "| 在第六翼" not in full and "| --- |" not in full, "表格竖线残留"

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
