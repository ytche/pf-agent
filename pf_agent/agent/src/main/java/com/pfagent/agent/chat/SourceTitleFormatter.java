package com.pfagent.agent.chat;

import java.util.regex.Pattern;

/**
 * 来源展示标题兜底（F-002 / KN204 / KN219）
 *
 * 只作用于对外展示字段（{@link ChatResponse.SourceRef#title()}），检索匹配仍用原始
 * title 元数据——本类不参与过滤/排序，也不改写 Document 或落盘快照。
 *
 * 规则（设计 Spec 已确认）：
 *  - 非空 title：去尾部中英文冒号；超过 60 字截断加省略号。
 *  - 空 title：取正文首个有效行，去 Markdown/表格符号后截断 40 字加省略号；
 *    首行为空或纯符号时继续向下取，全文无有效文本回退 tocPath 末段。
 *  - tocPath 末段同样做去尾冒号与 60 字兜底（复用展示口径，不另立规则）。
 */
final class SourceTitleFormatter {

    /** 正文首行兜底标题上限（字） */
    private static final int BODY_TITLE_MAX_CHARS = 40;

    /** 任意展示标题上限（字） */
    private static final int DISPLAY_TITLE_MAX_CHARS = 60;

    private static final String ELLIPSIS = "…";

    /** Markdown 标题前缀（# / ## …） */
    private static final Pattern HEADING_PREFIX = Pattern.compile("^#{1,6}\\s*");
    /** 引用块前缀（可重复） */
    private static final Pattern QUOTE_PREFIX = Pattern.compile("^(?:>\\s*)+");
    /** 列表前缀（无序 - * + 或有序 1. / 1、） */
    private static final Pattern LIST_PREFIX = Pattern.compile("^(?:[-*+]\\s+|\\d+[.)、]\\s*)");
    /** Markdown 强调/行内代码/表格竖线符号 */
    private static final Pattern MARKDOWN_SYMBOL = Pattern.compile("[*_`|]+");
    private static final Pattern WHITESPACE = Pattern.compile("\\s+");
    /** 至少含一个文字或数字才算「有效」行（纯符号/表格分隔线被跳过） */
    private static final Pattern MEANINGFUL = Pattern.compile(".*[\\p{L}\\p{N}].*", Pattern.DOTALL);
    /** tocPath 段分隔：箭头/大于号/斜杠，两侧空白一并吃掉 */
    private static final Pattern TOC_SEPARATOR = Pattern.compile("\\s*(?:→|>|/)\\s*");

    private SourceTitleFormatter() {
        // 工具类禁止实例化
    }

    /**
     * 组装对外展示标题。
     *
     * @param title   原始 title 元数据（可为 null/空）
     * @param text    chunk 正文（空 title 时取首个有效行兜底）
     * @param tocPath 目录路径（正文无有效文本时取末段兜底）
     * @return 展示标题；三个来源都无内容时返回空串
     */
    static String displayTitle(String title, String text, String tocPath) {
        String normalized = normalizeTitle(title);
        if (!normalized.isBlank()) {
            return normalized;
        }
        String bodyLine = firstMeaningfulLine(text);
        if (bodyLine != null) {
            return truncate(bodyLine, BODY_TITLE_MAX_CHARS);
        }
        return normalizeTitle(lastTocSegment(tocPath));
    }

    /** 展示标题通用口径：去尾中英文冒号 → 超过 60 字截断加省略号 */
    private static String normalizeTitle(String title) {
        if (title == null || title.isBlank()) {
            return "";
        }
        return truncate(stripTrailingColon(title.strip()), DISPLAY_TITLE_MAX_CHARS);
    }

    /** 正文首个有效行：逐行去 Markdown/表格符号，纯符号行跳过；无有效行返回 null */
    private static String firstMeaningfulLine(String text) {
        if (text == null || text.isBlank()) {
            return null;
        }
        for (String rawLine : text.split("\n", -1)) {
            String line = cleanBodyLine(rawLine);
            if (MEANINGFUL.matcher(line).matches()) {
                return line;
            }
        }
        return null;
    }

    /** 去 Markdown/表格符号并压缩空白；清洗后可能为空（纯符号行） */
    private static String cleanBodyLine(String rawLine) {
        String line = rawLine.strip();
        line = HEADING_PREFIX.matcher(line).replaceFirst("");
        line = QUOTE_PREFIX.matcher(line).replaceFirst("");
        line = LIST_PREFIX.matcher(line).replaceFirst("");
        line = MARKDOWN_SYMBOL.matcher(line).replaceAll("");
        return WHITESPACE.matcher(line).replaceAll(" ").strip();
    }

    /** 去尾部中英文冒号（连续冒号一并去掉），再去两端空白 */
    private static String stripTrailingColon(String title) {
        int end = title.length();
        while (end > 0) {
            char c = title.charAt(end - 1);
            if (c != '：' && c != ':' && c != '﹕') {
                break;
            }
            end--;
        }
        return title.substring(0, end).strip();
    }

    /** tocPath 最后一个非空段；空路径返回空串 */
    private static String lastTocSegment(String tocPath) {
        if (tocPath == null || tocPath.isBlank()) {
            return "";
        }
        String[] segments = TOC_SEPARATOR.split(tocPath);
        for (int i = segments.length - 1; i >= 0; i--) {
            if (!segments[i].isBlank()) {
                return segments[i].strip();
            }
        }
        return "";
    }

    /** 按码点截断（不劈开代理对），超长时补省略号 */
    private static String truncate(String text, int maxChars) {
        if (text.codePointCount(0, text.length()) <= maxChars) {
            return text;
        }
        return text.substring(0, text.offsetByCodePoints(0, maxChars)) + ELLIPSIS;
    }
}
