package com.pfagent.agent.rag;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * 种族向量库数据加载器
 *
 * 与 ClassDataLoader 同构：首次启动时委托 ChunkImporter 导入种族 chunks
 * （race_overview / race_trait / alt_trait / fcb_entry 等组件类型），持久化到独立 JSON。
 * 统一行模型 StandardChunk + StandardChunkMapper，六个模块共用。
 */
@Component
public class RaceDataLoader implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(RaceDataLoader.class);

    @Autowired
    private ChunkImporter chunkImporter;
    @Autowired
    private StandardChunkMapper mapper;
    @Autowired
    @Qualifier("raceVectorStore")
    private VectorStore vectorStore;

    @Value("${pf.chunks.race-path}")
    private String chunksPath;

    @Value("${pf.stores.race-file-path}")
    private String vectorStorePath;


    @Override
    public void run(String... args) {
        if (Files.exists(Path.of(vectorStorePath))) {
            log.info("种族向量库文件已存在，跳过导入: {}", vectorStorePath);
            return;
        }
        int total = chunkImporter.importChunks(
                Path.of(chunksPath), StandardChunk.class, mapper, vectorStore, new File(vectorStorePath));
        log.info("种族导入完成：共 {} 条", total);
    }
}
