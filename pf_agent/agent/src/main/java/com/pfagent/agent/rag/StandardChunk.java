package com.pfagent.agent.rag;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.util.List;
import java.util.Map;

/**
 * 统一 chunk 行模型（专长/种族/背景特性/装备/技能/规则 六个模块共用）
 *
 * 六个模块的 vectorizer 产物字段结构完全一致（与法术/职业的字段结构不同），
 * 故用一个 StandardChunk 服务全部，避免为每模块重复定义行模型。
 * 字段与 Python 侧 JSONL 顶部键一一对应；忽略未知字段保持兼容。
 * 注意：source_confidence 用包装类型（部分行可能缺省），aliases/metadata/extra
 * 天然可为空（list/map 由 Jackson 容错为空对象）。
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record StandardChunk(
        String chunk_id,
        String doc_id,
        String category,
        String component_type,
        String title,
        String text,
        String book_abbreviation,
        String book_name_cn,
        String book_name_en,
        Integer source_confidence,
        String chm_toc_path,
        List<String> aliases,
        Map<String, Object> metadata,
        Map<String, Object> extra
) {
}
