"""test_profession_kn224.py — KN224 职业归属修正与无标题职业页标题兜底

设计：docs/superpowers/specs/2026-11-12-kn224-class-attribution-and-title-fallback-design.md

覆盖：
- D3 多层权威校验（CHM TOC 末级 / 来源锚点 source_page stem / 文件名后缀），
  不以 known_classes 作为唯一守卫；
- D1「表：X」表题取职业名，与权威锚点不一致时保持原值；
- D2「每级技能点数…」逆序扫描面包屑取与锚点一致的职业名；
- D4/D5 标题兜底 + breadcrumbs 同步，page_678 必须保持不修；
- 死斗战士（page_755）是真实职业，归属与标题都保留。
"""
from pathlib import Path

import pytest

from vectorizer.processors.profession import (
    MD_MAPPING_JSON,
    ProfessionProcessor,
    SourceMarker,
    _class_name_from_special_title,
    _file_authority_names,
    _infer_title_fallback,
    load_md_mapping,
)

# vectorizer/tests/ 的祖父目录 = pf_data/phase1
PHASE1 = Path(__file__).resolve().parents[2]
INPUT_DIR = PHASE1 / "pf_rules_md_organized" / "职业"
MD_MAPPING = load_md_mapping(MD_MAPPING_JSON)


# ============================================================
#  D3：多层权威校验
# ============================================================


class TestFileAuthorityNames:
    def test_toc_last_level(self):
        """CHM TOC 末级是权威职业名（直挂 page 文件）。"""
        names = _file_authority_names(Path("进阶职业/PoP进阶之路/page_755.md"), MD_MAPPING)
        assert "死斗战士" in names

    def test_source_anchor_stem(self):
        """来源锚点 source_page 的 stem 是权威职业名。"""
        marker = SourceMarker("UNDEAD", "灵魂守卫.md", "<!-- UNDEAD-source:灵魂守卫.md:灵魂守卫 -->")
        names = _file_authority_names(
            Path("进阶职业/亡灵杀手手册_灵魂守卫.md"), MD_MAPPING, [marker]
        )
        assert "灵魂守卫" in names

    def test_filename_suffix(self):
        """直挂文件名 <来源书>_<职业名>.md 的后缀是权威职业名。"""
        marker = SourceMarker("LotFW", "妖精誓缚者.md", "<!-- LotFW-source:妖精誓缚者.md:feysworn -->")
        names = _file_authority_names(
            Path("进阶职业/第一世界TFWRotF_妖精誓缚者.md"), MD_MAPPING, [marker]
        )
        assert "妖精誓缚者" in names

    def test_page_678_toc_last_is_not_class(self):
        """page_678 的 TOC 末级是章节集合，不是「进阶专长」。"""
        names = _file_authority_names(Path("进阶职业/PotR正义之道/page_678.md"), MD_MAPPING)
        assert names == {"专长、庇护主、法术、奇物"}


# ============================================================
#  D1 / D2：表格块标题取职业名
# ============================================================


class TestTableTitleClass:
    def test_table_caption_accepted_when_authoritative(self):
        assert _class_name_from_special_title(
            "表：密传骑士", ["传奇编年史CoL 密传骑士", "表：密传骑士"], {"密传骑士"}
        ) == "密传骑士"

    def test_table_caption_rejected_when_mismatched(self, capsys):
        assert _class_name_from_special_title(
            "表：未知名字", ["x", "表：未知名字"], {"密传骑士"}, "x.md"
        ) is None
        assert "与权威锚点不一致" in capsys.readouterr().err

    def test_skill_ranks_scans_breadcrumbs_reverse(self):
        breadcrumbs = [
            "冒险者指南AG 进阶职业",
            "钉魂密使（Rivethun Emissary）",
            "每级技能点数：4+智力调整值生命骰：D8职业特性",
        ]
        assert _class_name_from_special_title(
            breadcrumbs[-1], breadcrumbs, {"钉魂密使"}
        ) == "钉魂密使"

    def test_skill_ranks_without_authority_returns_none(self):
        breadcrumbs = ["未知来源", "每级技能点数：4+智力调整值"]
        assert _class_name_from_special_title(
            breadcrumbs[-1], breadcrumbs, {"钉魂密使"}
        ) is None


# ============================================================
#  D4：标题兜底
# ============================================================


def _blocks(title: str, text: str):
    return [{"title": title, "text": text, "breadcrumbs": [title], "level": 1, "markers": []}]


class TestTitleFallback:
    def test_real_class_page_gets_title(self):
        new_title = _infer_title_fallback(
            _blocks("page_679", "伊沙-瓦舞者（Ashavic Dancer）至高天神使……"),
            Path("进阶职业/PotR正义之道/page_679.md"),
            MD_MAPPING,
            [],
        )
        assert new_title == "伊沙-瓦舞者（Ashavic Dancer）"

    def test_guard_page_678_keeps_stem(self):
        """page_678「进阶专长」不是职业，标题必须保持 page_678。"""
        assert _infer_title_fallback(
            _blocks("page_678", "进阶专长（Prestigious Feat）进阶职业给出了……"),
            Path("进阶职业/PotR正义之道/page_678.md"),
            MD_MAPPING,
            [],
        ) is None

    def test_non_prestige_path_ignored(self):
        assert _infer_title_fallback(
            _blocks("page_1094", "战士（Fighter）任何……"),
            Path("核心职业/战士/page_1094.md"),
            MD_MAPPING,
            [],
        ) is None

    def test_existing_heading_not_touched(self):
        """已有 # 标题（title != stem）的文件不触发兜底。"""
        assert _infer_title_fallback(
            _blocks("伊沙-瓦舞者", "伊沙-瓦舞者（Ashavic Dancer）……"),
            Path("进阶职业/PotR正义之道/page_679.md"),
            MD_MAPPING,
            [],
        ) is None


def _real_blocks(doc: str):
    """按流水线口径（clean → split）取该文件的块（不跑完整 processor）。"""
    from vectorizer.formats.profession import clean_file, split_into_blocks

    cleaned, _ = clean_file(INPUT_DIR / doc, MD_MAPPING)
    return split_into_blocks(cleaned, doc)


# 18 个真实职业页：文件无 # 标题 + 首行「中文（English）」+ 经 D3 权威校验
EXPECTED_FALLBACK_TITLES = {
    "进阶职业/ISI内海诡道/page_742.md": "妩媚交际花（Enchantingcourtesan）",
    "进阶职业/ISI内海诡道/page_743.md": "狮子剑（Lionblade）",
    "进阶职业/PoP进阶之路/page_755.md": "死斗战士（Pit Fighter）",
    "进阶职业/City of Strangers/page_756.md": "臃肿法师（Bloatmage）",
    "进阶职业/亡灵杀手手册_灵魂守卫.md": "灵魂守卫（Soul Warden）",
    "进阶职业/PotR正义之道/page_679.md": "伊沙-瓦舞者（Ashavic Dancer）",
    "进阶职业/PotR正义之道/page_680.md": "酿酒师（Brewkeeper）",
    "进阶职业/PotR正义之道/page_681.md": "绯红十字军（Crimson Templar）",
    "进阶职业/PotR正义之道/page_682.md": "挑战者（Darechaser）",
    "进阶职业/PotR正义之道/page_683.md": "晨花隐者（Dawnflower Anchorite）",
    "进阶职业/PotR正义之道/page_684.md": "誓诚缪斯（Devoted Muse）",
    "进阶职业/PotR正义之道/page_685.md": "继业骑士（Heritor Knight）",
    "进阶职业/PotR正义之道/page_686.md": "戍乡人（Hinterlander）",
    "进阶职业/PotR正义之道/page_687.md": "玫瑰戍卫（RoseWarden）",
    "进阶职业/PotR正义之道/page_688.md": "符文守卫（Runeguard）",
    "进阶职业/PotR正义之道/page_690.md": "负痕求道者（ScarSeeker）",
    "进阶职业/PotR正义之道/page_691.md": "天体颂唱者（Sphere Singer）",
    "进阶职业/PotR正义之道/page_692.md": "观星者（Stargazer）",
}


class TestEighteenRealClassPages:
    @pytest.mark.parametrize("doc,expected", sorted(EXPECTED_FALLBACK_TITLES.items()))
    def test_fallback_title(self, doc, expected):
        blocks = _real_blocks(doc)
        markers = [m for b in blocks for m in b.get("markers", [])]
        assert _infer_title_fallback(blocks, Path(doc), MD_MAPPING, markers) == expected

    def test_page_678_is_the_only_rejected_one(self):
        """19 个候选页中仅 page_678 被排除（进阶专长不是职业）。"""
        blocks = _real_blocks("进阶职业/PotR正义之道/page_678.md")
        assert _infer_title_fallback(blocks, Path("进阶职业/PotR正义之道/page_678.md"), MD_MAPPING, []) is None


# ============================================================
#  产物级回归（全量装配一次）
# ============================================================

@pytest.fixture(scope="module")
def chunks_by_doc():
    p = ProfessionProcessor(source_resolver=None)
    p.load_resources(INPUT_DIR)
    docs = [
        "进阶职业/冒险者指南AG_进阶职业.md",
        "进阶职业/传奇编年史CoL_进阶职业.md",
        "进阶职业/格拉里昂的半身人_半身人投机客.md",
        "进阶职业/第一世界TFWRotF_妖精誓缚者.md",
        "进阶职业/PoP进阶之路/page_755.md",
        "进阶职业/亡灵杀手手册_灵魂守卫.md",
        "进阶职业/PotR正义之道/page_678.md",
        "进阶职业/PotR正义之道/page_679.md",
    ]
    return {rel: p.process(INPUT_DIR / rel) for rel in docs}


class TestChunkRegression:
    @pytest.mark.parametrize("doc,title,expected", [
        ("进阶职业/冒险者指南AG_进阶职业.md",
         "每级技能点数：4+智力调整值生命骰：D8职业特性", "钉魂密使"),
        ("进阶职业/传奇编年史CoL_进阶职业.md", "表：密传骑士", "密传骑士"),
        ("进阶职业/格拉里昂的半身人_半身人投机客.md", "表：半身人投机客", "半身人投机客"),
        ("进阶职业/第一世界TFWRotF_妖精誓缚者.md", "表：妖精誓缚者", "妖精誓缚者"),
    ])
    def test_table_chunks_attributed(self, chunks_by_doc, doc, title, expected):
        matched = [c for c in chunks_by_doc[doc] if c.title == title]
        assert len(matched) == 1
        assert matched[0].metadata["class_name"] == expected

    def test_pit_fighter_is_real_class(self, chunks_by_doc):
        """死斗战士是真实职业：归属保留，标题由兜底补上。"""
        chunk = chunks_by_doc["进阶职业/PoP进阶之路/page_755.md"][0]
        assert chunk.metadata["class_name"] == "死斗战士"
        assert chunk.title == "死斗战士（Pit Fighter）"

    def test_page_678_untouched(self, chunks_by_doc):
        chunk = chunks_by_doc["进阶职业/PotR正义之道/page_678.md"][0]
        assert chunk.title == "page_678"
        assert chunk.metadata["heading_breadcrumbs"] == ["page_678"]

    def test_breadcrumbs_synced_for_all_blocks(self, chunks_by_doc):
        """亡灵杀手手册_灵魂守卫：13 个块的 breadcrumbs 里不再残留文件名 stem。"""
        stem = "亡灵杀手手册_灵魂守卫"
        chunks = chunks_by_doc["进阶职业/亡灵杀手手册_灵魂守卫.md"]
        assert len(chunks) == 13
        for chunk in chunks:
            breadcrumbs = chunk.metadata["heading_breadcrumbs"]
            assert stem not in breadcrumbs
            assert "灵魂守卫（Soul Warden）" in breadcrumbs
        assert chunks[0].title == "灵魂守卫（Soul Warden）"

    def test_first_block_title_and_id_changed(self, chunks_by_doc):
        chunk = chunks_by_doc["进阶职业/PotR正义之道/page_679.md"][0]
        assert chunk.title == "伊沙-瓦舞者（Ashavic Dancer）"
        assert chunk.metadata["class_name"] == "伊沙-瓦舞者"
