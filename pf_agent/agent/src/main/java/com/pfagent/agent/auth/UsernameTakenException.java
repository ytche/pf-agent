package com.pfagent.agent.auth;

/**
 * 注册/登录失败异常（SP7 T2）
 *
 * 对应 D4 错误码语义：由 T3 的 AuthController 捕获映射 HTTP 状态
 * （本异常 → 409 username_taken）。
 */
public class UsernameTakenException extends RuntimeException {

    public UsernameTakenException(String username) {
        super("用户名已被注册: " + username);
    }
}
