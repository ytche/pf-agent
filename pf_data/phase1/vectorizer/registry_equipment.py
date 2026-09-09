"""registry_equipment.py — 装备模块规范字段注册表（M2 元数据设计定稿）

职责：
  - 定义规范字段（M2 §二：10 规范字段 + extra 保真）
  - 中文标签 → 规范 key 映射（含全角/同义变体归一，M2 决策 5）
  - 奇物 slot 13 枚举（M2 §三 3.1，CHM TOC L4 权威词表）
  - component_type 枚举（M2 §四：16 主类 + 3 辅助）
  - field_status 合法值（沿用专长/技能三态，去 ambiguous）

所有字段标签硬编码集中于此。formats/equipment.py 与 processors/equipment.py
从此处引用，不再各自维护独立的标签列表。长标签优先（-len 排序）防止
"价格" 误匹配 "价格调整"/"装备价格调整" 前缀吞并（勘探实测变体）。
"""

# ---- M2 §二 规范字段（10）----

EQUIP_CANONICAL_FIELDS: tuple[str, ...] = (
    "item_name", "english_name", "slot", "subcategory",
    "price", "weight", "aura", "caster_level",
    "craft_cost", "craft_conditions", "craft_requirements",
    "damage", "critical",
)

# ---- 规范字段 → 中文标签变体（含全角/同义归一，决策 5）----
# 勘探 field_labels_seen 97 种标签聚合（2026-08-08）：高频归一进规范字段，
# 低频散字段（毒药/栽培/科技/武器组等）进 metadata.extra 原文保真（§二 2.5）。
# 归一方向：全角（ＣＬ→CL、灵氲→灵光）+ 同义（制造成本/制作成本/成本/花费/
# 价钱→craft_cost；制造条件/制作条件/建造条件→craft_conditions；制造要求/
# 制造需求/制作需求/制作要求/制造→craft_requirements）。
# 「花费」实证（2026-08-08 全库 186 处 83% 制造行语境）归 craft_cost：
# ISG 条目 `制造需求：**…**花费：**XGP**` 的「花费」= 制造成本（条目行
# 字段链已有 `**价格：**` 零售价），归 price 会覆盖零售价（seed_12/14 回归）

EQUIP_FIELD_LABEL_ALIASES: dict[str, list[str]] = {
    "price":             ["价格", "价格（GP）", "价钱", "价值", "价格调整",
                          "装备价格调整"],
    "weight":            ["重量", "重量（磅）", "全重"],
    "aura":              ["灵光", "灵氲", "光环"],
    "caster_level":      ["施法者等级", "CL", "cl", "ＣＬ", "制造DC"],
    "craft_cost":        ["制造成本", "制作成本", "成本", "花费", "制造花费", "制作花费",
                          "成本（GP）", "制造成本与需求", "自我值"],
    "craft_conditions":  ["制造条件", "制作条件", "建造条件"],
    "craft_requirements": ["制造要求", "制造需求", "制作需求", "制作要求", "制造",
                          "栽培要求"],
    "damage":            ["伤害", "伤害（S）", "伤害（M）", "小型伤害", "中型伤害",
                          "伤害类型"],
    "critical":          ["重击", "重击倍数", "重击范围"],
    "slot":              ["位置", "栏位", "装备位置", "槽位", "部位"],
    # 「类型」不入 subcategory：毒药家族 `**类型** 毒素，接触…`（B 形态
    # 空格值）是独立低频散字段，须走 EQUIP_EXTRA_FIELD_LABELS 保真 key
    # （seed_01 断言 `fields["类型"]`；若归入 subcategory 则 KeyError）
    # 「物品」剔除（M6 KN 噪鸣纸值内误切）：`_expand_inline_bare_segs`
    # 值内裸标签段扫描（`_RE_BARE_NOCOLON_SEG` 值前瞻含 `，`）把需求值
    # `制造奇物，*活化物品，魔嘴术*` 的「物品」切成 subcategory 标签 →
    # 值断成 `制造奇物，*活化` + `，魔嘴术*` 两段；全库实证「物品」作为
    # 字段标签 0 处真用法（66 处均为正文「正常物品：」），别名纯误登记
    "subcategory":       ["分类", "种类", "类别", "物品类型"],
}

# ---- 低频散字段词表（extra 保真，不建 schema 约束，决策 5）----
# 毒药家族：类型/豁免/频率/痊愈/潜伏期/成瘾性/发作频率/初始效果/后续效果/
# 工艺DC/破坏DC/强韧DC/豁免DC/效果/需求/描述
# 栽培家族：栽培成本/采集DC/产量/制备
# 武器家族：射程/硬度/生命值/护甲加值/最大敏捷加值/防具检定减值/奥术失败机率/
# 速度/容弹量/哑火/易碎/武器组/材质/弹药
# 其他：摧毁/毁灭/历史/共振/阵营/感官/语言/属性/时间/效果名/来源/出处
EQUIP_EXTRA_FIELD_LABELS: tuple[str, ...] = (
    "类型", "豁免", "频率", "痊愈", "潜伏期", "潜伏", "成瘾性", "发作频率",
    "初始效果", "后续效果", "工艺DC", "破坏DC", "强韧DC", "豁免DC", "效果",
    "需求", "描述", "栽培成本", "采集DC", "产量", "制备", "射程", "硬度",
    "生命值", "护甲加值", "最大敏捷加值", "防具检定减值", "奥术失败机率",
    "速度", "容弹量", "哑火", "易碎", "武器组", "材质", "弹药", "摧毁",
    "毁灭", "历史", "共振", "阵营", "感官", "语言", "属性", "时间", "效果名",
    "来源", "出处", "制作时间", "配方", "工具", "先决条件", "制造奇物",
    "法术效果", "战役用途", "缺点", "缺陷", "形状", "声望", "概率", "条件",
    "使用", "需要", "消耗", "造物", "治愈", "医疗", "工艺", "强韧", "介绍",
    "龙骨", "故障", "能力", "武器与防具", "距离", "特殊",
)

# ---- 全量中文标签（展平去重，长标签优先）----

_ALL_LABELS_SET: set[str] = set()
for _aliases in EQUIP_FIELD_LABEL_ALIASES.values():
    _ALL_LABELS_SET.update(_aliases)
_ALL_LABELS_SET.update(EQUIP_EXTRA_FIELD_LABELS)

ALL_EQUIP_FIELD_LABELS: list[str] = sorted(
    _ALL_LABELS_SET,
    key=lambda x: (-len(x), x),  # 长标签优先，同长按字母序
)

# ---- 中文标签 → 规范 key 反向映射（含别名）----

EQUIP_LABEL_TO_KEY: dict[str, str] = {}
for _key, _labels in EQUIP_FIELD_LABEL_ALIASES.items():
    for _label in _labels:
        EQUIP_LABEL_TO_KEY[_label] = _key

# ---- 奇物 slot 13 枚举（M2 §三 3.1，CHM TOC L4 权威词表）----
# 2026-08-09 M5 对齐：采用 CHM TOC L4 实际词形（腰部/躯体/…，page_223~234
# 标题）——元数据设计 §三 3.1 的「腰/躯/…」是勘探摘要简化词形，产物/源数据
# 用 CHM 词形；简化词形与译注变体由 processor 层 _EQUIP_SLOT_ALIASES 归一。

EQUIP_SLOT_VALUES: tuple[str, ...] = (
    "腰部", "躯体", "胸部", "眼部", "脚部", "手部", "头部", "头饰",
    "颈部", "肩部", "腕部", "戒指", "无",
)

# ---- component_type 枚举（M2 §四：16 主类 + 3 辅助，人工门 2 拍板）----

EQUIP_COMPONENT_TYPES: tuple[str, ...] = (
    # 主类 16
    "weapon", "armor", "ammo", "gear", "alchemical_item",
    "potion_scroll_wand", "ring", "rod", "staff", "wondrous_item",
    "cursed_item", "intelligent_item", "artifact", "enchantment",
    "magic_plant", "equipment_package",
    # 辅助 3（降权）
    "equipment_intro", "equipment_index", "equipment_rule",
)

# ---- 附魔目标枚举（M2 §三 3.2）----

EQUIP_ENCHANTMENT_TARGETS: tuple[str, ...] = (
    "armor", "shield", "weapon", "ammo", "special",
)

# ---- field_status 合法值（三态，沿用专长/技能，去 ambiguous）----

EQUIP_FIELD_STATUS_VALUES: set[str] = {
    "parsed",           # 字段成功解析，值非空
    "missing",          # 源文本中未找到该字段
    "not_applicable",   # 该条目不适用此字段（如普通武器无 aura；非奇物无 slot）
}
