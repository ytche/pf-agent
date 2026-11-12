-- F-021 遥测入库（错误标注 + 数据缺口）：由 JSONL 文件落盘改为 PostgreSQL 持久化。
-- 由 Flyway 管理（ddl-auto=validate，Hibernate 只校验不建表）。
-- 字段照抄原 JSONL 行结构（FeedbackRecorder / DataGapRecorder），sources 用 JSONB。
-- 版本分配：F-021=V4、F-023=V5（已协调，不得撞版）。

CREATE TABLE error_annotation (
  id              VARCHAR(64) PRIMARY KEY,   -- 应用层生成：ann- + 毫秒时间戳 + 随机后缀
  conversation_id VARCHAR(36),               -- 会话 ID（可空：前端未带会话的标注）
  question        TEXT,                      -- 用户原始问题快照
  answer          TEXT,                      -- Agent 回答快照（含来源以精确复现错误现场）
  sources         JSONB,                     -- 回答当时引用的来源快照 [{book,tocPath,chunkId,content}]
  error_type      VARCHAR(32),               -- 事实错误/检索漏召回/编造来源/答非所问/结构差
  correction      TEXT,                      -- 用户修正（可空）
  comment         TEXT,                      -- 用户备注（可空）
  resolution      VARCHAR(32) NOT NULL DEFAULT '待分析',  -- 闭环跟踪状态
  created_at      TIMESTAMPTZ NOT NULL       -- 标注时刻（展示/分析按秒对齐）
);
CREATE INDEX idx_error_annotation_created_at ON error_annotation(created_at DESC);

CREATE TABLE data_gap (
  id                BIGSERIAL PRIMARY KEY,      -- 合成代理键（原 JSONL 行无 id）
  dedup_key         VARCHAR(64) NOT NULL UNIQUE,-- 内容 + 时间戳的 SHA-256：写库与迁移导入幂等去重
  question          TEXT NOT NULL,              -- 用户原始问题
  attempted_filters TEXT,                       -- 尝试过的过滤条件（工具参数原始字符串，可空）
  reason            TEXT,                       -- 缺口原因描述
  created_at        TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_data_gap_created_at ON data_gap(created_at DESC);
