"""test_profession_verify_checks.py — verify_profession 各 check 纯函数单测

参照 race 的 test_race_verify_checks.py 范式（构造最小 chunks dict 直测 check
函数，不读产物）。聚焦 5 个 check 的 PASS/FAIL 分支与 CP3 新增的「来源漂移
豁免」逻辑（_PALADIN_SOURCE_DRIFT：历史解析 bug 降级 WARNING 不 FAIL）。
"""
from vectorizer.verify import verify_profession as vp


def _arch(title, abbr, cls="圣骑士", arch=None):
    """构造 class_archetype StandardChunk dict。"""
    return {
        "title": title,
        "text": f"{title}：变体介绍。",
        "component_type": "class_archetype",
        "book_abbreviation": abbr,
        "doc_id": "核心职业/圣骑士/page_55.md",
        "metadata": {
            "class_name": cls,
            "archetype_name": arch or title.split("（")[0].split("(")[0].strip(),
        },
    }


def _feat(cls, title, abbr, subtype=None, arch=None):
    """构造 class_feature StandardChunk dict。"""
    return {
        "title": title,
        "text": f"{title}：能力描述。",
        "component_type": "class_feature",
        "book_abbreviation": abbr,
        "doc_id": "核心职业/圣骑士/page_55.md",
        "metadata": {
            "class_name": cls,
            "archetype_name": arch,
            "feature_subtype": subtype,
        },
    }


def _paladin_baseline():
    """43 个 EXPECTED 圣骑士变体全正确 + 3 个已知漂移豁免项 + 圣律沿循者 + 子誓约。

    子誓约以 class_feature 归属圣律沿循者（不得成为独立 archetype）。
    """
    chunks = [
        _arch(name, abbr) for name, abbr in vp.EXPECTED_PALADIN.items()
    ]
    # 3 个历史解析 bug（源数据权威 vs 产物 book 漂移，应豁免 WARNING 不 FAIL）
    chunks.append(_arch("亡灵制裁者（Undead Scourge）", "USH"))
    chunks.append(_arch("灰骑士（Gray Paladin）", "HA"))
    chunks.append(_arch("珍珠寻者（Pearl seeker）", "AA"))
    # 圣律沿循者 变体 + 10 子誓约 feature（归属圣律沿循者）
    for oath in vp.SUB_OATHS:
        chunks.append(_feat("圣骑士", f"{oath}（Oath）", "UM", arch="圣律沿循者"))
    return chunks


def _witch_hexes(n=5):
    return [
        _feat("女巫", f"巫术{i}", "UM", subtype="hex", arch="冬女巫") for i in range(n)
    ]


def _witch_patrons():
    return [
        _feat("女巫", f"早春庇护主", "UW", subtype="patron", arch="春之庇护"),
        _feat("女巫", f"盛夏庇护主", "UW", subtype="patron", arch="夏之庇护"),
        _feat("女巫", f"深秋庇护主", "UW", subtype="patron", arch="秋之庇护"),
        _feat("女巫", f"林地庇护主", "UW", subtype="patron", arch="林地庇护"),
    ]


def _bards(n=68):
    return [
        _feat("吟游诗人", f"传世名作{i}", "UM", subtype="bardic_masterpiece")
        for i in range(n)
    ]


def _winter_arch(abbr):
    return {
        "title": "冬女巫（Winter Witch）",
        "text": "冬女巫介绍。",
        "component_type": "class_archetype",
        "book_abbreviation": abbr,
        "doc_id": "基础职业/女巫/page_70.md",
        "metadata": {"class_name": "女巫", "archetype_name": "冬女巫"},
    }


# ============================================================
#  check_paladin_archetypes
# ============================================================


class TestPaladinArchetypes:
    def _full(self, winter_books=("ISM",)):
        chunks = _paladin_baseline() + _witch_hexes() + _witch_patrons() + _bards()
        chunks += [_winter_arch(b) for b in winter_books]
        return chunks

    def test_full_pass_with_known_drift(self):
        """43 变体全正确 + 3 豁免漂移 + 冬女巫 ISM → PASS（豁免降级 WARNING）"""
        ok, issues = vp.check_paladin_archetypes(self._full(), {})
        assert ok, issues

    def test_non_exempt_drift_fails(self):
        """非豁免变体来源书漂移（神圣防卫者应为 APG 实际 CRB）→ FAIL"""
        chunks = self._full()
        chunks.append(_arch("神圣防卫者（Divine Defender）", "CRB"))
        ok, issues = vp.check_paladin_archetypes(chunks, {})
        assert not ok
        assert any("神圣防卫者 应为 APG，实际 CRB" in i for i in issues)

    def test_sub_oath_as_archetype_fails(self):
        """子誓约被误识别为独立 archetype → FAIL"""
        chunks = self._full()
        chunks.append(_arch("反腐化誓约（Oath against Corruption）", "UM"))
        ok, issues = vp.check_paladin_archetypes(chunks, {})
        assert not ok
        assert any("应为 class_feature，但被识别为 class_archetype" in i for i in issues)

    def test_winter_witch_needs_ism_version(self):
        """冬女巫全部为 UM（无 ISM 出处）→ FAIL"""
        chunks = self._full(winter_books=("UM",))
        ok, issues = vp.check_paladin_archetypes(chunks, {})
        assert not ok
        assert any("应存在 ISM 版本" in i for i in issues)

    def test_winter_witch_ism_um_coexist_pass(self):
        """冬女巫 ISM + UM 并存（page_70 UM 标注合法）→ PASS"""
        chunks = self._full(winter_books=("ISM", "UM"))
        ok, issues = vp.check_paladin_archetypes(chunks, {})
        assert ok, issues


# ============================================================
#  check_no_false_archetypes
# ============================================================


class TestNoFalseArchetypes:
    def test_clean_archetypes_pass(self):
        """合法变体标题（含英文括号能力名形态）不触发负向 regex"""
        chunks = [
            _arch("圣律沿循者（Oathbound Paladin，又译誓缚圣武士）", "UM"),
            _arch("灰骑士（Gray Paladin）", "HA"),
        ]
        ok, issues = vp.check_no_false_archetypes(chunks, {})
        assert ok, issues

    def test_field_label_as_archetype_fails(self):
        """「本职技能（Class Skills）：」被误识别为 class_archetype → FAIL"""
        chunks = [{
            "title": "本职技能（Class Skills）：",
            "text": "正文",
            "component_type": "class_archetype",
            "book_abbreviation": "CRB",
            "doc_id": "基础职业/女巫/page_1.md",
            "metadata": {"class_name": "女巫"},
        }]
        ok, issues = vp.check_no_false_archetypes(chunks, {})
        assert not ok
        assert "V001" in issues[0]


# ============================================================
#  check_no_false_hex_sections
# ============================================================


class TestNoFalseHexSections:
    def test_generic_hex_section_fails(self):
        """通用章节标题（强力巫术（Major Hexes））被标为 hex → FAIL"""
        chunks = [{
            "title": "强力巫术（Major Hexes）",
            "text": "本章节列出强力巫术。",
            "component_type": "class_feature",
            "book_abbreviation": "CRB",
            "doc_id": "基础职业/女巫/page_1.md",
            "metadata": {"class_name": "女巫", "feature_subtype": "major_hex"},
        }]
        ok, issues = vp.check_no_false_hex_sections(chunks, {})
        assert not ok
        assert any("误识别为具体巫术" in i for i in issues)

    def test_missing_expected_hexes_fails(self):
        """5 个 P&P 具体巫术未独立成 chunk → FAIL"""
        ok, issues = vp.check_no_false_hex_sections([], {})
        assert not ok
        assert any("缺失" in i for i in issues)

    def test_expected_hexes_present_pass(self):
        """5 个 P&P 巫术独立成 class_feature chunk → PASS"""
        chunks = []
        for name in vp.EXPECTED_HEXES:
            for cn, abbr, sub in (
                (name, "CRB", "hex"), (f"高等{name}", "CRB", "major_hex"),
                (f"强化{name}", "CRB", "grand_hex"),
            ):
                chunks.append(_feat("女巫", cn, abbr, subtype=sub))
        ok, issues = vp.check_no_false_hex_sections(chunks, {})
        assert ok, issues


# ============================================================
#  check_venom_siphoner
# ============================================================


class TestVenomSiphoner:
    def test_complete_venom_pass(self):
        """汲毒巫 archetype + 3 能力独立 chunk 且归属汲毒巫 → PASS"""
        chunks = [
            {
                "title": "汲毒巫（Venom Siphoner）",
                "text": "汲毒巫介绍。该变体……",
                "component_type": "class_archetype",
                "book_abbreviation": "CRB",
                "doc_id": "基础职业/女巫/page_2.md",
                "metadata": {"class_name": "女巫", "archetype_name": "汲毒巫"},
            },
            _feat("女巫", "毒物魔宠（Venomous Familiar）", "CRB", arch="汲毒巫"),
            _feat("女巫", "毒液专家（Venom Expert）", "CRB", arch="汲毒巫"),
            _feat("女巫", "毒性血液（Venomous Blood）", "CRB", arch="汲毒巫"),
        ]
        ok, issues = vp.check_venom_siphoner(chunks, {})
        assert ok, issues

    def test_missing_archetype_fails(self):
        """缺少汲毒巫 archetype → FAIL"""
        ok, issues = vp.check_venom_siphoner([], {})
        assert not ok
        assert any("缺少汲毒巫" in i for i in issues)


# ============================================================
#  check_subtype_coverage
# ============================================================


class TestSubtypeCoverage:
    def test_min_count_violation_fails(self):
        """subtype 数量低于下限（rage_power 需 200）→ FAIL"""
        chunks = [_feat("野蛮人", "狂暴之力", "CRB", subtype="rage_power")]
        ok, issues = vp.check_subtype_coverage(chunks, {})
        assert not ok
        assert any("rage_power" in i for i in issues)

    def test_abundant_subtypes_pass(self):
        """每个 subtype 数量远超下限 → PASS"""
        chunks = []
        for subtype, min_count, _ in vp.EXPECTED_SUBTYPES:
            n = min_count + 3 if min_count else 1
            for i in range(n):
                chunks.append(_feat("某职业", f"{subtype}-{i}", "CRB", subtype=subtype))
        ok, issues = vp.check_subtype_coverage(chunks, {})
        assert ok, issues
