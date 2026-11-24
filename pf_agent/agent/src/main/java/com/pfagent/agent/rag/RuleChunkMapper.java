package com.pfagent.agent.rag;

import org.springframework.ai.document.Document;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

/**
 * 规则 chunk → Document 映射（StandardChunk 扁平化扩展，KN221）
 *
 * 复用 StandardChunkMapper 的统一映射（来源书 / tocPath / title 等溯源约定），
 * 额外把规则表格标记从 nested metadata 扁平化为 Document 顶层键：
 * has_table / table_ids / table_titles / table_row_counts（数据侧 rule.py 写入，
 * 与 rule_tables.json 同源于 vectorizer/rule_tables.py）。
 *
 * 只透传这 4 键（spec D6），正文与 chunk_id 不变；缺省键经 putNonNull 跳过，
 * 与 ProfessionChunkMapper 口径一致。规则向量库重建后 Document metadata
 * 即可直接暴露表格信号，无需再解析嵌套结构。
 */
@Component
public class RuleChunkMapper implements ChunkMapper<StandardChunk> {

    /** 规则 chunk metadata 的表格标记键（KN221 D6，值与规则解析器同源） */
    static final List<String> TABLE_METADATA_KEYS =
            List.of("has_table", "table_ids", "table_titles", "table_row_counts");

    @Autowired
    private StandardChunkMapper baseMapper;

    @Override
    public Document toDocument(StandardChunk c) {
        Document doc = baseMapper.toDocument(c);
        Map<String, Object> meta = doc.getMetadata();
        Map<String, Object> nested = c.metadata() == null ? Map.of() : c.metadata();
        for (String key : TABLE_METADATA_KEYS) {
            putNonNull(meta, key, nested.get(key));
        }
        return doc;
    }

    private void putNonNull(Map<String, Object> meta, String key, Object value) {
        if (value != null) {
            meta.put(key, value);
        }
    }
}
