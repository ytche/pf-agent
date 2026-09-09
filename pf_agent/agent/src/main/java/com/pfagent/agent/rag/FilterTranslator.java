package com.pfagent.agent.rag;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 逻辑过滤字段 → 扁平 metadata 键翻译（设计 §5.1 表）
 *
 * 工具层把用户意图转成"逻辑字段"（如 className/school/level），但向量库的
 * metadata 是扁平标量键（见 SpellChunkMapper.flattenMetadata），且 spell 的
 * className+level 是"组合语义"——同一个 className 在不同条件下翻译成不同键：
 *   - className + level → spell_level_<职业> = level
 *   - className 单独     → has_spell_<职业> = "true"
 * 本类集中维护这套映射，未知字段直接丢弃（返回的只含可执行的扁平条件），
 * 是否告警提示字段清单由检索工具层（RetrievalTools）负责。
 */
@Component
public class FilterTranslator {

    /**
     * 返回某模块可用的逻辑过滤字段名清单（供字段错误提示使用）
     *
     * @param module 数据模块；未知值返回空列表
     */
    public List<String> availableFields(String module) {
        return switch (module) {
            case "spell" -> List.of("title", "school", "subschool", "className", "level", "book");
            case "class" -> List.of("className", "archetypeName", "featureSubtype", "componentType", "book", "title");
            // 六个标准模块：统一行模型，book/componentType 通用 + title 条目名精确过滤（P0-B2）
            case "feat", "race", "trait", "equipment", "skill", "rule" -> List.of("book", "componentType", "title");
            default -> List.of();
        };
    }

    /**
     * 把逻辑过滤字段翻译为扁平条件列表
     *
     * @param module  数据模块；未知值返回空列表
     * @param filters 逻辑字段 → 期望值（可能为空）
     * @return 扁平 FilterField 列表；无有效条件时为空列表
     */
    public List<FilterField> translate(String module, Map<String, String> filters) {
        if (module == null || filters == null || filters.isEmpty()) {
            return List.of();
        }
        List<FilterField> out = new ArrayList<>();
        switch (module) {
            case "spell" -> translateSpell(filters, out);
            case "class" -> translateClass(filters, out);
            // 六个标准模块字段映射一致，共用一个翻译方法
            case "feat", "race", "trait", "equipment", "skill", "rule" -> translateStandard(filters, out);
            default -> {
                // 未知模块：无可用翻译
            }
        }
        return out;
    }

    /**
     * spell 模块：className/level 走组合逻辑，其余字段 1:1 映射。
     * level 无 className 时无意义（spell_level_<职业> 键必须带职业名），丢弃。
     */
    private void translateSpell(Map<String, String> filters, List<FilterField> out) {
        String className = filters.get("className");
        String level = filters.get("level");
        if (className != null && !className.isBlank()) {
            boolean hasLevel = level != null && !level.isBlank();
            // 原样拼键（含括号变体），与 SpellChunkMapper.flattenMetadata 的展开规则一致
            out.add(new FilterField(
                    hasLevel ? "spell_level_" + className : "has_spell_" + className,
                    hasLevel ? level : "true"));
        }
        for (Map.Entry<String, String> e : filters.entrySet()) {
            String field = e.getKey();
            if (field.equals("className") || field.equals("level")) {
                continue;
            }
            String key = switch (field) {
                case "title" -> "title";
                case "school" -> "school";
                case "subschool" -> "subschool";
                case "book" -> "book_abbreviation";
                default -> null; // 未知字段丢弃
            };
            if (key != null) {
                out.add(new FilterField(key, e.getValue()));
            }
        }
    }

    /** class 模块：全部 1:1 映射，无组合逻辑 */
    private void translateClass(Map<String, String> filters, List<FilterField> out) {
        for (Map.Entry<String, String> e : filters.entrySet()) {
            String key = switch (e.getKey()) {
                case "className" -> "class_name";
                case "archetypeName" -> "archetype_name";
                case "featureSubtype" -> "feature_subtype";
                case "componentType" -> "component_type";
                case "book" -> "book_abbreviation";
                case "title" -> "title";
                default -> null;
            };
            if (key != null) {
                out.add(new FilterField(key, e.getValue()));
            }
        }
    }

    /** 六个标准模块：book / componentType / title 三个通用字段 1:1 映射，无组合逻辑。
     *  title 走条目名精确匹配（eq），支持「LLM 已知确切条目名按名查」（P0-B2）。 */
    private void translateStandard(Map<String, String> filters, List<FilterField> out) {
        for (Map.Entry<String, String> e : filters.entrySet()) {
            String key = switch (e.getKey()) {
                case "book" -> "book_abbreviation";
                case "componentType" -> "component_type";
                case "title" -> "title";
                default -> null;
            };
            if (key != null) {
                out.add(new FilterField(key, e.getValue()));
            }
        }
    }
}
