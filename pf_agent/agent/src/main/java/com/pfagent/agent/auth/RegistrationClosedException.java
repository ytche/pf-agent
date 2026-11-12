package com.pfagent.agent.auth;

/**
 * 注册入口已关闭（F-023）：admin 通过界面把 registration_enabled 置 false 后，
 * POST /api/auth/register 拒绝，映射 403 registration_closed。
 */
public class RegistrationClosedException extends RuntimeException {

    public RegistrationClosedException() {
        super("注册入口已关闭，请联系管理员");
    }
}
