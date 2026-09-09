"""processors/race.py — 种族文件处理器

设计（2026-08-04，元数据定稿 + 人工确认门 2 后实现）：
  - 复用 FileProcessor 模板方法（三钩子：build_chunk / resolve_source / infer_metadata）
  - 扫描清单 = docs/种族/format_cluster_assign.json 112 rel（勘探同口径，
    矩阵 rel 前缀与 race_per_file.jsonl 一致，est 对账在 verify_races）
  - 12 枚举 component_type 由 formats 层章节状态机产出（build_chunk 透传）；
    D 簇（怪物玩法扩展）裸标题主条目 formats 层定为 race_sidebar，按簇感知
    映射 monster_block——怪物主条目（霜巨人等）不应降权，检索端可区分类怪条目
  - resolve_source：provider 链 → 引用块兜底（复用 feat 引用块解析：80 处
    引用块全为「中文名（英文名）缩写，页码见原书，未整理 → X → Y」箭头形态，
    与专长同构；HTML 注释缩写查 FEAT_SOURCES 补充表兜底，种族书不在表内
    返回 None 保持 '?'，不编造）
  - infer_metadata：元数据定稿 3.1 核心 7 + 3.2 结构 6（intro 专属）+
    3.3 条目级 14（字段族按 component_type 判 not_applicable，同专长
    任务链/造物字段模式）；parse_fields 用公共层 parse_fields_common
    （第三处同算法抽公共层，禁 copy 模板扩展）
  - POSTPROCESSORS = 通用 backfill 两件套（BackfillChmTocPath 注释/来源行
    toc 回填 + BackfillFeatSource 引用块 source 补齐），子类覆写报告目录
    到 docs/种族/（防覆盖专长报告）；book '?' 统计后再定是否补映射步骤
"""

import json
import logging
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from vectorizer.formats.race import RaceFormat
from vectorizer.postprocess.feat_chain import BackfillChmTocPath, BackfillFeatSource
from vectorizer.processors import register
from vectorizer.processors.base import Chunk, FileProcessor
from vectorizer.processors.feat import _feat_source_from_content
from vectorizer.processors.parse_fields_common import parse_fields
from vectorizer.sources.providers import SourceContext, SourceResolver, SourceResult

logger = logging.getLogger(__name__)


# ---- 输入范围（勘探同口径：format_cluster_assign.json 112 rel）----
_ORGANIZED_ROOT = Path(__file__).resolve().parent.parent.parent / "pf_rules_md_organized"
_RACE_ASSIGN_JSON = Path(__file__).resolve().parent.parent.parent / "docs" / "种族" / "format_cluster_assign.json"

# 勘探簇值 → 定稿 A~G 归一（X 前缀 = 勘探待定簇，形态已确认：X_race_full =
# 完整亚种页 → A；X_race_alt_traits = 替换特性 → B）
_CLUSTER_NORM = {
    "A_arg_page": "A",
    "X_race_full": "A",
    "B_alt_traits": "B",
    "X_race_alt_traits": "B",
    "C_fcb": "C",
    "D_monster_play": "D",
    "E_mixed": "E",
    "F_overview": "F",
    "G_sidebar": "G",
}


def _load_race_scan_rels() -> dict:
    """加载格式簇分配表 → {rel: 归一簇值}（扫描清单 + format_cluster 同源）"""
    try:
        with open(_RACE_ASSIGN_JSON, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        raise RuntimeError(
            f"无法加载格式簇分配表 {_RACE_ASSIGN_JSON}（种族扫描清单同口径来源）：{e}"
        ) from e
    norm = {}
    for rel, cluster in raw.items():
        if cluster not in _CLUSTER_NORM:
            raise RuntimeError(f"格式簇分配表含未知簇值: {cluster}（rel={rel}）")
        norm[rel] = _CLUSTER_NORM[cluster]
    return norm


RACE_SCAN_RELS: dict = _load_race_scan_rels()


def _race_file_condition(file_path: Path) -> bool:
    """种族文件判断：文件 rel 在格式簇分配表清单内（112 文件）"""
    try:
        rel = file_path.resolve().relative_to(_ORGANIZED_ROOT)
    except ValueError:
        return False
    return str(rel) in RACE_SCAN_RELS


def _race_group_for(file_path: Path) -> str:
    """族群（目录归属，元数据定稿 3.1）：核心/常见/罕见/其他/怪物法典MC/
    内海怪物志/冒险之路AP/来源书/概述"""
    parts = list(file_path.parts)
    try:
        i = parts.index("种族")
    except ValueError:
        return ""
    for p in parts[i + 1:-1]:
        if p in ("核心种族", "常见种族", "罕见种族", "其他种族"):
            return p[:-2]
        if p in ("怪物法典MC", "内海怪物志", "冒险之路AP"):
            return p
    if file_path.stem in ("page_10", "page_11"):
        return "概述"
    return "来源书"


# 怪物种族页按页编号（无种族目录名可循）→ 归属种族映射表
#（page_716 翼龙人 Wyvaran：文件首行即种族名，FCB 6 条 race_name 错位）
_PAGE_RACE_NAME_OVERRIDES = {
    "page_716": "翼龙人",
}

# KN132（2026-08-04）：race_intro 标题纯净性黑名单——书名/章节/特性名形态
# 的 intro 标题不得登记/覆盖 race_name（野兽血脉/夜之血脉/巫团血脉/海洋之血
# 书名、神裔能力变体/魔裔亚种章节、虫类领域/碧幻菌炸弹/进化型态/官方勘误
# 特性名）→ 跳过 → 条目继承文件级族名（_race_name_from_path）。纯净族名
#（猫族/土元素裔/绪任克斯枭族…）放行。全库 11 个多 intro 文件逐个核对过
# 黑名单覆盖：PHH 4 亚种/BotB 6 族/ISR 新种族 3 族/BotS 2 族全放行，
# BotN/BotC/神裔/魔裔/半蝎人/德洛人/page_15 污染 intro 全被拦。
# KN134（2026-08-04）追加 4 个概述页组标题词（核心种族/常见种族/罕见种族/
# 整体描述）——page_10 概述页组标题 intro 不得登记/覆盖 race_name（「核心
# 种族」若登记会污染其后 37 族介绍段继承），配合 _RACE_GROUP_TITLES 落空
# 特判。
_RE_RACE_NAME_IMPURE = re.compile(
    r"(能力变体|裔替换儿|亚种|勘误|领域|炸弹|型态|血脉|之血|种族特性|种族选项|新种族|核心种族|常见种族|罕见种族|整体描述)"
)

# KN134（2026-08-04）：概述页组标题（非族名 intro）→ infer_metadata 时
# race_name 强制落空——不落登记值（「常见种族」chunk 前已登记矮人）也不落
# title 兜底（组标题词非族名），检索按族过滤不误命中。族介绍段（矮人/精灵…）
# title 即族名，不在此列。
_RACE_GROUP_TITLES = ("核心种族", "常见种族", "罕见种族", "整体描述")


# ---- race_name 解析 stage 函数（供 entity_name_resolvers 注册） ----
# 判定函数本体留在 race.py；base.py 只提供「有序短路 + 例外前置」执行语义。
# 每个 resolver 返回 Optional[str]：str（含空串）= 命中；None = 继续下一个。


def _resolve_race_name_exception(proc: "RaceProcessor", chunk: Chunk, item: dict) -> Optional[str]:
    """例外前置：race_overview 行 title 即族名；概述页组标题 intro 非族名 → 落空。"""
    if chunk.component_type == "race_overview":
        return chunk.title
    if chunk.component_type == "race_intro" and chunk.title in _RACE_GROUP_TITLES:
        return ""
    return None


def _resolve_race_name_registered(proc: "RaceProcessor", chunk: Chunk, item: dict) -> Optional[str]:
    """intro 登记 / 替换特性组标题覆盖后的族名（build_chunk 已做纯净性过滤）。"""
    return proc._race_name if proc._race_name else None


def _resolve_race_name_dash_split(proc: "RaceProcessor", chunk: Chunk, item: dict) -> Optional[str]:
    """替换特性汇总标题「X——Y」→ 取 X 作为族名。"""
    if "——" in chunk.title:
        return chunk.title.split("——", 1)[0]
    return None


def _resolve_race_name_path(proc: "RaceProcessor", chunk: Chunk, item: dict) -> Optional[str]:
    """无 intro 文件按路径 / 页号映射归属种族兜底（含 _PAGE_RACE_NAME_OVERRIDES）。"""
    return proc._race_name_fallback if proc._race_name_fallback else None


def _race_name_from_path(file_path: Path) -> str:
    """无 intro 文件按路径归属种族兜底（k3 验收 R1）。

    天赋职业奖励系列（HA 版 FCB）等文件无 race_intro 条目，原兜底取
    条目标题（职业名）→ race_name 错位（人类天赋职业奖励 → 审判者等）。
    文件路径第三级目录即归属种族（种族/<分组>/<种族名>/xxx.md → 第三级）；
    怪物种族页（种族/怪物种族/page_NN，无目录名）走映射表；其余返回 ""
    保持 chunk.title 现状。

    KN132（2026-08-04）扩展两级/四级文件名族名兜底：
      - 怪物法典MC/内海怪物志 单文件（种族/怪物种族/怪物法典MC/大地精.md，
        四级）：文件名即族名（大地精/半蝎人/半人马_陷阵士 → 半人马），
        「开篇」除外——intro 标题（**大地精**）被状态机并吞时族名仍可溯
      - 两级「书名Xxx_章节」文件（种族/野兽血脉BotB_种族特性.md 等）：
        剥章节后缀取族名（夜之血脉BotN_吸血裔种族特性 → 吸血裔；阴影血脉
        BoS_剪影人 → 剪影人；罕见种族/位面冒险PA_暮行者.md → 暮行者）；
        多族/聚合文件剥光返回 ""（BotB/BotS/ISR 核心/新种族），族名靠
        条目级 intro/组标题覆盖（build_chunk）
    """
    parts = list(file_path.parts)
    try:
        i = parts.index("种族")
    except ValueError:
        return ""
    # 三级目录形态（分组/种族名/文件）：parts[i+3] 才是文件（同 _race_group_for
    # 的 [i+1:-1] 排文件逻辑）；两级形态（分组/文件，如 page_1456）不取
    if len(parts) > i + 3 and parts[i + 1] in ("核心种族", "常见种族", "罕见种族", "其他种族"):
        return parts[i + 2]
    if len(parts) > i + 1 and parts[i + 1] == "怪物种族":
        # KN132：怪物法典MC/内海怪物志 单文件（四级）——文件名即族名
        if len(parts) > i + 3 and parts[i + 2] in ("怪物法典MC", "内海怪物志"):
            stem = file_path.stem
            # 半人马_陷阵士 → 半人马（_ 前）；「开篇」非种族文件
            return stem.split("_")[0] if stem != "开篇" else ""
        return _PAGE_RACE_NAME_OVERRIDES.get(file_path.stem, "")
    # KN132：两级「书名Xxx_章节」文件（种族/<文件名>.md 或 种族/<分组>/<文件
    # 名>.md 且含 _——三级分支已排除 len > i+3，此处 len <= i+3 涵盖罕见种族/
    # 阴影血脉BoS_剪影人.md 等「分组/文件」形态）
    if len(parts) <= i + 3 and "_" in file_path.stem and not file_path.stem.startswith("page_"):
        chapter = file_path.stem.rpartition("_")[2]
        # 剥章节后缀词表（长→短）：吸血裔种族特性 → 吸血裔；替换儿种族
        # 选项 → 替换儿；影生暗生种族特性 → 影生暗生；核心种族替换特性 →
        # 核心（残留词 → ""）；种族特性 → ""（BotB 多族）
        for suffix in ("种族特性替换汇总", "替换种族特性", "种族替换特性", "种族特性", "种族选项", "新种族", "亚种", "种族"):
            if chapter.endswith(suffix):
                name = chapter[: -len(suffix)]
                return name if (len(name) >= 2 and name not in ("核心", "其他")) else ""
        # 无后缀可剥：_ 后即族名（剪影人/窃影鬼/暮行者/熵裔/秩裔）
        return chapter if len(chapter) >= 2 else ""
    return ""


# ---- 字段标签集（parse_fields 公共层参数；capture 标签 → 定稿 3.3 key）----
_RACE_LABEL_TO_KEY = {
    "先决条件": "prerequisites",
    "专长效果": "benefit",
    "灵光": "aura",
    "施法者等级": "caster_level",
    "价格": "cost",
    "重量": "weight",
    "制造条件": "crafting_conditions",
    "制造成本": "crafting_cost",
    "学派": "school",
    "环级": "spell_level",
    "等级": "spell_level",  # 法术块变体词（page_814 伽瑟兰/柳絮随风，2026-08-04）
    "施放时间": "casting_time",
    "施法时间": "casting_time",  # 法术块变体词（同上）
    "目标": "spell_targets",
}
# 边界标签（只作值边界不作 capture，KN013 M5 防吞值）：formats/race 拆行
# 标签集同款（特殊情况/装备位置等拆行边界但不产字段）；
# 「成分/距离/豁免检定」= 法术块变体词（page_814），作边界防 school 吞值
_RACE_EXTRA_LABELS = ("特殊情况", "装备位置", "射程", "范围", "持续时间", "豁免", "豁免检定", "法术抗力", "成分", "距离")
_RACE_ALL_FIELD_LABELS = tuple(_RACE_LABEL_TO_KEY)

# 规范字段全集（定稿 3.1/3.2/3.3，27 个 + field_status）
_RACE_CANONICAL_FIELDS = (
    "race_name", "race_name_en", "alternate_name", "race_group", "rp_value",
    "format_cluster", "source",
    "ability_adj", "bio_type", "size", "speed", "senses", "languages",
    "replaces", "prerequisites", "benefit", "cost", "weight", "aura",
    "caster_level", "crafting_conditions", "crafting_cost", "school",
    "spell_level", "casting_time", "spell_targets", "entry_subtype",
)

# 字段族 → 适用 component_type（字段对非适用形态 not_applicable）
_FIELD_FAMILY = {
    "ability_adj": {"race_intro", "race_overview"},
    "bio_type": {"race_intro", "race_overview"}, "size": {"race_intro", "race_overview"},
    "speed": {"race_intro", "race_overview"}, "senses": {"race_intro", "race_overview"},
    "languages": {"race_intro"},
    "replaces": {"alt_trait"},
    "prerequisites": {"race_feat"}, "benefit": {"race_feat"},
    "cost": {"race_item"}, "weight": {"race_item"}, "aura": {"race_item"},
    "caster_level": {"race_item"}, "crafting_conditions": {"race_item"},
    "crafting_cost": {"race_item"},
    "school": {"race_spell"}, "spell_level": {"race_spell"},
    "casting_time": {"race_spell"}, "spell_targets": {"race_spell"},
    "entry_subtype": {"race_variant"},
}


# ---- 条目级字段提取正则 ----

# 属性调整：归一后行形态 **+2敏捷，+2魅力，-2感知**：…（数字开头字段行）
_RE_INTRO_ABILITY_ADJ = re.compile(r"^\*\*([+−-]?\d[^\n]*?)\*\*[：:]\s*(.+)$", re.M)
# 裸标签形态（X_race_full 亚种页）：替换属性调整：+2力量…
_RE_INTRO_ABILITY_ADJ_BARE = re.compile(r"^[ \t　]*替换?属性调整[：:]\s*(.+)$", re.M)
# 通用字段行（**标签**：值），标签含白名单词 → 取标签与值
_RE_INTRO_FIELD = re.compile(
    r"^\*\*([一-鿿A-Za-z（）()\s/]*?(?:生物类型|体型|速度|语言)[^\n]*?)\*\*[：:]\s*(.+)$",
    re.M,
)
# 感官行：**昏暗视觉（Low-Light Vision）**：…（含视觉/嗅觉/听觉/感官）
_RE_INTRO_SENSES = re.compile(
    r"^\*\*([一-鿿]*?(?:视觉|嗅觉|听觉|感官|感观)[一-鿿（()A-Za-z\- ]*?)\*\*[：:]\s*(.+)$",
    re.M,
)
# 法术表格行：| 学派 |  | 防护系 |（race_spell 表格形态，parse_fields 星形不覆盖）
_RE_TABLE_FIELD = re.compile(
    r"^\|\s*(学派|环级|施放时间|目标)\s*\|\s*[^|\n]*\|\s*([^|\n]+)\s*\|", re.M
)
# name_en 尾部标注段：RP 值（Iron Citizen 2 RP）与 PFS 标记（…, PFS禁用）
_RE_EN_RP_TAIL = re.compile(r"\s*\d+\s*RP\s*$")
_RE_EN_PFS_SEG = re.compile(r"[，,、]\s*PFS[^，,、]*$")

# MC 杂项细分（race_variant 的 entry_subtype，定稿 3.3）
_ENTRY_SUBTYPES = ("模板", "血统", "陷阱", "诅咒", "巫术", "领域", "背景", "炼金发现", "秘示域", "仆从")


def _clean_name_en(raw_en: str) -> tuple:
    """剥离 name_en 尾部 RP/PFS 标注段 → (清洗后 en, rp_value)。

    formats 层 _split_paren_content 把含字母的括号段（2 RP / PFS禁用）并入
    英文名（勘探「标题内嵌标注」traps），aliases 须剥离防检索污染；
    rp_value 存提取值（定稿 3.1，(2RP) 标注）。
    """
    rp = ""
    en = (raw_en or "").strip()
    m = _RE_EN_RP_TAIL.search(en)
    if m:
        rp = m.group(0).replace(" ", "").strip()
        en = en[:m.start()].rstrip(",，、 ").strip()
    en = _RE_EN_PFS_SEG.sub("", en).strip()
    # 星壳嵌套残留（KN133：`（****Serpent's Sense, ****Ex****）` 星壳
    # 嵌套剥除后英文名段间残留 `**`，aliases 污染检索）——最后剥净
    en = en.replace("**", "").strip()
    return en, rp


def _extract_entry_subtype(item: dict) -> str:
    """MC 杂项细分：条目名含关键字（模板/血统/陷阱/…）→ subtype"""
    name = item.get("name", "") or ""
    for kw in _ENTRY_SUBTYPES:
        if kw in name:
            return kw
    return ""


# ---- 后处理链（race 版报告目录，防覆盖专长报告）----


class RaceBackfillChmTocPath(BackfillChmTocPath):
    """toc 空回填（同专长三级链路：注释源 md → md_map / 来源行路径），
    报告写 docs/种族/（子类覆写类属性目录，feat_chain 逻辑零改动）"""
    DEFAULT_REPORT_DIR = Path("docs/种族")


class RaceBackfillFeatSource(BackfillFeatSource):
    """metadata.source 补齐（引用块），报告写 docs/种族/"""
    DEFAULT_REPORT_DIR = Path("docs/种族")


class RaceBackfillBookFromSource:
    """book '?' 回填：metadata.source「出自《X pg. N》」→ 书名映射表。

    背景：罕见种族/核心种族亚种页条目级来源行（**出自《进阶种族手册 pg. 1》**，
    page_934/1456 等）由 formats 层提取进 metadata.source，但 resolve_source 的
    provider 链与引用块兜底均不覆盖该形态 → book '?' 1325 中 36 个可解析。
    书名为源数据自带体系（page_934 头部「书名参考：」表同源：进阶玩家手册=APG
    等异译，HA=恐怖冒险与共享表一致）。
    置信度 65：条目级显式来源标记，与引用块兜底档一致。
    幂等：book 已解析跳过；只改 book 三字段 + source_confidence，备份 .bak_bookfix。
    """
    DEFAULT_REPORT_DIR = Path("docs/种族")

    # source 书名（剥「 pg. N」页码后）→ (缩写, 中文名, 英文名)；键为源数据原文
    _BOOK_MAP = {
        "进阶种族手册": ("ARG", "种族指南", "Advanced Race Guide"),
        "进阶玩家手册": ("APG", "进阶玩家指南", "Advanced Player's Guide"),
        "恐怖冒险": ("HA", "恐怖冒险", "Horror Adventures"),
        "内海种族": ("ISR", "内海种族", "Inner Sea Races"),
        "阴影血脉": ("BoS", "阴影血脉", "Blood of Shadows"),
        "邪恶特务": ("AoE", "邪恶特务", "Agents of Evil"),
        "格拉利昂的混种": ("BoG", "格拉利昂的混种", "Bastards of Golarion"),
        "边缘英雄": ("HftF", "边缘英雄", "Heroes from the Fringe"),
        "荒野英雄": ("HotW", "荒野英雄", "Heroes of the Wild"),
        "皇庭英豪": ("HotHC", "皇庭英豪", "Heroes of the High Court"),
        "街道英雄": ("HotS", "街道英雄", "Heroes of the Streets"),
        "龙之遗产": ("LoD", "龙之遗产", "Legacy of Dragons"),
        "第一世界遗产": ("LotFW", "第一世界的遗产", "Legacy of the First World"),
        "Ultimate Wilderness": ("UW", "极限荒野", "Ultimate Wilderness"),
    }
    _RE_SOURCE_BOOK = re.compile(r"出自《([^》]+)》")

    @staticmethod
    def _book_title(raw: str) -> str:
        """source 书名剥页码：出自《进阶种族手册 pg. 1》→ 进阶种族手册"""
        return re.sub(r"\s*pg\.\s*\d+\s*$", "", raw).strip()

    def run(self, output_dir: Path, report_dir: Optional[Path] = None) -> Dict[str, Any]:
        chunks_path = output_dir / "chunks.jsonl"
        report_dir = report_dir or type(self).DEFAULT_REPORT_DIR
        with open(chunks_path, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]

        stats = Counter()
        unfilled = []
        for r in rows:
            if r.get("book_abbreviation") != "?":
                continue
            m = self._RE_SOURCE_BOOK.search((r.get("metadata") or {}).get("source") or "")
            if not m:
                continue
            hit = self._BOOK_MAP.get(self._book_title(m.group(1)))
            if not hit:
                unfilled.append(m.group(1))
                continue
            abbr, cn, en = hit
            r["book_abbreviation"] = abbr
            r["book_name_cn"] = cn
            r["book_name_en"] = en
            r["source_confidence"] = 65
            stats[abbr] += 1

        if stats:
            shutil.copyfile(chunks_path, str(chunks_path) + ".bak_bookfix")
            with open(chunks_path, "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")

        report_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            "# race book 回填报告（finalize，RaceBackfillBookFromSource）",
            "",
            f"> 回填 {sum(stats.values())} 个（书 {len(stats)} 种）",
            f"> 依据：metadata.source「出自《X pg. N》」（formats 层条目级来源行），"
            f"书名映射表同源 page_934 头部「书名参考：」表",
            "",
            "| 书 | 数量 |",
            "|---|---|",
        ]
        lines += [f"| {abbr} | {n} |" for abbr, n in stats.most_common()]
        if unfilled:
            from collections import Counter as _C
            lines += ["", f"未映射书名（保持 '?'）：" + "；".join(f"{b}×{n}" for b, n in _C(unfilled).most_common())]
        with open(report_dir / "race_book_backfill_report.md", "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return {"filled": sum(stats.values()), "unfilled": len(unfilled)}


class RaceProcessor(FileProcessor):
    """种族文件处理器"""

    # entity name 解析 stage：例外前置 → intro 登记 → 「——」拆分 → 路径兜底；
    # base.process() 在 build_chunk 后执行，首个非空结果写入 chunk.metadata['entity_name']。
    entity_name_resolvers = [
        _resolve_race_name_exception,
        _resolve_race_name_registered,
        _resolve_race_name_dash_split,
        _resolve_race_name_path,
    ]

    # v2.2 决策 A 模式：finalize 后处理链（顺序即声明顺序）。首版 = 通用两件套
    # （toc 回填 + source 补齐，与类目无关）；book '?' 统计后若需映射步骤再补。
    POSTPROCESSORS = [RaceBackfillChmTocPath, RaceBackfillBookFromSource, RaceBackfillFeatSource]

    @property
    def category(self) -> str:
        return "race"

    def __init__(self, source_resolver: SourceResolver):
        super().__init__(source_resolver=source_resolver, format_handler=RaceFormat())
        # 逐文件状态（process() 重置）
        self._race_name = ""
        self._race_name_en = ""
        self._race_group = ""
        self._race_name_fallback = ""
        self._format_cluster = ""

    def process(self, file_path: Path) -> List[Chunk]:
        """逐文件状态重置：族群/格式簇按文件固定；race_name 由首个 intro
        登记（无 intro 文件由路径归属兜底，见 _race_name_from_path）"""
        self._race_name = ""
        self._race_name_en = ""
        self._race_group = _race_group_for(file_path)
        self._race_name_fallback = _race_name_from_path(file_path)
        try:
            rel = file_path.resolve().relative_to(_ORGANIZED_ROOT)
            self._format_cluster = RACE_SCAN_RELS[str(rel)]
        except (ValueError, KeyError):
            self._format_cluster = ""
        return super().process(file_path)

    def build_chunk(self, template: Chunk, item: dict) -> Chunk:
        """设置种族条目标题、正文、英文别名与 component_type"""
        template.text = item.get("text", "")
        # KN133「：」开头家族（源形态 `**X（EN）**：正文`，normalize 拆行后
        # 正文行保留行首冒号，全库 51 处）——剥行首「：」防检索污染
        # KN135-2（2026-08-04）：半角 `:` 同剥（源形态 `**X（EN）**:正文`
        # 星壳标题+半角冒号剥壳残留，page_716/939/940 共 7 处）
        template.text = re.sub(r"(?m)^[:：]", "", template.text)
        template.title = " ".join(item.get("name", "").split())
        cleaned_en, _rp = _clean_name_en(item.get("name_en", "") or "")
        template.aliases = [cleaned_en] if cleaned_en else []
        # 首个 race_intro 登记文件主种族名（无 intro 文件由目录名兜底，见下）。
        # KN132（2026-08-04）：放开「只登记首个」——多种族文件（BotB 6 族/
        # PHH 4 亚种/ISR 新种族 3 族/BotS 2 族）族标题逐块覆盖，条目继承最近
        # 族标题；纯净性黑名单（书名/章节/特性名 intro）跳过登记与覆盖 →
        # 条目继承文件级族名（_race_name_from_path）
        if item.get("kind") == "race_intro" and not _RE_RACE_NAME_IMPURE.search(template.title):
            self._race_name = template.title
            self._race_name_en = cleaned_en
        # KN132：替换特性组标题（ISR 核心聚合/page_752，裸中文标题+组句
        #「X角色可以选择以下种族特性替换原本的种族特性。」）→ 族名覆盖，
        # 组内条目继承（条目原口径=特性名 → 族名，与 M22/ISR 其他「X——Y」
        # 族名口径一致）；「其他种族」开场组句形态不同不命中
        if (item.get("_bare_cn_title") and item.get("kind") == "alt_trait"
                and "替换原本的种族特性" in template.text):
            self._race_name = template.title
            self._race_name_en = cleaned_en
        template.component_type = item.get("kind", "race_trait")
        # D 簇（怪物玩法）裸标题主条目：formats 层 intro 态裸标题 → race_sidebar
        #（降权语义），怪物主条目（霜巨人等）应正常权重 → monster_block
        #（簇感知映射，非业务特判——簇值来自勘探分配表）
        if self._format_cluster == "D" and template.component_type == "race_sidebar":
            template.component_type = "monster_block"
        return template

    def resolve_source(self, chunk: Chunk, ctx: SourceContext, item: dict) -> Chunk:
        """解析来源书：标准 provider 链优先，失败时按文件来源标记兜底。

        共享链（SOURCE_BOOK_ABBREVIATIONS）未覆盖的种族书（惧怖冒险/位面行者
        手册等），文件内来源引用块（> 来源：… → 缩写 →）自带完整书名，
        置信度 65：与专长引用块兜底档一致（显式来源标记，高于纯正文提及 50）。
        """
        result = self.source_resolver.resolve(ctx)
        if result.book_abbreviation == "?":
            hint = _feat_source_from_content(ctx.file_content)
            if hint:
                result = SourceResult(hint[0], hint[1], hint[2], 65, "RaceSourceLineProvider")
        chunk.book_abbreviation = result.book_abbreviation
        chunk.book_name_cn = result.book_name_cn
        chunk.book_name_en = result.book_name_en
        chunk.source_confidence = result.confidence
        return chunk

    def infer_metadata(self, chunk: Chunk, item: dict) -> Chunk:
        """27 字段元数据（种族元数据设计定稿 3.1/3.2/3.3）。

        - 文本字段走公共 parse_fields（**标签：** / **标签**： 双格式）
        - 结构字段（intro 专属）从 text 字段行正则提取（ARG 页行形态）
        - 条目级字段按 component_type 分支取用（字段族 not_applicable）
        - field_status 三态（parsed/missing/not_applicable，无 ambiguous）
        """
        text = item.get("text", "")
        raw = parse_fields(
            text,
            all_labels=_RACE_ALL_FIELD_LABELS,
            extra_labels=_RACE_EXTRA_LABELS,
            label_to_key=_RACE_LABEL_TO_KEY,
        )
        ct = chunk.component_type
        md: Dict[str, Any] = {}

        # ---- 3.1 核心字段 ----
        # race_name 由 entity_name_resolvers 有序链产出（base.process() 已写入
        # chunk.metadata['entity_name']）；测试等绕过 base.process() 的路径回退到
        # resolve_entity_name() 现场计算，保证语义一致。
        if "entity_name" in chunk.metadata:
            md["race_name"] = chunk.metadata["entity_name"]
        else:
            md["race_name"] = self.resolve_entity_name(chunk, item)
        md["race_name_en"] = self._race_name_en
        # 又译段 formats 层 _split_paren_content 已剥离且无独立字段形态 → 恒空
        #（全库登记见产出即检文档，verify 不强制）
        md["alternate_name"] = ""
        md["race_group"] = self._race_group
        md["rp_value"] = _clean_name_en(item.get("name_en", "") or "")[1]
        md["format_cluster"] = self._format_cluster
        md["source"] = item.get("source", "")

        # ---- 3.2 结构字段（intro 专属；overview 表格行消费 formats 层拆好的键）----
        if ct == "race_intro":
            md["ability_adj"] = self._extract_ability_adj(text)
            md["bio_type"] = self._extract_intro_field(text, "生物类型")
            md["size"] = self._extract_size(text)
            md["speed"] = self._extract_speed(text)
            md["senses"] = self._extract_senses(text)
            md["languages"] = self._extract_intro_field(text, "语言")

        # ---- 3.3 条目级字段 ----
        md["replaces"] = item.get("replaces", "")
        if ct == "race_feat":
            md["prerequisites"] = raw.get("prerequisites", "")
            md["benefit"] = raw.get("benefit", "")
        elif ct == "race_item":
            for key in ("cost", "weight", "aura", "caster_level",
                        "crafting_conditions", "crafting_cost"):
                md[key] = raw.get(key, "")
        elif ct == "race_spell":
            md["school"] = raw.get("school", "") or self._extract_table_field(text, "学派")
            md["spell_level"] = raw.get("spell_level", "") or self._extract_table_field(text, "环级")
            md["casting_time"] = raw.get("casting_time", "") or self._extract_table_field(text, "施放时间")
            md["spell_targets"] = raw.get("spell_targets", "") or self._extract_table_field(text, "目标")
        elif ct == "race_overview":
            # 概述表行：结构字段由 formats 层表格拆分直接消费（无语言列）
            for key in ("ability_adj", "bio_type", "size", "speed", "senses"):
                md[key] = item.get(key, "")
        elif ct == "race_variant":
            md["entry_subtype"] = _extract_entry_subtype(item)

        md["field_status"] = self._compute_field_status(md, ct)
        chunk.metadata = md
        return chunk

    # ---- 结构字段提取器 ----

    @staticmethod
    def _extract_ability_adj(text: str) -> str:
        """属性调整：数字开头字段行优先（ARG 标准形态），裸标签兜底"""
        m = _RE_INTRO_ABILITY_ADJ.search(text)
        if m:
            return m.group(1).strip()
        m = _RE_INTRO_ABILITY_ADJ_BARE.search(text)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _extract_intro_field(text: str, label: str) -> str:
        """通用字段行值（**标签**：值，标签含 label）"""
        for m in _RE_INTRO_FIELD.finditer(text):
            if label in m.group(1):
                return m.group(2).strip()
        return ""

    @classmethod
    def _extract_size(cls, text: str) -> str:
        """体型：**中型体型**：… → 中型（标签去「体型」后缀）"""
        for m in _RE_INTRO_FIELD.finditer(text):
            if "体型" in m.group(1):
                return m.group(1).replace("体型", "").strip()
        return ""

    @classmethod
    def _extract_speed(cls, text: str) -> str:
        """速度：描述含数值（猫族的基本速度为30尺 → 30尺），失败存标签去「速度」"""
        for m in _RE_INTRO_FIELD.finditer(text):
            if "速度" in m.group(1):
                v = re.search(r"\d+\s*尺", m.group(2))
                return v.group(0) if v else m.group(1).replace("速度", "").strip()
        return ""

    @staticmethod
    def _extract_senses(text: str) -> str:
        """感官：多行合并（昏暗视觉 + 黑暗视觉 → "昏暗视觉，黑暗视觉"）"""
        parts = []
        for m in _RE_INTRO_SENSES.finditer(text):
            name = re.sub(r"[（(].*?[）)]", "", m.group(1)).strip()
            if name and name not in parts:
                parts.append(name)
        return "，".join(parts)

    @staticmethod
    def _extract_table_field(text: str, label: str) -> str:
        """法术表格行值（| 学派 |  | 防护系 |）"""
        for m in _RE_TABLE_FIELD.finditer(text):
            if m.group(1) == label:
                return m.group(2).strip()
        return ""

    # ---- field_status 三态（定稿：parsed / missing / not_applicable，无 ambiguous）----

    @staticmethod
    def _compute_field_status(metadata: dict, ct: str) -> dict:
        """计算每个规范字段的解析状态。

        字段族判定：条目级/结构字段对非适用 component_type → not_applicable
        （alt_trait 无 cost、race_feat 无 ability_adj 等）；核心字段（race_name
        等）全类型适用，缺失 → missing。
        """
        status = {}
        for field in _RACE_CANONICAL_FIELDS:
            ok = bool(metadata.get(field))
            if ok:
                status[field] = "parsed"
            elif field in _FIELD_FAMILY and ct not in _FIELD_FAMILY[field]:
                status[field] = "not_applicable"
            else:
                status[field] = "missing"
        return status


# 模块加载时自动注册
register("race", RaceProcessor, _race_file_condition)
