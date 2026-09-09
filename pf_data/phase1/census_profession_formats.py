#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
职业目录格式普查脚本（只读）

对 pf_rules_md_organized/职业/ 下全部 .md 文件计算结构指纹，
并按指纹签名聚类输出 JSON / Markdown 报告。
"""

import json
import re
from collections import defaultdict
from pathlib import Path

# 绝对路径，确保在任意工作目录都能运行
BASE_DIR = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
PROFESSION_DIR = BASE_DIR / "pf_rules_md_organized" / "职业"
CHUNKS_FILE = BASE_DIR / "vectorization_prep_profession" / "chunks.jsonl"

JSON_OUTPUT = BASE_DIR / "职业目录格式簇报告.json"
MD_OUTPUT = BASE_DIR / "职业目录格式簇报告.md"

# 变体标记的三种括号形式
VARIANT_MARK_RE = re.compile(r"[（\(【［].*变体.*[）\)】］]")

# 标题行
H1_RE = re.compile(r"^#\s+(.+)$")
H2_RE = re.compile(r"^##\s+(.+)$")
H3_RE = re.compile(r"^###\s+(.+)$")

# 独占一行的加粗
BOLD_TITLE_RE = re.compile(r"^\s*\*\*.+\*\*\s*$")

# 噪声行
URL_RE = re.compile(r"https?://")
TRANSLATOR_RE = re.compile(r"译者")
RETURN_TOC_RE = re.compile(r"返回目录")
IMAGE_RE = re.compile(r"^\s*!\[")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->")
SOURCE_MARKER_RE = re.compile(r"<!--\s*\S+-source:")
PIPE_RE = re.compile(r"\|")

# 代码块围栏（简单状态机）
CODE_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def collect_md_files(root: Path) -> list[Path]:
    """递归收集所有 .md 文件，按路径排序。"""
    return sorted(root.rglob("*.md"))


def parse_file(path: Path) -> dict:
    """读取单个 md 文件并返回原始指纹（不含 chunk 信息）。"""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    headings = {"h1": 0, "h2": 0, "h3": 0}
    variant_marked_h2 = 0
    variant_unmarked_h2 = 0
    bold_titles = 0
    noise_url_lines = 0
    noise_translator_lines = 0
    noise_return_toc_lines = 0
    noise_image_lines = 0
    noise_html_comment_lines = 0
    source_marker_lines = 0
    pipe_table_lines = 0

    in_code_block = False

    for raw_line in lines:
        line = raw_line.rstrip("\n")

        # 代码块状态切换
        if CODE_FENCE_RE.match(line):
            in_code_block = not in_code_block
            continue

        if HTML_COMMENT_RE.search(line):
            noise_html_comment_lines += 1
        if SOURCE_MARKER_RE.search(line):
            source_marker_lines += 1

        if not in_code_block:
            if PIPE_RE.search(line):
                pipe_table_lines += 1

        # 标题检测
        h1_match = H1_RE.match(line)
        h2_match = H2_RE.match(line)
        h3_match = H3_RE.match(line)

        if h1_match:
            headings["h1"] += 1
        elif h2_match:
            headings["h2"] += 1
            title_text = h2_match.group(1)
            if VARIANT_MARK_RE.search(title_text):
                variant_marked_h2 += 1
            else:
                variant_unmarked_h2 += 1
        elif h3_match:
            headings["h3"] += 1

        # 独占一行的加粗
        if BOLD_TITLE_RE.match(line):
            bold_titles += 1

        # 噪声行
        if URL_RE.search(line):
            noise_url_lines += 1
        if TRANSLATOR_RE.search(line):
            noise_translator_lines += 1
        if RETURN_TOC_RE.search(line):
            noise_return_toc_lines += 1
        if IMAGE_RE.match(line):
            noise_image_lines += 1

    return {
        "headings": headings,
        "variant_marked_h2": variant_marked_h2,
        "variant_unmarked_h2": variant_unmarked_h2,
        "bold_titles": bold_titles,
        "noise_url_lines": noise_url_lines,
        "noise_translator_lines": noise_translator_lines,
        "noise_return_toc_lines": noise_return_toc_lines,
        "noise_image_lines": noise_image_lines,
        "noise_html_comment_lines": noise_html_comment_lines,
        "source_marker_lines": source_marker_lines,
        "pipe_table_lines": pipe_table_lines,
    }


def load_chunk_stats(chunks_file: Path) -> dict[str, dict]:
    """从 chunks.jsonl 汇总每个 doc_id 的 chunk 统计。"""
    stats = defaultdict(lambda: {
        "chunks_produced": 0,
        "archetype_chunks": 0,
        "unknown_class_chunks": 0,
    })

    with chunks_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue

            doc_id = chunk.get("doc_id")
            if not doc_id:
                continue

            s = stats[doc_id]
            s["chunks_produced"] += 1
            if chunk.get("component_type") == "class_archetype":
                s["archetype_chunks"] += 1
            if chunk.get("class_name") == "未知职业":
                s["unknown_class_chunks"] += 1

    return dict(stats)


def bucket(value: int, thresholds: list[int], labels: list[str]) -> str:
    """按阈值分桶，返回标签。"""
    for thr, label in zip(thresholds, labels):
        if value <= thr:
            return label
    return labels[-1]


def make_signature(fp: dict) -> str:
    """
    生成聚类签名。
    使用计数分桶，避免每个文件独占一簇；同时保留关键差异。
    """
    h1 = fp["headings"]["h1"]
    h2 = fp["headings"]["h2"]
    h3 = fp["headings"]["h3"]

    h1_b = bucket(h1, [0, 1], ["无H1", "单H1", "多H1"])
    h2_b = bucket(h2, [0, 1, 5, 20], ["无H2", "单H2", "少量H2", "中量H2", "大量H2"])
    h3_b = bucket(h3, [0, 1, 10], ["无H3", "少量H3", "中量H3", "大量H3"])
    vm_b = bucket(fp["variant_marked_h2"], [0, 1, 5], ["无标记H2", "少量标记H2", "中量标记H2", "大量标记H2"])
    vu_b = bucket(fp["variant_unmarked_h2"], [0, 1, 5], ["无未标记H2", "少量未标记H2", "中量未标记H2", "大量未标记H2"])
    bt_b = bucket(fp["bold_titles"], [0, 1, 5], ["无加粗标题", "少量加粗标题", "中量加粗标题", "大量加粗标题"])

    noise = (
        fp["noise_url_lines"]
        + fp["noise_translator_lines"]
        + fp["noise_return_toc_lines"]
        + fp["noise_image_lines"]
        + fp["noise_html_comment_lines"]
    )
    noise_b = bucket(noise, [0, 1, 10], ["无噪声", "少量噪声", "中量噪声", "大量噪声"])

    pipe_b = bucket(fp["pipe_table_lines"], [0, 1, 10], ["无表格", "少量表格", "中量表格", "大量表格"])
    arche = fp.get("archetype_chunks", 0)
    arche_b = bucket(arche, [0, 1, 5, 20], ["无变体chunk", "单变体chunk", "少量变体chunk", "中量变体chunk", "大量变体chunk"])
    src_b = bucket(fp.get("source_marker_lines", 0), [0, 1, 5], ["无源标记", "少量源标记", "中量源标记", "大量源标记"])

    return f"{h1_b}|{h2_b}|{h3_b}|{vm_b}|{vu_b}|{bt_b}|{noise_b}|{pipe_b}|{arche_b}|{src_b}"


def detect_issues(fp: dict, rel_path: str) -> list[str]:
    """根据指纹与路径检测疑似问题。"""
    issues = []

    # 1. 加粗标题多但 ## 带标记变体标题少 → 疑似缺 ## 前缀
    if fp["bold_titles"] > 0 and fp["variant_marked_h2"] <= 1:
        issues.append("疑似缺 `##` 前缀的变体标题")

    # 2. 含纯噪声行（含 HTML 注释、行首图片，均按 spec 属于噪声行）
    noise_total = (
        fp["noise_url_lines"]
        + fp["noise_translator_lines"]
        + fp["noise_return_toc_lines"]
        + fp["noise_image_lines"]
        + fp["noise_html_comment_lines"]
    )
    if noise_total > 0:
        issues.append("含纯噪声行（URL / 译者 / 返回目录 / 图片 / HTML 注释）")

    # 3. 明显是变体聚合文件但未识别到变体
    lower_rel = rel_path.lower()
    is_archetype_file = any(k in lower_rel for k in ("变体", "archetype", "职业选项"))
    if is_archetype_file and fp.get("archetype_chunks", 0) == 0:
        issues.append("未识别到变体，疑似格式不规范")

    # 4. 含未知职业 chunk
    if fp.get("unknown_class_chunks", 0) > 0:
        issues.append("含未知职业 chunk")

    # 5. 有未标记变体 H2 但无标记变体 H2
    if fp["variant_unmarked_h2"] > 0 and fp["variant_marked_h2"] == 0:
        issues.append("疑似缺变体标记")

    return issues


def build_report(files: list[Path], chunk_stats: dict[str, dict]) -> dict:
    """构建 per-file 完整指纹。"""
    report = {}

    for path in files:
        rel_path = path.relative_to(PROFESSION_DIR).as_posix()
        fp = parse_file(path)
        stats = chunk_stats.get(rel_path, {
            "chunks_produced": 0,
            "archetype_chunks": 0,
            "unknown_class_chunks": 0,
        })

        fp.update(stats)
        fp["signature"] = make_signature(fp)
        fp["issues"] = detect_issues(fp, rel_path)

        report[rel_path] = fp

    return report


def cluster_by_signature(report: dict) -> dict[str, list[str]]:
    """按 signature 聚类。"""
    clusters = defaultdict(list)
    for rel_path, fp in report.items():
        clusters[fp["signature"]].append(rel_path)
    return dict(clusters)


def format_summary(fp: dict) -> str:
    """生成单个簇的特征摘要表格。"""
    h = fp["headings"]
    return (
        f"| 维度 | 值 |\n"
        f"|---|---|\n"
        f"| H1 / H2 / H3 | {h['h1']} / {h['h2']} / {h['h3']} |\n"
        f"| 标记变体 H2 | {fp['variant_marked_h2']} |\n"
        f"| 未标记变体 H2 | {fp['variant_unmarked_h2']} |\n"
        f"| 独占行加粗标题 | {fp['bold_titles']} |\n"
        f"| URL / 译者 / 返回目录 | {fp['noise_url_lines']} / {fp['noise_translator_lines']} / {fp['noise_return_toc_lines']} |\n"
        f"| 图片 / HTML注释 / 源标记 | {fp['noise_image_lines']} / {fp['noise_html_comment_lines']} / {fp.get('source_marker_lines', 0)} |\n"
        f"| 管道表格行 | {fp['pipe_table_lines']} |\n"
        f"| chunks / 变体 / 未知职业 | {fp['chunks_produced']} / {fp['archetype_chunks']} / {fp['unknown_class_chunks']} |\n"
    )


def write_json(report: dict, output: Path) -> None:
    with output.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def write_markdown(report: dict, output: Path) -> None:
    clusters = cluster_by_signature(report)

    total_files = len(report)
    total_clusters = len(clusters)
    covered_files = sum(len(v) for v in clusters.values())

    # 计算每个簇的聚合指标
    cluster_summaries = []
    for sig, files in clusters.items():
        total_chunks = sum(report[f]["chunks_produced"] for f in files)
        total_archetype = sum(report[f]["archetype_chunks"] for f in files)
        total_unknown = sum(report[f]["unknown_class_chunks"] for f in files)
        total_issues = sum(len(report[f]["issues"]) for f in files)
        # 噪声密度 = 含噪声文件占比
        noisy_files = sum(1 for f in files if any("噪声" in i for i in report[f]["issues"]))
        # 问题文件（至少一个 issue）
        problem_files = sum(1 for f in files if report[f]["issues"])

        # 代表性指纹（取簇内首个）
        rep_fp = report[files[0]]
        cluster_summaries.append({
            "signature": sig,
            "files": files,
            "file_count": len(files),
            "total_chunks": total_chunks,
            "total_archetype": total_archetype,
            "total_unknown": total_unknown,
            "total_issues": total_issues,
            "noisy_files": noisy_files,
            "problem_files": problem_files,
            "rep_fp": rep_fp,
        })

    # 按簇内 chunk 影响面排序（影响面大在前），用于优先级建议
    by_impact = sorted(cluster_summaries, key=lambda x: x["total_chunks"], reverse=True)

    lines = []
    lines.append("# 职业目录格式簇报告\n")
    lines.append(f"- 文件总数：**{total_files}**\n")
    lines.append(f"- 簇数：**{total_clusters}**\n")
    lines.append(f"- 覆盖文件数：**{covered_files}**\n")
    lines.append(f"- 源目录：`{PROFESSION_DIR}`\n")
    lines.append(f"- chunks 来源：`{CHUNKS_FILE}`\n")
    lines.append("\n")

    lines.append("## 总体观察\n")
    problem_clusters = [c for c in cluster_summaries if c["problem_files"] > 0]
    lines.append(f"- 问题簇（至少含一个 issue）数量：**{len(problem_clusters)}**\n")
    lines.append(f"- 问题文件总数：**{sum(c['problem_files'] for c in problem_clusters)}**\n")
    lines.append("- 本报告在 spec 要求维度外，额外统计了 `source_marker_lines`（形如 `<!-- XXX-source:... -->` 的源标记 HTML 注释），用于识别聚合文件的拼接痕迹。\n")
    lines.append("\n")

    for idx, c in enumerate(cluster_summaries, start=1):
        lines.append(f"### 簇 {idx}：{c['signature']}\n")
        lines.append(format_summary(c["rep_fp"]))
        lines.append(f"- 文件数：{c['file_count']}\n")
        lines.append(f"- chunks 影响面：{c['total_chunks']}（变体 chunk {c['total_archetype']}，未知职业 chunk {c['total_unknown']}）\n")
        lines.append(f"- 问题文件数：{c['problem_files']} / {c['file_count']}\n")

        # 疑似问题聚合
        issue_counter = defaultdict(int)
        for f in c["files"]:
            for issue in report[f]["issues"]:
                issue_counter[issue] += 1
        if issue_counter:
            lines.append("- 疑似问题：\n")
            for issue, cnt in sorted(issue_counter.items(), key=lambda x: -x[1]):
                lines.append(f"  - {issue}：{cnt} 个文件\n")
        else:
            lines.append("- 疑似问题：无\n")

        # 文件清单：太长时折叠
        files_sorted = sorted(c["files"])
        if len(files_sorted) <= 10:
            lines.append("- 文件清单：\n")
            for f in files_sorted:
                lines.append(f"  - `{f}`\n")
        else:
            lines.append(f"- 文件清单（共 {len(files_sorted)} 个，节选前 10）：\n")
            for f in files_sorted[:10]:
                lines.append(f"  - `{f}`\n")
            lines.append("  - ...\n")

        lines.append("\n")

    lines.append("## 修复优先级建议\n")
    lines.append("按“簇内所有文件的 chunk 影响面总和”从高到低排序，优先处理影响面大且问题文件占比高的簇。\n\n")
    lines.append("| 优先级 | 簇签名 | 文件数 | chunks 影响面 | 问题文件数 | 主要问题 |\n")
    lines.append("|---|---|---|---|---|---|\n")
    rank = 1
    for c in by_impact:
        if c["problem_files"] == 0:
            continue
        issue_counter = defaultdict(int)
        for f in c["files"]:
            for issue in report[f]["issues"]:
                issue_counter[issue] += 1
        main_issue = max(issue_counter, key=issue_counter.get) if issue_counter else "-"
        lines.append(
            f"| {rank} | `{c['signature']}` | {c['file_count']} | {c['total_chunks']} | "
            f"{c['problem_files']} | {main_issue} |\n"
        )
        rank += 1

    lines.append("\n")
    lines.append("---\n")
    lines.append("*报告由 `census_profession_formats.py` 自动生成，未修改任何源文件。*\n")

    output.write_text("".join(lines), encoding="utf-8")


def main() -> None:
    if not PROFESSION_DIR.exists():
        raise FileNotFoundError(f"源目录不存在：{PROFESSION_DIR}")
    if not CHUNKS_FILE.exists():
        raise FileNotFoundError(f"chunks 文件不存在：{CHUNKS_FILE}")

    files = collect_md_files(PROFESSION_DIR)
    chunk_stats = load_chunk_stats(CHUNKS_FILE)
    report = build_report(files, chunk_stats)

    write_json(report, JSON_OUTPUT)
    write_markdown(report, MD_OUTPUT)

    print(f"已覆盖 {len(files)} 个 md 文件，生成 {len(cluster_by_signature(report))} 个簇。")
    print(f"JSON：{JSON_OUTPUT}")
    print(f"Markdown：{MD_OUTPUT}")


if __name__ == "__main__":
    main()
