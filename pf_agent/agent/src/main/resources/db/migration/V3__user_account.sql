-- SP7 单体用户表（D2）：注册/登录 + JWT 鉴权的用户域最小 schema。
-- 由 Flyway 管理（ddl-auto=validate，Hibernate 只校验不建表）。
-- 最小够用：不预留角色/邮箱字段（将来微服务用户库重新设计，本表不背演进包袱）。
-- username 的 UNIQUE 是大小写敏感的（PG 默认），大小写不敏感由应用层归一（AuthService 入库前转小写）。

CREATE TABLE user_account (
  id            BIGSERIAL PRIMARY KEY,
  username      VARCHAR(64) UNIQUE NOT NULL,   -- 登录名，应用层归一（去首尾空白 + 小写）
  password_hash VARCHAR(72) NOT NULL,          -- BCrypt（60 字符，留余量）
  nickname      VARCHAR(64),                   -- 可选展示名，默认 = username（应用层兜底）
  created_at    TIMESTAMPTZ NOT NULL,
  last_login_at TIMESTAMPTZ
);
