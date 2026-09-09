-- SP2 匿名会话配额（F-011）：会话生命周期累计轮数列
-- 修正 SP1 V1 注释中「SP2 配额复用 message_rounds」的错误假设——message_rounds 会被
-- F-005 裁剪钉在 historyRounds 上限，不能作累计配额依据；total_rounds 永不被裁剪，
-- 只增不减，作为匿名每会话轮数配额的真实累计值。
-- ADD COLUMN ... DEFAULT 0 是 PG 在线安全操作（11+ 不重写表，含已有数据）。

ALTER TABLE chat_conversation ADD COLUMN total_rounds INT NOT NULL DEFAULT 0;
