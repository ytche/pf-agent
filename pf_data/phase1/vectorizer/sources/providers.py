"""
sources/providers.py — SourceProvider 链式来源书判定

设计：
  - 链式置信度聚合，高置信度 Provider 优先
  - 置信度范围 10~95，首个命中即返回
  - 通用 Provider 对所有类目适用，特有 Provider 按类目激活

用法：
  resolver = SourceResolver(ALL_PROVIDERS)
  result = resolver.resolve(ctx)
  # → SourceResult(book_abbreviation="CRB", confidence=75, ...)
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---- 共享资源路径 ----

# md_mapping.json：md 文件名 → {html_file, toc_path, book_source}
# 由 CHM 转换期生成（git e2c559b），记录 Markdown 源文件在 CHM 目录中的位置，
# 供所有类目复用。归档在 pf_data/_archive/chm_scripts/ 时不可用，2026-08-01 提升为共享资源。
MD_MAPPING_JSON = Path(__file__).resolve().parents[3] / "md_mapping.json"

# ---- 来源书常量 ----

SOURCE_BOOK_ABBREVIATIONS: Dict[str, tuple] = {
    "CRB": ("核心规则书", "Core Rulebook"),
    "APG": ("进阶玩家指南", "Advanced Player's Guide"),
    "UM": ("极限魔法", "Ultimate Magic"),
    "UC": ("极限战斗", "Ultimate Combat"),
    "ACG": ("进阶职业指南", "Advanced Class Guide"),
    "ARG": ("种族指南", "Advanced Race Guide"),
    "OA": ("异能冒险", "Occult Adventures"),
    "UI": ("极限异能", "Ultimate Intrigue"),
    "ISWG": ("内海世界指南", "Inner Sea World Guide"),
    "ISM": ("内海魔法", "Inner Sea Magic"),
    "ISG": ("内海诸神", "Inner Sea Gods"),
    "AArch": ("冒险之路：正义之怒", "Adventure Path: Wrath of the Righteous"),
    "CotR": ("皇冠之路", "Crown of the Righteous"),
    "FoB": ("信仰之书", "Faith of Battle"),
    "FoC": ("信仰之书：探索者", "Faith of the Crusader"),
    "FoP": ("信仰之书：圣战", "Faith of the Paladin"),
    "MTT": ("魔法战术工具箱", "Magic Tactics Toolbox"),
    "RTT": ("符文战术工具箱", "Rune Tactics Toolbox"),
    "TG": ("科技指南", "Technology Guide"),
    "PotR": ("诸神之怒", "Path of the Righteous"),
    "BotA": ("古国血脉", "Blood of the Ancients"),
    "EMH": ("元素大师手册", "Elemental Master's Handbook"),
    "ISR": ("内海种族", "Inner Sea Races"),
    "COMP": ("玩家伴侣", "Player Companion"),
    "CAMPAIGN": ("战役设定", "Campaign Setting"),
    "MA": ("神话冒险", "Mythic Adventures"),
    "PA": ("位面冒险", "Planar Adventures"),
    "HA": ("恐怖冒险", "Horror Adventures"),
    "BotD": ("永罪之书", "Book of the Damned"),
    "DEP": ("龙国初探", "Dragon Empires Primer"),
    "PSP": ("探索者协会初探", "Pathfinder Society Primer"),
    "CoP": ("纯洁勇士", "Champion of Purity"),
    "VC": ("恶棍志", "Villain Codex"),
    # ---- 装备模块纯新增键（2026-08-08，KN165 专属表短路配套）----
    # 只增不改：跨模块同名冲突键（RTT/UI/AArch/FoB/PotR/HoG/PA 等）语义以
    # 装备专属表短路为准，此处不动（KN136 共享层改动漂移教训）。同名同书
    # 直接复用既有键（ISWG/ISM/ISG/ISR/EMH/HA/BotD/PSP/CoP/VC/MTT/MA/CRB）。
    "PoP": ("万界之力", "Planes of Power"),
    "QGthE": ("卡蒂亚，通向东方的大门", "Qadira, Gateway to the East"),
    "WS": ("PF官方漫画Worldscape", "Worldscape"),
    "PHH": ("位面行者手册", "Plane-Hopper's Handbook"),
    "BotE": ("元素血脉", "Blood of the Elements"),
    "ISC": ("内海战斗", "Inner Sea Combat"),
    "PIS": ("内海海盗", "Pirates of the Inner Sea"),
    "ISI": ("内海诡道", "Inner Sea Intrigue"),
    "KIS": ("内海骑士", "Knights of the Inner Sea"),
    "IST": ("内海神殿", "Inner Sea Temples"),
    "ISS": ("内海舰船", "Ships of the Inner Sea"),
    "CTR": ("再探经典宝藏", "Classic Treasures Revisited"),
    "AP": ("冒险之路", "Adventure Path"),
    "MM": ("商人货单", "Merchant's Manifest"),
    "MMG": ("魔法市集指南", "Magical Marketplace"),
    "PotH": ("地狱骑士之道", "Path of the Hellknight"),
    "TEoG": ("塔尔多，荣光荡漾之地", "Taldor, Echoes of Glory"),
    "NLS": ("奈多，阴影之地", "Nidal, Land of Shadows"),
    "ASoL": ("安多安，自由之魂", "Andoran, Spirit of Liberty"),
    "GR": ("巨人再临", "Giants Revisited"),
    "HotD": ("幽暗地域英雄", "Heroes of the Darklands"),
    "PsyA": ("异能选集", "Psychic Anthology"),
    "BoG": ("格拉里昂的混种", "Bastards of Golarion"),
    "EoG": ("格拉里昂的精灵", "Elves of Golarion"),
    "HaG": ("格拉里昂的半身人", "Halflings of Golarion"),
    "HoG": ("格拉里昂的英雄", "Heroes of Golarion"),
    "AA": ("冒险者的军械库", "Adventurer's Armory"),
    "AqA": ("水下冒险", "Aquatic Adventures"),
    "QaC": ("任务与战役", "Quests and Campaigns"),
    "PSFG": ("探索者协会战地指南", "Pathfinder Society Field Guide"),
    "ARMOR": ("护甲大师手册", "Armor Master's Handbook"),
    "QJotE": ("卡蒂亚，东方明珠", "Qadira, Jewel of the East"),
    "DR": ("遥远国度", "Distant Realms"),
    "VBoL": ("瓦瑞西亚，传说诞生之地", "Varisia, Birthplace of Legends"),
    "HotHC": ("皇庭英豪", "Heroes of the High Court"),
    "MO": ("神话源始", "Mythic Origins"),
    "CHR": ("经典恐怖再临", "Classic Horrors Revisited"),
    "HftF": ("缘界英雄", "Heroes from the Fringe"),
    "HotW": ("荒野英雄", "Heroes of the Wild"),
    "HotS": ("街巷英雄", "Heroes of the Streets"),
    "AA2": ("冒险者的军械库2", "Adventurer's Armory 2"),
    "KoG": ("格拉里昂的狗头人", "Kobolds of Golarion"),
    "DoG": ("格拉里昂的矮人", "Dwarves of Golarion"),
    "SoS": ("秘密探寻者", "Seekers of Secrets"),
    "P&P": ("药剂与毒药", "Potions and Poisons"),
    "ACO": ("进化职业起源", "Advanced Class Origins"),
    "AoE": ("邪恶特务", "Agents of Evil"),
    "DD": ("门徒教义", "Disciple's Doctrine"),
    "CaC": ("部属与伙伴", "Cohorts and Companions"),
    "UNDEAD": ("亡灵杀手手册", "Undead Slayer's Handbook"),
    "F&P": ("信仰与哲学", "Faiths and Philosophies"),
    "PotW": ("废土子民", "People of the Wastes"),
    "LT": ("失落秘宝", "Lost Treasures"),
    "LotLK": ("林诺姆诸王之国", "Lands of the Linnorm Kings"),
    "CoB": ("平衡勇士", "Champions of Balance"),
    "CoC": ("秽邪勇士", "Champions of Corruption"),
    "PoS": ("繁星子民", "People of the Stars"),
    "GttRK": ("河域诸国指南", "Guide to the River Kingdoms"),
    "Dragonslayer": ("屠龙者手册", "Dragonslayer's Handbook"),
    "MHH": ("怪物猎人手册", "Monster Hunter's Handbook"),
    "DHH": ("恶魔猎人手册", "Demon Hunter's Handbook"),
    "MSH": ("怪物召唤者手册", "Monster Summoner's Handbook"),
    "WEAPON": ("武器大师手册", "Weapon Master's Handbook"),
    "BotD2": ("永罪之书第二卷：混沌诸王", "Book of the Damned - Volume 2: Lords of Chaos"),
    "RM": ("敌手指南", "Rival Guide"),
    "BoS": ("阴影血脉", "Blood of Shadows"),
    "BotN": ("夜之血脉", "Blood of the Night"),
    "BotC": ("巫团血脉", "Blood of the Coven"),
    "BotM": ("月之血脉", "Blood of the Moon"),
    "DS": ("遥远世界", "Distant Shores"),
    "BotS": ("海洋之血", "Blood of the Sea"),
    "NLoFS": ("纽梅利亚，星落之地", "Numeria, Land of Fallen Stars"),
    "StLC": ("萨迦瓦，失落的殖民地", "Sargava, the Lost Colony"),
    "THH": ("哈罗牌手册", "The Harrow Handbook"),
}

# 文件名 → 来源书缩写映射（不含 ".md"）
FILENAME_ABBR_MAP: Dict[str, str] = {
    "Spell CRB": "CRB",
    "Spell APG": "APG",
    "Spell UM": "UM",
    "Spell UC": "UC",
    "Spell ACG": "ACG",
    "Spell ARG": "ARG",
    "Spell OA": "OA",
    "Spell UI": "UI",
    "Spell ISWG": "ISWG",
    "Spell ISM": "ISM",
    "Spell ISG": "ISG",
    "Spell index": "INDEX",
    "Spell MTT": "MTT",
    "AG-冒险者指南": "COMP",
    "MC-怪物志": "COMP",
    "药剂与毒药P&P_法术": "COMP",
    "任务与战役_法术": "COMP",
    "元素大师手册EMH_法术": "EMH",
    "屠龙者手册_法术": "COMP",
    "屠龙者手册_世界名著": "COMP",
    "夜之血脉BotN_法术": "COMP",
    "ISR-内海种族": "ISR",
    "内海神殿_法术": "CAMPAIGN",
    "动物档案AArch_法术": "AArch",
    "月之血脉BotM_法术": "COMP",
    "阴影血脉BoS_法术": "COMP",
    # Phase 2: page_* 编译帖映射（forum compilation posts）
    "page_625": "MA",       # 神话法术
    "page_623": "MA",       # 神话专长（MA 神话冒险）
    "page_624": "MA",       # 神话专长（MA 神话冒险）
    "page_853": "COMP",     # 玩家伴侣法术合集
    "page_854": "COMP",     # 玩家伴侣法术合集（恐怖主题）
    "page_1219": "COMP",    # 荒野魔法（玩家伴侣）
    "page_1474": "PA",      # 位面冒险法术
    "page_1494": "BotD",    # 永罪之书法术
    # Phase 2: 已知来源文件映射
    "异能选集PA_法术": "COMP",           # 异能选集（玩家伴侣）
    "格拉里昂的纯洁勇士_法术": "CoP",    # 纯洁勇士
    "初探探索者协会_法术": "PSP",        # 探索者协会初探
    "初探龙国DEP_法术": "DEP",           # 龙国初探
    "官方Blog": "COMP",                 # 官方博客（玩家伴侣相关）
    "反派法典VC_神秘仪式": "VC",          # 反派法典：神秘仪式（Villain Codex）
}

# 目录名 → 来源书缩写
DIRECTORY_ABBR_MAP: Dict[str, str] = {
    "冒险之路": "AArch",
    "玩家伴侣": "COMP",
    "战役设定": "CAMPAIGN",
    "技能": "CRB",  # 技能模块（2026-08-07）：技能/ 目录全部属 CRB 核心规则书
    # （A 批 38 文件均无 HTML 来源注释，目录级判定置信度 80）
}


# ---- 数据类 ----

@dataclass
class SourceMarker:
    """HTML 注释中的来源标记"""
    book_abbr: str
    confidence: int = 95


@dataclass
class SourceContext:
    """来源判定上下文，跨类目通用"""
    file_path: Path
    file_content: str = ""
    chm_toc_path: str = ""
    html_markers: List[SourceMarker] = field(default_factory=list)
    directory_hints: List[str] = field(default_factory=list)
    aggregation_table: Optional[Dict[str, str]] = None


@dataclass
class SourceResult:
    """来源判定结果"""
    book_abbreviation: str
    book_name_cn: str = ""
    book_name_en: str = ""
    confidence: int = 0
    provider_name: str = ""


UNKNOWN_SOURCE = SourceResult(
    book_abbreviation="?",
    book_name_cn="未知来源",
    book_name_en="Unknown",
    confidence=0,
    provider_name="DefaultProvider",
)


# ---- 抽象基类 ----

class SourceProvider(ABC):
    """来源书判定 Provider — 每个 Provider 实现一个判定通道"""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def confidence(self) -> int:
        """此 Provider 判定准确时的置信度（10~95）"""
        ...

    @abstractmethod
    def resolve(self, ctx: SourceContext) -> Optional[SourceResult]:
        """
        尝试从 context 中判定来源书。
        返回 None 表示无法判定。
        """
        ...


# ---- 具体 Provider ----

class HTMLCommentProvider(SourceProvider):
    """从 HTML 注释 <!-- Source: ... --> 提取来源书（置信度 95）"""

    name = "HTMLCommentProvider"
    confidence = 95

    def resolve(self, ctx: SourceContext) -> Optional[SourceResult]:
        m = re.search(r'<!--\s*Source:\s*([A-Za-z0-9_-]+)\s*-->', ctx.file_content)
        if m:
            abbr = m.group(1).strip()
            if abbr in SOURCE_BOOK_ABBREVIATIONS:
                cn, en = SOURCE_BOOK_ABBREVIATIONS[abbr]
                return SourceResult(abbr, cn, en, self.confidence, self.name)
        return None


class AggregationTableProvider(SourceProvider):
    """从聚合页来源书表解析（V009 新增，置信度 85）"""

    name = "AggregationTableProvider"
    confidence = 85

    def resolve(self, ctx: SourceContext) -> Optional[SourceResult]:
        if ctx.aggregation_table and ctx.file_path.name in ctx.aggregation_table:
            abbr = ctx.aggregation_table[ctx.file_path.name]
            if abbr in SOURCE_BOOK_ABBREVIATIONS:
                cn, en = SOURCE_BOOK_ABBREVIATIONS[abbr]
                return SourceResult(abbr, cn, en, self.confidence, self.name)
        return None


class DirectoryNameProvider(SourceProvider):
    """从目录中文名映射到缩写（置信度 80）"""

    name = "DirectoryNameProvider"
    confidence = 80

    def resolve(self, ctx: SourceContext) -> Optional[SourceResult]:
        for hint in ctx.directory_hints:
            for cn_name, abbr in DIRECTORY_ABBR_MAP.items():
                if cn_name in hint:
                    if abbr in SOURCE_BOOK_ABBREVIATIONS:
                        cn, en = SOURCE_BOOK_ABBREVIATIONS[abbr]
                        return SourceResult(abbr, cn, en, self.confidence, self.name)
        return None


class FileNameAbbrProvider(SourceProvider):
    """从文件名 ASCII 缩写推断（置信度 75）"""

    name = "FileNameAbbrProvider"
    confidence = 75

    def resolve(self, ctx: SourceContext) -> Optional[SourceResult]:
        stem = ctx.file_path.stem
        # 精确匹配
        if stem in FILENAME_ABBR_MAP:
            abbr = FILENAME_ABBR_MAP[stem]
            if abbr in SOURCE_BOOK_ABBREVIATIONS:
                cn, en = SOURCE_BOOK_ABBREVIATIONS[abbr]
                return SourceResult(abbr, cn, en, self.confidence, self.name)

        # 模糊匹配：文件名含 "CRB" → CRB
        for key, abbr in FILENAME_ABBR_MAP.items():
            if abbr != "INDEX" and abbr in stem:
                if abbr in SOURCE_BOOK_ABBREVIATIONS:
                    cn, en = SOURCE_BOOK_ABBREVIATIONS[abbr]
                    return SourceResult(abbr, cn, en, self.confidence - 5, self.name)

        return None


class MdMappingTocProvider(SourceProvider):
    """从 md_mapping.json 加载 CHM 目录路径（公用资源加载器）

    职责：
      - 惰性加载共享资源 md_mapping.json（md 文件名 → html_file/toc_path/book_source）
      - lookup_toc_path(file_name) 按文件名查表，返回 toc_path（不写 SourceContext）

    为什么不走 SourceContext.chm_toc_path：
      SourceContext.chm_toc_path 同时被 CHMTocPathProvider 消费（子串缩写匹配来源书）。
      若由本 provider 提前填充，会激活该匹配——实测 "PA" 误中 "PATHFINDER"，
      改变已冻结模块（spell）的来源书判定。故由骨架 FileProcessor 直接查表写入 chunk，
      CHMTocPathProvider 永远读不到富化值，来源书判定链保持不变。

    实现：
      - 公用部分，各模块无需自理。首次调用时自动加载一次，全局共享。
      - resolve() 仅为满足 SourceProvider 抽象（纯富化，返回 None，不参与来源书链）。
    """

    name = "MdMappingTocProvider"
    confidence = 75

    def __init__(self, mapping_path: Optional[Path] = None):
        self._mapping_path = mapping_path or MD_MAPPING_JSON
        self._mapping: Dict[str, Dict[str, Any]] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        path = Path(self._mapping_path)
        if not path.exists():
            logger.info("md_mapping 未找到，跳过 TOC 富化: %s", path)
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._mapping = data
                logger.info("md_mapping 加载完成: %d 条目", len(self._mapping))
            else:
                logger.warning("md_mapping 顶层非 dict，忽略: %s", path)
        except Exception as e:
            logger.warning("md_mapping 加载失败 %s: %s", path, e)

    def lookup_toc_path(self, file_name: str) -> str:
        """按 md 文件名查 CHM 目录路径；未命中返回空串。"""
        self._ensure_loaded()
        entry = self._mapping.get(file_name)
        if entry and entry.get("toc_path"):
            return entry["toc_path"]
        return ""

    def resolve(self, ctx: SourceContext) -> Optional[SourceResult]:
        """纯富化：不进来源书链，始终返回 None。"""
        return None


class CHMTocPathProvider(SourceProvider):
    """从 CHM TOC 路径分析（置信度 70）"""

    name = "CHMTocPathProvider"
    confidence = 70

    def resolve(self, ctx: SourceContext) -> Optional[SourceResult]:
        if not ctx.chm_toc_path:
            return None
        # 提取 TOC 路径中的来源书线索
        for abbr in SOURCE_BOOK_ABBREVIATIONS:
            if abbr in ctx.chm_toc_path.upper():
                cn, en = SOURCE_BOOK_ABBREVIATIONS[abbr]
                return SourceResult(abbr, cn, en, self.confidence, self.name)
        return None


class SpellIndexProvider(SourceProvider):
    """
    法术索引表 Provider（法术类目特有，置信度 65）

    从 Spell index.md 加载法术→来源书映射表，按英文名查找。
    同时产出索引 chunk（component_type: "spell_index"）供 RAG 检索。
    """

    name = "SpellIndexProvider"
    confidence = 65

    def __init__(self, index_path: Optional[Path] = None):
        self.index_path = index_path
        self._index: Dict[str, str] = {}  # English Name → Book Abbr
        self._loaded = False

    def load(self, path: Optional[Path] = None) -> None:
        """加载 Spell index.md"""
        p = path or self.index_path
        if not p or not p.exists():
            logger.warning("Spell index 未找到: %s", p)
            return

        text = p.read_text(encoding="utf-8")

        # Phase 2: 先合并跨行英文名（如 Familiar\n       Flgment → Familiar Flgment）
        # 物理换行发生在英文名内部，续行不以 | 开头
        lines = text.splitlines()
        merged: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") or not merged:
                merged.append(stripped)
            else:
                # 续行：追加到上一行（替换末尾换行处为空格）
                merged[-1] = merged[-1] + " " + stripped

        for line in merged:
            # 格式：| 来源书缩写 | 中文名(English Name) [可选标签] |
            # 注意：部分条目 ) 后有 [种族] 等标签（如 [矮人]、[精灵]）
            m = re.match(r'^\|\s*([A-Za-z/]+)\s*\|\s*.+\(([^)]+)\)[^|]*\|$', line)
            if m:
                book_abbr = m.group(1).strip()
                eng_name = re.sub(r'\s+', ' ', m.group(2).strip())
                self._index[eng_name.lower()] = book_abbr

        self._loaded = True
        logger.info("Spell index 加载完成: %d 条目", len(self._index))

    def resolve(self, ctx: SourceContext) -> Optional[SourceResult]:
        if not self._loaded:
            return None
        # 从文件内容中提取英文名，查表
        for line in ctx.file_content.splitlines():
            m = re.search(r'\*\*[^*]+\s*\(([^)]+)\)\*\*', line)
            if m:
                eng_name = re.sub(r'\s+', ' ', m.group(1).strip()).lower()
                if eng_name in self._index:
                    abbr = self._index[eng_name]
                    if abbr in SOURCE_BOOK_ABBREVIATIONS:
                        cn, en = SOURCE_BOOK_ABBREVIATIONS[abbr]
                        return SourceResult(abbr, cn, en, self.confidence, self.name)
        return None

    def get_all_entries(self) -> Dict[str, str]:
        """返回完整索引表（用于生成索引 chunk）"""
        return dict(self._index)


class ContentBookMentionProvider(SourceProvider):
    """从正文含来源书线索推断（置信度 50）

    P1a 修复（2026-08-02）：旧实现做全文子串扫描（前 2000 字符），
    会把「先决条件交叉引用 / 正文页码引用 / 参见」误当成来源书
    （如 专长11 正文 "Core Rulebook第442页" → 整文件误判 CRB）。
    改为行级扫描 + 来源声明形态白名单：
      - 信任行：标题《X》/ # 标题 / **来源** **出处** **Source** 行 /
        > 来源：引用块 / 出自《X》句（专长42 含 pg 的出自句也信任）
      - 拒绝行：先决条件 / 前提 / 页码引用（第 N 页 / pg.N）/ 参见
      - 行级扫描天然消除跨行伪命中（"Core \\r\\nRulebook" 拆行不再匹配）
    形态样例取自 40 个 conf=50 实证 doc（2026-08-02 审计）。
    """

    name = "ContentBookMentionProvider"
    confidence = 50

    # 正文引用形态（命中即跳过该行）：先决条件/前提/页码/参见
    _RE_REFERENCE_LINE = re.compile(
        r"先决条件|前提|前置|参见|"
        r"第\s*[0-9０-９]+\s*页|\bpg\.?\s*[0-9]+|[0-9]+\s*页|页\s*[0-9]+"
    )
    # 「出自《X》的 Y」= 引用其他书中的内容（第一世界TFWRotF 实证：
    # "使用出自《探索者战役设定：内海诸神》的传音者"），非本文件出处声明
    _RE_OUT_OF_REFERENCE = re.compile(r"出自《[^》]{1,30}》的")
    # 来源声明行（search）：来源/出处/Source 标签、> 来源引用块、# 标题、出自句
    _RE_SOURCE_STATEMENT = re.compile(
        r"^\*{0,2}(来源|出处|Source)|^>\s*来源|^#|出自"
    )
    # 标题行（match，行首锚定）：**《X》专长** 等星号/井号包裹的《X》标题
    _RE_TITLE_LINE = re.compile(r"^[*#\s]*《[^》]{1,30}》")

    def resolve(self, ctx: SourceContext) -> Optional[SourceResult]:
        # 只看前 2000 字符（文件级来源线索语义：文件头部的来源声明）
        for raw_line in ctx.file_content[:2000].splitlines():
            line = raw_line.strip()
            if not line:
                continue
            is_out_ref = bool(self._RE_OUT_OF_REFERENCE.search(line))
            is_statement = (not is_out_ref) and bool(
                self._RE_SOURCE_STATEMENT.search(line)
            )
            is_title = bool(self._RE_TITLE_LINE.match(line))
            # 1) 引用形态（先决/页码/参见/「出自《X》的 Y」）→ 跳过；
            #    来源声明行（**来源** X pg. 25）与出自句（出自《X》pg8）
            #    内的页码是条目出处，不属于引用 → 豁免
            if (self._RE_REFERENCE_LINE.search(line) or is_out_ref) and not is_statement:
                continue
            # 2) 非来源声明、非标题的普通正文 → 跳过（不扫书名）
            if not (is_statement or is_title):
                continue
            # 3) 信任行扫描书名（行级扫描天然消除跨行伪命中）。
            #    同一行出现多个书（"出自《Planar Adventures pg. 28, Advanced
            #    Race Guide pg. 174》"）时取行内最先出现的书为主出处
            #    （其他专长1 实证：ARG 在缩写表顺序上先于 PA，旧实现误判 ARG）。
            best_pos = -1
            best_abbr = None
            for abbr, (cn, en) in SOURCE_BOOK_ABBREVIATIONS.items():
                pos = line.find(cn)
                en_pos = line.find(en)
                if en_pos != -1 and (pos == -1 or en_pos < pos):
                    pos = en_pos
                if pos != -1 and (best_pos == -1 or pos < best_pos):
                    best_pos = pos
                    best_abbr = abbr
            if best_abbr is not None:
                cn, en = SOURCE_BOOK_ABBREVIATIONS[best_abbr]
                return SourceResult(best_abbr, cn, en, self.confidence, self.name)
        return None


class ParentDirFallbackProvider(SourceProvider):
    """从上级目录名推断（置信度 30）"""

    name = "ParentDirFallbackProvider"
    confidence = 30

    def resolve(self, ctx: SourceContext) -> Optional[SourceResult]:
        parent = ctx.file_path.parent.name if ctx.file_path.parent else ""
        for cn_name, abbr in DIRECTORY_ABBR_MAP.items():
            if cn_name in parent:
                if abbr in SOURCE_BOOK_ABBREVIATIONS:
                    cn, en = SOURCE_BOOK_ABBREVIATIONS[abbr]
                    return SourceResult(abbr, cn, en, self.confidence, self.name)
        return None


class DefaultProvider(SourceProvider):
    """无法判定的兜底（置信度 10）"""

    name = "DefaultProvider"
    confidence = 10

    def resolve(self, ctx: SourceContext) -> Optional[SourceResult]:
        return UNKNOWN_SOURCE


# ---- 链式聚合 ----

ALL_PROVIDERS: List[SourceProvider] = [
    HTMLCommentProvider(),
    AggregationTableProvider(),
    DirectoryNameProvider(),
    FileNameAbbrProvider(),
    CHMTocPathProvider(),
    SpellIndexProvider(),  # Phase 2: 需 load_resources() 调用 load() 后生效
    ContentBookMentionProvider(),
    ParentDirFallbackProvider(),
    DefaultProvider(),
]


class SourceResolver:
    """链式聚合 — 按置信度排序，首个非 None 返回"""

    def __init__(self, providers: List[SourceProvider]):
        self.providers = sorted(providers, key=lambda p: p.confidence, reverse=True)

    def resolve(self, ctx: SourceContext) -> SourceResult:
        for provider in self.providers:
            try:
                result = provider.resolve(ctx)
                if result and result.book_abbreviation != "?":
                    return result
            except Exception as e:
                logger.debug("Provider %s 异常: %s", provider.name, e)
                continue
        return UNKNOWN_SOURCE
