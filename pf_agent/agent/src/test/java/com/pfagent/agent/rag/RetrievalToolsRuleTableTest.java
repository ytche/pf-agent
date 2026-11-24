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
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * getRuleTable 工具测试（KN221，spec D8~D11）
 *
 * 覆盖 LLM 侧行为契约：
 *  - 产物不可用 / 空表名 → 可读提示，不抛
 *  - 未收录表名 → 如实提示 + 检索建议，不编造、不挂溯源
 *  - 模糊多命中 → 候选清单要求消歧，不猜第一张、不挂溯源
 *  - 单表命中 → 服务格式化结果 + 真实/合成溯源 Document 进 SourceCollector（[#N] 不缺席）
 *  - row 参数原样透传给服务（5 / 5级 / 第5行 兼容由服务层测试覆盖）
 */
@ExtendWith(MockitoExtension.class)
class RetrievalToolsRuleTableTest {

    @Mock
    private RuleTableService ruleTableService;
    @Mock
    private SourceCollector collector;

    private RuleTableService.RuleTable table(String tableId, String chunkId) {
        return new RuleTableService.RuleTable(
                tableId, chunkId, "page_299", 1, "standard", "", "动物伙伴基本数据",
                List.of("等级", "", "HD", "", "BAB"),
                List.of(List.of("5", "", "5", "", "+3")),
                false, 20, 3, 24,
                List.of("| 表：动物伙伴基本数据 |", "| --- |"));
    }

    /** 产物未加载：降级提示，不调用服务查询 */
    @Test
    void unavailableReturnsHint() {
        when(ruleTableService.isAvailable()).thenReturn(false);

        String result = tools().getRuleTable("动物伙伴基本数据", "5");

        assertThat(result).contains("rule_tables.json 未加载", "vectorSearch");
        verifyNoInteractions(collector);
    }

    /** 空表名：提示用法，不查询 */
    @Test
    void blankTableReturnsUsageHint() {
        when(ruleTableService.isAvailable()).thenReturn(true);

        String result = tools().getRuleTable("  ", null);

        assertThat(result).contains("请提供表名或 table_id", "getRuleTable");
        verifyNoInteractions(collector);
        verify(ruleTableService, never()).find(any());
    }

    /** 未收录：如实提示 + 检索建议，不编造、不挂来源 */
    @Test
    void unknownTableReturnsReadableMiss() {
        when(ruleTableService.isAvailable()).thenReturn(true);
        when(ruleTableService.find("不存在的表")).thenReturn(List.of());

        String result = tools().getRuleTable("不存在的表", null);

        assertThat(result).contains("未收录表名「不存在的表」", "searchByMetadata", "不要编造表格数值");
        verifyNoInteractions(collector);
    }

    /** 模糊多命中：返回候选清单要求消歧，不猜第一张、不挂来源 */
    @Test
    void ambiguousTableReturnsCandidatesWithoutProvenance() {
        List<RuleTableService.RuleTable> matches = List.of(
                table("rule_page_120_0000#t1", "rule_page_120_0000"),
                table("rule_page_121_0000#t1", "rule_page_121_0000"));
        when(ruleTableService.isAvailable()).thenReturn(true);
        when(ruleTableService.find("状态数值表")).thenReturn(matches);
        when(ruleTableService.formatCandidates("状态数值表", matches)).thenReturn("候选清单");

        String result = tools().getRuleTable("状态数值表", null);

        assertThat(result).isEqualTo("候选清单");
        verifyNoInteractions(collector);
        verify(ruleTableService, never()).formatTable(any(), any());
    }

    /** 单表命中：格式化结果 + row 透传 + 溯源 Document 进 SourceCollector（[#3]） */
    @Test
    void singleMatchFormatsTableAndAttachesProvenance() {
        RuleTableService.RuleTable matched = table("rule_page_299_0000#t1", "rule_page_299_0000");
        Document provenance = Document.builder().text("原文")
                .metadata(Map.of("chunk_id", "rule_page_299_0000")).build();
        when(ruleTableService.isAvailable()).thenReturn(true);
        when(ruleTableService.find("动物伙伴基本数据")).thenReturn(List.of(matched));
        when(ruleTableService.provenanceDocument(matched)).thenReturn(provenance);
        when(ruleTableService.formatTable(matched, "5级")).thenReturn("行 5: 5 |  | 5 |  | +3");
        CollectorStubs.stubIds(collector, List.of(3));

        String result = tools().getRuleTable("动物伙伴基本数据", "5级");

        assertThat(result).contains("行 5: 5 |  | 5 |  | +3", "来源编号 [#3]");
        verify(ruleTableService).formatTable(matched, "5级");
        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<Document>> captor = ArgumentCaptor.forClass(List.class);
        verify(collector).addWithLimit(captor.capture());
        assertThat(captor.getValue()).containsExactly(provenance);
    }

    /** row 省略（null）原样透传，由服务返回表头 + 前 20 行 */
    @Test
    void nullRowIsPassedThrough() {
        RuleTableService.RuleTable matched = table("rule_page_299_0000#t1", "rule_page_299_0000");
        Document provenance = Document.builder().text("原文").metadata(Map.of()).build();
        when(ruleTableService.isAvailable()).thenReturn(true);
        when(ruleTableService.find("rule_page_299_0000#t1")).thenReturn(List.of(matched));
        when(ruleTableService.provenanceDocument(matched)).thenReturn(provenance);
        when(ruleTableService.formatTable(matched, null)).thenReturn("表头: 等级");
        CollectorStubs.stubIds(collector, List.of());

        String result = tools().getRuleTable("rule_page_299_0000#t1", null);

        assertThat(result).isEqualTo("表头: 等级");
        assertThat(result).doesNotContain("来源编号");
    }

    private RetrievalTools tools() {
        RetrievalTools t = new RetrievalTools();
        ReflectionTestUtils.setField(t, "ruleTableService", ruleTableService);
        ReflectionTestUtils.setField(t, "collector", collector);
        return t;
    }
}
