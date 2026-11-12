package com.pfagent.agent.rag;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.util.json.schema.JsonSchemaGenerator;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * @Tool 方法生成的 function schema 必须自洽：所有 {@code $ref} 都要能在同一份
 * schema 文档内解析，不能有悬空引用。
 *
 * 背景：Spring AI 1.0.0-M6 的 JsonSchemaGenerator.generateForMethodInput 对每个参数
 * 单独生成 schema 再内联进 properties。victools 遇到同一泛型类型在一个参数对象内出现
 * ≥2 次时，会把它提升为文档根的 {@code $defs} 并写 {@code $ref:"#/$defs/..."}，但
 * $defs 实际被嵌在该参数节点下，引用因此悬空——DeepSeek 对这类 schema 直接 400
 * （Pointer '/$defs/Map_String.String_' does not exist）。本测试用与运行时同源的
 * 生成器（{@link JsonSchemaGenerator#generateForMethodInput}）覆盖全部 @Tool 方法，
 * 防止同类回归；并单独覆盖含 Map 字段的 searchByMetadata / listEntries。
 */
class RetrievalToolsToolSchemaTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Test
    void allToolSchemasHaveOnlyResolvableRefs() throws Exception {
        List<String> toolNames = new ArrayList<>();
        for (Method method : RetrievalTools.class.getDeclaredMethods()) {
            if (!method.isAnnotationPresent(Tool.class)) {
                continue;
            }
            toolNames.add(method.getName());
            JsonNode schema = MAPPER.readTree(JsonSchemaGenerator.generateForMethodInput(method));
            assertThat(danglingRefs(schema))
                    .as("@Tool %s 的 schema 存在悬空 $ref", method.getName())
                    .isEmpty();
        }
        assertThat(toolNames).contains("searchByMetadata", "listEntries");
    }

    @Test
    void searchByMetadataSchemaInlinesMapsWithoutDefs() throws Exception {
        Method method = RetrievalTools.class.getMethod("searchByMetadata", String.class, MetadataSearchQuery.class);
        JsonNode schema = MAPPER.readTree(JsonSchemaGenerator.generateForMethodInput(method));

        assertThat(danglingRefs(schema)).isEmpty();
        // 修复的核心：不再出现 $defs（悬空引用的来源），也没有任何 $ref
        assertThat(collectRefs(schema)).as("searchByMetadata schema 不应含 $ref").isEmpty();
        assertThat(findKeys(schema, "$defs")).as("searchByMetadata schema 不应含 $defs").isEmpty();
        JsonNode query = schema.at("/properties/query");
        assertThat(query.at("/properties/filters").get("type").asText()).isEqualTo("object");
        assertThat(query.at("/properties/gte").get("type").asText()).isEqualTo("object");
        assertThat(query.at("/properties/lte").get("type").asText()).isEqualTo("object");
        assertThat(query.at("/properties/orFilters").get("type").asText()).isEqualTo("object");
        assertThat(query.at("/properties/allowBroadQuery").get("type").asText()).isEqualTo("boolean");
    }

    @Test
    void listEntriesSchemaInlinesMapsWithoutDefs() throws Exception {
        Method method = RetrievalTools.class.getMethod("listEntries", String.class, ListEntriesQuery.class);
        JsonNode schema = MAPPER.readTree(JsonSchemaGenerator.generateForMethodInput(method));

        assertThat(danglingRefs(schema)).isEmpty();
        assertThat(collectRefs(schema)).as("listEntries schema 不应含 $ref").isEmpty();
        assertThat(findKeys(schema, "$defs")).as("listEntries schema 不应含 $defs").isEmpty();
        JsonNode query = schema.at("/properties/query");
        assertThat(query.at("/properties/filters").get("type").asText()).isEqualTo("object");
        assertThat(query.at("/properties/orFilters").get("type").asText()).isEqualTo("object");
        assertThat(query.at("/properties/allowBroadQuery").get("type").asText()).isEqualTo("boolean");
    }

    /** 收集 schema 中所有引用但无法在文档内解析的 $ref（JSON Pointer 解析）。 */
    private static List<String> danglingRefs(JsonNode schema) {
        List<String> dangling = new ArrayList<>();
        for (String ref : collectRefs(schema)) {
            if (!ref.startsWith("#")) {
                continue;
            }
            String pointer = ref.substring(1);
            if (pointer.isEmpty()) {
                continue;
            }
            if (schema.at(pointer).isMissingNode()) {
                dangling.add(ref);
            }
        }
        return dangling;
    }

    /** 深度遍历收集所有 "$ref" 值。 */
    private static Set<String> collectRefs(JsonNode node) {
        Set<String> refs = new LinkedHashSet<>();
        walk(node, entry -> {
            if ("$ref".equals(entry.getKey()) && entry.getValue().isTextual()) {
                refs.add(entry.getValue().asText());
            }
        });
        return refs;
    }

    /** 深度遍历收集指定键的所有取值。 */
    private static List<JsonNode> findKeys(JsonNode node, String key) {
        List<JsonNode> found = new ArrayList<>();
        walk(node, entry -> {
            if (key.equals(entry.getKey())) {
                found.add(entry.getValue());
            }
        });
        return found;
    }

    private static void walk(JsonNode node, java.util.function.Consumer<java.util.Map.Entry<String, JsonNode>> visitor) {
        if (node.isObject()) {
            node.fields().forEachRemaining(visitor);
            node.elements().forEachRemaining(child -> walk(child, visitor));
        }
        else if (node.isArray()) {
            node.elements().forEachRemaining(child -> walk(child, visitor));
        }
    }
}
