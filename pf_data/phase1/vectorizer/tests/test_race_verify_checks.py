"""
test_race_verify_checks.py — verify_races 补检查项 TDD 测试

背景（k3 验收建议 5，2026-08-04）：KN130（page_11 三族整行静默丢失，
doc 级召回 37/37 不覆盖行级）/ KN131（page_752 52 条误标 race_trait，
M22 只修聚合文件漏页文件）修复后，将「page_11 行级召回」「page_752
component_type」补入 verify_races，防止同类声明-现状偏差复现。
"""

from pathlib import Path

# ============================================================
#  _page11_race_names：源表数据行族名提取
# ============================================================


# 真实 page_11 形态切片（表 1 组别首行 + 无组别行；表 2 同构）
_SRC_SAMPLE = (
    "| 表：各种族随机起始年龄和老化效果 |\n"
    "| --- |\n"
    "| 种族 | 随机起始年龄 | 老化效果 |\n"
    "| 成年 | 天赋之力 | 自学成才 | 训练有素 | 中年 | 老年 | 暮年 | 最大年龄 |\n"
    "| 核心种族 | 矮人 | 40岁 | +3d6 | +5d6 | +7d6 | 125岁 | 188岁 | 250岁 | 250+2d100岁 |\n"
    "| 精灵 | 110岁 | +4d6 | +6d6 | +10d6 | 175岁 | 263岁 | 350岁 | 350+4d100岁 |\n"
    "| 表：各种族随机身高和体重 |\n"
    "| --- |\n"
    "| 基本身高 | 基本体重 | 修正值 | 体重乘数 | 基本身高 | 基本体重 | 修正值 | 体重乘数 |\n"
    "| 核心种族 | 矮人 | 3尺9寸 | 150磅 | 2d4 | ×7磅 | 3尺7寸 | 120磅 | 2d4 | ×7磅 |\n"
    "| 精灵 | 5尺4寸 | 100磅 | 2d8 | ×3磅 | 5尺4寸 | 90磅 | 2d6 | ×3磅 |\n"
)


class TestPage11RaceNames:
    """_page11_race_names：两表数据行族名提取（组别首行/无组别行）"""

    def test_extracts_race_names_from_both_tables(self):
        from vectorizer.verify.verify_races import _page11_race_names
        assert _page11_race_names(_SRC_SAMPLE) == {"矮人", "精灵"}

    def test_group_word_not_mistaken_as_race(self):
        """组别词（核心种族）不得被当族名（表 2 无组别行时首格即族名）"""
        from vectorizer.verify.verify_races import _page11_race_names
        names = _page11_race_names(_SRC_SAMPLE)
        assert "核心种族" not in names
        assert "成年" not in names
        assert "基本身高" not in names

    def test_header_rows_ignored(self):
        """表头/标题/分隔行（种族/成年/基本身高/---）不产出族名"""
        from vectorizer.verify.verify_races import _page11_race_names
        names = _page11_race_names(_SRC_SAMPLE)
        assert len(names) == 2
        assert "种族" not in names and "成年" not in names


# ============================================================
#  check_page11_row_recall：行级召回（KN130 防回归）
# ============================================================


class TestPage11RowRecall:
    """page_11 行级召回：源表族名 ↔ race_overview title 对账"""

    def _run(self, chunks, src_text=_SRC_SAMPLE, tmp_path=None):
        from vectorizer.verify.verify_races import check_page11_row_recall
        src = Path(tmp_path) / "page_11.md" if tmp_path is not None else None
        if src_text is not None and tmp_path is not None:
            src.write_text(src_text, encoding="utf-8")
        return check_page11_row_recall(chunks, {}, src)

    def test_all_rows_hit_passes(self, tmp_path):
        """两族两表全命中 → 通过"""
        chunks = [
            {"title": "矮人", "component_type": "race_overview"},
            {"title": "精灵", "component_type": "race_overview"},
        ]
        ok, issues = self._run(chunks, tmp_path=tmp_path)
        assert ok, issues

    def test_missing_row_fails(self, tmp_path):
        """源表有矮人无 chunk → 失败并点名（KN130 场景）"""
        chunks = [{"title": "精灵", "component_type": "race_overview"}]
        ok, issues = self._run(chunks, tmp_path=tmp_path)
        assert not ok
        assert any("矮人" in i for i in issues), issues

    def test_doc_title_not_counted(self, tmp_path):
        """非 overview chunk（年龄/身高和体重 intro）不参与对账——
        intro 标题（年龄/身高和体重）与族名无关，缺失不误报"""
        chunks = [
            {"title": "矮人", "component_type": "race_overview"},
            {"title": "精灵", "component_type": "race_overview"},
            {"title": "年龄", "component_type": "race_intro"},
        ]
        ok, issues = self._run(chunks, tmp_path=tmp_path)
        assert ok, issues

    def test_missing_doc_intro_ok(self, tmp_path):
        """源样本 2 族全命中时，即使无 intro chunk 也通过（只对账 overview）"""
        chunks = [
            {"title": "矮人", "component_type": "race_overview"},
            {"title": "精灵", "component_type": "race_overview"},
        ]
        ok, issues = self._run(chunks, tmp_path=tmp_path)
        assert ok, issues


# ============================================================
#  check_page752_component_type：page_752 全 alt_trait（KN131 防回归）
# ============================================================


class TestPage752ComponentType:
    """page_752（ISR 核心替换特性页文件）component_type 全为 alt_trait"""

    def test_all_alt_trait_passes(self):
        from vectorizer.verify.verify_races import check_page752_component_type
        chunks = [
            {"doc_id": "page_752", "title": "矮人", "component_type": "alt_trait"},
            {"doc_id": "page_752", "title": "旧日之敌", "component_type": "alt_trait"},
        ]
        ok, issues = check_page752_component_type(chunks, {})
        assert ok, issues

    def test_mixed_component_fails_with_titles(self):
        """KN131 场景：误标 race_trait 条目点名"""
        from vectorizer.verify.verify_races import check_page752_component_type
        chunks = [
            {"doc_id": "page_752", "title": "矮人", "component_type": "alt_trait"},
            {"doc_id": "page_752", "title": "旧日之敌", "component_type": "race_trait"},
        ]
        ok, issues = check_page752_component_type(chunks, {})
        assert not ok
        assert any("旧日之敌" in i for i in issues), issues

    def test_no_chunks_skips(self):
        """page_752 无 chunk → 跳过（不误报）"""
        from vectorizer.verify.verify_races import check_page752_component_type
        ok, issues = check_page752_component_type([], {})
        assert ok, issues


# ============================================================
#  check_race_name_enum：race_name 实体枚举合法性（B2）
# ============================================================


class TestRaceNameEnum:
    """race_name 必须落在 entity_enum.json（实体名 ∪ 别名 ∪ 豁免）内"""

    def _ctx(self):
        return {"entity_enum_set": {"矮人", "精灵", "猫族", "猫人", "年龄"}}

    def test_all_valid_passes(self):
        from vectorizer.verify.verify_races import check_race_name_enum
        chunks = [
            {"chunk_id": "a", "metadata": {"race_name": "矮人"}},
            {"chunk_id": "b", "metadata": {"race_name": "猫人"}},  # alias
            {"chunk_id": "c", "metadata": {"race_name": ""}},     # empty skipped
        ]
        ok, issues = check_race_name_enum(chunks, self._ctx())
        assert ok, issues

    def test_invalid_race_name_fails(self):
        from vectorizer.verify.verify_races import check_race_name_enum
        chunks = [
            {"chunk_id": "a", "metadata": {"race_name": "矮人"}},
            {"chunk_id": "b", "metadata": {"race_name": "未知污染"}},
        ]
        ok, issues = check_race_name_enum(chunks, self._ctx())
        assert not ok
        assert any("未知污染" in i for i in issues), issues

    def test_exemption_value_passes(self):
        from vectorizer.verify.verify_races import check_race_name_enum
        chunks = [
            {"chunk_id": "a", "metadata": {"race_name": "年龄"}},  # exemption
        ]
        ok, issues = check_race_name_enum(chunks, self._ctx())
        assert ok, issues

    def test_empty_race_name_skipped(self):
        from vectorizer.verify.verify_races import check_race_name_enum
        chunks = [
            {"chunk_id": "a", "metadata": {"race_name": ""}},
            {"chunk_id": "b", "metadata": {}},
        ]
        ok, issues = check_race_name_enum(chunks, self._ctx())
        assert ok, issues
