package com.pfagent.agent.admin;

/**
 * 不能移除最后一个管理员（F-023 自保护），映射 409 last_admin。
 *
 * 删除或降级一个 admin 账号时若系统仅剩这一个 admin，拒绝操作，避免把自己锁死在
 * 管理后台之外。
 */
public class LastAdminException extends RuntimeException {

    public LastAdminException() {
        super("不能删除或降级最后一个管理员");
    }
}
