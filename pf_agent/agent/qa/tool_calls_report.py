#!/usr/bin/env python3
"""工具调用统计报告（F-006 / AKN-023）：读取 tool_calls.jsonl，按工具聚合 + 请求级分段耗时。

复盘 Agent 检索行为的分析端：每次问答后端把工具调用明细（工具类型/参数/成败/耗时/
轮次）落盘 tool_calls.jsonl，本脚本聚合统计——看 LLM 走了哪些工具、参数是否合理、
失败集中在哪个工具、检索是否低效（多次 vectorSearch / 频繁 reportDataGap），
驱动 prompt 与检索策略调优。

AKN-023 埋点约定（向后兼容）：
  - 每次问答另写一条 recordType=request_summary 的记录，携带
    totalDurationMs / llmCallCount / llmDurationMs / toolTotalMs 等请求级字段，
    无工具调用的问答也有这条记录；
  - 工具调用记录可带 requestId 与对应摘要关联；
  - 旧记录没有这些字段时按未知处理（显示 "-"），不抛异常；
  - 请求级字段每个请求只取一次（优先 request_summary），不按工具行重复累计；
  - 同一 conversationId 的多次问答按 requestId 分开，request_summary 不计入工具统计。

用法：
    python3 tool_calls_report.py                                # 默认读 ~/.pf_agent/tool_calls.jsonl
    python3 tool_calls_report.py --file /path/to/tool_calls.jsonl
    python3 tool_calls_report.py --sessions                     # 额外输出每会话工具序列
    python3 tool_calls_report.py --failures                     # 额外输出失败调用清单
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_FILE = Path.home() / ".pf_agent" / "tool_calls.jsonl"

# 工具名 → 中文说明（展示友好 + 异常参数提示）
TOOL_NAMES = {
    "vectorSearch": "语义检索",
    "searchByMetadata": "元数据枚举",
    "reportDataGap": "缺口报告",
}

# 请求级摘要记录类型（AKN-023）；旧记录没有 recordType，按工具记录处理
REQUEST_SUMMARY_TYPE = "request_summary"

# AKN-023 请求级可选耗时字段（旧记录可能全部缺失）
LATENCY_FIELDS = ("totalDurationMs", "llmCallCount", "llmDurationMs")


def is_request_summary(record: dict) -> bool:
    """是否为请求级摘要记录（不参与工具调用统计）。"""
    return record.get("recordType") == REQUEST_SUMMARY_TYPE


def _number(record: dict, key: str):
    """安全读取数值字段：缺失 / 非数值 / 布尔值返回 None。"""
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _first_number(records: list[dict], key: str):
    """按记录顺序取第一个有效数值：请求级字段每请求只应计一次。"""
    for record in records:
        value = _number(record, key)
        if value is not None:
            return value
    return None


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


def tool_records(records: list[dict]) -> list[dict]:
    """仅工具调用记录（排除 request_summary 摘要行）。"""
    return [r for r in records if not is_request_summary(r)]


def fmt_ms(ms) -> str:
    """耗时格式化：缺失显示 "-"；>=1000ms 显示秒，否则毫秒。"""
    if ms is None:
        return "-"
    return f"{ms / 1000:.1f}s" if ms >= 1000 else f"{ms:.0f}ms"


def per_tool_report(records: list[dict]) -> None:
    """按工具聚合：次数/成败/成功率/平均耗时/结果字符。

    可选字段（durationMs / resultChars）缺失的历史记录不参与对应均值，显示 "-"。
    """
    by_tool = defaultdict(list)
    for r in records:
        by_tool[r.get("toolName") or "?"].append(r)

    print(f"{'工具':<20}{'次数':>5}{'成功':>5}{'失败':>5}{'成功率':>9}{'均耗时':>9}{'均结果':>8}")
    print("-" * 64)
    for tool, rs in sorted(by_tool.items(), key=lambda x: -len(x[1])):
        ok = sum(1 for r in rs if r.get("success"))
        durations = [d for d in (_number(r, "durationMs") for r in rs) if d is not None]
        result_chars = [d for d in (_number(r, "resultChars") for r in rs) if d is not None]
        avg_ms = sum(durations) / len(durations) if durations else None
        avg_chars = sum(result_chars) / len(result_chars) if result_chars else None
        name = f"{tool}({TOOL_NAMES.get(tool, '?')})"
        print(f"{name:<20}{len(rs):>5}{ok:>5}{len(rs) - ok:>5}{ok / len(rs):>8.1%}"
              f"{fmt_ms(avg_ms):>9}{(f'{avg_chars:.0f}' if avg_chars is not None else '-'):>7}")


def _request_key(record: dict) -> str:
    """请求分组键：优先 requestId；旧记录回退 conversationId + question（不同问题即不同请求）。"""
    request_id = record.get("requestId")
    if request_id:
        return str(request_id)
    return f"{record.get('conversationId') or '?'}|{record.get('question') or ''}"


def _has_latency(record: dict) -> bool:
    return is_request_summary(record) or any(
        _number(record, key) is not None for key in LATENCY_FIELDS)


def _request_groups(records: list[dict]) -> list[list[dict]]:
    """按请求分组，只纳入与耗时相关的记录（旧的无耗时工具行不参与）。"""
    groups = {}
    for record in records:
        if not (_has_latency(record) or record.get("requestId")):
            continue
        groups.setdefault(_request_key(record), []).append(record)
    return list(groups.values())


def _request_metrics(group: list[dict]) -> dict:
    """单个请求的请求级指标：摘要记录优先，字段只取一次；工具耗时按工具行求和。"""
    summary = next((r for r in group if is_request_summary(r)), None)
    ordered = ([summary] if summary is not None else []) + [r for r in group if r is not summary]
    tool_rows = [r for r in group if not is_request_summary(r)]
    meta = summary or group[0]

    summary_tool_ms = _number(summary, "toolTotalMs") if summary is not None else None
    if summary_tool_ms is not None:
        tool_ms = summary_tool_ms
    else:
        durations = [d for d in (_number(r, "durationMs") for r in tool_rows) if d is not None]
        tool_ms = sum(durations) if durations else None

    request_id = next((r.get("requestId") for r in group if r.get("requestId")), None)
    return {
        "request_id": str(request_id) if request_id else None,
        "conversation_id": meta.get("conversationId") or "?",
        "question": meta.get("question") or "",
        "total": _first_number(ordered, "totalDurationMs"),
        "llm_count": _first_number(ordered, "llmCallCount"),
        "llm_ms": _first_number(ordered, "llmDurationMs"),
        "tool_ms": tool_ms,
    }


def latency_report(records: list[dict]) -> None:
    """AKN-023 分段耗时汇总：按请求一行，请求级字段每请求只计一次。

    网络耗时与服务端耗时无法拆分，口径统一标注为「LLM 调用端到端耗时（含网络）」。
    """
    if not any(_has_latency(r) for r in records):
        return

    print("\n分段耗时（LLM 调用端到端耗时（含网络）；缺失字段显示 '-'）:")
    print(f"{'请求':<22}{'会话':<10}{'总耗时':>10}{'LLM 次数':>9}{'LLM 累计':>10}{'工具累计':>10}")
    print("-" * 76)
    for group in _request_groups(records):
        metrics = _request_metrics(group)
        key = metrics["request_id"] if metrics["request_id"] else metrics["conversation_id"][:8]
        llm_count = "-" if metrics["llm_count"] is None else str(int(metrics["llm_count"]))
        question = metrics["question"][:12]
        print(f"{key:<22}{metrics['conversation_id'][:8]:<10}"
              f"{fmt_ms(metrics['total']):>10}{llm_count:>9}"
              f"{fmt_ms(metrics['llm_ms']):>10}{fmt_ms(metrics['tool_ms']):>10}"
              f"  [{question}]")


def session_tool_sequences(records: list[dict]) -> None:
    """按会话输出工具序列：看 LLM 检索路径（多轮/回退/缺口）。"""
    by_session = defaultdict(list)
    for r in records:
        by_session[r.get("conversationId") or "?"].append(r)

    print(f"\n会话工具序列（共 {len(by_session)} 个会话）:")
    for cid, rs in by_session.items():
        question = (rs[0].get("question") or "")[:24]
        seq = " → ".join(
            f"{r.get('toolName') or '?'}"
            f"{'✗' if r.get('success') is False else ''}"
            f"@{r.get('round') if r.get('round') is not None else '?'}"
            for r in rs
        )
        print(f"  {cid[:8]} [{question}]: {seq}")


def failed_calls(records: list[dict], limit: int = 10) -> None:
    """失败调用清单：定位参数问题/检索异常。"""
    failed = [r for r in records if not r.get("success")]
    if not failed:
        return
    print(f"\n失败调用（前 {limit} 条）:")
    for r in failed[:limit]:
        print(f"  {r.get('timestamp') or '?'} {r.get('toolName') or '?'}"
              f" 耗时{fmt_ms(_number(r, 'durationMs'))}"
              f" 参数: {(r.get('arguments') or '')[:100]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="工具调用统计报告（F-006 / AKN-023）")
    parser.add_argument("--file", default=str(DEFAULT_FILE), help="tool_calls.jsonl 路径")
    parser.add_argument("--sessions", action="store_true", help="额外输出每会话工具序列")
    parser.add_argument("--failures", action="store_true", help="额外输出失败调用清单")
    args = parser.parse_args()

    records = load_records(Path(args.file))
    if not records:
        print("无工具调用记录。")
        return

    calls = tool_records(records)
    summaries = [r for r in records if is_request_summary(r)]
    n_sessions = len({r.get("conversationId") or "?" for r in records})
    # 无工具行时最大轮次为 0：只有 request_summary 的文件不能虚构一轮工具调用
    rounds = [v for v in (_number(r, "round") for r in calls) if v is not None]
    n_rounds = max(rounds) + 1 if rounds else 0
    print(f"总工具调用: {len(calls)}，请求摘要: {len(summaries)}，会话: {n_sessions}，"
          f"最大轮次: {n_rounds}\n")

    per_tool_report(calls)
    latency_report(records)
    if args.sessions:
        session_tool_sequences(calls)
    if args.failures:
        failed_calls(calls)


if __name__ == "__main__":
    main()
