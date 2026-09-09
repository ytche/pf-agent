"""
fix_feat_weapon_master.py — 武器大师手册_专长.md 标题形态归一（P0 级，est=85 got=20）

背景（2026-08-02 KN036 后继续审计）：判别器 est=85（FC-6c 49 + FC-8c 16 +
FC-1n 10 + FC-8e 7 + 零星）但当前产出仅 20 — 65 个真专长丢失。文件全部
裸 LF 行尾。条目标题 RE2 漂移形态（无行首 `**` 包裹）：

  A  同行四星（~29）：`中文 EN****（类型）****   *描述*`（法切无类型变体）
      → `**中文（EN）（类型）**` + 描述行原样
  B  跨行拆词（~65）：`中文 EN片段 `（尾空格）+ 下行
      `EN片段****（类型）****   *描述*`（英文名跨行拆段）
      → 合并 `**中文（EN片段 EN片段）（类型）**` + 描述行原样
      B1 特例（L68 武道专家）：下行 `****（类型）**` 纯 4 星+类型闭合
  C  神祇跨行（~8）：`**中文（EN片段 ` + 下行 `EN片段）**`（标准 RE2 断裂）
      → 合并 `**中文（EN片段 EN片段）**`
  D  技法 3 行断裂（~3）：`**中文（**` + 英文行（来源行插中间）+ `EN****）**`
      → 合并 `**中文（EN）**`；粘连正文（`****）****正文`）拆出正文行
  E  字段行开星漂移：`先决条件：**` / `先决条件**：` → `**先决条件：**`
      （R2 字段标签 opens 缺失变体）

修复原则（对齐 page_321/KN035、page_670/KN036 先例）：
  - 改源数据不改脚本：归一为 pipeline 已支持标准形态（FC-1n/FC-1q）
  - 材质条目（`*炼银（Alchemical` 等斜体段，非专长）不动——判别器 FC-8e
    误数，est 虚高部分随修复后 got≥est 自然无 WARN
  - 描述/正文/字段行一律原样保留（RE_CROSS_EN/字段解析等既有机制负责）
  - 行尾：全文件裸 LF，输出保持裸 LF

用法：python3 fix_feat_weapon_master.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长/武器大师手册_专长.md"

# 英文名字符类（含反引号 `——Marksman`s / Gorum`s 等源数据用反引号替代撇号）。
# 必须带捕获括号：各正则按 group 序号取 EN 续段
RE_EN = r"([A-Za-z][A-Za-z\'\-., \`]*?)"

# A 同行四星：中文 EN****（类型）****   *描述* / 中文 EN****   *描述*
# 原文星序：EN 后第一个 ****，类型括号（若有）后第二个 ****——`\*\*\*\*\s*`
# 匹配「4 星 + （」的粘连，类型组须在 4 星之后。
# 类型组整体可选项：无类型时前缀 `\s*` 已消费 4 星后的空格，直接进描述行；
# 有类型时 `\s*` 吃 0 空格、组内 `（类型）****` 消费第二组 4 星 + 空格。
# （早版本把「无类型」写成 `|\*\*\*\*\s{2,3}` 分支——前缀已消费唯一 4 星，
# 该分支再要求 4 星永远失败，导致法切等无类型条目漏匹配。）
RE_A = re.compile(
    r"^([一-鿿（）]{2,15}?) " + RE_EN + r"\*\*\*\*\s*"
    r"(?:（([一-鿿A-Za-z ，、]+)）\*\*\*\*\s{2,3})?(\*.*)$"
)
# B 跨行标题行（可带缩进 + 尾空格；缩进源为进阶武器训练条目；
# 可选前置 4 星漂移——L1066 `  ****一人成军 Fighter`s `）
RE_B_TITLE = re.compile(r"^\s*(?:\*\*\*\*)?([一-鿿（）]{2,15}?) " + RE_EN + r" $")
# B 下行：EN****（类型）****   *描述*（英文名续段，类型组可无——B 无类型变体）
RE_B_NEXT1 = re.compile(
    r"^" + RE_EN + r"\*\*\*\*\s*(?:（([一-鿿A-Za-z ，、]+)）\*\*\*\*\s{2,3})?(\*.*)$"
)
# B1 下行：****（类型）**（L68 武道专家，无描述）
RE_B_NEXT2 = re.compile(r"^\*\*\*\*\s*（([一-鿿A-Za-z ，、]+)）\*\*$")
# B2 下行：EN****（类型****）：**正文（进阶武器训练：4 星 + （类型 + 4 星 + ）：**）
RE_B_NEXT3 = re.compile(
    r"^" + RE_EN + r"\*\*\*\*\（([一-鿿A-Za-z ，、]+?)" + "\\*" * 4 + r"\）：\*\*(.*)$"
)
# B4 下行：EN****（纯 4 星闭合，无正文——L411 节标题 Feat****）
RE_B_NEXT4 = re.compile(r"^" + RE_EN + r"\*\*\*\*$")
# B5 下行：EN****：**正文（4 星 + ：** + 正文，无类型——L1174 武器掌握）
RE_B_NEXT5 = re.compile(r"^" + RE_EN + r"\*\*\*\*\：\*\*(.*)$")
# C 神祇跨行：**中文（EN片段 （尾空格）
RE_C_TITLE = re.compile(r"^(\*\*[一-鿿]{2,15}（[A-Za-z][A-Za-z\'\-., \`]*?) $")
RE_C_NEXT = re.compile(r"^([A-Za-z\'\-., \`]*?)）\*\*$")
# C2 同行无类型：中文（EN****）：**正文（FC-1n 断裂：括号在中文后）
RE_C2A = re.compile(
    r"^([一-鿿]{2,10})（" + RE_EN + r"\*\*\*\*\）：\*\*(.*)$"
)
# C2 同行带类型：中文 英文****（类型****）：**正文（FC-1q 断裂：括号在英文后）
RE_C2B = re.compile(
    r"^\s*([一-鿿]{2,10}) " + RE_EN + r"\*\*\*\*\（([一-鿿A-Za-z ，、]+?)"
    + "\\*" * 4 + r"\）：\*\*(.*)$"
)
# C2 跨行：中文（EN片段 （尾空格，无 ** 前缀——RE2 漂移吞了开星）
RE_C2C_TITLE = re.compile(r"^\s*([一-鿿]{2,10})（" + RE_EN + r" $")
RE_C2C_NEXT = re.compile(r"^" + RE_EN + r"\*\*\*\*\）：\*\*(.*)$")
# L253 特例：牙突．****零 Outslug ——4 星替代了 `（`（FC-1n 开括号被漂移替换）
RE_WEIRD = re.compile(r"^([一-鿿]{2,10}．)" + "\\*" * 4 + r"([一-鿿]{1,6}) " + RE_EN + r" $")
# D 技法 3 行断裂：**中文（**
RE_D1 = re.compile(r"^\*\*[一-鿿]{2,15}（\*\*$")
RE_D2 = re.compile(r"^([A-Za-z][A-Za-z\'\-., \`]*?) $")
RE_D3 = re.compile(r"^([A-Za-z][A-Za-z\'\-., \`]*?)\*\*\*\*\）\*\*$")
# D3B 粘连正文变体：EN****）****正文——4 星 + ） + 4 星 + 正文。
# 星数以 "\\*" * N 显式拼接，避免字面量手数星数错位（4 星写成 3/5 星）。
RE_D3B = re.compile(
    r"^([A-Za-z][A-Za-z\'\-., \`]*?)" + "\\*" * 4 + r"\）" + "\\*" * 4 + r"(.*)$"
)
# E 字段行开星漂移：行首中文标签（2-10 字）+（：** 或 **：）缺开星
# 变体：先决条件：** / 先决条件**： / 进阶先决条件：** / 可选替换能力：**
#      / 基础奖励：** / 进阶奖励：**——归一为 **标签：**（R2 可识别闭合形态）
RE_E = re.compile(r"^([一-鿿]{2,10})([：:]\*\*|\*\*[：:])")


def main() -> int:
    raw = open(PATH, "rb").read()
    text = raw.decode("utf-8", "ignore")
    lines = text.split("\n")
    out: list[str] = []
    report: list[str] = []
    fixed = 0
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]

        # B 跨行拆词：标题行 + 下行英文续段（跳过来源/注释行）
        m = RE_B_TITLE.match(line)
        if m:
            j = i + 1
            while j < n and (lines[j].strip().startswith(("> 来源", "<!--")) or not lines[j].strip()):
                j += 1
            if j < n:
                nxt = lines[j].strip()
                m1 = RE_B_NEXT1.match(nxt)
                if m1:
                    typ = f"（{m1.group(2)}）" if m1.group(2) else ""
                    out.append(f"**{m.group(1)}（{m.group(2)} {m1.group(1)}）{typ}**")
                    out.append(m1.group(3))
                    report.append(f"L{i+1}-L{j+1}: B 合并 {m.group(1)}（{m.group(2)} {m1.group(1)}）{typ}")
                    fixed += 1
                    i = j + 1
                    continue
                m3 = RE_B_NEXT3.match(nxt)
                if m3:
                    # 进阶武器训练：EN****（类型****）：**正文
                    out.append(f"**{m.group(1)}（{m.group(2)} {m3.group(1)}）（{m3.group(2)}）**")
                    out.append(m3.group(3))
                    report.append(f"L{i+1}-L{j+1}: B3 合并 {m.group(1)}（{m.group(2)} {m3.group(1)}）（{m3.group(2)}）")
                    fixed += 1
                    i = j + 1
                    continue
                m2 = RE_B_NEXT2.match(nxt)
                if m2:
                    out.append(f"**{m.group(1)}（{m.group(2)}）（{m2.group(1)}）**")
                    report.append(f"L{i+1}-L{j+1}: B1 合并 {m.group(1)}（{m.group(2)}）（{m2.group(1)}）")
                    fixed += 1
                    i = j + 1
                    continue
                m4 = RE_B_NEXT4.match(nxt)
                if m4:
                    # 节标题闭合行：EN**** → **中文（EN）**
                    out.append(f"**{m.group(1)}（{m.group(2)} {m4.group(1)}）**")
                    report.append(f"L{i+1}-L{j+1}: B4 合并 {m.group(1)}（{m.group(2)} {m4.group(1)}）")
                    fixed += 1
                    i = j + 1
                    continue
                m5 = RE_B_NEXT5.match(nxt)
                if m5:
                    # 无类型：EN****：**正文
                    out.append(f"**{m.group(1)}（{m.group(2)} {m5.group(1)}）**")
                    out.append(m5.group(2))
                    report.append(f"L{i+1}-L{j+1}: B5 合并 {m.group(1)}（{m.group(2)} {m5.group(1)}）")
                    fixed += 1
                    i = j + 1
                    continue

        # C2 跨行：中文（EN片段 （无 ** 前缀，RE2 漂移吞了开星）+ 下行 EN片段****）：**正文
        m = RE_C2C_TITLE.match(line)
        if m:
            j = i + 1
            while j < n and (lines[j].strip().startswith(("> 来源", "<!--")) or not lines[j].strip()):
                j += 1
            if j < n:
                mc = RE_C2C_NEXT.match(lines[j].strip())
                if mc:
                    out.append(f"**{m.group(1)}（{m.group(2)} {mc.group(1)}）**")
                    out.append(mc.group(2))
                    report.append(f"L{i+1}-L{j+1}: C2 跨行合并 {m.group(1)}（{m.group(2)} {mc.group(1)}）")
                    fixed += 1
                    i = j + 1
                    continue

        # C2 同行无类型：中文（EN****）：**正文
        m = RE_C2A.match(line)
        if m:
            out.append(f"**{m.group(1)}（{m.group(2)}）**")
            out.append(m.group(3))
            report.append(f"L{i+1}: C2 同行 -> **{m.group(1)}（{m.group(2)}）**")
            fixed += 1
            i += 1
            continue

        # C2 同行带类型：中文 英文****（类型****）：**正文（进阶武器训练同行变体）
        m = RE_C2B.match(line)
        if m:
            out.append(f"**{m.group(1)}（{m.group(2)}）（{m.group(3)}）**")
            out.append(m.group(4))
            report.append(f"L{i+1}: C2B 同行 -> **{m.group(1)}（{m.group(2)}）（{m.group(3)}）**")
            fixed += 1
            i += 1
            continue

        # L253 特例：牙突．****零 Outslug （4 星替代了开括号）+ 下行 B 型续段
        m = RE_WEIRD.match(line)
        if m:
            j = i + 1
            while j < n and (lines[j].strip().startswith(("> 来源", "<!--")) or not lines[j].strip()):
                j += 1
            if j < n:
                m1 = RE_B_NEXT1.match(lines[j].strip())
                if m1:
                    typ = f"（{m1.group(2)}）" if m1.group(2) else ""
                    out.append(f"**{m.group(1)}{m.group(2)}（{m.group(3)} {m1.group(1)}）{typ}**")
                    out.append(m1.group(3))
                    report.append(f"L{i+1}-L{j+1}: 特例合并 {m.group(1)}{m.group(2)}（{m.group(3)} {m1.group(1)}）{typ}")
                    fixed += 1
                    i = j + 1
                    continue

        # C 神祇跨行：**中文（EN片段  + 下行 EN片段）**
        m = RE_C_TITLE.match(line)
        if m:
            j = i + 1
            while j < n and (lines[j].strip().startswith(("> 来源", "<!--")) or not lines[j].strip()):
                j += 1
            if j < n:
                m2 = RE_C_NEXT.match(lines[j].strip())
                if m2:
                    out.append(f"{m.group(1)} {m2.group(1)}）**".replace(" ）", "）"))
                    report.append(f"L{i+1}-L{j+1}: C 合并 {m.group(1)[:30]}...")
                    fixed += 1
                    i = j + 1
                    continue

        # D 技法 3 行断裂：**中文（** + 英文行 + EN****）**（**粘连正文）
        if RE_D1.match(line):
            j = i + 1
            while j < n and (lines[j].strip().startswith(("> 来源", "<!--")) or not lines[j].strip()):
                j += 1
            if j < n and RE_D2.match(lines[j]):
                k = j + 1
                while k < n and (lines[k].strip().startswith(("> 来源", "<!--")) or not lines[k].strip()):
                    k += 1
                if k < n:
                    # line 为 `**中文（**` 形态，[2:-2] 残留尾部 `（`——rstrip 防括号重复
                    cn = line[2:-2].rstrip("（")
                    md3 = RE_D3B.match(lines[k].strip())
                    if md3:
                        out.append(f"**{cn}（{lines[j].strip()} {md3.group(1)}）**")
                        if md3.group(2):
                            out.append(md3.group(2))
                        report.append(f"L{i+1}-L{k+1}: D 合并 {line}...")
                        fixed += 1
                        i = k + 1
                        continue
                    md3 = RE_D3.match(lines[k].strip())
                    if md3:
                        out.append(f"**{cn}（{lines[j].strip()} {md3.group(1)}）**")
                        report.append(f"L{i+1}-L{k+1}: D 合并 {line}...")
                        fixed += 1
                        i = k + 1
                        continue
            elif j < n:
                # 无英文行变体（L669：**专长（** + Feats****）**）——直接试闭合行
                cn = line[2:-2].rstrip("（")
                md3 = RE_D3B.match(lines[j].strip())
                if md3:
                    out.append(f"**{cn}（{md3.group(1)}）**")
                    if md3.group(2):
                        out.append(md3.group(2))
                    report.append(f"L{i+1}-L{j+1}: D 无英文行合并 {line}...")
                    fixed += 1
                    i = j + 1
                    continue
                md3 = RE_D3.match(lines[j].strip())
                if md3:
                    out.append(f"**{cn}（{md3.group(1)}）**")
                    report.append(f"L{i+1}-L{j+1}: D 无英文行合并 {line}...")
                    fixed += 1
                    i = j + 1
                    continue

        # A 同行四星
        m = RE_A.match(line)
        if m:
            typ = f"（{m.group(3)}）" if m.group(3) else ""
            out.append(f"**{m.group(1)}（{m.group(2)}）{typ}**")
            out.append(m.group(4))
            report.append(f"L{i+1}: A 同行 -> **{m.group(1)}（{m.group(2)}）{typ}**")
            fixed += 1
            i += 1
            continue

        # E 字段行开星漂移：行首标签（2-10 字）+（：** 或 **：）→ **标签：**
        me = RE_E.match(line)
        if me:
            rest = line[me.end():]
            line = f"**{me.group(1)}：**" + rest
            report.append(f"L{i+1}: E 字段行补开星 -> {line[:30]}")
            fixed += 1

        out.append(line)
        i += 1

    out_bytes = "\n".join(out).encode("utf-8")
    if out_bytes == raw:
        print("无变更")
        return 1
    with open(PATH, "wb") as f:
        f.write(out_bytes)
    print(f"== {PATH}：修复 {fixed} 处")
    for r in report:
        print("   ", r)
    print(f"总行数: {n} -> {len(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
