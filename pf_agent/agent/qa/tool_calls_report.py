#!/usr/bin/env python3
"""工具调用统计报告（F-006）：读取 tool_calls.jsonl，按工具聚合 + 会话工具序列。

复盘 Agent 检索行为的分析端：每次问答后端把工具调用明细（工具类型/参数/成败/耗时/
轮次）落盘 tool_calls.jsonl，本脚本聚合统计——看 LLM 走了哪些工具、参数是否合理、
失败集中在哪个工具、检索是否低效（多次 vectorSearch / 频繁 reportDataGap），
驱动 prompt 与检索策略调优。

用法：
    python3 tool_calls_report.py                                # 默认读 ~/.pf_agent/tool_calls.jsonl
    python3 tool_calls_report.py --file /path/to/tool_calls.jsonl
    python3 tool_calls_report.py --sessions                     # 额外输出每会话工具序列
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_FILE = Path.home() / ".pf_agent" / "tool_calls.jsonl"

# 工具名 → 中文说明（展示友好 + 异常参数提示）
TOOL_NAMES = {
    "vectorSearch": "语义检索",
    "searchByMetadata": "元数据枚举",
    "reportDataGap": "缺口报告",
}


def load_records(path: Path) -> list[dict]:
    """读取 JSONL，容错跳过坏行/空行。"""
    records = []
    if not path.exists():
        print(f"[错误] 工具调用文件不存在: {path}", file=sys.stderr)
        return records
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"[警告] 跳过第 {line_no} 行（非 JSON）: {line[:80]}", file=sys.stderr)
    return records


def fmt_ms(ms: float) -> str:
    """耗时格式化：>=1000ms 显示秒，否则毫秒。"""
    return f"{ms / 1000:.1f}s" if ms >= 1000 else f"{ms:.0f}ms"


def per_tool_report(records: list[dict]) -> None:
    """按工具聚合：次数/成败/成功率/平均耗时/结果字符。"""
    by_tool = defaultdict(list)
    for r in records:
        by_tool[r["toolName"]].append(r)

    print(f"{'工具':<20}{'次数':>5}{'成功':>5}{'失败':>5}{'成功率':>9}{'均耗时':>9}{'均结果':>8}")
    print("-" * 64)
    for tool, rs in sorted(by_tool.items(), key=lambda x: -len(x[1])):
        ok = sum(1 for r in rs if r["success"])
        avg_ms = sum(r["durationMs"] for r in rs) / len(rs)
        avg_chars = sum(r["resultChars"] for r in rs) / len(rs)
        name = f"{tool}({TOOL_NAMES.get(tool, '?')})"
        print(f"{name:<20}{len(rs):>5}{ok:>5}{len(rs) - ok:>5}{ok / len(rs):>8.1%}"
              f"{fmt_ms(avg_ms):>9}{avg_chars:>7.0f}")


def session_tool_sequences(records: list[dict]) -> None:
    """按会话输出工具序列：看 LLM 检索路径（多轮/回退/缺口）。"""
    by_session = defaultdict(list)
    for r in records:
        by_session[r["conversationId"]].append(r)

    print(f"\n会话工具序列（共 {len(by_session)} 个会话）:")
    for cid, rs in by_session.items():
        question = (rs[0].get("question") or "")[:24]
        seq = " → ".join(
            f"{r['toolName']}{'✗' if not r['success'] else ''}@{r['round']}" for r in rs
        )
        print(f"  {cid[:8]} [{question}]: {seq}")


def failed_calls(records: list[dict], limit: int = 10) -> None:
    """失败调用清单：定位参数问题/检索异常。"""
    failed = [r for r in records if not r["success"]]
    if not failed:
        return
    print(f"\n失败调用（前 {limit} 条）:")
    for r in failed[:limit]:
        print(f"  {r['timestamp']} {r['toolName']} 耗时{fmt_ms(r['durationMs'])}"
              f" 参数: {r['arguments'][:100]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="工具调用统计报告（F-006）")
    parser.add_argument("--file", default=str(DEFAULT_FILE), help="tool_calls.jsonl 路径")
    parser.add_argument("--sessions", action="store_true", help="额外输出每会话工具序列")
    parser.add_argument("--failures", action="store_true", help="额外输出失败调用清单")
    args = parser.parse_args()

    records = load_records(Path(args.file))
    if not records:
        print("无工具调用记录。")
        return

    n_sessions = len({r["conversationId"] for r in records})
    n_rounds = max(r["round"] for r in records) + 1
    print(f"总工具调用: {len(records)}，会话: {n_sessions}，最大轮次: {n_rounds}\n")

    per_tool_report(records)
    if args.sessions:
        session_tool_sequences(records)
    if args.failures:
        failed_calls(records)


if __name__ == "__main__":
    main()
