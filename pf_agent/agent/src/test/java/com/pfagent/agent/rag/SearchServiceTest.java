package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.SimpleVectorStore;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * SearchService 单元测试
 *
 * 覆盖：
 *  - 通用语义检索：多库独立召回后按相似度降序合并取 topK，请求参数透传
 *  - 枚举式元数据过滤：className+level / className 单独 / 多条件 AND / 模块路由
 *  - 防御分支：未知字段 → 空列表不查询；未知模块 → IllegalArgumentException
 */
@ExtendWith(MockitoExtension.class)
class SearchServiceTest {

    @Mock
    private SimpleVectorStore spellStore;
    @Mock
    private SimpleVectorStore classStore;
    @Mock
    private SimpleVectorStore featStore;
    @Mock
    private SimpleVectorStore raceStore;
    @Mock
    private SimpleVectorStore traitStore;
    @Mock
    private SimpleVectorStore equipmentStore;
    @Mock
    private SimpleVectorStore skillStore;
    @Mock
    private SimpleVectorStore ruleStore;

    /** 多库独立检索后按相似度降序合并取 topK */
    @Test
    void searchMergesBySimilarityDescAcrossStores() {
        Document classHigh = Document.builder().text("职业").score(0.9).build();
        Document spellHigh = Document.builder().text("法术").score(0.8).build();
        Document spellLow = Document.builder().text("法术低").score(0.7).build();
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(spellHigh, spellLow));
        when(classStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(classHigh));

        List<Document> result = service().search("女巫");

        assertThat(result).containsExactly(classHigh, spellHigh); // 0.9 → 0.8，top2
    }

    /** 构造带 topK 与阈值的检索请求 */
    @Test
    void searchBuildsRequestWithTopKAndThreshold() {
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of());

        service().search("火球术射程");

        ArgumentCaptor<SearchRequest> captor = ArgumentCaptor.forClass(SearchRequest.class);
        verify(spellStore).similaritySearch(captor.capture());
        SearchRequest req = captor.getValue();
        assertThat(req.getQuery()).isEqualTo("火球术射程");
        assertThat(req.getTopK()).isEqualTo(2);
        assertThat(req.getSimilarityThreshold()).isEqualTo(0.5);
    }

    /** 合并结果超过 topK 时截断 */
    @Test
    void searchTruncatesMergedResultsOverTopK() {
        Document d1 = Document.builder().text("a").score(1.0).build();
        Document d2 = Document.builder().text("b").score(0.9).build();
        Document d3 = Document.builder().text("c").score(0.8).build();
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(d1, d2, d3));
        when(classStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of());

        List<Document> result = service().search("q");

        assertThat(result).hasSize(2);
    }

    /** 指定 spell 模块时只查 spell 库 */
    @Test
    void searchSpellModuleQueriesOnlySpellStore() {
        Document d = Document.builder().text("火球").score(0.8).build();
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(d));

        List<Document> result = service().search("火球术射程", "spell");

        assertThat(result).containsExactly(d);
        verify(spellStore).similaritySearch(any(SearchRequest.class));
        verifyNoInteractions(classStore);
    }

    /** 指定 all 或 null 时查全部模块 */
    @Test
    void searchAllOrNullQueriesAllStores() {
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of());
        when(classStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of());

        service().search("q", "all");
        service().search("q", null);

        verify(spellStore, org.mockito.Mockito.times(2)).similaritySearch(any(SearchRequest.class));
        verify(classStore, org.mockito.Mockito.times(2)).similaritySearch(any(SearchRequest.class));
    }

    /** 未知模块返回空列表 */
    @Test
    void searchUnknownModuleReturnsEmptyList() {
        assertThat(service().search("q", "monster")).isEmpty();
        verifyNoInteractions(spellStore, classStore);
    }

    /** 指定 feat 模块时只查 feat 库 */
    @Test
    void searchFeatModuleQueriesOnlyFeatStore() {
        Document d = Document.builder().text("猛力攻击").score(0.85).build();
        when(featStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(d));

        List<Document> result = service().search("猛力攻击先决条件", "feat");

        assertThat(result).containsExactly(d);
        verify(featStore).similaritySearch(any(SearchRequest.class));
        verifyNoInteractions(spellStore, classStore);
    }

    // ---------- 枚举式元数据过滤 ----------

    /** className 加 level 走 spell 库且构造 AND 过滤请求 */
    @Test
    void searchByMetadataClassNameWithLevelRoutesToSpellAndAndFilter() {
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of());

        List<Document> result = service().searchByMetadata("spell", Map.of("className", "女巫", "level", "1"));

        assertThat(result).isEmpty();
        ArgumentCaptor<SearchRequest> captor = ArgumentCaptor.forClass(SearchRequest.class);
        verify(spellStore).similaritySearch(captor.capture());
        SearchRequest req = captor.getValue();
        assertThat(req.getQuery()).isEqualTo("spell");
        assertThat(req.getTopK()).isEqualTo(500);          // 枚举式大 topK
        assertThat(req.getFilterExpression()).isNotNull(); // AND 表达式已构造
    }

    /** 仅 className 时构造 has_spell 过滤请求 */
    @Test
    void searchByMetadataClassNameAloneBuildsHasSpellFilter() {
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of());

        service().searchByMetadata("spell", Map.of("className", "德鲁伊"));

        ArgumentCaptor<SearchRequest> captor = ArgumentCaptor.forClass(SearchRequest.class);
        verify(spellStore).similaritySearch(captor.capture());
        assertThat(captor.getValue().getFilterExpression()).isNotNull();
    }

    /** 多条件 AND 时路由到 class 库 */
    @Test
    void searchByMetadataMultiConditionAndRoutesToClassStore() {
        when(classStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of());

        service().searchByMetadata("class", Map.of(
                "className", "女巫", "featureSubtype", "hex", "book", "APG"));

        ArgumentCaptor<SearchRequest> captor = ArgumentCaptor.forClass(SearchRequest.class);
        verify(classStore).similaritySearch(captor.capture());
        SearchRequest req = captor.getValue();
        assertThat(req.getQuery()).isEqualTo("class");
        assertThat(req.getFilterExpression()).isNotNull();
        verifyNoInteractions(spellStore);
    }

    /** 全部字段未知时返回空列表、不查询 */
    @Test
    void searchByMetadataAllFieldsUnknownReturnsEmptyWithoutQuery() {
        List<Document> result = service().searchByMetadata("spell", Map.of("foo", "bar"));

        assertThat(result).isEmpty();
        verifyNoInteractions(spellStore);
    }

    /** 未知模块抛 IllegalArgumentException */
    @Test
    void searchByMetadataUnknownModuleThrowsIllegalArgument() {
        assertThatThrownBy(() -> service().searchByMetadata("monster", Map.of("className", "女巫")))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("未知数据模块");
    }

    // ---------- 方案 B（AKN-003）：class 基础职业页加分重排 ----------

    /** class 基础页相似度略低于变体时，加分后基础页排前 */
    @Test
    void searchClassBasePageBoostedAboveVariant() {
        // 基础页 0.68 vs 变体 0.69：咬紧（实际差 <0.02），+0.03 后基础页应居首
        Document basePage = classDoc("必须预先选择并准备法术", 0.68, "职业 → 基础职业 → 女巫");
        Document archetype = classDoc("灵脉守卫是自发施法者", 0.69, "职业 → 基础职业 → 女巫 → 职业变体");
        when(classStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(archetype, basePage));

        List<Document> result = service(0.03).search("女巫是准备施法者吗", "class");

        assertThat(result).containsExactly(basePage, archetype);
    }

    /** 问变体时基础页相似度极低，加分也不误伤变体 */
    @Test
    void searchVariantQueryBasePageBoostNotMisleading() {
        // 变体 0.74 vs 基础页 0.55（真实差 >0.6）：即使 +0.03，基础页仍在变体后
        Document basePage = classDoc("女巫基础能力", 0.55, "职业 → 基础职业 → 女巫");
        Document archetype = classDoc("树篱女巫变体能力", 0.74, "职业 → 基础职业 → 女巫 → 职业变体");
        when(classStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(archetype, basePage));

        List<Document> result = service(0.03).search("树篱女巫变体的能力", "class");

        assertThat(result).containsExactly(archetype, basePage);
    }

    /** 非 class 模块不加分重排 */
    @Test
    void searchNonClassModuleNotReranked() {
        // spell 模块基础页逻辑不应触发：两文档按原始相似度排序
        Document spellHigh = Document.builder().text("火球术").score(0.9).build();
        Document spellLow = Document.builder().text("火球术").score(0.8).build();
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(spellHigh, spellLow));

        List<Document> result = service(0.03).search("火球术", "spell");

        assertThat(result).containsExactly(spellHigh, spellLow);
    }

    /** class 模块扩容候选集 topK */
    @Test
    void searchClassModuleExpandsCandidateTopK() {
        when(classStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of());

        service(0.03).search("女巫职业等级表", "class");

        ArgumentCaptor<SearchRequest> captor = ArgumentCaptor.forClass(SearchRequest.class);
        verify(classStore).similaritySearch(captor.capture());
        // topK=2 + classExtraCandidates=3 → 5
        assertThat(captor.getValue().getTopK()).isEqualTo(5);
    }

    /** 核心职业基础页（CRB 牧师等，前缀「职业 → 核心职业 → 」）同样命中加分，压过同分邻居 */
    @Test
    void searchCoreClassBasePageBoostedAboveNeighbor() {
        Document basePage = classDoc("牧师领域与法术", 0.68, "职业 → 核心职业 → 牧师");
        Document neighbor = classDoc("牧师变体能力", 0.69, "职业 → 核心职业 → 牧师 → 神祇/领域");
        when(classStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(neighbor, basePage));

        List<Document> result = service(0.03).search("牧师是准备施法者吗", "class");

        assertThat(result).containsExactly(basePage, neighbor);
    }

    /** 核心职业深层页（神祇/领域等）不命中加分——若误命中会错误压过更高分邻居 */
    @Test
    void searchCoreClassDeepPageNotBoosted() {
        Document deep = classDoc("牧师的领域能力", 0.68, "职业 → 核心职业 → 牧师 → 神祇/领域");
        Document neighbor = classDoc("武僧基础页", 0.69, "职业 → 核心职业 → 武僧");
        when(classStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(deep, neighbor));

        List<Document> result = service(0.03).search("牧师领域", "class");

        // 深层页不命中：0.69 > 0.68 按原始相似度，武僧基础页居首；若深层页误命中 +0.03 → 0.71 会错误居首
        assertThat(result).containsExactly(neighbor, deep);
    }

    // ---------- F-002 检索端语义降权：空 text 过滤 + intro/reference 降权 ----------

    /** 空 text chunk 不进结果：即使相似度最高也剔除（无信息量，过滤而非降权） */
    @Test
    void searchFiltersOutBlankTextDocuments() {
        Document normal = doc("猛力攻击先决条件", 0.9, Map.of("component_type", "feat"));
        Document blank = doc("", 0.95, Map.of("component_type", "feat"));
        when(featStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(blank, normal));

        List<Document> result = service().search("猛力攻击先决条件", "feat");

        assertThat(result).containsExactly(normal);
    }

    /** filter-blank-text 关闭时保留空 text chunk（兼容极端场景，可回退） */
    @Test
    void searchBlankTextKeptWhenFilterDisabled() {
        Document normal = doc("猛力攻击", 0.9, Map.of());
        Document blank = doc("", 0.95, Map.of());
        when(featStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(blank, normal));

        List<Document> result = service(0.03, 0.03, false).search("猛力攻击", "feat");

        assertThat(result).containsExactly(blank, normal);
    }

    /** intro chunk 相似度略高于真实条目时，-0.03 后真实条目居首（对称于 class 基础页加分） */
    @Test
    void searchIntroChunkPenalizedBelowRealEntry() {
        Document featEntry = doc("猛力攻击先决条件", 0.69, Map.of("title", "猛力攻击", "component_type", "feat"));
        Document featIntro = doc("战斗专长列表", 0.70, Map.of("title", "战斗专长", "component_type", "feat_intro"));
        when(featStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(featIntro, featEntry));

        List<Document> result = service().search("猛力攻击先决条件", "feat");

        assertThat(result).containsExactly(featEntry, featIntro);
    }

    /** rule_reference 同 intro 语义：降权压后 */
    @Test
    void searchRuleReferencePenalizedBelowSection() {
        Document section = doc("攻击加值计算", 0.69, Map.of("title", "攻击", "component_type", "rule_section"));
        Document ref = doc("快速参考指引", 0.70, Map.of("title", "快速参考", "component_type", "rule_reference"));
        when(ruleStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(ref, section));

        List<Document> result = service().search("攻击加值", "rule");

        assertThat(result).containsExactly(section, ref);
    }

    /** 非 intro/reference 类型不受降权影响（不误伤普通条目） */
    @Test
    void searchNonIntroTypesNotPenalized() {
        Document d1 = doc("猛力攻击", 0.9, Map.of("component_type", "feat"));
        Document d2 = doc("团队专长", 0.8, Map.of("component_type", "feat"));
        when(featStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(d1, d2));

        List<Document> result = service().search("专长", "feat");

        assertThat(result).containsExactly(d1, d2);
    }

    /** intro-penalty 置 0 时行为与现状一致（配置可回退验证） */
    @Test
    void searchIntroPenaltyZeroPreservesOriginalOrder() {
        Document intro = doc("战斗专长", 0.70, Map.of("component_type", "feat_intro"));
        Document entry = doc("猛力攻击", 0.69, Map.of("component_type", "feat"));
        when(featStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(intro, entry));

        List<Document> result = service(0.03, 0.0, true).search("猛力攻击", "feat");

        assertThat(result).containsExactly(intro, entry);
    }

    // ---------- F-002 检索端语义降权：oversize 超长 chunk ----------

    /** oversize 超长 chunk（text>threshold）排序减分，压到正常条目之后 */
    @Test
    void searchOversizeChunkPenalizedBelowNormalEntry() {
        Document normal = doc("火球术射程 400 英尺", 0.69, Map.of("title", "火球术", "component_type", "spell"));
        Document oversize = doc("a".repeat(6000), 0.70, Map.of("title", "法术索引表", "component_type", "spell_index"));
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(oversize, normal));

        List<Document> result = service().search("火球术射程", "spell");

        assertThat(result).containsExactly(normal, oversize);
    }

    /** 未超过阈值的 chunk 不降权（阈值边界内按原始相似度排序） */
    @Test
    void searchBelowOversizeThresholdNotPenalized() {
        Document big = doc("b".repeat(5000), 0.90, Map.of("component_type", "rule_section"));
        Document small = doc("小片段", 0.80, Map.of("component_type", "rule_section"));
        when(ruleStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(big, small));

        List<Document> result = service().search("规则", "rule");

        // 恰好 5000 字符未超阈值，不被降权
        assertThat(result).containsExactly(big, small);
    }

    /** oversize-penalty 置 0 时行为与现状一致（配置可回退验证） */
    @Test
    void searchOversizePenaltyZeroPreservesOriginalOrder() {
        Document oversize = doc("c".repeat(6000), 0.70, Map.of("component_type", "spell_index"));
        Document normal = doc("火球术射程", 0.69, Map.of("component_type", "spell"));
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(oversize, normal));

        List<Document> result = service(0.03, 0.03, 0.0, 5000, true).search("火球术", "spell");

        assertThat(result).containsExactly(oversize, normal);
    }

    // ---------- P0-B2 修法 B：候选扩容 + title/aliases 词元命中加权 ----------

    /** 非 class 模块候选集也扩容：requestTopK = topK + rerankExtraCandidates（重排前截断问题对治） */
    @Test
    void searchNonClassModuleExpandsCandidateTopK() {
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of());

        service(0.03, 0.03, 0.02, 5000, true, 10, 0.0, List.of()).search("火球术射程", "spell");

        ArgumentCaptor<SearchRequest> captor = ArgumentCaptor.forClass(SearchRequest.class);
        verify(spellStore).similaritySearch(captor.capture());
        // topK=2 + rerankExtraCandidates=10 → 12
        assertThat(captor.getValue().getTopK()).isEqualTo(12);
    }

    /** class 模块候选集在 rerank 扩容基础上再叠加 class-extra-candidates（保留 AKN-003 既有机制） */
    @Test
    void searchClassModuleStacksRerankAndClassExtraCandidates() {
        when(classStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of());

        service(0.03, 0.03, 0.02, 5000, true, 10, 0.0, List.of()).search("女巫职业等级表", "class");

        ArgumentCaptor<SearchRequest> captor = ArgumentCaptor.forClass(SearchRequest.class);
        verify(classStore).similaritySearch(captor.capture());
        // topK=2 + rerank=10 + classExtra=3 → 15
        assertThat(captor.getValue().getTopK()).isEqualTo(15);
    }

    /** title 命中 query 词元时 +0.05，压过略高余弦的邻居（被点名的确切条目应居首） */
    @Test
    void searchTitleTokenMatchBoostsChunkAboveCosineNeighbor() {
        // 锚点 title 含 query 词元「精通擒抱」：0.65 + 0.05 = 0.70 > 邻居 0.69
        Document anchor = doc("精通擒抱的规则", 0.65, Map.of("title", "精通擒抱", "component_type", "feat"));
        Document neighbor = doc("战技加值计算", 0.69, Map.of("title", "战技", "component_type", "feat"));
        when(featStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(neighbor, anchor));

        List<Document> result = service(0.03, 0.03, 0.02, 5000, true, 0, 0.05, List.of())
                .search("精通擒抱", "feat");

        assertThat(result).containsExactly(anchor, neighbor);
    }

    /** aliases 命中 query 词元同样加分（title 不含词元时走 aliases 兜底） */
    @Test
    void searchAliasesTokenMatchBoostsChunk() {
        // 锚点 title 不含「擒抱」，aliases 含：0.65 + 0.05 = 0.70 > 邻居 0.69
        Document anchor = doc("战技技巧", 0.65, Map.of("title", "战技技巧", "aliases", "精通擒抱", "component_type", "feat"));
        Document neighbor = doc("战技加值计算", 0.69, Map.of("title", "战技", "component_type", "feat"));
        when(featStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(neighbor, anchor));

        List<Document> result = service(0.03, 0.03, 0.02, 5000, true, 0, 0.05, List.of())
                .search("擒抱", "feat");

        assertThat(result).containsExactly(anchor, neighbor);
    }

    /** 停用词词元被剔除后不触发加权（防「如何/什么/规则」等泛词大面积误加权） */
    @Test
    void searchStopwordTokensNotBoosted() {
        Document anchor = doc("叠加规则正文", 0.65, Map.of("title", "叠加", "component_type", "rule_section"));
        Document neighbor = doc("叠加规则", 0.69, Map.of("title", "叠加", "component_type", "rule_section"));
        when(ruleStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(anchor, neighbor));

        // query 全为停用词 → 词元为空 → 不加分，按原始相似度排序
        List<Document> result = service(0.03, 0.03, 0.02, 5000, true, 0, 0.05,
                        List.of("如何", "什么", "规则")).search("如何 什么 规则", "rule");

        assertThat(result).containsExactly(neighbor, anchor);
    }

    /** title-match-boost 置 0 时行为与现状一致（配置可回退验证） */
    @Test
    void searchTitleBoostZeroPreservesOriginalOrder() {
        Document anchor = doc("精通擒抱的规则", 0.65, Map.of("title", "精通擒抱", "component_type", "feat"));
        Document neighbor = doc("战技加值计算", 0.69, Map.of("title", "战技", "component_type", "feat"));
        when(featStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of(neighbor, anchor));

        List<Document> result = service(0.03, 0.03, 0.02, 5000, true, 0, 0.0, List.of())
                .search("精通擒抱", "feat");

        assertThat(result).containsExactly(neighbor, anchor);
    }

    // ---------- T3 防御性验证：spell title 过滤 eq 链路 ----------

    /** spell title 过滤构造非空 eq 表达式（medium-21 疑点：spell title 翻译已存在，防御性覆盖） */
    @Test
    void searchByMetadataSpellTitleBuildsEqFilter() {
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of());

        service().searchByMetadata("spell", Map.of("title", "防护邪恶"));

        ArgumentCaptor<SearchRequest> captor = ArgumentCaptor.forClass(SearchRequest.class);
        verify(spellStore).similaritySearch(captor.capture());
        assertThat(captor.getValue().getFilterExpression()).isNotNull();
    }

    private SearchService service() {
        return service(0.03, 0.03, 0.02, 5000, true, 0, 0.0, List.of());
    }

    private SearchService service(double classBaseBonus) {
        // 兼容旧签名：classBaseBonus 可变，其余降权参数用默认值
        return service(classBaseBonus, 0.03, 0.02, 5000, true, 0, 0.0, List.of());
    }

    /** Batch A 兼容：classBaseBonus / introPenalty / filterBlankText 可控，oversize 用默认值 */
    private SearchService service(double classBaseBonus, double introPenalty, boolean filterBlankText) {
        return service(classBaseBonus, introPenalty, 0.02, 5000, filterBlankText, 0, 0.0, List.of());
    }

    /** 全量参数版：classBaseBonus / introPenalty / oversizePenalty / oversizeThreshold / filterBlankText 均可控（F-002） */
    private SearchService service(double classBaseBonus, double introPenalty, double oversizePenalty,
                                  int oversizeThreshold, boolean filterBlankText) {
        return service(classBaseBonus, introPenalty, oversizePenalty, oversizeThreshold, filterBlankText,
                0, 0.0, List.of());
    }

    /** P0-B2 全量参数版：既有 F-002 五项 + rerankExtraCandidates / titleMatchBoost / titleBoostStopwords 可控 */
    private SearchService service(double classBaseBonus, double introPenalty, double oversizePenalty,
                                  int oversizeThreshold, boolean filterBlankText,
                                  int rerankExtraCandidates, double titleMatchBoost,
                                  List<String> titleBoostStopwords) {
        SearchService s = new SearchService();
        ReflectionTestUtils.setField(s, "spellStore", spellStore);
        ReflectionTestUtils.setField(s, "classStore", classStore);
        ReflectionTestUtils.setField(s, "featStore", featStore);
        ReflectionTestUtils.setField(s, "raceStore", raceStore);
        ReflectionTestUtils.setField(s, "traitStore", traitStore);
        ReflectionTestUtils.setField(s, "equipmentStore", equipmentStore);
        ReflectionTestUtils.setField(s, "skillStore", skillStore);
        ReflectionTestUtils.setField(s, "ruleStore", ruleStore);
        ReflectionTestUtils.setField(s, "filterTranslator", new FilterTranslator());
        ReflectionTestUtils.setField(s, "topK", 2);
        ReflectionTestUtils.setField(s, "similarityThreshold", 0.5);
        ReflectionTestUtils.setField(s, "enumerationTopK", 500);
        ReflectionTestUtils.setField(s, "classBaseBonus", classBaseBonus);
        ReflectionTestUtils.setField(s, "classExtraCandidates", 3);
        ReflectionTestUtils.setField(s, "introPenalty", introPenalty);
        ReflectionTestUtils.setField(s, "filterBlankText", filterBlankText);
        ReflectionTestUtils.setField(s, "oversizePenalty", oversizePenalty);
        ReflectionTestUtils.setField(s, "oversizeThreshold", oversizeThreshold);
        ReflectionTestUtils.setField(s, "rerankExtraCandidates", rerankExtraCandidates);
        ReflectionTestUtils.setField(s, "titleMatchBoost", titleMatchBoost);
        ReflectionTestUtils.setField(s, "titleBoostStopwords", titleBoostStopwords);
        s.initStores();
        return s;
    }

    /** 构造带 metadata 的 Document（component_type 等降权判据字段） */
    private Document doc(String text, double score, Map<String, Object> meta) {
        return Document.builder().text(text).score(score).metadata(meta).build();
    }

    private Document classDoc(String text, double score, String tocPath) {
        Map<String, Object> meta = tocPath == null ? Map.of() : Map.of("tocPath", tocPath);
        return Document.builder().text(text).score(score).metadata(meta).build();
    }
}
