package com.pfagent.agent.auth;

import java.util.Locale;
import java.util.regex.Pattern;

/**
 * 登录名/密码规范化与校验（SP7 抽出共享，F-023 admin 建号/改密复用）
 *
 * 注册（AuthService）与 admin 增改用户（AdminService）需要同一套规则，逻辑抽到此处
 * 避免两处漂移：
 * - 登录名：去首尾空白 + 小写后须为 3~64 字符的字母、数字、下划线或中文
 * - 密码：去首尾空白后至少 8 位
 */
public final class Credentials {

    /** 登录名合法字符：字母 / 数字 / 下划线 / 中文（归一后 3~64 字符） */
    private static final Pattern USERNAME_PATTERN = Pattern.compile("[\\p{IsHan}A-Za-z0-9_]{3,64}");

    /** 密码长度下限 */
    static final int MIN_PASSWORD_LENGTH = 8;

    private Credentials() {
    }

    /** 归一登录名：去首尾空白 + 小写并做格式校验，非法时抛 IllegalArgumentException */
    public static String normalizeUsername(String rawUsername) {
        String username = rawUsername == null ? "" : rawUsername.trim().toLowerCase(Locale.ROOT);
        if (!USERNAME_PATTERN.matcher(username).matches()) {
            throw new IllegalArgumentException(
                    "用户名须为 3~64 字符的字母、数字、下划线或中文: " + username);
        }
        return username;
    }

    /** 校验密码强度（≥8 位），返回去首尾空白后的密码；非法时抛 IllegalArgumentException */
    public static String validatePassword(String rawPassword) {
        String password = rawPassword == null ? "" : rawPassword.trim();
        if (password.length() < MIN_PASSWORD_LENGTH) {
            throw new IllegalArgumentException("密码至少 " + MIN_PASSWORD_LENGTH + " 位");
        }
        return password;
    }
}
