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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 职业成长表直查服务（J5，F-019，D3）
 *
 * 加载 class_table_export.py 产出的 class_tables.json（数据侧把职业概览页的
 * 「表：XX」成长表预整理为 等级 → BAB/豁免/特殊能力/每日法术位 的结构化行），
 * 提供别名归一（两级：自身索引 + SpellListService 兜底）与按职业+等级的查表。
 *
 * 与 getSpellList 的关系：法术清单管"能学什么"，成长表管"每级数值多少"；
 * 本服务是派生数值（BAB/豁免/法术位）的唯一权威查表入口，LLM 禁止按公式自算。
 * 兼职/神话阶层一期不做合成（LLM 查表+查规则自行合成）。
 *
 * 溯源（J5 方案）：每职业带 source_chunk_id，优先用 SearchService.getByChunkId
 * 点查真实 chunk 交 SourceCollector；点查未命中（向量库版本错位）降级合成
 * Document 并 warn，保证 [#N] 不缺席。
 *
 * 加载缺失/失败时降级（available=false），不炸启动，对齐 SpellListService。
 */
@Component
public class ClassTableService {

    private static final Logger log = LoggerFactory.getLogger(ClassTableService.class);

    @Value("${pf.class-tables.file-path:../../pf_data/phase1/vectorizer/output/职业/class_tables.json}")
    private String filePath;

    @Autowired
    private SpellListService spellListService;
    @Autowired
    private SearchService searchService;

    private final ObjectMapper objectMapper = new ObjectMapper();

    /** 规范职业名 → 成长表（@PostConstruct 加载，加载前/失败为空） */
    private Map<String, ClassTable> classes = Map.of();
    /** 别名（含规范名自身，英文别名小写双向登记）→ 规范职业名；未加载时为空 */
    private Map<String, String> aliasIndex = Map.of();
    /** coverage.resolved_via（数据侧登记的跨键解析，如 骑士→骑将）；未加载时为空 */
    private Map<String, String> resolvedVia = Map.of();
    /** coverage.missing 名单（名字能识别但数据侧未整理的职业），诚实缺口返回用 */
    private List<String> missingClasses = List.of();
    private boolean available;

    /** 清单是否加载成功（文件存在且解析通过） */
    public boolean isAvailable() {
        return available;
    }

    /** 全部已收录规范职业名（有序，供未知职业自纠提示） */
    public List<String> knownClasses() {
        return classes.keySet().stream().sorted().toList();
    }

    /** 数据侧已登记缺失的职业名（coverage.missing），未知但有记录的缺口清单 */
    public List<String> missingClasses() {
        return missingClasses;
    }

    /**
     * 别名归一：先查自身索引（规范名/别名，英文别名大小写不敏感）；
     * miss 后查 coverage.resolved_via（数据侧登记的跨键解析，如 骑士→骑将）；
     * 仍 miss 借 SpellListService.resolve() 兜底（两产物同源于 CANONICAL_CLASS
     * 规范键空间），兜底结果须在本表 classes 内才算命中；未知返回 null。
     */
    public String resolve(String className) {
        if (className == null) {
            return null;
        }
        String key = className.trim();
        if (key.isEmpty()) {
            return null;
        }
        String canonical = aliasIndex.get(key);
        if (canonical == null) {
            canonical = aliasIndex.get(key.toLowerCase());
        }
        if (canonical == null) {
            String viaResolved = resolvedVia.get(key);
            if (viaResolved != null && classes.containsKey(viaResolved)) {
                canonical = viaResolved;
            }
        }
        if (canonical != null) {
            return canonical;
        }
        String viaSpellList = spellListService == null ? null : spellListService.resolve(key);
        if (viaSpellList != null && classes.containsKey(viaSpellList)) {
            return viaSpellList;
        }
        return null;
    }

    /** 该职业最大等级（resolve 后的规范名；未收录返回 0） */
    public int maxLevel(String canonical) {
        ClassTable table = classes.get(canonical);
        return table == null ? 0 : table.maxLevel();
    }

    /** 该职业是否有每日法术表（resolve 后的规范名） */
    public boolean hasSpellTable(String canonical) {
        ClassTable table = classes.get(canonical);
        return table != null && table.hasSpellTable();
    }

    /**
     * 单行成长表（紧凑单行，喂给 LLM）：
     * 「法师」等级 5：BAB +2 | 强韧 +1 | 反射 +1 | 意志 +4 | 特殊：无
     * 每日法术：0环4、1环3、2环2、3环1（null 环位省略；无 spell 段=无法术表行）
     */
    public String formatRow(String canonical, int level) {
        ClassTable table = classes.get(canonical);
        if (table == null) {
            return "职业「" + canonical + "」的成长表尚未加载。";
        }
        ClassLevel row = table.levels().get(String.valueOf(level));
        if (row == null) {
            return "职业「" + canonical + "」等级 " + level + " 无成长表数据。";
        }
        StringBuilder sb = new StringBuilder();
        sb.append('「').append(canonical).append("」等级 ").append(level).append("：");
        sb.append("BAB ").append(row.bab() == null ? "—" : row.bab());
        sb.append(" | 强韧 ").append(row.fort() == null ? "—" : row.fort());
        sb.append(" | 反射 ").append(row.ref() == null ? "—" : row.ref());
        sb.append(" | 意志 ").append(row.will() == null ? "—" : row.will());
        sb.append(" | 特殊：");
        if (row.special() == null || row.special().isEmpty()) {
            sb.append("无");
        } else {
            sb.append(String.join("、", row.special()));
        }
        String spells = formatSpells(table, row);
        if (!spells.isEmpty()) {
            sb.append('\n').append(spells);
        }
        return sb.toString();
    }

    /** 全表（level 省略语义）：1~max_level 逐行，行数 = levels 键数 */
    public String formatTable(String canonical) {
        ClassTable table = classes.get(canonical);
        if (table == null) {
            return "职业「" + canonical + "」的成长表尚未加载。";
        }
        StringBuilder sb = new StringBuilder();
        sb.append('「').append(canonical).append("」成长表（1~").append(table.maxLevel()).append(" 级）：");
        for (int lv = 1; lv <= table.maxLevel(); lv++) {
            sb.append('\n').append(formatRow(canonical, lv));
        }
        return sb.toString();
    }

    /**
     * 溯源 Document：优先 SearchService.getByChunkId("class", source_chunk_id) 点查
     * 真实 chunk（前端溯源区直接展示成长表原文页）；未命中（向量库版本错位等）降级
     * 合成 Document（title/chunk_id/doc_id 齐），保证 [#N] 不缺席并 warn。
     */
    public Document provenanceDocument(String canonical) {
        ClassTable table = classes.get(canonical);
        String title = canonical + "职业成长表";
        if (table == null) {
            return Document.builder().text("").metadata(Map.of("title", title)).build();
        }
        if (searchService != null && table.sourceChunkId() != null) {
            Document doc = searchService.getByChunkId("class", table.sourceChunkId());
            if (doc != null) {
                return doc;
            }
            log.warn("成长表 source_chunk_id 点查未命中（职业={}，chunk_id={}），"
                    + "疑似 class_tables.json 与向量库版本错位，降级合成溯源 Document。",
                    canonical, table.sourceChunkId());
        }
        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("title", title);
        meta.put("book_name_cn", title);
        if (table.sourceChunkId() != null) {
            meta.put("chunk_id", table.sourceChunkId());
        }
        if (table.sourceDocId() != null) {
            meta.put("doc_id", table.sourceDocId());
        }
        return Document.builder()
                .text(title + "（数据侧 class_tables.json 预整理；向量库未检索到对应原文 chunk，"
                        + "可用 vectorSearch 检索该职业成长规则原文）")
                .metadata(meta)
                .build();
    }

    /** 每日法术位段：「每日法术：0环4、1环3…」；null 环位省略；无法术表返回空串 */
    private String formatSpells(ClassTable table, ClassLevel row) {
        if (!table.hasSpellTable()) {
            return "";
        }
        if (row.spells() == null || row.spells().isEmpty()) {
            return "每日法术：—";
        }
        List<String> parts = row.spells().entrySet().stream()
                .filter(e -> e.getValue() != null)
                .sorted(Map.Entry.comparingByKey((a, b) -> Integer.compare(Integer.parseInt(a), Integer.parseInt(b))))
                .map(e -> e.getKey() + "环" + e.getValue())
                .toList();
        return parts.isEmpty() ? "每日法术：—" : "每日法术：" + String.join("、", parts);
    }

    /** 加载 class_tables.json 进内存；缺失/解析失败 → 降级 available=false，不炸启动 */
    @PostConstruct
    void load() {
        Path path = Path.of(filePath);
        if (!Files.exists(path)) {
            log.warn("class_tables.json 不存在（{}），职业成长表工具将降级不可用。", path.toAbsolutePath());
            return;
        }
        try {
            ClassTableFile file = objectMapper.readValue(path.toFile(), ClassTableFile.class);
            this.classes = file.classes() == null ? Map.of() : file.classes();
            this.aliasIndex = buildAliasIndex(this.classes);
            this.resolvedVia = file.coverage() == null || file.coverage().resolvedVia() == null
                    ? Map.of()
                    : file.coverage().resolvedVia();
            this.missingClasses = file.coverage() == null || file.coverage().missing() == null
                    ? List.of()
                    : file.coverage().missing().stream().map(MissingClass::className).toList();
            this.available = true;
            log.info("class_tables.json 加载完成：{} 职业、缺失 {} 职业（{}）",
                    classes.size(), missingClasses.size(), path.getFileName());
        } catch (IOException e) {
            log.error("class_tables.json 解析失败（{}），职业成长表工具将降级不可用。", path.toAbsolutePath(), e);
        }
    }

    /** 别名索引：规范名自身 + 每职业 aliases（若有）→ 规范名；英文别名额外小写登记。
     *  撞车时首登记优先（putIfAbsent）并 warn，便于发现数据侧别名撞名 */
    private Map<String, String> buildAliasIndex(Map<String, ClassTable> data) {
        Map<String, String> index = new LinkedHashMap<>();
        data.forEach((canonical, table) -> {
            putAlias(index, canonical, canonical);
            putAlias(index, canonical.toLowerCase(), canonical);
            if (table.aliases() != null) {
                table.aliases().forEach(alias -> {
                    putAlias(index, alias, canonical);
                    putAlias(index, alias.toLowerCase(), canonical);
                });
            }
        });
        return index;
    }

    /** 单个别名登记：已存在且指向不同规范名时保留首登记并 warn */
    private void putAlias(Map<String, String> index, String alias, String canonical) {
        String existing = index.putIfAbsent(alias, canonical);
        if (existing != null && !existing.equals(canonical)) {
            log.warn("成长表别名撞名：「{}」已指向「{}」，忽略指向「{}」的重复登记（首登记优先）。",
                    alias, existing, canonical);
        }
    }

    // ---------- class_tables.json 数据模型（组件 camelCase，snake_case JSON 键用 @JsonProperty 映射） ----------

    /** 顶层文件：classes + coverage；version/generated_from/source_fingerprint 等忽略 */
    @JsonIgnoreProperties(ignoreUnknown = true)
    record ClassTableFile(
            @JsonProperty("classes") Map<String, ClassTable> classes,
            @JsonProperty("coverage") Coverage coverage) {
    }

    /** coverage：parsed（已收录）/ missing（已登记缺口）/ resolved_via（跨键解析）；stats 忽略 */
    @JsonIgnoreProperties(ignoreUnknown = true)
    record Coverage(
            List<String> parsed,
            @JsonProperty("missing") List<MissingClass> missing,
            @JsonProperty("resolved_via") Map<String, String> resolvedVia) {

        Coverage {
            parsed = parsed == null ? List.of() : parsed;
            missing = missing == null ? List.of() : missing;
            resolvedVia = resolvedVia == null ? Map.of() : resolvedVia;
        }
    }

    /** 缺口登记项：class（职业名）/ reason / doc_id */
    @JsonIgnoreProperties(ignoreUnknown = true)
    record MissingClass(
            @JsonProperty("class") String className,
            String reason,
            @JsonProperty("doc_id") String docId) {
    }

    /** 单职业成长表：source_chunk_id/source_doc_id/max_level/has_spell_table/levels */
    @JsonIgnoreProperties(ignoreUnknown = true)
    record ClassTable(
            List<String> aliases,
            @JsonProperty("source_chunk_id") String sourceChunkId,
            @JsonProperty("source_doc_id") String sourceDocId,
            @JsonProperty("max_level") int maxLevel,
            @JsonProperty("has_spell_table") boolean hasSpellTable,
            Map<String, ClassLevel> levels) {

        ClassTable {
            aliases = aliases == null ? List.of() : aliases;
            levels = levels == null ? Map.of() : levels;
        }
    }

    /** 单行等级成长：bab/fort/ref/will 保留 D3 原文（多攻形态不展开）；special/spells 可缺省。
     *  spells 值除整数/null 外可能是领域加值字符串（如牧师的 "4+1"），按原文透出不做计算 */
    @JsonIgnoreProperties(ignoreUnknown = true)
    record ClassLevel(
            String bab,
            String fort,
            String ref,
            String will,
            List<String> special,
            Map<String, Object> spells) {

        ClassLevel {
            special = special == null ? List.of() : special;
            spells = spells == null ? Map.of() : spells;
        }
    }
}
