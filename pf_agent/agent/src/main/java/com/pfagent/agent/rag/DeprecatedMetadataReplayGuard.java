package com.pfagent.agent.rag;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

/**
 * 退役配置防误用闸口（DVG-001）：旧 {@code pf.stores.metadata-replay=true} fail-fast。
 *
 * SpellMetadataReplayTool 已彻底删除（2026-11-11），向量库唯一写路径为
 * 「数据侧 chunks.jsonl → Java DataLoader 全量重灌」（手册见 docs/DEPLOYMENT.md）。
 * 历史部署命令、环境变量或旧文档可能仍带 replay=true——本闸口长期保留：
 * 仅旧配置显式为 true 时装配，最高优先级先于任一 DataLoader 执行并终止启动，
 * 防「以为迁移已执行」的错觉；配置缺失或 false 时不装配，零行为变化。
 * 只读：不读取或修改 store，不调用 Mapper，不执行任何迁移。
 */
@Component
@ConditionalOnProperty(name = "pf.stores.metadata-replay", havingValue = "true")
@Order(Ordered.HIGHEST_PRECEDENCE)
public class DeprecatedMetadataReplayGuard implements CommandLineRunner {

    @Override
    public void run(String... args) {
        throw new IllegalStateException(
                "SpellMetadataReplayTool 已删除，pf.stores.metadata-replay=true 不再受支持。\n"
                        + "请将该配置移除或设为 false，并按 docs/DEPLOYMENT.md 的 chunks 全量重灌流程处理；\n"
                        + "不要直接修改 vector_store JSON。");
    }
}
