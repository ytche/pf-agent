package com.pfagent.agent.rag;

import org.springframework.ai.document.Document;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * BookFilter（SP8b J4）：按 chunk metadata 的 {@code book_abbreviation} 做全局书过滤
 *
 * 配置驱动（pf.search.book-filter.*），检索侧默认开启，对 vectorSearch 与
 * searchByMetadata 两条路径统一生效。这是全局检索策略而非工具参数——LLM 侧
 * 不暴露 book 过滤参数（防 LLM 自行构造书名单出错），prompt 零改动。
 *
 * 语义（设计方案 §J4）：
 *  - blacklist：剔除 books 列名值（如脏值 "?"），其余保留；
 *  - whitelist：仅保留 books 列名值；
 *  - 两种模式下，book 值缺失/空白（未知）的条目按 {@code unknown-book-keep}
 *    处理（默认 true 保留，防数据脏期出现假缺口）。
 *
 * whitelist「已知书」集合口径说明：Java 侧不存在现成的权威缩写值域
 * （FilterTranslator 只维护字段名白名单，不含字段值域；数据侧 SOURCE_BOOKS
 * 在 Python 仓库，不在 Java classpath）。故 whitelist 模式简化为：用户配置的
 * books 列表本身即「已知书」集合——值在列表内保留、非空值不在列表内剔除、
 * 空值/未知按 unknown-book-keep。切 whitelist 前的数据清洗责任在数据侧
 * （方案 J4 过渡期 rationale：黑名单剔除确定垃圾值，待清洗完成再切白名单）。
 */
@Component
public class BookFilter {

    /** 总开关：false 时全放行（零行为变化） */
    @Value("${pf.search.book-filter.enabled:true}")
    private boolean enabled;
    /** 模式：blacklist（剔除列名值）| whitelist（仅保留列名值） */
    @Value("${pf.search.book-filter.mode:blacklist}")
    private String mode;
    /** 书名清单：黑名单为剔出值；白名单为仅保留值。默认 ["?"]（过渡策略转正，见方案 J4） */
    @Value("${pf.search.book-filter.books:?}")
    private List<String> books;
    /** book 值缺失/空白（未知）时是否保留（默认 true，防假缺口） */
    @Value("${pf.search.book-filter.unknown-book-keep:true}")
    private boolean unknownBookKeep;

    /** 单条判定：该 Document 是否保留在检索结果中 */
    public boolean keep(Document doc) {
        if (!enabled) {
            return true;
        }
        String book = bookOf(doc);
        if (book.isBlank()) {
            return unknownBookKeep; // book 字段缺失/空白 → 未知，按 unknown-book-keep
        }
        boolean listed = bookSet().contains(book.toLowerCase(Locale.ROOT));
        if ("whitelist".equalsIgnoreCase(mode)) {
            return listed; // 非空值不在白名单内一律剔除（列表即已知书集合，见类注释口径）
        }
        return !listed; // blacklist：剔除列名值
    }

    /** 批量过滤：返回保留的子列表（保持原顺序） */
    public List<Document> filter(List<Document> docs) {
        return docs.stream().filter(this::keep).toList();
    }

    /** book 值归一化集合：去空白 + 大小写不敏感（缩写为 ASCII，防大小写抖动漏剔） */
    private Set<String> bookSet() {
        return books.stream()
                .filter(b -> b != null && !b.isBlank())
                .map(b -> b.trim().toLowerCase(Locale.ROOT))
                .collect(Collectors.toSet());
    }

    /** metadata 安全取 book_abbreviation（缺失/非字符串返回空串 → 归为未知） */
    private String bookOf(Document doc) {
        Object v = doc.getMetadata().get("book_abbreviation");
        return v == null ? "" : v.toString().trim();
    }
}
