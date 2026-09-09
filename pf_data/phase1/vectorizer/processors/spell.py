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
from vectorizer.postprocess.spell_chain import LinkMythicBaseSpells
from vectorizer.processors.base import Chunk, FileProcessor
from vectorizer.processors import register
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


def _truncate_trailing_prose(level_str: str) -> str:
    """截断环位字符串中的尾部散文。

    "术士/法师 8\\n\\n该法术的功能如同..." → "术士/法师 8"
    找到最后一个 "职业名 N" 模式的位置，截断其后内容。
    """
    if not level_str:
        return level_str

    # 找到最后一个 "词 数字" 的位置（数字不限在末尾）
    # 匹配模式：中文字符或字母 + 空格 + 数字
    m = re.search(r'([^\s,，]+)\s+(\d+)\s*$', level_str, re.MULTILINE)
    if not m:
        # fallback: 找纯数字在行尾
        m = re.search(r'(?:^|\s)(\d+)\s*$', level_str, re.MULTILINE)

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

    return result


class SpellProcessor(FileProcessor):
    """法术文件处理器"""

    # 阶段二（2026-09-01，k3 裁定 3 方案 A）：KN011 link 内建为 finalize 组件，
    # 对齐 feat 决策 A——pipeline 单命令产出含 link 的最终态。link 不删行，
    # index.json 与 chunks 行数天然一致（pipeline _write_index 先于 _finalize）。
    POSTPROCESSORS = [LinkMythicBaseSpells]

    @property
    def category(self) -> str:
        return "spell"

    def __init__(self, source_resolver: SourceResolver):
        super().__init__(source_resolver=source_resolver, format_handler=SpellFormat())
        self.spell_index_provider: Optional[SpellIndexProvider] = None

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

        # 环位：parse_fields 优先，fallback _infer_level
        spell_level = self._extract_spell_level(raw)
        if not spell_level:
            spell_level = self._infer_level(item)
        metadata["spell_level"] = spell_level

        # 领域/子域：从 spell_level 原始值剥离
        metadata["domains"] = self._extract_domains_from_level(raw)
        metadata["subdomains"] = self._extract_subdomains_from_level(raw)

        # 施法时间
        metadata["casting_time"] = _truncate_value_prose(
            raw.get("casting_time", "") or raw.get("施法时间", "") or raw.get("施放时间", ""),
            field="casting_time",
        )

        # 成分
        metadata["components"] = self._parse_components(raw.get("components", "") or raw.get("成分", "") or raw.get("法术成分", ""))

        # 射程
        metadata["range"] = _truncate_value_prose(self._extract_range(raw), field="range")

        # 目标/区域/效果
        metadata["target"] = _truncate_value_prose(
            raw.get("target", "") or raw.get("目标", ""),
            field="target",
        )
        metadata["area"] = self._extract_area(raw)
        metadata["effect"] = _truncate_value_prose(
            raw.get("effect", "") or raw.get("效果", ""),
            field="effect",
        )

        # 持续时间
        metadata["duration"] = _truncate_value_prose(
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

    def load_resources(self, input_dir: Path) -> None:
        """加载 Spell index 作为来源书判定资源"""
        index_path = input_dir / "Spell index.md"
        if not index_path.exists():
            logger.info("Spell index 未找到，跳过加载: %s", index_path)
            return
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
