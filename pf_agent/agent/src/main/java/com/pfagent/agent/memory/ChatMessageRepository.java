package com.pfagent.agent.memory;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

/**
 * 消息仓储（chat_message）
 *
 * 查询按 conversation_id + seq 全排序走 idx_chat_message_conv_seq 索引；
 * 裁剪（F-005）删除最旧轮用 deleteByConversationIdAndSeqLessThanEqual；
 * clear 整会话删除用 deleteByConversationId（显式删，不依赖外键级联，H2/PG 行为一致）。
 *
 * F-020 起重新生成用带 seq + role 条件的更新替换最后一条助手消息：条件不满足时
 * 影响行数为 0，由 ConversationStore 转 409 conversation_changed，绝不覆盖期间新增消息。
 */
public interface ChatMessageRepository extends JpaRepository<ChatMessageEntity, Long> {

    /** 某会话全部消息按 seq 升序（旧 → 新，读取历史用） */
    List<ChatMessageEntity> findByConversationIdOrderBySeqAsc(String conversationId);

    /** 某会话最大 seq 的消息（裁剪会留下空洞，count ≠ max seq，seq 分配须以 max seq 为起点） */
    Optional<ChatMessageEntity> findTopByConversationIdOrderBySeqDesc(String conversationId);

    /** 某会话消息条数（写入前估量是否超轮数上限用） */
    long countByConversationId(String conversationId);

    /** 删除某会话全部消息（clear 用；外键 CASCADE 在生产作兜底） */
    @Transactional
    void deleteByConversationId(String conversationId);

    /** 删除某会话 seq 不超过指定值的消息（裁剪最旧轮，引用快照随行删除） */
    @Transactional
    void deleteByConversationIdAndSeqLessThanEqual(String conversationId, int seq);

    /**
     * 替换指定助手消息的正文/来源/缺口/完成时间；seq 与 role 作为终端条件，
     * 只有仍是原助手消息时才更新（期间出现新消息或已替换 → 0 行）。
     */
    @Transactional
    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("update ChatMessageEntity m set m.content = :content, m.sources = :sources,"
            + " m.gapReported = :gapReported, m.createdAt = :completedAt"
            + " where m.conversationId = :conversationId and m.seq = :seq and m.role = 'assistant'")
    int replaceAssistantMessage(@Param("conversationId") String conversationId,
                                @Param("seq") int seq,
                                @Param("content") String content,
                                @Param("sources") String sources,
                                @Param("gapReported") boolean gapReported,
                                @Param("completedAt") Instant completedAt);
}
