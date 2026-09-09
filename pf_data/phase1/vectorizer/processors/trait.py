"""processors/trait.py — 背景特性文件处理器

设计（2026-08-05，元数据设计 + source_spec 人工门 2 后实现）：
  - 复用 FileProcessor 模板方法（三钩子：build_chunk / resolve_source / infer_metadata）
  - 扫描清单 = docs/背景特性/format_cluster_assign.json 63 rel（勘探同口径）
  - component_type 三值：trait / trait_intro（章节介绍段，formats 层
    format_cluster="intro" 标记）/ trait_flaw（缺陷条目，item.flaw 标记）；
    trait_category 不产 chunk（设计决策点 2——章节标题 formats 层已排除，
    与种族 KN085 空 text 口径一致）
  - trait_type 归一词表 12 值（元数据设计 §四）：formats 层字段行/标题括号/
    【】前置已聚合为原始 list，此处归一（信仰/宗教/信念→信念、基础（X）
    并入对应类型等）；无字段文件（ISG）trait_type 空 → missing 不臆造（待确认点 4）
  - resolve_source：共享 provider 链优先 → 专属表冲突覆盖（source_spec 第三
    部分 50 书权威，config/trait_sources.json——共享表 FoC/FoB 为信仰之书
    错义，堕落信念/均衡信念须截断）→ 引用块兜底（复用 feat 解析）→
    条目级【书缩写】兜底（基础页 page_150~158 的 APG/UCa/AA）
  - infer_metadata：6 字段直通 item（formats 层已解析字段行/出自行/神名括号，
    效果值已并入正文）+ field_status 三态；deity 字段族按宗教主题判
    not_applicable（设计 §3.3「非宗教背景无 deity」）
  - POSTPROCESSORS = toc 回填（通用件子类覆写报告目录到 docs/背景特性/）
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from vectorizer.formats.trait import TraitFormat
from vectorizer.postprocess.feat_chain import BackfillChmTocPath
from vectorizer.processors import register
from vectorizer.processors.base import Chunk, FileProcessor
from vectorizer.processors.feat import _feat_source_from_content
from vectorizer.sources.providers import SourceContext, SourceResolver, SourceResult

logger = logging.getLogger(__name__)


# ---- 输入范围（勘探同口径：format_cluster_assign.json 63 rel）----
_ORGANIZED_ROOT = Path(__file__).resolve().parent.parent.parent / "pf_rules_md_organized"
_TRAIT_ASSIGN_JSON = (
    Path(__file__).resolve().parent.parent.parent / "docs" / "背景特性" / "format_cluster_assign.json"
)


def _load_trait_scan_rels() -> dict:
    """加载格式簇分配表 → {rel: 簇值}（扫描清单 + 文件簇 format_cluster 同源）"""
    try:
        with open(_TRAIT_ASSIGN_JSON, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        raise RuntimeError(
            f"无法加载格式簇分配表 {_TRAIT_ASSIGN_JSON}（背景特性扫描清单同口径来源）：{e}"
        ) from e
    # 簇值直接透传（15 簇是定稿形态，无需 race 式归一；值异常即报错防静默失配）
    for rel, cluster in raw.items():
        if not isinstance(cluster, str) or not cluster:
            raise RuntimeError(f"格式簇分配表含异常簇值: {cluster!r}（rel={rel}）")
    return raw


TRAIT_SCAN_RELS: dict = _load_trait_scan_rels()


def _trait_file_condition(file_path: Path) -> bool:
    """背景特性文件判断：文件 rel 在格式簇分配表清单内（63 文件）"""
    try:
        rel = file_path.resolve().relative_to(_ORGANIZED_ROOT)
    except ValueError:
        return False
    return str(rel) in TRAIT_SCAN_RELS


# ---- 来源书专属表（source_spec 第三部分 50 书权威映射） ----
# 键 = 文件名前缀 / 规范缩写 / 中英文书名（多键同值）。
# 共享链（SOURCE_BOOK_ABBREVIATIONS）FoC/FoB 为「信仰之书」错义
#（背景特性 FoC=堕落信念 Champions of Corruption / FoB=均衡信念
# Champions of Balance）；PotS 冲突（沙之子民/繁星子民）中文键优先截断。
_TRAIT_SOURCES_JSON = Path(__file__).resolve().parent.parent / "config" / "trait_sources.json"


def _load_trait_sources() -> Dict[str, dict]:
    with open(_TRAIT_SOURCES_JSON, encoding="utf-8") as f:
        return json.load(f).get("sources", {})


TRAIT_SOURCES: Dict[str, dict] = _load_trait_sources()

# 文件名来源线索：`安多安ASoL_背景特性` → (安多安, ASoL)；
# `繁星子民_背景特性` / `格拉里昂的人类_种族背景特性` → (繁星子民, None)；
# 基础页 page_NN 无后缀 → (None, None)。
# 两段式：先试「中文+ASCII」形态（非贪婪中文 + 贪婪尾 ASCII），
# 再试纯中文形态——abbr 组必填才能抓到尾缩写（可选组会回溯为 None）。
_RE_FILE_CN_PREFIX = re.compile(r"^(.*?)([A-Za-z0-9&]+)_(?:种族)?背景特性$")
_RE_FILE_CN_ONLY = re.compile(r"^(.+?)_(?:种族)?背景特性$")


def _extract_file_hints(stem: str) -> tuple:
    m = _RE_FILE_CN_PREFIX.match(stem)
    if m:
        return (m.group(1).strip() or None, m.group(2))
    m = _RE_FILE_CN_ONLY.match(stem)
    if m:
        return (m.group(1).strip() or None, None)
    return (None, None)


# 条目级【书缩写】形态（基础页 source 值：APG/UCa/AA/WMH）
_RE_ITEM_SOURCE_ABBR = re.compile(r"^[A-Za-z&]{1,6}$")


# ---- trait_type 归一词表（元数据设计 §四） ----

# 精确词归一（26 值 → 13 值）；「宗教背景」优先于「宗教」（长词先查）
_TRAIT_TYPE_NORM = {
    "信仰": "信念",
    "宗教": "信念",  # 裸「宗教」标签 → 信念（宗教背景→宗教见下）
    "信念": "信念",
    "信念背景": "信念",  # 产出即检补漏：任务与战役「信念背景」变体
    "地区背景": "地区",
    "区域": "地区",      # 产出即检补漏：ISP 分类字段「区域」变体
    "社交": "社会",
    "社会背景": "社会",   # 2026-08-06 章节标记行补漏（矮人 **社会背景：）
    "战斗背景": "战斗",
    "魔法背景": "魔法",
    "种族背景": "种族",
    "宗教背景": "宗教",
    "信仰背景": "信念",   # 2026-08-06 章节标记行补漏（精灵 Religious Traits 双语行）
    "典范": "典范",  # 独立体系（取代两个通常背景，产出即检补漏）
    "典范背景": "典范",   # 2026-08-06 章节标记行补漏（HH 段 17 背景）
    "缺陷背景": "缺陷",   # 2026-08-06 章节标记行补漏（新词表值，方案 R1）
    "派系背景": "派系",
    "宇宙背景": "宇宙",
    "装备背景": "装备",
    "坐骑背景": "坐骑",
}
# 基础（X）并入对应类型（人工门拍板 2026-08-05：基础（战斗）→ 战斗，
# 不保留「基础」限定词，与来源书扩展条目同词表）；异体「基本（魔法）」
# 同样并入（勘探 26 值含「基本（魔法）」）
_RE_BASIC_TRAIT = re.compile(r"^基[本础]?[（(]([^）)]+)[）)]$")


def _normalize_trait_types(values: list) -> list:
    """trait_type 归一词表（12 值）：精确词 → 词表；基础（X）→ 括号内类型
    词（并入）；未知值保持原样（不臆造不丢弃，审计可登记）；去重保序。"""
    out: list = []
    for v in values:
        v = (v or "").strip()
        if not v:
            continue
        # 基础（X）形态先命中：取括号内类型词（基础（战斗）→ 战斗），
        # 再走统一归一链（剥括号残留异体 + 精确词映射）
        m = _RE_BASIC_TRAIT.match(v)
        if m:
            v = m.group(1)
        v = re.sub(r"[（(][^）)]*[）)]$", "", v).strip()
        v = _TRAIT_TYPE_NORM.get(v, v)
        if v and v not in out:
            out.append(v)
    return out


# ---- 页面级默认 trait_type（方案 R2，2026-08-06）----
# CHM 目录「背景特性」L1 下 13 个类型目录直接对应基础页/体系页（无中间层）；
# 页面无章节标记行/字段行时条目按页面类型兜底（页 = 目录）。
# 背景特性17 为混合页（原内容=篷车星系「宇宙」+ HH 补录段）——R3 特殊规则：
# HH 段条目（formats 层 _hh_section 戳）跳过此表（段落级 marker 填，无标记
# 维持空），原内容段按页面默认「宇宙」。
_PAGE_TYPE_DEFAULT = {
    "page_150": "战斗", "page_151": "信念", "page_152": "魔法",
    "page_153": "社会", "page_154": "派系", "page_155": "种族",
    "page_156": "地区", "page_157": "宗教", "page_158": "缺陷",
    "page_1579": "装备", "背景特性17": "宇宙", "坐骑背景": "坐骑",
}

# 宗教主题（deity 字段族适用判定，设计 §3.3）
_RELIGIOUS_TRAIT_TYPES = {"宗教", "信念"}

# 规范字段全集（元数据设计 §3.1/3.2/3.3，7 个 + field_status）
_TRAIT_CANONICAL_FIELDS = (
    "trait_type", "requirement", "source", "deity",
    "pfs_eligible", "flaw", "format_cluster",
)


class TraitBackfillChmTocPath(BackfillChmTocPath):
    """toc 空回填（同专长三级链路：注释源 md → md_map / 来源行路径），
    报告写 docs/背景特性/（子类覆写类属性目录，feat_chain 逻辑零改动）"""
    DEFAULT_REPORT_DIR = Path("docs/背景特性")


class TraitProcessor(FileProcessor):
    """背景特性文件处理器"""

    # finalize 后处理链（v2.2 决策 A 模式）：toc 回填通用件，报告目录覆写。
    # source 补齐（BackfillFeatSource）不需要：metadata.source 在 formats 层
    # 已从出自行/【书缩写】填好，引用块是文件头整理标记非条目正文。
    POSTPROCESSORS = [TraitBackfillChmTocPath]

    @property
    def category(self) -> str:
        return "trait"

    def __init__(self, source_resolver: SourceResolver):
        super().__init__(source_resolver=source_resolver, format_handler=TraitFormat())
        self._format_cluster = ""

    def process(self, file_path: Path) -> List[Chunk]:
        """逐文件状态重置：文件簇按扫描清单固定（infer_metadata 引用）"""
        self._format_cluster = ""
        try:
            rel = file_path.resolve().relative_to(_ORGANIZED_ROOT)
            self._format_cluster = TRAIT_SCAN_RELS[str(rel)]
        except (ValueError, KeyError):
            pass
        return super().process(file_path)

    def build_chunk(self, template: Chunk, item: dict) -> Chunk:
        """设置条目标题、正文、英文别名与 component_type

        component_type 三值（元数据设计 §二）：intro 标记（章节介绍段）→
        trait_intro；flaw 标记 → trait_flaw（缺陷独立规则体系，PFS 禁用 +
        反向特性，检索需可区分）；其余 → trait。trait_category 不产 chunk
        （formats 层章节标题已排除），此处无对应分支。
        """
        template.title = " ".join(item.get("name", "").split())
        template.text = item.get("text", "")
        template.aliases = [" ".join(item["name_en"].split())] if item.get("name_en") else []
        if item.get("format_cluster") == "intro":
            template.component_type = "trait_intro"
        elif item.get("flaw"):
            template.component_type = "trait_flaw"
        return template

    def resolve_source(self, chunk: Chunk, ctx: SourceContext, item: dict) -> Chunk:
        """解析来源书：共享链优先 → 专属表冲突覆盖 → 引用块 → 条目级缩写。

        1. 共享 provider 链（HTML 注释 95 / 聚合 85 / 目录 80 / 文件名 75）
        2. 专属表冲突覆盖：文件名来源线索（前缀/后缀缩写）查 trait_sources
           ——共享表 FoC/FoB 为信仰之书错义（trait 是堕落/均衡信念），同缩写
           但中文名不同即覆盖（trait 表是 source_spec 人工核对权威）
        3. 引用块兜底（复用 feat 解析，置信度 65）
        4. 条目级【书缩写】（基础页 page_150~158 的 APG/UCa/AA，置信度 60）
        """
        result = self.source_resolver.resolve(ctx)

        cn_hint, abbr_hint = _extract_file_hints(ctx.file_path.stem)
        entry = None
        if cn_hint:
            entry = TRAIT_SOURCES.get(cn_hint)
        if entry is None and abbr_hint:
            entry = TRAIT_SOURCES.get(abbr_hint)
        if entry and (result.book_abbreviation == "?" or entry["cn"] != result.book_name_cn):
            # 专属表命中且与共享链冲突（FoC/FoB 错义）→ trait 表权威
            result = SourceResult(entry["abbr"], entry["cn"], entry["en"], 75, "TraitFileNameProvider")
        elif result.book_abbreviation == "?":
            hint = _feat_source_from_content(ctx.file_content)
            if hint:
                result = SourceResult(hint[0], hint[1], hint[2], 65, "TraitSourceLineProvider")

        if result.book_abbreviation == "?":
            src = (item or {}).get("source", "") or ""
            # 剥页码/星壳/《》半壳后缀再匹配：`Knights of the Inner Sea pg. 33`
            # （坐骑背景 `**出自**：` 字段值含页码）/ `**SH**`（星壳包缩写）/
            # `间谍大师手册Spymaster's Handbook》 第7页`（缺《半壳）——先剥再查
            probe = re.sub(
                r"[\*]+|[Pp]g\.?\s*\d+[）)]?$|》?\s*第[0-9零一二三四五六七八九十百]{1,6}页$",
                "", src,
            ).strip()
            for cand in (src, probe):
                if not cand:
                    continue
                e = TRAIT_SOURCES.get(cand)
                if e is None and _RE_ITEM_SOURCE_ABBR.match(cand):
                    e = TRAIT_SOURCES.get(cand)
                if e:
                    result = SourceResult(
                        e["abbr"], e["cn"], e["en"], 60, "TraitItemSourceProvider"
                    )
                    break

        chunk.book_abbreviation = result.book_abbreviation
        chunk.book_name_cn = result.book_name_cn
        chunk.book_name_en = result.book_name_en
        chunk.source_confidence = result.confidence
        return chunk

    def infer_metadata(self, chunk: Chunk, item: dict) -> Chunk:
        """7 字段元数据（元数据设计 §三）。

        - trait_type / requirement / source / deity 直通 item（formats 层
          已解析字段行/出自行/神名括号；效果值并入正文不单列字段）
        - trait_type 过归一词表（12+1）；无字段文件（ISG）→ 空 list 不臆造
        - pfs_eligible / flaw 布尔（formats 层判定）
        - format_cluster = 文件簇（扫描清单，split 层 item 簇仅 intro 分支
          用于 component_type，不进 metadata——文件簇是勘探定稿口径）
        - field_status 三态（parsed / missing / not_applicable）
        """
        md: Dict[str, Any] = {}
        md["trait_type"] = _normalize_trait_types(item.get("trait_type", []) or [])
        # 兜底链（方案 2026-08-06 优先级）：解析值 > 章节标记行 marker > R2
        # 页面级默认 > missing。marker 段落级（formats 层 _stamp_item 戳）；
        # R2 页面默认按 doc_id 查表（页 = CHM 类型目录），trait_intro（无字段
        # 行 not_applicable 豁免）与 HH 补录段条目（R3：段落级 marker 填，
        # 无标记维持空）跳过防误伤。
        if not md["trait_type"]:
            if item.get("_trait_type_from_marker"):
                md["trait_type"] = _normalize_trait_types([item["_trait_type_from_marker"]])
            elif chunk.component_type != "trait_intro" and not item.get("_hh_section"):
                default = _PAGE_TYPE_DEFAULT.get(chunk.doc_id)
                if default:
                    md["trait_type"] = [default]
        md["requirement"] = item.get("requirement", "")
        md["source"] = item.get("source", "")
        md["deity"] = item.get("deity", "")
        md["pfs_eligible"] = bool(item.get("pfs_eligible", False))
        md["flaw"] = bool(item.get("flaw", False))
        md["format_cluster"] = self._format_cluster
        md["field_status"] = self._compute_field_status(md, chunk.component_type, chunk.doc_id)
        chunk.metadata = md
        return chunk

    # ---- field_status 三态（设计 §3.3：parsed / missing / not_applicable）----

    @staticmethod
    def _compute_field_status(metadata: dict, ct: str, doc_id: str = "") -> dict:
        """计算每个规范字段的解析状态。

        - trait_type 为 list：非空 = parsed
        - pfs_eligible / flaw 为布尔：True = parsed，False = missing（专长同款）；
          例外：page_158 缺陷系统整页 PFS 禁用（页面级声明 `【PFS】PFS中不可使用
          缺陷系统。`，R4 2026-08-06 任务 4）→ False 为显式值（parsed），
          trait_type R2 页面级默认方案同构
        - format_cluster 恒有文件簇默认值 → parsed
        - 字段族 not_applicable：intro 无字段行（trait_type/requirement/deity
          恒不适用）；trait_flaw 无神名（deity 不适用）；trait 非宗教主题
          deity 不适用（设计 §3.3「非宗教背景无 deity」）
        """
        status = {}
        for field in _TRAIT_CANONICAL_FIELDS:
            val = metadata.get(field)
            if field == "trait_type":
                ok = bool(val)
            elif field in ("pfs_eligible", "flaw"):
                ok = val is True or (
                    field == "pfs_eligible" and doc_id == "page_158"
                )
            elif field == "format_cluster":
                ok = True
            else:
                ok = bool(val)
            if ok:
                status[field] = "parsed"
            elif field == "deity":
                # 宗教主题条目缺失 → missing（应可解析）；其余 not_applicable
                religious = bool(
                    set(metadata.get("trait_type", []) or []) & _RELIGIOUS_TRAIT_TYPES
                )
                status[field] = "missing" if religious else "not_applicable"
            elif field in ("trait_type", "requirement") and ct == "trait_intro":
                status[field] = "not_applicable"
            else:
                status[field] = "missing"
        return status


# 模块加载时自动注册
register("trait", TraitProcessor, _trait_file_condition)
