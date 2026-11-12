"""test_spell_level_cleaning.py — spell_level 元数据清洗单测（2026-10-28 方案）

覆盖：
  - R3 归一表：20 组获批映射逐一断言 + level 不动 + 幂等
  - R3 不动项：巡林客/导师/红螳螂杀手/召唤施/快速医疗/法术 保持原样
  - R3 复合拆条：术士法师 → 术士 + 法师（两条，level 复制）
  - R2 头残片白名单：清单内回填 (class, level)、清单外结构性跳过
  - R4：class=None（裸环级）保持原样
"""
import pytest

from vectorizer.processors.spell import (
    SPELL_LEVEL_A_BUCKET_WHITELIST,
    _CLASS_COMPOUND_SPLIT,
    _CLASS_NAME_NORM,
    _SPELL_LEVEL_CUT_EXCLUSION_TITLES,
    _normalize_spell_level_items,
)

# 与 processors/spell.py 常量同源断言（防实现漂移）
_APPROVED = {
    "炼金术士": "炼金术师", "练金术师": "炼金术师", "鍊金术师": "炼金术师",
    "炼金师": "炼金术师",
    "诗人": "吟游诗人", "游吟诗人": "吟游诗人", "吟游吟游诗人": "吟游诗人",
    "战斗祭祀": "战斗祭司", "战争祭司": "战斗祭司",
    "血脉暴怒者": "血脉狂怒者",
    "唤魂者": "唤魂师", "唤灵师": "唤魂师", "唤师师": "唤魂师",
    "通灵师": "通灵者",
    "异能师": "异能者", "异能师者": "异能者",
    "召唤师（Unchained）": "召唤师（Unchained）",
    "召唤师（unchained）": "召唤师（Unchained）",
    "召唤师(Unchained)": "召唤师（Unchained）",
    "反圣骑士": "反圣武士", "黑暗卫士": "反圣武士",
    # KN245 裁定（2026-10-30）：括号缩写形态，全库仅 1 处（食尸鬼的饥饿）
    "黑暗卫士(Blk)": "反圣武士",
    "圣骑士": "圣武士",
    "审判官": "审判者", "判官": "审判者",
    "慛眠师": "催眠师",
    "巫师": "法师",
    "魔战": "魔战士", "密学士": "秘学士", "奥能者": "奥能师",
}

_UNTOUCHED = ["巡林客", "导师", "红螳螂杀手", "召唤施", "快速医疗", "法术"]


class TestClassNameNorm:
    def test_mapping_matches_approved_table(self):
        """常量与拍板审批表逐条一致（20 组，多对一展开后键集合相等）"""
        assert _CLASS_NAME_NORM == _APPROVED

    def test_no_untouched_names_in_mapping(self):
        """红线：不动项不得入常量"""
        for name in _UNTOUCHED:
            assert name not in _CLASS_NAME_NORM

    def test_level_unchanged_and_idempotent(self):
        items = [{"class": k, "level": 3} for k in _APPROVED]
        once = _normalize_spell_level_items(items)
        twice = _normalize_spell_level_items(once)
        assert twice == once
        assert all(it["level"] == 3 for it in once)

    def test_compound_split_shushi_fashi(self):
        """术士法师 → 术士 + 法师（审批表第 20 组，拆两条）"""
        out = _normalize_spell_level_items([{"class": "术士法师", "level": 4}])
        assert out == [{"class": "术士", "level": 4}, {"class": "法师", "level": 4}]
        # 幂等
        assert _normalize_spell_level_items(out) == out

    def test_untouched_preserved(self):
        items = [{"class": n, "level": 1} for n in _UNTOUCHED]
        assert _normalize_spell_level_items(items) == items

    def test_class_none_preserved(self):
        """R4：裸环级 class=None 保持原样"""
        items = [{"class": None, "level": 3}]
        assert _normalize_spell_level_items(items) == items

    def test_compound_table_only_approved(self):
        assert set(_CLASS_COMPOUND_SPLIT) == {"术士法师"}


class TestABucketWhitelist:
    def test_whitelist_final_count(self):
        """修订 1 终值：52 已修 + 504 新回填 = 556（探针 584 − 裁 25 − M1 接管 3）"""
        assert len(SPELL_LEVEL_A_BUCKET_WHITELIST) == 556

    def test_whitelist_shape(self):
        """条目 = 最终 items（词表校验/F3/标点剥离/归一后），class 非空、level 0-9"""
        for cid, items in SPELL_LEVEL_A_BUCKET_WHITELIST.items():
            assert cid.startswith("spell_")
            assert items, f"{cid} 空 items"
            for it in items:
                assert it["class"] and 0 <= it["level"] <= 9, f"{cid} 异常项 {it}"

    def test_no_unmapped_dirty_tokens(self):
        """白名单 items 不得含未获批脏名 token（表外脏名 6 条已裁除）"""
        dirty = {"黑暗卫士", "吟游吟游诗人", "歌者/歌者"}  # KN245 后三词已获批归一
        for cid, items in SPELL_LEVEL_A_BUCKET_WHITELIST.items():
            for it in items:
                assert it["class"] not in dirty, f"{cid} 含表外脏名 {it['class']}"

    def test_m1_taken_over_three_not_in_whitelist(self):
        """M1 通道接管 3 条不占白名单名额（值由补救通道产出，与白名单一致）"""
        for suffix in ("Spell FoP_0005", "page_1365_0403", "page_1365_0404"):
            assert not any(k.endswith(suffix) for k in SPELL_LEVEL_A_BUCKET_WHITELIST)

    def test_cut_ids_not_in_whitelist(self):
        """KN245 18 条裁定项均不入白名单（值来自解析/别名/标签容错，非头残片回填）"""
        cut = ["Spell FoP_0009","page_1008_0017","page_1034_0005","page_1034_0008",
               "page_1048_0003","page_1168_0017","page_1168_0029",
               "page_1363_0030","page_1365_0278","page_1365_0372","page_1365_0384",
               "page_1365_0413","page_1365_0471","page_1365_0490","page_1494_0005",
               "任务与战役_法术_0000","BotM_0000","BotM_0001"]
        for suffix in cut:
            assert not any(k.endswith(suffix) for k in SPELL_LEVEL_A_BUCKET_WHITELIST), suffix

# ============================================================
# F4（返工）：rescue 通道 / M3 守卫 / 优先级单测
# ============================================================

from vectorizer.processors.spell import (
    SpellProcessor,
    _SPELL_LEVEL_CUT_EXCLUSIONS,
    _SPELL_LEVEL_RESCUE_LEGAL_CLASSES,
    _is_cut_exclusion,
    parse_fields,
)
from vectorizer.processors.base import Chunk


def _mk_chunk(cid="spell_test_0000", doc="test_doc"):
    return Chunk(
        chunk_id=cid, doc_id=doc, category="spell", component_type="spell",
        title="", text="", book_abbreviation="?", book_name_cn="",
        book_name_en="", source_confidence=0,
    )


class TestRescueChannel:
    """M1 C 桶窄路补救通道行为契约"""

    _PRE = "测试术(Test)\n\n**等级**：吟游诗人/歌者 \n2、审判者 2**施放时间**：标准"

    _TEXT = "**测试术(Test)**\n**等级：**吟游诗人/歌者 2、审判者 2\n"

    def _item(self, pre=None):
        return {"name": "测试术", "text": self._TEXT,
                "_pre_unify_text": pre if pre is not None else self._PRE}

    def test_rescue_parses_glued_line(self):
        r = SpellProcessor._rescue_inline_level(self._item(), _mk_chunk())
        assert sorted((i["class"], i["level"]) for i in r) == [
            ("吟游诗人", 2), ("审判者", 2), ("歌者", 2)]

    def test_missing_snapshot_skips(self):
        """快照键缺失 → 跳过（向后兼容）"""
        assert SpellProcessor._rescue_inline_level({"name": "测试术"}, _mk_chunk()) == []

    def test_name_not_found_skips(self):
        assert SpellProcessor._rescue_inline_level(
            {"name": "不存在的条目", "text": self._TEXT, "_pre_unify_text": self._PRE}, _mk_chunk()) == []

    def test_bare_number_rejected(self):
        """裸数字（无职业）→ 拒填（B 桶拍板）"""
        item = {"name": "测试术", "text": self._TEXT,
                "_pre_unify_text": "测试术(Test)\n\n**等级**：3\n**施放时间**"}
        assert SpellProcessor._rescue_inline_level(item, _mk_chunk()) == []

    def test_illegal_token_rejected(self):
        """词表外 token → 整体拒填（魔战已随 KN245 获批合法化，用仍非法的串）"""
        item = {"name": "测试术", "text": self._TEXT,
                "_pre_unify_text": "测试术(Test)\n\n**等级**：快速医疗 2，法师 2"}
        assert SpellProcessor._rescue_inline_level(item, _mk_chunk()) == []

    def test_ma_doc_excluded(self):
        """MA 文档排除（page_625 清单 + MA 前缀）"""
        for doc in ("page_625", "MA-神话"):
            r = SpellProcessor._rescue_inline_level(self._item(), _mk_chunk(doc=doc))
            assert r == [], doc

    def test_cut_exclusion_registry_closed(self):
        """KN245 已清零（2026-10-30）：裁除集为空，机制保留作未来登记位。"""
        assert _SPELL_LEVEL_CUT_EXCLUSION_TITLES == {}
        for cid, title in {
            "spell_page_1008_0018": "受虐之影",
            "spell_page_1363_0030": "食尸鬼的饥饿",
            "spell_任务与战役_法术_0000": "典礼",
            "spell_月之血脉BotM_法术_0000": "诅咒瞪视",
        }.items():
            assert not _is_cut_exclusion(cid, title), (cid, title)

    def test_dedup(self):
        pre = "测试术(Test)\n\n**等级**：先知 4、先知 4、牧师 3"
        r = SpellProcessor._rescue_inline_level(self._item(pre), _mk_chunk())
        assert sorted((i["class"], i["level"]) for i in r) == [("先知", 4), ("牧师", 3)]

    def test_token_punct_strip(self):
        """token 前导黏连标点剥离（；;：:，、）→ 催眠师合法化"""
        pre = "测试术(Test)\n\n**等级**：；催眠师 3、异能者 3"
        r = SpellProcessor._rescue_inline_level(self._item(pre), _mk_chunk())
        assert sorted((i["class"], i["level"]) for i in r) == [("催眠师", 3), ("异能者", 3)]


class TestM3SchoolGuard:
    """M3 first-wins 环位值学派检测守卫"""

    def test_guard_triggers_on_school_first(self):
        text = ("**X (Y)**\n**环位：**塑能系\n**等级：**吟游诗人4，牧师4\n"
                "**持续时间：**1轮")
        raw = parse_fields(text)
        assert "吟游诗人" in raw["spell_level"]

    def test_guard_untouched_normal_school(self):
        """正常场景（school 键装学派，spell_level 首值非学派）不误伤"""
        text = ("**X (Y)**\n**学派：**塑能系\n**等级：**吟游诗人4，牧师4\n"
                "**持续时间：**1轮")
        raw = parse_fields(text)
        assert raw["spell_level"] == "吟游诗人4，牧师4"

    def test_guard_untouched_non_school_first(self):
        """首值非学派名 → 零变化"""
        text = "**X (Y)**\n**环位：**吟游诗人4，牧师4\n**持续时间：**1轮"
        raw = parse_fields(text)
        assert raw["spell_level"] == "吟游诗人4，牧师4"

    def test_guard_untouched_other_fields(self):
        """其他字段不受守卫影响"""
        text = ("**X (Y)**\n**环位：**塑能系\n**等级：**牧师4\n"
                "**持续时间：**1轮\n**范围：**近距")
        raw = parse_fields(text)
        assert raw["duration"] == "1轮" and raw["range"] == "近距"


class TestKn248LevelLabelGuard:
    """KN248：条目自身没有等级标签时，不得从 400 字符快照窃取相邻法术环级。"""

    # 快照里紧跟一条真实法术的等级行（模拟 400 字符窗口越界）
    _PRE = ("唤醒被噬之魂（Awaken the Devoured）**\n**学派：**预言系[痛苦]\n"
            "**等级：**牧师 \n5，审判者 4，异能者 5\n**施法时间：**1标准动作")

    def _item(self, text, name="法术"):
        return {"name": name, "text": text, "_pre_unify_text": self._PRE}

    def test_section_intro_refused(self):
        """章节导语：只有标题 + 导读段"""
        text = "**法术 (Spells)**\n《永罪之书》里面纪录了无以计数的法术……"
        assert SpellProcessor._rescue_inline_level(self._item(text), _mk_chunk()) == []

    def test_table_fragment_refused(self):
        """表格碎片：区间数字表头"""
        text = "**7-9            中度 (Medium)**"
        assert SpellProcessor._rescue_inline_level(self._item(text), _mk_chunk()) == []

    def test_empty_stub_refused(self):
        """空壳条目：标题 + 来源行（SMF012 转换遗留块头）"""
        text = ("**愚者之灾 (Befuddled Combatant)**\n"
                "> 来源：治疗者手册（Healer's Handbook）HH，页码见原书")
        assert SpellProcessor._rescue_inline_level(self._item(text), _mk_chunk()) == []

    def test_prose_level_words_not_counted_as_label(self):
        """正文里的「1轮/等级」「施法者等级」不算等级标签"""
        text = ("**发散  (D)**\n**豁免：** 反射，通过则减半\n"
                "**持续时间：** 1轮/等级\n施法者等级+1")
        assert SpellProcessor._rescue_inline_level(self._item(text), _mk_chunk()) == []

    def test_own_bold_label_still_rescued(self):
        """自身有 **等级：** 标签时，rescue 仍按快照补救（不误伤）"""
        text = "**测试术 (Test)**\n**等级：**牧师 \n5"
        r = SpellProcessor._rescue_inline_level(
            {"name": "测试术", "text": text,
             "_pre_unify_text": "测试术(Test)\n**等级：**牧师 5、审判者 4"},
            _mk_chunk())
        assert sorted((i["class"], i["level"]) for i in r) == [
            ("审判者", 4), ("牧师", 5)]


class TestRescueBeforeWhitelistPriority:
    """F1：rescue 产出完整值优先于白名单残片值；白名单仅作校验锚/兜底"""

    def test_rescue_full_value_wins(self):
        """rescue 解出完整值（含白名单缺的首组职业）；白名单项 ⊂ rescue"""
        cid = "spell_test_prio_0000"
        wl_items = [{"class": "审判者", "level": 2}]
        pre = "测试术(Test)\n\n**等级**：吟游诗人/歌者 2、审判者 2、牧师 3"
        item = {"name": "测试术", "text": "**测试术(Test)**\n**等级：**吟游诗人/歌者 2、审判者 2\n",
                "_pre_unify_text": pre}
        r = SpellProcessor._rescue_inline_level(item, _mk_chunk(cid=cid))
        assert sorted((i["class"], i["level"]) for i in r) == [
            ("吟游诗人", 2), ("审判者", 2), ("歌者", 2), ("牧师", 3)]
        got = {(i["class"], i["level"]) for i in r}
        assert all((i["class"], i["level"]) in got for i in wl_items)

    def test_whitelist_backstop_when_rescue_empty(self, monkeypatch):
        """rescue 空 → 白名单兜底"""
        from vectorizer.processors import spell as spell_mod
        cid = "spell_test_prio_0001"
        wl_items = [{"class": "女巫", "level": 2}]
        monkeypatch.setitem(spell_mod.SPELL_LEVEL_A_BUCKET_WHITELIST, cid, wl_items)
        item = {"name": "测试术", "text": "**测试术(Test)**\n**等级：**女巫 2\n",
                "_pre_unify_text": "测试术(Test)\n\n**等级**：3"}
        assert SpellProcessor._rescue_inline_level(item, _mk_chunk(cid=cid)) == []
        assert SpellProcessor._a_bucket_whitelist_level(item, _mk_chunk(cid=cid)) == wl_items


# ============================================================
# KN245 获批映射与通用规则（2026-10-29 用户逐条批准）
# ============================================================

from vectorizer.processors.spell import (
    _repair_repeated_word,
    _truncate_trailing_prose,
)


class TestKn245ApprovedMappings:
    """获批 5 组：①魔战→魔战士 ②密学士→秘学士 ③奥能者→奥能师"""

    @pytest.mark.parametrize("dirty,clean", [
        ("魔战", "魔战士"), ("密学士", "秘学士"), ("奥能者", "奥能师"),
    ])
    def test_mapping_in_norm(self, dirty, clean):
        from vectorizer.processors.spell import _normalize_class_name
        assert _normalize_class_name(dirty) == clean
        # 幂等
        assert _normalize_class_name(clean) == clean

    def test_normalize_items_applies_mapping(self):
        out = _normalize_spell_level_items([{"class": "魔战", "level": 3}])
        assert out == [{"class": "魔战士", "level": 3}]


class TestKn245GenericRules:
    """获批通用规则：重复词修复 + 组内去重 + 分号组拆分"""

    def test_repeated_word_repair(self):
        """吟游吟游诗人→吟游诗人（XXYY→XY 型）"""
        assert _repair_repeated_word("吟游吟游诗人") == "吟游诗人"
        out = _normalize_spell_level_items([{"class": "吟游吟游诗人", "level": 0}])
        assert out == [{"class": "吟游诗人", "level": 0}]

    def test_repeated_word_repair_negative(self):
        """非重复形态不误伤（术士/吟游诗人/魔战士原样）"""
        for ok in ("术士", "吟游诗人", "魔战士", "先知", "战斗祭司"):
            assert _repair_repeated_word(ok) == ok

    def test_group_dedup_keep_first(self):
        """复合组内重复 token 去重（先知/奥能师 保首一次）"""
        items = [{"class": "牧师", "level": 0}, {"class": "先知", "level": 0},
                 {"class": "奥能师", "level": 0}, {"class": "先知", "level": 0}]
        out = _normalize_spell_level_items(items)
        assert sorted((i["class"], i["level"]) for i in out) == sorted(
            [("奥能师", 0), ("先知", 0), ("牧师", 0)])

    def test_group_dedup_negative_distinct_levels(self):
        """同级不同环不去重（先知 0/先知 1 保留）"""
        items = [{"class": "先知", "level": 0}, {"class": "先知", "level": 1}]
        assert _normalize_spell_level_items(items) == items

    def test_semicolon_group_split(self):
        """分号=组分隔符（召唤师 4；女巫 3 → 召唤师 4 + 女巫 3，_truncate 单点）"""
        from vectorizer.formats.spell import SpellFormat
        cleaned = _truncate_trailing_prose("魔战士 3、召唤师 4；女巫 3")
        parsed = SpellFormat.parse_spell_level(cleaned)
        pairs = sorted((i["class"], i["level"]) for i in parsed if i.get("class"))
        assert pairs == sorted([("女巫", 3), ("召唤师", 4), ("魔战士", 3)])

    def test_semicolon_split_no_false_positive(self):
        """无分号字符串零影响（幂等）"""
        assert _truncate_trailing_prose("术士/法师 2") == "术士/法师 2"

    def test_rescue_end_to_end_kn245(self):
        """端到端：含获批脏名+重复词+分号的源行经 rescue 管线产出干净值"""
        pre = ("阴影陷阱(Shadow Trap)\n\n**等级**：反圣武士 1、吟游吟游诗人/歌者/歌者 1、"
               "血脉狂怒者 1、术士/法师/奥能师/奥能师 1、女巫 1")
        item = {"name": "阴影陷阱", "text": "**阴影陷阱(Shadow Trap)**\n**等级：**反圣武士 1\n",
                "_pre_unify_text": pre}
        r = SpellProcessor._rescue_inline_level(item, _mk_chunk())
        pairs = sorted((i["class"], i["level"]) for i in r)
        assert pairs == sorted([("反圣武士", 1), ("吟游诗人", 1), ("歌者", 1),
                                ("血脉狂怒者", 1), ("术士", 1), ("法师", 1),
                                ("奥能师", 1), ("女巫", 1)])


class TestRescueAnchorGuard:
    """QA-K1 返工：错锚定场景回归——污染标题/锚位不符拒填（宁空勿错）"""

    def test_polluted_roman_title_refused(self):
        """KN244 污染标题（I/II/III/IV）锚定会抓到无关等级行 → 拒填"""
        # 快照内首个 "IV" 在无关条目（形态后缀 IV）处——旧逻辑会抓来错等级行
        pre = ("其他术(Other)\n\n**等级**：术士/法师 8\n\n"
               "撕扯肢体 IV(Rending Flesh)\n\n**等级**：异能者 8\n\n无关术 形态IV 说明")
        item = {"name": "IV", "_pre_unify_text": pre}
        assert SpellProcessor._rescue_inline_level(item, _mk_chunk()) == []

    def test_polluted_title_variants_all_refused(self):
        for t in ("I", "II", "III", "IV", "V", "VI"):
            item = {"name": t, "_pre_unify_text": f"X\n\n**等级**：术士 1"}
            assert SpellProcessor._rescue_inline_level(item, _mk_chunk()) == [], t

    def test_good_title_midline_anchor_refused(self):
        """锚位边界：名称出现在行中（非行首/【】后标题位）→ 拒填"""
        pre = "正文说明术士术法等级：牧师 1、法师 2\n后续内容"
        item = {"name": "术士", "_pre_unify_text": pre}
        # 快照中 "术士" 首次出现在行首之外 → 无合法锚位
        assert SpellProcessor._rescue_inline_level(item, _mk_chunk()) == []

    def test_good_title_line_start_anchor_ok(self):
        """正常标题（行首锚位）不受影响"""
        pre = "测试术(Test)\n\n**等级**：吟游诗人 2、审判者 2"
        item = {"name": "测试术", "text": "**测试术(Test)**\n**等级：**吟游诗人 2\n",
                "_pre_unify_text": pre}
        r = SpellProcessor._rescue_inline_level(item, _mk_chunk())
        assert sorted((i["class"], i["level"]) for i in r) == [("吟游诗人", 2), ("审判者", 2)]

    def test_school_bracket_title_anchor_ok(self):
        """【学派】前缀标题（】后锚位）不受影响"""
        pre = "【塑能】测试术(Test)\n\n**等级**：牧师 1"
        item = {"name": "测试术", "text": "**【塑能】测试术(Test)**\n**等级：**牧师 1\n",
                "_pre_unify_text": pre}
        r = SpellProcessor._rescue_inline_level(item, _mk_chunk())
        assert r == [{"class": "牧师", "level": 1}]
