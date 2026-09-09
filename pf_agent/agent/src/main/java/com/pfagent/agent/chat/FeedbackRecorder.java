package com.pfagent.agent.chat;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;

/**
 * 错误标注记录器（错误标注闭环）
 *
 * 前端「标错」按钮提交一条用户反馈，落一条 JSONL 到 annotations 文件，
 * 供 qa/annotations_report.py 按 errorType 聚类分析，驱动 prompt/检索策略迭代。
 * 追加式（不覆盖历史），父目录不存在时自动创建。
 *
 * 写入失败只记日志不抛出：标注是尽力而为的遥测，不应拖垮前端交互。
 * 时间戳用秒精度 ISO 格式（与分析脚本对齐，同 DataGapRecorder）。
 */
@Component
public class FeedbackRecorder {

    private static final Logger log = LoggerFactory.getLogger(FeedbackRecorder.class);

    /** 秒精度 ISO 时间戳（不带纳秒，与分析脚本/展示格式一致） */
    private static final DateTimeFormatter TIMESTAMP = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");

    @Value("${pf.feedback.file-path}")
    private String filePath;
    private final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * 追加一条错误标注记录（JSONL 一行），返回生成的记录 ID
     *
     * 记录含 question/answer/sources 回答快照，分析时可精确复现错误现场。
     */
    public String record(FeedbackRequest request) {
        String id = generateId();
        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("id", id);
        entry.put("conversationId", request.conversationId());
        entry.put("question", request.question());
        entry.put("answer", request.answer());
        entry.put("sources", request.sources());
        entry.put("errorType", request.errorType());
        entry.put("correction", request.correction());
        entry.put("comment", request.comment());
        entry.put("resolution", "待分析");
        entry.put("timestamp", LocalDateTime.now().format(TIMESTAMP));
        try {
            Path path = Path.of(filePath);
            Path parent = path.toAbsolutePath().getParent();
            if (parent != null) {
                Files.createDirectories(parent);
            }
            Files.writeString(path, objectMapper.writeValueAsString(entry) + System.lineSeparator(),
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (Exception e) {
            log.error("[Feedback] 记录错误标注失败: {}", filePath, e);
        }
        return id;
    }

    /** ann- 前缀 + 毫秒时间戳 + 随机后缀，单机并发下唯一，无需数据库自增 */
    private String generateId() {
        return "ann-" + System.currentTimeMillis()
                + "-" + ThreadLocalRandom.current().nextInt(1000, 10000);
    }
}
