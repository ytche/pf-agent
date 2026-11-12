"""KN235 白盒测试：equipment chunking 价目表章节标题/材料变体守卫。

登记口径（docs/已知问题记录.md KN235）：DVG-003 定性 equipment chunks 混入
非确切条目名的 gear chunk。守卫三件套（formats/equipment.py）：
1. `_CHM_GOODS_SECTION_TITLES`（跨页章节级通用名名单，同
   _CHM_LEGENDARY_SECTIONS 先例）——IOUN/joined-FULL/FULL/CHM_TITLE/
   BARE_STAR/TAIL 六处开条目分支命中 → 降级 category（processor 层
   equipment_intro），不标 gear/weapon/armor；
2. `material_variants`（表格首列「父名（变体名）」数据驱动登记，全库唯一
   page_209 `| 火纹钢 (冰纹钢) |`）——变体详述标题 sink 并入父条目；
3. registry `购买价格` → price 别名 + `费用` EXTRA 保真词——
   UE 交通工具 `购买价格：100gp；费用：3cp` 不再被 TAIL 回拨拆出
   title=购买 伪条目，price 值也不被 `；费用：…` 污染。

本文件补正/反例边界（coder 批次未给守卫单元测试）。
KN235 遗留③⑤（2026-09-22 拍板修复）同文件补测：
3. `_CHM_GOODS_SECTION_TITLES` 增补 4 个规则说明段标题（page_212
   使用毒药/制作毒药/使用烟花/进阶烟花工艺）→ equipment_intro；
4. `_CHM_SUBSECTION_SINK_TITLES`（炼金配方星壳小节标签）→ sink
   并入父条目 text，不开独立条目。
"""

import pytest

from vectorizer.formats.equipment import (
    EquipmentFormat, _CHM_GOODS_SECTION_TITLES,
)


def _split(text: str, source: str = "货品服务/page_211.md"):
    return EquipmentFormat().split_into_items(text, source_name=source)


class TestGoodsSectionDemotion:
    def test_chm_title_section_demoted(self):
        # `**住宿与服务LODGING AND SERVICES**` 章节头 → category 非 item
        items = _split(
            "| 住宿与服务 | 价格 |\n"
            "| --- | --- |\n"
            "| 冷水浴 | 2cp |\n"
            "**住宿与服务LODGING AND SERVICES**\n"
            "在典型的城市或者小镇的住宿与服务的价格。\n"
            "冷水浴Bath (cold)   2cp\n"
        )
        sec = [i for i in items if i["title"] == "住宿与服务"]
        assert len(sec) == 1
        assert sec[0]["type"] == "category"
        assert "冷水浴Bath (cold)" in sec[0]["text"]

    def test_ioun_shaped_service_entry_demoted(self):
        # `**医生DOCTOR**`（无括号中文+英文紧邻，恰落 IOUN 形态）→ category
        items = _split(
            "| 服务 | 价格 |\n"
            "| --- | --- |\n"
            "| 医生 | 1gp |\n"
            "**医生DOCTOR**\n"
            "价格 1 gp\n"
            "医生是熟练使用非法术的治疗和药物的人。\n"
        )
        doc = [i for i in items if i["title"] == "医生"]
        assert len(doc) == 1
        assert doc[0]["type"] == "category"
        assert "熟练使用非法术" in doc[0]["text"]

    def test_full_section_demoted(self):
        items = _split(
            "| 交通工具 | 价格 |\n"
            "| --- | --- |\n"
            "| 四轮马车 | 100gp |\n"
            "**交通工具（Transports）**\n"
            "你可以购买一台完整的交通工具。\n"
        )
        sec = [i for i in items if i["title"] == "交通工具"]
        assert len(sec) == 1 and sec[0]["type"] == "category"

    def test_bare_star_section_demoted(self):
        items = _split(
            "| 毒药 | 价格 |\n"
            "| --- | --- |\n"
            "| 黑莲汁 | 4500gp |\n"
            "**毒药**\n"
            "毒药是一类用来克服负面环境的物质。\n",
            source="货品服务/page_212.md",
        )
        sec = [i for i in items if i["title"] == "毒药"]
        assert len(sec) == 1 and sec[0]["type"] == "category"

    def test_tail_slash_section_demoted(self):
        # 210 工具包家族：正文行 `工具包/箱：这部分包括…` 被 `/` 出处
        # 信号误开 → 降级 category
        items = _split(
            "| 工具包 | 价格 |\n"
            "| --- | --- |\n"
            "| 炼金术士工具包 | 20gp |\n"
            "工具包/箱：这部分包括了一些为各类职业所预选的装备组件。\n",
            source="货品服务/page_210.md",
        )
        sec = [i for i in items if i["title"] == "工具包"]
        assert len(sec) == 1 and sec[0]["type"] == "category"

    @pytest.mark.parametrize("title", ["四轮马车", "诱饵戒指", "精金", "黑莲汁"])
    def test_real_items_unaffected(self, title):
        assert title not in _CHM_GOODS_SECTION_TITLES


class TestMaterialVariantMerge:
    def test_variant_merged_into_parent(self):
        items = _split(
            "| 材料 | 弹药 | 轻甲 |\n"
            "| --- | --- | --- |\n"
            "| 火纹钢 (冰纹钢) | 每发+15gp | +1000gp |\n"
            "**火纹钢 (Fire-Forged Steel)**\n"
            "火纹钢能引导热量离开从而保护穿戴者。\n"
            "**冰纹钢 (Frost-Forged Steel)**\n"
            "这种材料和火纹钢有着相同的源头。\n"
            "冰纹钢制作的武器防具一定是精制品。\n",
            source="武器_防具/page_209.md",
        )
        by_title = {i["title"]: i for i in items}
        assert list(by_title) == ["", "火纹钢"]
        assert "相同的源头" in by_title["火纹钢"]["text"]
        assert "一定是精制品" in by_title["火纹钢"]["text"]

    def test_variant_map_from_table_row_only(self):
        # 无「父名（变体名）」表格登记时，同名标题仍是独立条目
        items = _split(
            "**火纹钢 (Fire-Forged Steel)**\n"
            "火纹钢能引导热量离开。\n"
            "**冰纹钢 (Frost-Forged Steel)**\n"
            "这种材料和火纹钢有着相同的源头。\n",
            source="武器_防具/page_209.md",
        )
        by_title = {i["title"]: i for i in items}
        assert list(by_title) == ["火纹钢", "冰纹钢"]


class TestRuleSectionDemotion:
    """KN235 遗留③：page_212 规则说明段（使用毒药/制作毒药/使用烟花/
    进阶烟花工艺）是规则小节标题而非物品 → 与价目表章节同款降级
    category（equipment_intro），不标 gear。标题已入
    _CHM_GOODS_SECTION_TITLES（joined-FULL/FULL/CHM_TITLE 分支均判定）"""

    def test_applying_poison_joined_full_demoted(self):
        # `**使用毒药(Applying \nPoison)**` 跨行 join 后 FULL 形态
        items = _split(
            "| 黑莲汁 | 4500gp |\n"
            "| --- | --- |\n"
            "**使用毒药(Applying \nPoison)**\n"
            "一剂涂在武器上的毒药只影响单一目标。\n",
            source="货品服务/page_212.md",
        )
        sec = [i for i in items if i["title"] == "使用毒药"]
        assert len(sec) == 1
        assert sec[0]["type"] == "category"
        assert "单一目标" in sec[0]["text"]

    def test_advanced_fireworks_chm_title_demoted(self):
        # `**进阶烟花工艺 ADVANCED FIREWORK \nTECHNLOUES **` 无括号星壳
        # （CHM_TITLE 形态，断行英文 join）
        items = _split(
            "**进阶烟花工艺 ADVANCED FIREWORK \nTECHNLOUES **\n"
            "拥有工艺（炼金术）技能的角色可以使用以下进阶烟花工艺。\n",
            source="货品服务/page_212.md",
        )
        sec = [i for i in items if i["title"] == "进阶烟花工艺"]
        assert len(sec) == 1
        assert sec[0]["type"] == "category"

    @pytest.mark.parametrize(
        "title", ["使用毒药", "制作毒药", "使用烟花", "进阶烟花工艺"])
    def test_rule_sections_in_demote_list(self, title):
        assert title in _CHM_GOODS_SECTION_TITLES

    def test_real_item_named_similar_unaffected(self):
        # 「黑莲汁」等真条目紧邻规则段不受影响
        items = _split(
            "| 毒药 | 价格 |\n"
            "| --- | --- |\n"
            "| 黑莲汁 | 4500gp |\n"
            "**黑莲汁（Black Lotus Extract）**\n"
            "**价格：**4500gp\n"
            "这是最强力的毒素之一。\n",
            source="货品服务/page_212.md",
        )
        lotus = [i for i in items if i["title"] == "黑莲汁"]
        assert len(lotus) == 1 and lotus[0]["type"] == "item"


class TestRecipeSubsectionSink:
    """KN235 遗留⑤：「炼金配方」星壳小节标签（配方材料+工艺DC+时间+
    工具）sink 并入所属父条目 text，不开独立条目（同 material_variants
    并入思路，_CHM_SUBSECTION_SINK_TITLES 结构特征驱动）"""

    def test_recipe_subsection_merged_into_parent(self):
        items = _split(
            "| 毒药 | 价格 |\n"
            "| --- | --- |\n"
            "| 血呕 | 40gp |\n"
            "**血呕（Blood Gorge）**\n"
            "**价格：**40gp\n"
            "当你喝下这种糖浆般的黑色血清时。\n"
            "**炼金配方**\n"
            "**配方**（5寒铁+10月露酒）/过滤；**工艺DC** 25；"
            "**时间** 10分钟；**工具：**过滤器；**类型：**炼金药\n",
            source="货品服务/page_212.md",
        )
        by_title = {i["title"]: i for i in items}
        assert "炼金配方" not in by_title
        blood = by_title["血呕"]
        # 小节标题行 + 配方行全量保真并入父条目
        assert "**炼金配方**" in blood["text"]
        assert "（5寒铁+10月露酒）/过滤" in blood["text"]
        assert "过滤器；**类型：**炼金药" in blood["text"]

    def test_next_item_still_opens_after_recipe(self):
        # 配方 sink 后，紧随其后的下一个条目标题照常开条目
        items = _split(
            "| 毒药 | 价格 |\n"
            "| --- | --- |\n"
            "| 血呕 | 40gp |\n"
            "**血呕（Blood Gorge）**\n"
            "当你喝下这种糖浆般的黑色血清时。\n"
            "**炼金配方**\n"
            "**配方**（5寒铁+10月露酒）/过滤；**工艺DC** 25；"
            "**时间** 10分钟；**工具：**过滤器；**类型：**炼金药\n"
            "**可怖战绘（Frightful War Paint）**\n"
            "**价格：**300gp\n"
            "这种白色的膏体让你的脸看起来瘦骨嶙峋。\n",
            source="货品服务/page_212.md",
        )
        by_title = {i["title"]: i for i in items}
        assert "炼金配方" not in by_title
        assert "瘦骨嶙峋" in by_title["可怖战绘"]["text"]
        # 配方文本留在父条目而非下一个条目
        assert "寒铁" not in by_title["可怖战绘"]["text"]

    def test_recipe_label_alone_not_item(self):
        # 名单钉住：「炼金配方」在 sink 名单内
        from vectorizer.formats.equipment import _CHM_SUBSECTION_SINK_TITLES
        assert "炼金配方" in _CHM_SUBSECTION_SINK_TITLES


class TestPurchasePriceAlias:
    def test_purchase_price_line_not_pseudo_item(self):
        items = _split(
            "| 四轮马车 | 100gp |\n"
            "| --- | --- |\n"
            "**四轮马车（Carriage）**\n"
            "购买价格：100gp；费用：3cp\n"
            "这种四轮交通工具的封闭车厢中能够运输至多四人。\n",
        )
        by_title = {i["title"]: i for i in items}
        assert list(by_title) == ["", "四轮马车"]
        car = by_title["四轮马车"]
        assert car["type"] == "item"
        assert car["fields"]["price"] == "100gp"
        # 费用 = EXTRA 保真 key（乘坐费用，非物品价格）
        assert car["fields"]["费用"] == "3cp"
        assert "封闭车厢" in car["text"]

    def test_price_value_not_polluted_by_fee_seg(self):
        # `；费用：…` 段不切净时 price 值尾会被污染（回归钉住）
        items = _split(
            "| 二轮马车 | 15gp |\n"
            "| --- | --- |\n"
            "**二轮马车（Cart）**\n"
            "购买价格：15gp；费用：1cp\n"
            "一匹马或者其他驮兽便可以拉动。\n",
        )
        cart = {i["title"]: i for i in items}["二轮马车"]
        assert cart["fields"]["price"] == "15gp"
        assert cart["fields"]["费用"] == "1cp"


class TestRecipeSubsectionEdge:
    """QA 补充（KN235 遗留⑤边界）：

    coder 批次已覆盖：配方段在条目末尾、配方段后紧跟另一条目、
    名单钉住、规则段降级（joined-FULL/CHM_TITLE/名单钉住/真条目
    不受影响）。以下边界 coder 未覆盖，QA 补测钉住行为。"""

    def test_empty_recipe_section_before_next_item(self):
        # 空配方段：`**炼金配方**` 后紧跟下一条目标题（无配方行）
        items = _split(
            "| 毒药 | 价格 |\n"
            "| --- | --- |\n"
            "| 血呕 | 40gp |\n"
            "**血呕（Blood Gorge）**\n"
            "**价格：**40gp\n"
            "黑色血清。\n"
            "**炼金配方**\n"
            "**可怖战绘（Frightful War Paint）**\n"
            "**价格：**300gp\n"
            "瘦骨嶙峋。\n",
            source="货品服务/page_212.md",
        )
        by_title = {i["title"]: i for i in items}
        assert "炼金配方" not in by_title
        blood = by_title["血呕"]
        assert "**炼金配方**" in blood["text"]  # 标签行保真并入父条目
        assert "瘦骨嶙峋" in by_title["可怖战绘"]["text"]
        assert "炼金配方" not in by_title["可怖战绘"]["text"]

    def test_recipe_in_middle_body_continues_in_parent(self):
        # 配方段出现在条目中间、其后仍有该条目正文 → 后续正文
        # 不得被配方标签切断或流入下一条目
        items = _split(
            "**血呕（Blood Gorge）**\n"
            "**价格：**40gp\n"
            "第一段描述。\n"
            "**炼金配方**\n"
            "**配方**（5寒铁）/过滤；**工艺DC** 25；**时间** 10分钟；"
            "**工具：**过滤器；**类型：**炼金药\n"
            "第二段描述仍在血呕条目内。\n"
            "**可怖战绘（Frightful War Paint）**\n"
            "**价格：**300gp\n"
            "白色膏体。\n",
            source="货品服务/page_212.md",
        )
        by_title = {i["title"]: i for i in items}
        blood = by_title["血呕"]
        assert "第一段描述" in blood["text"]
        assert "第二段描述仍在血呕条目内" in blood["text"]
        assert "（5寒铁）/过滤" in blood["text"]
        assert "第二段描述" not in by_title["可怖战绘"]["text"]

    def test_recipe_label_with_tail_still_sink(self):
        # 标签带尾巴（`**炼金配方**：xxx`）→ 整行 sink，不开条目
        items = _split(
            "**血呕（Blood Gorge）**\n"
            "**价格：**40gp\n"
            "黑色血清。\n"
            "**炼金配方**：见下\n",
            source="货品服务/page_212.md",
        )
        by_title = {i["title"]: i for i in items}
        assert "炼金配方" not in by_title
        assert "见下" in by_title["血呕"]["text"]

    def test_recipe_then_rule_section_opens_category(self):
        # 配方段后紧跟规则段标题（制作毒药）→ 规则段降级 category，
        # 配方文本留在父条目，不进入 category 段
        items = _split(
            "**血呕（Blood Gorge）**\n"
            "**价格：**40gp\n"
            "黑色血清。\n"
            "**炼金配方**\n"
            "**配方**（5寒铁）/过滤；**工艺DC** 25；**时间** 10分钟；"
            "**工具：**过滤器；**类型：**炼金药\n"
            "**制作毒药**\n"
            "你可以使用工艺（炼金术）技能制作毒药。\n",
            source="货品服务/page_212.md",
        )
        by_title = {i["title"]: i for i in items}
        assert "炼金配方" not in by_title
        sec = by_title["制作毒药"]
        assert sec["type"] == "category"
        assert "工艺（炼金术）" in sec["text"]
        assert "寒铁" in by_title["血呕"]["text"]
        assert "寒铁" not in sec["text"]

    def test_bare_star_existing_hit_regression(self):
        # BARE_STAR 分支既有命中者（毒药与毒品/炼金物品）不受
        # 新增 sink 名单影响，仍开 category
        items = _split(
            "**毒药与毒品**\n"
            "以下是常见的毒药与毒品。\n"
            "**炼金物品**\n"
            "炼金物品列表。\n",
            source="货品服务/page_212.md",
        )
        by_title = {i["title"]: i for i in items}
        assert by_title["毒药与毒品"]["type"] == "category"
        assert by_title["炼金物品"]["type"] == "category"

    def test_rule_title_collision_with_full_shape(self):
        # 撞名行为钉住：`**使用烟花（Sparkler）**` FULL 形态命中降级
        # 名单 → 也降级 category（当前实现按 cn 名单判定不看形态）。
        # 若未来某书真有同名物品条目将被误降级——登记为已知残留风险。
        items = _split(
            "**使用烟花（Sparkler）**\n"
            "**价格：**5gp\n"
            "一种手持烟花。\n",
            source="货品服务/page_212.md",
        )
        sec = [i for i in items if i["title"] == "使用烟花"]
        assert len(sec) == 1 and sec[0]["type"] == "category"

    def test_recipe_label_at_page_top_opens_intro(self):
        # 配方标签出现在页首（无当前条目）→ sink 兜底开 intro，
        # 不产 title=炼金配方 的条目（行为钉住：文案进导言段）
        items = _split(
            "**炼金配方**\n"
            "**配方**（1盐）/过滤；**工艺DC** 15\n",
            source="货品服务/page_212.md",
        )
        assert all(i["title"] != "炼金配方" for i in items)
