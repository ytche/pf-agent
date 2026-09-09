"""
test_feat_processor.py — 专长 Processor 元数据 TDD 测试

测试目标（对齐 test_spell_metadata_v0_3.py 风格）：
  - parse_fields() 从统一 IR 文本提取专长字段原始值（双格式 + 边界防吞值）
  - _parse_prerequisites() 结构化解析（设计 §三：只做形态识别，不做语义理解）
  - infer_metadata() 输出 14 键 metadata + field_status 三态
  - field_status 计算正确（字段族 not_applicable 判定）
  - 幂等性：重复调用不改变结果
  - _feat_file_condition 文件分派正确
"""

from pathlib import Path

from vectorizer.formats.feat import FeatFormat
from vectorizer.processors.feat import (
    FeatProcessor,
    _feat_file_condition,
    _parse_prerequisites,
    parse_fields,
)


def make_processor() -> FeatProcessor:
    """空 provider 链的 FeatProcessor（来源书解析不在本文件覆盖范围）"""
    from vectorizer.sources.providers import SourceResolver
    return FeatProcessor(source_resolver=SourceResolver([]))


def run_item(item: dict) -> dict:
    """infer_metadata 便捷入口：Chunk 模板由 _build_chunk_template 生成"""
    proc = make_processor()
    chunk = proc._build_chunk_template(Path("seed.md"), 0, proc._build_source_context(Path("seed.md"), ""))
    return proc.infer_metadata(chunk, item).metadata


# ============================================================
#  parse_fields
# ============================================================


class TestParseFields:
    """字段原始值提取（双格式 + 边界）"""

    def test_standard_format(self):
        result = parse_fields("**先决条件：** 智力 13\n")
        assert result == {"prerequisites": "智力 13"}

    def test_bold_close_before_colon_format(self):
        result = parse_fields("**先决条件**：智力 13\n")
        assert result == {"prerequisites": "智力 13"}

    def test_effect_label_maps_to_benefit(self):
        """'效果'是 benefit 别名（设计 §2.2：效果 395 次）"""
        result = parse_fields("**效果：** 你获得 +2 检定\n")
        assert result == {"benefit": "你获得 +2 检定"}

    def test_long_label_preferred(self):
        """长标签优先：'专长效果' 匹配 benefit，不因 '效果' 子串歧义"""
        result = parse_fields("**专长效果：** 你获得 +2\n")
        assert result == {"benefit": "你获得 +2"}

    def test_blank_line_is_hard_boundary(self):
        result = parse_fields("**先决条件：** 智力 13\n\n后续正文段落\n")
        assert result == {"prerequisites": "智力 13"}

    def test_extra_label_boundary_no_capture(self):
        """extra 标签（推荐背景）作值边界但不产生字段（KN013 M5 同款）"""
        result = parse_fields("**先决条件：** 智力 13\n**推荐背景：** 商人\n")
        assert result == {"prerequisites": "智力 13"}
        assert "推荐背景" not in result

    def test_prereq_not_swallowed_by_effect(self):
        """关键防吞值：先决条件值不得被相邻 **效果：** 吞入"""
        text = "**先决条件**：坚忍\n**效果：** 你在饮酒后获得士气加值\n"
        result = parse_fields(text)
        assert result == {"prerequisites": "坚忍", "benefit": "你在饮酒后获得士气加值"}

    def test_fullwidth_space_normalization(self):
        result = parse_fields("**先决条件：** 智力　13\n")
        assert result == {"prerequisites": "智力 13"}

    def test_strip_trailing_asterisks(self):
        result = parse_fields("**先决条件：** 坚忍 **\n")
        assert result == {"prerequisites": "坚忍"}

    def test_empty_text(self):
        assert parse_fields("") == {}


class TestParseFieldsSource:
    """出处行提取：值锚定行尾（不跨行吃后续正文行）——造物专长一览 KN030 ③ 前置。

    全库 16 处出处行后均紧跟正文行（造物专长一览/平衡勇士/闹鬼英雄手册/
    位面冒险/间谍大师手册），旧路径 value 跨行把正文吞进 source。
    """

    def test_source_value_line_anchored(self):
        """**出自**：值后跟正文行 → 值止于行尾，不吃正文"""
        text = "**出自**：Pathfinder #16: Endless Night pg. 63\n*除了被列出的数种塑肉手术外*"
        result = parse_fields(text)
        assert result["source"] == "Pathfinder #16: Endless Night pg. 63"

    def test_source_quad_star_form(self):
        """****出自**： 4 星开头形态（造物专长一览 54 行型）"""
        result = parse_fields("****出自**：Horror Adventures pg. 87\n你可以通过一个可憎的炼金术工序创造生命。")
        assert result["source"] == "Horror Adventures pg. 87"

    def test_source_lai_zi_label(self):
        """**来自**： 标签（恶魔移植物 293 行型，'来自' 与 '出自' 同义出处标签）"""
        result = parse_fields("****来自**：Pathfinder #74: Sword of Valor pg. 73\n你对恶魔的解剖学…")
        assert result["source"] == "Pathfinder #74: Sword of Valor pg. 73"

    def test_source_bare_source_form(self):
        """**Source 值（无冒号无闭合星，342 行型）"""
        result = parse_fields("**Source Monster Hunter's Handbook pg. 24\n你用敌人留下的纪念品…")
        assert result["source"] == "Monster Hunter's Handbook pg. 24"

    def test_source_standard_label_unchanged(self):
        """**来源：** 标准形态照常提取"""
        result = parse_fields("**来源：**Champions of Purity pg. 20\n**先决条件**：魅力 13")
        assert result["source"] == "Champions of Purity pg. 20"

    def test_source_strip_trailing_punct(self):
        """值尾标点剥除（对齐既有 value 处理）"""
        result = parse_fields("**出自**：Haunted Heroes Handbook pg. 30\n")
        assert result["source"] == "Haunted Heroes Handbook pg. 30"

    def test_mission_fields(self):
        result = parse_fields("**专长目标：** 救出商人\n**即时收益：** 500 gp\n")
        assert result == {"task_goal": "救出商人", "task_reward": "500 gp"}

    def test_normal_dialect_putong(self):
        """P0a page_820：合作规避的「普通：」是通常状况方言"""
        result = parse_fields("**普通：** 你必须和你的盟友分处敌人的两边\n")
        assert result == {"normal": "你必须和你的盟友分处敌人的两边"}

    def test_task_reward_dialect_wanchenghoude(self):
        """P0a page_820：龙触者「完成后的收益：」是完成收益方言"""
        result = parse_fields("**完成后的收益：** 扩大收益到另一种龙\n")
        assert result == {"task_reward": "扩大收益到另一种龙"}

    def test_normal_dialect_yibanqingkuang(self):
        """P0a 专长58：水下侍从「一般情况：」是通常状况方言"""
        result = parse_fields("**一般情况：** 召唤自然盟友 II 的默认持续时间为1轮/等级\n")
        assert result == {"normal": "召唤自然盟友 II 的默认持续时间为1轮/等级"}

    def test_craft_fields(self):
        result = parse_fields("**制造成本：** 1000 gp\n**制造条件：** 匠人 5 级\n")
        assert result == {"craft_cost": "1000 gp", "craft_conditions": "匠人 5 级"}


# ============================================================
#  _parse_prerequisites 结构化（设计 §三）
# ============================================================


class TestParsePrerequisites:
    """prerequisites 形态识别：ability/skill/class_level/bab/spell/feat/race/other"""

    def test_ability_and_spell(self):
        """设计示例：智力 13，能够施放异能宣战"""
        result = _parse_prerequisites("智力 13，能够施放异能宣战（Instigate Psychic Duel）")
        assert result["raw"] == "智力 13，能够施放异能宣战（Instigate Psychic Duel）"
        assert result["items"] == [
            {"type": "ability", "ability": "智力", "value": 13},
            {"type": "spell", "value": "能够施放异能宣战（Instigate Psychic Duel）"},
        ]

    def test_class_level_and_feat(self):
        """设计示例：催眠师5级，痛苦注视（Painful Stare）职业能力"""
        result = _parse_prerequisites("催眠师5级，痛苦注视（Painful Stare）职业能力")
        assert result["items"][0] == {"type": "class_level", "class": "催眠师", "level": 5}
        assert result["items"][1] == {"type": "feat", "value": "痛苦注视（Painful Stare）职业能力"}

    def test_bab_with_or_branch(self):
        """设计示例：BAB+6或武僧等级6 → or 分支挂 bab item"""
        result = _parse_prerequisites("BAB+6或武僧等级6")
        assert result["items"] == [{"type": "bab", "value": 6, "or": "武僧等级6"}]

    def test_skill_levels(self):
        """设计示例：唬骗3级，潜行3级"""
        result = _parse_prerequisites("唬骗3级，潜行3级")
        assert result["items"] == [
            {"type": "skill", "skill": "唬骗", "level": 3},
            {"type": "skill", "skill": "潜行", "level": 3},
        ]

    def test_race_bab_other_mix(self):
        """设计示例：迅捷狐妖变身者，基础攻击加值+10，狐妖"""
        result = _parse_prerequisites("迅捷狐妖变身者，基础攻击加值+10，狐妖")
        assert len(result["items"]) == 3
        assert result["items"][0]["type"] == "race"          # 含'变身者'形态
        assert result["items"][1] == {"type": "bab", "value": 10}
        # 第三段纯中文：形态不可分（feat/race 语义），保留归类不炸即可
        assert result["items"][2]["type"] in ("feat", "other")

    def test_bare_feat_name(self):
        """设计示例：寓守于攻（纯中文专长名 → feat）"""
        result = _parse_prerequisites("寓守于攻")
        assert result["items"][0]["type"] == "feat"
        assert result["items"][0]["value"] == "寓守于攻"

    def test_bare_level_no_class(self):
        """无职业名的 '5级'：形态不完整 → other"""
        result = _parse_prerequisites("5级")
        assert result["items"][0] == {"type": "other", "value": "5级"}

    def test_empty_raw(self):
        assert _parse_prerequisites("") == {"raw": "", "items": []}


# ============================================================
#  infer_metadata
# ============================================================


class TestInferMetadata:
    """14 键 metadata + field_status 三态"""

    def test_full_entry(self):
        metadata = run_item({
            "name": "突袭警惕",
            "name_en": "Ambush Awareness",
            "feat_type": ["战斗"],
            "format_cluster": "standard",
            "pfs_eligible": True,
            "text": "**先决条件：** 警觉\n**专长效果：** 你获得 +2 先攻检定\n",
        })
        assert set(metadata) == {
            "feat_type", "prerequisites", "benefit", "normal", "special", "source",
            "task_goal", "task_reward", "advanced_reward",
            "craft_cost", "craft_conditions", "craft_aura",
            "format_cluster", "pfs_eligible", "field_status",
        }
        assert metadata["feat_type"] == ["战斗"]
        assert metadata["prerequisites"]["raw"] == "警觉"
        assert metadata["prerequisites"]["items"][0]["type"] == "feat"
        assert metadata["benefit"] == "你获得 +2 先攻检定"
        assert metadata["format_cluster"] == "standard"
        assert metadata["pfs_eligible"] is True

    def test_mission_feat_field_status(self):
        """任务链专长：task_* parsed，craft_* not_applicable"""
        metadata = run_item({
            "name": "困于城中",
            "feat_type": ["故事"],
            "format_cluster": "elided",
            "pfs_eligible": False,
            "text": "**专长目标：** 逃出城邦\n**即时收益：** 你获得情报网\n",
        })
        fs = metadata["field_status"]
        assert fs["task_goal"] == "parsed"
        assert fs["task_reward"] == "parsed"
        assert fs["advanced_reward"] == "not_applicable"
        assert fs["craft_cost"] == "not_applicable"
        assert fs["craft_conditions"] == "not_applicable"
        assert fs["craft_aura"] == "not_applicable"
        assert fs["benefit"] == "missing"

    def test_normal_feat_craft_not_applicable(self):
        """普通专长：任务链/造物六字段全 not_applicable"""
        metadata = run_item({
            "name": "碎物者",
            "feat_type": ["战斗"],
            "format_cluster": "standard",
            "pfs_eligible": False,
            "text": "**专长效果：** 你用椅子造成伤害\n",
        })
        fs = metadata["field_status"]
        for f in ("task_goal", "task_reward", "advanced_reward",
                  "craft_cost", "craft_conditions", "craft_aura"):
            assert fs[f] == "not_applicable", f"{f} 应 not_applicable"
        assert fs["benefit"] == "parsed"
        assert fs["prerequisites"] == "missing"
        assert fs["normal"] == "missing"
        assert fs["special"] == "missing"
        assert fs["source"] == "missing"

    def test_prerequisites_missing_when_absent(self):
        metadata = run_item({
            "name": "碎物者",
            "format_cluster": "standard",
            "pfs_eligible": False,
            "text": "**专长效果：** xxx\n",
        })
        assert metadata["prerequisites"] is None
        assert metadata["field_status"]["prerequisites"] == "missing"

    def test_pfs_true_parsed_false_missing(self):
        fs_true = run_item({
            "name": "A", "format_cluster": "standard", "pfs_eligible": True,
            "text": "**专长效果：** xxx\n",
        })["field_status"]
        fs_false = run_item({
            "name": "A", "format_cluster": "standard", "pfs_eligible": False,
            "text": "**专长效果：** xxx\n",
        })["field_status"]
        assert fs_true["pfs_eligible"] == "parsed"
        assert fs_false["pfs_eligible"] == "missing"

    def test_format_cluster_always_parsed(self):
        metadata = run_item({"name": "A", "format_cluster": "elided", "pfs_eligible": False, "text": "x\n"})
        assert metadata["field_status"]["format_cluster"] == "parsed"

    def test_source_from_index_line(self):
        """索引行【来源缩写】→ metadata.source（正文无'来源'标签时）"""
        metadata = run_item({
            "name": "抵异作成",
            "source": "PotW",
            "format_cluster": "lb_marker",
            "pfs_eligible": False,
            "text": "**先决条件：** 施法能力\n",
        })
        assert metadata["source"] == "PotW"

    def test_source_from_text_label(self):
        """正文'来源'标签优先于索引缩写"""
        metadata = run_item({
            "name": "A",
            "source": "PotW",
            "format_cluster": "lb_marker",
            "pfs_eligible": False,
            "text": "**来源：** 冒险家军械库\n",
        })
        assert metadata["source"] == "冒险家军械库"

    def test_feat_type_fallback_from_text(self):
        """item 无 feat_type 时回退到正文'类型'标签"""
        metadata = run_item({
            "name": "A", "format_cluster": "standard", "pfs_eligible": False,
            "text": "**类型：** 战斗\n",
        })
        assert metadata["feat_type"] == ["战斗"]

    def test_idempotent(self):
        proc = make_processor()
        chunk = proc._build_chunk_template(Path("seed.md"), 0, proc._build_source_context(Path("seed.md"), ""))
        item = {
            "name": "突袭警惕", "name_en": "Ambush Awareness", "feat_type": ["战斗"],
            "format_cluster": "standard", "pfs_eligible": True,
            "text": "**先决条件：** 警觉\n**专长效果：** 你获得 +2\n",
        }
        proc.infer_metadata(chunk, item)
        first = dict(chunk.metadata)
        proc.infer_metadata(chunk, item)
        assert chunk.metadata == first


# ============================================================
#  build_chunk / _feat_file_condition
# ============================================================


class TestBuildChunk:
    def test_title_text_aliases(self):
        proc = make_processor()
        chunk = proc._build_chunk_template(Path("seed.md"), 0, proc._build_source_context(Path("seed.md"), ""))
        result = proc.build_chunk(chunk, {"name": "突袭警惕", "name_en": "Ambush Awareness", "text": "正文"})
        assert result.title == "突袭警惕"
        assert result.text == "正文"
        assert result.aliases == ["Ambush Awareness"]

    def test_no_name_en(self):
        proc = make_processor()
        chunk = proc._build_chunk_template(Path("seed.md"), 0, proc._build_source_context(Path("seed.md"), ""))
        result = proc.build_chunk(chunk, {"name": "困于城中", "text": "正文"})
        assert result.aliases == []

    def test_table_align_spaces_normalized(self):
        """表格行列对齐空格（HTML &nbsp; 序列转换产物）→ title/aliases 压缩为单空格。
        全库 371 aliases + 152 title 含 2+ 连续空格（page_195 等 30 文件表格行英文名），
        检索端精确匹配会 miss，字段归一化在 build_chunk 收口。"""
        proc = make_processor()
        chunk = proc._build_chunk_template(Path("seed.md"), 0, proc._build_source_context(Path("seed.md"), ""))
        result = proc.build_chunk(chunk, {
            "name": "Aldori         Dueling Disciple",
            "name_en": "Agile         Maneuvers",
            "text": "正文",
        })
        assert result.title == "Aldori Dueling Disciple"
        assert result.aliases == ["Agile Maneuvers"]

    def test_lb_marker_component_type_feat_index(self):
        """R6：lb_marker 表格索引行 → component_type=feat_index（设计 §五）"""
        proc = make_processor()
        chunk = proc._build_chunk_template(Path("seed.md"), 0, proc._build_source_context(Path("seed.md"), ""))
        result = proc.build_chunk(chunk, {"name": "酿造大师", "format_cluster": "lb_marker", "text": "| … |"})
        assert result.component_type == "feat_index"

    def test_standard_component_type_keeps_feat(self):
        """R6：正文条目（standard 等）保持 component_type=feat"""
        proc = make_processor()
        chunk = proc._build_chunk_template(Path("seed.md"), 0, proc._build_source_context(Path("seed.md"), ""))
        result = proc.build_chunk(chunk, {"name": "突袭警惕", "format_cluster": "standard", "text": "正文"})
        assert result.component_type == "feat"

    def test_intro_marker_component_type_feat_intro(self):
        """KN094：intro 标记 → component_type=feat_intro（章首/类别介绍段）"""
        proc = make_processor()
        chunk = proc._build_chunk_template(Path("seed.md"), 0, proc._build_source_context(Path("seed.md"), ""))
        result = proc.build_chunk(chunk, {"name": "团队专长", "intro": True, "text": "介绍散文。"})
        assert result.component_type == "feat_intro"

    def test_lb_marker_priority_over_intro(self):
        """KN094：lb_marker 优先于 intro（feat_index 优先，KN085 28 个空 text 不误伤）"""
        proc = make_processor()
        chunk = proc._build_chunk_template(Path("seed.md"), 0, proc._build_source_context(Path("seed.md"), ""))
        result = proc.build_chunk(chunk, {"name": "酿造大师", "format_cluster": "lb_marker", "intro": True, "text": ""})
        assert result.component_type == "feat_index"


class TestResolveSource:
    """来源书解析：标准链失败时走专长注释缩写兜底（config/feat_sources.json）"""

    @staticmethod
    def _resolve(processor, file_path: Path, content: str, item: dict = None):
        proc = processor
        ctx = proc._build_source_context(file_path, content)
        chunk = proc._build_chunk_template(file_path, 0, ctx)
        return proc.resolve_source(chunk, ctx, item or {})

    def test_comment_abbr_fallback(self):
        """标准链 '?' 时：<!-- UW-source: ... --> → 极限荒野（Ultimate Wilderness）"""
        proc = make_processor()
        chunk = self._resolve(
            proc,
            Path("pf_rules_md_organized/专长/极限荒野UW_专长.md"),
            "# 极限荒野（Ultimate Wilderness）专长\n<!-- UW-source:专长11.md:突袭警惕 -->\n",
        )
        assert chunk.book_abbreviation == "UW"
        assert chunk.book_name_cn == "极限荒野"
        assert chunk.book_name_en == "Ultimate Wilderness"
        assert chunk.source_confidence > 0

    def test_comment_abbr_case_variant(self):
        """大小写变体（BOTD → BotD 规范缩写）"""
        proc = make_processor()
        chunk = self._resolve(
            proc,
            Path("pf_rules_md_organized/专长/永罪之书_专长.md"),
            "# 永罪之书 专长\n<!-- BOTD-source:xxx.md -->\n",
        )
        assert chunk.book_abbreviation == "BotD"

    def test_source_line_extraction(self):
        """引用块提取：> 来源：中文（English）→ 缩写 → 全通道（中文注释文件的主通道）"""
        proc = make_processor()
        chunk = self._resolve(
            proc,
            Path("pf_rules_md_organized/专长/格拉里昂的秽邪勇士_专长.md"),
            "# 格拉里昂的秽邪勇士 专长\n<!-- 秽邪勇士-source:专长.md -->\n"
            "> 来源：秽邪勇士（Champions of Corruption），页码见原书，未整理 → 秽邪勇士 → 专长\n",
        )
        assert chunk.book_abbreviation == "秽邪勇士"
        assert chunk.book_name_cn == "秽邪勇士"
        assert chunk.book_name_en == "Champions of Corruption"
        assert chunk.source_confidence > 0

    def test_source_line_abbr_tail_ascii(self):
        """引用块箭头段中文+缩写粘连 → 取尾部 ASCII 缩写（异能选集PA → PA）"""
        proc = make_processor()
        chunk = self._resolve(
            proc,
            Path("pf_rules_md_organized/专长/异能选集PA_专长.md"),
            "# 异能选集 PA 专长\n<!-- 异能选集PA-source:xxx.md -->\n"
            "> 来源：异能选集（Psychic Anthology），页码见原书，未整理 → 异能选集PA → 专长\n",
        )
        assert chunk.book_abbreviation == "PA"
        assert chunk.book_name_cn == "异能选集"
        assert chunk.book_name_en == "Psychic Anthology"

    def test_source_line_no_abbr_uses_cn(self):
        """引用块无缩写（任务与战役）→ 中文书名作缩写"""
        proc = make_processor()
        chunk = self._resolve(
            proc,
            Path("pf_rules_md_organized/专长/任务与战役_专长.md"),
            "# 任务与战役 专长\n<!-- 任务与战役-source:xxx.md -->\n"
            "> 来源：任务与战役（Quests and Campaigns），页码见原书，未整理 → 任务与战役 → 专长\n",
        )
        assert chunk.book_abbreviation == "任务与战役"
        assert chunk.book_name_en == "Quests and Campaigns"

    def test_unknown_abbr_stays_unknown(self):
        """注释缩写不在补充表 → 保持 '?'（不编造来源）"""
        proc = make_processor()
        chunk = self._resolve(
            proc,
            Path("pf_rules_md_organized/专长/xxx.md"),
            "# 未知书 专长\n<!-- XYZ-source:xxx.md -->\n",
        )
        assert chunk.book_abbreviation == "?"

    def test_no_comment_stays_unknown(self):
        proc = make_processor()
        chunk = self._resolve(
            proc,
            Path("pf_rules_md_organized/专长/page_999.md"),
            "# 某页专长\n",
        )
        assert chunk.book_abbreviation == "?"

    def test_standard_chain_wins(self):
        """标准链已命中（文件名 CRB）→ 不走兜底"""
        from vectorizer.sources.providers import ALL_PROVIDERS, SourceResolver
        proc = FeatProcessor(source_resolver=SourceResolver(ALL_PROVIDERS))
        chunk = self._resolve(
            proc,
            Path("pf_rules_md_organized/专长/核心规则书CRB_专长.md"),
            "<!-- CRB-source:xxx.md -->\n",
        )
        assert chunk.book_abbreviation == "CRB"


class TestFeatFileCondition:
    """R1 输入范围：condition = 判别器矩阵 rel 查表（根目录 66 + 专长/ 123 = 189）"""

    def test_positive_organized_subdir(self):
        """专长/ 子目录文件（矩阵 123 内）→ 产"""
        assert _feat_file_condition(Path("pf_rules_md_organized/专长/page_311.md")) is True

    def test_positive_root_dir_numbered_file(self):
        """根目录 专长11.md（矩阵 66 内）→ 产"""
        assert _feat_file_condition(Path("pf_rules_md_organized/专长11.md")) is True

    def test_positive_root_dir_basename_file(self):
        """根目录 造物专长一览.md（矩阵 66 内）→ 产"""
        assert _feat_file_condition(Path("pf_rules_md_organized/造物专长一览.md")) is True

    def test_negative_spell_path(self):
        """法术目录（矩阵外）→ 不产"""
        assert _feat_file_condition(Path("pf_rules_md_organized/法术/abjuration.md")) is False

    def test_negative_unorganized(self):
        """未整理批（矩阵外，来源标记'未整理'）→ 不产"""
        assert _feat_file_condition(
            Path("pf_rules_md_organized/未整理/永罪之书BotD/专长38.md")
        ) is False

    def test_negative_role_options(self):
        """角色选项归置（矩阵外）→ 不产"""
        assert _feat_file_condition(Path("pf_rules_md_organized/角色/专长/Niobe_专长.md")) is False

    def test_negative_duplicate_page(self):
        """矩阵外重复副本 page_202（根与专长/ 各一）→ 不产"""
        assert _feat_file_condition(Path("pf_rules_md_organized/专长/page_202.md")) is False

    def test_negative_fake_path(self):
        """fake 绝对路径（不 resolve 到 organized 根下）→ 不产"""
        assert _feat_file_condition(Path("/x/Feats.md")) is False


class TestDedupDuplicateStem:
    """R1 同书多份取主版本：矩阵含同 stem 双 rel（造物专长一览 根目录旧副本
    + 专长/ 规范化主版本，est/got 相同 28/46），pipeline 按 doc_id=stem 各产
    一份会撞 chunk_id —— process 层跳过后到副本（sorted 遍历子目录版在前）"""

    def _process(self, proc, path: Path, text: str):
        """临时文件模拟 pipeline 单文件处理；同实例跨文件调用共享 _seen_stems"""
        path.write_text(text, encoding="utf-8")
        return proc.process(path)

    def test_duplicate_stem_second_skipped(self, tmp_path):
        """同 stem 两文件先后 process → 后者被跳过，chunk_id 无撞车"""
        proc = make_processor()
        content = (
            "**测试专长（Test Feat）**\n"
            "**先决条件：** 角色等级1。\n"
            "**专长效果：** 测试效果。\n"
        )
        # 子目录版（sorted 先遍历）为主版本
        main = tmp_path / "sub" / "造物专长一览.md"
        main.parent.mkdir(parents=True)
        dup = tmp_path / "造物专长一览.md"
        first = self._process(proc, main, content)
        second = self._process(proc, dup, content)
        assert len(first) > 0, "主版本应产出 chunk"
        assert second == [], "后到同 stem 副本应被跳过"
        ids = [c.chunk_id for c in first]
        assert len(ids) == len(set(ids))

    def test_different_stems_untouched(self, tmp_path):
        """不同 stem 文件互不影响"""
        proc = make_processor()
        content = "**测试专长（Test Feat）**\n**先决条件：** 角色等级1。\n**专长效果：** 测试。\n"
        a = tmp_path / "page_203.md"
        b = tmp_path / "专长11.md"
        ca = self._process(proc, a, content)
        cb = self._process(proc, b, content)
        assert len(ca) > 0 and len(cb) > 0
