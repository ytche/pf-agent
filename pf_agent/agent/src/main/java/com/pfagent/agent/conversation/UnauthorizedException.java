package com.pfagent.agent.conversation;

/** 缺少或非法身份凭证（非法 JWT 不得静默降级为匿名），统一 401。 */
public class UnauthorizedException extends RuntimeException {

    public UnauthorizedException() {
        super("缺少或无效的身份凭证，请重新登录");
    }
}
