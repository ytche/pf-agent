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

import java.util.ArrayList;
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
    /** J4：全局书过滤（blacklist 默认剔 "?"），在 blank 剔除后、排序前统一过滤两条检索路径 */
    @Autowired
    private BookFilter bookFilter;

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
                .filter(bookFilter::keep) // J4 全局书过滤（排序前过滤，被剔条目释放 topK 名额）
                .sorted(Comparator.comparingDouble((Document doc) -> rankedScore(doc, classModule, tokens))
                        .reversed())
                .limit(topK)
                .toList();
    }

    /**
     * 枚举式元数据过滤（旧签名，SP8a J2 起为兼容保留）
     *
     * 仅供无 or/范围/排序需求的 AND 精确过滤调用；内部委托给
     * {@link #searchByMetadata(String, MetadataSearchQuery)}，行为与旧实现一致
     * （单模块 store、全部条件 AND、大 topK + 相似度阈值全放行）。
     */
    public List<Document> searchByMetadata(String module, Map<String, String> filters) {
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(filters);
        return searchByMetadata(module, query);
    }

    /**
     * 分页元数据：当页 + 真实总数（skip/limit 截断之前）。
     *
     * @param page       当前页 Document 列表（已去重、排序、分页）
     * @param totalCount 过滤+去重+排序后、skip/limit 之前的完整结果数（不受 limit 截断影响）
     * @param offset     当前页起始下标（钳制后，≥0）
     * @param limit      页大小（钳制后，≥1）
     * @param capped     是否有任一 store 的原始命中数达到 enumerationTopK（总数可能被检索上限截断）
     * @param cap        单库检索上限（enumerationTopK；跨模块合并后的 totalCount 可大于 cap）
     */
    public record PagedResult(List<Document> page, int totalCount, int offset, int limit,
            boolean capped, int cap) {

        /** 未触达检索上限的兼容构造（测试/旧调用）。 */
        public PagedResult(List<Document> page, int totalCount, int offset, int limit) {
            this(page, totalCount, offset, limit, false, 0);
        }

        /** 当前页之后是否还有结果（检索上限内；limit 截断时为 true，即使当页已全部展示） */
        public boolean hasMore() {
            return offset + page.size() < totalCount;
        }
    }

    /**
     * 枚举式元数据过滤（增强版，SP8a J2）
     *
     * 支持 orFilters（组内 OR）/ gte / lte 范围比较 / sort 排序 / limit+offset 分页 /
     * module="all" 跨模块（八库分别查询后按 (module, chunk_id) 去重合并）。
     * 过滤表达式由 FilterTranslator 翻译后的条件组组装——eq 条件与 or 组、gte、lte
     * 之间为 AND；单库候选 ≤ enumerationTopK，all 合并后可超过该值；排序与分页在合并后内存施加。
     *
     * @param module spell / class / feat / race / trait / equipment / skill / rule / all
     * @param query  过滤参数对象（字段名校验与空查询提示在工具层完成）
     * @return 过滤命中的 Document 列表（已去重、排序、分页）；无可执行条件时为空列表
     * @throws IllegalArgumentException 模块名非法时（"all" 除外）
     */
    public List<Document> searchByMetadata(String module, MetadataSearchQuery query) {
        return searchByMetadataPaged(module, query).page();
    }

    /**
     * 与 {@link #searchByMetadata} 相同，但额外返回分页元数据（真实总数/offset/limit），
     * 供工具层输出 has_more/next_offset 提示；真实总数不受 limit 截断影响。
     * 任一库原始命中数达到 enumerationTopK 时 {@link PagedResult#capped()} 为 true，
     * 此时 totalCount 只是检索上限内的条数，实际命中可能更多。
     *
     * F-026：无业务条件时不再逐库跳过，而是构建不带用户过滤表达式的查询（仅由工具层在
     * 用户明确放行后调用），并按 title → module → chunk_id 等确定性规则排序；模块可用性、
     * 全局书过滤、500 上限、跨模块合并去重与 capped 语义保持不变。
     */
    public PagedResult searchByMetadataPaged(String module, MetadataSearchQuery query) {
        List<VectorStore> stores = resolveStores(module);
        if (module != null && !"all".equals(module) && stores.isEmpty()) {
            throw new IllegalArgumentException("未知数据模块: " + module + "，可用模块: spell/class/feat/race/trait/equipment/skill/rule");
        }

        // 跨模块：逐库用各自模块名翻译（spell 组合键等模块专属逻辑只对 spell 库生效），
        // 每库构造自己的过滤表达式分别查询；查询时携带模块名（写入 metadata.pf_module
        // 供展示层标注），合并后按 (module, chunk_id) 去重（chunk_id 缺失退化为 doc id）
        Map<String, Document> merged = new LinkedHashMap<>();
        boolean capped = false;
        // F-026：无业务条件时不再跳过查询，而是走不带用户过滤表达式的无条件路径
        // （仅由用户明确放行后到达；模块可用性/全局过滤/500 上限/合并去重语义不变）
        boolean unconditional = !query.hasAnyCondition();
        for (VectorStore store : stores) {
            String storeModule = moduleOf(store);
            String effectiveModule = "all".equals(module) || module == null ? storeModule : module;
            FilterTranslator.TranslatedQuery conditions = filterTranslator.translateQuery(effectiveModule, query);
            if (!unconditional && conditions.isEmpty()) {
                continue; // 该库无可执行条件（如 spell level 无 className），跳过不查询
            }
            FilterExpressionBuilder builder = new FilterExpressionBuilder();
            FilterExpressionBuilder.Op op = null;
            for (FilterField condition : conditions.eq()) {
                op = and(builder, op, builder.eq(condition.key(), condition.value()));
            }
            for (FilterTranslator.TranslatedQuery.OrGroup group : conditions.or()) {
                FilterExpressionBuilder.Op groupOp = null;
                for (FilterField alternative : group.alternatives()) {
                    groupOp = groupOp == null ? builder.eq(alternative.key(), alternative.value())
                            : builder.or(groupOp, builder.eq(alternative.key(), alternative.value()));
                }
                if (groupOp != null) {
                    op = and(builder, op, builder.group(groupOp));
                }
            }
            for (FilterField condition : conditions.gte()) {
                op = and(builder, op, builder.gte(condition.key(), condition.value()));
            }
            for (FilterField condition : conditions.lte()) {
                op = and(builder, op, builder.lte(condition.key(), condition.value()));
            }
            SearchRequest.Builder requestBuilder = SearchRequest.builder()
                    .query(effectiveModule)
                    .topK(enumerationTopK)
                    .similarityThresholdAll();
            if (op != null) {
                requestBuilder.filterExpression(op.build());
            }
            List<Document> hits = store.similaritySearch(requestBuilder.build());
            if (hits.size() >= enumerationTopK) {
                capped = true;
            }
            for (Document doc : hits) {
                doc.getMetadata().put("pf_module", storeModule);
                String chunkKey = value(doc, "chunk_id");
                if (chunkKey.isBlank()) {
                    chunkKey = doc.getId();
                }
                merged.putIfAbsent(storeModule + "|" + chunkKey, doc);
            }
        }
        List<Document> docs = new ArrayList<>(bookFilter.filter(List.copyOf(merged.values())));
        docs.sort(comparatorOf(query));
        int offset = Math.max(0, query.getOffset() == null ? 0 : query.getOffset());
        int limit = Math.max(1, Math.min(query.getLimit() == null ? enumerationTopK : query.getLimit(), enumerationTopK));
        int totalCount = docs.size();
        List<Document> page = docs.stream().skip(offset).limit(limit).toList();
        return new PagedResult(page, totalCount, offset, limit, capped, enumerationTopK);
    }

    /**
     * 按 chunk_id 点查完整条目（SP8a J1）
     *
     * 对目标模块 store 构造 chunk_id 精确过滤 + 相似度阈值全放行 + topK 1，
     * 走现有 FilterExpressionBuilder 通路，不新增 store 访问机制。
     *
     * @param module  数据模块（不支持 all）
     * @param chunkId 检索结果 metadata 中的 chunk_id
     * @return 命中的 Document；未命中返回 null
     */
    public Document getByChunkId(String module, String chunkId) {
        VectorStore store = storesByModule.get(module);
        if (store == null || chunkId == null || chunkId.isBlank()) {
            return null;
        }
        FilterExpressionBuilder builder = new FilterExpressionBuilder();
        SearchRequest request = SearchRequest.builder()
                .query(module)
                .topK(1)
                .similarityThresholdAll()
                .filterExpression(builder.eq("chunk_id", chunkId).build())
                .build();
        List<Document> docs = store.similaritySearch(request);
        return docs.isEmpty() ? null : docs.get(0);
    }

    /** 条件 AND 连接辅助：首个条件直接采用，之后 builder.and 累加 */
    private FilterExpressionBuilder.Op and(FilterExpressionBuilder builder,
            FilterExpressionBuilder.Op op, FilterExpressionBuilder.Op next) {
        return op == null ? next : builder.and(op, next);
    }

    /**
     * 排序比较器：sortBy=title|level|book 字典/数值序，sortOrder=asc|desc；缺省保持默认序。
     *
     * F-026 无条件路径额外保证跨页确定性（只约束无业务条件的查询，不改写既有条件查询）：
     *  - 未显式指定排序：title → module → chunk_id 升序；
     *  - 显式排序：主键按 sortOrder，之后追加 module → chunk_id 升序兜底。
     */
    private Comparator<Document> comparatorOf(MetadataSearchQuery query) {
        boolean unconditional = !query.hasAnyCondition();
        String sortBy = query.getSortBy();
        Comparator<Document> comparator;
        if ("title".equals(sortBy)) {
            comparator = Comparator.comparing(doc -> value(doc, "title"));
        } else if ("level".equals(sortBy)) {
            comparator = Comparator.comparingInt(this::levelOf);
        } else if ("book".equals(sortBy)) {
            comparator = Comparator.comparing(doc -> value(doc, "book_abbreviation"));
        } else if (!unconditional) {
            return (a, b) -> 0;
        } else {
            comparator = Comparator.comparing(doc -> value(doc, "title"));
        }
        if ("desc".equals(query.getSortOrder())) {
            comparator = comparator.reversed();
        }
        return unconditional ? comparator.thenComparing(this::tiebreakComparator) : comparator;
    }

    /** 无条件路径的同值兜底：module → chunk_id 升序（chunk_id 缺失退化为 doc id） */
    private int tiebreakComparator(Document a, Document b) {
        int byModule = value(a, "pf_module").compareTo(value(b, "pf_module"));
        return byModule != 0 ? byModule : chunkKey(a).compareTo(chunkKey(b));
    }

    /** 去重/排序兜底键：chunk_id 缺失退化为 doc id */
    private String chunkKey(Document doc) {
        String chunkId = value(doc, "chunk_id");
        return chunkId.isBlank() ? String.valueOf(doc.getId()) : chunkId;
    }

    /** level 排序取值：第一个 spell_level_* 值的整数，缺失/非数字按 0 */
    private int levelOf(Document doc) {
        for (Map.Entry<String, Object> entry : doc.getMetadata().entrySet()) {
            if (entry.getKey().startsWith("spell_level_")) {
                try {
                    return Integer.parseInt(entry.getValue().toString());
                } catch (NumberFormatException e) {
                    return 0;
                }
            }
        }
        return 0;
    }

    /** metadata 安全取值（缺失返回空串） */
    private String value(Document doc, String key) {
        Object v = doc.getMetadata().get(key);
        return v == null ? "" : v.toString();
    }

    /** store → 模块名反查（跨模块合并去重时标注来源模块） */
    private String moduleOf(VectorStore store) {
        return storesByModule.entrySet().stream()
                .filter(e -> e.getValue() == store)
                .map(Map.Entry::getKey)
                .findFirst()
                .orElse("");
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
