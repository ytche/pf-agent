package com.pfagent.agent.telemetry;

import org.springframework.ai.chat.model.ChatResponse;

/**
 * 请求级 LLM 用量采集契约（F-009 / F-016 共用）。
 *
 * <p>实现方负责维护 request_id、call_seq、conversation/owner 上下文与价目折算；
 * 调用方只在每次模型调用成功后提交响应与耗时，不自行计算 token 或费用。
 */
public interface UsageRecorder {

    /**
     * 记录一次成功返回的 LLM 调用。
     *
     * @param purpose    agent / rerank / force_answer
     * @param model      实际模型标识
     * @param response   模型响应（usage 缺失时仍允许提交）
     * @param durationMs 调用耗时
     */
    void record(String purpose, String model, ChatResponse response, long durationMs);
}
