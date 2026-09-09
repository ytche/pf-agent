"""
fix_feat_page203.py — page_203 详情区「EN 星号粘连标题」16 行源数据归一（P0 级，est=266 got=258 丢 8）

背景（2026-08-02 审计发现，P0 级）：page_203（《进化职业手册》专长页）详情区
16 处标题为 RE2 断裂复合形态 `**中文**** EN***`（标题闭合后 4 星 + 空格 + EN +
尾星堆，EN 独立星号包裹；3 处跨行）。normalize 的标题链对「EN 尾无类型括号」
形态无覆盖：只剥 2 星留 `**中文** EN****` 畸形或截断中文（`**健硕之（歌, …**）**`），
split 无正则识别 → 14 个专长未产出独立 feat chunk（正文错误粘连进相邻 chunk）。

判别器 est=266 = 表格区 141（含 4 类型标记行虚高）+ 详情 126 口径；got 258 =
137 feat_index（表格区）+ 121 feat（详情区 113 + 表格混入）。修复后 got 精确
对齐真实条目（137 索引 + 126 详情 = 263）。

修复（改源数据不改脚本，对齐 KN042/KN046/KN048 锚点先例）：
  - 16 行归一为详情区已识别形态 `**中文（EN）**`（无类型）或 `**中文（EN）（类型）**`
  - 3 处跨行（EN 拆词到续行）合并为单行
  - **混合行尾（2655 行 = 840 CRLF + 1815 LF）**：逐行保留原行尾，不整体转换
  - 目标行外全部继承行字节级原样保留

验证：2655 → 2652 行（3 处跨行合并）、CRLF 计数 840 不变、
`**中文**** EN` 形态残留 0、修复后重跑 pipeline + verify。

用法：python3 fix_feat_page203.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长/page_203.md"

# 标题形态：`**中文**** EN…`（EN 独立星号包裹）。组1=中文，组2=EN 串。
# 组2 含尾星堆（`Believer`s Boon******`），故只排除换行不排除星。
RE_HEAD = re.compile(r"^\*\*([一-鿿][^*\n]*?)\*{4} ?([^\n]*)$")
# EN 串尾类型括号（中文括号+中文类型）
RE_TYPE = re.compile(r"（([一-鿿，、]{1,8})）$")


def normalize_line(line: str) -> str | None:
    """归一单行标题。返回 None 表示非目标形态。

    line 为去行尾的完整行（跨行形态返回 None，由调用方合并续行再调）。
    """
    m = RE_HEAD.match(line)
    if not m:
        return None
    cn, rest = m.group(1), m.group(2)
    # 排除非专长标题：`**译者：****傻豆**`（译者行）、`**《…》****…**`（页标题）
    if "：" in cn or "《" in cn or "》" in cn:
        return None
    rest = rest.strip()
    # EN 必须以 ASCII 字母开头（`**译者：****傻豆**` 中文 EN 排除）
    if not rest or not rest[0].isascii() or not rest[0].isalpha():
        return None
    # 去尾星堆（`******` 等）
    rest = re.sub(r"\*+$", "", rest).strip()
    if not rest:
        return None  # 无 EN（`**中文******` 形态）——不属本形态族
    # 提取尾类型括号（战斗专长等）；EN 区间星（`EN****（类型）` 分隔）一并去掉
    tm = RE_TYPE.search(rest)
    if tm:
        typ = tm.group(1)
        en = re.sub(r"\*+", "", rest[: tm.start()]).strip()
    else:
        typ, en = None, re.sub(r"\*+", "", rest).strip()
    assert re.fullmatch(r"[A-Za-z`'][A-Za-z0-9`'’\s\.\-]*", en), \
        f"EN 解析异常：{rest[:40]!r}"
    out = f"**{cn}（{en}）**"
    if typ:
        out = f"**{cn}（{en}）（{typ}）**"
    return out


def main() -> int:
    raw = open(PATH, "rb").read()
    lines = raw.split(b"\n")  # 行内容可能以 \r 结尾
    n = len(lines)
    print(f"输入：{n} 行，CRLF {raw.count(b'\r\n')}")

    out: list[bytes] = []
    fixed = 0
    merged = 0
    report: list[str] = []
    fixed_orig: list[bytes] = []  # 被替换/合并的原文行（守恒检查时排除）

    i = 0
    while i < n:
        content = lines[i].decode("utf-8")
        has_cr = content.endswith("\r")
        text = content[:-1] if has_cr else content

        # 跨行形态：当前行以 `**中文**** EN` 开头且未闭合（无 `**` 尾）
        m1 = RE_HEAD.match(text)
        if m1 and not m1.group(2).endswith("**"):
            # 合并续行（EN 后半 + 尾星堆）
            if i + 1 < n:
                nxt = lines[i + 1].decode("utf-8")
                merged_text = text + nxt.strip("\r")
                fixed_line = normalize_line(merged_text)
                if fixed_line:
                    out.append((fixed_line + ("\r" if has_cr else "")).encode("utf-8"))
                    report.append(f"L{i+1}+L{i+2} 跨行合并 → {fixed_line[:40]}")
                    fixed += 1
                    merged += 1
                    fixed_orig.append(lines[i])
                    fixed_orig.append(lines[i + 1])
                    i += 2
                    continue
        else:
            fixed_line = normalize_line(text)
            if fixed_line:
                out.append((fixed_line + ("\r" if has_cr else "")).encode("utf-8"))
                report.append(f"L{i+1} → {fixed_line[:40]}")
                fixed += 1
                fixed_orig.append(lines[i])
                i += 1
                continue
        # 非目标行：原样保留
        out.append(lines[i])
        i += 1

    out_bytes = b"\n".join(out)
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证 ----
    # 目标行数 = 16 行 + 3 跨行合并（每处 -1 行）
    assert fixed == 16, f"预期修复 16 处，实际 {fixed}"
    assert len(new_lines) == n - 3, f"预期 {n-3} 行，实际 {len(new_lines)}"
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n"), \
        "CRLF 计数变化，行尾被污染"
    # 残留检查：无 `**中文**** EN` 形态（bytes 字面量禁中文，decode 后判断）
    residual = [l.decode("utf-8") for l in new_lines
                if re.match(r"^\*\*[一-鿿]+\*\*\*\*\s*[A-Za-z]",
                            l.decode("utf-8", errors="replace"))]
    assert not residual, f"残留 {len(residual)} 处：{residual[:3]!r}"
    # 继承行守恒：非修复行（未被替换/合并的原文）在输出与输入中出现次数一致。
    # 修复行的原形态在输出中出现 0 次是预期（被替换），必须排除在守恒外。
    fixed_orig_set = set(fixed_orig)
    for l in set(lines) - fixed_orig_set:
        assert new_lines.count(l) == lines.count(l), \
            f"继承行字节不守恒：{l[:40]!r} 出现次数 {new_lines.count(l)} != {lines.count(l)}"

    if out_bytes == raw:
        print("无变更")
        return 1

    with open(PATH, "wb") as f:
        f.write(out_bytes)
    print(f"== {PATH}：修复 {fixed} 处（含跨行合并 {merged}）")
    for r in report:
        print("   ", r)
    print(f"CRLF: {raw.count(b'\r\n')} -> {out_bytes.count(b'\r\n')} "
          f"| 总行数: {n} -> {len(new_lines)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
