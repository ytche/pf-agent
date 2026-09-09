#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTML 回退读取辅助模块。

当 `pf_rules_md/未整理/` 下的某个 Markdown 源文件格式混乱、无法可靠拆分时，
本模块允许整理脚本回退到对应的原始 HTML/CHM 源文件，先转换为 Markdown，
再做清洗后处理，最后才进行条目切分与聚合。

所有回退过的文件都会记录到 `未整理目录HTML回退处理记录.json/.md`，
方便后续排查问题。
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
MD_BASE = BASE / "pf_rules_md/未整理"
REGISTRY_JSON = BASE / "未整理目录HTML回退处理记录.json"
REGISTRY_MD = BASE / "未整理目录HTML回退处理记录.md"

HTML_BASES = [
    Path("/Users/chezi/.openclaw/workspace/pf_rules"),
    Path("/Users/chezi/.openclaw/workspace/pf_rules_chm"),
]

# 让本模块能导入 pf_data 下的 CHM->Markdown 转换器
_CONVERTER_DIR = BASE.parent
if str(_CONVERTER_DIR) not in sys.path:
    sys.path.insert(0, str(_CONVERTER_DIR))

from chm_to_md_converter_v2 import html_to_markdown, read_html_file  # noqa: E402

_SPELL_LABELS = [
    "学派", "环级", "施放时间", "成分", "范围", "目标", "效果",
    "持续时间", "豁免", "法术抗力",
]

_ITEM_LABELS = [
    "灵光", "施法者等级", "位置", "栏位", "价格", "重量", "类型",
    "出处", "来源", "制造要求", "制造需求", "制造花费", "制造DC", "效果",
]

_FEAT_LABELS = [
    "先决条件", "专长效果", "好处", "特殊", "正常", "战斗",
]

_GENERIC_LABELS = list(dict.fromkeys(_SPELL_LABELS + _ITEM_LABELS + _FEAT_LABELS))


def _label_pattern(kind: str) -> list[str]:
    if kind == "spell":
        return _SPELL_LABELS
    if kind == "item":
        return _ITEM_LABELS
    if kind == "feat":
        return _FEAT_LABELS
    return _GENERIC_LABELS


def find_html_for(src_md_path: Path) -> Optional[Path]:
    """根据 Markdown 源文件路径，查找对应的原始 HTML 文件。"""
    try:
        rel = src_md_path.relative_to(MD_BASE)
    except ValueError:
        rel = src_md_path
    stem = rel.stem
    for root in HTML_BASES:
        for ext in (".html", ".htm"):
            candidate = root / (stem + ext)
            if candidate.exists():
                return candidate
            candidate = root / rel.with_suffix(ext)
            if candidate.exists():
                return candidate
    return None


def convert_html_to_clean_md(html_path: Path, kind: str = "") -> str:
    """读取 HTML 并转换为清洗后的 Markdown。

    kind 可选："spell" / "item" / "feat" / ""（通用），
    用于决定强制换行的字段标签集合。
    """
    html = read_html_file(html_path)
    md = html_to_markdown(html, html_path.name)

    # 1. 兼容带 style 等属性的 <BR>
    md = re.sub(r"<br\b[^>]*>", "\n", md, flags=re.IGNORECASE)

    # 2. 合并 **加粗块** 内的换行，解决标题跨行问题
    def _collapse_bold(m: re.Match) -> str:
        inner = re.sub(r"\s+", " ", m.group(1)).strip()
        return f"**{inner}**"

    md = re.sub(r"\*\*(.*?)\*\*", _collapse_bold, md, flags=re.DOTALL)

    # 3. 在常见字段标签前强制换行（仅当标签后紧跟冒号/全角冒号时）
    labels = _label_pattern(kind)
    if labels:
        labels_re = "|".join(re.escape(label) for label in labels)
        md = re.sub(rf"(?<![\n|：:；;,.\s])(?=(?:{labels_re})[：:])", "\n", md)

    # 4. 规范化空行
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def load_registry() -> list[dict]:
    """加载 HTML 回退处理记录。"""
    if not REGISTRY_JSON.exists():
        return []
    return json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))


def save_registry(entries: list[dict]) -> None:
    """保存 JSON 记录，并同步生成 Markdown 表格。"""
    REGISTRY_JSON.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _render_markdown(entries)


def _render_markdown(entries: list[dict]) -> None:
    lines = [
        "# 未整理目录 HTML 回退处理记录",
        "",
        "> 本文件记录因 Markdown 源文件格式混乱而回退到原始 HTML 重新提取/清洗的处理。",
        "> 由 `未整理目录HTML回退处理记录.json` 自动生成，请勿直接手工编辑本表格。",
        "",
        "| 来源 Markdown | 对应 HTML | 问题记录 | 严重程度 | 处理方式 | 接入脚本 | 状态 | 处理时间 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for e in entries:
        lines.append(
            f"| `{e['source_md']}` | `{e['html_path']}` | {e.get('problem_entry', '')} | "
            f"{e.get('severity', '')} | {e.get('handler', '')} | {e.get('script', '')} | "
            f"{e.get('status', '待接入')} | {e.get('processed_at', '')} |"
        )
    lines.append("")
    lines.append("## 统计")
    lines.append("")
    total = len(entries)
    resolved_statuses = {"已接入", "脚本已修复", "无需接入"}
    resolved = sum(1 for e in entries if e.get("status") in resolved_statuses)
    pending = total - resolved
    lines.append(f"- 总记录数：{total}")
    lines.append(f"- 已解决（已接入/脚本修复/无需接入）：{resolved}")
    lines.append(f"- 待接入：{pending}")
    lines.append("")
    REGISTRY_MD.write_text("\n".join(lines), encoding="utf-8")


def read_source_text(src_md_path: Path, kind: str = "") -> str:
    """读取源文件文本；如果该文件已注册为 HTML 回退，则返回清洗后的 HTML 文本。"""
    src_md_path = src_md_path.resolve()
    try:
        rel = src_md_path.relative_to(MD_BASE)
    except ValueError:
        # 不在未整理目录下，直接读原文件
        return src_md_path.read_text(encoding="utf-8")

    rel_key = rel.as_posix()
    entries = load_registry()
    for entry in entries:
        if entry.get("source_md") == rel_key and entry.get("status") == "已接入":
            html_path = Path(entry["html_path"])
            if html_path.exists():
                return convert_html_to_clean_md(html_path, kind)
            # HTML 缺失时回退到原 Markdown，避免阻塞
            break

    return src_md_path.read_text(encoding="utf-8")


def mark_connected(
    src_md_path: Path,
    script_name: str,
    kind: str = "",
    handler: str = "html_to_markdown + clean_postprocess",
) -> None:
    """标记某个源文件已在指定脚本中接入 HTML 回退处理。"""
    src_md_path = src_md_path.resolve()
    try:
        rel_key = src_md_path.relative_to(MD_BASE).as_posix()
    except ValueError:
        rel_key = src_md_path.as_posix()

    entries = load_registry()
    updated = False
    now = datetime.now().isoformat(timespec="seconds")
    for entry in entries:
        if entry.get("source_md") == rel_key:
            entry["status"] = "已接入"
            entry["script"] = script_name
            entry["handler"] = handler
            entry["processed_at"] = now
            updated = True
            break

    if not updated:
        html_path = find_html_for(src_md_path)
        entries.append({
            "source_md": rel_key,
            "html_path": str(html_path) if html_path else "",
            "problem_entry": "",
            "categories": "",
            "severity": "",
            "handler": handler,
            "script": script_name,
            "status": "已接入",
            "processed_at": now,
        })

    save_registry(entries)


def init_registry_from_problem_record() -> None:
    """从 `未整理目录整理问题记录.md` 初始化待接入列表（仅开发/重建时使用）。"""
    from html_fallback_init import build_registry_entries  # avoid circular import
    entries = build_registry_entries()
    save_registry(entries)
