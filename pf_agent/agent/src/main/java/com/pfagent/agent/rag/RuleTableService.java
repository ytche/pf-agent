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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 规则内嵌表格查表服务（KN221，spec D8~D11）
 *
 * 加载数据侧 rule_table_export.py 产出的 rule_tables.json（与规则 chunk 的 4 个
 * 表格 metadata 键同源于 vectorizer/rule_tables.py）。规格：
 *  - 顶层 tables 为对象字典，键 = table_id（`{chunk_id}#t{index}`，index 1-based）；
 *  - 每条含 layout（standard / flattened / no_separator）、caption/title、headers、
 *    rows、header_inferred、row_count、line_start/line_end、raw_lines；
 *  - flattened 的 headers/rows 为空，只承诺原文行，不伪造列级结构；
 *  - 少量表 title 为空串（空壳/断行表），只能按 table_id / chunk_id 查询。
 *
 * 查询口径：table 支持 table_id / chunk_id / 表名（title 或 caption），归一化全半角
 * 与空白后先精确、再子串模糊；模糊多命中返回全部候选由工具显式要求消歧，绝不猜。
 * 行匹配（D9）：归一全半角并去「级/第/行」后，先比首个非空单元格、再比任意单元格；
 * flattened 表按原文行号/原文内容匹配并注明降级。
 *
 * 溯源（D11）：优先 SearchService.getByChunkId("rule", chunk_id) 点查真实 chunk 交
 * SourceCollector；点查未命中（向量库版本错位等）降级合成 Document 并 warn，
 * 对齐 ClassTableService 先例，保证 [#N] 不缺席。
 *
 * 产物缺失/解析失败时 available=false，不炸启动。
 */
@Component
public class RuleTableService {

    private static final Logger log = LoggerFactory.getLogger(RuleTableService.class);

    static final String LAYOUT_STANDARD = "standard";
    static final String LAYOUT_FLATTENED = "flattened";
    static final String LAYOUT_NO_SEPARATOR = "no_separator";

    /** 无 row 时最多展示的数据行数（D10，控制上下文体积） */
    static final int MAX_ROWS = 20;
    /** 歧义候选最多展示数 */
    static final int MAX_CANDIDATES = 20;

    @Value("${pf.rule-tables.file-path:../../pf_data/phase1/vectorizer/output/规则/rule_tables.json}")
    private String filePath;

    @Autowired(required = false)
    private SearchService searchService;

    private final ObjectMapper objectMapper = new ObjectMapper();

    /** table_id → 表（@PostConstruct 加载，加载前/失败为空） */
    private Map<String, RuleTable> tables = Map.of();
    /** 文件顺序的表列表（候选展示与候选顺序稳定） */
    private List<RuleTable> ordered = List.of();
    private boolean available;

    /** 产物是否加载成功（文件存在且解析通过） */
    public boolean isAvailable() {
        return available;
    }

    /** 已收录表数（加载前/失败为 0） */
    public int tableCount() {
        return ordered.size();
    }

    /** 已收录表（文件顺序，只读；供测试/诊断） */
    public List<RuleTable> allTables() {
        return ordered;
    }

    /**
     * 按 table_id / chunk_id / 表名（title 或 caption）解析表。
     *
     * 优先级：table_id 精确 > chunk_id 精确（同 chunk 多表全部返回）> 表名精确
     * （归一后）> 表名子串模糊（双向包含，query 长度 ≥2）。返回空列表 = 未收录；
     * 返回多项 = 歧义，调用方须让 LLM 用 table_id/chunk_id 消歧，不得猜第一项。
     */
    public List<RuleTable> find(String table) {
        if (table == null) {
            return List.of();
        }
        String key = table.trim();
        if (key.isEmpty()) {
            return List.of();
        }
        RuleTable byTableId = tables.get(key);
        if (byTableId != null) {
            return List.of(byTableId);
        }
        List<RuleTable> byChunkId = ordered.stream()
                .filter(t -> key.equals(t.chunkId()))
                .toList();
        if (!byChunkId.isEmpty()) {
            return byChunkId;
        }
        String norm = normalizeText(key);
        if (norm.isEmpty()) {
            return List.of();
        }
        List<RuleTable> exactTitle = ordered.stream()
                .filter(t -> norm.equals(normalizeText(t.title()))
                        || norm.equals(normalizeText(t.caption())))
                .toList();
        if (!exactTitle.isEmpty()) {
            return exactTitle;
        }
        if (norm.length() < 2) {
            return List.of();
        }
        return ordered.stream().filter(t -> fuzzyTitleMatch(t, norm)).toList();
    }

    /**
     * 单表结果格式化（D10）：standard/no_separator 返回表头 + 行（有 row 时只返回命中行，
     * 无 row 时最多 20 行并提示总行数）；flattened 只返回原文行并显式标注降级。
     * 行未命中如实说明并给可用行键，不编造数值。
     */
    public String formatTable(RuleTable table, String row) {
        StringBuilder sb = new StringBuilder();
        sb.append("表：").append(displayName(table))
                .append("（layout=").append(table.layout())
                .append("，table_id=").append(table.tableId())
                .append("，chunk_id=").append(table.chunkId())
                .append("，共 ").append(table.rowCount()).append(" 行）\n");
        if (LAYOUT_FLATTENED.equals(table.layout())) {
            return formatFlattened(table, row, sb);
        }
        return formatStructured(table, row, sb);
    }

    /** 歧义候选清单：表名/layout/行数/table_id/chunk_id，提示用 table_id 或 chunk_id 消歧 */
    public String formatCandidates(String query, List<RuleTable> candidates) {
        StringBuilder sb = new StringBuilder("表名「").append(query.trim()).append("」命中 ")
                .append(candidates.size()).append(" 张表，无法确定唯一目标。请改用 table_id 或 chunk_id 精确定位：\n");
        int shown = Math.min(candidates.size(), MAX_CANDIDATES);
        for (int i = 0; i < shown; i++) {
            RuleTable t = candidates.get(i);
            sb.append(i + 1).append(". ").append(displayName(t))
                    .append(" | layout:").append(t.layout())
                    .append(" | ").append(t.rowCount()).append(" 行")
                    .append(" | table_id:").append(t.tableId())
                    .append(" | chunk_id:").append(t.chunkId()).append('\n');
        }
        if (candidates.size() > shown) {
            sb.append("…（另有 ").append(candidates.size() - shown)
                    .append(" 张未展示，请用更具体的表名或 chunk_id 收窄）\n");
        }
        return sb.toString();
    }

    /**
     * 溯源 Document：优先 SearchService.getByChunkId("rule", chunk_id) 点查真实 chunk；
     * 未命中（向量库版本错位等）降级合成 Document（title/chunk_id/doc_id/table_id 齐）
     * 并 warn，保证 [#N] 不缺席。
     */
    public Document provenanceDocument(RuleTable table) {
        String title = displayName(table);
        if (searchService != null && table.chunkId() != null) {
            Document doc = searchService.getByChunkId("rule", table.chunkId());
            if (doc != null) {
                return doc;
            }
            log.warn("规则表格 source chunk_id 点查未命中（table_id={}，chunk_id={}），"
                    + "疑似 rule_tables.json 与向量库版本错位，降级合成溯源 Document。",
                    table.tableId(), table.chunkId());
        }
        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("title", title);
        if (table.chunkId() != null) {
            meta.put("chunk_id", table.chunkId());
        }
        if (table.docId() != null) {
            meta.put("doc_id", table.docId());
        }
        meta.put("table_id", table.tableId());
        String text;
        if (table.rawLines().isEmpty()) {
            text = title;
        } else {
            text = String.join("\n", table.rawLines())
                    + "\n（数据侧 rule_tables.json 预整理）";
        }
        return Document.builder().text(text).metadata(meta).build();
    }

    // ---------- 格式化内部实现 ----------

    /** standard / no_separator：表头 + 行（行号按表内 1-based 顺序） */
    private String formatStructured(RuleTable table, String row, StringBuilder sb) {
        if (!table.headers().isEmpty()) {
            sb.append("表头: ").append(joinCells(table.headers()));
            if (table.headerInferred()) {
                sb.append("（无分隔行，表头按首行推断，需按原文审慎解释）");
            }
            sb.append('\n');
        }
        if (row == null || row.isBlank()) {
            appendRows(table, sb, table.rows(), 1);
            return sb.toString();
        }
        List<RowHit> hits = matchRows(table.rows(), row);
        if (hits.isEmpty()) {
            sb.append("未找到与 row=\"").append(row.trim()).append("\" 匹配的行"
                    + "（支持 5 / 5级 / 第5行；先匹配首个非空单元格，再匹配任意单元格）。\n");
            appendAvailableKeys(table, sb);
            return sb.toString();
        }
        sb.append("命中 ").append(hits.size()).append(" 行：\n");
        int shown = Math.min(hits.size(), MAX_ROWS);
        for (int i = 0; i < shown; i++) {
            RowHit hit = hits.get(i);
            sb.append("行 ").append(hit.index()).append(": ")
                    .append(joinCells(hit.cells())).append('\n');
        }
        if (hits.size() > shown) {
            sb.append("…（共命中 ").append(hits.size()).append(" 行，仅展示前 ")
                    .append(shown).append(" 行）\n");
        }
        return sb.toString();
    }

    /** 无 row 时按上限展示数据行，并在截断时提示总行数与取行方式 */
    private void appendRows(RuleTable table, StringBuilder sb, List<List<String>> rows, int startIndex) {
        if (rows.isEmpty()) {
            sb.append("（无数据行，仅表头；原文行可用 chunk_id 结合 getEntryById 查看）\n");
            return;
        }
        int shown = Math.min(rows.size(), MAX_ROWS);
        for (int i = 0; i < shown; i++) {
            sb.append("行 ").append(startIndex + i).append(": ")
                    .append(joinCells(rows.get(i))).append('\n');
        }
        if (rows.size() > shown) {
            sb.append("…（共 ").append(table.rowCount()).append(" 行，仅展示前 ")
                    .append(shown).append(" 行；可用 row 参数按首列/单元格值取行，如 row=\"5\"）\n");
        }
    }

    /** 行未命中时的可用行键：前 20 行首列值，帮助 LLM 下一轮自纠 */
    private void appendAvailableKeys(RuleTable table, StringBuilder sb) {
        List<String> keys = new ArrayList<>();
        for (List<String> cells : table.rows()) {
            if (keys.size() >= MAX_ROWS) {
                break;
            }
            String first = firstNonEmpty(cells);
            keys.add(first);
        }
        if (!keys.isEmpty()) {
            sb.append("可用行键（前 ").append(keys.size()).append(" 行首列）: ")
                    .append(String.join("、", keys)).append('\n');
        }
    }

    /** flattened：只返回原文行并标降级；row 为数字时按表内行号取，否则按原文内容匹配 */
    private String formatFlattened(RuleTable table, String row, StringBuilder sb) {
        List<String> raw = table.rawLines();
        sb.append("布局说明: flattened —— 分隔行位置不规范，无法可靠还原列结构，"
                + "以下为原文行（不承诺列级对应，请按原文引用）。\n");
        if (raw.isEmpty()) {
            sb.append("（该表无原文行可展示）\n");
            return sb.toString();
        }
        if (row == null || row.isBlank()) {
            int shown = Math.min(raw.size(), MAX_ROWS);
            for (int i = 0; i < shown; i++) {
                sb.append("行 ").append(i + 1).append(": ").append(raw.get(i)).append('\n');
            }
            if (raw.size() > shown) {
                sb.append("…（原文共 ").append(raw.size()).append(" 行，仅展示前 ")
                        .append(shown).append(" 行）\n");
            }
            return sb.toString();
        }
        String key = row.trim();
        if (isDigits(normalizeRowKey(key))) {
            int index = Integer.parseInt(normalizeRowKey(key));
            if (index >= 1 && index <= raw.size()) {
                sb.append("行 ").append(index).append(": ").append(raw.get(index - 1)).append('\n');
                return sb.toString();
            }
            sb.append("第 ").append(index).append(" 行超出该表原文行数（共 ")
                    .append(raw.size()).append(" 行）。\n");
            return sb.toString();
        }
        String norm = normalizeText(key);
        List<String> matched = new ArrayList<>();
        for (String line : raw) {
            if (normalizeText(line).contains(norm)) {
                matched.add(line);
                if (matched.size() >= MAX_ROWS) {
                    break;
                }
            }
        }
        if (matched.isEmpty()) {
            sb.append("未在原文行中找到与 row=\"").append(key).append("\" 匹配的内容"
                    + "（flattened 表按原文行号或原文内容匹配）。\n");
            return sb.toString();
        }
        sb.append("原文匹配 ").append(matched.size()).append(" 行：\n");
        for (String line : matched) {
            sb.append("- ").append(line).append('\n');
        }
        return sb.toString();
    }

    /** 结构化表行匹配（D9）：首列精确 > 任意单元格精确 > 任意单元格子串（非数字键） */
    private List<RowHit> matchRows(List<List<String>> rows, String row) {
        String key = normalizeRowKey(row);
        List<RowHit> hits = new ArrayList<>();
        if (key.isEmpty()) {
            return hits;
        }
        for (int i = 0; i < rows.size(); i++) {
            List<String> cells = rows.get(i);
            String first = firstNonEmpty(cells);
            if (!first.isEmpty() && key.equals(normalizeRowKey(first))) {
                hits.add(new RowHit(i + 1, cells));
            }
        }
        if (!hits.isEmpty()) {
            return hits;
        }
        for (int i = 0; i < rows.size(); i++) {
            List<String> cells = rows.get(i);
            if (cells.stream().anyMatch(c -> key.equals(normalizeRowKey(c)))) {
                hits.add(new RowHit(i + 1, cells));
            }
        }
        if (!hits.isEmpty() || isDigits(key)) {
            return hits;
        }
        String norm = normalizeText(key);
        for (int i = 0; i < rows.size(); i++) {
            List<String> cells = rows.get(i);
            if (cells.stream().anyMatch(c -> normalizeText(c).contains(norm))) {
                hits.add(new RowHit(i + 1, cells));
            }
        }
        return hits;
    }

    private boolean fuzzyTitleMatch(RuleTable table, String norm) {
        String title = normalizeText(table.title());
        String caption = normalizeText(table.caption());
        return (!title.isEmpty() && (title.contains(norm) || norm.contains(title)))
                || (!caption.isEmpty() && (caption.contains(norm) || norm.contains(caption)));
    }

    /** 表名展示：title > caption > (无表题)（空壳表只有 table_id 可定位） */
    private String displayName(RuleTable table) {
        if (table.title() != null && !table.title().isBlank()) {
            return table.title();
        }
        if (table.caption() != null && !table.caption().isBlank()) {
            return table.caption();
        }
        return "(无表题)";
    }

    private static String joinCells(List<String> cells) {
        return String.join(" | ", cells);
    }

    private static String firstNonEmpty(List<String> cells) {
        for (String cell : cells) {
            if (cell != null && !cell.isBlank()) {
                return cell;
            }
        }
        return "";
    }

    /** 全半角 + 大小写 + 空白归一（ASCII 全角区与表意空格） */
    static String normalizeText(String text) {
        if (text == null) {
            return "";
        }
        StringBuilder sb = new StringBuilder(text.length());
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if (ch == '\u3000') {
                continue;
            }
            if (ch >= '\uFF01' && ch <= '\uFF5E') {
                ch = (char) (ch - 0xFEE0);
            }
            if (Character.isWhitespace(ch)) {
                continue;
            }
            sb.append(Character.toLowerCase(ch));
        }
        return sb.toString();
    }

    /** 行键归一：在文本归一基础上去掉「级/第/行」（兼容 5 / 5级 / 第5行） */
    static String normalizeRowKey(String text) {
        return normalizeText(text).replace("级", "").replace("第", "").replace("行", "");
    }

    private static boolean isDigits(String text) {
        if (text == null || text.isEmpty()) {
            return false;
        }
        for (int i = 0; i < text.length(); i++) {
            if (!Character.isDigit(text.charAt(i))) {
                return false;
            }
        }
        return true;
    }

    /** 加载 rule_tables.json 进内存；缺失/解析失败 → 降级 available=false，不炸启动 */
    @PostConstruct
    void load() {
        Path path = Path.of(filePath);
        if (!Files.exists(path)) {
            log.warn("rule_tables.json 不存在（{}），规则表格工具将降级不可用。", path.toAbsolutePath());
            return;
        }
        try {
            RuleTableFile file = objectMapper.readValue(path.toFile(), RuleTableFile.class);
            Map<String, RuleTable> loaded = file.tables() == null ? Map.of() : file.tables();
            this.tables = loaded;
            this.ordered = List.copyOf(loaded.values());
            this.available = true;
            Map<String, Integer> byLayout = new LinkedHashMap<>();
            for (RuleTable table : ordered) {
                byLayout.merge(table.layout(), 1, Integer::sum);
            }
            log.info("rule_tables.json 加载完成：{} 张表（按 layout {}，{}）",
                    ordered.size(), byLayout, path.getFileName());
        } catch (IOException e) {
            log.error("rule_tables.json 解析失败（{}），规则表格工具将降级不可用。", path.toAbsolutePath(), e);
        }
    }

    // ---------- rule_tables.json 数据模型（snake_case JSON 键用 @JsonProperty 映射） ----------

    /** 顶层文件：version/table_id_index_base/tables；generated_at/counts 等忽略 */
    @JsonIgnoreProperties(ignoreUnknown = true)
    record RuleTableFile(
            String version,
            @JsonProperty("table_id_index_base") int tableIdIndexBase,
            @JsonProperty("tables") Map<String, RuleTable> tables) {
    }

    /** 单表：layout + 表题/表头/行 + 原文行与行号范围（结构见数据侧 Table.to_dict） */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record RuleTable(
            @JsonProperty("table_id") String tableId,
            @JsonProperty("chunk_id") String chunkId,
            @JsonProperty("doc_id") String docId,
            int index,
            String layout,
            String caption,
            String title,
            List<String> headers,
            List<List<String>> rows,
            @JsonProperty("header_inferred") boolean headerInferred,
            @JsonProperty("row_count") int rowCount,
            @JsonProperty("line_start") int lineStart,
            @JsonProperty("line_end") int lineEnd,
            @JsonProperty("raw_lines") List<String> rawLines) {

        public RuleTable {
            headers = headers == null ? List.of() : headers;
            rows = rows == null ? List.of() : rows;
            rawLines = rawLines == null ? List.of() : rawLines;
            caption = caption == null ? "" : caption;
            title = title == null ? "" : title;
        }
    }

    /** 行命中：表内 1-based 行号 + 单元格（保持原始空单元格位置，不压缩） */
    private record RowHit(int index, List<String> cells) {
    }
}
