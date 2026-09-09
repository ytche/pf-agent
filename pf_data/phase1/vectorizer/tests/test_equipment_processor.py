"""
test_equipment_processor.py — equipment processor 层 TDD 测试

M5 用户拍板（2026-08-09）：
- CHM 大页对齐 D4：page_220→ring、221→rod、222→staff、947→cursed_item、
  948→intelligent_item、949→artifact、946→equipment_package、234→wondrous_item
  （书聚合混合文件维持 wondrous_item 吸收 + slot 区分）
- slot 严格 13 枚举（CHM TOC L4 词形：腰部/躯体/胸部/眼部/脚部/手部/头部/
  头饰/颈部/肩部/腕部/戒指/无）：别名/括号译注/多位置取前位归一；护甲类值
  （护甲/盾牌/盔甲/铠甲）→ armor 类；其余非奇物值（—/符文/武器等）→ 不设
  slot 键（field_status=not_applicable）

断言对象：processors/equipment.py 的 _file_component_type（文件级类目）/
_signal_component_type（条目级信号覆盖）/ _normalize_slot（slot 严格归一）。
"""

from vectorizer.processors.equipment import (
    _SLOT_RELEVANT_CT,
    _file_component_type,
    _normalize_slot,
    _signal_component_type,
)
from vectorizer.registry_equipment import EQUIP_SLOT_VALUES


# ============================================================
#  文件级类目映射（_file_component_type）
# ============================================================


class TestFileComponentType:
    """CHM 大页映射（用户拍板「CHM 大页对齐 D4」）+ 既有文件语义不回归"""

    # (rel, 期望类目)：page 映射 8 项 + 既有文件语义 6 项
    CASES = [
        # CHM 大页映射（精确 stem，禁子串推导）
        ("装备_魔法物品/魔法物品/戒指_权杖_法杖/page_220.md", "ring"),
        ("装备_魔法物品/魔法物品/戒指_权杖_法杖/page_221.md", "rod"),
        ("装备_魔法物品/魔法物品/戒指_权杖_法杖/page_222.md", "staff"),
        ("装备_魔法物品/page_234.md", "wondrous_item"),
        ("装备_魔法物品/page_946.md", "equipment_package"),
        ("装备_魔法物品/魔法物品/page_947.md", "cursed_item"),
        ("装备_魔法物品/魔法物品/page_948.md", "intelligent_item"),
        ("装备_魔法物品/魔法物品/page_949.md", "artifact"),
        # 既有文件语义不回归
        ("装备_魔法物品/魔法物品/戒指_权杖_法杖/AA_戒指.md", "ring"),
        ("装备_魔法物品/特定魔法防具/护甲大师手册_特定魔法防具.md", "armor"),
        ("装备_魔法物品/武器/敌手指南RM_武器.md", "weapon"),
        ("装备_魔法物品/武器附魔/巨人猎手手册_武器附魔.md", "enchantment"),
        ("装备_魔法物品/魔法物品/奇物/page_223.md", "wondrous_item"),
        ("装备_魔法物品/货品服务/page_210.md", "gear"),
    ]

    def test_page_mapping(self):
        for rel, expect in self.CASES:
            assert _file_component_type(rel) == expect, (
                f"{rel} 应 {expect}，实际 {_file_component_type(rel)}")


# ============================================================
#  条目级信号覆盖（_signal_component_type）
# ============================================================


class TestSignalComponentType:
    """slot 信号严格化：13 枚举值 → wondrous_item（仅 gear/wondrous 默认类）；
    护甲类值 → armor；专属类不被 slot 信号覆盖"""

    def test_slot_enum_gear_default(self):
        # gear 默认 + slot=戒指 → 奇物
        assert _signal_component_type({"slot": "戒指"}, "gear") == "wondrous_item"

    def test_slot_enum_special_class_no_override(self):
        # ring 专属类不被 slot 信号覆盖（M5 拍板：CHM 大页对齐 D4）
        assert _signal_component_type({"slot": "戒指"}, "ring") == "ring"
        assert _signal_component_type({"slot": "无"}, "staff") == "staff"
        assert _signal_component_type({"slot": "无"}, "artifact") == "artifact"

    def test_armor_slot_keeps_armor(self):
        # 特定魔法防具文件级 armor + slot=护甲 → armor（修复：信号曾覆盖成 wondrous）
        assert _signal_component_type({"slot": "护甲"}, "armor") == "armor"

    def test_armor_slot_from_gear(self):
        # 书聚合护甲条目（ISC_魔法护甲和盾牌 默认 gear）→ armor
        assert _signal_component_type({"slot": "护甲"}, "gear") == "armor"
        assert _signal_component_type({"slot": "盾牌"}, "gear") == "armor"
        assert _signal_component_type({"slot": "盔甲"}, "wondrous_item") == "armor"
        assert _signal_component_type({"slot": "铠甲"}, "gear") == "armor"

    def test_invalid_slot_keeps_default(self):
        # 无法归一值（—/符文/武器）→ 保持文件级默认（不误判奇物）
        assert _signal_component_type({"slot": "—"}, "gear") == "gear"
        assert _signal_component_type({"slot": "符文（rune）"}, "gear") == "gear"
        assert _signal_component_type({"slot": "武器"}, "gear") == "gear"

    def test_slot_alias_enum(self):
        # 别名归一后 ∈ 枚举 → 奇物（身体→躯体）
        assert _signal_component_type({"slot": "身体"}, "gear") == "wondrous_item"

    def test_damage_signal_regression(self):
        # 伤害/重击 → weapon（M3 既有信号不回归）
        assert _signal_component_type({"damage": "1d6", "critical": "×2"}, "gear") == "weapon"

    def test_armor_field_signal_regression(self):
        # 护甲加值等字段 → armor（M3 既有信号不回归）
        assert _signal_component_type({"护甲加值": "+1"}, "gear") == "armor"

    def test_enchantment_slot_not_override(self):
        # 附魔专属目录不被 slot 信号覆盖（「无」是 13 枚举合法值但附魔无位置）
        assert _signal_component_type({"slot": "无"}, "enchantment") == "enchantment"
        assert _signal_component_type({"slot": "戒指"}, "enchantment") == "enchantment"


# ============================================================
#  奇物 slot 有效类目（_SLOT_RELEVANT_CT，M5 拍板）
# ============================================================

# slot 只对奇物语义类目有意义：非奇物类目（enchantment/weapon/armor/gear 等）
# 即使源数据写了位置值（附魔条目「位置 无」），infer_metadata 也不设 slot 键、
# field_status 置 not_applicable（verify 检查 4「enchantment 不得带 slot」断言
# 暴露 6 条后固化的防回退护栏，2026-08-09）


class TestSlotRelevantCT:
    """_SLOT_RELEVANT_CT 值域防回退：含全部奇物语义类目、不含非奇物类目"""

    def test_contains_wondrous_family(self):
        for ct in ("wondrous_item", "ring", "rod", "staff", "cursed_item",
                   "intelligent_item", "artifact", "magic_plant"):
            assert ct in _SLOT_RELEVANT_CT, f"{ct} 应有 slot 语义"

    def test_excludes_non_wondrous(self):
        for ct in ("enchantment", "weapon", "armor", "gear", "ammo",
                   "alchemical_item", "potion_scroll_wand", "equipment_package",
                   "equipment_intro", "equipment_index", "equipment_rule"):
            assert ct not in _SLOT_RELEVANT_CT, f"{ct} 不得有 slot 语义（非奇物）"


# ============================================================
#  slot 严格 13 枚举归一（_normalize_slot）
# ============================================================


class TestNormalizeSlot:
    """严格 13 枚举：直通/别名/括号译注/多位置前位/非法值 None"""

    def test_enum_direct(self):
        # 13 枚举（CHM TOC L4 词形）直通
        for v in EQUIP_SLOT_VALUES:
            assert _normalize_slot(v) == v, f"{v} 应直通"

    def test_aliases(self):
        CASES = {
            "身体": "躯体", "躯干": "躯体",
            "腰带": "腰部", "手腕": "腕部", "手": "手部", "手指": "戒指",
            "头带": "头饰", "肩膀": "肩部", "颈": "颈部", "眼睛": "眼部",
            "双脚": "脚部", "脸部": "头部",
        }
        for raw, expect in CASES.items():
            assert _normalize_slot(raw) == expect, f"{raw} 应归 {expect}"

    def test_paren_translator_note(self):
        # 括号译注剥主词
        CASES = {
            "头部（head）": "头部",
            "头饰（headband）": "头饰",
            "腕部（arm or wrist，译注：都是占据腕部栏位）": "腕部",
            "无（武器）": "无",
            "无（none）": "无",
            "无（取代一只手）": "无",
            "头部head": "头部",
            "手［注：来自早期的奇妙写法，大概是没 ，使用时拿在手上］": "手部",
        }
        for raw, expect in CASES.items():
            assert _normalize_slot(raw) == expect, f"{raw} 应归 {expect}"

    def test_multi_position_first(self):
        # 多位置取前位（CHM 位置顺序在前的为主槽位）
        CASES = {
            "颈部或肩部": "颈部",
            "腰带或肩部": "腰部",
            "头部或腰部": "头部",
            "无或颈部": "无",
            "颈部，手指或无": "颈部",
            "躯干和头部（见下文）": "躯体",
            "无，重力1磅": "无",
        }
        for raw, expect in CASES.items():
            assert _normalize_slot(raw) == expect, f"{raw} 应归 {expect}"

    def test_invalid_none(self):
        # 护甲类（归 armor 类信号，slot 不设）/ 非奇物值 → None
        for v in ("护甲", "盾牌", "盔甲", "铠甲", "—", "-", "特殊", "可变",
                  "符文（rune）", "武器", "武器附魔", "盾牌附魔"):
            assert _normalize_slot(v) is None, f"{v} 应 None"
