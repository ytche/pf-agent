package com.pfagent.agent.rag;

import org.springframework.ai.document.Document;
import org.springframework.stereotype.Component;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 法术 chunk → Document 映射
 *
 * 从 SpellDataLoader 抽离，保持原 toDocument 逻辑不变。
 * tocPath 语义：doc_id > title（对齐向量化阶段）。
 */
@Component
public class SpellChunkMapper implements ChunkMapper<SpellChunk> {

    @Override
    public Document toDocument(SpellChunk c) {
        Map<String, Object> meta = new HashMap<>();
        meta.put("chunk_id", c.chunk_id());
        meta.put("doc_id", c.doc_id());
        meta.put("title", c.title());
        meta.put("book_name_cn", c.book_name_cn());
        meta.put("book_abbreviation", c.book_abbreviation());
        meta.put("book_name_en", c.book_name_en());
        meta.put("aliases", c.aliases() == null ? "" : String.join(", ", c.aliases()));

        // 来源追溯路径：doc_id > title（对齐向量化阶段 tocPath 语义）
        String tocPath = (c.doc_id() == null ? "" : c.doc_id())
                + " > "
                + (c.title() == null ? "" : c.title());
        meta.put("tocPath", tocPath);

        // 嵌套 metadata 扁平化：filterExpression 只作用于顶层标量，
        // spell_level 是嵌套数组，必须展开为 spell_level_<职业>/has_spell_<职业> 顶层键
        // 才能被 searchByMetadata 精确过滤命中（值统一转 String，保证过滤类型一致）。
        flattenMetadata(meta, c.metadata());

        return Document.builder()
                .text(c.text() == null ? "" : c.text())
                .metadata(meta)
                .build();
    }

    /**
     * 把法术 chunk 的嵌套 metadata 展开为顶层标量键。
     *
     * 键名兼容性（v1.5 C3）：spell_level_<职业>/has_spell_<职业> 直接使用数据侧职业名，
     * 含括号变体（如"召唤师（Unchained）"）按原样展开——filterExpression 的 eq 是值精确匹配，
     * 键名本身不解析，风险仅在数据侧命名不一致；已知脏职业名（拼写重复/解析垃圾）登记 KN
     * 由源数据侧修复，不在 mapper 层硬编码清洗。
     */
    private void flattenMetadata(Map<String, Object> meta, Map<String, Object> src) {
        if (src == null) {
            return;
        }
        Object school = src.get("school");
        if (school != null) {
            meta.put("school", school.toString());
        }
        Object subschool = src.get("subschool");
        if (subschool != null) {
            meta.put("subschool", subschool.toString());
        }
        Object spellLevel = src.get("spell_level");
        if (spellLevel instanceof List<?> levels) {
            for (Object entry : levels) {
                if (entry instanceof Map<?, ?> m) {
                    Object cls = m.get("class");
                    if (cls == null) {
                        continue;
                    }
                    String className = cls.toString();
                    meta.put("has_spell_" + className, "true");
                    Object level = m.get("level");
                    if (level != null) {
                        meta.put("spell_level_" + className, level.toString());
                    }
                }
            }
        }
    }
}
