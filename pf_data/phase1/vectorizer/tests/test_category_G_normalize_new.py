"""
G 类：新增格式变体与去噪规则测试

覆盖 Prepare Phase 发现的 13 格式簇中未覆盖的部分：
  - 【学派】格式族（Clusters 5-7）
  - OA/UI 超紧凑内联格式（Cluster 4a）
  - 去噪规则：◎ / ![[图片]] / ~~ / [种族] / 整理者：
  - 分组标题过滤
  - 无加粗字段（F2 格式）
"""

import pytest
from vectorizer.formats.spell import SpellFormat


class TestSchoolBracketFormat:
    """【学派】标题格式归一化"""

    def test_school_bracket_conversion(self, spell_format: SpellFormat, sample_school_bracket_text: str):
        """【咒法系】→ **中文 (English)** 转换"""
        normalized = spell_format.normalize(sample_school_bracket_text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "强酸箭" in names, f"未找到强酸箭，找到: {names}"
        assert "高等蛇龙术" in names, f"未找到高等蛇龙术，找到: {names}"

    def test_school_bracket_with_subschool(self, spell_format: SpellFormat):
        """含子学派的 【学派】(子学派) 格式"""
        text = "【咒法系】(创造)强酸箭(Acid Arrow)[酸]\n**等级：** 魔战士 2\n"
        normalized = spell_format.normalize(text)
        assert "**强酸箭 (Acid Arrow)**" in normalized, f"转换失败: {normalized}"

    def test_school_bracket_no_subschool(self, spell_format: SpellFormat):
        """无子学派 【学派】 格式"""
        text = "【变化系】高等蛇龙术(Form of the Dragon III)[龙类]\n**等级：** 术士/法师 7\n"
        normalized = spell_format.normalize(text)
        assert "**高等蛇龙术 (Form of the Dragon III)**" in normalized, f"转换失败: {normalized}"

    def test_school_bracket_no_descriptor(self, spell_format: SpellFormat):
        """无描述符的 【学派】 格式"""
        text = "【防护系】抵抗能量伤害(Resist Energy)\n**等级：** 牧师 2\n"
        normalized = spell_format.normalize(text)
        assert "**抵抗能量伤害 (Resist Energy)**" in normalized, f"转换失败: {normalized}"

    def test_school_bracket_not_a_title(self, spell_format: SpellFormat):
        """纯 【防护系】 单行不应被转换（无英文名）"""
        text = "【防护系】\n这是说明文字\n"
        normalized = spell_format.normalize(text)
        # 不应该产生 **中文 (English)** 格式
        assert "**(**" not in normalized, f"误转换了纯分组标题: {normalized}"


class TestInlineCompactFormat:
    """OA/UI 超紧凑内联格式展开"""

    def test_oa_inline_expanded(self, spell_format: SpellFormat, sample_oa_inline_text: str):
        """OA 内联格式展开后应能被正常分割"""
        normalized = spell_format.normalize(sample_oa_inline_text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "阿卡西构形" in names, f"未找到阿卡西构形，找到: {names}"
        assert "梦境旅行" in names, f"未找到梦境旅行，找到: {names}"

    def test_oa_inline_fields_separate_lines(self, spell_format: SpellFormat):
        """内联格式展开后字段应在单独行上"""
        text = "**阿卡西构形（Akashic Form）****学派**：变化系**等级**：术士/法师 6\n"
        normalized = spell_format.normalize(text)
        lines = normalized.split('\n')
        has_school_line = any("**学派" in line for line in lines)
        has_level_line = any("**等级" in line for line in lines)
        assert has_school_line, f"学派未独立成行: {normalized}"
        assert has_level_line, f"等级未独立成行: {normalized}"

    def test_oa_inline_strikethrough(self, spell_format: SpellFormat):
        """OA 格式中 ~~ 删除线应被剥离"""
        text = "~~**超态变化（Metamorphosis）**~~**学派**：变化系\n"
        normalized = spell_format.normalize(text)
        assert "~~" not in normalized, f"删除线未剥离: {normalized}"
        assert "**超态变化 (Metamorphosis)**" in normalized, f"标题不正确: {normalized}"


class TestNoiseNormalize:
    """去噪规则"""

    def test_translator_notes_stripped(self, spell_format: SpellFormat):
        """◎ 译者标记行被剥离"""
        text = "**强酸箭 (Acid Arrow)**\n◎ 译者注：此处原文有误\n"
        normalized = spell_format.normalize(text)
        assert "◎" not in normalized, f"译者标记未剥离: {normalized}"

    def test_image_markers_stripped(self, spell_format: SpellFormat):
        """![[图片]] 标记行被剥离"""
        text = "**强酸箭 (Acid Arrow)**\n![[image001.png]]\n![[spell_icon.jpg]]\n"
        normalized = spell_format.normalize(text)
        assert "![" not in normalized, f"图片标记未剥离: {normalized}"

    def test_metadata_lines_stripped(self, spell_format: SpellFormat):
        """整理者：元数据行被剥离"""
        text = "整理者：草野\n**强酸箭 (Acid Arrow)**\n"
        normalized = spell_format.normalize(text)
        assert "整理者" not in normalized, f"元数据行未剥离: {normalized}"

    def test_title_race_suffix_stripped(self, spell_format: SpellFormat):
        """ARG [种族] 后缀被剥离"""
        text = "**隆地术 (Groundswell) [矮人]**\n**学派：** 变化系\n"
        normalized = spell_format.normalize(text)
        assert "**隆地术 (Groundswell)**" in normalized, f"[矮人]未剥离: {normalized}"
        assert "[矮人]" not in normalized, f"[矮人]残留: {normalized}"

    def test_strikethrough_stripped(self, spell_format: SpellFormat):
        """~~ 删除线被剥离"""
        text = "~~**衰老抗性 (Age Resistance)**~~\n"
        normalized = spell_format.normalize(text)
        assert "~~" not in normalized, f"删除线未剥离: {normalized}"
        assert "**衰老抗性 (Age Resistance)**" in normalized, f"标题异常: {normalized}"

    def test_complex_noise_combined(self, spell_format: SpellFormat, sample_noise_text: str):
        """综合噪声场景：各种噪声同时存在"""
        normalized = spell_format.normalize(sample_noise_text)
        # 噪声被去除
        assert "◎" not in normalized, "译者标记残留"
        assert "![" not in normalized, "图片标记残留"
        assert "整理者" not in normalized, "整理者标记残留"
        assert "~~" not in normalized, "删除线残留"
        assert "[矮人]" not in normalized, "种族标签残留"
        # 标题仍正确
        assert "**强酸箭 (Acid Arrow)**" in normalized, "强酸箭标题丢失"
        assert "**隆地术 (Groundswell)**" in normalized, "隆地术标题异常"
        assert "**衰老抗性 (Age Resistance)**" in normalized, "衰老抗性标题异常"


class TestGroupHeaderFilter:
    """分组标题过滤"""

    def test_group_header_skipped(self, spell_format: SpellFormat, sample_group_header_text: str):
        """**伽瑟兰法术（GATHLAIN SPELLS）** 不被计入法术条目"""
        normalized = spell_format.normalize(sample_group_header_text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "强酸箭" in names, f"强酸箭未找到: {names}"
        assert "原初本能" in names, f"原初本能未找到: {names}"
        assert "伽瑟兰法术" not in names, f"分组标题被误识别: {names}"
        assert len(items) == 2, f"应有 2 个法术，实际 {len(items)}"

    def test_group_header_content_excluded(self, spell_format: SpellFormat):
        """分组标题后的说明文本不应混入前一条目的正文"""
        text = (
            "**强酸箭 (Acid Arrow)**\n"
            "**学派：** 咒法系\n"
            "**等级：** 魔战士 2\n"
            "\n"
            "**伽瑟兰法术（GATHLAIN SPELLS）**\n"
            "以下为伽瑟兰文明特有的法术。\n"
            "\n"
            "**原初本能 (Alpha Instinct)**\n"
            "**学派：** 变化系\n"
            "**等级：** 德鲁伊 7\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        for item in items:
            if item["name"] == "强酸箭":
                assert "伽瑟兰" not in item["text"], "分组内容混入强酸箭正文"
                assert "原初本能" not in item["text"], "后续条目混入强酸箭正文"

    def test_sea_spells_header_filtered(self, spell_format: SpellFormat):
        """**海洋法术（SPELLS OF THE SEA）** 应被过滤"""
        text = (
            "**海洋法术（SPELLS OF THE SEA）**\n"
            "以下为海洋相关法术。\n"
            "\n"
            "**溺底术 (Drown)**\n"
            "**学派：** 咒法系\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "海洋法术" not in names, f"分组标题误识别: {names}"
        assert "溺底术" in names, f"溺底术未找到: {names}"


class TestUnlabeledFieldFormat:
    """无加粗字段格式（F2）"""

    def test_unlabeled_field_conversion(self, spell_format: SpellFormat, sample_unlabeled_field_text: str):
        """等级：魔战士 2 → **等级：** 魔战士 2"""
        normalized = spell_format.normalize(sample_unlabeled_field_text)
        assert "**学派：**" in normalized, f"学派未加粗: {normalized}"
        assert "**等级：**" in normalized, f"等级未加粗: {normalized}"
        assert "**持续时间：**" in normalized, f"持续时间未加粗: {normalized}"

    def test_unlabeled_field_still_parses(self, spell_format: SpellFormat, sample_unlabeled_field_text: str):
        """无加粗字段转换后仍能被 split_into_items 正确解析"""
        normalized = spell_format.normalize(sample_unlabeled_field_text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "防生物力场" in names, f"未找到防生物力场，找到: {names}"


class TestIntroTextBeforeTitle:
    """介绍段落末尾无换行直接接 **中文 (English)** 标题"""

    def test_intro_text_flow_into_first_spell(self, spell_format: SpellFormat):
        """介绍段末尾无换行，**中文 (English)** 标题紧接其后"""
        text = (
            "**荒野魔法**自然是一种伟大的力量。"
            "**原初本能（ALPHA INSTINCT）****学派：**惑控系**等级：**吟游诗人3\n"
            "**描述：**你化为野兽。\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "原初本能" in names, f"未找到原初本能: {names}"
        assert len(items) == 1, f"应有 1 个法术，实际 {len(items)}"

    def test_intro_text_flow_after_strip_noise(self, spell_format: SpellFormat):
        """去噪（URL/译者/图片）后介绍段与标题合并的处理"""
        text = (
            "译者: 张三\n"
            "![[image.png]]\n"
            "http://example.com\n"
            "**荒野魔法**自然是一种伟大的力量。"
            "**原初本能（ALPHA INSTINCT）****学派：**惑控系\n"
            "**等级：**吟游诗人3\n"
            "**描述：**你化为野兽。\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "原初本能" in names, f"去噪后未找到原初本能: {names}"

    def test_multiple_spells_ultra_compact(self, spell_format: SpellFormat):
        """多个法术超紧凑拼接，标题间无空行（Cluster 9 典型）"""
        text = (
            "**原初本能（ALPHA INSTINCT）****学派：**惑控系**等级：**吟游诗人3"
            "**描述：**你化为野兽。"
            "**海中铁骑（AQUATIC CAVALRY）****学派：**咒法系**等级：**德鲁伊2"
            "**描述：**你召唤海马。\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "原初本能" in names, f"未找到原初本能: {names}"
        assert "海中铁骑" in names, f"未找到海中铁骑: {names}"
        assert len(items) == 2, f"应有 2 个法术，实际 {len(items)}"

    def test_inline_ref_not_false_positive(self, spell_format: SpellFormat):
        """描述中的 **中文 (English)** 引用不应被误分割"""
        text = (
            "**强酸箭（Acid Arrow）**\n"
            "**学派：**咒法系\n"
            "**描述：**你创造一支酸液箭，如同 **强酸箭（Acid Arrow）** 法术。\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "强酸箭" in names, f"未找到强酸箭: {names}"
        # 不应多出额外的条目
        assert len(items) == 1, f"描述中的引用不应产生新条目: {names}"

    def test_normalize_idempotent_with_intro(self, spell_format: SpellFormat):
        """含介绍段落的文本重复 normalize 应幂等"""
        text = (
            "**荒野魔法**自然是一种伟大的力量。"
            "**原初本能（ALPHA INSTINCT）****学派：**惑控系\n"
            "**等级：**吟游诗人3\n"
        )
        normalized = spell_format.normalize(text)
        normalized2 = spell_format.normalize(normalized)
        assert normalized == normalized2, "归一化不幂等"


class TestEdgeCases:
    """边界情况"""

    def test_multiple_blank_lines_preserved(self, spell_format: SpellFormat):
        """多个空行之间的法术仍被正确识别"""
        text = (
            "**强酸箭 (Acid Arrow)**\n"
            "**学派：** 咒法系\n"
            "\n\n\n"
            "**酸雾术 (Acid Fog)**\n"
            "**学派：** 咒法系\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        assert len(items) == 2, f"应有 2 个条目，实际 {len(items)}"

    def test_ap_resource_suffix_stripped(self, spell_format: SpellFormat):
        """（AP资源）后缀被剥离"""
        text = "**皇冠战争法术 (Crown War Spells)（AP资源）**\n**学派：** 变化系\n"
        normalized = spell_format.normalize(text)
        assert "AP资源" not in normalized, f"AP资源后缀未剥离: {normalized}"
        assert "**皇冠战争法术 (Crown War Spells)**" in normalized, f"标题异常: {normalized}"

    def test_no_double_bold_after_normalize(self, spell_format: SpellFormat):
        """归一化后不应出现 **字段：** 值 被再次加粗"""
        text = "**学派：** 咒法系\n"
        normalized = spell_format.normalize(text)
        # 重复归一化应幂等
        normalized2 = spell_format.normalize(normalized)
        assert normalized == normalized2, f"归一化不幂等"


class TestCrossLineTitleBreak:
    """跨行标题断裂修复

    暴君魔爪等冒险之路文件常见模式：
      **中文（English_part1
      English_part2）**#140: 来源
    应归一化为单行 **中文 (English_part1 English_part2)**。
    """

    def test_crossline_closing_bold_simple(self, spell_format: SpellFormat):
        """**血石护心镜（Bloodstone \\nMirror）** → 合并为单行"""
        text = (
            "**血石护心镜（Bloodstone \n"
            "Mirror）**#140: Eulogy for Roslar's Coffer\n"
            "**学派：** 防护系\n"
            "**等级：** 牧师 7\n"
        )
        normalized = spell_format.normalize(text)
        # 必须有合并后的单行标题
        assert "**血石护心镜 (Bloodstone Mirror)**" in normalized, (
            f"未合并跨行标题: {normalized!r}"
        )
        # 不应残留跨行模式
        assert "Bloodstone \nMirror" not in normalized, (
            f"跨行未合并: {normalized!r}"
        )

    def test_crossline_closing_bold_multi_word(self, spell_format: SpellFormat):
        """**鲜红十字军祷言（Litany of the Red \\nCrusader）** → 多词英文名合并"""
        text = (
            "**鲜红十字军祷言（Litany of the Red \n"
            "Crusader）**#140: Eulogy for Roslar's Coffer\n"
            "**学派：** 死灵系\n"
            "**等级：** 反圣武士 1\n"
        )
        normalized = spell_format.normalize(text)
        assert "**鲜红十字军祷言 (Litany of the Red Crusader)**" in normalized, (
            f"多词未合并: {normalized!r}"
        )

    def test_crossline_closing_bold_splits_correctly(self, spell_format: SpellFormat):
        """合并后的标题应被 split_into_items 正确分割为独立条目"""
        text = (
            "**血石护心镜（Bloodstone \n"
            "Mirror）**#140: Eulogy for Roslar's Coffer\n"
            "**学派：** 防护系\n"
            "**等级：** 牧师 7\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "血石护心镜" in names, f"未找到血石护心镜: {names}"
        # 标题行不应残留跨行
        for it in items:
            if it["name"] == "血石护心镜":
                assert "\n" not in it["name"], f"标题残留换行: {it['name']!r}"

    def test_crossline_closing_bold_idempotent(self, spell_format: SpellFormat):
        """重复归一化应幂等（防止首次归一化后再次触发跨行修复）"""
        text = (
            "**血石护心镜（Bloodstone \n"
            "Mirror）**#140\n"
            "**学派：** 防护系\n"
        )
        normalized1 = spell_format.normalize(text)
        normalized2 = spell_format.normalize(normalized1)
        assert normalized1 == normalized2, f"归一化不幂等:\n1: {normalized1!r}\n2: {normalized2!r}"

    def test_crossline_closing_bold_no_false_positive_single_line(self, spell_format: SpellFormat):
        """单行标题 **中文 (English)** 不应被破坏"""
        text = "**强酸箭 (Acid Arrow)**\n**学派：** 咒法系\n"
        normalized = spell_format.normalize(text)
        assert "**强酸箭 (Acid Arrow)**" in normalized, (
            f"单行标题被破坏: {normalized!r}"
        )

    def test_crossline_closing_bold_no_false_positive_description(self, spell_format: SpellFormat):
        """新 fixer 仅作用于 ** 包裹的标题，描述中的括号不受其影响。

        注：现有 _fix_broken_english_names 已广义合并 letter\\nletter，
        本测试仅验证新 fixer 不引入 **外** 的新合并副作用。
        """
        text = (
            "**强酸箭 (Acid Arrow)**\n"
            "**学派：** 咒法系\n"
            "**描述：** 描述中 (English \n"
            "Continuation) 说明细节。\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        # 只应有 1 个法术条目（强酸箭），不应误分割为多个
        assert names.count("强酸箭") == 1, f"误分割: {names}"
        # 标题内容完整保留
        assert "**强酸箭 (Acid Arrow)**" in normalized

    def test_source_annotation_suffix_stripped(self, spell_format: SpellFormat):
        """**Title(English)**#140: 来源 后缀被剥离，便于 split_into_items 识别。

        暴君魔爪常见模式：标题行尾带 #140: Eulogy for Roslar's Coffer
        应归一化为 **Title(English)** 纯标题行。
        """
        text = (
            "**禁称（Unspoken Name）**#140: Eulogy for Roslar's Coffer\n"
            "**学派：** 预言系\n"
            "**等级：** 牧师 3\n"
        )
        normalized = spell_format.normalize(text)
        # 来源标注必须被剥离
        assert "#140" not in normalized, f"来源标注未剥离: {normalized!r}"
        # 标题内容保留
        assert "**禁称 (Unspoken Name)**" in normalized, (
            f"标题异常: {normalized!r}"
        )
        # 必须能被 split_into_items 正确识别
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "禁称" in names, f"未找到禁称: {names}"

    def test_crossline_with_source_annotation(self, spell_format: SpellFormat):
        """跨行标题 + #XXX: 来源标注的组合（暴君魔爪典型）"""
        text = (
            "**血石护心镜（Bloodstone \n"
            "Mirror）**#140: Eulogy for Roslar's Coffer\n"
            "**学派：** 防护系\n"
            "**等级：** 牧师 7\n"
        )
        normalized = spell_format.normalize(text)
        # 跨行合并 + 来源剥离都应生效
        assert "**血石护心镜 (Bloodstone Mirror)**" in normalized, (
            f"未合并/剥离: {normalized!r}"
        )
        assert "#140" not in normalized, f"来源未剥离: {normalized!r}"
        # split_into_items 应能识别
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "血石护心镜" in names, f"未找到血石护心镜: {names}"
        assert len(items) == 1, f"应有 1 个条目，实际 {len(items)}"


class TestPipeTableIndexExclusion:
    """管道表格 A-Z 索引中的 cell 不应被识别为法术。

    page_625 等文件的 A-Z 索引结构：
        **A**
        | 超越之障（Ablative Barrier） 动物形态（Animal Aspect） ... | ... |
    每个 cell 在源文件中跨多行（前导空格 + 中文），不应被 wrap_bare_spell_titles
    误识别为独立的法术标题。
    """

    def test_pipe_table_cell_not_wrapped_as_title(self, spell_format: SpellFormat):
        """前导空格的管道表格 cell 不应被加粗为标题。

        源 page_625.md 的 A-Z 索引 cell 在不同行：
          | 超越之障（Ablative
                 Barrier）
               动物形态（Animal
                 Aspect） |
        """
        text = (
            "**A**\n"
            "\n"
            "| 超越之障（Ablative \n"
            "       Barrier） \n"
            "     动物形态（Animal \n"
            "       Aspect） |\n"
            "| --- |\n"
        )
        normalized = spell_format.normalize(text)
        # 管道表格 cell 不应被加粗包装
        assert "**动物形态" not in normalized, (
            f"管道表格 cell 被误加粗: {normalized!r}"
        )
        # split_into_items 应只识别出 '**A**' 章节头（实际 0 个法术条目，
        # 因为 A-Z 索引本身不产生法术条目）
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "动物形态" not in names, f"管道表格 cell 被误识别为法术: {names}"
        assert "超越之障" not in names, f"管道表格 cell 被误识别为法术: {names}"

    def test_page_625_chunk_count(self, spell_format: SpellFormat):
        """page_625.md 修复后 chunk 数应大幅低于修复前的 404。

        注：基线 estimated_count=71 是手数错误（page_625 实际有 257 个
        **来源** 标记 = 257 个真实法术）。本测试验证 A-Z 索引管道表格被
        正确排除（不再 404），而真实法术条目保留（约 257）。
        """
        with open("pf_rules_md_organized/法术/page_625.md", encoding="utf-8") as f:
            raw = f.read()
        normalized = spell_format.normalize(raw)
        items = spell_format.split_into_items(normalized)
        count = len(items)
        # 修复前为 404（含约 150 个 A-Z 索引 cell 误识别）。
        # 修复后应大幅下降，接近真实法术数 257 ±容差。
        assert count <= 320, (
            f"page_625 修复后 chunk 数 {count}，应 ≤320（修复前 404）"
        )
        assert count >= 240, (
            f"page_625 修复后 chunk 数 {count}，应 ≥240（实际 ~257 个真实法术）"
        )


class TestCompilationIntroStripping:
    """page_1365 等编译帖的剥离规则。

    page_1365.md 是果园编译帖，含：
      - 头部编译说明（如「截至2017/06/24为止，官方已经出了80本书...」）
      - 索引表（| PZO9401 二度黑暗玩家指南 | 原译者：四月 | 校正：笨哈 |）
      - 书籍分组标题 `##### PZO9401` + 书籍副标题（如「(开头+边栏待补完)」）
      - 真实法术（以 `【学派】中文名(English)` 开头，字段逐行展开）

    剥离目标：
      1. 头部编译说明（保留，但应在第一法术前结束 — 不影响 chunk 数）
      2. 索引管道表格（应剥离，避免被识别为内容）
      3. `##### PZO94xx` 书籍分组标题及其紧跟的副标题行
    """

    def test_book_group_heading_stripped(self, spell_format: SpellFormat):
        """`##### PZO9401` + 紧跟的副标题行（如 "(开头+边栏待补完)"）应被剥离。

        修复前 `##### PZO9401` 被识别为标题、副标题行被吞入下一个 chunk。
        修复后两个都被剥离，不产生 chunk。
        """
        text = (
            "**前面法术**\n"
            "**等级**：牧师 1\n"
            "\n"
            "##### PZO9401\n"
            "二度黑暗玩家指南（Second\n"
            "Darkness - Player's Guide）(开头+边栏待补完)\n"
            "\n"
            "**后面法术**\n"
            "**等级**：法师 2\n"
        )
        normalized = spell_format.normalize(text)
        assert "##### PZO9401" not in normalized, (
            f"`##### PZO9401` 未剥离: {normalized!r}"
        )
        assert "(开头+边栏待补完)" not in normalized, (
            f"书籍副标题未剥离: {normalized!r}"
        )
        # 不应产生 PZO9401 这类虚假 chunk
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "PZO9401" not in names, f"书籍分组标题被误识别为法术: {names}"
        assert "二度黑暗玩家指南" not in names, f"书籍副标题被误识别为法术: {names}"

    def test_index_pipe_table_stripped(self, spell_format: SpellFormat):
        """顶部索引管道表格（| PZO9401 二度黑暗玩家指南 | 原译者：四月 |）应被剥离。

        page_1365 行 1-141 是编译说明 + 索引表，行 70-141 是索引表。
        索引表中的"PZO9401 二度黑暗玩家指南"等不应被识别为法术。

        注：参考实际 page_1365 L146-154，`##### PZO9401` 与真实法术之间
        有 ~4 个空行（不仅是 1 个），剥离器应在空行处停止吃副标题。
        """
        text = (
            "## 玩家伴侣索引（Player Companion Index）\n"
            "\n"
            "| PZO9401 二度黑暗玩家指南（Second Darkness） | 原译者：四月 | 校正：笨哈 |\n"
            "| --- | --- | --- |\n"
            "| PZO9403 奥斯里昂（Osirion） | 原译者：软软软 | 校正：笨哈 |\n"
            "\n"
            "##### PZO9401\n"
            "二度黑暗玩家指南（开头+边栏待补完）\n"
            "\n"
            "\n"
            "\n"
            "\n"
            "**真实法术 (Real Spell)**\n"
            "**等级**：牧师 1\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        # 索引表中的"二度黑暗玩家指南"、"奥斯里昂"等是书籍名而非法术
        assert "二度黑暗玩家指南" not in names, (
            f"索引表书籍名被误识别为法术: {names}"
        )
        assert "奥斯里昂" not in names, (
            f"索引表书籍名被误识别为法术: {names}"
        )
        # "真实法术" 应保留
        assert "真实法术" in names, f"真实法术丢失: {names}"

    def test_page_1365_chunk_count(self, spell_format: SpellFormat):
        """page_1365.md 修复后 chunk 数应大幅低于修复前的 640。

        注：基线 estimated_count=280 是手数下界错误（按 616 个【学派】标记
        反推），实际 page_1365 含 ~594 个真实法术（含字段或被无字段行误切
        的描述性法术）。修复前 640 chunk 含约 150 个误识别：
          - 索引表中的书籍名（约 70 条）
          - `##### PZO94xx` 书籍分组标题（约 60+ 条）
          - 副标题"(开头+边栏待补完)"等被吞入 chunk（约 60+ 条）

        修复后应大幅下降，趋近真实法术数（约 594）。
        """
        with open("pf_rules_md_organized/法术/玩家伴侣/page_1365.md", encoding="utf-8") as f:
            raw = f.read()
        normalized = spell_format.normalize(raw)
        items = spell_format.split_into_items(normalized)
        count = len(items)
        # 修复前为 640。修复后应大幅下降，趋近真实法术数 ~594 ±容差。
        assert count <= 640, (
            f"page_1365 修复后 chunk 数 {count}，应 ≤640（修复前 640，未改善）"
        )
        # 修复后必须显著低于 640（剥离索引表 + 书籍分组 + 副标题）
        assert count <= 620, (
            f"page_1365 修复后 chunk 数 {count}，应 ≤620（基线 640 - 至少 20 剥离）"
        )
        # 真实法术数 ~594，应至少保留 500
        assert count >= 500, (
            f"page_1365 修复后 chunk 数 {count}，应 ≥500（不应误删真实法术）"
        )


class TestSubschoolVariantsMetadata:
    """任务与战役_法术.md 的典礼（Ceremony）法术含 4 个变体子条目：

    ** 葬礼 (Funeral)**
    ** 节庆 (Holiday Fete)**
    ** 婚礼 (Marriage)**
    ** 赐名 (Naming)**
    ** 领域典礼 (Domain Ceremonies)**

    它们不是独立法术，而是同一法术（Ceremony）的子条目，
    应在 metadata.subschool_variants 标记，保持 1 个 chunk。
    """

    def test_ceremony_stays_one_chunk(self, spell_format: SpellFormat):
        """任务与战役_法术.md 应产出 1 个 chunk（典礼 Ceremony）。

        注：变体子条目（葬礼/节庆/婚礼/赐名/领域典礼）应保留在同一 chunk 内。
        """
        with open(
            "pf_rules_md_organized/法术/任务与战役_法术.md", encoding="utf-8"
        ) as f:
            raw = f.read()
        normalized = spell_format.normalize(raw)
        items = spell_format.split_into_items(normalized)
        count = len(items)
        assert count == 1, (
            f"任务与战役_法术 应为 1 chunk，实际 {count}（变体被误识别为独立法术）"
        )
        names = [it["name"] for it in items]
        assert "典礼" in names or "Ceremony" in str(items), (
            f"未找到典礼法术: {names}"
        )

    def test_subschool_variants_extracted(self, spell_format: SpellFormat):
        """变体子条目名称应在 metadata.subschool_variants 标记。"""
        from vectorizer.processors.spell import SpellProcessor
        from vectorizer.sources.providers import SourceResolver
        with open(
            "pf_rules_md_organized/法术/任务与战役_法术.md", encoding="utf-8"
        ) as f:
            raw = f.read()
        # SpellProcessor 需要 SourceResolver（不需实际加载索引）
        proc = SpellProcessor(source_resolver=SourceResolver(providers=[]))
        normalized = spell_format.normalize(raw)
        items = spell_format.split_into_items(normalized)
        assert len(items) == 1, f"期望 1 chunk，实际 {len(items)}"
        # 触发 infer_metadata（接受 chunk 和 item 两个参数）
        from vectorizer.processors.base import Chunk
        chunk = Chunk(
            chunk_id="任务与战役_法术:0",
            doc_id="任务与战役_法术",
            category="spell",
            component_type="spell",
            title=items[0]["name"],
            text=items[0]["text"],
            book_abbreviation="QC",
            book_name_cn="任务与战役",
            book_name_en="Quests and Campaigns",
            source_confidence=80,
        )
        result = proc.infer_metadata(chunk, items[0])
        # chunk 是 dataclass；result 可能是同一实例（mutate）或返回新对象
        if isinstance(result, dict):
            metadata = result.get("metadata", {})
        else:
            metadata = result.metadata
        variants = metadata.get("subschool_variants", [])
        assert "funeral" in variants, f"funeral 未标记: {variants}"
        assert "holiday_fete" in variants, f"holiday_fete 未标记: {variants}"
        assert "marriage" in variants, f"marriage 未标记: {variants}"
        assert "naming" in variants, f"naming 未标记: {variants}"
        assert "domain_ceremony" in variants, f"domain_ceremony 未标记: {variants}"


class TestBracketCrosslineEnglishName:
    """【学派】格式跨行英文名合并

    page_1008/1141/1142 等文件常见模式：
      【变化】(变形)返初溯源(First
      World Revisions)
    应归一化为单行的 【变化】(变形)返初溯源(First World Revisions)。
    """

    def test_crossline_english_with_subschool(self, spell_format: SpellFormat):
        """【变化】(变形)返初溯源(First World Revisions) 跨行合并"""
        text = (
            "【变化】(变形)返初溯源(First \n"
            "World Revisions)\n"
            "**等级**：炼金术师/调查员2\n"
        )
        normalized = spell_format.normalize(text)
        # 跨行英文名被合并
        assert "返初溯源(First World Revisions)" in normalized or \
            "**返初溯源 (First World Revisions)**" in normalized, (
            f"跨行英文名未合并: {normalized!r}"
        )
        # split_into_items 应能识别
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "返初溯源" in names, f"未找到返初溯源: {names}"

    def test_crossline_english_no_subschool(self, spell_format: SpellFormat):
        """【变化】太阳恐惧(FEAR THE SUN) 跨行合并"""
        text = (
            "【变化】太阳恐惧(FEAR \n"
            "THE SUN)\n"
            "**等级**：反圣武士1\n"
        )
        normalized = spell_format.normalize(text)
        assert "太阳恐惧(FEAR THE SUN)" in normalized or \
            "**太阳恐惧 (FEAR THE SUN)**" in normalized, (
            f"跨行英文名未合并: {normalized!r}"
        )
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "太阳恐惧" in names, f"未找到太阳恐惧: {names}"

    def test_crossline_english_two_word(self, spell_format: SpellFormat):
        """【变化】(变形)低贱形态(IGNOBLE FORM) 双词跨行合并"""
        text = (
            "【变化】(变形)低贱形态(IGNOBLE \n"
            "FORM)\n"
            "**等级**：牧师/先知/战斗祭司2\n"
        )
        normalized = spell_format.normalize(text)
        assert "低贱形态(IGNOBLE FORM)" in normalized or \
            "**低贱形态 (IGNOBLE FORM)**" in normalized, (
            f"双词跨行未合并: {normalized!r}"
        )
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "低贱形态" in names, f"未找到低贱形态: {names}"

    def test_crossline_no_false_positive_normal(self, spell_format: SpellFormat):
        """正常 【学派】 格式不受影响"""
        text = "【咒法系】(创造)强酸箭(Acid Arrow)[酸]\n**等级：** 魔战士 2\n"
        normalized = spell_format.normalize(text)
        assert "**强酸箭 (Acid Arrow)**" in normalized, (
            f"正常格式被破坏: {normalized!r}"
        )

    def test_crossline_idempotent(self, spell_format: SpellFormat):
        """重复归一化应幂等"""
        text = (
            "【变化】(变形)返初溯源(First \n"
            "World Revisions)\n"
            "**等级**：术士/法师 3\n"
        )
        normalized1 = spell_format.normalize(text)
        normalized2 = spell_format.normalize(normalized1)
        assert normalized1 == normalized2, (
            f"归一化不幂等:\n1: {normalized1!r}\n2: {normalized2!r}"
        )

    def test_crossline_english_inline(self, spell_format: SpellFormat):
        """行内模式的 【学派】中文(多词English) 跨行合并后正确转换"""
        text = (
            "一些介绍文字。"
            "【死灵】(阴影)暗影打击(UMBRAL \n"
            "STRIKE)\n"
            "**等级：** 牧师 4\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "暗影打击" in names, f"未找到暗影打击: {names}"


class TestInlineAliasCompact:
    """KN012：行内粘连别名标签拆行（bold 别名 施放时间/持续/抗力/SR）。

    源数据中字段值末尾直接拼接别名 bold 标签（无换行）：
      **豁免：** 强韧，通过则无效**抗力**：有
    _fix_inline_compact 的 Step 2/3 必须支持别名标签集（不仅 LEGACY_13），
    Step 4 无冒号场景保持原集合（避免散文中 **抗力** 误拆）。
    """

    def test_alias_spell_resistance_inline_split(self, spell_format: SpellFormat):
        """正例：**豁免：** …无效**抗力**：有 → normalize 后 **法术抗力** 独立成行（无粘连）"""
        text = (
            "**酸液飞溅 (Acid Splash)**\n"
            "**学派：** 咒法系（创造）[酸]\n"
            "**环位：** 术士/法师 1\n"
            "**施法时间：** 标准动作\n"
            "**豁免：** 无**抗力**：可\n"
            "**描述：** 你喷出一团酸液。\n"
        )
        normalized = spell_format.normalize(text)
        # 严格断言：normalize 后 **抗力（**法术抗力）不得出现在非行首位置
        lines = normalized.split("\n")
        for ln in lines:
            stripped = ln.lstrip()
            # 找到包含 **法术抗力 的行
            if "**法术抗力" in stripped or "**抗力" in stripped:
                # 该行要么以 **法术抗力/抗力 开头（独立行），要么不应包含前字段值尾
                assert stripped.startswith("**法术抗力") or stripped.startswith("**抗力"), (
                    f"**抗力 别名粘连未拆:\n  -> {ln!r}\n  全文:\n{normalized}"
                )

    def test_alias_duration_inline_split(self, spell_format: SpellFormat):
        """正例：**持续**：1轮**豁免**：… → **持续时间** 独立成行（无粘连）"""
        text = (
            "**酸液飞溅 (Acid Splash)**\n"
            "**学派：** 咒法系\n"
            "**持续**：1轮/等级**豁免**：无\n"
            "**描述：** 喷出酸液。\n"
        )
        normalized = spell_format.normalize(text)
        # 严格断言：行首含 **持续时间/持续 的行必须独占该标签
        lines = normalized.split("\n")
        for ln in lines:
            stripped = ln.lstrip()
            if "**持续时间" in stripped or stripped.startswith("**持续："):
                assert stripped.startswith("**持续时间") or stripped.startswith("**持续"), (
                    f"**持续** 别名粘连未拆:\n  -> {ln!r}\n  全文:\n{normalized}"
                )

    def test_alias_casting_time_inline_split(self, spell_format: SpellFormat):
        """正例：值**施放时间**：标准动作 → **施法时间** 独立成行（无粘连）"""
        text = (
            "**酸液飞溅 (Acid Splash)**\n"
            "**学派：** 咒法系\n"
            "**范围：** 近距**施放时间**：标准动作\n"
            "**描述：** 喷出酸液。\n"
        )
        normalized = spell_format.normalize(text)
        lines = normalized.split("\n")
        for ln in lines:
            stripped = ln.lstrip()
            if "**施法时间" in stripped or "**施放时间" in stripped:
                assert stripped.startswith("**施法时间") or stripped.startswith("**施放时间"), (
                    f"**施放时间** 别名粘连未拆:\n  -> {ln!r}\n  全文:\n{normalized}"
                )

    def test_canonical_spell_resistance_inline_split(self, spell_format: SpellFormat):
        """正例（规范标签回归）：**豁免：** …无效**法术抗力** 有 → 独立成行"""
        text = (
            "**酸液飞溅 (Acid Splash)**\n"
            "**学派：** 咒法系\n"
            "**豁免：** 无**法术抗力**：可\n"
            "**描述：** 喷出酸液。\n"
        )
        normalized = spell_format.normalize(text)
        lines = normalized.split("\n")
        for ln in lines:
            stripped = ln.lstrip()
            if "**法术抗力" in stripped:
                assert stripped.startswith("**法术抗力"), (
                    f"**法术抗力** 规范标签粘连未拆:\n  -> {ln!r}\n  全文:\n{normalized}"
                )

    def test_prose_bold_alias_not_split(self, spell_format: SpellFormat):
        """反例：散文中 **抗力**（无冒号）不被拆行"""
        text = (
            "**酸液飞溅 (Acid Splash)**\n"
            "**学派：** 咒法系\n"
            "**描述：** 该法术的**抗力**较弱。\n"
        )
        normalized = spell_format.normalize(text)
        # 描述行内的 **抗力** 必须保留（不被拆为独立行）
        assert "**抗力**较弱" in normalized or "**抗力** 较弱" in normalized, (
            f"散文中 **抗力** 被错误拆行:\n{normalized}"
        )

    def test_prose_bold_duration_not_split(self, spell_format: SpellFormat):
        """反例：散文中 **持续**（无冒号）强调不被拆行"""
        text = (
            "**酸液飞溅 (Acid Splash)**\n"
            "**学派：** 咒法系\n"
            "**描述：** 效果**持续**专注检定。\n"
        )
        normalized = spell_format.normalize(text)
        assert "**持续**专注" in normalized or "**持续** 专注" in normalized, (
            f"散文中 **持续** 被错误拆行:\n{normalized}"
        )

    def test_idempotent_on_already_split_text(self, spell_format: SpellFormat):
        """幂等：标签已在行首的文本，normalize 两次结果相同"""
        text = (
            "**酸液飞溅 (Acid Splash)**\n"
            "**学派：** 咒法系\n"
            "**环位：** 术士/法师 1\n"
            "**施法时间：** 标准动作\n"
            "**抗力：** 可\n"
            "**描述：** 喷出酸液。\n"
        )
        once = spell_format.normalize(text)
        twice = spell_format.normalize(once)
        assert once == twice, (
            f"normalize 不幂等:\n--- 1st ---\n{once}\n--- 2nd ---\n{twice}"
        )


class TestSpellTitleNormalization:
    """KN016：法术 chunk 合并污染修复（标题形态归一化簇）。

    8 簇：E/G/H/B/C/D/I + 零散变体（已通过源数据兜底）
    关键约束：候选标题行之后 1~3 个非空行内必须出现字段块开头
    （**学派：** / **等级：** / 规范后等价别名）— 否则不触发归一化。
    """

    # ===== E 簇：闭合断裂跨行 =====

    def test_e_broken_closing_with_pg_suffix(self, spell_format: SpellFormat):
        """E 簇正例：**X (Y) **\\n\\n**\\nBloodmarch Hills pg. 71 → 标准单行标题 + 页码行转正文"""
        text = (
            "一些介绍文字。\n"
            "**雷鸣脚步 (Thunderous Footfalls) **\n"
            "\n"
            "**\n"
            "Bloodmarch Hills pg. 71\n"
            "**学派：** 塑能系\n"
            "**描述：** 你重步踏地。\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "雷鸣脚步" in names, (
            f"E 簇标题未归一化为标准形:\n  names={names}\n  full={normalized}"
        )

    # ===== G 簇：裸标题无星号 =====

    def test_g_bare_title_wrapped(self, spell_format: SpellFormat):
        """G 簇正例：行首裸 `X (Y)` → 补 ** 包装"""
        text = (
            "前面段落。\n"
            "梦境旅行 (Dream Travel)\n"
            "**学派：** 咒法系（传送）\n"
            "**描述：** 你进入梦境位面。\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "梦境旅行" in names, (
            f"G 簇裸标题未被识别为 chunk:\n  names={names}\n  full={normalized}"
        )

    # ===== H 簇：缺闭合粗体 =====

    def test_h_missing_closing_bold_added(self, spell_format: SpellFormat):
        """H 簇正例：`**X (Y)` → 补行尾闭合 `**`"""
        text = (
            "前面段落。\n"
            "**饥渴之影 (The Hungering of Shadows)\n"
            "**学派：** 死灵系\n"
            "**描述：** 你被饥渴之影追逐。\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "饥渴之影" in names, (
            f"H 簇缺闭合粗体未被识别:\n  names={names}\n  full={normalized}"
        )

    # ===== B 簇：跨行粗体 =====

    def test_b_crossline_bold_merged(self, spell_format: SpellFormat):
        """B 簇正例：`**X\\n(Y)**` → 合并为单行 `**X (Y)**`"""
        text = (
            "前面段落。\n"
            "**目盲\n"
            "(Blindness/Deafness)**\n"
            "**学派：** 死灵系\n"
            "**描述：** 目标目盲或耳聋。\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "目盲" in names, (
            f"B 簇跨行粗体未合并:\n  names={names}\n  full={normalized}"
        )

    # ===== C 簇：粗体标题粘句尾 =====

    def test_c_title_stuck_to_sentence(self, spell_format: SpellFormat):
        """C 簇正例：`…相应类型法术。**X (Y)**` → 标题前插入换行"""
        text = (
            "你可使用任何相应类型法术。**次等指使术 (Geas, Lesser)**\n"
            "**学派：** 惑控系（胁迫）[影响心灵]\n"
            "**描述：** 你命令目标服从你。\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "次等指使术" in names, (
            f"C 簇标题粘句尾未拆开:\n  names={names}\n  full={normalized}"
        )

    # ===== D 簇：粗体标题带尾巴 =====

    def test_d_title_with_translator_tail(self, spell_format: SpellFormat):
        """D 簇正例：`**X (Y)**｜致谢 Xu ... → 标题独立成行，致谢行转为标题下一行正文"""
        text = (
            "**痛苦启示 (Agonizing Revelation)**｜本条翻译致谢** Xu22341380008**。\n"
            "**学派：** 死灵系\n"
            "**描述：** 目标感受痛苦。\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "痛苦启示" in names, (
            f"D 簇标题尾巴未拆开:\n  names={names}\n  full={normalized}"
        )

    # ===== I 簇：嵌套粗体 =====

    def test_i_nested_bold_denested(self, spell_format: SpellFormat):
        """I 簇正例：`X (**Y**)**` → 去嵌套为 `**X (Y)**`（顺带统一全角括号）"""
        text = (
            "前面段落。\n"
            "共享形态（**Share Shape**)**\n"
            "**学派：** 变化系（变形）\n"
            "**描述：** 你与同伴共享形态。\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "共享形态" in names, (
            f"I 簇嵌套粗体未去嵌套:\n  names={names}\n  full={normalized}"
        )

    # ===== 反向故障：spell_pattern 误判 =====

    def test_regression_animal_companion_archive_0008(self, spell_format: SpellFormat):
        """spell_动物档案AArch_法术_0008 反向故障：title 被污染成整句描述
        修复（I 簇去嵌套）后 title 应归位为法术名"""
        text = (
            "**<整句描述>...  共享形态 (**Share Shape**)**\n"
            "**学派：** 变化系\n"
            "**描述：** 你与同伴共享形态。\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "共享形态" in names, (
            f"反向故障未修复（I 簇）:\n  names={names}\n  full={normalized}"
        )

    # ===== Negative test：散文引用不升级 =====

    def test_negative_prose_reference_not_promoted(self, spell_format: SpellFormat):
        """负例：正文中 `如同 X (Y) 一般` 的法术名引用，不被升级为标题"""
        text = (
            "**酸液飞溅 (Acid Splash)**\n"
            "**学派：** 咒法系\n"
            "**描述：** 该法术如同强酸箭 (Acid Arrow) 一般造成酸液伤害。\n"
            "如同X (Y) 般描述后续段落。\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        # 应该只有 "酸液飞溅" 1 个 chunk，强酸箭 引用不被升级
        assert names.count("酸液飞溅") == 1, f"酸液飞溅 重复: {names}"
        assert "强酸箭" not in names, (
            f"散文引用 '强酸箭 (Acid Arrow)' 被错误升级为标题:\n  names={names}\n  full={normalized}"
        )

    # ===== 零散变体：源数据已修，但仍走解析器兜底测试 =====

    def test_canonical_form_idempotent(self, spell_format: SpellFormat):
        """幂等：标准单行标题文本 normalize 两次结果相同（新增 _normalize_spell_titles 必须幂等）"""
        text = (
            "**酸液飞溅 (Acid Splash)**\n"
            "**学派：** 咒法系\n"
            "**环位：** 术士/法师 1\n"
            "**描述：** 喷出酸液。\n"
        )
        once = spell_format.normalize(text)
        twice = spell_format.normalize(once)
        assert once == twice, (
            f"_normalize_spell_titles 不幂等:\n--- 1st ---\n{once}\n--- 2nd ---\n{twice}"
        )


class TestOneCCHalfRegex:
    """KN017：Phase 1c½ 神祇后缀正则必须仅作用于标题结构（**X (Y)**/deity）。

    旧正则 `^(\*\*.*?)/[一-鿿]{1,12}\\s*$` 过宽，误剥字段值末尾的：
      - /等级（持续时间/范围，最常见）
      - /法师（class=法师 丢失，全量 632 次触发中 39 次）
      - /法器（components 成分 法器 丢失）
      - /歌者、/战斗祭司、/奥能师、/猎人、/调查员（复合职业拆分丢失次要职业）
    新正则要求 `**X (Y)**/deity` 形态，字段行（含字段标签或不以 `)**` 收尾）永不匹配。
    """

    def test_duration_per_level_not_stripped(self, spell_format: SpellFormat):
        """正例：`/等级` 行尾不被剥（持续时间值保留完整）"""
        text = (
            "**酸液飞溅 (Acid Splash)**\n"
            "**学派：** 咒法系\n"
            "**持续时间：** 1分钟/等级\n"
            "**描述：** 喷出酸液。\n"
        )
        normalized = spell_format.normalize(text)
        assert "1分钟/等级" in normalized, (
            f"持续时间 `/等级` 被错误剥除:\n{normalized}"
        )

    def test_spell_level_mage_not_stripped(self, spell_format: SpellFormat):
        """正例：行尾 `/法师` 不被剥（class=法师 标记保留）"""
        text = (
            "**酸液飞溅 (Acid Splash)**\n"
            "**学派：** 咒法系\n"
            "**环位：** 吟游诗人 1，术士/法师\n"
            "**描述：** 喷出酸液。\n"
        )
        normalized = spell_format.normalize(text)
        assert "术士/法师" in normalized, (
            f"环位 `/法师` 被错误剥除（应保留）:\n{normalized}"
        )

    def test_components_focus_not_stripped(self, spell_format: SpellFormat):
        """正例：成分值 `/法器` 不被剥"""
        text = (
            "**酸液飞溅 (Acid Splash)**\n"
            "**学派：** 咒法系\n"
            "**成分：** 材料/法器\n"
            "**描述：** 喷出酸液。\n"
        )
        normalized = spell_format.normalize(text)
        assert "材料/法器" in normalized, (
            f"成分 `/法器` 被错误剥除:\n{normalized}"
        )

    def test_complex_class_bard_singer_not_stripped(self, spell_format: SpellFormat):
        """正例：复合职业 `吟游诗人/歌者` 完整保留"""
        text = (
            "**轻量化 (Lighten Object)**\n"
            "**学派：** 变化系\n"
            "**环位：** 吟游诗人/歌者 1\n"
            "**描述：** 减轻物品重量。\n"
        )
        normalized = spell_format.normalize(text)
        assert "吟游诗人/歌者" in normalized, (
            f"复合职业 `/歌者` 被错误剥除:\n{normalized}"
        )

    def test_complex_class_warpriest_not_stripped(self, spell_format: SpellFormat):
        """正例：复合职业 `牧师/先知/战斗祭司` 完整保留"""
        text = (
            "**轻量化 (Lighten Object)**\n"
            "**学派：** 变化系\n"
            "**环位：** 牧师/先知/战斗祭司 1\n"
            "**描述：** 减轻物品重量。\n"
        )
        normalized = spell_format.normalize(text)
        assert "战斗祭司" in normalized, (
            f"复合职业 `/战斗祭司` 被错误剥除:\n{normalized}"
        )

    def test_complex_class_kineticist_not_stripped(self, spell_format: SpellFormat):
        """正例：复合职业 `术士/法师/奥能师` 完整保留"""
        text = (
            "**轻量化 (Lighten Object)**\n"
            "**学派：** 变化系\n"
            "**环位：** 术士/法师/奥能师 1\n"
            "**描述：** 减轻物品重量。\n"
        )
        normalized = spell_format.normalize(text)
        assert "奥能师" in normalized, (
            f"复合职业 `/奥能师` 被错误剥除:\n{normalized}"
        )

    def test_complex_class_ranger_hunter_not_stripped(self, spell_format: SpellFormat):
        """正例：复合职业 `游侠/猎人` 完整保留"""
        text = (
            "**猎手印记 (Hunter's Mark)**\n"
            "**学派：** 预言系\n"
            "**环位：** 游侠/猎人 1\n"
            "**描述：** 标记猎物。\n"
        )
        normalized = spell_format.normalize(text)
        assert "猎人" in normalized, (
            f"复合职业 `/猎人` 被错误剥除:\n{normalized}"
        )

    def test_complex_class_alchemist_investigator_not_stripped(self, spell_format: SpellFormat):
        """正例：复合职业 `炼金术师/调查员` 完整保留"""
        text = (
            "**炼金炸弹 (Alchemist's Fire)**\n"
            "**学派：** 塑能系\n"
            "**环位：** 炼金术师/调查员 1\n"
            "**描述：** 投掷炼金炸弹。\n"
        )
        normalized = spell_format.normalize(text)
        assert "调查员" in normalized, (
            f"复合职业 `/调查员` 被错误剥除:\n{normalized}"
        )

    def test_fop_deity_title_with_closing_bold_unchanged(self, spell_format: SpellFormat):
        """反例：FoP 真神祇标题形态 `**X (Y)**/deity` 当前实际不存在（_unify_school_bracket_titles 先剥）；
        新正则收窄后即使再次出现也仅匹配标准标题结构，FoP 不会被错误地匹配到字段行上。

        本测试固定一种"既含 `(English)` 又含 `/deity`"的字段样式（实际上不会出现），
        验证新正则不会把它当标题处理。
        """
        # 字段样式：**学派：** 变化/法师 — 这里没有 (English) 形态，不会被新正则误剥
        text = (
            "**轻量化 (Lighten Object)**\n"
            "**学派：** 变化系/防护系\n"
            "**描述：** 减轻物品重量。\n"
        )
        normalized = spell_format.normalize(text)
        # 字段值不应被破坏
        assert "变化系/防护系" in normalized, (
            f"字段值 `/防护系` 被错误剥除:\n{normalized}"
        )


class TestParseSpellLevelNoSpaceFallback:
    """KN017：parse_spell_level 无空格兜底。

    源数据 `法师2`、`术士/法师2` 无空格时旧 `(.+?)\\s+(\\d+)` 不匹配 → 该 part 静默丢弃。
    新增无空格兜底 `^([一-鿿][一-鿿/]*?)(\\d+)$`。
    """

    def test_class_no_space(self):
        """正例：`法师2` → [{"class": "法师", "level": 2}]"""
        from vectorizer.formats.spell import SpellFormat
        result = SpellFormat.parse_spell_level("法师2")
        assert result == [{"class": "法师", "level": 2}], (
            f"无空格 `法师2` 未解析: {result}"
        )

    def test_complex_class_no_space(self):
        """正例：`术士/法师2` → F3 拆分后 [{术士:2}, {法师:2}]"""
        from vectorizer.formats.spell import SpellFormat
        result = SpellFormat.parse_spell_level("术士/法师2")
        # 注：F3 拆分在 _extract_spell_level 调用方，parse_spell_level 仅负责单 part 解析
        # 复合 part 通过后续拆分逻辑处理。这里仅确认 part 不被丢弃
        assert len(result) >= 1, f"复合职业 `术士/法师2` 被丢弃: {result}"

    def test_with_space_unchanged(self):
        """回归：有空格 `炼金术师 2` 不变"""
        from vectorizer.formats.spell import SpellFormat
        result = SpellFormat.parse_spell_level("炼金术师 2")
        assert result == [{"class": "炼金术师", "level": 2}], (
            f"有空格形态被破坏: {result}"
        )

    def test_pure_number_unchanged(self):
        """回归：纯数字 `3` → [{class: None, level: 3}]"""
        from vectorizer.formats.spell import SpellFormat
        result = SpellFormat.parse_spell_level("3")
        assert result == [{"class": None, "level": 3}], (
            f"纯数字形态被破坏: {result}"
        )

    def test_negative_non_class_string(self):
        """反例：`1分钟/等级` 类非职业串不误判（环位字段中不会出现该串，固定为 negative）"""
        from vectorizer.formats.spell import SpellFormat
        result = SpellFormat.parse_spell_level("1分钟/等级")
        # 该串不在环位字段规范中，应被丢弃（或保持不变）——关键是不要把它当职业
        # 正则 `^([一-鿿][一-鿿/]*?)(\d+)$` 不会匹配（中间有非汉字字符）
        for item in result:
            assert item.get("class") != "1分钟", (
                f"非职业串 `1分钟/等级` 被误判为职业: {result}"
            )

    def test_mixed_list_with_no_space(self):
        """正例：混合列表 `炼金术师 2, 魔战士 1, 法师2` 全解析"""
        from vectorizer.formats.spell import SpellFormat
        result = SpellFormat.parse_spell_level("炼金术师 2, 魔战士 1, 法师2")
        classes = [item.get("class") for item in result]
        assert "炼金术师" in classes, f"`炼金术师` 丢失: {result}"
        assert "魔战士" in classes, f"`魔战士` 丢失: {result}"
        assert "法师" in classes, f"`法师` (无空格) 丢失: {result}"


class TestSplitWarning:
    """KN017：split_into_items 丢弃告警 — 仅可观测性，不改 split 行为。

    三个丢弃点（章节边界 / A-Z 索引 / 新标题出现）：
    当 current_name is None 且被跳过的段落非空且含字段信号（**学派：** / **环位：** / **等级：**），
    logger.warning 输出文件名 + 段落首 80 字符。
    """

    def test_chapter_boundary_drop_with_field_signal(self, spell_format: SpellFormat, caplog):
        """章节边界 + 字段信号 → warning"""
        # 文件头出现一个孤立法术块（无标题），紧跟一个真正的章节边界
        text = (
            "**学派：** 咒法系\n"
            "**环位：** 术士/法师 1\n"
            "**描述：** 这是无标题的孤儿块。\n"
            "\n"
            "## 下一章\n"
            "**酸液飞溅 (Acid Splash)**\n"
            "**学派：** 咒法系\n"
            "**描述：** 喷出酸液。\n"
        )
        with caplog.at_level("WARNING"):
            items = spell_format.split_into_items(text, source_name="test_file.md")
        # 应至少触发 1 条 WARNING（孤儿块被丢弃）
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) >= 1, (
            f"章节边界孤儿块未触发告警:\n  caplog={[r.getMessage() for r in caplog.records]}"
        )
        # 警告内容应包含 source_name
        assert any("test_file.md" in r.getMessage() for r in warnings), (
            f"告警未包含 source_name:\n  {[r.getMessage() for r in warnings]}"
        )

    def test_az_index_drop_with_field_signal(self, spell_format: SpellFormat, caplog):
        """A-Z 索引 + 字段信号 → warning"""
        text = (
            "**A**\n"  # A-Z 索引，重置 current_name
            "**学派：** 咒法系\n"
            "**环位：** 术士/法师 1\n"
            "**描述：** 这是 A-Z 索引后丢失的孤儿。\n"
            "\n"
            "**酸液飞溅 (Acid Splash)**\n"
            "**学派：** 咒法系\n"
            "**描述：** 喷出酸液。\n"
        )
        with caplog.at_level("WARNING"):
            items = spell_format.split_into_items(text, source_name="test_index.md")
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) >= 1, (
            f"A-Z 索引孤儿块未触发告警:\n  caplog={[r.getMessage() for r in caplog.records]}"
        )

    def test_group_header_drop_no_field_signal(self, spell_format: SpellFormat, caplog):
        """分组标题（不含字段信号）→ 不告警（避免噪声）"""
        text = (
            "防护系法术\n"  # 分组标题，无字段信号
            "\n"
            "**酸液飞溅 (Acid Splash)**\n"
            "**学派：** 咒法系\n"
            "**描述：** 喷出酸液。\n"
        )
        with caplog.at_level("WARNING"):
            items = spell_format.split_into_items(text, source_name="test_group.md")
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        # 分组标题不含字段信号，不应告警
        assert len(warnings) == 0, (
            f"分组标题（含字段信号判定错误）误告警:\n  {[r.getMessage() for r in warnings]}"
        )


class TestKn023UrlTriggerFalsePositive:
    """KN023 回归：含 index.php 的 URL 行不得触发索引表剥离。

    KN023 根因（2026-08-01 实证）：`_strip_compilation_intro` 的索引表检测用
    `'index' in ln` 子串匹配，URL 行 `[http://.../index.php?...]` 含 "index"
    误触发 pipe_skip，且 pipe_skip 的"标题跨行延续"条件（含 ** 的非 ** 开头行）
    吞掉后续正文行——6 文件（Spell OA/page_625/page_854/page_1219/Spell ACG/
    Spell CRB）共 45 处链接后正文丢失（登记口径 33）。
    """

    def test_url_line_does_not_trigger_pipe_skip(self, spell_format: SpellFormat):
        """含 index.php 的 URL 行 + 后续正文链接 + 字段行应全部保留。"""
        text = (
            "[http://45.79.87.129/bbs/index.php?topic=81720.0]"
            "(http://45.79.87.129/bbs/index.php?topic=81720.0)\n"
            "\n"
            "**异能魔法（Psychic Magic）**\n"
            "**等级**：异能者 3\n"
            "**目标**：一个生物\n"
            "该法术的功能类似于[神秘技能解放（Occult Skill Unlocks）]"
            "(http://www.goddessfantasy.net/bbs/index.php?topic=78448#msg742539)"
            "中的望气（read aura），但是该法术不需要进行检定\n"
        )
        normalized = spell_format.normalize(text)
        # KN023 实样：链接后 14 字 probe "中的望气readaura但是" 必须保留
        assert "中的望气" in normalized, f"链接后正文被吞: {normalized!r}"
        assert "不需要进行检定" in normalized, f"链接后正文被吞: {normalized!r}"
        assert "异能者 3" in normalized, f"字段行被吞: {normalized!r}"
        assert "一个生物" in normalized, f"字段行被吞: {normalized!r}"

    def test_inline_link_row_does_not_trigger_pipe_skip(self, spell_format: SpellFormat):
        """正文中段含 index.php 链接的行不得再次触发索引表剥离。"""
        text = (
            "**异能魔法（Psychic Magic）**\n"
            "**等级**：异能者 3\n"
            "该法术的功能类似于[神秘技能解放（Occult Skill Unlocks）]"
            "(http://www.goddessfantasy.net/bbs/index.php?topic=78448#msg742539)"
            "中的望气（read aura），但是该法术不需要进行检定。每轮都要从目标的"
            "四个灵光中选取一种，并借此获得与它的状态和性质相关的贵重情报。\n"
        )
        normalized = spell_format.normalize(text)
        assert "贵重情报" in normalized, f"链接行后的正文被吞: {normalized!r}"
        assert "异能者 3" in normalized, f"字段行被吞: {normalized!r}"

    def test_real_index_table_still_stripped(self, spell_format: SpellFormat):
        """真索引表（标题含"索引"、不含 URL）仍被剥离（page_1365 行为保持）。"""
        text = (
            "**玩家伴侣索引（****Player \n"
            "Companion Index****）**\n"
            "\n"
            "| PZO9401 二度黑暗玩家指南 | 原译者：四月 |\n"
            "| --- | --- |\n"
            "\n"
            "**真实法术 (Real Spell)**\n"
            "**等级**：牧师 1\n"
        )
        normalized = spell_format.normalize(text)
        assert "PZO9401" not in normalized, f"真索引表未剥离: {normalized!r}"
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "真实法术" in names, f"真实法术丢失: {names}"

    def test_pipe_skip_continuation_narrowed(self, spell_format: SpellFormat):
        """pipe_skip 跨行延续收窄：嵌套加粗（****）标题行仍吞，字段行不再吞。"""
        text = (
            "**玩家伴侣索引（****Player \n"
            "Companion Index****）**\n"
            "\n"
            "| PZO9401 二度黑暗 | 原译者：四月 |\n"
            "| --- | --- |\n"
            "+ 每2个等级5尺）**目标**：一个生物\n"
            "**真实法术 (Real Spell)**\n"
            "**等级**：牧师 1\n"
        )
        normalized = spell_format.normalize(text)
        # 嵌套加粗标题跨行仍被吞（索引标题完整性）
        assert "Companion Index" not in normalized, f"索引标题跨行未被吞: {normalized!r}"
        # 字段行（+ 前缀 + 行中 **，紧贴管道行无空行缓冲）不再被吞
        assert "每2个等级5尺" in normalized, f"字段行被误吞: {normalized!r}"

    def test_reverse_fallback_no_crossline_swallow(self, spell_format: SpellFormat):
        """反向故障兜底不跨行吞正文（KN023 第三处根因）。

        `**` 开头的长正文行 + 下一行标题曾被整体匹配（`[^*]*` 跨行贪婪），
        整段正文被删只留标题（Spell OA 169 处）。收窄 `[^\n*]*` 后：
        `**长正文…`（行内无闭合 `**`）+ 下一行 `**标题 (English)**` 不得误匹配。
        """
        text = (
            "**你用较弱的异能力量为物体充能。该物体能够被侦测异能存在"
            "（detect psychic significance）法术侦测到。如果你希望的话，"
            "还能够把自己拥有这件物体的经历写入物体之中。\n"
            "**认知妨碍  (Cognitive Block)**\n"
            "**等级**：异能者 3\n"
        )
        normalized = spell_format.normalize(text)
        assert "物体充能" in normalized, f"正文被跨行吞: {normalized!r}"
        assert "认知妨碍" in normalized, f"标题丢失: {normalized!r}"
        assert "异能者 3" in normalized, f"字段行丢失: {normalized!r}"

    def test_i_cluster_oa_title_preserves_leading_char(self, spell_format: SpellFormat):
        """I 簇 + 反向兜底交互：**中文名（****English****）** 前置 ** 不得成孤岛被吞字。

        KN023 第 4 处根因（2026-08-01 实证，page_277）：OA 标题
        `**刺青魔法（****Tattoo Magic****）****正文…` —— I 簇负向后顾
        （星号加括号字符合集）不允许中文名前有 `*`，匹配从"青"开始，
        留下孤岛 `**刺**`；随后反向兜底正则把 `**刺**青魔法 (Tattoo Magic)**`
        整体当非法包裹吞掉"刺"，标题变"青魔法"。I 簇须先消耗行首 `**` 包裹形态。
        """
        text = (
            "**刺青魔法（****Tattoo \n"
            "Magic****）****尽管几乎所有已知的文明都有进行刺青的仪式\n"
        )
        normalized = spell_format.normalize(text)
        assert "**刺青魔法 (Tattoo Magic)**" in normalized, (
            f"OA 标题前置字被吞: {normalized!r}"
        )
        assert "**青魔法" not in normalized, f"标题仍被吞字: {normalized!r}"

    def test_reverse_fallback_no_same_line_title_swallow(self, spell_format: SpellFormat):
        """反向兜底不吞同行合法标题（KN023 第 5 处根因，page_782/787 实证）。

        `**中文 (English)**` 合法标题 + 同行长正文，若正文后续出现 `(...)**`
        形态（如 `**先决条件 (Requirements)**`），旧 group1 `[^\n*]*` 把含括号
        的标题吞下，整段 `**灰花匠 (Gray Gardener)**在伽尔特…(Requirements)**`
        被当非法包裹替换，标题丢失。group1 排除括号字符后不触发。
        """
        text = (
            "**灰花匠 (Gray Gardener)**在伽尔特 (Galt)，作为红色革命 (Red "
            "Revolution)前期的那些时光带来的秘密组织。扩展阅读请看"
            "[伽尔特](http://www.goddessfantasy.net/bbs/index.php?topic=29733.0)"
            "**生命骰 (Hit Die)：**d8**先决条件 (Requirements)**要成为灰花匠\n"
        )
        normalized = spell_format.normalize(text)
        assert "**灰花匠 (Gray Gardener)**" in normalized, (
            f"同行标题被反向兜底吞: {normalized!r}"
        )
        assert "在伽尔特 (Galt)" in normalized, f"同行正文被吞: {normalized!r}"
        assert "先决条件 (Requirements)" in normalized, f"字段被吞: {normalized!r}"


class TestBareTitleProseGuard:
    """KN019 D 类：_wrap_bare_spell_titles 误包正文首段（2026-08-04 修复）

    正文行（行首无缩进 + 行尾英文括号）被 bare_pattern 包星 → split 当标题，
    正文与法术名失联（坐骑术/星界投射/魔法恒定术等 20 条第一类）。
    守卫：候选行「前一非空行是表格行 或 组1 含正文句特征（主语/逗号/( 开头/数字）」+
    「紧邻后行是正文续行」→ 判正文首段，不包星。
    """

    def test_mount_statblock_following_prose_not_wrapped(self, spell_format):
        """坐骑术形态：stat block 表格后正文首段（行尾英文括号）不包星"""
        text = (
            "**坐骑术 (Mount)**\n"
            "| 环位 | 咒法 1 |\n"
            "| --- |\n"
            "\n"
            "\n"
            "你召唤出一匹轻型马 (light horse) 或矮种马 (pony) \n"
            "来作为坐骑使用 (种类由你选择)。这些坐骑会提供自愿而良好的服务。\n"
        )
        normalized = spell_format.normalize(text)
        assert "**你召唤出一匹轻型马" not in normalized, (
            f"表格后正文首段被误包星: {normalized!r}"
        )
        assert "你召唤出一匹轻型马 (light horse) 或矮种马 (pony)" in normalized

    def test_astral_projection_mid_prose_not_wrapped(self, spell_format):
        """星界投射形态：正文中正文段（主语+逗号）不包星"""
        text = (
            "**星界投射 (Astral Projection)**\n"
            "当你处在星界的时候，你的星界身体和你的肉体之间始终以一根虚体银线 (incorporeal silvery cord) \n"
            "相连。如果这根银线断掉，你的星界形体和肉体都会死亡。\n"
        )
        normalized = spell_format.normalize(text)
        assert "**当你处在星界的时候" not in normalized, (
            f"正文段被误包星: {normalized!r}"
        )

    def test_permanency_cost_line_not_wrapped(self, spell_format):
        """魔法恒定术形态：正文段（主语+数字）不包星"""
        text = (
            "你可以以20000GP的代价来释放一个魔法恒定术 (Permanency) \n"
            "以恒定这个法术的效果。如果你通过多次施放本法术来扩大一个半位面。\n"
        )
        normalized = spell_format.normalize(text)
        assert "**你可以以20000GP" not in normalized, f"正文段被误包星: {normalized!r}"

    def test_paren_leading_prose_line_not_wrapped(self, spell_format):
        """( 开头正文段（触发术/沉默术形态）不包星"""
        text = (
            "(spell activation) 或法术完成型 (spell completion) \n"
            "魔法物品的能力，就好像你的职业能力里不再具有那些法术一般。\n"
        )
        normalized = spell_format.normalize(text)
        assert "**(spell activation)" not in normalized, f"正文段被误包星: {normalized!r}"

    def test_valid_bare_title_isolated_still_wrapped(self, spell_format):
        """合法裸标题（UC 格式，后行空）保持包星"""
        text = "超越之障 (Ablative Barrier)\n\n下一段正文。\n"
        normalized = spell_format.normalize(text)
        # 包星输出为 **中文  (English)**（group1 贪婪吞括号前空格，既有行为）
        assert "**超越之障" in normalized and "(Ablative Barrier)**" in normalized, (
            f"合法标题未包星: {normalized!r}"
        )

    def test_title_after_table_blank_lines_still_wrapped(self, spell_format):
        """表格后空行隔离的合法标题（page_854 形态）保持包星"""
        text = (
            "| 环位 | 咒法 9 |\n"
            "| --- |\n"
            "\n\n\n\n"
            "【塑能】联系怪诞存在 II(Contact Entity II) \n"
            "\n"
        )
        normalized = spell_format.normalize(text)
        # 【塑能】前缀已被 _unify_school_bracket_titles 剥离（既有行为），
        # 核心断言：表格后空行隔离的合法标题仍被包星
        assert "**联系怪诞存在 II" in normalized, (
            f"合法标题被误跳过: {normalized!r}"
        )

    def test_enumeration_continuation_line_not_wrapped(self, spell_format):
        """枚举行续段（(Miracle)，移除诅咒 后行续枚举）不包星"""
        text = (
            "破除结界 (Break enchantment)、复原术 (Restoration)\n"
            "(Miracle)，移除诅咒 (Remove Curse) \n"
            "或者祈愿术 (Wish) \n"
            "移除，但是由于脱水而遭受的效果必须通过正常的途径治愈。\n"
        )
        normalized = spell_format.normalize(text)
        assert "**(Miracle)" not in normalized, f"枚举续段被误包星: {normalized!r}"

    def test_statblock_prose_merges_into_spell_chunk(self, spell_format):
        """集成：坐骑术 normalize + split 后正文并入法术 chunk，无伪标题"""
        text = (
            "**坐骑术 (Mount)**\n"
            "| 环位 | 咒法 1 |\n"
            "| --- |\n"
            "\n"
            "你召唤出一匹轻型马 (light horse) 或矮种马 (pony) \n"
            "来作为坐骑使用 (种类由你选择)。\n"
        )
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        # 无伪标题
        assert not any("你召唤出一匹轻型马" in n for n in names), (
            f"伪标题残留: {names}"
        )
        # 坐骑术 chunk 含正文
        mount = next((it for it in items if "坐骑术" in it["name"]), None)
        assert mount is not None, f"坐骑术缺失: {names}"
        assert "你召唤出一匹轻型马" in mount["text"], (
            f"正文未并入坐骑术 chunk: {mount['text'][:120]!r}"
        )

    # ===== KN019 第二类：跨行 HTML 残留（2026-08-04 修复）=====
    def test_page1177_cn_period_prose_line_not_wrapped(self, spell_format):
        """page_1177 形态：<b> 跨行粗体残留（组1 含中文句号「。」）不包星

        源形态：**诅咒法术⏎施法者们在烦扰别人上创意无限。**【死灵】(Calamitous Flailing)[诅咒]⏎| 环位 | …
        表格行存在时 [诅咒] 类型括号被剥离 → 行尾变英文括号命中 bare_pattern，
        且句号不在弱特征词表 → 连 prose_marker 都未命中 → 页引言被包星成伪标题
        （page_1177_0000）。强特征「含。」直接判正文段。
        """
        text = (
            "**诅咒法术\n"
            "施法者们在烦扰别人上创意无限。**【死灵】(Calamitous Flailing)[诅咒]\n"
            "| 环位 | 诅咒 1 |\n"
        )
        normalized = spell_format.normalize(text)
        assert "**施法者们在烦扰别人上创意无限" not in normalized, (
            f"页引言被误包星: {normalized!r}"
        )

    def test_page1365_crossline_star_prose_not_wrapped(self, spell_format):
        """page_1365 形态：<i> 跨行斜体残留（组1 以逗号「，」开头）不包星

        源形态：这个法术类似***召唤怪物****** ⏎I(summon monster I) ***，除了你可以召唤1个小巨灵（janni）
        弱特征命中但后行是空行 → 后行判据失败 → 续段被包星。强特征「，」开头
        跳过后的行判据直接判正文段。
        """
        text = (
            "这个法术类似***召唤怪物****** \n"
            "I(summon monster I) ***，除了你可以召唤1个小巨灵（janni）\n"
        )
        normalized = spell_format.normalize(text)
        # 断言：不存在以 **，除了 开头的独立行（伪标题形态）
        assert not any(l.startswith("**，除了") for l in normalized.split("\n")), (
            f"续段被误包星: {normalized!r}"
        )

    def test_page1365_long_crossline_star_prose_not_wrapped(self, spell_format):
        """page_1365 长变体：1D4+1 形态续段（组1 逗号开头）不包星"""
        text = (
            "这个法术类似***次级召唤巨灵******(lesser \n"
            "summon genie) ***，除了你可以召唤1D4+1个小巨灵（janni）或者1D3个风巨灵（djinni）或者1个土巨灵（shaitan）**\n"
        )
        normalized = spell_format.normalize(text)
        # 断言：不存在以 **，除了 开头的独立行（伪标题形态）
        assert not any(l.startswith("**，除了") for l in normalized.split("\n")), (
            f"续段被误包星: {normalized!r}"
        )

    def test_page1177_calamitous_flailing_cn_name_join(self, spell_format):
        """KN019 第二类闭环：跨行英文名补中文名后 → 合法标题

        源形态（page_1177 修复后）：**诅咒法术⏎施法者们在烦扰别人上创意无限。**⏎【死灵】手舞足蹈(Calamitous ⏎Flailing)[诅咒]
        英文名跨行（CHM 折行残留）但「_unify_school_bracket_titles」用 \\s* 跨行
        拼接 + 中文名 → 归一化成 **手舞足蹈 (Calamitous Flailing)** 合法标题，
        使 stat block 有归属（修复前无中文名 → 无法归一化 → 整块 split_drop 丢失）。
        """
        text = (
            "**诅咒法术\n"
            "施法者们在烦扰别人上创意无限。**【死灵】手舞足蹈(Calamitous \n"
            "Flailing)[诅咒]\n"
            "| 环位 | 诅咒 1 |\n"
        )
        normalized = spell_format.normalize(text)
        assert "**手舞足蹈 (Calamitous Flailing)**" in normalized, (
            f"补中文名后应归一化成合法标题: {normalized!r}"
        )
        # 引言仍不被包星（._wrap_bare_spell_titles 守卫对修复形态同样生效）
        assert "**施法者们在烦扰别人上创意无限" not in normalized, (
            f"页引言被误包星: {normalized!r}"
        )

    def test_page1177_calamitous_flailing_no_cn_name_not_wrapped(self, spell_format):
        """跨行英文名 + 无中文名：不产生伪标题（守卫对跨行形态同样生效）

        修复前源形态（无中文名）：【死灵】(Calamitous ⏎Flailing) 无中文名无法
        归一化 → 不包星成伪标题，也不产生半截「**手舞足蹈」标题。
        """
        text = (
            "**诅咒法术\n"
            "施法者们在烦扰别人上创意无限。**【死灵】(Calamitous \n"
            "Flailing)[诅咒]\n"
            "| 环位 | 诅咒 1 |\n"
        )
        normalized = spell_format.normalize(text)
        assert not any(l.startswith("**手舞足蹈") for l in normalized.split("\n")), (
            f"无中文名不应产出半截标题: {normalized!r}"
        )
        assert "**施法者们在烦扰别人上创意无限" not in normalized, (
            f"页引言被误包星: {normalized!r}"
        )
