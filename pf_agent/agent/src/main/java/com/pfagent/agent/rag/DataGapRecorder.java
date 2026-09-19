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
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
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
     * 读取最近的数据缺口记录（SP8a J3，只读）
     *
     * 反向（最新在前）扫描 JSONL，单行损坏跳过并记 warn（不整体失败）；keyword
     * 非空时对 question/reason 做子串匹配；命中数达到 limit 即停，不全量载入内存
     * （滑动双端队列只保留最近 limit 条命中，最后倒序输出）。
     *
     * @param limit   返回条数上限（调用方已做默认与上限收敛）
     * @param keyword 匹配 question/reason 的子串，可空
     * @return 最新在前的记录列表；文件不存在/为空/全损坏时为空列表
     */
    public List<GapEntry> listGaps(int limit, String keyword) {
        Path path = Path.of(filePath);
        if (limit <= 0 || !Files.exists(path)) {
            return List.of();
        }
        Deque<GapEntry> matched = new ArrayDeque<>();
        try {
            for (String line : Files.readAllLines(path, StandardCharsets.UTF_8)) {
                if (line.isBlank()) {
                    continue;
                }
                try {
                    Map<?, ?> entry = objectMapper.readValue(line, Map.class);
                    String question = entry.get("question") == null ? "" : entry.get("question").toString();
                    String reason = entry.get("reason") == null ? "" : entry.get("reason").toString();
                    if (keyword != null && !keyword.isBlank()
                            && !question.contains(keyword) && !reason.contains(keyword)) {
                        continue;
                    }
                    matched.addLast(new GapEntry(
                            entry.get("timestamp") == null ? "" : entry.get("timestamp").toString(),
                            question, reason));
                    if (matched.size() > limit) {
                        matched.removeFirst();
                    }
                } catch (Exception e) {
                    // 单行损坏跳过：gap 读取是尽力而为的辅助通路，不拖垮主链路
                    log.warn("[DataGap] 跳过损坏的缺口记录行: {}", e.getMessage());
                }
            }
        } catch (Exception e) {
            log.error("[DataGap] 读取数据缺口失败: {}", filePath, e);
            return List.of();
        }
        List<GapEntry> result = new ArrayList<>(matched);
        Collections.reverse(result); // 双端队列为最旧在前，倒序成最新在前
        return result;
    }

    /** 一条数据缺口记录（读取侧视图，字段同写入 JSONL） */
    public record GapEntry(String timestamp, String question, String reason) {
    }

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
