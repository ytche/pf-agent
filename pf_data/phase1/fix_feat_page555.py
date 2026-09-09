"""
fix_feat_page555.py — page_555 详情区标题断裂源数据修复（P0 级，详情 30 条目 28 丢失）

背景（2026-08-02 审计发现，P0 级）：page_555 是《近战工具箱》专长页，两部分：
  表格区（L10-74，30 条目，英文名行 + 中文名行双行）→ pipeline 已正常产出
  feat_index 30 个 ✓；
  详情区（L83-342，30 个真实条目）→ 条目标题 3 种 RE2 断裂形态，pipeline
  仅识别 2 个（巧妙闪躲/急速披挂，且丢类型标注），28 个 100% 丢失。

详情区标题形态族：
  T1 `**中文（EN）****（类型）****`    ** 前缀 + 4星漂移 + 类型（26 个，L83 等）
  T2 `中文****EN****（类型）****`      无 ** 前缀（1 个，L94 环形杀法）
  T3 `中文****EN`                      行尾断裂无类型，正文在下一行（3 个，
                                        L298 擒抱施法 / L314 睁一只眼 / L325 反应式奥能之盾）

修复（改源数据不改脚本，对齐 KN035 先例 d8f638f）：
  T1/T2 → FC-1q `**中文（EN）（类型）**`
  T3    → FC-1n `**中文（EN）**`（下行正文原样）
  表格区/正文行不动；星数一律 "\\\\*" * 4 显式拼接防手数错位；
  行尾字节级保留（详情区裸 LF 主流行尾，修改行沿用原行行尾）

用法：python3 fix_feat_page555.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长/page_555.md"

# 英文名字符类（含反引号保险——Marksman`s 风格源数据）
RE_EN = r"[A-Za-z][A-Za-z'\-., `]*?"

# T1：**中文（EN）** + 4星 + （类型） + 4星（行尾）
RE_T1 = re.compile(r"^\*\*([一-鿿]{2,15})（(" + RE_EN + r")）" + "\\*" * 4
                   + r"（([一-鿿A-Za-z ，、]+)）" + "\\*" * 4 + r"$")
# T2：中文 + 4星 + EN + 4星 + （类型） + 4星（行尾，无 ** 前缀）
RE_T2 = re.compile(r"^([一-鿿]{2,15})" + "\\*" * 4 + r"(" + RE_EN + r")"
                   + "\\*" * 4 + r"（([一-鿿A-Za-z ，、]+)）" + "\\*" * 4 + r"$")
# T3：中文 + 4星 + EN（行尾断裂，正文在下一行）
RE_T3 = re.compile(r"^([一-鿿]{2,15})" + "\\*" * 4 + r"(" + RE_EN + r")$")


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
    assert n == 342, f"预期 342 行，实际 {n} 行——行号假设失效，中止"
    assert lines[82][0].startswith("**巧妙闪躲（Artful Dodge）****"), \
        f"L83 非详情区首行：{lines[82][0][:40]!r}"

    # 标题特征行：** 前缀中文 或 中文+4星（详情区标题形态；正文/字段行天然不匹配）
    RE_TITLEISH = re.compile(r"^(\*\*)?[一-鿿]{2,15}(" + "\\*" * 4 + r"|（)")

    fixed = 0
    report: list[str] = []
    unmatched: list[int] = []

    for i in range(82, n):  # 仅详情区（L83 起）
        text, cr = lines[i]
        st = text.strip()
        if not st:
            continue
        m1 = RE_T1.match(st)
        m2 = RE_T2.match(st)
        m3 = RE_T3.match(st)
        if m1:
            new = f"**{m1.group(1)}（{m1.group(2).strip()}）（{m1.group(3)}）**"
        elif m2:
            new = f"**{m2.group(1)}（{m2.group(2).strip()}）（{m2.group(3)}）**"
        elif m3:
            new = f"**{m3.group(1)}（{m3.group(2).strip()}）**"
        else:
            # 只有标题特征行未匹配才算问题（防正文行误报）
            if RE_TITLEISH.match(st):
                unmatched.append(i + 1)
            continue
        lines[i] = (new, cr)
        fixed += 1
        report.append(f"L{i+1}: {st[:44]} -> {new}")

    if unmatched:
        print("未匹配的标题特征行：", unmatched[:20])
        return 1

    out_bytes = join_lines(lines)
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
          f"| 总行数: {n} -> {len(lines)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
