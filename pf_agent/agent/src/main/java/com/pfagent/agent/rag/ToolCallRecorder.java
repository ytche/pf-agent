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
import java.util.List;

/**
 * 工具调用落盘记录器（F-006）
 *
 * 一次问答结束后把本请求的全部工具调用明细以 JSONL 追加写入工具调用文件，
 * 供 qa/tool_calls_report.py 聚合分析（工具类型/次数/成功率/耗时），驱动
 * prompt 与检索策略调优。追加式不覆盖历史，父目录不存在时自动创建。
 *
 * 写入失败只记日志不抛出：工具调用统计是复盘遥测，不应拖垮问答主链路。
 * 与 FeedbackRecorder / DataGapRecorder 同型。
 */
@Component
public class ToolCallRecorder {

    private static final Logger log = LoggerFactory.getLogger(ToolCallRecorder.class);

    @Value("${pf.tools.file-path}")
    private String filePath;
    private final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * 追加写入一批工具调用记录（每次问答一批，JSONL 每行一条）。
     * 空列表直接返回（无工具调用不落盘——无调用则无观测数据）。
     */
    public void flush(List<ToolCallRecord> records) {
        if (records == null || records.isEmpty()) {
            return;
        }
        try {
            Path path = Path.of(filePath);
            Path parent = path.toAbsolutePath().getParent();
            if (parent != null) {
                Files.createDirectories(parent);
            }
            StringBuilder sb = new StringBuilder();
            for (ToolCallRecord r : records) {
                sb.append(objectMapper.writeValueAsString(r)).append(System.lineSeparator());
            }
            Files.writeString(path, sb.toString(), StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (Exception e) {
            log.error("[ToolCall] 记录工具调用失败: {}", filePath, e);
        }
    }
}
