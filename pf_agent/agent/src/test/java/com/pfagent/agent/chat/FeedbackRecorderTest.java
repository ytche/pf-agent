package com.pfagent.agent.chat;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pfagent.agent.telemetry.ErrorAnnotationEntity;
import com.pfagent.agent.telemetry.ErrorAnnotationRepository;
import com.pfagent.agent.telemetry.ErrorAnnotationService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * FeedbackRecorder 集成测试（F-021：标注入库，@DataJpaTest + H2）
 *
 * 覆盖错误标注写 error_annotation 表（替代原 annotations.jsonl 落盘）：
 *  - record 落一行，含 id/conversationId/question/answer/sources/errorType/
 *    correction/comment/resolution 全部字段与回答快照（sources 为 JSONB 列）
 *  - 多次调用各落一行（id 唯一），不覆盖历史
 *  - correction/comment/sources 可为空
 *  - 入库成功返回 ok=true + id（降级路径由 FeedbackRecorderMemoryModeTest 覆盖）
 *
 * 关闭 Flyway（V4 是 PG 方言）：由 Hibernate 按实体注解 create-drop 建表。
 * FeedbackRecorder/ErrorAnnotationService 是 @Component，slice 测试不自动装配，
 * 此处手动 new + 反射注入真仓库与事务模板（同 JdbcChatMemoryTest 口径）。
 */
@DataJpaTest(properties = {"spring.flyway.enabled=false", "spring.jpa.hibernate.ddl-auto=create-drop"})
class FeedbackRecorderTest {

    private static final ObjectMapper JSON = new ObjectMapper();

    @Autowired
    private ErrorAnnotationRepository repository;
    @Autowired
    private PlatformTransactionManager transactionManager;

    private FeedbackRecorder recorder;

    @BeforeEach
    void setUp() {
        ErrorAnnotationService service = new ErrorAnnotationService();
        ReflectionTestUtils.setField(service, "repository", repository);
        ReflectionTestUtils.setField(service, "transactionTemplate", new TransactionTemplate(transactionManager));

        recorder = new FeedbackRecorder();
        ReflectionTestUtils.setField(recorder, "annotationServiceProvider", providerOf(service));
    }

    /** 落库一行：全部字段与回答快照（sources 存 JSONB）齐备 */
    @Test
    void recordPersistsRowWithAllFieldsAndSnapshot() throws Exception {
        FeedbackResponse response = recorder.record(request());

        assertThat(response.ok()).isTrue();
        assertThat(response.id()).startsWith("ann-");

        ErrorAnnotationEntity row = repository.findById(response.id()).orElseThrow();
        assertThat(row.getConversationId()).isEqualTo("cid-1");
        assertThat(row.getQuestion()).isEqualTo("火球术是几环？");
        assertThat(row.getAnswer()).isEqualTo("3 环");
        assertThat(row.getErrorType()).isEqualTo("事实错误");
        assertThat(row.getCorrection()).isEqualTo("射程写错了");
        assertThat(row.getComment()).isEqualTo("用户备注");
        assertThat(row.getResolution()).isEqualTo("待分析");
        assertThat(row.getCreatedAt())
                .isBetween(Instant.now().minus(1, ChronoUnit.MINUTES), Instant.now().plus(1, ChronoUnit.MINUTES));

        // sources 快照：回答当时引用的 chunk，供分析时精确复现（含 chunkId 可追溯到具体 chunk）
        List<Map<String, Object>> sources = JSON.readValue(row.getSources(), new TypeReference<>() {
        });
        assertThat(sources).hasSize(1);
        assertThat(sources.get(0))
                .containsEntry("book", "核心规则书 (CRB)")
                .containsEntry("tocPath", "法术 > 火球术")
                .containsEntry("chunkId", "spell_CRB_0001")
                .containsEntry("content", "火球术是 3 环法术");
    }

    /** 多次调用各落一行（id 唯一），不覆盖历史 */
    @Test
    void recordPersistsMultipleRowsWithoutOverwrite() {
        FeedbackResponse first = recorder.record(request());
        FeedbackResponse second = recorder.record(
                new FeedbackRequest("cid-2", "q2", "a2", List.of(), "答非所问", null, null));

        assertThat(first.id()).isNotEqualTo(second.id());
        assertThat(repository.count()).isEqualTo(2);
        assertThat(repository.findById(second.id()).orElseThrow().getConversationId()).isEqualTo("cid-2");
    }

    /** correction/comment 为空（仅类型标注）时仍正常落库；空 sources 存 [] 而非 NULL */
    @Test
    void recordPersistsWithoutOptionalFields() {
        FeedbackResponse response = recorder.record(
                new FeedbackRequest("cid-3", "q", "a", List.<ChatResponse.SourceRef>of(), "结构差", null, null));

        ErrorAnnotationEntity row = repository.findById(response.id()).orElseThrow();
        assertThat(row.getErrorType()).isEqualTo("结构差");
        assertThat(row.getCorrection()).isNull();
        assertThat(row.getComment()).isNull();
        assertThat(row.getSources().replace(" ", "")).isEqualTo("[]");
    }

    /** sources 为 null 时存 NULL（与旧 JSONL 口径一致），其余字段照常 */
    @Test
    void recordPersistsNullSourcesAsNull() {
        FeedbackResponse response = recorder.record(
                new FeedbackRequest("cid-4", "q", "a", null, "事实错误", null, null));

        assertThat(repository.findById(response.id()).orElseThrow().getSources()).isNull();
    }

    /** 每次调用返回唯一 id，两次不同且都能查到 */
    @Test
    void recordReturnsUniqueIdPerCall() {
        String id1 = recorder.record(request()).id();
        String id2 = recorder.record(request()).id();

        assertThat(id1).isNotEqualTo(id2);
        assertThat(repository.findById(id1)).isPresent();
        assertThat(repository.findById(id2)).isPresent();
    }

    /** 入参非法（errorType 超列宽 varchar(32)）→ 先拒不入库，reason=invalid_input（调用方回 400） */
    @Test
    void recordRejectsOverlongErrorTypeWithoutWriting() {
        FeedbackResponse response = recorder.record(
                new FeedbackRequest("cid", "q", "a", List.of(), "事实错误".repeat(20), null, null));

        assertThat(response.ok()).isFalse();
        assertThat(response.id()).isNull();
        assertThat(response.reason()).isEqualTo(FeedbackResponse.REASON_INVALID_INPUT);
        assertThat(repository.count()).isZero();
    }

    /** 入参非法（conversationId 超列宽 varchar(36)）同样先拒不入库 */
    @Test
    void recordRejectsOverlongConversationIdWithoutWriting() {
        FeedbackResponse response = recorder.record(
                new FeedbackRequest("c".repeat(37), "q", "a", List.of(), "事实错误", null, null));

        assertThat(response.reason()).isEqualTo(FeedbackResponse.REASON_INVALID_INPUT);
        assertThat(repository.count()).isZero();
    }

    /** 边界：恰好等于列宽上限的入参正常入库 */
    @Test
    void recordAcceptsFieldsAtColumnLimit() {
        FeedbackResponse response = recorder.record(new FeedbackRequest(
                "c".repeat(36), "q", "a", List.of(), "e".repeat(32), null, null));

        assertThat(response.ok()).isTrue();
        assertThat(repository.findById(response.id())).isPresent();
    }

    private static ObjectProvider<ErrorAnnotationService> providerOf(ErrorAnnotationService service) {
        @SuppressWarnings("unchecked")
        ObjectProvider<ErrorAnnotationService> provider = mock(ObjectProvider.class);
        when(provider.getIfAvailable()).thenReturn(service);
        return provider;
    }

    private FeedbackRequest request() {
        var src = new ChatResponse.SourceRef("核心规则书 (CRB)", "法术 > 火球术", "spell_CRB_0001", "火球术是 3 环法术");
        return new FeedbackRequest("cid-1", "火球术是几环？", "3 环", List.of(src),
                "事实错误", "射程写错了", "用户备注");
    }
}
