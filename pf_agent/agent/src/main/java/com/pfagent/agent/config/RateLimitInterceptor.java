package com.pfagent.agent.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

import java.io.IOException;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * F-010 按 IP 固定窗口限频（pf.rate-limit.enabled=true 时装配）
 *
 * /api/chat 当前无鉴权无限制，接口外露存在脚本滥用风险。此拦截器对同一 IP 在每分钟
 * 固定窗口内限制请求次数（默认 20/分），超限返回 429 + JSON 错误体。单实例内存计数
 * 足够（分布式限频属微服务版范畴，D1/D2）。
 *
 * 窗口语义（D2）：每分钟一个窗口，窗口边界允许至多 2 倍突发属已知可接受特性（成本
 * 控制场景不需要精确滑动窗口）。{@link ConcurrentHashMap} 键为 IP，值为
 * [窗口起始分钟, 窗口内计数]；下一分钟首请求覆盖为新窗口。为防长跑进程 IP 泄漏导致
 * map 无限膨胀，活跃键数超过阈值时惰性清理过期窗口项（窗口起始 != 当前分钟）。
 *
 * IP 提取（D3）：默认取 {@link HttpServletRequest#getRemoteAddr()}；trust-forwarded-for
 * 开启（反向代理部署）时取 X-Forwarded-For 首跳，默认关闭防伪造。
 */
@Component
@ConditionalOnProperty(name = "pf.rate-limit.enabled", havingValue = "true")
public class RateLimitInterceptor implements HandlerInterceptor {

    private static final Logger log = LoggerFactory.getLogger(RateLimitInterceptor.class);
    /** 惰性清理阈值：活跃键超过即全量扫除过期窗口，防 map 膨胀 */
    private static final int CLEANUP_THRESHOLD = 10_000;

    private final ConcurrentHashMap<String, long[]> windowCounts = new ConcurrentHashMap<>();

    @Value("${pf.rate-limit.per-minute:20}")
    private int perMinute;
    @Value("${pf.rate-limit.trust-forwarded-for:false}")
    private boolean trustForwardedFor;
    @Autowired
    private ObjectMapper objectMapper;

    @Override
    public boolean preHandle(HttpServletRequest request,
                             HttpServletResponse response,
                             Object handler) throws IOException {
        String ip = resolveClientIp(request);
        long windowStart = nowWindowStart();
        long count = windowCounts.compute(ip, (key, current) -> {
            if (current == null || current[0] != windowStart) {
                return new long[]{windowStart, 1};
            }
            current[1]++;
            return current;
        })[1];

        if (windowCounts.size() > CLEANUP_THRESHOLD) {
            cleanupExpiredWindows();
        }

        if (count > perMinute) {
            writeRateLimited(response, windowStart);
            return false;
        }
        return true;
    }

    /** 解析客户端 IP：trust-forwarded-for 且 XFF 头存在时取首跳（代理前的真实客户端），否则直连地址 */
    private String resolveClientIp(HttpServletRequest request) {
        if (trustForwardedFor) {
            String forwarded = request.getHeader("X-Forwarded-For");
            if (forwarded != null && !forwarded.isBlank()) {
                return forwarded.split(",")[0].trim();
            }
        }
        return request.getRemoteAddr();
    }

    /** 当前固定窗口起始（Unix 分钟粒度）；窗口切换 = 起始分钟变化 */
    private long nowWindowStart() {
        return System.currentTimeMillis() / 1_000 / 60;
    }

    /** 写 429 + JSON 错误体；retryAfterSeconds = 距本分钟窗口结束的秒数 */
    private void writeRateLimited(HttpServletResponse response, long windowStart) throws IOException {
        // Servlet API 无常量（SC_TOO_MANY_REQUESTS 仅在 HTTP 规范），429 用字面量
        response.setStatus(429);
        response.setContentType("application/json");
        response.setCharacterEncoding("UTF-8");
        long retryAfterSeconds = 60 - (System.currentTimeMillis() / 1_000 - windowStart * 60);
        objectMapper.writeValue(response.getWriter(), Map.of(
                "error", "rate_limited",
                "message", "请求过于频繁，请稍后再试",
                "retryAfterSeconds", Math.max(retryAfterSeconds, 1)));
    }

    /** 惰性清理：删除窗口起始非当前分钟的条目（已离开的 IP 不再有新请求，防永久残留） */
    private void cleanupExpiredWindows() {
        long windowStart = nowWindowStart();
        windowCounts.entrySet().removeIf(entry -> entry.getValue()[0] != windowStart);
        log.debug("限频窗口惰性清理完成，剩余活跃键 {}", windowCounts.size());
    }
}
