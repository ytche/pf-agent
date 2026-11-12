package com.pfagent.agent.chat;

import java.time.Instant;
import java.util.List;

/**
 * 对话响应 — LLM 回答 + 来源 + gap 标记 + 会话 ID
 *
 * gapReported：本次请求是否记录了数据缺口（前端可提示"已记录待优化"）。
 * conversationId：前端未传时由后端生成，随响应返回供前端留存。
 * messageId / messageSeq / completedAt：F-020 起追加的助手消息定位字段（旧客户端可忽略），
 * 重新生成保持同一消息 ID。
 */
public record ChatResponse(
        String answer,
        List<SourceRef> sources,
        boolean gapReported,
        String conversationId,
        Long messageId,
        Integer messageSeq,
        Instant completedAt
) {

    /** 兼容构造：未落库或不关心消息定位时（单元测试、异常降级）使用 */
    public ChatResponse(String answer, List<SourceRef> sources, boolean gapReported, String conversationId) {
        this(answer, sources, gapReported, conversationId, null, null, null);
    }

    /**
     * 单条规则来源引用
     *
     * book 为兼容字段：中文书名与缩写合并后的展示名（如 "核心规则书 (CRB)"），
     * 旧客户端与历史快照继续按此消费。bookNameCn / bookAbbreviation 为 F-020
     * 追加的结构化字段，官方或未知来源可能为空；历史快照缺失时 Jackson 置 null。
     *
     * title 为 F-002 / KN-204 / KN-219 追加的展示标题兜底字段：检索原始 title 为空时
     * 取正文首个有效行（40 字截断），无有效正文回退 tocPath 末段；非空 title 去尾冒号
     * 且超过 60 字截断。只影响展示，tocPath / content / 检索匹配路径保持原值；
     * 旧历史快照缺该字段时 Jackson 置 null，前端可继续回退 tocPath。
     */
    public record SourceRef(
            String book,
            String bookNameCn,
            String bookAbbreviation,
            String title,
            String tocPath,
            String chunkId,
            String content
    ) {

        /** 兼容构造：F-002 之前的调用方与旧快照（无展示标题兜底字段） */
        public SourceRef(String book, String bookNameCn, String bookAbbreviation,
                         String tocPath, String chunkId, String content) {
            this(book, bookNameCn, bookAbbreviation, null, tocPath, chunkId, content);
        }

        /** 兼容构造：只提供旧四字段（无结构化书名/缩写） */
        public SourceRef(String book, String tocPath, String chunkId, String content) {
            this(book, null, null, null, tocPath, chunkId, content);
        }
    }
}
