package com.pfagent.agent.rag;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.util.List;
import java.util.Map;

/**
 * 法术 chunk 的 JSONL 行模型（对应 vectorizer 输出 chunks.jsonl 的一行）
 *
 * 只解析索引和来源追溯需要的字段；嵌套 metadata 保留原始结构，
 * 后续要基于学派/等级过滤检索结果时可直接使用。
 * 忽略未知字段（如后续向量化版本新增的其他字段），保证兼容。
 * SP8c J6：补 base_spell_* 三字段——神话变体法术行顶层的结构化"基础法术"指针
 * （257 条链），是 Layer 0 引用链"基础/变体"边的唯一结构化来源。
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
        Map<String, Object> extra,
        String base_spell_chunk_id,
        String base_spell_title,
        String base_spell_book
) {
}
