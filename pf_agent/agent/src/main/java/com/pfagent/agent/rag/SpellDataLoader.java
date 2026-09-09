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
 * 法术向量库数据加载器
 *
 * 应用启动时执行：若法术向量库持久化文件不存在（首次启动），委托 ChunkImporter
 * 读取 Python 侧产出的 chunks.jsonl 并批量 embedding 入库，持久化为 JSON，
 * 供后续启动秒级加载。
 */
@Component
public class SpellDataLoader implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(SpellDataLoader.class);

    @Autowired
    private ChunkImporter chunkImporter;
    @Autowired
    private SpellChunkMapper mapper;
    @Autowired
    @Qualifier("spellVectorStore")
    private VectorStore vectorStore;

    @Value("${pf.chunks.spells-path}")
    private String spellsPath;

    @Value("${pf.stores.spell-file-path}")
    private String vectorStorePath;


    @Override
    public void run(String... args) {
        // 以持久化文件是否已存在判断是否首次启动（向量库无 count() API）
        if (Files.exists(Path.of(vectorStorePath))) {
            log.info("法术向量库文件已存在，跳过导入: {}", vectorStorePath);
            return;
        }
        int total = chunkImporter.importChunks(
                Path.of(spellsPath), SpellChunk.class, mapper, vectorStore, new File(vectorStorePath));
        log.info("法术导入完成：共 {} 条", total);
    }
}
