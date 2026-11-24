package com.pfagent.agent.rag;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.ai.document.Document;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * RuleChunkMapper 单元测试（KN221，spec D6）
 *
 * 验证规则 StandardChunk → Document 映射：复用 StandardChunkMapper 统一映射
 * （来源书 / tocPath / title 对齐溯源约定），并把 nested metadata 的 4 个表格键
 * 扁平化为 Document 顶层键：has_table / table_ids / table_titles / table_row_counts。
 * 数据侧每个规则 chunk 都写这 4 键（无表时 has_table=false + 空列表）；metadata
 * 缺失/为 null 时须安全跳过，不影响基础映射。
 */
class RuleTableMapperTest {

    private final RuleChunkMapper mapper = new RuleChunkMapper();

    @BeforeEach
    void setUp() {
        ReflectionTestUtils.setField(mapper, "baseMapper", new StandardChunkMapper());
    }

    /** 基础映射保留 + 4 个表格键原样扁平化（列表值不序列化成字符串） */
    @Test
    void toDocumentPassesThroughTableMetadataKeepingBaseMapping() {
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("has_table", true);
        metadata.put("table_ids", List.of("rule_page_299_0000#t1"));
        metadata.put("table_titles", List.of("动物伙伴基本数据"));
        metadata.put("table_row_counts", List.of(20));
        StandardChunk c = new StandardChunk(
                "rule_page_299_0000", "page_299", "规则", "rule_section",
                "动物伙伴", "表格正文", "CRB", "核心规则书", "Core Rulebook", 90,
                "规则 → 战斗 → 动物伙伴", List.of(), metadata, Map.of());

        Document doc = mapper.toDocument(c);

        assertThat(doc.getText()).isEqualTo("表格正文");
        Map<String, Object> meta = doc.getMetadata();
        assertThat(meta.get("chunk_id")).isEqualTo("rule_page_299_0000");
        assertThat(meta.get("book_name_cn")).isEqualTo("核心规则书");
        assertThat(meta.get("tocPath")).isEqualTo("规则 → 战斗 → 动物伙伴");
        assertThat(meta.get("has_table")).isEqualTo(true);
        assertThat(meta.get("table_ids")).isEqualTo(List.of("rule_page_299_0000#t1"));
        assertThat(meta.get("table_titles")).isEqualTo(List.of("动物伙伴基本数据"));
        assertThat(meta.get("table_row_counts")).isEqualTo(List.of(20));
    }

    /** 无表 chunk：has_table=false + 空列表原样透传（数据侧口径，便于过滤） */
    @Test
    void toDocumentPassesEmptyTableMetadata() {
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("has_table", false);
        metadata.put("table_ids", List.of());
        metadata.put("table_titles", List.of());
        metadata.put("table_row_counts", List.of());
        StandardChunk c = new StandardChunk(
                "rule_page_1_0000", "page_1", "规则", "rule_section", "规则正文", "纯散文",
                "CRB", "核心规则书", "Core Rulebook", 90, null, null, metadata, null);

        Document doc = mapper.toDocument(c);

        assertThat(doc.getMetadata().get("has_table")).isEqualTo(false);
        assertThat(doc.getMetadata().get("table_ids")).isEqualTo(List.of());
        assertThat(doc.getMetadata().get("table_titles")).isEqualTo(List.of());
        assertThat(doc.getMetadata().get("table_row_counts")).isEqualTo(List.of());
        // 无 chm_toc_path 时回退 doc_id + title（StandardChunkMapper 约定）
        assertThat(doc.getMetadata().get("tocPath")).isEqualTo("page_1 > 规则正文");
    }

    /** metadata 为 null 时表格键全部跳过，基础映射不受影响 */
    @Test
    void toDocumentNullMetadataSkipsTableKeys() {
        StandardChunk c = new StandardChunk(
                "rule_page_2_0000", "page_2", "规则", "rule_intro", "引言", "正文",
                "CRB", "核心规则书", "Core Rulebook", 90, null, null, null, null);

        Document doc = mapper.toDocument(c);

        Map<String, Object> meta = doc.getMetadata();
        assertThat(meta.get("has_table")).isNull();
        assertThat(meta.get("table_ids")).isNull();
        assertThat(meta.get("table_titles")).isNull();
        assertThat(meta.get("table_row_counts")).isNull();
        assertThat(meta.get("chunk_id")).isEqualTo("rule_page_2_0000");
    }

    /** 只透传 4 个表格键：nested metadata 的其它键不进入 Document 顶层 */
    @Test
    void toDocumentIgnoresOtherNestedKeys() {
        StandardChunk c = new StandardChunk(
                "rule_page_3_0000", "page_3", "规则", "rule_table", "表格", "正文",
                "CRB", "核心规则书", "Core Rulebook", 90, null, null,
                Map.of("has_table", true, "other_key", "不应透传"), null);

        Document doc = mapper.toDocument(c);

        assertThat(doc.getMetadata().get("has_table")).isEqualTo(true);
        assertThat(doc.getMetadata()).doesNotContainKey("other_key");
    }
}
