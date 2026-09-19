package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.springframework.ai.document.Document;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * BookFilter 单元测试（SP8b J4）
 *
 * 覆盖：
 *  - blacklist：剔除列名值（"?"）/保留正常书
 *  - whitelist：保留列名书/剔除非列名书
 *  - unknown-book-keep true/false 两路（book 字段缺失/空白归为未知）
 *  - enabled=false 全放行
 *  - 大小写不敏感匹配（缩写为 ASCII）
 */
class BookFilterTest {

    private static Document doc(String book) {
        Map<String, Object> meta = book == null ? Map.of() : Map.of("book_abbreviation", book);
        return Document.builder().text("text").metadata(meta).build();
    }

    /** 默认形态（blacklist ["?"] + unknownBookKeep=true，与 application.yml 默认一致） */
    private static BookFilter filter(boolean enabled, String mode, List<String> books, boolean unknownBookKeep) {
        BookFilter f = new BookFilter();
        ReflectionTestUtils.setField(f, "enabled", enabled);
        ReflectionTestUtils.setField(f, "mode", mode);
        ReflectionTestUtils.setField(f, "books", books);
        ReflectionTestUtils.setField(f, "unknownBookKeep", unknownBookKeep);
        return f;
    }

    /** blacklist：剔除列名脏值 "?"，保留正常书 */
    @Test
    void blacklistRemovesListedValueAndKeepsNormalBooks() {
        BookFilter f = filter(true, "blacklist", List.of("?"), true);
        Document crb = doc("CRB");
        Document apg = doc("APG");
        assertThat(f.keep(doc("?"))).isFalse();
        assertThat(f.keep(crb)).isTrue();
        assertThat(f.filter(List.of(doc("?"), crb, apg))).containsExactly(crb, apg);
    }

    /** blacklist：大小写不敏感，"?" 的任何大小写变体都被剔除 */
    @Test
    void blacklistMatchesCaseInsensitively() {
        BookFilter f = filter(true, "blacklist", List.of("CRB"), true);
        assertThat(f.keep(doc("crb"))).isFalse();
        assertThat(f.keep(doc("CrB"))).isFalse();
    }

    /** whitelist：仅保留列名书，列表外非空值剔除 */
    @Test
    void whitelistKeepsListedBooksAndRemovesOthers() {
        BookFilter f = filter(true, "whitelist", List.of("CRB", "APG"), true);
        assertThat(f.keep(doc("CRB"))).isTrue();
        assertThat(f.keep(doc("APG"))).isTrue();
        assertThat(f.keep(doc("XYZ"))).isFalse();
        assertThat(f.keep(doc("怪物"))).isFalse();
    }

    /** unknown-book-keep=true：book 缺失/空白条目保留（防假缺口） */
    @Test
    void unknownBookKeptWhenUnknownBookKeepIsTrue() {
        BookFilter f = filter(true, "blacklist", List.of("?"), true);
        assertThat(f.keep(doc(null))).isTrue(); // metadata 完全缺 book 字段
        BookFilter fw = filter(true, "whitelist", List.of("CRB"), true);
        assertThat(fw.keep(doc(null))).isTrue();
        assertThat(fw.keep(doc("  "))).isTrue(); // 空白同样归为未知
    }

    /** unknown-book-keep=false：book 缺失/空白条目剔除 */
    @Test
    void unknownBookRemovedWhenUnknownBookKeepIsFalse() {
        BookFilter f = filter(true, "blacklist", List.of("?"), false);
        assertThat(f.keep(doc(null))).isFalse();
        BookFilter fw = filter(true, "whitelist", List.of("CRB"), false);
        assertThat(fw.keep(doc(null))).isFalse();
    }

    /** enabled=false：全放行（零行为变化） */
    @Test
    void disabledKeepsEverything() {
        BookFilter f = filter(false, "blacklist", List.of("?"), false);
        assertThat(f.keep(doc("?"))).isTrue();
        assertThat(f.keep(doc(null))).isTrue();
        assertThat(f.filter(List.of(doc("?"), doc(null), doc("CRB")))).hasSize(3);
    }

    /** filter 批量过滤保持原顺序且只剔除列名值 */
    @Test
    void filterBatchPreservesOrderAndDropsListed() {
        BookFilter f = filter(true, "blacklist", List.of("?"), true);
        Document a = doc("CRB");
        Document b = doc("?");
        Document c = doc(null);
        Document d = doc("APG");
        assertThat(f.filter(List.of(a, b, c, d))).containsExactly(a, c, d);
    }

    /** 边界（QA 补测）：metadata book 值首尾空白先归一再匹配——" CRB " 视为 CRB */
    @Test
    void bookValueSurroundingWhitespaceIsTrimmedBeforeMatching() {
        BookFilter f = filter(true, "blacklist", List.of("CRB"), true);
        assertThat(f.keep(doc(" CRB "))).isFalse();
        assertThat(f.keep(doc("\tCRB\n"))).isFalse();
        BookFilter fw = filter(true, "whitelist", List.of("CRB"), true);
        assertThat(fw.keep(doc(" crb "))).isTrue();
    }

    /** 边界（QA 补测）：whitelist + books 为空列表 → 全部已知书剔除，未知值仍按 unknown-book-keep */
    @Test
    void whitelistWithEmptyBooksListRemovesAllKnownBooks() {
        BookFilter kept = filter(true, "whitelist", List.of(), true);
        assertThat(kept.keep(doc("CRB"))).isFalse();
        assertThat(kept.keep(doc("?"))).isFalse();
        assertThat(kept.keep(doc(null))).isTrue(); // 未知保留
        BookFilter dropped = filter(true, "whitelist", List.of(), false);
        assertThat(dropped.keep(doc(null))).isFalse();
    }

    /** 边界（QA 补测）：metadata 值为非字符串（数字等）→ toString 归一参与匹配，不抛异常 */
    @Test
    void nonStringBookMetadataValueHandledGracefully() {
        Document numeric = Document.builder().text("t")
                .metadata(Map.of("book_abbreviation", 404)).build();
        BookFilter f = filter(true, "blacklist", List.of("?"), true);
        assertThat(f.keep(numeric)).isTrue(); // "404" 非黑名单值，保留
    }

    /** 边界（QA 补测）：仅大小写归一、不做全半角归一——全角 "？" 不等于半角 "?"
     * （KN228 的 92 条 '?' 为 ASCII；若未来数据侧出现全角问号需另登记处理） */
    @Test
    void fullWidthQuestionMarkNotMatchedByAsciiBlacklist() {
        BookFilter f = filter(true, "blacklist", List.of("?"), true);
        assertThat(f.keep(doc("？"))).isTrue();
    }
}
