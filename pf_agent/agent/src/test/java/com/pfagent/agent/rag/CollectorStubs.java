package com.pfagent.agent.rag;

import org.mockito.Mockito;
import org.springframework.ai.document.Document;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import static org.mockito.ArgumentMatchers.any;

/**
 * Task 14 测试辅助：为 mock 的 SourceCollector 提供 addWithLimit 桩。
 *
 * 生产路径统一走 {@link SourceCollector#addWithLimit(List)}，工具测试不再直接
 * stub 已废弃的 add()。默认桩把全部入参视为收下并顺序发号（1..n）。
 */
final class CollectorStubs {

    private CollectorStubs() {
    }

    /** 全部收下、按入参顺序发号 1..n（dropped=0） */
    static void stubAcceptAll(SourceCollector collector) {
        Mockito.lenient().when(collector.addWithLimit(any())).thenAnswer(invocation -> {
            List<Document> docs = invocation.getArgument(0);
            return result(docs, sequentialNumbers(docs == null ? 0 : docs.size()));
        });
    }

    /** 指定编号视图（与入参等长；不足补 null），用于模拟个别条目被护栏拒绝 */
    static void stubIds(SourceCollector collector, List<Integer> idsByInput) {
        Mockito.lenient().when(collector.addWithLimit(any())).thenAnswer(invocation -> {
            List<Document> docs = invocation.getArgument(0);
            return result(docs, idsByInput);
        });
    }

    /** 构造 AddResult：null 位置视为被拒，acceptedDocs 与 idsByInput 对齐 */
    static SourceCollector.AddResult result(List<Document> docs, List<Integer> idsByInput) {
        List<Document> safeDocs = docs == null ? List.of() : docs;
        List<Integer> ids = idsByInput == null ? List.of() : idsByInput;
        if (ids.isEmpty() && !safeDocs.isEmpty()) {
            // 显式空编号：模拟未收集（非护栏拒绝），不应触发 dropped 提示
            return new SourceCollector.AddResult(List.of(), List.of(), 0, 0, 0, 0, false);
        }
        List<Document> accepted = new ArrayList<>();
        List<Integer> view = new ArrayList<>(safeDocs.size());
        int dropped = 0;
        int retained = 0;
        for (int i = 0; i < safeDocs.size(); i++) {
            Integer id = i < ids.size() ? ids.get(i) : null;
            view.add(id);
            if (id == null) {
                dropped++;
            } else {
                accepted.add(safeDocs.get(i));
                retained = Math.max(retained, id);
            }
        }
        return new SourceCollector.AddResult(accepted, view, dropped, dropped, 0, retained, dropped > 0);
    }

    /** 兜底：全部收下、按入参顺序发号 */
    static SourceCollector.AddResult acceptAll(List<Document> docs) {
        int size = docs == null ? 0 : docs.size();
        return result(docs, sequentialNumbers(size));
    }

    /** 真实 Collector 场景的编号视图（1..n） */
    static List<Integer> sequentialNumbers(int size) {
        List<Integer> ids = new ArrayList<>(size);
        for (int i = 1; i <= size; i++) {
            ids.add(i);
        }
        return ids;
    }

    /** ids 中是否有被拒位置 */
    static boolean hasDropped(List<Integer> ids) {
        return ids != null && ids.stream().anyMatch(Objects::isNull);
    }
}
