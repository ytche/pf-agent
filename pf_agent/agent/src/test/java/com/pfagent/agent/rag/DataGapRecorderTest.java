package com.pfagent.agent.rag;

import com.pfagent.agent.telemetry.DataGapRepository;
import com.pfagent.agent.telemetry.DataGapService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * DataGapRecorder 集成测试（F-021：缺口入库，@DataJpaTest + H2）
 *
 * 覆盖数据缺口写 data_gap 表（替代原 data_gaps.jsonl 落盘）：
 *  - record 落一行，含 question/attemptedFilters/reason/createdAt 全部字段
 *  - dedup_key 幂等：同（秒精度时间戳 + 内容）不重复插行
 *  - listGaps 最新在前 + limit 截断 + keyword 对 question/reason 子串匹配
 *  - limit ≤ 0 / 空库 → 空列表
 *
 * 关闭 Flyway（V4 是 PG 方言）：由 Hibernate 按实体注解 create-drop 建表。
 * DataGapRecorder/DataGapService 是 @Component，slice 测试不自动装配，
 * 此处手动 new + 反射注入真仓库与事务模板（同 JdbcChatMemoryTest 口径）。
 */
@DataJpaTest(properties = {"spring.flyway.enabled=false", "spring.jpa.hibernate.ddl-auto=create-drop"})
class DataGapRecorderTest {

    @Autowired
    private DataGapRepository repository;
    @Autowired
    private PlatformTransactionManager transactionManager;

    private DataGapService service;
    private DataGapRecorder recorder;

    @BeforeEach
    void setUp() {
        service = new DataGapService();
        ReflectionTestUtils.setField(service, "repository", repository);
        ReflectionTestUtils.setField(service, "transactionTemplate", new TransactionTemplate(transactionManager));

        recorder = new DataGapRecorder();
        ReflectionTestUtils.setField(recorder, "gapServiceProvider", providerOf(service));
    }

    /** 落库一行，含 question/attemptedFilters/reason/createdAt 全部字段 */
    @Test
    void recordPersistsRowWithAllFields() {
        boolean persisted = recorder.record("女巫的XX变体规则", "{className:女巫}", "查不到该变体");

        assertThat(persisted).isTrue();
        assertThat(repository.findAll()).singleElement().satisfies(row -> {
            assertThat(row.getQuestion()).isEqualTo("女巫的XX变体规则");
            assertThat(row.getAttemptedFilters()).isEqualTo("{className:女巫}");
            assertThat(row.getReason()).isEqualTo("查不到该变体");
            assertThat(row.getCreatedAt()).isNotNull();
            assertThat(row.getDedupKey()).hasSize(64);
        });
    }

    /** 每次调用各落一行（不同内容） */
    @Test
    void recordPersistsMultipleRowsWithoutOverwrite() {
        assertThat(recorder.record("q1", "f1", "r1")).isTrue();
        assertThat(recorder.record("q2", "f2", "r2")).isTrue();

        assertThat(repository.count()).isEqualTo(2);
    }

    /** dedup_key 幂等：同（秒精度时间戳 + 内容）重复写入不新增行，第二次返回 false */
    @Test
    void persistSameContentAndSecondIsIdempotent() {
        Instant at = LocalDateTime.parse("2026-08-01T01:17:41").atZone(ZoneId.systemDefault()).toInstant();

        assertThat(service.persist("q", "f", "r", at)).isTrue();
        assertThat(service.persist("q", "f", "r", at)).isFalse();

        assertThat(repository.count()).isEqualTo(1);
    }

    /** 内容相同但时间戳不同 → 两条独立缺口（不误判为重复） */
    @Test
    void persistSameContentDifferentSecondCreatesSeparateRows() {
        service.persist("q", "f", "r", LocalDateTime.parse("2026-08-01T01:00:00")
                .atZone(ZoneId.systemDefault()).toInstant());
        service.persist("q", "f", "r", LocalDateTime.parse("2026-08-01T01:00:01")
                .atZone(ZoneId.systemDefault()).toInstant());

        assertThat(repository.count()).isEqualTo(2);
    }

    // ---------- SP8a J3：listGaps 只读读取 ----------

    /** 读取最新在前，limit 截断；时间戳按秒精度 ISO 输出（口径同旧 JSONL） */
    @Test
    void listGapsReturnsLatestFirstWithLimit() {
        persist("q1", "f1", "r1", "2026-08-01T10:00:01");
        persist("q2", "f2", "r2", "2026-08-01T10:00:02");
        persist("q3", "f3", "r3", "2026-08-01T10:00:03");

        DataGapRecorder.GapQueryResult result = recorder.listGaps(2, null);
        List<DataGapRecorder.GapEntry> gaps = result.gaps();

        assertThat(result.available()).isTrue();
        assertThat(gaps).hasSize(2);
        assertThat(gaps.get(0).question()).isEqualTo("q3"); // 最新在前
        assertThat(gaps.get(1).question()).isEqualTo("q2");
        assertThat(gaps.get(0).timestamp()).isEqualTo("2026-08-01T10:00:03");
        assertThat(gaps.get(0).reason()).isEqualTo("r3");
    }

    /** keyword 对 question/reason 子串匹配 */
    @Test
    void listGapsKeywordFiltersQuestionAndReason() {
        persist("女巫的XX规则", "f1", "查不到", "2026-08-01T10:00:01");
        persist("牧师问题", "f2", "缺少女巫变体数据", "2026-08-01T10:00:02");

        List<DataGapRecorder.GapEntry> gaps = recorder.listGaps(10, "女巫").gaps();

        assertThat(gaps).hasSize(2); // question 命中 + reason 命中
    }

    /** keyword 不命中的记录被排除，命中记录保持最新在前 */
    @Test
    void listGapsKeywordExcludesNonMatchingRecords() {
        persist("匹配问题一", "f1", "查不到女巫规则", "2026-08-01T10:00:01");
        persist("无关问题", "f2", "无关原因", "2026-08-01T10:00:02");
        persist("无关问题二", "f3", "命中原因 女巫变体", "2026-08-01T10:00:03");

        List<DataGapRecorder.GapEntry> gaps = recorder.listGaps(10, "女巫").gaps();

        assertThat(gaps).hasSize(2);
        assertThat(gaps.get(0).reason()).isEqualTo("命中原因 女巫变体"); // 最新命中在前
        assertThat(gaps.get(1).question()).isEqualTo("匹配问题一");
    }

    /** 空库：库可用（available=true）但无记录——与「库不可用」严格区分 */
    @Test
    void listGapsEmptyDatabaseIsAvailableButEmpty() {
        DataGapRecorder.GapQueryResult result = recorder.listGaps(20, null);

        assertThat(result.available()).isTrue();
        assertThat(result.gaps()).isEmpty();
    }

    /** 库不可用（读取异常）：available=false，不得与「无记录」混同 */
    @Test
    void listGapsDatabaseFailureReportsUnavailable() {
        DataGapRepository brokenRepository = mock(DataGapRepository.class);
        when(brokenRepository.findByOrderByCreatedAtDescIdDesc(any())).thenThrow(new RuntimeException("db down"));
        DataGapService brokenService = new DataGapService();
        ReflectionTestUtils.setField(brokenService, "repository", brokenRepository);
        ReflectionTestUtils.setField(brokenService, "transactionTemplate", new TransactionTemplate(transactionManager));
        DataGapRecorder brokenRecorder = new DataGapRecorder();
        ReflectionTestUtils.setField(brokenRecorder, "gapServiceProvider", providerOf(brokenService));

        DataGapRecorder.GapQueryResult result = brokenRecorder.listGaps(20, null);

        assertThat(result.available()).isFalse();
        assertThat(result.gaps()).isEmpty();
    }

    /** limit 为 0 或负数时直接返回空列表（读取侧防御） */
    @Test
    void listGapsNonPositiveLimitReturnsEmpty() {
        persist("q1", "f1", "r1", "2026-08-01T10:00:01");

        assertThat(recorder.listGaps(0, null).gaps()).isEmpty();
        assertThat(recorder.listGaps(-5, null).gaps()).isEmpty();
    }

    /** 用固定秒精度时间戳写一条（去重键以此为准，保证用例可重复） */
    private void persist(String question, String filters, String reason, String timestamp) {
        service.persist(question, filters, reason,
                LocalDateTime.parse(timestamp).atZone(ZoneId.systemDefault()).toInstant());
    }

    private static ObjectProvider<DataGapService> providerOf(DataGapService service) {
        @SuppressWarnings("unchecked")
        ObjectProvider<DataGapService> provider = mock(ObjectProvider.class);
        when(provider.getIfAvailable()).thenReturn(service);
        return provider;
    }
}
