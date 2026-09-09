package com.pfagent.agent.rag;

import org.springframework.ai.vectorstore.VectorStore;

/**
 * 向量库文件持久化接口（SP1 §4：VectorStore 边界收口）
 *
 * SimpleVectorStore 的 load(File)/save(File) 是实例方法、VectorStore 接口没有；
 * 把「加载 / 落盘」隔离到此内部接口，业务检索代码（SearchService 等）只面向
 * VectorStore 检索 API，不感知持久化细节。为将来向量库迁入 PostgreSQL（换用
 * 别的 VectorStore 实现）预留切换点。
 *
 * loadIfExists / save 均为幂等语义：文件不存在时 load 静默跳过；save 前自行确保
 * 父目录存在。接口对传入 VectorStore 不假设实现——具体实现按各自能力决定如何落地。
 */
public interface VectorStorePersistence {

    /** 持久化文件存在则加载到 store；不存在则跳过（返回时 store 为空库，等 DataLoader 构建） */
    void loadIfExists(VectorStore store, String path);

    /** 把 store 内容落盘到 path（父目录不存在会自动创建） */
    void save(VectorStore store, String path);
}
