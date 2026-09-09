package com.pfagent.agent.rag;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.vectorstore.SimpleVectorStore;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.stereotype.Component;

import java.io.File;

/**
 * SimpleVectorStore 的 {@link VectorStorePersistence} 默认实现
 *
 * VectorStore 接口本身无 load/save（SimpleVectorStore 的实例方法），此处下转实现类
 * 完成文件加载与落盘。当前工程全部向量库均为 SimpleVectorStore，故对其它实现不做
 * 文件持久化（debug 提示）。
 */
@Component
public class SimpleVectorStorePersistence implements VectorStorePersistence {

    private static final Logger log = LoggerFactory.getLogger(SimpleVectorStorePersistence.class);

    @Override
    public void loadIfExists(VectorStore store, String path) {
        if (!(store instanceof SimpleVectorStore simpleStore)) {
            log.debug("向量库实现 {} 不支持文件加载，跳过: {}", store.getClass().getSimpleName(), path);
            return;
        }
        File file = new File(path);
        if (!file.exists()) {
            log.info("[VectorStore] 未发现向量库文件 {}，等待 DataLoader 构建", path);
            return;
        }
        simpleStore.load(file);
        log.info("[VectorStore] 已从 {} 加载已有向量库", path);
    }

    @Override
    public void save(VectorStore store, String path) {
        if (!(store instanceof SimpleVectorStore simpleStore)) {
            log.debug("向量库实现 {} 不支持文件落盘，跳过: {}", store.getClass().getSimpleName(), path);
            return;
        }
        File file = new File(path);
        file.getParentFile().mkdirs();
        simpleStore.save(file);
    }
}
