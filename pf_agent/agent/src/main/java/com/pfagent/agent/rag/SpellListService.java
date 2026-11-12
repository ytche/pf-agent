package com.pfagent.agent.rag;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
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
import java.util.Objects;

/**
 * 职业法术列表直查服务（SP3 F-007，D4；F-025 折叠清单消费）
 *
 * 加载 spell_list_export.py 产出的 spell_lists.json（数据侧把 27 职业官方列表页
 * 预整理为环级结构化清单），提供别名归一与按职业+环级的枚举查询。
 *
 * 与 searchByMetadata 的关系（D7）：本服务是**枚举直达通道**——列表页本身是
 * 权威完整枚举，不受 chunk 元数据 spell_level 35% 缺失与职业名脏变体影响。
 * 加载缺失/失败时降级（available=false、方法返回可读空态），不炸启动，
 * 对齐 DataLoader 宽松语义。
 *
 * union 产物消费（B1 → F-025）：spell_lists_union.json 版本决定消费路径——
 * 1.1 直读数据侧已折叠的完整条目序列（官方主条目 + 新增派生组，每个法术只
 * 出现一次，sources 保留全部去重来源书）；1.0 走旧「官方 + derived 过滤」
 * 兼容路径并 WARN（不做运行时二次去重）；缺失/畸形/未知版本/无效 1.1 一律
 * WARN 降级为仅官方清单。
 *
 * 溯源（用户 2026-09-06 拍板）：每职业 JSON 带 source_toc_path（列表页 CHM 目录
 * 路径）+ source_excerpt（列表页标题行 + 条目数概述），Java 运行时零额外 IO，
 * 直接由 listPageDocument 构造溯源 Document 交 SourceCollector。
 */
@Component
public class SpellListService {

    private static final Logger log = LoggerFactory.getLogger(SpellListService.class);
    private static final int MAX_LEVEL = 9;
    private static final String UNION_VERSION_FOLDED = "1.1";

    @Value("${pf.spell-lists.file-path:../../pf_data/phase1/vectorizer/output/法术/spell_lists.json}")
    private String filePath;

    /**
     * B1 派生补充清单（方案_B1法术派生补充清单_20261029，拍板 2026-10-28/29；
     * F-025 升级为折叠清单消费）：spell_lists_union.json 路径。
     * 缺失/解析失败/版本不受支持/无效 1.1 → WARN 降级为仅官方清单（不 FAIL），
     * 与 spell_lists.json 缺失降级同语义（对齐 ListExportService 独立容错先例）。
     */
    @Value("${pf.spell-lists.union-file-path:../../pf_data/phase1/vectorizer/output/法术/spell_lists_union.json}")
    private String unionFilePath;

    private final ObjectMapper objectMapper = new ObjectMapper();

    /** 规范职业名 → 法术清单（@PostConstruct 加载，加载前/失败为空） */
    private Map<String, SpellList> classes = Map.of();
    /** 别名（含规范名自身）→ 规范职业名；未加载时为空 */
    private Map<String, String> aliasIndex = Map.of();
    private boolean available;
    /**
     * 派生条目索引：职业 → 环级字符串 → derived 条目列表（union 1.0 兼容路径
     * 加载成功时非空；excluded 五职业不会出现在其中——数据侧产物保证 OA 零派生）。
     */
    private Map<String, Map<String, List<UnionEntry>>> unionDerived = Map.of();
    /**
     * 折叠条目索引：职业 → 环级字符串 → 去重后完整条目序列（union 1.1 路径，
     * 同时包含官方主条目与纯派生主条目；1.0 路径为空）。
     */
    private Map<String, Map<String, List<UnionEntry>>> unionFolded = Map.of();
    /** union 产物是否加载成功（失败降级不影响官方清单可用性） */
    private boolean unionAvailable;
    /** union 是否走 1.1 折叠直读路径（false=1.0 兼容路径或不可用） */
    private boolean unionFoldedPath;

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
     * 计数口径与 formatLevel/levelTotal 共用同一份解析后条目序列
     * （union 1.1=折叠后不同法术数；union 1.0=官方+派生；无 union=官方）。
     */
    public String levelOverview(String className) {
        SpellList list = classes.get(className);
        if (list == null) {
            return "职业「" + className + "」的法术清单尚未加载。";
        }
        StringBuilder sb = new StringBuilder();
        sb.append('「').append(className).append("」法术列表共收录 0~9 环 ")
                .append(totalEntries(className)).append(" 条法术，各环级条目数：");
        List<String> parts = new ArrayList<>();
        for (int lv = 0; lv <= MAX_LEVEL; lv++) {
            parts.add(lv + "环 " + levelEntries(className, lv).size() + " 条");
        }
        sb.append(String.join("、", parts));
        sb.append("。请指定具体环级（0~9）查看清单，如 level=")
                .append(firstNonEmptyLevel(className)).append('。');
        return sb.toString();
    }

    /**
     * 单职业单环合并条目总数（与 formatLevel/pagination 同一份解析后序列；
     * union 1.1=折叠后不同法术数，union 1.0=官方+派生，无 union=官方数）。
     */
    public int levelTotal(String className, int level) {
        return levelEntries(className, level).size();
    }

    /**
     * 单环级紧凑清单（D5）：`序号. 中文名（English） [书缩写]` 逐行。
     * 结果超 maxChars（复用 pf.search.metadata-result-chars 护栏）时截断并给
     * 翻页指引（真实总数 / 返回区间 / has_more / 续取 offset），防海量条目
     * 淹没 LLM；className 须已 resolve 过的规范名。
     *
     * 分页（B1 端到端补口，与 J2 searchByMetadata 同构）：offset/limit 均为
     * null 时行为同旧版（全量窗口 + 翻页指引 footer）；传入时按 [offset, offset+limit)
     * 窗口返回。offset 为负钳制为 0；offset 越界返回可读提示。翻完末页 footer
     * 给「已翻完全部结果（共 N 条）」。
     *
     * F-025：书缩写位置展示 sources 全部非空书缩写的去重结果（主来源在前，
     * 其余按首次出现顺序），如 [PSP/COMP]；只有主来源为 derived 的条目带〔派生〕。
     */
    public String formatLevel(String className, int level, int maxChars) {
        return formatLevel(className, level, maxChars, null, null);
    }

    /** 分页版单环清单：见 {@link #formatLevel(String, int, int)}。 */
    public String formatLevel(String className, int level, int maxChars,
                              Integer offset, Integer limit) {
        SpellList list = classes.get(className);
        if (list == null) {
            return "职业「" + className + "」的法术清单尚未加载。";
        }
        List<DisplayEntry> entries = levelEntries(className, level);
        int total = entries.size();

        // ---- 窗口计算（offset/limit 均 null = 全量窗口，默认行为同旧版）----
        boolean paged = offset != null || limit != null;
        int off = offset == null ? 0 : Math.max(offset, 0);
        int winEnd = limit == null ? total : Math.min(off + Math.max(limit, 0), total);
        if (paged && off >= total && total > 0) {
            return "无命中：共 " + total + " 条，但 offset=" + off
                    + " 越界（limit=" + (limit == null ? "全部" : limit)
                    + "），请减小 offset 翻页。";
        }
        winEnd = Math.max(winEnd, off);

        StringBuilder sb = new StringBuilder();
        sb.append('「').append(className).append("」").append(level).append(" 环法术（共 ")
                .append(total).append(" 条）：\n");
        int shown = 0;
        for (int i = off; i < entries.size() && i < winEnd; i++) {
            String line = buildLine(i + 1, entries.get(i)) + '\n';
            if (sb.length() + line.length() > maxChars) {
                break;
            }
            sb.append(line);
            shown++;
        }
        int nextOffset = off + shown;
        boolean hasMore = nextOffset < total;
        if (!paged && !hasMore) {
            return sb.toString();  // 默认全量未截断：footer 零变化（旧行为）
        }
        if (shown == 0) {
            // 首条即超字符预算：翻页 offset 不前进，不给续取指引（对齐 AKN015-T2）
            sb.append("…（本页从第 ").append(off + 1).append(" 条起（offset=")
                    .append(off).append("，limit=").append(limit == null ? "全部" : limit)
                    .append("）的内容超出单次展示字符上限，本页无条目可展示；请收窄"
                            + "（按来源书/书名过滤也是合法收窄路径）后重试，"
                            + "不要用相同 offset 重复翻页）");
            return sb.toString();
        }
        sb.append("…（共 ").append(total).append(" 条，本次返回第 ")
                .append(off + 1).append('~').append(off + shown).append(" 条");
        if (hasMore) {
            sb.append("，has_more=true；续取：保持其他参数不变，offset=")
                    .append(nextOffset);
            sb.append("（也可按来源书/书名收窄过滤）");
        } else {
            sb.append("；已翻完全部结果（共 ").append(total).append(" 条）");
        }
        sb.append('）');
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
        loadUnion();
    }

    /**
     * 加载 spell_lists_union.json 并按版本选择消费路径（B1 → F-025）：
     * 1.1 → 校验后直读折叠完整条目序列；1.0/无版本 → 旧 derived-only 兼容
     * 索引并 WARN（保留旧计数行为，不做运行时去重）；更高未知版本、缺失、
     * 畸形、无效 1.1 → WARN 降级为仅官方清单（unionAvailable=false）。
     */
    private void loadUnion() {
        if (unionFilePath == null || unionFilePath.isBlank()) {
            // 测试/非 Spring 场景未注入路径 → 静默跳过（union 不可用，官方清单零影响）
            return;
        }
        Path path = Path.of(unionFilePath);
        if (!Files.exists(path)) {
            log.warn("spell_lists_union.json 不存在（{}），getSpellList 降级为仅官方清单"
                    + "（派生补充不可用，B1 口径声明见工具说明）。", path.toAbsolutePath());
            return;
        }
        try {
            // presence-aware 解析（评审 r1-P1）：先用 JsonNode 读树以区分「缺键」与「JSON null」，
            // 版本分支与 1.1 结构校验全部基于键存在性，通过后再转 record
            JsonNode root = objectMapper.readTree(path.toFile());
            // 评审 r2-P1：根节点为空文件/null/缺节点/非对象时 WARN 降级——
            // treeToValue 会返回 null 并在后续解引用处 NPE 逃逸出 @PostConstruct
            if (root == null || root.isMissingNode() || root.isNull() || !root.isObject()) {
                log.warn("spell_lists_union.json 根节点为空/null/非对象（{}），getSpellList 降级为仅官方清单"
                        + "（畸形产物不猜测解析）。", path.getFileName());
                return;
            }
            String version = root.hasNonNull("version") ? root.get("version").asText() : null;
            if (version == null || version.isBlank() || "1.0".equals(version)) {
                // F-025：1.0 旧产物（含缺 version 字段）兼容读取（版本过渡，不是二次去重通道），
                // 保留旧计数行为
                log.warn("spell_lists_union.json 为 1.0 旧产物（{}）：按官方+派生旧口径兼容读取，"
                        + "未折叠的重复条目仍会重复计数；请重建 1.1 产物（F-025）。", path.getFileName());
                UnionFile file = objectMapper.treeToValue(root, UnionFile.class);
                if (file == null) {
                    log.warn("spell_lists_union.json 无法转为模型（{}），getSpellList 降级为仅官方清单。",
                            path.getFileName());
                    return;
                }
                this.unionDerived = derivedOnlyIndex(file);
                this.unionFolded = Map.of();
                this.unionAvailable = true;
                this.unionFoldedPath = false;
                log.info("spell_lists_union.json 加载完成：{} 职业（derived 索引已建，1.0 兼容路径）",
                        unionDerived.size());
                return;
            }
            if (!UNION_VERSION_FOLDED.equals(version)) {
                log.warn("spell_lists_union.json 版本 {} 不受支持（{}），getSpellList 降级为仅官方清单"
                        + "（不按 1.1 猜测解析）。", version, path.getFileName());
                return;
            }
            if (!isValidUnion11(root)) {
                log.warn("spell_lists_union.json 为无效 1.1 产物（条目/来源容器或元素为 null、缺 classes/levels"
                        + " 键、source/matched_by 空白、派生来源缺 chunk_id、官方来源缺 book/chunk_id 键、"
                        + "主来源镜像不一致或未覆盖官方清单全部职业与 0~9 环），getSpellList 降级为仅官方清单"
                        + "（F-025 不静默补造来源）。", path.getFileName());
                return;
            }
            UnionFile file = objectMapper.treeToValue(root, UnionFile.class);
            if (file == null) {
                log.warn("spell_lists_union.json 无法转为模型（{}），getSpellList 降级为仅官方清单。",
                        path.getFileName());
                return;
            }
            Map<String, Map<String, List<UnionEntry>>> index = new LinkedHashMap<>();
            file.classes().forEach((cls, cl) -> {
                Map<String, List<UnionEntry>> byLevel = new LinkedHashMap<>();
                cl.levels().forEach(byLevel::put);
                index.put(cls, byLevel);
            });
            this.unionFolded = index;
            this.unionDerived = Map.of();
            this.unionAvailable = true;
            this.unionFoldedPath = true;
            log.info("spell_lists_union.json 加载完成：{} 职业（1.1 折叠清单直读，{}）",
                    index.size(), path.getFileName());
        } catch (IOException | RuntimeException e) {
            log.warn("spell_lists_union.json 解析失败（{}），getSpellList 降级为仅官方清单。",
                    path.toAbsolutePath(), e);
        }
    }

    /** union 1.0 兼容索引：只收 derived 条目（official_list 条目不重复并入） */
    private Map<String, Map<String, List<UnionEntry>>> derivedOnlyIndex(UnionFile file) {
        Map<String, Map<String, List<UnionEntry>>> index = new LinkedHashMap<>();
        file.classes().forEach((cls, cl) -> {
            Map<String, List<UnionEntry>> byLevel = new LinkedHashMap<>();
            cl.levels().forEach((lv, entries) -> byLevel.put(lv,
                    entries.stream().filter(e -> "derived".equals(e.source())).toList()));
            index.put(cls, byLevel);
        });
        return index;
    }

    /**
     * union 1.1 结构校验（评审 r1-P1 强化，presence-aware：区分「缺键」与「JSON null」）：
     * classes 必须为非空对象；每职业 levels 必须为对象；每环级必须为条目数组；
     * 条目/来源数组元素不得为 null；每条目 sources 非空数组；每个 source 的
     * book/chunk_id 键必须存在（值允许 null）、source/matched_by 非空白、
     * 派生来源 chunk_id 非空白；首个 source（主来源）与顶层镜像
     * book/chunk_id/source/matched_by 同键同值（level_evidence 缺键等价 null，
     * 仅一侧有非空值时要求相等）——仅官方主条目可省略顶层 matched_by 键
     * （其 source 中必须记录）。另校验 union 覆盖官方清单全部职业与 0~9 环
     * （评审 r2-P2：版本错配时不得静默清空某职业/环级的官方条目）。
     * 任一不满足视为无效 1.1 产物（F-025 §9），校验本身不抛异常。
     */
    private boolean isValidUnion11(JsonNode root) {
        try {
            JsonNode classes = root.get("classes");
            if (classes == null || !classes.isObject() || classes.isEmpty()) {
                return false;
            }
            for (JsonNode cl : classes) {
                JsonNode levels = cl.get("levels");
                if (levels == null || !levels.isObject()) {
                    return false;
                }
                for (JsonNode levelEntries : levels) {
                    if (!levelEntries.isArray()) {
                        return false;
                    }
                    for (JsonNode entry : levelEntries) {
                        if (!isValidUnion11Entry(entry)) {
                            return false;
                        }
                    }
                }
            }
            return coversOfficialClasses(root);
        } catch (RuntimeException e) {
            return false;
        }
    }

    private boolean isValidUnion11Entry(JsonNode entry) {
        if (entry == null || !entry.isObject()) {
            return false;
        }
        JsonNode sources = entry.get("sources");
        if (sources == null || !sources.isArray() || sources.isEmpty()) {
            return false;
        }
        for (JsonNode source : sources) {
            if (!isValidUnion11Source(source)) {
                return false;
            }
        }
        JsonNode primary = sources.get(0);
        if (!mirrorsPrimary(entry, primary, "book")
                || !mirrorsPrimary(entry, primary, "chunk_id")
                || !mirrorsPrimary(entry, primary, "source")
                || !mirrorsPrimaryOptional(entry, primary, "level_evidence")) {
            return false;
        }
        if (entry.has("matched_by")) {
            return mirrorsPrimary(entry, primary, "matched_by");
        }
        // 顶层 matched_by 省略仅限官方主条目（派生主条目必须顶层记录）
        return primary.has("source") && "official_list".equals(primary.get("source").asText());
    }

    /** 主来源镜像：顶层与主来源必须同键（缺任一键=镜像缺失=无效）且同值（JSON null 合法） */
    private boolean mirrorsPrimary(JsonNode entry, JsonNode primary, String field) {
        return entry.has(field) && primary.has(field)
                && Objects.equals(entry.get(field), primary.get(field));
    }

    /**
     * 可选镜像字段（level_evidence，评审 r2-P1）：缺键等价 JSON null——spec §6.2
     * 只要求派生来源保存该字段，官方条目/官方来源可整体省略；两侧都缺键或
     * 都为 null 视为一致，仅当一侧有非空值时要求两侧相等。
     */
    private boolean mirrorsPrimaryOptional(JsonNode entry, JsonNode primary, String field) {
        JsonNode top = entry.get(field);
        JsonNode fromPrimary = primary.get(field);
        boolean topAbsent = top == null || top.isNull();
        boolean primaryAbsent = fromPrimary == null || fromPrimary.isNull();
        if (topAbsent || primaryAbsent) {
            return topAbsent && primaryAbsent;
        }
        return Objects.equals(top, fromPrimary);
    }

    /**
     * 1.1 覆盖率校验（评审 r2-P2）：union 必须覆盖官方清单的全部职业与 0~9 环键。
     * 折叠路径下 classes/levels 完全以 union 为准，覆盖缺失（如 union 与
     * spell_lists.json 来自不同构建版本）会静默清空该职业/环级，故按无效 1.1
     * 降级。官方清单未加载时无覆盖基准，放行。
     */
    private boolean coversOfficialClasses(JsonNode root) {
        if (classes.isEmpty()) {
            return true;
        }
        JsonNode unionClasses = root.get("classes");
        for (String className : classes.keySet()) {
            JsonNode unionClass = unionClasses.get(className);
            if (unionClass == null || !unionClass.isObject()) {
                return false;
            }
            JsonNode levels = unionClass.get("levels");
            if (levels == null || !levels.isObject()) {
                return false;
            }
            for (int level = 0; level <= MAX_LEVEL; level++) {
                if (!levels.has(String.valueOf(level))) {
                    return false;
                }
            }
        }
        return true;
    }

    private boolean isValidUnion11Source(JsonNode source) {
        if (source == null || !source.isObject()) {
            return false;
        }
        // book/chunk_id 键必须存在（值允许 null）；source/matched_by 必须非空白
        if (!source.has("book") || !source.has("chunk_id")) {
            return false;
        }
        String sourceKind = textOrNull(source.get("source"));
        String matchedBy = textOrNull(source.get("matched_by"));
        if (sourceKind == null || sourceKind.isBlank()
                || matchedBy == null || matchedBy.isBlank()) {
            return false;
        }
        // 派生来源 chunk_id 必须非空白（官方来源允许显式 null，但键必须存在）
        if ("derived".equals(sourceKind)) {
            String chunkId = textOrNull(source.get("chunk_id"));
            if (chunkId == null || chunkId.isBlank()) {
                return false;
            }
        }
        return true;
    }

    /** 文本字段取值：缺失/非文本节点返回 null */
    private String textOrNull(JsonNode node) {
        return node == null || !node.isTextual() ? null : node.asText();
    }

    /** union 产物是否加载成功（工具说明/测试口径用） */
    public boolean isUnionAvailable() {
        return unionAvailable;
    }

    /** union 是否走 1.1 折叠直读路径（false=1.0 兼容路径或不可用） */
    public boolean isUnionFoldedPath() {
        return unionFoldedPath;
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

    /**
     * 单职业单环的展示条目序列（levelOverview/levelTotal/formatLevel/分页
     * 共用同一份，F-025 §4.2）：
     * union 1.1 = 数据侧已折叠的完整条目序列；union 1.0 = 官方 + derived；
     * union 不可用 = 官方。
     */
    private List<DisplayEntry> levelEntries(String className, int level) {
        List<DisplayEntry> result = new ArrayList<>();
        if (!unionFoldedPath) {
            SpellList list = classes.get(className);
            if (list != null) {
                for (SpellListEntry e : list.levels().getOrDefault(String.valueOf(level), List.of())) {
                    result.add(new DisplayEntry(e.cn(), e.en(),
                            e.book() == null || e.book().isBlank() ? List.of() : List.of(e.book()),
                            false));
                }
            }
            for (UnionEntry e : unionDerived.getOrDefault(className, Map.of())
                    .getOrDefault(String.valueOf(level), List.of())) {
                result.add(toDisplayEntry(e));
            }
            return result;
        }
        for (UnionEntry e : unionFolded.getOrDefault(className, Map.of())
                .getOrDefault(String.valueOf(level), List.of())) {
            result.add(toDisplayEntry(e));
        }
        return result;
    }

    /** union 条目 → 展示条目：书缩写取 sources 全部非空 book 的保序去重，派生标记随主来源 */
    private DisplayEntry toDisplayEntry(UnionEntry e) {
        List<String> books = new ArrayList<>();
        if (e.sources() != null) {
            for (UnionSource s : e.sources()) {
                if (s.book() != null && !s.book().isBlank() && !books.contains(s.book())) {
                    books.add(s.book());
                }
            }
        }
        if (books.isEmpty() && e.book() != null && !e.book().isBlank()) {
            books.add(e.book());
        }
        return new DisplayEntry(e.cn(), e.en(), books, "derived".equals(e.source()));
    }

    /** 单职业全环条目总数（union 感知口径，概览头用） */
    private long totalEntries(String className) {
        long total = 0;
        for (int lv = 0; lv <= MAX_LEVEL; lv++) {
            total += levelEntries(className, lv).size();
        }
        return total;
    }

    /** 首个非空环级（概览提示示例用；全空返回 0） */
    private int firstNonEmptyLevel(String className) {
        for (int lv = 0; lv <= MAX_LEVEL; lv++) {
            if (!levelEntries(className, lv).isEmpty()) {
                return lv;
            }
        }
        return 0;
    }

    /** 全职业全环条目总数（加载日志用；union 加载前调用，官方口径） */
    private long totalAll() {
        return classes.values().stream().mapToLong(list -> list.levels().values().stream()
                .mapToLong(List::size).sum()).sum();
    }

    /** 单条目紧凑行：`序号. 中文名（English） [书1/书2]`，主来源 derived 时带〔派生〕 */
    private String buildLine(int index, DisplayEntry entry) {
        StringBuilder line = new StringBuilder(index + ". ").append(entry.cn());
        if (entry.en() != null && !entry.en().isBlank()) {
            line.append('（').append(entry.en()).append('）');
        }
        if (!entry.books().isEmpty()) {
            line.append(" [").append(String.join("/", entry.books())).append(']');
        }
        if (entry.derived()) {
            line.append("〔派生〕");
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

    // ---------- spell_lists_union.json 数据模型（B1 schema 1.0 → F-025 schema 1.1） ----------

    /** union 顶层：1.0 可省略 version（按 1.0 兼容处理）；scope_note/excluded_classes 忽略 */
    @JsonIgnoreProperties(ignoreUnknown = true)
    record UnionFile(
            String version,
            @JsonProperty("classes") Map<String, UnionClass> classes) {

        UnionFile {
            classes = classes == null ? Map.of() : classes;
        }
    }

    /** union 单职业：levels 结构与官方清单同键（"0"~"9"） */
    @JsonIgnoreProperties(ignoreUnknown = true)
    record UnionClass(@JsonProperty("levels") Map<String, List<UnionEntry>> levels) {

        UnionClass {
            levels = levels == null ? Map.of() : levels;
        }
    }

    /**
     * union 单条目：1.0 为 derived 候选（source/level_evidence/matched_by）；
     * 1.1 顶层 book/chunk_id/source 镜像主来源，sources 为完整去重来源列表
     * （首个即主来源，official_list 主条目的 matched_by 由 source 记录）。
     */
    @JsonIgnoreProperties(ignoreUnknown = true)
    record UnionEntry(
            String cn,
            String en,
            String book,
            @JsonProperty("chunk_id") String chunkId,
            String source,
            @JsonProperty("level_evidence") String levelEvidence,
            @JsonProperty("matched_by") String matchedBy,
            List<UnionSource> sources) {

        UnionEntry {
            cn = cn == null ? "" : cn;
        }
    }

    /** union 1.1 单个来源：book/chunk_id/source/matched_by 必填（chunk_id 仅官方可为 null） */
    @JsonIgnoreProperties(ignoreUnknown = true)
    record UnionSource(
            String book,
            @JsonProperty("chunk_id") String chunkId,
            String source,
            @JsonProperty("level_evidence") String levelEvidence,
            @JsonProperty("matched_by") String matchedBy) {
    }

    /** 展示层条目：清单行渲染的统一形态（书缩写已保序去重，派生标记随主来源） */
    private record DisplayEntry(String cn, String en, List<String> books, boolean derived) {
    }
}
