package com.pfagent.agent.rag;

import com.pfagent.agent.telemetry.DataGapService;
import com.pfagent.agent.telemetry.RecorderBytecode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.test.util.ReflectionTestUtils;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * DataGapRecorder 降级测试（F-021，memory / DB 不可用）
 *
 * 用户拍板（2026-09-24）：memory（DB 不可用）模式下**不记录**——不保留文件兼容/双写，
 * 也不谎报成功。本类锁定：
 *  - record 返回 false（调用方 RetrievalTools 据此不置 gapReported、据实回话）
 *  - listGaps 返回「库不可用」标记（available=false），与「库可用但无记录」区分
 *  - 记录器不再有任何文件落盘通路（字节码回归锁，见 FeedbackRecorderMemoryModeTest 说明）
 */
class DataGapRecorderMemoryModeTest {

    @Test
    void recordWithoutDatabaseReportsFailure() {
        DataGapRecorder recorder = new DataGapRecorder();
        ReflectionTestUtils.setField(recorder, "gapServiceProvider", emptyProvider());

        assertThat(recorder.record("q", "f", "r")).isFalse();
    }

    /** 读侧不得把「库不可用」说成「暂无记录」 */
    @Test
    void listGapsWithoutDatabaseReportsUnavailable() {
        DataGapRecorder recorder = new DataGapRecorder();
        ReflectionTestUtils.setField(recorder, "gapServiceProvider", emptyProvider());

        DataGapRecorder.GapQueryResult result = recorder.listGaps(20, null);

        assertThat(result.available()).isFalse();
        assertThat(result.gaps()).isEmpty();
    }

    /** 字节码不得引用任何文件写入 API（含路径类型），锁死「DB 不可用时回退写 jsonl」的路径 */
    @Test
    void bytecodeReferencesNoFileWriteApi() throws Exception {
        assertThat(RecorderBytecode.symbolsOf(DataGapRecorder.class))
                .doesNotContain("java/nio/file/Files")
                .doesNotContain("java/nio/file/Path")
                .doesNotContain("java/io/FileWriter")
                .doesNotContain("java/io/FileOutputStream")
                .doesNotContain("java/io/RandomAccessFile")
                .doesNotContain("java/io/PrintWriter")
                .doesNotContain("java/io/BufferedWriter");
    }

    private static ObjectProvider<DataGapService> emptyProvider() {
        return new ObjectProvider<>() {
            @Override
            public DataGapService getObject() {
                throw new IllegalStateException("no bean");
            }

            @Override
            public DataGapService getObject(Object... args) {
                throw new IllegalStateException("no bean");
            }

            @Override
            public DataGapService getIfAvailable() {
                return null;
            }

            @Override
            public DataGapService getIfUnique() {
                return null;
            }
        };
    }
}
