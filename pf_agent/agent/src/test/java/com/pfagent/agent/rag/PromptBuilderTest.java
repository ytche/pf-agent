package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * PromptBuilder 单元测试（v1.4 重写）
 *
 * 不再预检索注入文档：检索改由 LLM 通过工具驱动，system prompt 只承载
 * 角色 + 工具引导 + 输出约束（设计 §8 PromptBuilder 重写）：
 *  - 必须用检索工具、禁止凭记忆编造
 *  - Markdown 输出约束（禁 HTML、枚举用表格）
 *  - 引用来源、reportDataGap 指引、区分明确规则/推断
 */
class PromptBuilderTest {

    private final PromptBuilder promptBuilder = new PromptBuilder();

    /** 系统提示要求必须使用检索工具、禁止编造 */
    @Test
    void buildSystemPromptMandatesRetrievalAndBansFabrication() {
        String prompt = promptBuilder.buildSystemPrompt();

        assertThat(prompt).contains("必须使用提供的检索工具查找规则数据");
        assertThat(prompt).contains("禁止凭记忆编造规则");
    }

    /** 系统提示包含 Markdown 输出约束 */
    @Test
    void buildSystemPromptIncludesMarkdownOutputConstraint() {
        String prompt = promptBuilder.buildSystemPrompt();

        assertThat(prompt).contains("输出 Markdown");
        assertThat(prompt).contains("禁止输出 HTML");
        assertThat(prompt).contains("Markdown 表格");
    }

    /** 系统提示包含来源引用要求 */
    @Test
    void buildSystemPromptIncludesSourceCitationRequirement() {
        String prompt = promptBuilder.buildSystemPrompt();

        assertThat(prompt).contains("引用来源");
    }

    /** 系统提示包含 reportDataGap 工具指引 */
    @Test
    void buildSystemPromptIncludesReportDataGapGuidance() {
        String prompt = promptBuilder.buildSystemPrompt();

        assertThat(prompt).contains("reportDataGap");
        assertThat(prompt).contains("如实告知用户缺少相关知识");
    }

    /** 系统提示区分明确规则与推断 */
    @Test
    void buildSystemPromptDistinguishesExplicitRulesFromInference() {
        String prompt = promptBuilder.buildSystemPrompt();

        assertThat(prompt).contains("明确规则");
        assertThat(prompt).contains("推断内容");
    }

    /** 系统提示要求规则断言必须有检索依据 */
    @Test
    void buildSystemPromptRequiresRetrievalBasisForAssertions() {
        String prompt = promptBuilder.buildSystemPrompt();

        // AKN-003：回答中每条规则事实（施法方式/生命骰/豁免/法术位等）必须能在
        // 检索结果原文中找到依据；检索未提供的规则事实禁止凭记忆补全
        assertThat(prompt).contains("依据");
        assertThat(prompt).contains("禁止");
        assertThat(prompt).contains("补全");
        assertThat(prompt).contains("施法方式");
    }

    /** 系统提示要求职业核心机制以基础页为准 */
    @Test
    void buildSystemPromptDefersClassCoreMechanicsToBasePage() {
        String prompt = promptBuilder.buildSystemPrompt();

        // AKN-003：职业变体文本与基础职业页冲突时，以基础职业能力检索结果为准
        assertThat(prompt).contains("基础职业");
        assertThat(prompt).contains("变体");
        assertThat(prompt).contains("冲突");
    }

    /** 系统提示包含模块路由速查：升级/兼职指向 class、通用规则指向 rule、拿不准走 all */
    @Test
    void buildSystemPromptIncludesModuleRoutingHints() {
        String prompt = promptBuilder.buildSystemPrompt();

        // P0-B T2：治 easy-7/medium-0「兼职」被 LLM 误路由 rule
        assertThat(prompt).contains("兼职");
        assertThat(prompt).contains("角色升级");
        assertThat(prompt).contains("module:\"all\"");
        assertThat(prompt).contains("class");
    }

    /** 系统提示包含来源编号标注约束（SP4 D4）：句末 [#N]、编号只能取自工具返回、禁编造 */
    @Test
    void buildSystemPromptIncludesCitationNumberConstraint() {
        String prompt = promptBuilder.buildSystemPrompt();

        // SP4 D4：D3 语法 [#N]、工具返回文本是唯一编号来源、禁止编造编号
        assertThat(prompt).contains("[#N]");
        assertThat(prompt).contains("只能取自工具返回");
        assertThat(prompt).contains("禁止编造编号");
        assertThat(prompt).contains("reportDataGap");
    }
}
