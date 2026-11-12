package com.pfagent.agent.telemetry;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * TelemetryImporter 集成测试（F-021 历史 JSONL → 库迁移，@DataJpaTest + H2）
 *
 * 覆盖一次性迁移的关键不变量：
 *  - annotations.jsonl：带 id 的行按 id 导入；无 id 的老行按内容合成稳定 id
 *  - data_gaps.jsonl：question/timestamp 齐备的行导入，缺失行跳过
 *  - 坏行（非法 JSON）跳过不中断，其余行照常导入
 *  - **幂等**：重复执行不产生重复行（第二次导入行数不变）
 *  - 文件不存在时不报错、不导入
 */
@DataJpaTest(properties = {"spring.flyway.enabled=false", "spring.jpa.hibernate.ddl-auto=create-drop"})
class TelemetryImporterTest {

    @Autowired
    private ErrorAnnotationRepository annotationRepository;
    @Autowired
    private DataGapRepository gapRepository;
    @Autowired
    private PlatformTransactionManager transactionManager;

    @TempDir
    Path tempDir;

    private TelemetryImporter importer;
    private Path annotationsFile;
    private Path gapsFile;

    @BeforeEach
    void setUp() {
        ErrorAnnotationService annotationService = new ErrorAnnotationService();
        ReflectionTestUtils.setField(annotationService, "repository", annotationRepository);
        ReflectionTestUtils.setField(annotationService, "transactionTemplate", new TransactionTemplate(transactionManager));

        DataGapService gapService = new DataGapService();
        ReflectionTestUtils.setField(gapService, "repository", gapRepository);
        ReflectionTestUtils.setField(gapService, "transactionTemplate", new TransactionTemplate(transactionManager));

        annotationsFile = tempDir.resolve("annotations.jsonl");
        gapsFile = tempDir.resolve("data_gaps.jsonl");

        importer = new TelemetryImporter();
        ReflectionTestUtils.setField(importer, "feedbackFilePath", annotationsFile.toString());
        ReflectionTestUtils.setField(importer, "gapsFilePath", gapsFile.toString());
        ReflectionTestUtils.setField(importer, "annotationServiceProvider", providerOf(annotationService));
        ReflectionTestUtils.setField(importer, "gapServiceProvider", providerOf(gapService));
    }

    /** 导入两份历史文件：合法行全部入库（含缺字段行补默认值），只有无法解析的 JSON 才算坏行 */
    @Test
    void importsLegacyFiles() throws Exception {
        writeAnnotationsFile();
        writeGapsFile();

        importer.run(null);

        // 2 条带 id/无 id 的完整行 + 1 条缺 timestamp 的行（合成 epoch，不丢行）
        assertThat(annotationRepository.count()).isEqualTo(3);
        assertThat(annotationRepository.findById("ann-legacy-1")).isPresent()
                .get()
                .satisfies(row -> {
                    assertThat(row.getQuestion()).isEqualTo("q1");
                    assertThat(row.getErrorType()).isEqualTo("事实错误");
                    assertThat(row.getSources()).contains("spell_CRB_0001");
                });
        // 无 id 的老行合成稳定 id（ann-import- 前缀）
        assertThat(annotationRepository.findAll())
                .anyMatch(row -> row.getId().startsWith("ann-import-") && "q2".equals(row.getQuestion()));

        // g1/g2 + 缺 question 的行（补空串保留，不丢行）
        assertThat(gapRepository.count()).isEqualTo(3);
        assertThat(gapRepository.findAll())
                .anyMatch(row -> "g1".equals(row.getQuestion()) && "f1".equals(row.getAttemptedFilters()));
        assertThat(gapRepository.findAll())
                .anyMatch(row -> "".equals(row.getQuestion()) && "缺 question".equals(row.getReason()));
    }

    /** 缺/坏 timestamp 不丢行：按 epoch 落库（旧报告脚本对这些行是照常纳入的） */
    @Test
    void missingTimestampIsImportedWithEpochInsteadOfDropped() throws Exception {
        Files.writeString(annotationsFile, """
                {"id":"ann-no-ts","conversationId":"cid-x","question":"无时间戳行","errorType":"事实错误"}
                {"id":"ann-bad-ts","question":"坏时间戳行","timestamp":"not-a-timestamp"}
                """, StandardCharsets.UTF_8);
        Files.writeString(gapsFile, """
                {"question":"缺口无时间戳","reason":"r"}
                """, StandardCharsets.UTF_8);

        importer.run(null);

        assertThat(annotationRepository.count()).isEqualTo(2);
        assertThat(annotationRepository.findById("ann-no-ts").orElseThrow().getCreatedAt())
                .isEqualTo(Instant.EPOCH);
        assertThat(annotationRepository.findById("ann-bad-ts").orElseThrow().getCreatedAt())
                .isEqualTo(Instant.EPOCH);
        assertThat(gapRepository.findAll()).singleElement()
                .satisfies(row -> assertThat(row.getCreatedAt()).isEqualTo(Instant.EPOCH));
    }

    /** 无 id 行合成键纳入 errorType/comment：同问同答同秒、仅这些字段不同的两行不被合并 */
    @Test
    void synthIdDistinguishesRowsDifferingOnlyByErrorTypeOrComment() throws Exception {
        Files.writeString(annotationsFile, """
                {"conversationId":"c","question":"同问","answer":"同答","errorType":"事实错误","comment":null,"timestamp":"2026-09-17T01:16:13"}
                {"conversationId":"c","question":"同问","answer":"同答","errorType":"结构差","comment":null,"timestamp":"2026-09-17T01:16:13"}
                {"conversationId":"c","question":"同问","answer":"同答","errorType":"事实错误","comment":"备注不同","timestamp":"2026-09-17T01:16:13"}
                """, StandardCharsets.UTF_8);
        Files.writeString(gapsFile, "", StandardCharsets.UTF_8);

        importer.run(null);

        assertThat(annotationRepository.count()).isEqualTo(3);
        assertThat(annotationRepository.findAll())
                .extracting(ErrorAnnotationEntity::getId)
                .doesNotHaveDuplicates();
    }

    /** 幂等：重复执行不产生重复行，合成 id 也保持稳定 */
    @Test
    void repeatedRunDoesNotDuplicateRows() throws Exception {
        writeAnnotationsFile();
        writeGapsFile();

        importer.run(null);
        List<ErrorAnnotationEntity> firstPass = annotationRepository.findAll();
        importer.run(null);

        assertThat(annotationRepository.count()).isEqualTo(3);
        assertThat(gapRepository.count()).isEqualTo(3);
        assertThat(annotationRepository.findAll())
                .extracting(ErrorAnnotationEntity::getId)
                .containsExactlyInAnyOrderElementsOf(firstPass.stream().map(ErrorAnnotationEntity::getId).toList());
    }

    /** 历史文件不存在：不报错、不导入 */
    @Test
    void missingFilesAreSkipped() {
        importer.run(null);

        assertThat(annotationRepository.count()).isZero();
        assertThat(gapRepository.count()).isZero();
    }

    /** 带 id 但内容不同的行按 id 去重（同 id 只保留首条） */
    @Test
    void duplicateIdKeepsSingleRow() throws Exception {
        Files.writeString(annotationsFile, """
                {"id":"ann-dup","question":"q1","timestamp":"2026-09-17T01:16:13"}
                {"id":"ann-dup","question":"q2","timestamp":"2026-09-17T02:00:00"}
                """, StandardCharsets.UTF_8);
        Files.writeString(gapsFile, "", StandardCharsets.UTF_8);

        importer.run(null);

        assertThat(annotationRepository.count()).isEqualTo(1);
        assertThat(annotationRepository.findById("ann-dup").orElseThrow().getQuestion()).isEqualTo("q1");
    }

    private void writeAnnotationsFile() throws Exception {
        Files.writeString(annotationsFile, """
                {"id":"ann-legacy-1","conversationId":"cid-1","question":"q1","answer":"a1","sources":[{"book":"核心规则书 (CRB)","tocPath":"法术 > 火球术","chunkId":"spell_CRB_0001","content":"火球术是 3 环法术"}],"errorType":"事实错误","correction":null,"comment":"备注","resolution":"待分析","timestamp":"2026-09-17T01:16:13"}
                {"conversationId":"cid-2","question":"q2","answer":"a2","sources":null,"errorType":"结构差","correction":null,"comment":null,"resolution":"待分析","timestamp":"2026-09-17T02:00:00"}
                {"conversationId":"cid-3","question":"q3","answer":"a3","sources":null,"errorType":"答非所问","correction":null,"comment":null,"resolution":"待分析"}
                {bad json
                """, StandardCharsets.UTF_8);
    }

    private void writeGapsFile() throws Exception {
        Files.writeString(gapsFile, """
                {"question":"g1","attemptedFilters":"f1","reason":"r1","timestamp":"2026-08-01T01:17:41"}
                {"question":"g2","attemptedFilters":null,"reason":"r2","timestamp":"2026-08-01T02:00:00"}
                {"reason":"缺 question","timestamp":"2026-08-01T03:00:00"}
                """, StandardCharsets.UTF_8);
    }

    private static <T> ObjectProvider<T> providerOf(T service) {
        @SuppressWarnings("unchecked")
        ObjectProvider<T> provider = mock(ObjectProvider.class);
        when(provider.getIfAvailable()).thenReturn(service);
        return provider;
    }
}
