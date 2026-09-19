package com.pfagent.agent.auth;

/**
 * 登录凭证错误异常（SP7 T2）
 *
 * 用户不存在与密码错误统一抛本异常（不区分两种失败，防用户名枚举）；
 * 由 T3 的 AuthController 捕获映射 HTTP 401 invalid_credentials。
 */
public class InvalidCredentialsException extends RuntimeException {

    public InvalidCredentialsException() {
        super("用户名或密码错误");
    }
}
