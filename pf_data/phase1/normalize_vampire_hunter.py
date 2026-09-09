#!/usr/bin/env python3
"""V006 Phase B: 归一化吸血鬼猎人源文件，加 ## 标题使每个技能独立成 chunk。

问题：page_1209.md/page_1210.md 的每个汉字被 ** 包裹（**武**器**与**防**具
**擅**长**（Weapon and Armor Proficiency）**），且多个能力名挤在同一行。
promote_bold_headings 无法正确处理 → 4 个 chunk 应拆为 20+。

策略（与 V004 normalize_masterpiece_titles.py 相同）：
1. 备份
2. 剥离所有 ** 装饰 → 得到纯文本
3. 用正则识别 cn（English，tag）模式 → 在每个能力名前断行加 ## 标题
4. 处理能力名后的冒号（**能力名**：正文 → ## 能力名\\n正文）
"""
import re
import shutil
from pathlib import Path

BASE = Path(__file__).parent / "pf_rules_md_organized" / "职业" / "其他职业" / "吸血鬼猎人"
TARGETS = [
    BASE / "page_1209.md",
    BASE / "page_1210.md",
]

# 匹配剥离 ** 后的能力名：cn（English，tag）
ABILITY_TITLE_RE = re.compile(
    r'([一-鿿]{2,}?（[A-Za-z][A-Za-z\s,]*?（?:Ex|Su|Sp）?）)\s*[：:]\s*'
)


def process_file(path: Path) -> int:
    if not path.exists():
        print(f"  跳过: {path} 不存在")
        return 0

    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        shutil.copy2(path, bak)

    text = path.read_text(encoding="utf-8")
    # 先剥离所有 ** → 得到干净的纯文本
    clean = text.replace("**", "")
    lines = clean.splitlines(keepends=True)
    new_lines: list[str] = []
    changed = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            new_lines.append(line)
            continue

        # 保留已有 ## 标题、表格、引用
        if stripped.startswith(("#", "|", ">")):
            new_lines.append(line)
            continue

        # 查找行内的能力名模式
        parts = ABILITY_TITLE_RE.split(stripped)
        if len(parts) > 1:
            # parts 结构: [before, ability1, after1, ability2, after2, ...]
            # 交替出现：正文/能力名/正文/能力名/正文
            for i, part in enumerate(parts):
                if not part:
                    continue
                is_ability = False
                if ABILITY_TITLE_RE.fullmatch(part):
                    is_ability = True
                elif i > 0 and ABILITY_TITLE_RE.match(part):
                    is_ability = True
                if is_ability:
                    new_lines.append(f"## {part}\n")
                    changed += 1
                else:
                    new_lines.append(f"{part}\n")
        else:
            new_lines.append(line)

    path.write_text("".join(new_lines), encoding="utf-8")
    print(f"  {path.name}: {changed} 处 ## 标题（原 {len(lines)} 行）")
    return changed


def main():
    total = 0
    for target in TARGETS:
        n = process_file(target)
        total += n
    print(f"\n总计 {total} 处能力名标题")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
