package com.pfagent.agent.rag;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SimpleVectorStore;
import org.springframework.test.util.ReflectionTestUtils;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

/**
 * ChunkImporter 单元测试 — 通用 JSONL 导入器
 *
 * 覆盖：文件缺失报错、正常导入（入库+持久化+返回总数）、空行跳过、
 * 超过批量大小时分批入库（用快照捕获，因 add 传入的 list 会被 clear 复用）。
 *
 * SP1 §4 收口：落盘从 vectorStore.save(File) 迁移到 VectorStorePersistence.save，
 * 此处 mock persistence 并断言调用迁移。
 */
@ExtendWith(MockitoExtension.class)
class ChunkImporterTest {

    @Mock
    private SimpleVectorStore vectorStore;
    @Mock
    private VectorStorePersistence persistence;

    @TempDir
    Path tempDir;

    private final ChunkImporter importer = new ChunkImporter();
    private final SpellChunkMapper mapper = new SpellChunkMapper();

    @BeforeEach
    void injectPersistence() {
        ReflectionTestUtils.setField(importer, "persistence", persistence);
    }

    /** chunks 文件不存在时抛出带路径的错误 */
    @Test
    void importChunksMissingFileThrowsWithPath() {
        assertThatThrownBy(() -> importer.importChunks(
                tempDir.resolve("missing.jsonl"), SpellChunk.class, mapper, vectorStore, storeFile()))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("chunks 文件不存在");
    }

    /** 正常导入：入库、保存并返回总数 */
    @Test
    void importChunksImportsStoresAndReturnsCount() throws IOException {
        Files.writeString(chunksFile(), spellLine(0) + "\n" + spellLine(1) + "\n");

        int total = importer.importChunks(chunksFile(), SpellChunk.class, mapper, vectorStore, storeFile());

        assertThat(total).isEqualTo(2);
        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<Document>> captor = ArgumentCaptor.forClass(List.class);
        verify(vectorStore, times(1)).add(captor.capture());
        assertThat(captor.getValue()).hasSize(2);
        verify(persistence).save(vectorStore, storeFile().getPath());
    }

    /** 导入时空行被跳过 */
    @Test
    void importChunksSkipsBlankLines() throws IOException {
        Files.writeString(chunksFile(), spellLine(0) + "\n\n" + spellLine(1) + "\n");

        int total = importer.importChunks(chunksFile(), SpellChunk.class, mapper, vectorStore, storeFile());

        assertThat(total).isEqualTo(2);
        verify(vectorStore, times(1)).add(anyList());
    }

    /** 超过批量大小时分批入库 */
    @Test
    void importChunksSplitsBatchesOverBatchSize() throws IOException {
        int total = 501; // BATCH_SIZE=500，应分成 500 + 1 两批
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < total; i++) {
            sb.append(spellLine(i)).append('\n');
        }
        Files.writeString(chunksFile(), sb);

        // add(batch) 传入的是会被 clear 复用的同一 ArrayList，必须在调用时立即复制快照
        List<List<Document>> snapshots = new ArrayList<>();
        doAnswer(inv -> {
            @SuppressWarnings("unchecked")
            List<Document> arg = inv.getArgument(0);
            snapshots.add(new ArrayList<>(arg));
            return null;
        }).when(vectorStore).add(anyList());

        importer.importChunks(chunksFile(), SpellChunk.class, mapper, vectorStore, storeFile());

        assertThat(snapshots).hasSize(2);
        assertThat(snapshots.get(0)).hasSize(500);
        assertThat(snapshots.get(1)).hasSize(1);
        verify(vectorStore, times(2)).add(anyList());
        verify(persistence).save(vectorStore, storeFile().getPath());
    }

    /** 生成一行合法法术 JSONL */
    private static String spellLine(int i) {
        return "{\"chunk_id\":\"spell_CRB_" + String.format("%04d", i)
                + "\",\"doc_id\":\"CRB\",\"category\":\"spell\",\"component_type\":\"spell\",\"title\":\"火球术" + i
                + "\",\"text\":\"text" + i + "\",\"book_abbreviation\":\"CRB\",\"book_name_cn\":\"核心规则书\","
                + "\"book_name_en\":\"CRB\",\"source_confidence\":1,\"aliases\":null,\"metadata\":{},\"extra\":{}}";
    }

    private Path chunksFile() {
        return tempDir.resolve("chunks.jsonl");
    }

    private File storeFile() {
        return tempDir.resolve("store.json").toFile();
    }
}
