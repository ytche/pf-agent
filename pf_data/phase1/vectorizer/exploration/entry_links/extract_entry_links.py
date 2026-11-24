#!/usr/bin/env python3
"""F-017 条目文本引用离线抽取器（只读，产出待人工核对明细）

覆盖八模块：种族 / 职业 / 专长 / 法术 / 装备 / 规则 / 技能 / 背景特性。

引用句式（本文件 _REF_RE 为准）：
  1. 「见 X」「详见 X」「参见 X」「另见 X」「亦见 X」
  2. 《》 / 【】 / 「」 / “” / ASCII 双引号 / ASCII 单引号 / 全半角括号
  3. 「锚点 + 效果|条目|本书 + 名称」，如「见效果‘X’」「见条目《X》」「见本书第 3 章」
  4. 「见第 N 章」「第 N 节」「第 N 页」
  5. 结构引用（上文 / 下表 / 附录）单列未决
  6. 锚点后正则完全不匹配的上下文记 ref_style=uncovered，不静默丢弃

匹配与判定：
  - 先做 title/alias 精确命中（NFKC + 去空白 + 首尾标点 + 拉丁 casefold）；
    命中即抽取，不被成语表抑制。
  - 未命中且裸「见」落在整词表（听见/意见/可见/见解/见效/见长/见地等）中才抑制，
    不用单字黑名单；summary 记录 suppressed_count 与样例。
  - 同名多候选保留全部并标 ambiguous；未命中标 unresolved；两者都不计入唯一边。
  - 每条记录有稳定 candidate_id（occurrence_id + 目标身份），用于重跑回填人工判定。
  - occurrence_id = SHA-256(source_chunk_id + "\\x1f" + 文本偏移 + "\\x1f" + 规范化引用文本)。
  - 唯一边键 = (source_chunk_id, target_module, target_chunk_id)，只统计 exact 出现。
  - 重跑读取已有 review JSONL，按 candidate_id 回填 verdict/reviewer/note/
    reviewed_at/chosen_target_chunk_id/correct_target_chunk_id；冲突非零退出并写 diff。
  - 同输入输出字节幂等；不修改任何 chunks 产物。

用法（Task 15 全库命令）：
  python3 vectorizer/exploration/entry_links/extract_entry_links.py \
    --chunks 'vectorizer/output/*/chunks.jsonl' \
    --out /tmp/pf-batch-a/f017

单模块/目录亦可；--output-dir 与 --out 等价。人工核对后重算汇总：
  python3 vectorizer/exploration/entry_links/extract_entry_links.py \
    --from-review /tmp/pf-batch-a/f017/entry_links_review.jsonl \
    --out /tmp/pf-batch-a/f017 \
    --markdown /tmp/pf-batch-a/f017/F017_汇总.md

输出：
  entry_links_review.jsonl       待核对明细（回填人工判定）
  entry_links_summary.json       出现次数 / 唯一边数 / 判定分布 / 形态样例 / 抑制统计
  entry_links_review_diff.json   仅重跑且有历史明细时输出：新增 / 消失 / 回填 / 冲突

人工判定值：正确 / 非引用误报 / 名称正确但目标错误 / 歧义未决
Markdown 汇总可由 --markdown 生成；统一任务也可直接使用 summary 字段渲染。
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

EXTRACTOR_VERSION = "f017-0.2.0"
REVIEW_FILENAME = "entry_links_review.jsonl"
SUMMARY_FILENAME = "entry_links_summary.json"
DIFF_FILENAME = "entry_links_review_diff.json"

REVIEW_VERDICTS = ("正确", "非引用误报", "名称正确但目标错误", "歧义未决")
PENDING_VERDICT = "未核对"

EXPECTED_MODULES = ("race", "class", "feat", "spell", "equipment", "rule", "skill", "trait")

MODULE_NAMES_CN = {
    "race": "种族",
    "class": "职业",
    "feat": "专长",
    "spell": "法术",
    "equipment": "装备",
    "rule": "规则",
    "skill": "技能",
    "trait": "背景特性",
}

CATEGORY_TO_MODULE = {
    "race": "race",
    "class": "class",
    "profession": "class",
    "职业": "class",
    "feat": "feat",
    "spell": "spell",
    "equipment": "equipment",
    "rule": "rule",
    "skill": "skill",
    "trait": "trait",
}

_COMPONENT_PREFIX_MODULE: Tuple[Tuple[str, str], ...] = (
    ("race_", "race"),
    ("class_", "class"),
    ("feat", "feat"),
    ("spell", "spell"),
    ("trait", "trait"),
    ("skill", "skill"),
    ("rule", "rule"),
)

# 显式目标白名单（P0 修正：race_overview 排除，race_intro 保留）。
# 不在白名单的 component_type 仍可作为引用来源被扫描，但不进入候选目录。
TARGET_COMPONENT_TYPES = {
    "race": frozenset({
        "race_intro",
        "race_trait",
        "alt_trait",
        "race_archetype",
        "race_feat",
        "race_item",
        "race_spell",
        "fcb_entry",
        "monster_block",
        "race_sidebar",
    }),
    "class": frozenset({
        "class_feature",
        "class_archetype",
        "class_overview",
        "class_recommendation",
    }),
    "feat": frozenset({"feat"}),
    "spell": frozenset({"spell"}),
    "equipment": frozenset({
        "gear",
        "wondrous_item",
        "weapon",
        "ring",
        "armor",
        "rod",
        "staff",
        "artifact",
        "cursed_item",
        "enchantment",
        "magic_plant",
        "equipment_package",
        "intelligent_item",
        "alchemical_item",
    }),
    "rule": frozenset({
        "rule_section",
        "rule_entry",
        "rule_table",
        "rule_reference",
    }),
    "skill": frozenset({
        "skill",
        "skill_task",
        "skill_rule",
        "skill_equipment",
        "skill_note",
        "ui_supplement",
    }),
    "trait": frozenset({"trait", "trait_flaw"}),
}

CATALOG_RISK_NOTES = {
    "race": "race_overview 与 race_intro 存在同族名条目；P0 决策排除 race_overview，保留 race_intro。",
    "class": "class_overview 含大量通用节标题（本职技能/职业特性/职业变体等），精确命中可能歧义或误报。",
    "equipment": "equipment_intro 已排除（103 条空 title）；equipment_package 个别 title 是整段物品清单。",
    "rule": "rule_section/rule_table 含通用标题（图片/注/表格名），精确命中需重点人工核对。",
    "feat": "feat_index/feat_intro 不作为目标，仅 feat 条目进入候选。",
    "spell": "spell_index 不作为目标。",
    "skill": "skill_index/skill_intro 不作为目标。",
    "trait": "trait_intro 不作为目标。",
}

# ---- 引用正则 ----

_ANCHOR = r"详见|参见|另见|亦见|见"
_ANCHOR_RE = re.compile(_ANCHOR)
_NUM = r"[0-9０-９一二三四五六七八九十百千零〇两]+"
_REF_RE = re.compile(
    rf"(?P<anchor>{_ANCHOR})\s*"
    rf"(?:(?P<label>效果|条目|本书)\s*[:：]?\s*)?(?:"
    r"《(?P<book>[^《》\n]{1,60})》"
    r"|【(?P<corner>[^【】\n]{1,60})】"
    r"|「(?P<corner_jp>[^「」\n]{1,60})」"
    r"|“(?P<curly>[^“”\n]{1,60})”"
    r"|‘(?P<curly_single>[^‘’\n]{1,60})’"
    r'|"(?P<ascii_double>[^"\n]{1,60})"'
    r"|'(?P<ascii_single>[^'\n]{1,60})'"
    r"|（(?P<paren_cn>[^（）\n]{1,60})）"
    r"|\((?P<paren_ascii>[^()\n]{1,60})\)"
    rf"|第\s*(?P<chapter>{_NUM})\s*[章节]"
    rf"|第\s*(?P<page>{_NUM})\s*页"
    r"|(?P<latin>[A-Za-z][A-Za-z0-9'’\-]*(?: [A-Za-z0-9'’\-]+){0,4})"
    r"|(?P<plain>[^\s，。；：、！？（）()《》「」“”\"'【】\[\]\n|]{1,30})"
    r")"
)

# 整词表：只抑制未精确命中目录的裸「见」。长词优先，避免「可见一斑」被「可见」抢先。
SUPPRESS_WORDS = tuple(sorted({
    "由此可见", "显而易见", "可见一斑", "见仁见智", "一见钟情", "见怪不怪",
    "见微知著", "见义勇为", "见风使舵", "见缝插针",
    "听见", "意见", "可见", "预见", "预防", "会见", "遇见", "寻见",
    "见证", "见识", "见解", "见效", "见长", "见地", "常见", "罕见",
    "所见", "只见", "但见", "却见", "又见", "所见即所得",
    "见到", "见过", "见闻", "见教", "见谅", "见笑", "见称", "见诸",
    "见方", "见机", "见外", "再见", "少见", "仅见", "足见", "深见",
    "浅见", "拙见", "高见", "远见", "卓见", "政见", "成见", "偏见",
    "主见", "创见", "洞见", "窥见", "梦见", "想见", "撞见", "碰见",
    "拜见", "觐见", "召见", "接见", "引见", "求见", "谒见", "瞧见",
    "看见", "望见", "眼见", "多見",
}, key=lambda word: (-len(word), word)))

_STRUCTURAL_EXACT = {"上", "下", "前", "后", "同上", "同上文"}
_STRUCTURAL_PREFIXES = (
    "上文", "下文", "前文", "后文", "上表", "下表", "上图", "下图",
    "本章", "本节", "上述", "前述", "附录", "边栏", "侧栏", "正文",
    "后述", "序章",
)

_RESTORE_FIELDS = (
    "verdict",
    "reviewer",
    "note",
    "reviewed_at",
    "chosen_target_chunk_id",
    "correct_target_chunk_id",
)


class InputValidationError(ValueError):
    """输入护栏失败（缺模块 / 未知 category / chunk_id 冲突）。"""


class ReviewConflictError(RuntimeError):
    """人工判定回填冲突；CLI 以非零码退出。"""

    def __init__(self, conflicts: List[dict], diff: dict):
        super().__init__(f"人工判定冲突 {len(conflicts)} 条")
        self.conflicts = conflicts
        self.diff = diff


def occurrence_id_for(chunk_id: str, offset: int, normalized_ref: str) -> str:
    payload = f"{chunk_id}\x1f{offset}\x1f{normalized_ref}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def candidate_id_for(occurrence_id: str, module: Optional[str],
                     chunk_id: Optional[str]) -> str:
    payload = f"{occurrence_id}\x1f{module or ''}\x1f{chunk_id or ''}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def normalize_reference(text: Optional[str]) -> str:
    if not text:
        return ""
    value = unicodedata.normalize("NFKC", str(text))
    value = re.sub(r"\s+", "", value)
    value = value.strip("，。；：、！？（）()【】[]「」“”\"'《》")
    return value.casefold()


def _module_of(chunk: dict) -> Optional[str]:
    category = str(chunk.get("category") or "").strip()
    if category in CATEGORY_TO_MODULE:
        return CATEGORY_TO_MODULE[category]
    component_type = str(chunk.get("component_type") or "").strip()
    for prefix, module in _COMPONENT_PREFIX_MODULE:
        if component_type.startswith(prefix):
            return module
    return None


def _expand_chunk_paths(raw_paths: Sequence[str]) -> List[str]:
    expanded: List[str] = []
    seen = set()
    for raw in raw_paths:
        matches = [raw]
        if any(char in raw for char in "*?["):
            matches = sorted(glob.glob(raw, recursive=True))
            if not matches:
                raise FileNotFoundError(f"glob 未匹配到 chunks: {raw}")
        for match in matches:
            if match not in seen:
                seen.add(match)
                expanded.append(match)
    return expanded


def _iter_chunk_files(paths: Sequence[str]) -> Iterable[Path]:
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            candidate = path / "chunks.jsonl"
            if not candidate.exists():
                raise FileNotFoundError(f"目录下未找到 chunks.jsonl: {path}")
            yield candidate
        elif path.exists():
            yield path
        else:
            raise FileNotFoundError(f"chunks 路径不存在: {path}")


def _load_chunks(paths: Sequence[str]) -> Tuple[List[dict], dict]:
    loaded: Dict[str, dict] = {}
    raw_rows = 0
    duplicates = 0
    for path in _iter_chunk_files(paths):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                raw_rows += 1
                chunk = json.loads(line)
                chunk_id = str(chunk.get("chunk_id") or "")
                if not chunk_id:
                    raise InputValidationError(f"chunk 缺少 chunk_id: {path}")
                if chunk_id in loaded:
                    if (loaded[chunk_id].get("text") or "") != (chunk.get("text") or ""):
                        raise InputValidationError(
                            f"chunk_id 冲突且 text 不同: {chunk_id} @ {path}"
                        )
                    duplicates += 1
                    continue
                loaded[chunk_id] = chunk
    stats = {
        "chunk_rows_read": raw_rows,
        "duplicate_chunk_rows": duplicates,
    }
    return list(loaded.values()), stats


def _build_catalog(chunks: Sequence[dict]) -> Tuple[Dict[str, List[dict]], dict]:
    catalog: Dict[str, List[dict]] = defaultdict(list)
    targets_by_component: Dict[str, Counter] = defaultdict(Counter)
    excluded_by_component: Dict[str, Counter] = defaultdict(Counter)
    for chunk in chunks:
        module = _module_of(chunk)
        if module is None:
            continue
        component_type = str(chunk.get("component_type") or "")
        if component_type not in TARGET_COMPONENT_TYPES.get(module, frozenset()):
            excluded_by_component[module][component_type] += 1
            continue
        title = str(chunk.get("title") or "").strip()
        if not title:
            continue
        targets_by_component[module][component_type] += 1
        entries = [(title, "title")]
        aliases = chunk.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        for alias in aliases:
            alias_text = str(alias or "").strip()
            if alias_text:
                entries.append((alias_text, "alias"))
        seen_norms = set()
        for text_value, matched_on in entries:
            norm = normalize_reference(text_value)
            if not norm or norm in seen_norms:
                continue
            seen_norms.add(norm)
            catalog[norm].append({
                "module": module,
                "chunk_id": str(chunk["chunk_id"]),
                "title": title,
                "component_type": component_type,
                "book_abbreviation": str(chunk.get("book_abbreviation") or ""),
                "matched_on": matched_on,
                "matched_text": text_value,
            })
    for candidates in catalog.values():
        candidates.sort(key=lambda item: (
            item["module"], item["chunk_id"], item["matched_on"]
        ))
    stats = {
        "catalog_targets_by_module": {
            module: sum(counter.values()) for module, counter in sorted(targets_by_component.items())
        },
        "catalog_targets_by_component_type": {
            module: dict(sorted(counter.items()))
            for module, counter in sorted(targets_by_component.items())
        },
        "excluded_targets_by_component_type": {
            module: dict(sorted(counter.items()))
            for module, counter in sorted(excluded_by_component.items())
        },
    }
    return dict(catalog), stats


def _ref_style(match: re.Match) -> Tuple[str, str, Optional[str]]:
    label = match.group("label")
    for group, style in (
        ("book", "book"),
        ("corner", "corner"),
        ("corner_jp", "corner"),
        ("curly", "quoted"),
        ("curly_single", "quoted"),
        ("ascii_double", "ascii_quoted"),
        ("ascii_single", "ascii_quoted"),
        ("paren_cn", "paren"),
        ("paren_ascii", "paren"),
    ):
        value = match.group(group)
        if value is not None:
            return value, style, label
    if match.group("chapter") is not None:
        return f"第{match.group('chapter')}章", "chapter", label
    if match.group("page") is not None:
        return f"第{match.group('page')}页", "page", label
    latin = match.group("latin")
    if latin is not None:
        return latin, "plain", label
    plain = match.group("plain") or ""
    if plain in _STRUCTURAL_EXACT or plain.startswith(_STRUCTURAL_PREFIXES):
        return plain, "structural", label
    return plain, "plain", label


def _suppressed_word(text: str, start: int) -> Optional[str]:
    base = max(0, start - 4)
    window = text[base:start + 12]
    for word in SUPPRESS_WORDS:
        search_from = 0
        while True:
            index = window.find(word, search_from)
            if index < 0:
                break
            word_start = base + index
            if word_start <= start < word_start + len(word):
                return word
            search_from = index + 1
    return None


def _uncovered_snippet(text: str, end: int) -> str:
    raw = text[end:end + 16].lstrip()
    raw = re.split(r"[，。；：、！？\n]", raw, maxsplit=1)[0]
    return raw[:12]


def _context(text: str, start: int, end: int) -> str:
    return text[max(0, start - 40):min(len(text), end + 60)].replace("\n", " ")


def _base_occurrence(chunk: dict, module: str, occurrence_id: str, anchor: str,
                     label: Optional[str], ref_text: str, ref_normalized: str,
                     ref_style: str, offset: int, end: int) -> dict:
    return {
        "occurrence_id": occurrence_id,
        "source_chunk_id": str(chunk["chunk_id"]),
        "source_module": module,
        "source_title": str(chunk.get("title") or ""),
        "source_component_type": str(chunk.get("component_type") or ""),
        "book_abbreviation": str(chunk.get("book_abbreviation") or ""),
        "ref_form": anchor,
        "ref_label": label,
        "ref_style": ref_style,
        "ref_text": ref_text,
        "ref_normalized": ref_normalized,
        "uncovered_form": ref_style == "uncovered",
        "text_offset": offset,
        "text_end": end,
        "match_status": None,
        "candidate_count": 0,
        "candidate_index": 0,
        "candidate": None,
        "target_module": None,
        "target_chunk_id": None,
        "target_title": None,
        "target_book_abbreviation": None,
        "target_component_type": None,
        "matched_on": None,
        "edge_key": None,
        "chosen_target_chunk_id": None,
        "correct_target_chunk_id": None,
        "context": _context(chunk.get("text") or "", offset, end),
        "verdict": None,
        "reviewer": None,
        "note": None,
        "reviewed_at": None,
    }


def _candidate_row(base: dict, candidate: dict, index: int, total: int,
                   status: str) -> dict:
    row = dict(base)
    row["candidate_id"] = candidate_id_for(
        base["occurrence_id"], candidate["module"], candidate["chunk_id"]
    )
    row["match_status"] = status
    row["candidate_count"] = total
    row["candidate_index"] = index
    row["candidate"] = candidate
    row["target_module"] = candidate["module"]
    row["target_chunk_id"] = candidate["chunk_id"]
    row["target_title"] = candidate["title"]
    row["target_book_abbreviation"] = candidate["book_abbreviation"]
    row["target_component_type"] = candidate["component_type"]
    row["matched_on"] = candidate["matched_on"]
    row["edge_key"] = (
        f"{base['source_chunk_id']}|{candidate['module']}|{candidate['chunk_id']}"
        if status == "exact" else None
    )
    return row


def _unresolved_row(base: dict) -> dict:
    row = dict(base)
    row["candidate_id"] = candidate_id_for(base["occurrence_id"], None, None)
    row["match_status"] = "unresolved"
    row["candidate_count"] = 0
    row["candidate_index"] = 0
    return row


def _extract_rows(chunks: Sequence[dict], catalog: Dict[str, List[dict]]) -> Tuple[List[dict], List[dict]]:
    rows: List[dict] = []
    suppressed: List[dict] = []
    for chunk in chunks:
        module = _module_of(chunk)
        if module is None:
            continue
        text = str(chunk.get("text") or "")
        chunk_id = str(chunk["chunk_id"])
        covered_anchor_starts = set()

        for match in _REF_RE.finditer(text):
            anchor = match.group("anchor")
            covered_anchor_starts.update(
                nested.start() for nested in _ANCHOR_RE.finditer(
                    text, match.start(), match.end()
                )
            )
            ref_text, ref_style, label = _ref_style(match)
            normalized = normalize_reference(ref_text)
            if not normalized:
                continue
            occurrence_id = occurrence_id_for(chunk_id, match.start(), normalized)
            base = _base_occurrence(
                chunk, module, occurrence_id, anchor, label,
                ref_text, normalized, ref_style, match.start(), match.end(),
            )
            candidates = catalog.get(normalized, [])
            if not candidates and anchor == "见":
                word = _suppressed_word(text, match.start())
                if word:
                    suppressed.append({
                        "source_chunk_id": chunk_id,
                        "text_offset": match.start(),
                        "suppressed_word": word,
                        "ref_text": ref_text,
                        "context": _context(text, match.start(), match.end()),
                    })
                    continue
            if not candidates:
                rows.append(_unresolved_row(base))
            elif len(candidates) == 1:
                rows.append(_candidate_row(base, candidates[0], 0, 1, "exact"))
            else:
                for index, candidate in enumerate(candidates):
                    rows.append(_candidate_row(
                        base, candidate, index, len(candidates), "ambiguous"
                    ))

        # 锚点存在但后续完全没有可识别引用形态：记 uncovered，不能静默消失。
        for anchor_match in _ANCHOR_RE.finditer(text):
            start = anchor_match.start()
            if start in covered_anchor_starts:
                continue
            anchor = anchor_match.group(0)
            snippet = _uncovered_snippet(text, anchor_match.end())
            if anchor == "见":
                word = _suppressed_word(text, start)
                if word:
                    suppressed.append({
                        "source_chunk_id": chunk_id,
                        "text_offset": start,
                        "suppressed_word": word,
                        "ref_text": snippet,
                        "context": _context(text, start, anchor_match.end()),
                    })
                    continue
            normalized = normalize_reference(snippet)
            occurrence_id = occurrence_id_for(chunk_id, start, normalized)
            base = _base_occurrence(
                chunk, module, occurrence_id, anchor, None,
                snippet, normalized, "uncovered", start, anchor_match.end(),
            )
            rows.append(_unresolved_row(base))

    rows.sort(key=lambda row: (
        row["source_chunk_id"],
        row["text_offset"],
        row["candidate_index"],
        row["target_module"] or "",
        row["target_chunk_id"] or "",
    ))
    suppressed.sort(key=lambda item: (
        item["source_chunk_id"], item["text_offset"], item["suppressed_word"]
    ))
    return rows, suppressed


# ---- 人工判定回填 ----

def _row_identity(row: dict) -> dict:
    return {
        "candidate_id": row.get("candidate_id"),
        "occurrence_id": row.get("occurrence_id"),
        "source_chunk_id": row.get("source_chunk_id"),
        "ref_text": row.get("ref_text"),
        "text_offset": row.get("text_offset"),
        "target_module": row.get("target_module"),
        "target_chunk_id": row.get("target_chunk_id"),
    }


def _load_review_rows(path: Path) -> List[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _merge_prior_review(rows: List[dict], prior_rows: Sequence[dict]) -> Tuple[dict, List[dict]]:
    conflicts: List[dict] = []
    prior_by_key: Dict[Tuple[str, str], dict] = {}
    legacy_rows = 0
    for prior in prior_rows:
        candidate_id = prior.get("candidate_id")
        if not candidate_id:
            legacy_rows += 1
            continue
        key = (str(prior.get("occurrence_id") or ""), str(candidate_id))
        verdict = prior.get("verdict")
        if verdict is not None and verdict not in REVIEW_VERDICTS:
            conflicts.append({
                "candidate_id": candidate_id,
                "reason": f"非法 verdict: {verdict!r}",
            })
            continue
        if key in prior_by_key:
            existing = prior_by_key[key]
            if {field: existing.get(field) for field in _RESTORE_FIELDS} != {
                field: prior.get(field) for field in _RESTORE_FIELDS
            }:
                conflicts.append({
                    "candidate_id": candidate_id,
                    "reason": "历史明细中同一 occurrence_id+candidate_id 存在冲突判定",
                })
            continue
        prior_by_key[key] = prior

    new_keys = {(row["occurrence_id"], row["candidate_id"]) for row in rows}
    old_keys = set(prior_by_key)
    added_keys = new_keys - old_keys
    missing_keys = old_keys - new_keys
    restored = 0

    for row in rows:
        prior = prior_by_key.get((row["occurrence_id"], row["candidate_id"]))
        if prior is None:
            continue
        prior_identity = _row_identity(prior)
        new_identity = _row_identity(row)
        mismatched = [
            key for key in prior_identity
            if key in prior and prior_identity[key] != new_identity[key]
        ]
        if mismatched:
            conflicts.append({
                "candidate_id": row["candidate_id"],
                "reason": f"candidate_id 身份字段变化: {mismatched}",
            })
            continue
        for field in _RESTORE_FIELDS:
            row[field] = prior.get(field)
        restored += 1

    rows_by_key = {(row["occurrence_id"], row["candidate_id"]): row for row in rows}

    def identity_of(key: Tuple[str, str]) -> dict:
        source = rows_by_key.get(key) or prior_by_key.get(key) or {}
        return _row_identity(source)

    diff = {
        "prior_rows": len(prior_rows),
        "new_rows": len(rows),
        "restored_rows": restored,
        "added_rows": [identity_of(key) for key in sorted(added_keys)],
        "missing_rows": [identity_of(key) for key in sorted(missing_keys)],
        "missing_verdict_rows": [
            _row_identity(row) for row in rows if row.get("verdict") is None
        ],
        "legacy_rows_ignored": legacy_rows,
        "conflicts": conflicts,
    }
    return diff, conflicts


# ---- 汇总 ----

def _build_summary(rows: Sequence[dict], meta: dict, suppressed: Sequence[dict]) -> dict:
    occurrences: Dict[str, dict] = {}
    for row in rows:
        occurrences.setdefault(row["occurrence_id"], row)

    status_by_occurrence = Counter()
    style_by_occurrence = Counter()
    module_by_occurrence = Counter()
    book_by_occurrence = Counter()
    for row in occurrences.values():
        status_by_occurrence[row["match_status"]] += 1
        style_by_occurrence[row["ref_style"]] += 1
        module_by_occurrence[row["source_module"]] += 1
        book_by_occurrence[row["book_abbreviation"]] += 1

    exact_rows = [row for row in rows if row["match_status"] == "exact"]
    edge_keys = sorted({row["edge_key"] for row in exact_rows if row["edge_key"]})
    edges_by_target_module = Counter()
    for edge_key in edge_keys:
        edges_by_target_module[edge_key.split("|")[1]] += 1

    affected_chunks = sorted({row["source_chunk_id"] for row in exact_rows})
    verdict_counts = Counter(row.get("verdict") or PENDING_VERDICT for row in rows)
    verdict_by_module: Dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        verdict_by_module[row["source_module"]][row.get("verdict") or PENDING_VERDICT] += 1

    form_samples: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        style = row["ref_style"]
        if len(form_samples[style]) >= 3:
            continue
        form_samples[style].append({
            "occurrence_id": row["occurrence_id"],
            "source_chunk_id": row["source_chunk_id"],
            "source_module": row["source_module"],
            "ref_style": style,
            "ref_text": row["ref_text"],
            "match_status": row["match_status"],
            "target_module": row["target_module"],
            "target_title": row["target_title"],
        })

    summary = {
        "extractor_version": EXTRACTOR_VERSION,
        "mode": meta.get("mode", "extract"),
        "input_files": meta.get("input_files", []),
        "chunks_loaded": meta.get("chunks_loaded", 0),
        "chunk_rows_read": meta.get("chunk_rows_read", 0),
        "duplicate_chunk_rows": meta.get("duplicate_chunk_rows", 0),
        "chunks_with_unknown_module": meta.get("chunks_with_unknown_module", 0),
        "missing_modules": meta.get("missing_modules", []),
        "unknown_category_chunks": meta.get("unknown_category_chunks", 0),
        "unknown_category_chunk_ids": meta.get("unknown_category_chunk_ids", []),
        "catalog_targets": meta.get("catalog_targets", 0),
        "catalog_keys": meta.get("catalog_keys", 0),
        "catalog_targets_by_module": meta.get("catalog_targets_by_module", {}),
        "catalog_targets_by_component_type": meta.get("catalog_targets_by_component_type", {}),
        "target_component_types": {
            module: sorted(types)
            for module, types in sorted(TARGET_COMPONENT_TYPES.items())
        },
        "excluded_targets_by_component_type": meta.get("excluded_targets_by_component_type", {}),
        "catalog_risk_notes": CATALOG_RISK_NOTES,
        "reference_occurrences": len(occurrences),
        "review_rows": len(rows),
        "exact_match_occurrences": status_by_occurrence.get("exact", 0),
        "ambiguous_occurrences": status_by_occurrence.get("ambiguous", 0),
        "unresolved_occurrences": status_by_occurrence.get("unresolved", 0),
        "uncovered_occurrences": sum(
            1 for row in occurrences.values() if row["ref_style"] == "uncovered"
        ),
        "ambiguous_candidate_rows": sum(
            1 for row in rows if row["match_status"] == "ambiguous"
        ),
        "unique_edges": len(edge_keys),
        "unique_edges_by_target_module": dict(sorted(edges_by_target_module.items())),
        "affected_source_chunks": len(affected_chunks),
        "affected_source_chunks_by_module": {
            module: len({
                row["source_chunk_id"] for row in exact_rows
                if row["source_module"] == module
            })
            for module in sorted({row["source_module"] for row in exact_rows})
        },
        "affected_source_chunk_ids_sample": affected_chunks[:20],
        "occurrences_by_source_module": dict(sorted(module_by_occurrence.items())),
        "occurrences_by_ref_style": dict(sorted(style_by_occurrence.items())),
        "occurrences_by_book": dict(sorted(book_by_occurrence.items())),
        "verdict_counts": dict(sorted(verdict_counts.items())),
        "verdict_counts_by_module": {
            module: dict(sorted(counter.items()))
            for module, counter in sorted(verdict_by_module.items())
        },
        "form_samples": {
            style: samples for style, samples in sorted(form_samples.items())
        },
        "suppressed_count": len(suppressed),
        "suppressed_samples": list(suppressed[:20]),
        "allowed_verdicts": list(REVIEW_VERDICTS),
        "pending_verdict_rows": sum(1 for row in rows if row.get("verdict") is None),
        "edge_key_fields": ["source_chunk_id", "target_module", "target_chunk_id"],
        "markdown_entry": "extract_entry_links.py --from-review <review.jsonl> --out <dir> --markdown <file>",
    }
    return summary


def write_markdown_report(summary: dict, path: Path) -> None:
    lines = [
        "# F-017 条目文本引用抽取汇总",
        "",
        f"- 模式：{summary.get('mode')}",
        f"- 抽取出现次数：{summary.get('reference_occurrences', 0)}",
        f"- 精确命中出现：{summary.get('exact_match_occurrences', 0)}",
        f"- 歧义出现：{summary.get('ambiguous_occurrences', 0)}",
        f"- 未决出现：{summary.get('unresolved_occurrences', 0)}（其中 uncovered "
        f"{summary.get('uncovered_occurrences', 0)}）",
        f"- 抑制的裸「见」：{summary.get('suppressed_count', 0)}",
        f"- 唯一边：{summary.get('unique_edges', 0)}",
        f"- 受影响来源 chunk：{summary.get('affected_source_chunks', 0)}",
        f"- 待核对行：{summary.get('pending_verdict_rows', 0)} / "
        f"{summary.get('review_rows', 0)}",
        "",
        "## 判定分布",
        "",
        "| 判定 | 行数 |",
        "| --- | --- |",
    ]
    for verdict, count in summary.get("verdict_counts", {}).items():
        lines.append(f"| {verdict} | {count} |")
    lines.extend([
        "",
        "## 来源模块分布",
        "",
        "| 模块 | 出现次数 |",
        "| --- | --- |",
    ])
    for module, count in summary.get("occurrences_by_source_module", {}).items():
        lines.append(f"| {module} | {count} |")
    lines.extend([
        "",
        "## 来源书分布",
        "",
        "| 书 | 出现次数 |",
        "| --- | --- |",
    ])
    for book, count in summary.get("occurrences_by_book", {}).items():
        lines.append(f"| {book or '?'} | {count} |")
    lines.extend([
        "",
        "## 形态样例",
        "",
    ])
    for style, samples in summary.get("form_samples", {}).items():
        if samples:
            sample = samples[0]
            lines.append(
                f"- {style}: `{sample.get('ref_text')}` → "
                f"{sample.get('match_status')} / {sample.get('target_title') or '无目标'}"
            )
    lines.extend([
        "",
        "## 白名单风险",
        "",
    ])
    for module, note in summary.get("catalog_risk_notes", {}).items():
        lines.append(f"- {module}: {note}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_summary(path: Path, summary: dict) -> None:
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _input_meta(chunk_paths: Sequence[str], chunks: Sequence[dict], load_stats: dict,
                strict: bool) -> Tuple[dict, List[dict], List[str]]:
    present_modules = {_module_of(chunk) for chunk in chunks}
    present_modules.discard(None)
    missing_modules = [module for module in EXPECTED_MODULES if module not in present_modules]

    unknown_categories = []
    for chunk in chunks:
        category = str(chunk.get("category") or "").strip()
        if category not in CATEGORY_TO_MODULE:
            unknown_categories.append({
                "chunk_id": str(chunk.get("chunk_id") or ""),
                "category": category,
            })

    if strict and missing_modules:
        raise InputValidationError(f"缺少模块 chunks: {', '.join(missing_modules)}")
    if strict and unknown_categories:
        sample = ", ".join(item["chunk_id"] for item in unknown_categories[:5])
        raise InputValidationError(f"未知 category 的 chunk {len(unknown_categories)} 条（示例: {sample}）")

    meta = {
        "mode": "extract",
        "input_files": [str(path) for path in _iter_chunk_files(chunk_paths)],
        "chunks_loaded": len(chunks),
        "chunk_rows_read": load_stats["chunk_rows_read"],
        "duplicate_chunk_rows": load_stats["duplicate_chunk_rows"],
        "chunks_with_unknown_module": sum(1 for chunk in chunks if _module_of(chunk) is None),
        "missing_modules": missing_modules,
        "unknown_category_chunks": len(unknown_categories),
        "unknown_category_chunk_ids": [item["chunk_id"] for item in unknown_categories[:20]],
    }
    return meta, unknown_categories, missing_modules


def extract_entry_links(chunk_paths: Sequence[str], output_dir: str,
                        strict: bool = False,
                        prior_review: Optional[str] = None) -> dict:
    """只读扫描 chunks，回填人工判定后写出待核对 JSONL、summary 与 diff。"""
    expanded_paths = _expand_chunk_paths(chunk_paths)
    chunks, load_stats = _load_chunks(expanded_paths)
    chunks.sort(key=lambda chunk: str(chunk["chunk_id"]))
    meta, _, missing_modules = _input_meta(expanded_paths, chunks, load_stats, strict)
    if missing_modules:
        print(f"WARN 缺少模块 chunks: {', '.join(missing_modules)}", file=sys.stderr)

    catalog, catalog_stats = _build_catalog(chunks)
    meta.update(catalog_stats)
    meta["catalog_targets"] = sum(
        sum(counter.values()) for counter in catalog_stats["catalog_targets_by_component_type"].values()
    )
    meta["catalog_keys"] = len(catalog)

    rows, suppressed = _extract_rows(chunks, catalog)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    review_path = out_dir / REVIEW_FILENAME
    prior_path = Path(prior_review) if prior_review else review_path
    diff = None
    conflicts: List[dict] = []
    if prior_path.exists():
        prior_rows = _load_review_rows(prior_path)
        diff, conflicts = _merge_prior_review(rows, prior_rows)
        (out_dir / DIFF_FILENAME).write_text(
            json.dumps(diff, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    if conflicts:
        raise ReviewConflictError(conflicts, diff or {})

    summary = _build_summary(rows, meta, suppressed)
    _write_jsonl(review_path, rows)
    _write_summary(out_dir / SUMMARY_FILENAME, summary)
    if diff is not None:
        print(
            f"回填人工判定 {diff['restored_rows']} 行；新增 {len(diff['added_rows'])}，"
            f"消失 {len(diff['missing_rows'])}。",
            file=sys.stderr,
        )
    return summary


def summarize_review(review_path: str, output_dir: str,
                     markdown_path: Optional[str] = None) -> dict:
    """从已有 review JSONL 重算 summary（不读取 chunks、不改写 review）。"""
    path = Path(review_path)
    if not path.exists():
        raise FileNotFoundError(f"review 文件不存在: {path}")
    rows = _load_review_rows(path)
    meta = {
        "mode": "from-review",
        "input_files": [str(path)],
        "markdown_entry": "extract_entry_links.py --from-review <review.jsonl> --out <dir> --markdown <file>",
    }
    summary = _build_summary(rows, meta, [])
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_summary(out_dir / SUMMARY_FILENAME, summary)
    if markdown_path:
        write_markdown_report(summary, Path(markdown_path))
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="F-017 条目引用离线抽取（只读）")
    parser.add_argument("--chunks", nargs="+",
                        help="chunks.jsonl 路径/glob/目录列表，如 'vectorizer/output/*/chunks.jsonl'")
    parser.add_argument("--output-dir", "--out", dest="output_dir", required=True,
                        help="待核对明细输出目录（--out 为等价别名）")
    parser.add_argument("--from-review", help="已有 review JSONL；仅重算 summary，不重新抽取")
    parser.add_argument("--markdown", help="可选 Markdown 汇总输出路径")
    parser.add_argument("--strict", action="store_true",
                        help="缺模块或存在未知 category 时失败")
    parser.add_argument("--prior-review", help="历史 review JSONL（默认取输出目录同名文件）")
    args = parser.parse_args(argv)

    try:
        if args.from_review:
            if args.chunks:
                parser.error("--from-review 与 --chunks 不能同时使用")
            summary = summarize_review(
                args.from_review, args.output_dir, args.markdown
            )
        else:
            if not args.chunks:
                parser.error("必须提供 --chunks 或 --from-review")
            summary = extract_entry_links(
                args.chunks, args.output_dir,
                strict=args.strict, prior_review=args.prior_review,
            )
            if args.markdown:
                write_markdown_report(summary, Path(args.markdown))
    except ReviewConflictError as error:
        print(
            f"F-017 人工判定冲突 {len(error.conflicts)} 条；"
            f"详见 {Path(args.output_dir) / DIFF_FILENAME}，本次不覆盖 review。",
            file=sys.stderr,
        )
        for conflict in error.conflicts[:10]:
            print(f"  - {conflict['candidate_id']}: {conflict['reason']}", file=sys.stderr)
        return 2
    except (FileNotFoundError, InputValidationError, json.JSONDecodeError) as error:
        print(f"F-017 输入错误: {error}", file=sys.stderr)
        return 2

    print(
        f"F-017 抽取完成：出现 {summary['reference_occurrences']} 次 / "
        f"精确 {summary['exact_match_occurrences']} / "
        f"歧义 {summary['ambiguous_occurrences']} / "
        f"未决 {summary['unresolved_occurrences']} / "
        f"uncovered {summary['uncovered_occurrences']} / "
        f"抑制 {summary['suppressed_count']} / "
        f"唯一边 {summary['unique_edges']}；明细 {summary['review_rows']} 行，"
        f"待核对 {summary['pending_verdict_rows']} 行。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
