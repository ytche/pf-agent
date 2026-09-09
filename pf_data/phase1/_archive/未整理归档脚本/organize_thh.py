"""
哈罗牌手册 THH 整理脚本（重写版）

按 pf_data/未整理目录整理规则.md 执行整理工作：
- §3 来源标注格式
- §4.0 源书聚合（每本规则书独立 <来源书>_<类型>.md）
- §4.1 处理表
- §4.2 货品服务/炼金/毒药归 page_212
- §4.4 行尾换行符保持
- §16 整理后文档格式整洁性（关键！）

源目录：pf_data/phase1/pf_rules_md/未整理/哈罗牌手册THH/
"""

import re
from pathlib import Path

# ---------- 路径常量 ----------
PHASE1 = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC = PHASE1 / "pf_rules_md" / "未整理" / "哈罗牌手册THH"
DST = PHASE1 / "pf_rules_md_organized"

# 来源标注（统一）
def src_attr(entry_name: str = "") -> str:
    """生成 `> 来源：...` 标注"""
    base = (
        "> 来源：哈罗牌手册（Tarot Heroes Handbook）THH"
        "，页码见原书，未整理 → 哈罗牌手册THH"
    )
    if entry_name:
        # entry_name 可用于子节定位，例如 "→ 变体/选项 → 盗贼+天赋"
        return f"{base} → {entry_name}"
    return base


# ---------- 通用 IO 函数（保持行尾） ----------
def read_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    has_crlf = b"\r\n" in raw
    return raw.decode("utf-8"), ("\r\n" if has_crlf else "\n")


def write_bytes(path: Path, content: str, nl: str) -> None:
    """按指定行尾写回"""
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    if nl == "\r\n":
        content = content.replace("\n", "\r\n")
    path.write_bytes(content.encode("utf-8"))


def append_to_file(path: Path, addition: str) -> None:
    """追加内容到文件，保持行尾风格（无 NL 标记则添加）"""
    text, nl = read_text(path)
    if not text.endswith(nl):
        text += nl
    if not addition.startswith(nl):
        addition = nl + addition
    new_text = text + addition
    if not new_text.endswith(nl):
        new_text += nl
    write_bytes(path, new_text, nl)


def append_skip_if_exists(path: Path, addition: str, marker: str) -> bool:
    """追加内容到文件，但若已含 marker 则跳过（§6.6 增量重跑）"""
    text, nl = read_text(path)
    if marker in text:
        print(f"  [SKIP] {path.name} 已含 {marker}，跳过")
        return False
    append_to_file(path, addition)
    return True


def create_new_file(path: Path, content: str, use_lf: bool = True) -> None:
    """新建文件，使用 LF（标准）；如存在则跳过"""
    if path.exists():
        print(f"  [SKIP] {path.name} 已存在，跳过创建")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    if not content.endswith("\n"):
        content += "\n"
    if not use_lf:
        content = content.replace("\n", "\r\n")
    path.write_bytes(content.encode("utf-8"))


def read_src(name: str) -> str:
    p = SRC / name
    return p.read_text(encoding="utf-8")


# ---------- 文本清洗 ----------
def merge_broken_bold(text: str) -> str:
    """合并跨行加粗标题：`**xxx\nyyy\nzzz**` → `**xxxyyyzzz**`

    处理 3 行以上跨行加粗（常见于哈罗牌手册长标题）。
    仅在内容非纯空白时才合并，避免误把 `**\\n**`（孤立空标记）合并成 `****`。
    """
    pattern = re.compile(r"\*\*([^*]+?)\*\*")
    def _sub(m):
        content = m.group(1)
        if not content.strip():
            # 孤立 `**\n**` 不合并，保持原样
            return m.group(0)
        return "**" + content.replace("\n", "").replace("\r", "") + "**"
    return pattern.sub(_sub, text)


def extract_bold_title(body: str) -> tuple[str, str]:
    """从条目开头提取加粗标题，返回 (标题内容, 余下正文)"""
    # 修复跨行加粗
    body = merge_broken_bold(body)
    m = re.match(r"\*\*([^*]+)\*\*\s*\n+", body)
    if m:
        title = m.group(1).strip()
        rest = body[m.end():].strip()
        return title, rest
    return "", body


def normalize_paragraphs(text: str) -> str:
    """规范化段落：合并连续空行（3+ → 2），去除首尾空行，移除孤儿 `**` 行"""
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 移除孤儿的 ** 行（仅含 `**` 或 `**\n`），通常是源文件中残留的空加粗标记
    text = re.sub(r"^\*\*\s*\n", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n\*\*\s*$", "", text, flags=re.MULTILINE)
    return text.strip()


def format_entry(title: str, body: str, source_attr: str) -> str:
    """生成一个条目的标准格式（## 标题 + 来源 + 正文）"""
    parts = [f"## {title}", "", source_attr, ""]
    if body:
        parts.append(body)
        parts.append("")
    return "\n".join(parts)


# ============================================================
# 1. 专长（5 条） → 专长/哈罗牌手册THH_专长.md
# ============================================================
def organize_feats():
    text = merge_broken_bold(read_src("专长6.md"))

    # 5 个专长的起始标记（标题可能跨行、可能无 **）
    sections = [
        ("哈罗召唤术（Harrowed Summoning）", "哈罗召唤术（Harrowed"),
        ("致命发牌者（Deadly Dealer）", "**致命发牌者（Deadly"),
        ("自残旋风（All-Consuming Swing）", "**自残旋风（All-Consuming"),
        ("熊之平衡（Bears Balance）", "**熊之平衡（Bears"),
        ("残忍击打（Merciless Beating）", "**残忍击打（Merciless"),
    ]

    # 切割
    indices = []
    for name, marker in sections:
        idx = text.find(marker)
        if idx < 0:
            print(f"  WARN: 找不到 {name} ({marker})")
            continue
        indices.append((name, idx))

    blocks = []
    for i, (name, start) in enumerate(indices):
        end = indices[i + 1][1] if i + 1 < len(indices) else len(text)
        body = text[start:end].strip()
        # 移除原标题行（保留正文）
        # 找下一个 **前提** 或 **好处** 作为正文起点
        body_start = re.search(r"(\*\*前提\*\*|\*\*好处\*\*|^\*\*\*[^*])", body, re.MULTILINE)
        if body_start:
            rest = body[body_start.start():].strip()
        else:
            # 兜底：去掉标题的前 1-2 行
            lines = body.split("\n", 2)
            rest = lines[2] if len(lines) > 2 else body
        rest = normalize_paragraphs(rest)
        blocks.append((name, rest))

    content = "# 哈罗牌手册 THH 专长\n\n"
    content += "<!-- THH-source:专长6.md -->\n\n"

    for name, body in blocks:
        content += format_entry(name, body, src_attr("专长")) + "\n\n---\n\n"

    out = DST / "专长" / "哈罗牌手册THH_专长.md"
    create_new_file(out, content)
    print(f"[OK] 专长聚合: {out.relative_to(PHASE1)}")


# ============================================================
# 2. 盗贼天赋（5）+ 高级盗贼天赋（1） → 专长/哈罗牌手册THH_盗贼天赋.md
# ============================================================
def organize_rogue_talents():
    text = read_src("变体_选项/盗贼1.md")
    text = merge_broken_bold(text)

    # 切掉主条目（变体本身），只保留引述部分
    main_idx = text.find("引述:")
    if main_idx > 0:
        text = text[main_idx:]

    # 拆分 盗贼天赋 和 高级盗贼天赋
    talent_match = re.search(
        r"引述:\s*盗贼天赋（[^）]+）\s*\n+(.*?)(?=引述:\s*高级盗贼天赋|$)",
        text,
        re.DOTALL,
    )
    advanced_match = re.search(
        r"引述:\s*高级盗贼天赋（[^）]+）\s*\n+(.*?)$",
        text,
        re.DOTALL,
    )

    talent_block = talent_match.group(1).strip() if talent_match else ""
    advanced_block = advanced_match.group(1).strip() if advanced_match else ""

    # 清洗引述文本（去掉 "引述:" 标签）
    talent_block = re.sub(r"^引述:\s*[^\n]+\n+", "", talent_block).strip()
    advanced_block = re.sub(r"^引述:\s*[^\n]+\n+", "", advanced_block).strip()

    # 处理盗贼天赋中的 5 个新天赋 + 1 个盗贼变体能力
    # 每个能力以 **xxx（English Name）** 开头
    content = "# 哈罗牌手册 THH 盗贼天赋\n\n"
    content += "<!-- THH-source:变体_选项/盗贼1.md -->\n\n"

    # 盗贼天赋
    content += "## 盗贼天赋\n\n"
    content += src_attr("变体/选项 → 盗贼+天赋") + "\n\n"

    # 把盗贼天赋中的每个能力单独标注
    talents = split_talent_block(talent_block)
    for tname, tbody in talents:
        tbody = normalize_paragraphs(tbody)
        content += f"### {tname}\n\n{tbody}\n\n"

    content += "---\n\n"

    # 高级盗贼天赋
    content += "## 高级盗贼天赋\n\n"
    content += src_attr("变体/选项 → 盗贼+天赋") + "\n\n"

    advanceds = split_talent_block(advanced_block)
    for aname, abody in advanceds:
        abody = normalize_paragraphs(abody)
        content += f"### {aname}\n\n{abody}\n\n"

    out = DST / "专长" / "哈罗牌手册THH_盗贼天赋.md"
    create_new_file(out, content)
    print(f"[OK] 盗贼天赋聚合: {out.relative_to(PHASE1)}")


def split_talent_block(block: str) -> list[tuple[str, str]]:
    """把多个天赋条目拆分；支持加粗与纯文本标题

    源文件特点：标题后常直接接正文（无换行），如 `以牌为镖（Card\n  Sharp，Su）：盗贼获得...`
    因此正则只要求 `[:：]` 即可，不必 `\n+`。
    """
    # 优先匹配 **天赋名（English Name，类别）**：
    pattern_bold = re.compile(
        r"\*\*([^*\n]+?（[^）]+）)\*\*[:：]?",
        re.MULTILINE,
    )
    # 兜底匹配纯文本标题：xxx（English Name，类别）：
    pattern_plain = re.compile(
        r"(?<![\*\*])([一-龥\w]+（[A-Za-z][^）]*?）)[:：]",
        re.MULTILINE,
    )

    matches = list(pattern_bold.finditer(block))
    if not matches:
        matches = list(pattern_plain.finditer(block))

    if not matches:
        return [("盗贼天赋条目", block.strip())]

    # 收集第一个匹配前的"推荐"段落
    pre_text = block[: matches[0].start()].strip()

    entries = []
    if pre_text and pre_text not in ("", "盗贼天赋", "高级盗贼天赋"):
        entries.append(("推荐天赋", pre_text))

    for i, m in enumerate(matches):
        title = m.group(1).strip()
        # 合并跨行/连续空白为单空格
        title = re.sub(r"\s+", " ", title)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(block)
        body = block[start:end].strip()
        entries.append((title, body))

    return entries


# ============================================================
# 3. 女巫巫术（新） → 专长/哈罗牌手册THH_女巫巫术.md
# ============================================================
def organize_witch_hexes():
    text = read_src("变体_选项/女巫+巫术.md")
    text = merge_broken_bold(text)

    # 切掉主条目（牌灵师变体），只保留巫术部分
    main_idx = text.find("引述: 巫术")
    if main_idx > 0:
        text = text[main_idx:]

    content = "# 哈罗牌手册 THH 女巫巫术\n\n"
    content += "<!-- THH-source:变体_选项/女巫+巫术.md -->\n\n"

    # 巫术: 占卜者 (Soothsayer)
    content += "## 巫术\n\n"
    content += src_attr("变体/选项 → 女巫+巫术") + "\n\n"
    hex_match = re.search(
        r"占卜者（Soothsayer，Su）[:：]?\s*(.*?)(?=引述|$)",
        text,
        re.DOTALL,
    )
    if hex_match:
        body = normalize_paragraphs(hex_match.group(1))
        content += "### 占卜者（Soothsayer，Su）\n\n"
        content += body + "\n\n"

    content += "---\n\n"

    # 强力巫术: 哈罗诅咒 (Harrowing Curse)
    content += "## 强力巫术\n\n"
    content += src_attr("变体/选项 → 女巫+巫术") + "\n\n"
    major_match = re.search(
        r"哈罗诅咒（Harrowing\s+Curse，Su）[:：]?\s*(.*?)(?=引述|$)",
        text,
        re.DOTALL,
    )
    if major_match:
        body = normalize_paragraphs(major_match.group(1))
        content += "### 哈罗诅咒（Harrowing Curse，Su）\n\n"
        content += body + "\n\n"

    out = DST / "专长" / "哈罗牌手册THH_女巫巫术.md"
    create_new_file(out, content)
    print(f"[OK] 女巫巫术聚合: {out.relative_to(PHASE1)}")


# ============================================================
# 4. 魔战士奥能（新） → 专长/哈罗牌手册THH_魔战士奥能.md
# ============================================================
def organize_magus_arcana():
    text = read_src("变体_选项/魔战士+奥能.md")
    text = merge_broken_bold(text)

    # 切掉主条目（牌法师变体），只保留奥能部分
    main_idx = text.find("引述: 新魔战士奥能")
    if main_idx > 0:
        text = text[main_idx:]

    content = "# 哈罗牌手册 THH 魔战士奥能\n\n"
    content += "<!-- THH-source:变体_选项/魔战士+奥能.md -->\n\n"

    content += "## 新魔战士奥能\n\n"
    content += src_attr("变体/选项 → 魔战士+奥能") + "\n\n"

    # 提取 奥术发牌者 + 罗刹之幸
    arcana_entries = []
    arcana1 = re.search(
        r"奥术发牌者（Arcane\s+Dealer，Su）[:：]?\s*(.*?)(?=罗刹之幸|引述|$)",
        text,
        re.DOTALL,
    )
    if arcana1:
        arcana_entries.append(("奥术发牌者（Arcane Dealer，Su）", arcana1.group(1)))

    arcana2 = re.search(
        r"罗刹之幸（Rakshasa's\s+Fortune，Su）[:：]?\s*(.*?)(?=引述|$)",
        text,
        re.DOTALL,
    )
    if arcana2:
        arcana_entries.append(("罗刹之幸（Rakshasa's Fortune，Su）", arcana2.group(1)))

    for aname, abody in arcana_entries:
        abody = normalize_paragraphs(abody)
        content += f"### {aname}\n\n{abody}\n\n"

    out = DST / "专长" / "哈罗牌手册THH_魔战士奥能.md"
    create_new_file(out, content)
    print(f"[OK] 魔战士奥能聚合: {out.relative_to(PHASE1)}")


# ============================================================
# 5. 诗人传世名作（2） → 传世名作汇总.md（追加）
# ============================================================
def organize_bard_masterpieces():
    text = read_src("变体_选项/诗人传世名作1.md")
    text = merge_broken_bold(text)

    addition = "<!-- THH-source:变体_选项/诗人传世名作1.md -->\n\n"
    addition += "## 哈罗牌手册 THH 传世名作\n\n"
    addition += src_attr("变体/选项 → 诗人传世名作") + "\n\n"

    # 2 传世名作（先匹配标题块，再剥离首行作为正文起始）
    masterpieces = [
        ("幻象的裁决（Illusion's Decree，喜剧/演讲）",
         r"幻象的裁决[\s\S]*?(前提[:：].*?)(?=扭曲钢铁的传说|$)"),
        ("扭曲钢铁的传说（Tales of Twisting Steel，小品/演讲）",
         r"扭曲钢铁的传说[\s\S]*?(前提[:：].*)$"),
    ]

    for title, pattern in masterpieces:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            body = normalize_paragraphs(m.group(1))
            addition += f"### {title}\n\n{body}\n\n"

    out = DST / "传世名作汇总.md"
    marker = "<!-- THH-source:变体_选项/诗人传世名作1.md -->"
    if append_skip_if_exists(out, addition, marker):
        print(f"[OK] 传世名作追加: {out.relative_to(PHASE1)}")


# ============================================================
# 6. 物品（10 魔法） → 装备_魔法物品/魔法物品/哈罗牌手册THH_装备.md
# 7. 普通物品（2） → 装备_魔法物品/货品服务/page_212.md
# ============================================================
def organize_items():
    text = read_src("物品1.md")
    text = merge_broken_bold(text)

    # 分割普通物品和魔法物品
    # 普通物品在第一个表格（含"价格（GP）| 重量（磅）| 位置|..."）
    magic_start = text.find("| 物品 | 价格（GP） | 重量（磅） | 位置 | 施法者等级")
    if magic_start < 0:
        print("  WARN: 找不到魔法物品表头")
        return

    normal_section = text[:magic_start].strip()
    magic_section = text[magic_start:].strip()

    # ---- 普通物品 → page_212 ----
    # 转换为 ## 总标题 + 表格 + ### 子条目
    page212_addition = (
        "## 哈罗牌手册 THH 特有冒险装备（哈罗牌相关）\n\n"
        "<!-- THH-source:物品1.md:哈罗牌具 -->\n\n"
    )

    # 提取表格（**哈罗牌具** 标题 + 表格行块）
    table_match = re.search(
        r"(\*\*[^*\n]+\*\*\s*\n+)?"
        r"(\|\s*物品\s*\|[^\n]*\n\|[\s\-:|]+\|[^\n]*\n(?:\|[^\n]*\n?)+)",
        normal_section,
    )
    if table_match:
        page212_addition += table_match.group(2).strip() + "\n\n"

    # 跳过表格，提取每个普通物品的 **名称（English）**：描述
    # 只匹配包含 `：` 的条目（描述开头），跳过纯标题（如 **哈罗牌具...**）
    item_blocks = []
    for m in re.finditer(
        r"\*\*([^*\n]+?（[^*\n]+?）)\*\*[:：]\s*(.*?)(?=\*\*[^*\n]+?）\*\*[:：]|\Z)",
        normal_section,
        re.DOTALL,
    ):
        title = re.sub(r"\s+", " ", m.group(1).strip())
        body = m.group(2).strip()
        if title and body:
            item_blocks.append((title, body))

    for title, body in item_blocks:
        page212_addition += f"### {title}\n\n{normalize_paragraphs(body)}\n\n"

    p212 = DST / "装备_魔法物品" / "货品服务" / "page_212.md"
    marker = "<!-- THH-source:物品1.md:哈罗牌具 -->"
    if append_skip_if_exists(p212, page212_addition, marker):
        print(f"[OK] 普通物品追加: {p212.relative_to(PHASE1)}")

    # ---- 魔法物品 → 哈罗牌手册THH_装备.md ----
    # 分离魔法物品表格 和 物品描述
    desc_start = magic_section.find("**（Backbiter's")
    if desc_start < 0:
        desc_start = magic_section.find("**（")

    if desc_start > 0:
        magic_table = magic_section[:desc_start].strip()
        magic_desc = magic_section[desc_start:].strip()
    else:
        magic_table = magic_section
        magic_desc = ""

    # 解析物品描述
    desc_items = parse_item_descriptions(magic_desc)

    content = "# 哈罗牌手册 THH 魔法物品\n\n"
    content += "<!-- THH-source:物品1.md -->\n\n"
    content += src_attr("物品") + "\n\n"

    content += "## 物品表\n\n"
    content += magic_table + "\n\n"

    content += "## 物品详细描述\n\n"

    for title, body in desc_items:
        content += f"### {title}\n\n"
        content += normalize_paragraphs(body) + "\n\n---\n\n"

    out = DST / "装备_魔法物品" / "魔法物品" / "哈罗牌手册THH_装备.md"
    create_new_file(out, content)
    print(f"[OK] 魔法物品聚合: {out.relative_to(PHASE1)}")


def parse_item_descriptions(desc: str) -> list[tuple[str, str]]:
    """解析物品详细描述为列表

    源文件标题模式（merge_broken_bold 后）：
    - `**物品名（English）**：正文...` （同一行）
    - `**物品名（English）**\n：正文...` （标题一行，正文下一行）
    - `**（English Only）**：正文...` （无中文名，如 Backbiter's focus、Man mountain armor）
    """
    # 1. 从表格中提取中文名映射（用于补全无中文名的条目）
    cn_name_map = _build_item_cn_map()

    # 2. 匹配标题（不强制要求 \n+）
    pattern = re.compile(r"\*\*([^*\n]+)\*\*[:：]?\s*", re.MULTILINE)
    matches = list(pattern.finditer(desc))

    if not matches:
        return [("物品描述", desc)]

    items = []
    for i, m in enumerate(matches):
        raw_title = m.group(1).strip()
        # 合并跨行空格
        raw_title = re.sub(r"\s+", " ", raw_title)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(desc)
        body = desc[start:end].strip()
        # 清理正文开头残留的 `：` 或 `：\n`
        body = re.sub(r"^[:：]\s*", "", body).strip()
        # 补全中文名
        title = _resolve_item_title(raw_title, cn_name_map)
        items.append((title, body))

    return items


def _build_item_cn_map() -> dict[str, str]:
    """从魔法物品表格中构建 `English name → 中文名` 映射"""
    text = read_src("物品1.md")
    text = merge_broken_bold(text)
    cn_map: dict[str, str] = {}
    # 表格行形如：`| 中文名（English name） | 价格 | ...`
    for m in re.finditer(
        r"\|\s*([^|]+?)\s*\|\s*\d+\s*\|",
        text,
    ):
        cell = m.group(1).strip()
        # 提取中文名（English name） 中的英文部分
        mm = re.match(r"(.+?)（([^）]+)）", cell)
        if mm:
            cn_name, en_name = mm.group(1).strip(), mm.group(2).strip()
            # 排除普通物品
            if en_name and not en_name.startswith("Harrow"):
                cn_map[en_name] = cn_name
    return cn_map


def _resolve_item_title(raw: str, cn_map: dict[str, str]) -> str:
    """根据 raw 标题解析最终 `### 标题`

    raw 形如:
    - `削命牌（Deck of Slivering Fate）`
    - `（Backbiter's focus）`
    - `山人铠（Man mountain armor）`
    """
    raw = raw.strip()
    # 已经是 `中文（English）` 形式
    if raw.startswith("（"):
        # 仅英文，去 cn_map 查中文名
        m = re.match(r"（([^）]+)）", raw)
        if m:
            en = m.group(1).strip()
            cn = cn_map.get(en, "")
            if cn:
                return f"{cn}（{en}）"
            return f"（{en}）"
        return raw
    return raw


# ============================================================
# 8. 法术荒疫（1） → 规则/法术荒疫_哈罗牌手册THH.md
# ============================================================
def organize_spellscar():
    text = read_src("法术荒疫选项.md").strip()
    text = merge_broken_bold(text)

    content = "# 法术荒疫 - 哈罗牌手册 THH\n\n"
    content += "<!-- THH-source:法术荒疫选项.md -->\n\n"

    # 提取法术荒疫名（去除跨行）
    title_match = re.match(
        r"哈罗扰乱（Harrow\s+Vexed）[:：]?",
        text,
        re.DOTALL,
    )
    if title_match:
        title = "哈罗扰乱（Harrow Vexed）"
        body = text[title_match.end():].strip()
    else:
        title = "哈罗扰乱（Harrow Vexed）"
        body = text

    content += f"## {title}\n\n"
    content += src_attr("法术荒疫选项") + "\n\n"
    content += normalize_paragraphs(body) + "\n\n"

    out = DST / "规则" / "法术荒疫_哈罗牌手册THH.md"
    create_new_file(out, content)
    print(f"[OK] 法术荒疫: {out.relative_to(PHASE1)}")


# ============================================================
# 9. 故事形态（幻灵范例） → 职业/基础职业/召唤师/THH_故事召唤师与故事形态.md
# ============================================================
def organize_storykin():
    text = read_src("变体_选项/召唤师.md").strip()
    text = merge_broken_bold(text)

    content = "# 哈罗牌手册 THH 召唤师变体与幻灵\n\n"
    content += "<!-- THH-source:变体_选项/召唤师.md -->\n\n"

    # 主条目：故事召唤师（Story Summoner）召唤师变体
    story_match = re.search(
        r"故事召唤师（Story\s*Summoner）\s*\n+(.*?)(?=引述:|$)",
        text,
        re.DOTALL,
    )
    if story_match:
        body = normalize_paragraphs(story_match.group(1))
        content += "## 故事召唤师（Story Summoner）【召唤师变体】\n\n"
        content += src_attr("变体/选项 → 召唤师") + "\n\n"
        content += body + "\n\n---\n\n"

    # 引述：新幻灵范例（故事形态）
    storykin_match = re.search(
        r"引述:\s*新幻灵范例[^\n]*\n+(.*?)$",
        text,
        re.DOTALL,
    )
    if storykin_match:
        body = normalize_paragraphs(storykin_match.group(1))
        content += "## 新幻灵范例（故事形态 Storykin）\n\n"
        content += src_attr("变体/选项 → 召唤师") + "\n\n"
        content += body + "\n\n"

    out = DST / "职业" / "基础职业" / "召唤师" / "THH_故事召唤师与故事形态.md"
    create_new_file(out, content)
    print(f"[OK] 召唤师变体与幻灵: {out.relative_to(PHASE1)}")


# ============================================================
# 10. 职业变体（追加到已有页面）
# ============================================================
def append_variant(
    file_rel: str, source_md: str, content: str, entry_name: str, variant_title: str = ""
):
    """追加变体到指定目标文件（已含 THH-source 则跳过）"""
    target = DST / file_rel
    marker = f"<!-- THH-source:{source_md}:{entry_name} -->"
    if variant_title:
        body = f"## {variant_title}\n\n{src_attr('变体/选项')}\n\n{content.strip()}\n\n"
    else:
        body = content
    addition = f"{marker}\n\n{body}"

    if append_skip_if_exists(target, addition, marker):
        print(f"[OK] {entry_name} -> {file_rel}")


def organize_class_variants():
    # 1. 斯科扎尼老千（盗贼变体）→ 盗贼/page_49.md
    text = merge_broken_bold(read_src("变体_选项/盗贼1.md"))
    m = re.search(
        r"\*\*斯科扎尼老千.*?【盗贼变体】\*\*\s*\n(.*?)(?=引述:)",
        text,
        re.DOTALL,
    )
    if m:
        body = normalize_paragraphs(m.group(1))
        # 二次清理：合并正文中可能残余的跨行加粗
        body = merge_broken_bold(body)
        append_variant(
            "职业/核心职业/盗贼/page_49.md",
            "变体_选项/盗贼1.md",
            body,
            "斯科扎尼老千",
            "斯科扎尼老千（Sczarni Swindler）【盗贼变体】",
        )

    # 2. 寻牌者（审判者变体）→ 审判者/page_78.md
    text = merge_broken_bold(read_src("变体_选项/审判者1.md"))
    m = re.search(
        r"(?:\*\*)?寻牌者（Suit\s*Seeker）\s*【审判者变体】(?:\*\*)?\s*\n(.*?)$",
        text,
        re.DOTALL,
    )
    if m:
        body = normalize_paragraphs(m.group(1))
        body = merge_broken_bold(body)
        append_variant(
            "职业/基础职业/审判者/page_78.md",
            "变体_选项/审判者1.md",
            body,
            "寻牌者",
            "寻牌者（Suit Seeker）【审判者变体】",
        )

    # 3. 哈罗牌守卫（武僧变体）→ 武僧/page_53.md
    # 源文件使用 `）` 全角右括号或 `)` 半角，兼容两种
    text = merge_broken_bold(read_src("变体_选项/武僧1.md"))
    m = re.search(
        r"\*\*哈罗牌守卫（HARROW\s*WARDEN[)）]\s*【武僧变体】\*\*\s*\n(.*?)$",
        text,
        re.DOTALL,
    )
    if m:
        body = normalize_paragraphs(m.group(1))
        body = merge_broken_bold(body)
        append_variant(
            "职业/核心职业/武僧/page_53.md",
            "变体_选项/武僧1.md",
            body,
            "哈罗牌守卫",
            "哈罗牌守卫（HARROW WARDEN）【武僧变体】",
        )

    # 4. 太阳秘示域（先知秘示域）→ 先知/page_88.md
    text = merge_broken_bold(read_src("变体_选项/先知秘示域1.md"))
    m = re.search(
        r"\*\*太阳秘示域\*\*\s*\n(.*?)$",
        text,
        re.DOTALL,
    )
    if m:
        body = normalize_paragraphs(m.group(1))
        body = merge_broken_bold(body)
        append_variant(
            "职业/基础职业/先知/page_88.md",
            "变体_选项/先知秘示域1.md",
            body,
            "太阳秘示域",
            "太阳秘示域【先知秘示域】",
        )

    # 5. 故事召唤师（召唤师变体）→ 召唤师/page_411.md
    text = merge_broken_bold(read_src("变体_选项/召唤师.md"))
    m = re.search(
        r"故事召唤师（Story\s*Summoner）\s*\n(.*?)(?=引述:|$)",
        text,
        re.DOTALL,
    )
    if m:
        body = normalize_paragraphs(m.group(1))
        body = merge_broken_bold(body)
        append_variant(
            "职业/基础职业/召唤师/page_411.md",
            "变体_选项/召唤师.md",
            body,
            "故事召唤师",
            "故事召唤师（Story Summoner）【召唤师变体】",
        )

    # 6. 牌法师（魔战士变体）→ 魔战士/page_82.md
    text = merge_broken_bold(read_src("变体_选项/魔战士+奥能.md"))
    m = re.search(
        r"牌法师（Card\s*Caster）\s*\n(.*?)(?=引述:|$)",
        text,
        re.DOTALL,
    )
    if m:
        body = normalize_paragraphs(m.group(1))
        body = merge_broken_bold(body)
        append_variant(
            "职业/基础职业/魔战士/page_82.md",
            "变体_选项/魔战士+奥能.md",
            body,
            "牌法师",
            "牌法师（Card Caster）【魔战士变体】",
        )

    # 7. 牌灵师（女巫变体）→ 女巫/page_92.md
    text = merge_broken_bold(read_src("变体_选项/女巫+巫术.md"))
    m = re.search(
        r"\*\*牌灵师（CARTOMANCER）\*\*\s*\n(.*?)(?=引述:|$)",
        text,
        re.DOTALL,
    )
    if m:
        body = normalize_paragraphs(m.group(1))
        body = merge_broken_bold(body)
        append_variant(
            "职业/基础职业/女巫/page_92.md",
            "变体_选项/女巫+巫术.md",
            body,
            "牌灵师",
            "牌灵师（CARTOMANCER）【女巫变体】",
        )

    # 8. 哈罗血统（术士血统）→ 术士/page_64.md
    text = merge_broken_bold(read_src("变体_选项/术士血统1.md"))
    m = re.search(
        r"\*\*哈罗血统（Harrow\s*Bloodline）\s*【术士血统】\*\*\s*\n(.*?)$",
        text,
        re.DOTALL,
    )
    if m:
        body = normalize_paragraphs(m.group(1))
        body = merge_broken_bold(body)
        append_variant(
            "职业/核心职业/术士/page_64.md",
            "变体_选项/术士血统1.md",
            body,
            "哈罗血统",
            "哈罗血统（Harrow Bloodline）【术士血统】",
        )


# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("哈罗牌手册 THH 整理开始")
    print("=" * 60)
    organize_feats()
    organize_rogue_talents()
    organize_witch_hexes()
    organize_magus_arcana()
    organize_bard_masterpieces()
    organize_items()
    organize_spellscar()
    organize_storykin()
    organize_class_variants()
    print("=" * 60)
    print("整理完成")
    print("=" * 60)