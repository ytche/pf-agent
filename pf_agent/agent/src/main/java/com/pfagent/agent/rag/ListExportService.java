package com.pfagent.agent.rag;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.document.Document;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Stream;

/**
 * 专长/种族/装备权威清单直查服务（B4，D2）
 *
 * 一个服务承载 feat/race/equipment 三模块：三 JSON 同构（公共 9 字段 + 模块特有可空字段），
 * 一个加载器循环三个配置路径逐模块独立容错——某文件缺失/解析失败只置该模块
 * available=false，不影响其余两模块，不炸启动（对齐 SpellListService/ClassTableService）。
 *
 * 无条件查询返回统计概览（stats + entries 内存聚合，零 IO）防刷屏；
 * 有条件查询内存 Stream 过滤（三清单合计 6866 条，成本可忽略）+ keyword 子串
 * （NFKC 全半角归一，复用 EntryResolver.normalize）。
 *
 * 溯源（复用 J5 通路）：返回条目的 chunk_id 走 SearchService.getByChunkId 批量点查
 * 真实 chunk 交 SourceCollector；点查未命中（向量库版本错位）降级合成 Document
 * 并 warn（数据一致性技术债务候选），保证 [#N] 不缺席。
 *
 * 不提供运行时刷新：重启加载生效；source_fingerprint 仅启动日志留痕。
 */
@Component
public class ListExportService {

    private static final Logger log = LoggerFactory.getLogger(ListExportService.class);

    static final List<String> MODULES = List.of("feat", "race", "equipment");
    static final Map<String, String> MODULE_LABELS = Map.of(
            "feat", "专长", "race", "种族", "equipment", "装备");

    static final List<String> FEAT_FILTER_FIELDS = List.of("featType", "book", "hasPrerequisites");
    static final List<String> RACE_FILTER_FIELDS = List.of("raceGroup", "size", "bioType", "book");
    static final List<String> EQUIPMENT_FILTER_FIELDS = List.of(
            "componentType", "slot", "book", "price_min", "price_max");

    /** 概览按书统计的最大展示条数（装备 by_book 50+，防刷屏） */
    private static final int OVERVIEW_BOOK_CAP = 20;

    @Value("${pf.list-exports.feat-file-path:../../pf_data/phase1/vectorizer/output/专长/feat_lists.json}")
    private String featFilePath;
    @Value("${pf.list-exports.race-file-path:../../pf_data/phase1/vectorizer/output/种族/race_lists.json}")
    private String raceFilePath;
    @Value("${pf.list-exports.equipment-file-path:../../pf_data/phase1/vectorizer/output/装备/equipment_lists.json}")
    private String equipmentFilePath;

    @Autowired
    private SearchService searchService;

    private final ObjectMapper objectMapper = new ObjectMapper();

    /** 模块名 → 清单条目（@PostConstruct 加载，加载前/失败为空列表） */
    private final Map<String, List<ListEntry>> entriesByModule = new LinkedHashMap<>();
    /** 模块名 → source_fingerprint（启动对账留痕，未加载为 null） */
    private final Map<String, String> fingerprintByModule = new LinkedHashMap<>();

    /** 该模块清单是否加载成功（文件存在且解析通过） */
    public boolean isAvailable(String module) {
        return entriesByModule.containsKey(module);
    }

    /** 全部已加载模块名（有序：feat/race/equipment 中已加载者） */
    public List<String> knownModules() {
        return MODULES.stream().filter(entriesByModule::containsKey).toList();
    }

    /** 该模块可枚举的全部条目数（未加载返回 0） */
    public int total(String module) {
        return entriesByModule.getOrDefault(module, List.of()).size();
    }

    /** 该模块可用 filters/orFilters 字段清单（未知模块返回空表） */
    public List<String> availableFilterFields(String module) {
        return switch (module == null ? "" : module) {
            case "feat" -> FEAT_FILTER_FIELDS;
            case "race" -> RACE_FILTER_FIELDS;
            case "equipment" -> EQUIPMENT_FILTER_FIELDS;
            default -> List.of();
        };
    }

    /** query 中不属于该模块可用字段的字段名（保序去重；未知模块时全部返回） */
    public Set<String> unknownFilterFields(String module, ListEntriesQuery query) {
        List<String> available = availableFilterFields(module);
        Set<String> unknown = new LinkedHashSet<>();
        if (query.filters() != null) {
            query.filters().keySet().stream().filter(f -> !available.contains(f)).forEach(unknown::add);
        }
        if (query.orFilters() != null) {
            query.orFilters().keySet().stream().filter(f -> !available.contains(f)).forEach(unknown::add);
        }
        return unknown;
    }

    /**
     * 无条件查询的统计概览：total + 模块特有维度统计 + by_book 统计（前 20 本书），
     * 末尾引导提供 keyword 或过滤条件收窄。数据来自启动已加载的内存清单，零 IO。
     */
    public String overview(String module) {
        List<ListEntry> entries = entriesByModule.getOrDefault(module, List.of());
        String label = MODULE_LABELS.getOrDefault(module, module);
        StringBuilder sb = new StringBuilder();
        sb.append('「').append(label).append("」权威清单共 ").append(entries.size()).append(" 条");
        Map<String, Long> dimension = dimensionStats(module, entries);
        if (!dimension.isEmpty()) {
            sb.append('，').append(dimensionLabel(module)).append('：').append(joinStats(dimension));
        }
        Map<String, Long> byBook = countBy(entries, ListEntry::book);
        if (!byBook.isEmpty()) {
            sb.append("；按书：").append(joinStats(cap(byBook, OVERVIEW_BOOK_CAP)));
        }
        sb.append("。请提供 keyword 或过滤条件查看具体清单（可用字段: ")
                .append(availableFilterFields(module)).append("）");
        return sb.toString();
    }

    /** 该模块清单是否有可用的 price_gp 数值（旧版清单全部为 null → 不支持 price 排序） */
    public boolean hasPriceData(String module) {
        return entriesByModule.getOrDefault(module, List.of()).stream()
                .anyMatch(entry -> entry.priceGp() != null);
    }

    /**
     * 有条件查询：keyword 子串（NFKC 全半角归一）+ filters AND 精确 + orFilters 组内 OR，
     * 默认按 name（unicode 序），sortBy=book 时按书再按名；sortBy=price 时按 price_gp
     * （asc 默认 / desc，price_gp=null 的条目恒排最后且不参与极值结论）；再按 offset/limit 分页。
     * 返回命中总数 total 与本页条目（EntryPage）。
     */
    public EntryPage search(String module, ListEntriesQuery query, int limit, int offset) {
        List<ListEntry> all = entriesByModule.getOrDefault(module, List.of());
        Stream<ListEntry> stream = all.stream();
        if (query.keyword() != null && !query.keyword().isBlank()) {
            String term = EntryResolver.normalize(query.keyword());
            stream = stream.filter(e -> keywordMatches(e, term));
        }
        if (query.filters() != null) {
            for (Map.Entry<String, String> condition : query.filters().entrySet()) {
                stream = stream.filter(e -> fieldMatches(e, condition.getKey(), condition.getValue()));
            }
        }
        if (query.orFilters() != null) {
            for (Map.Entry<String, List<String>> group : query.orFilters().entrySet()) {
                List<String> values = group.getValue();
                if (values != null && !values.isEmpty()) {
                    stream = stream.filter(e -> values.stream()
                            .anyMatch(v -> fieldMatches(e, group.getKey(), v)));
                }
            }
        }
        Comparator<ListEntry> comparator = switch (query.sortBy() == null ? "" : query.sortBy()) {
            case "book" -> Comparator.comparing(ListExportService::bookLabel).thenComparing(ListEntry::name);
            case "price" -> priceComparator(query.sortOrder());
            default -> Comparator.comparing(ListEntry::name);
        };
        List<ListEntry> filtered = stream.sorted(comparator).toList();
        int from = Math.min(Math.max(offset, 0), filtered.size());
        int to = Math.min(from + Math.max(limit, 0), filtered.size());
        return new EntryPage(filtered.subList(from, to), filtered.size());
    }

    /**
     * price_gp 排序：null 恒排最后（升/降序都是），同价按 name 稳定排序。
     * 降序只反转有价条目的数值顺序，不影响 null 的位置。
     */
    private static Comparator<ListEntry> priceComparator(String sortOrder) {
        boolean desc = "desc".equalsIgnoreCase(sortOrder);
        Comparator<Integer> valueOrder = desc ? Comparator.reverseOrder() : Comparator.naturalOrder();
        return Comparator
                .comparing((ListEntry entry) -> entry.priceGp() == null)
                .thenComparing(entry -> entry.priceGp() == null ? 0 : entry.priceGp(), valueOrder)
                .thenComparing(ListEntry::name);
    }

    /**
     * 单条目紧凑行（喂给 LLM）：`序号. 中文名（English）[书] | 属性段 | chunk_id: xxx`。
     * 属性段按模块：feat→类别/前置（无前置省略）；race→分组/体型/速度（ability_adj/senses
     * 仅 detailed=命中 ≤20 条时附，防长行刷屏）；equipment→类型/价格/重量。
     * book 为 "?"/空白时如实展示「未知来源」（race by_book 全 "?" 先例，不编造来源）。
     * 行尾来源编号 [#N] 由工具层追加（截断行不标注）。
     */
    public String entryLine(String module, int index, ListEntry entry, boolean detailed) {
        StringBuilder sb = new StringBuilder(index + ". ").append(entry.name());
        if (entry.nameEn() != null && !entry.nameEn().isBlank()) {
            sb.append('（').append(entry.nameEn()).append('）');
        }
        sb.append("[").append(bookLabel(entry)).append(']');
        switch (module == null ? "" : module) {
            case "feat" -> {
                if (!entry.featType().isEmpty()) {
                    sb.append(" | 类别:").append(String.join("/", entry.featType()));
                }
                if (entry.prerequisitesRaw() != null && !entry.prerequisitesRaw().isBlank()) {
                    sb.append(" | 前置:").append(entry.prerequisitesRaw());
                }
            }
            case "race" -> {
                sb.append(" | 分组:").append(nullToDash(entry.raceGroup()));
                sb.append(" | 体型:").append(nullToDash(entry.size()));
                sb.append(" | 速度:").append(nullToDash(entry.speed()));
                if (detailed) {
                    if (entry.abilityAdj() != null && !entry.abilityAdj().isBlank()) {
                        sb.append(" | 属性调整:").append(entry.abilityAdj());
                    }
                    if (entry.senses() != null && !entry.senses().isBlank()) {
                        sb.append(" | 感官:").append(entry.senses());
                    }
                }
            }
            case "equipment" -> {
                sb.append(" | 类型:").append(nullToDash(entry.componentType()));
                sb.append(" | 价格:").append(nullToDash(entry.price()));
                sb.append(" | 重量:").append(nullToDash(entry.weight()));
            }
            default -> {
            }
        }
        if (entry.chunkId() != null) {
            sb.append(" | chunk_id: ").append(entry.chunkId());
        }
        return sb.toString();
    }

    /**
     * 溯源 Document 批量点查（复用 J5 通路）：逐条用 (module, chunk_id) 走
     * SearchService.getByChunkId 点查真实 chunk；未命中或 chunk_id 为 null（向量库
     * 版本错位）降级合成 Document（title=name，metadata 带 chunk_id/doc_id）并 warn，
     * 保证 [#N] 不缺席。返回与入参条目一一对齐（同序同长）。
     */
    public List<Document> provenanceDocuments(String module, List<ListEntry> entries) {
        List<Document> docs = new ArrayList<>(entries.size());
        for (ListEntry entry : entries) {
            if (searchService != null && entry.chunkId() != null) {
                Document doc = searchService.getByChunkId(module, entry.chunkId());
                if (doc != null) {
                    docs.add(doc);
                    continue;
                }
                log.warn("清单条目 chunk_id 点查未命中（module={}，name={}，chunk_id={}），"
                        + "疑似清单 JSON 与向量库版本错位，降级合成溯源 Document。",
                        module, entry.name(), entry.chunkId());
            } else if (entry.chunkId() != null) {
                log.warn("清单条目 chunk_id 点查未命中（module={}，name={}，chunk_id={}，"
                        + "SearchService 未注入），降级合成溯源 Document。", module, entry.name(), entry.chunkId());
            }
            docs.add(syntheticDocument(module, entry));
        }
        return docs;
    }

    /** 点查未命中时的降级合成 Document（title=name，metadata 带 chunk_id/doc_id） */
    private Document syntheticDocument(String module, ListEntry entry) {
        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("title", entry.name());
        meta.put("book_name_cn", entry.bookNameCn() == null || entry.bookNameCn().isBlank()
                ? "未知来源" : entry.bookNameCn());
        if (entry.chunkId() != null) {
            meta.put("chunk_id", entry.chunkId());
        }
        if (entry.docId() != null) {
            meta.put("doc_id", entry.docId());
        }
        return Document.builder()
                .text('「' + entry.name() + '」' + MODULE_LABELS.getOrDefault(module, module)
                        + "清单条目（数据侧清单 JSON 预整理；向量库未检索到对应原文 chunk，"
                        + "可用 vectorSearch 检索该条目原文）")
                .metadata(meta)
                .build();
    }

    /** 加载三个清单 JSON 进内存；逐模块独立容错（缺失/解析失败仅该模块不可用） */
    @PostConstruct
    void load() {
        loadModule("feat", featFilePath);
        loadModule("race", raceFilePath);
        loadModule("equipment", equipmentFilePath);
    }

    /** 单模块加载：文件缺失 warn / 解析失败 error，均不炸启动；成功登记条目与 fingerprint */
    private void loadModule(String module, String filePath) {
        Path path = Path.of(filePath);
        if (!Files.exists(path)) {
            log.warn("{}_lists.json 不存在（{}），{}清单枚举将降级不可用。",
                    module, path.toAbsolutePath(), MODULE_LABELS.get(module));
            return;
        }
        try {
            ListExportFile file = objectMapper.readValue(path.toFile(), ListExportFile.class);
            List<ListEntry> entries = file.entries() == null ? List.of() : file.entries();
            entriesByModule.put(module, entries);
            if (file.sourceFingerprint() != null) {
                fingerprintByModule.put(module, file.sourceFingerprint());
            }
            log.info("{}_lists.json 加载完成：{} 解析 {} 条（stats.total={}），source_fingerprint={}（{}）",
                    module, MODULE_LABELS.get(module), entries.size(),
                    file.stats() == null || file.stats().total() == null ? "?" : file.stats().total(),
                    file.sourceFingerprint(), path.getFileName());
        } catch (IOException e) {
            log.error("{}_lists.json 解析失败（{}），{}清单枚举将降级不可用。",
                    module, path.toAbsolutePath(), MODULE_LABELS.get(module), e);
        }
    }

    /** keyword 子串匹配：name/name_en/aliases 任一归一后包含检索词（检索词已归一） */
    private static boolean keywordMatches(ListEntry entry, String normalizedTerm) {
        return containsNormalized(entry.name(), normalizedTerm)
                || containsNormalized(entry.nameEn(), normalizedTerm)
                || entry.aliases().stream().anyMatch(alias -> containsNormalized(alias, normalizedTerm));
    }

    private static boolean containsNormalized(String value, String normalizedTerm) {
        return value != null && !value.isBlank()
                && EntryResolver.normalize(value).contains(normalizedTerm);
    }

    /** 单字段精确匹配：featType 对列表任一命中；hasPrerequisites 按 prerequisites_raw 非空；其余直比对 */
    private static boolean fieldMatches(ListEntry entry, String field, String value) {
        if (value == null) {
            return false;
        }
        return switch (field) {
            case "featType" -> entry.featType().contains(value);
            case "hasPrerequisites" -> "true".equalsIgnoreCase(value)
                    ? entry.prerequisitesRaw() != null && !entry.prerequisitesRaw().isBlank()
                    : !"true".equalsIgnoreCase(value) && (entry.prerequisitesRaw() == null
                            || entry.prerequisitesRaw().isBlank());
            case "book" -> value.equals(entry.book());
            case "raceGroup" -> value.equals(entry.raceGroup());
            case "size" -> value.equals(entry.size());
            case "bioType" -> value.equals(entry.bioType());
            case "componentType" -> value.equals(entry.componentType());
            case "slot" -> value.equals(entry.slot());
            // AKN-025：价格区间只比较有 price_gp 的条目，null（无标价）不命中
            case "price_min" -> priceGpMatches(entry, value, true);
            case "price_max" -> priceGpMatches(entry, value, false);
            default -> false;
        };
    }

    /** price_min/price_max：value 解析失败按不命中（工具层已先行校验并给出提示） */
    private static boolean priceGpMatches(ListEntry entry, String value, boolean lowerBound) {
        if (entry.priceGp() == null) {
            return false;
        }
        try {
            long threshold = Long.parseLong(value.trim());
            return lowerBound ? entry.priceGp() >= threshold : entry.priceGp() <= threshold;
        } catch (NumberFormatException e) {
            return false;
        }
    }

    /** 模块概览的特有统计维度：feat→feat_type 计数；race→race_group 计数；equipment→component_type 计数 */
    private static Map<String, Long> dimensionStats(String module, List<ListEntry> entries) {
        return switch (module == null ? "" : module) {
            case "feat" -> countBy(
                    entries.stream().flatMap(e -> e.featType().stream()).toList(), t -> t);
            case "race" -> countBy(entries, ListEntry::raceGroup);
            case "equipment" -> countBy(entries, ListEntry::componentType);
            default -> Map.of();
        };
    }

    private static String dimensionLabel(String module) {
        return switch (module == null ? "" : module) {
            case "feat" -> "按专长类别";
            case "race" -> "按种族分组";
            case "equipment" -> "按类型";
            default -> "按类型";
        };
    }

    private static <T> Map<String, Long> countBy(List<T> items, java.util.function.Function<T, String> keyOf) {
        Map<String, Long> counts = new LinkedHashMap<>();
        for (T item : items) {
            String key = keyOf.apply(item);
            if (key == null || key.isBlank() || "?".equals(key)) {
                key = "未知来源";
            }
            counts.merge(key, 1L, Long::sum);
        }
        return counts;
    }

    /** 统计段拼接："战斗 10、团队 5"；多书时按计数降序截断到 cap 并附计数提示 */
    private static String joinStats(Map<String, Long> stats) {
        return stats.entrySet().stream()
                .sorted(Map.Entry.<String, Long>comparingByValue().reversed())
                .map(e -> e.getKey() + " " + e.getValue())
                .reduce((a, b) -> a + "、" + b)
                .orElse("");
    }

    private static Map<String, Long> cap(Map<String, Long> stats, int max) {
        if (stats.size() <= max) {
            return stats;
        }
        List<Map.Entry<String, Long>> sorted = stats.entrySet().stream()
                .sorted(Map.Entry.<String, Long>comparingByValue().reversed())
                .toList();
        Map<String, Long> capped = new LinkedHashMap<>();
        long rest = 0;
        for (int i = 0; i < sorted.size(); i++) {
            if (i < max) {
                capped.put(sorted.get(i).getKey(), sorted.get(i).getValue());
            } else {
                rest += sorted.get(i).getValue();
            }
        }
        capped.put("（其余 " + (sorted.size() - max) + " 种书共 " + rest + " 条）", rest);
        return capped;
    }

    /** 书标签："?"/空白 → 未知来源（race 全量 "?" 先例，如实展示不编造） */
    private static String bookLabel(ListEntry entry) {
        return entry.book() == null || entry.book().isBlank() || "?".equals(entry.book())
                ? "未知来源" : entry.book();
    }

    private static String nullToDash(String value) {
        return value == null || value.isBlank() ? "—" : value;
    }

    /** 分页查询结果：本页条目 + 命中总数（截断提示/翻页引导用） */
    public record EntryPage(List<ListEntry> entries, int total) {
    }

    // ---------- *_lists.json 数据模型（组件 camelCase，snake_case JSON 键用 @JsonProperty 映射） ----------

    /** 顶层文件：entries + stats + source_fingerprint；version/generated_from/sections 等忽略 */
    @JsonIgnoreProperties(ignoreUnknown = true)
    record ListExportFile(
            @JsonProperty("source_fingerprint") String sourceFingerprint,
            List<ListEntry> entries,
            Stats stats) {
    }

    /** 数据侧对账统计（total 仅日志对账用；概览展示走内存聚合） */
    @JsonIgnoreProperties(ignoreUnknown = true)
    record Stats(Integer total) {
    }

    /** 单清单条目：三模块共用一个 record，模块特有字段全部可空（空字段格式化时省略） */
    @JsonIgnoreProperties(ignoreUnknown = true)
    record ListEntry(
            String name,
            @JsonProperty("name_en") String nameEn,
            String book,
            @JsonProperty("book_name_cn") String bookNameCn,
            @JsonProperty("component_type") String componentType,
            @JsonProperty("chunk_id") String chunkId,
            @JsonProperty("doc_id") String docId,
            List<String> aliases,
            @JsonProperty("feat_type") List<String> featType,
            @JsonProperty("prerequisites_raw") String prerequisitesRaw,
            @JsonProperty("race_group") String raceGroup,
            @JsonProperty("ability_adj") String abilityAdj,
            @JsonProperty("bio_type") String bioType,
            String size,
            String speed,
            String senses,
            String price,
            @JsonProperty("price_gp") Integer priceGp,
            String weight,
            String slot) {

        ListEntry {
            name = name == null ? "" : name;
            aliases = aliases == null ? List.of() : aliases;
            featType = featType == null ? List.of() : featType;
        }
    }
}
