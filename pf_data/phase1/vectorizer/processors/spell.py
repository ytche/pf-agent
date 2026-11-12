"""
processors/spell.py — 法术 Processor

法术模块比职业简单：
  - 无 archetype/variant 概念
  - 一个法术 = 一个 chunk（component_type = "spell"）
  - 来源书大部分从文件名即可知
  - 特有字段存 Chunk.metadata（school/level/descriptor 等）
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from vectorizer.formats.spell import SpellFormat
from vectorizer.postprocess.spell_chain import LinkMythicBaseSpells, SupplementSpellAliases
from vectorizer.processors.base import Chunk, FileProcessor
from vectorizer.processors import register
from vectorizer.processors.spell_legacy_id_map import (
    DERIVED_STATE_PATH,
    load_legacy_id_map,
    save_derived_legacy_id_map,
)
from vectorizer.registry import (
    CANONICAL_FIELDS,
    CANONICAL_SCHOOLS,
    FIELD_LABEL_ALIASES,
    LABEL_TO_KEY,
    LEGACY_13_LABELS,
    SCHOOL_ABBR_MAP,
)
from vectorizer.sources.providers import SourceContext, SourceResolver, SpellIndexProvider

logger = logging.getLogger(__name__)


# ---- module-level helpers ----

def _is_semantically_empty(val) -> bool:
    """判断值是否语义为空。

    - None → True
    - "" / 纯空白 str → True
    - [] → True
    - {} → True
    - dict 内全部值为 falsy → True
    """
    if val is None:
        return True
    if isinstance(val, str):
        return val.strip() == ""
    if isinstance(val, (list, tuple)):
        return len(val) == 0
    if isinstance(val, dict):
        if len(val) == 0:
            return True
        # 所有值都为 falsy → 语义空
        return not any(v for v in val.values())
    return False


# ============================================================
# spell_level 元数据清洗（2026-10-28 方案拍板）
# ============================================================

# R3 职业名归一表（CLASS_NAME_NORM）：仅含 2026-10-28 逐条获批的 20 组映射。
# 巡林客/导师/红螳螂杀手/召唤施/快速医疗/法术 等"不动+登记"项不得入表
# （拍板记录第 5 条红线）。归一只改 class 字符串，不动 level。
# 召唤师（Unchained）形态归一保留 Unchained 语义（全角括号规范形）。
_CLASS_NAME_NORM = {
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
    # KN245 裁定（2026-10-30）：源文件括号缩写形态，全库仅此 1 处
    # （page_1363 食尸鬼的饥饿）；「黑暗卫士」本身已是上方获批别名。
    "黑暗卫士(Blk)": "反圣武士",
    "圣骑士": "圣武士",
    "审判官": "审判者", "判官": "审判者",
    "慛眠师": "催眠师",
    "巫师": "法师",
    # KN245 获批（2026-10-29 用户逐条批准，原文证据核实）：
    "魔战": "魔战士", "密学士": "秘学士", "奥能者": "奥能师",
}

# R2 头残片机械回填白名单（KN228 模式护栏）：标题行后第一行残片形态
# `N、职业/职业 \nM` / `N, 职业/职业 \nM`（表头值跨行、首段被标题归一吞吃
# 后的残留——class 机械可证）且全链无值的条目。键=chunk_id，值=(职业串, 环级)。
# ⚠️ 重建子集声明：M11 桶清单未落盘，拍板 A 桶 560 条（COMP 457/CAMPAIGN 102）
# 无法从方案描述唯一重建（可重建机械集为 52 条本清单 / 1031 条等级行保留法
# [伴随 33 条既有值变更不可接受]）；超出本清单的可回填条目按红线停下报告，
# 差额挂 KN 待 M11 清单补登后另行批次（见 已知问题记录.md KN 登记）。
# ============================================================
# KN242 修订 1：A 桶白名单终值 556（52 已修 + 504 新回填）
# ============================================================
# 探针版 584（docs/spell/akn_a_bucket_whitelist.json）经 architect 裁定裁剪：
# 裁 25（垃圾串 19 + 表外脏名 6，登记 KN 待批）+ M1 通道接管 3（标点黏连，
# §M2 点名保留：Spell FoP_0005 / page_1365_0403 / page_1365_0404，值与
# 白名单一致，由补救通道产出）。常量值 = 词表校验 + F3 拆分 + 标点剥离 +
# CLASS_NAME_NORM 归一后的最终 items（实施时不再二次加工，物理保证
# == 白名单）。白名单外可回填条目结构性跳过（停下报告护栏）。
SPELL_LEVEL_A_BUCKET_WHITELIST = {
    "spell_Spell AArch_0001": [{"class": '德鲁伊', "level": 3}, {"class": '游侠', "level": 3}, {"class": '猎人', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_Spell AArch_0002": [{"class": '德鲁伊', "level": 5}, {"class": '猎人', "level": 5}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '女巫', "level": 5}],
    "spell_Spell AArch_0003": [{"class": '女巫', "level": 2}],
    "spell_Spell AArch_0005": [{"class": '游侠', "level": 2}, {"class": '猎人', "level": 2}],
    "spell_Spell AArch_0006": [{"class": '圣武士', "level": 4}, {"class": '游侠', "level": 4}, {"class": '猎人', "level": 4}],
    "spell_Spell AArch_0007": [{"class": '圣武士', "level": 2}, {"class": '游侠', "level": 2}, {"class": '猎人', "level": 2}],
    "spell_Spell AArch_0008": [{"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}, {"class": '女巫', "level": 4}],
    "spell_Spell AArch_0009": [{"class": '德鲁伊', "level": 1}, {"class": '圣武士', "level": 1}, {"class": '游侠', "level": 1}, {"class": '猎人', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '女巫', "level": 1}],
    "spell_Spell FoP_0000": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '德鲁伊', "level": 1}, {"class": '审判者', "level": 1}, {"class": '游侠', "level": 1}, {"class": '猎人', "level": 1}],
    "spell_Spell FoP_0001": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '圣武士', "level": 1}],
    "spell_Spell FoP_0003": [{"class": '圣武士', "level": 1}, {"class": '游侠', "level": 1}, {"class": '猎人', "level": 1}],
    "spell_Spell FoP_0004": [{"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '牧师', "level": 1}],
    "spell_Spell FoP_0006": [{"class": '审判者', "level": 1}, {"class": '圣武士', "level": 1}],
    "spell_Spell MTT_0012": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '召唤师', "level": 4}],
    "spell_Spell OA_0071": [{"class": '秘学士', "level": 4}, {"class": '异能者', "level": 4}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}],
    "spell_page_1007_0001": [{"class": '催眠师', "level": 4}, {"class": '秘学士', "level": 4}, {"class": '异能者', "level": 4}, {"class": '唤魂师', "level": 4}],
    "spell_page_1007_0002": [{"class": '通灵者', "level": 3}, {"class": '催眠师', "level": 3}, {"class": '异能者', "level": 3}, {"class": '萨满', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1007_0003": [{"class": '吟游诗人', "level": 1}, {"class": '歌者', "level": 1}, {"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '审判者', "level": 1}, {"class": '通灵者', "level": 1}, {"class": '催眠师', "level": 1}, {"class": '秘学士', "level": 1}, {"class": '异能者', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '唤魂师', "level": 1}, {"class": '女巫', "level": 1}],
    "spell_page_1008_0007": [{"class": '催眠师', "level": 3}, {"class": '异能者', "level": 3}, {"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}, {"class": '女巫', "level": 4}],
    "spell_page_1008_0008": [{"class": '催眠师', "level": 5}, {"class": '异能者', "level": 6}, {"class": '术士', "level": 7}, {"class": '法师', "level": 7}, {"class": '奥能师', "level": 7}, {"class": '女巫', "level": 7}],
    "spell_page_1008_0009": [{"class": '吟游诗人', "level": 3}, {"class": '歌者', "level": 3}, {"class": '审判者', "level": 3}, {"class": '催眠师', "level": 3}, {"class": '秘学士', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1008_0010": [{"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '审判者', "level": 3}, {"class": '萨满', "level": 3}, {"class": '唤魂师', "level": 3}],
    "spell_page_1008_0011": [{"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '德鲁伊', "level": 3}, {"class": '猎人', "level": 3}, {"class": '审判者', "level": 3}, {"class": '魔战士', "level": 3}, {"class": '秘学士', "level": 3}, {"class": '圣武士', "level": 3}, {"class": '萨满', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1008_0012": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '萨满', "level": 1}, {"class": '女巫', "level": 1}],
    "spell_page_1008_0013": [{"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '审判者', "level": 3}, {"class": '魔战士', "level": 3}, {"class": '秘学士', "level": 3}, {"class": '萨满', "level": 3}],
    "spell_page_1008_0018": [{"class": '吟游诗人', "level": 1}, {"class": '歌者', "level": 1}, {"class": '血脉狂怒者', "level": 1}, {"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '催眠师', "level": 1}, {"class": '秘学士', "level": 1}, {"class": '异能者', "level": 1}, {"class": '萨满', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '女巫', "level": 1}],
    "spell_page_1009_0000": [{"class": '奥能师', "level": 6}, {"class": '术士', "level": 6}, {"class": '法师', "level": 6}],
    "spell_page_1009_0001": [{"class": '奥能师', "level": 5}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}],
    "spell_page_1009_0002": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '召唤师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1009_0003": [{"class": '牧师', "level": 4}, {"class": '先知', "level": 4}, {"class": '战斗祭司', "level": 4}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '召唤师', "level": 5}],
    "spell_page_1009_0004": [{"class": '术士', "level": 7}, {"class": '法师', "level": 7}, {"class": '奥能师', "level": 7}, {"class": '召唤师', "level": 6}],
    "spell_page_1009_0005": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '召唤师', "level": 4}, {"class": '女巫', "level": 5}],
    "spell_page_1009_0006": [{"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '吟游诗人', "level": 1}, {"class": '歌者', "level": 1}, {"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '德鲁伊', "level": 1}, {"class": '猎人', "level": 1}, {"class": '游侠', "level": 1}, {"class": '女巫', "level": 1}],
    "spell_page_1010_0001": [{"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '吟游诗人', "level": 1}, {"class": '歌者', "level": 1}, {"class": '召唤师', "level": 1}],
    "spell_page_1010_0002": [{"class": '德鲁伊', "level": 2}, {"class": '游侠', "level": 1}, {"class": '猎人', "level": 1}, {"class": '召唤师', "level": 1}],
    "spell_page_1010_0003": [{"class": '牧师', "level": 7}, {"class": '先知', "level": 7}, {"class": '魔战士', "level": 6}, {"class": '术士', "level": 7}, {"class": '法师', "level": 7}, {"class": '奥能师', "level": 7}, {"class": '召唤师', "level": 6}, {"class": '女巫', "level": 7}],
    "spell_page_1010_0005": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '审判者', "level": 3}, {"class": '游侠', "level": 2}, {"class": '女巫', "level": 3}],
    "spell_page_1010_0006": [{"class": '审判者', "level": 5}, {"class": '术士', "level": 6}, {"class": '法师', "level": 6}, {"class": '奥能师', "level": 6}, {"class": '女巫', "level": 6}],
    "spell_page_1011_0002": [{"class": '审判者', "level": 6}],
    "spell_page_1011_0003": [{"class": '审判者', "level": 4}],
    "spell_page_1011_0005": [{"class": '德鲁伊', "level": 5}, {"class": '猎人', "level": 5}, {"class": '审判者', "level": 5}],
    "spell_page_1011_0006": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}],
    "spell_page_1012_0000": [{"class": '魔战士', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1012_0001": [{"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}, {"class": '召唤师', "level": 3}, {"class": '女巫', "level": 4}],
    "spell_page_1012_0002": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '召唤师', "level": 4}, {"class": '女巫', "level": 5}],
    "spell_page_1012_0003": [{"class": '术士', "level": 6}, {"class": '法师', "level": 6}, {"class": '奥能师', "level": 6}, {"class": '召唤师', "level": 5}, {"class": '女巫', "level": 6}],
    "spell_page_1019_0001": [{"class": '术士', "level": 6}, {"class": '法师', "level": 6}],
    "spell_page_1019_0003": [{"class": '牧师', "level": 3}, {"class": '法师', "level": 3}, {"class": '术士', "level": 3}, {"class": '吟游诗人', "level": 3}],
    "spell_page_1106_0001": [{"class": '审判者', "level": 2}, {"class": '秘学士', "level": 2}, {"class": '萨满', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1106_0002": [{"class": '审判者', "level": 1}, {"class": '秘学士', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}],
    "spell_page_1106_0003": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '秘学士', "level": 2}, {"class": '圣武士', "level": 2}, {"class": '游侠', "level": 2}, {"class": '萨满', "level": 2}],
    "spell_page_1106_0004": [{"class": '秘学士', "level": 1}, {"class": '游侠', "level": 1}, {"class": '猎人', "level": 1}, {"class": '萨满', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '女巫', "level": 1}],
    "spell_page_1106_0005": [{"class": '秘学士', "level": 2}, {"class": '游侠', "level": 2}, {"class": '萨满', "level": 2}],
    "spell_page_1107_0001": [{"class": '异能者', "level": 4}, {"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}],
    "spell_page_1107_0002": [{"class": '异能者', "level": 3}],
    "spell_page_1107_0004": [{"class": '吟游诗人', "level": 2}, {"class": '歌者', "level": 2}, {"class": '血脉狂怒者', "level": 2}, {"class": '催眠师', "level": 2}, {"class": '异能者', "level": 3}, {"class": '萨满', "level": 3}, {"class": '唤魂师', "level": 2}, {"class": '女巫', "level": 3}],
    "spell_page_1107_0006": [{"class": '魔战士', "level": 3}, {"class": '通灵者', "level": 3}, {"class": '催眠师', "level": 2}, {"class": '异能者', "level": 2}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '唤魂师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1107_0007": [{"class": '审判者', "level": 3}, {"class": '秘学士', "level": 3}, {"class": '异能者', "level": 3}, {"class": '萨满', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1107_0008": [{"class": '审判者', "level": 3}, {"class": '秘学士', "level": 3}, {"class": '唤魂师', "level": 3}, {"class": '女巫', "level": 4}],
    "spell_page_1107_0011": [{"class": '异能者', "level": 8}],
    "spell_page_1107_0013": [{"class": '唤魂师', "level": 5}],
    "spell_page_1108_0001": [{"class": '牧师', "level": 4}, {"class": '先知', "level": 4}, {"class": '战斗祭司', "level": 4}, {"class": '魔战士', "level": 4}, {"class": '通灵者', "level": 4}, {"class": '秘学士', "level": 4}, {"class": '圣武士', "level": 3}, {"class": '萨满', "level": 3}, {"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}, {"class": '唤魂师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1108_0002": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '审判者', "level": 2}, {"class": '魔战士', "level": 2}, {"class": '通灵者', "level": 2}, {"class": '圣武士', "level": 1}, {"class": '萨满', "level": 2}],
    "spell_page_1108_0003": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '审判者', "level": 2}, {"class": '圣武士', "level": 2}, {"class": '萨满', "level": 2}, {"class": '唤魂师', "level": 2}],
    "spell_page_1142_0001": [{"class": '奥能师', "level": 9}, {"class": '术士', "level": 9}, {"class": '法师', "level": 9}],
    "spell_page_1142_0004": [{"class": '奥能师', "level": 8}, {"class": '术士', "level": 8}, {"class": '法师', "level": 8}],
    "spell_page_1149_0002": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '吟游诗人', "level": 1}, {"class": '歌者', "level": 1}, {"class": '魔战士', "level": 1}, {"class": '红螳螂杀手', "level": 1}],
    "spell_page_1149_0003": [{"class": '魔战士', "level": 1}, {"class": '圣武士', "level": 1}, {"class": '红螳螂杀手', "level": 1}],
    "spell_page_1149_0004": [{"class": '魔战士', "level": 1}, {"class": '圣武士', "level": 1}, {"class": '游侠', "level": 1}, {"class": '猎人', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}],
    "spell_page_1149_0005": [{"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1149_0006": [{"class": '魔战士', "level": 1}, {"class": '圣武士', "level": 1}],
    "spell_page_1149_0007": [{"class": '审判者', "level": 4}, {"class": '魔战士', "level": 4}, {"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}],
    "spell_page_1150_0000": [{"class": '审判者', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1150_0001": [{"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}, {"class": '女巫', "level": 3}],
    "spell_page_1150_0002": [{"class": '德鲁伊', "level": 3}, {"class": '猎人', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1150_0003": [{"class": '德鲁伊', "level": 5}, {"class": '猎人', "level": 5}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '女巫', "level": 5}],
    "spell_page_1150_0004": [{"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1151_0001": [{"class": '奥能师', "level": 4}, {"class": '术士', "level": 4}, {"class": '法师', "level": 4}],
    "spell_page_1151_0002": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1151_0003": [{"class": '奥能师', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}],
    "spell_page_1151_0004": [{"class": '女巫', "level": 3}],
    "spell_page_1151_0005": [{"class": '女巫', "level": 7}],
    "spell_page_1153_0000": [{"class": '审判者', "level": 4}, {"class": '魔战士', "level": 4}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '女巫', "level": 5}],
    "spell_page_1153_0001": [{"class": '炼金术师', "level": 1}, {"class": '调查员', "level": 1}, {"class": '德鲁伊', "level": 0}, {"class": '猎人', "level": 0}, {"class": '游侠', "level": 1}],
    "spell_page_1153_0002": [{"class": '德鲁伊', "level": 3}, {"class": '猎人', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}],
    "spell_page_1153_0003": [{"class": '反圣武士', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '德鲁伊', "level": 1}, {"class": '猎人', "level": 1}, {"class": '魔战士', "level": 1}, {"class": '红螳螂杀手', "level": 1}, {"class": '召唤师', "level": 1}, {"class": '女巫', "level": 1}],
    "spell_page_1153_0004": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '游侠', "level": 2}, {"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1153_0005": [{"class": '奥能师', "level": 4}, {"class": '术士', "level": 4}, {"class": '法师', "level": 4}],
    "spell_page_1153_0006": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '女巫', "level": 5}],
    "spell_page_1153_0007": [{"class": '召唤师', "level": 2}, {"class": '女巫', "level": 3}],
    "spell_page_1154_0000": [{"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}],
    "spell_page_1154_0001": [{"class": '女巫', "level": 5}],
    "spell_page_1154_0002": [{"class": '吟游诗人', "level": 2}, {"class": '歌者', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1154_0003": [{"class": '牧师', "level": 5}, {"class": '先知', "level": 5}, {"class": '战斗祭司', "level": 5}, {"class": '审判者', "level": 4}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}],
    "spell_page_1154_0004": [{"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1154_0005": [{"class": '奥能师', "level": 5}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}],
    "spell_page_1154_0006": [{"class": '德鲁伊', "level": 8}, {"class": '术士', "level": 8}, {"class": '法师', "level": 8}, {"class": '奥能师', "level": 8}, {"class": '女巫', "level": 8}],
    "spell_page_1154_0007": [{"class": '奥能师', "level": 5}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}],
    "spell_page_1155_0002": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '审判者', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '女巫', "level": 1}],
    "spell_page_1155_0004": [{"class": '审判者', "level": 2}, {"class": '游侠', "level": 2}, {"class": '猎人', "level": 2}],
    "spell_page_1156_0002": [{"class": '女巫', "level": 4}],
    "spell_page_1156_0003": [{"class": '游侠', "level": 4}, {"class": '猎人', "level": 4}],
    "spell_page_1156_0004": [{"class": '吟游诗人', "level": 2}, {"class": '歌者', "level": 2}, {"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '游侠', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1156_0005": [{"class": '德鲁伊', "level": 6}, {"class": '猎人', "level": 6}, {"class": '女巫', "level": 6}],
    "spell_page_1160_0000": [{"class": '审判者', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1160_0001": [{"class": '女巫', "level": 5}],
    "spell_page_1161_0001": [{"class": '血脉狂怒者', "level": 2}, {"class": '魔战士', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1161_0005": [{"class": '萨满', "level": 1}],
    "spell_page_1162_0001": [{"class": '游侠', "level": 1}, {"class": '猎人', "level": 1}, {"class": '萨满', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1162_0002": [{"class": '魔战士', "level": 4}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '女巫', "level": 6}],
    "spell_page_1162_0003": [{"class": '魔战士', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '召唤师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1162_0004": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '德鲁伊', "level": 2}, {"class": '魔战士', "level": 2}, {"class": '游侠', "level": 1}, {"class": '猎人', "level": 1}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1162_0005": [{"class": '德鲁伊', "level": 3}, {"class": '猎人', "level": 3}, {"class": '魔战士', "level": 3}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1162_0006": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '德鲁伊', "level": 1}, {"class": '猎人', "level": 1}, {"class": '萨满', "level": 1}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '女巫', "level": 1}],
    "spell_page_1163_0001": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '女巫', "level": 5}],
    "spell_page_1163_0002": [{"class": '吟游诗人', "level": 3}, {"class": '歌者', "level": 3}, {"class": '审判者', "level": 3}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1163_0003": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '女巫', "level": 5}],
    "spell_page_1163_0004": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '女巫', "level": 5}],
    "spell_page_1163_0005": [{"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1163_0006": [{"class": '牧师', "level": 5}, {"class": '先知', "level": 5}, {"class": '战斗祭司', "level": 5}, {"class": '德鲁伊', "level": 5}, {"class": '猎人', "level": 5}, {"class": '审判者', "level": 5}, {"class": '魔战士', "level": 5}, {"class": '萨满', "level": 5}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '女巫', "level": 5}],
    "spell_page_1163_0007": [{"class": '女巫', "level": 6}],
    "spell_page_1164_0001": [{"class": '游侠', "level": 2}, {"class": '猎人', "level": 2}, {"class": '萨满', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1164_0002": [{"class": '德鲁伊', "level": 4}, {"class": '猎人', "level": 4}, {"class": '萨满', "level": 4}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '女巫', "level": 4}],
    "spell_page_1164_0003": [{"class": '德鲁伊', "level": 1}, {"class": '猎人', "level": 1}, {"class": '审判者', "level": 1}, {"class": '游侠', "level": 1}, {"class": '萨满', "level": 1}, {"class": '女巫', "level": 1}],
    "spell_page_1164_0004": [{"class": '德鲁伊', "level": 5}, {"class": '猎人', "level": 5}, {"class": '术士', "level": 6}, {"class": '法师', "level": 6}, {"class": '奥能师', "level": 6}],
    "spell_page_1164_0005": [{"class": '德鲁伊', "level": 7}, {"class": '术士', "level": 7}, {"class": '法师', "level": 7}, {"class": '奥能师', "level": 7}, {"class": '萨满', "level": 7}, {"class": '召唤师', "level": 6}, {"class": '女巫', "level": 7}],
    "spell_page_1164_0006": [{"class": '德鲁伊', "level": 3}, {"class": '审判者', "level": 3}, {"class": '魔战士', "level": 2}, {"class": '游侠', "level": 2}, {"class": '猎人', "level": 2}, {"class": '萨满', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1164_0007": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '游侠', "level": 2}, {"class": '萨满', "level": 2}],
    "spell_page_1165_0002": [{"class": '游侠', "level": 3}, {"class": '萨满', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1166_0001": [{"class": '萨满', "level": 2}],
    "spell_page_1166_0002": [{"class": '游侠', "level": 2}, {"class": '萨满', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1166_0003": [{"class": '萨满', "level": 2}],
    "spell_page_1166_0004": [{"class": '奥能师', "level": 5}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}],
    "spell_page_1170_0003": [{"class": '召唤师', "level": 1}],
    "spell_page_1173_0001": [{"class": '奥能师', "level": 5}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}],
    "spell_page_1173_0002": [{"class": '女巫', "level": 3}],
    "spell_page_1173_0003": [{"class": '女巫', "level": 5}],
    "spell_page_1173_0005": [{"class": '异能者', "level": 3}],
    "spell_page_1173_0010": [{"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1173_0011": [{"class": '异能者', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1174_0001": [{"class": '魔战士', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1174_0002": [{"class": '女巫', "level": 2}],
    "spell_page_1176_0005": [{"class": '德鲁伊', "level": 1}, {"class": '猎人', "level": 1}, {"class": '魔战士', "level": 1}, {"class": '游侠', "level": 1}, {"class": '萨满', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '女巫', "level": 1}],
    "spell_page_1177_0002": [{"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '萨满', "level": 3}, {"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}, {"class": '唤魂师', "level": 3}, {"class": '女巫', "level": 2}],
    "spell_page_1177_0003": [{"class": '血脉狂怒者', "level": 2}, {"class": '德鲁伊', "level": 3}, {"class": '猎人', "level": 3}, {"class": '萨满', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1177_0004": [{"class": '魔战士', "level": 2}, {"class": '萨满', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '召唤师', "level": 3}, {"class": '女巫', "level": 2}],
    "spell_page_1331_0002": [{"class": '审判者', "level": 3}, {"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}, {"class": '召唤师', "level": 3}, {"class": '女巫', "level": 4}],
    "spell_page_1331_0003": [{"class": '审判者', "level": 6}, {"class": '术士', "level": 7}, {"class": '法师', "level": 7}, {"class": '奥能师', "level": 7}, {"class": '召唤师', "level": 6}, {"class": '女巫', "level": 7}],
    "spell_page_1331_0004": [{"class": '女巫', "level": 2}],
    "spell_page_1331_0005": [{"class": '奥能师', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}],
    "spell_page_1331_0007": [{"class": '奥能师', "level": 5}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}],
    "spell_page_1331_0008": [{"class": '女巫', "level": 3}],
    "spell_page_1331_0009": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '审判者', "level": 1}, {"class": '圣武士', "level": 1}, {"class": '女巫', "level": 2}],
    "spell_page_1331_0010": [{"class": '奥能师', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}],
    "spell_page_1331_0011": [{"class": '魔战士', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1332_0000": [{"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}, {"class": '德鲁伊', "level": 4}, {"class": '猎人', "level": 4}],
    "spell_page_1334_0000": [{"class": '先知', "level": 1}, {"class": '女巫', "level": 2}],
    "spell_page_1363_0001": [{"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}],
    "spell_page_1363_0017": [{"class": '德鲁伊', "level": 4}, {"class": '猎人', "level": 4}],
    "spell_page_1363_0018": [{"class": '德鲁伊', "level": 1}, {"class": '猎人', "level": 1}, {"class": '游侠', "level": 1}],
    "spell_page_1363_0020": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}],
    "spell_page_1363_0024": [{"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '德鲁伊', "level": 3}, {"class": '猎人', "level": 3}],
    "spell_page_1363_0025": [{"class": '吟游诗人', "level": 1}, {"class": '歌者', "level": 1}, {"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}],
    "spell_page_1363_0026": [{"class": '魔战士', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1363_0027": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1363_0028": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '圣武士', "level": 1}],
    "spell_page_1363_0029": [{"class": '圣武士', "level": 1}],
    "spell_page_1363_0031": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}],
    "spell_page_1363_0041": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1363_0042": [{"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}],
    "spell_page_1363_0043": [{"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}],
    "spell_page_1363_0044": [{"class": '牧师', "level": 0}, {"class": '先知', "level": 0}, {"class": '战斗祭司', "level": 0}, {"class": '术士', "level": 0}, {"class": '法师', "level": 0}, {"class": '奥能师', "level": 0}],
    "spell_page_1363_0047": [{"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '召唤师', "level": 3}],
    "spell_page_1363_0048": [{"class": '术士', "level": 6}, {"class": '法师', "level": 6}],
    "spell_page_1363_0050": [{"class": '牧师', "level": 3}, {"class": '法师', "level": 3}, {"class": '术士', "level": 3}, {"class": '吟游诗人', "level": 3}],
    "spell_page_1363_0052": [{"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '德鲁伊', "level": 3}, {"class": '猎人', "level": 3}],
    "spell_page_1363_0053": [{"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1363_0056": [{"class": '术士', "level": 9}, {"class": '法师', "level": 9}, {"class": '奥能师', "level": 9}],
    "spell_page_1363_0057": [{"class": '吟游诗人', "level": 1}, {"class": '歌者', "level": 1}, {"class": '红螳螂杀手', "level": 1}],
    "spell_page_1363_0060": [{"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1363_0061": [{"class": '吟游诗人', "level": 1}, {"class": '歌者', "level": 1}, {"class": '牧师', "level": 0}, {"class": '先知', "level": 0}, {"class": '战斗祭司', "level": 0}],
    "spell_page_1363_0062": [{"class": '术士', "level": 8}, {"class": '法师', "level": 8}, {"class": '奥能师', "level": 8}],
    "spell_page_1363_0063": [{"class": '吟游诗人', "level": 1}, {"class": '歌者', "level": 1}, {"class": '德鲁伊', "level": 1}, {"class": '猎人', "level": 1}],
    "spell_page_1363_0068": [{"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}],
    "spell_page_1363_0071": [{"class": '游侠', "level": 2}, {"class": '红螳螂杀手', "level": 2}],
    "spell_page_1363_0072": [{"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}],
    "spell_page_1363_0073": [{"class": '红螳螂杀手', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1363_0074": [{"class": '牧师', "level": 4}, {"class": '先知', "level": 4}, {"class": '战斗祭司', "level": 4}, {"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}],
    "spell_page_1363_0075": [{"class": '牧师', "level": 5}, {"class": '先知', "level": 5}, {"class": '战斗祭司', "level": 5}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}],
    "spell_page_1363_0077": [{"class": '术士', "level": 6}, {"class": '法师', "level": 6}, {"class": '奥能师', "level": 6}, {"class": '审判者', "level": 4}],
    "spell_page_1363_0078": [{"class": '吟游诗人', "level": 2}, {"class": '调查员', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1363_0080": [{"class": '审判者', "level": 3}, {"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}],
    "spell_page_1363_0081": [{"class": '审判者', "level": 6}, {"class": '术士', "level": 7}, {"class": '法师', "level": 7}, {"class": '奥能师', "level": 7}],
    "spell_page_1363_0082": [{"class": '女巫', "level": 2}],
    "spell_page_1363_0083": [{"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}],
    "spell_page_1363_0085": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}],
    "spell_page_1363_0086": [{"class": '女巫', "level": 3}],
    "spell_page_1363_0087": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '审判者', "level": 1}],
    "spell_page_1363_0088": [{"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}],
    "spell_page_1363_0089": [{"class": '魔战士', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}],
    "spell_page_1363_0090": [{"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}, {"class": '德鲁伊', "level": 4}, {"class": '猎人', "level": 4}],
    "spell_page_1363_0091": [{"class": '审判者', "level": 4}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}],
    "spell_page_1363_0092": [{"class": '审判者', "level": 4}, {"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}],
    "spell_page_1363_0093": [{"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1363_0094": [{"class": '德鲁伊', "level": 5}, {"class": '猎人', "level": 5}, {"class": '圣武士', "level": 4}],
    "spell_page_1363_0095": [{"class": '审判者', "level": 6}, {"class": '术士', "level": 6}, {"class": '法师', "level": 6}, {"class": '奥能师', "level": 6}],
    "spell_page_1363_0096": [{"class": '审判者', "level": 4}, {"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}],
    "spell_page_1363_0097": [{"class": '魔战士', "level": 5}, {"class": '术士', "level": 6}, {"class": '法师', "level": 6}, {"class": '奥能师', "level": 6}],
    "spell_page_1363_0098": [{"class": '术士', "level": 9}, {"class": '法师', "level": 9}, {"class": '奥能师', "level": 9}, {"class": '女巫', "level": 9}],
    "spell_page_1363_0099": [{"class": '术士', "level": 9}, {"class": '法师', "level": 9}, {"class": '奥能师', "level": 9}],
    "spell_page_1363_0100": [{"class": '术士', "level": 7}, {"class": '法师', "level": 7}, {"class": '奥能师', "level": 7}, {"class": '女巫', "level": 7}],
    "spell_page_1363_0101": [{"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '召唤师', "level": 2}],
    "spell_page_1363_0102": [{"class": '召唤师', "level": 3}, {"class": '女巫', "level": 4}],
    "spell_page_1363_0103": [{"class": '召唤师', "level": 4}, {"class": '女巫', "level": 5}],
    "spell_page_1363_0104": [{"class": '术士', "level": 9}, {"class": '法师', "level": 9}, {"class": '奥能师', "level": 9}, {"class": '女巫', "level": 9}],
    "spell_page_1363_0105": [{"class": '术士', "level": 8}, {"class": '法师', "level": 8}, {"class": '奥能师', "level": 8}, {"class": '召唤师', "level": 6}],
    "spell_page_1363_0106": [{"class": '术士', "level": 8}, {"class": '法师', "level": 8}, {"class": '奥能师', "level": 8}, {"class": '召唤师', "level": 6}],
    "spell_page_1363_0107": [{"class": '术士', "level": 9}, {"class": '法师', "level": 9}, {"class": '奥能师', "level": 9}, {"class": '女巫', "level": 9}],
    "spell_page_1363_0108": [{"class": '牧师', "level": 4}, {"class": '先知', "level": 4}, {"class": '战斗祭司', "level": 4}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}],
    "spell_page_1363_0109": [{"class": '术士', "level": 7}, {"class": '法师', "level": 7}, {"class": '奥能师', "level": 7}, {"class": '召唤师', "level": 6}],
    "spell_page_1363_0110": [{"class": '先知', "level": 1}, {"class": '女巫', "level": 2}],
    "spell_page_1363_0112": [{"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}],
    "spell_page_1363_0113": [{"class": '术士', "level": 6}, {"class": '法师', "level": 6}, {"class": '奥能师', "level": 6}],
    "spell_page_1363_0114": [{"class": '圣武士', "level": 3}],
    "spell_page_1363_0115": [{"class": '德鲁伊', "level": 6}, {"class": '猎人', "level": 6}, {"class": '召唤师', "level": 4}],
    "spell_page_1363_0116": [{"class": '德鲁伊', "level": 8}],
    "spell_page_1363_0118": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '女巫', "level": 1}],
    "spell_page_1363_0119": [{"class": '德鲁伊', "level": 2}, {"class": '游侠', "level": 1}, {"class": '猎人', "level": 1}],
    "spell_page_1363_0120": [{"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '萨满', "level": 3}],
    "spell_page_1363_0121": [{"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1363_0122": [{"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}],
    "spell_page_1363_0123": [{"class": '术士', "level": 6}, {"class": '法师', "level": 6}, {"class": '奥能师', "level": 6}],
    "spell_page_1363_0124": [{"class": '术士', "level": 6}, {"class": '法师', "level": 6}, {"class": '奥能师', "level": 6}, {"class": '通灵者', "level": 3}],
    "spell_page_1363_0125": [{"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}],
    "spell_page_1363_0126": [{"class": '德鲁伊', "level": 8}, {"class": '牧师', "level": 8}, {"class": '先知', "level": 8}],
    "spell_page_1363_0127": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '审判者', "level": 2}],
    "spell_page_1363_0128": [{"class": '游侠', "level": 2}, {"class": '猎人', "level": 2}, {"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}],
    "spell_page_1363_0129": [{"class": '游侠', "level": 1}, {"class": '猎人', "level": 1}, {"class": '德鲁伊', "level": 2}, {"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}],
    "spell_page_1363_0130": [{"class": '德鲁伊', "level": 1}, {"class": '游侠', "level": 1}, {"class": '猎人', "level": 1}, {"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}],
    "spell_page_1363_0131": [{"class": '圣武士', "level": 4}],
    "spell_page_1363_0134": [{"class": '圣武士', "level": 3}, {"class": '游侠', "level": 3}, {"class": '萨满', "level": 3}],
    "spell_page_1363_0135": [{"class": '吟游诗人', "level": 2}, {"class": '德鲁伊', "level": 2}, {"class": '通灵者', "level": 2}, {"class": '秘学士', "level": 2}, {"class": '异能者', "level": 2}, {"class": '游侠', "level": 2}, {"class": '萨满', "level": 2}],
    "spell_page_1363_0136": [{"class": '血脉狂怒者', "level": 3}, {"class": '牧师', "level": 3}, {"class": '德鲁伊', "level": 3}, {"class": '圣武士', "level": 3}, {"class": '游侠', "level": 3}, {"class": '萨满', "level": 3}],
    "spell_page_1363_0137": [{"class": '血脉狂怒者', "level": 3}, {"class": '牧师', "level": 3}, {"class": '德鲁伊', "level": 3}, {"class": '圣武士', "level": 3}, {"class": '游侠', "level": 3}, {"class": '萨满', "level": 3}],
    "spell_page_1363_0139": [{"class": '德鲁伊', "level": 4}, {"class": '萨满', "level": 4}, {"class": '术士', "level": 4}, {"class": '法师', "level": 4}],
    "spell_page_1365_0005": [{"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}],
    "spell_page_1365_0009": [{"class": '术士', "level": 8}, {"class": '法师', "level": 8}, {"class": '奥能师', "level": 8}],
    "spell_page_1365_0018": [{"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}],
    "spell_page_1365_0019": [{"class": '德鲁伊', "level": 1}, {"class": '猎人', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}],
    "spell_page_1365_0023": [{"class": '术士', "level": 7}, {"class": '法师', "level": 7}, {"class": '奥能师', "level": 7}],
    "spell_page_1365_0025": [{"class": '圣武士', "level": 4}, {"class": '游侠', "level": 4}, {"class": '猎人', "level": 4}],
    "spell_page_1365_0026": [{"class": '圣武士', "level": 2}],
    "spell_page_1365_0028": [{"class": '圣武士', "level": 4}],
    "spell_page_1365_0029": [{"class": '圣武士', "level": 2}],
    "spell_page_1365_0031": [{"class": '圣武士', "level": 3}, {"class": '游侠', "level": 4}, {"class": '猎人', "level": 4}],
    "spell_page_1365_0032": [{"class": '圣武士', "level": 3}, {"class": '游侠', "level": 4}, {"class": '猎人', "level": 4}],
    "spell_page_1365_0033": [{"class": '圣武士', "level": 1}],
    "spell_page_1365_0034": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}],
    "spell_page_1365_0035": [{"class": '牧师', "level": 4}, {"class": '先知', "level": 4}, {"class": '战斗祭司', "level": 4}],
    "spell_page_1365_0036": [{"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}],
    "spell_page_1365_0037": [{"class": '游侠', "level": 3}, {"class": '猎人', "level": 3}],
    "spell_page_1365_0042": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '圣武士', "level": 1}],
    "spell_page_1365_0043": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '德鲁伊', "level": 1}],
    "spell_page_1365_0044": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '圣武士', "level": 2}],
    "spell_page_1365_0045": [{"class": '游侠', "level": 4}, {"class": '猎人', "level": 4}, {"class": '术士', "level": 6}, {"class": '法师', "level": 6}, {"class": '奥能师', "level": 6}],
    "spell_page_1365_0055": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '德鲁伊', "level": 1}],
    "spell_page_1365_0056": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '圣武士', "level": 1}],
    "spell_page_1365_0059": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}],
    "spell_page_1365_0060": [{"class": '审判者', "level": 1}, {"class": '圣武士', "level": 1}],
    "spell_page_1365_0061": [{"class": '审判者', "level": 1}, {"class": '圣武士', "level": 1}],
    "spell_page_1365_0066": [{"class": '审判者', "level": 2}, {"class": '圣武士', "level": 2}],
    "spell_page_1365_0068": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '召唤师', "level": 1}],
    "spell_page_1365_0069": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '召唤师', "level": 5}],
    "spell_page_1365_0070": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '德鲁伊', "level": 1}],
    "spell_page_1365_0071": [{"class": '德鲁伊', "level": 3}, {"class": '猎人', "level": 3}],
    "spell_page_1365_0072": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '德鲁伊', "level": 1}, {"class": '猎人', "level": 1}],
    "spell_page_1365_0073": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '审判者', "level": 2}],
    "spell_page_1365_0074": [{"class": '审判者', "level": 2}],
    "spell_page_1365_0078": [{"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 4}],
    "spell_page_1365_0079": [{"class": '游侠', "level": 1}, {"class": '猎人', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}],
    "spell_page_1365_0080": [{"class": '审判者', "level": 3}, {"class": '游侠', "level": 4}, {"class": '猎人', "level": 4}],
    "spell_page_1365_0082": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}],
    "spell_page_1365_0083": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '德鲁伊', "level": 1}, {"class": '猎人', "level": 1}],
    "spell_page_1365_0085": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '女巫', "level": 4}],
    "spell_page_1365_0086": [{"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1365_0087": [{"class": '术士', "level": 9}, {"class": '法师', "level": 9}, {"class": '奥能师', "level": 9}],
    "spell_page_1365_0088": [{"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}, {"class": '召唤师', "level": 4}],
    "spell_page_1365_0089": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1365_0090": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '召唤师', "level": 5}],
    "spell_page_1365_0110": [{"class": '德鲁伊', "level": 3}, {"class": '游侠', "level": 3}, {"class": '猎人', "level": 3}],
    "spell_page_1365_0111": [{"class": '德鲁伊', "level": 5}, {"class": '猎人', "level": 5}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}],
    "spell_page_1365_0112": [{"class": '女巫', "level": 2}],
    "spell_page_1365_0114": [{"class": '游侠', "level": 2}, {"class": '猎人', "level": 2}],
    "spell_page_1365_0115": [{"class": '圣武士', "level": 4}, {"class": '游侠', "level": 4}, {"class": '猎人', "level": 4}],
    "spell_page_1365_0116": [{"class": '圣武士', "level": 2}, {"class": '游侠', "level": 2}, {"class": '猎人', "level": 2}],
    "spell_page_1365_0117": [{"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}, {"class": '女巫', "level": 4}],
    "spell_page_1365_0118": [{"class": '德鲁伊', "level": 1}, {"class": '圣武士', "level": 1}],
    "spell_page_1365_0120": [{"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}],
    "spell_page_1365_0121": [{"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}],
    "spell_page_1365_0122": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1365_0123": [{"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}],
    "spell_page_1365_0124": [{"class": '女巫', "level": 3}],
    "spell_page_1365_0125": [{"class": '女巫', "level": 7}],
    "spell_page_1365_0126": [{"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '德鲁伊', "level": 3}, {"class": '猎人', "level": 3}],
    "spell_page_1365_0127": [{"class": '圣武士', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1365_0128": [{"class": '圣武士', "level": 3}, {"class": '法师', "level": 5}, {"class": '术士', "level": 5}, {"class": '奥能师', "level": 5}],
    "spell_page_1365_0129": [{"class": '圣武士', "level": 4}, {"class": '法师', "level": 8}, {"class": '术士', "level": 8}, {"class": '奥能师', "level": 8}],
    "spell_page_1365_0130": [{"class": '牧师', "level": 7}, {"class": '先知', "level": 7}, {"class": '战斗祭司', "level": 7}, {"class": '圣武士', "level": 4}],
    "spell_page_1365_0131": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '法师', "level": 2}, {"class": '术士', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1365_0132": [{"class": '审判者', "level": 5}, {"class": '圣武士', "level": 4}],
    "spell_page_1365_0133": [{"class": '吟游诗人', "level": 2}, {"class": '歌者', "level": 2}, {"class": '法师', "level": 2}, {"class": '术士', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1365_0134": [{"class": '吟游诗人', "level": 5}, {"class": '歌者', "level": 5}],
    "spell_page_1365_0135": [{"class": '吟游诗人', "level": 6}, {"class": '歌者', "level": 6}],
    "spell_page_1365_0136": [{"class": '审判者', "level": 4}, {"class": '魔战士', "level": 4}],
    "spell_page_1365_0137": [{"class": '炼金术师', "level": 1}, {"class": '调查员', "level": 1}, {"class": '德鲁伊', "level": 0}, {"class": '猎人', "level": 0}],
    "spell_page_1365_0138": [{"class": '德鲁伊', "level": 3}, {"class": '猎人', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}],
    "spell_page_1365_0139": [{"class": '反圣武士', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}],
    "spell_page_1365_0140": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '游侠', "level": 2}],
    "spell_page_1365_0141": [{"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}],
    "spell_page_1365_0142": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '女巫', "level": 5}],
    "spell_page_1365_0153": [{"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}],
    "spell_page_1365_0154": [{"class": '女巫', "level": 5}],
    "spell_page_1365_0155": [{"class": '吟游诗人', "level": 2}, {"class": '歌者', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1365_0156": [{"class": '牧师', "level": 5}, {"class": '先知', "level": 5}, {"class": '战斗祭司', "level": 5}, {"class": '审判者', "level": 4}],
    "spell_page_1365_0157": [{"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1365_0158": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}],
    "spell_page_1365_0159": [{"class": '德鲁伊', "level": 8}, {"class": '术士', "level": 8}, {"class": '法师', "level": 8}, {"class": '奥能师', "level": 8}],
    "spell_page_1365_0160": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}],
    "spell_page_1365_0161": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '魔战士', "level": 1}],
    "spell_page_1365_0162": [{"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1365_0164": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '审判者', "level": 1}],
    "spell_page_1365_0165": [{"class": '魔战士', "level": 2}, {"class": '游侠', "level": 2}, {"class": '猎人', "level": 2}],
    "spell_page_1365_0166": [{"class": '审判者', "level": 2}],
    "spell_page_1365_0168": [{"class": '女巫', "level": 4}],
    "spell_page_1365_0169": [{"class": '游侠', "level": 4}, {"class": '猎人', "level": 4}],
    "spell_page_1365_0170": [{"class": '吟游诗人', "level": 2}, {"class": '歌者', "level": 2}, {"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}],
    "spell_page_1365_0171": [{"class": '德鲁伊', "level": 6}, {"class": '猎人', "level": 6}, {"class": '女巫', "level": 6}],
    "spell_page_1365_0173": [{"class": '审判者', "level": 3}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1365_0181": [{"class": '德鲁伊', "level": 4}, {"class": '猎人', "level": 4}, {"class": '游侠', "level": 4}],
    "spell_page_1365_0182": [{"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '德鲁伊', "level": 3}, {"class": '猎人', "level": 3}],
    "spell_page_1365_0183": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '女巫', "level": 5}],
    "spell_page_1365_0184": [{"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1365_0185": [{"class": '魔战士', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1365_0186": [{"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}, {"class": '召唤师', "level": 3}],
    "spell_page_1365_0187": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '召唤师', "level": 4}],
    "spell_page_1365_0188": [{"class": '术士', "level": 6}, {"class": '法师', "level": 6}, {"class": '奥能师', "level": 6}, {"class": '召唤师', "level": 5}],
    "spell_page_1365_0189": [{"class": '德鲁伊', "level": 2}, {"class": '审判者', "level": 2}, {"class": '圣武士', "level": 1}, {"class": '游侠', "level": 1}, {"class": '猎人', "level": 1}],
    "spell_page_1365_0191": [{"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}, {"class": '女巫', "level": 4}],
    "spell_page_1365_0192": [{"class": '审判者', "level": 6}],
    "spell_page_1365_0193": [{"class": '审判者', "level": 4}],
    "spell_page_1365_0195": [{"class": '德鲁伊', "level": 5}, {"class": '猎人', "level": 5}, {"class": '审判者', "level": 5}],
    "spell_page_1365_0196": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}],
    "spell_page_1365_0204": [{"class": '术士', "level": 6}, {"class": '法师', "level": 6}, {"class": '奥能师', "level": 6}, {"class": '女巫', "level": 6}],
    "spell_page_1365_0205": [{"class": '德鲁伊', "level": 4}, {"class": '猎人', "level": 4}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}],
    "spell_page_1365_0206": [{"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '吟游诗人', "level": 1}, {"class": '歌者', "level": 1}],
    "spell_page_1365_0207": [{"class": '德鲁伊', "level": 2}, {"class": '游侠', "level": 1}, {"class": '猎人', "level": 1}],
    "spell_page_1365_0208": [{"class": '牧师', "level": 7}, {"class": '先知', "level": 7}, {"class": '魔战士', "level": 6}],
    "spell_page_1365_0210": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '审判者', "level": 3}],
    "spell_page_1365_0211": [{"class": '审判者', "level": 5}, {"class": '术士', "level": 6}, {"class": '法师', "level": 6}, {"class": '奥能师', "level": 6}],
    "spell_page_1365_0212": [{"class": '术士', "level": 6}, {"class": '法师', "level": 6}, {"class": '奥能师', "level": 6}],
    "spell_page_1365_0213": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}],
    "spell_page_1365_0214": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}],
    "spell_page_1365_0215": [{"class": '牧师', "level": 4}, {"class": '先知', "level": 4}, {"class": '战斗祭司', "level": 4}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}],
    "spell_page_1365_0216": [{"class": '术士', "level": 7}, {"class": '法师', "level": 7}, {"class": '奥能师', "level": 7}, {"class": '召唤师', "level": 6}],
    "spell_page_1365_0217": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '召唤师', "level": 4}],
    "spell_page_1365_0218": [{"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '吟游诗人', "level": 1}, {"class": '歌者', "level": 1}],
    "spell_page_1365_0219": [{"class": '审判者', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1365_0220": [{"class": '女巫', "level": 5}],
    "spell_page_1365_0235": [{"class": '萨满', "level": 2}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}],
    "spell_page_1365_0236": [{"class": '游侠', "level": 1}, {"class": '猎人', "level": 1}, {"class": '萨满', "level": 3}],
    "spell_page_1365_0237": [{"class": '魔战士', "level": 4}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}],
    "spell_page_1365_0238": [{"class": '魔战士', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}],
    "spell_page_1365_0239": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '德鲁伊', "level": 2}],
    "spell_page_1365_0240": [{"class": '德鲁伊', "level": 3}, {"class": '猎人', "level": 3}, {"class": '魔战士', "level": 3}],
    "spell_page_1365_0241": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '德鲁伊', "level": 1}, {"class": '猎人', "level": 1}],
    "spell_page_1365_0242": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1365_0243": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '女巫', "level": 5}],
    "spell_page_1365_0244": [{"class": '吟游诗人', "level": 3}, {"class": '歌者', "level": 3}, {"class": '审判者', "level": 3}],
    "spell_page_1365_0245": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '女巫', "level": 5}],
    "spell_page_1365_0246": [{"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1365_0247": [{"class": '牧师', "level": 5}, {"class": '先知', "level": 5}, {"class": '战斗祭司', "level": 5}, {"class": '德鲁伊', "level": 5}, {"class": '猎人', "level": 5}, {"class": '审判者', "level": 5}],
    "spell_page_1365_0248": [{"class": '女巫', "level": 6}],
    "spell_page_1365_0260": [{"class": '德鲁伊', "level": 1}, {"class": '猎人', "level": 1}, {"class": '游侠', "level": 1}],
    "spell_page_1365_0261": [{"class": '游侠', "level": 2}, {"class": '猎人', "level": 2}, {"class": '萨满', "level": 3}],
    "spell_page_1365_0262": [{"class": '德鲁伊', "level": 4}, {"class": '猎人', "level": 4}, {"class": '萨满', "level": 4}],
    "spell_page_1365_0263": [{"class": '德鲁伊', "level": 1}, {"class": '猎人', "level": 1}, {"class": '审判者', "level": 1}],
    "spell_page_1365_0264": [{"class": '德鲁伊', "level": 5}, {"class": '猎人', "level": 5}, {"class": '术士', "level": 6}, {"class": '法师', "level": 6}, {"class": '奥能师', "level": 6}],
    "spell_page_1365_0265": [{"class": '德鲁伊', "level": 7}, {"class": '术士', "level": 7}, {"class": '法师', "level": 7}, {"class": '奥能师', "level": 7}],
    "spell_page_1365_0266": [{"class": '德鲁伊', "level": 3}, {"class": '审判者', "level": 3}],
    "spell_page_1365_0267": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '游侠', "level": 2}],
    "spell_page_1365_0268": [{"class": '牧师', "level": 5}, {"class": '先知', "level": 5}, {"class": '战斗祭司', "level": 5}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}],
    "spell_page_1365_0269": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '萨满', "level": 2}],
    "spell_page_1365_0270": [{"class": '游侠', "level": 3}, {"class": '萨满', "level": 2}],
    "spell_page_1365_0271": [{"class": '吟游诗人', "level": 2}, {"class": '歌者', "level": 2}, {"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}],
    "spell_page_1365_0273": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1365_0274": [{"class": '萨满', "level": 4}, {"class": '召唤师', "level": 4}, {"class": '女巫', "level": 4}],
    "spell_page_1365_0279": [{"class": '游侠', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1365_0283": [{"class": '德鲁伊', "level": 4}, {"class": '猎人', "level": 4}, {"class": '萨满', "level": 4}, {"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}, {"class": '召唤师', "level": 4}],
    "spell_page_1365_0286": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '德鲁伊', "level": 1}, {"class": '猎人', "level": 1}],
    "spell_page_1365_0287": [{"class": '血脉狂怒者', "level": 2}, {"class": '魔战士', "level": 2}],
    "spell_page_1365_0290": [{"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '血脉狂怒者', "level": 1}],
    "spell_page_1365_0292": [{"class": '吟游诗人', "level": 2}, {"class": '歌者', "level": 2}, {"class": '游侠', "level": 2}, {"class": '猎人', "level": 2}],
    "spell_page_1365_0294": [{"class": '吟游诗人', "level": 2}, {"class": '歌者', "level": 2}, {"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}],
    "spell_page_1365_0295": [{"class": '萨满', "level": 2}],
    "spell_page_1365_0296": [{"class": '游侠', "level": 2}, {"class": '萨满', "level": 2}],
    "spell_page_1365_0297": [{"class": '萨满', "level": 2}],
    "spell_page_1365_0298": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}],
    "spell_page_1365_0300": [{"class": '萨满', "level": 1}, {"class": '女巫', "level": 1}],
    "spell_page_1365_0301": [{"class": '反圣武士', "level": 1}, {"class": '炼金术师', "level": 1}, {"class": '调查员', "level": 1}],
    "spell_page_1365_0303": [{"class": '吟游诗人', "level": 1}, {"class": '歌者', "level": 1}, {"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}],
    "spell_page_1365_0304": [{"class": '催眠师', "level": 5}, {"class": '异能者', "level": 6}],
    "spell_page_1365_0305": [{"class": '异能者', "level": 4}, {"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}],
    "spell_page_1365_0306": [{"class": '异能者', "level": 3}],
    "spell_page_1365_0307": [{"class": '吟游诗人', "level": 2}, {"class": '歌者', "level": 2}, {"class": '催眠师', "level": 2}],
    "spell_page_1365_0308": [{"class": '吟游诗人', "level": 2}, {"class": '歌者', "level": 2}, {"class": '血脉狂怒者', "level": 2}],
    "spell_page_1365_0309": [{"class": '血脉狂怒者', "level": 2}, {"class": '审判者', "level": 2}],
    "spell_page_1365_0310": [{"class": '魔战士', "level": 3}, {"class": '通灵者', "level": 3}],
    "spell_page_1365_0311": [{"class": '审判者', "level": 3}, {"class": '秘学士', "level": 3}],
    "spell_page_1365_0312": [{"class": '审判者', "level": 3}, {"class": '秘学士', "level": 3}],
    "spell_page_1365_0314": [{"class": '异能者', "level": 5}, {"class": '唤魂师', "level": 4}],
    "spell_page_1365_0315": [{"class": '异能者', "level": 8}],
    "spell_page_1365_0317": [{"class": '唤魂师', "level": 5}],
    "spell_page_1365_0319": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '德鲁伊', "level": 1}],
    "spell_page_1365_0320": [{"class": '吟游诗人', "level": 2}, {"class": '歌者', "level": 2}, {"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '催眠师', "level": 3}],
    "spell_page_1365_0321": [{"class": '催眠师', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}],
    "spell_page_1365_0323": [{"class": '吟游诗人', "level": 1}, {"class": '歌者', "level": 1}, {"class": '血脉狂怒者', "level": 1}],
    "spell_page_1365_0324": [{"class": '反圣武士', "level": 1}, {"class": '血脉狂怒者', "level": 1}],
    "spell_page_1365_0325": [{"class": '审判者', "level": 2}, {"class": '通灵者', "level": 2}],
    "spell_page_1365_0326": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}],
    "spell_page_1365_0327": [{"class": '牧师', "level": 5}, {"class": '先知', "level": 5}, {"class": '战斗祭司', "level": 5}, {"class": '德鲁伊', "level": 5}, {"class": '猎人', "level": 5}],
    "spell_page_1365_0328": [{"class": '催眠师', "level": 2}, {"class": '秘学士', "level": 3}],
    "spell_page_1365_0329": [{"class": '催眠师', "level": 5}, {"class": '秘学士', "level": 6}],
    "spell_page_1365_0330": [{"class": '审判者', "level": 1}, {"class": '萨满', "level": 1}],
    "spell_page_1365_0331": [{"class": '吟游诗人', "level": 3}, {"class": '歌者', "level": 3}, {"class": '催眠师', "level": 3}],
    "spell_page_1365_0333": [{"class": '术士', "level": 0}, {"class": '法师', "level": 0}, {"class": '奥能师', "level": 0}],
    "spell_page_1365_0334": [{"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}],
    "spell_page_1365_0335": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '审判者', "level": 1}],
    "spell_page_1365_0336": [{"class": '催眠师', "level": 2}, {"class": '萨满', "level": 2}],
    "spell_page_1365_0337": [{"class": '秘学士', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}],
    "spell_page_1365_0338": [{"class": '血脉狂怒者', "level": 2}, {"class": '魔战士', "level": 2}],
    "spell_page_1365_0339": [{"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}],
    "spell_page_1365_0340": [{"class": '吟游诗人', "level": 2}, {"class": '歌者', "level": 2}, {"class": '催眠师', "level": 2}],
    "spell_page_1365_0341": [{"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1365_0342": [{"class": '女巫', "level": 3}],
    "spell_page_1365_0343": [{"class": '女巫', "level": 8}],
    "spell_page_1365_0346": [{"class": '血脉狂怒者', "level": 1}, {"class": '魔战士', "level": 1}, {"class": '萨满', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '唤魂师', "level": 1}, {"class": '召唤师', "level": 1}],
    "spell_page_1365_0405": [{"class": '吟游诗人', "level": 3}, {"class": '歌者', "level": 3}, {"class": '审判者', "level": 3}],
    "spell_page_1365_0406": [{"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '审判者', "level": 3}],
    "spell_page_1365_0407": [{"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '德鲁伊', "level": 3}, {"class": '猎人', "level": 3}],
    "spell_page_1365_0408": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}],
    "spell_page_1365_0409": [{"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}],
    "spell_page_1365_0419": [{"class": '牧师', "level": 4}, {"class": '先知', "level": 4}, {"class": '战斗祭司', "level": 4}, {"class": '魔战士', "level": 4}],
    "spell_page_1365_0420": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '审判者', "level": 2}],
    "spell_page_1365_0421": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '审判者', "level": 2}],
    "spell_page_1365_0484": [{"class": '秘学士', "level": 1}, {"class": '通灵者', "level": 1}],
    "spell_page_1365_0500": [{"class": '召唤师', "level": 1}],
    "spell_page_1365_0513": [{"class": '审判者', "level": 3}, {"class": '圣武士', "level": 3}],
    "spell_page_1365_0522": [{"class": '催眠师', "level": 4}, {"class": '秘学士', "level": 4}],
    "spell_page_1365_0523": [{"class": '通灵者', "level": 3}, {"class": '催眠师', "level": 3}],
    "spell_page_1365_0524": [{"class": '吟游诗人', "level": 1}, {"class": '歌者', "level": 1}, {"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}],
    "spell_page_1365_0525": [{"class": '女巫', "level": 1}],
    "spell_page_1365_0526": [{"class": '女巫', "level": 6}],
    "spell_page_1365_0527": [{"class": '审判者', "level": 1}, {"class": '异能者', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '女巫', "level": 1}],
    "spell_page_1365_0528": [{"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1365_0529": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}],
    "spell_page_1365_0530": [{"class": '女巫', "level": 3}],
    "spell_page_1365_0531": [{"class": '女巫', "level": 5}],
    "spell_page_1365_0533": [{"class": '异能者', "level": 3}],
    "spell_page_1365_0538": [{"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1365_0539": [{"class": '异能者', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1365_0544": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '审判者', "level": 2}],
    "spell_page_1365_0545": [{"class": '吟游诗人', "level": 3}, {"class": '歌者', "level": 3}, {"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}],
    "spell_page_1365_0547": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '审判者', "level": 2}],
    "spell_page_1365_0548": [{"class": '魔战士', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1365_0549": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '萨满', "level": 2}],
    "spell_page_1365_0550": [{"class": '催眠师', "level": 4}, {"class": '秘学士', "level": 4}],
    "spell_page_1365_0551": [{"class": '异能者', "level": 3}],
    "spell_page_1365_0552": [{"class": '异能者', "level": 5}],
    "spell_page_1365_0553": [{"class": '萨满', "level": 8}, {"class": '术士', "level": 8}, {"class": '法师', "level": 8}, {"class": '奥能师', "level": 8}],
    "spell_page_1365_0554": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '通灵者', "level": 2}],
    "spell_page_1365_0555": [{"class": '秘学士', "level": 4}, {"class": '异能者', "level": 5}],
    "spell_page_1365_0556": [{"class": '牧师', "level": 0}, {"class": '先知', "level": 0}, {"class": '战斗祭司', "level": 0}, {"class": '德鲁伊', "level": 0}, {"class": '猎人', "level": 0}],
    "spell_page_1365_0557": [{"class": '萨满', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_1365_0558": [{"class": '德鲁伊', "level": 2}, {"class": '魔战士', "level": 2}],
    "spell_page_1365_0559": [{"class": '审判者', "level": 1}, {"class": '魔战士', "level": 1}],
    "spell_page_1365_0560": [{"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}],
    "spell_page_1365_0561": [{"class": '牧师', "level": 4}, {"class": '先知', "level": 4}, {"class": '战斗祭司', "level": 4}, {"class": '德鲁伊', "level": 4}, {"class": '猎人', "level": 4}],
    "spell_page_1365_0562": [{"class": '德鲁伊', "level": 7}, {"class": '审判者', "level": 6}],
    "spell_page_1365_0563": [{"class": '萨满', "level": 2}],
    "spell_page_1365_0564": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '德鲁伊', "level": 2}],
    "spell_page_1365_0565": [{"class": '秘学士', "level": 5}, {"class": '游侠', "level": 3}, {"class": '猎人', "level": 3}, {"class": '萨满', "level": 5}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}],
    "spell_page_1365_0566": [{"class": '魔战士', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1365_0567": [{"class": '女巫', "level": 2}],
    "spell_page_1365_0568": [{"class": '萨满', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_1365_0571": [{"class": '女巫', "level": 3}],
    "spell_page_1365_0572": [{"class": '异能者', "level": 9}, {"class": '女巫', "level": 9}],
    "spell_page_1365_0573": [{"class": '通灵者', "level": 3}, {"class": '秘学士', "level": 3}, {"class": '异能者', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_1365_0574": [{"class": '审判者', "level": 2}, {"class": '通灵者', "level": 1}, {"class": '异能者', "level": 2}],
    "spell_page_1365_0575": [{"class": '审判者', "level": 4}, {"class": '通灵者', "level": 3}, {"class": '异能者', "level": 5}, {"class": '游侠', "level": 3}, {"class": '猎人', "level": 3}],
    "spell_page_1365_0576": [{"class": '女巫', "level": 7}],
    "spell_page_1365_0577": [{"class": '女巫', "level": 8}],
    "spell_page_1365_0578": [{"class": '血脉狂怒者', "level": 3}, {"class": '魔战士', "level": 3}],
    "spell_page_1365_0579": [{"class": '审判者', "level": 2}, {"class": '秘学士', "level": 2}],
    "spell_page_1365_0580": [{"class": '审判者', "level": 1}, {"class": '秘学士', "level": 1}],
    "spell_page_1365_0581": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '秘学士', "level": 2}],
    "spell_page_1365_0582": [{"class": '秘学士', "level": 1}, {"class": '游侠', "level": 1}, {"class": '猎人', "level": 1}],
    "spell_page_1365_0583": [{"class": '秘学士', "level": 2}, {"class": '游侠', "level": 2}],
    "spell_page_1365_0593": [{"class": '德鲁伊', "level": 1}, {"class": '猎人', "level": 1}, {"class": '魔战士', "level": 1}, {"class": '游侠', "level": 1}, {"class": '萨满', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '女巫', "level": 1}],
    "spell_page_1365_0599": [{"class": '魔战士', "level": 3}, {"class": '萨满', "level": 4}],
    "spell_page_1365_0600": [{"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '萨满', "level": 3}],
    "spell_page_1365_0601": [{"class": '血脉狂怒者', "level": 2}, {"class": '德鲁伊', "level": 3}, {"class": '猎人', "level": 3}],
    "spell_page_1365_0602": [{"class": '魔战士', "level": 2}, {"class": '萨满', "level": 3}],
    "spell_page_669_0000": [{"class": '吟游诗人', "level": 2}, {"class": '歌者', "level": 2}, {"class": '牧师', "level": 3}, {"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '催眠师', "level": 3}, {"class": '萨满', "level": 3}],
    "spell_page_669_0001": [{"class": '催眠师', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_669_0003": [{"class": '吟游诗人', "level": 1}, {"class": '歌者', "level": 1}, {"class": '血脉狂怒者', "level": 1}, {"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '催眠师', "level": 1}, {"class": '异能者', "level": 1}, {"class": '萨满', "level": 2}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '唤魂师', "level": 2}, {"class": '女巫', "level": 1}],
    "spell_page_669_0004": [{"class": '反圣武士', "level": 1}, {"class": '血脉狂怒者', "level": 1}, {"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '德鲁伊', "level": 1}, {"class": '猎人', "level": 1}, {"class": '魔战士', "level": 1}, {"class": '异能者', "level": 1}, {"class": '萨满', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '召唤师', "level": 1}],
    "spell_page_669_0006": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '通灵者', "level": 2}, {"class": '催眠师', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_669_0007": [{"class": '牧师', "level": 5}, {"class": '先知', "level": 5}, {"class": '战斗祭司', "level": 5}, {"class": '德鲁伊', "level": 5}, {"class": '猎人', "level": 5}, {"class": '通灵者', "level": 4}, {"class": '催眠师', "level": 4}, {"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '女巫', "level": 5}],
    "spell_page_669_0010": [{"class": '审判者', "level": 1}, {"class": '萨满', "level": 1}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_669_0011": [{"class": '吟游诗人', "level": 3}, {"class": '歌者', "level": 3}, {"class": '催眠师', "level": 3}, {"class": '萨满', "level": 3}, {"class": '女巫', "level": 3}],
    "spell_page_669_0013": [{"class": '奥能师', "level": 0}, {"class": '术士', "level": 0}, {"class": '法师', "level": 0}],
    "spell_page_669_0015": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '审判者', "level": 1}, {"class": '秘学士', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}],
    "spell_page_669_0016": [{"class": '催眠师', "level": 2}, {"class": '萨满', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_669_0017": [{"class": '秘学士', "level": 3}, {"class": '术士', "level": 3}, {"class": '法师', "level": 3}, {"class": '奥能师', "level": 3}, {"class": '召唤师', "level": 2}, {"class": '女巫', "level": 3}],
    "spell_page_669_0018": [{"class": '血脉狂怒者', "level": 2}, {"class": '魔战士', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_669_0019": [{"class": '奥能师', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}],
    "spell_page_669_0020": [{"class": '吟游诗人', "level": 2}, {"class": '歌者', "level": 2}, {"class": '催眠师', "level": 2}, {"class": '异能者', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_669_0021": [{"class": '奥能师', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}],
    "spell_page_669_0022": [{"class": '女巫', "level": 3}],
    "spell_page_669_0023": [{"class": '女巫', "level": 8}],
    "spell_page_693_0002": [{"class": '德鲁伊', "level": 2}, {"class": '猎人', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '召唤师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_693_0003": [{"class": '萨满', "level": 4}, {"class": '召唤师', "level": 4}, {"class": '女巫', "level": 4}],
    "spell_page_717_0000": [{"class": '圣武士', "level": 4}, {"class": '游侠', "level": 4}, {"class": '猎人', "level": 4}],
    "spell_page_717_0001": [{"class": '圣武士', "level": 2}],
    "spell_page_717_0003": [{"class": '圣武士', "level": 4}],
    "spell_page_717_0004": [{"class": '圣武士', "level": 2}],
    "spell_page_717_0006": [{"class": '圣武士', "level": 3}, {"class": '游侠', "level": 4}, {"class": '猎人', "level": 4}],
    "spell_page_717_0007": [{"class": '圣武士', "level": 3}, {"class": '游侠', "level": 4}, {"class": '猎人', "level": 4}],
    "spell_page_717_0008": [{"class": '圣武士', "level": 1}],
    "spell_page_717_0009": [{"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '牧师', "level": 2}],
    "spell_page_717_0010": [{"class": '先知', "level": 4}, {"class": '战斗祭司', "level": 4}, {"class": '牧师', "level": 4}],
    "spell_page_717_0011": [{"class": '先知', "level": 3}, {"class": '战斗祭司', "level": 3}, {"class": '牧师', "level": 3}],
    "spell_page_718_0001": [{"class": '奥能师', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}],
    "spell_page_718_0002": [{"class": '奥能师', "level": 9}, {"class": '术士', "level": 9}, {"class": '法师', "level": 9}],
    "spell_page_718_0003": [{"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}, {"class": '召唤师', "level": 4}, {"class": '女巫', "level": 4}],
    "spell_page_718_0004": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_718_0005": [{"class": '术士', "level": 5}, {"class": '法师', "level": 5}, {"class": '奥能师', "level": 5}, {"class": '召唤师', "level": 5}, {"class": '女巫', "level": 5}],
    "spell_page_719_0001": [{"class": '德鲁伊', "level": 1}, {"class": '猎人', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}],
    "spell_page_719_0005": [{"class": '奥能师', "level": 7}, {"class": '术士', "level": 7}, {"class": '法师', "level": 7}],
    "spell_page_720_0001": [{"class": '牧师', "level": 1}, {"class": '先知', "level": 1}, {"class": '战斗祭司', "level": 1}, {"class": '德鲁伊', "level": 1}, {"class": '圣武士', "level": 1}, {"class": '游侠', "level": 1}, {"class": '猎人', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}],
    "spell_page_720_0002": [{"class": '牧师', "level": 2}, {"class": '先知', "level": 2}, {"class": '战斗祭司', "level": 2}, {"class": '圣武士', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}],
    "spell_page_720_0003": [{"class": '游侠', "level": 4}, {"class": '猎人', "level": 4}, {"class": '术士', "level": 6}, {"class": '法师', "level": 6}, {"class": '奥能师', "level": 6}],
    "spell_page_805_0001": [{"class": '游侠', "level": 2}, {"class": '术士', "level": 2}, {"class": '法师', "level": 2}, {"class": '奥能师', "level": 2}, {"class": '召唤师', "level": 2}, {"class": '女巫', "level": 2}],
    "spell_page_805_0005": [{"class": '德鲁伊', "level": 4}, {"class": '猎人', "level": 4}, {"class": '萨满', "level": 4}, {"class": '术士', "level": 4}, {"class": '法师', "level": 4}, {"class": '奥能师', "level": 4}, {"class": '召唤师', "level": 4}],
    "spell_page_852_0001": [{"class": '德鲁伊', "level": 7}, {"class": '猎人', "level": 7}, {"class": '术士', "level": 7}, {"class": '法师', "level": 7}, {"class": '奥能师', "level": 7}, {"class": '召唤师', "level": 6}],
    "spell_page_883_0006": [{"class": '秘学士', "level": 1}, {"class": '通灵者', "level": 1}, {"class": '萨满', "level": 1}, {"class": '术士', "level": 1}, {"class": '法师', "level": 1}, {"class": '奥能师', "level": 1}, {"class": '女巫', "level": 1}],
}

# KN244/246 标题正名后，白名单旧 ID 对应的原始标题。
# 仅登记新旧标题不一致项，回退时必须再次核对，防止值错挂到正名后的条目。
_SPELL_LEVEL_A_BUCKET_TITLE_OVERRIDES = {
    "spell_page_1107_0013": "幻肢",
    "spell_page_1331_0007": "隔绝思维",
    "spell_page_1363_0085": "隔绝思维",
    "spell_page_1365_0342": "秘藏柜",
    "spell_page_1365_0599": "蜻蜓诅咒",
    "spell_page_1365_0304": "死亡契约",
    "spell_page_1365_0305": "欺敌传送",
    "spell_page_1365_0324": "仙人掌粹的活力",
    "spell_page_1365_0556": "绝处逢生",
    "spell_page_1365_0557": "法师的徐行空间",
}


# KN245 裁除集（2026-10-30 已清零）：18 条全部裁定——14 条回填、3 条经 SMF010
# 标签容错回填、阿底顿 2 条转 _NON_SPELL_ENTRIES。机制保留为空集：未来出现
# 「源行不可证但又非空不可」的条目时在此登记，任何通道（白名单/补救）均不回填。
_SPELL_LEVEL_CUT_EXCLUSIONS = frozenset()
_SPELL_LEVEL_CUT_EXCLUSION_TITLES = {}

# 非法术条目（KN245 2026-10-30 裁定）：源页把毒品/物品条目排进法术目录，
# 字段为 类型/成瘾性/价格/伤害，没有学派与环级。保留在 chunks 内不迁移分类，
# 仅把 spell_level 标为 not_applicable，使其不参与空率门与清单派生。
_NON_SPELL_ENTRIES = frozenset({
    ("page_1494", "阿底顿"),
})


def _legacy_spell_chunk_id(chunk_id: str, legacy_id_map=None) -> Optional[str]:
    """查派生映射；显式无锚的新条目返回 None，避免同号误挂白名单。"""
    if legacy_id_map is None:
        legacy_id_map = load_legacy_id_map(str(DERIVED_STATE_PATH))
    if chunk_id in legacy_id_map:
        return legacy_id_map[chunk_id]
    return chunk_id


def _is_cut_exclusion(chunk_id: str, title: str, legacy_id_map=None) -> bool:
    """按旧 ID 与条目标题双键判定裁除，避免顺移后的同号误伤。"""
    legacy_id = _legacy_spell_chunk_id(chunk_id, legacy_id_map)
    return legacy_id is not None and _SPELL_LEVEL_CUT_EXCLUSION_TITLES.get(legacy_id) == title


# C 桶补救通道职业词表（修订 1 M2 词表校验同口径）：规范 26 职业 + 已批
# 不动/合法项（红螳螂杀手/召唤师（Unchained）/诡术师/巡林客/导师）。
# 词表外 token（正文残句/垃圾串/表外脏名）→ 该条补救结果整体丢弃——
# 结构性拦住裁除项（KN245 终态 3 条）经补救通道复活。
_SPELL_LEVEL_RESCUE_LEGAL_CLASSES = frozenset([
    "术士", "法师", "女巫", "牧师", "吟游诗人", "德鲁伊", "先知", "审判者",
    "魔战士", "奥能师", "异能者", "召唤师", "游侠", "圣武士", "炼金术师",
    "萨满", "反圣武士", "战斗祭司", "催眠师", "秘学士", "歌者", "通灵者",
    "猎人", "唤魂师", "血脉狂怒者", "调查员",
    "红螳螂杀手", "召唤师（Unchained）", "诡术师", "巡林客", "导师",
])


# 复合职业漏 `/` 分隔的特批拆条（审批表第 20 组：术士法师 → 术士+法师，
# 走 F3 同序）；仅含该一组获批项。
_CLASS_COMPOUND_SPLIT = {"术士法师": ("术士", "法师")}


_RE_REPEATED_WORD = re.compile(r"^(.{2,6}?)\1(诗人|歌者|术士|法师|术师|祭司|战士|师)$")


def _repair_repeated_word(cls: str) -> str:
    """KN245 获批通用规则：「XXYY→XY」型重复词修复（吟游吟游诗人→吟游诗人）。

    保守形态：仅前段严格重复 + 白名单职业后缀命中时修复；无命中原样返回。
    """
    m = _RE_REPEATED_WORD.match(cls)
    if m:
        return m.group(1) + m.group(2)
    return cls


def _normalize_spell_level_items(items: list) -> list:
    """R3：spell_level 条目归一（幂等，覆盖所有产出路径）。

    class=None（裸环级 R4）保持原样；复合拆条展开为多条（level 复制）；
    KN245 通用规则：重复词修复 + 复合组内 (class, level) 去重（保首）。
    """
    out = []
    for it in items:
        cls = it.get("class")
        if cls is None:
            out.append(it)
            continue
        if cls in _CLASS_COMPOUND_SPLIT:
            for sub in _CLASS_COMPOUND_SPLIT[cls]:
                out.append({"class": sub, "level": it["level"]})
            continue
        cls = _repair_repeated_word(cls)
        norm = _normalize_class_name(cls)
        # 修复/归一任一命中即用新值（repair 改了但 NORM 未改时也不能回落原值）
        item = it if (norm == cls == it["class"]) else {"class": norm, "level": it["level"]}
        # 复合组内重复 token 去重（KN245：牧师/先知/奥能师/先知 → 先知 保首一次）
        if any(o.get("class") == item["class"] and o.get("level") == item["level"]
               for o in out):
            continue
        out.append(item)
    return out


def _normalize_class_name(cls: str) -> str:
    """R3：职业名归一（仅获批 20 组映射，映射表外保持原样）。"""
    return _CLASS_NAME_NORM.get(cls, cls)


def _truncate_trailing_prose(level_str: str) -> str:
    """环位取值预处理与尾部散文截断（两产出路径 _extract/rescue 共用）。

    1. 分号当组分隔符（KN245）：召唤师 4；女巫 3 → 两组，归一为顿号后走标准解析。
    2. SMF010：值后紧贴下一字段标签（…术士/法师3施法时间 标准动作）时先切断，
       否则末尾职业组会被尾部散文一起丢弃；只切断取值，不新增字段。
    3. 截断尾部散文：找到最后一个 "职业名 N"（行尾）的位置，丢弃其后内容。
       例："术士/法师 8\\n\\n该法术的功能如同..." → "术士/法师 8"
    """
    level_str = (level_str or "").replace("；", "、").replace(";", "、")
    level_str = re.split(
        r'(?<=\d)(?:施法时间|施放时间|法术成分|成分|范围|目标|持续时间|豁免|法术抗力)',
        level_str, maxsplit=1,
    )[0]
    if not level_str:
        return level_str

    # 找到最后一个 "词 数字" 的位置（数字不限在末尾）
    # 匹配模式：中文字符或字母 + 空格 + 数字
    matches = list(re.finditer(r'([^\s,，]+)\s+(\d+)\s*$', level_str, re.MULTILINE))
    m = matches[-1] if matches else None
    if not m:
        # fallback: 找纯数字在行尾
        matches = list(re.finditer(r'(?:^|\s)(\d+)\s*$', level_str, re.MULTILINE))
        m = matches[-1] if matches else None

    if m:
        # 截断到该匹配之后（保留到该数字为止）
        end_pos = m.end()
        # 清理尾部空白和换行
        truncated = level_str[:end_pos].rstrip('，,；; \t\n\r')
        return truncated
    return level_str


# KN013 M2：通用字段值截断器（duration/target/effect/range/casting_time 共用）
# 截断信号：句末标点（。）后仍有 >10 字符正文，或 \n 后的行不以续行信号开头。
# 续行信号：行首为 + / ( / （ / 和 / 或 / ， / 、 / 数字。
# duration 专属：保留 (D) / （可消解） / （解消） / (见后文) 等终止标记。

_CONTINUATION_PREFIXES = ("+", "(", "（", "和", "或", "，", "、", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "/", "*")
_DURATION_TERMINATORS = ("(D)", "（可消解）", "（解消）", "(见后文)", "（见后文）")


# KN013 M1：字段值内联 `**` 残留剥除（值边界不完整把下一字段标签/正文吞进值内）。
# 残留形态实测（2026-09-23 全量扫描 119 处 `**` / 95 chunks，新基线 4172）：
#   a. `120尺**区域：** 120尺长...`   —— 行内吞下一字段标签+值 → 从 `**` 处截断
#   b. `个人**法术` / `1轮/等级**科莱什人...` —— 行内吞标签/正文 → 从 `**` 处截断
#   c. `专注，最高10分钟/等级 **\n(可解消)` —— 行尾悬挂 `**`（加粗跨行残留），
#      后续行是合法续行 → 只摘 `**`，保留续行
#   d. `两个生物\n**` / `...\n**意志，通过则部分...` —— `**` 在行首（下一字段块起点）
#      → 从 `**` 处截断
#   e. `**1轮/级`（值首悬挂）→ 剥前导星

def _strip_inline_label_residue(value: str) -> str:
    """剥除字段值内混入的内联 `**` 标签/正文残留（KN013 M1）。"""
    if not value or "**" not in value:
        return value
    from vectorizer.registry import ALL_FIELD_LABELS

    label_pat = re.compile(
        r'^(?:' + "|".join(re.escape(l) for l in ALL_FIELD_LABELS) + r')(?=[：:*\s]|$)'
    )

    v = value.lstrip("*").lstrip()
    modified = False
    while "**" in v:
        idx = v.find("**")
        before, after = v[:idx], v[idx + 2:]
        # 规则 d：`**` 在行首（含值首，前导已剥）→ 字段边界，截断
        if before == "" or before.endswith("\n"):
            v = before.rstrip(" \t，,；;")
            modified = True
            break
        # 规则 a：`**` 后为已知字段标签 → 字段边界，截断
        if label_pat.match(after.lstrip()):
            v = before.rstrip(" \t，,；;")
            modified = True
            break
        # 规则 c：`**` 行尾悬挂（同行其后无实质内容），后续行是合法续行
        # → 只摘 `**` 及同行残余
        rest_of_line = after.split("\n", 1)[0]
        if rest_of_line.strip(" \t，,；;。") == "":
            v = before + after[len(rest_of_line):]
            modified = True
            continue
        # 规则 b：行内吞正文/非标标签 → 从 `**` 处截断
        v = before.rstrip(" \t，,；;")
        modified = True
        break
    if modified:
        # `值 或 **` 类形态摘星后会留下悬空连接词（或/和），一并摘除
        v = re.sub(r'[ \t]*[或和]\s*$', '', v).rstrip(" \t，,；;")
    return v.strip()


def _parse_field_value(value: str, *, field: str = "") -> str:
    """KN013 方案 A：字符串字段值清洗层 = M1 内联残留剥除 + M2 尾部散文截断。"""
    return _truncate_value_prose(_strip_inline_label_residue(value), field=field)

# R5: 字段值末尾粘附的散文起始信号（如 Spell UI 格式中 duration 直接粘 "该法术的功能如同..."）
# 当值中出现这些模式时，从模式起始处截断。
_PROSE_LEAD_INS: tuple[str, ...] = (
    "该法术的功能如同", "该法术的功能就如",
    "该法术工作方式如同", "该法术工作方式就如",
    "这个法术工作方式如同", "这个法术的功能如同",
    "此法术的功能如同", "此法术工作方式如同",
)


def _truncate_value_prose(value: str, *, field: str = "") -> str:
    """KN013 M2：截断字段值中的尾部散文（适用于 target/effect/range/casting_time/duration）。

    算法（执行顺序按两轮审计复盘后的稳定顺序，2026-07-30 修订）：
      1. R5 散文信号截断（_PROSE_LEAD_INS，对整体值）—— 必须在 \\n 分支之前，
         否则 duration 两行值时第二行非续行字符会提前 return 脏值，R5 永远执行不到
      2. 通用：`\\n` 截断，第二行若以 `**` 开头（KN012 拆行后的下一字段块）→ 视为字段边界截断
         —— 必须在 duration 终止标记之前，否则 `1分钟\\n**无 (见后文)` 会被终止标记早 return
      3. duration 专属终止标记（(D) / （可消解）等）
      4. 通用：`。` 后仍有 >10 字符正文 → 截到 `。` 之后

    反例保护：
      - 合法续行（如 range `近距 (25尺\\n+ 5尺/2级)`）完整保留
      - 单 `*` 开头的合法续行（如存在）放行；`**` 开头视为字段边界截断
      - 单句以 `。` 结尾且 `。` 后无 >10 字符 → 保留
    """
    if not value:
        return value

    # ---- R5：散文起始信号截断（"该法术的功能如同..." 等）----
    # 必须在 \\n 分支之前：对整体值检查，找到散文信号即截断，
    # 避免 \\n 分支对 duration 两行值提前 return 脏首行。
    for lead_in in _PROSE_LEAD_INS:
        idx = value.find(lead_in)
        if idx > 0:  # 信号不在值的最开头（否则可能是合法值）
            return value[:idx].rstrip("，,；; \t\n\r")

    # ---- 通用：`\n` 截断 ----
    # 必须在 duration 终止标记之前，否则 `(见后文)` 等终止标记在中间匹配时
    # 会让函数早 return 原值，跳过对 \\n** 残留的清理。
    lines = value.split("\n")
    if len(lines) > 1:
        second = lines[1].lstrip()
        if second:
            # Bug A (2026-07-30)：第二行以 `**` 开头视为字段边界截断
            # KN012 拆行后字段值呈 `值\\n**下一字段**` 形态，
            # `_CONTINUATION_PREFIXES` 中 `*` 项必须不匹配 `**`。
            if second.startswith("**"):
                return lines[0].rstrip("，,；; \t\n\r")
            # 第二行若不以续行信号开头 → 截断到第一行末尾
            if not second.startswith(_CONTINUATION_PREFIXES):
                return lines[0].rstrip("，,；; \t\n\r")

    # ---- duration 专属终止标记 ----
    if field == "duration":
        for term in _DURATION_TERMINATORS:
            idx = value.find(term)
            if idx >= 0:
                cut_at = idx + len(term)
                rest = value[cut_at:]
                # 若终止标记后紧跟 >10 字符 CJK 正文 → 截断
                # 判定：首个 CJK 字符出现位置 < 10 字符视为延续，否则视为正文截断
                if rest and len(rest.strip()) > 10:
                    return value[:cut_at].rstrip("，,；; \t\n\r")
                # 终止标记后无正文或短文本 → 保留原值
                return value

    # ---- 通用：`。` 后正文截断 ----
    # 找到第一个 `。` 的位置；其后若还有 >10 字符非空内容 → 截断到 `。` 之后
    m = re.search(r'。', value)
    if m:
        after = value[m.end():].strip()
        if len(after) > 10:
            return value[:m.end()].rstrip("，,；; \t\n\r")

    return value


def parse_fields(text: str) -> dict:
    """从统一 IR 文本中提取所有字段的原始字符串值。

    输入前提：text 已通过 _unify_field_labels() 归一化为 **标签：** 值 格式。
    使用 LABEL_TO_KEY 将中文标签映射为规范 key，返回 {canonical_key: raw_value_str}。

    算法：
      1. 用 ALL_FIELD_LABELS + EXTRA_FORMAT_LABELS 构建匹配所有中文标签的 regex
      2. 值 = 从当前标签冒号后到下一个 **标签：** 或文本末尾
      3. 缺失字段值为空字符串 ""
    KN013 M5：EXTRA_FORMAT_LABELS（描述/诡计描述/伪装对象）也作为值边界，
    防止前面字段（duration/range/target 等）吞入描述文本。
    """
    from vectorizer.registry import ALL_FIELD_LABELS, EXTRA_FORMAT_LABELS, LABEL_TO_KEY

    result: dict[str, str] = {}
    if not text:
        return result

    # 构建标签交替 regex（长标签优先，已在 registry 中保证）。
    # KN013 M5：边界识别扩展为 ALL_FIELD_LABELS + EXTRA_FORMAT_LABELS，
    # 描述/诡计描述/伪装对象也可作为值边界，但 LABEL_TO_KEY 不含它们，
    # 不会误产生新字段。
    boundary_labels = ALL_FIELD_LABELS + EXTRA_FORMAT_LABELS
    labels_pattern = "|".join(re.escape(label) for label in boundary_labels)
    # 字段捕获标签集仍只含规范字段别名（LABEL_TO_KEY 的范围）
    capture_labels_pattern = "|".join(re.escape(label) for label in ALL_FIELD_LABELS)
    # 字段值边界：下一个字段标签（标准或变体）、空白行（\n\n）、或文本末尾
    # \n\n 作为硬边界是安全的：数据中字段值从不跨空白行（已实测确认）
    # 边界 lookahead 同时识别 **Label：** 和 **Label**：两种形式
    next_field = (
        rf'\n\n'
        rf'|\n\*\*(?:{labels_pattern})[：:]\*\*'
        rf'|\n\*\*(?:{labels_pattern})\*\*[：:]'
    )
    # 格式 1: **标签：** 值（统一 IR 标准格式）
    field_re = re.compile(
        rf'\*\*({capture_labels_pattern})[：:]\*\*\s*([\s\S]*?)(?={next_field}|\Z)',
        re.MULTILINE,
    )
    # 格式 2: **标签**：值（** 在冒号前关闭的残留格式，安全网）
    field_re_v2 = re.compile(
        rf'\*\*({capture_labels_pattern})\*\*[：:]\s*([\s\S]*?)(?={next_field}|\Z)',
        re.MULTILINE,
    )

    def _extract(match_re):
        for m in match_re.finditer(text):
            label = m.group(1)
            value = m.group(2).strip()
            # 去掉值末尾可能的 ** 残留（裸标签残留/格式符）
            value = value.rstrip("*").strip()
            # 全角空格 → 半角
            value = value.replace("　", " ")
            key = LABEL_TO_KEY.get(label)
            if key and key not in result:
                result[key] = value

    # 优先标准格式，再 fallback 格式 2
    _extract(field_re)
    _extract(field_re_v2)

    # KN242 修订 1 M3：环位值学派检测守卫（first-wins 局部修复，方案选型 B）。
    # 缺陷形态：`**环位：**塑能系` 先行占位 → first-wins 丢弃后续 `**等级：**职业N…`
    # 正确行（约 10 条）。守卫仅对 spell_level 键生效：首值为纯学派名（复用
    # _extract_school 9 学派白名单口径，含别名）时，取后续 **等级：** 行值；
    # 其他字段行为零变化，非学派首值零变化。
    _sl_first = (result.get("spell_level") or "").lstrip("*").strip()
    if _sl_first and re.match(
        r"^(防护|咒法|预言|惑控|塑能|幻术|死灵|变化|通用|附魔)(系)?\s*$", _sl_first
    ):
        m_lv = re.search(r"\*\*等级[：:]\*\*\s*([^\n]{1,200})", text)
        if m_lv:
            result["spell_level"] = m_lv.group(1).strip()

    return result


class SpellProcessor(FileProcessor):
    """法术文件处理器"""

    # 阶段二（2026-09-01，k3 裁定 3 方案 A）：KN011 link 内建为 finalize 组件，
    # 对齐 feat 决策 A——pipeline 单命令产出含 link 的最终态。link 不删行，
    # index.json 与 chunks 行数天然一致（pipeline _write_index 先于 _finalize）。
    # 2026-09-21（KN233）：追加 SupplementSpellAliases——curated 中文别名补录
    # （社区通用译名，源 md 不改），置于 link 之后（link 只读 aliases 建索引，
    # 补充别名不影响 KN011 命中语义）。
    POSTPROCESSORS = [LinkMythicBaseSpells, SupplementSpellAliases]
    _legacy_id_map = None

    @property
    def category(self) -> str:
        return "spell"

    def __init__(self, source_resolver: SourceResolver):
        super().__init__(source_resolver=source_resolver, format_handler=SpellFormat())
        self.spell_index_provider: Optional[SpellIndexProvider] = None
        self._legacy_id_map = None

    def build_chunk(self, template: Chunk, item: dict) -> Chunk:
        """设置法术标题、正文和英文别名"""
        template.title = item.get("name", "")
        template.text = item.get("text", "")
        template.aliases = [item.get("name_en", "")] if item.get("name_en") else []
        return template

    def resolve_source(self, chunk: Chunk, ctx: SourceContext, item: dict) -> Chunk:
        """解析来源书：文件名优先 → SpellIndexProvider fallback"""
        result = self.source_resolver.resolve(ctx)
        chunk.book_abbreviation = result.book_abbreviation
        chunk.book_name_cn = result.book_name_cn
        chunk.book_name_en = result.book_name_en
        chunk.source_confidence = result.confidence
        return chunk

    def infer_metadata(self, chunk: Chunk, item: dict) -> Chunk:
        """schema v0.3：parse_fields() 主路径 + 旧方法 fallback。

        优先从统一 IR 文本中用 parse_fields() 提取所有字段原始值，
        然后经过各字段类型转换器输出结构化 metadata。
        parse_fields 未覆盖的字段由 _infer_school / _infer_level 等 fallback 补位。
        """
        text = item.get("text", "")
        raw = parse_fields(text)

        metadata: dict[str, Any] = {}

        # 学派：parse_fields 优先，fallback _infer_school
        metadata["school"] = self._extract_school(raw, item)

        # 子学派：从 school 原始值的 (...) 提取
        metadata["subschool"] = self._extract_subschool(raw)

        # 描述符：委托 SpellFormat.parse_descriptors（不改现有逻辑）
        metadata["descriptor"] = self._extract_descriptor(text)

        # 环位：parse_fields 优先，fallback _infer_level，再 fallback 头残片白名单
        spell_level = self._extract_spell_level(raw)
        if not spell_level:
            spell_level = self._infer_level(item)
        if not spell_level:
            # M1 C 桶窄路（修订 1 返工 F1：rescue 优先于白名单）——rescue 从
            # _pre_unify 源行重算，值更完整（白名单 evidence 为头残片，缺被
            # 吞吃首组职业）；两级 fallback 均空才触发；MA/裸数字/词表外丢弃
            spell_level = self._rescue_inline_level(item, chunk, self._legacy_id_map)
        if not spell_level:
            spell_level = self._a_bucket_whitelist_level(item, chunk, self._legacy_id_map)
        else:
            legacy_id = _legacy_spell_chunk_id(chunk.chunk_id, self._legacy_id_map)
            expected_title = _SPELL_LEVEL_A_BUCKET_TITLE_OVERRIDES.get(legacy_id)
            current_title = (item.get("name") or "").strip()
            if not expected_title or current_title == expected_title:
                # 白名单校验锚（F1）：旧 ID + 标题双键，rescue 已产出时只校验不覆盖。
                expected = SPELL_LEVEL_A_BUCKET_WHITELIST.get(legacy_id, [])
                got = {(it["class"], it["level"]) for it in _normalize_spell_level_items(spell_level)}
                missing = [it for it in expected if (it["class"], it["level"]) not in got]
                if missing:
                    print(f"⚠️ KN242-F1 对账异常 {chunk.chunk_id}: "
                          f"rescue 结果缺白名单项 {missing}（rescue={spell_level}）")
        # 裁除红线覆盖所有解析路径：主解析/rescue/白名单均不得回填。
        if _is_cut_exclusion(
            chunk.chunk_id, (item.get("name") or "").strip(), self._legacy_id_map
        ):
            spell_level = []
        # R3 归一（覆盖全部路径：主路径 _extract_spell_level / _infer_level /
        # 头残片 fallback 的 class 值统一在此处理，幂等）：
        #   ① CLASS_NAME_NORM 逐条获批映射（20 组）；② 复合职业漏分隔特批拆条
        #   （术士法师 → 术士 + 法师，审批表第 20 组）；不动项（巡林客/导师/
        #   红螳螂杀手/召唤施等）不在表内自然保持原样。
        spell_level = _normalize_spell_level_items(spell_level)
        metadata["spell_level"] = spell_level

        # 领域/子域：从 spell_level 原始值剥离
        metadata["domains"] = self._extract_domains_from_level(raw)
        metadata["subdomains"] = self._extract_subdomains_from_level(raw)

        # 施法时间
        metadata["casting_time"] = _parse_field_value(
            raw.get("casting_time", "") or raw.get("施法时间", "") or raw.get("施放时间", ""),
            field="casting_time",
        )

        # 成分
        metadata["components"] = self._parse_components(raw.get("components", "") or raw.get("成分", "") or raw.get("法术成分", ""))

        # 射程
        metadata["range"] = _parse_field_value(self._extract_range(raw), field="range")

        # 目标/区域/效果
        metadata["target"] = _parse_field_value(
            raw.get("target", "") or raw.get("目标", ""),
            field="target",
        )
        area_val = self._extract_area(raw)
        metadata["area"] = _strip_inline_label_residue(area_val) if area_val else area_val
        metadata["effect"] = _parse_field_value(
            raw.get("effect", "") or raw.get("效果", ""),
            field="effect",
        )

        # 持续时间
        metadata["duration"] = _parse_field_value(
            raw.get("duration", "") or raw.get("持续时间", "") or raw.get("持续", ""),
            field="duration",
        )

        # 豁免/法术抗力
        metadata["saving_throw"] = self._parse_saving_throw(
            raw.get("saving_throw", "") or raw.get("豁免", "") or raw.get("豁免检定", "")
        )
        metadata["spell_resistance"] = self._parse_spell_resistance(
            raw.get("spell_resistance", "") or raw.get("法术抗力", "") or raw.get("抗力", "") or raw.get("SR", "")
        )

        # field_status
        metadata["field_status"] = self._compute_field_status(metadata)

        # 非法术条目（KN245）：源页把毒品/物品条目排进法术目录，环级不适用。
        if (chunk.doc_id or "", (item.get("name") or "").strip()) in _NON_SPELL_ENTRIES:
            metadata["spell_level"] = []
            metadata["field_status"]["spell_level"] = "not_applicable"

        # 保留现有 subschool_variants 逻辑（ceremony 等多形态子条目）
        variants = self._infer_subschool_variants(item)
        if variants:
            metadata["subschool_variants"] = variants

        chunk.metadata = metadata
        return chunk

    # 中文/英文名 → subschool_variants tag 的映射表
    # 仅 ceremony（任务与战役_法术.md）使用此结构，其余文件不变
    _SUBSCHOOL_VARIANT_MAP = {
        "funeral": ("葬礼", "funeral"),
        "holiday_fete": ("节庆", "holiday", "fete"),
        "marriage": ("婚礼", "marriage"),
        "naming": ("赐名", "naming"),
        "domain_ceremony": ("领域典礼", "domain", "ceremony"),
    }

    def _infer_subschool_variants(self, item: dict) -> list[str]:
        """检测子条目（如 - 葬礼 (Funeral)）并返回其 slug 列表。
        匹配策略：
          1. 取 chunk.text 中所有 `- XxxName (...)` 行（编号列表项）
          2. 将中文名/英文名映射到 _SUBSCHOOL_VARIANT_MAP 的 slug
          3. 去重保持顺序，返回列表
        """
        text = item.get("text", "")
        import re
        # 匹配 `- <中文变体名>[ \t]*（English）` 或 `- <英文> (English)`
        # 注意：英文 caption 可能是 `Funeral` 等单英文词，也可能跨行
        # `Holiday\nFete`。先合并相邻英文段，再统一匹配。
        lines = text.split("\n")
        variants: list[str] = []
        seen: set[str] = set()
        i = 0
        while i < len(lines):
            line = lines[i]
            m = re.match(r'^-\s+([^\n（(]+?)\s*[（(](.*)$', line)
            if not m:
                i += 1
                continue
            zh_name = m.group(1).strip()
            # 合并括号内可能跨行的英文（如 Holiday\nFete）
            en_part = m.group(2)
            j = i
            while j < len(lines) and en_part.count(")") + en_part.count("）") == 0:
                j += 1
                if j < len(lines):
                    en_part += " " + lines[j].strip()
            en_name = en_part.rstrip(")）").strip()

            # 在 _SUBSCHOOL_VARIANT_MAP 中匹配
            for slug, keywords in self._SUBSCHOOL_VARIANT_MAP.items():
                if slug in seen:
                    continue
                # 中文完全匹配 或 英文任一关键词匹配
                if zh_name == keywords[0]:
                    if slug not in seen:
                        variants.append(slug)
                        seen.add(slug)
                    break
                # 英文关键词
                for kw in keywords[1:]:
                    if kw.lower() in en_name.lower():
                        if slug not in seen:
                            variants.append(slug)
                            seen.add(slug)
                        break
                else:
                    continue
                break  # outer loop
            i = j + 1
        return variants

    def _infer_school(self, item: dict) -> str:
        """从正文中推断学派（支持多种格式变体）"""
        text = item.get("text", "")
        import re

        # 格式 1: **学派：** 值（支持跨行值，到下一个 ** 字段或结尾为止）
        m = re.search(r'\*\*学派[：:]\*\*\s*([\s\S]+?)(?=\n\*\*|$)', text)
        if m:
            raw = m.group(1).strip()
            return self._normalize_school_name(raw)
        # 格式 2: **学派**：值
        m = re.search(r'\*\*学派\*\*[：:]\s*(.+?)(?:\n|$)', text)
        if m:
            raw = m.group(1).strip()
            return self._normalize_school_name(raw)
        # 格式 3: | 学派 值 |（管道表格残留）
        m = re.search(r'\|\s*学派\s+(.+?)\s*\|', text)
        if m:
            raw = m.group(1).strip()
            return self._normalize_school_name(raw)
        # 格式 4: 【学派】值（5a/5b/5c/6/7 格式变体）
        m = re.search(r'^【([^】]+)】', text)
        if m:
            raw = m.group(1).strip()
            return self._normalize_school_name(raw)
        return ""

    @staticmethod
    def _normalize_school_name(raw: str) -> str:
        """归一化学派名：去掉子学派、描述符、格式残留，简称→全称"""
        import re
        # 去掉子学派 (创造)（咒术）
        raw = re.sub(r'[（(][^）)]*[）)]', '', raw)
        # 去掉描述符 【影响心灵】[酸][火]
        raw = re.sub(r'【[^】]*】', '', raw)
        raw = re.sub(r'\[[^\]]*\]', '', raw)
        # 去掉 ** 格式残留
        raw = raw.replace('**', '')
        # 去掉引号残留（如 惑控系 "影响心灵"）
        raw = re.sub(r'["""][^"""]*["'']', '', raw)
        # 去掉尾部标点/空格（内联字段残留）
        raw = re.sub(r'[；;，,\s]+$', '', raw)
        raw = raw.strip()
        # 别名统一映射
        alias_map = {
            # 简称 → 全称
            "咒法": "咒法系", "变化": "变化系", "死灵": "死灵系",
            "塑能": "塑能系", "幻术": "幻术系", "惑控": "惑控系",
            "预言": "预言系", "防护": "防护系",
            # 别名 → 规范名
            "附魔": "惑控系", "附魔系": "惑控系",
            "通用系": "通用", "变形系": "变化系",
            "塑能术": "塑能系",
        }
        if raw in alias_map:
            raw = alias_map[raw]
        return raw

    def _infer_level(self, item: dict) -> list:
        """从正文中推断环位（支持多种格式变体，跨行值）"""
        text = item.get("text", "")
        import re
        level_str = ""
        labels = self._LEVEL_LABELS_PAT
        # 格式 1: **环位/等级：** 值（值可能跨行，直到下一个 ** 字段为止）
        m = re.search(
            rf'\*\*(?:环位|等级)[：:]\*\*\s*([\s\S]+?)(?=\n\*\*(?:{labels}))',
            text
        )
        if m:
            level_str = m.group(1).strip()
        # 格式 2: **环位/等级**：值
        if not level_str:
            m = re.search(
                rf'\*\*(?:环位|等级)\*\*[：:]\s*([\s\S]+?)(?=\n\*\*(?:{labels}))',
                text
            )
            if m:
                level_str = m.group(1).strip()
        if level_str:
            return SpellFormat.parse_spell_level(level_str)
        return []

    # _infer_level 环位正则等用的字段标签列表
    _FIELD_LABELS_PAT = "|".join(LEGACY_13_LABELS)

    _LEVEL_LABELS_PAT = _FIELD_LABELS_PAT

    def _infer_descriptors(self, item: dict) -> list:
        """从正文中提取描述符标签"""
        return SpellFormat.parse_descriptors(item.get("text", ""))

    # ============================================================
    #  schema v0.3 字段提取器
    # ============================================================

    def _extract_school(self, raw: dict, item: dict) -> str:
        """从 parse_fields 结果中提纯学派名。

        KN013 M3：白名单前缀截断。
        school 值被标签-冒号跨行断开污染时（`预言系等级：通灵者 0`、`变化系；等级牧师1`），
        在归一化前先匹配 9 个白名单前缀，命中即截到前缀末尾；未命中保留原文。

        2026-07-30（第3轮返工扩展 M3 +）：先剥离前导 ** 格式残留，让白名单前缀能命中；
          并扩展白名单含别名（附魔/通用系/变形系/塑能术），覆盖 KN013 6 处格拉里昂 schools。
        """
        value = raw.get("school", "")
        if not value:
            value = self._infer_school(item)
        if not value:
            return ""
        # M3+：剥离前导 ** 格式残留，让 M3 正则能命中裸学派遣
        value = value.lstrip("*").lstrip()
        # M3 白名单前缀截断（扩展含别名：附魔/通用系/变形系/塑能术）
        m = re.match(
            r'^(防护|咒法|预言|惑控|塑能|幻术|死灵|变化|通用|附魔)(系)?',
            value
        )
        if m:
            value = m.group(0)
        # 复用现有归一化逻辑
        normalized = self._normalize_school_name(value)
        if normalized in CANONICAL_SCHOOLS or normalized in SCHOOL_ABBR_MAP:
            return SCHOOL_ABBR_MAP.get(normalized, normalized)
        # 白名单校验失败：尝试简称→全称
        expanded = SCHOOL_ABBR_MAP.get(normalized)
        if expanded:
            return expanded
        return normalized  # 未知学派保留归一化后的值

    def _extract_subschool(self, raw: dict) -> Optional[str]:
        """从 school 原始值的 (...) 中提取子学派。"""
        school_raw = raw.get("school", "")
        if not school_raw:
            return None
        m = re.search(r'[（(]([^）)]+)[）)]', school_raw)
        if not m:
            return None
        subschool = m.group(1).strip()
        if not subschool:
            return None
        # 查子学派注册表
        subschools_config = self._load_subschools_config()
        # 用 school 归一化后的值匹配注册表
        school_normalized = self._normalize_school_name(school_raw)
        allowed = subschools_config.get("subschools", {}).get(school_normalized, [])
        if subschool in allowed:
            return subschool
        # 未知子学派：保留原文
        return subschool if subschool else None

    @staticmethod
    def _extract_descriptor(text: str) -> list:
        """委托 SpellFormat.parse_descriptors。"""
        return SpellFormat.parse_descriptors(text)

    @staticmethod
    def _extract_spell_level(raw: dict) -> list:
        """从 spell_level / 环位 / 等级原始值解析环位列表。

        对尾部散文做截断清理，避免 parse_spell_level 因 $ 锚点失败。
        F3: 拆分复合职业（如 术士/法师 → 术士 + 法师）并按数字顺序归一化（术士 在 法师 前）。
        """
        level_str = raw.get("spell_level", "") or raw.get("环位", "") or raw.get("等级", "")
        if not level_str:
            return []
        # 截断尾部散文：取最后一个合法的 "职业名 N" 或纯数字之后的内容
        cleaned = _truncate_trailing_prose(level_str)
        items = SpellFormat.parse_spell_level(cleaned)
        # F3: 拆分复合职业 by '/'
        expanded = []
        for item in items:
            cls = item.get("class")
            if cls and "/" in cls:
                # 拆分并按中文笔画顺序归一化（短名在前，如 术士 < 法师）
                sub_names = sorted([c.strip() for c in cls.split("/") if c.strip()])
                for sub in sub_names:
                    expanded.append({"class": sub, "level": item["level"]})
            else:
                expanded.append(item)
        return expanded

    @staticmethod
    def _a_bucket_whitelist_level(item: dict, chunk: Chunk, legacy_id_map=None) -> list:
        """R2 A 桶白名单回填（KN228 模式护栏，修订 1 终值 556）。

        常量 SPELL_LEVEL_A_BUCKET_WHITELIST = 词表校验 + F3 拆分 + 标点剥离
        + CLASS_NAME_NORM 归一后的最终 items（生成时一次性加工，此处原样
        返回）——白名单外同形态条目结构性跳过（停下报告护栏）。
        裸数字（B 桶 91）/ 无残片（D 桶 764）/ MA 文档均不触发。
        """
        legacy_id = _legacy_spell_chunk_id(chunk.chunk_id, legacy_id_map)
        expected_title = _SPELL_LEVEL_A_BUCKET_TITLE_OVERRIDES.get(legacy_id)
        if expected_title and (item.get("name") or "").strip() != expected_title:
            return []
        return [dict(it) for it in SPELL_LEVEL_A_BUCKET_WHITELIST.get(legacy_id, [])]

    # MA 神话文档排除（修订 1 M1 红线：doc_id/文件名含神话或 MA 前缀；
    # page_625 = MA 神话扫描清单文档（book=MA），doc_id 无 MA 字样，按清单登记）
    _RE_MA_DOC = re.compile(r"神话|(?:^|[-_])MA(?:[-_－— ]|$)|^MA")
    _MA_DOCS = frozenset({"page_625"})

    @classmethod
    def _rescue_inline_level(cls, item: dict, chunk: Chunk, legacy_id_map=None) -> list:
        """M1 C 桶窄路补救通道（修订 1）：全局正则不动的空值补救。

        触发条件（入口处保证）：_extract_spell_level 与 _infer_level 均空。
        数据源 = formats split 入口快照 item["_pre_unify_text"]（
        _unify_school_bracket_titles 调用前的原文；键缺失则跳过，向后兼容）。
        单行正则抽标题行内黏连的等级段（两种形态：
        `【学派】…(EN)**等级：**…` 与 `【学派】…(EN) 等级：…`），走既有管线
        （截断散文 → parse_spell_level → F3 → 归一）。
        全部 class=None（裸数字）→ 丢弃维持空（B 桶拍板）；MA 文档排除。
        """
        if cls._RE_MA_DOC.search(chunk.doc_id or "") or (chunk.doc_id in cls._MA_DOCS):
            return []
        if _is_cut_exclusion(
            chunk.chunk_id, (item.get("name") or "").strip(), legacy_id_map
        ):
            return []  # KN245 保留裁除项：任何通道不回填
        # KN248 入口守卫：rescue 的定位是「标签在、值没解析出来」。条目自身没有
        # 等级标签（章节导语 / 表头碎片 / 空壳条目 / 毒品条目）不属于该形态——
        # 快照是「标题起 400 字符」窗口，会越过下一条目标题取到它的等级行，
        # 造成环级窃取（实测 29 条 / union 147 条假派生）。标签缺失一律拒填。
        # 判定用「** 开头 / 行首 / 】之后」三形态，覆盖全部合法写法（含 SMF010
        # 归一后的 `**等级：**`、紧凑标题 `【学派】名(EN) 等级：`）而不命中正文里
        # 的「施法者等级」「1轮/等级」「等级相等」；实测在有值的 3857 条上零误伤。
        if not re.search(r"(?:\*\*|^|】)\s*(?:等级|环位)", item.get("text") or "", re.M):
            return []
        pre = (item.get("_pre_unify_text") or "").strip()
        if not pre:
            return []
        name = (item.get("name") or "").strip()
        if not name:
            return []
        # 锚定守卫（QA-K1 返工，宁空勿错）：
        # ① KN244 污染标题（截成 I/II 等罗马数字碎片）——首现锚定会抓到文档中
        #   首个同名碎片（可能是无关条目的 等级行/形态后缀），直接拒填，等标题簇
        #   批次修复后回填（转 KN244/246 族登记）；
        # ② 锚位边界校验——名称在快照中须位于行首或【】之后（标题位）；
        #   仅完整罗马后缀标题额外允许句号/右括号边界，普通散文锚定仍拒填。
        # KN245 保留裁除项在最终 metadata 写入前统一生效，覆盖所有解析路径。
        if re.fullmatch(r"[IVX]{1,6}", name):
            return []
        roman_suffix = bool(re.search(r"\s[IVX]{1,6}$", name))
        idx = -1
        for m in re.finditer(re.escape(name), pre):
            pos0 = m.start()
            prev = pre[pos0 - 1] if pos0 > 0 else "\n"
            if prev in ("\n", "】") or (roman_suffix and prev in "。！？）)"):
                idx = pos0
                break
        if idx == -1:
            return []
        seg = pre[idx:idx + 400]
        # 值跨行形态：捕获至下一字段、正文起点或空行；禁止越过当前法术
        # 读到后续条目的等级行（上限 300 字符），散文截断由 _truncate_trailing_prose 负责。
        m = re.search(
            r"(?:\*\*等级\*\*[：:]|\*\*等级[：:]\*\*|(?<![一-鿿])等级[：:]|"
            r"(?<=系)等级[：:]|\*\*等级\*\*[ \t]*\r?\n[ \t]*)"
            r"[：:]?[ \t]*([\s\S]{1,300}?)(?=\*\*|\n[ \t]*\*\*|"
            r"(?:施法时间|施放时间|成分|范围|距离|目标|效果|持续时间|持续|豁免|法术抗力)[：:]|"
            r"该法术|这法术|此法术|\n[ \t]*[一-鿿]{1,8}[：:]|\n\n|\Z)",
            seg,
        )
        if not m:
            return []
        raw_val = m.group(1).strip().lstrip("：:，,、；;* ").rstrip("*,；;。").strip()
        if not raw_val:
            return []
        cleaned = _truncate_trailing_prose(raw_val)
        parsed = SpellFormat.parse_spell_level(cleaned)
        expanded = []
        for it in parsed:
            c = it.get("class")
            if c:
                # M2 词表校验规则：token 前导黏连标点剥离（；;：:，、）
                c = c.lstrip("；;:：，、* ").strip() or None
            if c and "/" in c:
                for sub in sorted(x.strip() for x in c.split("/") if x.strip()):
                    expanded.append({"class": sub, "level": it["level"]})
            elif c is None:
                expanded.append(it)
            else:
                expanded.append({"class": c, "level": it["level"]})
        if not any(it.get("class") for it in expanded):
            return []  # 裸数字 → 不回填（B 桶拍板不动）
        normalized = _normalize_spell_level_items(expanded)
        # M2 词表校验：任一 token 不在职业词表 → 整体丢弃（裁除项
        # 垃圾/表外脏名结构性拦截，不经条目名特判）
        if any(it["class"] not in _SPELL_LEVEL_RESCUE_LEGAL_CLASSES for it in normalized):
            return []
        seen = set()
        deduped = []
        for it in normalized:
            k = (it["class"], it["level"])
            if k not in seen:
                seen.add(k)
                deduped.append(it)
        return deduped

    @staticmethod
    def _extract_domains_from_level(raw: dict) -> list:
        """从 spell_level 原始值中剥离 领域/子域 条目。"""
        level_str = raw.get("spell_level", "") or raw.get("环位", "") or raw.get("等级", "")
        domains = []
        # KN014：子域/子领域 排他 — 只匹配纯 领域，排除 子域/子领域
        for m in re.finditer(r'([^\s,，、]+(?<!子)领域)\s*(\d+)', level_str):
            domains.append({"name": m.group(1), "level": int(m.group(2))})
        return domains

    @staticmethod
    def _extract_subdomains_from_level(raw: dict) -> list:
        """从 spell_level 原始值中剥离子领域条目（含等级）。"""
        level_str = raw.get("spell_level", "") or raw.get("环位", "") or raw.get("等级", "")
        subdomains = []
        for m in re.finditer(r'([^\s,，、]+子域)\s*(\d+)', level_str):
            subdomains.append({"name": m.group(1), "level": int(m.group(2))})
        return subdomains

    @staticmethod
    def _parse_components(value: str) -> dict:
        """解析成分字段为结构化 dict。

        PF 中文版主要使用中文成分名：
          "语言，姿势，材料 (一把沙子/法器)"
          → {"verbal": True, "somatic": True,
              "material": "一把沙子", "focus": None, "divine_focus": True}

        也兼容英文缩写变体（V/S/M/F/DF）。
        """
        result = {"verbal": False, "somatic": False, "material": None,
                   "focus": None, "divine_focus": False}
        if not value:
            return result

        # 1. 中文成分检测
        if re.search(r'(?:语言|言语|语文)', value):
            result["verbal"] = True
        if re.search(r'姿[势態]', value):
            result["somatic"] = True

        # 2. 材料/器材/法器 及括号内容
        m_paren = re.search(r'[（(]([^）)]+)[）)]', value)

        has_material = '材料' in value
        has_focus = '器材' in value
        has_divine = '法器' in value

        # 法器（Divine Focus）
        if has_divine:
            result["divine_focus"] = True
            if m_paren:
                result["material"] = m_paren.group(1)
        # 器材（Focus）
        if has_focus:
            if m_paren:
                result["focus"] = m_paren.group(1)
        # 材料（Material）— 注意可能与法器共存（材料/法器）
        if has_material:
            if m_paren and not has_divine:
                # 纯材料有括号
                result["material"] = m_paren.group(1)
            elif not m_paren and not has_divine:
                # 纯材料无括号 → 有材料无特殊说明
                result["material"] = "见原文"
            elif not m_paren and has_divine:
                # 材料/法器 无括号 → 材料可选
                result["material"] = "见原文"

        # 3. 英文缩写 fallback（V/S/M/F/DF）
        if not result["verbal"] and not result["somatic"] and not result["divine_focus"]:
            main = re.sub(r'[（(][^）)]+[）)]', '', value).strip()
            if 'V' in main:
                result["verbal"] = True
            if 'S' in main:
                result["somatic"] = True
            if 'M' in main or 'F' in main or 'DF' in main:
                if m_paren:
                    result["material"] = m_paren.group(1)
                if 'DF' in main:
                    result["divine_focus"] = True
                elif 'F' in main:
                    result["focus"] = m_paren.group(1) if m_paren else None
                    result["material"] = None

        return result

    @staticmethod
    def _extract_range(raw: dict) -> str:
        """提取射程值。优先 距离/射程 标签，次选 范围 标签。"""
        # 优先精确标签
        for key in ("range",):
            val = raw.get(key, "")
            if val:
                return val
        # "距离" 标签均映射到 range
        val = raw.get("range", "")
        if val:
            return val
        return raw.get("范围", "")

    @staticmethod
    def _extract_area(raw: dict) -> Optional[str]:
        """提取区域值。优先 '区域' 标签。"""
        val = raw.get("area", "")
        if val:
            return val
        # "区域" 标签直接返回
        return raw.get("区域") or None

    @staticmethod
    def _parse_saving_throw(value: str) -> dict:
        """解析豁免字段为结构化 dict。

        "强韧通过则无效" → {"type": "强韧", "effect": "通过则无效", "harmless": False}
        "意志通过则无效（无害）" → harmless=True
        "意志，通过则无效 **\\n(无害)" → 跨行无害识别，effect 清洗去 ** 和前导逗号

        F1 鲁棒性：若 raw value 后跟正文/下一字段（F2 COMP 边界未规范化场景），
        仅保留 <豁免类型>[，<效果>] + (无害)，丢弃后续垃圾。
        """
        result = {"type": "", "effect": "", "harmless": False}
        # KN018：显式否定与空值分流
        if not value:
            return result
        if value.strip() in ("无", "没有", "—", "否"):
            result["type"] = "无"  # 归一化，不保留原形
            return result
        # 检测 (无害) - 含跨行场景
        if "无害" in value:
            result["harmless"] = True
        # 去除 (无害) 标记
        clean = re.sub(r'[（(]无害[）)]', '', value).strip()
        # 尝试拆分 type 和 effect
        m = re.match(r'(强韧|反射|意志)(.*)', clean)
        if m:
            result["type"] = m.group(1)
            raw_effect = m.group(2)
        else:
            raw_effect = clean
        # 清洗 effect：去前导中文/英文标点和空白 + 去尾部 ** 和空白
        # 并丢弃包含 ** 或换行的尾部（说明吞了下一字段或正文）
        effect = re.sub(r'^[，,；;：:\s]+', '', raw_effect).strip()
        effect = effect.rstrip("*").strip()
        # 若清洗后 effect 含 ** 或换行（吞了正文/下一字段），截断到该边界之前
        if effect:
            cut = re.search(r'\*\*|\n', effect)
            if cut:
                effect = effect[:cut.start()].rstrip("*").strip()
        # F1：截断（见描述）/（见文本）/（见后文）后的正文粘连。
        # 这些标志本身表示"效果描述见正文"，若其后紧跟中文（非标点），
        # 说明正文与豁免值发生了同行粘连（如 PA 异能选集格式），在此截断。
        if effect:
            cut_marker = re.search(r'[（(]见(?:描述|文本|后文)[）)]', effect)
            if cut_marker:
                end = cut_marker.end()
                after = effect[end:]
                if after and re.match(r'[一-鿿]', after):
                    effect = effect[:end]
        if effect:
            result["effect"] = effect
        return result

    @staticmethod
    def _parse_spell_resistance(value: str) -> dict:
        """解析法术抗力字段为结构化 dict。

        "可" → {"applies": True, "harmless": False, "note": None}
        "不可" → {"applies": False, ...}
        "可（无害）" → applies=True, harmless=True, note=None
        "见下文" → applies=True, note="见下文"
        "**可（无害）\\n正文" → COMP 裸标签格式，前导 ** 与后续正文都被丢弃

        F1 鲁棒性：若 raw value 后面紧跟正文（F2 COMP 边界未规范化场景），
        仅保留 <SR 关键词> + (无害)，丢弃后续垃圾。
        """
        result = {"applies": False, "harmless": False, "note": None}
        if not value:
            return result
        # 识别无害标记 - 跨行场景
        if "无害" in value:
            result["harmless"] = True
        # 从值中剥离 (无害) / （无害）以便匹配关键词
        clean = re.sub(r'[（(]无害[）)]', '', value).strip()
        # 剥离前导 ** 与空白（COMP 等格式中关键词被 ** 包围，如 **可）
        clean = re.sub(r'^[\*\s]+', '', clean)
        # 匹配开头的 SR 关键词（即使后面跟着垃圾）
        keyword_pat = r'^(可|不可|是|否|无|有|见下文|见文本|见后文)'
        m = re.match(keyword_pat, clean)
        if m:
            keyword = m.group(1)
            if keyword in ('可', '是', '有'):
                result["applies"] = True
            elif keyword in ('不可', '否'):
                result["applies"] = False
                result["note"] = keyword  # KN018：truthy → parsed
            elif keyword == '无':
                # 在 SR 字段中"无"映射为 applies=False
                result["applies"] = False
                result["note"] = keyword  # KN018：truthy → parsed
            elif keyword in ('见下文', '见文本', '见后文'):
                result["applies"] = True
                result["note"] = keyword
            return result
        # 已知值直接分类（清洗后，整段匹配）
        if clean in ("不可", "否"):
            result["applies"] = False
            result["note"] = clean  # KN018：truthy → parsed
            return result
        if clean in ("可", "是", "有", "无"):
            # "无" 在 SR 字段：applies=False
            result["applies"] = (clean != "无")
            if clean == "无":
                result["note"] = clean  # KN018：truthy → parsed
            return result
        if clean in ("见下文", "见文本", "见后文"):
            result["applies"] = True
            result["note"] = clean
            return result
        # 清洗后为空（仅含无害等标记的情况）
        if not clean:
            result["applies"] = True
            return result
        # 未知值：applies 默认 True，保留原文到 note
        result["applies"] = True
        result["note"] = clean
        return result

    @staticmethod
    def _compute_field_status(metadata: dict) -> dict:
        """计算每个规范字段的解析状态。

        对于 dict 类型字段（components/saving_throw/spell_resistance），
        额外检查内部值是否有真理值，避免空默认 dict 被误判为 parsed。
        """
        not_applicable = {"subschool", "area", "effect"}
        status = {}
        for field in CANONICAL_FIELDS:
            if field == "field_status":
                continue
            val = metadata.get(field)
            if _is_semantically_empty(val):
                if field in not_applicable:
                    status[field] = "not_applicable"
                else:
                    status[field] = "missing"
            else:
                status[field] = "parsed"
        return status

    # ---- 配置加载 ----

    _descriptors_config: Optional[dict] = None
    _subschools_config: Optional[dict] = None

    @classmethod
    def _load_descriptors_config(cls) -> dict:
        if cls._descriptors_config is None:
            config_path = Path(__file__).parent.parent / "config" / "spell_descriptors.json"
            try:
                with open(config_path, encoding="utf-8") as f:
                    cls._descriptors_config = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                cls._descriptors_config = {"mapping": {}}
        return cls._descriptors_config

    @classmethod
    def _load_subschools_config(cls) -> dict:
        if cls._subschools_config is None:
            config_path = Path(__file__).parent.parent / "config" / "spell_subschools.json"
            try:
                with open(config_path, encoding="utf-8") as f:
                    cls._subschools_config = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                cls._subschools_config = {"subschools": {}}
        return cls._subschools_config

    # ---- 生命周期钩子覆写 ----

    def _collect_legacy_id_current_entries(self, input_dir: Path) -> list:
        class SplitDropLogFilter(logging.Filter):
            def filter(self, record):
                return "[split_drop]" not in record.getMessage()

        entries = []
        format_logger = logging.getLogger("vectorizer.formats.spell")
        log_filter = SplitDropLogFilter()
        format_logger.addFilter(log_filter)
        try:
            for file_path in sorted(input_dir.rglob("*.md")):
                if not _spell_file_condition(file_path):
                    continue
                text = file_path.read_text(encoding="utf-8")
                text = self.pre_normalize(file_path, text)
                text = self.format.normalize(text)
                text = self.format.promote(text)
                items = self.format.split_into_items(text, source_name=file_path.name)
                for index, item in enumerate(items):
                    entries.append({
                        "chunk_id": f"spell_{file_path.stem}_{index:04d}",
                        "doc_id": file_path.stem,
                        "title": item.get("name", ""),
                    })
        finally:
            format_logger.removeFilter(log_filter)
        if self.spell_index_provider:
            index_chunk = self._build_spell_index_chunk()
            if index_chunk:
                entries.append({
                    "chunk_id": index_chunk.chunk_id,
                    "doc_id": index_chunk.doc_id,
                    "title": index_chunk.title,
                })
        return entries

    def load_resources(self, input_dir: Path) -> None:
        """加载来源索引，并按当前 split 序列派生白名单 legacy-id 映射。"""
        index_path = input_dir / "Spell index.md"
        if index_path.exists():
            provider = SpellIndexProvider(index_path=index_path)
            provider.load()
            self.spell_index_provider = provider
            # 更新 SourceResolver 中已有的 SpellIndexProvider 引用
            for p in self.source_resolver.providers:
                if isinstance(p, SpellIndexProvider):
                    p._index = provider._index
                    p._loaded = provider._loaded
                    break
            logger.info("SpellIndexProvider 已加载: %d 条目", len(provider._index))
        else:
            logger.info("Spell index 未找到，跳过加载: %s", index_path)

        current_entries = self._collect_legacy_id_current_entries(input_dir)
        self._legacy_id_map = save_derived_legacy_id_map(current_entries)
        load_legacy_id_map.cache_clear()
        logger.info("KN249 legacy-id 映射已派生: %d 当前条目", len(self._legacy_id_map))

    def post_process(self, chunks: List[Chunk]) -> List[Chunk]:
        """追加法术索引 chunk"""
        if self.spell_index_provider:
            idx_chunk = self._build_spell_index_chunk()
            if idx_chunk:
                chunks.append(idx_chunk)
        return chunks

    def _build_spell_index_chunk(self) -> Optional[Chunk]:
        """构建法术索引 chunk（来源书对照表）"""
        entries = self.spell_index_provider.get_all_entries()
        if not entries:
            return None
        index_text = "\n".join(
            f"| {abbr} | {name} |"
            for name, abbr in sorted(entries.items(), key=lambda x: x[0])
        )
        return Chunk(
            chunk_id="spell_index_0000",
            doc_id="Spell index",
            category="spell",
            component_type="spell_index",
            title="法术索引表（来源书对照）",
            text=index_text,
            book_abbreviation="INDEX",
            book_name_cn="法术索引",
            book_name_en="Spell Index",
            source_confidence=100,
            aliases=[],
            metadata={"entry_count": len(entries)},
        )


def _spell_file_condition(file_path: Path) -> bool:
    """法术文件判断：在 法术/ 目录下且不是 index 文件"""
    fname = file_path.name.lower()
    if fname == "spell index.md":
        return False  # Index 单独处理
    parts = list(file_path.parts)
    return "法术" in parts or any("Spell" in p for p in parts)


# 模块加载时自动注册
register("spell", SpellProcessor, _spell_file_condition)
