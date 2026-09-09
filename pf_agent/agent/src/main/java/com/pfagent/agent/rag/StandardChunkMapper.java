package com.pfagent.agent.rag;

import org.springframework.ai.document.Document;
import org.springframework.stereotype.Component;

import java.util.HashMap;
import java.util.Map;

/**
 * 统一 chunk → Document 映射（六个模块共用）
 *
 * 顶部字段 1:1 放入 metadata，对齐统一溯源约定（book_name_cn / book_abbreviation /
 * tocPath / title），使 PromptBuilder 与 ChatService 无需区分模块即可溯源。
 * 各模块 nested metadata（feat_type、race_name、slot 等）首期不扁平化——数据侧
 * 结构各异且无精确过滤强诉求，需要时可按模块独立扩展（见设计决策）。
 *
 * 溯源路径用 chm_toc_path（数据侧已含完整目录，如"专长 → 战斗专长"），
 * 比 doc_id（page_*.md）更有目录引导价值；null 时回退 doc_id + title 拼接。
 */
@Component
public class StandardChunkMapper implements ChunkMapper<StandardChunk> {

    @Override
    public Document toDocument(StandardChunk c) {
        Map<String, Object> meta = new HashMap<>();
        putNonNull(meta, "chunk_id", c.chunk_id());
        putNonNull(meta, "doc_id", c.doc_id());
        putNonNull(meta, "category", c.category());
        putNonNull(meta, "component_type", c.component_type());
        putNonNull(meta, "title", c.title());
        putNonNull(meta, "book_name_cn", c.book_name_cn());
        putNonNull(meta, "book_name_en", c.book_name_en());
        putNonNull(meta, "book_abbreviation", c.book_abbreviation());
        putNonNull(meta, "aliases", c.aliases() == null ? "" : String.join(", ", c.aliases()));

        // 溯源路径：chm_toc_path 优先，缺失时回退 doc_id + title
        String tocPath = c.chm_toc_path();
        if (tocPath == null || tocPath.isBlank()) {
            tocPath = (c.doc_id() == null ? "" : c.doc_id())
                    + " > "
                    + (c.title() == null ? "" : c.title());
        }
        meta.put("tocPath", tocPath);

        return Document.builder()
                .text(c.text() == null ? "" : c.text())
                .metadata(meta)
                .build();
    }

    private void putNonNull(Map<String, Object> meta, String key, Object value) {
        if (value != null) {
            meta.put(key, value);
        }
    }
}
