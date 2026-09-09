package com.pfagent.agent.chat;

import java.util.List;

/**
 * 对话响应 — LLM 回答 + 来源 + gap 标记 + 会话 ID
 *
 * gapReported：本次请求是否记录了数据缺口（前端可提示"已记录待优化"）。
 * conversationId：前端未传时由后端生成，随响应返回供前端留存。
 */
public record ChatResponse(
        String answer,
        List<SourceRef> sources,
        boolean gapReported,
        String conversationId
) {

    /**
     * 单条规则来源引用
     */
    public record SourceRef(
            String book,
            String tocPath,
            String chunkId,
            String content
    ) {
    }
}
