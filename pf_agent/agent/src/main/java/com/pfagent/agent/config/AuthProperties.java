package com.pfagent.agent.config;

import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;

/**
 * 鉴权配置属性与装配校验（SP7 T1 引入开关与 jdbc 校验，T2 接入用户域后扩展 JWT 密钥提醒；
 * T3 才落地 AuthController / AuthInterceptor 的 HTTP 面）
 *
 * 装配校验（D1，fail-fast）：pf.auth.enabled=true 时用户表在 PG（Flyway V3），
 * 强制要求 pf.chat.memory=jdbc；若仍为 memory 模式则启动即失败并给出明确错误信息，
 * 避免「开了鉴权却连用户表都没有」的静默错配。
 *
 * 密钥提醒（D3，不阻断）：pf.auth.enabled=true 且 pf.auth.jwt-secret 仍为开发默认值时
 * 启动打 WARN——自部署场景友好（能跑），但明确提示生产必须经 PF_AUTH_JWT_SECRET 覆盖。
 */
@Configuration
public class AuthProperties {

    private static final Logger log = LoggerFactory.getLogger(AuthProperties.class);

    /** 开发默认 JWT 密钥（仅本地跑通；与 JwtService 默认值保持一致） */
    public static final String DEFAULT_JWT_SECRET = "pf-agent-dev-jwt-secret-change-me";

    /** 鉴权开关（默认关：开源自部署零行为变化） */
    @Value("${pf.auth.enabled:false}")
    private boolean authEnabled;

    @Value("${pf.chat.memory:jdbc}")
    private String chatMemory;

    @Value("${pf.auth.jwt-secret:" + DEFAULT_JWT_SECRET + "}")
    private String jwtSecret;

    @PostConstruct
    public void validateAuthMode() {
        if (authEnabled && !"jdbc".equalsIgnoreCase(chatMemory)) {
            throw new IllegalStateException(
                    "pf.auth.enabled=true 要求 pf.chat.memory=jdbc（用户表在 PostgreSQL），"
                            + "当前 pf.chat.memory=" + chatMemory + "。请将 pf.chat.memory 设为 jdbc 并配置数据源，"
                            + "或关闭鉴权（pf.auth.enabled=false）。");
        }
        if (authEnabled) {
            log.info("鉴权已启用（pf.auth.enabled=true）：/api/chat 需 JWT（T3 落地拦截器）");
            if (DEFAULT_JWT_SECRET.equals(jwtSecret)) {
                log.warn("pf.auth.jwt-secret 仍为开发默认值：生产部署必须经 env PF_AUTH_JWT_SECRET 覆盖，"
                        + "否则 JWT 可被任意伪造。");
            }
        }
    }

    public boolean isAuthEnabled() {
        return authEnabled;
    }

    public String getJwtSecret() {
        return jwtSecret;
    }
}
