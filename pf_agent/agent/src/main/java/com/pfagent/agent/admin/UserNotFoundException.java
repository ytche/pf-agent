package com.pfagent.agent.admin;

/**
 * 目标用户不存在（F-023 admin 用户管理），映射 404 not_found。
 */
public class UserNotFoundException extends RuntimeException {

    public UserNotFoundException(Long id) {
        super("用户不存在: " + id);
    }

    public UserNotFoundException(String message) {
        super(message);
    }
}
