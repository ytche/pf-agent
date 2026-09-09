package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * DataGapRecorder 单元测试
 *
 * 覆盖数据缺口 JSONL 追加（设计 §7）：
 *  - record 追加一行 JSONL，含 question/attemptedFilters/reason/timestamp
 *  - 多次调用逐行追加（不覆盖）
 *  - 父目录不存在时自动创建
 */
class DataGapRecorderTest {

    @TempDir
    Path tempDir;

    /** 追加 JSONL 一行，含 question/attemptedFilters/reason/timestamp 全部字段 */
    @Test
    void recordAppendsJsonlLineWithAllFieldsAndTimestamp() throws Exception {
        Path file = tempDir.resolve("data_gaps.jsonl");

        recorder(file).record("女巫的XX变体规则", "{className:女巫}", "查不到该变体");

        String line = Files.readString(file, StandardCharsets.UTF_8).trim();
        assertThat(line).contains("\"question\":\"女巫的XX变体规则\"");
        assertThat(line).contains("\"attemptedFilters\":\"{className:女巫}\"");
        assertThat(line).contains("\"reason\":\"查不到该变体\"");
        assertThat(line).matches(".*\"timestamp\":\"\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\".*");
    }

    /** 多次调用逐行追加，不覆盖历史 */
    @Test
    void recordAppendsMultipleLinesWithoutOverwrite() throws Exception {
        Path file = tempDir.resolve("gaps.jsonl");
        DataGapRecorder r = recorder(file);

        r.record("q1", "f1", "r1");
        r.record("q2", "f2", "r2");

        String content = Files.readString(file, StandardCharsets.UTF_8);
        assertThat(content.lines()).hasSize(2);
        assertThat(content).contains("q1").contains("q2");
    }

    /** 父目录不存在时自动创建 */
    @Test
    void recordCreatesMissingParentDirectory() throws Exception {
        Path file = tempDir.resolve("nested").resolve("deep").resolve("gaps.jsonl");

        recorder(file).record("q", "f", "r");

        assertThat(file).exists();
        assertThat(Files.readString(file, StandardCharsets.UTF_8)).contains("q");
    }

    private DataGapRecorder recorder(Path file) {
        DataGapRecorder r = new DataGapRecorder();
        ReflectionTestUtils.setField(r, "filePath", file.toString());
        return r;
    }
}
