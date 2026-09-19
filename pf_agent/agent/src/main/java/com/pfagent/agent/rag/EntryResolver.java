package com.pfagent.agent.rag;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 跨模块条目名解析器（SP8c J6 Layer 0）
 *
 * 启动时（@PostConstruct）从八个模块的 chunks.jsonl 构建内存索引：
 *  标题 / alias（大小写不敏感、全半角 NFKC 归一、去空白）→ 条目引用（module, chunk_id）。
 * 实测 42,639 条目 / 45,161 归一键（2026-09-18），索引体积 <10MB、构建 <1s。索引源用 chunks.jsonl 而非向量库 JSON：
 *  1. 向量库持久化 JSON 含 embedding（614MB），解析成本高；
 *  2. 引用链需要的结构化关系（prerequisites items、spell_level 列表、base_spell_*）
 *     只在 chunks.jsonl 的原始行模型里（mapper 扁平化后 prerequisites 等不入 Document metadata）。
 *
 * 同时预解析三条已结构化的边（方案 J6 Layer 0，Layer 1 文本引用抽取不在本期）：
 *  - 基础/变体：法术行顶层 base_spell_chunk_id/base_spell_title/base_spell_book（257 条）；
 *  - 它引用的：专长 metadata.prerequisites.items 中可按名精确/别名解析的条目
 *    （自由文本已被数据侧结构化为 items，仅输出能解析的，解析不到不输出）；
 *    法术的 spell_level 职业环级表（class 名解析到职业条目）；
 *  - 引用它的：prerequisites 反向索引 + spell_level 反向索引。
 *
 * 开关 pf.search.entry-resolver-enabled（默认 true）；关闭时不建索引，
 * 工具层返回固定提示。文件缺失/单行损坏均容错（warn + 跳过），不阻断启动。
 *
 * SP8d 扩展：substringSearch 在名归一索引上做双向子串匹配（keywordSearch v1，
 * 探针证实 vectorSearch 精确术语失败率 16.5% 后的低成本兜底，详见方案 J7）。
 */
@Component
public class EntryResolver {

    private static final Logger log = LoggerFactory.getLogger(EntryResolver.class);
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    /** 专长前置里各条目类型的优先解析模块 */
    private static final Map<String, String> ITEM_TYPE_MODULES = Map.of(
            "feat", "feat",
            "skill", "skill",
            "race", "race",
            "spell", "spell",
            "class_level", "class");

    @Value("${pf.chunks.spells-path}")
    private String spellsPath;
    @Value("${pf.chunks.classes-path}")
    private String classesPath;
    @Value("${pf.chunks.feat-path}")
    private String featPath;
    @Value("${pf.chunks.race-path}")
    private String racePath;
    @Value("${pf.chunks.trait-path}")
    private String traitPath;
    @Value("${pf.chunks.equipment-path}")
    private String equipmentPath;
    @Value("${pf.chunks.skill-path}")
    private String skillPath;
    @Value("${pf.chunks.rule-path}")
    private String rulePath;
    /** J6 条目索引开关（默认 true）；关闭时 resolveEntry/getEntryLinks 返回固定提示 */
    @Value("${pf.search.entry-resolver-enabled:true}")
    private boolean enabled;
    /** SP8d：keywordSearch 子串匹配的候选上限（默认 20）；字段初值兜底非 Spring 单测场景 */
    @Value("${pf.search.entry-resolver-max-results:20}")
    private int maxResults = 20;

    /** 归一名 → (chunkKey → 条目引用)：chunkKey 二级去重，同名多chunk=多义候选 */
    private final Map<String, Map<String, EntryRef>> nameIndex = new HashMap<>();
    /** chunkKey（module|chunkId）→ 条目引用 */
    private final Map<String, EntryRef> entriesByChunkKey = new LinkedHashMap<>();
    /** 变体 chunkKey → 基础法术（base_spell_* 解析；基础条目不在索引时用标题/书构造） */
    private final Map<String, EntryLink> baseByVariant = new LinkedHashMap<>();
    /** 基础法术 chunkKey → 变体列表 */
    private final Map<String, List<EntryRef>> variantsByBase = new LinkedHashMap<>();
    /** 条目 chunkKey → 它引用的（prerequisites 解析 + 职业环级表），note 为关系说明 */
    private final Map<String, List<EntryLink>> referencesByEntry = new LinkedHashMap<>();
    /** 目标条目 chunkKey → 引用它的来源列表 */
    private final Map<String, List<EntryLink>> referencedByEntry = new LinkedHashMap<>();

    private volatile boolean built = false;

    /** 条目引用：解析与链接输出的最小元数据 */
    public record EntryRef(String module, String chunkId, String title,
                           String bookNameCn, String bookAbbreviation) {
    }

    /** 条目链接：目标条目 + 关系说明（如 "前置专长"、"法师 1 环"） */
    public record EntryLink(EntryRef target, String note) {
    }

    /** 三层链接结果：基础/变体、引用它的、它引用的；各层为空列表表示无 */
    public record EntryLinks(EntryRef entry, EntryRef base, List<EntryRef> variants,
                             List<EntryLink> referencedBy, List<EntryLink> references) {
    }

    /** jsonl 行的轻量中间模型：只留索引用字段，避免持有 42K 行完整 text */
    private record Row(String module, String chunkId, String title, String bookNameCn,
                       String bookAbbreviation, List<String> names,
                       String baseChunkId, String baseTitle, String baseBook,
                       List<Map<String, Object>> prereqItems,
                       List<String[]> spellLevels) {
    }

    /** 子串候选的中间排序模型：命中级别 + 归一 title 长度（短者优先的稳定排序键） */
    private record Scored(EntryRef ref, int score, int titleLength) {
    }

    /** 开关状态：false 时工具层不应调用索引方法（防御返回空） */
    public boolean isEnabled() {
        return enabled;
    }

    /**
     * 按名解析条目（大小写不敏感、全半角归一）：命中返回全部候选（按 chunk 去重），
     * 未命中返回空列表。
     */
    public List<EntryRef> resolve(String name) {
        return resolve(name, null);
    }

    /**
     * 按名解析条目（可指定模块消歧/收窄）。
     *
     * @param name   条目名或别名
     * @param module 目标模块（可空 = 全模块）；非空时只返回该模块候选
     */
    public List<EntryRef> resolve(String name, String module) {
        if (!enabled || name == null) {
            return List.of();
        }
        Map<String, EntryRef> byChunk = nameIndex.get(normalize(name));
        if (byChunk == null) {
            return List.of();
        }
        List<EntryRef> refs = new ArrayList<>(byChunk.values());
        if (module != null && !module.isBlank()) {
            refs.removeIf(ref -> !module.equals(ref.module()));
        }
        return refs;
    }

    /**
     * 双向子串匹配（全模块）：同 substringSearch(term, null)。
     */
    public List<EntryRef> substringSearch(String term) {
        return substringSearch(term, null);
    }

    /**
     * 双向子串匹配（SP8d keywordSearch v1）：归一化后术语含 title/alias 或
     * title/alias 含术语均算命中。排序：精确命中(0) > 前缀命中(1) > 子串命中(2)，
     * 同级按归一 title 短者优先，再按 chunkKey 稳定序；结果截断到 maxResults。
     *
     * @param term   检索术语（大小写不敏感、全半角归一、去空白）
     * @param module 目标模块（可空 = 全模块）；非空时只返回该模块候选
     */
    public List<EntryRef> substringSearch(String term, String module) {
        if (!enabled || !built || term == null) {
            return List.of();
        }
        String normalizedTerm = normalize(term);
        if (normalizedTerm.isEmpty()) {
            return List.of();
        }
        Map<String, Scored> scored = new HashMap<>();
        for (Map.Entry<String, Map<String, EntryRef>> nameEntry : nameIndex.entrySet()) {
            int score = matchScore(normalizedTerm, nameEntry.getKey());
            if (score < 0) {
                continue;
            }
            for (EntryRef ref : nameEntry.getValue().values()) {
                if (module != null && !module.isBlank() && !module.equals(ref.module())) {
                    continue;
                }
                String key = chunkKey(ref.module(), ref.chunkId());
                Scored candidate = new Scored(ref, score, normalize(ref.title()).length());
                scored.merge(key, candidate, (a, b) -> a.score() <= b.score() ? a : b);
            }
        }
        return scored.values().stream()
                .sorted(Comparator.comparingInt(Scored::score)
                        .thenComparingInt(Scored::titleLength)
                        .thenComparing(s -> chunkKey(s.ref().module(), s.ref().chunkId())))
                .limit(maxResults)
                .map(Scored::ref)
                .toList();
    }

    /** 术语与归一名（title/alias）的命中级别：精确 0 / 前缀 1 / 双向子串 2 / 未命中 -1 */
    private int matchScore(String term, String name) {
        if (name.equals(term)) {
            return 0;
        }
        if (name.startsWith(term) || term.startsWith(name)) {
            return 1;
        }
        return name.contains(term) || term.contains(name) ? 2 : -1;
    }

    /** 按 (module, chunk_id) 查条目引用；未命中返回 null */
    public EntryRef findByChunkId(String module, String chunkId) {
        if (!enabled || !built || module == null || chunkId == null) {
            return null;
        }
        return entriesByChunkKey.get(chunkKey(module, chunkId));
    }

    /** 取条目的三层链接（基础/变体、引用它的、它引用的）；条目须在索引中 */
    public EntryLinks linksOf(EntryRef entry) {
        if (!enabled || !built || entry == null) {
            return new EntryLinks(entry, null, List.of(), List.of(), List.of());
        }
        String key = chunkKey(entry.module(), entry.chunkId());
        return new EntryLinks(
                entry,
                baseByVariant.get(key) == null ? null : baseByVariant.get(key).target(),
                variantsByBase.getOrDefault(key, List.of()),
                referencedByEntry.getOrDefault(key, List.of()),
                referencesByEntry.getOrDefault(key, List.of()));
    }

    /** 归一化：NFKC（全半角统一）→ 去全部空白 → 小写 */
    static String normalize(String name) {
        String nfkc = Normalizer.normalize(name.trim(), Normalizer.Form.NFKC);
        StringBuilder sb = new StringBuilder(nfkc.length());
        for (int i = 0; i < nfkc.length(); i++) {
            char ch = nfkc.charAt(i);
            if (!Character.isWhitespace(ch)) {
                sb.append(Character.toLowerCase(ch));
            }
        }
        return sb.toString();
    }

    /** 构建内存索引（开关关闭时跳过；两遍扫描：先注册全部条目，再解析边） */
    @PostConstruct
    void buildIndex() {
        if (!enabled) {
            log.info("[EntryResolver] 开关关闭（pf.search.entry-resolver-enabled=false），跳过索引构建");
            return;
        }
        List<Row> rows = new ArrayList<>(8192);
        rows.addAll(readRows("spell", Path.of(spellsPath), true));
        rows.addAll(readRows("class", Path.of(classesPath), false));
        rows.addAll(readRows("feat", Path.of(featPath), false));
        rows.addAll(readRows("race", Path.of(racePath), false));
        rows.addAll(readRows("trait", Path.of(traitPath), false));
        rows.addAll(readRows("equipment", Path.of(equipmentPath), false));
        rows.addAll(readRows("skill", Path.of(skillPath), false));
        rows.addAll(readRows("rule", Path.of(rulePath), false));
        for (Row row : rows) {
            register(row);
        }
        for (Row row : rows) {
            resolveEdges(row);
        }
        built = true;
        log.info("[EntryResolver] 索引构建完成：{} 条目、{} 名归一索引键", entriesByChunkKey.size(), nameIndex.size());
    }

    /** 注册条目：标题 + aliases 入名归一索引（同 chunk 多名字去重） */
    private void register(Row row) {
        EntryRef ref = new EntryRef(row.module(), row.chunkId(), row.title(),
                row.bookNameCn(), row.bookAbbreviation());
        String chunkKey = chunkKey(row.module(), row.chunkId());
        entriesByChunkKey.put(chunkKey, ref);
        for (String name : row.names()) {
            if (name == null || name.isBlank()) {
                continue;
            }
            nameIndex.computeIfAbsent(normalize(name), k -> new LinkedHashMap<>())
                    .putIfAbsent(chunkKey, ref);
        }
    }

    /** 解析条目的三类边：基础/变体、prerequisites、职业环级表 */
    private void resolveEdges(Row row) {
        String chunkKey = chunkKey(row.module(), row.chunkId());
        resolveBaseSpellEdge(row, chunkKey);
        resolvePrereqEdges(row, chunkKey);
        resolveSpellLevelEdges(row, chunkKey);
    }

    /** 基础/变体：base_spell_chunk_id 正向 + 变体反向（基础条目不在索引时退化为标题构造） */
    private void resolveBaseSpellEdge(Row row, String chunkKey) {
        if (row.baseChunkId() == null || row.baseChunkId().isBlank()) {
            return;
        }
        EntryRef base = entriesByChunkKey.get(chunkKey("spell", row.baseChunkId()));
        if (base == null && row.baseTitle() != null && !row.baseTitle().isBlank()) {
            base = new EntryRef("spell", row.baseChunkId(), row.baseTitle(), "", row.baseBook());
        }
        if (base == null) {
            return;
        }
        baseByVariant.put(chunkKey, new EntryLink(base, "神话变体"));
        variantsByBase.computeIfAbsent(chunkKey("spell", base.chunkId()), k -> new ArrayList<>())
                .add(entriesByChunkKey.get(chunkKey));
    }

    /** prerequisites：items 按类型优先模块解析名字，仅输出精确/别名命中的边 */
    private void resolvePrereqEdges(Row row, String chunkKey) {
        for (Map<String, Object> item : row.prereqItems()) {
            String type = item.get("type") instanceof String t ? t : "other";
            String note = switch (type) {
                case "feat" -> "前置专长";
                case "skill" -> "前置技能";
                case "race" -> "前置种族";
                case "spell" -> "法术前置";
                case "class_level" -> "职业等级前置";
                default -> "前置条件";
            };
            String name = itemName(item, type);
            if (name == null || name.isBlank()) {
                continue;
            }
            EntryRef target = resolveSingle(name, ITEM_TYPE_MODULES.get(type));
            if (target == null) {
                continue;   // 解析不到不输出该边（方案 J6：不匹配不硬解析）
            }
            addLink(referencesByEntry, chunkKey, new EntryLink(target, note));
            addLink(referencedByEntry, chunkKey(target.module(), target.chunkId()),
                    new EntryLink(entriesByChunkKey.get(chunkKey), note));
        }
    }

    /** 职业环级表：spell_level 的 class 名解析到职业条目，正向（环级表）+ 反向 */
    private void resolveSpellLevelEdges(Row row, String chunkKey) {
        for (String[] level : row.spellLevels()) {
            String className = level[0];
            if (className == null || className.isBlank()) {
                continue;
            }
            EntryRef target = resolveSingle(className, "class");
            if (target == null) {
                continue;
            }
            String note = level[1] == null || level[1].isBlank()
                    ? "职业法术列表" : level[1] + " 环法术列表";
            addLink(referencesByEntry, chunkKey, new EntryLink(target, note));
            addLink(referencedByEntry, chunkKey(target.module(), target.chunkId()),
                    new EntryLink(entriesByChunkKey.get(chunkKey), note));
        }
    }

    /** prerequisites item → 待解析名字：feat/race/spell/other 取 value，skill 取 skill，class_level 取 class/value */
    private String itemName(Map<String, Object> item, String type) {
        return switch (type) {
            case "feat", "race", "spell", "other" -> str(item.get("value"));
            case "skill" -> str(item.get("skill"));
            case "class_level" -> {
                String cls = str(item.get("class"));
                yield cls != null && !cls.isBlank() ? cls : str(item.get("value"));
            }
            default -> null;
        };
    }

    /** 解析到唯一条目：优先指定模块；优先模块多义/未命中时回退全模块唯一命中 */
    private EntryRef resolveSingle(String name, String preferredModule) {
        List<EntryRef> candidates = resolve(name, preferredModule);
        if (candidates.size() == 1) {
            return candidates.get(0);
        }
        if (!candidates.isEmpty()) {
            return null;    // 优先模块内仍多义：不硬解析
        }
        List<EntryRef> all = resolve(name);
        return all.size() == 1 ? all.get(0) : null;
    }

    /** 追加链接（跳过目标缺失的退化链接） */
    private void addLink(Map<String, List<EntryLink>> index, String chunkKey, EntryLink link) {
        if (link.target() == null) {
            return;
        }
        index.computeIfAbsent(chunkKey, k -> new ArrayList<>()).add(link);
    }

    /** 读一个模块的 chunks.jsonl → 行模型列表；文件缺失 warn 跳过，单行损坏 warn 跳过 */
    private List<Row> readRows(String module, Path path, boolean spell) {
        List<Row> rows = new ArrayList<>();
        if (!Files.exists(path)) {
            log.warn("[EntryResolver] chunks.jsonl 不存在，模块 {} 跳过: {}", module, path);
            return rows;
        }
        try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            String line;
            int lineNo = 0;
            while ((line = reader.readLine()) != null) {
                lineNo++;
                if (line.isBlank()) {
                    continue;
                }
                try {
                    Map<String, Object> raw = OBJECT_MAPPER.readValue(line, Map.class);
                    rows.add(spell ? toSpellRow(raw) : toStandardRow(module, raw));
                } catch (Exception e) {
                    log.warn("[EntryResolver] {} 第 {} 行解析失败，跳过: {}", path, lineNo, e.getMessage());
                }
            }
        } catch (Exception e) {
            log.warn("[EntryResolver] 读取 {} 失败，模块 {} 跳过: {}", path, module, e.getMessage());
        }
        return rows;
    }

    /** 法术行 → Row：base_spell_* 顶层字段 + spell_level 环级表 */
    private Row toSpellRow(Map<String, Object> raw) {
        Map<String, Object> metadata = mapValue(raw.get("metadata"));
        return new Row(
                "spell",
                str(raw.get("chunk_id")),
                str(raw.get("title")),
                str(raw.get("book_name_cn")),
                str(raw.get("book_abbreviation")),
                names(raw, metadata),
                str(raw.get("base_spell_chunk_id")),
                str(raw.get("base_spell_title")),
                str(raw.get("base_spell_book")),
                List.of(),
                spellLevels(metadata.get("spell_level")));
    }

    /** 标准模块行 → Row：prerequisites items 从嵌套 metadata 取 */
    private Row toStandardRow(String module, Map<String, Object> raw) {
        Map<String, Object> metadata = mapValue(raw.get("metadata"));
        return new Row(
                module,
                str(raw.get("chunk_id")),
                str(raw.get("title")),
                str(raw.get("book_name_cn")),
                str(raw.get("book_abbreviation")),
                names(raw, metadata),
                null, null, null,
                prereqItems(metadata.get("prerequisites")),
                List.of());
    }

    /** 名字列表：title + aliases（顶层字段） */
    private List<String> names(Map<String, Object> raw, Map<String, Object> metadata) {
        List<String> names = new ArrayList<>();
        names.add(str(raw.get("title")));
        Object aliases = raw.get("aliases");
        if (aliases instanceof List<?> list) {
            for (Object alias : list) {
                names.add(str(alias));
            }
        }
        return names;
    }

    /** spell_level 嵌套列表 → [class, level] 对 */
    private List<String[]> spellLevels(Object spellLevel) {
        List<String[]> levels = new ArrayList<>();
        if (spellLevel instanceof List<?> list) {
            for (Object entry : list) {
                if (entry instanceof Map<?, ?> m) {
                    String cls = str(m.get("class"));
                    if (cls != null && !cls.isBlank()) {
                        levels.add(new String[]{cls, str(m.get("level"))});
                    }
                }
            }
        }
        return levels;
    }

    /** prerequisites 嵌套对象 → items 列表 */
    private List<Map<String, Object>> prereqItems(Object prerequisites) {
        if (!(prerequisites instanceof Map<?, ?> p)) {
            return List.of();
        }
        Object items = p.get("items");
        if (!(items instanceof List<?> list)) {
            return List.of();
        }
        List<Map<String, Object>> result = new ArrayList<>();
        for (Object item : list) {
            if (item instanceof Map<?, ?> m) {
                @SuppressWarnings("unchecked")
                Map<String, Object> typed = (Map<String, Object>) m;
                result.add(typed);
            }
        }
        return result;
    }

    /** module|chunkId 组合键（与 SearchService 跨模块去重键风格一致） */
    private String chunkKey(String module, String chunkId) {
        return module + "|" + chunkId;
    }

    /** Object → String（null → null，保证 isBlank 判断语义） */
    private String str(Object value) {
        return value == null ? null : value.toString();
    }

    /** Object → Map 安全转型 */
    @SuppressWarnings("unchecked")
    private Map<String, Object> mapValue(Object value) {
        return value instanceof Map<?, ?> m ? (Map<String, Object>) m : Map.of();
    }
}
