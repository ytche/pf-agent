package com.pfagent.agent.memory;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 * 消息仓储（chat_message）
 *
 * 查询按 conversation_id + seq 全排序走 idx_chat_message_conv_seq 索引；
 * 裁剪（F-005）删除最旧轮用 deleteByConversationIdAndSeqLessThanEqual；
 * clear 整会话删除用 deleteByConversationId（显式删，不依赖外键级联，H2/PG 行为一致）。
 */
public interface ChatMessageRepository extends JpaRepository<ChatMessageEntity, Long> {

    /** 某会话全部消息按 seq 升序（旧 → 新，读取历史用） */
    List<ChatMessageEntity> findByConversationIdOrderBySeqAsc(String conversationId);

    /** 某会话最大 seq 的消息（裁剪会留下空洞，count ≠ max seq，seq 分配须以 max seq 为起点） */
    Optional<ChatMessageEntity> findTopByConversationIdOrderBySeqDesc(String conversationId);

    /** 某会话消息条数（写入前估量是否超轮数上限用） */
    long countByConversationId(String conversationId);

    /** 删除某会话全部消息（clear 用；外键 CASCADE 在生产作兜底） */
    void deleteByConversationId(String conversationId);

    /** 删除某会话 seq 不超过指定值的消息（裁剪最旧轮） */
    void deleteByConversationIdAndSeqLessThanEqual(String conversationId, int seq);
}
