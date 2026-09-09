"""formats/profession.py — 职业格式处理（文本层）

从 vectorization_prep_profession.py 机械迁移（CP1，纯复制不改行为）：
文本清洗链（is_header_noise → promote_inline_archetype_headings）、
clean_file、split_into_blocks、merge_small_blocks、archetype 标题判定。
跨文件共享符号（SOURCE_COMMENT_RE / INPUT_DIR）也定义在此，processors 单向依赖本文件。
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from vectorizer.formats.base import BaseFormat

# ---------------------------------------------------------------------------
# 共享路径/常量（processors 单向依赖本文件；与老脚本 vectorization_prep_profession.py 同源）
# ---------------------------------------------------------------------------
# 职业源数据根目录（pf_data/phase1/pf_rules_md_organized/职业）
INPUT_DIR = Path(__file__).resolve().parent.parent.parent / "pf_rules_md_organized" / "职业"
TERMS_JSON = Path(__file__).resolve().parent.parent.parent / "terms.json"
# CP0 修正：规则书缩写对应表 2026-08 起位于 docs/（老脚本旧路径 b4920e8 后已失效）
SOURCE_BOOK_ABBR_MD = Path(__file__).resolve().parent.parent.parent / "docs" / "规则书缩写对应表.md"
MD_MAPPING_JSON = Path(__file__).resolve().parent.parent.parent.parent / "md_mapping.json"

MIN_CHUNK_CHARS = 100
MAX_CHUNK_CHARS = 1500
# 速查类标题应合并到父能力块，不作为独立 chunk
QUICK_REF_PREFIXES = ("【法术速查】", "【特性速查】")

# HTML 注释来源标记，例如 <!-- MAH-source:page_667.md:some_anchor -->
SOURCE_COMMENT_RE = re.compile(
    r"<!--\s*(.+?)-source:([^:>]+)(?::([^>]*))?\s*-->",
    re.IGNORECASE,
)


@dataclass
class SourceMarker:
    source_book_abbr: Optional[str]
    source_page: Optional[str]
    raw: str
    anchor: Optional[str] = None  # HTML 注释中的锚点，用于校验标记是否属于当前块


def _md_mapping_lookup(
    md_mapping: Dict[str, Dict[str, Any]], key: str
) -> Optional[str]:
    if not key:
        return None
    entry = md_mapping.get(key)
    if entry and entry.get("toc_path"):
        return entry["toc_path"]
    return None


def resolve_chm_toc_path(
    rel_path: Path,
    source_markers: List[SourceMarker],
    md_mapping: Dict[str, Dict[str, Any]],
) -> str:
    """优先用 md_mapping 中的 toc_path，回退到目录结构。"""
    # 1. 当前文件名
    toc = _md_mapping_lookup(md_mapping, rel_path.name)
    if toc:
        return toc

    # 2. HTML 注释里指向的源 page 文件（支持带目录的路径）
    for marker in source_markers:
        page = marker.source_page
        if not page:
            continue
        toc = _md_mapping_lookup(md_mapping, page)
        if not toc:
            toc = _md_mapping_lookup(md_mapping, Path(page).name)
        if toc:
            return toc

    # 3. 回退：用相对目录结构
    return " → ".join(rel_path.with_suffix("").parts)


def is_header_noise(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    # 去掉首尾粗体/删除线标记后再判断（如 **译者：xxx**）
    stripped = re.sub(r"^(\*\*|~~)+|(\*\*|~~)+$", "", s).strip()
    if stripped.startswith("http://") or stripped.startswith("https://"):
        return True
    if re.match(r"^!?\[.*?\]\(https?://[^)]+\)$", stripped):
        return True
    if re.match(r"^(译者|翻译|整理者|编者|校对|编辑)[:：]", stripped):
        return True
    if stripped == "---校对分隔线---":
        return True
    return False


def _merge_unclosed_bold_spans(lines: List[str]) -> List[str]:
    """把跨行的 **粗体** 重新合并成单行，避免标题/能力名被换行切断。

    例如：
        **凋零（****Blight,
        Su****）**：...
    会被合并为：
        **凋零（****Blight, Su****）**：...
    这样后续的标题提升/拆分才能正确处理。
    """
    out: List[str] = []
    buf = ""

    def _count_bold_markers(text: str) -> int:
        # 按成对的 ** 计数，忽略单个 *（源数据里强调基本用 **）
        return text.count("**")

    def _flush_buf() -> None:
        nonlocal buf
        if buf:
            out.append(buf)
            buf = ""

    for line in lines:
        # 表格行不参与粗体 span 合并；如果当前有未闭合 buf，先 flush
        if line.strip().startswith("|"):
            _flush_buf()
            out.append(line)
            continue

        if buf:
            # 若当前缓冲已经是一个应独立的加粗变体标题，不要再把下一行吞进来
            if _is_bold_variant_title_boundary(buf):
                out.append(buf)
                buf = ""
            else:
                # 空白行作为段落边界：避免把下一个加粗标题吞进上一个未闭合粗体
                if not line.strip():
                    out.append(buf)
                    out.append("")
                    buf = ""
                    continue
                buf += line
                if _count_bold_markers(buf) % 2 == 0:
                    out.append(buf)
                    buf = ""
                continue

        if _count_bold_markers(line) % 2 == 1:
            buf = line
        else:
            out.append(line)

    _flush_buf()
    return out

_BOLD_TITLE_GENERIC = {
    "职业变体", "变体", "变体职业特性", "Class Archetypes",
    "Alternate Class Features", "Archetypes", "变体列表", "职业变体列表",
}
_FEATURE_SECTION_KEYWORDS = ["血统", "血承", "领域", "巫术", "强力巫术", "高等巫术", "庇护主"]


def _is_bold_variant_title_boundary(text: str) -> bool:
    """判断当前缓冲行是否是应独立成段的加粗变体标题。

    CHM 输出里常见标题形如：
        **野性之声** Voice of the Wild**【**ACG**】**
        **赌侠（MAVERICK，铳士变体）**
    这些行不以句末标点结尾，会被 merge_line_breaks 与下一段正文拼成一行，
    导致后续标题提升失效。若识别到此类行，直接作为硬边界断开。
    """
    s = text.strip()
    if not (s.startswith("*") and s.endswith("*")):
        return False
    plain = s.replace("*", "").strip()
    if not plain or len(plain) < 3:
        return False
    if not re.search(r"[一-鿿]", plain):
        return False
    # 职业能力标记
    if re.search(r"(?:^|[\s（(〔［【])Ex(?:$|[\s）)〕］】])", plain) or \
       re.search(r"(?:^|[\s（(〔［【])Su(?:$|[\s）)〕］】])", plain) or \
       re.search(r"(?:^|[\s（(〔［【])Sp(?:$|[\s）)〕］】])", plain):
        return False
    if plain in _BOLD_TITLE_GENERIC:
        return False
    # 显式变体标记
    if re.search(r"[〔［【（(].{1,12}?变体[〕］】）)]", plain):
        return True
    if re.search(r"\b[Aa]rchetype\b", plain) or re.search(r"\b[Aa]lternate\s+Class\b", plain):
        return True
    # 来源书方括号/花括号/尖括号
    if re.search(r"[【〔［]([A-Za-z0-9&]{2,})[】〕］]", plain):
        return True
    # 圆括号内的全大写缩写（可能是来源书，如 (ACG)）
    m = re.search(r"[（(]([A-Za-z0-9&]{2,})[）)]", plain)
    if m:
        # feature 章节（如 强力巫术（UM））不是变体标题
        if "变体" not in plain and any(kw in plain for kw in _FEATURE_SECTION_KEYWORDS):
            return False
        return True
    return False


def merge_line_breaks(lines: List[str]) -> List[str]:
    """把被硬换行拆开的段落重新合并。

    注意：
    - `>` 开头的引用行作为段落硬边界，后续正文不会再拼接到引用行上，
      避免整段正文被误判定为引用/导航块而过滤。
    - HTML 注释（如 `<!-- HH-source:... -->`）是来源标记，不应与下一行
      的标题/正文合并；否则注释会把后面的加粗标题"吞掉"，导致标题在
      `**` 剥离后丢失。
    """
    out: List[str] = []
    buf = ""

    for raw in lines:
        line = raw.rstrip()
        s = line.strip()

        if not s:
            if buf:
                out.append(buf)
                buf = ""
            out.append("")
            continue

        if re.match(r"^#{1,6}\s", line):
            if buf:
                out.append(buf)
                buf = ""
            out.append(line)
            continue

        # HTML 注释行独立成段，不吸后续内容
        if s.startswith("<!--"):
            if buf:
                out.append(buf)
                buf = ""
            out.append(line)
            continue

        # 加粗变体标题行独立成段，避免与下一段正文合并
        if buf and _is_bold_variant_title_boundary(buf):
            out.append(buf)
            buf = ""

        if buf:
            # 表格、列表、引用等块级元素直接断开
            if re.match(r"^([|*+->]|\d+\.)\s", s):
                out.append(buf)
                buf = line.lstrip()
                continue

            # 引用行与正文之间硬断开：引用行不吸收后续正文
            if s.startswith(">") != buf.startswith(">"):
                out.append(buf)
                buf = s
                continue

            # 前一行没有句末标点则合并
            if not re.search(r"[。！？：；.!?;:,]$", buf):
                # 破折号/连字符结尾时保留空格，否则直接拼接
                if buf.endswith(("-", "–", "—")):
                    buf = buf + " " + s
                else:
                    buf = buf + s
                continue
            else:
                out.append(buf)
                buf = s
                continue
        else:
            buf = s

    if buf:
        out.append(buf)

    return out


def _strip_leading_image_link(line: str) -> str:
    """去掉行首 Markdown 图片/链接标记 ![alt](url)，保留后续内容。"""
    # 兼容图片与链接两种写法；链接后允许任意空白
    return re.sub(r"^!\[.*?\]\s*\([^)]+\)\s+", "", line)


def promote_image_prefixed_headings(lines: List[str]) -> List[str]:
    """去掉 PFS 图片链接前缀，把加粗变体标题还原为独立加粗标题行。

    CHM 源数据里常见 PFS 标志前缀：
        ![[图片]](https://...) **冬女巫（Winter Witch）**
        ![[图片]](...) **冻影忍（Frozen Shadow） 出自内海诡道Inner Sea Intrigue**

    若原样去掉图片链接，同行的正文会让标题进入 `promote_leading_bold_headings`，
    从而被错误地判定为前一个变体的子级（level 3）。本函数把标题与正文拆成两行，
    让 `promote_bold_headings` 像处理其他顶层变体标题一样将其提升为 level 2。

    安全阀：只处理 `![alt](url) **标题**[正文]` 这种明确格式；去掉图片后不以 `**`
    开头的普通图文行原样保留。
    """
    heading_re = re.compile(r"^!\[.*?\]\s*\([^)]+\)\s+(\*{2,})(.+?)\1(.*)$")
    out: List[str] = []
    for line in lines:
        s = line.strip()
        if not s.startswith("!["):
            out.append(line)
            continue

        m = heading_re.match(s)
        if not m:
            # 去掉图片链接后若仍是加粗标题候选，保留给后续 promotion 处理
            stripped = _strip_leading_image_link(s)
            if stripped != s and stripped.startswith("**"):
                out.append(stripped)
            else:
                out.append(line)
            continue

        title = m.group(2).replace("*", "").strip()
        rest = m.group(3).strip().lstrip("：: ")
        if not title:
            out.append(line)
            continue

        out.append("**" + title + "**")
        if rest:
            out.append(rest)

    return out


def promote_bold_headings(lines: List[str]) -> List[str]:
    """把独占一行的 **标题** 提升为 Markdown 标题，兼容多余的 * 号。"""
    out: List[str] = []
    last_level = 0
    generic_titles = {
        "职业变体", "变体", "变体职业特性", "Class Archetypes",
        "Alternate Class Features", "Archetypes",
    }

    for line in lines:
        m = re.match(r"^(#{1,6})\s+", line)
        if m:
            last_level = len(m.group(1))
            out.append(line)
            continue

        s = line.strip()
        leading = re.match(r"^\*+", s)
        trailing = re.search(r"\*+$", s)
        if not leading or not trailing:
            out.append(line)
            continue
        if len(leading.group()) < 2 or len(trailing.group()) < 2:
            out.append(line)
            continue

        # 去掉所有 * 号得到标题本体
        title = s.replace("*", "").strip()
        if len(title) < 2 or title in generic_titles:
            out.append(line)
            continue

        # 无信号且以冒号结尾 → 多半是字段标签，不提升
        # 例外：推荐/建议类标题即使以冒号结尾也应提升（如 **推荐狂暴之力：**）
        has_signal = bool(
            re.search(r"[A-Za-z]", title)
            or re.search(r"\b(?:Ex|Su|Sp)\b", title)
            or re.match(r"【[A-Z]+】", title)
            or re.match(r"^推荐", title)
            or re.match(r"^建议", title)
        )
        if not has_signal and (title.endswith("：") or title.endswith(":")):
            out.append(line)
            continue

        # 推荐/建议类标题去掉尾部冒号，保持标题纯净
        if re.match(r"^推荐|^建议", title):
            title = title.rstrip("：:")

        level = min(last_level + 1, 4) if last_level else 2
        out.append("#" * level + " " + title)

    return out


def is_ability_heading_text(title: str, rest: str) -> bool:
    combined = title + " " + rest
    if re.search(r"\b(?:Ex|Su|Sp)\b", combined):
        return True
    if re.search(r"[（(][A-Za-z][^）)]*[）)]", combined):
        return True
    if re.match(r"【[A-Z]+】", title):
        return True
    return False


def promote_leading_bold_headings(lines: List[str]) -> List[str]:
    """把行首 **标题**正文 拆成标题+正文，用于处理变体页中常见的内联粗体标题。

    例如：**魔镜女巫（Mirror Witch）**很多镜子...
    → ## 魔镜女巫（Mirror Witch）
      很多镜子...
    """
    out: List[str] = []
    last_level = 0
    heading_re = re.compile(r"^(#{1,6})\s+")

    for line in lines:
        hm = heading_re.match(line)
        if hm:
            last_level = len(hm.group(1))
            out.append(line)
            continue

        s = line.strip()
        # 只处理"**标题**正文"且后面确实还有非空正文的情况
        m = re.match(r"^(\*{2,})(.+?)\1(\S.*)$", s)
        if not m:
            out.append(line)
            continue

        # 如果捕获的"正文"仍以 * 开头，说明是整行都被粗体包裹的情况，
        # 交给 promote_bold_headings 处理，避免在这里截断。
        if m.group(3).startswith("*"):
            out.append(line)
            continue

        seg = m.group(2).replace("*", "").strip()
        rest = m.group(3).strip()
        if not seg or not rest:
            out.append(line)
            continue

        # 标题需具备 heading 信号，避免把普通强调词误拆
        if not (
            looks_like_ability_title(seg)
            or re.search(r"[A-Za-z]", seg)
            or re.match(r"【[A-Z0-9&]+】", seg)
        ):
            out.append(line)
            continue

        level = min(last_level + 1, 4) if last_level else 2
        out.append("#" * level + " " + seg)
        out.append(rest)

    return out


def promote_inline_ability_headings(lines: List[str]) -> List[str]:
    """把 **能力名（English，Ex）：** 描述 这样的行拆成标题+正文，兼容内部 * 号干扰。"""
    out: List[str] = []
    last_level = 0

    for line in lines:
        m = re.match(r"^(#{1,6})\s+", line)
        if m:
            last_level = len(m.group(1))
            out.append(line)
            continue

        s = line.strip()
        if "**" not in s:
            out.append(line)
            continue

        # 去掉所有 * 后，看是否是一个"标题：正文"结构
        plain = s.replace("*", "")
        cm = re.search(r"^(.+?)([：:])(.*)$", plain)
        if not cm:
            out.append(line)
            continue

        rest_plain = cm.group(3).strip()

        # 确认原文在分隔符前确实存在 **，避免把普通句子误拆
        sep_char = cm.group(2)
        sep_idx = s.find(sep_char)
        if sep_idx < 0 or "**" not in s[:sep_idx]:
            out.append(line)
            continue

        title_plain = cm.group(1).strip()

        # KN222：过渡句（如「后述内容为…职业能力。」）被吞进标题时，从「句末标点」
        # 切分——标点前为过渡句（移入正文），标点后若本身具备能力信号则作为真实标题。
        # 注意不能按「第一个 ** 之前」判定过渡句：`*战斗大师（**Battle Master**，ＥＸ）：`
        # 和 `念动（Telekinetic Blast）**元素**：` 的标题不在 ** 开头（英文粗体/字段标签
        # 在行内），无句末标点则一律不剥离，保持旧行为。
        lead = ""
        pm = re.search(r"^(.*[。．！？])\s*(.+)$", title_plain)
        pm_rejected = False
        if pm:
            cand = pm.group(2).strip()
            # 三条判定，缺一不可：
            # 1) cand 自身须具备能力信号——不能 combined（cand+rest）判定，正文里的
            #    英文括号（如 `(Bravo's Finesse，EX)`）会让无信号的中文能力名
            #    （如「武器和护甲擅长」）被误判为标题。
            # 2) lead 不得含「【…】/［…］」变体标记——变体页常见单行结构
            #    `变体名（EN）【职业】+intro+能力名（EN，Ex）：正文`，此时 lead 是
            #    变体名而非过渡句，剥离会把首个能力名提成空标题、标签在 merge 丢失。
            # 3) 无句末标点的一律不剥离（散星号/字段标签形态，见前注）。
            if (
                cand
                and is_ability_heading_text(cand, "")
                and not re.search(r"[【［][^】］]+[】］]", pm.group(1))
            ):
                lead, title_plain = pm.group(1).strip(), cand
            else:
                # pm 识别到句末标点但 cand 无信号（如 `+ 法术等级 + …随意施展`，
                # cand=`要使用这些法术…随意施展`）：标题是「句子+字段标签」而非能力
                # 标题，此时只认标题自身信号，rest 里的英文括号（`舞光术（dancing
                # lights）`）不能反证——否则整段被提成空壳标题、正文随块被
                # MIN_CHUNK_CHARS 丢弃（page_796 8 字符缺失根因）。
                # 仁义剑客/骑士变体等变体页单行结构虽同为 pm rejected，但标题自身
                # 含 `(Virtuous Bravo)`/`(Code of Gallantry)` 英文信号，title-only
                # 判定照样通过，不受影响。
                pm_rejected = True
        if not title_plain or not is_ability_heading_text(
            title_plain, "" if pm_rejected else rest_plain
        ):
            out.append(line)
            continue
        body = " ".join(filter(None, [lead, rest_plain])).strip()

        level = min(last_level + 1, 5) if last_level else 3
        out.append("#" * level + " " + title_plain)
        if body:
            out.append(body)

    return out


def _normalize_heading_title(title: str) -> str:
    """将标题规范化，用于删除线/变体去重等键值匹配。"""
    t = title.replace("*", "").replace("~", "").replace("　", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _master_key(title: str) -> str:
    """生成变体主表查找键：取标题开头的连续中文字符。"""
    t = _normalize_heading_title(title)
    m = re.search(r"^[一-鿿]+", t)
    if m:
        return m.group(0)
    return t


def _collect_deprecated_titles(lines: List[str]) -> Set[str]:
    """在清理后的行中收集带 ~~ 删除线的标题（清理前调用）。"""
    deprecated: Set[str] = set()
    heading_re = re.compile(r"^(#{1,6})\s+(.*)$")
    for line in lines:
        m = heading_re.match(line)
        if not m:
            continue
        title = m.group(2).strip()
        if "~~" in title:
            deprecated.add(_normalize_heading_title(title))
    return deprecated


def _is_archetype_file(rel_path: Path, md_mapping: Dict[str, Dict[str, Any]]) -> bool:
    """根据路径或 CHM 目录判断文件是否与职业变体相关。"""
    for part in rel_path.parts:
        lower = part.lower()
        if "变体" in lower or "archetype" in lower:
            return True
    toc = resolve_chm_toc_path(rel_path, [], md_mapping)
    if toc and toc.split(" → ")[-1] in ("职业变体", "变体"):
        return True
    return False


def promote_inline_archetype_headings(
    lines: List[str],
    rel_path: Path,
    md_mapping: Dict[str, Dict[str, Any]],
) -> List[str]:
    """在变体文件中，把行首/行内与变体名、来源标记混在一起的正文拆成独立标题。

    支持的输入模式：
    - 名称（English）【X变体】后接正文
    - 名称（English）［X变体］后接正文
    - 名称【X变体】（English）后接正文
    - #### 名称（English）【X变体】后接正文（标题与正文挤在同一行）
    - English Name (Paladin Archetype)后接正文

    例如：守望女巫(Witch-Watcher)【女巫】在格拉里昂...
    → ## 守望女巫(Witch-Watcher)【女巫】
       在格拉里昂...
    """
    if not _is_archetype_file(rel_path, md_mapping):
        return lines

    out: List[str] = []
    last_level = 0
    heading_re = re.compile(r"^(#{1,6})\s+(.*)$")
    generic = {
        "职业变体", "变体", "变体职业特性", "Class Archetypes",
        "Alternate Class Features", "Archetypes", "变体列表", "职业变体列表",
    }

    # 模式 A：名称（English）【/［X变体】/］ 后接正文
    # 模式 B：名称【X变体】（English） 后接正文
    # 模式 C：English Name (Paladin Archetype)后接正文
    # 模式 D：名称（English）：后接正文（常见于变体/能力标题与正文挤在一行）
    inline_patterns = [
        ('A', re.compile(
            r"^(.{1,30}?)\s*[（(]([A-Za-z][^）)]*?)[）)]\s*([【［])([^】］]{1,12}?)[】］]\s*(.+)$"
        )),
        ('B', re.compile(
            r"^(.{1,30}?)\s*【([^】]{1,12}?)】\s*[（(]([A-Za-z][^）)]*?)[）)]\s*(.+)$"
        )),
        ('C', re.compile(
            r"^([A-Za-z][A-Za-z0-9'\-\s]*?)\s*\(\s*(?:[A-Za-z]+\s+)?[Aa]rchetype\s*\)\s*(.+)$"
        )),
        ('D', re.compile(
            r"^(.{1,30}?)\s*[（(]([A-Za-z][^）)]*?)[）)]\s*[：:]\s*(.+)$"
        )),
    ]

    def _looks_like_inline_archetype(s: str) -> bool:
        """判断去掉 heading 标记后的行是否是内联变体标题。"""
        if not s:
            return False
        for _, pat in inline_patterns:
            if pat.match(s):
                return True
        return False

    def _split_inline_archetype(s: str) -> Optional[Tuple[str, str]]:
        """返回 (heading_title, body_text)。"""
        for kind, pat in inline_patterns:
            m = pat.match(s)
            if not m:
                continue
            if kind == 'A':
                name, eng, bracket_char, tag, body = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
                # 如果 body 是另一个变体标记（如 名称（EN）【UW】【圣武士变体】），
                # 说明第一个括号只是来源标记，不应拆分。
                if re.match(r"^[【［].*变体[】］]", body.strip()):
                    return None
                bracket_open, bracket_close = ("【", "】") if bracket_char == "【" else ("［", "］")
                heading = f"{name.strip()}（{eng.strip()}）{bracket_open}{tag.strip()}{bracket_close}"
                return heading, body.strip()
            if kind == 'B':
                name, tag, eng, body = m.group(1), m.group(2), m.group(3), m.group(4)
                # 如果 tag 本身是变体标记，body 是来源标记，保留原行不拆分。
                if "变体" in tag and re.match(r"^[【［]", body.strip()):
                    return None
                heading = f"{name.strip()}（{eng.strip()}）{tag.strip()}"
                return heading, body.strip()
            if kind == 'C':
                return f"{m.group(1).strip()} (Paladin Archetype)", m.group(2).strip()
            if kind == 'D':
                name, eng, body = m.group(1), m.group(2), m.group(3)
                heading = f"{name.strip()}（{eng.strip()}）"
                return heading, body.strip()
        return None

    for line in lines:
        hm = heading_re.match(line)
        if hm:
            last_level = len(hm.group(1))
            title_part = hm.group(2).strip()
            # 若标题行本身也内联了正文（如 #### 名称（English）【变体】正文...），拆开来
            if _looks_like_inline_archetype(title_part):
                split = _split_inline_archetype(title_part)
                if split:
                    heading, body = split
                    name_part = re.split(r"[（(〔［【］］】）]", heading)[0].strip()
                    name_norm = _normalize_heading_title(name_part)
                    if name_norm and name_norm not in generic and not re.search(r"\b(?:Ex|Su|Sp)\b", name_part):
                        out.append("#" * last_level + " " + heading)
                        if body:
                            out.append(body)
                        continue
            out.append(line)
            continue

        s = line.strip()
        # HTML 注释行不应被当作内联变体拆分
        if s.startswith('<!--') or s.startswith('-->'):
            out.append(line)
            continue
        if not _looks_like_inline_archetype(s):
            out.append(line)
            continue

        split = _split_inline_archetype(s)
        if not split:
            out.append(line)
            continue

        heading, body = split
        name_part = re.split(r"[（(〔［【］］】）]", heading)[0].strip()
        name_norm = _normalize_heading_title(name_part)
        if not name_norm or name_norm in generic:
            out.append(line)
            continue
        if re.search(r"\b(?:Ex|Su|Sp)\b", name_part):
            out.append(line)
            continue

        level = min(last_level + 1, 4) if last_level else 2
        out.append("#" * level + " " + heading)
        if body:
            out.append(body)

    return out


def clean_file(
    file_path: Path,
    md_mapping: Dict[str, Dict[str, Any]],
) -> Tuple[List[str], Set[str]]:
    """清洗文件，返回干净的行列表和删除线标题集合。

    HTML 注释来源标记仍保留在流中，由分块阶段收集。
    """
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    raw_lines = text.splitlines()

    cleaned: List[str] = []

    for line in raw_lines:
        if is_header_noise(line):
            continue
        cleaned.append(line)

    rel_path = file_path.relative_to(INPUT_DIR)
    cleaned = _merge_unclosed_bold_spans(cleaned)
    cleaned = merge_line_breaks(cleaned)
    cleaned = promote_image_prefixed_headings(cleaned)
    cleaned = promote_bold_headings(cleaned)
    cleaned = promote_leading_bold_headings(cleaned)
    cleaned = promote_inline_ability_headings(cleaned)
    cleaned = promote_inline_archetype_headings(cleaned, rel_path, md_mapping)
    # 在剥离 ~~ 之前先收集删除线标题
    deprecated_titles = _collect_deprecated_titles(cleaned)
    # 清理残余的 ** 粗体标记与 ~~ 删除线，减少噪音
    cleaned = [line.replace("**", "").replace("~~", "") for line in cleaned]

    return cleaned, deprecated_titles


# ---------------------------------------------------------------------------
# 分块
# ---------------------------------------------------------------------------
def split_into_blocks(lines: List[str], doc_id: str) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {
        "title": Path(doc_id).stem,
        "level": 1,
        "breadcrumbs": [Path(doc_id).stem],
        "lines": [],
        "markers": [],
    }
    heading_re = re.compile(r"^(#{1,6})\s+(.*)$")
    pending_markers: List[SourceMarker] = []

    def flush(absorb_pending: bool = False) -> None:
        if absorb_pending:
            current["markers"].extend(pending_markers)
            pending_markers.clear()
        text = "\n".join(current["lines"]).strip()
        is_initial = current["title"] == Path(doc_id).stem and current["level"] == 1
        if text or current["markers"] or not is_initial:
            blocks.append({
                "title": current["title"],
                "level": current["level"],
                "breadcrumbs": current["breadcrumbs"][:],
                "text": text,
                "markers": current["markers"][:],
            })
        current["lines"] = []
        current["markers"] = []

    for line in lines:
        hm = heading_re.match(line)
        if hm:
            flush()
            level = len(hm.group(1))
            title = hm.group(2).strip()
            breadcrumbs = current["breadcrumbs"][:level - 1] + [title]
            current = {
                "title": title,
                "level": level,
                "breadcrumbs": breadcrumbs,
                "lines": [],
                "markers": list(pending_markers),  # B3 fix: markers → NEW block
            }
            pending_markers.clear()
            continue

        marker_match = SOURCE_COMMENT_RE.search(line)
        if marker_match:
            pending_markers.append(SourceMarker(
                source_book_abbr=marker_match.group(1).strip(),
                source_page=marker_match.group(2).strip(),
                raw=marker_match.group(0),
                anchor=(marker_match.group(3) or "").strip() or None,
            ))
            continue

        current["lines"].append(line)

    flush(absorb_pending=True)

    if not blocks:
        blocks.append({
            "title": Path(doc_id).stem,
            "level": 1,
            "breadcrumbs": [Path(doc_id).stem],
            "text": "\n".join(lines).strip(),
            "markers": [],
        })

    return blocks


def merge_small_blocks(
    blocks: List[Dict[str, Any]],
    is_archetype_file: bool = False,
) -> List[Dict[str, Any]]:
    if not blocks:
        return blocks

    merged = [blocks[0].copy()]
    for b in blocks[1:]:
        prev = merged[-1]
        combined_len = len(prev["text"]) + len(b["text"])
        b_title = b.get("title", "")
        prev_title = prev.get("title", "")

        # 当前块如果是变体/章节标题，不应被前面的小块吞掉标题。
        b_is_archetype = looks_like_archetype_title(
            b_title, is_archetype_file=is_archetype_file, level=b.get("level", 0)
        )
        prev_is_archetype = looks_like_archetype_title(
            prev_title, is_archetype_file=is_archetype_file, level=prev.get("level", 0)
        )

        # 变体标题块之间的合并：同名或父子层级才合并；不同变体保持独立。
        if b_is_archetype and prev_is_archetype:
            prev_name = _master_key(prev_title)
            b_name = _master_key(b_title)
            same_name = prev_name and b_name and prev_name == b_name
            if (
                (same_name or prev["level"] < b["level"])
                and len(prev["text"]) < MIN_CHUNK_CHARS
                and combined_len <= MAX_CHUNK_CHARS
            ):
                if prev["level"] < b["level"]:
                    # prev 是父级变体，b 是其下的子块；保留父级标题
                    prev["text"] = (prev["text"] + "\n" + b["text"]).strip()
                else:
                    # 同名变体：b 通常带有【来源/职业】标记，保留 b 的标题
                    b["text"] = (prev["text"] + "\n" + b["text"]).strip()
                    prev.update(b)
                continue
            merged.append(b.copy())
            continue

        if b_is_archetype and not prev_is_archetype:
            # 若前一块与当前变体是同一名称的"无标记"版本（如 `振奋乐师（Solacer）`
            # 后接 `振奋乐师（Solacer）【吟游诗人变体】`），把前者作为上下文并入
            # 当前变体，并让当前块与前者同级，避免无标记版本被识别为能力，
            # 也避免当前块被当作前者的子级。
            prev_name = _master_key(prev_title)
            b_name = _master_key(b_title)
            same_name = prev_name and b_name and prev_name == b_name
            if combined_len <= MAX_CHUNK_CHARS and same_name:
                b["text"] = (prev["text"] + "\n" + b["text"]).strip()
                # 提升到与无标记版本同级，并去掉无标记祖先
                b["level"] = prev["level"]
                b["breadcrumbs"] = (prev["breadcrumbs"][:-1] if prev["breadcrumbs"] else []) + [b_title]
                prev.update(b)
                continue

            # 若前一块只是短小的来源引用/说明，把它并入当前变体，避免来源丢失
            if (
                len(prev["text"]) < MIN_CHUNK_CHARS
                and combined_len <= MAX_CHUNK_CHARS
                and not looks_like_ability_title(prev_title)
                and not prev.get("feature_subtype")
                and not _normalize_heading_title(prev_title).startswith(("推荐", "建议"))
            ):
                b["text"] = (prev["text"] + "\n" + b["text"]).strip()
                prev.update(b)
                continue
            merged.append(b.copy())
            continue

        # 若前一块是变体标题但内容过短，不要把它的标题吞掉，而是把当前内容并入前一块
        if prev_is_archetype and len(prev["text"]) < MIN_CHUNK_CHARS and combined_len <= MAX_CHUNK_CHARS:
            prev["text"] = (prev["text"] + "\n" + b["text"]).strip()
            continue

        # 推荐/建议类 Build 提示保持独立，不要被后续小块吞掉
        if _normalize_heading_title(prev_title).startswith(("推荐", "建议")):
            merged.append(b.copy())
            continue

        # 法术速查/特性速查是对父能力的解释，合并到前一个块里（在字数上限内）
        if any(b_title.startswith(prefix) for prefix in QUICK_REF_PREFIXES):
            if combined_len <= MAX_CHUNK_CHARS:
                prev["text"] = (prev["text"] + "\n" + b["text"]).strip()
                continue
            else:
                merged.append(b.copy())
                continue

        # 当前块如果只是个空标题，不要把它前面的小块吞掉
        if not b["text"].strip():
            merged.append(b.copy())
            continue

        # 由条目表显式标记的 subtype（如补充书巫术/庇护主）必须保留独立标题；
        # 但若前一块是短小的章节说明/概述文本，则把它作为上下文合并进来。
        if b.get("feature_subtype"):
            if (
                len(prev["text"]) < MIN_CHUNK_CHARS
                and not looks_like_ability_title(prev_title)
                and not prev.get("feature_subtype")
                and not looks_like_archetype_title(
                    prev_title, is_archetype_file=is_archetype_file, level=prev.get("level", 0)
                )
                and (len(prev["text"]) + len(b["text"])) <= MAX_CHUNK_CHARS
            ):
                merged.pop()
                b["text"] = (prev["text"] + "\n" + b["text"]).strip()
                merged.append(b.copy())
                continue
            merged.append(b.copy())
            continue

        # 前一个块如果是具体能力/巫术条目，即使短小也不应被下一块吞掉标题
        if (
            len(prev["text"]) < MIN_CHUNK_CHARS
            and looks_like_ability_title(prev_title)
        ):
            merged.append(b.copy())
            continue

        if len(prev["text"]) < MIN_CHUNK_CHARS and combined_len <= MAX_CHUNK_CHARS:
            prev_text_was_empty = not prev["text"].strip()
            prev["text"] = (prev["text"] + "\n" + b["text"]).strip()
            # 合并时优先保留前一个块的标题；但如果前一块没有实质文本
            # （只是空标题），则保留当前块更具体的标题，避免"巫术（Hex）"
            # 这种章节标题把第一个能力块吞掉。
            if prev_text_was_empty:
                prev["title"] = b["title"]
                prev["breadcrumbs"] = b["breadcrumbs"][:]
                prev["level"] = b["level"]
            else:
                prev["title"] = prev["title"] or b["title"]
                prev["breadcrumbs"] = (
                    prev["breadcrumbs"][:] if prev["title"] else b["breadcrumbs"][:]
                )
                prev["level"] = prev["level"] if prev["title"] else b["level"]
        else:
            merged.append(b.copy())

    return merged


# ---------------------------------------------------------------------------
# 组件识别
# ---------------------------------------------------------------------------
# Rule-2-removal 已知精确误判，不会被 Rule 1 捕获但可能被 Rule 2b/3 误判。
# 【】内为血脉/诅咒/秘示域等非变体标记，不适合追加【X变体】到源文件。
_ARCHETYPE_TITLE_EXCLUDE = frozenset({
    '阴影（Shadow）【血脉狂怒者血脉狂怒者血脉】',
})


def looks_like_archetype_title(title: str, is_archetype_file: bool = False, level: int = 0) -> bool:
    if not title:
        return False

    # 精确排除已知误判
    if title in _ARCHETYPE_TITLE_EXCLUDE:
        return False

    # 文件级标题（H1）不应被视为具体变体标题，否则在合并小 block 时
    # 会把第一个 H2 变体的内容并入 H1 并丢失该变体名称。
    if level <= 1:
        return False

    generic = {
        "职业变体", "变体职业特性", "变体", "Class Archetypes",
        "Alternate Class Features", "Archetypes", "变体列表", "职业变体列表",
    }
    name_part = re.split(r"[（(〔［]", title)[0].strip()
    name_norm = _normalize_heading_title(name_part)
    if not name_norm or name_norm in generic:
        return False

    # 显式包含 Ex/Su/Sp 的是职业能力，不是变体
    if re.search(r"\b(?:Ex|Su|Sp)\b", title):
        return False

    # 含"巫术"且英文名以 Hex/Hexes 结尾的是巫术条目/章节，不是变体
    if "巫术" in title and re.search(r"[（(][^）)]*\bHex(?:es)?\b\s*[）)]", title):
        return False

    # 1. 包含"〔X变体〕/［X变体］/（X变体）/【X变体】"
    if re.search(r"[〔［](?P<base>[^〕］]+?)变体[〕］]", title):
        return True
    if re.search(r"（(?P<base>[^）]{1,12}?)变体）", title):
        return True
    if re.search(r"【(?P<base>[^】]{1,12}?)变体】", title):
        return True

    # 【注：Rule 2 已移除 — 2026-07-23】
    # 原 Rule 2 用于捕获 名称（English）【来源】格式的变体标题，但不区分
    # 【来源书缩写】与变体标记，导致先知诅咒、血脉、奥术发现等 19 条误判。
    # 已通过 add_missing_archetype_markers.py 给所有 Rule-2-only 真变体
    # 追加了【X变体】标记，由 Rule 1 接管。

    # 2b. 名称 English / English Name【来源/职业标记】（无括号，用空格分隔）
    if re.search(r"\s+[A-Za-z][A-Za-z0-9'\-]*(?:\s+[A-Za-z][A-Za-z0-9'\-]*)*\s*【[^】]+】", title):
        return True

    # 3. 在变体相关文件中，level<=3 且带有英文名的条目视为变体
    if is_archetype_file and level <= 3 and re.search(r"[（(][A-Za-z][^）)]*[）)]", title):
        return True

    return False


def extract_archetype_info(title: str) -> Tuple[Optional[str], Optional[str]]:
    if not title:
        return None, None

    name_part = re.split(r"[（(〔［]", title)[0].strip()
    base_class = None

    # 支持多种括号：〔X变体〕、（X变体）、【X变体】、［X变体］
    # 兼容括号内带英文前缀的格式，如 "名称（English，X变体）"；
    # base 只取紧邻 "变体" 前的职业名，避免把前缀英文也抓进来。
    m = re.search(r"[〔［][^〕］]*?(?P<base>[^，,、〕］\s]{1,12}?)变体[〕］]", title)
    if not m:
        m = re.search(r"（[^）]*?(?P<base>[^，,、）\s]{1,12}?)变体）", title)
    if not m:
        m = re.search(r"【[^】]*?(?P<base>[^，,、】\s]{1,12}?)变体】", title)
    if m:
        base_class = m.group("base").strip()

    return name_part, base_class


def looks_like_ability_title(title: str) -> bool:
    if not title:
        return False
    if "变体" in title:
        return False
    if re.search(r"\b(?:Ex|Su|Sp)\b", title):
        return True
    if re.search(r"[（(][A-Za-z][^）)]*[）)]", title):
        return True
    if re.match(r"【[A-Z]+】", title):
        return True
    return False


class ProfessionFormat(BaseFormat):
    """职业格式处理（文本层）。

    文本层职责：clean_file（清洗链 + 删除线标题收集）与 split_into_blocks
    （行 → 块）均为本文件模块级函数。expand / merge / build_chunk 属块层
    编排，由 ProfessionProcessor 的 process() 全权调用，不经本类方法——
    因此 normalize / promote 保持原文透传（避免二次清洗破坏与老脚本等价），
    split_into_items 暴露块拆分入口供复用（processor 注入 doc_id）。
    """

    category = "profession"

    def __init__(self) -> None:
        # processor 每文件注入（split_into_blocks 初始标题用文件名 stem）
        self.doc_id = ""

    def normalize(self, text: str) -> str:
        # 外部 normalize 不透传外部规则：职业清洗链是行级全流程（clean_file），
        # 由 processor 直接调用 clean_file 保真执行；此处返回原文防二次清洗。
        return text

    def promote(self, text: str) -> str:
        # 结构提升已内嵌 clean_file 阶段（promote_* 系列），无独立 promote 步。
        return text

    def split_into_items(self, text: str, *, source_name: Optional[str] = None) -> List[dict]:
        return split_into_blocks(text.splitlines(), self.doc_id)


