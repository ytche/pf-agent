package com.pfagent.agent.usage;

import com.pfagent.agent.telemetry.UsageRecorder;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * 内存模式用量占位（F-009）：没有数据源与 usage_record 表，采集为 no-op。
 *
 * ChatService 依赖 {@link UsageRecorder}，memory 模式下若没有实现会装配失败；
 * 这里保持接口形状，不记录任何数据，也不假装成功写库。
 */
@Component
@ConditionalOnProperty(name = "pf.chat.memory", havingValue = "memory", matchIfMissing = true)
public class NoopUsageRecorder implements UsageRecorder {

    @Override
    public void record(String purpose, String model, ChatResponse response, long durationMs) {
        // 内存模式不落库
    }
}
