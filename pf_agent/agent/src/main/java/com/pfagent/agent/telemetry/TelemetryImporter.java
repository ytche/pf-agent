package com.pfagent.agent.telemetry;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;

/**
 * F-021 历史 JSONL 一次性迁移导入（annotations.jsonl / data_gaps.jsonl → PostgreSQL）
 *
 * 落盘改入库后，既有数据需要搬进库。启动时按开关执行一次：
 * <pre>PF_TELEMETRY_IMPORT_ENABLED=true mvn spring-boot:run</pre>
 * 或 {@code -Dpf.telemetry.import.enabled=true}（默认不设即不执行的通用一次性开关口径，
 * 仅本导入自身使用，与其他历史一次性开关无任何耦合）。
 *
 * <b>幂等</b>：annotations 以记录 id 为主键（无 id 的老行按内容 SHA-256 合成稳定 id），
 * data_gap 以「秒精度时间戳 + 内容」的 dedup_key 去重——重复执行只跳过、不产生重复行。
 *
 * <b>不丢行</b>（搬迁不可逆，口径损失必须显式）：只有「JSON 本身无法解析」的行才算坏行；
 * 时间戳缺失/不可解析的行按 {@link Instant#EPOCH} 入库并在日志里报出「合成时间戳 N 条」
 * （迁移前这些行在旧报告脚本里是照常纳入的）；data_gap 缺 question 时补空串
 * （列 NOT NULL）同样计数上报。合成 id 把 question/answer/errorType/correction/comment/
 * sources 全部纳入哈希，避免「同问同答同秒、仅错误类型或备注不同」的老行被静默合并。
 *
 * 只在显式打开开关时装配；库未装配（pf.chat.memory=memory）时记 warn 跳过——
 * memory 模式没有库可导。
 */
@Component
@ConditionalOnProperty(name = "pf.telemetry.import.enabled", havingValue = "true")
public class TelemetryImporter implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(TelemetryImporter.class);

    /** 旧 JSONL 时间戳为秒精度本地时间（FeedbackRecorder/DataGapRecorder 的写入口径） */
    private static final DateTimeFormatter TIMESTAMP = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");

    @Value("${pf.feedback.file-path}")
    private String feedbackFilePath;
    @Value("${pf.gaps.file-path}")
    private String gapsFilePath;

    @Autowired
    private ObjectProvider<ErrorAnnotationService> annotationServiceProvider;
    @Autowired
    private ObjectProvider<DataGapService> gapServiceProvider;

    private final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * 单类迁移统计：导入（新插入）/ 已存在跳过 / 合成时间戳（缺或坏 timestamp 按 epoch）/
     * 缺 question 补空（仅 data_gap）/ 坏行（JSON 无法解析或入库失败）。
     */
    private record ImportStat(int imported, int skipped, int synthTime, int synthQuestion, int failed) {

        ImportStat plus(ImportStat other) {
            return new ImportStat(
                    imported + other.imported,
                    skipped + other.skipped,
                    synthTime + other.synthTime,
                    synthQuestion + other.synthQuestion,
                    failed + other.failed);
        }
    }

    @Override
    public void run(ApplicationArguments args) {
        ErrorAnnotationService annotationService = annotationServiceProvider.getIfAvailable();
        DataGapService gapService = gapServiceProvider.getIfAvailable();
        if (annotationService == null || gapService == null) {
            log.warn("[Telemetry] 数据库未装配（pf.chat.memory != jdbc），跳过历史遥测迁移");
            return;
        }
        try {
            importAnnotations(Path.of(feedbackFilePath), annotationService);
            importGaps(Path.of(gapsFilePath), gapService);
        } catch (Exception e) {
            // 一次性迁移失败不阻断启动：记录错误供人工重跑（幂等，重跑安全）
            log.error("[Telemetry] 历史遥测迁移失败（可修复后重跑，幂等）", e);
        }
    }

    private void importAnnotations(Path path, ErrorAnnotationService annotationService) {
        List<String> lines = readLines(path, "annotations");
        if (lines == null) {
            return;
        }
        ImportStat stat = new ImportStat(0, 0, 0, 0, 0);
        for (String line : lines) {
            Map<?, ?> row;
            try {
                row = objectMapper.readValue(line, Map.class);
            } catch (Exception e) {
                log.warn("[Telemetry] annotations 坏行（JSON 无法解析）跳过: {}", abbreviate(line));
                stat = stat.plus(new ImportStat(0, 0, 0, 0, 1));
                continue;
            }
            Instant createdAt = parseTimestamp(row.get("timestamp"));
            boolean synthTime = createdAt == null;
            if (synthTime) {
                createdAt = Instant.EPOCH;   // 不丢行：缺/坏时间戳按 epoch 落库并计数上报
            }
            String id = asString(row.get("id"));
            if (id.isBlank()) {
                // 老行可能没有 id：按全部内容字段合成稳定 id（重复导入命中同一主键）；
                // 纳入 errorType/correction/comment/sources，避免仅这些字段不同的行被合并
                id = "ann-import-" + TelemetryDigest.sha256Hex(
                        asString(row.get("question")),
                        asString(row.get("answer")),
                        writeJsonOrEmpty(row.get("sources")),
                        asString(row.get("errorType")),
                        asString(row.get("correction")),
                        asString(row.get("comment")),
                        TIMESTAMP.format(createdAt.atZone(ZoneId.systemDefault()))).substring(0, 32);
            }
            try {
                boolean inserted = annotationService.persistIfAbsent(new ErrorAnnotationEntity(
                        id,
                        asString(row.get("conversationId")),
                        nullableString(row.get("question")),
                        nullableString(row.get("answer")),
                        writeJson(row.get("sources")),
                        nullableString(row.get("errorType")),
                        nullableString(row.get("correction")),
                        nullableString(row.get("comment")),
                        createdAt));
                stat = stat.plus(inserted
                        ? new ImportStat(1, 0, synthTime ? 1 : 0, 0, 0)
                        : new ImportStat(0, 1, synthTime ? 1 : 0, 0, 0));
            } catch (Exception e) {
                log.warn("[Telemetry] annotations 行导入失败（id={}）: {}", id, e.getMessage());
                stat = stat.plus(new ImportStat(0, 0, synthTime ? 1 : 0, 0, 1));
            }
        }
        log.info("[Telemetry] annotations 迁移：导入 {} 条，已存在跳过 {} 条，合成时间戳 {} 条，坏行 {} 条",
                stat.imported(), stat.skipped(), stat.synthTime(), stat.failed());
    }

    private void importGaps(Path path, DataGapService gapService) {
        List<String> lines = readLines(path, "data_gap");
        if (lines == null) {
            return;
        }
        ImportStat stat = new ImportStat(0, 0, 0, 0, 0);
        for (String line : lines) {
            Map<?, ?> row;
            try {
                row = objectMapper.readValue(line, Map.class);
            } catch (Exception e) {
                log.warn("[Telemetry] data_gap 坏行（JSON 无法解析）跳过: {}", abbreviate(line));
                stat = stat.plus(new ImportStat(0, 0, 0, 0, 1));
                continue;
            }
            Instant createdAt = parseTimestamp(row.get("timestamp"));
            boolean synthTime = createdAt == null;
            if (synthTime) {
                createdAt = Instant.EPOCH;   // 不丢行：缺/坏时间戳按 epoch 落库并计数上报
            }
            String question = asString(row.get("question"));
            boolean blankQuestion = question.isBlank();
            if (blankQuestion) {
                question = "";   // 列 NOT NULL：缺 question 补空串保留该行（不静默丢弃）
            }
            try {
                boolean inserted = gapService.persist(
                        question, nullableString(row.get("attemptedFilters")),
                        nullableString(row.get("reason")), createdAt);
                ImportStat delta = new ImportStat(
                        inserted ? 1 : 0, inserted ? 0 : 1, synthTime ? 1 : 0, blankQuestion ? 1 : 0, 0);
                stat = stat.plus(delta);
            } catch (Exception e) {
                log.warn("[Telemetry] data_gap 行导入失败: {}", e.getMessage());
                stat = stat.plus(new ImportStat(0, 0, synthTime ? 1 : 0, blankQuestion ? 1 : 0, 1));
            }
        }
        log.info("[Telemetry] data_gap 迁移：导入 {} 条，已存在跳过 {} 条，合成时间戳 {} 条，"
                        + "缺 question 补空 {} 条，坏行 {} 条",
                stat.imported(), stat.skipped(), stat.synthTime(), stat.synthQuestion(), stat.failed());
    }

    /** 读全部行；文件不存在返回 null（调用方按「无需迁移」处理），读取异常同样返回 null 并记错 */
    private List<String> readLines(Path path, String label) {
        if (!Files.exists(path)) {
            log.info("[Telemetry] 历史 {} 文件不存在（{}），无需迁移", label, path);
            return null;
        }
        try {
            return Files.readAllLines(path, StandardCharsets.UTF_8);
        } catch (Exception e) {
            log.error("[Telemetry] 读取历史 {} 文件失败: {}", label, path, e);
            return null;
        }
    }

    /** 秒精度本地时间戳字符串 → Instant；缺失/格式非法返回 null（调用方按 epoch 兜底计「合成时间戳」） */
    private static Instant parseTimestamp(Object value) {
        String text = asString(value);
        if (text.isBlank()) {
            return null;
        }
        try {
            return LocalDateTime.parse(text, TIMESTAMP).atZone(ZoneId.systemDefault()).toInstant();
        } catch (Exception e) {
            return null;
        }
    }

    /** JSONB 列存 JSON 文本；null 保持 null（与旧 JSONL 口径一致），序列化失败降级为 null */
    private String writeJson(Object value) {
        if (value == null) {
            return null;
        }
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception e) {
            log.warn("[Telemetry] sources 序列化失败，该行来源快照置空: {}", e.getMessage());
            return null;
        }
    }

    /** 合成键用：null 视为空串（不产生 "null" 字面量，避免不同缺失字段撞哈希） */
    private String writeJsonOrEmpty(Object value) {
        String json = writeJson(value);
        return json == null ? "" : json;
    }

    private static String asString(Object value) {
        return value == null ? "" : value.toString();
    }

    private static String nullableString(Object value) {
        if (value == null) {
            return null;
        }
        String text = value.toString();
        return text.isEmpty() ? null : text;
    }

    private static String abbreviate(String line) {
        return line.length() > 80 ? line.substring(0, 80) + "…" : line;
    }
}
