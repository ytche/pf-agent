package com.pfagent.agent.chat;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 来源展示标题兜底（F-002 / KN204 / KN219）：只作用于对外展示字段，不触检索原始 title。
 *
 * 覆盖三种形态：空 title → 正文首个有效行（去 Markdown/表格符号，40 字截断）；
 * 无有效正文 → tocPath 末段；冒号结尾去冒号；>60 字截断。
 */
class SourceTitleFormatterTest {

    /** 正常 title 原样展示（仅做去尾冒号与长度兜底），不取正文 */
    @Test
    void keepsNormalTitleWithoutFallingBackToBody() {
        String title = SourceTitleFormatter.displayTitle("火球术", "正文首行", "法术 > 火球术");

        assertThat(title).isEqualTo("火球术");
    }

    /** 空 title → 正文首个有效行，去掉 Markdown 标题符号 */
    @Test
    void blankTitleFallsBackToFirstBodyLineWithoutMarkdownMarks() {
        String title = SourceTitleFormatter.displayTitle("", "# 诱因（Catalyst）\n在游戏的故事中……", "规则 > 诱因");

        assertThat(title).isEqualTo("诱因（Catalyst）");
    }

    /** 首行为表格分隔线/纯符号：向下取首个有效行，并去掉表格与强调符号 */
    @Test
    void blankTitleSkipsSymbolOnlyLinesToFirstMeaningfulLine() {
        String title = SourceTitleFormatter.displayTitle(null,
                "| --- | --- |\n|  |\n**怪物特殊能力**\n正文",
                "怪物 > 特殊能力");

        assertThat(title).isEqualTo("怪物特殊能力");
    }

    /** 空 title 的正文首行超过 40 字：40 字 + 省略号 */
    @Test
    void blankTitleTruncatesBodyLineToFortyCharsWithEllipsis() {
        String body = "追逐".repeat(30); // 60 字

        String title = SourceTitleFormatter.displayTitle("", body, "规则 > 追逐");

        assertThat(title).isEqualTo("追逐".repeat(20) + "…");
    }

    /** 正文首行不足 40 字：不补省略号 */
    @Test
    void blankTitleKeepsShortBodyLineWithoutEllipsis() {
        String title = SourceTitleFormatter.displayTitle("", "> 休整期\n正文", null);

        assertThat(title).isEqualTo("休整期");
    }

    /** 全文无有效文本（空白/纯符号）→ 回退 tocPath 末段 */
    @Test
    void blankTitleWithNoMeaningfulBodyFallsBackToLastTocSegment() {
        String title = SourceTitleFormatter.displayTitle("  ", "| --- | --- |\n\n***", "规则 → 战斗 → 追逐与休整");

        assertThat(title).isEqualTo("追逐与休整");
    }

    /** tocPath 支持 ">" 与 "/" 分隔：取最后一个非空段 */
    @Test
    void lastTocSegmentSupportsSlashAndGreaterThanSeparators() {
        assertThat(SourceTitleFormatter.displayTitle("", "", "核心职业/盗贼/page_49.md"))
                .isEqualTo("page_49.md");
        assertThat(SourceTitleFormatter.displayTitle(null, null, "怪物 > 特殊能力 > "))
                .isEqualTo("特殊能力");
    }

    /** 冒号结尾（中文全角与英文半角）去除 */
    @Test
    void stripsTrailingChineseAndEnglishColon() {
        assertThat(SourceTitleFormatter.displayTitle("诱因（Catalyst）：", "正文", "规则"))
                .isEqualTo("诱因（Catalyst）");
        assertThat(SourceTitleFormatter.displayTitle("Grapple:", "正文", "规则"))
                .isEqualTo("Grapple");
    }

    /** 仅由冒号组成的 title 视为空 → 继续按正文/tocPath 兜底 */
    @Test
    void colonOnlyTitleIsTreatedAsBlank() {
        assertThat(SourceTitleFormatter.displayTitle("：", "首行有效正文", "规则 > 条目"))
                .isEqualTo("首行有效正文");
    }

    /** 非空 title 超过 60 字：60 字 + 省略号 */
    @Test
    void truncatesLongTitleToSixtyCharsWithEllipsis() {
        String longTitle = "长".repeat(80);

        String title = SourceTitleFormatter.displayTitle(longTitle, "正文", "规则");

        assertThat(title).isEqualTo("长".repeat(60) + "…");
    }

    /** 恰好 60 字不截断 */
    @Test
    void keepsTitleAtSixtyCharsUnchanged() {
        String title60 = "长".repeat(60);

        assertThat(SourceTitleFormatter.displayTitle(title60, "正文", "规则")).isEqualTo(title60);
    }

    /** title / 正文 / tocPath 全缺：返回空串（前端可继续回退书名字段），不抛异常 */
    @Test
    void allSourcesMissingYieldsEmptyTitle() {
        assertThat(SourceTitleFormatter.displayTitle(null, null, null)).isEmpty();
        assertThat(SourceTitleFormatter.displayTitle("", "   \n\t", "   ")).isEmpty();
    }
}
