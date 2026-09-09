package com.pfagent.agent.chat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * FeedbackRecorder 单元测试
 *
 * 覆盖错误标注 JSONL 落盘（错误标注闭环，对标 DataGapRecorder 的 data_gaps 模式）：
 *  - record 追加一行 JSONL，含 id/conversationId/question/answer/sources/errorType/
 *    correction/comment/resolution/timestamp 全部字段与回答快照
 *  - 多次调用逐行追加（不覆盖）
 *  - 父目录不存在时自动创建
 *  - record 返回生成的 id，且两次调用 id 唯一
 *  - correction/comment 可为空（仅类型标注也落盘）
 */
class FeedbackRecorderTest {

    @TempDir
    Path tempDir;

    /** 追加一条 JSONL：含 id/会话/问题/回答/sources 快照/类型/时间戳等全部字段与回答快照 */
    @Test
    void recordAppendsJsonlLineWithAllFieldsAndSnapshot() throws Exception {
        Path file = tempDir.resolve("annotations.jsonl");
        String id = recorder(file).record(request());
        String line = Files.readString(file, StandardCharsets.UTF_8).trim();

        assertThat(id).startsWith("ann-");
        assertThat(line).contains("\"id\":\"" + id + "\"");
        assertThat(line).contains("\"conversationId\":\"cid-1\"");
        assertThat(line).contains("\"question\":\"火球术是几环？\"");
        assertThat(line).contains("\"answer\":\"3 环\"");
        assertThat(line).contains("\"errorType\":\"事实错误\"");
        assertThat(line).contains("\"correction\":\"射程写错了\"");
        assertThat(line).contains("\"comment\":\"用户备注\"");
        assertThat(line).contains("\"resolution\":\"待分析\"");
        assertThat(line).matches(".*\"timestamp\":\"\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\".*");
        // sources 快照：回答当时引用的 chunk，供分析时精确复现（含 chunk_id 可追溯到具体 chunk）
        assertThat(line).contains(
                "\"sources\":[{\"book\":\"核心规则书 (CRB)\",\"tocPath\":\"法术 > 火球术\",\"chunkId\":\"spell_CRB_0001\",\"content\":\"火球术是 3 环法术\"}]");
    }

    /** 多次调用逐行追加，不覆盖历史 */
    @Test
    void recordAppendsMultipleLinesWithoutOverwrite() throws Exception {
        Path file = tempDir.resolve("annotations.jsonl");
        FeedbackRecorder r = recorder(file);

        r.record(request());
        r.record(new FeedbackRequest("cid-2", "q2", "a2", List.of(), "答非所问", null, null));

        assertThat(Files.readString(file, StandardCharsets.UTF_8).lines()).hasSize(2);
    }

    /** 父目录不存在时自动创建后落盘 */
    @Test
    void recordCreatesMissingParentDirectory() throws Exception {
        Path file = tempDir.resolve("nested").resolve("deep").resolve("annotations.jsonl");

        recorder(file).record(request());

        assertThat(file).exists();
    }

    /** 每次调用返回唯一 id，两次不同 */
    @Test
    void recordReturnsUniqueIdPerCall() throws Exception {
        Path file = tempDir.resolve("annotations.jsonl");
        FeedbackRecorder r = recorder(file);

        String id1 = r.record(request());
        String id2 = r.record(request());

        assertThat(id1).isNotEqualTo(id2);
    }

    /** correction/comment 为空（仅类型标注）时仍正常落盘 */
    @Test
    void recordPersistsWithoutOptionalFields() throws Exception {
        Path file = tempDir.resolve("annotations.jsonl");

        recorder(file).record(new FeedbackRequest("cid-3", "q", "a", List.of(), "结构差", null, null));

        String line = Files.readString(file, StandardCharsets.UTF_8).trim();
        assertThat(line).contains("\"errorType\":\"结构差\"");
    }

    private FeedbackRecorder recorder(Path file) {
        FeedbackRecorder r = new FeedbackRecorder();
        ReflectionTestUtils.setField(r, "filePath", file.toString());
        return r;
    }

    private FeedbackRequest request() {
        var src = new ChatResponse.SourceRef("核心规则书 (CRB)", "法术 > 火球术", "spell_CRB_0001", "火球术是 3 环法术");
        return new FeedbackRequest("cid-1", "火球术是几环？", "3 环", List.of(src),
                "事实错误", "射程写错了", "用户备注");
    }
}
