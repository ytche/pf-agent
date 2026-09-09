package com.pfagent.agent.rag;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.util.List;
import java.util.Map;

/**
 * 法术 chunk 的 JSONL 行模型（对应 vectorizer 输出 chunks.jsonl 的一行）
 *
 * 只解析索引和来源追溯需要的字段；嵌套 metadata 保留原始结构，
 * 后续要基于学派/等级过滤检索结果时可直接使用。
 * 忽略未知字段（如后续向量化版本新增的 base_spell_chunk_id 等），保证兼容。
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record SpellChunk(
        String chunk_id,
        String doc_id,
        String category,
        String component_type,
        String title,
        String text,
        String book_abbreviation,
        String book_name_cn,
        String book_name_en,
        int source_confidence,
        List<String> aliases,
        Map<String, Object> metadata,
        Map<String, Object> extra
) {
}
