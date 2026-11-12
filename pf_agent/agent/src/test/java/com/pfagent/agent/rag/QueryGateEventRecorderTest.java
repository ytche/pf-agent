package com.pfagent.agent.rag;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pfagent.agent.telemetry.QueryGateEventService;
import com.pfagent.agent.telemetry.QueryGateEventService.EventType;
import com.pfagent.agent.telemetry.QueryGateEventService.QueryGateEvent;
import com.pfagent.agent.telemetry.QueryGateEventService.Reason;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * QueryGateEventRecorder 契约测试（F-026 设计 §8）
 *
 * 覆盖：BLOCKED/ALLOWED 字段完整（会话/问题取 ToolCallTracker 上下文）、reason 口径、
 * query JSON 序列化（含 offset/limit 区分翻页）、每次判定一行、无请求上下文跳过、
 * 服务未装配或写库/序列化异常只降级不抛出。持久化实现由 telemetry lane 提供，
 * 此处用内存实现验证契约，不依赖数据库。
 */
class QueryGateEventRecorderTest {

    private static final ObjectMapper JSON = new ObjectMapper();

    private ToolCallTracker tracker;
    private RecordingService service;
    private QueryGateEventRecorder recorder;

    @BeforeEach
    void setUp() {
        tracker = new ToolCallTracker();
        service = new RecordingService();
        recorder = recorderWith(service);
    }

    /** BLOCKED：字段完整，问题/会话来自请求上下文，query JSON 保留业务条件 */
    @Test
    void blockedRecordsEventWithRequestContextAndQueryJson() throws Exception {
        tracker.begin("cid-blocked", "CRB 里所有类型的规则条目");

        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("book", "CRB"));
        query.setOffset(0);
        query.setLimit(50);

        boolean recorded = recorder.recordBlocked("searchByMetadata", "all", Reason.BOOK_ONLY, query);

        assertThat(recorded).isTrue();
        assertThat(service.events).singleElement().satisfies(event -> {
            assertThat(event.conversationId()).isEqualTo("cid-blocked");
            assertThat(event.question()).isEqualTo("CRB 里所有类型的规则条目");
            assertThat(event.toolName()).isEqualTo("searchByMetadata");
            assertThat(event.module()).isEqualTo("all");
            assertThat(event.eventType()).isEqualTo(EventType.BLOCKED);
            assertThat(event.reason()).isEqualTo(Reason.BOOK_ONLY);
            assertThat(event.createdAt()).isNotNull();
            JsonNode json = readTree(event.queryJson());
            assertThat(json.get("filters").get("book").asText()).isEqualTo("CRB");
            assertThat(json.get("offset").asInt()).isZero();
            assertThat(json.get("limit").asInt()).isEqualTo(50);
        });
    }

    /** ALLOWED：放行事件与 reason 口径正确，record 也是 JSON 对象 */
    @Test
    void allowedRecordsEventWithEventTypeAndReason() throws Exception {
        tracker.begin("cid-allowed", "CRB 所有专长，完整列出");

        ListEntriesQuery query = new ListEntriesQuery(
                null, Map.of("book", "CRB"), null, 50, 0, "name");

        assertThat(recorder.recordAllowed("listEntries", "feat", Reason.BOOK_ONLY, query)).isTrue();

        assertThat(service.events).singleElement().satisfies(event -> {
            assertThat(event.eventType()).isEqualTo(EventType.ALLOWED);
            assertThat(event.reason()).isEqualTo(Reason.BOOK_ONLY);
            assertThat(event.toolName()).isEqualTo("listEntries");
            assertThat(event.module()).isEqualTo("feat");
            assertThat(event.queryJson()).startsWith("{");
        });
    }

    /** 每次护栏判定各记一行：offset 不同的同条件翻页可由 query JSON 区分 */
    @Test
    void everyGuardDecisionRecordsOneRowAndOffsetDistinguishesPages() throws Exception {
        tracker.begin("cid-page", "继续");

        MetadataSearchQuery first = new MetadataSearchQuery();
        first.setOffset(0);
        first.setLimit(50);
        MetadataSearchQuery second = new MetadataSearchQuery();
        second.setOffset(50);
        second.setLimit(50);

        recorder.recordAllowed("searchByMetadata", "feat", Reason.NO_CONDITIONS, first);
        recorder.recordAllowed("searchByMetadata", "feat", Reason.NO_CONDITIONS, second);

        assertThat(service.events).hasSize(2);
        assertThat(readTree(service.events.get(0).queryJson()).get("offset").asInt()).isZero();
        assertThat(readTree(service.events.get(1).queryJson()).get("offset").asInt()).isEqualTo(50);
        assertThat(service.events).extracting(QueryGateEvent::eventType)
                .containsOnly(EventType.ALLOWED);
    }

    /** 未 begin（单测直调/管理直调）：跳过且不写空会话事件，主流程不抛 */
    @Test
    void recordWithoutRequestContextIsSkipped() {
        assertThatCode(() -> assertThat(
                recorder.recordBlocked("searchByMetadata", "all", Reason.NO_CONDITIONS, Map.of()))
                .isFalse())
                .doesNotThrowAnyException();

        assertThat(service.events).isEmpty();
    }

    /** drain 之后请求上下文已清空：同样跳过，不残留上一请求的会话/问题 */
    @Test
    void recordAfterDrainIsSkipped() {
        tracker.begin("cid-drained", "旧问题");
        tracker.drain();

        assertThat(recorder.recordAllowed("listEntries", "feat", Reason.NO_CONDITIONS, Map.of())).isFalse();
        assertThat(service.events).isEmpty();
    }

    /** memory 模式：持久化服务未装配，只降级不阻断 */
    @Test
    void missingServiceDoesNotThrowNorBlock() {
        QueryGateEventRecorder memoryRecorder = recorderWith(null);
        tracker.begin("cid-memory", "问题");

        assertThat(memoryRecorder.recordBlocked("searchByMetadata", "all", Reason.BOOK_ONLY, Map.of()))
                .isFalse();
        assertThat(service.events).isEmpty();
    }

    /** 写库异常：只降级，不改变工具结果 */
    @Test
    void persistFailureDoesNotPropagate() {
        QueryGateEventRecorder brokenRecorder = recorderWith(new RecordingService() {
            @Override
            public void persist(QueryGateEvent event) {
                throw new IllegalStateException("db down");
            }
        });
        tracker.begin("cid-broken", "问题");

        assertThatCode(() -> assertThat(
                brokenRecorder.recordBlocked("searchByMetadata", "all", Reason.BOOK_ONLY, Map.of()))
                .isFalse())
                .doesNotThrowAnyException();
    }

    /** 序列化失败：跳过事件、不写半条记录、不抛出 */
    @Test
    void serializationFailureIsSkipped() {
        tracker.begin("cid-bad-json", "问题");

        assertThatCode(() -> assertThat(
                recorder.recordBlocked("searchByMetadata", "all", Reason.NO_CONDITIONS, new ExplodingQuery()))
                .isFalse())
                .doesNotThrowAnyException();
        assertThat(service.events).isEmpty();
    }

    /** 关键字段缺失（编程错误）也不阻断主流程 */
    @Test
    void missingRequiredFieldIsSkipped() {
        tracker.begin("cid-missing", "问题");

        assertThat(recorder.record(null, "all", EventType.BLOCKED, Reason.BOOK_ONLY, Map.of())).isFalse();
        assertThat(recorder.record("searchByMetadata", "all", null, Reason.BOOK_ONLY, Map.of())).isFalse();
        assertThat(recorder.record("searchByMetadata", "all", EventType.BLOCKED, null, Map.of())).isFalse();
        assertThat(service.events).isEmpty();
    }

    /** Jackson 可正常序列化的复杂查询对象（null 字段忽略与否不作契约） */
    @Test
    void nullQueryStillProducesJson() {
        tracker.begin("cid-null-query", "问题");

        assertThat(recorder.recordAllowed("listEntries", "feat", Reason.NO_CONDITIONS, null)).isTrue();
        assertThat(service.events).singleElement()
                .extracting(QueryGateEvent::queryJson)
                .isEqualTo("null");
    }

    private QueryGateEventRecorder recorderWith(QueryGateEventService target) {
        QueryGateEventRecorder candidate = new QueryGateEventRecorder();
        ReflectionTestUtils.setField(candidate, "toolCallTracker", tracker);
        ReflectionTestUtils.setField(candidate, "serviceProvider", providerOf(target));
        return candidate;
    }

    private static JsonNode readTree(String json) throws Exception {
        return JSON.readTree(json);
    }

    private static ObjectProvider<QueryGateEventService> providerOf(QueryGateEventService service) {
        @SuppressWarnings("unchecked")
        ObjectProvider<QueryGateEventService> provider = mock(ObjectProvider.class);
        when(provider.getIfAvailable()).thenReturn(service);
        return provider;
    }

    /** 内存实现：记录事件，供断言；可被子类覆写为抛异常 */
    private static class RecordingService implements QueryGateEventService {

        final List<QueryGateEvent> events = new ArrayList<>();

        @Override
        public void persist(QueryGateEvent event) {
            events.add(event);
        }
    }

    /** 序列化即失败的查询对象（getter 抛异常） */
    @SuppressWarnings("unused")
    private static class ExplodingQuery {

        public String getBroken() {
            throw new IllegalStateException("boom");
        }
    }
}
