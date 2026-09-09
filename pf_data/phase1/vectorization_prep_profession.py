#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PF 1e 职业目录向量化预处理脚本（三分法迭代版）

将 pf_rules_md_organized/职业 下的 Markdown 文件清洗、分块、富化元数据，
输出到 vectorization_prep_profession/，不修改原始文件。

分块策略：
- class_overview：职业整体介绍（HD、技能、擅长、定位等）
- class_feature：单个职业能力/天赋（如"制裁邪恶""盗贼天赋"）
- class_archetype：单个职业变体（如"医护骑士""亡灵制裁者"）
- class_recommendation：Build 建议（如"推荐狂暴之力"）

同时生成 class_archetype_index.json，记录职业-变体-来源书-chunk_id 关系。
"""

import json
import hashlib
import re
import shutil
import sys
from collections import Counter
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any

from term_rules import SOURCE_BOOK_TRANSLATIONS

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
INPUT_DIR = Path(__file__).parent / "pf_rules_md_organized" / "职业"
OUTPUT_DIR = Path(__file__).parent / "vectorization_prep_profession"
TERMS_JSON = Path(__file__).parent / "terms.json"
SOURCE_BOOK_ABBR_MD = Path(__file__).parent / "规则书缩写对应表.md"
MD_MAPPING_JSON = Path(__file__).parent.parent / "md_mapping.json"

MIN_CHUNK_CHARS = 100
MAX_CHUNK_CHARS = 1500

# 容易出现误命中、需要过滤的通用中文字符串
GENERIC_CHINESE_ALIASES = {
    "出自", "变体", "职业变体", "变体职业特性", "职业能力", "职业特性",
    "该能力", "此能力", "取代", "调整", "来源", "整理者", "校对", "译者", "编辑",
    "未整理", "核心规则", "规则书", "规则",
    "法术", "专长", "技能", "种族", "怪物", "物品", "装备", "武器", "护甲",
}

# 速查类标题应合并到父能力块，不作为独立 chunk
QUICK_REF_PREFIXES = ("【法术速查】", "【特性速查】")

# Build 建议类标题，保持独立 chunk，不要被后面的小块吞掉
RECOMMENDATION_HEADINGS = {"推荐巫术", "建议巫术", "推荐", "建议"}

# 文件名里的缩写 → 规则书缩写对应表中的规范缩写
ABBR_ALIASES = {
    "KIS": "KOTI",   # 内海骑士文件名用 KIS，缩写表是 KotI
    # 传世名作用户自创简写（含单引号）→ 规范缩写
    "D'SD": "DD",    # D'sD → Disciple's Doctrine
    "D'SH": "DSH",   # D'sH → Dragonslayer's Handbook
    "H'SH": "HH",    # H'sH → Healer's Handbook
    "M'S": "MEM",    # M's  → Merchant's Manifest (MeM)
    # 文件名缩写 → 规范缩写（156 未知来源修复）
    "PIS": "POTI",   # 内海海盗 → Pirates of the Inner Sea (PotI)
    "UNDEAD": "USH", # 亡灵杀手手册 → Undead Slayer's Handbook (USH)
    "AH": "AHH",     # 反英雄手册 → Antihero's Handbook (AHH)
    "ARMOR": "AMH",  # 护甲大师手册 → Armor Master's Handbook (AMH)
}

# 规则书元组（中文名、英文名、缩写），与缩写表保持一致
_CRB = ("核心规则书", "Pathfinder RPG Core Rulebook", "CRB")
_APG = ("进阶玩家手册", "Advanced Player's Guide", "APG")
_ACG = ("进阶职业手册", "Advanced Class Guide", "ACG")
_UM = ("极限魔法", "Ultimate Magic", "UM")
_UC = ("极限战斗", "Ultimate Combat", "UC")
_OA = ("异能冒险", "Occult Adventures", "OA")
_UI = ("极限诡道", "Ultimate Intrigue", "UI")
_UW = ("极限荒野", "Ultimate Wilderness", "UW")
_PU = ("解放者", "Pathfinder Unchained", "PU")
_MA = ("神话冒险", "Mythic Adventures", "MA")
_HOG = ("格拉利昂的半身人", "Halflings of Golarion", "HoG")
_PSP = ("初探探索者协会", "Pathfinder Society Primer", "PSP")
_LOTFW = ("第一世界的遗产", "Legacy of the First World", "LotFW")
_COB = ("均衡勇士", "Champions of Balance", "CoB")
_EOG = ("格拉利昂的精灵", "Elves of Golarion", "EoG")
_COS = ("奇怪之城", "City of Strangers", "CoS")
_COTR = ("正义编年史", "Chronicles of the Righteous", "CotR")

# 目录级来源书覆盖（用于中文俗称目录）
DIRECTORY_BOOK_OVERRIDES = {
    "掉链子（Unchained）": _PU,
    "掉链子": _PU,
}

# 文件名→缩写覆盖：对文件名不含ASCII缩写（纯中文名）的文件，
# 为 feature 子块（### 级）提供来源后缀（B2 修复之后剩余场景）
FILENAME_BOOK_OVERRIDES = {
    # B2 修复：文件名无 ASCII 缩写，靠 HTML 注释修复后 feature 子块仍无来源
    "格拉里昂的半身人_半身人投机客": "HOG",
    "初探探索者协会_外勤探员": "PSP",
    "第一世界TFWRotF_妖精誓缚者": "LOTFW",
    "格拉里昂的平衡勇士_均衡密使": "COB",
    "格拉里昂的精灵_寻光者": "EOG",
    # B1 修复：文件名无 ASCII 缩写，HTML 注释虽已修复但 feature 子块无来源
    "亡灵杀手手册_灵魂守卫": "USH",
    "护甲大师手册_骑士变体": "AMH",
    # 其他：文件名有英文但非规范缩写，feature 子块无法命中 abbr_map
    "秘术选集ArcaneAnthology_变体": "ARA",
    # 无来源文件补丁
    "page_862": "CRB",
}

# 职业容器目录的默认来源书（当无法从更低层路径推断时使用）
CONTAINER_DEFAULT_BOOK = {
    "核心职业": _CRB,
    "混合职业": _ACG,
    "其他职业": _CRB,
}

# 职业目录的默认来源书（按职业名）
CLASS_DEFAULT_BOOK = {
    # 核心职业（CRB）
    "野蛮人": _CRB, "吟游诗人": _CRB, "牧师": _CRB, "德鲁伊": _CRB,
    "战士": _CRB, "武僧": _CRB, "圣骑士": _CRB, "游侠": _CRB,
    "盗贼": _CRB, "术士": _CRB, "法师": _CRB,
    # 混合职业（ACG）
    "奥能师": _ACG, "血脉狂怒者": _ACG, "拳师": _ACG, "猎人": _ACG,
    "调查员": _ACG, "萨满": _ACG, "战吟者": _ACG, "杀手": _ACG,
    "游荡剑客": _ACG, "战斗祭司": _ACG,
    # 基础职业
    "炼金术师": _APG, "反圣武士": _APG, "骑将": _APG, "审判者": _APG,
    "先知": _APG, "召唤师": _APG, "女巫": _APG,
    "魔战士": _UM,
    "铳士": _UC, "铳手": _UC, "忍者": _UC, "武士": _UC,
    "通灵者": _OA, "秘学士": _OA, "催眠师": _OA,
    "侠客": _UI,
    "游荡者": _PU,
    # 其他职业
    "吸血鬼猎人": _CRB, "导魂者": _CRB,
}

# 职业容器目录名
CLASS_CONTAINERS = {
    "核心职业",
    "混合职业",
    "基础职业",
    "Unchained",
    "掉链子（Unchained）",
    # 2026-07-21 补充：以下容器此前缺失，导致操念使/异能者/唤魂师/变形者/导魂者等 609 个 chunk 归属失败
    "异能冒险（Occult Adventures）",
    "极限荒野（Ultimate Wilderness）",
    "其他职业",
    "神话冒险",
}

# 路径包含这些容器名时，直接把整个目录自归属为该容器（不是具体职业）
CONTAINER_SELF_ATTRIBUTION = {"神话冒险"}

# HTML 注释来源标记，例如 <!-- MAH-source:page_667.md:some_anchor -->
SOURCE_COMMENT_RE = re.compile(
    r"<!--\s*(.+?)-source:([^:>]+)(?::([^>]*))?\s*-->",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------
@dataclass
class SourceMarker:
    source_book_abbr: Optional[str]
    source_page: Optional[str]
    raw: str
    anchor: Optional[str] = None  # HTML 注释中的锚点，用于校验标记是否属于当前块


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    source_paths: List[str]
    category: str
    component_type: str           # class_overview / class_feature / class_archetype / class_recommendation
    class_name: str
    archetype_name: Optional[str]
    book_source: str
    book_source_english: str
    book_abbreviation: str
    chm_toc_path: str
    title: str
    heading_breadcrumbs: List[str]
    source_markers: List[Dict[str, Any]]
    terms: List[str]
    aliases: List[str]
    feature_subtype: Optional[str]
    is_deprecated: bool
    char_count: int
    text: str
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StructureEntry:
    """补充文件条目表中的单一条目。"""
    cn: str
    en: str
    subtype: str
    tag: Optional[str] = None


@dataclass(frozen=True)
class SupplementSpec:
    """补充文件结构规范：章节 + 条目。"""
    sections: List[str]
    entries: List[StructureEntry]


# 女巫补充文件结构改写注册表
WITCH_SUPPLEMENT_REGISTRY: Dict[str, SupplementSpec] = {
    "基础职业/女巫/皇庭英豪HotHC_庇护主.md": SupplementSpec(
        sections=["庇护主"],
        entries=[StructureEntry("保护", "Protection", "patron")],
    ),
    "基础职业/女巫/格拉里昂的纯洁勇士_女巫庇护主与巫术.md": SupplementSpec(
        sections=["女巫庇护主", "女巫巫术", "强力巫术", "高等巫术"],
        entries=[
            StructureEntry("边界", "Boundaries", "patron"),
            StructureEntry("奉献", "Devotion", "patron"),
            StructureEntry("和平", "Peace", "patron"),
            StructureEntry("净化灵光", "Aura of Purity", "hex", tag="Su"),
            StructureEntry("和平之绊", "Peace Bond", "hex", tag="Su"),
            StructureEntry("女巫的赠礼", "Witch's Bounty", "major_hex", tag="Su"),
            StructureEntry("女巫的眷顾", "Witch's Charge", "major_hex", tag="Su"),
            StructureEntry("非暴力诅咒", "Curse of Nonviolence", "grand_hex", tag="Su"),
            StructureEntry("安息", "Lay to Rest", "grand_hex", tag="Sp"),
        ],
    ),
}


# ---------------------------------------------------------------------------
# 来源书判定框架（Provider 模式）
# ---------------------------------------------------------------------------
"""
把来源书推断从 10 级 if-else 瀑布改为"多证据源 + 置信度"模型。
每个 SourceProvider 独立给出候选来源与置信度，最终按置信度取最高。
这样可以把显式标记、文件名、变体主表、段落内联标记、目录/TOC、职业默认
等证据解耦，避免职业默认过早覆盖更具体的证据。
"""


@dataclass
class SourceCandidate:
    """来源书候选。"""

    book: Tuple[str, str, str]  # (中文名, 英文名, 缩写)
    confidence: int             # 0-100，越高越可靠
    provider: str               # 用于调试


@dataclass
class SourceContext:
    """来源判定所需的上下文。"""

    rel_path: Path
    source_markers: List[SourceMarker]
    title: str
    text: str
    breadcrumbs: List[str]
    component_type: str
    class_name: str
    archetype_name: Optional[str]
    block_index: int
    file_blocks: List[Dict[str, Any]]
    book_lookup: Dict[str, Any]
    md_mapping: Dict[str, Dict[str, Any]]
    toc_path: str
    archetype_masters: Dict[str, Dict[str, Dict[str, Any]]]


class SourceProvider:
    """来源书证据提供者的抽象基类。"""

    def candidates(self, ctx: SourceContext) -> List[SourceCandidate]:
        raise NotImplementedError


class ExplicitMarkerProvider(SourceProvider):
    """显式来源标记：HTML 注释、> 来源：、出自《...》（Abbreviation）。"""

    def __init__(self, book_lookup: Dict[str, Any]):
        self.book_lookup = book_lookup

    def candidates(self, ctx: SourceContext) -> List[SourceCandidate]:
        results: List[SourceCandidate] = []
        abbr_map = self.book_lookup.get("abbr", {})
        cn_map = self.book_lookup.get("cn_to_abbr", {})
        en_map = self.book_lookup.get("en_to_abbr", {})

        # class_archetype 的来源推断需要避免正文中的法术/能力缩写（如 UM、UI）
        # 覆盖标题与变体主表等更可靠的证据，因此调低正文提示权重、提高标题权重。
        is_archetype = ctx.component_type == "class_archetype"

        # 1. HTML 注释里的缩写
        for marker in ctx.source_markers:
            raw = (marker.source_book_abbr or "").strip()
            abbr = re.search(r"[A-Za-z0-9&]+", raw)
            if not abbr:
                continue
            # 若标记带锚点，校验锚点是否在当前块上下文内，防止跨节泄漏
            if marker.anchor:
                context_text = " ".join(
                    [ctx.title, ctx.archetype_name or ""] + ctx.breadcrumbs
                )
                if marker.anchor not in context_text:
                    continue
            book = _book_from_abbr(abbr.group(0).upper(), abbr_map)
            if book:
                conf = 97 if is_archetype else 95
                results.append(SourceCandidate(book, conf, "ExplicitMarkerProvider:HTML"))

        # 2. 正文开头的"来源："提示
        text_conf = 94 if is_archetype else 95
        for hint in _extract_text_source_hints(ctx.text):
            book = _book_from_abbr(hint.upper(), abbr_map)
            if book:
                results.append(SourceCandidate(book, text_conf, "ExplicitMarkerProvider:text-abbr"))
            book = _match_book_name(hint, cn_map, en_map, abbr_map)
            if book:
                results.append(SourceCandidate(book, text_conf, "ExplicitMarkerProvider:text-book"))

        # 3. 标题中的来源提示（如【ARG】、（MTT 职业变体））
        title_conf = 96 if is_archetype else 90
        for hint in _extract_title_source_hints(ctx.title):
            book = _book_from_abbr(hint.upper(), abbr_map)
            if book:
                results.append(SourceCandidate(book, title_conf, "ExplicitMarkerProvider:title-abbr"))
            book = _match_book_name(hint, cn_map, en_map, abbr_map)
            if book:
                results.append(SourceCandidate(book, title_conf, "ExplicitMarkerProvider:title-book"))

        return results


class FilenameTokenProvider(SourceProvider):
    """文件名中的英文缩写（如 WO_圣骑士变体.md）。"""

    def __init__(self, book_lookup: Dict[str, Any]):
        self.book_lookup = book_lookup

    def candidates(self, ctx: SourceContext) -> List[SourceCandidate]:
        results: List[SourceCandidate] = []
        abbr_map = self.book_lookup.get("abbr", {})
        for token in re.findall(r"[A-Za-z0-9&]{2,}", ctx.rel_path.name):
            book = _book_from_abbr(token.upper(), abbr_map)
            if book:
                results.append(SourceCandidate(book, 85, "FilenameTokenProvider"))
        # 文件名整体覆盖：对文件名不含 ASCII 缩写的文件
        stem = ctx.rel_path.stem
        if stem in FILENAME_BOOK_OVERRIDES:
            book = _book_from_abbr(FILENAME_BOOK_OVERRIDES[stem], abbr_map)
            if book:
                results.append(SourceCandidate(book, 85, "FilenameTokenProvider:override"))
        return results


class DirectoryTocProvider(SourceProvider):
    """目录名或 CHM TOC 路径中的来源书。"""

    def __init__(self, book_lookup: Dict[str, Any]):
        self.book_lookup = book_lookup

    def candidates(self, ctx: SourceContext) -> List[SourceCandidate]:
        results: List[SourceCandidate] = []
        abbr_map = self.book_lookup.get("abbr", {})
        cn_map = self.book_lookup.get("cn_to_abbr", {})
        en_map = self.book_lookup.get("en_to_abbr", {})

        # 目录级覆盖
        for part in ctx.rel_path.parts:
            for variant in _name_variants(part):
                if variant in DIRECTORY_BOOK_OVERRIDES:
                    results.append(SourceCandidate(DIRECTORY_BOOK_OVERRIDES[variant], 60, "DirectoryTocProvider:override"))

        # 目录中的中文来源书名/缩写
        for part in ctx.rel_path.parts:
            book = _match_book_name(part, cn_map, en_map, abbr_map)
            if book:
                results.append(SourceCandidate(book, 60, "DirectoryTocProvider:dir"))
            for token in re.findall(r"[A-Za-z0-9&]{2,}", part):
                book = _book_from_abbr(token.upper(), abbr_map)
                if book:
                    results.append(SourceCandidate(book, 60, "DirectoryTocProvider:dir-abbr"))

        # CHM TOC 路径
        toc_parts = ctx.toc_path.split(" → ")
        for part in toc_parts:
            book = _match_book_name(part, cn_map, en_map, abbr_map)
            if book:
                results.append(SourceCandidate(book, 55, "DirectoryTocProvider:toc"))
            for token in re.findall(r"[A-Za-z0-9&]{2,}", part):
                book = _book_from_abbr(token.upper(), abbr_map)
                if book:
                    results.append(SourceCandidate(book, 55, "DirectoryTocProvider:toc-abbr"))

        return results


class AggregationTableProvider(SourceProvider):
    """解析聚合页顶部的来源书表，为能力/变体补标来源书。

    核心职业/基础职业等的 page_xx.md 顶部常有一个 Markdown 表格，
    列出每个职业能力的来源书分布。此 Provider 解析该表格并产生
    置信度 65 的候选，覆盖职业默认书（30），但低于显式标记（95）。

    注意：表格行可能被 `\\n` 换行切断（如 `野性之怒（Animal \\n Fury）`），
    因此需要先把跨行内容拼接为逻辑行再拆单元格。
    """

    def __init__(self):
        self._cache: Dict[str, Dict[str, Tuple[str, str, str]]] = {}

    def candidates(self, ctx: SourceContext) -> List[SourceCandidate]:
        if ctx.component_type not in ("class_archetype", "class_feature"):
            return []
        doc_id = ctx.rel_path.as_posix()
        if doc_id not in self._cache:
            self._cache[doc_id] = self._parse_table(
                Path("pf_rules_md_organized") / "职业" / ctx.rel_path, ctx.book_lookup
            )
        table = self._cache[doc_id]
        if not table:
            return []
        title_key = ctx.title.strip()[:20]
        if title_key in table:
            return [SourceCandidate(table[title_key], 65, "AggregationTableProvider")]
        cn_part = ctx.title.split("（")[0].strip()[:20]
        if cn_part in table:
            return [SourceCandidate(table[cn_part], 65, "AggregationTableProvider")]
        return []

    @staticmethod
    def _parse_table(path: Path, book_lookup: Dict[str, Any]) -> Dict[str, Tuple[str, str, str]]:
        if not path.exists():
            return {}
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return {}

        lines = text.splitlines()
        # 拼接跨行单元格：一行不以 | 开头但前一行是表格行 → 续行
        logical_rows: List[str] = []
        for line in lines:
            s = line.strip()
            if s.startswith("|"):
                logical_rows.append(s)
            elif s and logical_rows:
                logical_rows[-1] += " " + s

        # 找第一个表格
        table_start = -1
        for i, row in enumerate(logical_rows):
            if row.count("|") >= 2:
                table_start = i
                break
        if table_start < 0:
            return {}

        result: Dict[str, Tuple[str, str, str]] = {}
        current_book: Optional[Tuple[str, str, str]] = None
        abbr_map = book_lookup.get("abbr", {})

        for row in logical_rows[table_start:]:
            cells = AggregationTableProvider._split_cells(row)
            if not cells:
                continue
            # 分隔行跳过
            if all(c.strip() in ("---", "") for c in cells):
                continue

            first = cells[0].strip()
            book = AggregationTableProvider._match_book(first, abbr_map)
            if book:
                current_book = book
                for cell in cells[1:]:
                    ab = AggregationTableProvider._extract_ability(cell)
                    if ab:
                        result[ab] = book
            elif current_book:
                for cell in cells:
                    ab = AggregationTableProvider._extract_ability(cell)
                    if ab:
                        result[ab] = current_book

        return result

    @staticmethod
    def _split_cells(row: str) -> List[str]:
        parts = row.split("|")
        if len(parts) <= 2:
            return []
        return parts[1:-1]

    @staticmethod
    def _match_book(cell: str, abbr_map: Dict[str, Any]) -> Optional[Tuple[str, str, str]]:
        m = re.search(r"（([A-Z]{2,5})）", cell)
        if m:
            abbr = m.group(1)
            return _book_from_abbr(abbr, abbr_map)
        return None

    @staticmethod
    def _extract_ability(cell: str) -> Optional[str]:
        name = cell.strip()
        cn = re.split(r"[（(]", name)[0].strip()
        if not cn or len(cn) < 2:
            return None
        cn = re.sub(r"【[^】]+】", "", cn).strip()
        if not cn:
            return None
        return cn[:20]


class ClassDefaultProvider(SourceProvider):
    """职业默认来源书（最弱证据之一）。"""

    def candidates(self, ctx: SourceContext) -> List[SourceCandidate]:
        for part in ctx.rel_path.parts:
            if part in CLASS_DEFAULT_BOOK:
                return [SourceCandidate(CLASS_DEFAULT_BOOK[part], 30, "ClassDefaultProvider")]
        return []


class ContainerDefaultProvider(SourceProvider):
    """职业容器默认来源书。"""

    def candidates(self, ctx: SourceContext) -> List[SourceCandidate]:
        for part in ctx.rel_path.parts:
            if part in CONTAINER_DEFAULT_BOOK:
                return [SourceCandidate(CONTAINER_DEFAULT_BOOK[part], 20, "ContainerDefaultProvider")]
        return []


class CRBFallbackProvider(SourceProvider):
    """职业根节点兜底 CRB。"""

    def candidates(self, ctx: SourceContext) -> List[SourceCandidate]:
        toc_parts = ctx.toc_path.split(" → ")
        if len(toc_parts) >= 2 and toc_parts[0] == "职业":
            second = toc_parts[1]
            if second in ("职业变体", "角色升级", "天赋职业", "核心职业"):
                return [SourceCandidate(_CRB, 10, "CRBFallbackProvider")]
        return []


class ArchetypeMasterProvider(SourceProvider):
    """变体主表覆盖（仅对 class_archetype 生效）。"""

    def __init__(self, archetype_masters: Dict[str, Dict[str, Dict[str, Any]]]):
        self.archetype_masters = archetype_masters

    def candidates(self, ctx: SourceContext) -> List[SourceCandidate]:
        if ctx.component_type != "class_archetype":
            return []
        if ctx.class_name == "未知职业":
            return []
        master = self.archetype_masters.get(ctx.class_name, {}).get(_master_key(ctx.title))
        if not master:
            return []
        source_book = master.get("source_book")
        if not source_book:
            return []
        book = (
            source_book,
            master.get("source_book_english") or "?",
            master.get("book_abbreviation") or "?",
        )
        return [SourceCandidate(book, 95, "ArchetypeMasterProvider")]


class InlineSourceProvider(SourceProvider):
    """
    段落级/块级来源标记回溯。
    对汇总文件内未被变体主表收录的变体，扫描标题前后文本中的来源书标记。
    """

    def __init__(self, book_lookup: Dict[str, Any]):
        self.book_lookup = book_lookup

    def candidates(self, ctx: SourceContext) -> List[SourceCandidate]:
        if ctx.component_type not in ("class_archetype", "class_feature"):
            return []

        abbr_map = self.book_lookup.get("abbr", {})
        cn_map = self.book_lookup.get("cn_to_abbr", {})
        en_map = self.book_lookup.get("en_to_abbr", {})

        snippets: List[str] = []
        # 当前 block 文本前 800 字
        snippets.append(ctx.text[:800])
        # 前一个 block 末尾 400 字（来源行可能在标题之前）
        if ctx.block_index > 0:
            prev_text = ctx.file_blocks[ctx.block_index - 1].get("text", "")
            snippets.append(prev_text[-400:])
        # 标题本身
        snippets.append(ctx.title)

        results: List[SourceCandidate] = []
        for snippet in snippets:
            # 出自《书名》（Abbreviation）
            for m in re.finditer(r"出自《([^《》]+)》(?:[（(]([A-Za-z][A-Za-z0-9'\-\s]*)[）)])?", snippet):
                abbr = (m.group(2) or "").strip()
                if abbr:
                    book = _book_from_abbr(abbr.upper(), abbr_map)
                    if book:
                        results.append(SourceCandidate(book, 75, "InlineSourceProvider:出自"))
                book_name = m.group(1).strip()
                book = _match_book_name(book_name, cn_map, en_map, abbr_map)
                if book:
                    results.append(SourceCandidate(book, 75, "InlineSourceProvider:出自书名"))

            # 出自 书名（Abbreviation） 或 出自书名...页码（无《》）
            for m in re.finditer(r"出自\s*《?([^《》\n,，]{2,60})》?", snippet):
                book_name = m.group(1).strip()
                book = _match_book_name(book_name, cn_map, en_map, abbr_map)
                if book:
                    results.append(SourceCandidate(book, 75, "InlineSourceProvider:出自书名"))

            # > 来源：书名（Abbreviation）
            for m in re.finditer(r"来源[：:]\s*([^，,\n]+)", snippet):
                hint = m.group(1).strip()
                book = _book_from_abbr(hint.upper(), abbr_map)
                if book:
                    results.append(SourceCandidate(book, 75, "InlineSourceProvider:来源行-abbr"))
                book = _match_book_name(hint, cn_map, en_map, abbr_map)
                if book:
                    results.append(SourceCandidate(book, 75, "InlineSourceProvider:来源行-book"))

            # HTML 注释来源标记
            for m in SOURCE_COMMENT_RE.finditer(snippet):
                raw = m.group(1).strip()
                book = _book_from_abbr(raw.upper(), abbr_map)
                if book:
                    results.append(SourceCandidate(book, 75, "InlineSourceProvider:HTML-comment"))

            # 标题/文本中的 【XX】
            for m in re.finditer(r"【([A-Za-z0-9&]+)】", snippet):
                book = _book_from_abbr(m.group(1).upper(), abbr_map)
                if book:
                    results.append(SourceCandidate(book, 70, "InlineSourceProvider:【】"))

            # 文本开头直接出现"书名（English Name）"的来源标记（如神炼勇士、荒野守望者）
            if ctx.component_type == "class_archetype":
                lead = snippet[:200]
                for m in re.finditer(r"^([^，,。；;\n]{2,30}?)[（(]([A-Za-z][^）)]{2,})[）)]", lead):
                    book = _match_book_name(m.group(0), cn_map, en_map, abbr_map)
                    if not book:
                        book = _match_book_name(m.group(1).strip(), cn_map, en_map, abbr_map)
                    if not book:
                        book = _match_book_name(m.group(2).strip(), cn_map, en_map, abbr_map)
                    if book:
                        results.append(SourceCandidate(book, 72, "InlineSourceProvider:开头来源书"))

        return results


def resolve_book_sources(ctx: SourceContext) -> Tuple[str, str, str]:
    """按置信度聚合所有 Provider 的候选来源，返回最佳结果。"""
    providers: List[SourceProvider] = [
        ExplicitMarkerProvider(ctx.book_lookup),
        FilenameTokenProvider(ctx.book_lookup),
        ArchetypeMasterProvider(ctx.archetype_masters),
        InlineSourceProvider(ctx.book_lookup),
        DirectoryTocProvider(ctx.book_lookup),
        AggregationTableProvider(),
        ClassDefaultProvider(),
        ContainerDefaultProvider(),
        CRBFallbackProvider(),
    ]

    best: Optional[SourceCandidate] = None
    for provider in providers:
        for candidate in provider.candidates(ctx):
            if best is None or candidate.confidence > best.confidence:
                best = candidate

    if best is None:
        return "未知来源", "?", "?"
    return best.book


# 保留旧函数供兼容调用（内部已改为基于 Provider 的同一逻辑）

def detect_book(
    rel_path: Path,
    source_markers: List[SourceMarker],
    book_lookup: Dict[str, Any],
    md_mapping: Dict[str, Dict[str, Any]],
    title: str = "",
    text: str = "",
    breadcrumbs: Optional[List[str]] = None,
    component_type: str = "",
    class_name: str = "",
    archetype_name: Optional[str] = None,
    block_index: int = 0,
    file_blocks: Optional[List[Dict[str, Any]]] = None,
    archetype_masters: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
) -> Tuple[str, str, str]:
    """基于 Provider 框架推断来源书（兼容旧接口）。"""
    breadcrumbs = breadcrumbs or []
    file_blocks = file_blocks or []
    archetype_masters = archetype_masters or {}
    toc_path = resolve_chm_toc_path(rel_path, source_markers, md_mapping)
    ctx = SourceContext(
        rel_path=rel_path,
        source_markers=source_markers,
        title=title,
        text=text,
        breadcrumbs=breadcrumbs,
        component_type=component_type,
        class_name=class_name,
        archetype_name=archetype_name,
        block_index=block_index,
        file_blocks=file_blocks,
        book_lookup=book_lookup,
        md_mapping=md_mapping,
        toc_path=toc_path,
        archetype_masters=archetype_masters,
    )
    return resolve_book_sources(ctx)


# ---------------------------------------------------------------------------
# 术语表加载
# ---------------------------------------------------------------------------
def load_terms(path: Path) -> Tuple[Dict[str, str], Dict[str, List[str]], List[str]]:
    """返回 (english->english, alias->english, 按长度降序排列的别名列表)。"""
    terms = json.loads(path.read_text(encoding="utf-8"))
    alias_to_english: Dict[str, List[str]] = {}
    term_to_english: Dict[str, str] = {}

    for term in terms:
        english = term["english"]
        term_to_english[english] = english

        aliases = [term.get("recommended", "")] + term.get("other_translations", [])
        for alias in aliases:
            alias = alias.strip()
            if not alias:
                continue
            # 过滤过短或过于宽泛的别名
            if alias in GENERIC_CHINESE_ALIASES:
                continue
            if len(alias) == 1 and not re.match(r"^[A-Za-z]+$", alias):
                continue
            alias_to_english.setdefault(alias, []).append(english)

    # 英文术语自身也参与匹配
    for english in term_to_english:
        alias_to_english.setdefault(english, []).append(english)

    aliases_sorted = sorted(alias_to_english.keys(), key=len, reverse=True)
    return term_to_english, alias_to_english, aliases_sorted


# ---------------------------------------------------------------------------
# 规则书缩写表加载
# ---------------------------------------------------------------------------
def load_abbreviation_table(path: Path) -> Dict[str, Any]:
    """解析规则书缩写对应表，返回 abbr->(中文名,英文名)、中文名->abbr、英文名->abbr 映射。"""
    abbr_to_info: Dict[str, Tuple[str, str, str]] = {}
    cn_to_abbr: Dict[str, str] = {}
    en_to_abbr: Dict[str, str] = {}

    if not path.exists():
        return {"abbr": abbr_to_info, "cn_to_abbr": cn_to_abbr, "en_to_abbr": en_to_abbr}

    text = path.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) < 3:
            continue
        if "英文缩写" in parts or "英文名称" in parts or "中文名称" in parts:
            # 表头
            continue
        en_name, cn_name, abbr = parts[0], parts[1], parts[2]
        if not abbr or abbr == "-":
            continue
        abbr_key = abbr.upper()
        # 中文名可能包含"/"分隔的多个别名，取第一个作为规范来源书名
        cn_primary = re.split(r"[/、，,|]+", cn_name)[0].strip()
        # 保留缩写表原本的 casing（如 AqA），便于输出与缩写表一致
        abbr_to_info[abbr_key] = (cn_primary, en_name, abbr)
        en_to_abbr[en_name] = abbr_key
        # 中文名列可能包含"/"表示多个别名
        for alt in re.split(r"[/、，,|]+", cn_name):
            alt = alt.strip()
            if alt:
                cn_to_abbr[alt] = abbr_key

    # 合并 term_rules 中的标准译名，补齐中文别名
    for en_name, cn_name in SOURCE_BOOK_TRANSLATIONS.items():
        abbr_key = en_to_abbr.get(en_name)
        if not abbr_key:
            continue
        for alt in re.split(r"[/、，,|]+", cn_name):
            alt = alt.strip()
            if alt:
                cn_to_abbr.setdefault(alt, abbr_key)

    return {"abbr": abbr_to_info, "cn_to_abbr": cn_to_abbr, "en_to_abbr": en_to_abbr}


# ---------------------------------------------------------------------------
# CHM TOC 映射加载
# ---------------------------------------------------------------------------
def load_md_mapping(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data
    return {}


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


def has_known_chm_toc_path(
    rel_path: Path,
    source_markers: List[SourceMarker],
    md_mapping: Dict[str, Dict[str, Any]],
) -> bool:
    if _md_mapping_lookup(md_mapping, rel_path.name):
        return True
    for marker in source_markers:
        page = marker.source_page
        if not page:
            continue
        if _md_mapping_lookup(md_mapping, page) or _md_mapping_lookup(md_mapping, Path(page).name):
            return True
    return False


# ---------------------------------------------------------------------------
# 职业名称发现
# ---------------------------------------------------------------------------
def discover_known_classes(input_dir: Path) -> Set[str]:
    known: Set[str] = set()
    for container in CLASS_CONTAINERS:
        container_dir = input_dir / container
        if not container_dir.is_dir():
            continue
        for sub in container_dir.iterdir():
            if sub.is_dir() and any(sub.rglob("*.md")):
                known.add(sub.name)
    return known


# 进阶职业直挂文件标题中的通用词/子章节标题/已知非职业名，不应作为职业名返回
_PRESTIGE_GENERIC_TITLES = {
    "进阶职业", "变体", "职业变体", "职业", "介绍", "概述", "目录",
    "进阶条件", "进阶要求", "生命骰", "本职技能", "职业能力",
    "天赋", "每日法术", "武器和防具擅长", "武器和护甲擅长",
    "要求", "前提条件", "先决条件", "戒律",
    # 已知的聚合/非职业完整标题（精确匹配）
    "地狱骑士戒律",
}

# 进阶职业标题中常见的来源书前缀模式
_PRESTIGE_SOURCE_PREFIX_RES = [
    # 中文书名（英文书名）缩写 职业名
    re.compile(r"^[一-鿿]+(?:[（(][^）)]+[）)])\s*[A-Za-z0-9]*\s+"),
    # 中文书名缩写 职业名（缩写紧贴中文，如 传奇编年史CoL）
    re.compile(r"^[一-鿿]+[A-Za-z0-9]+\s+"),
    # 中文书名 缩写 职业名（如 内海海盗 PIS）
    re.compile(r"^[一-鿿]+\s+[A-Z0-9]+\s+"),
]


def _is_valid_prestige_name(candidate: str) -> bool:
    """候选是否为可用的进阶职业名：非空、含中文、不在通用/无效标题列表中。"""
    return bool(
        candidate
        and re.search(r"[一-鿿]", candidate)
        and candidate not in _PRESTIGE_GENERIC_TITLES
    )


def _extract_prestige_class_name(title: str, rel_path: Path) -> Optional[str]:
    """从进阶职业直挂文件的标题或文件名中提取职业名；无法安全提取时返回 None。"""
    norm_title = _normalize_heading_title(title or "")

    # 1) 先尝试剥除标题开头的来源书前缀
    prefix_matched = False
    for prefix_re in _PRESTIGE_SOURCE_PREFIX_RES:
        stripped = prefix_re.sub("", norm_title, count=1)
        if stripped != norm_title:
            prefix_matched = True
            m = re.match(r"^[一-鿿]+", stripped)
            if m:
                candidate = m.group(0)
                if _is_valid_prestige_name(candidate):
                    return candidate
            # 剥除后没有可用中文 → 继续尝试兜底
            break

    # 2) 三条来源书前缀正则均未匹配时，直接对完整标题取前导连续中文
    if not prefix_matched:
        m = re.match(r"^[一-鿿]+", norm_title)
        if m:
            candidate = m.group(0)
            if _is_valid_prestige_name(candidate):
                return candidate

    # 3) 直接挂在 进阶职业/ 下的文件，文件名通常编码为 <来源书>_<职业名>.md
    parts = rel_path.parts
    if "进阶职业" in parts:
        idx = parts.index("进阶职业")
        # 路径形如 职业/进阶职业/<文件名>.md，且文件名带下划线
        if idx + 1 == len(parts) - 1:
            stem = rel_path.stem
            if "_" in stem:
                candidate = stem.rsplit("_", 1)[-1]
                if _is_valid_prestige_name(candidate):
                    return candidate
    return None


def infer_class_name(
    rel_path: Path,
    title: str,
    breadcrumbs: List[str],
    known_classes: Set[str],
) -> str:
    """从目录路径、变体标题中推断职业名称。

    目录路径（尤其是"职业/核心职业/<职业名>"这种规范结构）比标题里的
    "X变体"标记更稳定。优先按路径推断，避免标题中"圣武士变体"等旧译名
    把圣骑士路径下的变体错分到另一个职业名。
    """
    parts = rel_path.parts

    # 进阶职业：结构为 进阶职业/<来源书>/<进阶职业名>/... 或 进阶职业/<来源书>/page_xxx.md
    if "进阶职业" in parts:
        idx = parts.index("进阶职业")
        # 第 3 层是目录 → 目录名即进阶职业名（如 进阶职业/CRB进阶职业/龙脉术士/...）
        if idx + 2 < len(parts) and not parts[idx + 2].endswith(".md"):
            return parts[idx + 2]
        # 直挂文件（含聚合文件）→ 安全解析标题/文件名，避免来源书前缀或子章节标题被当作职业名
        prestige_class = _extract_prestige_class_name(title, rel_path)
        if prestige_class:
            return prestige_class
        # 无法安全提取 → 落到通用规则，允许 未知职业

    # 1. 从路径中的职业容器推断（最优先）
    for container in CLASS_CONTAINERS:
        if container in parts:
            idx = parts.index(container)
            if idx + 1 < len(parts) and parts[idx + 1] in known_classes:
                return parts[idx + 1]

    # 2. 任意路径部分匹配已知职业名
    for part in parts:
        if part in known_classes:
            return part

    # 自归属容器：路径包含这些目录名时，直接归属为该容器本身
    for container in CONTAINER_SELF_ATTRIBUTION:
        if container in parts:
            return container

    # 3. 从面包屑或标题里的"〔X变体〕"提取基础职业
    # 兼容旧译/补充书格式：前X、UnchainedX、枪手等
    _BASE_CLASS_SYNONYMS = {
        "圣武士": "圣骑士",
        "枪手": "铳手",
    }
    for candidate in breadcrumbs + [title]:
        _, base_class = extract_archetype_info(candidate)
        if not base_class:
            continue
        if base_class.startswith("前"):
            base_class = base_class[1:]
        elif base_class.startswith("Unchained"):
            base_class = base_class[len("Unchained"):]
        base_class = _BASE_CLASS_SYNONYMS.get(base_class, base_class)
        if base_class and base_class in known_classes:
            return base_class

    return "未知职业"


# ---------------------------------------------------------------------------
# 来源书识别
# ---------------------------------------------------------------------------
def _book_from_abbr(abbr_key: str, abbr_map: Dict[str, Tuple[str, str, str]]) -> Optional[Tuple[str, str, str]]:
    abbr_key = ABBR_ALIASES.get(abbr_key, abbr_key)
    if abbr_key in abbr_map:
        cn, en, abbr_original = abbr_map[abbr_key]
        return cn, en, abbr_original
    return None


def _name_variants(part: str) -> List[str]:
    """生成目录名/文件名的可能变体，用于模糊匹配来源书名。"""
    variants = [part]
    # 去掉括号及英文后缀
    stripped = re.split(r"[（(]", part)[0].strip()
    if stripped and stripped != part:
        variants.append(stripped)
    # 形如"位面行者手册PHH"
    m = re.match(r"(.+?)[A-Za-z0-9&]+$", part)
    if m:
        prefix = m.group(1).strip()
        if prefix and prefix not in variants:
            variants.append(prefix)
    # 去掉开头的英文缩写，如"ISM内海魔法"→"内海魔法"
    m = re.match(r"^[A-Za-z0-9&]+(.+)$", part)
    if m:
        no_leading = m.group(1).strip()
        if no_leading and no_leading not in variants:
            variants.append(no_leading)
    # 提取括号内的英文全称
    m = re.search(r"[（(]([A-Za-z][^）)]*)[）)]", part)
    if m:
        eng = m.group(1).strip()
        if eng and eng not in variants:
            variants.append(eng)
    # 去掉"pg. N / p. N / page N / N页"等页码后缀，如"Ultimate Wilderness pg. 70"
    m = re.match(r"^(.+?)\s+(?:pg\.?|p\.?|page)\s*\d+", part, re.IGNORECASE)
    if m:
        no_page = m.group(1).strip()
        if no_page and no_page not in variants:
            variants.append(no_page)
    # 去掉中文"N页"后缀，如"极限荒野71页"
    m = re.match(r"^(.+?)(?:\s+)?\d+\s*页", part)
    if m:
        no_page = m.group(1).strip()
        if no_page and no_page not in variants:
            variants.append(no_page)
    return variants


def _match_book_name(
    part: str,
    cn_map: Dict[str, str],
    en_map: Dict[str, str],
    abbr_map: Dict[str, Tuple[str, str, str]],
) -> Optional[Tuple[str, str, str]]:
    """尝试用中文名或英文名匹配单个目录/文件片段。"""
    for variant in _name_variants(part):
        if variant in cn_map:
            abbr_key = cn_map[variant]
            if abbr_key in abbr_map:
                cn, en, abbr_original = abbr_map[abbr_key]
                return cn, en, abbr_original
        if variant in en_map:
            abbr_key = en_map[variant]
            if abbr_key in abbr_map:
                cn, en, abbr_original = abbr_map[abbr_key]
                return cn, en, abbr_original
    return None


def _extract_title_source_hints(title: str) -> List[str]:
    """从标题里提取可能的来源书缩写，如【ARG】、（MTT 职业变体）。

    只取被明确括号包裹的 token，避免标题中的注释性文字（如
    "该版本在PFS中不可用，请使用UW极限荒野版本"）被误当作来源书。
    """
    hints: List[str] = []
    # 全角/半角方括号、圆括号、尖括号、花括号中的英文缩写
    # 允许缩写后跟中文/空格等非括号字符（如【UC 法师变体】），只提取前置缩写
    for m in re.finditer(r"[（(〔［【<\[]([A-Za-z0-9&']{2,})[^）)〕］\]】>]*[）)〕］\]】>]", title):
        hints.append(m.group(1).upper())
    return hints


def _extract_text_source_hints(text: str) -> List[str]:
    """从正文开头提取"来源：xxx"中的来源书名称/缩写。"""
    hints: List[str] = []
    if not text:
        return hints
    # 只扫描前 500 字，避免误命中；纯文本来源标记往往出现在段首
    snippet = text[:500]
    for m in re.finditer(r"来源[：:]\s*([^，,\n]+)", snippet):
        hints.append(m.group(1).strip())
    # 也匹配"> 来源：位面行者手册（Plane-Hopper's Handbook）PHH"里的缩写
    for m in re.finditer(r"[（(]([A-Za-z][^）)]*)[）)]\s*([A-Za-z0-9&]+)", snippet):
        hints.append(m.group(2).upper())
    # 匹配"出自《极限荒野》（Ultimate Wilderness）"这类纯文本来源标记
    for m in re.finditer(r"出自《([^《》]+)》(?:[（(]([A-Za-z][A-Za-z0-9'\-\s]*)[）)])?", snippet):
        abbr = (m.group(2) or "").strip()
        if abbr:
            hints.append(abbr.upper())
        book_name = m.group(1).strip()
        if book_name:
            hints.append(book_name)
    return hints


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

        title_plain = cm.group(1).strip()
        rest_plain = cm.group(3).strip()
        if not is_ability_heading_text(title_plain, rest_plain):
            out.append(line)
            continue

        # 确认原文在分隔符前确实存在 **，避免把普通句子误拆
        sep_char = cm.group(2)
        sep_idx = s.find(sep_char)
        if sep_idx < 0 or "**" not in s[:sep_idx]:
            out.append(line)
            continue

        level = min(last_level + 1, 5) if last_level else 3
        out.append("#" * level + " " + title_plain)
        if rest_plain:
            out.append(rest_plain)

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


def classify_component(
    title: str,
    breadcrumbs: List[str],
    rel_path: Path,
    level: int,
    md_mapping: Dict[str, Dict[str, Any]],
    known_classes: Set[str],
    archetype_masters: Dict[str, Dict[str, Any]],
) -> str:
    # "X奖励法术"这类章节标题是规则总览，不是具体能力
    if re.search(r"奖励法术$", _normalize_heading_title(title)):
        return "class_overview"

    is_archetype_file = _is_archetype_file(rel_path, md_mapping)
    title_is_archetype = looks_like_archetype_title(
        title, is_archetype_file=is_archetype_file, level=level
    )

    # 若祖先标题属于特性章节（如庇护主、奖励法术等），当前标题不可能是变体
    feature_section_hints = {
        "庇护主", "奖励法术", "巫术", "强力巫术", "高等巫术", "法术", "领域",
        "血承", "狂暴之力", "盗贼天赋", "忍术", "科研发现", "领域", "学派",
    }
    ancestor_is_feature_section = any(
        any(h in _normalize_heading_title(b) for h in feature_section_hints)
        for b in breadcrumbs[:-1]
    )

    # 通过 CHM 基础页变体表确认该标题是变体
    class_name = infer_class_name(rel_path, title, breadcrumbs, known_classes)
    norm_title = _master_key(title)
    in_master = class_name in archetype_masters and norm_title in archetype_masters[class_name]

    if (title_is_archetype or in_master) and not ancestor_is_feature_section:
        # 若祖先中已经存在变体标题，说明当前是变体下的职业能力
        has_archetype_ancestor = any(
            looks_like_archetype_title(
                b, is_archetype_file=is_archetype_file, level=level
            )
            for b in breadcrumbs[:-1]
        )
        # CHM 基础页变体表确认的变体，即使位于上一个变体标题之后，
        # 也应作为独立变体 chunk，而不是被当作前一个变体的职业能力。
        if in_master:
            return "class_archetype"
        # 强变体信号：标题里显式包含"〔/［/（/【 X变体 〕/］/）/】"，
        # 说明是格式被压扁的独立变体，不应被当作前一个变体的子能力。
        strong_archetype_signal = re.search(
            r"[〔［【（].{1,12}?变体[〕］】）]", title
        )
        if strong_archetype_signal:
            return "class_archetype"
        if not has_archetype_ancestor:
            return "class_archetype"

    # 推荐/建议类标题是 Build 建议，不是具体职业能力。
    # 此检查必须在面包屑变体检查之前，因为推荐块可能位于变体下方，
    # 但不应因此被误判为变体下的 class_feature。
    norm = _normalize_heading_title(title)
    if norm.startswith(("推荐", "建议")):
        return "class_recommendation"

    for b in breadcrumbs:
        if looks_like_archetype_title(
            b, is_archetype_file=is_archetype_file, level=level
        ):
            return "class_feature"

    if looks_like_ability_title(title):
        return "class_feature"

    feature_sections = {
        "天赋", "之力", "talent", "deed", "rage power", "discovery",
        "hex", "bomb", "arcana", "order", "domain", "bloodline", "spirit",
        "favored enemy", "rogue talent", "ki power", "祝福", "子域", "秘示域",
    }
    for b in breadcrumbs:
        lower = b.lower()
        if any(k in lower for k in feature_sections):
            return "class_feature"

    return "class_overview"


def infer_feature_subtype(breadcrumbs: List[str]) -> Optional[str]:
    """根据面包屑中最近的节标题推断 feature_subtype。"""
    subtype_mapping = [
        (["高等巫术", "grand hex"], "grand_hex"),
        (["强力巫术", "major hex"], "major_hex"),
        (["巫术", "hex"], "hex"),
        (["庇护主", "patron"], "patron"),
        (["科研发现", "discovery"], "discovery"),
        (["领域", "domain"], "domain"),
        (["血承", "bloodline"], "bloodline"),
        (["狂暴之力", "rage power"], "rage_power"),
        (["盗贼天赋", "rogue talent"], "rogue_talent"),
        (["忍术", "ninja trick"], "ninja_trick"),
        (["流派", "arcane school"], "arcane_school"),
        (["传世名作", "bardic masterpiece"], "bardic_masterpiece"),
        # V006: 低风险 subtype_mapping 扩展
        (["奥术发现", "arcane discovery"], "arcane_discovery"),            # 法师
        (["奥能技艺", "arcanist exploit"], "exploit"),                      # 奥能师
        (["魔战士奥能", "magus arcana"], "arcana"),                          # 魔战士
        (["炫技", "deed"], "deed"),                                          # 铳手/游荡剑客
        (["枪械训练", "gun training"], "gun_training"),                      # 铳手
        (["侠客天赋", "vigilante talent"], "vigilante_talent"),              # 侠客
        (["社交天赋", "social talent"], "social_talent"),                    # 侠客
        (["杀手天赋", "slayer talent"], "slayer_talent"),                    # 杀手
        (["调查员天赋", "investigator talent"], "investigator_talent"),      # 调查员
        (["幻灵亚种", "eidolon subtype"], "eidolon_subtype"),                # 召唤师
        (["精神增幅", "phrenic amplification"], "phrenic_amplification"),    # 异能者
        (["情感羁绊", "emotional focus"], "emotional_focus"),                # 唤魂师
        (["子域", "subdomain"], "subdomain"),                                # 牧师
    ]
    for ancestor in reversed(breadcrumbs):
        norm = _normalize_heading_title(ancestor).lower()
        for keywords, subtype in subtype_mapping:
            if any(kw in norm for kw in keywords):
                return subtype
    return None


def _doc_feature_subtype_hint(rel_path: Path) -> Optional[str]:
    """根据文件路径/名推断该文件主要描述的 feature_subtype，用于补充文件兜底。"""
    name = rel_path.name.lower()
    # 注意顺序：先匹配更具体的"强力/高等"，再匹配"巫术"
    if "强力巫术" in name or "major" in name:
        return "major_hex"
    if "高等巫术" in name or "grand" in name:
        return "grand_hex"
    if "庇护主" in name or "patron" in name:
        return "patron"
    if "巫术" in name or "hex" in name:
        return "hex"
    return None


def _looks_like_concrete_hex_title(title: str) -> bool:
    """判断标题是否像具体的巫术条目，而非章节标题。"""
    norm = _normalize_heading_title(title)
    # 必须含有具体标签或英文名
    if re.search(r"\b(?:Ex|Su|Sp)\b", norm):
        return True
    # 提取括号内的英文，排除纯章节名
    m = re.search(r"[（(]([A-Za-z][^）)]*?)[）)]", norm)
    if m:
        eng = m.group(1).strip()
        generic = {
            "Hex", "Hexes", "Major Hex", "Major Hexes",
            "Grand Hex", "Grand Hexes",
            "Witch Hex", "Witch Hexes", "Spirit Hex",
            "Hex Scar",
        }
        if eng and eng not in generic and not eng.endswith("Spirit Hex"):
            return True
    return False


# ---------------------------------------------------------------------------
# 职业基础页识别与变体主表解析
# ---------------------------------------------------------------------------
def _parse_patron_summary_table(
    text: str,
    book_lookup: Dict[str, Any],
) -> Dict[str, Tuple[str, Tuple[str, str, str]]]:
    """从庇护主总览表格解析每个庇护主的中英文名与来源书。

    总览表格示例：
        | 进阶玩家手册（APG） | 灵巧（Agility） | 阴影（Shadow） |
        | 动物（Animals） | 力量（Strength） |
    返回：{中文名: (英文名, (中文来源, 英文来源, 缩写))}
    """
    abbr_map = book_lookup.get("abbr", {})
    cn_map = book_lookup.get("cn_to_abbr", {})
    en_map = book_lookup.get("en_to_abbr", {})

    patron_books: Dict[str, Tuple[str, Tuple[str, str, str]]] = {}
    current_book: Tuple[str, str, str] = ("未知来源", "?", "?")

    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if any("---" in c for c in cells):
            continue

        for cell in cells:
            if not cell:
                continue

            # 尝试识别来源书单元格
            book = None
            m = re.search(r"[（(]([A-Za-z0-9&]+)[）)]", cell)
            if m:
                book = _book_from_abbr(m.group(1).upper(), abbr_map)
            if not book:
                book = _match_book_name(cell, cn_map, en_map, abbr_map)
            if book:
                current_book = book
                continue

            # 识别庇护主名
            pm = re.search(
                r"^(.+?)\s*[（(]\s*([A-Za-z][A-Za-z0-9'\-]*)\s*[）)]",
                cell,
            )
            if pm:
                cn = pm.group(1).strip()
                en = pm.group(2).strip()
                if cn and cn != "庇护主" and "庇护主" not in en:
                    patron_books[cn] = (en, current_book)

    return patron_books


def _split_patron_reward_tables(
    block: Dict[str, Any],
    book_lookup: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """把"庇护主（Patron）奖励法术"大表格拆成每个庇护主独立块。

    如果块内没有"XX庇护主奖励法术"表格头，则原样返回。
    """
    text = block.get("text", "")
    lines = text.splitlines()

    # 定位每个庇护主奖励法术表格的表头行
    header_indices: List[Tuple[int, str]] = []
    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        for cell in cells:
            m = re.match(r"^(.+?)庇护主奖励法术$", cell)
            if m:
                header_indices.append((i, m.group(1).strip()))
                break

    if not header_indices:
        return [block]

    # 用表头之前的总览表格建立中文→英文/来源书映射
    summary_text = "\n".join(lines[: header_indices[0][0]])
    mapping = _parse_patron_summary_table(summary_text, book_lookup)

    result: List[Dict[str, Any]] = []

    # 总览块：规则说明 + 总览表
    overview = block.copy()
    overview["text"] = "\n".join(lines[: header_indices[0][0]]).strip()
    result.append(overview)

    # 每个庇护主独立成块
    for idx, (start_i, patron_cn) in enumerate(header_indices):
        end_i = header_indices[idx + 1][0] if idx + 1 < len(header_indices) else len(lines)
        patron_lines = lines[start_i:end_i]
        en, book = mapping.get(patron_cn, (None, ("未知来源", "?", "?")))
        title = f"{patron_cn}（{en}）" if en else patron_cn

        sub = block.copy()
        sub["title"] = title
        sub["text"] = "\n".join(patron_lines).strip()
        sub["breadcrumbs"] = block["breadcrumbs"][:] + [title]
        sub["level"] = block.get("level", 1) + 1
        sub["book_override"] = book
        result.append(sub)

    return result


def _split_patron_reward_tables_strategy(
    block: Dict[str, Any],
    ctx: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """庇护主奖励法术大表拆分策略，注册到 WitchProcessor.EXPAND_STRATEGIES。"""
    title = _normalize_heading_title(block.get("title", ""))
    if (
        "庇护主" in title
        or any("庇护主" in _normalize_heading_title(cr) for cr in block.get("breadcrumbs", []))
    ):
        return _split_patron_reward_tables(block, ctx["book_lookup"])
    return [block]


def _normalize_table_row_text(text: str) -> str:
    """把跨行的表格单元格内换行/多余空白压缩成单空格。"""
    return re.sub(r"\s+", " ", text.replace("\n", " ")).strip()


def _iter_witch_hex_table_rows(lines: List[str]) -> List[List[str]]:
    """把 page_92.md 里可能跨行的表格行归并并切分为单元格。

    源文件中的表格单元格经常被硬换行拆开，例如：
        | 巫术 | 凋零（Blight） | 凶兽（Beast
        of Ill-Omen） |
    本函数先把包含 `|` 的连续行合并成完整行，再按 `|` 切分。
    """
    rows: List[List[str]] = []
    buf: List[str] = []

    def _flush() -> None:
        nonlocal buf
        if not buf:
            return
        row_text = _normalize_table_row_text(" ".join(buf))
        buf = []
        if not row_text.startswith("|"):
            return
        cells = [c.strip() for c in row_text.strip("|").split("|")]
        # 跳过分隔线行
        if any("---" in c for c in cells):
            return
        if not any(cells):
            return
        rows.append(cells)

    for line in lines:
        if "|" not in line:
            _flush()
            continue
        buf.append(line)
        if line.rstrip().endswith("|"):
            _flush()

    _flush()
    return rows


def parse_witch_hex_source_table(lines: List[str]) -> Dict[str, Tuple[str, str, str]]:
    """解析 page_92.md 中"巫术/强力/高等巫术 来源 APG/UM"对照表。

    返回 {中文名: (中文来源, 英文来源, 缩写)}，仅包含 UM 列的条目。
    """
    um_hexes: Dict[str, Tuple[str, str, str]] = {}
    for cells in _iter_witch_hex_table_rows(lines):
        # 正常数据行：3 列（章节/APG/UM）；续行：2 列（APG/UM）
        if len(cells) >= 3:
            um_cell = cells[2]
        elif len(cells) == 2:
            um_cell = cells[1]
        else:
            continue

        um_cell = _normalize_table_row_text(um_cell)
        if not um_cell:
            continue

        for m in re.finditer(
            r"([一-鿿]+)\s*（\s*([A-Za-z][A-Za-z0-9'’\-\s]*)\s*）",
            um_cell,
        ):
            cn = m.group(1).strip()
            if cn and cn not in ("巫术", "强力巫术", "高等巫术"):
                um_hexes[cn] = _UM
    return um_hexes


def classify_base_page(toc_path: str) -> Tuple[str, str]:
    """根据 CHM TOC 路径末级判断文件属于哪类职业基础页。"""
    if not toc_path:
        return "supplement", ""
    last = toc_path.split(" → ")[-1]
    if last in ("职业变体", "变体"):
        return "archetype_base", ""
    if last == "巫术/庇护主":
        return "feature_base", "witch_hex_patron"
    if last == "科研发现":
        return "feature_base", "alchemist_discovery"
    if last == "法术列表":
        return "spell_list_base", ""
    if last in ("职业特性", "特色专长", "领域", "血承", "流派"):
        return "feature_base", ""
    return "supplement", ""


def _is_archetype_base_page(
    rel_path: Path,
    md_mapping: Dict[str, Dict[str, Any]],
    cleaned_lines: Optional[List[str]] = None,
) -> bool:
    """判断文件是否为职业变体基础页（优先 CHM TOC，回退目录/内容启发式）。"""
    toc_path = resolve_chm_toc_path(rel_path, [], md_mapping)
    if classify_base_page(toc_path)[0] == "archetype_base":
        return True

    # 回退：职业容器下、以 page_*.md 结尾的文件，若首标题含"职业变体/变体"则视为基础页
    parts = rel_path.parts
    if len(parts) >= 3 and parts[-1].startswith("page_") and parts[-1].endswith(".md"):
        if parts[-3] in CLASS_CONTAINERS:
            if cleaned_lines:
                heading_re = re.compile(r"^(#{1,6})\s+(.*)$")
                for line in cleaned_lines:
                    m = heading_re.match(line)
                    if not m:
                        continue
                    # 只检查首个 heading；后续 heading 可能是能力/变体子标题，
                    # 不能代表整页类型（如 page_71.md 是科研发现页，后续才有变体标题）
                    return "变体" in m.group(2) or "Archetype" in m.group(2)
    return False


def _looks_like_source_cell(cell: str) -> bool:
    """判断单元格是否包含规则书来源信息（中文书名或英文缩写）。"""
    cell = cell.strip()
    if not cell:
        return False
    # 包含括号内的英文缩写，例如 终极魔法（UM）
    if re.search(r"[（(][A-Za-z0-9&]{2,}[）)]", cell):
        return True
    # 包含已知中文书名关键词（粗略判断）
    if re.search(r"(?:核心|进阶|极限|异能|神话|解放|荒野|内海|位面|冒险|指南|手册|志|英雄)", cell):
        return True
    return False


def _parse_source_cell(
    cell: str,
    book_lookup: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """从表格来源单元格解析出（中文名、英文名、缩写）。"""
    abbr_map = book_lookup.get("abbr", {})
    cn_map = book_lookup.get("cn_to_abbr", {})
    en_map = book_lookup.get("en_to_abbr", {})

    # 优先取括号内的英文缩写
    for token in re.findall(r"[（(]([A-Za-z0-9&]+)[）)]", cell):
        abbr = token.upper()
        abbr = ABBR_ALIASES.get(abbr, abbr)
        if abbr in abbr_map:
            cn, en, abbr_original = abbr_map[abbr]
            return cn, en, abbr_original

    # 尝试按中文/英文书名匹配
    result = _match_book_name(cell, cn_map, en_map, abbr_map)
    if result:
        return result

    return None, None, None


def _parse_variant_name_cell(cell: str) -> Tuple[Optional[str], Optional[str], bool]:
    """从表格变体名单元格解析（中文名、英文名、是否已废弃）。"""
    is_deprecated = "~~" in cell
    norm = cell.replace("*", "").replace("~", "").strip()

    # 名称（English Name，备注） 或 名称（English Name）
    m = re.search(
        r"(.+?)\s*[（(]\s*([A-Za-z][A-Za-z0-9'\-\s]*?)\s*(?:[,，]\s*[^）)]*)?[）)]",
        norm,
    )
    if m:
        chinese = m.group(1).strip()
        english = m.group(2).strip()
        return chinese, english, is_deprecated

    if len(norm) >= 2:
        return norm, None, is_deprecated

    return None, None, is_deprecated


def parse_archetype_master_table(
    lines: List[str],
    book_lookup: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """解析变体基础页顶部的来源-变体表，建立变体名到来源的映射。

    返回 dict：{normalized_title: {...}}

    改进点：
    1. 预处理表格，合并因清洗仍被拆开的单元格；
    2. last_source 仅在成功解析到新来源时才更新，避免失败来源污染后续行；
    3. 支持"来源|变体|备注"三列及变体名单列；
    4. 对无法识别的来源行给出警告并跳过。
    """
    # 1. 先提取并合并第一个连续 markdown 表格
    #    CHM 转换后的表格常把单个单元格拆成多行（第二行以空格缩进），
    #    先把这些续行拼回上一行的末尾，再按单元格解析。
    table_lines: List[str] = []
    in_table = False
    for line in lines:
        s = line.strip()
        if s.startswith("|"):
            in_table = True
            table_lines.append(s)
        elif in_table and s:
            # 表格内部的非空续行（通常以空格开头），拼到上一个 | 行末尾
            if table_lines:
                table_lines[-1] = table_lines[-1].rstrip() + " " + s
        elif in_table and not s:
            # 空行标志表格结束
            break

    if not table_lines:
        return {}

    # 2. 合并跨行单元格：如果下一行也以 | 开头，且上一行最后一个单元格未闭合
    #    （即上一行结尾无 |，或合并后单元格数与表头不一致），则把它接到上一行末尾。
    merged_lines: List[str] = []
    for line in table_lines:
        if merged_lines and line.startswith("|"):
            # 简单策略：如果上一行不以 | 结尾，或上一行拆分后最后一个单元格非空且当前行拆分后第一个单元格非空，
            # 说明上一行可能被截断，尝试合并。
            prev = merged_lines[-1]
            if not prev.rstrip().endswith("|"):
                merged_lines[-1] = prev.rstrip() + " " + line.lstrip()
                continue
            # 若当前行第一个非空单元格看起来像上一行最后一个单元格的延续，也合并
            prev_cells = [c.strip() for c in prev.strip("|").split("|")]
            cur_cells = [c.strip() for c in line.strip("|").split("|")]
            if (
                prev_cells
                and cur_cells
                and prev_cells[-1]
                and cur_cells[0]
                and not _looks_like_source_cell(cur_cells[0])
                and not _parse_variant_name_cell(cur_cells[0])[0]
            ):
                prev_cells[-1] = prev_cells[-1] + " " + cur_cells[0]
                merged_lines[-1] = "| " + " | ".join(prev_cells) + " |"
                continue
        merged_lines.append(line)

    # 3. 解析合并后的表格
    masters: Dict[str, Dict[str, Any]] = {}
    last_source: Tuple[Optional[str], Optional[str], Optional[str]] = (None, None, None)
    header_col_count: Optional[int] = None

    for line in merged_lines:
        cells = [c.strip() for c in line.strip("|").split("|")]
        # 跳过表头、分隔线、空行
        if any("---" in c for c in cells):
            if header_col_count is None:
                header_col_count = len(cells)
            continue
        if any(c in ("来源书", "变体名", "来源", "变体") for c in cells):
            if header_col_count is None:
                header_col_count = len(cells)
            continue
        if not cells or not any(cells):
            continue

        # 识别本行中的来源单元格与变体单元格，支持一行多列变体
        row_sources: List[Tuple[Optional[str], Optional[str], Optional[str]]] = []
        variant_cells: List[str] = []
        for cell in cells:
            if not cell:
                continue
            if _looks_like_source_cell(cell):
                parsed = _parse_source_cell(cell, book_lookup)
                if parsed[0]:
                    row_sources.append(parsed)
                    continue
                # 看起来像来源但解析失败（如"医护骑士（Hospitaler）"被括号英文误判），
                # 回退为变体名处理。
            variant_cells.append(cell)

        if row_sources:
            source = row_sources[-1]
            last_source = source
        else:
            source = last_source

        for variant_cell in variant_cells:
            if not variant_cell:
                continue
            chinese, english, is_deprecated = _parse_variant_name_cell(variant_cell)
            if not chinese:
                continue

            info = {
                "chinese_name": chinese,
                "english_name": english,
                "source_book": source[0] if source else None,
                "source_book_english": source[1] if source else None,
                "book_abbreviation": source[2] if source else None,
                "is_deprecated": is_deprecated,
            }
            masters[_normalize_heading_title(chinese)] = info
            if english:
                masters[_normalize_heading_title(english)] = info

    return masters


def _inject_missing_archetype_headings(
    blocks: List[Dict[str, Any]],
    rel_path: Path,
    ctx: Dict[str, Any],
    cleaned_lines: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """对职业基础页的变体主表，补充只有表行、没有独立 heading 的变体块。

    这类变体常见于来源书未单独整理出详情页的条目；注入一个带来源与职业标记的
    level-2 heading，使其能生成 class_archetype chunk，避免 MISSING。
    """
    if not blocks:
        return blocks

    first = blocks[0]

    # 若当前文件缺少 level-1 基础页标题（如 CHM 导出把 `# 职业变体` 弄成了纯文本），
    # 且清洗后的首行看起来像基础页标题，则合成一个 level-1 标题块，让后续注入能进行。
    if first.get("level") != 1 and cleaned_lines:
        for line in cleaned_lines:
            s = line.strip()
            if not s:
                continue
            # 跳过来源标记注释行；它们不是标题
            if s.startswith("<!--"):
                continue
            if "变体" in s or "Archetype" in s:
                # 去掉首尾加粗/删除线标记，保留标题核心
                synth_title = re.sub(r"^[*~]+", "", s)
                synth_title = re.sub(r"[*~]+$", "", synth_title).strip()
                if synth_title:
                    first = {
                        "title": synth_title,
                        "level": 1,
                        "breadcrumbs": [synth_title],
                        "text": "",
                        "markers": [],
                    }
                    blocks = [first] + blocks
                    break
            # 只考虑第一个有意义的非注释行
            break

    if first.get("level") != 1:
        return blocks

    first_title = first.get("title", "")
    if "变体" not in first_title and "Archetype" not in first_title:
        return blocks

    known_classes = ctx.get("known_classes", set())
    class_name = infer_class_name(rel_path, "", [], known_classes)
    masters = ctx.get("archetype_masters", {}).get(class_name, {})
    if not masters:
        return blocks

    existing_keys = set()
    for b in blocks:
        title = b.get("title", "")
        existing_keys.add(_master_key(title))

    injected: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for key, info in masters.items():
        # masters 同时以中文名和英文名做键，只取中文键
        if not re.search(r"[一-鿿]", key):
            continue
        cn = info.get("chinese_name", key)
        if not cn:
            continue
        cn_key = _master_key(cn)
        if cn_key in existing_keys or cn_key in seen:
            continue
        seen.add(cn_key)

        eng = info.get("english_name") or ""
        abbr = info.get("book_abbreviation") or "?"
        source_book = info.get("source_book") or "未知来源"
        source_book_en = info.get("source_book_english") or "?"

        # 标题格式：中文名（English）【ABBR 职业变体】，保证 looks_like_archetype_title 命中
        if eng:
            heading_title = f"{cn}（{eng}）【{abbr} {class_name}变体】"
        else:
            heading_title = f"{cn}【{abbr} {class_name}变体】"
        body = f"来源：{source_book}（{source_book_en}）"
        injected.append({
            "title": heading_title,
            "level": 2,
            "breadcrumbs": [first.get("title", rel_path.as_posix()), heading_title],
            "text": body,
            "markers": [],
        })

    if not injected:
        return blocks

    return [first] + injected + blocks[1:]


# ---------------------------------------------------------------------------
# 术语命中
# ---------------------------------------------------------------------------
# extract_terms 的搜索器缓存：把 ASCII 别名预编译成正则，非 ASCII 别名用子串匹配
_terms_searcher_cache: Dict[Tuple[str, ...], List[Tuple[str, str, Any]]] = {}


def _build_term_searchers(
    alias_to_english: Dict[str, List[str]],
    aliases_sorted: List[str],
) -> List[Tuple[str, str, Any]]:
    """构建术语搜索器列表：每个元素为 (alias, english, compiled_pattern_or_None)。

    ASCII 别名预编译带单词边界的正则；非 ASCII 别名使用 None 表示子串匹配。
    """
    searchers: List[Tuple[str, str, Any]] = []
    for alias in aliases_sorted:
        english = alias_to_english[alias][0]
        if alias.isascii():
            pattern = r"(?<![A-Za-z])" + re.escape(alias) + r"(?![A-Za-z])"
            try:
                compiled = re.compile(pattern)
            except re.error:
                # 极个别别名可能产生非法正则，降级为子串匹配
                compiled = None
            searchers.append((alias, english, compiled))
        else:
            searchers.append((alias, english, None))
    return searchers


def extract_terms(
    text: str,
    alias_to_english: Dict[str, List[str]],
    aliases_sorted: List[str],
) -> Tuple[List[str], List[str]]:
    terms_set: Set[str] = set()
    aliases_hit: Set[str] = set()

    key = tuple(aliases_sorted)
    searchers = _terms_searcher_cache.get(key)
    if searchers is None:
        searchers = _build_term_searchers(alias_to_english, aliases_sorted)
        _terms_searcher_cache[key] = searchers

    for alias, english, compiled in searchers:
        if compiled is not None:
            matched = compiled.search(text) is not None
        else:
            matched = alias in text
        if matched:
            terms_set.add(english)
            aliases_hit.add(alias)

    return sorted(terms_set), sorted(aliases_hit)


# ---------------------------------------------------------------------------
# 质量过滤
# ---------------------------------------------------------------------------
def is_pure_table_or_nav(text: str) -> bool:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return True
    markup = sum(
        1
        for l in lines
        if l.startswith("|")
        or l.startswith("---")
        or l.startswith("<!--")
        or l.startswith(">")
    )
    return markup / len(lines) >= 0.8


def _looks_like_class_table(text: str) -> bool:
    """判断文本是否像职业等级进度表（BAB/豁免/每日法术）。"""
    t = text.replace(" ", "")
    return (
        "基本攻击加值" in t
        and "强韧豁免" in t
        and "反射豁免" in t
        and "意志豁免" in t
        and "等级" in t
    )


def _split_oversized_class_table(block: Dict[str, Any]) -> List[Dict[str, Any]]:
    """把超过 MAX_CHUNK_CHARS 且内含职业表的 block 拆成描述部分 + 职业表部分。

    拆分点定位第一个 `| 表：职业名 |` 行。
    """
    text = block.get("text", "")
    m = re.search(r"^\|\s*表[：:]\s*.+?$", text, re.MULTILINE)
    if not m:
        return [block]

    desc_text = text[: m.start()].strip()
    table_text = text[m.start() :].strip()
    if not desc_text or not table_text:
        return [block]

    # 提取表标题，如 "| 表：女巫 |" → "表：女巫"
    caption = re.sub(r"^\|\s*表[：:]\s*|\s*\|.*$", "", m.group(0)).strip()
    table_title = f"表：{caption}" if caption else "职业表"

    results: List[Dict[str, Any]] = []
    if desc_text:
        desc = block.copy()
        desc["text"] = desc_text
        results.append(desc)

    table_block = block.copy()
    table_block["title"] = table_title
    table_block["text"] = table_text
    table_block["breadcrumbs"] = block["breadcrumbs"] + [table_title]
    table_block["level"] = block.get("level", 1) + 1
    results.append(table_block)
    return results


# ---------------------------------------------------------------------------
# 核心处理流程
# ---------------------------------------------------------------------------


def _canonical_score(path: Path, book_lookup: Dict[str, Any]) -> int:
    """给去重候选路径打分，优先保留来源信息更完整的副本。"""
    score = 0
    abbr_map = book_lookup.get("abbr", {})
    cn_map = book_lookup.get("cn_to_abbr", {})

    if not path.name.startswith("page_"):
        score += 1

    for token in re.findall(r"[A-Za-z]{2,}", path.name):
        if token.upper() in abbr_map:
            score += 2

    for part in path.parts:
        if part in cn_map:
            score += 1

    return score


def create_processor(
    file_path: Path,
    rel_path: Path,
    ctx: Dict[str, Any],
) -> "FileProcessor":
    """根据 rel_path 创建对应的文件处理器。

    女巫相关文件统一使用 WitchProcessor，使其能注入职业特化的来源书覆盖、
    subtype 推断和庇护主奖励法术拆分策略；其中注册过的补充书额外带上条目表。
    """
    doc_id = rel_path.as_posix()
    spec = WITCH_SUPPLEMENT_REGISTRY.get(doc_id)
    if "女巫" in rel_path.parts:
        return WitchProcessor(file_path, rel_path, ctx, spec)
    if "圣骑士" in rel_path.parts or "圣武士" in rel_path.parts:
        return PaladinProcessor(file_path, rel_path, ctx)
    # V006: 中风险职业 → 类隔离 Processor
    if "先知" in rel_path.parts:
        return OracleProcessor(file_path, rel_path, ctx)
    if "术士" in rel_path.parts:
        return SorcererProcessor(file_path, rel_path, ctx)
    if "战斗祭司" in rel_path.parts:
        return WarpriestProcessor(file_path, rel_path, ctx)
    if "召唤师" in rel_path.parts:
        return SummonerProcessor(file_path, rel_path, ctx)
    if "变形者" in rel_path.parts:
        return ShifterProcessor(file_path, rel_path, ctx)
    return FileProcessor(file_path, rel_path, ctx)


def _format_reward_spells(text: str) -> List[str]:
    """把奖励法术列表按等级切分成多行。"""
    # 中文等级：2级——
    text = re.sub(r"(\d+级——)", r"\n\1", text)
    # 英文序数：2nd— / 4th— / 1st— / 3rd—
    text = re.sub(r"(\d+(?:st|nd|rd|th)—)", r"\n\1", text)
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _strip_entry_prefix(segment: str, _entry: StructureEntry) -> str:
    """去掉条目段首的 "中文名（English, tag）：" 等前缀，留下正文。"""
    # 去掉标题残留：英文括号、tag、冒号、星号等；保留数字（如 "2级——"）
    segment = re.sub(r"^[\s,，）\)\*:：]+", "", segment).strip()
    # 源文件偶有 " , SU）" 这类大写 tag 残留，再清一次
    segment = re.sub(r"^(?:\s*(?:Ex|Su|Sp)\s*[）)])?\s*[,，）\)\*:：]*", "", segment, flags=re.IGNORECASE).strip()
    return segment


def _english_anchor_pattern(en: str) -> str:
    """为英文能力名构造容错正则（忽略大小写、空格、逗号、撇号、弯引号）。"""
    words = re.split(r"[\s'’]+", en)
    parts = []
    for w in words:
        parts.append("".join(f"[{c.lower()}{c.upper()}]" if c.isalpha() else re.escape(c) for c in w))
    return r"[\s'’]*".join(parts)


def _entry_anchor_pattern(entry: StructureEntry) -> str:
    """条目锚点：中文名（English Name，容忍大小写/空格/标点）。"""
    en_pat = _english_anchor_pattern(entry.en)
    return re.escape(entry.cn) + r"\s*（\s*" + en_pat + r"(?=[\s,，）)])"


def _section_subtype(section: str) -> str:
    if "庇护主" in section:
        return "patron"
    if "强力" in section:
        return "major_hex"
    if "高等" in section:
        return "grand_hex"
    return "hex"


def _find_anchors(
    text: str,
    spec: SupplementSpec,
) -> List[Tuple[int, int, str, Any]]:
    """在压缩文本中定位所有章节与条目锚点。

    返回 [(start, end, kind, data)]，按 start 排序。kind 为 "section" 或 "entry"。
    """
    text = text.replace("*", "")

    # 1. 条目锚点：优先用 "中文名（English" 定位；源文件未给出英文名时，
    #    退回到 "章节关键词 + 中文名" 定位（如 HotHC 的保护）。
    entry_anchors: List[Tuple[int, int, str, StructureEntry]] = []
    for entry in spec.entries:
        found = False
        for m in re.finditer(_entry_anchor_pattern(entry), text):
            entry_anchors.append((m.start(), m.end(), "entry", entry))
            found = True
        if found:
            continue
        # Fallback：章节关键词 + 中文名
        for sec in spec.sections:
            pat = re.escape(sec) + r"(\s*)" + re.escape(entry.cn)
            for m in re.finditer(pat, text):
                entry_start = m.start() + len(sec) + len(m.group(1))
                entry_end = entry_start + len(entry.cn)
                entry_anchors.append((entry_start, entry_end, "entry", entry))
    entry_anchors.sort()

    filtered_entries: List[Tuple[int, int, str, StructureEntry]] = []
    prev_end = -1
    for a in entry_anchors:
        if a[0] < prev_end:
            continue
        filtered_entries.append(a)
        prev_end = a[1]

    # 2. 章节锚点：对每个章节，取同 subtype 的第一个条目，向前找最近的章节关键词
    subtype_first_entry: Dict[str, StructureEntry] = {}
    for entry in spec.entries:
        if entry.subtype not in subtype_first_entry:
            subtype_first_entry[entry.subtype] = entry

    section_anchors: List[Tuple[int, int, str, str]] = []
    for sec in spec.sections:
        subtype = _section_subtype(sec)
        first_entry = subtype_first_entry.get(subtype)
        if not first_entry:
            continue
        first_anchor = next((a for a in filtered_entries if a[3].subtype == subtype), None)
        if not first_anchor:
            continue
        first_start = first_anchor[0]
        best = None
        for m in re.finditer(re.escape(sec), text):
            if m.end() <= first_start:
                best = m
            else:
                break
        if best:
            section_anchors.append((best.start(), best.end(), "section", sec))

    anchors: List[Tuple[int, int, str, Any]] = section_anchors + filtered_entries
    anchors.sort()

    # 跳过重叠
    filtered: List[Tuple[int, int, str, Any]] = []
    prev_end = -1
    for start, end, kind, data in anchors:
        if start < prev_end:
            continue
        filtered.append((start, end, kind, data))
        prev_end = end

    return filtered


def structure_supplement(
    lines: List[str],
    spec: SupplementSpec,
    doc_id: str,
) -> List[str]:
    """把单行压缩的女巫补充文件改写成标准 Markdown 结构。

    输出保留文件级标题、来源引用和 HTML 注释，只把正文段落按条目表拆分。
    为了让每个子 chunk 都能追溯到来源书，把文件顶部的来源引用行追加到
    每个章节/条目的输出中。
    """
    preserved: List[str] = []
    body_lines: List[str] = []

    for line in lines:
        s = line.strip()
        if not s:
            preserved.append(line)
            continue
        # 保留文件级标题 (# / ##)、来源引用、HTML 注释
        if re.match(r"^#{1,2}\s+", line) or s.startswith(">") or s.startswith("<!--"):
            preserved.append(line)
            continue
        body_lines.append(s)

    if not body_lines:
        return lines

    body_text = "\n".join(body_lines)
    anchors = _find_anchors(body_text, spec)

    # 任何条目表中的条目定位失败都报错
    found_entries = {data.cn for _, _, kind, data in anchors if kind == "entry"}
    expected_entries = {e.cn for e in spec.entries}
    missing = expected_entries - found_entries
    if missing:
        raise ValueError(f"[{doc_id}] 条目表中的以下条目未在正文中定位: {sorted(missing)}")

    # 发现未登记的疑似标题时输出警告（仅在条目段首扫描，避免奖励法术列表里的法术名触发噪音）
    heading_like_re = re.compile(r"[一-鿿]{2,12}（[A-Za-z][A-Za-z0-9'’\- ]*(?:\s*,\s*(?:Ex|Su|Sp))?[）)]")
    for idx, (start, end, kind, data) in enumerate(anchors):
        if kind != "entry":
            continue
        next_start = anchors[idx + 1][0] if idx + 1 < len(anchors) else len(body_text)
        segment_head = body_text[end:next_start][:120]
        # 去掉段首残留 tag/标点，真正的下一个标题应当出现在最前面
        head_stripped = re.sub(
            r"^(?:\s*(?:Ex|Su|Sp)\s*[）)])?\s*[,，）\)\*:：]*",
            "",
            segment_head,
            flags=re.IGNORECASE,
        )
        m = heading_like_re.match(head_stripped)
        if m:
            cn = re.match(r"[一-鿿]+", m.group(0)).group(0)
            if cn not in expected_entries and cn not in {sec for sec in spec.sections}:
                print(f"WARN [{doc_id}] 发现未登记疑似标题: {m.group(0)}", file=sys.stderr)

    # 提取文件顶部的来源引用行，供后续每个条目复用
    source_ref_line = next(
        (ln for ln in preserved if ln.strip().startswith(">") and "来源" in ln),
        None,
    )

    out = preserved[:]
    for idx, (start, end, kind, data) in enumerate(anchors):
        if kind == "section":
            out.append("## " + data)
        else:
            title = f"### {data.cn}（{data.en}）" if not data.tag else f"### {data.cn}（{data.en}, {data.tag}）"
            out.append(title)
            # 把来源引用行追加到每个条目，使子 chunk 也能识别来源书
            if source_ref_line:
                out.append(source_ref_line)

        next_start = anchors[idx + 1][0] if idx + 1 < len(anchors) else len(body_text)
        segment = body_text[end:next_start].strip()
        if kind == "entry":
            segment = _strip_entry_prefix(segment, data)
        else:
            # 章节段首可能粘着章节名自身或多余符号
            segment = re.sub(r"^" + re.escape(data) + r"[\s：:*]*", "", segment).strip()

        if segment:
            for ln in _format_reward_spells(segment):
                out.append(ln)

    return out




class FileProcessor:
    """文件级处理器（薄封装）。

    默认实现全部委托现有模块级函数，行为与改造前一致。
    职业/规则书特有的逻辑通过子类覆盖 clean / expand 等钩子实现。
    """

    def __init__(
        self,
        file_path: Path,
        rel_path: Path,
        ctx: Dict[str, Any],
    ) -> None:
        self.file_path = file_path
        self.rel_path = rel_path
        self.ctx = ctx
        self.doc_id = rel_path.as_posix()
        self.doc_subtype_hint: Optional[str] = _doc_feature_subtype_hint(rel_path)
        self.raw_block_count = 0
        self.file_class_name: Optional[str] = None

    # ---------------------------------------------------------------------
    # 可覆盖钩子
    # ---------------------------------------------------------------------
    def clean(self, lines: List[str]) -> Tuple[List[str], Set[str]]:
        """清洗文件，返回干净的行列表和删除线标题集合。"""
        return clean_file(self.file_path, self.ctx["md_mapping"])

    def split(self, lines: List[str]) -> List[Dict[str, Any]]:
        """把清洗后的行拆成 block。"""
        return split_into_blocks(lines, self.doc_id)

    # 可注册的展开策略；基类为空，子类通过覆写/追加注入职业特化逻辑
    EXPAND_STRATEGIES: List[Any] = []

    def expand(self, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """拆分/展开特殊结构。策略通过 EXPAND_STRATEGIES 注册，保持基类通用。"""
        for strategy in self.EXPAND_STRATEGIES:
            new_blocks: List[Dict[str, Any]] = []
            for b in blocks:
                new_blocks.extend(strategy(b, self.ctx))
            blocks = new_blocks

        # 对职业基础页补充表行变体（无独立 heading 的变体）
        cleaned_lines = getattr(self, "cleaned_lines", None)
        blocks = _inject_missing_archetype_headings(
            blocks, self.rel_path, self.ctx, cleaned_lines
        )

        # 把超过字数上限且内含职业等级表的大块拆成"描述 + 职业表"
        result: List[Dict[str, Any]] = []
        for b in blocks:
            if len(b.get("text", "")) > MAX_CHUNK_CHARS and _looks_like_class_table(b.get("text", "")):
                result.extend(_split_oversized_class_table(b))
            else:
                result.append(b)
        return result

    def merge(self, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """合并过小的相邻块。"""
        is_archetype_file = _is_archetype_file(self.rel_path, self.ctx["md_mapping"])
        return merge_small_blocks(blocks, is_archetype_file=is_archetype_file)

    # -----------------------------------------------------------------
    # Chunk 构建模板方法
    # -----------------------------------------------------------------
    def build_chunk(
        self,
        block: Dict[str, Any],
        deprecated_titles: Set[str],
        block_index: int = 0,
        file_blocks: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Chunk]:
        """把单个 block 构建成 Chunk；子类可覆盖整个流程或其中某个子钩子。"""
        text = block["text"].strip()
        if not text:
            return None

        title = block["title"]
        breadcrumbs = block["breadcrumbs"]
        level = block["level"]
        source_markers: List[SourceMarker] = block.get("markers", [])

        # 继承父块来源标记：对本块无标记但有父块标记的情形，
        # 基于 breadcrumbs 找到父块并继承标记。
        # 解决 B3 修复后 feature 子块（### 级）仍无标记的问题。
        # 逐级向上查找（breadcrumbs[:-1], breadcrumbs[:-2], ...），
        # 跳过"出自《Pathfinder #N:...》"等非内容标题中间块。
        if not source_markers and file_blocks and len(breadcrumbs) > 1:
            target_doc = getattr(self, 'doc_id', '')
            for i in range(len(breadcrumbs) - 1, 0, -1):
                parent_crumbs = breadcrumbs[:i]
                found = None
                for fb in file_blocks:
                    if fb.get("breadcrumbs") == parent_crumbs:
                        pm = fb.get("markers", [])
                        found = (fb.get("title", "")[:40], pm)
                        if pm:
                            source_markers = [
                                SourceMarker(m.source_book_abbr, m.source_page, m.raw)
                                for m in pm
                            ]
                        break
                if source_markers:
                    break
            # 若 file_blocks 中未找到（H2/H3 被 merge 合并导致 breadcrumbs 改变），
            # 回退到 merge 前缓存的显式标记，逐级向上查找。
            if not source_markers:
                marker_cache = getattr(self, '_explicit_marker_cache', {})
                if marker_cache:
                    for i in range(len(breadcrumbs) - 1, 0, -1):
                        parent_key = tuple(breadcrumbs[:i])
                        if parent_key in marker_cache:
                            source_markers = [
                                SourceMarker(m.source_book_abbr, m.source_page, m.raw)
                                for m in marker_cache[parent_key]
                            ]
                            break

        component_type = self.classify_component(title, breadcrumbs, level)
        class_name = self.infer_class_name(title, breadcrumbs)
        archetype_name = self.infer_archetype_name(title, breadcrumbs, component_type, level)
        master_info = self.get_archetype_master(class_name, title)

        # 来源书判定使用规范职业名（优先路径推断），避免标题中的"圣武士"与路径中的"圣骑士"不一致
        # 导致变体主表 miss。
        source_class_name = class_name
        archetype_masters = self.ctx.get("archetype_masters", {})
        known_classes = self.ctx.get("known_classes", set())
        if source_class_name not in archetype_masters:
            path_class_name = infer_class_name(self.rel_path, "", [], known_classes)
            if path_class_name in archetype_masters:
                source_class_name = path_class_name

        book_source, book_source_english, book_abbreviation = self.resolve_source(
            source_markers, title, text, breadcrumbs, component_type, source_class_name, archetype_name,
            master_info, block_index, file_blocks
        )

        book_override = block.get("book_override")
        if book_override:
            book_source, book_source_english, book_abbreviation = book_override

        chm_toc_path = self.resolve_chm_toc_path(source_markers)
        terms, aliases = self.extract_terms(text)
        feature_subtype = self.infer_feature_subtype(breadcrumbs, title, component_type, archetype_name)

        # 通用 subtype 修正（class_recommendation 无 subtype）
        if component_type == "class_recommendation":
            feature_subtype = None
        elif component_type == "class_feature":
            if archetype_name and feature_subtype:
                feature_subtype = None
            if feature_subtype == "patron" and re.search(r"\b(?:Ex|Su|Sp)\b", title):
                feature_subtype = None
            if feature_subtype in ("hex", "major_hex", "grand_hex") and not _looks_like_concrete_hex_title(title):
                feature_subtype = None

        is_deprecated = self.is_deprecated(title, component_type, deprecated_titles, master_info)

        return Chunk(
            chunk_id=self._make_chunk_id(title, text),
            doc_id=self.doc_id,
            source_paths=[self.doc_id],
            category="职业",
            component_type=component_type,
            class_name=class_name,
            archetype_name=archetype_name,
            book_source=book_source,
            book_source_english=book_source_english,
            book_abbreviation=book_abbreviation,
            chm_toc_path=chm_toc_path,
            title=title,
            heading_breadcrumbs=breadcrumbs,
            source_markers=[asdict(m) for m in source_markers],
            terms=terms,
            aliases=aliases,
            feature_subtype=feature_subtype,
            is_deprecated=is_deprecated,
            char_count=len(text),
            text=text,
        )

    # -----------------------------------------------------------------
    # 子钩子：可被 WitchProcessor 等子类覆盖
    # -----------------------------------------------------------------
    def classify_component(self, title: str, breadcrumbs: List[str], level: int) -> str:
        component_type = classify_component(
            title,
            breadcrumbs,
            self.rel_path,
            level,
            self.ctx["md_mapping"],
            self.ctx["known_classes"],
            self.ctx["archetype_masters"],
        )
        # 职业基础页（职业 → 容器 → 职业名）的顶层标题（如"女巫（Witch）"）
        # 不应因含英文括号被误判为 class_feature，应作为 class_overview。
        if (
            component_type == "class_feature"
            and len(breadcrumbs) == 2
            and level == 2
            and self._is_base_class_page()
        ):
            return "class_overview"
        return component_type

    def _is_base_class_page(self) -> bool:
        """判断当前文件是否为职业基础页（CHM TOC 路径为 职业/容器/职业名）。"""
        toc = resolve_chm_toc_path(self.rel_path, [], self.ctx["md_mapping"])
        parts = toc.split(" → ")
        return len(parts) == 3 and parts[0] == "职业"

    def infer_class_name(self, title: str, breadcrumbs: List[str]) -> str:
        class_name = infer_class_name(self.rel_path, title, breadcrumbs, self.ctx["known_classes"])
        # 单一进阶职业 page 文件（进阶职业/<来源书>/page_xxx.md）中，若 block 级推断
        # 未命中已知职业（如把具体能力名误作职业名），回退到文件级职业名。
        if self.file_class_name and class_name not in self.ctx["known_classes"]:
            return self.file_class_name
        return class_name

    def _is_single_prestige_page(self) -> bool:
        """判断是否为 进阶职业/<来源书>/page_xxx.md 形式的单一进阶职业直挂文件。"""
        parts = self.rel_path.parts
        if "进阶职业" not in parts:
            return False
        idx = parts.index("进阶职业")
        return idx + 2 == len(parts) - 1 and parts[-1].startswith("page_")

    def _extract_file_prestige_class(self, cleaned: List[str]) -> Optional[str]:
        """从单一进阶职业 page 文件清洗后的内容中解析职业名。

        优先使用 md_mapping 中的 CHM TOC 路径末级（最可靠），回退到第一个
        能提取出有效职业名的 heading 标题。
        """
        # 1. 优先 md_mapping 的 toc_path 末级
        toc_path = resolve_chm_toc_path(self.rel_path, [], self.ctx["md_mapping"])
        if toc_path:
            last = toc_path.split(" → ")[-1]
            if last and last not in _PRESTIGE_GENERIC_TITLES and re.search(r"[一-鿿]", last):
                return last

        # 2. 回退：清洗后第一个可提取职业名的 heading
        heading_re = re.compile(r"^(#{1,6})\s+(.*)$")
        for line in cleaned:
            m = heading_re.match(line.strip())
            if not m:
                continue
            title = m.group(2).strip()
            candidate = _extract_prestige_class_name(title, self.rel_path)
            if candidate:
                return candidate
        return None

    def infer_archetype_name(
        self,
        title: str,
        breadcrumbs: List[str],
        component_type: str,
        level: int,
    ) -> Optional[str]:
        if component_type == "class_recommendation":
            return None  # 推荐块不属于任何变体
        if component_type == "class_archetype":
            name_part, _ = extract_archetype_info(title)
            return name_part
        if component_type == "class_feature":
            md_mapping = self.ctx["md_mapping"]
            for b in reversed(breadcrumbs[:-1]):
                if looks_like_archetype_title(
                    b,
                    is_archetype_file=_is_archetype_file(self.rel_path, md_mapping),
                    level=level,
                ):
                    name_part, _ = extract_archetype_info(b)
                    return name_part
        return None

    def resolve_source(
        self,
        source_markers: List[SourceMarker],
        title: str,
        text: str,
        breadcrumbs: List[str],
        component_type: str,
        class_name: str,
        archetype_name: Optional[str],
        master_info: Optional[Dict[str, Any]],
        block_index: int = 0,
        file_blocks: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, str, str]:
        # 变体主表信息直接注入 Provider 框架，由 ArchetypeMasterProvider 统一处理。
        # 这里保留 master_info 参数以保持子类接口兼容，但不再在 resolve_source 中手动覆盖。
        return detect_book(
            self.rel_path,
            source_markers,
            self.ctx["book_lookup"],
            self.ctx["md_mapping"],
            title=title,
            text=text,
            breadcrumbs=breadcrumbs,
            component_type=component_type,
            class_name=class_name,
            archetype_name=archetype_name,
            block_index=block_index,
            file_blocks=file_blocks,
            archetype_masters=self.ctx.get("archetype_masters"),
        )

    def resolve_chm_toc_path(self, source_markers: List[SourceMarker]) -> str:
        return resolve_chm_toc_path(self.rel_path, source_markers, self.ctx["md_mapping"])

    def get_archetype_master(self, class_name: str, title: str) -> Optional[Dict[str, Any]]:
        if class_name == "未知职业":
            return None
        norm_title = _master_key(title)
        masters = self.ctx.get("archetype_masters", {})
        # 优先使用标题推断的职业名（如 圣武士），若未命中则回退到路径推断的规范职业名（如 圣骑士）
        if class_name in masters and norm_title in masters[class_name]:
            return masters[class_name][norm_title]
        path_class_name = infer_class_name(self.rel_path, "", [], self.ctx.get("known_classes", set()))
        if path_class_name != class_name and path_class_name in masters:
            return masters[path_class_name].get(norm_title)
        return None

    def extract_terms(self, text: str) -> Tuple[List[str], List[str]]:
        return extract_terms(text, self.ctx["alias_to_english"], self.ctx["aliases_sorted"])

    def infer_feature_subtype(
        self,
        breadcrumbs: List[str],
        title: str,
        component_type: str,
        archetype_name: Optional[str],
    ) -> Optional[str]:
        if component_type not in ("class_feature",):
            return None
        subtype = infer_feature_subtype(breadcrumbs)
        if not subtype:
            subtype = self.doc_subtype_hint
        # V006: Unchained 野蛮人狂暴之力补标 — 掉链子版缺少"狂暴之力"breadcrumb
        if not subtype and "掉链子（Unchained）/野蛮人" in self.doc_id:
            if re.search(r"[（(][A-Za-z]", title) and re.search(r"\b(?:Ex|Su|Sp)\b", title):
                subtype = "rage_power"
        return subtype

    def is_deprecated(
        self,
        title: str,
        component_type: str,
        deprecated_titles: Set[str],
        master_info: Optional[Dict[str, Any]],
    ) -> bool:
        if component_type == "class_archetype":
            if _normalize_heading_title(title) in deprecated_titles:
                return True
            if master_info and master_info.get("is_deprecated"):
                return True
        return False

    def _make_chunk_id(self, title: str, text: str) -> str:
        return hashlib.sha256(
            (self.doc_id + "|" + title + "|" + text).encode("utf-8")
        ).hexdigest()

    def keep(self, chunk: Chunk) -> bool:
        """过滤短小/纯导航 chunk；保留具体能力、变体和规则型表格。"""
        is_short = chunk.char_count < MIN_CHUNK_CHARS
        is_concrete_ability = (
            chunk.component_type == "class_feature"
            and chunk.class_name != "未知职业"
            and looks_like_ability_title(chunk.title)
            and not any(chunk.title.startswith(p) for p in QUICK_REF_PREFIXES + ("【专长速查】",))
        )
        if is_short and not (is_concrete_ability or chunk.component_type in ("class_archetype", "class_recommendation")):
            return False
        # 职业基础页里的等级/豁免/BAB/每日法术表本身是可检索规则，不能丢弃
        if (
            is_pure_table_or_nav(chunk.text)
            and not _looks_like_class_table(chunk.text)
            and chunk.component_type != "class_archetype"
            and chunk.feature_subtype not in (
                "patron", "domain", "bloodline", "arcane_school"
            )
        ):
            return False
        return True

    # -----------------------------------------------------------------
    # 主流程
    # -----------------------------------------------------------------
    def run(self) -> List[Chunk]:
        lines = self.file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        cleaned, deprecated_titles = self.clean(lines)
        # 供 expand 阶段合成职业变体基础页首标题用
        self.cleaned_lines = cleaned
        # 对单一进阶职业直挂 page 文件预解析文件级职业名，避免能力 chunk 被误归属为能力名
        if self._is_single_prestige_page():
            self.file_class_name = self._extract_file_prestige_class(cleaned)
        blocks = self.split(cleaned)
        self.raw_block_count = len(blocks)
        # 在 merge 之前缓存显式来源标记（来自 HTML 注释），
        # 因为 merge 可能合并 H2→H3 导致标记丢失。
        self._explicit_marker_cache: Dict[Tuple[str, ...], List[SourceMarker]] = {}
        for b in blocks:
            markers = b.get("markers", [])
            if markers:
                bc = tuple(b.get("breadcrumbs", []))
                self._explicit_marker_cache[bc] = markers
        blocks = self.expand(blocks)
        blocks = self.merge(blocks)

        chunks: List[Chunk] = []
        for idx, block in enumerate(blocks):
            chunk = self.build_chunk(block, deprecated_titles, idx, blocks)
            if chunk is None:
                continue
            if self.keep(chunk):
                chunks.append(chunk)
        return chunks



class OracleProcessor(FileProcessor):
    """先知文件处理器：类隔离下匹配"启示"/"秘示域"→revelation，不污染全局 breadcrumb。"""
    def infer_feature_subtype(
        self, breadcrumbs, title, component_type, archetype_name,
    ) -> Optional[str]:
        subtype = super().infer_feature_subtype(breadcrumbs, title, component_type, archetype_name)
        if not subtype and component_type == "class_feature":
            for ancestor in reversed(breadcrumbs):
                norm = _normalize_heading_title(ancestor).lower()
                if "启示" in norm or "秘示域" in norm:
                    return "revelation"
        return subtype


class WarpriestProcessor(FileProcessor):
    """战斗祭司处理器：类隔离下匹配"祝福"→blessing。"""
    def infer_feature_subtype(
        self, breadcrumbs, title, component_type, archetype_name,
    ) -> Optional[str]:
        subtype = super().infer_feature_subtype(breadcrumbs, title, component_type, archetype_name)
        if not subtype and component_type == "class_feature":
            for ancestor in reversed(breadcrumbs):
                norm = _normalize_heading_title(ancestor).lower()
                if "祝福" in norm:
                    return "blessing"
        return subtype


class SummonerProcessor(FileProcessor):
    """召唤师处理器：类隔离下匹配"进化"→evolution。"""
    def infer_feature_subtype(
        self, breadcrumbs, title, component_type, archetype_name,
    ) -> Optional[str]:
        subtype = super().infer_feature_subtype(breadcrumbs, title, component_type, archetype_name)
        if not subtype and component_type == "class_feature":
            for ancestor in reversed(breadcrumbs):
                norm = _normalize_heading_title(ancestor).lower()
                if "进化" in norm:
                    return "evolution"
        return subtype


class ShifterProcessor(FileProcessor):
    """变形者处理器：类隔离下匹配"拟态"→aspect。"""
    def infer_feature_subtype(
        self, breadcrumbs, title, component_type, archetype_name,
    ) -> Optional[str]:
        subtype = super().infer_feature_subtype(breadcrumbs, title, component_type, archetype_name)
        if not subtype and component_type == "class_feature":
            for ancestor in reversed(breadcrumbs):
                norm = _normalize_heading_title(ancestor).lower()
                if "拟态" in norm:
                    return "aspect"
        return subtype


class SorcererProcessor(FileProcessor):
    """术士处理器：类隔离下匹配"血统"→bloodline。"""
    def infer_feature_subtype(
        self, breadcrumbs, title, component_type, archetype_name,
    ) -> Optional[str]:
        subtype = super().infer_feature_subtype(breadcrumbs, title, component_type, archetype_name)
        if not subtype and component_type == "class_feature":
            for ancestor in reversed(breadcrumbs):
                norm = _normalize_heading_title(ancestor).lower()
                if "血统" in norm:
                    return "bloodline"
        return subtype


class WitchProcessor(FileProcessor):
    """女巫文件处理器：处理补充书等不规则排版，并注入女巫特化的来源书/subtype规则。"""

    EXPAND_STRATEGIES = [_split_patron_reward_tables_strategy]

    def __init__(
        self,
        file_path: Path,
        rel_path: Path,
        ctx: Dict[str, Any],
        spec: Optional[SupplementSpec] = None,
    ) -> None:
        super().__init__(file_path, rel_path, ctx)
        self.spec = spec
        self.entry_subtype_map: Dict[str, str] = {
            e.cn: e.subtype for e in (spec.entries if spec else [])
        }

    def clean(self, lines: List[str]) -> Tuple[List[str], Set[str]]:
        """先走标准清洗，再按条目表改写补充文件结构（仅注册过的补充书）。"""
        cleaned, deprecated_titles = super().clean(lines)
        if self.spec:
            cleaned = structure_supplement(cleaned, self.spec, self.doc_id)
        return cleaned, deprecated_titles

    def expand(self, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """基类展开 + 根据条目表补打 feature_subtype。"""
        blocks = super().expand(blocks)
        for b in blocks:
            title = _normalize_heading_title(b.get("title", ""))
            cn = re.split(r"[（(]", title)[0].strip()
            if cn in self.entry_subtype_map:
                b["feature_subtype"] = self.entry_subtype_map[cn]
        return blocks

    def resolve_source(
        self,
        source_markers: List[SourceMarker],
        title: str,
        text: str,
        breadcrumbs: List[str],
        component_type: str,
        class_name: str,
        archetype_name: Optional[str],
        master_info: Optional[Dict[str, Any]],
        block_index: int = 0,
        file_blocks: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, str, str]:
        """在默认来源推断后注入女巫专属覆盖规则。"""
        book = super().resolve_source(
            source_markers,
            title,
            text,
            breadcrumbs,
            component_type,
            class_name,
            archetype_name,
            master_info,
            block_index=block_index,
            file_blocks=file_blocks,
        )
        if class_name != "女巫":
            return book

        cn = _master_key(title)

        # ① page_92.md 中 UM 列巫术覆盖（默认被错标为 APG）
        if (
            component_type == "class_feature"
            and cn in self.ctx.get("witch_um_hex_names", set())
            and book[2] in ("APG", "?")
        ):
            return _UM

        # ② 变体职业能力继承变体来源（如冬女巫能力继承 ISM）
        if (
            component_type == "class_feature"
            and archetype_name
            and book[2] in ("APG", "?")
        ):
            arch_master = self.get_archetype_master(class_name, archetype_name)
            if arch_master and arch_master.get("book_abbreviation"):
                return (
                    arch_master["source_book"],
                    arch_master.get("source_book_english", book[1]),
                    arch_master["book_abbreviation"],
                )

        # ③ 四季/林地庇护主所在段落的来源覆盖（默认被错标为 APG）
        if component_type == "class_feature" and book[2] in ("APG", "?"):
            subtype = self.infer_feature_subtype(breadcrumbs, title, component_type, archetype_name)
            if subtype == "patron":
                ancestors = " → ".join(breadcrumbs)
                if any(
                    k in ancestors
                    for k in ("四季庇护主", "UW里的其余庇护主", "极限荒野", "Ultimate Wilderness")
                ):
                    return _UW

        return book


# ---------------------------------------------------------------------------
# 圣武士/圣骑士文件处理器
# ---------------------------------------------------------------------------

class PaladinProcessor(FileProcessor):
    """圣武士/圣骑士文件处理器。

    page_55.md 汇总页存在两处特殊排版问题：
    1. 恩惠/祷言段落的 `**` 未闭合，导致 `_merge_unclosed_bold_spans` 把后续
       神选之子、珍珠寻者、薄暮骑士等变体标题吞进同一行；
    2. 神卫标题缺少来源缩写与变体标记，导致被识别为普通能力而非变体。

    本处理器在标准清洗后做硬编码修正，仅作用于 `核心职业/圣骑士/page_55.md`。
    """

    def clean(self, lines: List[str]) -> Tuple[List[str], Set[str]]:
        cleaned, deprecated_titles = super().clean(lines)
        if self.doc_id == "核心职业/圣骑士/page_55.md":
            cleaned = _fix_paladin_page_55(cleaned)
        return cleaned, deprecated_titles


def _fix_paladin_page_55(lines: List[str]) -> List[str]:
    """硬编码修复 page_55.md 的变体标题丢失与神卫标题问题。"""
    out: List[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        # 1. 修复第 2164 行的未闭合 **，阻止后续大段合并
        if "复原祷言（Restorative）" in line and "目标获得快速医疗3" in line:
            line = re.sub(
                r"^\s*\*\*\s*：\s*目标获得快速医疗3，持续1/2圣武士轮。\s*\*\*",
                "目标获得快速医疗3，持续1/2圣武士轮。",
                line,
            )
            out.append(line)
            i += 1
            continue

        # 2. 拆分被前一段吞进来的 heading / 来源行 / HTML 注释 / 正文
        # 注意：lookbehind 必须排除 #，否则 ### 神祇（Deity） 这类合法
        # level-3 标题会被误判为"内容行内嵌的 heading"，导致后续被切成
        # 裸 `#` + `## 神祇`（level 降级），下挂的子能力被误识别为变体。
        if re.search(r"(?<=[^#])##\s|(?<=[^#])###\s|(?<=[^#])<!-- ", line):
            for part in _split_swallowed_headings(line):
                if part:
                    out.append(part)
            i += 1
            continue

        # 3. 把珍珠寻者来源行的 AA 改为 AqA，并把标题里的 AA 标记也改为 AqA
        if "（Aquatic Adventures）AA" in line:
            line = line.replace("（Aquatic Adventures）AA", "（Aquatic Adventures）AqA")
        if line.lstrip().startswith("#") and "珍珠寻者" in line and "【AA" in line:
            line = re.sub(r"【AA\s+圣武士变体】", "【AqA 圣骑士变体】", line)
            line = re.sub(r"【AA\s+圣骑士变体】", "【AqA 圣骑士变体】", line)

        # 4. 修复神卫标题：补上 CaC 与变体标记，并去掉被吞掉的重复子标题
        if line.strip() == "## 神卫（Divine Guardian）":
            j = i + 1
            while j < n and lines[j].strip() == "":
                j += 1
            if j < n and lines[j].strip().startswith("> 来源：部属与伙伴（Cohorts and Companions）"):
                src_idx = j
                j += 1
                while j < n and lines[j].strip() == "":
                    j += 1
                if j < n and "神卫（Divine Guardian）" in lines[j] and "变体" in lines[j]:
                    dup_idx = j
                    src_line = lines[src_idx].rstrip()
                    if "CaC" not in src_line:
                        src_line = src_line.replace(
                            "部属与伙伴（Cohorts and Companions）",
                            "部属与伙伴（Cohorts and Companions）CaC",
                        )
                    out.append("## 神卫（Divine Guardian）【CaC 圣骑士变体】")
                    out.append(src_line)
                    i = dup_idx + 1
                    continue

        out.append(line)
        i += 1

    # 5. 规范化 page_55.md 内所有变体标题的"圣武士变体"为目录一致的"圣骑士变体"
    normalized: List[str] = []
    for line in out:
        if line.lstrip().startswith("#"):
            # 处理"【BoS 圣武士变体】"这类带缩写的标记
            line = re.sub(
                r"([【〔［（])([A-Za-z0-9&]+)\s*圣武士变体([】〕］）])",
                r"\1\2 圣骑士变体\3",
                line,
            )
            # 处理"【圣武士圣武士变体】"或"［圣武士变体］"这类无缩写标记
            line = re.sub(
                r"[【〔［（]圣武士圣武士变体[】〕］）]|[【〔［（]圣武士变体[】〕］）]",
                "【圣骑士变体】",
                line,
            )
            # 珍珠寻者在缩写表中为 AqA，但源文件标题写 AA，这里强制修正
            if "珍珠寻者" in line and "【AA" in line:
                line = re.sub(r"【AA\s+圣骑士变体】", "【AqA 圣骑士变体】", line)
        normalized.append(line)

    return normalized


def _split_swallowed_headings(line: str) -> List[str]:
    """把一行内被吞掉的 heading / 来源行 / HTML 注释 / 正文拆成独立行。"""
    parts = re.split(r"(?<=\S)(?=\s*##\s|\s*###\s|\s*<!-- )", line)
    out: List[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue

        # heading + 来源行 + 正文 粘在一起：先拆 heading
        m = re.match(r"^(#{1,6}\s+.+?)\s*(>\s*来源：.*)$", part)
        if m:
            out.append(m.group(1).strip())
            part = m.group(2).strip()

        # 再把来源行和正文分开（来源行以路径箭头结尾，正文不再以箭头开头）
        m2 = re.match(r"^(>\s*来源：.+?→\s*.+?)\s+(?![→\s])(.*)$", part)
        if m2:
            out.append(m2.group(1).strip())
            body = m2.group(2).strip()
            if body:
                out.append(body)
            continue

        out.append(part)
    return out


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def process_profession_corpus(
    input_dir: Path,
    term_to_english: Dict[str, str],
    alias_to_english: Dict[str, List[str]],
    aliases_sorted: List[str],
    book_lookup: Dict[str, Any],
    md_mapping: Dict[str, Dict[str, Any]],
) -> Tuple[List[Chunk], List[str], Dict[str, Any]]:
    known_classes = discover_known_classes(input_dir)

    files = sorted(input_dir.rglob("*.md"))

    # 去重：相同清洗后文本只保留一份规范副本
    hash_to_path: Dict[str, Path] = {}
    duplicate_count = 0
    parse_errors: List[str] = []

    for file_path in files:
        try:
            # 使用字节级哈希，避免清洗规则变化导致重复副本漏判
            h = hashlib.sha256(file_path.read_bytes()).hexdigest()
            if h not in hash_to_path:
                hash_to_path[h] = file_path
            else:
                duplicate_count += 1
                existing = hash_to_path[h]
                existing_score = _canonical_score(existing, book_lookup)
                new_score = _canonical_score(file_path, book_lookup)
                if new_score > existing_score:
                    hash_to_path[h] = file_path
                elif new_score == existing_score and len(file_path.parts) < len(existing.parts):
                    hash_to_path[h] = file_path
        except Exception as e:
            parse_errors.append(f"{file_path}: {e}")

    canonical_files = sorted(hash_to_path.values(), key=lambda p: str(p))

    # 预扫描：识别职业变体基础页并解析变体主表（优先 CHM TOC，回退目录启发式）
    archetype_masters: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for file_path in canonical_files:
        rel_path = file_path.relative_to(input_dir)
        try:
            cleaned_lines, _ = clean_file(file_path, md_mapping)
        except Exception as e:
            parse_errors.append(f"{file_path}: 清洗失败: {e}")
            continue
        if not _is_archetype_base_page(rel_path, md_mapping, cleaned_lines):
            continue
        try:
            class_name = infer_class_name(rel_path, "", [], known_classes)
            masters = parse_archetype_master_table(cleaned_lines, book_lookup)
            if masters:
                archetype_masters.setdefault(class_name, {}).update(masters)
        except Exception as e:
            parse_errors.append(f"{file_path}: 解析变体主表失败: {e}")

    chunks: List[Chunk] = []
    raw_chunk_count = 0

    # 预解析女巫 page_92.md 的 UM 巫术来源表，供 WitchProcessor 覆盖用
    witch_um_hex_names: Dict[str, Tuple[str, str, str]] = {}
    witch_hex_page = input_dir / "基础职业" / "女巫" / "page_92.md"
    if witch_hex_page.exists():
        try:
            witch_um_hex_names = parse_witch_hex_source_table(
                witch_hex_page.read_text(encoding="utf-8", errors="ignore").splitlines()
            )
        except Exception as e:
            parse_errors.append(f"{witch_hex_page}: 解析女巫巫术来源表失败: {e}")

    ctx: Dict[str, Any] = {
        "book_lookup": book_lookup,
        "md_mapping": md_mapping,
        "known_classes": known_classes,
        "alias_to_english": alias_to_english,
        "aliases_sorted": aliases_sorted,
        "archetype_masters": archetype_masters,
        "witch_um_hex_names": witch_um_hex_names,
    }

    for file_path in canonical_files:
        rel_path = file_path.relative_to(input_dir)
        try:
            processor = create_processor(file_path, rel_path, ctx)
            file_chunks = processor.run()
            raw_chunk_count += processor.raw_block_count
            chunks.extend(file_chunks)
        except Exception as e:
            parse_errors.append(f"{file_path}: {e}")

    stats = {
        "total_files": len(files),
        "canonical_files": len(canonical_files),
        "duplicate_files": duplicate_count,
        "raw_chunks": raw_chunk_count,
        "unique_chunks": len(chunks),
    }

    return chunks, parse_errors, stats


# ---------------------------------------------------------------------------
# 职业-变体索引
# ---------------------------------------------------------------------------
def build_class_index(chunks: List[Chunk]) -> Dict[str, Any]:
    index: Dict[str, Any] = {}

    for chunk in chunks:
        cn = chunk.class_name or "未知职业"
        cls = index.setdefault(cn, {
            "class_name": cn,
            "overview_chunk_ids": [],
            "feature_chunk_ids": [],
            "archetypes": {},
        })

        if chunk.component_type == "class_overview":
            cls["overview_chunk_ids"].append(chunk.chunk_id)
        elif chunk.component_type == "class_feature":
            cls["feature_chunk_ids"].append(chunk.chunk_id)
        elif chunk.component_type == "class_archetype":
            an = chunk.archetype_name or "未知变体"
            arc = cls["archetypes"].setdefault(an, {
                "archetype_name": an,
                "base_class": cn,
                "source_book": chunk.book_source,
                "source_book_english": chunk.book_source_english,
                "book_abbreviation": chunk.book_abbreviation,
                "chm_toc_path": chunk.chm_toc_path,
                "chunk_ids": [],
            })
            arc["chunk_ids"].append(chunk.chunk_id)

    return index


def _chunk_to_dict(chunk: Chunk) -> Dict[str, Any]:
    """把 Chunk 序列化为 dict；空的 extra 字段不写入输出，保持向下兼容。"""
    d = asdict(chunk)
    if not d.get("extra"):
        d.pop("extra", None)
    return d


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def write_outputs(
    output_dir: Path,
    chunks: List[Chunk],
    stats: Dict[str, Any],
    parse_errors: List[str],
    class_index: Dict[str, Any],
    md_mapping: Dict[str, Dict[str, Any]],
) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    # chunks.jsonl
    with (output_dir / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(_chunk_to_dict(chunk), ensure_ascii=False) + "\n")

    # manifest.json
    book_counter = Counter(c.book_source for c in chunks)
    term_counter = Counter()
    for c in chunks:
        for t in c.terms:
            term_counter[t] += 1
    component_counter = Counter(c.component_type for c in chunks)
    subtype_counter = Counter(c.feature_subtype for c in chunks if c.feature_subtype)
    chm_known = sum(
        1
        for c in chunks
        if has_known_chm_toc_path(
            Path(c.doc_id), [SourceMarker(**m) for m in c.source_markers], md_mapping
        )
    )

    manifest = {
        "version": "2.0",
        "input_dir": str(INPUT_DIR),
        "output_dir": str(output_dir),
        "generated_at": datetime.now().isoformat(),
        "stats": {
            **stats,
            "avg_chunk_chars": round(sum(c.char_count for c in chunks) / len(chunks), 1) if chunks else 0,
            "component_distribution": dict(component_counter),
            "feature_subtype_distribution": dict(subtype_counter),
            "chm_toc_path_known": chm_known,
            "class_count": len(class_index),
            "archetype_count": sum(len(cls["archetypes"]) for cls in class_index.values()),
        },
        "book_distribution": dict(book_counter.most_common()),
        "top_terms": [{"term": t, "chunks": n} for t, n in term_counter.most_common(20)],
        "parse_errors": parse_errors,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # class_archetype_index.json
    (output_dir / "class_archetype_index.json").write_text(
        json.dumps(class_index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # quality_report.md
    report_lines = [
        "# 职业目录向量化预处理质量报告（三分法）",
        "",
        f"- 输入目录：`{INPUT_DIR}`",
        f"- 输出目录：`{output_dir}`",
        f"- 原始文件数：{stats['total_files']}",
        f"- 规范文件数：{stats['canonical_files']}",
        f"- 重复副本数：{stats['duplicate_files']}",
        f"- 原始 chunk 数：{stats['raw_chunks']}",
        f"- 去重后 chunk 数：{stats['unique_chunks']}",
        f"- 平均 chunk 字符数：{manifest['stats']['avg_chunk_chars']}",
        f"- 识别职业数：{manifest['stats']['class_count']}",
        f"- 识别变体数：{manifest['stats']['archetype_count']}",
        "",
        "## 组件类型分布",
        "",
        "| 组件类型 | Chunk 数 |",
        "|---|---|",
    ]
    for comp, n in component_counter.most_common():
        report_lines.append(f"| {comp} | {n} |")

    report_lines += [
        "",
        "## 来源书分布（Top 20）",
        "",
        "| 来源书 | Chunk 数 |",
        "|---|---|",
    ]
    for book, n in book_counter.most_common(20):
        report_lines.append(f"| {book} | {n} |")

    report_lines += [
        "",
        "## 高频命中术语（Top 20）",
        "",
        "| 术语 | 出现 chunk 数 |",
        "|---|---|",
    ]
    for term, n in term_counter.most_common(20):
        report_lines.append(f"| {term} | {n} |")

    report_lines += [
        "",
        "## 职业与变体索引概览",
        "",
        f"共 {len(class_index)} 个职业，{manifest['stats']['archetype_count']} 个变体。",
        "",
        "| 职业 | Overview | Feature | 变体数 |",
        "|---|---|---|---|",
    ]
    for cn in sorted(class_index.keys())[:50]:
        cls = class_index[cn]
        report_lines.append(
            f"| {cn} | {len(cls['overview_chunk_ids'])} | {len(cls['feature_chunk_ids'])} | {len(cls['archetypes'])} |"
        )

    report_lines += [
        "",
        "## 样本 Chunk",
        "",
    ]
    samples: Dict[str, Chunk] = {}
    for c in chunks:
        if c.component_type not in samples:
            samples[c.component_type] = c
        if len(samples) >= 4:
            break

    for comp, c in samples.items():
        report_lines += [
            f"### 样本：{comp} - {c.title}",
            "",
            f"- 职业：{c.class_name}",
            f"- 来源书：{c.book_source}（{c.book_abbreviation}）",
            f"- CHM 目录：{c.chm_toc_path}",
            f"- 文档：{c.doc_id}",
            f"- 命中术语：{', '.join(c.terms[:10])}{'...' if len(c.terms) > 10 else ''}",
            "```text",
            c.text[:800] + ("..." if len(c.text) > 800 else ""),
            "```",
            "",
        ]

    if parse_errors:
        report_lines += [
            "",
            "## 解析错误",
            "",
        ]
        for err in parse_errors[:20]:
            report_lines.append(f"- {err}")

    (output_dir / "quality_report.md").write_text(
        "\n".join(report_lines),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------
def main() -> None:
    term_to_english, alias_to_english, aliases_sorted = load_terms(TERMS_JSON)
    book_lookup = load_abbreviation_table(SOURCE_BOOK_ABBR_MD)
    md_mapping = load_md_mapping(MD_MAPPING_JSON)

    chunks, parse_errors, stats = process_profession_corpus(
        INPUT_DIR,
        term_to_english,
        alias_to_english,
        aliases_sorted,
        book_lookup,
        md_mapping,
    )

    class_index = build_class_index(chunks)
    write_outputs(OUTPUT_DIR, chunks, stats, parse_errors, class_index, md_mapping)

    print(f"处理完成：{stats['canonical_files']} 个规范文件 → {len(chunks)} 个 chunk")
    print(f"职业数：{len(class_index)}，变体数：{sum(len(cls['archetypes']) for cls in class_index.values())}")
    print(f"输出目录：{OUTPUT_DIR}")


if __name__ == "__main__":
    main()
