-- SP1 会话持久化初始 schema（PostgreSQL）
-- 由 Flyway 管理（ddl-auto=validate，Hibernate 只校验不建表）。
-- 设计来源：SP1_持久化基础设施方案 §3 D3。

CREATE TABLE chat_conversation (
  id              VARCHAR(36) PRIMARY KEY,   -- 后端生成的 UUID（conversationId）
  created_at      TIMESTAMPTZ NOT NULL,
  last_active_at  TIMESTAMPTZ NOT NULL,
  message_rounds  INT NOT NULL DEFAULT 0     -- 冗余轮数（F-005 裁剪 + SP2 配额复用）
);

CREATE TABLE chat_message (
  id              BIGSERIAL PRIMARY KEY,
  conversation_id VARCHAR(36) NOT NULL REFERENCES chat_conversation(id) ON DELETE CASCADE,
  seq             INT NOT NULL,              -- 会话内消息序号（从 1 递增；一轮 = user + assistant 两条）
  role            VARCHAR(10) NOT NULL,      -- user / assistant
  content         TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_chat_message_conv_seq ON chat_message(conversation_id, seq);
