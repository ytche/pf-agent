package com.pfagent.agent.rag;

import java.util.ArrayList;
import java.util.List;

/**
 * 展示层文本清洗工具（KN207）。
 *
 * 仓库内部整理路径行「> 来源：XXX，页码见原书，未整理 → XX → YY」对 LLM 与用户都是噪声，
 * 但数据侧需保留作 toc 回填追溯用（用户拍板）——因此只在展示出口剥离，落盘 chunk 与
 * embedding 不动。匹配规则保守（宁漏勿错）：仅当一行 trim 后以「> 来源：」开头且含
 * 「未整理 →」/「未整理→」才删除，不含该标记的「> 来源：」行保留。
 */
public final class TextSanitizer {

    private static final String SOURCE_LINE_PREFIX = "> 来源：";
    private static final String MARKER_WITH_SPACE = "未整理 →";
    private static final String MARKER_NO_SPACE = "未整理→";

    private TextSanitizer() {
        // 工具类禁止实例化
    }

    /**
     * 剥离仓库内部整理路径行：逐行删除「> 来源：」开头且含「未整理 →」/「未整理→」的整行，
     * 剥离后把因此产生的连续空行坍缩为一个、文末空行直接去掉。
     * 不含可剥离行的文本原样返回；null/空串安全返回原值。
     */
    public static String stripInternalSourceLine(String text) {
        if (text == null || text.isEmpty()) {
            return text;
        }
        String[] lines = text.split("\n", -1);
        for (String line : lines) {
            if (isInternalSourceLine(line)) {
                return rebuild(lines);
            }
        }
        return text;
    }

    /** 判断一行是否为仓库内部整理路径行（宁漏勿错：两个条件同时满足才删） */
    private static boolean isInternalSourceLine(String line) {
        String trimmed = line.trim();
        return trimmed.startsWith(SOURCE_LINE_PREFIX)
                && (trimmed.contains(MARKER_WITH_SPACE) || trimmed.contains(MARKER_NO_SPACE));
    }

    /**
     * 重建文本：剔除内部行后按行拼接，空行只保留一个（行首/文末空行去掉）。
     * 空行占位与下行分隔都由「\n」承担：空行分支追加一个占位换行，下行非空时再补分隔，
     * 两个换行恰好构成一个空行；连续空行在占位后由 lastWasBlank 短路跳过。
     */
    private static String rebuild(String[] lines) {
        List<String> kept = new ArrayList<>();
        for (String line : lines) {
            if (!isInternalSourceLine(line)) {
                kept.add(line);
            }
        }
        StringBuilder sb = new StringBuilder();
        boolean first = true;
        boolean lastWasBlank = false;
        for (String line : kept) {
            if (line.isBlank()) {
                if (first || lastWasBlank) {
                    continue;
                }
                sb.append('\n');
                lastWasBlank = true;
                first = false;
            } else {
                if (!first) {
                    sb.append('\n');
                }
                sb.append(line);
                lastWasBlank = false;
                first = false;
            }
        }
        // 去掉文末空行（末尾残留的换行占位）
        int len = sb.length();
        while (len > 0 && sb.charAt(len - 1) == '\n') {
            len--;
        }
        sb.setLength(len);
        return sb.toString();
    }
}
