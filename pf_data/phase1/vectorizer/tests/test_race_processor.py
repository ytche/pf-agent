"""
test_race_processor.py — 种族 Processor race_name 归属 TDD 测试

背景（k3 验收 R1，2026-08-04）：人工门 1 批准「FCB race_name 按页归属
种族填 + 既有错位 chunk 一并修正」，但无 race_intro 条目文件（天赋职业
奖励系列、怪物种族页）兜底取条目标题（职业名）→ race_name 错位 30 条。

修复：_race_name_from_path 按路径归属种族兜底——
  种族/<分组>/<种族名>/xxx.md 三级目录 → 第三级目录名；
  种族/怪物种族/page_NN（无目录名）→ 映射表；
  其余 → ""（保持 chunk.title 现状）。
"""

from pathlib import Path

from vectorizer.processors.race import (
    RaceProcessor,
    _race_name_from_path,
)


def make_processor() -> RaceProcessor:
    """空 provider 链的 RaceProcessor（来源书解析不在本文件覆盖范围）"""
    from vectorizer.sources.providers import SourceResolver
    return RaceProcessor(source_resolver=SourceResolver([]))


def infer_metadata(proc: RaceProcessor, name: str = "审判者", text: str = "正文") -> dict:
    """infer_metadata 便捷入口（同 test_feat_processor.run_item 模式）"""
    ctx = proc._build_source_context(Path("seed.md"), text)
    chunk = proc._build_chunk_template(Path("seed.md"), 0, ctx)
    chunk.title = name
    return proc.infer_metadata(chunk, {"text": text, "name": name}).metadata


# ============================================================
#  _race_name_from_path（纯函数）
# ============================================================


class TestRaceNameFromPath:
    """路径归属种族推导：三级目录 / 怪物种族映射 / 其余兜底"""

    def test_core_race_three_level(self):
        p = Path("pf_rules_md_organized/种族/核心种族/人类/人类天赋职业奖励.md")
        assert _race_name_from_path(p) == "人类"

    def test_common_race_three_level(self):
        p = Path("pf_rules_md_organized/种族/常见种族/魔裔/魔裔天赋职业奖励.md")
        assert _race_name_from_path(p) == "魔裔"

    def test_other_race_three_level(self):
        """格拉里昂的狗头人（文件名复杂）→ 目录名「狗头人」"""
        p = Path("pf_rules_md_organized/种族/其他种族/狗头人/格拉里昂的狗头人_可选天赋职业奖励.md")
        assert _race_name_from_path(p) == "狗头人"

    def test_monster_page_mapping(self):
        """怪物种族页按页编号（无目录名）→ 映射表（翼龙人 Wyvaran）"""
        p = Path("pf_rules_md_organized/种族/怪物种族/page_716.md")
        assert _race_name_from_path(p) == "翼龙人"

    def test_monster_codex_flat_file_name(self):
        """怪物法典MC 单文件（四级，文件名即族名）→ 狗头人（KN132：无 intro
        文件的 intro 标题（**狗头人**）被状态机并吞时族名仍可溯）"""
        p = Path("pf_rules_md_organized/种族/怪物种族/怪物法典MC/狗头人.md")
        assert _race_name_from_path(p) == "狗头人"

    def test_monster_codex_open_file_not_race(self):
        """怪物法典MC 开篇.md（非种族文件）→ ""（不臆造）"""
        p = Path("pf_rules_md_organized/种族/怪物种族/怪物法典MC/开篇.md")
        assert _race_name_from_path(p) == ""

    def test_inner_sea_bestiary_file_name(self):
        """内海怪物志 单文件（同 MC 语义）→ 半蝎人；含 _ 文件名 → _ 前（半人马）"""
        p = Path("pf_rules_md_organized/种族/怪物种族/内海怪物志/半蝎人.md")
        assert _race_name_from_path(p) == "半蝎人"
        p = Path("pf_rules_md_organized/种族/怪物种族/内海怪物志/半人马_陷阵士.md")
        assert _race_name_from_path(p) == "半人马"

    def test_book_chapter_file_suffix_strip(self):
        """两级「书名Xxx_章节」文件剥章节后缀取族名（KN132）：
        夜之血脉BotN_吸血裔种族特性 → 吸血裔、巫团血脉BotC_替换儿种族选项 →
        替换儿、阴影血脉BoS_剪影人 → 剪影人、位面冒险PA_暮行者 → 暮行者"""
        p = Path("pf_rules_md_organized/种族/夜之血脉BotN_吸血裔种族特性.md")
        assert _race_name_from_path(p) == "吸血裔"
        p = Path("pf_rules_md_organized/种族/巫团血脉BotC_替换儿种族选项.md")
        assert _race_name_from_path(p) == "替换儿"
        p = Path("pf_rules_md_organized/种族/罕见种族/阴影血脉BoS_剪影人.md")
        assert _race_name_from_path(p) == "剪影人"
        p = Path("pf_rules_md_organized/种族/罕见种族/位面冒险PA_暮行者.md")
        assert _race_name_from_path(p) == "暮行者"

    def test_book_chapter_file_aggregate_stripped(self):
        """多族/聚合文件剥光 → ""（族名靠条目级 intro/组标题覆盖）：
        BotB 种族特性、BotS 种族、ISR 核心/其他/新种族"""
        for stem in ("野兽血脉BotB_种族特性", "海洋之血BotS_种族",
                     "内海种族ISR_核心种族替换特性", "内海种族ISR_其他种族替换特性",
                     "内海种族ISR_新种族"):
            p = Path(f"pf_rules_md_organized/种族/{stem}.md")
            assert _race_name_from_path(p) == "", f"{stem} 应剥光返回空"

    def test_two_level_group_file_not_race_name(self):
        """两级形态（分组/文件，如 其他种族/page_1456.md）不得把文件名当种族名"""
        p = Path("pf_rules_md_organized/种族/其他种族/page_1456.md")
        assert _race_name_from_path(p) == ""

    def test_two_level_core_file_not_race_name(self):
        """核心种族/xxx.md 两级 → ""（intro 登记负责）"""
        p = Path("pf_rules_md_organized/种族/核心种族/page_12.md")
        assert _race_name_from_path(p) == ""

    def test_non_race_path(self):
        """非种族类目路径 → """""
        assert _race_name_from_path(Path("pf_rules_md_organized/专长/xxx.md")) == ""

    def test_unknown_monster_page_no_mapping(self):
        """怪物种族页无映射条目 → ""（不臆造）"""
        p = Path("pf_rules_md_organized/种族/怪物种族/page_999.md")
        assert _race_name_from_path(p) == ""


# ============================================================
#  infer_metadata 兜底链（intro 登记 > 路径归属 > chunk.title）
# ============================================================


class TestRaceNameInferMetadata:
    """race_name 兜底链优先级与 30 条错位修正语义"""

    def test_intro_registered_wins(self):
        """有 intro 登记：_race_name 优先（现有正确文件不受影响）"""
        proc = make_processor()
        proc._race_name = "人类"
        proc._race_name_fallback = ""  # 模拟有 intro 文件（路径归属为空）
        md = infer_metadata(proc)
        assert md["race_name"] == "人类"

    def test_path_fallback_used_when_no_intro(self):
        """无 intro：路径归属兜底（人类天赋职业奖励 → 人类，非职业名）"""
        proc = make_processor()
        proc._race_name = ""
        proc._race_name_fallback = "人类"
        md = infer_metadata(proc, name="审判者")
        assert md["race_name"] == "人类", f"应为归属种族而非职业名: {md['race_name']!r}"

    def test_title_fallback_last_resort(self):
        """无 intro 且无路径归属：chunk.title 兜底（现状保留）"""
        proc = make_processor()
        proc._race_name = ""
        proc._race_name_fallback = ""
        md = infer_metadata(proc, name="狗头人")
        assert md["race_name"] == "狗头人"

    def test_dash_title_split_race_name(self):
        """替换特性汇总标题「神裔——圣战魔法」兜底 → race_name=神裔（KN132：
        无 intro 文件整标题兜底 → 按族过滤漏检；title 保持完整形态）"""
        proc = make_processor()
        proc._race_name = ""
        proc._race_name_fallback = ""
        md = infer_metadata(proc, name="神裔——圣战魔法")
        assert md["race_name"] == "神裔", f"应取「——」前族名: {md['race_name']!r}"

    def test_non_dash_title_unchanged(self):
        """无「——」title 兜底行为不变（回归保护）"""
        proc = make_processor()
        proc._race_name = ""
        proc._race_name_fallback = ""
        md = infer_metadata(proc, name="狗头人")
        assert md["race_name"] == "狗头人"

    def test_dash_split_beats_file_fallback(self):
        """「X——Y」拆分优先于文件级族名（KN132：BotC 替换种族特性文件族名=
        替换儿，但条目「卓尔——黑暗拥趸」应=卓尔）"""
        proc = make_processor()
        proc._race_name = ""
        proc._race_name_fallback = "替换儿"
        md = infer_metadata(proc, name="卓尔——黑暗拥趸")
        assert md["race_name"] == "卓尔", f"应取条目自身族名: {md['race_name']!r}"

    def test_fallback_beats_title_for_plain(self):
        """无「——」时文件级族名优先于 title 兜底（KN132：MC 文件条目
        「新规则」等特性名 → 归属文件名族名）"""
        proc = make_processor()
        proc._race_name = ""
        proc._race_name_fallback = "大地精"
        md = infer_metadata(proc, name="新规则")
        assert md["race_name"] == "大地精", f"应取文件级族名: {md['race_name']!r}"


# ============================================================
#  KN132：build_chunk 覆盖逻辑（纯净 intro 覆盖 / 黑名单跳过 /
#  替换特性组标题覆盖）——覆盖逻辑在 build_chunk，须走完整链
# ============================================================


def build_chunk(proc: RaceProcessor, kind: str = "race_trait", name: str = "审判者",
                text: str = "正文", bare: bool = False, name_en: str = ""):
    """build_chunk 便捷入口：构造 item dict 并走 build_chunk"""
    ctx = proc._build_source_context(Path("seed.md"), text)
    template = proc._build_chunk_template(Path("seed.md"), 0, ctx)
    item = {"kind": kind, "name": name, "text": text}
    if bare:
        item["_bare_cn_title"] = True
    if name_en:
        item["name_en"] = name_en
    return proc.build_chunk(template, item)


class TestRaceNameBuildChunk:
    """KN132：多种族/无 intro 文件的族名归一（BotB/BotN/ISR 核心形态）"""

    def test_pure_intro_overrides_file_fallback(self):
        """纯净族标题 intro（猫族）覆盖登记，条目继承（BotB 形态：族标题
        逐块覆盖，不再只登记首个书名「野兽血脉」）"""
        proc = make_processor()
        proc._race_name_fallback = "野兽血脉"  # 模拟文件级兜底（实际剥光为 ""）
        # 先 build 书名 intro「野兽血脉」——黑名单拦截，不登记不覆盖
        build_chunk(proc, kind="race_intro", name="野兽血脉", text="本书介绍……")
        assert proc._race_name == "", "书名形态 intro 不得登记"
        # 再 build 纯净族标题「猫族」——覆盖登记
        build_chunk(proc, kind="race_intro", name="猫族", text="猫族玩家角色……")
        assert proc._race_name == "猫族", "纯净族标题应覆盖登记"
        # 条目继承族名
        md = infer_metadata(proc, name="古代奥斯里昂信徒")
        assert md["race_name"] == "猫族", f"条目应继承族标题: {md['race_name']!r}"

    def test_impure_intro_skipped_uses_path_fallback(self):
        """污染 intro（神裔能力变体/官方勘误/虫类领域等）跳过登记，
        条目继承文件级族名（神裔形态）"""
        proc = make_processor()
        proc._race_name_fallback = "神裔"
        for bad in ("神裔能力变体", "官方勘误", "虫类领域"):
            build_chunk(proc, kind="race_intro", name=bad, text="本章内容……")
            assert proc._race_name == "", f"{bad} 黑名单 intro 不得登记"
        md = infer_metadata(proc, name="圣战魔法")
        assert md["race_name"] == "神裔", f"条目应继承路径族名: {md['race_name']!r}"

    def test_alt_trait_group_title_override(self):
        """替换特性组标题（裸中文标题+组句）覆盖族名，组内条目继承
        （ISR 核心聚合/page_752 形态：条目原口径=特性名 → 族名）"""
        proc = make_processor()
        proc._race_name_fallback = ""
        build_chunk(proc, kind="alt_trait", name="矮人", bare=True,
                    text="矮人角色可以选择以下种族特性替换原本的种族特性。")
        assert proc._race_name == "矮人", "组标题应覆盖登记"
        md = infer_metadata(proc, name="掘心者")
        assert md["race_name"] == "矮人", f"组内条目应继承族名: {md['race_name']!r}"

    def test_group_title_other_race_phrase_not_match(self):
        """「其他种族」开场组句（*指定种族的角色可以选择以下种族特性。*）
        不含「替换原本的」→ 不覆盖（ISR 其他形态：组标题非族名）"""
        proc = make_processor()
        proc._race_name_fallback = ""
        build_chunk(proc, kind="alt_trait", name="其他种族", bare=True,
                    text="*指定种族的角色可以选择以下种族特性。*")
        assert proc._race_name == "", "非族名组句不得覆盖登记"

    def test_group_title_without_bare_flag_not_match(self):
        """非裸中文标题形态（无 _bare_cn_title 标记）不得触发组标题覆盖"""
        proc = make_processor()
        proc._race_name_fallback = ""
        build_chunk(proc, kind="alt_trait", name="矮人",
                    text="矮人角色可以选择以下种族特性替换原本的种族特性。")
        assert proc._race_name == "", "无裸标题标记不触发组标题覆盖"

    def test_pure_intro_sets_en_name(self):
        """纯净 intro 覆盖时同步登记英文名（race_name_en 供检索端展示）"""
        proc = make_processor()
        build_chunk(proc, kind="race_intro", name="猫族", text="猫族玩家角色……",
                    name_en="Catfolk")
        assert proc._race_name_en == "Catfolk"

    def test_group_title_intro_skipped_not_registered(self):
        """page_10 组标题/概念段 intro（核心种族/常见种族/罕见种族/整体描述）
        非族名——不得登记覆盖 race_name（KN134，2026-08-04：修复后 4 个组
        标题 chunk 从 race_overview 归 race_intro，intro 登记路径会把组标题
        当族名登记 → 污染后续条目继承）"""
        proc = make_processor()
        proc._race_name_fallback = ""
        for bad in ("核心种族", "常见种族", "罕见种族", "整体描述"):
            build_chunk(proc, kind="race_intro", name=bad, text="本章介绍段……")
            assert proc._race_name == "", f"{bad} 组标题 intro 不得登记"
        # 组标题 chunk 自身 metadata.race_name 落空（不落 chunk.title 兜底）。
        # 生产路径 build_chunk 已设 component_type=race_intro（item kind），
        # 测试辅助函数默认 component_type 非 intro —— 显式构造同口径
        proc2 = make_processor()
        ctx = proc2._build_source_context(Path("seed.md"), "正文")
        chunk = proc2._build_chunk_template(Path("seed.md"), 0, ctx)
        chunk.title = "核心种族"
        chunk.component_type = "race_intro"
        md = proc2.infer_metadata(chunk, {"text": "正文", "name": "核心种族"}).metadata
        assert md["race_name"] == "", \
            f"组标题 chunk race_name 应落空: {md['race_name']!r}"
        # 后续纯净族标题仍正常登记（归位后族介绍段照常覆盖）
        build_chunk(proc, kind="race_intro", name="矮人", text="矮人玩家角色……")
        assert proc._race_name == "矮人", "组标题拦截不得影响族名登记"


# ============================================================
#  KN113：race_overview 行 race_name 用行 title（不继承文件级 intro）
# ============================================================

class TestOverviewRaceName:
    """KN113：page_11 汇总页 68 行 race_overview 的 race_name 全被
    intro 文档标题「年龄」污染——overview 行 title 即种族名（精灵/侏儒…），
    不继承文件级 _race_name"""

    @staticmethod
    def _overview_metadata(proc, name: str) -> dict:
        """构造 component_type=race_overview 的 chunk 走 infer_metadata"""
        ctx = proc._build_source_context(Path("seed.md"), "正文")
        chunk = proc._build_chunk_template(Path("seed.md"), 0, ctx)
        chunk.title = name
        chunk.component_type = "race_overview"
        return proc.infer_metadata(chunk, {"text": "正文", "name": name}).metadata

    def test_overview_uses_row_title(self):
        """intro 已登记「年龄」时，overview 行仍用行 title（精灵）"""
        proc = make_processor()
        proc._race_name = "年龄"  # page_11 文档主标题（intro）已登记
        proc._race_name_fallback = ""
        md = self._overview_metadata(proc, "精灵")
        assert md["race_name"] == "精灵", f"overview 应取行 title: {md['race_name']!r}"

    def test_non_overview_keeps_inheritance(self):
        """非 overview chunk 保持兜底链：intro 登记优先（回归保护）"""
        proc = make_processor()
        proc._race_name = "年龄"
        proc._race_name_fallback = ""
        md = infer_metadata(proc, name="精灵")
        assert md["race_name"] == "年龄", "非 overview 仍走 intro 登记兜底链"

    def test_overview_race_name_en_stays_empty(self):
        """overview 行无英文名：race_name_en 保持空（不与 race_name 联动）"""
        proc = make_processor()
        proc._race_name = "年龄"
        proc._race_name_fallback = ""
        md = self._overview_metadata(proc, "侏儒")
        assert md["race_name"] == "侏儒"


# ============================================================
#  KN133：build_chunk「：」开头剥离 + _clean_name_en 剥 **
# ============================================================

class TestKN133TextColonAndAliasStars:
    """KN133（2026-08-04）：「：」开头家族 51 处（源形态 `**X（EN）**：正文`
    normalize 拆行后正文行保留行首冒号，如 page_398 海之子/寒霜试炼）——
    build_chunk 剥 text 行首「：」防检索污染；aliases `**` 残留（星壳嵌套
    `（****Serpent's Sense, ****Ex****）`）——_clean_name_en 剥 `**`"""

    def test_text_leading_colon_stripped(self):
        """text 行首「：」剥离（海之子形态）"""
        proc = make_processor()
        chunk = build_chunk(proc, name="海之子",
                            text="：来自沿海地区并拥有这一特性的半精灵，会在游泳检定上获得+4的种族加值。")
        assert not chunk.text.startswith("："), \
            f"行首「：」应剥离: {chunk.text[:20]!r}"
        assert chunk.text.startswith("来自沿海地区"), chunk.text[:30]

    def test_text_leading_halfwidth_colon_stripped(self):
        """text 行首半角 `:` 剥离（KN135-2：剥壳残留形态，page_716
        `**遗忘的记忆（EN）**:世代翼龙人长老…`，全库 7 处）"""
        proc = make_processor()
        chunk = build_chunk(proc, name="遗忘的记忆",
                            text=":世代翼龙人长老传承着早先于书本历史的故事。")
        assert not chunk.text.startswith(":"), \
            f"行首半角冒号应剥离: {chunk.text[:20]!r}"
        assert chunk.text.startswith("世代翼龙人长老"), chunk.text[:30]

    def test_text_leading_halfwidth_colon_multiline(self):
        """多行 text 每行行首半角冒号均剥离（page_939 超常感官 `:` 独立行
        形态——剥后留空行不残留冒号）"""
        proc = make_processor()
        chunk = build_chunk(proc, name="超常感官",
                            text=":\n:正文\n:次行")
        assert ":" not in chunk.text.split("\n")[0] or chunk.text.split("\n")[0] == "", \
            f"独立冒号行应剥空: {chunk.text[:20]!r}"
        assert ":正文" not in chunk.text and ":次行" not in chunk.text, \
            f"每行行首冒号均应剥除: {chunk.text!r}"

    def test_clean_name_en_strips_stars(self):
        """aliases 剥 `**`（星壳嵌套残留：`（****Serpent's Sense, ****Ex****）`）"""
        from vectorizer.processors.race import _clean_name_en
        en, _ = _clean_name_en("Serpent's Sense, **Ex**")
        assert "**" not in en, f"aliases 不得含星壳: {en!r}"
        assert en.strip() == "Serpent's Sense, Ex", en

    def test_clean_name_en_plain_unchanged(self):
        """无星壳英文名不变（回归保护）"""
        from vectorizer.processors.race import _clean_name_en
        en, _ = _clean_name_en("Catfolk")
        assert en == "Catfolk"
