package com.pfagent.agent.rag;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.document.Document;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 职业法术列表直查服务（SP3 F-007，D4）
 *
 * 加载 spell_list_export.py 产出的 spell_lists.json（数据侧把 27 职业官方列表页
 * 预整理为环级结构化清单），提供别名归一与按职业+环级的枚举查询。
 *
 * 与 searchByMetadata 的关系（D7）：本服务是**枚举直达通道**——列表页本身是
 * 权威完整枚举，不受 chunk 元数据 spell_level 35% 缺失与职业名脏变体影响。
 * 加载缺失/失败时降级（available=false、方法返回可读空态），不炸启动，
 * 对齐 DataLoader 宽松语义。
 *
 * 溯源（用户 2026-09-06 拍板）：每职业 JSON 带 source_toc_path（列表页 CHM 目录
 * 路径）+ source_excerpt（列表页标题行 + 条目数概述），Java 运行时零额外 IO，
 * 直接由 listPageDocument 构造溯源 Document 交 SourceCollector。
 */
@Component
public class SpellListService {

    private static final Logger log = LoggerFactory.getLogger(SpellListService.class);
    private static final int MAX_LEVEL = 9;

    @Value("${pf.spell-lists.file-path:../../pf_data/phase1/vectorizer/output/法术/spell_lists.json}")
    private String filePath;

    private final ObjectMapper objectMapper = new ObjectMapper();

    /** 规范职业名 → 法术清单（@PostConstruct 加载，加载前/失败为空） */
    private Map<String, SpellList> classes = Map.of();
    /** 别名（含规范名自身）→ 规范职业名；未加载时为空 */
    private Map<String, String> aliasIndex = Map.of();
    private boolean available;

    /** 清单是否加载成功（文件存在且解析通过） */
    public boolean isAvailable() {
        return available;
    }

    /** 全部规范职业名（有序，供未知职业自纠提示） */
    public List<String> knownClasses() {
        return classes.keySet().stream().sorted().toList();
    }

    /**
     * 别名归一：className（自身/别名/全角括号变体）→ 规范职业名；
     * 未知返回 null。className 为 null/空白同样返回 null。
     */
    public String resolve(String className) {
        if (className == null) {
            return null;
        }
        String key = className.trim();
        if (key.isEmpty()) {
            return null;
        }
        return aliasIndex.get(key);
    }

    /**
     * 该职业各环级条目数概览文本（level 为空/越界时给 LLM 的兜底，
     * 提示指定 0~9 环查看具体清单）。className 须已 resolve 过的规范名。
     */
    public String levelOverview(String className) {
        SpellList list = classes.get(className);
        if (list == null) {
            return "职业「" + className + "」的法术清单尚未加载。";
        }
        StringBuilder sb = new StringBuilder();
        sb.append('「').append(className).append("」法术列表共收录 0~9 环 ")
                .append(totalEntries(list)).append(" 条法术，各环级条目数：");
        List<String> parts = new ArrayList<>();
        for (int lv = 0; lv <= MAX_LEVEL; lv++) {
            int count = levelCount(list, lv);
            parts.add(lv + "环 " + count + " 条");
        }
        sb.append(String.join("、", parts));
        sb.append("。请指定具体环级（0~9）查看清单，如 level=")
                .append(firstNonEmptyLevel(list)).append('。');
        return sb.toString();
    }

    /**
     * 单环级紧凑清单（D5）：`序号. 中文名（English） [书缩写]` 逐行。
     * 结果超 maxChars（复用 pf.search.metadata-result-chars 护栏）时截断并提示
     * 收窄，防海量条目淹没 LLM；className 须已 resolve 过的规范名。
     */
    public String formatLevel(String className, int level, int maxChars) {
        SpellList list = classes.get(className);
        if (list == null) {
            return "职业「" + className + "」的法术清单尚未加载。";
        }
        List<SpellListEntry> entries = list.levels().getOrDefault(String.valueOf(level), List.of());
        StringBuilder sb = new StringBuilder();
        sb.append('「').append(className).append("」").append(level).append(" 环法术（共 ")
                .append(entries.size()).append(" 条）：\n");
        int shown = 0;
        for (int i = 0; i < entries.size(); i++) {
            String line = buildEntryLine(i + 1, entries.get(i)) + '\n';
            if (sb.length() + line.length() > maxChars) {
                break;
            }
            sb.append(line);
            shown++;
        }
        if (shown < entries.size()) {
            sb.append("…（清单过长，仅展示前 ").append(shown).append(" 条 / 共 ")
                    .append(entries.size()).append(" 条；如需完整可按来源书/书名收窄，或用 vectorSearch）");
        }
        return sb.toString();
    }

    /**
     * 构造该职业的列表页溯源 Document（D5/V3）：metadata 对齐统一溯源键
     * （book_name_cn/book_abbreviation/tocPath/chunk_id/doc_id/title），正文为
     * 数据侧嵌入的列表页摘要，Java 零额外 IO。className 须已 resolve 的规范名。
     */
    public Document listPageDocument(String className) {
        SpellList list = classes.get(className);
        String title = className + "法术列表";
        if (list == null) {
            // 防御：仅理论路径（resolve 后方法间状态不变），不抛异常给工具层
            return Document.builder().text("").metadata(Map.of("title", title)).build();
        }
        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("title", title);
        meta.put("book_name_cn", title);
        meta.put("doc_id", list.sourcePage());
        if (list.listChunkId() != null) {
            meta.put("chunk_id", list.listChunkId());
        }
        meta.put("tocPath", list.sourceTocPath());
        return Document.builder()
                .text(list.sourceExcerpt() == null ? title : list.sourceExcerpt())
                .metadata(meta)
                .build();
    }

    /** 加载 spell_lists.json 进内存；缺失/解析失败 → 降级 available=false，不炸启动 */
    @PostConstruct
    void load() {
        Path path = Path.of(filePath);
        if (!Files.exists(path)) {
            log.warn("spell_lists.json 不存在（{}），职业法术列表工具将降级不可用。", path.toAbsolutePath());
            return;
        }
        try {
            SpellListFile file = objectMapper.readValue(path.toFile(), SpellListFile.class);
            this.classes = file.classes();
            this.aliasIndex = buildAliasIndex(file.classes());
            this.available = true;
            log.info("spell_lists.json 加载完成：{} 职业、{} 条法术（{}）",
                    classes.size(), totalAll(), path.getFileName());
        } catch (IOException e) {
            log.error("spell_lists.json 解析失败（{}），职业法术列表工具将降级不可用。", path.toAbsolutePath(), e);
        }
    }

    /** 别名索引：规范名自身 + 每职业 aliases（变体）→ 规范名 */
    private Map<String, String> buildAliasIndex(Map<String, SpellList> data) {
        Map<String, String> index = new LinkedHashMap<>();
        data.forEach((canonical, list) -> {
            index.put(canonical, canonical);
            if (list.aliases() != null) {
                list.aliases().forEach(alias -> index.putIfAbsent(alias, canonical));
            }
        });
        return index;
    }

    /** 单职业全环条目总数 */
    private int totalEntries(SpellList list) {
        return list.levels().values().stream().mapToInt(List::size).sum();
    }

    /** 单职业单环条目数（环级缺省视为 0） */
    private int levelCount(SpellList list, int level) {
        return list.levels().getOrDefault(String.valueOf(level), List.of()).size();
    }

    /** 首个非空环级（概览提示示例用；全空返回 0） */
    private int firstNonEmptyLevel(SpellList list) {
        for (int lv = 0; lv <= MAX_LEVEL; lv++) {
            if (levelCount(list, lv) > 0) {
                return lv;
            }
        }
        return 0;
    }

    /** 全职业全环条目总数（加载日志用） */
    private long totalAll() {
        return classes.values().stream().mapToLong(list -> list.levels().values().stream()
                .mapToLong(List::size).sum()).sum();
    }

    /** 单条目紧凑行：`序号. 中文名（English） [书缩写]`；en/book 缺省时省段 */
    private String buildEntryLine(int index, SpellListEntry entry) {
        StringBuilder line = new StringBuilder(index + ". ").append(entry.cn());
        if (entry.en() != null && !entry.en().isBlank()) {
            line.append('（').append(entry.en()).append('）');
        }
        if (entry.book() != null && !entry.book().isBlank()) {
            line.append(" [").append(entry.book()).append(']');
        }
        return line.toString();
    }

    // ---------- spell_lists.json 数据模型（组件 camelCase，snake_case JSON 键用 @JsonProperty 映射） ----------

    /** 顶层文件：只取 classes，version/generated_from 忽略 */
    @JsonIgnoreProperties(ignoreUnknown = true)
    record SpellListFile(@JsonProperty("classes") Map<String, SpellList> classes) {
    }

    /** 单职业清单：aliases/source_page/source_toc_path/source_excerpt/list_chunk_id/levels */
    @JsonIgnoreProperties(ignoreUnknown = true)
    record SpellList(
            List<String> aliases,
            @JsonProperty("source_page") String sourcePage,
            @JsonProperty("source_toc_path") String sourceTocPath,
            @JsonProperty("source_excerpt") String sourceExcerpt,
            @JsonProperty("list_chunk_id") String listChunkId,
            Map<String, List<SpellListEntry>> levels) {

        SpellList {
            aliases = aliases == null ? List.of() : aliases;
            levels = levels == null ? Map.of() : levels;
        }
    }

    /** 单法术条目：cn/en/book/chunk_id（chunk_id 为 chunks 交叉命中，可能为 null） */
    @JsonIgnoreProperties(ignoreUnknown = true)
    record SpellListEntry(
            String cn,
            String en,
            String book,
            @JsonProperty("chunk_id") String chunkId) {

        SpellListEntry {
            cn = cn == null ? "" : cn;
        }
    }
}
