package com.pfagent.agent.memory;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * 会话仓储（chat_conversation）
 *
 * 主键即 conversationId（String UUID）。删除由 ConversationStore/JdbcChatMemory 显式
 * 先删消息再删会话；schema 侧外键 ON DELETE CASCADE 仍在，作生产环境兜底。
 *
 * F-020 起列表查询按「置顶优先、最近活跃倒序」；可见性条件 message_rounds > 0
 * （空父行保留但不出现在历史列表）。
 */
public interface ChatConversationRepository extends JpaRepository<ChatConversationEntity, String> {

    /** 账号会话分批读取：置顶优先，其余最近活跃倒序（只含已有成功轮次的会话） */
    @Query("select c from ChatConversationEntity c"
            + " where c.ownerUserId = :owner and c.messageRounds > 0"
            + " order by c.pinned desc, c.lastActiveAt desc, c.id desc")
    List<ChatConversationEntity> findVisibleByOwner(@Param("owner") Long owner, Pageable pageable);

    /** 账号可见会话总数（分页 nextCursor 判定用） */
    @Query("select count(c) from ChatConversationEntity c"
            + " where c.ownerUserId = :owner and c.messageRounds > 0")
    long countVisibleByOwner(@Param("owner") Long owner);

    /** 累计生成尝试 +1（普通问答与重新生成在模型调用前调用；父行缺失时返回 0） */
    @Transactional
    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("update ChatConversationEntity c set c.generationAttempts = c.generationAttempts + 1"
            + " where c.id = :id")
    int incrementGenerationAttempts(@Param("id") String id);

    /** 认领仅写 owner 为空的会话（条件更新，避免并发覆盖他人认领） */
    @Transactional
    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("update ChatConversationEntity c set c.ownerUserId = :owner"
            + " where c.id = :id and c.ownerUserId is null")
    int claimAnonymous(@Param("id") String id, @Param("owner") Long owner);
}
