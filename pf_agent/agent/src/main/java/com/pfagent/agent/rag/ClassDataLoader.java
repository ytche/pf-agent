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
 * 职业向量库数据加载器
 *
 * 与 SpellDataLoader 同构：首次启动时委托 ChunkImporter 导入职业 chunks
 * （class_overview / class_feature / class_archetype 等组件类型），持久化到独立 JSON。
 * 职业模块自 CP4 起走统一 StandardChunk 行模型（vectorizer/output/职业/chunks.jsonl），
 * 由 ProfessionChunkMapper 负责职业字段扁平化。
 */
@Component
public class ClassDataLoader implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(ClassDataLoader.class);

    @Autowired
    private ChunkImporter chunkImporter;
    @Autowired
    private ProfessionChunkMapper mapper;
    @Autowired
    @Qualifier("classVectorStore")
    private VectorStore vectorStore;

    @Value("${pf.chunks.classes-path}")
    private String classesPath;

    @Value("${pf.stores.class-file-path}")
    private String vectorStorePath;


    @Override
    public void run(String... args) {
        if (Files.exists(Path.of(vectorStorePath))) {
            log.info("职业向量库文件已存在，跳过导入: {}", vectorStorePath);
            return;
        }
        int total = chunkImporter.importChunks(
                Path.of(classesPath), StandardChunk.class, mapper, vectorStore, new File(vectorStorePath));
        log.info("职业导入完成：共 {} 条", total);
    }
}
