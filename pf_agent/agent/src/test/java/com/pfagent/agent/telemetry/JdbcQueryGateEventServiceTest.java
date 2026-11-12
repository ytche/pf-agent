package com.pfagent.agent.telemetry;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pfagent.agent.telemetry.QueryGateEventService.EventType;
import com.pfagent.agent.telemetry.QueryGateEventService.QueryGateEvent;
import com.pfagent.agent.telemetry.QueryGateEventService.Reason;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * JdbcQueryGateEventService 集成测试（F-026 设计 §8，@DataJpaTest + H2）
 *
 * 覆盖 JDBC 落库口径（query_gate_event）：
 *  - BLOCKED / ALLOWED 全字段，reason 落库值为 no_conditions / book_only
 *  - 每次护栏判定一行，offset/limit 保留在 query_json 中可区分翻页
 *  - 查询参数只存 JSON，不存回答正文/来源快照
 *  - 写库异常向调用方抛出（QueryGateEventRecorder 负责降级，主流程不受影响）
 *  - pf.chat.memory=memory 时不装配本服务（memory 模式无持久化通路）
 *
 * 关闭 Flyway（V6 是 PG 方言）：由 Hibernate 按实体注解 create-drop 建表。
 * JdbcQueryGateEventService 是 @Component，slice 测试不自动装配，
 * 此处手动 new + 反射注入真仓库与事务模板（同 DataGapService/FeedbackRecorderTest 口径）。
 */
@DataJpaTest(properties = {"spring.flyway.enabled=false", "spring.jpa.hibernate.ddl-auto=create-drop"})
class JdbcQueryGateEventServiceTest {

    private static final ObjectMapper JSON = new ObjectMapper();

    @Autowired
    private QueryGateEventRepository repository;
    @Autowired
    private PlatformTransactionManager transactionManager;

    private JdbcQueryGateEventService service;

    @BeforeEach
    void setUp() {
        service = newService(repository, transactionManager);
    }

    /** BLOCKED：全字段落库，query_json 保留业务条件与分页参数 */
    @Test
    void blockedPersistsAllFields() throws Exception {
        Instant at = Instant.parse("2026-11-11T08:00:00Z");
        String queryJson = "{\"filters\":{\"book\":\"CRB\"},\"offset\":0,\"limit\":50,\"sort\":\"name\"}";

        service.persist(new QueryGateEvent("cid-blocked", "CRB 里所有类型的规则条目", "searchByMetadata",
                "all", EventType.BLOCKED, Reason.BOOK_ONLY, queryJson, at));

        List<QueryGateEventEntity> rows = repository.findAll();
        assertThat(rows).singleElement().satisfies(row -> {
            assertThat(row.getId()).isNotNull();
            assertThat(row.getConversationId()).isEqualTo("cid-blocked");
            assertThat(row.getQuestion()).isEqualTo("CRB 里所有类型的规则条目");
            assertThat(row.getToolName()).isEqualTo("searchByMetadata");
            assertThat(row.getModule()).isEqualTo("all");
            assertThat(row.getEventType()).isEqualTo("BLOCKED");
            assertThat(row.getReason()).isEqualTo("book_only");
            assertThat(row.getCreatedAt()).isBetween(at.minus(1, ChronoUnit.SECONDS), at.plus(1, ChronoUnit.SECONDS));
            JsonNode json = JSON.readTree(row.getQueryJson());
            assertThat(json.get("filters").get("book").asText()).isEqualTo("CRB");
            assertThat(json.get("offset").asInt()).isZero();
            assertThat(json.get("limit").asInt()).isEqualTo(50);
            assertThat(json.get("sort").asText()).isEqualTo("name");
        });
    }

    /** ALLOWED：事件类型与 no_conditions 落库值正确，模块/工具按调用方口径保存 */
    @Test
    void allowedPersistsEventTypeAndReason() {
        service.persist(new QueryGateEvent("cid-allowed", "CRB 所有专长，完整列出", "listEntries",
                "feat", EventType.ALLOWED, Reason.NO_CONDITIONS, "{\"offset\":0,\"limit\":50}", Instant.now()));

        QueryGateEventEntity row = repository.findAll().get(0);
        assertThat(row.getEventType()).isEqualTo("ALLOWED");
        assertThat(row.getReason()).isEqualTo("no_conditions");
        assertThat(row.getToolName()).isEqualTo("listEntries");
        assertThat(row.getModule()).isEqualTo("feat");
        assertThat(row.getConversationId()).isEqualTo("cid-allowed");
    }

    /** 每次护栏判定一行：同一逻辑查询的翻页各落一行，query_json 的 offset/limit 可区分 */
    @Test
    void everyPagingDecisionPersistsItsOwnRow() throws Exception {
        service.persist(new QueryGateEvent("cid-page", "继续", "searchByMetadata", "feat",
                EventType.ALLOWED, Reason.NO_CONDITIONS, "{\"offset\":0,\"limit\":50}", Instant.now()));
        service.persist(new QueryGateEvent("cid-page", "继续", "searchByMetadata", "feat",
                EventType.ALLOWED, Reason.NO_CONDITIONS, "{\"offset\":50,\"limit\":50}", Instant.now()));

        List<QueryGateEventEntity> rows = repository.findAll();
        assertThat(rows).hasSize(2);
        assertThat(JSON.readTree(rows.get(0).getQueryJson()).get("offset").asInt()).isZero();
        assertThat(JSON.readTree(rows.get(1).getQueryJson()).get("offset").asInt()).isEqualTo(50);
        assertThat(rows).extracting(QueryGateEventEntity::getEventType).containsOnly("ALLOWED");
    }

    /** 只保存查询参数 JSON：表中不存在回答正文/来源快照列，事件快照不被误存 */
    @Test
    void eventStoresOnlyQueryJsonNotAnswerSnapshot() throws Exception {
        service.persist(new QueryGateEvent("cid-min", "问题", "searchByMetadata", "all",
                EventType.BLOCKED, Reason.NO_CONDITIONS, "{}", Instant.now()));

        QueryGateEventEntity row = repository.findAll().get(0);
        assertThat(JSON.readTree(row.getQueryJson()).isObject()).isTrue();
        assertThat(row.getQuestion()).isEqualTo("问题");
        assertThat(row.getQueryJson()).doesNotContain("sources").doesNotContain("answer");
    }

    /** 写库异常向调用方抛出（契约：由 QueryGateEventRecorder 捕获降级，不在服务内吞掉） */
    @Test
    void persistPropagatesWriteFailure() {
        QueryGateEventRepository broken = mock(QueryGateEventRepository.class);
        when(broken.save(any(QueryGateEventEntity.class))).thenThrow(new IllegalStateException("db down"));
        JdbcQueryGateEventService brokenService = newService(broken, transactionManager);

        assertThatThrownBy(() -> brokenService.persist(new QueryGateEvent("cid", "q", "listEntries", "all",
                EventType.BLOCKED, Reason.BOOK_ONLY, "{}", Instant.now())))
                .isInstanceOf(RuntimeException.class);
    }

    /** memory 模式（pf.chat.memory=memory）不装配持久化服务：没有写库通路 */
    @Test
    void notAssembledInMemoryMode() {
        runner().withPropertyValues("pf.chat.memory=memory").run(context ->
                assertThat(context).doesNotHaveBean(JdbcQueryGateEventService.class));
    }

    /** jdbc 模式装配本服务（Repository 与事务管理器由容器提供） */
    @Test
    void assembledInJdbcMode() {
        runner().withPropertyValues("pf.chat.memory=jdbc").run(context ->
                assertThat(context).hasSingleBean(JdbcQueryGateEventService.class));
    }

    private ApplicationContextRunner runner() {
        return new ApplicationContextRunner()
                .withUserConfiguration(JdbcQueryGateEventService.class)
                .withBean(QueryGateEventRepository.class, () -> mock(QueryGateEventRepository.class))
                .withBean(PlatformTransactionManager.class, () -> mock(PlatformTransactionManager.class));
    }

    private static JdbcQueryGateEventService newService(QueryGateEventRepository repository,
                                                        PlatformTransactionManager transactionManager) {
        JdbcQueryGateEventService candidate = new JdbcQueryGateEventService();
        ReflectionTestUtils.setField(candidate, "repository", repository);
        ReflectionTestUtils.setField(candidate, "transactionManager", transactionManager);
        ReflectionTestUtils.setField(candidate, "transactionTemplate", new TransactionTemplate(transactionManager));
        return candidate;
    }
}
