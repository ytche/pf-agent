package com.pfagent.agent.rag;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.boot.CommandLineRunner;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * SpellMetadataReplayTool 单元测试
 *
 * 验证一次性 metadata 重放：
 *  - 旧库（无扁平键）重放后含 spell_level_xxx 与 has_spell_xxx 扁平键
 *  - text / embedding 原样保留（重放只替换 metadata）
 *  - 按 chunk_id join 正确；store 有而 jsonl 无的 chunk 记为漂移
 *  - 幂等：已重放（含扁平键）时跳过
 */
class SpellMetadataReplayToolTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final SpellChunkMapper mapper = new SpellChunkMapper();

    @TempDir
    Path tempDir;

    /** 旧库重放后含扁平键且 textEmbedding 保留 */
    @Test
    void replayAddsFlatKeysKeepsTextEmbedding() throws Exception {
        Path store = writeOldStore();
        Path jsonl = writeChunksJsonl();
        SpellMetadataReplayTool tool = tool(store, jsonl);

        SpellMetadataReplayTool.ReplayStats stats = tool.replay();

        assertThat(stats.replayed()).isEqualTo(2);
        assertThat(stats.missed()).isEqualTo(1);   // spell_999 漂移
        assertThat(stats.skipped()).isFalse();

        Map<String, Object> saved = objectMapper.readValue(store.toFile(), Map.class);
        // 扁平键已加入（spell_001）
        @SuppressWarnings("unchecked")
        Map<String, Object> d1 = (Map<String, Object>) saved.get("uuid-001");
        @SuppressWarnings("unchecked")
        Map<String, Object> m1 = (Map<String, Object>) d1.get("metadata");
        assertThat(m1.get("school")).isEqualTo("咒法系");
        assertThat(m1.get("spell_level_女巫")).isEqualTo("1");
        assertThat(m1.get("spell_level_德鲁伊")).isEqualTo("1");
        assertThat(m1.get("has_spell_女巫")).isEqualTo("true");
        // text / embedding 原样保留
        assertThat(d1.get("text")).isEqualTo("火球术正文");
        assertThat(d1.get("embedding")).isEqualTo(List.of(0.1, 0.2));
        // 无 spell_level 的 doc 有 school 但无 has_spell 键
        @SuppressWarnings("unchecked")
        Map<String, Object> d2 = (Map<String, Object>) saved.get("uuid-002");
        @SuppressWarnings("unchecked")
        Map<String, Object> m2 = (Map<String, Object>) d2.get("metadata");
        assertThat(m2.get("school")).isEqualTo("预言系");
        assertThat(m2).doesNotContainKey("has_spell_女巫");
        // 漂移 doc 未被破坏（jsonl 无此 chunk_id，保留旧 metadata）
        @SuppressWarnings("unchecked")
        Map<String, Object> d999 = (Map<String, Object>) saved.get("uuid-999");
        @SuppressWarnings("unchecked")
        Map<String, Object> m999 = (Map<String, Object>) d999.get("metadata");
        assertThat(m999.get("title")).isEqualTo("旧数据");
        assertThat(m999).doesNotContainKey("school");
    }

    /** 重放幂等：已含扁平键时跳过 */
    @Test
    void replayIdempotentSkipsWhenFlatKeysPresent() throws Exception {
        Path store = writeOldStore();
        Path jsonl = writeChunksJsonl();
        SpellMetadataReplayTool tool = tool(store, jsonl);

        tool.replay();
        SpellMetadataReplayTool.ReplayStats second = tool.replay();

        assertThat(second.skipped()).isTrue();
        assertThat(second.replayed()).isZero();
    }

    /** store 文件不存在时跳过 */
    @Test
    void replayMissingStoreSkipped() throws Exception {
        Path jsonl = writeChunksJsonl();
        SpellMetadataReplayTool tool = tool(tempDir.resolve("missing.json"), jsonl);

        SpellMetadataReplayTool.ReplayStats stats = tool.replay();

        assertThat(stats.skipped()).isTrue();
    }

    /** SP8c J6：已重放过（含 school 扁平键）但缺 base_spell_* 的旧库，逐条比对能再补齐 */
    @Test
    void replayPicksUpBaseSpellFieldsOnPreviouslyReplayedStore() throws Exception {
        Path store = writePreviouslyReplayedStore();
        Path jsonl = writeChunksJsonlWithMythicVariant();
        SpellMetadataReplayTool tool = tool(store, jsonl);

        SpellMetadataReplayTool.ReplayStats stats = tool.replay();

        assertThat(stats.skipped()).isFalse();
        assertThat(stats.replayed()).isEqualTo(1);   // 只有变体条目的 metadata 不一致
        Map<String, Object> saved = objectMapper.readValue(store.toFile(), Map.class);
        @SuppressWarnings("unchecked")
        Map<String, Object> m2 = (Map<String, Object>) ((Map<String, Object>) saved.get("uuid-002")).get("metadata");
        assertThat(m2.get("base_spell_chunk_id")).isEqualTo("spell_001");
        assertThat(m2.get("base_spell_title")).isEqualTo("火球术");
        // 普通法术条目 metadata 与 mapper 产物一致，不重复替换
        SpellMetadataReplayTool.ReplayStats second = tool.replay();
        assertThat(second.skipped()).isTrue();
    }

    /** SP8c J6 补测：store metadata 含 mapper 产物之外的额外键（如未来 Layer 1 entry_links）——逐条比对判为不一致，重放整表替换（额外键被清除），再次运行跳过 */
    @Test
    void replayReplacesMetadataWithExtraKeysAndStaysIdempotent() throws Exception {
        Path jsonl = writeChunksJsonlWithMythicVariant();
        Path store = tempDir.resolve("store-extra.json");
        Map<String, Object> storeMap = new LinkedHashMap<>();
        int seq = 0;
        for (String line : Files.readAllLines(jsonl, StandardCharsets.UTF_8)) {
            if (line.isBlank()) {
                continue;
            }
            SpellChunk chunk = objectMapper.readValue(line, SpellChunk.class);
            Map<String, Object> meta = new LinkedHashMap<>(mapper.toDocument(chunk).getMetadata());
            meta.put("entry_links", List.of(Map.of("name", "闪避")));
            storeMap.put("uuid-extra-" + seq, storeDoc("uuid-extra-" + seq, meta));
            seq++;
        }
        objectMapper.writeValue(store.toFile(), storeMap);
        SpellMetadataReplayTool tool = tool(store, jsonl);

        SpellMetadataReplayTool.ReplayStats stats = tool.replay();

        assertThat(stats.skipped()).isFalse();
        assertThat(stats.replayed()).isEqualTo(2);
        Map<String, Object> saved = objectMapper.readValue(store.toFile(), Map.class);
        for (Object value : saved.values()) {
            @SuppressWarnings("unchecked")
            Map<String, Object> meta = (Map<String, Object>) ((Map<String, Object>) value).get("metadata");
            assertThat(meta).doesNotContainKey("entry_links");
        }
        SpellMetadataReplayTool.ReplayStats second = tool.replay();
        assertThat(second.skipped()).isTrue();
    }

    /**
     * 门控接线：设计 §13 要求该工具是 CommandLineRunner——metadata-replay=true 时
     * 启动即自动执行一次重放。验证 run() 无参调用等价于触发 replay()。
     */
    /** 符合 CommandLineRunner 契约，启动即触发重放 */
    @Test
    void runSatisfiesCommandLineRunnerContract() throws Exception {
        Path store = writeOldStore();
        Path jsonl = writeChunksJsonl();
        SpellMetadataReplayTool tool = tool(store, jsonl);

        assertThat(tool).isInstanceOf(CommandLineRunner.class);
        ((CommandLineRunner) tool).run();

        // run() 后 store 已被重放：含扁平键
        Map<String, Object> saved = objectMapper.readValue(store.toFile(), Map.class);
        @SuppressWarnings("unchecked")
        Map<String, Object> d1 = (Map<String, Object>) saved.get("uuid-001");
        @SuppressWarnings("unchecked")
        Map<String, Object> m1 = (Map<String, Object>) d1.get("metadata");
        assertThat(m1.get("spell_level_女巫")).isEqualTo("1");
    }

    private SpellMetadataReplayTool tool(Path store, Path jsonl) {
        SpellMetadataReplayTool t = new SpellMetadataReplayTool();
        ReflectionTestUtils.setField(t, "storeFilePath", store.toString());
        ReflectionTestUtils.setField(t, "chunksJsonlPath", jsonl.toString());
        ReflectionTestUtils.setField(t, "mapper", mapper);
        return t;
    }

    /** 构造旧库 store JSON：Map<docId, {id,text,metadata,embedding}>，metadata 无扁平键 */
    private Path writeOldStore() throws Exception {
        Map<String, Object> store = new LinkedHashMap<>();
        store.put("uuid-001", doc("uuid-001", "spell_001", "火球术", "火球术正文", List.of(0.1, 0.2)));
        store.put("uuid-002", doc("uuid-002", "spell_002", "侦测魔法", "侦测魔法正文", List.of(0.3, 0.4)));
        // spell_999 在 store 里但 jsonl 缺失 → 漂移
        store.put("uuid-999", doc("uuid-999", "spell_999", "旧数据", "旧数据正文", List.of(0.5, 0.6)));
        Path p = tempDir.resolve("store.json");
        objectMapper.writeValue(p.toFile(), store);
        return p;
    }

    /** 构造"已重放过"的 store：metadata = 当前 mapper 产物去掉 base_spell_*（v1.6 重放产物） */
    private Path writePreviouslyReplayedStore() throws Exception {
        SpellChunk base = new SpellChunk("spell_001", "page_spell_001", "spell", "spell", "火球术", "火球术正文",
                "CRB", "核心规则书", "Core Rulebook", 1, null, Map.of("school", "塑能系"), Map.of(),
                null, null, null);
        SpellChunk mythic = new SpellChunk("spell_002", "page_spell_002", "spell", "spell", "火球术（神话）", "神话变体正文",
                "CRB", "核心规则书", "Core Rulebook", 1, null, Map.of("school", "塑能系"), Map.of(),
                "spell_001", "火球术", "CRB");
        Map<String, Object> store = new LinkedHashMap<>();
        Map<String, Object> m1 = new LinkedHashMap<>(mapper.toDocument(base).getMetadata());
        store.put("uuid-001", storeDoc("uuid-001", m1));
        Map<String, Object> m2 = new LinkedHashMap<>(mapper.toDocument(mythic).getMetadata());
        m2.remove("base_spell_chunk_id");
        m2.remove("base_spell_title");
        m2.remove("base_spell_book");
        store.put("uuid-002", storeDoc("uuid-002", m2));
        Path p = tempDir.resolve("store.json");
        objectMapper.writeValue(p.toFile(), store);
        return p;
    }

    private Map<String, Object> storeDoc(String id, Map<String, Object> metadata) {
        Map<String, Object> d = new LinkedHashMap<>();
        d.put("id", id);
        d.put("text", metadata.get("title") + "正文");
        d.put("metadata", metadata);
        d.put("embedding", List.of(0.1, 0.2));
        return d;
    }

    /** 构造含神话变体（base_spell_*）的 chunks.jsonl */
    private Path writeChunksJsonlWithMythicVariant() throws Exception {
        Path p = tempDir.resolve("chunks.jsonl");
        Map<String, Object> c1 = new LinkedHashMap<>();
        c1.put("chunk_id", "spell_001");
        c1.put("doc_id", "page_spell_001");
        c1.put("category", "spell");
        c1.put("component_type", "spell");
        c1.put("title", "火球术");
        c1.put("text", "火球术正文");
        c1.put("book_abbreviation", "CRB");
        c1.put("book_name_cn", "核心规则书");
        c1.put("book_name_en", "Core Rulebook");
        c1.put("source_confidence", 1);
        c1.put("aliases", List.of());
        c1.put("metadata", Map.of("school", "塑能系"));
        c1.put("extra", Map.of());
        Map<String, Object> c2 = new LinkedHashMap<>(c1);
        c2.put("chunk_id", "spell_002");
        c2.put("doc_id", "page_spell_002");
        c2.put("title", "火球术（神话）");
        c2.put("text", "神话变体正文");
        c2.put("base_spell_chunk_id", "spell_001");
        c2.put("base_spell_title", "火球术");
        c2.put("base_spell_book", "CRB");
        String content = objectMapper.writeValueAsString(c1) + "\n"
                + objectMapper.writeValueAsString(c2) + "\n";
        Files.writeString(p, content, StandardCharsets.UTF_8);
        return p;
    }

    private Map<String, Object> doc(String id, String chunkId, String title, String text, List<Double> emb) {
        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("chunk_id", chunkId);
        meta.put("doc_id", "page_" + chunkId);
        meta.put("title", title);
        meta.put("tocPath", "page_" + chunkId + " > " + title);
        meta.put("book_name_cn", "核心规则书");
        meta.put("book_abbreviation", "CRB");
        Map<String, Object> d = new LinkedHashMap<>();
        d.put("id", id);
        d.put("text", text);
        d.put("metadata", meta);
        d.put("embedding", emb);
        return d;
    }

    /** 构造新格式 chunks.jsonl：spell_001 含 spell_level，spell_002 无 */
    private Path writeChunksJsonl() throws Exception {
        Path p = tempDir.resolve("chunks.jsonl");
        StringBuilder sb = new StringBuilder();
        Map<String, Object> c1 = new LinkedHashMap<>();
        c1.put("chunk_id", "spell_001");
        c1.put("doc_id", "page_spell_001");
        c1.put("category", "spell");
        c1.put("component_type", "spell");
        c1.put("title", "火球术");
        c1.put("text", "火球术正文");
        c1.put("book_abbreviation", "CRB");
        c1.put("book_name_cn", "核心规则书");
        c1.put("book_name_en", "Core Rulebook");
        c1.put("source_confidence", 1);
        c1.put("aliases", List.of());
        c1.put("metadata", Map.of(
                "school", "咒法系",
                "subschool", "创造",
                "spell_level", List.of(
                        Map.of("class", "女巫", "level", 1),
                        Map.of("class", "德鲁伊", "level", 1))));
        c1.put("extra", Map.of());
        sb.append(objectMapper.writeValueAsString(c1)).append('\n');

        Map<String, Object> c2 = new LinkedHashMap<>();
        c2.put("chunk_id", "spell_002");
        c2.put("doc_id", "page_spell_002");
        c2.put("category", "spell");
        c2.put("component_type", "spell");
        c2.put("title", "侦测魔法");
        c2.put("text", "侦测魔法正文");
        c2.put("book_abbreviation", "CRB");
        c2.put("book_name_cn", "核心规则书");
        c2.put("book_name_en", "Core Rulebook");
        c2.put("source_confidence", 1);
        c2.put("aliases", List.of());
        c2.put("metadata", Map.of("school", "预言系"));
        c2.put("extra", Map.of());
        sb.append(objectMapper.writeValueAsString(c2)).append('\n');

        Files.writeString(p, sb.toString(), StandardCharsets.UTF_8);
        return p;
    }
}
