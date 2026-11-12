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
import java.util.ArrayList;
import java.util.List;

/**
 * 工具调用落盘记录器（F-006 / AKN-023）
 *
 * 一次问答结束后把本请求的全部工具调用明细以 JSONL 追加写入工具调用文件，
 * 供 qa/tool_calls_report.py 聚合分析（工具类型/次数/成功率/耗时），驱动
 * prompt 与检索策略调优。追加式不覆盖历史，父目录不存在时自动创建。
 *
 * AKN-023 起每次问答另追加一条 {@code recordType=request_summary} 的请求级摘要
 * （见 {@link ToolCallTracker.RequestSummary}）：无工具调用的问答也写摘要，
 * 使总耗时 / LLM 调用次数与累计耗时不再只存在于应用日志；请求级指标只写一次，
 * 不复制到每条工具记录，避免分析脚本按行重复累计。旧 JSONL 记录保持可读。
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
     * 空列表直接返回（无工具调用时不写工具明细，请求级摘要另走 flushRequestSummary）。
     */
    public void flush(List<ToolCallRecord> records) {
        if (records == null || records.isEmpty()) {
            return;
        }
        List<String> lines = new ArrayList<>(records.size());
        try {
            for (ToolCallRecord r : records) {
                lines.add(objectMapper.writeValueAsString(r));
            }
        } catch (Exception e) {
            log.error("[ToolCall] 记录序列化失败: {}", filePath, e);
            return;
        }
        append(lines);
    }

    /**
     * 追加写入请求级耗时摘要（每次问答一条，无工具调用也必须写）。
     * 摘要是复盘分析的总耗时/LLM 次数与累计耗时口径来源，序列化失败只记日志。
     */
    public void flushRequestSummary(ToolCallTracker.RequestSummary summary) {
        if (summary == null) {
            return;
        }
        try {
            append(List.of(objectMapper.writeValueAsString(summary)));
        } catch (Exception e) {
            log.error("[ToolCall] 请求级耗时摘要序列化失败: {}", filePath, e);
        }
    }

    /** 逐行追加写入（每行一条 JSON），失败只记日志不抛 */
    private void append(List<String> lines) {
        try {
            Path path = Path.of(filePath);
            Path parent = path.toAbsolutePath().getParent();
            if (parent != null) {
                Files.createDirectories(parent);
            }
            StringBuilder sb = new StringBuilder();
            for (String line : lines) {
                sb.append(line).append(System.lineSeparator());
            }
            Files.writeString(path, sb.toString(), StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (Exception e) {
            log.error("[ToolCall] 记录工具调用失败: {}", filePath, e);
        }
    }
}
