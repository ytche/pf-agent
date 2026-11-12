package com.pfagent.agent.chat;

/**
 * 错误标注提交响应
 *
 * ok=true 表示已入库（id 为记录 ID，供前端/分析定位）；ok=false 表示未入库
 * （数据库未装配或写入失败），此时 id 为 null、reason 标注降级原因——
 * 前端据此提示失败，不再出现「写入失败仍回 id、用户以为成功」的谎报。
 *
 * reason 取值分两类：服务端降级（{@link #REASON_DB_UNAVAILABLE} 库不可用 /
 * {@link #REASON_WRITE_FAILED} 写失败）对应 503；客户端入参非法
 * （{@link #REASON_INVALID_INPUT}，如字段超长）对应 400——见 ChatController.feedback。
 */
public record FeedbackResponse(boolean ok, String id, String reason) {

    /** 降级原因：数据库不可用（pf.chat.memory != jdbc，memory 模式不记录） */
    public static final String REASON_DB_UNAVAILABLE = "db_unavailable";
    /** 降级原因：数据库写入失败 */
    public static final String REASON_WRITE_FAILED = "write_failed";
    /** 拒绝原因：入参非法（超长字段等），调用方回 4xx——客户端问题不是服务端降级 */
    public static final String REASON_INVALID_INPUT = "invalid_input";

    /** 入库成功 */
    public static FeedbackResponse persisted(String id) {
        return new FeedbackResponse(true, id, null);
    }

    /** 未入库（降级）：不返回 id，避免前端误以为已记录 */
    public static FeedbackResponse failed(String reason) {
        return new FeedbackResponse(false, null, reason);
    }
}
