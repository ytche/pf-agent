package com.pfagent.agent.util;

import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * MapUtil.str 单元测试
 *
 * 覆盖 Map.getOrDefault 覆盖不到的三个分支：key 缺失、value 为 null、非 String 值，
 * 以及正常取值路径。
 */
class MapUtilTest {

    /** key 缺失时返回空串 */
    @Test
    void strMissingKeyReturnsEmptyString() {
        assertThat(MapUtil.str(Map.of(), "book_name_cn")).isEmpty();
    }

    /** value 为 null 时返回空串 */
    @Test
    void strNullValueReturnsEmptyString() {
        Map<String, Object> meta = new HashMap<>();
        meta.put("tocPath", null);

        assertThat(MapUtil.str(meta, "tocPath")).isEmpty();
    }

    /** 非 String 类型值统一转字符串 */
    @Test
    void strNonStringValueConvertedToString() {
        assertThat(MapUtil.str(Map.of("level", 3), "level")).isEqualTo("3");
    }

    /** 正常 String 值原样返回 */
    @Test
    void strStringValueReturnedAsIs() {
        assertThat(MapUtil.str(Map.of("book_name_cn", "核心规则书"), "book_name_cn"))
                .isEqualTo("核心规则书");
    }
}
