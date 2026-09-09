"""
processors/feat.py — 专长文件处理器

设计：
  - 复用 FileProcessor 模板方法（三钩子：build_chunk / resolve_source / infer_metadata）
  - parse_fields 算法对齐 spell.parse_fields（KN013 M5：extra 标签作值边界防吞值），
    标签集来自 registry_feat（14 规范字段 + 变体别名；"效果"归属 benefit，设计 §2.2）
  - prerequisites 结构化 {raw, items}：只做形态识别与键提取（设计 §三），
    无法归类的段保留 other；检索主键是 raw 原文与 feat/skill/ability 词条
  - field_status 三态（parsed/missing/not_applicable，去 ambiguous，设计 §2.4）：
    任务链三字段与造物三字段按字段族判定 not_applicable（普通专长无 task_goal）
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from vectorizer.formats.feat import FeatFormat
from vectorizer.postprocess.feat_chain import (
    ApplyChmTocMapping,
    ApplyFeatCreationSourcePromote,
    BackfillChmTocPath,
    BackfillFeatSource,
)
from vectorizer.processors import register
from vectorizer.processors.base import Chunk, FileProcessor
from vectorizer.registry_feat import (
    FEAT_ALL_FIELD_LABELS,
    FEAT_CANONICAL_FIELDS,
    FEAT_EXTRA_FORMAT_LABELS,
    FEAT_LABEL_TO_KEY,
    split_feat_types,
)
from vectorizer.sources.providers import SourceContext, SourceResolver, SourceResult

logger = logging.getLogger(__name__)


def parse_fields(text: str) -> Dict[str, str]:
    """从统一 IR 文本提取专长字段原始值（对齐 spell.parse_fields 算法）。

    输入前提：text 已通过 formats/feat.py 归一为 **标签：** 值 格式。
    边界集 = 全量标签 + extra 标签（推荐背景/描述）：extra 只作值边界
    不产生字段（KN013 M5 同款防吞值）；"效果"已在 FEAT_ALL_FIELD_LABELS
    （设计 §2.2 benefit 别名含"效果 395"），不会混入相邻字段值。
    """
    result: Dict[str, str] = {}
    if not text:
        return result

    boundary_labels = FEAT_ALL_FIELD_LABELS + FEAT_EXTRA_FORMAT_LABELS
    labels_pattern = "|".join(re.escape(label) for label in boundary_labels)
    capture_labels_pattern = "|".join(re.escape(label) for label in FEAT_ALL_FIELD_LABELS)
    # 字段值边界：下一个字段标签（标准或变体）、空白行（\n\n）、或文本末尾。
    # \n\n 作硬边界是安全的：数据中字段值从不跨空白行（spell 侧已实测确认）。
    next_field = (
        rf'\n\n'
        rf'|\n\*\*(?:{labels_pattern})[：:]\*\*'
        rf'|\n\*\*(?:{labels_pattern})\*\*[：:]'
    )
    # 格式 1: **标签：** 值（统一 IR 标准格式）
    field_re = re.compile(
        rf'\*\*({capture_labels_pattern})[：:]\*\*\s*([\s\S]*?)(?={next_field}|\Z)',
        re.MULTILINE,
    )
    # 格式 2: **标签**：值（** 在冒号前关闭的残留格式，安全网）
    field_re_v2 = re.compile(
        rf'\*\*({capture_labels_pattern})\*\*[：:]\s*([\s\S]*?)(?={next_field}|\Z)',
        re.MULTILINE,
    )

    def _extract(match_re: re.Pattern) -> None:
        for m in match_re.finditer(text):
            label = m.group(1)
            value = m.group(2).strip()
            # 去掉值末尾可能的 ** 残留与段尾标点（裸标签残留/格式符，"无；"→"无"）
            value = value.rstrip("*,；;。，、").strip()
            # 全角空格 → 半角
            value = value.replace("　", " ")
            key = FEAT_LABEL_TO_KEY.get(label)
            if key and key not in result:
                result[key] = value

    # 出处类标签（source 字段）：值锚定行尾，不跨行吃后续正文行。
    # 全库 16 处出处行后紧跟正文行（造物专长一览/平衡勇士/闹鬼英雄手册/
    # 位面冒险/间谍大师手册），旧路径 value 跨行把正文吞进 source。
    # 形态覆盖：**出自：** / **出自**： / ****出自**：（4 星）/
    # **来自**：（'来自' 与 '出自' 同义出处标签）/ **Source 值（无冒号闭合星）。
    _SRC_LABELS_RE = re.compile(
        r"\*\*(?:来源|出处|出自|来自|Source)"
        r"(?:\*\*[：:]|[：:]\*\*|[^\n:：*])\s*([^\n]*)",
        re.MULTILINE,
    )
    for _m in _SRC_LABELS_RE.finditer(text):
        value = _m.group(1).rstrip("*,；;。，、").strip()
        if value and "source" not in result:
            result["source"] = value

    # 优先标准格式，再 fallback 格式 2
    _extract(field_re)
    _extract(field_re_v2)

    return result


# ---- 来源书补充表（专长特有：共享 provider 链的 SOURCE_BOOK_ABBREVIATIONS 未覆盖的书）----
# key = 专长文件 HTML 注释中的原样缩写（<!-- XXX-source: ... -->），
# value = 规范缩写 + 中英文书名。数据源：config/feat_sources.json
# （各文件开头 '> 来源：中文名（English）缩写' 引用块提取，人工核对）。

_FEAT_SOURCES_JSON = Path(__file__).resolve().parent.parent / "config" / "feat_sources.json"


def _load_feat_sources() -> Dict[str, dict]:
    with open(_FEAT_SOURCES_JSON, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("sources", {})


FEAT_SOURCES: Dict[str, dict] = _load_feat_sources()

# 专长文件的来源书注释形态：<!-- UW-source:专长11.md:突袭警惕 --> / <!-- 秽邪勇士-source:... -->
# （与 HTMLCommentProvider 识别的 <!-- Source: X --> 格式不同，专长整理时写入）
_RE_SOURCE_COMMENT = re.compile(r"<!--\s*([^\s<>]+?)-source:")


def _extract_comment_source_abbr(content: str) -> Optional[str]:
    m = _RE_SOURCE_COMMENT.search(content)
    return m.group(1) if m else None


# 整理时写入的来源引用块（各专长文件开头，权威来源信息）：
#   > 来源：极限荒野（Ultimate Wilderness），页码见原书，未整理 → 极限荒野UW → 专长
#   group1 = 中文名（可含逗号等），group2 = 英文名，group3 = 箭头段规范缩写
_RE_SOURCE_LINE = re.compile(
    r">\s*来源：([^（(→]+)(?:（([^）)]+)）)?[^→]*?→\s*([^→]+?)\s*→"
)

# 箭头段"极限荒野UW" → 尾部 ASCII 缩写（"UW"）；无 ASCII 时保留原文（秽邪勇士）
_RE_ABBR_TAIL = re.compile(r"[A-Za-z0-9&]+$")


def _feat_source_from_content(content: str) -> Optional[tuple]:
    """从文件内容提取来源书（abbr, cn, en）。

    通道 1（优先）：来源引用块 → cn/en 权威，abbr 取箭头段尾部 ASCII 缩写
      （"极限荒野UW"→UW；"药剂与毒药P&P"→P&P；"秽邪勇士"无 ASCII → 中文名）。
    通道 2（兜底）：HTML 注释缩写查 FEAT_SOURCES 补充表（无引用块的文件）。
    返回 None 表示无来源线索（保持 "?"，不编造）。
    """
    m = _RE_SOURCE_LINE.search(content)
    if m:
        cn = m.group(1).strip()
        en = (m.group(2) or "").strip()
        abbr_raw = (m.group(3) or "").strip()
        m_tail = _RE_ABBR_TAIL.search(abbr_raw)
        abbr = m_tail.group(0) if m_tail else abbr_raw
        return (abbr, cn, en)

    abbr = _extract_comment_source_abbr(content)
    entry = FEAT_SOURCES.get(abbr) if abbr else None
    if entry:
        return (entry["abbr"], entry["cn"], entry["en"])
    return None


# ---- prerequisites 形态识别（设计 §三：只做形态识别与键提取，不做语义理解）----

# PF1e 核心技能集（白名单；命中 → skill，否则 X N 级 → class_level）
_SKILL_NAMES: tuple[str, ...] = (
    "特技动作", "估价", "唬骗", "攀爬", "手艺", "交涉", "脱逃", "医疗",
    "威吓", "知识", "语言学", "察觉", "表演", "专业", "骑术", "察言观色",
    "隐匿", "生存", "游泳", "使用魔法装置", "飞行", "驯养动物", "潜行", "辨识法术",
)
_SKILL_NAMES_ALT = "|".join(_SKILL_NAMES)

_ABILITY_RE = re.compile(r"^(力量|敏捷|体质|智力|感知|魅力)[^\d]*?(\d+)$")
_BAB_RE = re.compile(r"^(?:BAB|基础攻击加值)\s*[+＋]?\s*(\d+)", re.IGNORECASE)
_SKILL_LEVEL_RE = re.compile(rf"^({_SKILL_NAMES_ALT})[^\d]*?(\d+)\s*级")
_CLASS_LEVEL_RE = re.compile(r"^(.{2,12})[^\d]*?(\d+)\s*级")
_SPELL_LEAD_RE = re.compile(r"^(能够?施放|能施放|施法能力)")
_FEAT_PAREN_RE = re.compile(r"[（(][A-Za-z]")
_RACE_HINT_RE = re.compile(r"变身者|种族|血统")


def _split_prereq_segments(raw: str) -> List[str]:
    """按中文逗号/顿号/分号/句点拆分先决条件段（'或'分支留在段内处理）"""
    return [s.strip() for s in re.split(r"[，,、；;。]", raw) if s.strip()]


def _classify_prereq_segment(seg: str) -> Dict[str, Any]:
    """单段形态识别（顺序即优先级）：
    bab（含 or 分支）→ ability → skill → class_level → race → spell → feat → other
    """
    # "或"分支：主段为 BAB → 挂 or 字段（设计示例）；其余含 or 段归 other
    if "或" in seg:
        main, or_part = seg.split("或", 1)
        m = _BAB_RE.match(main.strip())
        if m:
            return {"type": "bab", "value": int(m.group(1)), "or": or_part.strip()}
        return {"type": "other", "value": seg}

    m = _BAB_RE.match(seg)
    if m:
        return {"type": "bab", "value": int(m.group(1))}

    m = _ABILITY_RE.match(seg)
    if m:
        return {"type": "ability", "ability": m.group(1), "value": int(m.group(2))}

    m = _SKILL_LEVEL_RE.match(seg)
    if m:
        return {"type": "skill", "skill": m.group(1), "level": int(m.group(2))}

    m = _CLASS_LEVEL_RE.match(seg)
    if m:
        return {"type": "class_level", "class": m.group(1).strip(), "level": int(m.group(2))}

    # race 显式形态（变身者/种族/血统）优先于通用纯名归类
    if _RACE_HINT_RE.search(seg):
        return {"type": "race", "value": seg}

    if _SPELL_LEAD_RE.match(seg):
        return {"type": "spell", "value": seg}

    # 带括号英文引用 → 专长链；纯中文段 → feat（先决条件语境中绝大多数是专长名，
    # 设计示例"寓守于攻"归 feat；语义不可分的残留归 other 见下）
    if _FEAT_PAREN_RE.search(seg):
        return {"type": "feat", "value": seg}
    if re.fullmatch(r"[一-鿿（）()A-Za-z .'’\-]+", seg):
        return {"type": "feat", "value": seg}

    return {"type": "other", "value": seg}


def _parse_prerequisites(raw: str) -> Dict[str, Any]:
    """prerequisites 结构化：{raw, items}（设计 §三 形态枚举）。"""
    items = [_classify_prereq_segment(seg) for seg in _split_prereq_segments(raw)]
    return {"raw": raw, "items": items}


class FeatProcessor(FileProcessor):
    """专长文件处理器"""

    # v2.2 决策 A：finalize 后处理链（顺序不可变，教训 B1——重排即 book/toc/source
    # 回归）。apply_chm_toc_mapping 先铺大部分 doc 的 book，造物专长一览保持 '?'
    # 由 apply_feat_creation_source_promote 专处理；backfill 两脚本只填缺失字段，
    # 与 book 无耦合但保持声明顺序。pipeline 在 chunks.jsonl 落盘后逐个执行。
    POSTPROCESSORS = [
        ApplyChmTocMapping,
        ApplyFeatCreationSourcePromote,
        BackfillChmTocPath,
        BackfillFeatSource,
    ]

    @property
    def category(self) -> str:
        return "feat"

    def __init__(self, source_resolver: SourceResolver):
        super().__init__(source_resolver=source_resolver, format_handler=FeatFormat())
        # 同 stem 双份去重（造物专长一览 根目录/专长/）：sorted 遍历先到者为主版本
        self._seen_stems: set = set()

    def build_chunk(self, template: Chunk, item: dict) -> Chunk:
        """设置专长标题、正文和英文别名"""
        # 表格行列对齐空格（HTML &nbsp; 序列转换产物，全库 371 aliases + 152 title）
        # 压缩为单空格——字段语义归一化，避免检索端精确匹配 miss
        template.title = " ".join(item.get("name", "").split())
        template.text = item.get("text", "")
        template.aliases = [" ".join(item["name_en"].split())] if item.get("name_en") else []
        # 表格索引行（lb_marker）标 feat_index（专长元数据设计 §五），区别正文
        # feat：检索时索引行条目与正文条目可区分（法术 spell_index 同思路）。
        if item.get("format_cluster") == "lb_marker":
            template.component_type = "feat_index"
        # KN094：intro 标记（章首标题/类别介绍段，57 个高置信）标 feat_intro，
        # 检索端可降权区别于具体专长条目。lb_marker 优先（上分支已 return）。
        elif item.get("intro"):
            template.component_type = "feat_intro"
        return template

    def resolve_source(self, chunk: Chunk, ctx: SourceContext, item: dict) -> Chunk:
        """解析来源书：标准 provider 链优先，失败时按专长来源标记兜底。

        共享链（SOURCE_BOOK_ABBREVIATIONS）未覆盖的专长书（极限荒野等），
        文件内来源引用块（> 来源：... → 缩写 →）与 HTML 注释自带完整书名，
        置信度 65：低于文件名/目录名通道（75/80，先于兜底已尝试），
        高于纯正文提及（50），引用块/注释是整理时写入的显式来源标记。
        """
        result = self.source_resolver.resolve(ctx)
        if result.book_abbreviation == "?":
            hint = _feat_source_from_content(ctx.file_content)
            if hint:
                result = SourceResult(hint[0], hint[1], hint[2], 65, "FeatSourceLineProvider")
        chunk.book_abbreviation = result.book_abbreviation
        chunk.book_name_cn = result.book_name_cn
        chunk.book_name_en = result.book_name_en
        chunk.source_confidence = result.confidence
        return chunk

    def infer_metadata(self, chunk: Chunk, item: dict) -> Chunk:
        """14 字段元数据（专长元数据设计 §二）。

        - 文本字段走 parse_fields（**标签：** / **标签**： 双格式）
        - feat_type / format_cluster / pfs_eligible 由 formats 层 item 直接带
        - prerequisites 结构化（raw + items，设计 §三）
        - field_status 三态（设计 §2.4）
        """
        text = item.get("text", "")
        raw = parse_fields(text)

        metadata: Dict[str, Any] = {}

        # 类型：formats 层标题解析优先（item 直接带），正文"类型"字段兜底
        metadata["feat_type"] = item.get("feat_type") or split_feat_types(raw.get("feat_type", ""))

        # 先决条件：结构化对象；无字段 → None（field_status 判 missing）
        prereq_raw = raw.get("prerequisites", "")
        metadata["prerequisites"] = _parse_prerequisites(prereq_raw) if prereq_raw else None

        # 直通文本字段
        for key in ("benefit", "normal", "special"):
            metadata[key] = raw.get(key, "")
        # 来源：正文"来源"标签优先，索引行【缩写】（item.source）兜底
        metadata["source"] = raw.get("source", "") or item.get("source", "")

        # 任务链字段（普通专长 not_applicable）
        for key in ("task_goal", "task_reward", "advanced_reward"):
            metadata[key] = raw.get(key, "")

        # 造物字段（非造物专长 not_applicable）
        for key in ("craft_cost", "craft_conditions", "craft_aura"):
            metadata[key] = raw.get(key, "")

        # 形态簇与 PFS（formats 层判定）
        metadata["format_cluster"] = item.get("format_cluster", "standard")
        metadata["pfs_eligible"] = bool(item.get("pfs_eligible", False))

        metadata["field_status"] = self._compute_field_status(metadata)
        chunk.metadata = metadata
        return chunk

    # ---- field_status 三态（设计 §2.4：parsed / missing / not_applicable，无 ambiguous）----

    # 字段族专属字段：任务链三字段与造物三字段只适用于对应专长形态，
    # 缺失时判 not_applicable 而非 missing（普通专长无 task_goal）。
    _NOT_APPLICABLE_FIELDS = {
        "task_goal", "task_reward", "advanced_reward",
        "craft_cost", "craft_conditions", "craft_aura",
    }

    @staticmethod
    def _compute_field_status(metadata: dict) -> dict:
        """计算每个规范字段的解析状态。

        - prerequisites 为结构化对象：看 raw 是否有值
        - pfs_eligible 为布尔：True = 解析到 PFS 标记；False（未标记/不可用）→ missing
        - format_cluster 恒有默认值（standard）→ parsed
        """
        status = {}
        for field in FEAT_CANONICAL_FIELDS:
            if field == "field_status":
                continue
            val = metadata.get(field)
            if field == "prerequisites":
                ok = bool(val and val.get("raw"))
            elif field == "pfs_eligible":
                ok = val is True
            elif field == "format_cluster":
                ok = True
            else:
                ok = bool(val)
            if ok:
                status[field] = "parsed"
            elif field in FeatProcessor._NOT_APPLICABLE_FIELDS:
                status[field] = "not_applicable"
            else:
                status[field] = "missing"
        return status


    def process(self, file_path: Path) -> List[Chunk]:
        """同 stem 双份文件去重（R1 同书多份取主版本）：矩阵含同 stem 双 rel
        （造物专长一览 根目录旧副本 + 专长/ 规范化主版本，est/got 相同 28/46），
        pipeline 两文件都进 → 各产一份同前缀 chunk_id（前缀 = stem）撞车。
        sorted 遍历子目录版在前先处理并登记 stem，根目录旧副本后到被跳过。

        R1 输入范围含该双 rel（189 = 根 66 + 子 123），此处非范围收窄，是
        chunk_id 唯一性兜底；判别器回归 est/got 仍按矩阵双 rel 对账，
        产出仅计主版本（豁免登记 docs/state/）。"""
        if file_path.stem in self._seen_stems:
            logger.info("跳过同 stem 重复副本 %s（取主版本）", file_path.name)
            return []
        self._seen_stems.add(file_path.stem)
        return super().process(file_path)


# ---- 输入范围（R1：判别器同口径，禁止形态猜谜） ----
# pipeline 扫描集合 = fc_deviation_matrix.json 的 189 个 rel（根目录 66 + 专长/ 123）。
# 判别器扫哪些文件，pipeline 就产哪些文件——回归对账（est↔got）天然同口径；
# 未整理/角色选项归置等矩阵外文件一律不产（含重复副本 page_202，源数据层待清理）。
_ORGANIZED_ROOT = Path(__file__).resolve().parent.parent.parent / "pf_rules_md_organized"
_FEAT_MATRIX_JSON = Path(__file__).resolve().parent.parent / "exploration" / "专长" / "fc_deviation_matrix.json"


def _load_feat_scan_rels() -> set:
    try:
        with open(_FEAT_MATRIX_JSON, encoding="utf-8") as f:
            return {x["rel"] for x in json.load(f)}
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise RuntimeError(
            f"无法加载判别器矩阵 {_FEAT_MATRIX_JSON}（专长扫描清单同口径来源）：{e}"
        ) from e


FEAT_SCAN_RELS: set = _load_feat_scan_rels()


def _feat_file_condition(file_path: Path) -> bool:
    """专长文件判断：文件 rel 在判别器矩阵清单内（根目录 66 + 专长/ 123 = 189）"""
    try:
        rel = file_path.resolve().relative_to(_ORGANIZED_ROOT)
    except ValueError:
        return False
    return str(rel) in FEAT_SCAN_RELS


# 模块加载时自动注册
register("feat", FeatProcessor, _feat_file_condition)
