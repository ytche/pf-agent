package com.pfagent.agent.rag;

import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.test.util.ReflectionTestUtils;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.regex.Pattern;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * AKN-023 producer → consumer 集成测试：Java 落盘的 tool_calls.jsonl 交给真实
 * qa/tool_calls_report.py 聚合，验证契约不是靠 Java 单测自证。
 *
 * 覆盖：
 *  - 多工具（含同轮多工具）请求：请求级指标只按 request_summary 计一次，不按工具行重复累计；
 *  - 同一 conversationId 的两次问答：按 requestId 分成两行，不混合；
 *  - 无工具请求：只写 request_summary，报告仍输出其总耗时/LLM 指标；
 *  - 旧 JSONL 行与新记录混排：脚本不报错，旧行仍进工具统计（向后兼容）。
 *
 * 依赖本机 python3（CI 同）；不可用时跳过而不是失败。
 */
class ToolCallReportingIntegrationTest {

    @TempDir
    Path tmp;

    /** 多工具 + 同会话多请求 + 无工具请求，真实脚本一次跑通 */
    @Test
    void reportReadsMultiToolRequestAndSeparatesSameConversationRequests() throws Exception {
        assumeReportAvailable();
        Path file = tmp.resolve("tool_calls.jsonl");
        ToolCallRecorder recorder = recorder(file);
        String cid = "conv-shared";
        String question = "武僧清规有哪些内容";

        recorder.flush(List.of(
                call("tc-a1", "req-a", cid, question, "vectorSearch", 800, 0),
                call("tc-a2", "req-a", cid, question, "searchByMetadata", 700, 0)));
        recorder.flush(List.of(
                call("tc-a3", "req-a", cid, question, "vectorSearch", 1000, 1)));
        recorder.flushRequestSummary(summary("req-a", cid, question, 41000, 3, 36000, 3, 2500, 2));

        recorder.flush(List.of(
                call("tc-b1", "req-b", cid, question, "vectorSearch", 400, 0)));
        recorder.flushRequestSummary(summary("req-b", cid, question, 12000, 1, 9000, 1, 400, 1));

        recorder.flushRequestSummary(summary("req-c", "conv-no-tool", "火球术射程？",
                5000, 1, 4500, 0, 0, 0));

        String out = runReport(file);

        assertThat(out).contains("总工具调用: 4", "请求摘要: 3");
        assertThat(row(out, "req-a").subList(0, 6))
                .containsExactly("req-a", "conv-sha", "41.0s", "3", "36.0s", "2.5s");
        assertThat(row(out, "req-b").subList(0, 6))
                .containsExactly("req-b", "conv-sha", "12.0s", "1", "9.0s", "400ms");
        assertThat(row(out, "req-c").subList(0, 6))
                .containsExactly("req-c", "conv-no-", "5.0s", "1", "4.5s", "0ms");
    }

    /** 旧 F-006 行（无 recordType/requestId/耗时字段）+ 新摘要混排：脚本不报错且旧行仍统计 */
    @Test
    void reportStillReadsLegacyJsonlNextToNewRequestSummary() throws Exception {
        assumeReportAvailable();
        Path file = tmp.resolve("tool_calls.jsonl");
        Files.writeString(file, """
                {"id":"tc-old","conversationId":"conv-old","question":"旧问题","toolName":"vectorSearch",\
                "arguments":"{}","success":true,"durationMs":12,"resultChars":150,"round":0,\
                "timestamp":"2026-08-16T10:00:00"}
                """, StandardCharsets.UTF_8);
        recorder(file).flushRequestSummary(summary("req-new", "conv-new", "新问题",
                8000, 2, 7000, 0, 0, 0));

        String out = runReport(file);

        assertThat(out).contains("总工具调用: 1", "请求摘要: 1");
        assertThat(out).contains("vectorSearch(语义检索)");
        assertThat(row(out, "req-new").subList(0, 6))
                .containsExactly("req-new", "conv-new", "8.0s", "2", "7.0s", "0ms");
    }

    private ToolCallRecorder recorder(Path file) {
        ToolCallRecorder recorder = new ToolCallRecorder();
        ReflectionTestUtils.setField(recorder, "filePath", file.toString());
        return recorder;
    }

    private ToolCallRecord call(String id, String requestId, String conversationId, String question,
                                String toolName, long durationMs, int round) {
        return new ToolCallRecord(id, requestId, conversationId, question, toolName, "{}",
                true, durationMs, 120, round, "2026-11-12T10:00:00");
    }

    private ToolCallTracker.RequestSummary summary(String requestId, String conversationId,
                                                   String question, long totalDurationMs,
                                                   int llmCallCount, long llmDurationMs,
                                                   int toolCallCount, long toolTotalMs,
                                                   int toolRounds) {
        return new ToolCallTracker.RequestSummary(ToolCallTracker.REQUEST_SUMMARY_TYPE, requestId,
                conversationId, question, "2026-11-12T10:00:00", totalDurationMs, llmCallCount,
                llmDurationMs, toolCallCount, toolTotalMs, toolRounds);
    }

    private String runReport(Path file) throws Exception {
        Process process = new ProcessBuilder("python3", reportScript().toString(),
                "--file", file.toString()).redirectErrorStream(true).start();
        String out = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        assertThat(process.waitFor()).as("tool_calls_report.py 退出码\n" + out).isZero();
        return out;
    }

    private List<String> row(String out, String requestId) {
        Pattern pattern = Pattern.compile(Pattern.quote(requestId) + "\\s+.*");
        return out.lines()
                .map(String::strip)
                .filter(line -> pattern.matcher(line).matches())
                .findFirst()
                .map(line -> List.of(line.split("\\s+")))
                .orElseThrow(() -> new AssertionError("报告中找不到请求行: " + requestId + "\n" + out));
    }

    private void assumeReportAvailable() {
        Assumptions.assumeTrue(Files.exists(reportScript()),
                "qa/tool_calls_report.py 不存在（请从 pf_agent/agent 模块目录运行）");
        Assumptions.assumeTrue(pythonAvailable(), "本机 python3 不可用");
    }

    private boolean pythonAvailable() {
        try {
            Process process = new ProcessBuilder("python3", "--version").start();
            return process.waitFor() == 0;
        } catch (IOException | InterruptedException e) {
            Thread.currentThread().interrupt();
            return false;
        }
    }

    private Path reportScript() {
        Path module = Path.of("").toAbsolutePath();
        Path direct = module.resolve("qa/tool_calls_report.py");
        return Files.exists(direct) ? direct : module.resolve("pf_agent/agent/qa/tool_calls_report.py");
    }
}
