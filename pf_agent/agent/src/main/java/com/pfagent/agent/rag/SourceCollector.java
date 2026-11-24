package com.pfagent.agent.rag;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.document.Document;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Objects;

/**
 * 请求级来源收集器（设计 §6 / SP4 D1）
 *
 * 工具在手动工具循环里把检索命中的 Document 返回给 LLM（紧凑摘要），但
 * ChatResponse.sources（前端来源折叠区）需要完整 Document 供溯源。本类用
 * ThreadLocal 收集本请求所有工具命中的来源：
 *   - ChatService 每请求入口 begin()，出口 drain() 取走并清空
 *   - 每个 @Tool 命中时 add(docs)，多步查询的来源全部汇聚
 *   - add() 即按去重键分配编号（SP4 D1）：新键递增、重复键返回既有编号，
 *     编号 = 去重后数组下标 + 1，与 drain() 返回序天然对齐
 *   - drain() 取走全部唯一来源（LinkedHashMap 保插入序 = 编号序）
 *   - gap 标记与来源同生命周期：reportDataGap 工具 markGapReported()，
 *     ChatService 出口读 wasGapReported() 决定 ChatResponse.gapReported
 *
 * ThreadLocal 而非实例字段：ChatService 是单例，并发请求必须互不污染。
 *
 * F-016 请求级护栏：addWithLimit() 在分配编号前检查本请求去重后来源数与正文
 * UTF-8 字节合计。超限条目既不编号也不进 sources（由调用方据 AddResult.idsByInput()
 * 的 null 位同步裁剪工具输出）；护栏截断不是数据缺口，不触碰 gapReported。
 *
 * 生产工具路径（RetrievalTools，Task 14）已统一使用 {@link #addWithLimit(List)}，
 * 并按 AddResult 裁剪工具输出；{@link #add(List)} 仅保留给历史调用方。
 */
@Component
public class SourceCollector {

    private static final Logger log = LoggerFactory.getLogger(SourceCollector.class);

    /** F-016 默认请求级来源上限：数量（去重后）。 */
    public static final int DEFAULT_MAX_DOCS = 50;

    /** F-016 默认请求级来源上限：正文 UTF-8 字节合计（2MB）。 */
    public static final long DEFAULT_MAX_SOURCES_BYTES = 2L * 1024 * 1024;

    /** 去重键 → Document：key 去重语义见 dedupKey()，value 保留首次命中 */
    private final ThreadLocal<LinkedHashMap<String, Document>> current = new ThreadLocal<>();
    /** 本请求已保留来源的正文 UTF-8 字节合计（与 current 同生命周期） */
    private final ThreadLocal<Long> retainedBytes = new ThreadLocal<>();
    private final ThreadLocal<Boolean> gapReported = new ThreadLocal<>();

    /** addWithLimit(List) 使用的默认上限，由配置 pf.search.max-sources-* 注入 */
    private final int defaultMaxDocs;
    private final long defaultMaxBytes;

    @Autowired
    public SourceCollector(
            @Value("${pf.search.max-sources-per-request:50}") int defaultMaxDocs,
            @Value("${pf.search.max-sources-bytes:2097152}") long defaultMaxBytes) {
        this.defaultMaxDocs = defaultMaxDocs;
        this.defaultMaxBytes = defaultMaxBytes;
    }

    /** 单元测试/非 Spring 场景入口：与配置缺省值一致（50 条 / 2MB）。 */
    public SourceCollector() {
        this(DEFAULT_MAX_DOCS, DEFAULT_MAX_SOURCES_BYTES);
    }

    /** 请求入口：初始化本请求的收集状态 */
    public void begin() {
        current.set(new LinkedHashMap<>());
        retainedBytes.set(0L);
        gapReported.set(false);
    }

    /**
     * 一次 add 的结果（F-016）。
     *
     * @param acceptedDocs   本次调用新收下的来源（按编号序；重复键不计入）
     * @param idsByInput     与入参等长的编号视图，被护栏拒绝的位置为 null；
     *                       重复键位置返回既有编号。调用方据此逐条裁剪工具输出
     * @param droppedCount   本次调用被拒入参数，= droppedByCount + droppedByBytes
     * @param droppedByCount 因数量上限被拒的入参数（重复键不计）
     * @param droppedByBytes 因正文 UTF-8 字节超出剩余预算被拒的入参数
     * @param retainedTotal  本请求护栏下已保留的来源总数（截至本次调用）
     * @param truncated      本次调用是否发生拒绝，供调用方输出收窄提示
     */
    public record AddResult(List<Document> acceptedDocs, List<Integer> idsByInput,
                            int droppedCount, int droppedByCount, int droppedByBytes,
                            int retainedTotal, boolean truncated) {

        public AddResult {
            acceptedDocs = List.copyOf(acceptedDocs);
            idsByInput = Collections.unmodifiableList(new ArrayList<>(idsByInput));
        }

        /** 兼容视图：过滤掉被拒位置的 null，只保留已分配编号（按入参序）。 */
        public List<Integer> ids() {
            return idsByInput.stream().filter(Objects::nonNull).toList();
        }
    }

    /**
     * 工具命中时收集来源，并返回每个入参 doc 的来源编号（SP4 D1）。
     *
     * 兼容入口：委托 {@link #addWithLimit(List, int, long)} 但不设数量/体积上限，
     * 保持 F-016 接入前调用方的既有行为（宽结果仍全量入 sources）。
     * 生产工具路径已切换到 {@link #addWithLimit(List)} 并据 AddResult 裁剪输出；
     * 新代码不得再使用本入口，否则会产生未受护栏约束的来源。
     */
    @Deprecated(forRemoval = true)
    public List<Integer> add(List<Document> docs) {
        return addWithLimit(docs, 0, 0).ids();
    }

    /**
     * 只读预判：在当前请求状态下 {@link #addWithLimit(List)} 是否会收下该 doc。
     * 不分配编号、不写 map、不改 retainedBytes，仅供工具层做字符预算估算。
     *
     * 判定顺序与 addWithLimit 一致：未 begin 时 addWithLimit 为安全空操作，预判 true；
     * 去重键已存在 → true（复用既有编号）；数量或字节超出剩余预算 → false。
     */
    boolean canRetain(Document doc) {
        LinkedHashMap<String, Document> map = current.get();
        if (map == null) {
            return true;
        }
        if (doc == null) {
            return false;
        }
        String key = dedupKey(doc);
        if (map.containsKey(key)) {
            return true;
        }
        if (defaultMaxDocs > 0 && map.size() >= defaultMaxDocs) {
            return false;
        }
        Long stored = retainedBytes.get();
        long usedBytes = stored == null ? 0L : stored;
        long docBytes = utf8Length(doc.getText());
        return defaultMaxBytes <= 0 || docBytes <= defaultMaxBytes - usedBytes;
    }

    /**
     * 按配置的 F-016 默认上限收集来源（pf.search.max-sources-per-request /
     * pf.search.max-sources-bytes，缺省 50 条 / 2MB UTF-8 字节）。
     * 语义见 {@link #addWithLimit(List, int, long)}。
     */
    public AddResult addWithLimit(List<Document> docs) {
        return addWithLimit(docs, defaultMaxDocs, defaultMaxBytes);
    }

    /**
     * 工具命中时按请求级护栏收集来源，并返回本次调用的编号与拒绝计数（F-016）。
     *
     * 编号 1-based、按去重键在请求内的首次出现序连续分配：新键取当前 map 大小 + 1，
     * 重复键（去重键已存在）返回既有编号、既不占名额也不计字节。
     * 新键先过护栏再审编号：数量达到 maxDocs 或正文 UTF-8 字节超出剩余预算的 doc
     * 直接拒绝——不编号、不进入 sources、不改变已有编号，后续较小正文仍可继续占用
     * 剩余预算。maxDocs 或 maxBytes 为 0/负数表示该维度不限。
     *
     * docs 为 null、空或未 begin 时安全忽略并返回空结果。护栏截断不是数据缺口，
     * 不置 gapReported。
     */
    public AddResult addWithLimit(List<Document> docs, int maxDocs, long maxBytes) {
        LinkedHashMap<String, Document> map = current.get();
        if (map == null) {
            return new AddResult(List.of(), List.of(), 0, 0, 0, 0, false);
        }
        if (docs == null || docs.isEmpty()) {
            return new AddResult(List.of(), List.of(), 0, 0, 0, map.size(), false);
        }
        Long stored = retainedBytes.get();
        long usedBytes = stored == null ? 0L : stored;
        List<Document> accepted = new ArrayList<>();
        List<Integer> idsByInput = new ArrayList<>(docs.size());
        int droppedByCount = 0;
        int droppedByBytes = 0;
        for (Document doc : docs) {
            String key = dedupKey(doc);
            if (map.containsKey(key)) {
                idsByInput.add(numberOf(map, key)); // 重复键：返回既有编号，不占名额
                continue;
            }
            if (maxDocs > 0 && map.size() >= maxDocs) {
                droppedByCount++;
                idsByInput.add(null);
                continue;
            }
            long docBytes = utf8Length(doc.getText());
            if (maxBytes > 0 && docBytes > maxBytes - usedBytes) {
                droppedByBytes++;
                idsByInput.add(null);
                continue;
            }
            map.put(key, doc);               // 新键：put 后 size 即其编号
            usedBytes += docBytes;
            accepted.add(doc);
            idsByInput.add(map.size());
        }
        retainedBytes.set(usedBytes);
        int dropped = droppedByCount + droppedByBytes;
        if (dropped > 0) {
            log.warn("来源护栏截断：本次丢弃 {} 条（数量 {} / 体积 {}），本请求已保留 {} 条，"
                    + "maxDocs={}, maxBytes={}", dropped, droppedByCount, droppedByBytes,
                    map.size(), maxDocs, maxBytes);
        }
        return new AddResult(accepted, idsByInput, dropped, droppedByCount, droppedByBytes,
                map.size(), dropped > 0);
    }

    /**
     * 请求出口：取走全部唯一来源（插入序 = 编号序）并清空请求状态。
     * 未 begin（如异常路径）时返回空列表。
     *
     * AKN-008：原按 doc_id 去重，但 doc_id 是**页面级**（StandardChunk 的
     * doc_id 为 source 页路径，如 page_234 / 核心职业/盗贼/page_49.md），同页多 chunk
     * 只保留先到者——vectorSearch 先返回同页邻居，searchByMetadata title 过滤精确命中的
     * 锚点被吞，溯源判定（按 chunk_id）落空。改用 chunk_id（chunk 级，唯一）去重；
     * 缺 chunk_id 的 doc 兜底 doc_id 键（避免 null 合并，仅防御手工构造 doc）。
     */
    public List<Document> drain() {
        LinkedHashMap<String, Document> map = current.get();
        if (map == null) {
            return List.of();
        }
        List<Document> result = new ArrayList<>(map.values());
        current.remove();
        retainedBytes.remove();
        gapReported.remove();
        return result;
    }

    /** 标记本请求存在数据缺口（reportDataGap 工具调用） */
    public void markGapReported() {
        gapReported.set(true);
    }

    /** 本请求是否记录了数据缺口 */
    public boolean wasGapReported() {
        return Boolean.TRUE.equals(gapReported.get());
    }

    /**
     * 清空请求状态（异常路径兜底，防止 ThreadLocal 残留污染线程复用）。
     * drain() 已清空，此处幂等。
     */
    public void clear() {
        current.remove();
        retainedBytes.remove();
        gapReported.remove();
    }

    /** 正文 UTF-8 字节数；text 为 null 时计 0（不因缺失正文破坏护栏）。 */
    private long utf8Length(String text) {
        return text == null ? 0L : text.getBytes(StandardCharsets.UTF_8).length;
    }

    /**
     * 来源去重键：优先 chunk_id（chunk 级唯一），缺 chunk_id 兜底 "doc:doc_id"。
     * 语义与 AKN-008 定稿的 drain 去重键逐字一致——编号与去重必须同一把尺，否则
     * 编号错位会破坏「编号 N ↔ sources 第 N 条」的对齐（SP4 D7）。
     */
    private String dedupKey(Document doc) {
        Object chunkId = doc.getMetadata().get("chunk_id");
        if (chunkId == null || chunkId.toString().isBlank()) {
            Object docId = doc.getMetadata().get("doc_id");
            return "doc:" + (docId == null ? "" : docId);
        }
        return chunkId.toString();
    }

    /**
     * 查既有编号：key 在 LinkedHashMap 中的插入位次（1-based）。
     * 请求级来源数很小（通常个位数），遍历 keySet 换取单结构存储——不另建编号索引，
     * 从根上避免「编号表与去重 map 不同步」这类双结构腐化。
     */
    private int numberOf(LinkedHashMap<String, Document> map, String key) {
        int n = 1;
        for (String existing : map.keySet()) {
            if (existing.equals(key)) {
                return n;
            }
            n++;
        }
        throw new IllegalStateException("来源编号查询失败，去重键未注册: " + key);
    }
}
