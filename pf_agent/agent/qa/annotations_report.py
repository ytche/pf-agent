#!/usr/bin/env python3
"""错误标注分析报告：读取 error_annotation 表，按 errorType 聚类并输出优化建议。

错误标注闭环的分析端：前端「标错」→ /api/chat/feedback → error_annotation 表 → 本脚本
聚类统计 + 典型错误示例 + 优化建议（指向 prompt/检索/数据三处优化点），
把用户标注变成可执行的优化输入，驱动 Agent 准确率提升。

F-021 起标注入库（不再落 annotations.jsonl），本脚本相应改为直连 PostgreSQL 读取；
历史 JSONL 的一次性导入见 TelemetryImporter（PF_TELEMETRY_IMPORT_ENABLED=true 启动一次）。

用法：
    python3 annotations_report.py                                  # 连默认本地 PG
    python3 annotations_report.py --dsn postgresql://u:p@host:5432/pf_agent
    python3 annotations_report.py --out ./out                       # 输出目录（默认当前目录）

连接串优先级：--dsn > 环境变量 PF_ANNOTATIONS_DSN > SPRING_DATASOURCE_URL > 内置默认
（内置默认与 application.yml 的开发默认一致：pf_agent/pf_agent@localhost:5432/pf_agent）。
依赖 psycopg2（pip install psycopg2-binary）。
"""
import argparse
import json
import os
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

DEFAULT_DSN = "postgresql://pf_agent:pf_agent@localhost:5432/pf_agent"

QUERY = """
SELECT id, conversation_id, question, answer, sources, error_type,
       correction, comment, resolution, created_at
FROM error_annotation
ORDER BY created_at ASC, id ASC
"""


def resolve_dsn(explicit: str | None) -> str:
    """连接串优先级：--dsn > PF_ANNOTATIONS_DSN > SPRING_DATASOURCE_URL > 内置默认。"""
    for candidate in (explicit, os.environ.get("PF_ANNOTATIONS_DSN"),
                      os.environ.get("SPRING_DATASOURCE_URL")):
        if candidate:
            return candidate.removeprefix("jdbc:")  # Spring 的 jdbc: 前缀不是 libpq DSN 语法
    return DEFAULT_DSN


def load_annotations(dsn: str) -> list[dict]:
    """读 error_annotation 表，映射为与原 JSONL 行同形的 dict（渲染口径不变）。"""
    try:
        import psycopg2  # 延迟导入：缺依赖时不影响本模块其余纯函数被复用/测试
        from psycopg2.extras import RealDictCursor
    except ImportError:
        print("[错误] 缺少 psycopg2（pip install psycopg2-binary）", file=sys.stderr)
        return []

    try:
        with psycopg2.connect(dsn, cursor_factory=RealDictCursor) as conn, conn.cursor() as cur:
            cur.execute(QUERY)
            rows = cur.fetchall()
    except Exception as e:  # 连接失败/表不存在/权限不足：如实报错并给空报告
        print(f"[错误] 读取 error_annotation 失败: {e}", file=sys.stderr)
        return []

    return [row_to_item(row) for row in rows]


def row_to_item(row: dict) -> dict:
    """表行 → 报告渲染用的 dict（字段名与键名对齐原 JSONL 行）。"""
    sources = row.get("sources")
    if isinstance(sources, (str, bytes)):  # 驱动未做 jsonb 适配时兜底解析
        try:
            sources = json.loads(sources)
        except json.JSONDecodeError:
            print(f"[警告] sources 解析失败，按无来源处理: {str(sources)[:80]}", file=sys.stderr)
            sources = []
    created_at = row.get("created_at")
    return {
        "id": row.get("id") or "",
        "conversationId": row.get("conversation_id"),
        "question": row.get("question"),
        "answer": row.get("answer"),
        "sources": sources or [],
        "errorType": row.get("error_type"),
        "correction": row.get("correction"),
        "comment": row.get("comment"),
        "resolution": row.get("resolution"),
        # 秒精度本地时间字符串，与旧 JSONL 的展示口径一致：db 会话时区可能是 UTC，
        # 显式 astimezone() 归一到运行脚本机器的本地时区
        "timestamp": created_at.astimezone().strftime("%Y-%m-%dT%H:%M:%S") if created_at else "",
    }


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
    parser = argparse.ArgumentParser(description="错误标注分析报告（读 error_annotation 表）")
    parser.add_argument("--dsn", type=str, default=None,
                        help="PostgreSQL 连接串；默认取 PF_ANNOTATIONS_DSN / SPRING_DATASOURCE_URL / 内置默认")
    parser.add_argument("--out", type=Path, default=Path("."), help="输出目录（默认当前目录）")
    args = parser.parse_args()

    items = load_annotations(resolve_dsn(args.dsn))
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
