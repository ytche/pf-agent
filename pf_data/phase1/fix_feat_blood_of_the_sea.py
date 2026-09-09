"""
fix_feat_blood_of_the_sea.py — 海洋之血BotS_专长.md 19 处形态归一（P0 级，est=7 got=2 丢 5）

背景（2026-08-02 KN026 复算审计，P0 级）：海洋之血BotS_专长.md（《海洋之血》专长页，
未整理 → 海洋之血BotS 整理产物）7 条专长全部丢失（产出仅 2 个幽灵 chunk：
「海洋之血」doc 级索引 + 「塞卡利亚专」小节标题截断）。四种根因形态：

1. 条目标题「中文名 + 2 星 + 半角括号 EN 跨行 + 2 星 + 正文」杂糅（6 处）：
   `塞卡利亚专注纹**（Cecaelia Focus \nTattoo）**你在…`——标题无开头星、
   中文后残留闭合星、EN 半角括号跨行、正文与标题同行粘连。
2. 小节标题 4 星粘连（3 处）：`**塞卡利亚专长****正文` /
   `半鱼人专长****` / `梭螺鱼人专长****盟友呼唤**（Ally …`
   （小节标题 + 条目标题同行粘连，4 星对导致 split 星配对错位）。
3. 裸字段标签（7 处）：`先决条件**：…**效果**：…**` 星形错位
   （字段名后 2 星而非闭合星，子节标题过滤器不命中）。
4. 纹身列表行（3 处）：`专注纹列表：****金黄叉纹（Aureolin \nProng）：…`
   4 星粘连 + EN 跨行；`靛青藤纹（Indigo \nVines）：…` / `墨色旋纹（Inky \nWhorls）：…`
   EN 跨行（塞卡利亚专注纹正文的选择列表）。

修复（改源数据不改脚本，对齐 KN052-KN056 源数据归一先例）：
  1. 6 处条目标题归一为 `**中文（EN 折叠）**` 闭合形态，正文剥离独立成行
  2. 3 处小节标题剥 4 星成 `**中文**`，正文/条目标题断行剥离
  3. 7 处裸字段标签归一为 `**标签：**` 并拆行（子节标题过滤器命中所需）
  4. 3 处纹身列表行 4 星剥 2 星 + EN 跨行折叠

归一后 7 条全部为标准闭合标题（FC-1r/1q 可识别）→ got 2→7 = est 7。

验证：19 处转换、52 → 56 行（净 +4）、LF-only 不变（无 CRLF）、继承行字节守恒、
7 条专长中文名 + 3 个小节标题落位、条目 2 星杂糅 / 4 星 / 裸字段标签残留 0、
重跑 pipeline + verify + pytest。

用法：python3 fix_feat_blood_of_the_sea.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长/海洋之血BotS_专长.md"

CN_NAMES = ["塞卡利亚专注纹", "异怪克星施法者", "底栖魔鱼欺诈者", "无光海域探索者",
            "陆上生存者", "盟友呼唤", "水下侍从"]
SECTION_NAMES = ["塞卡利亚专长", "半鱼人专长", "梭螺鱼人专长"]

# 条目标题行 A：`中文名**（EN1 `（EN 跨行断点，行尾尾随空格；EN 可含连字符）
_RE_TITLE_A = re.compile(r"^([一-鿿]{2,})\*\*（([A-Za-z][A-Za-z -]*?)\s*$")
# 续行 B：`EN2）**正文`（正文直接跟标题，无星）
_RE_TITLE_B = re.compile(r"^([A-Za-z][A-Za-z -]*?)）\*\*(.+)$")
# 小节标题 4 星粘连变体：`**塞卡利亚专长****正文`
_RE_SECTION_6 = re.compile(r"^\*\*(塞卡利亚专长)\*\*\*\*(.+)$")
# `半鱼人专长****` 独立行
_RE_SECTION_28 = re.compile(r"^(半鱼人专长)\*\*\*\*$")
# `梭螺鱼人专长****盟友呼唤**（Ally `（小节标题 + 条目标题同行粘连）
_RE_SECTION_41 = re.compile(
    r"^(梭螺鱼人专长)\*\*\*\*(盟友呼唤)\*\*（([A-Za-z][A-Za-z -]*?)\s*$")
# 纹身列表行：`专注纹列表：****金黄叉纹（Aureolin `（4 星粘连）
_RE_LIST_4S = re.compile(r"^专注纹列表：\*\*\*\*(.+)$")
# 纹身列表续行：`Prong）：在陆地上…` / `Vines）：对抗…`
_RE_LIST_B = re.compile(r"^([A-Za-z][A-Za-z -]*?)）：(.+)$")
# 纹身列表行 EN 跨行：`靛青藤纹（Indigo `
_RE_LIST_EN = re.compile(r"^([一-鿿]{2,})（([A-Za-z][A-Za-z -]*?)\s*$")

# 裸字段标签两种星形：`**效果**：`（字段名双星包裹）与 `先决条件**：`（字段名后 2 星）
_RE_FLD_STAR = re.compile(r"\*\*(效果|特殊|一般情况)\*\*：")
_RE_FLD_BARE = re.compile(r"(?<![\*一-鿿])(先决条件)\*\*：")
# 行尾闭合星剥除（`。**` → `。`）
_RE_TRAIL_STAR = re.compile(r"\*\*$")


def _norm_fields(line: str) -> list[str]:
    """裸字段标签行归一：标签包裹 + 按标签拆行 + 行尾剥星。

    例：`先决条件**：塞卡利亚**效果**：从…。**`
        → [`**先决条件：**塞卡利亚`, `**效果：**从…。`]
    """
    line = _RE_FLD_STAR.sub(r"**\1：**", line)
    line = _RE_FLD_BARE.sub(r"**\1：**", line)
    parts = re.split(r"(?=\*\*(?:效果|特殊|一般情况)：)", line)
    return [p[:-2] if p.endswith("**") else p for p in parts]


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

        # ---- 1) 小节标题 4 星粘连 3 处 ----
        m = _RE_SECTION_6.match(t)
        if m:
            take_raw(i)
            out.append(f"**{m.group(1)}**")
            out.append(m.group(2))
            report.append(f"L{i+1} {m.group(1)}：4 星剥 2 星，正文断行剥离")
            fixed += 1
            i += 1
            continue
        m = _RE_SECTION_28.match(t)
        if m:
            take_raw(i)
            out.append(f"**{m.group(1)}**")
            report.append(f"L{i+1} {m.group(1)}：4 星剥 2 星")
            fixed += 1
            i += 1
            continue
        m = _RE_SECTION_41.match(t)
        if m:
            sec, cn, en1 = m.group(1), m.group(2), m.group(3)
            n1 = lines[i + 1].decode("utf-8")
            m2 = _RE_TITLE_B.match(n1)
            assert m2, f"{cn} 续行异常: {n1[:60]!r}"
            take_raw(i); take_raw(i + 1)
            out.append(f"**{sec}**")
            out.append(f"**{cn}（{en1} {m2.group(1)}）**")
            out.append(m2.group(2))
            report.append(f"L{i+1}-L{i+2} {sec}：小节标题剥离；{cn}：标题闭合归一")
            fixed += 1
            i += 2
            continue

        # ---- 2) 条目标题：中文名 + 2 星 + 半角括号 EN 跨行 + 2 星 + 正文（6 处）----
        m = _RE_TITLE_A.match(t)
        if m:
            cn, en1 = m.group(1), m.group(2)
            n1 = lines[i + 1].decode("utf-8")
            m2 = _RE_TITLE_B.match(n1)
            assert m2, f"{cn} 续行异常: {n1[:60]!r}"
            take_raw(i); take_raw(i + 1)
            out.append(f"**{cn}（{en1} {m2.group(1)}）**")
            out.append(m2.group(2))
            report.append(f"L{i+1}-L{i+2} {cn}：标题闭合归一 + 正文剥离")
            fixed += 1
            i += 2
            continue

        # ---- 3) 裸字段标签（7 处）----
        # 3a) 先决条件 3 行拼接（L43-45 盟友呼唤 / L48-50 水下侍从）
        if t == "先决条件**：梭螺鱼人，召唤自然盟友 ":
            n1 = lines[i + 1].decode("utf-8")
            m = re.match(r"^II法术能力，角色等级(3|5)级\*\*效果\*\*：(.+)$", n1)
            assert m, f"梭螺鱼人字段续行异常: {n1[:60]!r}"
            n2 = lines[i + 2].decode("utf-8")
            take_raw(i); take_raw(i + 1); take_raw(i + 2)
            if m.group(1) == "3":
                assert n2 == "法术能力每日使用次数。**特殊**：你可以多次选择该专长，" \
                             "每次获得额外2次使用次数。**", f"盟友呼唤末行异常: {n2[:60]!r}"
                assert m.group(2) == "你获得2次额外的召唤自然盟友 II ", \
                    f"盟友呼唤效果段异常: {m.group(2)[:60]!r}"
                out.append("**先决条件：**梭螺鱼人，召唤自然盟友 II法术能力，角色等级3级")
                out.append("**效果：**你获得2次额外的召唤自然盟友 II 法术能力每日使用次数。")
                out.append("**特殊：**你可以多次选择该专长，每次获得额外2次使用次数。")
            else:
                assert n2 == "II 的默认持续时间为1轮/等级。", \
                    f"水下侍从末行异常: {n2[:60]!r}"
                assert m.group(2) == "你的召唤自然盟友 II 法术能力的持续时间为1分钟/等级。" \
                                     "**一般情况**：召唤自然盟友 ", \
                    f"水下侍从效果段异常: {m.group(2)[:60]!r}"
                out.append("**先决条件：**梭螺鱼人，召唤自然盟友 II法术能力，角色等级5级")
                out.append("**效果：**你的召唤自然盟友 II 法术能力的持续时间为1分钟/等级。")
                out.append("**一般情况：**召唤自然盟友 II 的默认持续时间为1轮/等级。")
            report.append(f"L{i+1}-L{i+3} 字段 3 行拼接归一（{m.group(1)} 级）")
            fixed += 1
            i += 3
            continue
        # 3b) 单行字段标签（L10/31/34/37/40）：归一 + 拆行，不拼接
        if t.startswith("先决条件"):
            take_raw(i)
            parts = _norm_fields(t)
            out.extend(parts)
            report.append(f"L{i+1} 字段标签归一：{len(parts)} 段")
            fixed += 1
            i += 1
            continue

        # ---- 4) 纹身列表行（3 处）----
        m = _RE_LIST_4S.match(t)
        if m:
            n1 = lines[i + 1].decode("utf-8")
            m2 = _RE_LIST_B.match(n1)
            assert m2, f"专注纹列表续行异常: {n1[:60]!r}"
            take_raw(i); take_raw(i + 1)
            out.append(f"专注纹列表：**{m.group(1).rstrip()} {m2.group(1)}）：{m2.group(2)}")
            report.append(f"L{i+1}-L{i+2} 专注纹列表：4 星剥 2 星 + EN 跨行折叠")
            fixed += 1
            i += 2
            continue
        m = _RE_LIST_EN.match(t)
        if m:
            cn, en1 = m.group(1), m.group(2)
            n1 = lines[i + 1].decode("utf-8")
            m2 = _RE_LIST_B.match(n1)
            if m2:
                take_raw(i); take_raw(i + 1)
                out.append(f"{cn}（{en1} {m2.group(1)}）：{m2.group(2)}")
                report.append(f"L{i+1}-L{i+2} {cn}：EN 跨行折叠")
                fixed += 1
                i += 2
                continue

        out.append(t)
        i += 1

    out_bytes = "\n".join(out).encode("utf-8")
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证 ----
    assert fixed == 19, f"预期修复 19 处，实际 {fixed}"
    assert len(out) == n + 4, \
        f"预期 {n+4} 行（净 +4：拆行 +4 / 合并 -3），实际 {len(out)}"
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n"), \
        "CRLF 计数变化，行尾被污染"
    fixed_orig_set = set(fixed_orig)
    for l in set(lines) - fixed_orig_set:
        assert new_lines.count(l) == lines.count(l), \
            f"继承行字节不守恒：{l[:40]!r}"
    for cn in CN_NAMES:
        assert any(f"**{cn}（" in l.decode("utf-8") for l in new_lines), \
            f"{cn} 未落位"
    for sec in SECTION_NAMES:
        assert any(f"**{sec}**" in l.decode("utf-8") for l in new_lines), \
            f"{sec} 未落位"
    full = out_bytes.decode("utf-8", errors="replace")
    # 条目标题 2 星杂糅残留（`中文**（EN`）
    hits = re.findall(r"[一-鿿]{2,}\*\*（[A-Za-z]", full)
    assert not hits, f"条目标题 2 星杂糅残留 {len(hits)} 处: {hits}"
    assert "****" not in full, "4 星残留"
    hits = re.findall(r"(?<![\*一-鿿])先决条件\*\*：", full)
    assert not hits, f"先决条件裸标签残留 {len(hits)} 处"
    hits = re.findall(r"\*\*(效果|特殊|一般情况)\*\*：", full)
    assert not hits, f"字段双星标签残留 {len(hits)} 处"

    if out_bytes == raw:
        print("无变更")
        return 1

    with open(PATH, "wb") as f:
        f.write(out_bytes)
    print(f"== {PATH}：修复 {fixed} 处")
    for r in report:
        print("   ", r)
    print(f"CRLF: {raw.count(b'\r\n')} -> {out_bytes.count(b'\r\n')} "
          f"| 总行数: {n} -> {len(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
