package com.pfagent.agent.rag;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.document.Document;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.BufferedReader;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 法术向量库 metadata 一次性重放工具（方案 B）
 *
 * 背景：v1.6 设计确定 SpellChunkMapper 新增 school/subschool/spell_level_xxx 与
 * has_spell_xxx 扁平键，但现有持久化向量库 {@code vector_store_spells.json}（约 4200 条）是旧 mapper
 * 生成的、不含这些键。由于 Document.text 不变 → embedding 不变，全量重建（重新 embedding
 * 30 分钟）纯属浪费——只需把现有库的 metadata 按新 mapper 重新生成并替换。
 *
 * 原理：
 *  1. 读 chunks.jsonl → 用 SpellChunkMapper 生成每条的"新 metadata"（含扁平键），以 chunk_id 为 join 键
 *  2. 读现有 store JSON（顶层 Map&lt;docId, Document&gt;）→ 逐条按 metadata.chunk_id 匹配 → 替换 metadata
 *  3. 保留 id / text / embedding 原样（不重算向量），只替换 metadata
 *  4. 写回 store JSON，幂等：store metadata 已与 mapper 产物逐条一致则跳过
 *
 * 门控：{@code @ConditionalOnProperty(pf.stores.metadata-replay=true)}，一次性运行后关闭。
 */
@Component
@ConditionalOnProperty(name = "pf.stores.metadata-replay", havingValue = "true")
public class SpellMetadataReplayTool implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(SpellMetadataReplayTool.class);

    @Value("${pf.stores.spell-file-path}")
    private String storeFilePath;
    @Value("${pf.chunks.spells-path}")
    private String chunksJsonlPath;
    @Autowired
    private SpellChunkMapper mapper;
    private final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * 执行重放（幂等）。store 文件不存在或无待更新条目时跳过。
     *
     * 幂等判断（SP8c J6 修订）：旧版以"metadata 含 school 扁平键"为已重放标记，
     * 但 mapper 后续新增键（base_spell_*）时该标记失效——改为逐条比对：
     * 只要存在"fresh metadata（当前 mapper 产物）与存量 metadata 不一致"的条目
     * 就执行替换；全部一致才跳过。重放后 store 与 mapper 产物逐字一致，天然幂等。
     *
     * @return 重放统计：replayed = 成功替换 metadata 的条数，missed = store 有而 jsonl 无的漂移条数
     */
    public ReplayStats replay() {
        Path storePath = Path.of(storeFilePath);
        if (!Files.exists(storePath)) {
            log.info("[MetadataReplay] store 文件不存在，跳过: {}", storeFilePath);
            return ReplayStats.skip();
        }

        Map<String, Object> store = readStore(storePath);
        if (store == null) {
            return ReplayStats.skip();
        }

        // 1. chunks.jsonl → chunk_id → 新 metadata（复用 mapper 扁平化逻辑，保证与导入一致）
        Map<String, Map<String, Object>> freshMetaByChunkId = buildFreshMetaIndex();

        // 2. 逐条比对替换 metadata，保留 id/text/embedding
        int replayed = 0;
        int missed = 0;
        for (Object value : store.values()) {
            if (!(value instanceof Map<?, ?> doc)) {
                continue;
            }
            Object metaObj = doc.get("metadata");
            if (!(metaObj instanceof Map<?, ?> oldMeta)) {
                continue;
            }
            String chunkId = oldMeta.get("chunk_id") == null ? null : String.valueOf(oldMeta.get("chunk_id"));
            Map<String, Object> fresh = chunkId == null ? null : freshMetaByChunkId.get(chunkId);
            if (fresh == null) {
                missed++;   // store 有而 jsonl 无：保留旧 metadata（漂移，仅计数告警）
                log.warn("[MetadataReplay] chunk_id {} 在 chunks.jsonl 中未找到，保留旧 metadata", chunkId);
                continue;
            }
            if (fresh.equals(oldMeta)) {
                continue;   // 已与 mapper 产物一致（含此前已重放过），跳过
            }
            @SuppressWarnings("unchecked")
            Map<String, Object> mutableDoc = (Map<String, Object>) doc;
            mutableDoc.put("metadata", fresh);
            replayed++;
        }

        if (replayed == 0) {
            log.info("[MetadataReplay] 无待更新条目（store metadata 已与 mapper 产物一致），跳过");
            return ReplayStats.skip();
        }
        writeStore(storePath, store);
        log.info("[MetadataReplay] 完成：替换 {} 条 metadata，漂移 {} 条，已保存 {}", replayed, missed, storeFilePath);
        return new ReplayStats(replayed, missed, false);
    }

    /**
     * CommandLineRunner 入口：metadata-replay=true 时启动自动执行一次重放。
     * 幂等（重放过 / store 缺失会跳过），一次性运行后改回 false 并重启即不再触发。
     */
    @Override
    public void run(String... args) {
        replay();
    }

    /** 读 store JSON；格式异常时记录并返回 null（跳过） */
    @SuppressWarnings("unchecked")
    private Map<String, Object> readStore(Path storePath) {
        try {
            return (Map<String, Object>) objectMapper.readValue(storePath.toFile(), Map.class);
        } catch (Exception e) {
            log.error("[MetadataReplay] 读取 store 失败: {}", storeFilePath, e);
            return null;
        }
    }

    private void writeStore(Path storePath, Map<String, Object> store) {
        try {
            objectMapper.writerWithDefaultPrettyPrinter().writeValue(storePath.toFile(), store);
        } catch (Exception e) {
            throw new IllegalStateException("重放后写回 store 失败: " + storeFilePath, e);
        }
    }

    /** 重放统计 */
    public record ReplayStats(int replayed, int missed, boolean skipped) {
        static ReplayStats skip() {
            return new ReplayStats(0, 0, true);
        }
    }

    /** chunks.jsonl → chunk_id → 新 metadata（含扁平键），join 键与导入时一致 */
    private Map<String, Map<String, Object>> buildFreshMetaIndex() {
        Map<String, Map<String, Object>> index = new LinkedHashMap<>();
        Path jsonl = Path.of(chunksJsonlPath);
        if (!Files.exists(jsonl)) {
            throw new IllegalStateException("chunks.jsonl 不存在: " + chunksJsonlPath);
        }
        try (BufferedReader reader = Files.newBufferedReader(jsonl, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) {
                    continue;
                }
                SpellChunk chunk = objectMapper.readValue(line, SpellChunk.class);
                Document doc = mapper.toDocument(chunk);
                String chunkId = (String) doc.getMetadata().get("chunk_id");
                if (chunkId != null) {
                    index.put(chunkId, doc.getMetadata());
                }
            }
        } catch (Exception e) {
            throw new IllegalStateException("读取 chunks.jsonl 失败: " + chunksJsonlPath, e);
        }
        return index;
    }
}
