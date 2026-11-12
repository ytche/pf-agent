package com.pfagent.agent.telemetry;

import com.pfagent.agent.rag.ToolCallRecorder;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * RecorderBytecode 自检（F-021 回归锁的「锁是否真的能锁」）
 *
 * {@code FeedbackRecorderMemoryModeTest.bytecodeReferencesNoFileWriteApi} /
 * {@code DataGapRecorderMemoryModeTest.bytecodeReferencesNoFileWriteApi} 依赖本工具
 * 判断「记录器不再引用文件写入 API」。若扫描本身失效（定位不到 class、编码/断言写错），
 * 那些断言会永远通过而毫无保护——故这里用**阳性对照**证明扫描能识别真的写文件类。
 *
 * 阳性对照取本轮唯一仍落文件的 recorder {@link ToolCallRecorder}（tool_calls.jsonl，不在
 * F-021 范围）。若它将来也被迁到 DB，把对照换成任一仍引用 java.nio.file.Files 的类即可。
 */
class RecorderBytecodeTest {

    /** 阳性对照：真写文件的类必须被判出文件 API（否则回归锁是空的） */
    @Test
    void scannerDetectsClassThatWritesFiles() throws Exception {
        assertThat(RecorderBytecode.symbolsOf(ToolCallRecorder.class))
                .contains("java/nio/file/Files");
    }

    /** 阴性对照：已改库的两个 recorder 不得出现文件 API */
    @Test
    void scannerFindsNoFileApiInMigratedRecorders() throws Exception {
        assertThat(RecorderBytecode.symbolsOf(com.pfagent.agent.chat.FeedbackRecorder.class))
                .doesNotContain("java/nio/file/Files");
        assertThat(RecorderBytecode.symbolsOf(com.pfagent.agent.rag.DataGapRecorder.class))
                .doesNotContain("java/nio/file/Files");
    }
}
