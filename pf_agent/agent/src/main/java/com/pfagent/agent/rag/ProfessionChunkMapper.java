package com.pfagent.agent.rag;

import org.springframework.ai.document.Document;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.util.Map;

/**
 * 职业 chunk → Document 映射（StandardChunk 扁平化扩展）
 *
 * 复用 StandardChunkMapper 的统一映射（来源书 book_name_cn / book_abbreviation /
 * tocPath / title 等对齐溯源约定），额外把职业业务字段从 nested metadata 扁平化为
 * Document 顶层 metadata 键：class_name / archetype_name / feature_subtype——这些是
 * FilterTranslator.translateClass 结构化过滤的目标键，扁平后 class 过滤可与职业
 * 向量库的通用 Document 直接交互，无需解析嵌套结构。
 *
 * 约半数职业 chunk 无 archetype_name / feature_subtype（class_overview 与基础职业
 * class_feature 不挂变体），缺省键经 putNonNull 跳过不写，与各模块 null 兜底口径一致。
 */
@Component
public class ProfessionChunkMapper implements ChunkMapper<StandardChunk> {

    @Autowired
    private StandardChunkMapper baseMapper;

    @Override
    public Document toDocument(StandardChunk c) {
        Document doc = baseMapper.toDocument(c);
        Map<String, Object> meta = doc.getMetadata();
        Map<String, Object> nested = c.metadata() == null ? Map.of() : c.metadata();
        putNonNull(meta, "class_name", nested.get("class_name"));
        putNonNull(meta, "archetype_name", nested.get("archetype_name"));
        putNonNull(meta, "feature_subtype", nested.get("feature_subtype"));
        return doc;
    }

    private void putNonNull(Map<String, Object> meta, String key, Object value) {
        if (value != null) {
            meta.put(key, value);
        }
    }
}
