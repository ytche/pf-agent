package com.pfagent.agent.rag;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * EntryResolver 单元测试（SP8c J6 Layer 0）
 *
 * 用临时 chunks.jsonl 验证：
 *  - 名归一解析：大小写不敏感、全半角 NFKC 归一、alias 命中、查无此名
 *  - 多义候选：跨模块同名返回多个候选；module 参数收窄
 *  - 三层链接：base_spell 基础/变体、prerequisites 正反查（解析不到的条目不输出）、
 *    职业环级表正反查
 *  - 开关关闭不建索引；文件缺失/单行损坏容错
 */
class EntryResolverTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @TempDir
    Path tempDir;

    /** 标题精确命中 + 别名/大小写/全半角归一命中 */
    @Test
    void resolveHitsTitleAndAliasWithNormalization() throws Exception {
        EntryResolver resolver = resolverWith(spellJsonl(), featJsonl(), classJsonl());

        // 标题精确命中
        List<EntryResolver.EntryRef> hits = resolver.resolve("火球术");
        assertThat(hits).hasSize(1);
        assertThat(hits.get(0).module()).isEqualTo("spell");
        assertThat(hits.get(0).chunkId()).isEqualTo("spell_001");

        // 别名命中（大小写不敏感）
        assertThat(resolver.resolve("fireball")).extracting(EntryResolver.EntryRef::chunkId)
                .containsExactly("spell_001");
        // 全半角 + 空白归一：全角大写 Fireball
        assertThat(resolver.resolve("ＦＩＲＥＢＡＬＬ")).extracting(EntryResolver.EntryRef::chunkId)
                .containsExactly("spell_001");
        // 查无此名
        assertThat(resolver.resolve("不存在的条目")).isEmpty();
    }

    /** 跨模块同名返回多义候选；module 参数收窄到唯一 */
    @Test
    void resolveAmbiguousAcrossModulesAndModuleFilter() throws Exception {
        EntryResolver resolver = resolverWith(spellJsonl(), featJsonl(), classJsonl());

        List<EntryResolver.EntryRef> hits = resolver.resolve("冲锋");
        assertThat(hits).hasSize(2);
        assertThat(resolver.resolve("冲锋", "feat")).extracting(EntryResolver.EntryRef::chunkId)
                .containsExactly("feat_900");
        assertThat(resolver.resolve("冲锋", "spell")).extracting(EntryResolver.EntryRef::chunkId)
                .containsExactly("spell_900");
    }

    /** base_spell 解析：变体 → 基础；基础 → 变体列表 */
    @Test
    void linksResolvesBaseSpellBothDirections() throws Exception {
        EntryResolver resolver = resolverWith(spellJsonl(), featJsonl(), classJsonl());

        EntryResolver.EntryLinks variantLinks = resolver.linksOf(resolver.resolve("火球术（神话）").get(0));
        assertThat(variantLinks.base()).isNotNull();
        assertThat(variantLinks.base().chunkId()).isEqualTo("spell_001");

        EntryResolver.EntryLinks baseLinks = resolver.linksOf(resolver.resolve("火球术").get(0));
        assertThat(baseLinks.base()).isNull();
        assertThat(baseLinks.variants()).extracting(EntryResolver.EntryRef::chunkId)
                .containsExactly("spell_002");
    }

    /** prerequisites 正查：能解析的条目输出、解析不到的条目不输出 */
    @Test
    void linksResolvesPrereqItemsAndOmitsUnresolved() throws Exception {
        EntryResolver resolver = resolverWith(spellJsonl(), featJsonl(), classJsonl());

        EntryResolver.EntryLinks links = resolver.linksOf(resolver.resolve("盾牌掩护").get(0));

        assertThat(links.references()).extracting(l -> l.target().chunkId())
                .contains("feat_001");                          // 闪避 可解析
        assertThat(links.references()).extracting(l -> l.target().chunkId())
                .doesNotContain("feat_404");                    // 不存在的条目：不输出
        // 属性/ BAB 类前置（ability/bab）不产生条目链接
        assertThat(links.references().stream().map(EntryResolver.EntryLink::note))
                .containsOnly("前置专长");
    }

    /** prerequisites 反查：被前置的条目能查到引用它的来源 */
    @Test
    void linksResolvesReversePrereq() throws Exception {
        EntryResolver resolver = resolverWith(spellJsonl(), featJsonl(), classJsonl());

        EntryResolver.EntryLinks links = resolver.linksOf(resolver.resolve("闪避").get(0));

        assertThat(links.referencedBy()).extracting(l -> l.target().chunkId())
                .containsExactly("feat_002");
        assertThat(links.referencedBy().get(0).note()).isEqualTo("前置专长");
    }

    /** 职业环级表：法术 → 职业（环级说明）；职业 → 引用它的法术 */
    @Test
    void linksResolvesSpellLevelBothDirections() throws Exception {
        EntryResolver resolver = resolverWith(spellJsonl(), featJsonl(), classJsonl());

        EntryResolver.EntryLinks spellLinks = resolver.linksOf(resolver.resolve("闪电束").get(0));
        assertThat(spellLinks.references()).extracting(l -> l.target().chunkId())
                .containsExactly("class_001");
        assertThat(spellLinks.references().get(0).note()).isEqualTo("3 环法术列表");

        EntryResolver.EntryLinks classLinks = resolver.linksOf(resolver.resolve("法师").get(0));
        assertThat(classLinks.referencedBy()).extracting(l -> l.target().chunkId())
                .containsExactly("spell_003");
    }

    /** 别名归一化静态方法：NFKC + 去空白 + 小写 */
    @Test
    void normalizeFoldsCaseWidthAndWhitespace() {
        assertThat(EntryResolver.normalize("ＦＩｒｅ　Ball")).isEqualTo(EntryResolver.normalize("fireball"));
        assertThat(EntryResolver.normalize(" 火球术 ")).isEqualTo("火球术");
    }

    /** 开关关闭：不建索引，resolve 返回空 */
    @Test
    void disabledResolverReturnsEmpty() throws Exception {
        EntryResolver resolver = resolverWith(spellJsonl(), featJsonl(), classJsonl());
        ReflectionTestUtils.setField(resolver, "enabled", false);

        assertThat(resolver.isEnabled()).isFalse();
        assertThat(resolver.resolve("火球术")).isEmpty();
        assertThat(resolver.findByChunkId("spell", "spell_001")).isNull();
    }

    /** 容错：模块文件缺失不抛异常，其余模块正常索引；损坏行跳过 */
    @Test
    void missingFileAndBrokenLineTolerated() throws Exception {
        EntryResolver resolver = new EntryResolver();
        ReflectionTestUtils.setField(resolver, "spellsPath", tempDir.resolve("missing.jsonl").toString());
        ReflectionTestUtils.setField(resolver, "classesPath", classJsonl().toString());
        ReflectionTestUtils.setField(resolver, "featPath", featJsonl().toString());
        ReflectionTestUtils.setField(resolver, "racePath", emptyFile().toString());
        ReflectionTestUtils.setField(resolver, "traitPath", emptyFile().toString());
        ReflectionTestUtils.setField(resolver, "equipmentPath", emptyFile().toString());
        ReflectionTestUtils.setField(resolver, "skillPath", emptyFile().toString());
        ReflectionTestUtils.setField(resolver, "rulePath", emptyFile().toString());
        ReflectionTestUtils.setField(resolver, "enabled", true);

        resolver.buildIndex();

        assertThat(resolver.resolve("法师")).hasSize(1);   // spell 缺失不影响其他模块
    }

    /** 损坏行容错：单行 JSON 损坏被跳过，同文件其余行正常入索引 */
    @Test
    void brokenLineSkippedAndRemainingRowsIndexed() throws Exception {
        Path spells = tempDir.resolve("spells-broken.jsonl");
        String good = objectMapper.writeValueAsString(spellRow("spell_001", "火球术", List.of(), null, null, null, List.of()));
        Files.writeString(spells, good + "\n{not-valid-json\n", StandardCharsets.UTF_8);
        EntryResolver resolver = resolverWith(spells, featJsonl(), classJsonl());

        assertThat(resolver.resolve("火球术")).hasSize(1);
    }

    /** base_spell 指向的 chunk 不在索引时退化为标题构造引用（title/chunkId 保留，不丢边） */
    @Test
    void baseSpellFallsBackToTitleRefWhenBaseChunkMissing() throws Exception {
        Path spells = tempDir.resolve("spells-orphan.jsonl");
        Path p = writeJsonl("spells-orphan", List.of(
                spellRow("spell_002", "火球术（神话）", List.of(), "spell_404", "火球术", "CRB", List.of())));
        assertThat(p).isEqualTo(spells);
        EntryResolver resolver = resolverWith(spells, featJsonl(), classJsonl());

        EntryResolver.EntryLinks links = resolver.linksOf(resolver.resolve("火球术（神话）").get(0));

        assertThat(links.base()).isNotNull();
        assertThat(links.base().chunkId()).isEqualTo("spell_404");
        assertThat(links.base().title()).isEqualTo("火球术");
    }

    /** 优先模块内仍多义时不硬解析：该前置边不输出 */
    @Test
    void prereqAmbiguousWithinPreferredModuleOmitsEdge() throws Exception {
        Map<String, Object> prereq = Map.of("raw", "x", "items", List.of(Map.of("type", "feat", "value", "同名专长")));
        List<Map<String, Object>> rows = List.of(
                standardRow("feat", "feat_010", "同名专长", List.of(), Map.of("prerequisites", Map.of("items", List.of()))),
                standardRow("feat", "feat_011", "同名专长", List.of(), Map.of("prerequisites", Map.of("items", List.of()))),
                standardRow("feat", "feat_012", "依赖者", List.of(), Map.of("prerequisites", prereq)));
        Path feats = writeJsonl("feats-ambig", rows);
        EntryResolver resolver = resolverWith(spellJsonl(), feats, classJsonl());

        assertThat(resolver.resolve("同名专长", "feat")).hasSize(2);
        EntryResolver.EntryLinks links = resolver.linksOf(resolver.resolve("依赖者").get(0));
        assertThat(links.references()).isEmpty();
    }

    /** 环级表缺 level 字段时关系说明退化为"职业法术列表" */
    @Test
    void spellLevelBlankLevelFallsBackToGenericNote() throws Exception {
        Path spells = writeJsonl("spells-nolevel", List.of(
                spellRow("spell_001", "火球术", List.of(), null, null, null, List.of(Map.of("class", "法师")))));
        EntryResolver resolver = resolverWith(spells, featJsonl(), classJsonl());

        EntryResolver.EntryLinks links = resolver.linksOf(resolver.resolve("火球术").get(0));

        assertThat(links.references()).hasSize(1);
        assertThat(links.references().get(0).note()).isEqualTo("职业法术列表");
    }

    /** SP8d：子串命中排序——精确 > 前缀 > 子串，同级短 title 优先；精确同名排最前（与 resolve 的边界区分） */
    @Test
    void substringSearchRanksExactPrefixAndSubstringWithShortTitleFirst() throws Exception {
        EntryResolver resolver = resolverWith(spellJsonl(), featJsonl(), classJsonl());

        // 精确同名（resolveEntry 等价路径）排最前，前缀命中短名优先
        assertThat(resolver.substringSearch("火球术")).extracting(EntryResolver.EntryRef::chunkId)
                .containsExactly("spell_001", "spell_002");
        // 纯前缀片段：火球术(3字) 在 火球术（神话）(7字) 前
        assertThat(resolver.substringSearch("火球")).extracting(EntryResolver.EntryRef::chunkId)
                .containsExactly("spell_001", "spell_002");
        // 术语含 title（双向：title 是术语前缀）也算前缀命中
        assertThat(resolver.substringSearch("强化火球术射程")).extracting(EntryResolver.EntryRef::chunkId)
                .containsExactly("spell_001");
        // 纯子串命中：仅 火球术（神话） 的 title 含"神话"
        assertThat(resolver.substringSearch("神话")).extracting(EntryResolver.EntryRef::chunkId)
                .containsExactly("spell_002");
        // 别名子串：Fireball 别名含 "fire"（大小写不敏感归一）
        assertThat(resolver.substringSearch("fire")).extracting(EntryResolver.EntryRef::chunkId)
                .containsExactly("spell_001");
        // 归一化：全角混用同命中
        assertThat(resolver.substringSearch("ＦＩＲＥ")).extracting(EntryResolver.EntryRef::chunkId)
                .containsExactly("spell_001");
    }

    /** SP8d：跨模块命中 + module 参数收窄 */
    @Test
    void substringSearchAcrossModulesAndModuleFilter() throws Exception {
        EntryResolver resolver = resolverWith(spellJsonl(), featJsonl(), classJsonl());

        assertThat(resolver.substringSearch("冲")).extracting(EntryResolver.EntryRef::chunkId)
                .containsExactlyInAnyOrder("spell_900", "feat_900");
        assertThat(resolver.substringSearch("冲", "feat")).extracting(EntryResolver.EntryRef::chunkId)
                .containsExactly("feat_900");
        assertThat(resolver.substringSearch("冲", "spell")).extracting(EntryResolver.EntryRef::chunkId)
                .containsExactly("spell_900");
    }

    /** SP8d：查无命中返回空；空术语返回空 */
    @Test
    void substringSearchNoHitReturnsEmpty() throws Exception {
        EntryResolver resolver = resolverWith(spellJsonl(), featJsonl(), classJsonl());

        assertThat(resolver.substringSearch("不存在的条目xyz")).isEmpty();
        assertThat(resolver.substringSearch("  ")).isEmpty();
    }

    /** SP8d：结果截断到 maxResults（pf.search.entry-resolver-max-results） */
    @Test
    void substringSearchCapsAtMaxResults() throws Exception {
        EntryResolver resolver = resolverWith(spellJsonl(), featJsonl(), classJsonl());
        ReflectionTestUtils.setField(resolver, "maxResults", 1);

        assertThat(resolver.substringSearch("火球")).hasSize(1);
        assertThat(resolver.substringSearch("火球").get(0).chunkId()).isEqualTo("spell_001");
    }

    /** SP8d：开关关闭时子串搜索返回空 */
    @Test
    void substringSearchDisabledReturnsEmpty() throws Exception {
        EntryResolver resolver = resolverWith(spellJsonl(), featJsonl(), classJsonl());
        ReflectionTestUtils.setField(resolver, "enabled", false);

        assertThat(resolver.substringSearch("火球")).isEmpty();
    }

    /** SP8d：单字术语默认上限 20 截断，且同级按短 title 在前 */
    @Test
    void singleCharTermCapsAtDefaultMaxResultsWithShortTitleFirst() throws Exception {
        List<Map<String, Object>> rows = new ArrayList<>();
        // 25 条 title 均以"火"开头（前缀同级），长度递增；默认 maxResults=20 截断
        for (int i = 1; i <= 25; i++) {
            rows.add(spellRow("spell_fire_" + i, "火" + "术".repeat(i), List.of(), null, null, null, List.of()));
        }
        Path spells = writeJsonl("spells-single-char", rows);
        EntryResolver resolver = resolverWith(spells, featJsonl(), classJsonl());

        List<EntryResolver.EntryRef> hits = resolver.substringSearch("火");

        assertThat(hits).hasSize(20);
        assertThat(hits.get(0).title()).isEqualTo("火术");
        assertThat(hits.get(19).title()).isEqualTo("火" + "术".repeat(20));
    }

    /** SP8d：同条目被多名命中时去重并取最高级别（别名精确 > title 子串） */
    @Test
    void sameEntryMatchedByMultipleNamesDedupKeepsHighestScore() throws Exception {
        Path spells = writeJsonl("spells-dedup", List.of(
                spellRow("spell_a", "大火球术", List.of("火球术"), null, null, null, List.of()),
                spellRow("spell_b", "火球术冲击波", List.of(), null, null, null, List.of())));
        EntryResolver resolver = resolverWith(spells, featJsonl(), classJsonl());

        List<EntryResolver.EntryRef> hits = resolver.substringSearch("火球术");

        // spell_a 经别名"火球术"精确命中(0)、经 title 子串命中(2)，去重后只出现一次且按精确级别排最前
        assertThat(hits).extracting(EntryResolver.EntryRef::chunkId)
                .containsExactly("spell_a", "spell_b");
    }

    /** SP8d：双向子串两个方向的命中级别各自正确——前缀(1) 与纯子串(2) 可区分 */
    @Test
    void bidirectionalMatchLevelsAreDistinguished() throws Exception {
        Path spells = writeJsonl("spells-direction", List.of(
                spellRow("spell_p", "火球术", List.of(), null, null, null, List.of()),
                spellRow("spell_s", "烈焰火球术", List.of(), null, null, null, List.of())));
        EntryResolver resolver = resolverWith(spells, featJsonl(), classJsonl());

        // 方向一（术语以 title 开头，术语含 title）：前缀命中；对手条目不含该完整术语，不命中
        assertThat(resolver.substringSearch("火球术强化版")).extracting(EntryResolver.EntryRef::chunkId)
                .containsExactly("spell_p");
        // 方向二（title 以术语开头 = 前缀；title 仅含术语 = 子串）：级别可区分且排序正确
        assertThat(resolver.substringSearch("火球")).extracting(EntryResolver.EntryRef::chunkId)
                .containsExactly("spell_p", "spell_s");
    }

    /** 构造 EntryResolver：写入三个模块 jsonl，其余模块指向空文件，触发 buildIndex */
    private EntryResolver resolverWith(Path spells, Path feats, Path classes) throws Exception {
        EntryResolver resolver = new EntryResolver();
        ReflectionTestUtils.setField(resolver, "spellsPath", spells.toString());
        ReflectionTestUtils.setField(resolver, "classesPath", classes.toString());
        ReflectionTestUtils.setField(resolver, "featPath", feats.toString());
        ReflectionTestUtils.setField(resolver, "racePath", emptyFile().toString());
        ReflectionTestUtils.setField(resolver, "traitPath", emptyFile().toString());
        ReflectionTestUtils.setField(resolver, "equipmentPath", emptyFile().toString());
        ReflectionTestUtils.setField(resolver, "skillPath", emptyFile().toString());
        ReflectionTestUtils.setField(resolver, "rulePath", emptyFile().toString());
        ReflectionTestUtils.setField(resolver, "enabled", true);
        resolver.buildIndex();
        return resolver;
    }

    private int emptyFileSeq = 0;

    private Path emptyFile() throws Exception {
        Path p = tempDir.resolve("empty-" + (emptyFileSeq++) + ".jsonl");
        Files.writeString(p, "", StandardCharsets.UTF_8);
        return p;
    }

    /** 法术 jsonl：火球术（含别名）+ 神话变体 + 闪电束（环级表）+ 同名"冲锋" */
    private Path spellJsonl() throws Exception {
        List<Map<String, Object>> rows = List.of(
                spellRow("spell_001", "火球术", List.of("Fireball"), null, null, null, List.of()),
                spellRow("spell_002", "火球术（神话）", List.of(), "spell_001", "火球术", "CRB", List.of()),
                spellRow("spell_003", "闪电束", List.of(), null, null, null,
                        List.of(Map.of("class", "法师", "level", 3))),
                spellRow("spell_900", "冲锋", List.of(), null, null, null, List.of()));
        return writeJsonl("spells", rows);
    }

    /** 专长 jsonl：闪避 + 盾牌掩护（prerequisites 含可解析/不可解析/属性项）+ 同名"冲锋" */
    private Path featJsonl() throws Exception {
        Map<String, Object> prereq = Map.of(
                "raw", "敏捷13，闪避，不存在的条目，基础攻击加值+1",
                "items", List.of(
                        Map.of("type", "ability", "ability", "敏捷", "value", 13),
                        Map.of("type", "feat", "value", "闪避"),
                        Map.of("type", "feat", "value", "不存在的条目"),
                        Map.of("type", "bab", "value", 1)));
        Map<String, Object> noPrereq = new LinkedHashMap<>();
        noPrereq.put("prerequisites", null);
        List<Map<String, Object>> rows = List.of(
                standardRow("feat", "feat_001", "闪避", List.of(), Map.of("prerequisites", Map.of("raw", "无", "items", List.of()))),
                standardRow("feat", "feat_002", "盾牌掩护", List.of(), Map.of("prerequisites", prereq)),
                standardRow("feat", "feat_900", "冲锋", List.of(), noPrereq));
        return writeJsonl("feats", rows);
    }

    /** 职业 jsonl：法师基础职业页 */
    private Path classJsonl() throws Exception {
        List<Map<String, Object>> rows = List.of(
                standardRow("class", "class_001", "法师", List.of("Wizard"), Map.of()));
        return writeJsonl("classes", rows);
    }

    private Map<String, Object> spellRow(String chunkId, String title, List<String> aliases,
            String baseChunkId, String baseTitle, String baseBook, List<Map<String, Object>> spellLevel) {
        Map<String, Object> row = new LinkedHashMap<>(standardRow("spell", chunkId, title, aliases,
                Map.of("spell_level", spellLevel)));
        row.put("base_spell_chunk_id", baseChunkId);
        row.put("base_spell_title", baseTitle);
        row.put("base_spell_book", baseBook);
        return row;
    }

    private Map<String, Object> standardRow(String category, String chunkId, String title,
            List<String> aliases, Map<String, Object> metadata) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("chunk_id", chunkId);
        row.put("doc_id", "page_" + chunkId);
        row.put("category", category);
        row.put("component_type", category);
        row.put("title", title);
        row.put("text", title + "正文");
        row.put("book_abbreviation", "CRB");
        row.put("book_name_cn", "核心规则书");
        row.put("book_name_en", "Core Rulebook");
        row.put("source_confidence", 1);
        row.put("aliases", aliases);
        row.put("metadata", metadata);
        row.put("extra", Map.of());
        return row;
    }

    private Path writeJsonl(String name, List<Map<String, Object>> rows) throws Exception {
        Path p = tempDir.resolve(name + ".jsonl");
        StringBuilder sb = new StringBuilder();
        for (Map<String, Object> row : rows) {
            sb.append(objectMapper.writeValueAsString(row)).append('\n');
        }
        Files.writeString(p, sb.toString(), StandardCharsets.UTF_8);
        return p;
    }
}
