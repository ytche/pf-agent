-- F-009 token 用量与费用：每次成功返回的 DeepSeek LLM 调用一行。
--
-- 注意：本迁移在 F-009 代码评审中就地补充过 (request_id, call_seq) 唯一索引与
-- call_seq >= 1 检查，属于同批未发布的修正。若某环境已应用过早期 V8，不得覆盖或
-- 修改已发布迁移文件（checksum 会变）：应新增 V9 补齐约束，或 flyway repair 后重新校验。
-- 固定接在 V7 之后；由 Flyway 管理（ddl-auto=validate，Hibernate 只校验不建表）。
--
-- 口径（设计 §3/§4）：
--  - 一次用户问答/regenerate 生成一个 request_id，request 内每次 LLM 调用 call_seq 从 1 递增；
--  - usage 缺失时 prompt/completion/total_tokens 与 cost 必须为 null（不得写 0），
--    usage_missing=true 单独标记调用事实；
--  - 价目快照随行保存（改价不回写历史）；cost 在采集时按快照折算；
--  - 只统计 DeepSeek LLM，不包含 embedding/向量库成本。
-- 会话/用户主数据删除不级联删除用量（历史费用仍是事实），因此不加外键。

CREATE TABLE usage_record (
  id                          BIGSERIAL PRIMARY KEY,
  request_id                  VARCHAR(64) NOT NULL,      -- 一次问答/regenerate 的请求 ID
  call_seq                    INT NOT NULL,              -- 请求内 LLM 调用序号（从 1 递增）
  conversation_id             VARCHAR(36),               -- 会话 ID（可空）
  owner_id                    BIGINT,                    -- 会话所有者用户主键（可空）
  purpose                     VARCHAR(32) NOT NULL,      -- agent / rerank / force_answer
  model                       VARCHAR(64) NOT NULL,      -- 实际模型标识
  prompt_tokens               INT,                       -- usage 缺失时为 null，不得写 0
  completion_tokens           INT,
  total_tokens                INT,
  usage_missing               BOOLEAN NOT NULL DEFAULT false,
  prompt_price_per_million    NUMERIC(18, 6),            -- 采集时输入单价快照（每百万 token）
  completion_price_per_million NUMERIC(18, 6),           -- 采集时输出单价快照（每百万 token）
  cost                        NUMERIC(18, 6),            -- 缺 usage 或价目时为 null
  currency                    VARCHAR(8) NOT NULL DEFAULT 'CNY',
  duration_ms                 BIGINT NOT NULL DEFAULT 0, -- 调用端到端耗时
  created_at                  TIMESTAMPTZ NOT NULL
);

-- 汇总页按时间范围查询（日/月边界由应用时区换算成 UTC 区间）
CREATE INDEX idx_usage_record_created_at ON usage_record(created_at DESC);
-- 按请求核对每次调用：同 request_id 下 call_seq 唯一且从 1 递增
CREATE UNIQUE INDEX idx_usage_record_request_id ON usage_record(request_id, call_seq);
ALTER TABLE usage_record
  ADD CONSTRAINT ck_usage_record_call_seq CHECK (call_seq >= 1);
-- 匿名会话只读当前会话用量
CREATE INDEX idx_usage_record_conversation_id ON usage_record(conversation_id, created_at DESC);
-- 登录用户只看自己 / 管理员按用户聚合
CREATE INDEX idx_usage_record_owner_id ON usage_record(owner_id, created_at DESC);
