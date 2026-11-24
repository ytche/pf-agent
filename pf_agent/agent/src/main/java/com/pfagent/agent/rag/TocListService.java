package com.pfagent.agent.rag;

import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;
import java.util.regex.Pattern;

/**
 * 四模块（spell/feat/race/equipment）目录查询门面（F-008）
 *
 * 只读适配两套既有清单加载器：feat/race/equipment 走 {@link ListExportService}，
 * spell 走 {@link SpellListService}。启动时把两侧条目合并成统一
 * {@link TocEntry} 索引（含空路径条目，不丢弃），查询时按目录路径**分段前缀**
 * 过滤，支持 all 汇总与分页；空前缀返回根层目录概览，不伪装成条目页。
 *
 * 路径唯一分隔符为 {@value #SEPARATOR}，与 chunk 元数据一致；只做首尾空白与
 * 末尾分隔符清理，不做目录名猜测。spell 条目路径只取条目自身 chunk join 的
 * toc_path（union 折叠条目缺字段时按 chunk_id 回连官方清单条目），列表页
 * source_toc_path 不参与。空路径条目保留在索引与 {@link #pathStats(String)}
 * 统计中，只是无法被非空前缀命中。
 *
 * 唯一身份仍为 (module, chunk_id)：spell 同一法术可能出现在多个职业清单，
 * TocEntry 不含职业字段，故按 chunk_id 去重（无 chunk_id 的条目全部保留）。
 * 单模块清单缺失/解析失败时该模块降级为空索引，不影响其他模块与应用启动。
 */
@Component
public class TocListService {

    private static final Logger log = LoggerFactory.getLogger(TocListService.class);

    /** 目录路径唯一分隔符（与 chunks 的 chm_toc_path 一致） */
    public static final String SEPARATOR = " → ";
    public static final int DEFAULT_LIMIT = 50;
    /** 四模块固定顺序（all 汇总与排序口径） */
    public static final List<String> MODULES = List.of("spell", "feat", "race", "equipment");

    private static final String ALL = "all";

    private static final Comparator<TocEntry> ENTRY_ORDER =
            Comparator.comparingInt((TocEntry e) -> moduleRank(e.module()))
                    .thenComparing(TocEntry::tocPath)
                    .thenComparing(TocEntry::name)
                    .thenComparing(e -> e.chunkId() == null ? "" : e.chunkId());

    @Autowired(required = false)
    private ListExportService listExportService;

    @Autowired(required = false)
    private SpellListService spellListService;

    /** 模块 → 统一条目（rebuildIndex 后不可变；未加载/构建失败模块为空表） */
    private Map<String, List<TocEntry>> entriesByModule = Map.of();
    /** 模块 → 统计（raw 口径来自底层清单，unique 口径来自门面索引） */
    private Map<String, TocPathStats> statsByModule = Map.of();

    @PostConstruct
    void init() {
        rebuildIndex();
    }

    /**
     * 从两套既有服务内存数据重建索引（不触发任何加载/IO）。
     * 逐模块独立 try/catch：任一模块畸形/抛错只 WARN 并降级为空目录，
     * 不影响其他模块与应用启动。
     */
    void rebuildIndex() {
        Map<String, List<TocEntry>> built = new LinkedHashMap<>();
        Map<String, TocPathStats> stats = new LinkedHashMap<>();
        for (String module : List.of("feat", "race", "equipment")) {
            ModuleIndex index = safelyBuild(module, () -> indexListEntries(module));
            built.put(module, index.entries());
            stats.put(module, index.stats());
        }
        ModuleIndex spell = safelyBuild("spell", this::indexSpellEntries);
        built.put("spell", spell.entries());
        stats.put("spell", spell.stats());
        entriesByModule = Map.copyOf(built);
        statsByModule = Map.copyOf(stats);
        log.info("F-008 目录索引构建完成：feat={} race={} equipment={} spell={}",
                built.get("feat").size(), built.get("race").size(),
                built.get("equipment").size(), built.get("spell").size());
    }

    private ModuleIndex safelyBuild(String module, Supplier<ModuleIndex> builder) {
        try {
            return builder.get();
        } catch (RuntimeException e) {
            log.warn("F-008 目录索引构建失败（module={}），该模块降级为空目录，不影响其他模块。",
                    module, e);
            return ModuleIndex.EMPTY;
        }
    }

    /** 当前已加载且可用的模块（MODULES 顺序；未知模块提示用） */
    public List<String> knownModules() {
        return MODULES.stream().filter(this::isModuleLoaded).toList();
    }

    private boolean isModuleLoaded(String module) {
        return switch (module) {
            case "spell" -> spellListService != null && spellListService.isAvailable();
            case "feat", "race", "equipment" ->
                    listExportService != null && listExportService.isAvailable(module);
            default -> false;
        };
    }

    /**
     * 统一目录查询入口：
     *  - module：spell/feat/race/equipment/all（null/空白按 all；未知模块返回空结果，
     *    可先用 {@link #knownModules()} 给出可用模块提示）
     *  - tocPrefix：空前缀（清理后）→ {@link TocOverview} 根层目录概览；
     *    非空 → {@link TocPage} 条目页
     *  - limit 默认 50，非正数钳为 1（防翻页零步进）；offset 默认 0；
     *    offset 越界返回空 items 但保留真实 total
     */
    public TocResult listByToc(String module, String tocPrefix, Integer limit, Integer offset) {
        List<String> modules = resolveModules(module);
        String prefix = cleanPath(tocPrefix);
        if (prefix.isEmpty()) {
            return overview(modules);
        }
        int safeLimit = limit == null ? DEFAULT_LIMIT : Math.max(limit, 1);
        int safeOffset = offset == null ? 0 : Math.max(offset, 0);
        List<TocEntry> matched = select(modules).stream()
                .filter(entry -> matches(entry.tocPath(), prefix))
                .sorted(ENTRY_ORDER)
                .toList();
        int total = matched.size();
        int from = Math.min(safeOffset, total);
        int to = Math.min(from + safeLimit, total);
        return new TocPage(matched.subList(from, to), total, safeOffset, safeLimit);
    }

    /**
     * 分段前缀匹配：prefix 的每个段必须与 path 对应段相等（不做子串匹配）。
     * 契约：空/空白 path 永不匹配（包括空前缀）；空前缀对任意非空 path 恒真，
     * 仅作为匹配原语保留——{@link #listByToc} 对空前缀走目录概览，不调用本方法。
     */
    public static boolean matches(String tocPath, String tocPrefix) {
        String path = cleanPath(tocPath);
        String prefix = cleanPath(tocPrefix);
        if (path.isEmpty()) {
            return false;
        }
        if (prefix.isEmpty()) {
            return true;
        }
        String[] pathSegments = path.split(Pattern.quote(SEPARATOR), -1);
        String[] prefixSegments = prefix.split(Pattern.quote(SEPARATOR), -1);
        if (prefixSegments.length > pathSegments.length) {
            return false;
        }
        for (int i = 0; i < prefixSegments.length; i++) {
            String expected = prefixSegments[i].trim();
            if (expected.isEmpty() || !expected.equals(pathSegments[i].trim())) {
                return false;
            }
        }
        return true;
    }

    /** 未命中时可用的上级目录（由近及远；不含空前缀，空路径/单段前缀返回空表） */
    public List<String> ancestorPrefixes(String module, String tocPrefix) {
        String prefix = cleanPath(tocPrefix);
        if (prefix.isEmpty()) {
            return List.of();
        }
        String[] segments = prefix.split(Pattern.quote(SEPARATOR), -1);
        if (segments.length <= 1) {
            return List.of();
        }
        List<TocEntry> entries = select(resolveModules(module));
        List<String> ancestors = new ArrayList<>();
        for (int end = segments.length - 1; end >= 1; end--) {
            String candidate = joinSegments(segments, end);
            if (entries.stream().anyMatch(entry -> matches(entry.tocPath(), candidate))) {
                ancestors.add(candidate);
            }
        }
        return ancestors;
    }

    /**
     * 模块目录路径统计。
     *
     * 口径：rawTotal/nonEmptyPath/emptyPath 按底层清单**原始条目**统计（spell 含
     * 同一 chunk 跨职业的重复行），三者满足 rawTotal = nonEmptyPath + emptyPath；
     * uniqueTotal 为门面索引去重后的条目数。spell 同 chunk 去重时优先保留非空
     * tocPath，因此 emptyPath 可能大于“门面里可见的空路径条目”，这是原始数据
     * 的真实空值数，不会因去重被低估。
     */
    public TocPathStats pathStats(String module) {
        int rawTotal = 0;
        int uniqueTotal = 0;
        int nonEmpty = 0;
        int empty = 0;
        for (String key : resolveModules(module)) {
            TocPathStats stats = statsByModule.getOrDefault(key, TocPathStats.EMPTY);
            rawTotal += stats.rawTotal();
            uniqueTotal += stats.uniqueTotal();
            nonEmpty += stats.nonEmptyPath();
            empty += stats.emptyPath();
        }
        return new TocPathStats(rawTotal, uniqueTotal, nonEmpty, empty);
    }

    // ---------- 索引构建 ----------

    private ModuleIndex indexListEntries(String module) {
        if (listExportService == null || !listExportService.isAvailable(module)) {
            return ModuleIndex.EMPTY;
        }
        List<TocEntry> entries = new ArrayList<>();
        int rawTotal = 0;
        int nonEmpty = 0;
        for (ListExportService.ListEntry entry : listExportService.entries(module)) {
            if (entry == null) {
                continue;
            }
            rawTotal++;
            String tocPath = cleanPath(entry.tocPath());
            if (!tocPath.isEmpty()) {
                nonEmpty++;
            }
            entries.add(new TocEntry(module, entry.name(), entry.book(), entry.componentType(),
                    entry.chunkId(), tocPath));
        }
        return moduleIndex(entries, rawTotal, nonEmpty);
    }

    /**
     * spell 条目：同 chunk_id 跨职业去重（TocEntry 无职业字段），去重时优先保留
     * 非空 tocPath；无 chunk_id 的条目用 module+name+level 稳定键去重，避免跨职业
     * 重复行膨胀门面条目；两者无可用路径时同样保留在索引与 raw 统计中。
     */
    private ModuleIndex indexSpellEntries() {
        if (spellListService == null || !spellListService.isAvailable()) {
            return ModuleIndex.EMPTY;
        }
        Map<String, TocEntry> byChunkId = new LinkedHashMap<>();
        Map<String, TocEntry> unidentified = new LinkedHashMap<>();
        int rawTotal = 0;
        int nonEmpty = 0;
        for (SpellListService.SpellTocRow row : spellListService.tocRows()) {
            if (row == null) {
                continue;
            }
            rawTotal++;
            String tocPath = cleanPath(row.tocPath());
            if (!tocPath.isEmpty()) {
                nonEmpty++;
            }
            TocEntry entry = new TocEntry("spell", row.name(), row.book(), "spell",
                    row.chunkId(), tocPath);
            if (row.chunkId() == null || row.chunkId().isBlank()) {
                unidentified.putIfAbsent(stableKey(entry, row.level()), entry);
            } else {
                byChunkId.merge(row.chunkId(), entry, TocListService::preferNonEmptyPath);
            }
        }
        List<TocEntry> entries = new ArrayList<>(byChunkId.values());
        entries.addAll(unidentified.values());
        return moduleIndex(entries, rawTotal, nonEmpty);
    }

    private static TocEntry preferNonEmptyPath(TocEntry existing, TocEntry candidate) {
        return existing.tocPath().isEmpty() && !candidate.tocPath().isEmpty() ? candidate : existing;
    }

    /** 无 chunk_id 条目的稳定键：module + name + level（TocEntry 无 level，由原始行提供） */
    private static String stableKey(TocEntry entry, int level) {
        return entry.module() + '\u0000' + entry.name() + '\u0000' + level;
    }

    private static ModuleIndex moduleIndex(List<TocEntry> entries, int rawTotal, int nonEmpty) {
        return new ModuleIndex(List.copyOf(entries),
                new TocPathStats(rawTotal, entries.size(), nonEmpty, rawTotal - nonEmpty));
    }

    /** 单模块索引构建结果（含 unique/raw 两种口径统计） */
    private record ModuleIndex(List<TocEntry> entries, TocPathStats stats) {
        static final ModuleIndex EMPTY = new ModuleIndex(List.of(), TocPathStats.EMPTY);
    }

    private TocOverview overview(List<String> modules) {
        Map<String, Map<String, Integer>> countsByModule = new LinkedHashMap<>();
        for (String module : modules) {
            for (TocEntry entry : entriesByModule.getOrDefault(module, List.of())) {
                String root = rootSegment(entry.tocPath());
                if (root.isEmpty()) {
                    continue;
                }
                countsByModule.computeIfAbsent(module, key -> new LinkedHashMap<>())
                        .merge(root, 1, Integer::sum);
            }
        }
        List<TocNode> nodes = new ArrayList<>();
        int total = 0;
        for (Map.Entry<String, Map<String, Integer>> moduleCounts : countsByModule.entrySet()) {
            for (Map.Entry<String, Integer> node : moduleCounts.getValue().entrySet()) {
                nodes.add(new TocNode(moduleCounts.getKey(), node.getKey(), node.getValue()));
                total += node.getValue();
            }
        }
        nodes.sort(Comparator.comparingInt((TocNode n) -> moduleRank(n.module()))
                .thenComparing(Comparator.comparingInt(TocNode::count).reversed())
                .thenComparing(TocNode::segment));
        return new TocOverview(nodes, total);
    }

    // ---------- 公共工具 ----------

    private List<String> resolveModules(String module) {
        String key = module == null ? "" : module.trim();
        if (key.isEmpty() || ALL.equals(key)) {
            return MODULES;
        }
        return MODULES.contains(key) ? List.of(key) : List.of();
    }

    private List<TocEntry> select(List<String> modules) {
        List<TocEntry> entries = new ArrayList<>();
        for (String module : modules) {
            entries.addAll(entriesByModule.getOrDefault(module, List.of()));
        }
        return entries;
    }

    /** 只做首尾空白与末尾分隔符清理（末尾裸箭头及两侧空白） */
    private static String cleanPath(String path) {
        if (path == null) {
            return "";
        }
        String cleaned = path.trim();
        while (cleaned.endsWith("→")) {
            cleaned = cleaned.substring(0, cleaned.length() - 1).trim();
        }
        return cleaned;
    }

    private static String rootSegment(String tocPath) {
        if (tocPath == null || tocPath.isEmpty()) {
            return "";
        }
        int index = tocPath.indexOf(SEPARATOR);
        String root = index < 0 ? tocPath : tocPath.substring(0, index);
        return root.trim();
    }

    private static String joinSegments(String[] segments, int end) {
        return Arrays.stream(segments, 0, end)
                .map(String::trim)
                .reduce((a, b) -> a + SEPARATOR + b)
                .orElse("");
    }

    private static int moduleRank(String module) {
        int rank = MODULES.indexOf(module);
        return rank < 0 ? MODULES.size() : rank;
    }

    // ---------- 查询契约 ----------

    /** 统一查询结果：条目页或根层目录概览（调用方按类型分支，避免把概览伪装成条目页） */
    public interface TocResult {
    }

    /** 条目页：items 为本页条目，total 为命中总数（精确值）；capped 恒 false */
    public record TocPage(List<TocEntry> items, int total, int offset, int limit)
            implements TocResult {

        public TocPage {
            items = items == null ? List.of() : List.copyOf(items);
            total = Math.max(total, 0);
            offset = Math.max(offset, 0);
            limit = Math.max(limit, 0);
        }

        public boolean hasMore() {
            return offset + items.size() < total;
        }

        public boolean capped() {
            return false;
        }
    }

    /** 根层目录概览：一级节点 + 各节点条目数；total 为概览覆盖条目数之和 */
    public record TocOverview(List<TocNode> nodes, int total) implements TocResult {

        public TocOverview {
            nodes = nodes == null ? List.of() : List.copyOf(nodes);
        }
    }

    /** 根层目录节点：module + 一级目录名 + 其下条目数 */
    public record TocNode(String module, String segment, int count) {
    }

    /**
     * 目录路径统计（口径见 {@link TocListService#pathStats(String)}）：
     * rawTotal/nonEmptyPath/emptyPath 按底层原始条目（spell 含跨职业重复行），
     * uniqueTotal 按门面去重后条目；rawTotal = nonEmptyPath + emptyPath。
     */
    public record TocPathStats(int rawTotal, int uniqueTotal, int nonEmptyPath, int emptyPath) {
        public static final TocPathStats EMPTY = new TocPathStats(0, 0, 0, 0);
    }

    /** 统一清单条目：字段名固定（F-008 后续工具集成不得改名） */
    public record TocEntry(String module, String name, String book,
                           String componentType, String chunkId, String tocPath) {

        public TocEntry {
            module = module == null ? "" : module;
            name = name == null ? "" : name;
            tocPath = tocPath == null ? "" : tocPath;
        }
    }
}
