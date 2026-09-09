"""processors/skill.py — 技能文件处理器

设计（2026-08-07，技能元数据设计 §二~§四 + 人工门 1/2 拍板后实现）：
  - 复用 FileProcessor 模板方法（三钩子：build_chunk / resolve_source / infer_metadata）
  - 扫描清单 = prepare_batches.json 批次 A1+A2（38 文件，M3 批次 A = CRB 核心；
    B1/B2 批次 B 后续接入，component_type skill_rule/skill_equipment 不在此文件）
  - component_type 映射（设计 §四，6 类落地）：skill → skill、task/sub →
    skill_task（决策 7 子类独立 chunk）、note → skill_note、ui →
    ui_supplement、intro → skill_intro、index → skill_index
  - rule_version（设计 §二 2.3）：UI 补充目录 → ui，其余 A 批 → crb；
    B 批（unchained/giant/potr/occult/technology/faq）批次 B 接入
  - infer_metadata：14 字段（6 标识 + 6 正文 + source/rule_version）+ 双级
    dc_table/tasks + field_status 三态；非主条目类按各自字段集计算状态
  - resolve_source：共享 provider 链优先 → 引用块兜底（复用 feat 解析）；
    CRB 技能页共享链应直接命中 CRB，专属表不需要（无同名缩写冲突）
  - POSTPROCESSORS = toc 回填（通用件子类覆写报告目录到 docs/技能/）
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from vectorizer.formats.skill import SkillFormat
from vectorizer.postprocess.feat_chain import BackfillChmTocPath
from vectorizer.processors import register
from vectorizer.processors.base import Chunk, FileProcessor
from vectorizer.processors.feat import _feat_source_from_content
from vectorizer.sources.providers import SourceContext, SourceResolver, SourceResult

logger = logging.getLogger(__name__)


# ---- 输入范围（M3 批次 A：prepare_batches.json 的 A1+A2 = 38 文件）----
_ORGANIZED_ROOT = Path(__file__).resolve().parent.parent.parent / "pf_rules_md_organized"
_PREPARE_BATCHES_JSON = (
    Path(__file__).resolve().parent.parent / "exploration" / "skill" / "prepare_batches.json"
)


# B2 豁免 6 文件（不入扫描清单）：根目录 3 个 MD5 重复副本 + 2 个整理前
# renamed 副本 + 工具包.md（决策 11：纯装备页豁免不纳入，B2 只处理
# 工具和技能工具包.md）——去重结论见 docs/技能/散件去重结论.md
_B2_EXEMPT_RELS = {
    "背景技能.md",
    "整合技能.md",
    "分组技能.md",
    "新技能选项.md",
    "新技能规则.md",
    "工具包.md",
}
# B2 待接入文件（形态解析器未实现，先排除防 S1/S4/S5 误判；每接入一个
# 形态（S9 变体/S10 装备/FAQ）即从本集合移出对应文件）——FAQ 837 已接入
# （S9 问答流 _split_faq，2026-08-07），集合清空。
_B2_PENDING_RELS: set = set()

# B2 来源书专属表（审计 P1 修复，2026-08-07）：DirectoryNameProvider 对
# directory_hints（含文件名的全部路径 parts）做「技能」子串匹配 → 本类目
# 文件名/目录含「技能」二字的文件（Unchained 目录、工具和技能工具包.md 等）
# 全部误标 CRB（conf=80，557/557 系统性失实）。公共层不动（spell/职业冻结
# 模块共用，KN136 共享层改动漂移教训），非 CRB 文件在此按 rel 前缀短路
# 覆盖（对齐 trait 专属表冲突覆盖模式，置信度 75）。
# 注意：冒险者的军械库 abbr 用 AA——trait 表 AA=秘术选集（Arcane Anthology）
# 同名缩写（PF 生态真实同名），chunk 级字段无跨类目冲突，检索端按类目过滤。
_B2_SOURCE_OVERRIDES = {
    "规则/Unchained规则/技能与选项/": ("PU", "解放者手册", "Pathfinder Unchained"),
    "技能/巨人猎手手册_新技能选项.md": ("GIANT", "巨人猎手手册", "Giant Slayer's Handbook"),
    "规则/河域子民PotR_新技能规则.md": ("PotR", "河域之民", "People of the River"),
    "规则/异能规则/page_315.md": ("OCCULT", "异能规则", "Occult Rules"),
    "科技指南/科技世界/page_760.md": ("TG", "科技指南", "Technology Guide"),
    "官方FAQ/page_837.md": ("FAQ", "官方FAQ", "Official FAQ"),
    "工具和技能工具包.md": ("AA", "冒险者的军械库", "Adventurer's Armory"),
}
_B2_SOURCE_DOC_EXPECT = {
    # basename → abbr（verify 一致性断言的同源表）
    "背景技能.md": "PU", "整合技能.md": "PU", "分组技能.md": "PU",
    "page_647.md": "PU", "page_648.md": "PU", "page_649.md": "PU",
    "巨人猎手手册_新技能选项.md": "GIANT", "河域子民PotR_新技能规则.md": "PotR",
    "page_315.md": "OCCULT", "page_760.md": "TG", "page_837.md": "FAQ",
    "工具和技能工具包.md": "AA",
}


def _load_skill_scan_rels() -> set:
    """加载批次扫描清单 → {rel}

    A1 25 + A2 13 + B1 6 + B2 12 = 56 减 6 豁免 = 当前 50：
    - B1 Unchained 规则型 6（规则/Unchained规则/技能与选项/）
    - B2 已接入 6（巨人猎手 S8 + 河域子民/异能 315/科技 760/FAQ 837 S9 +
      工具和技能工具包 S10 装备）
    - B2 豁免 6：根目录背景/整合/分组技能重复副本 3 + 整理前 renamed
      副本（新技能选项/新技能规则）2 + 工具包.md 纯装备页（决策 11 拍板）
    """
    try:
        with open(_PREPARE_BATCHES_JSON, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        raise RuntimeError(
            f"无法加载批次清单 {_PREPARE_BATCHES_JSON}（技能扫描清单同口径来源）：{e}"
        ) from e
    rels = set()
    for batch in raw:
        if batch.get("batch") in ("A1", "A2", "B1", "B2"):
            for f in batch.get("files", []):
                rels.add(f.removeprefix("pf_rules_md_organized/"))
    rels -= _B2_EXEMPT_RELS
    rels -= _B2_PENDING_RELS
    expect = 56 - len(_B2_EXEMPT_RELS) - len(_B2_PENDING_RELS)
    if len(rels) != expect:
        raise RuntimeError(f"技能批次扫描清单应为 {expect} 文件，实际 {len(rels)}")
    return rels


SKILL_SCAN_RELS: set = _load_skill_scan_rels()


def _skill_file_condition(file_path: Path) -> bool:
    """技能文件判断：文件 rel 在批次 A 扫描清单内（38 文件）"""
    try:
        rel = file_path.resolve().relative_to(_ORGANIZED_ROOT)
    except ValueError:
        return False
    return str(rel) in SKILL_SCAN_RELS


# ---- 规范字段全集（元数据设计 §二，14 字段 + field_status）----

# 标识 + 正文 + 来源版本（主条目全量适用）
_SKILL_CANONICAL_FIELDS = (
    "skill_name", "english_name", "key_ability", "trained_only", "armor_penalty",
    "sub_specialty", "check", "action", "retry", "special", "untrained",
    "restriction", "source", "rule_version",
)
# 任务级字段（task/sub 适用：DC 双写决策 3 + 任务级字段归属 §3.2）
_TASK_FIELDS = ("skill_name", "english_name", "name", "name_en", "dc", "action",
                "retry", "special", "source", "rule_version")
# 速查块字段
_NOTE_FIELDS = ("skill_name", "name", "name_en", "source", "rule_version")
# UI 补充页字段
_UI_FIELDS = ("skill_name", "english_name", "title", "title_en", "source",
              "rule_version")
# 语言索引字段
_INDEX_FIELDS = ("name", "name_en", "source", "rule_version")
# 导言字段
_INTRO_FIELDS = ("title", "title_en", "source", "rule_version")
# 规则型条目字段（S7 Unchained 规则页：大节/难度档/范例/职业/子节）
_RULE_FIELDS = ("title", "title_en", "source", "rule_version")

# component_type 映射（设计 §四：item type → chunk 类型）
_TYPE_TO_CT = {
    "skill": "skill",
    "task": "skill_task",
    "sub": "skill_task",
    "note": "skill_note",
    "ui": "ui_supplement",
    "intro": "skill_intro",
    "index": "skill_index",
    "rule": "skill_rule",  # S7 Unchained 规则型（批次 B1；S9 变体规则同款）
    "equipment": "skill_equipment",  # S10 装备物品卡（工具和技能工具包）
}
# 条目名称字段（title 取值）：skill 主条目 formats 层产出 skill_name
#（非 name），其余 task/sub/note/index 用 name，ui/intro/rule 用标题
_NAME_KEYS = {"skill": "skill_name", "task": "name", "sub": "name", "note": "name",
              "ui": "skill_name", "intro": "title", "index": "name",
              "rule": "title", "equipment": "title"}

# rule_version 目录判定：UI 补充页 → ui；Unchained 规则型 → unchained；
# 其余 A 批 → crb（page_1038 是 UI 补充页的根目录孤儿副本，目录正则
# 覆盖不到，显式列出）
_RE_UI_DIR = re.compile(r"^技能/技能详述/UI的技能补充/")
_UI_ROOT_FILES = {"page_1038.md"}
# B1 Unchained 规则型 6 文件（S7 断点页：行尾/行内 \r = 硬断行——CRB 页 \r
# 是空行标记，语义按文件区分，pre_normalize 先行 \r→空格 join）
_UNCHAINED_B1_RELS = {
    "规则/Unchained规则/技能与选项/page_647.md",
    "规则/Unchained规则/技能与选项/page_648.md",
    "规则/Unchained规则/技能与选项/page_649.md",
    "规则/Unchained规则/技能与选项/背景技能.md",
    "规则/Unchained规则/技能与选项/整合技能.md",
    "规则/Unchained规则/技能与选项/分组技能.md",
}
# B2 纳入 6 文件 → rule_version（S8 巨人猎手/S9 变体规则/S10 装备物品卡；
# 设计 §2.3 枚举：giant/potr/occult/technology/faq；装备物品无规则版本
# 概念，rule_version 记类目名 equipment 供检索端区分）
_B2_REL_RULE_VERSION = {
    "技能/巨人猎手手册_新技能选项.md": "giant",
    "规则/河域子民PotR_新技能规则.md": "potr",
    "规则/异能规则/page_315.md": "occult",
    "科技指南/科技世界/page_760.md": "technology",
    "官方FAQ/page_837.md": "faq",
    "工具和技能工具包.md": "equipment",
}


class SkillBackfillChmTocPath(BackfillChmTocPath):
    """toc 空回填（同专长三级链路：注释源 md → md_map / 来源行路径），
    报告写 docs/技能/（子类覆写类属性目录，feat_chain 逻辑零改动）"""
    DEFAULT_REPORT_DIR = Path("docs/技能")


class SkillProcessor(FileProcessor):
    """技能文件处理器"""

    # finalize 后处理链（v2.2 决策 A 模式）：toc 回填通用件，报告目录覆写。
    # source 补齐（BackfillFeatSource）不需要：技能页无 `> 来源：` 引用块
    #（CRB 主条目来源由共享链直接解析，A 批无整文件来源注释）。
    POSTPROCESSORS = [SkillBackfillChmTocPath]

    @property
    def category(self) -> str:
        return "skill"

    def __init__(self, source_resolver: SourceResolver):
        super().__init__(source_resolver=source_resolver, format_handler=SkillFormat())
        self._rule_version = "crb"

    def process(self, file_path: Path) -> List[Chunk]:
        """逐文件状态重置：rule_version 按目录/清单判定（UI → ui，
        Unchained → unchained，B2 → giant/potr/occult/technology/faq/equipment）"""
        self._rule_version = "crb"
        try:
            rel = str(file_path.resolve().relative_to(_ORGANIZED_ROOT))
            if _RE_UI_DIR.match(rel) or rel in _UI_ROOT_FILES:
                self._rule_version = "ui"
            elif rel in _UNCHAINED_B1_RELS:
                self._rule_version = "unchained"
            elif rel in _B2_REL_RULE_VERSION:
                self._rule_version = _B2_REL_RULE_VERSION[rel]
        except ValueError:
            pass
        return super().process(file_path)

    def pre_normalize(self, file_path: Path, text: str) -> str:
        """断点页 \r → 空格：Unchained 规则页行尾/行内 \r 是硬断行（正文跨行、
        表格列分隔），CRB 页 \r 是空行标记——normalize 统一 \r→\n 会丢断点
        信息，此处按文件清单先行 join（\r\n 的 \r 一并转空格 = 行尾断点）"""
        try:
            rel = str(file_path.resolve().relative_to(_ORGANIZED_ROOT))
        except ValueError:
            return text
        if rel in _UNCHAINED_B1_RELS:
            return text.replace("\r", " ")
        return text

    def build_chunk(self, template: Chunk, item: dict) -> Chunk:
        """设置条目标题、正文、英文别名与 component_type

        component_type 六值（设计 §四，批次 A 范围）：skill → skill；
        task/sub → skill_task（任务级 + 知识/表演子类独立 chunk）；note →
        skill_note；ui → ui_supplement；intro → skill_intro；index →
        skill_index。skill_rule/skill_equipment 属批次 B 文件。
        """
        # ui 两形态：星壳（title/title_en）与文本（skill_name/english_name）
        if item["type"] == "ui":
            name = item.get("title") or item.get("skill_name")
        else:
            name = item.get(_NAME_KEYS[item["type"]], "")
        template.title = " ".join(str(name).split())
        # 主条目正文在 formats 层收集于 description 字段（text 字段主条目恒空）
        template.text = item.get("text") or item.get("description", "")
        name_en = item.get("name_en") or item.get("english_name") or item.get("title_en") or ""
        template.aliases = [" ".join(str(name_en).split())] if name_en else []
        template.component_type = _TYPE_TO_CT[item["type"]]
        return template

    def resolve_source(self, chunk: Chunk, ctx: SourceContext, item: dict) -> Chunk:
        """解析来源书：非 CRB 文件专属表短路 → 共享 provider 链 → 引用块兜底。

        审计 P1 修复（2026-08-07）：DirectoryNameProvider 对 directory_hints
        （含文件名的全部路径 parts）做「技能」子串匹配，本类目文件名/目录
        含「技能」二字的文件（Unchained 目录 6、工具和技能工具包.md、根目录
        孤儿页等）全部误标 CRB（conf=80，557/557 系统性失实）。公共层
        providers.py 不可动（spell/职业冻结模块共用，KN136），故非 CRB
        文件在进入共享链前按 rel 前缀短路（对齐 trait 专属表冲突覆盖模式）。

        技能 A 批 38 文件（技能详述 25 + UI 8 + 孤儿页 4 + 语言汇总）均属
        CRB（UI 8 页为 CRB 页内补充译文），共享链直接命中；无同名缩写冲突。
        """
        # B2 非 CRB 文件：共享链必错（「技能」子串误命中 CRB），短路覆盖
        try:
            rel = str(ctx.file_path.resolve().relative_to(_ORGANIZED_ROOT))
        except ValueError:
            rel = ""
        for prefix, (abbr, cn, en) in _B2_SOURCE_OVERRIDES.items():
            if rel.startswith(prefix):
                chunk.book_abbreviation = abbr
                chunk.book_name_cn = cn
                chunk.book_name_en = en
                chunk.source_confidence = 75
                return chunk
        result = self.source_resolver.resolve(ctx)
        if result.book_abbreviation == "?":
            hint = _feat_source_from_content(ctx.file_content)
            if hint:
                result = SourceResult(hint[0], hint[1], hint[2], 65, "SkillSourceLineProvider")
            elif _skill_file_condition(ctx.file_path):
                # 根目录孤儿页（page_161/162/182/1038）无目录提示、无引用块，
                # 但批次 A 38 文件全属 CRB 是人工门 1 拍板事实 → 类目已知范围兜底
                result = SourceResult("CRB", "核心规则书", "Core Rulebook", 60,
                                      "SkillKnownScopeProvider")
        chunk.book_abbreviation = result.book_abbreviation
        chunk.book_name_cn = result.book_name_cn
        chunk.book_name_en = result.book_name_en
        chunk.source_confidence = result.confidence
        return chunk

    def infer_metadata(self, chunk: Chunk, item: dict) -> Chunk:
        """按条目类型组装 metadata + field_status 三态（设计 §二~§四）

        - skill 主条目：14 字段全量（标识 6 + 正文 6 + source/rule_version），
          双级结构 dc_table/tasks 保真（决策 1/3）
        - task/sub：任务级字段（skill_name/task_name/dc/action/retry/special），
          sub 子类无 dc 时 missing
        - note/ui/index/intro：各自字段集（速查/UI 散文/语言/导言）
        - field_status：parsed（非空）/ missing（适用但缺）/ not_applicable
          （该条目类型不适用）
        """
        typ = item["type"]
        md: Dict[str, Any] = {}
        if typ == "skill":
            for f in ("skill_name", "english_name", "key_ability"):
                md[f] = item.get(f, "")
            md["trained_only"] = bool(item.get("trained_only", False))
            md["armor_penalty"] = bool(item.get("armor_penalty", False))
            md["sub_specialty"] = list(item.get("sub_specialty", []) or [])
            for f in ("check", "action", "retry", "special", "untrained", "restriction"):
                md[f] = item.get(f, "")
            md["dc_table"] = list(item.get("dc_table", []) or [])
            md["tasks"] = [
                {k: t.get(k, "") for k in
                 ("name", "name_en", "dc", "action", "retry", "special", "text")}
                for t in item.get("tasks", []) or []
            ]
            md["rule_version"] = self._rule_version
            fields = _SKILL_CANONICAL_FIELDS
        elif typ in ("task", "sub"):
            md["skill_name"] = item.get("skill_name", "")
            md["task_name"] = item.get("name", "")
            md["name_en"] = item.get("name_en", "")
            md["dc"] = item.get("dc", "")
            for f in ("action", "retry", "special"):
                md[f] = item.get(f, "")
            md["rule_version"] = self._rule_version
            fields = _TASK_FIELDS
        elif typ == "note":
            md["skill_name"] = item.get("skill_name", "")
            md["name"] = item.get("name", "")
            md["name_en"] = item.get("name_en", "")
            md["rule_version"] = self._rule_version
            fields = _NOTE_FIELDS
        elif typ == "ui":
            md["skill_name"] = item.get("skill_name", "")
            md["english_name"] = item.get("english_name", "")
            md["title"] = item.get("title", "")
            md["title_en"] = item.get("title_en", "")
            md["sections"] = list(item.get("sections", []) or [])
            md["rule_version"] = self._rule_version
            fields = _UI_FIELDS
        elif typ == "index":
            md["name"] = item.get("name", "")
            md["name_en"] = item.get("name_en", "")
            md["rule_version"] = self._rule_version
            fields = _INDEX_FIELDS
        elif typ == "rule":
            md["title"] = item.get("title", "")
            md["title_en"] = item.get("title_en", "")
            md["source"] = item.get("source", "")  # S8 来源行提取（S7 无来源行恒空）
            md["rule_version"] = self._rule_version
            fields = _RULE_FIELDS
        elif typ == "equipment":
            # S10 装备物品卡：字段集同 rule（title/title_en/source 段首来源行）
            md["title"] = item.get("title", "")
            md["title_en"] = item.get("title_en", "")
            md["source"] = item.get("source", "")
            md["rule_version"] = self._rule_version
            fields = _RULE_FIELDS
        else:  # intro
            md["title"] = item.get("title", "")
            md["title_en"] = item.get("title_en", "")
            md["rule_version"] = self._rule_version
            fields = _INTRO_FIELDS
        # formats 层形态簇（S1/S3/S4/S5/S6；S2 无任务页归 S1）——字段健康
        # 检查与判别器回归的簇级口径依赖此字段
        md["format_cluster"] = item.get("format_cluster", "")
        md["field_status"] = self._compute_field_status(md, fields, typ)
        chunk.metadata = md
        return chunk

    # ---- field_status 三态（设计 §二 2.4：parsed / missing / not_applicable）----

    @staticmethod
    def _compute_field_status(metadata: dict, fields: tuple, typ: str) -> dict:
        """计算条目字段解析状态。

        - list 字段（sub_specialty/dc_table/tasks/sections）：非空 = parsed
        - 布尔字段（trained_only/armor_penalty）：False = missing（与专长同款，
          技能正文无标记即未声明）
        - source：metadata 未填（resolve_source 结果在骨架层）→ not_applicable
        - 其余 str 字段：非空 = parsed，空 = missing
        """
        status = {}
        for f in fields:
            val = metadata.get(f)
            if f == "source":
                # 来源书在 chunk 骨架层（book_abbreviation）时 not_applicable；
                # rule 类 metadata 内嵌来源行原文（S8 `> 来源：` 行）时 parsed
                status[f] = "parsed" if val else "not_applicable"
            elif isinstance(val, bool):
                status[f] = "parsed" if val else "missing"
            elif isinstance(val, (list, dict)):
                status[f] = "parsed" if val else "missing"
            else:
                status[f] = "parsed" if val else "missing"
        return status


# 模块加载时自动注册
register("skill", SkillProcessor, _skill_file_condition)
