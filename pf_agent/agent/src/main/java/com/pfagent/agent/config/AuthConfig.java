package com.pfagent.agent.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

/**
 * 鉴权算法 Bean（SP7 T2 / D3）
 *
 * 只用 spring-security-crypto 的 BCryptPasswordEncoder（60 字符哈希，V3 表 password_hash
 * VARCHAR(72) 留余量），不引入 Spring Security 全家桶。
 */
@Configuration
public class AuthConfig {

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
