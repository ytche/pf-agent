package com.pfagent.agent.rag;

import org.springframework.ai.document.Document;

/**
 * chunk 模型 → Spring AI Document 映射器
 *
 * 每个数据模块（法术/职业/…）实现一个 mapper，负责把该模块的
 * JSONL 行模型转成统一 metadata 约定的 Document，供向量化与来源追溯使用。
 *
 * 约定字段（PromptBuilder / ChatService 依赖）：
 *  - book_name_cn / book_abbreviation / book_name_en：来源书
 *  - tocPath：目录路径（供来源追溯与目录引导）
 *  - title / aliases：条目名与别名
 * 各模块专有字段（class_name、feature_subtype 等）一并放入 metadata，供后续结构化过滤。
 */
public interface ChunkMapper<T> {

    Document toDocument(T chunk);
}
