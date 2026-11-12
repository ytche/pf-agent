-- F-020 / F-022 会话后端：统一会话归属、引用快照与配额计数。
-- 固定接在 F-026 的 V6 之后；不得与 V6 撞号（实施 Spec §6）。
-- 由 Flyway 管理（ddl-auto=validate，Hibernate 只校验不建表）。

-- 1) 会话：标题、置顶、账号归属、累计生成尝试次数。
ALTER TABLE chat_conversation
  ADD COLUMN title VARCHAR(200),
  ADD COLUMN pinned BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN owner_user_id BIGINT REFERENCES user_account(id) ON DELETE SET NULL,
  ADD COLUMN generation_attempts INT NOT NULL DEFAULT 0;

-- 既有匿名会话升级后配额不得重置：以历史累计轮数回填生成尝试次数。
-- 历史重新生成无法追溯，不虚构额外次数（实施 Spec §6.1）。
UPDATE chat_conversation SET generation_attempts = total_rounds WHERE total_rounds > 0;

-- 账号会话列表：置顶优先，其余按最近活跃倒序（分页与匿名 lookup 的过滤列）。
CREATE INDEX idx_chat_conversation_owner_pinned_active
  ON chat_conversation(owner_user_id, pinned DESC, last_active_at DESC);
CREATE INDEX idx_chat_conversation_owner_active
  ON chat_conversation(owner_user_id, last_active_at DESC);

-- 2) 消息：当轮引用快照 + 数据缺口标记。
-- sources 为 null 表示历史消息未保存来源，API/前端降级为“历史来源未保存”，不伪造。
ALTER TABLE chat_message
  ADD COLUMN sources JSONB,
  ADD COLUMN gap_reported BOOLEAN NOT NULL DEFAULT false;
