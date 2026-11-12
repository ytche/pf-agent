-- F-023 管理后台（后端部分）schema：
--   1) user_account 新增 role 列：区分普通用户与管理员（V3 注释曾声明「不预留角色字段」，
--      本迁移按 F-023 需求落地角色，与 V3 的历史注释解耦——V3 不改，演进由本迁移承载）。
--   2) app_setting 通用键值配置表：注册入口开关等运行时可变配置的落库点，
--      默认值以种子行写入（注册开关默认开，保持与既有开源自部署行为一致）。
-- 由 Flyway 管理（ddl-auto=validate，Hibernate 只校验不建表）。
-- ADD COLUMN ... DEFAULT 是 PG 在线安全操作（11+ 不重写表，历史行即时补默认值）。

ALTER TABLE user_account ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'user';

CREATE TABLE app_setting (
  setting_key   VARCHAR(64) PRIMARY KEY,       -- 配置键（如 registration_enabled）
  setting_value VARCHAR(255) NOT NULL,         -- 配置值（字符串，调用方按需解析）
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 注册入口开关默认开启（true）；admin 可在界面切换为 false 关闭注册。
INSERT INTO app_setting (setting_key, setting_value) VALUES ('registration_enabled', 'true');
