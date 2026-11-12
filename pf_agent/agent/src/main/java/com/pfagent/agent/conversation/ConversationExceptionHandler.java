package com.pfagent.agent.conversation;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;

/**
 * 会话与问答错误码映射（前端冻结契约 §5）
 *
 * 401 unauthorized / 403 forbidden / 404 conversation_not_found /
 * 409 conversation_changed / 410 conversation_deleted / 429 quota_exceeded /
 * 400 invalid_request。限频 429 rate_limited 与拦截器 401 由拦截器直接写出。
 */
@RestControllerAdvice(assignableTypes = {ConversationController.class, com.pfagent.agent.chat.ChatController.class})
public class ConversationExceptionHandler {

    @ExceptionHandler(ConversationNotFoundException.class)
    public ResponseEntity<Map<String, String>> notFound(ConversationNotFoundException ex) {
        return body(HttpStatus.NOT_FOUND, "conversation_not_found", ex.getMessage());
    }

    @ExceptionHandler(ConversationForbiddenException.class)
    public ResponseEntity<Map<String, String>> forbidden(ConversationForbiddenException ex) {
        return body(HttpStatus.FORBIDDEN, "forbidden", ex.getMessage());
    }

    @ExceptionHandler(ConversationDeletedException.class)
    public ResponseEntity<Map<String, String>> deleted(ConversationDeletedException ex) {
        return body(HttpStatus.GONE, "conversation_deleted", ex.getMessage());
    }

    @ExceptionHandler(ConversationConflictException.class)
    public ResponseEntity<Map<String, String>> conflict(ConversationConflictException ex) {
        return body(HttpStatus.CONFLICT, "conversation_changed", ex.getMessage());
    }

    @ExceptionHandler(ConversationQuotaExceededException.class)
    public ResponseEntity<Map<String, Object>> quota(ConversationQuotaExceededException ex) {
        return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS).body(Map.of(
                "error", "quota_exceeded",
                "message", ex.getMessage(),
                "limit", ex.getLimit()));
    }

    @ExceptionHandler(UnauthorizedException.class)
    public ResponseEntity<Map<String, String>> unauthorized(UnauthorizedException ex) {
        return body(HttpStatus.UNAUTHORIZED, "unauthorized", ex.getMessage());
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> invalidRequest(IllegalArgumentException ex) {
        return body(HttpStatus.BAD_REQUEST, "invalid_request", ex.getMessage());
    }

    private static ResponseEntity<Map<String, String>> body(HttpStatus status, String error, String message) {
        return ResponseEntity.status(status).body(Map.of("error", error, "message", message));
    }
}
