"""
test_rule_processor.py — rule processor 层 TDD 测试（M3 批次1 + M4 全量）

M2 人工门 2 拍板口径（2026-08-09）：
- 来源书 = 专属表短路（禁子串推导，技能 3.1 教训）；M4 全量 4 组键
  （目录/散件前缀/特殊 '?'/根级），conf 75；'?' 键 = 设计保留
  （作祟汇总 KN196 / page_320 KN195，装备 超游神器.md 先例）
- toc_group 4 枚举 = manifest 显式注解（prepare_batches.json toc_group_map，
  KN192 精神，不做路径推导）
- format_cluster / doc_role = rule_per_file.jsonl 显式注解（hint 是权威；
  如 page_130 有 H 标题但 hint=S5 → s5_prose）
- component_type M4 分派：overview→rule_intro / index_table→rule_reference /
  S4→rule_table / S6→rule_entry / 其余 rule_section（主）；无字段体系 → 不设
  field_status
- 判别器 = 全量 49 批 286 文件（core_rules 27 + rules 255 + retrain 1 +
  quick_reference 3）；page_508（hint「none（空文件）」）不产出（KN197）

断言对象：processors/rule.py 的 _resolve_rule_source（表短路）/
_rule_file_condition（判别器）/ RuleProcessor（三钩子全链，真实文件）。
"""

from pathlib import Path

from vectorizer.processors.base import Chunk
from vectorizer.processors.rule import (
    RULE_MANIFEST,
    RULE_SCAN_RELS,
    RuleProcessor,
    _rule_file_condition,
    _resolve_rule_source,
)

_ORGANIZED = Path(__file__).resolve().parent.parent.parent / "pf_rules_md_organized"


def _proc_chunk(rel: str) -> Chunk:
    """构造 RuleProcessor 并跑 build_chunk（只测分派，不跑全链）"""
    proc = RuleProcessor(source_resolver=None)
    proc._current_rel = rel
    template = Chunk(
        chunk_id="x", doc_id="y", category="rule", component_type="",
        title="节标题", text="正文", book_abbreviation="",
        book_name_cn="", book_name_en="", source_confidence=0)
    return proc.build_chunk(template, {"title": "节标题", "text": "正文"})


# ============================================================
#  component_type 分派（M4，manifest 显式注解）
# ============================================================


class TestComponentType:
    """doc_role=overview→rule_intro / index_table→rule_reference /
    S4→rule_table / S6→rule_entry / 其余 rule_section"""

    def test_section_default(self):
        """正文节（rule_chapter）→ rule_section（主 component）"""
        c = _proc_chunk("核心规则 Core Rulebook【CRB】/战斗规则/rpage_0003.md")
        assert c.component_type == "rule_section"

    def test_overview_intro(self):
        """章首导言（page_645 PU / page_732 UI）→ rule_intro（降权）"""
        assert _proc_chunk("page_645.md").component_type == "rule_intro"
        assert _proc_chunk("page_732.md").component_type == "rule_intro"

    def test_index_table_reference(self):
        """速查索引表（page_1 常用数据 / page_400 召唤怪物速查）→ rule_reference"""
        assert _proc_chunk("常用速查/page_1.md").component_type == "rule_reference"
        assert _proc_chunk("规则/怪物规则/page_400.md").component_type == "rule_reference"

    def test_s4_table(self):
        """整页纯表格（S4）→ rule_table"""
        assert _proc_chunk("规则/黑市指南BM_黑市规则.md").component_type == "rule_table"
        assert _proc_chunk("规则/UM规则/咒字/page_598.md").component_type == "rule_table"

    def test_s6_entry(self):
        """超大型聚合（S6）→ rule_entry"""
        assert _proc_chunk("规则/永罪之书_深渊魔神神恩.md").component_type == "rule_entry"
        assert _proc_chunk("规则/作祟汇总.md").component_type == "rule_entry"

    def test_reference_wins_over_table(self):
        """index_table 优先于 S4（page_1 是 S4 但 doc_role=index_table）"""
        assert _proc_chunk("常用速查/page_1.md").component_type == "rule_reference"


# ============================================================
#  来源书专属表短路
# ============================================================


class TestSourceShortCircuit:
    """rel 前缀 → (abbr, cn, en)，长前缀优先"""

    def test_crb_prefix(self):
        hit = _resolve_rule_source("核心规则 Core Rulebook【CRB】/战斗规则/rpage_0001.md")
        assert hit == ("CRB", "核心规则书", "Core Rulebook")

    def test_retrain_prefix(self):
        """重训 book=UCa（M2 拍板，KN194）"""
        hit = _resolve_rule_source("重训/page_159.md")
        assert hit == ("UCa", "极限进阶", "Ultimate Campaign")

    def test_quick_reference_prefix(self):
        hit = _resolve_rule_source("常用速查/page_1.md")
        assert hit == ("CRB", "核心规则书", "Core Rulebook")

    def test_rule_subdir_keys(self):
        """规则/ 各书子目录键（M4 展开，逐书定性）"""
        assert _resolve_rule_source("规则/UCa规则/休整期/page_967.md") == (
            "UCa", "极限进阶", "Ultimate Campaign")
        assert _resolve_rule_source("规则/怪物规则/page_300.md") == (
            "怪物", "怪物规则", "Monster Rules")
        assert _resolve_rule_source("规则/Unchained规则/page_640.md") == (
            "PU", "解放者手册", "Pathfinder Unchained")

    def test_unmapped_rel_none(self):
        """未定性前缀不得误命中（禁子串推导）"""
        assert _resolve_rule_source("规则/未知书/page_1.md") is None
        assert _resolve_rule_source("规则/异能规则/page_315.md") == (
            "OA", "异能冒险", "Occult Adventures")  # 已消费文件仍在表内

    def test_scattered_book_keys(self):
        """散件书件前缀键（来源行/注释定性，撞键沿装备先例）"""
        assert _resolve_rule_source("规则/永罪之书_仪式.md") == (
            "BotD", "永罪之书", "Book of the Damned")
        assert _resolve_rule_source("规则/动物档案AArch_魔宠变体.md") == (
            "AArch", "动物档案", "Animal Archive")  # 撞公共层 AArch
        assert _resolve_rule_source("规则/远程战术工具箱RTT_游侠陷阱.md") == (
            "RTT", "远程战术工具箱", "Ranged Tactics Toolbox")  # 撞公共层 RTT

    def test_special_unknown_keys(self):
        """作祟汇总 / page_320 → '?' 设计保留（KN195/196）"""
        assert _resolve_rule_source("规则/作祟汇总.md") == ("?", "未知", "Unknown")
        assert _resolve_rule_source("规则/page_320.md") == ("?", "未知", "Unknown")

    def test_root_level_keys(self):
        """根级文件键（CHM TOC 归属定性）"""
        assert _resolve_rule_source("page_1495.md") == ("HA", "恐怖冒险", "Horror Adventures")
        assert _resolve_rule_source("page_645.md") == ("PU", "解放者手册", "Pathfinder Unchained")
        assert _resolve_rule_source("第十季战役说明（Season_10_Campaign_Clarifications）.md") == (
            "PFS", "探索者协会", "Pathfinder Society")


# ============================================================
#  判别器（M4 = 全量 286 文件）
# ============================================================


class TestFileCondition:
    """M4 全量：286 文件 True；无关文件 False"""

    def test_b2_file(self):
        p = _ORGANIZED / "核心规则 Core Rulebook【CRB】/战斗规则/rpage_0001.md"
        assert _rule_file_condition(p)

    def test_rule_l1_file(self):
        p = _ORGANIZED / "规则/UCa规则/休整期/page_968.md"
        assert _rule_file_condition(p)

    def test_root_file(self):
        p = _ORGANIZED / "page_1495.md"
        assert _rule_file_condition(p)

    def test_unrelated_file_excluded(self):
        """非模块文件（如技能已消费 page_315 / 装备文件）不在判别器"""
        p = _ORGANIZED / "规则/异能规则/page_315.md"
        assert not _rule_file_condition(p)
        p2 = _ORGANIZED / "装备/whatever.md"
        assert not _rule_file_condition(p2)

    def test_scan_rel_count(self):
        """全量冻结集 = 286 文件（M1 人工门 1）"""
        assert len(RULE_SCAN_RELS) == 286

    def test_toc_group_distribution(self):
        """toc_group 分布：core_rules 27 + rules 255 + retrain 1 +
        quick_reference 3（M2 归属表口径）"""
        from collections import Counter
        cnt = Counter(RULE_MANIFEST[rel]["toc_group"] for rel in RULE_SCAN_RELS)
        assert cnt["core_rules"] == 27, cnt
        assert cnt["rules"] == 255, cnt
        assert cnt["retrain"] == 1, cnt
        assert cnt["quick_reference"] == 3, cnt

    def test_all_scan_rels_have_toc_group(self):
        """manifest 完整性：清单内每文件必有 toc_group 注解（M2 §三 3.1）"""
        for rel in RULE_SCAN_RELS:
            assert RULE_MANIFEST[rel]["toc_group"] in (
                "core_rules", "rules", "retrain", "quick_reference"), rel

    def test_all_scan_rels_resolvable(self):
        """专属表完整性：286 文件每文件可短路命中（漏表 = 来源失实）"""
        miss = [rel for rel in RULE_SCAN_RELS if _resolve_rule_source(rel) is None]
        assert not miss, miss[:5]

    def test_manifest_component_hints(self):
        """manifest doc_role 注解存在（component_type 分派依据）"""
        roles = {RULE_MANIFEST[r]["doc_role"] for r in RULE_SCAN_RELS
                 if RULE_MANIFEST[r].get("doc_role")}
        assert roles >= {"overview", "index_table"}, roles
