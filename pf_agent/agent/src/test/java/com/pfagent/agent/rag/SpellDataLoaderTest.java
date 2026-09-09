package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.ai.vectorstore.SimpleVectorStore;
import org.springframework.test.util.ReflectionTestUtils;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * SpellDataLoader 单元测试
 *
 * 启动两分支：向量库文件已存在 → 跳过导入；不存在 → 委托 ChunkImporter
 * 导入法术模块（路径、行模型、mapper、store、持久化文件均正确传递）。
 */
@ExtendWith(MockitoExtension.class)
class SpellDataLoaderTest {

    @Mock
    private ChunkImporter chunkImporter;
    @Mock
    private SpellChunkMapper mapper;
    @Mock
    private SimpleVectorStore vectorStore;

    @TempDir
    Path tempDir;

    /** 向量库文件已存在时跳过导入 */
    @Test
    void runExistingStoreSkipsImport() throws IOException {
        Path store = tempDir.resolve("store.json");
        Files.writeString(store, "{}");
        Path chunks = tempDir.resolve("chunks.jsonl");
        Files.writeString(chunks, "任意内容（不应被读取）");

        newLoader(chunks.toString(), store.toString()).run();

        verify(chunkImporter, never()).importChunks(any(), any(), any(), any(), any());
    }

    /** 向量库文件不存在时委托通用导入器 */
    @Test
    void runMissingStoreDelegatesToGenericImporter() throws IOException {
        Path chunks = tempDir.resolve("chunks.jsonl");
        Files.writeString(chunks, "{}");
        Path store = tempDir.resolve("store.json");
        when(chunkImporter.importChunks(any(), any(), any(), any(), any())).thenReturn(4200);

        newLoader(chunks.toString(), store.toString()).run();

        verify(chunkImporter).importChunks(
                eq(chunks), eq(SpellChunk.class), eq(mapper), eq(vectorStore), any(File.class));
    }

    private SpellDataLoader newLoader(String spellsPath, String storePath) {
        SpellDataLoader loader = new SpellDataLoader();
        ReflectionTestUtils.setField(loader, "chunkImporter", chunkImporter);
        ReflectionTestUtils.setField(loader, "mapper", mapper);
        ReflectionTestUtils.setField(loader, "vectorStore", vectorStore);
        ReflectionTestUtils.setField(loader, "spellsPath", spellsPath);
        ReflectionTestUtils.setField(loader, "vectorStorePath", storePath);
        return loader;
    }
}
