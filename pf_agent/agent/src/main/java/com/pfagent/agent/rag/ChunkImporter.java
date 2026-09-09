package com.pfagent.agent.rag;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * 通用 chunks 导入器
 *
 * 读取 JSONL → 逐行反序列化为模块 model → mapper 转 Document → 分批写入向量库 → 持久化。
 * 与具体模块解耦：模块差异（行模型、字段映射、向量库）通过泛型参数与 ChunkMapper 注入。
 *
 * 分批（每批 500 条）写入是为了在本地 embedding 期间能看到进度，
 * 避免长时间无日志被误认为卡死。
 */
@Component
public class ChunkImporter {

    private static final Logger log = LoggerFactory.getLogger(ChunkImporter.class);
    private static final int BATCH_SIZE = 500;

    @Autowired
    private VectorStorePersistence persistence;
    private final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * 导入并持久化一个数据模块的 chunks
     *
     * @param jsonlPath   chunks.jsonl 路径
     * @param chunkType   JSONL 行模型类型（SpellChunk / StandardChunk …）
     * @param mapper      行模型 → Document 映射器
     * @param vectorStore 目标向量库（每模块一个）
     * @param storeFile   向量库持久化文件
     * @return 导入的 chunk 总数
     */
    public <T> int importChunks(Path jsonlPath, Class<T> chunkType, ChunkMapper<T> mapper,
                                VectorStore vectorStore, File storeFile) {
        if (!Files.exists(jsonlPath)) {
            throw new IllegalStateException(
                    "chunks 文件不存在: " + jsonlPath.toAbsolutePath()
                            + "（请确认 application.yml 中 pf.chunks.*-path 配置正确）");
        }

        log.info("开始导入 chunks: {}", jsonlPath.toAbsolutePath());
        long start = System.currentTimeMillis();

        List<Document> batch = new ArrayList<>(BATCH_SIZE);
        int total = 0;
        try (BufferedReader reader = Files.newBufferedReader(jsonlPath, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) {
                    continue;
                }
                T chunk = objectMapper.readValue(line, chunkType);
                batch.add(mapper.toDocument(chunk));
                total++;

                if (batch.size() >= BATCH_SIZE) {
                    vectorStore.add(batch);
                    log.info("已导入 {} 条", total);
                    batch.clear();
                }
            }
            // 收尾批次
            if (!batch.isEmpty()) {
                vectorStore.add(batch);
            }
        } catch (IOException e) {
            throw new IllegalStateException("读取/解析 chunks 失败: " + jsonlPath.toAbsolutePath(), e);
        }

        // 落盘隔离到 VectorStorePersistence（VectorStore 接口无 save；父目录自动创建）
        persistence.save(vectorStore, storeFile.getPath());

        long seconds = (System.currentTimeMillis() - start) / 1000;
        log.info("导入完成：共 {} 条 chunk，耗时 {} 秒，向量库已保存至 {}",
                total, seconds, storeFile.getAbsolutePath());
        return total;
    }
}
