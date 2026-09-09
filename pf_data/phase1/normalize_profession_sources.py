"""职业源文件归一化脚本（Phase D 辅助）

按 `HANDOVER_K2_7_PROFESSION_CHUNK_QUALITY.md` 的 Phase D 护栏，对
`pf_rules_md_organized/职业/` 下源文件进行**纯结构性**批量修复：

1. 把血统/领域等章节标题里的来源书 `【ABB】` 改为 `（ABB）`，避免被误判为变体；
2. 把 CRB 介绍页中带英文括号的章节标题改为“标题：English”形式（P7）；
3. 删除纯噪声行（URL、译者、返回目录，P5）；
4. 把与 heading 同行的 HTML 来源注释移到独立行（P4）。

说明：行内加粗变体标题当前不批量拆分，由 `vectorization_prep_profession.py` 的
`promote_inline_archetype_headings` 按需处理，避免破坏 class 推断与来源归因。

所有修改均可 `git diff` 审查；脚本报改动的文件清单与前后样例。
"""
import re
from pathlib import Path


BASE_DIR = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
INPUT_DIR = BASE_DIR / "pf_rules_md_organized" / "职业"

# 纯噪声行（与 vectorization_prep_profession.is_header_noise 保持一致）
NOISE_PATTERNS = [
    re.compile(r"^\s*https?://"),
    re.compile(r"^\s*!?\[.*?\]\(https?://[^)]+\)\s*$"),
    re.compile(r"^\s*(译者|翻译|整理者|编者|校对|编辑)[:：]"),
    re.compile(r"^\s*返回目录\s*$"),
]

# 通用变体标题（不应被拆分为独立标题）
GENERIC_TITLES = {
    "职业变体", "变体", "变体职业特性", "Class Archetypes",
    "Alternate Class Features", "Archetypes", "变体列表", "职业变体列表",
}

# 血统/领域等 feature 章节关键词（用于识别需要改来源括号的标题）
FEATURE_SECTION_KEYWORDS = ["血统", "血承", "领域", "巫术", "强力巫术", "高等巫术", "庇护主"]


def _detect_eol(text: str) -> str:
    """检测原始文件主要换行符，优先 CRLF，其次 CR，最后 LF。"""
    if "\r\n" in text:
        return "\r\n"
    if "\r" in text:
        return "\r"
    return "\n"


def _content_equal(a: str, b: str) -> bool:
    """忽略换行符差异比较两段文本内容是否相同。"""
    return a.replace("\r\n", "\n").replace("\r", "\n") == b.replace("\r\n", "\n").replace("\r", "\n")


def is_noise_line(line: str) -> bool:
    """判断是否为可删除的纯噪声行（兼容首尾加粗/斜体包裹）。"""
    s = line.strip()
    if not s:
        return False
    # 去掉首尾的 * 或 _ 格式标记后再匹配
    unstyled = re.sub(r"^(\*+|_+)", "", s)
    unstyled = re.sub(r"(\*+|_+)$", "", unstyled).strip()
    for pat in NOISE_PATTERNS:
        if pat.search(unstyled):
            return True
    return False


def _is_inline_variant_title(title: str) -> bool:
    """判断一个行内加粗标题是否应被拆分为独立变体标题。

    必须显式包含变体标记（中文〔/［/（/【 X变体 〕/］/）/】或英文 Archetype），
    且不能是通用章节名或能力标记（Ex/Su/Sp）。
    """
    plain = title.replace("*", "").strip()
    if not plain or plain in GENERIC_TITLES:
        return False
    # 含 Ex/Su/Sp 的是职业能力，不拆
    if re.search(r"\b(?:Ex|Su|Sp)\b", plain):
        return False
    # 中文变体标记
    if re.search(r"[〔［【（].{1,12}?变体[〕］】）]", plain):
        return True
    # 英文 Archetype / Alternate Class
    if re.search(r"\(\s*(?:[A-Za-z]+\s+)?[Aa]rchetype\s*\)", plain):
        return True
    if re.search(r"\b[Aa]lternate\s+Class\b", plain):
        return True
    return False


def split_inline_bold_variant_titles(lines: list[str]) -> list[str]:
    """拆分 `**title**body` 这种行内加粗标题。

    当前策略：暂不批量拆分。行内变体标题由 `vectorization_prep_profession.py` 的
    `promote_inline_archetype_headings` 在变体文件中按需处理；源文件级拆分容易
    破坏后续 class 推断与来源归因，收益/风险比不高。
    """
    return lines[:]


def normalize_feature_source_brackets(lines: list[str]) -> list[str]:
    """把血统/领域/巫术等 feature 标题里的来源书 `【ABB】` 改为 `（ABB）`。

    这样标题不再命中 `looks_like_archetype_title` 的 pattern 2，
    从而被归入 class_feature 而非 class_archetype。

    只处理本身是 heading 或整行加粗标题，且含有 feature 关键词的行；
    避免误改同文件内的职业变体标题，也避免改动正文中的能力描述。
    """
    out: list[str] = []
    for line in lines:
        s = line.rstrip("\r\n")
        stripped = s.strip()
        # markdown heading，或整行被 * 包裹的标题（如 **标题**）
        is_heading = bool(re.match(r"^#{1,6}\s+", stripped)) or bool(
            re.fullmatch(r"\*+[^*].*\*", stripped)
        )
        plain = s.replace("*", "").replace("#", "").strip()
        has_feature_kw = any(kw in plain for kw in FEATURE_SECTION_KEYWORDS)
        is_variant = "变体" in plain
        if is_heading and has_feature_kw and not is_variant:
            def _to_parens(m: re.Match) -> str:
                inner = m.group(1).replace("*", "").strip()
                return f"（{inner}）"
            line = re.sub(r"【([^】]+)】", _to_parens, line)
        out.append(line)
    return out


def fix_intro_section_titles(lines: list[str], rel_path: Path) -> list[str]:
    """对 CRB 介绍页/概述页中带英文括号的节标题，把 `标题（English）` 改成
    `标题：English`，避免被识别为变体。

    注意：只处理“纯中文标题 + 纯英文译名”形式，跳过 markdown 链接、URL、
    已经含有变体标记或 `:` 分隔的标题。
    """
    # 只处理根目录或明显是介绍/概述的文件
    name = rel_path.name.lower()
    if not (
        name in ("page_31.md", "page_32.md", "page_33.md", "page_862.md")
        or "介绍" in name
        or "概述" in name
    ):
        return lines

    # 匹配：**中文标题（English Title）**
    # English 部分只允许字母、空格、连字符、撇号、逗号、句点，避免命中 URL。
    title_pat = re.compile(
        r"^(\*+)(.+?)[（(]([A-Za-z][A-Za-z\s\-',\.]*[A-Za-z])[）)](\*+)$"
    )

    out: list[str] = []
    for line in lines:
        s = line.rstrip("\r\n")
        m = title_pat.match(s)
        if m:
            zh = m.group(2).strip()
            eng = m.group(3).strip()
            # 跳过 markdown 链接、已带 ':' 的标题、以及不像中文标题的内容
            if (
                "](" not in zh
                and ":" not in zh
                and re.search(r"[一-鿿]", zh)
                and "变体" not in zh
                and "Archetype" not in zh
            ):
                line = f"{m.group(1)}{zh}：{eng}{m.group(4)}"
        out.append(line)
    return out


def move_html_comments_to_own_line(lines: list[str]) -> list[str]:
    """把 `<!-- source -->## 标题` 拆成两行。"""
    out: list[str] = []
    pat = re.compile(r"^(\s*<!--\s*.+?-->\s*)(#{1,6}\s+.*)$")
    for line in lines:
        s = line.rstrip("\r\n")
        m = pat.match(s)
        if m:
            out.append(m.group(1).strip())
            out.append(m.group(2).strip())
        else:
            out.append(line)
    return out


def _split_lines_keep_eol(text: str) -> list[tuple[str, str]]:
    """把文本拆成行，保留每行原始换行符。

    返回 [(content_without_eol, eol), ...]，末行无换行符时 eol 为空串。
    """
    records: list[tuple[str, str]] = []
    for raw in text.splitlines(True):
        if raw.endswith("\r\n"):
            records.append((raw[:-2], "\r\n"))
        elif raw.endswith("\r"):
            records.append((raw[:-1], "\r"))
        elif raw.endswith("\n"):
            records.append((raw[:-1], "\n"))
        else:
            records.append((raw, ""))
    return records


def normalize_file(path: Path) -> tuple[list[tuple[str, str]], list[str], str]:
    """对单个文件应用全部归一化规则，返回 (行记录, 修改说明, 默认换行符)。"""
    # 以 binary-safe 方式读取，保留原始换行符
    text = path.read_text(encoding="utf-8", errors="ignore", newline="")
    rel_path = path.relative_to(INPUT_DIR)

    default_eol = _detect_eol(text)
    records = _split_lines_keep_eol(text)
    changes: list[str] = []

    # 1. 删除纯噪声行
    cleaned = [rec for rec in records if not is_noise_line(rec[0])]
    if len(cleaned) != len(records):
        changes.append(f"删除 {len(records)-len(cleaned)} 行纯噪声")
        records = cleaned

    # 辅助：对保持行数不变的变换，保留每行原始换行符
    def _apply_same_count(fn):
        nonlocal records, changes
        contents = [c for c, _ in records]
        new_contents = fn(contents)
        if new_contents != contents:
            records = [(nc, eol) for nc, (_, eol) in zip(new_contents, records)]
            return True
        return False

    # 2. 拆分 inline 加粗标题（当前策略为 no-op）
    if _apply_same_count(split_inline_bold_variant_titles):
        changes.append("拆分行内加粗变体标题")

    # 3. 规范化 feature 章节来源括号
    if _apply_same_count(normalize_feature_source_brackets):
        changes.append("血统/领域等章节来源括号规范化")

    # 4. 介绍页节标题去英文括号
    if _apply_same_count(lambda lines: fix_intro_section_titles(lines, rel_path)):
        changes.append("介绍页节标题去英文括号")

    # 5. HTML 注释与 heading 分行（会插入新行，需单独处理换行符）
    def _split_html_comments(contents: list[str]) -> list[tuple[str, str]]:
        """返回新行记录；新增行使用默认换行符。"""
        pat = re.compile(r"^(\s*<!--\s*.+?-->\s*)(#{1,6}\s+.*)$")
        new_records: list[tuple[str, str]] = []
        for content, eol in records:
            m = pat.match(content)
            if m:
                new_records.append((m.group(1).strip(), eol))
                new_records.append((m.group(2).strip(), default_eol))
            else:
                new_records.append((content, eol))
        return new_records

    new_records = _split_html_comments([c for c, _ in records])
    if new_records != records:
        changes.append("HTML 来源注释与标题分行")
        records = new_records

    return records, changes, default_eol


def main() -> None:
    files = sorted(INPUT_DIR.rglob("*.md"))
    modified: list[tuple[str, list[str]]] = []

    for path in files:
        records, changes, _ = normalize_file(path)
        if not changes:
            continue
        content = "".join(f"{c}{eol}" for c, eol in records)
        # 若只是换行符差异而没有语义变化，则跳过写入，避免污染 diff
        original_text = path.read_text(encoding="utf-8", errors="ignore", newline="")
        if _content_equal(content, original_text):
            continue
        # 保留原始换行符写入
        path.write_text(content, encoding="utf-8", newline="")
        rel = path.relative_to(INPUT_DIR).as_posix()
        modified.append((rel, changes))

    print(f"共修改 {len(modified)} 个文件")
    # 输出前 20 个样例
    for rel, changes in modified[:20]:
        print(f"- {rel}: {', '.join(changes)}")
    if len(modified) > 20:
        print(f"- ... 还有 {len(modified)-20} 个文件")


if __name__ == "__main__":
    main()
