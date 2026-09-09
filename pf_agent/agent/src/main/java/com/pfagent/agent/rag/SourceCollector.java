package com.pfagent.agent.rag;

import org.springframework.ai.document.Document;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;

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
 */
@Component
public class SourceCollector {

    /** 去重键 → Document：key 去重语义见 dedupKey()，value 保留首次命中 */
    private final ThreadLocal<LinkedHashMap<String, Document>> current = new ThreadLocal<>();
    private final ThreadLocal<Boolean> gapReported = new ThreadLocal<>();

    /** 请求入口：初始化本请求的收集状态 */
    public void begin() {
        current.set(new LinkedHashMap<>());
        gapReported.set(false);
    }

    /**
     * 工具命中时收集来源，并返回每个入参 doc 的来源编号（SP4 D1）。
     *
     * 编号 1-based、按去重键在请求内的首次出现序分配：新键取当前 map 大小 + 1，
     * 重复键（去重键已存在）返回既有编号、不重复收集。返回列表与入参等长、下标一一对应。
     * docs 为 null、空或未 begin 时安全忽略并返回空列表。
     */
    public List<Integer> add(List<Document> docs) {
        LinkedHashMap<String, Document> map = current.get();
        if (docs == null || docs.isEmpty() || map == null) {
            return List.of();
        }
        List<Integer> ids = new ArrayList<>(docs.size());
        for (Document doc : docs) {
            String key = dedupKey(doc);
            if (!map.containsKey(key)) {
                map.put(key, doc);          // 新键：put 后 size 即其编号
                ids.add(map.size());
            } else {
                ids.add(numberOf(map, key)); // 重复键：返回既有编号
            }
        }
        return ids;
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
        gapReported.remove();
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
