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

    /** translateQuery 的翻译产物：eq（AND）+ or（OR 组）+ gte/lte（范围）三类扁平条件 */
    public record TranslatedQuery(List<FilterField> eq, List<OrGroup> or,
            List<FilterField> gte, List<FilterField> lte) {

        /** 是否完全不带可执行条件（调用方据此短路，不查询） */
        public boolean isEmpty() {
            return eq.isEmpty() && or.isEmpty() && gte.isEmpty() && lte.isEmpty();
        }

        /** 一个 OR 组：组内多个扁平条件任一命中（如同一字段的多个候选值） */
        public record OrGroup(List<FilterField> alternatives) {
        }
    }

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

    /**
     * 增强版翻译（SP8a J2）：把 MetadataSearchQuery 的 eq/or/gte/lte 全部翻译为扁平条件。
     *
     * 与 {@link #translate(String, Map)} 的差异：支持 OR 组与范围比较；spell 的
     * level 比较沿用组合键逻辑（作用于 spell_level_&lt;职业&gt;，职业名取 query.filters
     * 中的 className，缺失时该条件丢弃——工具层已提前返回"level 比较必须带 className"提示）。
     * 未知字段照旧丢弃（返回结果只含可执行条件），告警由工具层负责。
     */
    public TranslatedQuery translateQuery(String module, MetadataSearchQuery query) {
        List<FilterField> eq = translate(module, query.getFilters());
        List<TranslatedQuery.OrGroup> or = new ArrayList<>();
        if (query.getOrFilters() != null) {
            for (Map.Entry<String, List<String>> e : query.getOrFilters().entrySet()) {
                List<FilterField> alternatives = new ArrayList<>();
                for (String value : e.getValue()) {
                    FilterField condition = resolveCondition(module, e.getKey(), value, query.getFilters());
                    if (condition != null) {
                        alternatives.add(condition);
                        // spell 的 className 组合键：orFilters {className:[A,B]} 每值一个键，
                        // 单值 resolve 已拼 has_spell_<职业>，无需额外处理
                    }
                }
                if (!alternatives.isEmpty()) {
                    or.add(new TranslatedQuery.OrGroup(alternatives));
                }
            }
        }
        List<FilterField> gte = translateComparisons(module, query.getGte(), query.getFilters());
        List<FilterField> lte = translateComparisons(module, query.getLte(), query.getFilters());
        return new TranslatedQuery(eq, or, gte, lte);
    }

    /** 翻译 gte/lte 比较映射（单字段单值） */
    private List<FilterField> translateComparisons(String module, Map<String, String> comparisons,
            Map<String, String> contextFilters) {
        List<FilterField> out = new ArrayList<>();
        if (comparisons == null) {
            return out;
        }
        for (Map.Entry<String, String> e : comparisons.entrySet()) {
            FilterField condition = resolveCondition(module, e.getKey(), e.getValue(), contextFilters);
            if (condition != null) {
                out.add(condition);
            }
        }
        return out;
    }

    /**
     * 单字段单值翻译（供 or/gte/lte 复用）。
     *
     * spell 的 className/level 走组合语义（className → has_spell_&lt;职业&gt;；
     * level → spell_level_&lt;职业&gt;，职业名取 contextFilters 的 className，缺失丢弃）；
     * 其余字段按模块 1:1 映射；未知字段/未知模块返回 null。
     */
    private FilterField resolveCondition(String module, String field, String value, Map<String, String> contextFilters) {
        if (module == null || field == null || value == null) {
            return null;
        }
        return switch (module) {
            case "spell" -> resolveSpellCondition(field, value, contextFilters);
            case "class" -> resolveClassCondition(field, value);
            case "feat", "race", "trait", "equipment", "skill", "rule" -> resolveStandardCondition(field, value);
            default -> null;
        };
    }

    private FilterField resolveSpellCondition(String field, String value, Map<String, String> contextFilters) {
        if ("className".equals(field)) {
            return new FilterField("has_spell_" + value, "true");
        }
        if ("level".equals(field)) {
            String className = contextFilters == null ? null : contextFilters.get("className");
            if (className == null || className.isBlank()) {
                return null; // spell_level_<职业> 键必须带职业名，丢弃（工具层已提示）
            }
            return new FilterField("spell_level_" + className, value);
        }
        String key = switch (field) {
            case "title" -> "title";
            case "school" -> "school";
            case "subschool" -> "subschool";
            case "book" -> "book_abbreviation";
            default -> null;
        };
        return key == null ? null : new FilterField(key, value);
    }

    private FilterField resolveClassCondition(String field, String value) {
        String key = switch (field) {
            case "className" -> "class_name";
            case "archetypeName" -> "archetype_name";
            case "featureSubtype" -> "feature_subtype";
            case "componentType" -> "component_type";
            case "book" -> "book_abbreviation";
            case "title" -> "title";
            default -> null;
        };
        return key == null ? null : new FilterField(key, value);
    }

    private FilterField resolveStandardCondition(String field, String value) {
        String key = switch (field) {
            case "book" -> "book_abbreviation";
            case "componentType" -> "component_type";
            case "title" -> "title";
            default -> null;
        };
        return key == null ? null : new FilterField(key, value);
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
