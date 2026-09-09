"""
registry_feat.py — 专长向量化统一注册表（独立于 registry.py）

设计：
  - 法术 registry.py 属已完成冻结模块，不拆包重构；专长标签集独立于此文件，
    与 spell 侧零耦合（对齐"已完成模块冻结不重构"记忆）。
  - 职责：规范字段（14 个）、中文标签→规范 key 映射（含变体别名）、
    feat_type 白名单与归一化、field_status 合法值（三态）。
  - 标签硬编码集中于此；formats/feat.py 与 processors/feat.py 只从此处引用。

用法：
  from vectorizer.registry_feat import FEAT_LABEL_TO_KEY, FEAT_TYPES
"""

import json
import re
from pathlib import Path

# ---- feat 规范字段（专长元数据设计 §二）----

FEAT_CANONICAL_FIELDS: list[str] = [
    "feat_type",          # 类型（list；标题行括号〔战斗〕等）
    "prerequisites",      # 先决条件（结构化对象，见设计 §三）
    "benefit",            # 专长效果
    "normal",             # 通常状况（可选）
    "special",            # 特殊说明（可选）
    "source",             # 来源（引用原文）
    "task_goal",          # 任务链：专长目标
    "task_reward",        # 任务链：完成收益（含即时收益）
    "advanced_reward",    # 任务链：进阶奖励（含基础奖励，双档结构）
    "craft_cost",         # 造物：制造成本
    "craft_conditions",   # 造物：制造条件
    "craft_aura",         # 造物：灵光
    "format_cluster",     # 六放行形态（standard/whitespace/punct/lb_marker/img_marker/elided/annotation）
    "pfs_eligible",       # PFS 合法布尔（源数据 PFS 图标标记）
]

# ---- 规范字段 → 中文标签变体 ----
# 键 = 规范字段名，值 = 该字段在源文本中可能出现的中文标签列表。
# 设计 §二 别名聚合表；benefit 与 advanced_reward 均含"基础效果/进阶效果"
# 时归属 advanced_reward（基础/进阶成对出现，任务链体系），benefit 不收录。

FEAT_FIELD_LABEL_ALIASES: dict[str, list[str]] = {
    "feat_type":         ["类型"],
    "prerequisites":     ["先决条件", "前提", "前置条件", "先决", "要求", "需求", "前置", "前置需求", "条件"],
    "benefit":           ["专长效果", "效果", "好处", "收益"],
    "normal":            ["通常状况", "正常情况", "通常情况", "一般情况", "通常", "正常", "普通"],
    "special":           ["特殊说明", "特殊情况", "特殊状况", "特殊备注", "特殊"],
    "source":            ["来源", "出处", "出自", "来自", "Source"],
    "task_goal":         ["专长目标", "目标"],
    "task_reward":       ["完成收益", "即时收益", "完成奖励", "协同收益", "完成后的收益"],
    "advanced_reward":   ["进阶奖励", "进阶效果", "基础奖励", "基础效果"],
    "craft_cost":        ["制造成本", "价格", "代价"],
    "craft_conditions":  ["制造条件", "工艺", "位置"],
    "craft_aura":        ["灵光", "施法者等级"],
}

# ---- 全量中文标签（展平去重，长标签优先，保证正则交替不误匹配）----
# "效果" 是 "专长效果" 的前缀、"目标" 是 "专长目标" 的前缀——长标签必须排前。

_FEAT_ALL_LABELS_SET: set[str] = set()
for _aliases in FEAT_FIELD_LABEL_ALIASES.values():
    _FEAT_ALL_LABELS_SET.update(_aliases)

FEAT_ALL_FIELD_LABELS: list[str] = sorted(
    _FEAT_ALL_LABELS_SET,
    key=lambda x: (-len(x), x),  # 长标签优先，同长按字母序
)

# ---- 中文标签 → 规范 key 反向映射（parse_fields 用）----

FEAT_LABEL_TO_KEY: dict[str, str] = {}
for _key, _labels in FEAT_FIELD_LABEL_ALIASES.items():
    for _label in _labels:
        FEAT_LABEL_TO_KEY[_label] = _key

# ---- 规范 key → 规范中文标签（首个别名）----

FEAT_CANONICAL_LABEL: dict[str, str] = {
    _key: _labels[0] for _key, _labels in FEAT_FIELD_LABEL_ALIASES.items() if _labels
}

# ---- 额外格式标签（非规范字段，仅格式修复方法使用）----
# 前置专长/等值描述等散字段（设计 §二：低频散字段进 extra，不归一化）

FEAT_EXTRA_FORMAT_LABELS: list[str] = [
    "推荐背景",   # 任务链专长的背景推荐（page_1071）
    "描述",       # 正文描述标签（如有）
    # 服从仪典类专长（page_744 痛苦选项条目）：仪典步骤与三档神恩字段。
    # 登记后 _RE_FIELD_IN_TEXT 能识别 → 长 text 裸中文条目（FC-8n）不被
    # 子节标题过滤误删；`**标签**：` 行本身走 fallthrough 并入 text，行为不变。
    "服从仪典",
    "第一恩惠",
    "第二恩惠",
    "第三恩惠",
    # 炫耀财富（page_529）：金色粗斜体 `<B><I>` 字段段转出 `***装备位置：***`
    # → 链前部剥壳 `**装备位置：**` 独立行；登记后并入当前条目 text
    # （否则 _RE_PUNCT_TITLE 判为伪专长条目「装备位置」，split 多切 1 条）。
    "装备位置",
]

# ---- feat_type 白名单与归一化（config/feat_types.json 加载）----

_FEAT_TYPES_JSON = Path(__file__).resolve().parent / "config" / "feat_types.json"


def _load_feat_types() -> dict:
    with open(_FEAT_TYPES_JSON, encoding="utf-8") as f:
        return json.load(f)


_FEAT_TYPES_DATA = _load_feat_types()

# 规范类型白名单（未收录的类型保留原文，见 normalize_feat_type）
FEAT_TYPES: set[str] = set(_FEAT_TYPES_DATA["canonical"])

# 变体归一化映射（去"专长"后缀 / 同义词合并 / 英文变体）
FEAT_TYPE_NORMALIZE: dict[str, str] = _FEAT_TYPES_DATA["normalize"]

# 无信息量标签（剔除 = 无类型）
FEAT_TYPE_DISCARD: set[str] = set(_FEAT_TYPES_DATA["discard"])

# PFS 否定标签（「PFS不可用」等）→ pfs_eligible=false
FEAT_PFS_NEGATIVE: set[str] = set(_FEAT_TYPES_DATA["pfs_negative"])


def normalize_feat_type(raw: str) -> str | None:
    """归一化单个类型标签。

    - 变体归一化（战斗专长→战斗 / 物品制造→物品掌握 / Combat→战斗）
    - 白名单内直接返回；无信息量标签返回 None（剔除）
    - 未知类型保留原文（低频真类型候选：狐妖/地方/火/声音 等）
    """
    tag = raw.strip()
    if not tag:
        return None
    if tag in FEAT_TYPE_DISCARD:
        return None
    if tag in FEAT_TYPE_NORMALIZE:
        return FEAT_TYPE_NORMALIZE[tag]
    return tag


def split_feat_types(raw: str) -> list[str]:
    """拆分并归一化类型标签串（多标签中文逗号/顿号分隔）。

    "背叛，团队" → ["背叛", "团队"]；「PFS不可用」→ 不产标签
    （pfs_eligible=false 由调用方按 FEAT_PFS_NEGATIVE 判定）。
    """
    if not raw:
        return []
    parts = re_split_feat_types.split(raw)
    out: list[str] = []
    for p in parts:
        norm = normalize_feat_type(p)
        if norm:
            out.append(norm)
    return out


re_split_feat_types = re.compile(r"[,，、/；;]")
