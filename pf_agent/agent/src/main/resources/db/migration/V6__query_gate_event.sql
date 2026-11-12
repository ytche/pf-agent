-- F-026 大范围查询门禁事件：只记录实际到达工具层的 BLOCKED / ALLOWED 判定。
-- 由 Flyway 管理（ddl-auto=validate，Hibernate 只校验不建表）。
-- 版本分配：F-026=V6（F-020/F-022 前端实施固定用 V7，不得撞版）。
--
-- 不是全量提示词层拦截记录：模型直接给出的收窄建议、非宽条件正常查询、轻量概览
-- 均不写本表。会话与问题来自 ToolCallTracker 的请求上下文，不接受 LLM 工具参数；
-- 不保存回答正文或来源快照。query_json 存当次查询参数（业务条件 + offset/limit/sort），
-- 分析时按会话/工具/query_json 中的业务条件关联同一逻辑查询。

CREATE TABLE query_gate_event (
  id              BIGSERIAL PRIMARY KEY,        -- 数据库生成的事件 ID
  created_at      TIMESTAMPTZ NOT NULL,         -- 事件时间
  conversation_id VARCHAR(36),                  -- 当前请求所在会话 ID（请求上下文缺失时不写事件）
  question        TEXT,                         -- 当前请求级用户问题（翻页时可能是“继续”）
  tool_name       VARCHAR(64) NOT NULL,         -- searchByMetadata / listEntries
  module          VARCHAR(32),                  -- 当前模块或 all
  event_type      VARCHAR(16) NOT NULL,         -- BLOCKED / ALLOWED
  reason          VARCHAR(32) NOT NULL,         -- no_conditions / book_only
  query_json      JSONB                         -- 当次查询参数 JSON（不含回答/来源快照）
);
CREATE INDEX idx_query_gate_event_created_at ON query_gate_event(created_at DESC);
-- 按会话回看同一逻辑查询的门禁轨迹（放行后的翻页各记一行）
CREATE INDEX idx_query_gate_event_conversation ON query_gate_event(conversation_id, created_at DESC);
