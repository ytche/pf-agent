package com.pfagent.agent.chat;

import com.pfagent.agent.telemetry.ErrorAnnotationService;
import com.pfagent.agent.telemetry.RecorderBytecode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * FeedbackRecorder 降级测试（F-021，memory / DB 不可用）
 *
 * 用户拍板（2026-09-24）：memory（DB 不可用）模式下**不记录**——不保留文件兼容/双写，
 * 也不谎报成功。本类锁定两条不变量：
 *  - record 返回 ok=false、id=null、reason=db_unavailable（前端据 ok/状态码提示失败）
 *  - 记录器不再有任何文件落盘通路（回归锁：防「DB 不可用时回退写 jsonl」）
 *
 * 回归锁用**字节码扫描**而非字段类型扫描：旧实现是 `String filePath`（@Value）+
 * `Files.writeString`，只查「有没有 Path 字段」根本挡不住；扫描 class 常量池里的
 * 文件 API 符号引用（java/nio/file/Files、FileWriter…）才能真挡住任何回退写文件的实现。
 */
class FeedbackRecorderMemoryModeTest {

    @Test
    void recordWithoutDatabaseReportsFailureInsteadOfFakeSuccess() {
        FeedbackRecorder recorder = new FeedbackRecorder();
        ReflectionTestUtils.setField(recorder, "annotationServiceProvider", emptyProvider());

        FeedbackResponse response = recorder.record(
                new FeedbackRequest("cid", "q", "a", List.of(), "事实错误", null, null));

        assertThat(response.ok()).isFalse();
        assertThat(response.id()).isNull();   // 不给 id：避免前端以为已记录
        assertThat(response.reason()).isEqualTo(FeedbackResponse.REASON_DB_UNAVAILABLE);
    }

    /** 字节码不得引用任何文件写入 API（含路径类型），锁死「DB 不可用时回退写 jsonl」的路径 */
    @Test
    void bytecodeReferencesNoFileWriteApi() throws Exception {
        assertThat(RecorderBytecode.symbolsOf(FeedbackRecorder.class))
                .doesNotContain("java/nio/file/Files")
                .doesNotContain("java/nio/file/Path")
                .doesNotContain("java/io/FileWriter")
                .doesNotContain("java/io/FileOutputStream")
                .doesNotContain("java/io/RandomAccessFile")
                .doesNotContain("java/io/PrintWriter")
                .doesNotContain("java/io/BufferedWriter");
    }

    private static ObjectProvider<ErrorAnnotationService> emptyProvider() {
        return new ObjectProvider<>() {
            @Override
            public ErrorAnnotationService getObject() {
                throw new IllegalStateException("no bean");
            }

            @Override
            public ErrorAnnotationService getObject(Object... args) {
                throw new IllegalStateException("no bean");
            }

            @Override
            public ErrorAnnotationService getIfAvailable() {
                return null;
            }

            @Override
            public ErrorAnnotationService getIfUnique() {
                return null;
            }
        };
    }
}
