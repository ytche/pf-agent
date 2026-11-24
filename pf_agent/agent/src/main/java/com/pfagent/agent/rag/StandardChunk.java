package com.pfagent.agent.rag;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.Map;

/**
 * 统一 chunk 行模型（专长/种族/背景特性/装备/技能/规则 六个模块共用）
 *
 * 六个模块的 vectorizer 产物字段结构完全一致（与法术/职业的字段结构不同），
 * 故用一个 StandardChunk 服务全部，避免为每模块重复定义行模型。
 * record 组件按项目 Java 约定使用 lowerCamelCase；JSONL 键名仍是下划线风格，
 * 由 @JsonProperty 保持反序列化兼容（AKN-022）。
 * 注意：sourceConfidence 用包装类型（部分行可能缺省），aliases/metadata/extra
 * 天然可为空（list/map 由 Jackson 容错为空对象）。
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record StandardChunk(
        @JsonProperty("chunk_id") String chunkId,
        @JsonProperty("doc_id") String docId,
        String category,
        @JsonProperty("component_type") String componentType,
        String title,
        String text,
        @JsonProperty("book_abbreviation") String bookAbbreviation,
        @JsonProperty("book_name_cn") String bookNameCn,
        @JsonProperty("book_name_en") String bookNameEn,
        @JsonProperty("source_confidence") Integer sourceConfidence,
        @JsonProperty("chm_toc_path") String chmTocPath,
        List<String> aliases,
        Map<String, Object> metadata,
        Map<String, Object> extra
) {
}
