package com.pfagent.agent.rag;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

/**
 * ToolCallRecorder 单元测试（F-006 工具调用计数）
 *
 * 覆盖：JSONL 落盘格式、父目录自动创建、追加不覆盖、空列表不写、
 * 非法路径只记日志不抛（遥测不拖垮主链路）。
 */
class ToolCallRecorderTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private ToolCallRecorder recorder(Path filePath) {
        ToolCallRecorder r = new ToolCallRecorder();
        ReflectionTestUtils.setField(r, "filePath", filePath.toString());
        return r;
    }

    private ToolCallRecord record(String toolName, boolean success) {
        return new ToolCallRecord("tc-1", "cid-1", "火球术射程？",
                toolName, "{\"module\":\"spell\"}", success, 12, 150, 0, "2026-08-16T10:00:00");
    }

    private ToolCallTracker.RequestSummary summary(String requestId, String conversationId, String question) {
        return new ToolCallTracker.RequestSummary("request_summary", requestId, conversationId, question,
                "2026-11-12T10:00:00", 41870L, 3, 36200L, 2, 2450L, 2);
    }

    @Test
    void flushWritesOneJsonLinePerRecord(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("tool_calls.jsonl");
        ToolCallRecord r = record("vectorSearch", true);

        recorder(file).flush(List.of(r));

        String line = Files.readString(file, StandardCharsets.UTF_8).strip();
        // 每条记录一行合法 JSON，字段完整可被分析脚本解析
        var parsed = MAPPER.readTree(line);
        assertThat(parsed.get("toolName").asText()).isEqualTo("vectorSearch");
        assertThat(parsed.get("conversationId").asText()).isEqualTo("cid-1");
        assertThat(parsed.get("success").asBoolean()).isTrue();
        assertThat(parsed.get("durationMs").asLong()).isEqualTo(12);
        assertThat(parsed.get("round").asInt()).isEqualTo(0);
        assertThat(parsed.has("timestamp")).isTrue();
    }

    /** AKN-023：工具记录带 requestId 分组键（请求级耗时只写在 request_summary 记录里） */
    @Test
    void flushWritesRequestIdOnToolRecord(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("tool_calls.jsonl");
        ToolCallRecord r = new ToolCallRecord("tc-2", "req-1", "cid-1", "武僧清规有哪些内容",
                "vectorSearch", "{}", true, 30, 150, 0, "2026-11-12T10:00:00");

        recorder(file).flush(List.of(r));

        var parsed = MAPPER.readTree(Files.readString(file, StandardCharsets.UTF_8).strip());
        assertThat(parsed.get("requestId").asText()).isEqualTo("req-1");
        assertThat(parsed.get("toolName").asText()).isEqualTo("vectorSearch");
        assertThat(parsed.has("recordType")).isFalse();
    }

    /** AKN-023：request_summary 记录含 M34 分析脚本识别的字段名，每请求只写一条 */
    @Test
    void flushRequestSummaryWritesRequestLevelRecord(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("tool_calls.jsonl");

        recorder(file).flushRequestSummary(summary("req-1", "cid-1", "武僧清规有哪些内容"));

        var parsed = MAPPER.readTree(Files.readString(file, StandardCharsets.UTF_8).strip());
        assertThat(parsed.get("recordType").asText()).isEqualTo("request_summary");
        assertThat(parsed.get("requestId").asText()).isEqualTo("req-1");
        assertThat(parsed.get("conversationId").asText()).isEqualTo("cid-1");
        assertThat(parsed.get("totalDurationMs").asLong()).isEqualTo(41870L);
        assertThat(parsed.get("llmCallCount").asInt()).isEqualTo(3);
        assertThat(parsed.get("llmDurationMs").asLong()).isEqualTo(36200L);
        assertThat(parsed.get("toolTotalMs").asLong()).isEqualTo(2450L);
        assertThat(parsed.has("toolName")).isFalse();
    }

    /** 旧 10 字段构造（AKN-023 前进来的调用方）仍可序列化；旧 JSONL 反序列化由脚本容错 */
    @Test
    void flushSerializesLegacyRecordWithoutRequestId(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("tool_calls.jsonl");

        recorder(file).flush(List.of(record("vectorSearch", true)));

        var parsed = MAPPER.readTree(Files.readString(file, StandardCharsets.UTF_8).strip());
        assertThat(parsed.get("toolName").asText()).isEqualTo("vectorSearch");
        assertThat(parsed.get("requestId").isNull()).isTrue();
    }

    /** 旧 JSONL 行（无 recordType/requestId/耗时字段）仍可被脚本读取的格式保持一行一 JSON */
    @Test
    void flushKeepsOneJsonLinePerRecordForLegacyCompatibility(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("tool_calls.jsonl");
        recorder(file).flush(List.of(record("vectorSearch", true), record("searchByMetadata", false)));
        recorder(file).flushRequestSummary(summary("req-1", "cid-1", "q"));

        List<String> lines = Files.readAllLines(file, StandardCharsets.UTF_8).stream()
                .filter(line -> !line.isBlank())
                .toList();
        assertThat(lines).hasSize(3);
        assertThat(MAPPER.readTree(lines.get(2)).get("recordType").asText())
                .isEqualTo("request_summary");
    }

    @Test
    void flushCreatesParentDirectories(@TempDir Path tmp) {
        Path file = tmp.resolve("nested/deeper/tool_calls.jsonl");

        assertThatCode(() -> recorder(file).flush(List.of(record("vectorSearch", true))))
                .doesNotThrowAnyException();
        assertThat(file).exists();
    }

    @Test
    void flushAppendsWithoutOverwriting(@TempDir Path tmp) throws Exception {
        Path file = tmp.resolve("tool_calls.jsonl");
        ToolCallRecorder r = recorder(file);

        r.flush(List.of(record("vectorSearch", true)));
        r.flush(List.of(record("searchByMetadata", false)));

        List<String> lines = Files.readAllLines(file, StandardCharsets.UTF_8);
        assertThat(lines).hasSize(2);
        assertThat(MAPPER.readTree(lines.get(1)).get("toolName").asText())
                .isEqualTo("searchByMetadata");
    }

    @Test
    void flushEmptyListWritesNothing(@TempDir Path tmp) {
        Path file = tmp.resolve("tool_calls.jsonl");

        recorder(file).flush(List.of());

        assertThat(file).doesNotExist();
    }

    @Test
    void flushInvalidPathLogsAndDoesNotThrow() {
        // 非法文件路径（父目录是文件而非目录）：落盘失败只记日志，不抛异常拖垮主链路
        ToolCallRecorder r = recorder(Path.of("/dev/null/nonexistent/tool_calls.jsonl"));

        assertThatCode(() -> r.flush(List.of(record("vectorSearch", true))))
                .doesNotThrowAnyException();
    }
}
