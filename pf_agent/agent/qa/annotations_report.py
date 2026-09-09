#!/usr/bin/env python3
"""错误标注分析报告：读取 annotations.jsonl，按 errorType 聚类并输出优化建议。

错误标注闭环的分析端：前端「标错」→ /api/chat/feedback → annotations.jsonl → 本脚本
聚类统计 + 典型错误示例 + 优化建议（指向 prompt/检索/数据三处优化点），
把用户标注变成可执行的优化输入，驱动 Agent 准确率提升。

用法：
    python3 annotations_report.py                                # 默认读 ~/.pf_agent/annotations.jsonl
    python3 annotations_report.py --file /path/to/annotations.jsonl
    python3 annotations_report.py --out ./out                    # 输出目录（默认当前目录）
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# 错误类型 → 优化建议（指向优化点：prompt / 检索 / 数据）
TYPE_ADVICE = {
    "事实错误": "优先检查被引用 chunk 内容是否支撑该回答：chunk 本身对 → prompt 需更严格约束"
               "「只依据检索来源、数值照抄不推算」；chunk 错/过时 → 数据侧修复。",
    "检索漏召回": "检索策略问题：检查该主题召回结果（降权项/枚举过滤/topK 截断，见 F-001/F-002）。"
                "考虑补充别名/同义词、扩大枚举召回或预整理列表（F-007）。",
    "编造来源": "prompt 约束问题：回答内容未落在 sources 内。需强化「仅基于检索结果作答、无依据不编造」，"
               "并按来源编号回校（F-014，论文式上标标注）。",
    "答非所问": "意图/问题理解问题：检查意图路由与问题重写，确认多轮上下文是否串扰（F-003 相关）。",
    "结构差": "输出格式问题：补充结构化输出约束（分点/表格/来源编号）。",
    "其他": "人工复核，判断归属。",
}

DEFAULT_FILE = Path.home() / ".pf_agent" / "annotations.jsonl"


def load_annotations(path: Path) -> list[dict]:
    """读取 JSONL，容错跳过坏行/空行。"""
    items = []
    if not path.exists():
        print(f"[错误] 标注文件不存在: {path}", file=sys.stderr)
        return items
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"[警告] 跳过坏行: {line[:80]}", file=sys.stderr)
    return items


def truncate(s, n=120):
    """单行截断（换行压成空格），用于表格展示。"""
    s = (s or "").replace("\n", " ").strip()
    return s[:n] + ("…" if len(s) > n else "")


def source_counter(items: list[dict]) -> Counter:
    """统计被标错回答引用的来源 tocPath 出现次数（找出「问题 chunk」）。"""
    c = Counter()
    for it in items:
        for s in it.get("sources") or []:
            key = s.get("tocPath") or s.get("book") or "（无来源）"
            c[key] += 1
    return c


def render_distribution(items: list[dict]) -> list[str]:
    lines = ["## 一、类型分布", "",
             "| 错误类型 | 数量 | 占比 | 优化指向 |", "|---|---|---|---|"]
    n = len(items)
    by_type = Counter(it.get("errorType") or "其他" for it in items)
    for t, cnt in by_type.most_common():
        advice = TYPE_ADVICE.get(t, TYPE_ADVICE["其他"])
        lines.append(f"| {t} | {cnt} | {cnt / n * 100:.0f}% | {advice[:40]}… |")
    return lines


def render_detail(items: list[dict]) -> list[str]:
    lines = ["## 二、明细（按类型）", ""]
    by_type = defaultdict(list)
    for it in items:
        by_type[it.get("errorType") or "其他"].append(it)
    for t, its in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"### {t}（{len(its)} 条）")
        lines += ["", "| id | 时间 | 问题 | 回答（截断） | 来源数 | 修正/备注 |",
                  "|---|---|---|---|---|---|"]
        for it in its:
            n_src = len(it.get("sources") or [])
            fix = truncate(it.get("correction") or it.get("comment") or "—", 60)
            lines.append(f"| {it.get('id','')} | {it.get('timestamp','')} | "
                         f"{truncate(it.get('question'),60)} | {truncate(it.get('answer'),60)} | "
                         f"{n_src} | {fix} |")
        lines.append("")
    return lines


def render_hot_sources(sources: Counter, items: list[dict]) -> list[str]:
    lines = ["## 三、被标错来源 Top（问题 chunk）", "",
             "> 同一 tocPath 多次被标错，说明该 chunk 数据质量或检索命中后的利用有问题。",
             "", "| 来源（tocPath / book） | 被标次数 |", "|---|---|"]
    for src, cnt in sources.most_common(15):
        lines.append(f"| `{truncate(src,70)}` | {cnt} |")
    return lines


def render_advice(items: list[dict], sources: Counter) -> list[str]:
    lines = ["## 四、优化建议", ""]
    by_type = Counter(it.get("errorType") or "其他" for it in items)
    for t, cnt in by_type.most_common():
        if cnt == 0:
            continue
        lines.append(f"- **{t}（{cnt}）**：{TYPE_ADVICE.get(t, TYPE_ADVICE['其他'])}")
    hot = [s for s, c in sources.items() if c >= 2]
    if hot:
        lines += ["", f"**需重点核查的来源（被标 ≥2 次，{len(hot)} 个）**："]
        lines += [f"  - `{truncate(s, 80)}`" for s in hot[:10]]
    lines += ["", "> 标注记录随问题快照保留，可对单条执行「重问复现」验证修复效果。"]
    return lines


def build_report(items: list[dict]) -> str:
    if not items:
        return "# 错误标注分析报告\n\n暂无标注记录。"
    sources = source_counter(items)
    lines = [
        "# 错误标注分析报告", "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}　标注总数：**{len(items)}**",
        "",
    ]
    lines += render_distribution(items) + [""]
    lines += render_detail(items) + [""]
    lines += render_hot_sources(sources, items) + [""]
    lines += render_advice(items, sources)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="错误标注分析报告")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE,
                        help=f"annotations.jsonl 路径（默认 {DEFAULT_FILE}）")
    parser.add_argument("--out", type=Path, default=Path("."), help="输出目录（默认当前目录）")
    args = parser.parse_args()

    items = load_annotations(args.file)
    report = build_report(items)
    out_file = args.out / "annotations_report.md"
    args.out.mkdir(parents=True, exist_ok=True)
    out_file.write_text(report, encoding="utf-8")

    by_type = Counter(it.get("errorType") or "其他" for it in items)
    print(f"标注总数：{len(items)}")
    for t, cnt in by_type.most_common():
        print(f"  {t}: {cnt}")
    print(f"报告已写入 {out_file}")


if __name__ == "__main__":
    main()
