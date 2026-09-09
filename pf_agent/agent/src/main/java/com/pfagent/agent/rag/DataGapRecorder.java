package com.pfagent.agent.rag;

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

/**
 * 数据缺口记录器（设计 §7）
 *
 * 检索无结果时 reportDataGap 工具落一条 JSONL，供后续脚本分析驱动工具面/数据迭代。
 * 追加式（不覆盖历史），父目录不存在时自动创建。
 *
 * 写入失败只记日志不抛出：gap 上报是尽力而为的遥测，不应拖垮主回答链路。
 * 时间戳用秒精度 ISO 格式（2026-07-31T10:15:30），与分析脚本对齐。
 */
@Component
public class DataGapRecorder {

    private static final Logger log = LoggerFactory.getLogger(DataGapRecorder.class);

    /** 秒精度 ISO 时间戳（不带纳秒，保证与分析脚本/展示格式一致） */
    private static final DateTimeFormatter TIMESTAMP = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");

    @Value("${pf.gaps.file-path}")
    private String filePath;
    private final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * 追加一条数据缺口记录（JSONL 一行）
     *
     * @param question         用户原始问题
     * @param attemptedFilters 尝试过的过滤条件（工具参数的原始字符串）
     * @param reason           缺口原因描述
     */
    public void record(String question, String attemptedFilters, String reason) {
        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("question", question);
        entry.put("attemptedFilters", attemptedFilters);
        entry.put("reason", reason);
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
            log.error("[DataGap] 记录数据缺口失败: {}", filePath, e);
        }
    }
}
