package com.pfagent.agent.rag;

import jakarta.annotation.PostConstruct;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.ai.vectorstore.filter.FilterExpressionBuilder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 向量检索服务
 *
 * 两条检索路径（设计 §5.2）：
 *  1. {@link #search(String)}：跨模块语义检索——对八个模块（法术/职业/专长/种族/
 *     背景特性/装备/技能/规则）各库分别召回，按相似度降序合并取全局 topK。模块独立
 *     召回保证「跨域问题」（如"女巫职业"与"女巫法术"）都有机会命中各自语义词域。
 *  2. {@link #searchByMetadata(String, Map)}：枚举式元数据过滤——按逻辑字段（className/
 *     school 等，经 FilterTranslator 翻译为扁平键）精确过滤，配合大 topK + 无阈值
 *     （similarityThresholdAll），用于"按字段枚举"的确定性检索，不依赖语义相似度。
 *
 * topK 与相似度阈值通过 application.yml 的 pf.search.* 配置（带默认值）。
 */
@Service
public class SearchService {

    @Autowired
    @Qualifier("spellVectorStore")
    private VectorStore spellStore;
    @Autowired
    @Qualifier("classVectorStore")
    private VectorStore classStore;
    @Autowired
    @Qualifier("featVectorStore")
    private VectorStore featStore;
    @Autowired
    @Qualifier("raceVectorStore")
    private VectorStore raceStore;
    @Autowired
    @Qualifier("traitVectorStore")
    private VectorStore traitStore;
    @Autowired
    @Qualifier("equipmentVectorStore")
    private VectorStore equipmentStore;
    @Autowired
    @Qualifier("skillVectorStore")
    private VectorStore skillStore;
    @Autowired
    @Qualifier("ruleVectorStore")
    private VectorStore ruleStore;
    @Autowired
    private FilterTranslator filterTranslator;

    @Value("${pf.search.top-k:5}")
    private int topK;
    @Value("${pf.search.similarity-threshold:0.5}")
    private double similarityThreshold;
    @Value("${pf.search.enumeration-top-k:500}")
    private int enumerationTopK;
    /** 方案 B（AKN-003）：class 基础职业页排序加分。基础页与变体相似度咬紧（差 <0.02）
     *  时加分让基础页稳进 topK；问变体时基础页相似度天然低于阈值不在候选集，加分无影响。 */
    @Value("${pf.search.class-base-bonus:0.03}")
    private double classBaseBonus;
    @Value("${pf.search.class-extra-candidates:3}")
    private int classExtraCandidates;
    /** F-002：intro/reference 低信息量 chunk 排序减分（如 feat_intro/rule_reference）。
     *  仅影响排序不改 Document.score；置 0 关闭。降权不影响召回——被降权 chunk 仍在候选集。 */
    @Value("${pf.search.intro-penalty:0.03}")
    private double introPenalty;
    /** F-002：空 text chunk 无信息量（equipment 113 / feat 51 / skill 7 等），
     *  进库即空 embedding，检索时剔除而非降权；置 false 关闭。 */
    @Value("${pf.search.filter-blank-text:true}")
    private boolean filterBlankText;
    /** F-002：oversize 超长 chunk 排序减分。超长 embedding 语义稀释（如 spell 索引表
     *  43085 字符），排序减分压后；仅排序不改 score，置 0 关闭。 */
    @Value("${pf.search.oversize-penalty:0.02}")
    private double oversizePenalty;
    /** F-002：oversize 判定阈值（text 字符数），超过才减分 */
    @Value("${pf.search.oversize-threshold:5000}")
    private int oversizeThreshold;
    /** P0-B2：候选集扩容（topK + N，全模块）。重排前候选集只有 topK 条，锚点若原始余弦
     *  排 16 名外则任何排序加权都救不到；扩容给 title/基础页加权留重排空间。置 0 关闭。 */
    @Value("${pf.search.rerank-extra-candidates:10}")
    private int rerankExtraCandidates;
    /** P0-B2：检索词元命中 chunk title/aliases 的排序加分（仅排序，不改 score）。
     *  title 不进 embedding，vectorSearch 对「已知确切条目名」的查询低效，加权把被点名的
     *  确切条目抬过语义相近邻居；置 0 关闭。 */
    @Value("${pf.search.title-match-boost:0.05}")
    private double titleMatchBoost;
    /** P0-B2：title 加权停用词表，防止「如何/什么/规则」等泛词大面积误加权 */
    @Value("${pf.search.title-boost-stopwords:法术,规则,专长,效果,职业,装备,物品,魔法,如何,什么,哪些,途径,方法,of,the,and,to,in}")
    private List<String> titleBoostStopwords;

    private Map<String, VectorStore> storesByModule;
    private List<VectorStore> vectorStores;

    /**
     * 跨模块语义检索（通用路径）
     *
     * @param question 用户问题（作为 query 向量化）
     * @return 各模块合并后相似度达标的 Document 列表，按相似度降序取 topK
     */
    public List<Document> search(String question) {
        return search(question, "all");
    }

    /**
     * 语义检索（支持按模块路由）
     *
     * @param question 用户问题（作为 query 向量化）
     * @param module   spell / class / all；未知模块返回空列表（模块合法性由工具层校验）
     * @return 目标模块合并后相似度达标的 Document 列表，按相似度降序取 topK
     */
    public List<Document> search(String question, String module) {
        // 方案 B（AKN-003）：class 模块在 rerank 扩容基础上再叠加 class-extra-candidates，给基础页加分重排留空间
        boolean classModule = "class".equals(module);
        int requestTopK = topK + rerankExtraCandidates + (classModule ? classExtraCandidates : 0);
        // P0-B2：query 词元抽一次，供 title/aliases 加权重排共用
        List<String> tokens = extractTokens(question);
        SearchRequest request = SearchRequest.builder()
                .query(question)
                .topK(requestTopK)
                .similarityThreshold(similarityThreshold)
                .build();
        return resolveStores(module).stream()
                .flatMap(store -> store.similaritySearch(request).stream())
                .filter(doc -> !filterBlankText || !isBlankText(doc)) // 空 text 剔除（F-002）
                .sorted(Comparator.comparingDouble((Document doc) -> rankedScore(doc, classModule, tokens))
                        .reversed())
                .limit(topK)
                .toList();
    }

    /**
     * 枚举式元数据过滤（精确路径，设计 §5.2）
     *
     * 把逻辑过滤字段翻译为扁平条件后构造 AND 表达式，用大 topK + 相似度阈值全放行
     * 检索——结果数量由过滤条件决定而非相似度截断，保证枚举完整性
     * （如"女巫 3 环法术"应返回全部命中，而非语义上最相近的 N 条）。
     *
     * @param module  数据模块，spell / class / feat / race / trait / equipment / skill / rule
     * @param filters 逻辑字段 → 期望值（className/school 等）
     * @return 过滤命中的 Document 列表；模块非法或无可执行条件时为空列表
     * @throws IllegalArgumentException 模块名非法时
     */
    public List<Document> searchByMetadata(String module, Map<String, String> filters) {
        VectorStore store = storesByModule.get(module);
        if (store == null) {
            throw new IllegalArgumentException("未知数据模块: " + module + "，可用模块: spell/class/feat/race/trait/equipment/skill/rule");
        }
        List<FilterField> conditions = filterTranslator.translate(module, filters);
        if (conditions.isEmpty()) {
            return List.of();
        }

        // 全部条件 AND 连接：eq 是 metadata 标量精确匹配（扁平键由 FilterTranslator 保证存在）
        FilterExpressionBuilder builder = new FilterExpressionBuilder();
        FilterExpressionBuilder.Op op = null;
        for (FilterField condition : conditions) {
            FilterExpressionBuilder.Op eq = builder.eq(condition.key(), condition.value());
            op = op == null ? eq : builder.and(op, eq);
        }

        SearchRequest request = SearchRequest.builder()
                .query(module)
                .topK(enumerationTopK)
                .similarityThresholdAll()
                .filterExpression(op.build())
                .build();
        return store.similaritySearch(request);
    }

    /** 模块索引：依赖注入完成后构建（八模块 store → 名称索引 + 全量列表），检索按模块路由 */
    @PostConstruct
    void initStores() {
        Map<String, VectorStore> map = new LinkedHashMap<>();
        map.put("spell", spellStore);
        map.put("class", classStore);
        map.put("feat", featStore);
        map.put("race", raceStore);
        map.put("trait", traitStore);
        map.put("equipment", equipmentStore);
        map.put("skill", skillStore);
        map.put("rule", ruleStore);
        this.storesByModule = Map.copyOf(map);
        this.vectorStores = List.copyOf(map.values());
    }

    /**
     * 统一排序分（F-002 收敛所有排序调整，单点可控）：
     *   base 相似度
     *   + class 基础职业页加分（AKN-003 方案 B：基础页与变体相似度咬紧时稳进 topK，
     *     问变体时基础页远低于阈值不在候选集，加分无影响）
     *   - intro/reference 低信息量减分（F-002：feat_intro/rule_reference 等章节/目录引导
     *     类 chunk 与具体条目竞争 topK 的噪声，压后但仍在候选集）
     *   - oversize 超长减分（F-002：超长 embedding 语义稀释，如 spell 索引表）
     *   + title/aliases 词元命中加分（P0-B2：被点名的确切条目抬过语义相近邻居）
     * 全部仅影响排序，不改 Document.score；各惩罚项置 0 即关闭。
     */
    private double rankedScore(Document doc, boolean classModule, List<String> queryTokens) {
        Double score = doc.getScore();
        double s = score == null ? 0.0 : score;
        if (classModule && classBaseBonus > 0 && isBaseClassPage(doc)) {
            s += classBaseBonus;
        }
        if (introPenalty > 0 && isIntroOrReference(doc)) {
            s -= introPenalty;
        }
        if (oversizePenalty > 0 && isOversize(doc)) {
            s -= oversizePenalty;
        }
        if (titleMatchBoost > 0 && !queryTokens.isEmpty() && titleOrAliasesMatch(doc, queryTokens)) {
            s += titleMatchBoost;
        }
        return s;
    }

    /** oversize 判定：text 长度超过阈值（>，不含等于） */
    private boolean isOversize(Document doc) {
        String text = doc.getText();
        return text != null && text.length() > oversizeThreshold;
    }

    /** 空 text 判定：text 为 null 或纯空白（StandardChunkMapper 可能映射为 ""） */
    private boolean isBlankText(Document doc) {
        String text = doc.getText();
        return text == null || text.isBlank();
    }

    /** intro/reference 低信息量判定：component_type 以 _intro / _reference 结尾 */
    private boolean isIntroOrReference(Document doc) {
        Object ct = doc.getMetadata().get("component_type");
        if (!(ct instanceof String type)) {
            return false;
        }
        return type.endsWith("_intro") || type.endsWith("_reference");
    }

    /** 基础职业页判定：tocPath 恰为「职业 → 核心职业/基础职业 → X」，无更细分后缀（变体/巫术/庇护主）。
     *  两个前缀同为"基础职业页"语义：核心职业（CRB 牧师/战士等，约 3398 条）与基础职业
     *  （APG 扩展书炼金术师/女巫等，约 2168 条）；深层页（含「 → 」后缀）均不命中。 */
    private boolean isBaseClassPage(Document doc) {
        Object toc = doc.getMetadata().get("tocPath");
        if (!(toc instanceof String tp)) {
            return false;
        }
        List<String> prefixes = List.of("职业 → 核心职业 → ", "职业 → 基础职业 → ");
        return prefixes.stream().anyMatch(prefix -> tp.startsWith(prefix)
                && !tp.substring(prefix.length()).contains(" → "));
    }

    /** title/aliases 词元匹配：任一 query 词元是 title 或 aliases 的子串即命中（一次命中只加一次分）。
     *  title/aliases 从 metadata 读；aliases 由 mapper 存为逗号拼接字符串，缺失时为空串。 */
    private boolean titleOrAliasesMatch(Document doc, List<String> tokens) {
        Object title = doc.getMetadata().get("title");
        Object aliases = doc.getMetadata().get("aliases");
        String titleText = title == null ? "" : title.toString();
        String aliasesText = aliases == null ? "" : aliases.toString();
        return tokens.stream().anyMatch(tok -> titleText.contains(tok) || aliasesText.contains(tok));
    }

    /** 检索 query 词元抽取：按非字母字符切分，CJK 连续串长度 ≥2、ASCII 词长度 ≥2（小写化）入选，
     *  剔除停用词后去重。CJK 连续串整体作为一个词元（如「法力再生珍珠」）；中英混合 query 靠空格/
     *  标点把关键词隔离成独立段才能被独立提取。 */
    private List<String> extractTokens(String query) {
        if (query == null || query.isBlank()) {
            return List.of();
        }
        Set<String> stop = titleBoostStopwords.stream()
                .map(word -> word.toLowerCase(Locale.ROOT))
                .collect(Collectors.toSet());
        Set<String> tokens = new LinkedHashSet<>();
        for (String part : query.split("[\\P{L}]+")) {
            if (part.isEmpty()) {
                continue;
            }
            String norm = part.codePoints().anyMatch(Character::isIdeographic)
                    ? part
                    : part.toLowerCase(Locale.ROOT);
            if (norm.length() < 2 || stop.contains(norm)) {
                continue;
            }
            tokens.add(norm);
        }
        return List.copyOf(tokens);
    }

    /** 模块 → 目标向量库；all/null 返回全部，未知模块返回空 */
    private List<VectorStore> resolveStores(String module) {
        if (module == null || "all".equals(module)) {
            return vectorStores;
        }
        VectorStore store = storesByModule.get(module);
        return store == null ? List.of() : List.of(store);
    }
}
