package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

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

    // ---------- SP8a J3：listGaps 只读读取 ----------

    /** 读取最新在前，limit 截断 */
    @Test
    void listGapsReturnsLatestFirstWithLimit() throws Exception {
        Path file = tempDir.resolve("gaps.jsonl");
        DataGapRecorder r = recorder(file);
        r.record("q1", "f1", "r1");
        r.record("q2", "f2", "r2");
        r.record("q3", "f3", "r3");

        List<DataGapRecorder.GapEntry> gaps = r.listGaps(2, null);

        assertThat(gaps).hasSize(2);
        assertThat(gaps.get(0).question()).isEqualTo("q3"); // 最新在前
        assertThat(gaps.get(1).question()).isEqualTo("q2");
    }

    /** keyword 对 question/reason 子串匹配 */
    @Test
    void listGapsKeywordFiltersQuestionAndReason() throws Exception {
        Path file = tempDir.resolve("gaps.jsonl");
        DataGapRecorder r = recorder(file);
        r.record("女巫的XX规则", "f1", "查不到");
        r.record("牧师问题", "f2", "缺少女巫变体数据");

        List<DataGapRecorder.GapEntry> gaps = r.listGaps(10, "女巫");

        assertThat(gaps).hasSize(2); // question 命中 + reason 命中
    }

    /** 单行损坏跳过不抛异常，其余正常返回 */
    @Test
    void listGapsSkipsCorruptLines() throws Exception {
        Path file = tempDir.resolve("gaps.jsonl");
        DataGapRecorder r = recorder(file);
        r.record("q1", "f1", "r1");
        Files.writeString(file, "{bad json\n", StandardCharsets.UTF_8,
                java.nio.file.StandardOpenOption.APPEND);

        List<DataGapRecorder.GapEntry> gaps = r.listGaps(10, null);

        assertThat(gaps).hasSize(1);
        assertThat(gaps.get(0).question()).isEqualTo("q1");
    }

    /** 文件不存在返回空列表 */
    @Test
    void listGapsMissingFileReturnsEmpty() {
        Path file = tempDir.resolve("not_exists.jsonl");

        assertThat(recorder(file).listGaps(20, null)).isEmpty();
    }

    /** keyword 不命中的记录被排除，命中记录保持最新在前 */
    @Test
    void listGapsKeywordExcludesNonMatchingRecords() throws Exception {
        Path file = tempDir.resolve("gaps.jsonl");
        DataGapRecorder r = recorder(file);
        r.record("匹配问题一", "f1", "查不到女巫规则");
        r.record("无关问题", "f2", "无关原因");
        r.record("无关问题二", "f3", "命中原因 女巫变体");

        List<DataGapRecorder.GapEntry> gaps = r.listGaps(10, "女巫");

        assertThat(gaps).hasSize(2);
        assertThat(gaps.get(0).reason()).isEqualTo("命中原因 女巫变体"); // 最新命中在前
        assertThat(gaps.get(1).question()).isEqualTo("匹配问题一");
    }

    /** limit 为 0 或负数时直接返回空列表（读取侧防御） */
    @Test
    void listGapsNonPositiveLimitReturnsEmpty() throws Exception {
        Path file = tempDir.resolve("gaps.jsonl");
        DataGapRecorder r = recorder(file);
        r.record("q1", "f1", "r1");

        assertThat(r.listGaps(0, null)).isEmpty();
        assertThat(r.listGaps(-5, null)).isEmpty();
    }
}
