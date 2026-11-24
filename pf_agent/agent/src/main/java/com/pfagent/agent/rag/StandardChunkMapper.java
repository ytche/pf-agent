package com.pfagent.agent.rag;

import org.springframework.ai.document.Document;
import org.springframework.stereotype.Component;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

/**
 * 统一 chunk → Document 映射（六个模块共用）
 *
 * 顶部字段 1:1 放入 metadata，对齐统一溯源约定（book_name_cn / book_abbreviation /
 * tocPath / title），使 PromptBuilder 与 ChatService 无需区分模块即可溯源。
 * 各模块 nested metadata 结构各异，仅对有精确过滤诉求的字段按需扁平化
 * （如 race_name、trait_type），其余保持独立扩展。
 *
 * 溯源路径用 chm_toc_path（数据侧已含完整目录，如"专长 → 战斗专长"），
 * 比 doc_id（page_*.md）更有目录引导价值；null 时回退 doc_id + title 拼接。
 */
@Component
public class StandardChunkMapper implements ChunkMapper<StandardChunk> {

    @Override
    public Document toDocument(StandardChunk c) {
        Map<String, Object> meta = new HashMap<>();
        putNonNull(meta, "chunk_id", c.chunkId());
        putNonNull(meta, "doc_id", c.docId());
        putNonNull(meta, "category", c.category());
        putNonNull(meta, "component_type", c.componentType());
        putNonNull(meta, "title", c.title());
        putNonNull(meta, "book_name_cn", c.bookNameCn());
        putNonNull(meta, "book_name_en", c.bookNameEn());
        putNonNull(meta, "book_abbreviation", c.bookAbbreviation());
        putNonNull(meta, "aliases", c.aliases() == null ? "" : String.join(", ", c.aliases()));

        // 溯源路径：chm_toc_path 优先，缺失时回退 doc_id + title
        String tocPath = c.chmTocPath();
        if (tocPath == null || tocPath.isBlank()) {
            tocPath = (c.docId() == null ? "" : c.docId())
                    + " > "
                    + (c.title() == null ? "" : c.title());
        }
        meta.put("tocPath", tocPath);

        if (c.metadata() != null) {
            putNonBlank(meta, "race_name", c.metadata().get("race_name"));
            putNonBlank(meta, "race_name_en", c.metadata().get("race_name_en"));
        }

        // 背景特性 trait_type 是 nested metadata；扁平化后才能用于类型排除/空类型降权。
        // 空 list 显式写空串，供检索端区分「已解析为空」与「字段缺失」。
        Object traitType = c.metadata() == null ? null : c.metadata().get("trait_type");
        if (traitType instanceof List<?> values) {
            meta.put("trait_type", values.stream()
                    .filter(Objects::nonNull)
                    .map(Object::toString)
                    .filter(value -> !value.isBlank())
                    .collect(Collectors.joining(",")));
        } else if (traitType != null) {
            meta.put("trait_type", traitType.toString());
        } else if ("trait".equals(c.category())
                || (c.componentType() != null && c.componentType().startsWith("trait"))) {
            meta.put("trait_type", "");
        }

        return Document.builder()
                .text(c.text() == null ? "" : c.text())
                .metadata(meta)
                .build();
    }

    private void putNonBlank(Map<String, Object> meta, String key, Object value) {
        if (value != null && !value.toString().isBlank()) {
            meta.put(key, value);
        }
    }

    private void putNonNull(Map<String, Object> meta, String key, Object value) {
        if (value != null) {
            meta.put(key, value);
        }
    }
}
