package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.ai.document.Document;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * getClassTable 工具边界补充测试（QA 白盒审计追加，2026-09-22）
 *
 * coder 6 条工具测试覆盖了 25（上越界）/null/未知/missing/降级；
 * 补充：
 *  - level=0 与负数（下越界）同样走越界分支
 *  - 溯源降级合成 Document 确实进 SourceCollector（捕获 collector.add 实参，
 *    验证 [#N] 链路上降级文档不缺席）
 */
@ExtendWith(MockitoExtension.class)
class RetrievalToolsClassTableBoundaryTest {

    @Mock
    private SearchService searchService;
    @Mock
    private SourceCollector collector;
    @Mock
    private DataGapRecorder recorder;
    @Mock
    private SpellListService spellListService;
    @Mock
    private ClassTableService classTableService;

    /** level=0：下越界，提示等级范围 + 全表，不查单行 */
    @Test
    void getClassTableLevelZeroReturnsOutOfRangeHint() {
        when(classTableService.isAvailable()).thenReturn(true);
        when(classTableService.resolve("法师")).thenReturn("法师");
        when(classTableService.maxLevel("法师")).thenReturn(20);
        when(classTableService.formatTable("法师")).thenReturn("「法师」成长表（1~20 级）");
        when(classTableService.provenanceDocument("法师"))
                .thenReturn(Document.builder().text("t").metadata(Map.of("title", "表：法师")).build());
        when(collector.add(any())).thenReturn(List.of(1));

        String result = tools().getClassTable("法师", 0);

        assertThat(result).contains("越界", "1~20");
    }

    /** level 负数：下越界，同走越界分支 */
    @Test
    void getClassTableNegativeLevelReturnsOutOfRangeHint() {
        when(classTableService.isAvailable()).thenReturn(true);
        when(classTableService.resolve("法师")).thenReturn("法师");
        when(classTableService.maxLevel("法师")).thenReturn(20);
        when(classTableService.formatTable("法师")).thenReturn("「法师」成长表（1~20 级）");
        when(classTableService.provenanceDocument("法师"))
                .thenReturn(Document.builder().text("t").metadata(Map.of("title", "表：法师")).build());
        when(collector.add(any())).thenReturn(List.of(1));

        String result = tools().getClassTable("法师", -3);

        assertThat(result).contains("越界", "1~20");
    }

    /** 溯源降级场景：provenanceDocument 返回合成 Document（点查未命中产物），
     *  该 Document 必须原样进 SourceCollector（[#N] 链路不缺席） */
    @Test
    void getClassTableSyntheticProvenanceDocGoesIntoCollector() {
        Document synthetic = Document.builder()
                .text("法师职业成长表（数据侧 class_tables.json 预整理；向量库未检索到对应原文 chunk…）")
                .metadata(Map.of(
                        "title", "法师职业成长表",
                        "chunk_id", "class_page_66_0001",
                        "doc_id", "核心职业/法师/page_66.md"))
                .build();
        when(classTableService.isAvailable()).thenReturn(true);
        when(classTableService.resolve("法师")).thenReturn("法师");
        when(classTableService.maxLevel("法师")).thenReturn(20);
        when(classTableService.formatRow("法师", 5)).thenReturn("「法师」等级 5：BAB +2");
        when(classTableService.provenanceDocument("法师")).thenReturn(synthetic);
        when(collector.add(any())).thenReturn(List.of(7));

        String result = tools().getClassTable("法师", 5);

        assertThat(result).contains("来源编号 [#7]");
        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<Document>> captor = ArgumentCaptor.forClass(List.class);
        verify(collector).add(captor.capture());
        assertThat(captor.getValue()).containsExactly(synthetic);
    }

    private RetrievalTools tools() {
        RetrievalTools tools = new RetrievalTools();
        ReflectionTestUtils.setField(tools, "searchService", searchService);
        ReflectionTestUtils.setField(tools, "collector", collector);
        ReflectionTestUtils.setField(tools, "recorder", recorder);
        ReflectionTestUtils.setField(tools, "spellListService", spellListService);
        ReflectionTestUtils.setField(tools, "classTableService", classTableService);
        ReflectionTestUtils.setField(tools, "metadataResultChars", 1500);
        ReflectionTestUtils.setField(tools, "vectorResultChars", 1500);
        return tools;
    }
}
