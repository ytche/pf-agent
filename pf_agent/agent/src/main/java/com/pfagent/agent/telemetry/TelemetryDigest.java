package com.pfagent.agent.telemetry;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

/**
 * 遥测去重键摘要工具（F-021）
 *
 * 数据缺口表没有业务主键，dedup_key 由内容 SHA-256 合成：写库与迁移导入用同一算法，
 * 「同内容同秒」视为同一条缺口，重复写入/重复导入都不产生新行。
 * SHA-256 是 JDK 内建算法，缺失即 JVM 环境损坏，故直接抛 IllegalStateException。
 */
final class TelemetryDigest {

    private TelemetryDigest() {
    }

    /** 各字段以 NUL 连接后取 SHA-256 十六进制小写（NUL 不会出现在业务文本里，避免字段边界歧义） */
    static String sha256Hex(String... parts) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            StringBuilder joined = new StringBuilder();
            for (int i = 0; i < parts.length; i++) {
                if (i > 0) {
                    joined.append('\u0000');
                }
                joined.append(parts[i] == null ? "" : parts[i]);
            }
            return HexFormat.of().formatHex(digest.digest(joined.toString().getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("JVM 缺少 SHA-256 实现", e);
        }
    }
}
