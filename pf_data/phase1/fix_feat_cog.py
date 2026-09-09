"""
fix_feat_cog.py — 格拉里昂的城市CoG 5 专长「标题+描述 5 星粘连」源数据归一（P0 级，est=7 got=2 丢 5）

背景（2026-08-02 审计发现，P0 级）：格拉里昂的城市CoG 是专长10 的 K3 聚合
文件（`<!-- …-source:专长10.md:__aggregate__ -->`），7 个真实专长。前 2 个
（不屈坐骑/回转冲锋）standard 闭合标题已产出；后 5 个（塔尔多的私掠船员/
深隧专家/忍受痛苦/骑乘猛攻/伊利森冰霜法师）标题跨行（EN 拆词）+ 闭合后
**5 星粘连描述**（`Taldor）*****许多追求…*`）+ 字段行左星残缺同行粘连
（`先决条件**：值**专长效果**：值`），normalize 的 elided 处理把标题变成
双括号畸形（`（（Master Delver））`）且吞描述前星，split 无法识别，5 个
专长 100% 丢失。

形态族（每块 3 行）：
  L25  `**塔尔多的私掠船员（Corsair of `          （标题前缀，EN 拆词跨行）
  L26  `Taldor）*****许多追求…声誉。*`              （EN 后半 + 5 星 + 描述）
  L27  `先决条件**：…1个月。**专长效果**：…伤害。`  （字段同行，左星残缺）

修复（改源数据不改脚本，对齐 KN046 b70f774 锚点法先例）：
  - 每块 3 行合并 → 拆 4 行：`**中文（EN）**` 标题 + `*描述*` 行 +
    `**先决条件**：值` 行 + `**专长效果**：值` 行（partition 切字段）
  - 标题 = 前缀 + EN 后半（`）` 前）；描述 = 5 星后内容（保留原有后星）
  - 全裸 LF 文件（CRLF 0）；L1-L24/L48-L49 继承行字节级原样保留
  - 断言 n==49 + 5 前缀行 + 每块 3 行 + 字段行含 `**专长效果**：`

修复后：5 + 2 = 7 = est=7 精确匹配，verify 不再 WARN。

用法：python3 fix_feat_cog.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长/格拉里昂的城市CoG_专长.md"

# 5 个专长块（前缀行起始文本 → 解析用）：(前缀, EN 后半锚定)
BLOCKS = [
    ("**塔尔多的私掠船员（Corsair of ", "Taldor）"),
    ("**深隧专家（Master ", "Delver）"),
    ("**忍受痛苦（宗-库松之吻）（Endure Pain (Zon-Kuthon's ", "Kiss)）"),
    ("**骑乘猛攻（Mounted ", "Onslaught）（战斗）"),
    ("**伊利森冰霜法师（Irrisen ", "Icemage）（战斗）"),
]
# 续行：EN 后半 + `*****` + 描述（描述保留原有后星）
RE_CONT = re.compile(r"^(.+?）)（?\*{5}(.+)$")


def main() -> int:
    raw = open(PATH, "rb").read()
    lines = raw.split(b"\n")
    n = len(lines)
    assert n == 49, f"预期 49 行，实际 {n} 行——行号假设失效，中止"
    assert not any(l.endswith(b"\r") for l in lines), "文件含 CRLF，中止"

    # 定位 5 块（前缀行索引）
    idxs: list[int] = []
    for prefix, _ in BLOCKS:
        idxs.append(next(i for i, l in enumerate(lines)
                         if l.decode("utf-8").startswith(prefix)))
    assert idxs == sorted(idxs), "块顺序异常"
    for i, (prefix, _) in zip(idxs, BLOCKS):
        assert lines[i].decode("utf-8") == prefix.strip("\n"), \
            f"L{i+1} 非精确前缀：{lines[i][:40]!r}"

    out: list[bytes] = []
    fixed = 0
    report: list[str] = []

    # ---- L1 到第一个块前 原样保留 ----
    out.extend(lines[: idxs[0]])

    for bi, (i, (prefix, en_tail)) in enumerate(zip(idxs, BLOCKS)):
        assert i + 2 < n, f"块 {bi} 行数不足"
        cont = lines[i + 1].decode("utf-8")
        fields = lines[i + 2].decode("utf-8")

        # 标题 = 前缀中文部分 + EN 后半（闭合 `）` 前）
        title = prefix + cont[: cont.index("）") + 1]
        # 描述：`*****` 后内容（`*…*` 后星原样）
        m = RE_CONT.match(cont)
        assert m, f"块 {bi} 续行解析失败：{cont[:60]!r}"
        assert m.group(1) == en_tail, f"块 {bi} EN 后半失配：{m.group(1)!r}"
        desc = m.group(2)
        assert desc.startswith("*") or desc.endswith("*"), \
            f"块 {bi} 描述星缺失：{desc[:40]!r}"

        # 字段行：先决条件**：值 **专长效果**：值
        pre, sep, eff = fields.partition("**专长效果**：")
        assert sep and eff, f"块 {bi} 字段行缺专长效果"
        assert pre.startswith("先决条件**："), f"块 {bi} 字段行缺先决条件"
        pre_val = pre[len("先决条件**："):]

        out.append(f"{title}**".encode("utf-8"))
        out.append(f"*{desc}".encode("utf-8"))
        out.append(f"**先决条件**：{pre_val}".encode("utf-8"))
        out.append(f"**专长效果**：{eff}".encode("utf-8"))
        fixed += 1
        report.append(f"#{bi+1}: {title[2:]} 拆 4 行")

        # ---- 块间继承行（空行）原样保留；最后一块后保留尾部 ----
        next_i = idxs[bi + 1] if bi + 1 < len(idxs) else None
        out.extend(lines[i + 3: next_i if next_i is not None else n])

    out_bytes = b"\n".join(out)
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证：继承行全等 ----
    # 块前无偏移可直接比较；块后用字节后缀比较（各块 3→4 行产生行偏移，
    # 直接按索引切片会错位——append 的继承行必然位于 out 尾部）
    assert new_lines[: idxs[0]] == lines[: idxs[0]], "块前继承行被改动，中止"
    tail = b"\n".join(lines[idxs[-1] + 3:])
    assert out_bytes.endswith(tail), "块后继承行被改动，中止"

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
