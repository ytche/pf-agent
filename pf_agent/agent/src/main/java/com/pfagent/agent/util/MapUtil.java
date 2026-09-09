package com.pfagent.agent.util;

import java.util.Map;

/**
 * Map 读取工具
 */
public final class MapUtil {

    private MapUtil() {
    }

    /**
     * 从 metadata 安全取值：key 缺失或值为 null 均返回空串，非 String 值统一 toString。
     * Map.getOrDefault 只在 key 缺失时返回默认值、不防 value 为 null——此处两者都兜底，
     * 且对任意 Object 统一转字符串，供调用处直接做 isBlank / 字符串拼接而不必判空。
     */
    public static String str(Map<String, Object> map, String key) {
        Object v = map.get(key);
        return v == null ? "" : v.toString();
    }
}
