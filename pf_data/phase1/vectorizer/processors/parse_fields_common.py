"""parse_fields_common.py — 字段解析公共层（标签集参数化，2026-08-04）

背景：字段值提取算法（**标签：** / **标签**： 双格式 + 边界标签集 + \n\n 硬边界）
已在 spell.parse_fields 与 feat.parse_fields 各实现一份（KN013 M5 扩展），
二者冻结不重构；race 是第三处同类需求——按「禁 copy 模板扩展」规则抽公共函数，
标签集由调用方传入，避免第三份 copy。

算法契约（与 spell/feat 对齐，勿漂移）：
  1. 边界标签集 = all_labels + extra_labels；extra 只作值边界不作 capture（KN013 M5）
  2. 值边界 = 空白行（\n\n 硬边界，数据中字段值从不跨空白行）/ 下一字段标签
     （**标签：** 与 **标签**： 两种星形位置）/ 文本末尾
  3. 值清洗：尾部格式残留（*、中文/英文标点）剥除、全角空格 → 半角
"""

import re
from typing import Dict, List, Sequence


def parse_fields(
    text: str,
    *,
    all_labels: Sequence[str],
    extra_labels: Sequence[str],
    label_to_key: Dict[str, str],
) -> Dict[str, str]:
    """从统一 IR 文本提取字段原始值（**标签：** 值 格式）。

    - all_labels：规范字段标签集（capture，须在 label_to_key 有映射）
    - extra_labels：边界标签集（只作值边界不作 capture）
    - label_to_key：标签 → 规范 key 映射
    返回 {canonical_key: raw_value_str}；缺失字段值为空字符串。
    """
    result: Dict[str, str] = {}
    if not text:
        return result

    boundary_labels = list(all_labels) + list(extra_labels)
    labels_pattern = "|".join(re.escape(label) for label in boundary_labels)
    capture_labels_pattern = "|".join(re.escape(label) for label in all_labels)
    # 字段值边界：下一个字段标签（标准或变体）、空白行（\n\n）、或文本末尾。
    # \n\n 作硬边界是安全的：数据中字段值从不跨空白行（spell 侧已实测确认）。
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

    for match_re in (field_re, field_re_v2):
        for m in match_re.finditer(text):
            label = m.group(1)
            value = m.group(2).strip()
            # 去掉值末尾可能的 ** 残留与段尾标点（裸标签残留/格式符，"无；"→"无"）
            value = value.rstrip("*,；;。，、").strip()
            # 全角空格 → 半角
            value = value.replace("　", " ")
            key = label_to_key.get(label)
            if key and key not in result:
                result[key] = value

    return result
