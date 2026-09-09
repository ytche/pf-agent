package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * TextSanitizer 单元测试（KN207 展示层剥离）
 *
 * 匹配规则（宁漏勿错）：逐行处理，仅当一行同时满足 ①trim 后以「> 来源：」开头、
 * ②含「未整理 →」或「未整理→」——删除该行；剥离后把因此产生的连续空行坍缩为一个、
 * 文末空行直接去掉；不含该行的文本原样返回。
 */
class TextSanitizerTest {

    /** 标准行剥离：整行消失，上下文行保留 */
    @Test
    void stripsStandardInternalSourceLine() {
        String text = "法术正文\n"
                + "> 来源：亡灵杀手手册（Undead Slayer's Handbook），页码见原书，未整理 → 亡灵杀手手册 → 法术\n"
                + "生效条件";

        String result = TextSanitizer.stripInternalSourceLine(text);

        assertThat(result).doesNotContain("未整理 →");
        assertThat(result).doesNotContain("> 来源：亡灵杀手手册");
        assertThat(result).contains("法术正文");
        assertThat(result).contains("生效条件");
        assertThat(result).isEqualTo("法术正文\n生效条件");
    }

    /** 无空格变体「未整理→」同样剥离 */
    @Test
    void stripsMarkerWithoutSpaceVariant() {
        String text = "> 来源：反派法典（Villain Codex），页码见原书，未整理→反派法典 → 法术\n"
                + "正文保留";

        String result = TextSanitizer.stripInternalSourceLine(text);

        assertThat(result).doesNotContain("未整理→");
        assertThat(result).isEqualTo("正文保留");
    }

    /** 以「> 来源：」开头但不含「未整理 →」的行保留（防御误判） */
    @Test
    void keepsSourceLineWithoutMarker() {
        String text = "正文\n> 来源：核心规则书（Core Rulebook）\n更多正文";

        String result = TextSanitizer.stripInternalSourceLine(text);

        assertThat(result).isEqualTo(text);
        assertThat(result).contains("> 来源：核心规则书（Core Rulebook）");
    }

    /** 不含该行的文本原样返回；null/空串安全 */
    @Test
    void returnsTextUnchangedWhenNoInternalLine() {
        String plain = "普通正文内容，没有整理路径行";
        assertThat(TextSanitizer.stripInternalSourceLine(plain)).isEqualTo(plain);
    }

    @Test
    void nullAndEmptyAreSafe() {
        assertThat(TextSanitizer.stripInternalSourceLine(null)).isNull();
        assertThat(TextSanitizer.stripInternalSourceLine("")).isEmpty();
    }

    /** 剥离后空行坍缩：删行在中间时，其前后空行合并为一个，文末空行去掉 */
    @Test
    void collapsesConsecutiveBlankLinesAfterStrip() {
        String text = "前文\n\n> 来源：亡灵杀手手册（Undead Slayer's Handbook），页码见原书，未整理 → 亡灵杀手手册 → 法术\n\n后文\n";

        String result = TextSanitizer.stripInternalSourceLine(text);

        // 删行前后各一个空行 → 坍缩为一个；文末换行去掉
        assertThat(result).isEqualTo("前文\n\n后文");
        assertThat(result).doesNotContain("\n\n\n");
    }

    /** 删除行后两行直接相邻（原文无空行）→ 不凭空插入空行 */
    @Test
    void noExtraBlankLineWhenLinesAdjacent() {
        String text = "法术正文\n> 来源：亡灵杀手手册（Undead Slayer's Handbook），页码见原书，未整理 → 亡灵杀手手册 → 法术\n生效条件";

        String result = TextSanitizer.stripInternalSourceLine(text);

        assertThat(result).isEqualTo("法术正文\n生效条件");
    }
}
