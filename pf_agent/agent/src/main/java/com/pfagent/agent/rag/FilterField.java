package com.pfagent.agent.rag;

/**
 * 翻译后的扁平过滤条件
 *
 * {@code key} 是向量库 metadata 的实际顶层键（如 spell_level_女巫 / class_name），
 * {@code value} 是精确匹配值。多个条件之间语义为 AND（见 SearchService.searchByMetadata）。
 */
public record FilterField(String key, String value) {
}
