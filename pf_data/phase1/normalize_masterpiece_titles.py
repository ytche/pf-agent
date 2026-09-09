#!/usr/bin/env python3
"""V004: 归一化吟游诗人传世名作的源文件标题。

策略：剥离所有 ** 装饰后，严格匹配 cn（English）【ABBR】 模式：
  - cn: 2-10 个汉字（masterpiece 名长度区间）
  - (English): 英文，首字母
  - 【ABBR】: 来源书缩写（同行必须有闭合 】）

不匹配的正文/段落原样保留。
"""
import re
import sys
from pathlib import Path

TARGETS = [
    "pf_rules_md_organized/职业/核心职业/吟游诗人/传世名作汇总.md",
]

# 严格标题模式：cn（English）【ABBR】...
# 剥离 ** 之后才能匹配，所以允许 cn 是干净的 2-10 个汉字
# 匹配源文件中已有的【ABBR】 或 [ABBR]，归一化为 [ABBR] 以避免被脚本识别为变体标题
TITLE_RE = re.compile(
    r'^([一-鿿/]{2,15})\s*[（(]([A-Za-z][A-Za-z0-9\s\',.!?&\-:]+?)[）)]\s*[【\[]([A-Za-z0-9\s&\']+)[】\]][ \t]*(.*)$'
)

# 折叠前的 master piece 标题识别（用于在第一首前插入章节标题）
MASTERPIECE_FOLDED_RE = re.compile(
    r'^\*{2,}([一-鿿/]+?)\*{2,}\s*[（(]'
)

# 源书标签剥离 ** 后: [Blood of Angels]
SOURCE_BOOK_RE = re.compile(r'^\[([^\]]+)\]\s*$')


def fold_wrapped_lines(lines: list[str]) -> list[str]:
    """折叠 wrap：行末是空白/特定标点（空格、&、'、- 等），下一行以 ASCII 字母开头。

    用于合并被换行切断的英文标题（如 "At the Heart of It \\n All"）和
    缩写（如 "【M's\\nM】"）。
    """
    FOLD_END_CHARS = (' ', '\t', "'", '&', '-', ',')
    result: list[str] = []
    i = 0
    while i < len(lines):
        current = lines[i]
        if current.endswith('\r\n'):
            content = current[:-2]
            ending = '\r\n'
        elif current.endswith('\n'):
            content = current[:-1]
            ending = '\n'
        else:
            content = current
            ending = ''

        # 空行不折叠
        if not content.strip():
            result.append(current)
            i += 1
            continue

        # 当前行末尾是空白/特定标点，且下一行以字母开头则折叠
        while i + 1 < len(lines) and content.endswith(FOLD_END_CHARS):
            next_line = lines[i + 1]
            if not next_line.strip():
                break
            next_stripped = next_line.lstrip()
            if not next_stripped or not next_stripped[0].isascii() or not next_stripped[0].isalpha():
                break
            if next_stripped.startswith(('#', '<!--', '|', '>')):
                break
            content = content.rstrip() + ' ' + next_stripped.rstrip('\r\n')
            ending = ''
            i += 1

        result.append(content + ending)
        i += 1
    return result


def strip_intro_bold_labels(lines: list[str]) -> list[str]:
    """剥离 intro 章节里的 **字段标签** 加粗（防止被 promote_inline_ability_headings 误识别为标题）。

    intro 章节指第一个 `## 传世名作（Bardic Masterpieces）` heading 之前的部分。
    把 `**字段名**：` 这种 inline 标签的 `**` 去掉，避免脚本将其提升为 `## 字段名`。
    """
    intro_end = None
    for i, l in enumerate(lines):
        if l.lstrip().startswith('## 传世名作'):
            intro_end = i
            break
    if intro_end is None:
        return lines
    intro = lines[:intro_end]
    rest = lines[intro_end:]

    # 只剥离短标签 **X**（X ≤ 8 字符，非空格），保留其它内容
    cleaned_intro = []
    for line in intro:
        # 匹配 **Word** 短标签（Word 不含空格且 ≤ 8 字符）
        new_line = re.sub(r'\*\*(\S{1,8})\*\*', r'\1', line)
        cleaned_intro.append(new_line)
    return cleaned_intro + rest


def normalize_line(line: str) -> str:
    """剥离 ** 装饰后尝试匹配标题/源书标签；都不匹配则原样保留（去除整行加粗的注释）。"""
    # 已是 ## 标题
    if line.lstrip().startswith('## '):
        return line

    # 剥离所有 ** 装饰（汉字被 ** 包裹的情况）
    stripped = line.replace('**', '')

    # 源书标签
    if SOURCE_BOOK_RE.match(stripped.rstrip('\r\n')):
        return stripped

    # masterpiece 标题
    m = TITLE_RE.match(stripped.rstrip('\r\n'))
    if m:
        cn = m.group(1)
        en = m.group(2).strip()
        abbr = m.group(3)
        # 只保留来源书缩写 [ABBR]，丢弃其余元数据标记（如 [PFS]、[核心]、[玩家伴侣] 等）
        # 这些元数据不在脚本的书缩写表中，会被错误用作 book_abbreviation
        return f'## {cn}（{en}）[{abbr}]\n'

    # 整行加粗但不是标题的注释（如编辑说明）→ 去掉 ** 防止被 promote_bold_headings 误提升
    s = line.rstrip('\r\n')
    if s.startswith('**') and s.endswith('**') and len(s) > 4 and '（' not in stripped and '[' not in stripped:
        return stripped + ('\n' if line.endswith('\n') else '')

    return line


def truncate_appendix(lines: list[str]) -> list[str]:
    """删除 HH/EMH 重复附录块。"""
    cut_idx: int | None = None
    for i, line in enumerate(lines):
        if line.lstrip().startswith('<!--'):
            cut_idx = i
            break
    if cut_idx is None:
        return lines
    for i in range(cut_idx - 1, -1, -1):
        if lines[i].strip() == '':
            return lines[:i]
    return lines[:cut_idx]


def process_file(path: Path) -> tuple[int, int]:
    text = path.read_text(encoding='utf-8')
    raw_lines = text.splitlines(keepends=True)
    folded = fold_wrapped_lines(raw_lines)

    # 在第一首传世名作标题前插入 `## 传世名作（Bardic Masterpieces）` 章节标题
    # 这样下游脚本的 split_into_blocks 会把它当作 section heading，
    # 让后续 masterpiece chunks 的 breadcrumbs 包含 "传世名作"。
    inserted = False
    for i, l in enumerate(folded):
        m = MASTERPIECE_FOLDED_RE.match(l)
        if m:
            folded = folded[:i] + ['## 传世名作（Bardic Masterpieces）\n', '\n'] + folded[i:]
            inserted = True
            break
    if not inserted:
        # 也尝试在 strip 后再插（处理未匹配的情况）
        stripped_intro_fallback = strip_intro_bold_labels(folded)
        normalized_fallback = [normalize_line(line) for line in stripped_intro_fallback]
        truncated_fallback = truncate_appendix(normalized_fallback)
        changed = sum(1 for a, b in zip(raw_lines, truncated_fallback) if a != b) + abs(len(truncated_fallback) - len(raw_lines))
        path.write_text(''.join(truncated_fallback), encoding='utf-8')
        return changed, len(raw_lines)

    stripped_intro = strip_intro_bold_labels(folded)
    normalized = [normalize_line(line) for line in stripped_intro]
    truncated = truncate_appendix(normalized)
    changed = sum(1 for a, b in zip(raw_lines, truncated) if a != b) + abs(len(truncated) - len(raw_lines))
    path.write_text(''.join(truncated), encoding='utf-8')
    return changed, len(raw_lines)


def main() -> int:
    base = Path(__file__).parent
    total_changed = 0
    for rel_path in TARGETS:
        full_path = base / rel_path
        if not full_path.exists():
            print(f"SKIP: {rel_path} not found")
            continue
        changed, total = process_file(full_path)
        total_changed += changed
        print(f"  {rel_path}: {changed} 处改动（共 {total} 行）")
    print(f"\n总计 {total_changed} 处改动")
    return 0


if __name__ == "__main__":
    sys.exit(main())