package com.pfagent.agent.telemetry;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

/**
 * 类文件符号扫描工具（测试用，F-021 回归锁）
 *
 * 用来断言某个记录器**不再引用任何文件写入 API**：旧实现（DB 不可用时回退写 jsonl）的
 * 形态是 `@Value String filePath` + `Files.writeString`，只检查「有没有 Path 类型字段」
 * 挡不住这种回归；而类文件常量池里会留下被引用类/方法的符号字面量（如
 * `java/nio/file/Files`），按 ASCII 子串扫描才挡得住。
 */
public final class RecorderBytecode {

    private RecorderBytecode() {
    }

    /**
     * 返回类文件字节的 1 字节 = 1 字符视图（ISO-8859-1 映射），供 ASCII 子串断言。
     * 类文件在 target/test-classes 下与包路径同名，故按「简单类名 + .class」定位资源。
     */
    public static String symbolsOf(Class<?> type) throws IOException {
        String resource = type.getSimpleName() + ".class";
        try (InputStream in = type.getResourceAsStream(resource)) {
            if (in == null) {
                throw new IllegalStateException("找不到类文件资源: " + type.getName() + " (" + resource + ")");
            }
            return new String(in.readAllBytes(), StandardCharsets.ISO_8859_1);
        }
    }
}
