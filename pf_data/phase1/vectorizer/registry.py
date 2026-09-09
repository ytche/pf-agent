"""
registry.py — 法术向量化统一注册表

职责：
  - 定义 v0.3 规范字段（16 个 key）
  - 中文标签 → 规范 key 映射（含变体别名）
  - 学派白名单
  - field_status 合法值

所有字段标签硬编码集中于此。formats/spell.py 和 processors/spell.py
从此处引用，不再各自维护独立的标签列表。

用法：
  from vectorizer.registry import ALL_FIELD_LABELS, LABEL_TO_KEY, CANONICAL_SCHOOLS
"""

# ---- v0.3 规范字段 ----

CANONICAL_FIELDS: list[str] = [
    "school",
    "subschool",
    "descriptor",
    "spell_level",
    "domains",
    "subdomains",
    "casting_time",
    "components",
    "range",
    "target",
    "area",
    "effect",
    "duration",
    "saving_throw",
    "spell_resistance",
]

# ---- 规范字段 → 中文标签变体 ----
# 键 = v0.3 规范字段名，值 = 该字段在源文本中可能出现的中文标签列表

FIELD_LABEL_ALIASES: dict[str, list[str]] = {
    "school":            ["学派"],
    "subschool":         [],                         # 嵌入 school 原始值的 (...) 内
    "descriptor":        [],                         # 嵌入 school 原始值的 【】/[] 内
    "spell_level":       ["环位", "等级"],
    "domains":           ["领域"],                   # 从 spell_level 值中剥离
    "subdomains":        ["子域", "子领域"],          # 从 spell_level 值中剥离
    "casting_time":      ["施法时间", "施放时间"],
    "components":        ["成分", "法术成分", "组成部分"],
    "range":             ["范围", "射程", "距离"],
    "target":            ["目标"],
    "area":              ["区域"],
    "effect":            ["效果"],
    "duration":          ["持续时间", "持续"],
    "saving_throw":      ["豁免", "豁免检定"],
    "spell_resistance":  ["法术抗力", "抗力", "SR"],
}

# ---- 全量中文标签（展平去重，长标签优先，保证正则交替不误匹配）----
# 重要：标签用于 regex alternation (label1|label2|...) 时，
# 长标签必须排在短标签前，否则 "持续" 会误匹配 "持续时间" 的前两字。

_ALL_LABELS_SET: set[str] = set()
for _aliases in FIELD_LABEL_ALIASES.values():
    _ALL_LABELS_SET.update(_aliases)

ALL_FIELD_LABELS: list[str] = sorted(
    _ALL_LABELS_SET,
    key=lambda x: (-len(x), x),  # 长标签优先，同长按字母序
)

# ---- 额外格式标签（非 v0.3 规范字段，仅格式修复方法使用）----

EXTRA_FORMAT_LABELS: list[str] = [
    "诡计描述",
    "伪装对象",
    "描述",     # 源数据中出现但不映射到 v0.3 字段
]

# ---- 中文标签 → 规范 key 反向映射 ----
# 用于 parse_fields() 中将 **标签：** 值 映射到规范字段名

LABEL_TO_KEY: dict[str, str] = {}
for _key, _labels in FIELD_LABEL_ALIASES.items():
    for _label in _labels:
        LABEL_TO_KEY[_label] = _key


# ---- 规范 key → 规范中文标签（首个别名即为规范标签）----
# 用于把别名标签归一化为规范标签，避免 IR 中混入 施放时间/持续/抗力 等别名。

CANONICAL_LABEL: dict[str, str] = {
    _key: _labels[0] for _key, _labels in FIELD_LABEL_ALIASES.items() if _labels
}

# 别名 → 规范中文标签（用于裸标签归一化）
# F2 范围：仅 casting_time/duration/spell_resistance 的别名需要归一化为规范标签。
# 其他别名（如 等级↔环位）保持不变，因为两种写法在源数据中均常见。
_LABEL_ALIAS_NORMALIZE_KEYS: frozenset[str] = frozenset({
    "casting_time",
    "duration",
    "spell_resistance",
})
LABEL_ALIAS_TO_CANONICAL: dict[str, str] = {}
for _key, _labels in FIELD_LABEL_ALIASES.items():
    if _key not in _LABEL_ALIAS_NORMALIZE_KEYS:
        continue
    canonical = _labels[0] if _labels else None
    if not canonical:
        continue
    for _label in _labels:
        if _label != canonical:
            LABEL_ALIAS_TO_CANONICAL[_label] = canonical


# ---- 学派白名单 ----
# 核心 8 + 通用，允许扩展（如元素学派、七罪魔法）

CANONICAL_SCHOOLS: set[str] = {
    "防护系", "咒法系", "预言系", "惑控系", "塑能系",
    "幻术系", "死灵系", "变化系", "通用",
}

# 学派简称 → 全称映射
SCHOOL_ABBR_MAP: dict[str, str] = {
    "防护": "防护系", "咒法": "咒法系", "预言": "预言系",
    "惑控": "惑控系", "塑能": "塑能系", "幻术": "幻术系",
    "死灵": "死灵系", "变化": "变化系",
    # 别名 → 规范名
    "附魔": "惑控系", "附魔系": "惑控系",
    "通用系": "通用", "变形系": "变化系",
}

# ---- field_status 合法值 ----

FIELD_STATUS_VALUES: set[str] = {
    "parsed",           # 字段成功解析，值非空
    "missing",          # 源文本中未找到该字段
    "not_applicable",   # 该法术不适用此字段（如无 area/effect/subschool）
    "ambiguous",        # 解析到值但无法确定映射（如未知学派/子学派）
}


# ---- 向后兼容：标签分组 ----
# formats/spell.py 中原有 9 处硬编码标签列表，现统一从此处引用。
# 各方法需要不同的标签子集（如某些方法排除"等级"、"描述"）。

# ---- F2-inline 裸标签别名 ----
# 用于 formats/spell.py _unify_field_labels 的行内裸标签边界检测。
# 从 LABEL_ALIAS_TO_CANONICAL 的 keys 派生（施放时间/持续/抗力），
# 长标签优先防止正则前缀吞并（如 施放时间 在 施放 之前）。
# 不在 formats 层维护字面标签列表——此处是唯一来源。

F2_INLINE_ALIAS_LABELS: list[str] = sorted(
    LABEL_ALIAS_TO_CANONICAL.keys(),
    key=lambda x: (-len(x), x),
)

# LEGACY 13 标签规范集（用于 _unify_field_labels、compute_census、_fix_split_titles 等）
LEGACY_13_LABELS: list[str] = [
    "学派", "环位", "等级", "施法时间", "成分", "范围", "距离",
    "目标", "效果", "持续时间", "豁免", "法术抗力", "描述",
]

# Legacy 13 标签减"等级"（用于 _merge_bold_field_lines 和 _merge_pipe_table_lines
# 中检测字段标签行时，"等级"从不出现在这些格式中）
LEGACY_LABELS_NO_LEVEL: list[str] = [
    x for x in LEGACY_13_LABELS if x != "等级"
]

# Legacy 13 + 格式修复专用标签（用于 _fix_ff_space_inline_fields、_fix_bare_inline_fields）
LEGACY_EXPANDED_LABELS: list[str] = LEGACY_13_LABELS + [
    "诡计描述", "伪装对象", "施放时间", "持续",
]

# Legacy 13 + 格式修复专用标签不含"施放时间"/"持续"（用于 _fix_inline_compact）
LEGACY_INLINE_COMPACT_LABELS: list[str] = LEGACY_13_LABELS + [
    "诡计描述", "伪装对象",
]

# KN012：行内粘连别名标签（bold 别名 施放时间/持续/抗力/SR/区域/射程 等）
# 仅用于 _fix_inline_compact 的 Step 2/3 — Step 4 不扩展（避免散文中 **抗力** 误拆）
# R6：从所有 FIELD_LABEL_ALIASES 的值派生（而非仅 LABEL_ALIAS_TO_CANONICAL），
# 以覆盖 区域(area)、射程(range) 等字段别名在行内粘连中的拆行需求。
# 不在 formats 层维护字面列表。
_ALL_INLINE_ALIAS_LABELS: set[str] = set()
for _v in FIELD_LABEL_ALIASES.values():
    for _label in _v:
        _ALL_INLINE_ALIAS_LABELS.add(_label)
INLINE_COMPACT_ALIAS_LABELS: list[str] = sorted(
    _ALL_INLINE_ALIAS_LABELS,
    key=lambda x: (-len(x), x),
)
LEGACY_INLINE_COMPACT_STEP23_LABELS: list[str] = (
    LEGACY_INLINE_COMPACT_LABELS + INLINE_COMPACT_ALIAS_LABELS
)
