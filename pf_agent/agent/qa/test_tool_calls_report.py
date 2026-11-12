"""tool_calls_report.py 向后兼容 + 请求级耗时聚合测试（AKN-023）.

旧格式记录只有 toolName/success/durationMs/resultChars/round 等基础字段；
AKN-023 之后每次问答写一条 recordType=request_summary 的请求级摘要
（totalDurationMs/llmCallCount/llmDurationMs），工具记录可带 requestId 分组。
分析脚本必须：
  - 任何字段缺失时不报错（旧 JSONL 继续可读，未知值显示 "-"）；
  - 请求级字段每个请求只取一次，不按工具行重复累计；
  - 同一 conversationId 的多次问答按 requestId 分开；
  - request_summary 记录不得被当作工具调用统计。
"""
import json
import sys

import tool_calls_report


def _old_record(**overrides) -> dict:
    rec = {
        "timestamp": "2026-11-10T10:00:00",
        "conversationId": "conv-1",
        "question": "武僧清规有哪些内容",
        "toolName": "vectorSearch",
        "arguments": "{}",
        "success": True,
        "resultChars": 120,
        "round": 0,
    }
    rec.update(overrides)
    return rec


def _request_summary(**overrides) -> dict:
    rec = {
        "recordType": "request_summary",
        "requestId": "req-1",
        "conversationId": "conv-1",
        "question": "武僧清规有哪些内容",
        "timestamp": "2026-11-12T10:00:00",
        "totalDurationMs": 41000,
        "llmCallCount": 3,
        "llmDurationMs": 36000,
        "toolCallCount": 2,
        "toolTotalMs": 2500,
        "toolRounds": 2,
    }
    rec.update(overrides)
    return rec


def _latency_rows(out: str, prefix: str) -> list[list[str]]:
    return [line.split() for line in out.splitlines()
            if line.strip().startswith(prefix)]


def test_old_records_without_duration_fields_do_not_crash(capsys):
    records = [_old_record(), _old_record(toolName="searchByMetadata", success=False)]

    tool_calls_report.per_tool_report(records)

    out = capsys.readouterr().out
    assert "vectorSearch" in out
    assert "-" in out  # 无耗时字段时展示占位，而不是异常


def test_old_records_without_latency_fields_produce_no_latency_section(capsys):
    tool_calls_report.latency_report([_old_record(), _old_record(toolName="searchByMetadata")])

    assert "分段耗时" not in capsys.readouterr().out


def test_records_with_optional_latency_fields_aggregate(capsys):
    records = [
        _old_record(durationMs=30, totalDurationMs=41000, llmCallCount=2,
                    llmDurationMs=30000),
        _old_record(durationMs=50, resultChars=80),
    ]

    tool_calls_report.per_tool_report(records)
    tool_calls_report.latency_report(records)

    out = capsys.readouterr().out
    assert "vectorSearch" in out
    assert "LLM 调用端到端耗时（含网络）" in out


def test_latency_report_takes_request_fields_once_per_request(capsys):
    """同一请求的多条工具行都带请求级字段时，只取一次而不是按行累加。"""
    records = [
        _old_record(requestId="req-1", durationMs=30, totalDurationMs=1000,
                    llmCallCount=3, llmDurationMs=800),
        _old_record(requestId="req-1", durationMs=50, totalDurationMs=1000,
                    llmCallCount=3, llmDurationMs=800),
    ]

    tool_calls_report.latency_report(records)

    row = _latency_rows(capsys.readouterr().out, "req-1")[0]
    assert row[0] == "req-1"
    assert row[2] == "1.0s"      # 总耗时只取一次
    assert row[3] == "3"         # LLM 次数不是 6
    assert row[4] == "800ms"     # LLM 累计不是 1.6s
    assert row[5] == "80ms"      # 工具耗时按工具行真实求和


def test_request_summary_is_used_once_for_multi_tool_request(capsys):
    records = [
        _request_summary(requestId="req-a", toolCallCount=2, toolTotalMs=2500),
        _old_record(requestId="req-a", durationMs=800, round=0),
        _old_record(requestId="req-a", durationMs=1700, round=1, toolName="searchByMetadata"),
    ]

    tool_calls_report.latency_report(records)

    row = _latency_rows(capsys.readouterr().out, "req-a")[0]
    assert row[2] == "41.0s"
    assert row[3] == "3"
    assert row[4] == "36.0s"
    assert row[5] == "2.5s"


def test_request_summary_only_request_appears_in_latency_report(capsys):
    records = [_request_summary(requestId="req-no-tool", conversationId="conv-x",
                                toolCallCount=0, toolTotalMs=0, toolRounds=0)]

    tool_calls_report.latency_report(records)
    tool_calls_report.per_tool_report([])

    row = _latency_rows(capsys.readouterr().out, "req-no-tool")[0]
    assert row[2] == "41.0s"
    assert row[3] == "3"
    assert row[5] == "0ms"


def test_latency_report_separates_requests_in_same_conversation(capsys):
    records = [
        _request_summary(requestId="req-a", conversationId="conv-shared",
                         totalDurationMs=41000, llmCallCount=3, llmDurationMs=36000),
        _request_summary(requestId="req-b", conversationId="conv-shared",
                         totalDurationMs=12000, llmCallCount=1, llmDurationMs=9000),
    ]

    tool_calls_report.latency_report(records)

    out = capsys.readouterr().out
    assert len(_latency_rows(out, "req-a")) == 1
    assert len(_latency_rows(out, "req-b")) == 1
    row_a = _latency_rows(out, "req-a")[0]
    row_b = _latency_rows(out, "req-b")[0]
    assert row_a[1] == "conv-sha"
    assert row_a[2] == "41.0s"
    assert row_b[2] == "12.0s"
    assert row_b[3] == "1"


def test_latency_report_partial_fields_per_request(capsys):
    """旧式记录（无 requestId）按 conversationId+question 分组，缺失字段显示 '-'。"""
    records = [
        {"conversationId": "conv-partial", "question": "q1", "totalDurationMs": 1000},
        {"conversationId": "conv-partial", "question": "q2", "totalDurationMs": 2000},
        {"conversationId": "conv-mixed", "question": "q1", "totalDurationMs": 1000,
         "llmCallCount": 2},
        {"conversationId": "conv-mixed", "question": "q2", "totalDurationMs": 2000,
         "llmDurationMs": 500, "durationMs": 200},
    ]

    tool_calls_report.latency_report(records)

    out = capsys.readouterr().out
    partial = _latency_rows(out, "conv-par")
    assert len(partial) == 2
    assert partial[0][2:6] == ["1.0s", "-", "-", "-"]
    assert partial[1][2:6] == ["2.0s", "-", "-", "-"]
    mixed = _latency_rows(out, "conv-mix")
    assert len(mixed) == 2
    assert mixed[0][2:6] == ["1.0s", "2", "-", "-"]
    assert mixed[1][2:6] == ["2.0s", "-", "500ms", "200ms"]


def test_request_summary_records_are_not_counted_as_tool_calls(capsys):
    records = [
        _request_summary(),
        _old_record(durationMs=12),
    ]

    tool_calls_report.per_tool_report(
        [r for r in records if not tool_calls_report.is_request_summary(r)])
    tool_calls_report.session_tool_sequences(
        [r for r in records if not tool_calls_report.is_request_summary(r)])

    out = capsys.readouterr().out
    assert "vectorSearch(语义检索)" in out
    assert "请求摘要" not in out
    assert "vectorSearch@0" in out


def test_session_sequences_tolerate_missing_round_and_success(capsys):
    records = [
        {"conversationId": "conv-1", "question": "q", "toolName": "vectorSearch"},
        {"conversationId": "conv-1", "question": "q", "toolName": "searchByMetadata",
         "success": False},
    ]

    tool_calls_report.session_tool_sequences(records)

    out = capsys.readouterr().out
    assert "vectorSearch@?" in out
    assert "searchByMetadata✗@?" in out


def test_main_reports_zero_rounds_when_only_request_summary_exists(tmp_path, capsys, monkeypatch):
    """无工具行时不得虚构工具轮次：只有摘要（toolRounds=0）应报最大轮次 0。"""
    path = tmp_path / "tool_calls.jsonl"
    path.write_text(
        json.dumps(_request_summary(requestId="req-no-tool", toolCallCount=0,
                                    toolTotalMs=0, toolRounds=0), ensure_ascii=False) + "\n",
        encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["tool_calls_report.py", "--file", str(path)])

    tool_calls_report.main()

    out = capsys.readouterr().out
    assert "总工具调用: 0，请求摘要: 1，会话: 1，最大轮次: 0" in out


def test_load_records_skips_unknown_optional_fields(tmp_path):
    path = tmp_path / "tool_calls.jsonl"
    lines = [
        json.dumps(_old_record(), ensure_ascii=False),
        json.dumps(_old_record(durationMs=12, llmCallCount=3), ensure_ascii=False),
        json.dumps(_request_summary(), ensure_ascii=False),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    records = tool_calls_report.load_records(path)

    assert len(records) == 3
    assert tool_calls_report.is_request_summary(records[2])
