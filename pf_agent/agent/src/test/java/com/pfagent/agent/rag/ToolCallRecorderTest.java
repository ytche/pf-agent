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
