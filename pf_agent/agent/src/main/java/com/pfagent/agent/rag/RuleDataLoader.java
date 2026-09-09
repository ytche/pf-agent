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
 * 规则向量库数据加载器
 *
 * 与 ClassDataLoader 同构：首次启动时委托 ChunkImporter 导入规则 chunks
 * （rule_section / rule_table / rule_entry / rule_intro / rule_reference 等组件类型），
 * 持久化到独立 JSON。统一行模型 StandardChunk + StandardChunkMapper，六个模块共用。
 */
@Component
public class RuleDataLoader implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(RuleDataLoader.class);

    @Autowired
    private ChunkImporter chunkImporter;
    @Autowired
    private StandardChunkMapper mapper;
    @Autowired
    @Qualifier("ruleVectorStore")
    private VectorStore vectorStore;

    @Value("${pf.chunks.rule-path}")
    private String chunksPath;

    @Value("${pf.stores.rule-file-path}")
    private String vectorStorePath;


    @Override
    public void run(String... args) {
        if (Files.exists(Path.of(vectorStorePath))) {
            log.info("规则向量库文件已存在，跳过导入: {}", vectorStorePath);
            return;
        }
        int total = chunkImporter.importChunks(
                Path.of(chunksPath), StandardChunk.class, mapper, vectorStore, new File(vectorStorePath));
        log.info("规则导入完成：共 {} 条", total);
    }
}
